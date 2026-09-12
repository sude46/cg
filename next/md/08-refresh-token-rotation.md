# 08 — Refresh Token 轮换 / 复用检测（item 19）

---

## 0. 先说一个必须先修的现存安全 bug

登出（`POST /users/logout`）**根本没生效**，因为黑名单 key 不一致：

| 位置 | 写入/读取的 Redis key |
|------|----------------------|
| 登出 `app/users/routes.py:155` → `utils/redis_util.py:107-111` | `setex("jwt_blacklist:{jti}")` |
| 实际生效的校验 `middlewares/auth_middleware.py:122` | `exists("{JWT_BLACKLIST_KEY}:{jti}")`，默认就是 `jwt:blacklist:{jti}` |
| 死代码 `core/extensions.py:52`（从未被调用，见下） | `sismember("jwt_blacklist", jti)` |

> `init_jwt`/`init_extensions`（`core/extensions.py`）全项目无调用；factory 在 `factory.py:49` 直接 `jwt.init_app(app)`，
> 真正注册的 loader 是 `middlewares/auth_middleware.py:135`（`factory.py:89` 调用 `init_auth_middleware`）。
> 所以 `core/extensions.py` 那段是**死代码**，应删除以免误导。

**修法**：所有撤销统一走已经挂到 app 上的 `current_app.revoke_token(jti, expires)`：

```python
# app/users/routes.py:137-161 logout
from flask import current_app
...
remain = max(0, int(exp - datetime.now(UTC).timestamp()))
jwt_payload = get_jwt()
current_app.revoke_token(jwt_payload["jti"], remain)   # 统一 key: jwt:blacklist:{jti}
```

并删除 `utils/redis_util.add_blacklist` 和 `core/extensions.py` 的 blocklist loader，避免第二套 key。

---

## 1. 现状

- 登录签发 access(1h) + refresh(30d)：`app/users/services/auth_service.py:71-72`，`create_refresh_token(identity=user.id)`。
  TTL 来自 `config/base.py:56-57`。
- 刷新 `POST /users/refresh`（`app/users/routes.py:113-123`）只回新 access，**refresh 原样复活**：
  `AuthService.refresh_token`（`auth_service.py:110-116`）返回 `{access_token, token_type, expires_in}`。
- 没有轮换、没有复用检测：一个 refresh 泄露后可被反复用到 30 天，且无法察觉。

> 另外 `security.py:15` 写 access 15min/refresh 7d，与 `config/base.py` 的 1h/30d 不一致——以 flask-jwt-extended 的 config 为准。

---

## 2. 目标模型：一段登录会话 = 一个 family

每次 `登录` 生成一个 `family_id (fid)`，该次登录的 refresh 轮换都保持同一 `fid`。
Redis 只保存每个 family **当前有效的 refresh jti**：

```
refresh:{fid}  ->  <current_jti>   (TTL = refresh 剩余有效期)
auth:ver:{uid} ->  <int token_version>   (全局撤销用)
```

JWT 附加 claims：

```python
create_refresh_token(
    identity=user.id,
    additional_claims={"fid": fid, "ver": current_version},
)
```

- `jti` 由 flask-jwt-extended 自动生成。
- `ver` 用于"改密/封禁后一次性吊销该用户所有 token"。

---

## 3. 流程

### 3.1 登录

```python
import uuid
fid = uuid.uuid4().hex
ver = int(redis.get(f"auth:ver:{user.id}") or 0)
access = create_access_token(identity=user.id, additional_claims={"ver": ver})
refresh = create_refresh_token(identity=user.id,
                               additional_claims={"fid": fid, "ver": ver})
redis.setex(f"refresh:{fid}", REFRESH_TTL, decode_jti(refresh))  # decode_jti = jwt decode 取 jti
```

> 也可让 `create_refresh_token` 后用 `flask_jwt_extended.decode_token(refresh)["jti"]` 取 jti。

### 3.2 刷新（轮换 + 复用检测，原子）

```python
# 1) @jwt_required(refresh=True) 已校验签名/类型；取 claims
claims = get_jwt()
uid, fid, old_jti, ver = claims["sub"], claims["fid"], claims["jti"], claims.get("ver", 0)

# 2) 全局版本校验（改密/封禁后旧 token 全部失效）
if ver != int(redis.get(f"auth:ver:{uid}") or 0):
    raise AuthenticationError("登录状态已失效，请重新登录")

# 3) 原子轮换：只有"当前 jti"能换，换成功才更新
new_jti = decode_jti(create_refresh_token(identity=uid,
                    additional_claims={"fid": fid, "ver": ver}))
new_access = create_access_token(identity=uid, additional_claims={"ver": ver})

LUA = """
local cur = redis.call('GET', KEYS[1])
if not cur then return -1 end            -- family 不存在（已撤销/过期）
if cur ~= ARGV[1] then return 0 end      -- 复用：presented 不是当前值
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""
r = redis.eval(LUA, 1, f"refresh:{fid}", old_jti, new_jti, REFRESH_TTL)
if r == -1:
    raise AuthenticationError("登录已过期，请重新登录")
if r == 0:
    # 复用检测命中：整个 family 作废
    redis.delete(f"refresh:{fid}")
    current_app.revoke_token(old_jti, REFRESH_TTL)
    logger.warning("refresh token 复用 detected: user=%s fid=%s", uid, fid)
    raise AuthenticationError("检测到令牌复用，请重新登录")

# 4) 把旧 refresh 加入黑名单（防止竞态窗口内重放）
current_app.revoke_token(old_jti, REFRESH_TTL)
return {"access_token": new_access, "refresh_token": <新 refresh 原文>, "token_type": "bearer", "expires_in": 3600}
```

> **返回值要同时给新 refresh**（现状只给 access）。前端必须用新 refresh 覆盖旧的。
> 并发刷新时，Lua 的 compare-and-set 保证只有一个请求成功，另一个被判为复用——若前端存在
> 并发刷新（多个 tab），可在客户端做单飞（single-flight），或服务端容忍 5s 宽限（见 §6）。

### 3.3 登出

```python
current_app.revoke_token(access_jti, remain_access)
redis.delete(f"refresh:{fid}")          # 作废该设备的 refresh family
```

### 3.4 全局撤销（改密 / 封禁 / 忘记密码重置）

```python
redis.incr(f"auth:ver:{uid}")           # 所有旧 access/refresh 的 ver 过期
# 可选：遍历该用户所有活跃 fid（维护 auth:fids:{uid} SET）逐个删除，立即清理内存
```

- 在 doc 04 的 `change_password` 里调用。
- `access` 也要校验 `ver`：在 `auth_middleware.pre_auth_check` 里（`middlewares/auth_middleware.py:148`）加：

  ```python
  ver = jwt_data.get("ver", 0)
  if int(ver) != int(redis.get(f"auth:ver:{user_id}") or 0):
      raise AuthenticationError("登录状态已失效，请重新登录")
  ```

  注意用 `user_id` 需先解析，且 `ver` claim 对老 token 不存在 → 默认 0，与 `auth:ver` 缺省 0 一致，兼容。

---

## 4. 黑名单 vs token_version 的分工

| 机制 | 粒度 | 用途 |
|------|------|------|
| `jwt:blacklist:{jti}` | 单个 token | 登出、轮换后旧 refresh 作废 |
| `refresh:{fid}` | 单设备会话 | 轮换的当前值 + 复用检测 |
| `auth:ver:{uid}` | 用户全局 | 改密/封禁，一键吊销全部 |

三者缺一不可。只做 jti 黑名单无法检测复用；只做 version 无法精确轮换。

---

## 5. 配置 / 常量

- 统一 refresh TTL 来源：`config/base.py:57 JWT_REFRESH_TOKEN_EXPIRES`（当前 30 天）。
  建议缩短到 **7~14 天**（轮换后风险已降低，但泄露窗口更小）。
- `JWT_ACCESS_TOKEN_EXPIRES` 可保持 1h，或按 `security.py` 设 15min（推荐）。
- 新增 Redis key 前缀集中定义（如 `config/base.py` 的 `REDIS_KEY_PREFIX`）。

---

## 6. 边界与取舍

| 场景 | 处理 |
|------|------|
| 多设备 | 每次登录独立 `fid`，互不影响。无需额外处理。 |
| 多 tab 并发刷新 | 客户端 single-flight；或服务端给"复用"5s 宽限：若 `cur` 是被刚刚轮换掉的旧 jti 且距轮换 <5s，视为竞态而非攻击（记 `refresh:{fid}:prev`）。MVP 先不做宽限。 |
| Redis 故障 | `refresh:{fid}` 读不到 → 拒绝刷新（安全优先）。可降级放行但会削弱复用检测。 |
| 移动端后台 | refresh 轮换后必须持久化新 token；否则下次后台刷新用旧 token 触发复用误判。前端要处理好。 |
| 老 token | 无 `fid` claim 的 refresh 一律拒绝（强制重新登录），因为无法追踪。一次性兼容开关 `ALLOW_LEGACY_REFRESH=false`。 |

---

## 7. 测试

```python
def test_refresh_rotates_and_detects_reuse(app, client):
    # 登录
    r1 = login(...); refresh_1 = r1["data"]["refresh_token"]
    # 第一次刷新：成功，拿到 refresh_2
    r2 = client.post("/users/refresh", headers={"Authorization": f"Bearer {refresh_1}"})
    assert r2.status_code == 200
    refresh_2 = r2.json["data"]["refresh_token"]
    assert refresh_2 != refresh_1

    # 用旧 refresh_1 再刷：应 401（复用检测）
    r3 = client.post("/users/refresh", headers={"Authorization": f"Bearer {refresh_1}"})
    assert r3.status_code == 401

    # 复用后整个 family 作废：refresh_2 也不能再用
    r4 = client.post("/users/refresh", headers={"Authorization": f"Bearer {refresh_2}"})
    assert r4.status_code == 401
```

```python
def test_change_password_revokes_all_tokens(...):
    # 改密后，旧 access 和旧 refresh 都应 401
```

同时补登出测试：登出后旧 access 访问受保护接口应 401（验证 §0 的 key 不一致已修）。

---

## 8. 改动清单

- [ ] 修 §0：logout 改用 `current_app.revoke_token`；删 `utils/redis_util.add_blacklist`、`core/extensions.py` blocklist loader
- [ ] 登录注入 `fid` + `ver`，写 `refresh:{fid}`
- [ ] 刷新实现轮换 Lua + 复用检测，返回新 refresh
- [ ] `auth_middleware.pre_auth_check` 加 `ver` 校验
- [ ] `change_password`/封禁 调 `incr auth:ver:{uid}`
- [ ] `config/base.py` refresh TTL 调整（可选）
- [ ] 单测：轮换、复用、登出、改密吊销
