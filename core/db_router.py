import logging
import random

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger=logging.getLogger(__name__)

class MasterSlaveRouter:
    _instance=None

    def __new__(cls):
        if cls._instance is None:
            cls._instance=super().__new__(cls)
            cls._instance.master_engine=None
            cls._instance.replica_engines=[]
            cls._instance._replica_idx=0
        return cls._instance

    def init_app(self,app):
        #主库
        self.master_engine=app.extensions['sqlalchemy'].db.engine

        #从库
        for bind_key,uri in app.config.get('SQLALCHEMY_BINDS',{}).items():
            if 'replica' in bind_key or 'slave' in bind_key or 'read' in bind_key:
                engine=create_engine(
                    uri,
                    pool_pre_ping=True,  #连接前ping ,防断连
                    pool_recycle=3600,  #连接池回收时间，防止数据库断连
                    pool_size=5,
                    max_overflow=10
                )
                self.replica_engines.append({
                    'key':bind_key,
                    'engine':engine,
                    'healthy':True,
                    'fail_count':0
                })
        logger.info(f'DB路由初始化：主库*1，从库*{len(self.replica_engines)}')

    def get_replica(self,strategy='round_robin'):
        healthy=[r for r in self.replica_engines if r['healthy']]
        if not healthy:
            return None
        if strategy=='random':
            return random.choice(healthy)
        else:
            idx=self._replica_idx%len(healthy)
            self._replica_idx+=1
            return healthy[idx]
    def mark_replica_failure(self,replica_key):
        for r in self.replica_engines:
            if r['key']==replica_key:
                r['fail_count']+=1
                if r['fail_count']>=3:
                    r['healthy']=False
                    logger.warning(f'标记从库{replica_key}为不健康')
                break
    def get_session(self,for_write=False):
        if for_write:
            return self.master_engine
        replica=self.get_replica()
        if replica:
            Session=sessionmaker(bind=replica['engine'])
            return Session()
        else:
            logger.warning('没有可用的从库，使用主库')
            return self.master_engine

db_router=MasterSlaveRouter()
