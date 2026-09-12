# 05 — 通知未读数接口 + SSE 推送（items 12 / 20）

---

## 12. `GET /notifications/unread-count`（轻量轮询接口）

### 现状
未读数混在列表响应里（`app/notifications/services.py:138-147`），前端只能拉整个列表才能拿未读数。

### 改法

#### 12.1 抽出未读数解析逻辑

`app/notifications/services.py`，把 `get_user_notifications` 里第 137-145 行抽成方法：

```python
@staticmethod
def get_unread_count(user_id: int) -> int:
    """未读数：缓存 → miss 查 DB 回填（含空缓存防穿透）。"""
    count = NotificationCache.get_unread_count(user_id)
    if count is not None:
        return count
    total = notification_repository.count_unread(user_id)   # 默认走从库
    if total == 0:
        NotificationCache.set_empty(user_id)
    else:
        NotificationCache.set_unread_count(user_id, total)
    return total
```

`get_user_notifications` 第 137-145 行改为 `unread_count = NotificationService.get_unread_count(user_id)`。

> 强一致窗口：`NotificationCache.is_recently_modified(user_id)` 已存在。
> 若刚创建/已读通知（60s 内），`count_unread` 应走主库：`notification_repository.count_unread(user_id, force_master=True)`。
> 在 `get_unread_count` 里加这个分支即可。

#### 12.2 路由

`app/notifications/routes.py` 新增（`/unread-count` 是静态段，不会被 `/<int:notification_id>` 抢）：

```python
@api.route('/unread-count')
class UnreadCountResource(Resource):
    @api.doc('get_unread_count')
    @api.response(200, '获取未读通知数成功')
    @jwt_required()
    def get(self):
        count = NotificationService.get_unread_count(get_jwt_identity())
        return success_response(data={'unread_count': count}, message='获取未读数成功'), 200
```

前端只需轮询这一个接口（比 SSE 简单，先落地它，SSE 后置）。

#### 12.3 验证

```bash
curl -s http://localhost:5000/notifications/unread-count -H "Authorization: Bearer $TOKEN" | jq
# { "code":200, "data":{ "unread_count": 3 }, "message":"..." }
```

---

## 20. SSE 通知推送（替代轮询）

### 选型结论
单向推送用 **SSE**（Server-Sent Events），不是 WebSocket：
自带断线重连、走普通 HTTP、代理友好、实现简单。代价是每个连接占一个长连接 worker，需调整部署。

### 20.1 传输层：Redis Pub/Sub

项目的 **EventBus 是 Redis List + BRPOP**（`app/common/events.py`），适合"单消费者"，**不适合**给多个 SSE 连接广播。
为 SSE 新增**独立 Pub/Sub 频道** `notif:user:{uid}`：

```python
# app/notifications/publisher.py（或直接放 cache.py）
from core.redis_cache import redis_cache

CHANNEL = "notif:user:{user_id}"

def publish_notification(user_id: int, payload: dict):
    conn = redis_cache.get_conn(for_write=True)
    conn.publish(CHANNEL.format(user_id=user_id), json.dumps(payload))
```

在 `NotificationService.create_notification` 成功写库后（`app/notifications/services.py:89` 附近）调用：

```python
try:
    publish_notification(user_id, notification_schema.dump(notif))
except Exception as e:
    logger.warning("SSE 推送失败（不影响主流程）: %s", e)
```

> 注意：`redis_cache.get_conn(for_write=True)` 返回 master（写命令），publish 属于写，必须走主。

### 20.2 SSE 端点

`app/notifications/routes.py`：

```python
import json, time
from flask import Response, current_app, stream_with_context, request
from flask_jwt_extended import decode_token  # 见 20.3 鉴权

@api.route('/stream')
class NotificationStream(Resource):
    @api.doc(description='SSE 实时通知流')
    def get(self):
        # 20.3：EventSource 不能带 Authorization 头，从 query 取 token
        token = request.args.get('token')
        user_id = _verify_stream_token(token)   # 失败返回 401
        last_event_id = request.headers.get('Last-Event-ID')  # 断线续传

        response = Response(_event_generator(user_id, int(last_event_id or 0)),
                            mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'   # Nginx 关闭缓冲
        response.headers['Connection'] = 'keep-alive'
        return response
```

生成器：

```python
def _event_generator(user_id, last_id):
    conn = redis_cache.get_conn(for_write=False)
    pubsub = conn.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(f"notif:user:{user_id}")
    try:
        # 1. 补发断线期间遗漏的通知（Last-Event-ID）
        if last_id:
            for n in notification_repository.list_after_id(user_id, last_id, limit=50):
                yield _sse_format(n['id'], n)
        # 2. 心跳 + 订阅循环
        last_beat = time.monotonic()
        while True:
            msg = pubsub.get_message(timeout=1.0)      # 非阻塞轮询
            if msg and msg['type'] == 'message':
                payload = json.loads(msg['data'])
                yield _sse_format(payload['id'], payload)
            if time.monotonic() - last_beat > 20:      # 20s 心跳，防代理断连
                yield ': keepalive\n\n'
                last_beat = time.monotonic()
    finally:
        pubsub.unsubscribe()
        pubsub.close()


def _sse_format(event_id, data_dict):
    return f"id: {event_id}\nevent: notification\ndata: {json.dumps(data_dict, ensure_ascii=False)}\n\n"
```

> `app/notifications/repositories.py` 需新增 `list_after_id(user_id, last_id, limit)`（`Notification.id > last_id` order by id asc）。

### 20.3 鉴权（SSE 的坑）

浏览器 `EventSource` **不能自定义 Header**，所以不能带 `Authorization: Bearer`。三选一：

| 方案 | 做法 | 评价 |
|------|------|------|
| **短时 SSE token（推荐）** | 新增 `POST /notifications/stream-token`，用正常 JWT 换一个 60s、scope=sse、单次可用的 token；SSE URL 带 `?token=` | 安全，Token 泄露影响小 |
| query 传 access token | 直接把 access token 放 URL | 会进访问日志/Referer，**不推荐** |
| 同域 Cookie | `HttpOnly` Cookie 存 access token，`withCredentials` | 需改认证体系，改动大 |

推荐方案实现：复用 `security_manager.generate_jwt_token(user_id, token_type='sse', expires_in=60)`，
并在 SSE 端点校验 `verify_jwt_token(token, token_type='sse')`。

> 当前 `utils/redis_util.py`/`middlewares/auth_middleware.py` 的黑名单 key 不一致（见 doc 08），SSE token 用短 TTL 可规避。

### 20.4 部署配置（否则 SSE 会被 worker/代理掐断）

**Gunicorn**（`Dockerfile` / `docker-compose.yml` 的 app 启动命令）：
- SSE 是长连接，**不能**用 `sync` worker（会被占满）。用 `gthread` 或 `gevent`：

  ```bash
  gunicorn -k gevent -w 2 --worker-connections 1000 \
           --timeout 0 --keep-alive 75 -b 0.0.0.0:5000 wsgi:app
  ```
  `--timeout 0` 关闭 worker 超时（否则默认 30s 会 kill 长连接）。
  用 gthread 则需 `--threads` 足够、`--timeout` 调大。

**Nginx**（若前置）：
```nginx
location /notifications/stream {
    proxy_pass http://app:5000;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    chunked_transfer_encoding off;
}
```

**Redis**：Pub/Sub 是 fire-and-forget，用户离线期间的消息**不保留**，靠 `Last-Event-ID` + DB 补发兜底。

### 20.5 前端

```ts
const es = new EventSource(`/notifications/stream?token=${sseToken}`);
es.addEventListener('notification', (e) => {
  const n = JSON.parse(e.data);
  store.addNotification(n);
});
es.onerror = () => { /* EventSource 会自动重连，并把 Last-Event-ID 带上 */ };
```

---

## 实施批次建议

- **先做 item 12**（0.5h）：立刻解决前端未读角标轮询成本，不阻塞。
- **SSE（item 20）后置**：先确认部署环境能支持长连接（gunicorn worker 类型、Nginx 配置），否则做了也会频繁断线。可先保留轮询 + `unread-count`，SSE 作为增强。

## 改动清单

- [ ] `NotificationService.get_unread_count` + 路由 `GET /notifications/unread-count`
- [ ] `app/notifications/repositories.py:list_after_id`
- [ ] `publish_notification` + 在 `create_notification` 里投递
- [ ] SSE 端点 `GET /notifications/stream` + `POST /notifications/stream-token`
- [ ] Gunicorn worker 改 `gevent`/`gthread`，`--timeout 0`
- [ ] Nginx SSE location（若用 Nginx）
- [ ] 冒烟：`unread-count` 返回整数；SSE 用 `curl -N` 能收到心跳
