# 04 — 用户资料 / 设置 / 帖子详情关注态（items 11 / 13 / 15 / 16）

---

## 11. `GET /users/<id>` 公开资料

### 现状
只有 `GET /users/me`（`app/users/routes.py:126-135`），做不了"别人的主页"。
`UserSchema`（`app/users/schemas.py:80`）含 `email`，直接复用会泄露隐私。

### 目标
- 路由：`GET /users/<int:user_id>`，`@jwt_required(optional=True)`（未登录也能看主页）。
- 返回脱敏字段：`id, username, created_at, follower_count, following_count, post_count`。
- 登录态额外返回：`is_following`（当前用户是否关注 TA）、`is_me`。
- **绝不返回** `email / is_admin / mfa_enabled / login_fail_count / lock_until`。

### 11.1 新增 schema `PublicUserSchema`

`app/users/schemas.py` 末尾：

```python
from utils.schema_fields import UTCDateTime  # 见 doc 01 §7

class PublicUserSchema(Schema):
    id = fields.Integer()
    username = fields.String()
    created_at = UTCDateTime()
    follower_count = fields.Integer(dump_default=0)
    following_count = fields.Integer(dump_default=0)
    post_count = fields.Integer(dump_default=0)

public_user_schema = PublicUserSchema()
```

### 11.2 Service：`AuthService.get_public_profile`

`app/users/services/auth_service.py` 新增：

```python
@staticmethod
def get_public_profile(target_id: int, current_user_id: int | None = None) -> dict:
    # 1. 强一致窗口 → 主库
    if UserCache.is_recently_modified(target_id):
        user = user_repository.get_by_id(target_id, force_master=True)
    else:
        user = user_repository.get_by_id(target_id, force_master=False)  # 从库
    if not user or not getattr(user, "is_active", True):
        raise ResourceNotFoundError("用户不存在")

    profile = public_user_schema.dump(user)
    profile["post_count"] = user.posts.filter_by(deleted_at=None).count() \
        if hasattr(user, "posts") else 0

    if current_user_id:
        from app.follows.services import FollowService
        profile["is_me"] = (int(current_user_id) == int(target_id))
        profile["is_following"] = (
            False if profile["is_me"]
            else FollowService.is_following(int(current_user_id), target_id)
        )
    return {"user": profile}
```

> `User` 没有 `post_count` 列，需实时 count（走 `user.posts` 动态关系，或加 `post_repository.count_by_user`）。访问自己的主页时可用已有缓存 `UserCache.get_profile` 再脱敏，但**公开资料不要走含 email 的 profile 缓存**，见 11.3。

### 11.3 缓存隔离（重要）

`UserCache.set_profile` 写的是含 email 的 `UserSchema`（`app/users/services/auth_service.py:44,76`）。
公开资料**不要复用它**，否则有泄露风险。两种做法：

1. **推荐**：新增 `UserCache` 方法，key = `user:public:{id}`，只存 `PublicUserSchema` 输出。
2. 简单做法：读 `get_profile` 后用 `PublicUserSchema().dump(dict)` 白名单过滤——但内存里仍有 email，防御纵深差。

```python
# app/users/cache.py 新增
@classmethod
def _public_key(cls, user_id): return f"user:public:{user_id}"

@classmethod
def get_public_profile(cls, user_id):
    return redis_cache.get(cls._public_key(user_id), for_write=False)

@classmethod
def set_public_profile(cls, user_id, data):
    return redis_cache.set(cls._public_key(user_id), data, expire=cls.PROFILE_TTL, for_write=True)
```

`UserCache.invalidate/double_invalidate` 里一并删 `_public_key`。

### 11.4 路由

`app/users/routes.py` 新增（放在 `/me` 之前/之后都可以，`int` 转换器不会吞掉静态路由）：

```python
@api.route('/<int:user_id>')
class UserPublic(Resource):
    @api.doc(description='获取用户公开资料', params={'user_id': '用户ID'})
    @api.response(200, '获取成功')
    @jwt_required(optional=True)
    def get(self, user_id):
        current_user_id = get_jwt_identity()
        result = AuthService.get_public_profile(user_id, current_user_id)
        return success_response(data=result, message='获取用户资料成功'), 200
```

> **路由冲突检查**：`users_bp` 已有 `/me`、`/logout`、`/refresh`、`/register`、`/login`。
> Werkzeug 静态规则优先于 `<int>` 动态规则，`/users/me` 不会被 `<int:user_id>` 匹配（`me` 无法转 int）。安全。

---

## 13. `PUT /users/me` + `PUT /users/me/password`

`ChangePasswordSchema`（`app/users/schemas.py:69`）已定义但没挂路由（死代码）。

### 13.1 资料更新 `PUT /users/me`

可改字段：`username`、`email`（`User` 模型只有这两个可改，见 `app/users/models.py:20-21`）。请求至少给一个。

新增 `UpdateProfileSchema`（`app/users/schemas.py`）：

```python
class UpdateProfileSchema(Schema):
    username = fields.Str(required=False,
        validate=validate.Length(min=4, max=50, error="用户名长度必须在4-50字符之间"))
    email = fields.Email(required=False, error_messages={'invalid': '邮箱格式无效'})

    @validates_schema
    def at_least_one(self, data, **kwargs):
        if not data.get('username') and not data.get('email'):
            raise ValidationError("至少提供一个要修改的字段")
```

Service：

```python
@staticmethod
def update_profile(user_id: int, data: dict) -> dict:
    user = user_repository.get_by_id(user_id, force_master=True)
    if not user or not user.is_active:
        raise ResourceNotFoundError("用户不存在")

    old_username, old_email = user.username, user.email
    new_username = (data.get("username") or "").strip() or None
    new_email = (data.get("email") or "").strip() or None

    if new_username and new_username != old_username:
        if user_repository.get_by_username(new_username, force_master=True):
            raise ValidationError("用户名已存在")
        user.username = new_username
    if new_email and new_email != old_email:
        if user_repository.get_by_email(new_email, force_master=True):
            raise ValidationError("邮箱已存在")
        user.email = new_email

    db.session.commit()

    # 延迟双删：旧 + 新的用户名/邮箱索引 + profile + public
    UserCache.double_invalidate(user.id, username=old_username, email=old_email)
    UserCache.invalidate_by_username(new_username)
    UserCache.invalidate_by_email(new_email)
    UserCache.mark_recently_modified(user.id, ttl=5)
    USER_OPERATIONS.labels(action="update_profile", result="success").inc()
    return {"user": UserSchema().dump(user)}   # 自己看完整资料可以带 email
```

路由：

```python
from app.users.schemas import UpdateProfileSchema
from .services.auth_service import AuthService

@api.route('/me')
class CurrentUser(Resource):
    @jwt_required()
    def get(self): ...

    @api.doc(description='更新当前用户资料')
    @api.response(200, '更新成功')
    @jwt_required()
    @validate_json(UpdateProfileSchema)
    def put(self):
        data = getattr(g, 'validated_json', request.get_json())
        result = AuthService.update_profile(get_jwt_identity(), data)
        return success_response(data=result, message='资料更新成功'), 200
```

> **注意**：`user_repository.get_by_username` 走从库，改名前查重用**主库**（`force_master=True`），避免主从延迟导致误判。

### 13.2 修改密码 `PUT /users/me/password`

复用现有 `ChangePasswordSchema`（`old_password/new_password`）。

Service（放 `AuthService` 或 `password_service`）：

```python
@staticmethod
def change_password(user_id: int, old_password: str, new_password: str) -> dict:
    user = user_repository.get_by_id(user_id, force_master=True)
    if not user or not user.is_active:
        raise ResourceNotFoundError("用户不存在")
    if not password_service.verify_password(user.password_hash, old_password):
        raise AuthenticationError("原密码错误")
    if old_password == new_password:
        raise ValidationError("新密码不能与原密码相同")
    if password_service.is_password_reused(user, new_password):
        raise ValidationError("不能使用最近5次使用过的密码")

    validation = security_manager.password_validator.validate(new_password)
    if not validation["is_valid"]:
        raise ValidationError(f'密码不符合要求: {validation["issues"]}')

    password_service.update_password(user, new_password)
    db.session.commit()
    UserCache.double_invalidate(user.id)
    USER_OPERATIONS.labels(action="change_password", result="success").inc()

    # 安全：改密后吊销所有 refresh token（配合 doc 08 的 token_version）
    AuthService._revoke_all_refresh_tokens(user.id)
    return {"message": "密码修改成功"}
```

路由：

```python
@api.route('/me/password')
class ChangePassword(Resource):
    @api.doc(description='修改当前用户密码')
    @api.response(200, '修改成功')
    @jwt_required()
    @validate_json(ChangePasswordSchema)
    @route_limit("5 per minute")
    def put(self):
        data = getattr(g, 'validated_json', request.get_json())
        result = AuthService.change_password(
            get_jwt_identity(), data["old_password"], data["new_password"]
        )
        return success_response(data=result, message='密码修改成功'), 200
```

---

## 15. 帖子详情补 `is_following`

现状：`GET /posts/<id>` 已返回 `has_liked`（`app/posts/routes.py:127`，service `app/posts/services.py:187-191`）。
详情页的"关注"按钮还缺 `is_following`。

改 `PostService.get_post`（`app/posts/services.py:186-191`）返回值：

```python
from app.follows.services import FollowService  # 顶部导入

post_author_id = post_dict.get("user_id")
is_following = False
if current_user_id and post_author_id and int(current_user_id) != int(post_author_id):
    is_following = FollowService.is_following(int(current_user_id), post_author_id)

return {"post": post_dict, "has_liked": has_liked, "is_following": is_following}
```

路由 `app/posts/routes.py:124-130`：

```python
return success_response(data={
    "post": post_data,
    "has_liked": result["has_liked"],
    "is_following": result.get("is_following", False),
}, message="获取帖子详情成功"), 200
```

> 循环依赖检查：`app/follows/services.py` 不 import `posts.services`，安全。
> 若担心冷启动耦合，也可在 **路由层** 调 `FollowService.is_following`（路由已 import `LikeService`，同层加一个 import 无问题）。

---

## 16. `/posts?user_id=` 支持任意用户 id（确认项）

### 结论：**已实现，无需改代码**，只需验证。

- 路由取值并透传：`app/posts/routes.py:64` `user_id = request.args.get('user_id', type=int)`；
  `:71` `user_id=user_id` 传给 `PostService.get_posts`。
- Service 透传：`app/posts/services.py:102-106` → `post_repository.list_posts(user_id=user_id)`。
- Repository 过滤 + 排序：`app/posts/repositories.py:72-74` `filter_by(user_id=user_id).order_by(created_at.desc())`。
- 索引：`app/posts/models.py:30` `index_post_created('user_id','created_at')`，命中。

### 验证命令

```bash
curl -s "http://localhost:5000/posts?user_id=2&page=1&per_page=20" \
  -H "Authorization: Bearer $TOKEN" | jq '.data.pagination'
# 期望：只返回 user_id=2 的帖子，pagination.total 正确
```

### 顺带确认（可选）
`list_posts` 的复合索引 `index_post_created(user_id, created_at)` 未覆盖 `is_published/deleted_at`，
过滤条件多了两个谓词。数据量大时可能回表。若用户主页 QPS 高，建议把索引改成
`(user_id, deleted_at, is_published, created_at)`（前缀顺序按选择率调），此为非必须优化。

---

## 改动清单

- [ ] `app/users/schemas.py`：`PublicUserSchema`、`UpdateProfileSchema`
- [ ] `app/users/cache.py`：`get/set_public_profile` + 失效联动
- [ ] `AuthService`：`get_public_profile` / `update_profile` / `change_password`
- [ ] `app/users/routes.py`：`GET /users/<id>`、`PUT /users/me`、`PUT /users/me/password`
- [ ] `PostService.get_post` + posts route：加 `is_following`
- [ ] doc 08 的 `_revoke_all_refresh_tokens`（改密联动）
- [ ] 冒烟：公开资料不含 `email`；改密后旧 refresh 失效
