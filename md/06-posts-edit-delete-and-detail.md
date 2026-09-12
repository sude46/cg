# 06 — 删帖 / 编辑接口确认（item 14）

> 结论：**服务层与路由层均已实现，只需端到端确认。工作量 10min，无代码改动。**

---

## 1. 代码走查结论

### 路由已挂载（`app/posts/routes.py`）

| 方法 | 路径 | 位置 | 装饰器 |
|------|------|------|--------|
| PUT | `/posts/<int:post_id>` | `routes.py:131-153` | `@jwt_required` + `@validate_json(UpdatePostSchema)` + `@ownership_required('Post','post_id')` |
| DELETE | `/posts/<int:post_id>` | `routes.py:154-173` | `@jwt_required` + `@ownership_required('Post','post_id')` |

### 服务层已实现

- `PostService.update_post`（`app/posts/services.py:200-263`）：主库读 + 归属校验 + 字段校验 + 提交 + 延迟双删 + `post.updated` 事件 + StaleDataError→`ConflictError`（乐观锁，`Post.version_id`）。
- `PostService.delete_post`（`app/posts/services.py:267-310`）：主库读 + 归属校验 + 软删评论/硬删点赞（`post_repository.soft_delete_post`）+ 延迟双删 + `post.deleted` 事件。

### 鉴权

`ownership_required('Post','post_id')`（`utils/decorators.py`）校验资源存在且 `user_id == current_user`，
非本人返回 403/404。**编辑/删除都双保险**（路由装饰器 + service 内 `post.user_id != user_id`）。

---

## 2. 端到端确认步骤

```bash
# 1. 登录拿 token
TOKEN=$(curl -s -X POST http://localhost:5000/users/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"smoketest1","password":"Smoke@2026x"}' | jq -r .data.access_token)

# 2. 发帖
PID=$(curl -s -X POST http://localhost:5000/posts \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"edit me"}' | jq -r .data.id)

# 3. 编辑
curl -s -X PUT http://localhost:5000/posts/$PID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"edited"}' | jq
# 期望 200，data.content == "edited"

# 4. 详情确认已改
curl -s http://localhost:5000/posts/$PID -H "Authorization: Bearer $TOKEN" | jq '.data.post.content'

# 5. 删除
curl -s -X DELETE http://localhost:5000/posts/$PID -H "Authorization: Bearer $TOKEN" | jq
# 期望 200

# 6. 详情应 404
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5000/posts/$PID -H "Authorization: Bearer $TOKEN"
# 期望 404
```

### 反例（越权）

```bash
# 用 smoketest2 的 token 去改 smoketest1 的帖子
# 期望 403（或 404），而不是 200
```

---

## 3. 需要留意的两个已知点（非阻塞）

1. **`ownership_required` 与 `validate_json` 的执行顺序**：路由装饰器从上到下包装，`@ownership_required` 在 `@validate_json` 之下。
   若请求 body 非法，可能先触发 400；若资源不存在，触发 404。行为可接受，但确认一下错误优先级符合前端预期。

2. **`post_repository.soft_delete_post`**（`app/posts/repositories.py:100-113`）里 `post.comments.all()` / `post.likes.all()`：
   如果评论/点赞量巨大，删除会一次全查出来（`lazy='dynamic'` 的 `.all()`）。大量数据时建议改成批量 `UPDATE`：
   ```python
   Comment.query.filter_by(post_id=post.id, deleted_at=None).update({'deleted_at': now})
   Like.query.filter_by(post_id=post.id).delete()
   ```
   属性能优化，不是功能缺失。

---

## 4. 结论

- [x] `PUT /posts/<id>` 可用
- [x] `DELETE /posts/<id>` 可用
- [ ] 跑一遍上述 curl 确认（10min）

无需新增代码。若确认过程中发现 403 被吞成 500，检查**实际生效**的 `app/common/error_handlers.py` 的异常映射（`middlewares/error_middleware.py` 是死代码，改了没用）。
