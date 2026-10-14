import json
import logging
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable

from core.metrics import (
    EVENT_BUS_DEAD_LETTER_LENGTH,
    EVENT_BUS_EVENTS,
    EVENT_BUS_PROCESSING_LENGTH,
    EVENT_BUS_QUEUE_LENGTH,
)
from utils.redis_util import RedisClient

logger=logging.getLogger(__name__)

class RedisEventBus:
    '''
    基于 Redis List 的事件总线（at-least-once）

    - 生产者：LPUSH 事件到 event_bus:queue，立即返回
    - 消费者：每个进程一个后台线程，用 BLMOVE 把事件原子地从 queue 移到
      event_bus:processing，处理完成后 LREM ack；处理中进程崩溃则事件仍留在 processing
    - 恢复：周期性 reaper 扫描 processing，把滞留超过 VISIBILITY_TIMEOUT 的条目
      重新放回 queue（可能重复投递，故 handler 必须幂等）
    - 失败处理：整条事件重试(最多 MAX_RETRY 次)；无订阅者/解析失败/重试耗尽 -> 死信队列

    消费模型：每个进程一个消费线程（gunicorn -w N 即有 N 个消费者），它们共享同一
    queue/processing，reaper 按领取时间戳回收，因此多消费者是安全的；事件由哪个
    进程处理不确定（handler 只应依赖 Redis/DB，不依赖进程内状态）。
    语义：at-least-once（可能重复，不会静默丢）。
    '''
    _instance=None
    _lock=threading.Lock()

    MAX_RETRY=3              #同一条事件最多重试次数(默认,可用 EVENT_BUS_MAX_RETRY 覆盖)
    PUBLISH_RETRIES=3        #生产端入队失败重试次数(默认,可用 EVENT_BUS_PUBLISH_RETRIES 覆盖)
    PUBLISH_RETRY_DELAY=0.05
    CLAIM_TIMEOUT=1          #BLMOVE 阻塞超时(秒)(默认,可用 EVENT_BUS_CLAIM_TIMEOUT 覆盖)
    VISIBILITY_TIMEOUT=60    #processing 滞留可回收时间(秒)(默认,可用 EVENT_BUS_VISIBILITY_TIMEOUT 覆盖)
    DLQ_MAX=10000            #死信队列最大长度(默认,可用 EVENT_BUS_DLQ_MAX 覆盖；0=不限)
    DEDUP_TTL=86400          #事件幂等去重窗口(秒)(默认,可用 EVENT_BUS_DEDUP_TTL 覆盖；0=关闭)

    @classmethod
    def _done_key(cls,event_id:str)->str:
        '''事件幂等标记键(处理成功后写入,带 TTL)'''
        return f'event_bus:done:{event_id}'

    def _cfg(self,key:str,default:int)->int:
        '''
        读运行时配置。优先用 start() 保存的 app.config：
        消费线程跑在 app context 之外，current_app 在那里不可用，只有 self._app 能读到配置。
        回退顺序：self._app.config -> current_app.config(生产端请求内) -> 类默认值。
        '''
        app=getattr(self,'_app',None)
        if app is not None:
            value=app.config.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError,ValueError):
                    return default
        try:
            from flask import current_app
            value=current_app.config.get(key)
            if value is not None:
                return int(value)
        except Exception:
            pass
        return default

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance=super().__new__(cls)
                    cls._instance._subscribers={}
                    cls._instance._running=False
                    cls._instance._consumer_thread=None
                    cls._instance._redis_key='event_bus:queue'
                    cls._instance._processing_key='event_bus:processing'
                    cls._instance._processing_ts_key='event_bus:processing:ts'
                    cls._instance._dead_letter_key='event_bus:dead_letter'
                    cls._instance._consumer_id=''
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
            "id":uuid.uuid4().hex,
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

        publish_retries=self._cfg('EVENT_BUS_PUBLISH_RETRIES',self.PUBLISH_RETRIES)
        last_exc=None
        for attempt in range(publish_retries):
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
            f'事件入队失败(已重试{publish_retries}次),事件可能丢失:{event_name},error:{last_exc}'
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
            dlq_max=self._cfg('EVENT_BUS_DLQ_MAX',self.DLQ_MAX)
            if dlq_max>0:
                conn.ltrim(self._dead_letter_key,0,dlq_max-1)
            EVENT_BUS_EVENTS.labels(event=label,result='dead_letter').inc()
            try:
                EVENT_BUS_DEAD_LETTER_LENGTH.set(conn.llen(self._dead_letter_key))
            except Exception:
                pass
            logger.error(f'事件进入死信队列 reason={reason} event={label}')
        except Exception as e:
            logger.error(f'死信入队失败 reason={reason} event={label}:{e}')

    def _dispatch(self,conn,event_name:str,payload:dict,event:dict):
        '''
        分发一条事件给所有订阅者；无订阅者入死信，有 handler 失败则整条事件重试。
        幂等：同一 event.id 在去重窗口内只处理一次（覆盖 at-least-once 重复投递/死信重放）。
        '''
        event_id=event.get('id')
        dedup_ttl=self._cfg('EVENT_BUS_DEDUP_TTL',self.DEDUP_TTL)
        if event_id and dedup_ttl>0:
            try:
                if conn.exists(self._done_key(event_id)):
                    EVENT_BUS_EVENTS.labels(event=event_name,result='duplicate').inc()
                    logger.info(f'事件重复投递，跳过：{event_name},id={event_id}')
                    return
            except Exception as e:
                logger.error(f'事件幂等检查失败:{e}')

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
            if event_id and dedup_ttl>0:
                try:
                    conn.setex(self._done_key(event_id),dedup_ttl,'1')
                except Exception as e:
                    logger.error(f'写事件幂等标记失败:{e}')
            return

        EVENT_BUS_EVENTS.labels(event=event_name,result='handler_failed').inc()
        event["retry_count"]=event.get("retry_count",0)+1
        max_retry=self._cfg('EVENT_BUS_MAX_RETRY',self.MAX_RETRY)
        if event["retry_count"]<max_retry:
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

    def _claim(self,conn)->str|None:
        '''
        原子领取一条事件：BLMOVE 从 queue 右端取出、放入 processing 左端，
        并登记领取时间（用于 reaper 判断滞留）。返回原始事件 JSON 或 None。
        '''
        claim_timeout=self._cfg('EVENT_BUS_CLAIM_TIMEOUT',self.CLAIM_TIMEOUT)
        try:
            raw=conn.blmove(
                self._redis_key,self._processing_key,
                timeout=claim_timeout,src='RIGHT',dest='LEFT'
            )
        except Exception as e:
            logger.error(f'事件领取失败:{e}')
            return None
        if raw is None:
            return None
        if isinstance(raw,bytes):
            raw=raw.decode()
        try:
            conn.hset(self._processing_ts_key,raw,time.time())
        except Exception as e:
            # 登记失败也不丢：条目已在 processing，reaper 会因缺时间戳而回收
            logger.error(f'登记事件领取时间失败:{e}')
        return raw

    def _ack(self,conn,raw:str):
        '''处理完成后确认：从 processing 移除并清理时间戳。'''
        try:
            conn.lrem(self._processing_key,1,raw)
            conn.hdel(self._processing_ts_key,raw)
        except Exception as e:
            logger.error(f'事件 ack 失败(将依赖 reaper 回收):{e}')

    def _reap_stale(self,conn)->int:
        '''回收 processing 中滞留超过 VISIBILITY_TIMEOUT 或缺失时间戳的条目。'''
        visibility=self._cfg('EVENT_BUS_VISIBILITY_TIMEOUT',self.VISIBILITY_TIMEOUT)
        now=time.time()
        try:
            entries=conn.lrange(self._processing_key,0,-1) or []
            ts_map=conn.hgetall(self._processing_ts_key) or {}
        except Exception as e:
            logger.error(f'扫描 processing 失败:{e}')
            return 0

        entries=[e.decode() if isinstance(e,bytes) else e for e in entries]
        pending=set(entries)
        reclaimed=0
        for raw in entries:
            t=ts_map.get(raw)
            try:
                stale=(t is None) or (now-float(t)>visibility)
            except (TypeError,ValueError):
                stale=True
            if not stale:
                continue
            try:
                conn.lpush(self._redis_key,raw)
                conn.lrem(self._processing_key,1,raw)
                conn.hdel(self._processing_ts_key,raw)
                EVENT_BUS_EVENTS.labels(event='unknown',result='reclaimed').inc()
                reclaimed+=1
            except Exception as e:
                logger.error(f'回收滞留事件失败:{e}')

        # 清理孤儿时间戳(ack 在 LREM 与 HDEL 之间崩溃)
        for raw_field in list(ts_map.keys()):
            if raw_field not in pending:
                try:
                    conn.hdel(self._processing_ts_key,raw_field)
                except Exception:
                    pass

        if reclaimed:
            logger.warning(f'事件总线回收 {reclaimed} 条滞留事件(可能重复投递)')
        return reclaimed

    def _consume(self):
        """消费者线程：BLMOVE 领取事件 -> 处理 -> ack；空闲时回收滞留事件"""
        while self._running:
            try:
                conn=RedisClient.get_conn(for_write=True)
                if not conn:
                    time.sleep(1)
                    continue

                try:
                    EVENT_BUS_QUEUE_LENGTH.set(conn.llen(self._redis_key))
                    EVENT_BUS_PROCESSING_LENGTH.set(conn.llen(self._processing_key))
                except Exception:
                    pass

                raw=self._claim(conn)
                if raw is None:
                    self._reap_stale(conn)
                    continue

                try:
                    event=json.loads(raw)
                    event_name=event["event"]
                    payload=event["payload"]
                except Exception as e:
                    logger.error(f'事件解析失败，进入死信：{e}')
                    EVENT_BUS_EVENTS.labels(event='unknown',result='parse_error').inc()
                    self._dead_letter(conn,'parse_error',raw=raw)
                else:
                    self._dispatch(conn,event_name,payload,event)

                self._ack(conn,raw)
                self._reap_stale(conn)

            except Exception as e:
                logger.error(f"消费者线程异常：{e}")
                time.sleep(1)

    def start(self, app=None):
        '''
        启动消费者线程（每进程一个）。

        以"线程是否存活"为准，而非只看 _running：gunicorn --preload 会 fork 出继承
        _running=True、但线程并未被复制的子进程，若只看 _running 会直接跳过启动，
        导致没有消费者、事件静默堆积。
        '''
        if self._running and self._consumer_thread is not None and self._consumer_thread.is_alive():
            return
        self._app=app
        self._consumer_id=f'{socket.gethostname()}:{os.getpid()}'
        self._running=True
        self._consumer_thread=threading.Thread(target=self._consume,daemon=True)
        self._consumer_thread.start()
        logger.info(f"EventBus消费者线程已启动 consumer={self._consumer_id}")

    def stop(self):
        """停止消费者线程"""
        self._running = False
        if self._consumer_thread:
            self._consumer_thread.join(timeout=5)
            self._consumer_thread=None
            logger.info("EventBus 消费者线程已停止")
event_bus = RedisEventBus()
