# P1 改造方案总览（items 5–20）

> 目的：本目录只放**实施方案**，不改代码。每个文件给出「改哪些文件、改成什么样、怎么验证、有什么坑」。
> 前端尚未落地，因此可以**直接切换契约，不做兼容**（见 item 6 的结论）。

---

## 0. 先决条件：开工前必须先修现存 bug

> **详细改法（含 before/after、验证命令）见 [`00-pre-existing-bugs.md`](./00-pre-existing-bugs.md)。**
> 这些不是本次需求，但会直接让"统一契约"无法验证，必须先修。

| ID | 严重度 | 位置 | 问题 |
|----|--------|------|------|
| B1 | 🔴 | `utils/response.py:46` | `escaped_data` 未定义 → 每次 `success_response()` 都 `NameError`，整个 API 全挂 |
| B2 | 🔴 | `app/users/routes.py:155` | 登出写 `jwt_blacklist:{jti}`，校验读 `jwt:blacklist:{jti}` → 登出完全不生效 |
| B3 | 🟠 | `app/feeds/handlers.py:24` | `FeedServices` 拼写错误 → 删帖后 Feed 清理崩溃，时间线残留 |
| B4 | 🟡 | `app/feeds/handlers.py:16` | naive UTC 用 `.timestamp()` 按本地时区解释 → Feed score 偏移 |
| B5 | 🟠 | `app/likes/services.py:82` | `from comments.cache` 路径错误 → 评论点赞 500 |
| B6 | 🟠 | `services/search/document.py:201` | 查 `username` 但 mapping 是 `user_name` → 按作者名搜 0 结果 |
| B7 | 🟡 | `app/follows/services.py:46` | 关注时给被关注者加 `following_count`（应为关注者） |
| B8 | 🔴 | `middlewares/auth_middleware.py:172` | 校验不存在的 `user.status` → 禁用用户仍可访问 |
| B9 | 🟡 | `app/follows/services.py:34` | `is_actice` 拼写错误 → 禁用用户可关注 |
| B10 | 🟠 | `app/follows/services.py:161` | 互关列表序列化错误（分页容器当列表 dump） |
| B11 | 🟢 | `app/posts/services.py:54,80` | 发帖成功指标累加两次 |
| B12 | 🟢 | 多处 | 死代码：`middlewares/error_middleware.py`、`core/extensions.init_*`、`utils/helpers.py` 等 |
| B13 | 🟠 | `middlewares/auth_middleware.py:182` | `AuthenticationError(..., code=401)` 传了不存在的 kwarg |
| B14 | 🟡 | `app/notifications/services.py:140` | 未读数缓存 miss 时忽略强一致窗口，可能读从库旧值 |

修复顺序建议：`B28 → B1 → B2/B8/B13 → ...`；完整清单与详细改法见 `00-pre-existing-bugs.md`（Part 1 为 B1–B14，Part 2 为深度审计追加的 B15–B52，共 52 项）。

> **重要更正**：实际生效的错误处理器是 `app/common/error_handlers.py`（`core/factory.py:4,95` 注册），
> `middlewares/error_middleware.py` 是**死代码**（仅测试引用）。doc 01 §6 已按此更正，别改错文件。

---

## 1. 文件索引

| 文档 | 覆盖 item | 预估 |
|------|-----------|------|
| [`00-pre-existing-bugs.md`](./00-pre-existing-bugs.md) | 开工前置：B1–B14 详细修法 | 0.5~1d |
| [`01-response-pagination-time.md`](./01-response-pagination-time.md) | 5 分页统一、6 错误字段、7 时间格式、8 `data={}` 约定 | 1.5~2.5d |
| [`02-feed-cursor-pagination.md`](./02-feed-cursor-pagination.md) | 9 Feed 游标分页 | 1~2d |
| [`03-image-upload.md`](./03-image-upload.md) | 10 图片上传（OSS 直传签名 / 本地兜底） | 1~2d |
| [`04-user-profile-and-settings.md`](./04-user-profile-and-settings.md) | 11 公开资料、13 改资料/改密、15 详情补 `is_following`、16 `?user_id=` 确认 | 1.5d |
| [`05-notifications-and-sse.md`](./05-notifications-and-sse.md) | 12 未读数接口、20 SSE 推送 | 2.5~3.5d |
| [`06-posts-edit-delete-and-detail.md`](./06-posts-edit-delete-and-detail.md) | 14 编辑/删除接口确认、15（详情部分） | 0.5h |
| [`07-social-graph-and-user-search.md`](./07-social-graph-and-user-search.md) | 17 他人粉丝/关注、18 用户搜索 | 2d |
| [`08-refresh-token-rotation.md`](./08-refresh-token-rotation.md) | 19 refresh token 轮换/复用检测 | 1d |

---

## 2. 统一契约（所有文档共同遵守）

### 2.1 成功响应

```json
{ "code": 200, "data": {}, "message": "操作成功" }
```

- `data` **永远是对象**（不是 `null`、不是数组）。无业务数据时为 `{}`。
- 列表/分页数据一律放在 `data.items`。

### 2.2 分页响应（item 5 目标）

```json
{
  "code": 200,
  "data": {
    "items": [ ... ],
    "pagination": {
      "page": 1, "per_page": 20, "total": 137,
      "pages": 7, "has_next": true, "has_prev": false
    }
  },
  "message": "操作成功"
}
```

- **列表键统一为 `items`**（不再出现 `posts` / `follows` / `mutual_users` / `list`）。
- 模块额外元数据（`liked_post_ids`、`unread_count`、`source`、`search_engine`）作为 `data` 的**兄弟键**保留，不属于 `pagination`。
- Feed 走游标，不走 `pagination`（见 doc 02）。

### 2.3 失败响应（item 6 目标）

```json
{
  "code": 10001,
  "message": "帖子内容不能为空",
  "request_id": "1234567890"
}
```

- **字段名固定为 `message`，不再用 `error`**。前端无存量，直接切。
- `details` 仅在字段级校验错误时出现；429 额外带 `retry_after`。
- `code` = 业务错误码（`app/common/exceptions.py` 的 `error_code`），HTTP status 单独由响应状态行表达。

### 2.4 时间格式（item 7 目标）

所有对外时间字段：**带时区的 ISO8601 UTC，形如 `2026-09-11T07:30:00+00:00`**。
前端 `new Date(s)` 可直接解析。禁止裸 `isoformat()`（naive，无 `+00:00`）、禁止 `...Z` 与 `...+00:00` 混用。

### 2.5 空值约定（item 8）

- 单对象接口无数据：`data = {}`。
- 列表接口无数据：`data.items = []`，`pagination.total = 0`。
- 该约定写进 `docs/swagger_template.yml` + 各 Namespace 的 `@api.response` 描述，不改代码逻辑。

---

## 3. 建议实施批次（互相有依赖）

```
批次 A（契约地基，先做）
  B1 修 bug → 01（item 5/6/7/8）
    └─ 后续所有新增接口都直接按新契约写

批次 B（前端页面强依赖）
  06（item 14 确认，10min）→ 04（11/13/15/16）→ 05a（12 未读数）→ 03（上传）

批次 C（结构性 / 安全）
  02（Feed cursor）→ 07（17/18）
  08（refresh 轮换）

批次 D（可选增强）
  05b（SSE，item 20）
```

---

## 4. 验证方式

```bash
# 单元测试（service 层，改契约影响小）
venv/bin/pytest tests/unit/test_posts.py tests/unit/test_notifications.py tests/unit/test_follows.py -v

# 冒烟（跑 HTTP，契约改动主要在这里暴露；需 app 在跑）
docker rm -f weibo-app && sleep 3 && docker compose up -d app
venv/bin/pytest tests/smoke/test_smoke.py -v
```

冒烟测试里需要同步更新的断言（改契约时一并改 `tests/smoke/test_smoke.py`）：

- 第 73 行 `post = data['data']`：发帖返回单对象不变，OK。
- 第 78~81 行详情：`data['data']['post']` 不变。
- 第 92 行通知：`data['data'].get('items')`（去掉 `notifications` 兼容分支）。
- 第 99 行点赞：不变。
- 第 106~112 行 feed：`data['data']['items']`，并新增 `next_cursor` 断言。
- 第 116~117 行搜索：`data['data']['items']`（当前断言是 `posts`，要改）。

---

## 5. 每个 PR 的 Definition of Done

1. 按新契约返回，且**同一模块所有分页接口列表键都是 `items`**。
2. `grep` 全项目无 `"error"` 错误字段、无裸 `isoformat()` 对外输出。
3. 单测 + 冒烟通过；新增功能至少 1 条冒烟/单测。
4. 更新 `docs/swagger_template.yml` 或对应 Namespace 的响应模型。
5. 不引入新依赖（除非该文档明确列出并写入 `pyproject.toml`）。
