"""通知实时推送（SSE）。

- 发布：NotificationService 创建通知后 PUBLISH 到 `notifications:{user_id}` 频道
- 订阅：每个 SSE 连接用独立 pubsub 连接订阅该频道，转成 text/event-stream

不复用 app/common/events.py 的 List 事件总线：那是单消费者（BRPOP），
多进程下只有一个进程能取到，无法广播给所有在线连接。
"""
import json
import logging
import time

from utils.redis_util import RedisClient

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = 'notifications:'
HEARTBEAT_SECONDS = 20


def _channel(user_id: int) -> str:
    return f'{CHANNEL_PREFIX}{user_id}'


def publish_notification(user_id: int, payload: dict) -> None:
    """向指定用户的 SSE 频道推送事件；失败不影响主流程。"""
    if not user_id:
        return
    try:
        conn = RedisClient.get_conn(for_write=True)
        if not conn or not hasattr(conn, 'publish'):
            return
        conn.publish(_channel(user_id), json.dumps(payload, default=str))
    except Exception as e:
        logger.warning(f'[SSE] 推送通知失败 user_id={user_id}: {e}')


def iter_events(user_id: int, heartbeat: int = HEARTBEAT_SECONDS):
    """SSE 事件生成器：订阅用户频道，yield `data: ...\\n\\n`，空闲时发心跳。"""
    conn = RedisClient.get_conn(for_write=True)
    if conn is None:
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
                yield f'data: {data}\n\n'
                last = time.time()
            elif time.time() - last >= heartbeat:
                yield ': ping\n\n'
                last = time.time()
    finally:
        try:
            pubsub.unsubscribe()
            pubsub.close()
        except Exception:
            pass
