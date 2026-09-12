import logging
from datetime import UTC
from typing import Any

from services.search.document import PostDocument
from services.search.repositories import PostSearchRepository

logger=logging.getLogger(__name__)
class PostSearchService:
    '''
    帖子搜索fuwu
    这个类不直接操作ES，而是调用PostSearchRepository
    '''
    @classmethod
    def index_post(cls,post_data:dict[str,Any]):
        '''
        搜索帖子（双写同步调用)
        Args:
            post_data: 帖子数据字典，包含：
                - id: 帖子ID
                - content: 内容
                - user_id: 用户ID
                - username: 用户名
                - created_at: 创建时间
                - ...其他字段
        '''
        #计算机热度分数
        post_data['hot_score']=cls._calculate_hot_score(post_data)
        #兜底默认值：查询侧强制过滤 is_deleted=False / is_published=True
        post_data['is_deleted']=post_data.get('is_deleted',False)
        post_data['is_published']=post_data.get('is_published',True)
        return PostDocument.index(post_data['id'], post_data)
    @classmethod
    def update_post(cls,post_id:int,**fields):
        '''更新帖子'''
        return PostDocument.update(post_id,fields)

    @classmethod
    def delete_post(cls,post_id:int):
        '''删除帖子'''
        return PostDocument.delete(post_id)
    @staticmethod
    def search(query:str,page:int=1,per_page:int=20,user_id:int | None=None,sort_by:str='relevance'):
        '''搜索帖子（主接口）'''
        posts,total=PostSearchRepository.search(
            query=query,
            page=page,
            per_page=per_page,
            user_id=user_id,
            sort_by=sort_by
        )
        total_pages=(total+per_page-1)//per_page if total>0 else 1
        return {
            'items':posts,
            'total':total,
            'pagination':{
                'page':page,
                'per_page':per_page,
                'total':total,
                'total_pages':max(1,total_pages),
                'has_next':page<total_pages,
                'has_prev':page>1
            }
        }
    @classmethod
    def reindex_all(cls,fetch_func,batch_size:int=100):
        '''
        全量重建索引
        Args:
            fetch_func: 获取数据的函数，接收(offset, limit)返回帖子列表
            batch_size: 批次大小

        Returns:
            (成功数, 失败数)

        '''
        #删除旧索引
        PostDocument.delete_index()
        PostDocument.create_index()
        success=failed=0
        offset=0
        while True:
            #调用外部传入的获取函数
            posts=fetch_func(offset,batch_size)
            if not posts:
                break
            for post in posts:
                try:
                    if cls.index_post(post):
                        success+=1
                    else:
                        failed+=1
                except Exception as e:
                    logger.error(f"索引帖子失败:{e}")
                    failed+=1
            offset+=batch_size
            logger.info(f"已处理 {offset} 条帖子，成功 {success} 条，失败 {failed} 条")
        logger.info(f"重建索引完成，总成功 {success} 条，总失败 {failed} 条")
        return success,failed
    @staticmethod
    def _calculate_hot_score(post_data:dict[str,Any])->float:
        '''
        计算帖子热度分数
        算法：点赞 + 评论*2 + 时间衰减
        '''
        from datetime import datetime

        like_count=post_data.get('like_count',0)
        comment_count=post_data.get('comment_count',0)
        score=like_count+comment_count*2
        created_at=post_data.get('created_at')
        if created_at:
            if isinstance(created_at,str):
                created_at=datetime.fromisoformat(created_at.replace('Z','+00:00'))
            if created_at.tzinfo is None:
                created_at=created_at.replace(tzinfo=UTC)
            hours_since=(datetime.now(UTC)-created_at).total_seconds()/3600
            #24小时内的新帖有加成
            time_bonus=max(0,24-hours_since)*10

        return score+time_bonus


