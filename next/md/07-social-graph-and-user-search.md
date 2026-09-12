# 07 — 他人粉丝/关注列表 + 用户搜索（items 17 / 18）

---

## 17. 他人粉丝 / 关注列表

### 现状
`/follows/*` 全部只查当前用户（`app/follows/routes.py`）：
- `GET /follows/following/list` → `FollowService.get_following(current_user_id,...)`
- `GET /follows/followers` → `FollowService.get_followers(current_user_id,...)`
- `GET /follows/following/mutual` → `FollowService.get_mutual_follows(current_user_id,...)`

但 **service 早已支持任意 `user_id` 参数**（`app/follows/services.py:115,132,149`），
缺的只是"按路径参数查"的路由 + 返回结构化用户信息。

### 17.1 新增路由（RESTful 风格）

保留现有"我"的接口（前端"我的关注/粉丝"页直接用），新增"他人"的：

| 新路由 | 说明 |
|--------|------|
| `GET /follows/users/<int:user_id>/following` | 某人关注的人 |
| `GET /follows/users/<int:user_id>/followers` | 某人的粉丝 |
| `GET /follows/users/<int:user_id>/mutual` | 某人的互关（可选） |

`app/follows/routes.py` 新增（`@jwt_required(optional=True)`，未登录也能看）：

```python
@api.route('/users/<int:user_id>/following')
class UserFollowing(Resource):
    @api.doc(description='获取指定用户关注的人', params={'user_id':'用户ID','page':'页码','per_page':'每页数量'})
    @api.response(200, '获取成功')
    @jwt_required(optional=True)
    def get(self, user_id):
        page, per_page = get_pagination_params()
        result = FollowService.get_following(user_id=user_id, page=page, per_page=per_page)
        return paginated_response(result['items'], result['pagination'], message='获取成功'), 200


@api.route('/users/<int:user_id>/followers')
class UserFollowers(Resource):
    @api.doc(description='获取指定用户的粉丝')
    @api.response(200, '获取成功')
    @jwt_required(optional=True)
    def get(self, user_id):
        page, per_page = get_pagination_params()
        result = FollowService.get_followers(user_id=user_id, page=page, per_page=per_page)
        return paginated_response(result['items'], result['pagination'], message='获取成功'), 200
```

### 17.2 返回结构：直接给"人"，不要给 Follow 关系

现状 `follow_response_schema`（`app/follows/schemas.py:16-23`）返回：
```json
{ "id":1, "follower_id":1, "followed_id":2,
  "follower": {"id":1,"username":"a"}, "followed": {"id":2,"username":"b"} }
```
列表页要的是"关注列表里的人"，应返回：
```json
{ "id": 2, "username": "b", "relation_created_at": "...", "is_following": true }
```

`app/follows/services.py` 改造（顺带修 5.5 的 mutual 序列化 bug）：

```python
from app.users.schemas import UserSchema  # 或 PublicUserSchema（doc 04）

@staticmethod
def get_following(user_id, page=1, per_page=20):
    user = user_repository.get_by_id(user_id)
    if not user or not getattr(user, "is_active", True):
        raise ResourceNotFoundError("用户不存在或已被禁用")
    result = follow_repository.list_following(user_id, page=page, per_page=per_page)
    # result['items'] 是 Follow 列表，取 .followed
    items = [follow_response_schema_with_user(f) for f in result["items"]]
    return {"items": items, "pagination": result["pagination"]}


def follow_response_schema_with_user(follow):
    target = follow.followed  # 关注列表；粉丝列表用 follow.follower
    return {"id": target.id, "username": target.username}
```

> 如果需要 `is_following`（当前登录者是否也关注了列表里的人），用 `FollowCache.is_following` 批量判断；
> 列表页 N+1 需注意，建议用 `follow_repository` 批量查，或先不做该字段。

### 17.3 分页统一

按 doc 01 §5，service 返回 `{"items": [...], "pagination": {...}}`，路由用 `paginated_response`。
把 `app/follows/services.py:124,141,163` 的 `follows` / `mutual_users` 键统一改成 `items`。

### 17.4 隐私与性能

- **隐私**：当前产品无"私密账号"，粉丝/关注列表默认公开。若后续加私密账号，需在此判断
  `target.is_private and not FollowService.is_following(me, target)` → 返回 403 或隐藏列表。
- **性能**：`Follow` 已有索引 `idx_follower_created` / `idx_followed_created`
  （`app/follows/models.py:19-20`），分页 + 排序命中，无需新增。
- **查询走从库**：`FollowRepository._read_session()` 已是从库（`repositories.py:15-17`）。

### 17.5 顺带修复（已在 doc 01 §5.5 提过）
`app/follows/services.py:161` `UserListSchema().dump(items, many=True)` 是错误的，
会导致互关列表返回一堆分页容器。改为 `UserSchema(many=True).dump(items)`。

---

## 18. 用户搜索

### 现状
只能搜帖子。`UserRepository.search_by_keyword`（`app/users/repositories.py:80-91`）**已经实现**，
但从没被 service/route 调用（死代码）。

### 18.1 路由 `GET /users/search`

⚠️ 路由顺序：`/users/search` 必须放在 `/users/<int:user_id>`（doc 04）之前也能工作（静态优先），
但为可读性建议紧挨着放在 `/me` 附近，并用 `type=str` 参数。

`app/users/routes.py`：

```python
@api.route('/search')
class UserSearch(Resource):
    @api.doc(description='按用户名搜索用户',
             params={'q':'关键词','page':'页码','per_page':'每页数量'})
    @api.response(200, '搜索成功')
    @jwt_required(optional=True)
    def get(self):
        q = request.args.get('q', '').strip()
        if not q:
            return fail_response(ResponseCode.PARAM_ERROR, '搜索关键词不能为空'), 400
        page, per_page = get_pagination_params()
        result = AuthService.search_users(q, page=page, per_page=per_page)
        return paginated_response(result['items'], result['pagination'],
                                  message='搜索用户成功'), 200
```

### 18.2 Service

`AuthService.search_users`：

```python
@staticmethod
def search_users(keyword: str, page: int = 1, per_page: int = 20) -> dict:
    keyword = keyword.strip()[:50]
    result = user_repository.search_by_keyword(keyword, page=page, per_page=per_page)
    items = public_user_schema.dump(result["items"], many=True)  # 脱敏
    USER_OPERATIONS.labels(action="search", result="success").inc()
    return {"items": items, "pagination": result["pagination"]}
```

> 复用 doc 04 的 `PublicUserSchema`，**绝不返回 email**。
> `search_by_keyword` 用 `ilike('%kw%')`，`%`/`_` 未转义——用户输入含 `%` 时会变通配符。
> 加转义：`kw.replace('%', r'\%').replace('_', r'\_')` 并配 `escape='\\'`（SQLAlchemy `ilike(..., escape='\\')`）。

### 18.3 排序与索引

现状 `order_by(User.username)`，对 `%kw%` 前缀不固定，索引 `users.username` 基本用不上（`%` 开头）。
小数据量可接受。要更好体验，二选一：

1. **前缀搜索**：`username.ilike(f'{kw}%')`，可用 `username` 索引，但只匹配前缀。
2. **ES 用户索引**（推荐，与帖子搜索一致）：
   - 新增 `services/search/document.py:UserDocument`（`username` 用 `ik_max_word` + `keyword` 子字段）。
   - `manage_es.py` 增加用户索引创建 + 重建。
   - 搜索走 ES，DB `search_by_keyword` 作为降级。
   - 用户注册/改名时 `event_bus.publish('user.updated')` 增量索引（可后置）。

MVP 先用 DB `ilike` + 转义，够用；把 ES 索引作为后续增强。

### 18.4 验证

```bash
curl -s "http://localhost:5000/users/search?q=smoke&page=1&per_page=10" \
  -H "Authorization: Bearer $TOKEN" | jq '.data.items[0]'
# 期望：只含 id/username/created_at/follower_count/...，无 email
```

---

## 改动清单

- [ ] `app/follows/routes.py`：`/users/<id>/following`、`/users/<id>/followers`（+ mutual 可选）
- [ ] `app/follows/services.py`：返回人而非关系；键改 `items`；修 mutual 序列化
- [ ] `app/follows/schemas.py`：新增用户列表项 schema（id/username）
- [ ] `app/users/routes.py`：`GET /users/search`
- [ ] `AuthService.search_users` + 关键词转义
- [ ] （可选）ES 用户索引
- [ ] 冒烟：他人关注列表、用户搜索脱敏
