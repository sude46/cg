'''私信实时推送（SSE）。

- 发布：ChatService 发消息后 PUBLISH 到 `chats:{user_id}` 频道
- 订阅：每连接独立 pubsub 连接（pubsub 会独占池里一条连接，直到 close 才归还）
不复用 EventBus（单消费者 BRPOP），同 notifications/stream.py 的理由。
'''
import json
import logging
import time

from utils.redis_util import RedisClient

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = 'chats:'
HEARTBEAT_SECONDS = 15


def _channel(user_id: int) -> str:
    return f'{CHANNEL_PREFIX}{user_id}'


def publish_chat_event(user_id: int, payload: dict) -> None:
    '''向指定用户推送私信事件；失败不影响主流程。'''
    if not user_id:
        return
    try:
        conn = RedisClient.get_conn(for_write=True)
        if not conn or not hasattr(conn, 'publish'):
            return
        conn.publish(_channel(user_id), json.dumps(payload, default=str))
    except Exception as e:
        logger.warning(f'[ChatSSE] 推送失败 user_id={user_id}: {e}')


def iter_events(user_id: int, heartbeat: int = HEARTBEAT_SECONDS):
    '''SSE 生成器。

    订阅是长连接，走读连接，不占主库连接。
    注意：必须运行在 gthread / gevent 下，否则同步阻塞会耗尽 worker。
    '''
    if not user_id:
        return

    # 订阅走读连接：SSE 长连接不该占主库连接
    conn = RedisClient.get_conn(for_write=False)
    if conn is None:
        # 让前端能区分"服务不可用"和"网络抖动"，避免疯狂重连
        yield 'event: error\ndata: {"msg":"redis unavailable"}\n\n'
        return

    pubsub = conn.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(_channel(user_id))
    last = time.time()
    try:
        while True:
            message = pubsub.get_message(timeout=1)
            if message and message.get('type') == 'message':
                data = message.get('data')
                if isinstance(data, bytes):
                    data = data.decode('utf-8', 'replace')
                # payload 是 json.dumps 的结果，单行，无需拆行
                yield f'data: {data}\n\n'
                last = time.time()
            elif time.time() - last >= heartbeat:
                yield ': ping\n\n'
                last = time.time()
    finally:
        # 只关 pubsub，不要 conn.close()（conn 是全局单例，close 会炸全站）
        try:
            pubsub.unsubscribe()
            pubsub.close()
        except Exception:
            pass
