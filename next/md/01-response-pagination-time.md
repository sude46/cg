# 01 — 响应契约统一（items 5 / 6 / 7 / 8）

## 5. 分页结构统一为 `{ items, pagination: {...} }`

### 5.1 现状盘点

| 模块 | 位置 | 现状列表键 | 备注 |
|------|------|-----------|------|
| posts 列表 | `app/posts/routes.py:76-83` | `posts` | 还有 `liked_post_ids`（list） |
| posts 搜索 | `app/posts/routes.py:217-225` | `posts` | 还有 `search_engine` |
| comments | `app/comments/routes.py:125` | `items` | 已符合 |
| notifications | `app/notifications/routes.py:81` | `items` | service 返回 `{items,pagination,unread_count}` |
| follows following | `app/follows/routes.py:107` | `follows` | |
| follows followers | `app/follows/routes.py:129` | `follows` | |
| follows mutual | `app/follows/routes.py:152` | `mutual_users` | service 序列化还有 bug，见 5.5 |
| likes my-likes | `app/likes/routes.py:129` | `items` | 已符合 |
| feeds | `app/feeds/services.py:52-57` | `items` | 但分页方式是 page/per_page，本轮改 cursor，见 doc 02 |
| 旧工具 | `utils/response.py:77` | `list/page/size/total` | 无人调用，删 |
| 另一套旧工具 | `utils/helpers.py:9` | `list/page/size/total` | 无人调用，删 |

`utils/pagination.py:get_pagination_params()` 已被 comments/feeds/posts-search/follows 使用，可保留。
底层 `app/common/database.py:PaginationUtils.paginate()` 已经返回标准 `{items, pagination:{page,per_page,total,pages,has_next,has_prev}}`，**这是唯一的真相源，不要另起一套**。

### 5.2 改法：response 层加两个 helper

在 `utils/response.py` 末尾新增（先修 B1）：

```python
def build_pagination(page, per_page, total):
    """单一分页真源，结构固定。"""
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or 20))
    total = max(0, int(total or 0))
    pages = (total + per_page - 1) // per_page if total else 0
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def paginated_response(items, pagination, extra=None, message="操作成功"):
    """
    统一分页响应。
    - items: 当前页对象列表
    - pagination: 已是 build_pagination / pagination_utils.paginate 的产物
    - extra: 模块级元数据（如 liked_post_ids/unread_count/source）
    """
    data = {"items": items or [], "pagination": pagination or build_pagination(1, 20, 0)}
    if extra:
        data.update(extra)
    return success_response(data=data, message=message)
```

同时**删除** `utils/response.py:pagination_response` 和整个 `utils/helpers.py`（确认无引用后）。

### 5.3 各模块路由改法

**posts 列表** `app/posts/routes.py:74-83`：

```python
posts_data = posts_schema.dump(result["items"])
return paginated_response(
    posts_data,
    result["pagination"],
    extra={"liked_post_ids": list(result.get("liked_post_ids", []))},
    message="获取帖子列表成功",
), 200
```

**posts 搜索** `app/posts/routes.py:210-225`：同上，`extra` 再加 `search_engine`。

**follows** `app/follows/routes.py`：

```python
# 107 / 129 行
return paginated_response(result["items"], result["pagination"], message="获取成功"), 200
# 152 行
return paginated_response(result["items"], result["pagination"], message="获取成功"), 200
```

对应把 service 返回的 key 从 `follows` / `mutual_users` 改成 `items`：

- `app/follows/services.py:124` `return {'follows': items, ...}` → `return {'items': items, 'pagination': ...}`
- `app/follows/services.py:141` 同上
- `app/follows/services.py:163` `return {'mutual_users': users, ...}` → `{'items': users, ...}`

**notifications** `app/notifications/routes.py:81`：

```python
return paginated_response(
    notifications["items"],
    notifications["pagination"],
    extra={"unread_count": notifications["unread_count"]},
    message="获取通知列表成功",
), 200
```

**likes / comments** 已经是 `items`，只需把路由里的 `success_response(data=result)` 换成 `paginated_response(result["items"], result["pagination"])`，让语义显式。

### 5.4 搜索的分页字段名不一致（顺带修）

`services/search/services.py:56-63` 用的是 `total_pages`，其余模块是 `pages`。统一为 `pages`：

```python
"pagination": {
    "page": page, "per_page": per_page, "total": total,
    "pages": max(1, total_pages), "has_next": page < total_pages, "has_prev": page > 1,
},
```

### 5.5 follows mutual 的序列化 bug（item 17 前置）

`app/follows/services.py:159-161`：

```python
from app.users.schemas import UserListSchema
users = UserListSchema().dump(result.get("items", []), many=True)
```

`UserListSchema` 是"分页容器"，对**列表**用 `many=True` 会 dump 出一堆 `{items,total,...}`，前端拿不到用户字段。应改为用**单用户 schema 的 many**：

```python
from app.users.schemas import UserSchema   # 或新建 PublicUserSchema，见 doc 04
users = UserSchema(many=True).dump(result.get("items", []))
```

（`get_mutual_follows` 返回的 query 已经是 `User` 列表，见 `app/follows/repositories.py:113-125`。）

---

## 6. 错误响应字段统一

### 6.1 现状：**实际生效**的错误处理器是 `app/common/error_handlers.py`（重要更正）

factory 注册的是这一套（`core/factory.py:4`、`:95`）：

```python
from app.common.error_handlers import register_error_handlers
...
register_error_handlers(app)
```

所以**当前运行时**的错误格式有 4 种，且都跟"成功响应"不一致：

| # | 触发路径 | 代码位置 | 实际返回 |
|---|----------|----------|----------|
| 1 | `BaseError` 子类（Validation/NotFound/Permission/Auth/DB/RateLimit） | `app/common/error_handlers.py:36` → `app/common/exceptions.py:25 to_dict()` | `{"error_code":10001,"message":"...","details":{}}` |
| 2 | 404 / 405 | `error_handlers.py:40,45` → 同上 | 同 #1 |
| 3 | 未捕获异常 | `error_handlers.py:76-81 handle_global_exception` | `{"code":5000,"msg":"...","request_id":"...","details":null}`（用了 `msg` 和 `code`，**与 #1 不一致**） |
| 4 | flask-limiter 限流 | `middlewares/rate_limit_middleware.py:46` | `{"code":429,"error":"...","retry_after":N}` |
| 5 | 路由里手动 `fail_response` | `utils/response.py:56` | `{"code":...,"error":"...","request_id":"..."}` |

> ⚠️ `middlewares/error_middleware.py:init_error_handlers` **是死代码**（全项目只有 `tests/unit/test_middlewares.py:208` 引用它，factory 从未调用）。
> 写方案时不要改它，直接删掉，否则会误以为改了实际行为。

### 6.2 目标格式

```json
{ "code": 10001, "message": "帖子内容不能为空", "request_id": "..." }
```

429 额外带 `retry_after`；字段级校验错误额外带 `details: {...}`（仅非空时出现）。

### 6.3 改法（按生效路径，逐个改）

**a. `app/common/exceptions.py:to_dict`**：把 `error_code` 统一成 `code`

```python
def to_dict(self) -> dict:
    return {
        "code": self.error_code,
        "message": self.message,
        "details": self.details,
    }
```

**b. `app/common/error_handlers.py:handle_base_error`**：补 `request_id`，`details` 非空才带

```python
def handle_base_error(e: BaseError):
    request_id = g.get("request_id", "N/A")
    logging.getLogger("flask.app").warning(
        f"[CUSTOM ERROR] request_id={request_id}, code={e.error_code}, msg={e.message}"
    )
    body = {"code": e.error_code, "message": e.message, "request_id": request_id}
    if e.details:
        body["details"] = e.details
    response = jsonify(body)
    response.status_code = e.status_code
    return response
```

**c. `app/common/error_handlers.py:handle_global_exception`**：`msg` → `message`

```python
return jsonify({
    "code": error_code,
    "message": msg,
    "request_id": log_extra["request_id"],
}), 500
```

**d. `utils/response.py:fail_response`**（供路由 `return fail_response(...), 400` 用）

```python
def fail_response(code, error_msg, details=None, request_id=None):
    request_id = request_id or getattr(g, "request_id", None) or generate_request_id()
    response_data = {"code": code, "message": error_msg, "request_id": request_id}
    if details:
        response_data["details"] = details
    current_app.logger.error(f"[FAIL] request_id={request_id}, response={response_data}")
    return response_data
```

**e. `middlewares/rate_limit_middleware.py:46`**：统一格式

```python
@app.errorhandler(RateLimitExceeded)
def handle_rate_limit(e):
    body = {
        "code": 429,
        "message": "请求过于频繁，请稍后重试",
        "request_id": g.get("request_id", "N/A"),
        "retry_after": getattr(e, "retry_after", 60),
    }
    return body, 429
```

**f. 删除死代码 `middlewares/error_middleware.py`**，并删除 `tests/unit/test_middlewares.py:208-210` 对它的引用（见 `00-pre-existing-bugs.md`）。

### 6.4 测试同步

- `grep -rn '"error"' app middlewares utils` 应只剩日志/异常对象属性，不含响应字典。
- 断言从 `resp["error"]` 改 `resp["message"]`；从 `resp["error_code"]` 改 `resp["code"]`。
- 错误响应现在也带 `request_id`，可与日志关联排查。

---

## 7. 时间格式统一 ISO8601 UTC（`+00:00`）

### 7.1 现状

- `app/posts/schemas.py:8-14` 定义了 `IsoDateTime`，但 `PostSchema` **没用它**（第 76-77 行用的是普通 `fields.DateTime`），这属于死代码。
- 通知/评论/点赞/关注/用户 的 `created_at` 全部是 `fields.DateTime`，序列化 naive → `2026-09-11T07:30:00`（无时区）。
- DB 里存的是 naive UTC（`app/common/database.py:utcnow()` 返回 `datetime.now(UTC).replace(tzinfo=None)`）。
- ES 索引时 `services/search/document.py:101-102` 用 naive `.isoformat()`，搜索返回的时间串也无时区。

### 7.2 新建统一字段 `utils/schema_fields.py`

```python
from datetime import UTC, datetime

from marshmallow import fields


class UTCDateTime(fields.DateTime):
    """对外统一：带 +00:00 的 ISO8601 UTC 字符串。"""
    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)      # 库内 naive UTC
        else:
            value = value.astimezone(UTC)
        return value.isoformat()                    # 2026-09-11T07:30:00+00:00
```

### 7.3 替换所有对外的 `fields.DateTime`

| 文件 | 字段 |
|------|------|
| `app/posts/schemas.py:76-77,81` | `created_at` `updated_at` `deleted_at`（并删掉死类 `IsoDateTime`） |
| `app/comments/schemas.py` | `created_at/updated_at/deleted_at` |
| `app/likes/schemas.py` | `created_at` |
| `app/follows/schemas.py:21` | `created_at` |
| `app/notifications/schemas.py:23` | `created_at` |
| `app/users/schemas.py:88-89` | `created_at/last_login` |

写法：`created_at = UTCDateTime(attribute="created_at")`。
（只改序列化不影响 load；`UTCDateTime` 继承 `fields.DateTime`，load 行为不变。）

### 7.4 其它时间输出点

- 错误响应时间：`middlewares/error_middleware.py:80` 已确认是死代码（见 §6.1）。生效的 `app/common/error_handlers.py` **不返回 timestamp**，无需处理；若要加，用 `datetime.now(UTC).isoformat()`（`+00:00`）。
- `services/search/document.py:102` 索引时补时区：`doc['created_at'].replace(tzinfo=UTC).isoformat()`，并**重建索引**（旧数据是 naive）：

  ```bash
  docker exec -it weibo-app python manage_es.py reindex   # 按项目实际命令
  ```
- `PostService.search_posts` 返回的是 ES `_source` 原文。索引重建前，可在 `services/search/repositories.py:search` 出口做一次兜底：把 `created_at` 字符串无 `+` 且非 `Z` 时补 `+00:00`。索引重建后可去掉兜底。

### 7.5 验证

```python
# 冒烟/单测断言
from datetime import datetime
dt = datetime.fromisoformat(detail["created_at"])
assert dt.tzinfo is not None, "必须是带时区的 ISO8601"
assert detail["created_at"].endswith("+00:00")
```

---

## 8. `data` 为空返回 `{}` 的约定（文档化）

### 8.1 现状

`utils/response.py:44-48` 在 B1 修复后天然是 `data or {}`，即空返回 `{}`。
但**列表接口**如果直接 `success_response(data=[])` 会返回 `data: []`（与 `{}` 约定冲突）。

### 8.2 改法

- 约定写死在 response 层：`success_response` 对 `None` 输出 `{}`；对 `[]` **不做转换**（列表接口应返回分页对象，不应直接传 list）。
- 所有列表接口统一走 `paginated_response`，天然满足 `data.items=[]`。
- 写进 `docs/swagger_template.yml`：

  ```yaml
  EmptyData:
    type: object
    description: 无业务数据时为 {}；列表接口请使用 items+pagination 结构
  ```

- 在各模块 `@api.response(200, ...)` 描述里加一句："无数据时 `data` 为 `{}`"。

### 8.3 工作量

纯文档，10 分钟。**不改代码逻辑**（除 B1）。

---

## 9. 改动清单（checklist）

- [ ] 修 B1：`utils/response.py:46`
- [ ] 新增 `build_pagination` / `paginated_response`；删 `pagination_response`、删 `utils/helpers.py`
- [ ] posts routes：列表 + 搜索 → `paginated_response(extra=...)`
- [ ] follows service/routes：`follows`/`mutual_users` → `items`，修 mutual 序列化
- [ ] notifications route：列表 → `paginated_response`
- [ ] likes/comments route：显式 `paginated_response`
- [ ] `services/search/services.py`：`total_pages` → `pages`
- [ ] 错误响应统一：`app/common/exceptions.to_dict`、`app/common/error_handlers`、`utils/response.fail_response`、`rate_limit_middleware` 全改 `{code,message,request_id}`；删死代码 `middlewares/error_middleware.py`
- [ ] 新增 `utils/schema_fields.py:UTCDateTime`，替换 6 个 schemas 的 datetime 字段
- [ ] ES 索引时间补时区 + 重建索引
- [ ] 更新 `tests/smoke/test_smoke.py` 断言（见 README §4）
- [ ] 更新 swagger 文档与 `docs/swagger_template.yml`
