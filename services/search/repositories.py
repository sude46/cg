'''
搜索仓储层
职责：业务规则过滤：与数据Repository对齐
'''
import logging
from typing import List,Dict,Any,Optional,Tuple
from services.search.document import PostDocument

logger=logging.getLogger(__name__)

class PostSearchRepository:
    '''
    帖子搜索仓储
    对应app/posts/repositories.py，但操作ES非Mysql
    关键原则：和数据库Repositories保持一致的过滤逻辑
    -数据库guolv is_deleted=False，这里也要过滤
    -数据库过滤is_published=True,这里也要过滤
    '''
    @classmethod
    def get_by_id(cls,post_id:int):
        '''
        根据Id获取帖子，自动过滤已删除
        '''

        doc=PostDocument.get(post_id)
        if doc and not doc.get('is_deleted'):
            return doc
        return None
    @classmethod
    def list_by_user(cls,user_id:int,page:int=1,per_page:int=20):
        return PostDocument.search(
            query="",
            page=page,
            per_page=per_page,
            filters={'user_id':user_id},
            sort_by='time'
        )
    @classmethod
    def search(cls,query:str="",page:int=1,per_page:int=20,user_id:Optional[int]=None,sort_by:str='relevance'):
        filters={'user_id':user_id} if user_id else None
        return PostDocument.search(
            query=query,
            page=page,
            per_page=per_page,
            filters=filters,
            sort_by=sort_by
        )
