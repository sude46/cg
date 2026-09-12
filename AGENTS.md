# Weibo 平台项目 — 开发备忘录 (AGENTS.md)

> 本文件每次会话自动加载。改代码前先读；遇到问题先查"已踩过的坑"。

## 项目概况

微博社交平台（Flask + MySQL + Redis 主从哨兵 + Elasticsearch + Celery）。
后端分层：`routes`(flask-restx) → `services` → `repositories` → models，加 `cache` 层。

## 常用命令

```bash
# 启动/重建 app 容器（重要：reload 不可靠，改动后用这个强制重建）
docker rm -f weibo-app && sleep 3 && docker compose up -d app

# 重启 ES-CN（IK 版，用 rm -f，docker restart 会报 cgroup 错误）
docker rm -f weibo-es-cn && sleep 3 && docker compose up -d elasticsearch-cn

# 冒烟测试（先确保 app 在跑）
venv/bin/pytest tests/smoke/test_smoke.py -v

# 单元测试（部分会因宿主连不到 Docker 内 Redis 而失败，属环境问题）
venv/bin/pytest tests/unit/test_notifications.py -v

# 单测（不依赖外部服务，CI 同款命令）
ELASTICSEARCH_ENABLED=false REDIS_SENTINEL_HOST= REDIS_HOST=127.0.0.1 \
  REDIS_URL=redis://127.0.0.1:6379/0 CELERY_BROKER_URL=memory:// \
  CELERY_RESULT_BACKEND=cache venv/bin/pytest tests/unit -q

# 构建镜像（elasticsearch<9 约束在 pyproject.toml）
docker compose build app
```

## 依赖管理（重要）

- **依赖以 `pyproject.toml` 为准**，`requirements.txt` 由它生成并对齐当前可用 venv 版本。
- 改依赖只改 `pyproject.toml`，然后同步 `requirements.txt`，再跑校验（CI 用同一命令）：
  ```bash
  venv/bin/python scripts/check_requirements_sync.py
  ```
- 宿主 venv 与容器依赖不一致时，先对齐再排错（例如宿主曾装成 `elasticsearch 9.3.0`，连不上 8.11 服务端）。
- `.env` 需配置 `MFA_ENCRYPTION_KEY`（Fernet；用 `utils.security_utils.generate_mfa_encryption_key()` 生成），否则 MFA 加解密不可用。

## 容器与服务

- app：`weibo-app`，MySQL 主库 `weibo-mysql-master:3306/weibo` + 从库 replica-1
- celery worker：`weibo-celery-worker`（`-Q default,like`；like 队列来自 `task_routes`）
- Redis：master/replica/sentinel-1/2/3（写操作必须 `get_conn(for_write=True)`）
- ES：`weibo-es-cn`(**IK 中文分词版,9201**) ← app 连的是这个（标准版 `weibo-es` 已移除）
- IK 插件已装进 `elasticsearch/plugins/ik/`（匹配 ES 8.11.0）
- 测试用户：smoketest1 / `Smoke@2026x`（id 1），smoketest2 / `Smoke@2026y`（id 2）

## 从库复制运维（重要）

- 从库初始化脚本 `docker/mysql/init_replica.sh`：**先全量 seed（带一致 GTID 位点）再启动复制**。
  不要只手动 `CHANGE MASTER`——主库 binlog 会被 `binlog_expire_logs_seconds` 清理，空 GTID 补不回存量。
- 坑：**数据卷存在时 mysql entrypoint 会跳过初始化脚本**。遇到"复制没配"先查 `/data/mysql-replica-1` 是否存在，别先查网络。
- 巡检：`venv/bin/python scripts/check_replica.py`（默认 `127.0.0.1:3307`，账号 monitor/monitor123，
  依赖 MariaDB 的 `SLAVE MONITOR` 权限），检查 IO/SQL Running + 延迟，异常退出码非 0，可挂 cron。
- 读路由：Repository 读经 `core/db_router.py`，从库探测失败会回落主库并打点（`weibo_db_replica_failover_total`）。

## 路由约定（重要）

所有模块蓝图加 `Namespace('xxx', path='/')`，**不要**去掉蓝图的 `url_prefix`。
这样 URL 才是单前缀（`/posts`、`/feeds/timeline`），去掉 url_prefix 会导致所有模块文档冲突在根 `/docs`。

每个模块 `__init__.py` 必须 `from . import routes`（漏掉则路由全不注册）。

## 已踩过的坑（本次会话修复）

### 路由/蓝图
- feeds 无路由：`feeds/__init__.py` 漏 `from . import routes`；`routes.py` 把 `@api.expect` 写成 `@api.excpect`（AttributeError 崩整个模块导入）
- 双前缀 `/posts/posts`：Namespace 自动加前缀，用 `path='/'` 解决

### 序列化
- `POST /posts/<id>` 500（`isoformat ... doesn't apply to 'str'`）：`get_post` 已返回序列化 dict，路由又 `post_schema.dump()` 二次序列化 → 直接用 `result['post']`
- feeds timeline 500（`Post is not JSON serializable`）：服务层返回裸 ORM 对象，要 `posts_schema.dump()`；repository 查 Post 要 `joinedload(Post.author)`

### 认证/中间件
- JWT sub 是 int：`config/base.py` 加 `JWT_VERIFY_SUB = False`
- `middlewares/auth_middleware.py`：public_exact 路径要带前导 `/`；OPTIONS 别拼错
- `validate_json` 装饰器：schema 有的传 class 有的传 instance，用 `schema_class() if isinstance(schema_class,type) else schema_class`

### 事件/异步
- 消费者线程报 `Working outside of application context`：EventBus 存 `_app`，分发时 `with self._app.app_context()`
- Redis `READONLY You can't write against a read only replica`：BRPOP 是写命令，用 `get_conn(for_write=True)`
- `_calculate_hot_score` naive/aware datetime 相减报错：`fromisoformat` 后的 naive 要 `replace(tzinfo=timezone.utc)`

### Elasticsearch
- 配置键名不一致：`config/base.py` 是 `ELASTICSEARCH_HOST`（单数），`core/es_client.py` 读取要兼容两者（`.get('ELASTICSEARCH_HOST') or .get('ELASTICSEARCH_HOSTS')`）
- 客户端版本：**必须 `<9`**（pyproject 已锁 `>=8.11.0,<9`），9.x 客户端连不上 8.11 服务端
- app 连 `elasticsearch-cn:9200`（IK 版），`.env` 的 `ELASTICSEARCH_HOSTS` 已配好
- 搜索永远 0 结果：索引文档缺 `is_deleted` 字段，而查询强制 `term is_deleted: False`（ES 对缺失字段匹配不到）→ `index_post` 里兜底 `post_data['is_deleted']=False`
- 挂载插件目录只放解压后的 `ik/` 目录，**别放 zip**（ES 会把 zip 当插件目录扫描而启动崩溃）

### 环境
- `docker restart/stop` 报 systemd cgroup "already loaded" 错误 → 一律用 `docker rm -f` + `docker compose up -d`
- 从宿主 venv 跑单测连不到 Docker 内 Redis sentinel（`No master found`）是环境问题，不是代码 bug

### 监控（本次会话修复）
- `init_metrics_middleware` 只导出不注册 → `core/factory.py` 里要显式调用，且排在所有中间件最前（计时才准）
- 同名「模块 vs 包」：`app/users/services.py`（文件）被 `services/`（目录包）**遮蔽**，Python 包优先于模块，`from app.users.services import AuthService` 永远解析到 `services/auth_service.py`。已删除死文件 `app/users/services.py`
- Docker Compose external 网络：`external: true` 时必须用 `name:` 指定实际网络名（`weibo-platform_weibo-network`），只写 compose key 会找不存在的 `weibo-network`
- Linux 上 `host.docker.internal` 默认不解析，prometheus/alertmanager 容器要加 `extra_hosts: ["host.docker.internal:host-gateway"]`
- MySQL 实为 **MariaDB 10.6**：mysqld-exporter 靠 MySQL 协议能连，但要禁 `info_schema.innodb_metrics` 等 MySQL 专属 collector，否则大量 warning
- Celery broker 是**独立的** `weibo-redis-celery:6379`（非业务 redis-master），celery-exporter 要连这个
- flower 是面板不是 exporter，不导出 Prometheus 格式；监控 Celery 用 celery-exporter 直连 broker
- 埋点分层：DB 延迟→repository 层 `@monitor_db` 装饰器（离 SQL 最近）；业务成功/失败→service 层 Counter（能区分 success/error/duplicate）
- 读操作只埋 success（失败由 HTTP 4xx/5xx 指标 + 错误率告警兜底），写操作才分 success/error

## 搜索链路

发帖 → `event_bus.publish('post.created', ...)` → `services/search/event_handlers.py:on_post_created` → `PostSearchService.index_post` → ES 索引 `weibo_posts`。
IK 分词：`ik_max_word`（分析）+ `ik_smart`（搜索），映射在 `services/search/document.py`。

## 目录结构全览

```
weibo-platform/
├── app/                     # 业务模块（Flask 蓝图，每个模块 routes/services/repositories/models/schemas/cache）
│   ├── __init__.py          # create_app 延迟导入（避免循环依赖）
│   ├── users/               # 用户：注册/登录/MFA/账户锁定/密码/Tokem（services 拆成子模块）
│   │   └── services/        #   auth_service/password_service/mfa_service/account_service/token_service
│   ├── posts/               # 帖子 CRUD + 搜索 + 热搜
│   ├── comments/            # 评论 + 热评榜（ZSet）
│   ├── likes/               # 点赞（Redis Lua 原子 + Celery 异步刷 DB）
│   ├── follows/             # 关注/粉丝/互相关注
│   ├── feeds/               # Feed 流（推拉结合，粉丝>=1000 用拉模式）
│   ├── notifications/       # 通知（事件驱动，订阅 comment.created）
│   ├── permissions/         # 权限服务（services.py）
│   └── common/              # 异常/常量/数据库工具/事件总线
├── core/                    # 基础设施
│   ├── factory.py           # create_app 核心工厂（初始化顺序关键）
│   ├── blueprint_registry.py# 集中注册 7 个蓝图
│   ├── database.py          # db/migrate/BaseModel(软删除)/DatabaseManager(CLI命令)
│   ├── db_router.py         # 主从路由（读写分离，round_robin 选从库）
│   ├── redis_cache.py       # RedisCache 单例（防穿透/雪崩/击穿 + 各种数据类型封装）
│   ├── es_client.py         # ES 单例（connect 兼容 ELASTICSEARCH_HOST 单复数）
│   ├── metrics.py           # Prometheus 指标（HTTP/DB/Redis/Celery/各业务模块 Counter）
│   ├── celery_app.py        # Celery 实例 + beat_schedule
│   ├── extensions.py        # bcrypt/jwt/mail + init_redis（注意 factory 没用这套 init）
│   ├── security.py          # SecurityManager（密码强度/哈希/JWT 手写）
│   └── logging_config.py    # 结构化日志（TimedRotatingFileHandler）
├── config/                  # Flask 配置（base/development/production/testing）
├── services/search/         # ES 搜索（config/document/repositories/services/event_handlers）
├── middlewares/             # 认证/限流/CORS/安全头/日志/metrics/错误
├── tasks/                   # Celery 任务（base_task 埋点 + 各业务任务 + 对账 reconcile）
├── utils/                   # 装饰器/响应/Redis/雪花ID/分页/安全/校验
├── monitoring/              # 监控栈（见「监控体系」章节：prometheus/alertmanager/grafana/loki/promtail + 各 exporter）
├── migrations/              # Flask-Migrate（alembic）
├── tests/                   # smoke/unit/integration/performance
├── docs/                    # ES 设置/数据库优化设计
├── scripts/setup_es.sh      # ES 初始化脚本
├── manage_es.py             # ES 索引管理 CLI
├── wsgi.py                  # 入口（含 /metrics 端点）
├── Dockerfile               # python:3.11-slim + gunicorn
├── docker-compose.yml       # 业务栈（MySQL主从/Redis哨兵/ES/ES-CN/app）
└── .env                     # 环境变量（数据库/Redis/ES/Celery/密钥）
```

## 关键机制

### 分层与约定
- `routes`(flask-restx) → `services` → `repositories` → models，cache 层在 service 与 redis 之间
- 每个模块 `__init__.py` 定义 `xxx_bp = Blueprint(..., url_prefix='/xxx')`，必须 `from . import routes`
- 路由用 `Namespace('xxx', path='/')`（path 必须 `/` 否则双前缀）
- repository 查询 Post 要 `joinedload(Post.author)`，否则序列化报错

### 缓存一致性（Cache-Aside + 强一致标记 + 延迟双删）
- `mark_recently_modified(id, ttl=5)`：写后 5 秒内读强制走主库
- 延迟双删：立即删缓存 + Celery `delayed_invalidate` countdown=2 二次删（失败降级线程）
- 空值缓存 `__NULL__`（防穿透）+ 随机 TTL 偏移（防雪崩）+ `cache_through` 分布式锁（防击穿）

### 事件总线（app/common/events.py）
- Redis List 持久化事件总线：`publish` LPUSH，后台线程 BRPOP 分发
- 消费者用 `for_write=True`（BRPOP 是写命令）
- 分发时 `with self._app.app_context()`
- 失败重试最多 3 次；`event_bus.start(app)` 在 factory 末尾调用
- 已订阅事件：`post.created/updated/deleted/like_count_changed`（搜索）、`comment.created`（通知）

### 点赞（Redis 优先 + 异步落库）
- Redis Lua 原子脚本（`add_like` 用 evalsha），写 Set + Counter + 脏标记
- Celery `async_like_to_do` 异步刷 DB，pending_id 幂等
- 对账任务 `like_reconcile` 兜底（beat 每 300s）

### Feed 推拉结合
- 粉丝 <1000：推模式（`push_to_followers` 分批 Pipeline）
- 粉丝 >=1000：拉模式（读时 `_pull_from_database` 聚合）
- `BIG_V_THRESHOLD=1000`，key `feed:user:{uid}` ZSet

## 已知代码 bug（本次会话已全部修复，留档备查）

- [已修复] `core/config.py` 与 `config/__init__.py` 两套 `get_config` 冲突 → 删除死代码 `core/config.py`（全项目无引用）
- [已修复] `app/auth/` 假登录 stub（users 模块已完整覆盖认证）→ 删除整个死模块目录
- [已修复] `tasks/data_tasks.py:62` `reverser=True` → `reverse=True`
- [已修复] `tests/unit/test_security.py` 调用不存在的 `AuthService.get_user_entity` → 改用 `user_repository.get_by_id`；顺带修复 3 个过时测试（密码数据含连续字符被拒、`verify_jwt_token` 过期返回 None 而非抛异常）
- [已修复] `core/metrics.py` `CELERY_QUEUE_DEPTH` 恒 0 已废弃 → 删除

## 监控体系

### 组件（`monitoring/docker-compose.monitoring.yml`，共 10 个）
- prometheus（9090）、alertmanager（9093）、grafana（3000，admin/admin123）、loki（3100）、promtail
- exporter：node-exporter（host 网络 9100）、redis-exporter（9121）、mysqld-exporter（9104）、celery-exporter（9540）
- 钉钉告警 webhook `alert_webhook.py`（宿主机跑，5001，不在此 compose 内）

### 抓取目标（prometheus.yml）
weibo-api(app:5000)、node、redis-business、mysql-master、celery、alert-webhook

### 告警规则（prometheus/rules/weibo_rules.yml）
API P99 延迟>500ms、API 5xx>1%、Celery 队列堆积、Redis 内存>80%、DB 慢查询>500ms、MySQL down、对账差异

### 埋点覆盖（core/metrics.py 定义 → 各模块埋）
- 全模块已埋：posts/likes/feeds/comments/follows/notifications/users
- DB 延迟：各模块 repositories 用 `@monitor_db("select|insert|update|count", "<表>")`
- 业务计数：各模块 services 用 `<MODULE>_OPERATIONS.labels(action, result).inc()`，写操作分 success/error/duplicate，读操作只埋 success
- 用户认证埋点注意：routes 用的是 `services/auth_service.py`（子目录新版），不是旧 `services.py`

### 启动
```bash
docker compose -f monitoring/docker-compose.monitoring.yml up -d
# 钉钉 webhook（宿主机）：
venv/bin/python monitoring/alert_webhook.py   # 端口 5001
```

### 待办（未完成）
- mysqld-exporter 用 root 连库，可换专用监控账号（需 PROCESS/REPLICATION CLIENT 权限）

## 发展规划 / 演进方向

> 定位：可申请软著的分布式社交平台系统。当前缺前端 + CI/CD + 代码规范，补齐即可产品化。

### 短期（补成完整产品，软著落地）
- 前端：AI 生成（Vue3 + Vite + TypeScript + Element Plus），以 Swagger/OpenAPI 为输入
- CI/CD：GitHub Actions（ruff → pytest → docker build）
- 代码规范：pre-commit + editorconfig + ruff；统一缩进为 4 空格（现有 13 个 tab 缩进文件待清理）

### 中期（加业务模块，架构上每个都是 `app/<domain>/` 下加目录）
- 私信（IM）、话题/标签、收藏、举报与内容审核、搜索推荐

### 长期（架构演进）
- 微服务化拆分（事件总线已是解耦雏形，天然利于拆分）
- K8s + API 网关 + 服务网格
- 推荐系统（已有 ES + 热搜 + 行为数据基础）
