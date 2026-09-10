<!-- Copilot / AI agent 指南 for this repository -->
# 快速上手（为 AI 编码助手准备）

以下内容基于对仓库源码的静态分析（重点文件：`core/extensions.py`、`config/base.py`、`app/auth/routes.py`、`app/posts/models.py`、`utils/decorators.py`、`services/post_service.py`）。目标是帮助 AI 代理能快速、安全且一致地对该代码库做改动。

## 一、工程概貌（Big Picture）
- 框架：Flask + Flask-RESTX（见 `app/*/routes.py` 命名空间和 Swagger 模型）。
- 目录约定：每个业务域放在 `app/<domain>/`（如 `auth/`、`posts/`、`comments/` 等），域内应自包含 `routes/services/models/schemas`。
- 额外的“服务层”放在顶级 `services/`（如 `services/post_service.py`），用于跨域或高阶业务逻辑。
- 全局扩展实例集中在 `core/extensions.py`（`bcrypt, jwt, cors, mail`），应用应在工厂初始化里调用它们的 `init_app`/注册。

## 二、关键约定与可见模式（要遵守）
- 配置与密钥：配置在 `config/*.py`（`BaseConfig`），敏感值通过环境变量注入。注意：存在开发默认值（`SECRET_KEY`,`JWT_SECRET_KEY`），生产代码不要依赖这些默认值。
- 验证与装饰器：请求校验、限流、事务装饰器位于 `utils/decorators.py`（`validate_json`, `rate_limit`, `transactional`, `ownership_required`, `handle_errors`）。AI 修改或新增装饰器时，请参考这些实现并保持签名兼容。
- 异常与常量：全局异常/常量集中在 `app/common`，服务/路由应抛出定义好的业务异常（如 ValidationError/ResourceNotFoundError/AuthorizationError），由统一错误处理层转换为 HTTP 响应。
- 模型序列化：当前模型使用 `to_dict()`（例如 `app/posts/models.py`），建议逐步迁移到统一 Schema（Marshmallow 或 Pydantic）。在改造时：先新增 schema 并在服务层返回 schema.dump(obj)，再逐步替换各路由调用。
- 软删除：模型有 `is_deleted` 字段以及 `soft_delete()` / `query_active()` 风格使用，删除操作应为软删除并在查询侧过滤。

## 三、常见修改/PR 要点（具体示例）
- 使用扩展：引用统一实例 `from core.extensions import jwt, bcrypt`（不要直接创建新实例）。
- JWT/安全：配置中 `JWT_SECRET_KEY` 需从环境/密钥管理系统加载，生产环境禁用任何硬编码默认。`refresh` 路由使用 `@jwt_required(refresh=True)`（见 `app/auth/routes.py`）。
- 验证示例：把 `to_dict()` 替换为 Marshmallow schema 示例（放 `app/posts/schemas.py`），在路由用 `schema.dump(post)` 返回。
- 避免 N+1：在返回帖子详情时使用 `joinedload(Post.author)`；列表查询使用 `selectinload` 批量预加载关联（参见 `Post.comments`、`Post.likes` 的关系定义）。

## 四、工程中的“陷阱/需注意”的实证点
- 配置文件有拼写不一致（如 `JWT_REFERESH_TOKEN_EXPIRES` / `JWT_REFERESH_TOKEN_EXPIRES` 等）和命名差异，修改时请全局搜索并保持兼容性。
- `utils/decorators.py` 内部包含若干实现错误（拼写、变量名），AI 在修改或重构这些工具时请先运行或请求运行单元测试/手工验证行为。
- `wsgi.py` 与 `app/__init__.py` 为空 — 仓库当前没有可发现的明确启动脚本。不要假设启动命令；在生成运行/CI 文档前请向开发者确认期望的启动流程（建议采用应用工厂模式）。

## 五、推荐优先改进方向（短期、可落地）
- 引入统一 Schema：在各域下添加 `schemas.py`（使用 Marshmallow），逐步替换 `to_dict()`。
- 全局异常处理：在应用工厂或中间件中注册统一错误处理器，把业务异常映射到统一响应格式（见响应约定）。
- 密钥与安全硬化：从环境读取 `JWT_SECRET_KEY`/`SECRET_KEY`，并在 CI/CD 环境注入；移除或禁止使用代码中的开发默认值。
- 将内存限流改为 Redis 实现（`REDIS_URL` 在 `config/base.py` 已声明）。

## 六、响应与 API 约定（现有代码风格 + 强烈建议）
- 现有路由多返回 `(dict, status_code)`，短期兼容该风格；长期建议统一为：成功 `{'code':0,'data':...,'message':''}`；失败 `{'code':<业务码>,'error':'...','request_id':''}`，并由错误处理中间件生成。
- REST 资源命名：使用复数名词（`/posts`, `/comments`），资源层级如 `/posts/{post_id}/comments`。

## 七、开发与调试提示（如何运行/验证改动）
- 虚拟环境（Windows PowerShell）示例：
```powershell
& D:\cg\.venv\Scripts\Activate.ps1
$env:FLASK_APP = 'wsgi.py'
flask run
```
- 注意：仓库没有发现 `requirements.txt` / `pyproject.toml` / `Makefile` 或 CI 配置；如果需要运行，请先向仓库维护者确认运行依赖与推荐流程。

----
请审阅以上内容；我可以根据反馈把这些点合并到项目的 CONTRIBUTING 或 README，或把检查项转换为自动化 linters / tests（例如：校验配置键名、检查 `to_dict()` 覆盖面、检测拼写错误）。要我现在把此文件提交到仓库并修正明显拼写不一致吗？
