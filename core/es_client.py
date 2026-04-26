import logging
from typing import Optional
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError,ConnectionError
from config import get_config


logger=logging.getLogger(__name__)

class ESClient:
    '''
    ES客户端单例
    职责：连接管理，原始操作封装
    '''
    _instance:Optional['ESClient']=None
    _es:Optional['Elasticsearch']=None

    def __new__(cls):
        if cls._instance is None:
            cls._instance=super().__new__(cls)
        return cls._instance
    def connect(self,app_config:dict=None):
        '''建立连接'''
        if app_config is None:
            config=get_config()
            es_enabled=config.ELASTICSEARCH_ENABLED
            es_hosts=config.ES_HOSTS_LIST
            es_timeout=config.ELASTICSEARCH_TIMEOUT
        else:
            es_enabled=app_config.get('ELASTICSEARCH_ENABLED',True)
            hosts=app_config.get('ELASTICSEARCH_HOSTS','http://localhost:9200')
            es_hosts=hosts if isinstance(hosts,list) else [h.strip() for h in hosts.split(",") if h.strip()]
            es_timeout=app_config.get('ELASTICSEARCH_TIMEOUT',30)
        
        if not es_enabled:
            logger.info('ES已经禁用，跳过连接')
            return False
        try:
            self._es=Elasticsearch(
                es_hosts,
                timeout=es_timeout
            )
            if self._es.ping():
                info=self._es.info()
                logger.info(f'ES连接成功:{info['version']['number']}')
                return True
            else:
                logger.warning ('ES连接失败，ping不通')
                self._es=None
                return False
        except Exception as e:
            logger.error(f'ES连接异常:{e}')
            self._es=None
            return False
    
    @property
    def client(self):
        '''获取原始客户端'''
        if self._es is None:
            self.connect()
        return self._es
    def is_available(self):
        '''检查连接是否可用'''
        if self._es is None:
            return False
        try:
            return self._es.ping()
        except ConnectionError:
            return False
    def close(self):
        '''关闭连接'''
        if self._es is not None:
            self._es.transport.close()
            self._es=None

es_client=ESClient()