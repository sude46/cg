# Weibo DemoDemo

基于 Flask + Vue 3 的微博类社交平台，覆盖发帖、关注、点赞、评论、通知、私信、全文搜索与异步任务，并附带完整的可观测性方案。

后端采用严格分层架构（Routes → Service → Repository → Model），在**读写分离、缓存一致性、搜索降级、事件驱动、实时推送**等方向做了工程化实践，而不是一个只跑通增删改查的 demo。

- 语言 / 框架：Python 3.11+ · Flask 3 · Vue 3
- 存储：MySQL 主从 · Redis 哨兵 · Elasticsearch 8（IK 中文分词）
- 异步：Celery（worker / beat）
- 部署：Docker Compose · Gunicorn · nginx

## 项目亮点

- **主从读写分离**：读请求优选健康从库，从库连续失败自动标记不健康并回落主库，带冷却试探与 Prometheus 埋点（`core/db_router.py`）。
- **缓存一致性**：Cache-Aside + 延迟双删；通知未读数另有短窗口强一致标记，避免主从延迟回跳旧值。
- **搜索降级熔断**：Elasticsearch 故障时进入熔断窗口，自动降级为带护栏的数据库查询，窗口内不再探测 ES（`services/search`）。
- **事件驱动 + 对账兜底**：基于 Redis List 的持久化事件总线，失败重试；beat 定时对账 Redis 与 DB / 搜索索引的一致性。
- **实时推送**：通知流与私信流基于 SSE（`text/event-stream`）。
- **全链路可观测**：Prometheus 指标、Grafana 面板、Loki 日志、Jaeger 追踪（OpenTelemetry 贯通 HTTP → SQL → 事件总线 → Celery → ES）、Sentry。

## 功能

### 用户与安全
- 注册 / 登录 / 登出 / 刷新令牌（JWT access + refresh）
- 登出黑名单（JWT blocklist）
- TOTP 双因子认证（MFA secret 使用 Fernet 加密存储）
- 密码历史、密码强度校验、登录失败锁定
- 全站请求限流（Flask-Limiter，可配置存储与默认限额）

### 社交
- 帖子 CRUD、图片上传
- 评论（含热评）
- 点赞（帖子 / 评论）
- 关注 / 粉丝 / 互相关注

### 信息流与发现
- 关注时间线（Timeline）
- 全站广场
- 热榜与热搜
- 全文 / 子串搜索（Elasticsearch + IK 中文分词，支持相关度 / 时间 / 热度排序与搜索建议）

### 通知与私信
- 通知列表、未读数、已读 / 全部已读 / 删除
- 私信会话与消息
- 通知流与私信流 SSE 实时推送

### 异步与一致性
- Feed 推送、ES 索引同步、缓存失效（延迟双删）
- like / post / comment / user / search 多维度定时对账

## 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | Flask 3、Flask-RESTX、Flask-JWT-Extended、Flask-Limiter、Flask-CORS |
| 数据访问 | SQLAlchemy 2、Flask-SQLAlchemy、Alembic（Flask-Migrate）、PyMySQL |
| 存储 | MySQL / MariaDB（主从复制）、Redis 7（哨兵 + Pub/Sub）、Elasticsearch 8 + IK |
| 异步 | Celery 5（Redis broker / backend） |
| 前端 | Vue 3、Vite、TypeScript、Element Plus、TanStack Query、Axios |
| 可观测 | Prometheus、Grafana、Alertmanager、Loki、Promtail、Jaeger（OpenTelemetry）、Sentry |
| 部署 | Docker、Docker Compose、Gunicorn、nginx |

## 架构

```
                          ┌──────────────────────────────┐
   浏览器 ──────────────▶  │  web (nginx)  :8080          │
                          │   · 静态资源 / SPA 回退        │
                          │   · /api/     → Flask         │
                          │   · /uploads/ → Flask         │
                          └──────────────┬───────────────┘
                                         │
                          ┌──────────────▼───────────────┐
                          │  Flask (app)  :5000           │
                          │  Gunicorn (gthread)           │
                          │  Routes → Service → Repository│
                          └───┬───────┬────────┬──────────┘
                              │       │        │
             ┌────────────────┘       │        └───────────────┐
             ▼                        ▼                        ▼
     Redis 主从/哨兵            Celery worker/beat        MySQL 主从 / ES
     · 缓存 / Pub-Sub           · 异步任务 / 对账          · 读写分离 / 全文检索
     · 事件总线 / 限流
```

请求分层：

```
Routes (Blueprint / Flask-RESTX)   —— 参数解析、鉴权、限流
  → Service                        —— 业务逻辑、事务编排
    → Repository                   —— 数据访问（统一走主从路由）
      → Model (ORM)                —— 表结构
```

## 核心设计

### 1. 分层与依赖注入
应用通过工厂函数 `create_app` 创建，各层通过 `app` 实例传递依赖，无全局可变状态。`route_limit` 等代理对象采用延迟绑定（Proxy），避免导入期循环依赖。

### 2. 主从读写分离（`core/db_router.py`）
- 读路径经 `MasterSlaveRouter` 优选健康从库，并每次探测连通性，绝不把请求打到已挂从库。
- 从库连续失败达到阈值即标记不健康，冷却一段时间后再试探恢复。
- 无健康从库时，读操作回落主库，并对 `weibo_db_replica_healthy` / `weibo_db_replica_failover_total` 打点。

### 3. 缓存一致性
- 采用 **Cache-Aside**：读时回填，写后删除缓存。
- 写后为避免主从延迟导致的脏读，再触发一次**延迟删除**（Celery `delayed_invalidate*`）。
- 通知未读数维护**短窗口强一致标记**：窗口内的读强制走主库，避免回跳旧值。
- 整体为**最终一致**，不承诺强一致读。

### 4. 搜索降级与熔断（`services/search`）
- 正常走 Elasticsearch（IK 分词，支持全文与 ngram 子串）。
- ES 故障时写入熔断标记（携带 TTL），窗口内不再探测 ES。
- 降级模式可配置：`fallback`（带护栏的 DB LIKE）或 `unavailable`（直接返回不可用）。
- 索引同步失败的帖子进入 dirty 集合，由 `reconcile_search_index` 定时回灌。

### 5. 事件总线与对账
- `RedisEventBus`：生产者 LPUSH 事件，后台线程 BRPOP 消费并分发，进程重启不丢事件；处理失败最多重试 3 次。
- 事件注入 OpenTelemetry trace context，消费端续接同一条链路。
- beat 定时执行多维度对账：like / post / comment / user / search，差异数写入 `weibo_reconcile_diff_count`。

### 6. 实时推送（SSE）
通知流与私信流使用 Server-Sent Events（`text/event-stream`）。前端在断线后按退避策略重连。SSE 长连接会占用 Gunicorn 工作线程，容量需据此规划。

### 7. 限流
基于 Flask-Limiter，存储后端与默认限额均可通过环境变量配置，接口级限额通过 `route_limit` 声明。

### 8. 可观测性
- 指标：`/metrics` 暴露 HTTP / DB / Redis / Celery / 业务指标。
- 日志：结构化日志（含 `request_id` / `trace_id`）同时输出到 stdout 与文件。
- 追踪：OpenTelemetry 自动埋点 Flask / SQLAlchemy / Celery，经 OTLP 上报 Jaeger。
- 异常：Sentry 聚合前后端异常。

## 目录结构

```
app/                    业务模块
  users/                用户 / 认证 / MFA
  posts/                帖子 / 热榜 / 搜索入口
  comments/             评论
  likes/                点赞
  follows/              关注关系
  feeds/                时间线与 Feed 推送
  notifications/        通知 + SSE
  chats/                私信会话 / 消息 + SSE
  uploads/              图片上传与回显
  common/               健康检查、事件总线、异常、响应封装
core/                   应用工厂、数据库、扩展、蓝图注册、Celery、追踪、指标
config/                 分环境配置（development / production / testing）
services/               跨模块服务（搜索等）
middlewares/            鉴权、CORS、限流、日志、指标、安全头
tasks/                  Celery 任务与对账
migrations/             数据库迁移（Alembic）
monitoring/             Prometheus / Grafana / Loki / Jaeger / Alertmanager
scripts/                启动入口、ES 初始化、依赖校验、排障脚本
web/                    前端（Vue 3 + Vite）
docs/                   设计与运维文档（SLO、压测报告、ES 搭建、数据库优化）
tests/                  单元 / 集成 / 冒烟 / 性能测试
```

## 数据模型

| 表 | 说明 |
|---|---|
| `users` | 用户账号（含 MFA、锁定状态） |
| `password_histories` | 历史密码（禁止复用） |
| `posts` | 帖子 |
| `comments` | 评论 |
| `likes` | 点赞（帖子 / 评论） |
| `follows` | 关注关系 |
| `notifications` | 通知 |
| `conversations` | 私信会话 |
| `conversation_users` | 会话成员（含未读数） |
| `messages` | 私信消息 |

所有业务表支持软删除（`is_deleted`）。

## API 概览

后端各模块以 Flask-RESTX 提供接口，经前端 nginx 访问时统一前缀 `/api`。

| 模块 | 主要接口 |
|---|---|
| 认证 | `POST /users/register`、`POST /users/login`、`POST /users/refresh`、`POST /users/logout`、`GET /users/me` |
| 帖子 | `GET /posts`、`POST /posts`、`GET/PUT/DELETE /posts/{id}`、`GET /posts/search`、`GET /posts/hot-searches` |
| 评论 | `POST /comments`、`GET /comments/posts/{post_id}/comments`、`GET/PUT/DELETE /comments/{id}` |
| 点赞 | `POST/DELETE /likes`、`GET /likes/my-likes`、`POST /likes/posts/{post_id}/likes` |
| 关注 | `POST /follows/following`、`GET /follows/followers`、`GET /follows/following/list`、`GET /follows/following/mutual` |
| 信息流 | `GET /feeds/timeline`、`POST /feeds/publish`、`POST /feeds/refresh` |
| 通知 | `GET /notifications`、`PATCH /notifications/{id}/read`、`PATCH /notifications/read-all`、`GET /notifications/stream` |
| 私信 | `GET /chats/...`、`GET /chats/stream`、`GET /chats/unread-count` |
| 上传 | `POST /uploads`、`GET /uploads/files/{key}` |
| 健康 / 指标 | `GET /health`、`GET /metrics` |

完整的请求 / 响应结构见各模块 Swagger 文档（见下）。

## 快速开始（Docker Compose）

### 前置条件
- Docker 与 Docker Compose v2
- 内存建议 ≥ 4GB（Elasticsearch 较吃内存）；磁盘 ≥ 20GB
- Linux 建议设置 `vm.max_map_count=262144`（ES 要求）

### 步骤

```bash
git clone https://github.com/sude46/cg.git
cd cg
cp .env.example .env
# 编辑 .env：填写密钥与连接信息（见“环境变量”）
docker compose up -d --build
```

启动后：

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:8080 |
| 后端 API | http://localhost:5000 |
| 健康检查 | http://localhost:5000/health |

中文搜索需要把 IK 分词插件放入 ES 插件目录：

```bash
mkdir -p elasticsearch/plugins/analysis-ik
unzip -o elasticsearch-analysis-ik-8.11.0.zip -d elasticsearch/plugins/analysis-ik
# 修改后重启 ES：docker compose restart elasticsearch-cn
```

> 首次启动会自动初始化 MySQL 主从、Redis 哨兵与 Elasticsearch，耗时数分钟。
> 应用容器入口脚本会在启动前自动执行 `flask db upgrade`。

## 端口一览

| 服务 | 端口 |
|---|---|
| web（前端 / nginx） | `8080` |
| app（Flask API） | `5000` |
| MySQL 主库 / 从库 | `3306` / `3307` |
| Redis 主库 / 从库 | `6379` / `6380`、`6381` |
| Redis 哨兵 | `26379`、`26380`、`26381` |
| Elasticsearch | `9201` |
| Prometheus / Grafana / Alertmanager | `9090` / `3000` / `9093` |
| Jaeger UI / OTLP | `16686` / `4317`、`4318` |
| Loki | `3100` |

## 环境变量

完整列表与默认值见 [`.env.example`](.env.example)。关键项：

| 变量 | 说明 |
|---|---|
| `SECRET_KEY` | Flask 会话密钥，生产必须替换为随机值 |
| `JWT_SECRET_KEY` | JWT 签名密钥，生产必须替换 |
| `MFA_ENCRYPTION_KEY` | MFA secret 的 Fernet 加密密钥 |
| `DEV_DATABASE_URL` | 主库连接串（读写） |
| `REPLICA_DATABASE_URL` | 从库连接串（读） |
| `DATABASE_URL` | 生产配置使用的主库连接串 |
| `MYSQL_*` | MySQL 账号与口令（供 compose 初始化） |
| `REDIS_*` / `REDIS_SENTINEL_HOST` | Redis 与哨兵地址、口令 |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Celery broker / backend |
| `ELASTICSEARCH_ENABLED` / `ELASTICSEARCH_HOSTS` | 是否启用 ES 及地址 |
| `SEARCH_DEGRADE_MODE` / `SEARCH_DEGRADE_TTL` | 搜索降级模式与熔断窗口 |
| `STORAGE_BACKEND` / `STORAGE_PUBLIC_BASE` | 上传存储后端与回显基址 |
| `RATE_LIMIT_STORAGE` / `RATE_LIMIT_DEFAULT` | 限流存储与默认限额 |
| `MAIL_*` | 邮件服务配置 |

生成密钥示例：

```bash
python -c "import secrets; print(secrets.token_hex(32))"                     # SECRET_KEY / JWT_SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # MFA_ENCRYPTION_KEY
```

## 本地开发

后端：

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
# 确保 MySQL / Redis / ES 可用（可直接用 docker compose 起依赖）
flask db upgrade
python wsgi.py            # http://localhost:5000
```

前端：

```bash
cd web
npm install
npm run dev               # http://localhost:5173，/api 代理到 localhost:5000
npm run build             # 产物输出到 web/dist
```

## 测试

```bash
pytest tests/unit -q                       # 单元测试（SQLite + FakeRedis，CI 使用）
pytest tests/integration -q                # 集成测试
pytest tests/smoke -q                      # 冒烟测试

# 性能测试（先造数据/发 token，再压测；实测结果见 docs/PERF_REPORT.md）
docker exec -i -e PYTHONPATH=/app -e PERF_USERS=40 -e PERF_POSTS=10 \
  weibo-app python - < tests/performance/seed_tokens.py \
  | grep -o 'PERF_TOKENS_JSON=.*' | sed 's/^PERF_TOKENS_JSON=//' > /tmp/perf_tokens.json
PERF_TOKENS_FILE=/tmp/perf_tokens.json locust -f tests/performance/locustfile.py \
  --headless -u 40 -r 8 -t 60s --host http://127.0.0.1:5000
```

静态检查与依赖校验：

```bash
ruff check .
python scripts/check_requirements_sync.py  # requirements.txt 与 pyproject.toml 是否一致
```

## API 文档

各模块提供 Swagger 文档，路径为 `<模块前缀>/docs`，例如：

- 用户：`/api/users/docs`
- 帖子：`/api/posts/docs`
- 通知：`/api/notifications/docs`

## 生产部署要点

1. **配置**：使用 `FLASK_CONFIG=production`。生产配置强制要求 `DATABASE_URL`、`SECRET_KEY`、`JWT_SECRET_KEY`、`REDIS_PASSWORD`，缺失会拒绝启动；同时收紧登录锁定、CORS 与安全响应头。
2. **WSGI**：以 Gunicorn 运行（线程模型 `gthread`），不要使用 Flask 内置服务器。
3. **数据库迁移**：容器入口 `scripts/docker-entrypoint.sh` 会先执行 `flask db upgrade` 再启动应用；生产环境关闭自动建表。
4. **反向代理**：在应用前放置 nginx，处理 TLS、静态资源与 `/api`、`/uploads` 转发；应用侧信任一层代理（`X-Forwarded-For` / `X-Forwarded-Proto`）。
5. **上传体积**：nginx 需显式设置 `client_max_body_size`（默认 1MB），并与后端 `MAX_CONTENT_LENGTH` 对齐。
6. **上传持久化**：本地存储需将上传目录挂载为持久卷；多实例场景建议切换对象存储。
7. **磁盘**：nginx 会对大于 `client_body_buffer_size`（默认 8KB）的请求体写临时文件，务必保证其临时目录所在分区有充足空间，否则上传等请求会返回 500。
8. **备份**：定期备份 MySQL（如 `mysqldump`）并演练恢复；ES 数据卷按需快照。

## 可观测性

监控栈独立部署：

```bash
docker compose -f monitoring/docker-compose.monitoring.yml up -d
```

| 组件 | 地址 |
|---|---|
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| Alertmanager | http://localhost:9093 |
| Jaeger | http://localhost:16686 |
| Loki | http://localhost:3100 |

指标来自应用 `/metrics`，链路来自 OpenTelemetry。SLI / SLO 与告警规则定义见 [`docs/SLO.md`](docs/SLO.md)。

主从延迟指标：MySQL 走从库 exporter（`mysql_slave_status_seconds_behind_master`），Redis 走从库 exporter（`redis_master_last_io_seconds_ago` / `redis_master_link_up`）；Grafana `weibo-overview` 含对应面板，告警见 `weibo_rules.yml` 的 `weibo-replication-alerts`。

## 常见问题 / 排障

- **中文搜索无效**：确认 IK 插件已解压到 `elasticsearch/plugins/analysis-ik/`，并重启 ES。
- **首次启动很慢**：MySQL 主从初始化 + ES 建索引需要数分钟，观察 `docker compose ps` 是否 `healthy`。
- **图片上传失败**：
  - 通过 nginx 访问时，先确认 `client_max_body_size` 足够；
  - 若直接返回 nginx 的 HTML 500、且应用日志无记录，优先检查 nginx 临时目录所在分区是否写满；
  - 检查上传目录的挂载与写权限。
- **日志“看不到”**：应用日志同时写入 stdout 与 `logs/*.log`，容器内 `docker logs` 只覆盖前者。
- **限流误判 / 取不到真实 IP**：应用需在反向代理之后正确代理 `X-Forwarded-For`。

## 已知限制

- 事件总线为「尽力而为 + 对账兜底」，非精确一次投递。
- 搜索在 ES 故障时降级为数据库查询，召回与延迟不按 ES 目标承诺。
- SSE 并发受 Gunicorn 工作线程数限制，需按容量调整。
- 缓存整体为最终一致，不提供强一致读。
- 自建 MySQL 主从 / Redis 哨兵 / ES 适合单机或小规模部署，更大规模建议使用托管服务或编排系统。

详见 [`docs/SLO.md`](docs/SLO.md)。

## 贡献

欢迎提交 Issue 与 Pull Request。提交前请确保：

```bash
ruff check .
pytest tests/unit -q
python scripts/check_requirements_sync.py
```

## License

本项目采用 [MIT](LICENSE) 许可协议。
