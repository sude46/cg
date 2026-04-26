'''
搜索服务包
统一暴露接口，外部只导入这个模块
'''
from core.es_client import es_client
from services.search.document import PostDocument
from services.search.repositories import PostSearchRepository
from services.search.services import PostSearchService

__all__=[
    'es_client',    
    'PostDocument',
    'PostSearchRepository',
    'PostSearchService'
]
