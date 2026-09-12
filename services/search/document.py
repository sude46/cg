'''
ES文档模型定义
职责：索引结构、字段映射、基础CRUD
'''
import logging
from datetime import datetime
from typing import Any

from core.es_client import es_client
from elastic_transport import ConnectionError as ESConnectionError
from elastic_transport import ConnectionTimeout as ESConnectionTimeout
from elastic_transport import TransportError as ESTransportError
from elasticsearch import NotFoundError
from elasticsearch.exceptions import ApiError as ESApiError
from services.search.config import SearchConfig

logger=logging.getLogger(__name__)


class SearchBackendError(Exception):
    """Elasticsearch 后端不可用或调用失败（供上层熔断降级）"""

class PostDocument:
    '''
    帖子文档模型
    对应ES中的post索引
    '''
    @classmethod
    def get_index_name(cls):
        '''获取索引名'''
        return SearchConfig.get_index_name('posts')

    #字段映射
    MAPPINGS={
        'properties':{
            'id':{'type':'integer'},
            'user_id':{'type':'integer'},
            'user_name':{
                'type':'text',
                'fields':{'keyword':{'type':'keyword'}}
            },
            'content':{
                'type':'text',
                'analyzer':'ik_max_word',
                'search_analyzer':'ik_smart'
            },
            # 自动补全专用字段：IK + edge_ngram 建索引，ik_smart 查询
            'suggest':{
                'type':'text',
                'analyzer':'ik_edge_ngram',
                'search_analyzer':'ik_smart'
            },
            'image_url':{'type':'keyword'},
            'like_count':{'type':'integer'},
            'comment_count':{'type':'integer'},
            'created_at':{'type':'date'},
            'is_published':{'type':'boolean'},
            'is_deleted':{'type':'boolean'},
            'hot_score':{'type':'float'}
        }
    }

    @classmethod
    def create_index(cls):
        '''创建索引（如果不存在）'''
        if not es_client.is_available():
            return False
        index_name=cls.get_index_name()
        try:
            if es_client.client.indices.exists(index=index_name):
                logger.info(f'索引:{index_name}已存在')
                return True
            body={
                **SearchConfig.INDEX_SETTINGS,
                'mappings':cls.MAPPINGS
            }
            es_client.client.indices.create(
                index=index_name,
                body=body
            )
            logger.info(f'索引:{index_name}创建成功')
            return True
        except Exception as e:
            logger.error(f'索引:{index_name}创建失败:{e}')
            return False

    @classmethod
    def delete_index(cls):
        '''删除索引 （危险操作)'''
        if not es_client.is_available():
            return True
        index_name=cls.get_index_name()
        try:
            es_client.client.indices.delete(index=index_name,ignore=[404])
            logger.info(f'索引{index_name}删除成功')
            return True
        except Exception as e:
            logger.error(f'索引{index_name}删除失败:{e}')
            return False
    @classmethod
    def index(cls, doc_id: int, document: dict[str, Any]) -> bool:
        """
        索引文档（添加或更新）

        Args:
            doc_id: 文档ID（对应帖子ID）
            document: 文档内容
        """
        if not es_client.is_available():
            return False

        try:
            # 日期格式转换
            doc = document.copy()
            if isinstance(doc.get('created_at'), datetime):
                doc['created_at'] = doc['created_at'].isoformat()
            # 补全字段：与正文同源，调用方无需感知
            if doc.get('content'):
                doc['suggest'] = doc['content']

            es_client.client.index(
                index=cls.get_index_name(),
                id=doc_id,
                document=doc
            )
            return True

        except Exception as e:
            logger.error(f"索引文档失败: {e}")
            return False

    @classmethod
    def get(cls, doc_id: int) -> dict[str, Any] | None:
        """根据ID获取文档"""
        if not es_client.is_available():
            return None

        try:
            result = es_client.client.get(index=cls.get_index_name(), id=doc_id)
            return result['_source']
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"获取文档失败: {e}")
            return None

    @classmethod
    def update(cls, doc_id: int, document: dict[str, Any]) -> bool:
        """部分更新文档"""
        if not es_client.is_available():
            return False

        try:
            # 正文变更时同步维护补全字段
            if document.get('content'):
                document = {**document, 'suggest': document['content']}
            es_client.client.update(
                index=cls.get_index_name(),
                id=doc_id,
                doc=document
            )
            return True
        except NotFoundError:
            logger.warning(f"文档 {doc_id} 不存在，无法更新")
            return False
        except Exception as e:
            logger.error(f"更新文档失败: {e}")
            return False

    @classmethod
    def delete(cls, doc_id: int) -> bool:
        """
        删除文档（标记删除，非物理删除）
        物理删除用 delete_by_id，但我们推荐标记删除
        """
        return cls.update(doc_id, {"is_deleted": True})

    @classmethod
    def suggest(cls, prefix: str, size: int = 10) -> list[str]:
        """前缀补全建议：查询专用 suggest 字段（edge_ngram 建索引，ik_smart 查询）。

        ES 不可用/索引未就绪时优雅返回空，不抛错。
        """
        prefix = (prefix or '').strip()
        if not prefix:
            return []
        client = es_client.client
        if client is None:
            return []
        try:
            body = {
                "size": max(1, min(50, size)),
                "_source": ["content"],
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"is_deleted": False}},
                            {"term": {"is_published": True}}
                        ],
                        "must": [
                            {"match": {"suggest": {"query": prefix}}}
                        ]
                    }
                }
            }
            result = client.search(
                index=cls.get_index_name(),
                body=body
            )
            suggestions = []
            seen = set()
            for hit in result["hits"]["hits"]:
                content = ((hit.get("_source") or {}).get("content") or "").strip()
                if content and content not in seen:
                    seen.add(content)
                    suggestions.append(content[:50])
            return suggestions
        except Exception as e:
            logger.error(f"搜索建议失败: {e}")
            return []

    @classmethod
    def search(
        cls,
        query: str,
        page: int = 1,
        per_page: int = 20,
        filters: dict[str, Any] | None = None,
        sort_by: str = "relevance"
    ) -> tuple[list[dict[str, Any]], int]:
        """
        搜索文档

        Args:
            query: 搜索关键词
            page: 页码
            per_page: 每页数量
            filters: 额外过滤条件
            sort_by: 排序方式 relevance/time/hot

        Returns:
            (结果列表, 总数)
        """
        client = es_client.client
        if client is None:
            raise SearchBackendError("Elasticsearch 客户端不可用")

        try:
            # 构建查询
            must_conditions = [
                {"term": {"is_deleted": False}},
                {"term": {"is_published": True}}
            ]

            # 添加用户ID过滤
            if filters and filters.get('user_id'):
                must_conditions.append(
                    {"term": {"user_id": filters['user_id']}}
                )

            # 搜索词
            if query and query.strip():
                must_conditions.append({
                    "multi_match": {
                        "query": query,
                        "fields": ["content^3", "user_name"],  # content权重更高
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                })

            # 排序
            if sort_by == "time":
                sort = [{"created_at": {"order": "desc"}}]
            elif sort_by == "hot":
                sort = [{"hot_score": {"order": "desc"}}]
            else:  # relevance
                sort = ["_score", {"created_at": {"order": "desc"}}]

            # 构建完整查询
            search_body = {
                "query": {
                    "bool": {
                        "must": must_conditions
                    }
                },
                "sort": sort,
                "from": (page - 1) * per_page,
                "size": per_page
            }

            result = client.search(
                index=cls.get_index_name(),
                body=search_body
            )

            hits = result["hits"]["hits"]
            total = result["hits"]["total"]["value"]

            # 提取_source
            posts = [hit["_source"] for hit in hits]
            return posts, total

        except (ESConnectionError, ESConnectionTimeout, ESTransportError, ESApiError) as e:
            logger.error(f"搜索失败: {e}")
            raise SearchBackendError(f"Elasticsearch 查询失败: {e}") from e
