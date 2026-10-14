import json
import logging
import threading
import time
from collections.abc import Callable

from core.metrics import (
    EVENT_BUS_DEAD_LETTER_LENGTH,
    EVENT_BUS_EVENTS,
    EVENT_BUS_QUEUE_LENGTH,
)
from utils.redis_util import RedisClient

logger=logging.getLogger(__name__)

class RedisEventBus:
    '''
    基于 Redis List 的事件总线

    - 生产者：LPUSH 事件到队列，立即返回，不阻塞主流程
    - 消费者：后台线程 BRPOP 取事件，分发到订阅者（单进程内单线程）
    - 失败处理：整条事件重试(最多 MAX_RETRY 次)；无订阅者/解析失败/重试耗尽 -> 死信队列

    限制(待 P1 改造)：BRPOP 弹出即删除、处理中没有 ack，进程在处理中崩溃会丢该条事件。
    死信队列(event_bus:dead_letter)只保存"无法处理"的消息，真正的 at-least-once 需要
    Redis Stream consumer group 或 BRPOPLPUSH + processing list + ack。
    '''
    _instance=None
    _lock=threading.Lock()

    MAX_RETRY=3            #同一条事件最多重试次数
    PUBLISH_RETRIES=3      #生产端入队失败重试次数
    PUBLISH_RETRY_DELAY=0.05

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance=super().__new__(cls)
                    cls._instance._subscribers={}
                    cls._instance._running=False
                    cls._instance._consumer_thread=None
                    cls._instance._redis_key='event_bus:queue'
                    cls._instance._dead_letter_key='event_bus:dead_letter'
                    cls._instance._app=None
        return cls._instance

    def subscribe(self,event_name:str,handler:Callable):
        '''订阅事件'''
        if event_name not in self._subscribers:
            self._subscribers[event_name]=[]
        self._subscribers[event_name].append(handler)
        logger.info(f'事件订阅注册:{event_name}->{handler.__name__}')

    def publish(self,event_name:str,payload:dict)->bool:
        '''
        发布事件：LPUSH 到 Redis List，立即返回。
        入队失败重试 PUBLISH_RETRIES 次，仍失败则打指标 + error 日志（不再静默），返回 False。
        '''
        event={
            "event":event_name,
            "payload":payload,
            "timestamp":time.time(),
            "retry_count":0
        }
        # 注入 trace context，消费端可续接同一条链路
        try:
            from opentelemetry.propagate import inject
            carrier={}
            inject(carrier)
            if carrier:
                event["_otel"]=carrier
        except Exception:
            pass

        last_exc=None
        for attempt in range(self.PUBLISH_RETRIES):
            try:
                conn=RedisClient.get_conn(for_write=True)
                if not conn:
                    raise RuntimeError('Redis 未连接')
                conn.lpush(self._redis_key,json.dumps(event,ensure_ascii=False))
                EVENT_BUS_EVENTS.labels(event=event_name,result='published').inc()
                logger.debug(f"事件已入队：{event_name}")
                return True
            except Exception as e:
                last_exc=e
                time.sleep(self.PUBLISH_RETRY_DELAY*(attempt+1))
        EVENT_BUS_EVENTS.labels(event=event_name,result='publish_failed').inc()
        logger.error(
            f'事件入队失败(已重试{self.PUBLISH_RETRIES}次),事件可能丢失:{event_name},error:{last_exc}'
        )
        return False

    def _call_handler(self,handler,payload):
        '''在 app context 内执行订阅者。'''
        if self._app is not None:
            with self._app.app_context():
                handler(payload)
        else:
            handler(payload)

    def _dead_letter(self,conn,reason:str,event_name=None,event_json=None,raw=None):
        '''把无法处理/重试耗尽的事件写入死信队列，并打指标。'''
        item={'reason':reason,'event':event_name,'ts':time.time()}
        if event_json is not None:
            item['event_json']=event_json
        if raw is not None:
            item['raw']=raw
        label=event_name or 'unknown'
        try:
            conn.lpush(self._dead_letter_key,json.dumps(item,ensure_ascii=False))
            EVENT_BUS_EVENTS.labels(event=label,result='dead_letter').inc()
            try:
                EVENT_BUS_DEAD_LETTER_LENGTH.set(conn.llen(self._dead_letter_key))
            except Exception:
                pass
            logger.error(f'事件进入死信队列 reason={reason} event={label}')
        except Exception as e:
            logger.error(f'死信入队失败 reason={reason} event={label}:{e}')

    def _dispatch(self,conn,event_name:str,payload:dict,event:dict):
        '''分发一条事件给所有订阅者；无订阅者入死信，有 handler 失败则整条事件重试。'''
        handlers=self._subscribers.get(event_name,[])
        if not handlers:
            self._dead_letter(
                conn,'no_subscriber',event_name=event_name,
                event_json=json.dumps(event,ensure_ascii=False)
            )
            return

        # 续接发布端 trace context（无则视为新链路）
        try:
            from opentelemetry.propagate import extract
            parent_ctx=extract(event.get("_otel") or {})
        except Exception:
            parent_ctx=None

        failed=False
        for handler in handlers:
            try:
                if parent_ctx is not None:
                    from opentelemetry import trace
                    tracer=trace.get_tracer('weibo-eventbus')
                    with tracer.start_as_current_span(
                        f'eventbus:{event_name}', context=parent_ctx
                    ):
                        self._call_handler(handler,payload)
                else:
                    self._call_handler(handler,payload)
                logger.debug(f"事件处理成功：{event_name}->{handler.__name__}")
            except Exception as e:
                failed=True
                logger.error(f"事件处理失败:{event_name}->{handler.__name__}:{e}")

        if not failed:
            EVENT_BUS_EVENTS.labels(event=event_name,result='handled').inc()
            return

        EVENT_BUS_EVENTS.labels(event=event_name,result='handler_failed').inc()
        event["retry_count"]=event.get("retry_count",0)+1
        if event["retry_count"]<self.MAX_RETRY:
            try:
                conn.lpush(self._redis_key,json.dumps(event,ensure_ascii=False))
                EVENT_BUS_EVENTS.labels(event=event_name,result='retried').inc()
                logger.info(f"事件重试入队：{event_name},retry={event['retry_count']}")
            except Exception as e:
                logger.error(f"事件重试入队失败:{event_name}:{e}")
        else:
            self._dead_letter(
                conn,'retry_exhausted',event_name=event_name,
                event_json=json.dumps(event,ensure_ascii=False)
            )
            EVENT_BUS_EVENTS.labels(event=event_name,result='dropped').inc()

    def _consume(self):
        """消费者线程：BRPOP取事件并分发"""
        while self._running:
            try:
                conn=RedisClient.get_conn(for_write=True)
                if not conn:
                    time.sleep(1)
                    continue

                try:
                    EVENT_BUS_QUEUE_LENGTH.set(conn.llen(self._redis_key))
                except Exception:
                    pass

                #BRPOP阻塞等待，超时1秒（便于检查running状态）
                result=conn.brpop(self._redis_key,timeout=1)
                if not result:
                    continue
                _,event_json=result

                try:
                    event=json.loads(event_json)
                    event_name=event["event"]
                    payload=event["payload"]
                except Exception as e:
                    logger.error(f'事件解析失败，进入死信：{e}')
                    EVENT_BUS_EVENTS.labels(event='unknown',result='parse_error').inc()
                    self._dead_letter(conn,'parse_error',raw=event_json)
                    continue

                self._dispatch(conn,event_name,payload,event)

            except Exception as e:
                logger.error(f"消费者线程异常：{e}")
                time.sleep(1)

    def start(self, app=None):
        '''启动消费者线程'''
        if self._running:
            return
        self._app=app
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
