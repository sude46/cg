import json 
import logging 
import threading
import time
from  typing import Callable,Dict,List
from utils.redis_util import RedisClient

logger=logging.getLogger(__name__)

class RedisEventBus:
    '''
    基于Redis  ltributList 的持久化事件总线
    -生产者：Lpush事件到队列
    -学校消费者：后台线程BRPOP取事件，分发到订阅者
    -进程重启不丢事件（Redis持久化）
    '''
    _instance=None
    _lock=threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance=super().__new__(cls)
                    cls._instance._subscribers={}
                    cls._instance._running=False
                    cls._instance._consumer_thread=None
                    cls._instance._redis_key='event_bus:queue'
        return cls._instance
            
    def subscribe(self,event_name:str,handler:Callable):
        '''订阅事件'''
        if event_name not in self._subscribers:
            self._subscribers[event_name]=[]
        self._subscribers[event_name].append(handler)
        logger.info(f'事件订阅注册:{event_name}->{handler.__name__}')

    def publish(self,event_name:str,payload:dict):
        '''
        发布事件：LPUSH到Redis List ,立即返回
        不等待消费者处理，避免面阻塞主流程
        '''
        event={
            "event":event_name,
            "payload":payload,
            "timestamp":time.time(),
            "retry_count":0
        }
        try:
            conn=RedisClient.get_conn(for_write=True)
            if not conn:
                logger.error("Redis 未连接，事件丢失")
                return 
            conn.lpush(self._redis_key,json.dumps(event))
            logger.debug(f"事件已入队：{event_name}")
        except Exception as e:
            logger.error(f'事件入队失败：{event_name},error:{e}')

    def _consume(self):
        """消费者线程：BRPOP取事件并分发"""
        while self._running:
            try:
                conn=RedisClient.get_conn(for_write=False)
                if not conn:
                    time.sleep(1)
                    continue

                #BRPOP阻塞等待，超时1秒（便于检查——runing状态）
                result=conn.brpop(self._redis_key,timeout=1)
                if not result:
                    continue
                _,event_json=result
                event=json.loads(event_json)
                event_name=event["event"]
                payload=event["payload"]

                handlers=self._subscribers.get(event_name,[])
                if not handlers:
                    logger.warning(f"无订阅者：{event_name}")
                    continue
                for handler in handlers:
                    try:
                        handler(payload)
                        logger.debug(f"事件处理成功：{event_name}->{handler.__name__}")
                    except Exception as e:
                        logger.error(f"事件处理失败:{event_name}->{handler.__name__}:{e}")
                        #失败重试：最多3次，超过则丢弃（或进入死信队列）
                        event["retry_count"]=event.get("retry_count",0)+1
                        if event["retry_count"]<3:
                            conn.lpush(self._redis_key,json.dumps(event))
                            logger.info(f"事件重试入队：{event_name},retry={event['retry_count']}")

            except Exception as e:
                logger.error(f"消费者线程异常：{e}")
                time.sleep(1)
    def start(self):
        '''启动消费者线程'''
        if self._running:
            return 
        self._running=True
        self._consumer_thread=threading.Thread(target=self._consume,daemon=True)
        self._consumer_thread.start()
        logger.info("EventBus消费者线程已启动")
    
    def stop(self):
        """停止消费者线程"""
        self._running = False
        if self._consumer_thread:
            self._consumer_thread.join(timeout=5)
            logger.info("EventBus 消费者线程已停止")
event_bus = RedisEventBus()

    


