# 重构与改造计划（概要）

目的：把当前仓库逐步改造成按业务域自包含的可维护后端工程，统一校验/序列化、改进错误处理、引入工厂与装饰器模式，逐步提升可测试性与性能。

总目标（短句）：
- 按域组织代码：每个域包含 `routes/`, `services/`, `repositories/`, `schemas/`, `models/`。
- 统一入参校验与序列化（Marshmallow/Pydantic），替换 `to_dict()` 为 Schema 输出。
- 注册全局异常处理并输出统一响应格式。
- 建立应用工厂 `create_app()`，集中初始化 `core/extensions.py` 中的扩展。
- 引入装饰器（鉴权、校验、所有权校验、审计）、并在小范围内使用 Redis 做限流/缓存。

阶段划分（每阶段可单独 PR，易于回滚）：

阶段 A — 准备与低风险改动（当前任务）
- 产出：本计划文档 + TODO 列表（已创建）
- 验证：人工 review
- 预计时间：0.5 小时

阶段 B — 初始化与基础设施（优先级高，影响较广）
- 新增/修改：
  - `app/__init__.py`：实现 `create_app(config_name=None)` 的应用工厂。
  - `wsgi.py`：调用 `create_app()`（或保留供 CLI 使用）。
  - 保持 `core/extensions.py`（扩展实例），在工厂内调用 `init_app(app)`。
  - 在工厂内注册统一错误处理器（把 `app/common/exceptions.py` 的异常映射为统一 JSON 响应）。
- 验证：能够通过 `flask run` 启动（development 配置），并触发已知异常后得到统一响应。
- 预计时间：1–3 小时

阶段 C — Schema 迁移示例（中等风险，作为模版）
- 目标：先对 `posts` 域做端到端迁移，示范模式并覆盖测试。
- 新增/修改：
  - `app/posts/schemas.py`：`PostSchema`, `PostCreateSchema`。
  - `services/post_service.py`：替换 `post.to_dict()` 为 `PostSchema().dump(post)`。
  - 保留 `to_dict()` 为 Deprecated（兼容）。
- 验证：API `/posts` 的 create/get 流中返回 schema 格式，单元测试覆盖。
- 预计时间：2–4 小时

阶段 D — 装饰器与权限、限流实现
- 目标：完善 `utils/decorators.py`（或移动到 `app/common/decorators.py`），实现：
  - `@validate_json(schema)`（使用 Marshmallow load/validate 并把解析后的 data 附加到 `flask.g`）
  - `@rate_limit`（先保留内存实现，生产建议 Redis）
  - `@ownership_required(model, id_param='post_id')`
  - `@requires_permissions(...)`（简单 RBAC 示例）
- 验证：对受保护接口进行授权/限流测试

阶段 E — 逐域迁移与性能优化（迭代）
- 依次把 `users`, `comments`, `likes`, `follows`, `notifications` 按照 `posts` 模式迁移。
- 在查询层加入 `selectinload` / `joinedload` 优化 N+1；对关键路径添加缓存与 keyset 分页。
- 追加测试、压力测试脚本（k6/locust）并测量 p95。

回滚与风险控制
- 每次阶段性改动使用独立分支与 PR。
- 在 PR 描述里列出变更文件、运行验证步骤与回滚命令（通常是 `git revert`）。
- 重大改动前（如切换工厂、序列化体系）先在 `posts` 做 POC 并通过单元测试。

可交付物与验证清单（最小可交付）
- `app/__init__.py`（create_app）+ `wsgi.py`（可运行）
- `app/common` 中的统一异常/装饰器/分页工具
- `app/posts/schemas.py` + 修改后的 `services/post_service.py`（schema 输出）
- 单元测试：`tests/test_posts.py` 覆盖创建/查询/更新/删除（软删除）

示例命令与运行校验
```powershell
& D:\cg\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt   # 若无，请先创建 minimal requirements
$env:FLASK_APP='wsgi.py'
flask run
# 触发已知异常，检查 JSON 错误格式
```

代码风格与注意事项（项目特有）
- 统一使用 UTC 存储时间（模型中用 timezone-aware datetime）。
- 统一通过 `core/extensions.py` 提供扩展实例（`bcrypt`, `jwt`, `cors`, `mail`），不要再次创建新实例。
- 保持旧 API 兼容：在替换变量名或异常类时优先使用别名策略，逐步消毒旧引用。

下一步建议（我可以代做）
- 我可以现在开始实施阶段 B（建立工厂 + 注册扩展 + 全局错误处理），或直接实施阶段 C（把 `posts` 域迁移为示例）。

请回复要我立刻开始的阶段（例如：`开始 B` 或 `开始 C`）。
