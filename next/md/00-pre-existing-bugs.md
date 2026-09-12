# 00 — 现存 Bug 详细处理方案（开工前置）

> 本文件把代码走查发现的 bug **逐个**给出：位置、现象、根因、精确改法（before/after）、验证、影响面。
> 建议**先全部修完并跑通冒烟**，再动 item 5–20 的契约改造，否则改完无法判断是契约问题还是旧 bug。
>
> 严重度：🔴 阻断/安全 · 🟠 功能不可用 · 🟡 数据/正确性 · 🟢 清理/优化

| ID | 严重度 | 一句话 | 位置 |
|----|--------|--------|------|
| B1 | 🔴 | `success_response` 引用未定义变量，所有成功接口 500 | `utils/response.py:46` |
| B2 | 🔴 | 登出黑名单 key 不一致，登出根本不生效 | `app/users/routes.py:155` |
| B3 | 🟠 | `FeedServices` 拼写错误，删帖后 Feed 清理崩溃 | `app/feeds/handlers.py:24` |
| B4 | 🟡 | Feed score 用本地时区解释 naive UTC，时间线偏移 | `app/feeds/handlers.py:16` |
| B5 | 🟠 | 评论点赞 `from comments.cache` 导入路径错误，直接崩 | `app/likes/services.py:82` |
| B6 | 🟠 | ES 查询字段 `username` 但 mapping 是 `user_name`，搜作者名 0 结果 | `services/search/document.py:201` |
| B7 | 🟡 | 关注时更新了被关注者的 `following_count`（应为关注者） | `app/follows/services.py:46` |
| B8 | 🔴 | 禁用用户校验用不存在的 `user.status`，禁用账户仍可访问 | `middlewares/auth_middleware.py:172` |
| B9 | 🟡 | `is_actice` 拼写错误，禁用用户可发起关注 | `app/follows/services.py:34` |
| B10 | 🟠 | 互关列表用分页容器 schema 序列化列表，前端拿不到用户 | `app/follows/services.py:161` |
| B11 | 🟢 | 发帖成功指标累加两次 | `app/posts/services.py:54,80` |
| B12 | 🟢 | 死代码/重复实现，易误改（含 `error_middleware`） | 多处 |
| B13 | 🟠 | `AuthenticationError(..., code=401)` 传了不存在的 kwarg | `middlewares/auth_middleware.py:182` |
| B14 | 🟡 | 未读数缓存未命中时忽略了强一致窗口，可能读到从库旧值 | `app/notifications/services.py:140` |

---

## B1 🔴 `success_response` 引用未定义变量

**位置**：`utils/response.py:44-48`

**现象**：调用任何走 `success_response` 的接口 → `NameError: name 'escaped_data' is not defined` → 500。
（AGENTS.md 里说监控/登录链路已修好，但 working tree 这行是坏的。）

**根因**：原本是

```python
from utils.security_utils import html_escape
escaped_data = html_escape(data)
```

working tree 把 import 和赋值删了，但下面 `"data": escaped_data or {}` 的引用没删。
而 `utils/security_utils.py` 现在**已经没有 `html_escape`** 这个函数了（只有 Fernet 相关），所以不能简单加回 import。

**修法**（直接改引用，不做 HTML 转义）：

before：

```python
response_data = {
    "code": ResponseCode.SUCCESS,
    "data": escaped_data or {},
    "message": message
}
```

after：

```python
response_data = {
    "code": ResponseCode.SUCCESS,
    "data": data if data is not None else {},
    "message": message
}
```

**验证**：

```bash
venv/bin/python -c "from utils.response import success_response; print(success_response())"
# 期望 {'code': 200, 'data': {}, 'message': '操作成功'}
```

或跑冒烟：`GET /posts` 不再 500。

**影响面**：全项目所有成功接口。**必须先修**。

---

## B2 🔴 登出黑名单 key 不一致，登出无效

**位置**：
- 写：`app/users/routes.py:155` → `utils/redis_util.py:107-111`（`setex("jwt_blacklist:{jti}")`）
- 读（实际生效）：`middlewares/auth_middleware.py:122`（`exists("jwt:blacklist:{jti}")`）
- 另有死代码：`core/extensions.py:48-52`（`sismember("jwt_blacklist", jti)`，从未被调用）

**现象**：`POST /users/logout` 返回 200，但拿旧 access token 继续访问受保护接口**依然成功**。

**根因**：
- 真正的 blocklist loader 是 `middlewares/auth_middleware.py:135`（factory `:89` 调 `init_auth_middleware`）。
  它读 `app.config['JWT_BLACKLIST_KEY']`，默认 `jwt:blacklist` → key = `jwt:blacklist:{jti}`。
- 登出走的是另一套 `utils.redis_util.RedisClient.add_blacklist` → key = `jwt_blacklist:{jti}`。
  两套 key 只差一个 `:` 的位置，永远对不上。
- `core/extensions.py` 的 loader 又是第三种（Redis SET `jwt_blacklist`），而且 `init_jwt`/`init_extensions` 全项目无调用，纯死代码。

**修法**：统一走 `middlewares/auth_middleware.py` 里已经挂到 app 上的 `current_app.revoke_token`。

before（`app/users/routes.py`）：

```python
from flask import g, request
...
from utils.redis_util import redis_client
...
remain_seconds = max(0, int(exp - now))
redis_client.add_blacklist(jti, remain_seconds)
```

after：

```python
from flask import current_app, g, request   # 新增 current_app
# 删除: from utils.redis_util import redis_client
...
remain_seconds = max(0, int(exp - now))
current_app.revoke_token(jti, remain_seconds)   # key = jwt:blacklist:{jti}，且会预热 LRU
```

同时清理另外两套：
- 删除 `utils/redis_util.py:107-117` 的 `add_blacklist` / `is_blacklisted`（确认无引用）。
- 删除 `core/extensions.py` 里的 `init_redis` / `init_jwt` / `init_extensions`（保留文件顶部的 `jwt/bcrypt/mail` 实例，factory 依赖它们）。
- 删除 `core/extensions.py:48-57` 的 blocklist / revoked loader。

**验证**：

```bash
TOKEN=$(curl -s -X POST localhost:5000/users/login -H 'Content-Type: application/json' \
  -d '{"username":"smoketest1","password":"Smoke@2026x"}' | jq -r .data.access_token)
curl -s -X POST localhost:5000/users/logout -H "Authorization: Bearer $TOKEN" >/dev/null
curl -s -o /dev/null -w '%{http_code}\n' localhost:5000/users/me -H "Authorization: Bearer $TOKEN"
# 期望 401（修复前是 200）
```

> 注意：`_is_token_revoked` 的 LRU 有 10s 负缓存；`revoke_token` 会 `_blacklist_cache.set(jti, True)` 预热，所以登出立即生效，不受影响。

**关联**：item 19 refresh 轮换也依赖这套黑名单，必须先修。

---

## B3 🟠 `FeedServices` 拼写错误

**位置**：`app/feeds/handlers.py:24`

**现象**：删帖后事件分发到 `on_post_deleted` → `NameError: name 'FeedServices' is not defined`，
异常被 `except` 吞掉只打日志，结果是**粉丝时间线里残留已删帖**。

**修法**：

before：

```python
FeedServices.delete_post(
    post_id=payload['post_id'],
    author_id=payload['user_id'],
)
```

after：

```python
FeedService.delete_post(
    post_id=payload['post_id'],
    author_id=payload['user_id'],
)
```

**验证**：`grep -rn "FeedServices" app` 应为空；删帖后 `GET /feeds/timeline` 不再出现该帖。

---

## B4 🟡 Feed score 时区偏移

**位置**：`app/feeds/handlers.py:16`

**现象**：发帖后推送到粉丝 ZSet 的 score 与真实 UTC 时间有偏移（取决于服务器本地时区），导致时间线排序/游标分页错位。

**根因**：`payload['created_at']` 来自 `app/posts/services.py:74` 的 `post.created_at.isoformat()`，
是**naive UTC** 字符串。`datetime.fromisoformat(...)` 得到 naive datetime，
再 `.timestamp()` 会**按服务器本地时区**解释 → 非 UTC 机器上偏移。

**修法**：

before：

```python
from datetime import datetime
...
created_at=datetime.fromisoformat(payload['created_at']).timestamp(),
```

after：

```python
from datetime import UTC, datetime
...
dt = datetime.fromisoformat(payload['created_at'])
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=UTC)          # naive 视为 UTC
created_at = dt.timestamp(),
```

或统一传 datetime 对象，让 `FeedCache` 内部处理（`app/feeds/cache.py:56-57` 已支持 datetime）：

```python
created_at=dt,   # FeedCache 会 .timestamp()
```

**验证**：新帖 score 与 `post.created_at(UTC).timestamp()` 一致（可在测试里断言）。

---

## B5 🟠 评论点赞导入路径错误

**位置**：`app/likes/services.py:82`

**现象**：对**评论**点赞时（`target_type == 'comment'`）执行到该 import → `ModuleNotFoundError: No module named 'comments'` → 500。
帖子点赞不走这里，所以平时没暴露。

**根因**：项目包是 `app.comments.cache`，不是顶层 `comments.cache`。

**修法**：

before：

```python
if target_type=='comment':
    from comments.cache import CommentCache
```

after：

```python
if target_type=='comment':
    from app.comments.cache import CommentCache
```

> 同文件 `delete_like` 第 168 行写的是 `from app.comments.cache import CommentCache`（正确），
> 只有 `create_like` 这行漏了 `app.`。可顺手把顶部统一 import，避免函数内 import。

**验证**：`grep -rn "from comments" app` 应为空；给评论点赞返回 201。

---

## B6 🟠 ES 作者名字段不匹配

**位置**：`services/search/document.py:201` vs mapping `services/search/document.py:30`

**现象**：`/posts/search?q=某用户名` 时，按作者名匹配永远 0 结果（按 content 搜索正常，所以不易察觉）。

**根因**：mapping 定义的是 `user_name`：

```python
'user_name': {'type': 'text', 'fields': {'keyword': {'type': 'keyword'}}},
```

查询却写：

```python
"fields": ["content^3", "username"],
```

**修法**：

before：

```python
"fields": ["content^3", "username"],
```

after（二选一，建议统一成 `user_name`）：

```python
"fields": ["content^3", "user_name"],
```

> 若坚持 `username`，则要把 mapping 和索引文档字段名一起改成 `username`，代价更大。
> 索引文档里写入的字段来自 `app/posts/services.py:67-69` 的 `'user_name': user.username`，本来就是 `user_name`。

**验证**：

```bash
curl -s "localhost:5000/posts/search?q=smoketest1" -H "Authorization: Bearer $TOKEN" | jq '.data.items|length'
# 期望 > 0
```

---

## B7 🟡 关注时更新错用户的 `following_count`

**位置**：`app/follows/services.py:45-46`

**现象**：A 关注 B 后，B 的 `following_count` 被 +1（应为 A 的 `following_count` +1）。
数据：粉丝数对，关注数错位。

**根因**：

```python
user_repository.increment_follower_count(followed_id)   # 对：B 粉丝 +1
user_repository.increment_following_count(followed_id)  # 错：B 关注数 +1
```

**修法**：

after：

```python
user_repository.increment_follower_count(followed_id)   # B 粉丝 +1
user_repository.increment_following_count(follower_id)  # A 关注数 +1
```

**验证**：

```python
a = user_repository.get_by_id(a.id, force_master=True)
b = user_repository.get_by_id(b.id, force_master=True)
assert b.follower_count == 1
assert a.following_count == 1     # 修复前会 == 0
assert b.following_count == 0     # 修复前会 == 1
```

**存量数据修复**（可选，一次性 SQL，用真实计数覆盖，注意软删除）：

```sql
UPDATE users u SET
  follower_count  = (SELECT COUNT(*) FROM follows f WHERE f.followed_id = u.id AND f.deleted_at IS NULL),
  following_count = (SELECT COUNT(*) FROM follows f WHERE f.follower_id = u.id AND f.deleted_at IS NULL);
```

---

## B8 🔴 禁用用户校验字段错误

**位置**：`middlewares/auth_middleware.py:171-173`

**现象**：被 `is_active=False` 禁用的用户，拿着旧 token 仍能访问所有受保护接口。

**根因**：`User` 模型没有 `status` 字段（只有 `is_active`，见 `app/users/models.py:23`），
`getattr(user, 'status', None)` 永远 `None`，判断恒为假。

**修法**：

before：

```python
if getattr(user,'status',None)=='disabled':
    raise AuthenticationError('用户已被禁用')
```

after：

```python
if not getattr(user, 'is_active', True):
    raise AuthenticationError('用户已被禁用')
```

> `AuthService.get_current_user` / `authenticate_user` 已正确检查 `is_active`，
> 但中间件这层没拦住，导致所有其他模块的接口都漏。

**验证**：把测试用户 `is_active` 改 False，旧 token 访问 `/users/me`、`/posts` 都应 401。

---

## B9 🟡 `is_actice` 拼写错误

**位置**：`app/follows/services.py:34`

**现象**：关注时对"关注者"的启用状态校验被跳过（typo 使 `getattr` 返回默认 `True`）。

**修法**：

before：

```python
if not follower or not getattr(follower,'is_actice',True):
```

after：

```python
if not follower or not getattr(follower,'is_active',True):
```

**验证**：`grep -rn "is_actice" app` 应为空；禁用用户关注返回 404。

---

## B10 🟠 互关列表序列化错误

**位置**：`app/follows/services.py:161`

**现象**：`GET /follows/following/mutual` 返回的元素是 `{items,total,page,size,pages}` 这种分页容器，而不是用户对象，前端解析不到 `id/username`。

**根因**：`get_mutual_follows` 的 repository 返回的是 `User` 列表，
但 service 用 `UserListSchema()`（分页容器 schema）配合 `many=True` 去 dump 列表。

**修法**：

before：

```python
from app.users.schemas import UserListSchema
users = UserListSchema().dump(result.get('items', []), many=True)
```

after（用单用户 schema 的 many）：

```python
from app.users.schemas import UserSchema          # 或 doc 04 的 PublicUserSchema
users = UserSchema(many=True).dump(result.get('items', []))
```

> `UserSchema` 含 email，互关列表若对外，应改用 `PublicUserSchema` 脱敏（doc 04）。
> 同一轮把返回 key 从 `mutual_users` 统一成 `items`（doc 01 §5）。

**验证**：`data.mutual_users[0]`（或改后的 `items[0]`）含 `id`、`username`。

---

## B11 🟢 发帖成功指标累加两次

**位置**：`app/posts/services.py:54` 和 `:80`

**现象**：`POST_OPERATIONS{action="create",result="success"}` 每条帖子 +2，监控面板 QPS/成功率基数偏大。

**根因**：第 54 行 commit 后加了一次，第 80 行 return 前又加了一次。

**修法**：删除第 80 行那一次：

```python
# 删除这一行
POST_OPERATIONS.labels(action='create', result='success').inc()
return post
```

**验证**：发一条帖，指标增量应为 1。

---

## B12 🟢 死代码 / 重复实现（易误改，建议清理）

| 位置 | 说明 | 处理 |
|------|------|------|
| `middlewares/error_middleware.py` | 整套错误处理从未注册（factory 用的是 `app/common/error_handlers.py`） | 删除文件；删 `tests/unit/test_middlewares.py:208-210` 引用 |
| `core/extensions.py` `init_redis/init_jwt/init_extensions` | 全项目无调用；内部还有第三套 blocklist loader | 删除这三个函数，保留 `jwt/bcrypt/mail` 实例 |
| `utils/redis_util.py` `add_blacklist/is_blacklisted` | 与 `auth_middleware` 黑名单 key 不同，见 B2 | 删除 |
| `utils/helpers.py` | 另一套 `success_response/pagination_response`（`code:0`），无引用 | 删除整个文件 |
| `utils/response.py:pagination_response` | 旧分页格式，item 5 会替换 | item 5 时删除 |
| `app/posts/schemas.py:8-14 IsoDateTime` | 定义了但从未使用 | item 7 统一字段时删除 |
| `config/base.py` 与 `core/config.py` | 后者已删（AGENTS 记录） | 确认无残留引用 |

**验证**：`git grep -n "error_middleware\|init_error_handlers\|helpers import\|is_blacklisted"` 无结果。

---

## B13 🟠 `AuthenticationError` 传了不存在的 kwarg

**位置**：`middlewares/auth_middleware.py:182`

**现象**：JWT 校验失败分支本意返回 401、`code=401`，实际抛 `TypeError: __init__() got an unexpected keyword argument 'code'`，
被外层 `except Exception` 捕获，变成"认证服务异常"（语义/错误码错误）。

**根因**：`BaseError.__init__` 只接受 `message/status_code/error_code/details`（`app/common/exceptions.py:9-15`）。

**修法**：

before：

```python
raise AuthenticationError('认证失败', code=401)
```

after：

```python
raise AuthenticationError('认证失败')   # AuthenticationError 默认 status_code=401
```

**验证**：带无效 token 访问受保护接口，返回 401 且 `message` 为"认证失败..."，而不是"认证服务异常"。

---

## B14 🟡 未读数缓存未命中忽略强一致窗口

**位置**：`app/notifications/services.py:139-145`

**现象**：刚创建/标记已读通知后的 60s 内（`NotificationCache.mark_recently_modified`），
如果未读数缓存刚好 Miss，会走到 `count_unread(user_id)` **默认从库**，可能读到主从延迟前的旧值，角标回跳。

**修法**：在 `get_unread_count`（doc 05 §12.1 抽出来的方法）里加分支：

```python
force_master = NotificationCache.is_recently_modified(user_id)
total = notification_repository.count_unread(user_id, force_master=force_master)
```

**验证**：创建通知后立即查未读数，连续请求值单调不减（不出现旧值回跳）。（依赖真实主从，冒烟环境单库时不明显。）

---

## 建议修复顺序

```
1) B1           —— 否则什么都测不了
2) B2 / B8 / B13 —— 认证安全，且 item 19 依赖
3) B3 / B5 / B6 / B7 / B9 / B10 / B14 —— 功能/数据
4) B4           —— Feed，配合 item 9
5) B11 / B12    —— 清理
```

修完后：

```bash
venv/bin/pytest tests/unit -v
docker rm -f weibo-app && sleep 3 && docker compose up -d app
venv/bin/pytest tests/smoke/test_smoke.py -v
```

> 注意：`tests/smoke/test_smoke.py` 里没有覆盖到"登出后 token 失效""评论点赞""按作者名搜索""禁用用户"，
> 修复时建议顺手补 4 条断言，防止回归。

---
---

# Part 2 — 深度审计追加（B15–B52）

> 第二轮对全仓库（posts/feeds/search/likes/comments/notifications/users/follows/middlewares/core/tasks/config/utils）逐文件审计后新增。
> 均已对照源码核实（含方法签名、Redis 命令、SQLAlchemy/reqparse 行为）。同样只给方案，不改代码。

| ID | 严重度 | 位置 | 问题 |
|----|--------|------|------|
| B15 | 🟠 | `app/posts/cache.py:148-149` | 给 `zrevrange/zcard` 传了它们没有的 `for_write=` → 热帖读永远空 |
| B16 | 🟡 | `app/posts/cache.py:108` | aware `now` 减 naive `created_at` → 热帖计算永远失败 |
| B17 | 🟠 | `app/posts/routes.py:241,268` | 调用了 `PostSearchService` 里不存在的方法 → 两个接口 500 |
| B18 | 🟠 | `services/search/services.py:42-64` | ES 降级 DB 的分支是死代码，ES 挂了搜索返回空 |
| B19 | 🟠 | `services/search/services.py:119-121` | `time_bonus` 可能未赋值 → 索引时 `UnboundLocalError` |
| B20 | 🟡 | `app/comments/cache.py:100` | 失败返回 `False` 而非 `None` → 评论数被覆盖为 0 |
| B21 | 🟡 | `app/comments/cache.py:27-34,104` | 评论计数未从 DB 预热、DECR 会造无 TTL 的 0 |
| B22 | 🟡 | `app/likes/cache.py:111-126` | 计数缺失时返回 0 而非 None → 展示点赞数变 0 |
| B23 | 🟡 | `app/likes/services.py:50-58` | 回填已有点赞时 `add_like` 又 +1 → 计数虚高并被写回 DB |
| B24 | 🟠 | `app/notifications/routes.py:59` | reqparse `type=bool` 把 `"false"` 解析成 `True` |
| B25 | 🔴 | `app/notifications/routes.py:82-95` | 任意登录用户可给任何人伪造通知（刷屏/钓鱼） |
| B26 | 🟠 | `app/users/schemas.py:45` | `not validate_password(...)` 永远为假（返回 dict） |
| B27 | 🟠 | `app/users/schemas.py:47-55` | `PasswordPolicy.test()` 不抛异常 → schema 复杂度校验空转 |
| B28 | 🟡 | `redis_cache.exists` 读从库 | 强一致标记/账户锁读副本 → 一致性窗口形同虚设 |
| B29 | 🟡 | `app/users/models.py:44` | `mfa_secret` 只有 20 字符，装不下 Fernet 密文（~120） |
| B30 | 🟢 | `app/users/services/token_service.py:6` | `expires_in` 参数被忽略 |
| B31 | 🟡 | `app/follows/cache.py:106` | `EXPIRE` 作用在错误的 `following:` key 上 |
| B32 | 🟠 | `app/follows/cache.py:49-60` | `is_following` 缺失时返回 False 而非 None → DB 兜底不可达 |
| B33 | 🟡 | `app/follows/repositories.py:22-36` | `lock=True` 未真正 `with_for_update()` |
| B34 | 🟠 | `middlewares/logging_middleware.py:63,67` | `not request.is_json` 反了 + `slient` 拼写 → 请求体日志失效 |
| B35 | 🟢 | `middlewares/auth_middleware.py:94` | 公开前缀缺前导 `/` |
| B36 | 🟠 | `core/redis_cache.py:106,124-126` | `cache_through` 传了 setnx/release_lock 没有的 `for_write` → 永远抛异常 |
| B37 | 🟡 | `core/redis_cache.py:244-249` | `brpop` 是写命令却用读连接 |
| B38 | 🟡 | `core/database.py:15-25` | `SoftDeleteQuery.__iter__` 无限递归；`not entity.is_deleted` 不是 SQL |
| B39 | 🟢 | `core/database.py:117-118` | `session.execute('SELECT 1')` 在 SQLAlchemy 2.0 报错 |
| B40 | 🟢 | `core/security.py:195` | `bcrypt.InvalidHashError` 不存在 |
| B41 | 🟠 | `config/base.py:128` | 环境变量名 `CORE_ALLOWED_ORIGINS` 拼错（缺 S） |
| B42 | 🟠 | `config/development.py:34-42` | `if` 嵌套错误 → 缺 `MYSQL_DB` 不报错，连到 `.../None` |
| B43 | 🟠 | `tasks/post_reconcile.py:81-83` | `return` 在 for 内 → 只对账第一条；`total_diff` 可能未定义 |
| B44 | 🟠 | `tasks/data_tasks.py:45` | `if not rows` 永远为假（Result 对象）→ 不会提前退出 |
| B45 | 🟡 | `tasks/like_reconcile.py:47-49` | `or 0` 让 `is None` 判断失效 → Redis 抖动会把 DB 点赞清零 |
| B46 | 🟡 | `tasks/*.py` | DB 任务缺 app context（加 worker 即炸） |
| B47 | 🟠 | `manage_es.py:77-86,122` | `PostDocument.INDEX_NAME` 不存在 → status/delete 崩 |
| B48 | 🟠 | `utils/lock_utils.py:72-81` | `pessimistic_get` 有 `filter_by` 时不加锁；默认模式直接抛错 |
| B49 | 🟢 | `app/common/error_handlers.py:19,23` | 读了从未设置的 `g.request_start_time` / `g.user_id` |
| B50 | 🟢 | `app/posts/services.py:252` | 日志 f-string 漏了 `f` 且 `e` 未绑定 |
| B51 | 🟡 | `app/notifications/cache.py:72-77,199` | 延迟失效窗口内到达的通知会丢未读数 |
| B52 | 🟢 | `app/feeds/routes.py:53` | 文档写 per_page=20，实际 `get_pagination_params()` 默认 10 |

---

## 2A. posts / search

### B15 🟠 热帖读取永远为空（`for_write` 参数不存在）

**位置**：`app/posts/cache.py:148-149`

**根因**：`RedisCache.zrevrange(self,key,start,end,withscores=False)`（`core/redis_cache.py:172`）和
`RedisCache.zcard(self,key)`（`:265`）都**没有** `for_write` 形参。传了会 `TypeError`，被外层 `except` 吞掉返回 `([], 0)`。
（对比 `CommentCache.get_hot_comments` 第 173-174 行就是正确写法。）

**修法**：

```python
# before
results=redis_cache.zrevrange(key,start,end,withscores=False,for_write=False)
total=redis_cache.zcard(key,for_write=False) or 0
# after
results=redis_cache.zrevrange(key,start,end,withscores=False)
total=redis_cache.zcard(key) or 0
```

**验证**：`tasks/comment_reconcile.py:18` 的 `PostCache.get_hot_posts(...)` 不再返回 `([],0)`；热门榜有数据。

---

### B16 🟡 热帖分数计算永远失败（aware 减 naive）

**位置**：`app/posts/cache.py:108`

**根因**：`tasks/data_tasks.py:52` 传进来的 `row.created_at` 是 MySQL 取出的 **naive UTC**，
`datetime.now(UTC)` 是 aware → `TypeError: can't subtract offset-naive and offset-aware datetimes`，
`calculate_hot_posts` 直接进 `except` 返回 failed，热榜永不生成。

**修法**：

```python
# before
hours=max(0,(datetime.now(UTC)-created_at).total_seconds()/3600)
# after
if created_at.tzinfo is None:
    created_at = created_at.replace(tzinfo=UTC)
hours=max(0,(datetime.now(UTC)-created_at).total_seconds()/3600)
```

**验证**：手动跑 `tasks.data_tasks.calculate_hot_posts` 返回 `status=success` 且 `top_count>0`。

---

### B17 🟠 两个接口调用不存在的方法

**位置**：`app/posts/routes.py:241`（`get_hot_searches`）、`:268`（`get_search_suggestions`）

**根因**：`PostSearchService`（`services/search/services.py`）只有
`index_post/update_post/delete_post/search/reindex_all/_calculate_hot_score`，
没有这两个方法 → `AttributeError` → 500。

**修法**（二选一）：
- **实现**：在 `PostSearchService` 加两个类方法（热搜可用 Redis ZSet 统计搜索词；建议可用 ES completion 或对 `content` 做 `match_phrase_prefix`）。
- **下线**：删除 `HotSearches`/`SearchSuggestions` 两个 Resource，并同步删前端调用与文档。若当前无前端依赖，推荐先下线，避免留死接口。

**验证**：`GET /posts/hot-searches`、`GET /posts/search/suggestions?q=x` 返回 200 而非 500。

---

### B18 🟠 ES 搜索没有 DB 降级（fallback 死代码）

**位置**：`app/posts/services.py:349,367`（读 `result.get('fallback')`）vs `services/search/services.py:42-64`（从不设置 `fallback`）

**根因**：`PostSearchService.search` 永远返回 `{'items','total','pagination'}`，没有 `fallback`、也不调 `post_repository.search_posts`。
于是：
- `PostService.search_posts` 里两个分支都走 `not result.get('fallback')` → `is_es_search` 恒为 `True`；
- 路由 `app/posts/routes.py:213-215` 的 `else`（DB 序列化）分支**不可达**；
- ES 挂了/0 结果时接口返回空，而不是回退 DB `LIKE`。`tests/unit/test_posts.py:178` 的降级断言目前也是红的。

**修法**（在 `services/search/services.py:search` 里实现降级）：

```python
@staticmethod
def search(query, page=1, per_page=20, user_id=None, sort_by='relevance'):
    if not es_client.is_available():
        return PostSearchService._search_db_fallback(query, page, per_page, sort_by)
    posts, total = PostSearchRepository.search(...)
    if total == 0:
        fb = PostSearchService._search_db_fallback(query, page, per_page, sort_by)
        if fb['total'] > 0:
            return fb
    total_pages = (total + per_page - 1)//per_page if total else 1
    return {'items': posts, 'total': total,
            'pagination': {'page':page,'per_page':per_page,'total':total,
                           'total_pages':max(1,total_pages),
                           'has_next':page<total_pages,'has_prev':page>1}}
```

`_search_db_fallback` 用 `post_repository.search_posts(query, page, per_page)`，返回时设 `'fallback': True`。
（并同步把 doc 01 §5.4 要求的 `total_pages`→`pages` 一起改。）

**验证**：停 ES 后 `GET /posts/search?q=xxx` 有 DB 结果，`data.search_engine == 'database'`。

---

### B19 🟠 `time_bonus` 可能未赋值

**位置**：`services/search/services.py:119-121`

**根因**：

```python
if created_at:
    ...
    time_bonus=max(0,24-hours_since)*10
return score+time_bonus      # created_at 为空时 UnboundLocalError
```

**修法**：

```python
score=like_count+comment_count*2
time_bonus=0.0                      # 新增初始化
created_at=post_data.get('created_at')
if created_at:
    ...
return score+time_bonus
```

**验证**：`PostSearchService.index_post({'id':1,'content':'x'})`（不带 `created_at`）不再抛 `UnboundLocalError`。

---

## 2B. likes / comments / notifications

### B20 🟡 评论数失败哨兵用了 `False`

**位置**：`app/comments/cache.py:100`

**根因**：`get_count` 异常时 `return False`，而消费者用 `is not None` 判断
（`app/posts/services.py:121,183`）：`False is not None` 为真 → 把 `post.comment_count` 覆盖成 `False`（序列化为 0）。

**修法**：

```python
# before
return False
# after
return None
```

**验证**：Redis 故障时帖子详情仍显示 DB 的真实 `comment_count`。

---

### B21 🟡 评论计数与 DB 脱节

**位置**：`app/comments/cache.py:27-34`（DECR Lua）、`:104`（`set_count` 无调用者）、`:116-121`（`increment_count`）

**根因**：
1. `set_count` 全项目只有定义、无调用 → Redis 计数从未用 DB `Post.comment_count` 预热；
2. `increment_count` 对不存在的 key 执行 `INCR` 得 `1`，于是已有 5 条评论的帖子在下一条评论后显示 1；
3. DECR Lua `redis.call('SET',KEYS[1],0)` 会造一个**无 TTL** 的 0，永久覆盖真实值。

**修法**（组合）：

```python
# increment_count：缺失时不要造 1，交给 DB 兜底 / 先预热
@classmethod
def increment_count(cls, post_id):
    key = cls._count_key(post_id)
    if redis_cache.exists(key):                 # 只有已预热才自增
        return redis_cache.increment(key, 1)
    return None                                  # 调用方回退读 DB
```

```lua
-- DECR_LUA：不要造常量 key，保留 TTL 语义
local current=redis.call('GET', KEYS[1])
if current==false then return 0 end
if tonumber(current)<=0 then return 0 end
return redis.call('DECRBY',KEYS[1],1)
```

并在 `CommentService.create_comment` 首次写评论前，若 `get_count is None`，用
`post_repository.get_by_id(post_id).comment_count` 调 `CommentCache.set_count(post_id, n)` 预热（或直接在 `get_count` miss 时由 posts 层回退 DB，当前 posts 已经是这样，故**最关键的是不要造错值**）。

**验证**：预置 5 条评论的帖子再发 1 条，接口显示 6（不是 1）。

---

### B22 🟡 点赞数缺失时返回 0 而非 None

**位置**：`app/likes/cache.py:111-126`

**根因**：Counter 和 likers Set 都不存在时，`scard` 返回 `0`，函数返回 `0`（不是注释承诺的 `None`）。
`app/posts/services.py:117-119,178-180` 用 `is not None` 判断，于是把有真实 DB 点赞的帖子覆盖成 0。
另外 `preload_target_likers`（`cache.py:270`）**无任何调用者**，计数永远补不回来。

**修法**：

```python
# before
count = redis_cache.scard(cls._target_likers_key(target_type, target_id), for_write=False)
return int(count) if count is not None else 0
# after：likers Set 不存在就返回 None，让 Service 用 DB 值
if redis_cache.exists(cls._target_likers_key(target_type, target_id)):
    return int(redis_cache.scard(cls._target_likers_key(target_type, target_id)) or 0)
return None
```

**验证**：清空 Redis 后帖子详情显示 DB 的 `like_count`，不是 0。

---

### B23 🟡 回填点赞会多计一次

**位置**：`app/likes/services.py:50-58`（`create_like`）、`:137-146`（`delete_like`）

**根因**：DB 已有该点赞、Redis 丢失时，代码调 `LikeCache.add_like(...)` 回填。
但 `add_like` 的 Lua 对"用户不在目标 Set"会 `SADD` **并 `INCR`**，于是给已存在的点赞又 +1；
脏标记随后让 `tasks/like_reconcile.py` 把虚高值写回 DB。

**修法**：回填走"只建关系、不计数"的路径，计数用 DB 真值：

```python
# 回填时：
LikeCache.preload_user_likes(user_id, [target_id], target_type)   # 只 SADD 用户侧
# 目标侧计数以 DB 为准：
db_count = like_repository.count_likes_for_post(target_id)  # 或 _for_comment
LikeCache.preload_target_likers(target_id, <likers>, target_type)  # 内部以 len(likers) 设 Counter
```

**验证**：模拟 Redis 丢失后重复触发 `create_like`，计数不增长；`reconcile_like_counts` 不再产生差异。

---

### B24 🟠 `unread_only` 传 `false` 被当成 `true`

**位置**：`app/notifications/routes.py:59`

**根因**：`reqparse` 的 `type=bool` 实际是 `bool("false") == True`。

**修法**：

```python
from flask_restx.inputs import boolean
notifications_parser.add_argument('unread_only', type=boolean, default=False, location='args')
```

**验证**：`?unread_only=false` 返回全部通知；`?unread_only=true` 只返回未读。

---

### B25 🔴 通知创建接口可被任意用户伪造

**位置**：`app/notifications/routes.py:82-95` + `app/notifications/services.py:48-101`

**根因**：`POST /notifications` 请求体完全由客户端控制（收件人 `user_id`、`type`、`content`），
service 只校验用户存在，不校验调用者身份；`current_user_id` 拿到后从未使用。
任意登录用户可给任意人发通知。

**修法**（三选一，推荐 1）：
1. **删除该路由**，通知只由事件处理器（`comment.created` 等）创建；
2. 仅允许管理员：`if not getattr(g.current_user, 'is_admin', False): raise PermissionError(...)`；
3. 强制 `data['user_id']`/`actor_id` 由服务端事件注入，不接受客户端传参。

**验证**：普通用户 `POST /notifications` 返回 403/404。

---

## 2C. users

### B26 🟠 `not validate_password(...)` 永远为假

**位置**：`app/users/schemas.py:45`

**根因**：`utils.validators.validate_password`（`utils/validators.py:16-18`）返回的是**字典**，
`not {...}` 恒为 `False`，这层校验是死的（真正生效的是 `AuthService.register_user` 里的 `password_validator`）。

**修法**：

```python
# before
if not validate_password(data.get('password','')):
# after
if not validate_password(data.get('password',''))['is_valid']:
```

**验证**：`RegisterSchema().load({...弱密码...})` 在 schema 层即报错。

---

### B27 🟠 `PasswordPolicy.test()` 用法错误，复杂度校验空转

**位置**：`app/users/schemas.py:47-55`

**根因**：`password_strength.PasswordPolicy.test()` **返回失败策略列表，不抛异常**，
所以 `try/except` 里的 `raise ValidationError` 永不触发（只有包缺失才走手写回退）。

**修法**：

```python
def validate_password_complexity(password):
    if password_policy is not None:
        failures = password_policy.test(password)
        if failures:
            raise ValidationError("密码复杂度不足：" + ", ".join(map(str, failures)))
        return
    ...  # 保留现有手写回退
```

或直接复用 `utils.validators.validate_password_complexity`（它用的是能正确工作的 `SecurityManager`）。

**验证**：`RegisterSchema` 对弱密码报错。

---

### B28 🟡 所有"强一致标记/账户锁"读的是从库

**位置**：`core/redis_cache.py:258-263`（`exists` 无 `for_write` 参数，恒读 replica）
消费方：`app/posts/cache.py:92`、`app/users/cache.py:108`、`app/notifications/cache.py:165`、`app/users/services/account_service.py:36`

**根因**：标记/锁用 `for_write=True` 写到 master，读取却走 replica；主从异步复制下标记可能不可见，
导致"写后强制走主库"窗口失效、账户锁可能查不到。

**修法**：给 `exists` 加 `for_write` 参数并让上述读取传 `True`：

```python
# core/redis_cache.py
def exists(self, *keys: str, for_write=False) -> int:
    client = self._get_client(for_write=for_write)
    ...
# 消费方
return redis_cache.exists(cls._recent_key(post_id), for_write=True) > 0
```

**验证**：写后立即读（模拟主从延迟）能命中强一致分支。

---

### B29 🟡 `mfa_secret` 列长度不足

**位置**：`app/users/models.py:44`

**根因**：`db.String(20)`，但 `MFAService.encrypt_secret` 存的是 Fernet 密文（16 字符 TOTP secret 加密后约 120 字符），
严格模式报 `Data too long`，非严格模式截断后无法解密。

**修法**：

```python
# before
mfa_secret=db.Column(db.String(20),nullable=True)
# after
mfa_secret=db.Column(db.String(255),nullable=True)
```

配套：生成 alembic 迁移 `ALTER TABLE users MODIFY mfa_secret VARCHAR(255)`（当前无路由持久化该字段，属潜在问题）。

---

### B30 🟢 `TokenService.generate_tokens` 忽略 `expires_in`

**位置**：`app/users/services/token_service.py:6-11`

**修法**：

```python
return security_manager.generate_jwt_token(
    user_id=user_id, token_type='reset', expires_in=expires_in
)
```

---

## 2D. follows

### B31 🟡 `EXPIRE` 作用在错误的 key

**位置**：`app/follows/cache.py:106`

**根因**：第 104 行写的是 `following:{follower_id}`，第 106 行却给 `following:{followed_id}` 设过期 →
`following:{follower_id}` **永不过期**（内存泄漏 + 过期语义失效）。

**修法**：

```python
# before
pipe.expire(cls._following_key(followed_id),cls.TTL_DAYS*86400)
# after
pipe.expire(cls._following_key(follower_id),cls.TTL_DAYS*86400)
pipe.expire(cls._followers_key(followed_id),cls.TTL_DAYS*86400)
```

---

### B32 🟠 `is_following` 缺失时返回 False，DB 兜底不可达

**位置**：`app/follows/cache.py:49-60` + `app/follows/services.py:166-174`

**根因**：Redis `SISMEMBER` 对不存在的 key 返回 `0` → 包装函数返回 `False`（不是 `None`）；
service 用 `if cached is not None: return cached`，于是冷缓存/淘汰后真实关注关系被永久判为 `False`。

**修法**（cache 层区分"key 不存在"）：

```python
@classmethod
def is_following(cls, follower_id, followed_id):
    try:
        key = cls._following_key(follower_id)
        if redis_cache.exists(key, for_write=True) == 0:   # 需先加 B28 的 for_write
            return None
        return bool(redis_cache.sismember(key, str(followed_id), for_write=False))
    except Exception as e:
        logger.error(...); return None
```

**验证**：清空 `following:{uid}` 后，`GET /posts/<id>` 的 `is_following` 仍正确（走 DB）。

---

### B33 🟡 `lock=True` 并未加行锁

**位置**：`app/follows/repositories.py:22-36`

**根因**：docstring 和 `models.py:16` 注释都声称 `SELECT ... FOR UPDATE`，但代码从未调用 `.with_for_update()`。
唯一并发保护是 Redis 分布式锁（另一失败域）。

**修法**：

```python
# before
if lock:
    query=db.session.query(Follow)
...
return query.filter(...).first()
# after
if lock:
    query=db.session.query(Follow).with_for_update()
...
```

**验证**：并发关注同一对用户不出重复行（配合唯一索引/事务测试）。

---

## 2E. middlewares / core

### B34 🟠 请求体日志失效

**位置**：`middlewares/logging_middleware.py:63,67`

**根因**：(1) `not request.is_json` 写反 → JSON 请求（整个 API）被跳过；(2) `get_json(slient=True)` 拼错（正确是 `silent`）→ 一旦执行就 `TypeError` 被吞。

**修法**：

```python
# before
if request.method in ['POST', 'PUT', 'PATCH'] and not request.is_json:
    ...
    body=request.get_json(slient=True) or {}
# after
if request.method in ['POST', 'PUT', 'PATCH'] and request.is_json:
    ...
    body=request.get_json(silent=True) or {}
```

---

### B35 🟢 公开路由前缀缺前导 `/`

**位置**：`middlewares/auth_middleware.py:94`

**修法**：

```python
# before
public_prefixes=['/auth','api/auth','health']
# after
public_prefixes=['/auth','/api/auth','/health']
```

---

### B36 🟠 `cache_through` 恒抛异常

**位置**：`core/redis_cache.py:106,124-126` vs `:218`（`setnx`）、`:224`（`release_lock`）

**根因**：`setnx`/`release_lock` 不接受 `for_write`，传了即 `TypeError`；
`except` 返回 `loader()`，随后 `finally` 里的 `release_lock(..., for_write=...)` 再次抛异常并覆盖返回值 →
`cache_through` **永远失败**，且 `finally` 在未获得锁时也会释放别人的锁。

**修法**：

```python
# before
acquired=self.setnx(lock_key,lock_value,expire=lock_timeout,for_write=for_write)
...
finally:
    self.release_lock(lock_key,lock_value,for_write=for_write)
# after
acquired=self.setnx(lock_key,lock_value,expire=lock_timeout)   # setnx 内部已 for_write=True
if not acquired:
    time.sleep(0.1); return self.cache_through(...)
try:
    ...
finally:
    self.release_lock(lock_key,lock_value)                    # 仅在持锁路径释放
```

（注意把 release 移进"获得锁"的分支，避免误删他人锁。）

---

### B37 🟡 `brpop` 用读连接

**位置**：`core/redis_cache.py:244-249`

**根因**：`BRPOP` 会弹出元素，是写命令；读取副本会 `READONLY`。
（事件总线 `app/common/events.py` 已用直接连接 + `for_write=True`，这个封装没同步。）

**修法**：`client = self._get_client(for_write=True)`。

---

### B38 🟡 `SoftDeleteQuery.__iter__` 无限递归

**位置**：`core/database.py:15-25`

**根因**：`_add_soft_delete_filter` 里 `self.filter(...)` 返回的仍是 `SoftDeleteQuery`，
`iter()` 再触发 `__iter__` → `RecursionError`；且 `not entity.is_deleted` 是 Python 布尔（不是 SQL 表达式），过滤永远无效。

**修法**：

```python
def __iter__(self):
    return super().__iter__()

def _add_soft_delete_filter(self):
    if self.column_descriptions and len(self.column_descriptions) > 0:
        entity = self.column_descriptions[0]["entity"]
        if hasattr(entity, "is_deleted"):
            return self.filter(entity.is_deleted.is_(False))
    return self
```

> 该 `query_class` 影响全局 `Model.query`。若要真正生效，需在查询入口显式调用 `_add_soft_delete_filter()`（如 `BaseModel.query()`），
> 不要依赖 `__iter__`。当前仓库大多显式 `deleted_at.is_(None)`，建议先修递归、避免误伤。

**验证**：`list(User.query)` 不再 `RecursionError`。

---

### B39 🟢 SQLAlchemy 2.0 不接受裸字符串 SQL

**位置**：`core/database.py:118`

**修法**：

```python
from sqlalchemy import text
...
session.execute(text('SELECT 1'))
```

> `DatabaseManager.init_app/test_connection` 均未被 factory 调用（C4/B12 死代码），若保留就修，否则删除。

---

### B40 🟢 `bcrypt.InvalidHashError` 不存在

**位置**：`core/security.py:195`

**修法**：`except (ValueError, TypeError, UnicodeEncodeError) as e:`（去掉不存在的属性）。

> `SecurityManager.verify_password` 当前无调用（实际用 `password_service`），属潜在崩溃路径。

---

## 2F. config

### B41 🟠 CORS 环境变量名拼错

**位置**：`config/base.py:126-131`

**修法**：

```python
# before
os.getenv('CORE_ALLOWED_ORIGINS', 'http://localhost:5173')
# after
os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173')
```

**验证**：设置 `CORS_ALLOWED_ORIGINS=...` 后跨域生效。

---

### B42 🟠 `if` 嵌套错误，缺 `MYSQL_DB` 不报错

**位置**：`config/development.py:34-42`

**根因**：`if not mysql_db` 被错误地放进 `if not mysql_user` 里；当 `MYSQL_USER` 已设置而 `MYSQL_DB` 缺失时不报错，
最终 `_build_db_uri` 拼出 `.../@host/None`。

**修法**：

```python
missing_configs=[]
if not mysql_user:
    missing_configs.append('MYSQL_USER')
if not mysql_db:
    missing_configs.append('MYSQL_DB')
if missing_configs:
    raise OSError(f"开发环境数据库配置缺失：{', '.join(missing_configs)}，请通过环境变量设置")
```

**验证**：只设 `MYSQL_USER` 不设 `MYSQL_DB` 时启动即报错。

---

## 2G. tasks

### B43 🟠 对账只处理第一条

**位置**：`tasks/post_reconcile.py:81-83`（缩进在 `for key in keys` 内，12 空格）

**根因**：循环体里直接 `return`，处理第一个 key 后就返回；另外 `total_diff` 在 `scan_iter` 之后才定义（第 30 行），
若 `scan_iter` 抛错，外层 `except`（第 85 行）读 `total_diff` 会 `UnboundLocalError`。

**修法**：

```python
# 把 total_diff = 0 提到 try 之前（或 try 第一行）
total_diff = 0
try:
    ...
    for key in keys:
        ...
    # 循环结束后（8 空格缩进）再 return
    RECONCILE_DIFF_COUNT.labels(resource_type='post').set(total_diff)
    logger.info(f'[Reconcile] 对账完成: 检查{checked}条, 修正{fixed}条')
    return {'status': 'success', 'checked': checked, 'fixed': fixed}
except Exception as e:
    ...
```

**验证**：`sample_size=10` 时 `checked` 接近 10，而不是 0/1。

---

### B44 🟠 热帖查询不会提前退出

**位置**：`tasks/data_tasks.py:45`

**根因**：`db.session.execute(...)` 返回 `CursorResult`，不实现 `__bool__/__len__`，`not rows` 恒 `False`；
即使没有数据也会一直查满到 `offset>=50000`。

**修法**：

```python
# before
rows=db.session.execute(sql, {...})
if not rows:
    break
# after
rows=db.session.execute(sql, {...}).fetchall()
if not rows:
    break
```

或 `if len(rows) < batch_size: ...` 后 `break`。

---

### B45 🟡 对账可能把 DB 点赞清零

**位置**：`tasks/like_reconcile.py:47-49`

**根因**：`LikeCache.get_like_count(...) or 0` 把 Redis 异常的 `None` 变成 `0`，
下一行 `if redis_count is None: continue` 成为死代码；若此时 `db_count>0`，
会执行 `post_repository.update_like_count(t_id, 0)`，把真实点赞清零。

**修法**：

```python
# before
redis_count=LikeCache.get_like_count(t_id,t_type) or 0
if redis_count is None:
    continue
# after
redis_count=LikeCache.get_like_count(t_id,t_type)
if redis_count is None:
    continue
```

**验证**：模拟 `get_like_count` 抛异常，DB 点赞数不变。

---

### B46 🟡 Celery DB 任务缺 app context（加 worker 即炸）

**位置**：`tasks/like_tasks.py:33`、`tasks/like_reconcile.py:74`、`tasks/user_reconcile.py:43`、`tasks/data_tasks.py:39`

**根因**：这些任务直接操作 `db.session`/repository，但 `tasks/base_task.py` 与 `core/celery_app.py` 未提供 Flask app context；
在上下文外 `RuntimeError: Working outside of application context`。当前 compose 无 celery worker，属潜在问题。

**修法**（context-aware base task）：

```python
# tasks/base_task.py
from app import create_app
_flask_app = create_app()

class ContextTask(MonitoredTask):
    def __call__(self, *args, **kwargs):
        with _flask_app.app_context():
            return super().__call__(*args, **kwargs)
```

`core/celery_app.py` 的 `Celery(...)` 加 `task_cls=ContextTask`（或 `base=ContextTask`）。
注意 `create_app()` 会产生自己的 Redis/DB 连接，worker 侧单例即可；导入期建 app 要避免循环导入（可在 `tasks/__init__.py` 延迟创建）。

**验证**：起 worker 执行 `reconcile_like_counts.delay()` 不报 context 错误。

---

## 2H. tooling / cleanup

### B47 🟠 `manage_es.py` 引用了不存在的属性

**位置**：`manage_es.py:77,79,80,82,86,122`

**根因**：`PostDocument` 只有 `get_index_name()`，没有 `INDEX_NAME` → `AttributeError`。

**修法**：全部改为 `PostDocument.get_index_name()`（包括 `stats['indices'][...]` 的取值键）。

**验证**：`python manage_es.py status` 正常输出。

---

### B48 🟠 `pessimistic_get` 不加锁 / 默认模式报错

**位置**：`utils/lock_utils.py:72-81`

**根因**：`if filter_by: ... elif lock_mode=='share': ... else: raise` ——
只要传了 `filter_by`（文档示例正是这种用法），就既不 `FOR UPDATE` 也不报错，静默无锁；
不传 `filter_by` 且默认 `lock_mode='update'` 时直接 `ValueError`。

**修法**：

```python
for f in filters:
    query=query.filter(f)
if filter_by:
    query=query.filter_by(**filter_by)
if lock_mode=='update':
    query=query.with_for_update()
elif lock_mode=='share':
    query=query.with_for_update(read=True)
else:
    raise ValueError(f'不支持的lock_mode:{lock_mode}')
return query.first()
```

---

### B49 🟢 错误日志上下文键名不对

**位置**：`app/common/error_handlers.py:19,23`

**根因**：`g.get("request_start_time", ...)` 和 `g.get("user_id", ...)` 从未被设置；
实际中间件设的是 `g.start_time`（`logging_middleware.py:47`）和 `g.current_user`（`auth_middleware.py:175`）。
导致错误日志 `elapsed_time` 恒 0、`user_id` 恒 `N/A`。

**修法**：

```python
elapsed_time = round(time.time() - g.get("start_time", time.time()), 3)
user = g.get("current_user", None)
"user_id": getattr(user, "id", "N/A")
```

---

### B50 🟢 日志 f-string 漏 `f` 且 `e` 未绑定

**位置**：`app/posts/services.py:251-252`

**修法**：

```python
# before
except Exception:
    logging.warning('发布帖子更新事件失败，不影响主进程：{e}')
# after
except Exception as e:
    logger.warning(f'发布帖子更新事件失败，不影响主进程：{e}')
```

---

### B51 🟡 延迟失效窗口内通知会丢未读数

**位置**：`app/notifications/cache.py:72-77`（miss 返回 False）与 `:199`（`clear_unread` 用 `SET 0`）

**根因**：`double_invalidate_unread` 先删 key，延迟任务/线程再 `clear_unread` 写成 0；
窗口内新通知走 `increment_unread`，因 key 不存在直接返回 False，随后 0 覆盖，未读数 60s 内为 0。

**修法**：
- 延迟第二步改成 `delete`（删除 key），不要 `SET 0`；
- `increment_unread` miss 时改为 `INCR`（或 `SETNX 1`）而不是静默放弃，让下次读以缓存为准。
- 更稳妥：`get_unread_count` 缓存 miss 时始终从 DB 重算（已由 B14 的 `force_master` 分支覆盖一部分）。

---

### B52 🟢 Feed 文档/实现默认值不一致

**位置**：`app/feeds/routes.py:40,53`（parser 默认 20，`get_pagination_params()` 默认 10）；`:13` `'apikey'`

**修法**：

```python
page, per_page = get_pagination_params(default_per_page=20)   # 或本方案改 cursor 后废弃
# security type 用 'apiKey'
```

> item 9 改 cursor 后 `per_page`/`page` 会被 `limit` 取代，此项若执行 item 9 可忽略；`'apikey'` 顺手改。

---

## Part 2 修复优先级

```
第一梯队（功能/安全，必须修）
  B17  B18  B25  B36  B38  B41  B42  B43  B47
第二梯队（数据正确性）
  B15 B16 B20 B21 B22 B23 B28 B29 B31 B32 B33 B44 B45
第三梯队（可观测/健壮/潜在）
  B19 B24 B26 B27 B30 B34 B37 B46 B48 B51
清理
  B35 B39 B40 B49 B50 B52
```

> 说明：B28 是 B2/B13/B14 的根（`RedisCache.exists` 无 `for_write`），**建议先修 B28 再修 Part 1 的黑名单/一致性相关项**。
> B36/B38 属于"平时没走到、一走到就崩"的封装层，建议连同 B12 的死代码一起清。
