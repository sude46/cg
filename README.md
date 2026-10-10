# Weibo Platform

基于 Flask + Vue 3 的微博类社交平台，覆盖发帖、关注、点赞、评论、通知、私信、全文搜索与异步任务，并附带完整的可观测性方案。后端采用分层架构（Routes → Service → Repository → Model），支持 MySQL 主从、Redis 哨兵、Elasticsearch 中文搜索与 Celery 异步处理。

## 功能

- 用户认证：JWT（access / refresh）、登出黑名单、TOTP 双因子
- 社交互动：帖子 CRUD、评论、点赞、关注 / 粉丝 / 互关
- 信息流：关注时间线、全站广场、热榜与热搜
- 通知与私信：未读数、基于 SSE 的实时推送
- 搜索：Elasticsearch 全文 / 子串检索（IK 中文分词），故障自动降级到数据库
- 上传：图片上传与回显（本地存储，接口可扩展 S3 / MinIO / OSS）
- 异步任务：Celery 处理 Feed 推送、ES 索引、缓存失效与对账
- 可观测性：Prometheus 指标、Grafana 面板、Loki 日志、Jaeger 链路追踪、Sentry

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+、Flask 3、Flask-RESTX、SQLAlchemy 2、Alembic、Celery |
| 存储 | MySQL / MariaDB（主从）、Redis（哨兵 + Pub/Sub）、Elasticsearch 8 + IK |
| 前端 | Vue 3、Vite、TypeScript、Element Plus、TanStack Query、Axios |
| 可观测 | Prometheus、Grafana、Alertmanager、Loki、Jaeger（OpenTelemetry） |
| 部署 | Docker、Docker Compose、Gunicorn |

## 架构

```
                    ┌─────────────┐
   浏览器 ───────▶  │  web(nginx)  │ 8080
                    └──────┬──────┘
              /api/* 反代   │   /uploads/* 反代
                           ▼
                    ┌─────────────┐
                    │ Flask (app) │ 5000  ← Gunicorn
                    └──────┬──────┘
                           │
          Routes → Service → Repository → Model
             │            │           │
             ▼            ▼           ▼
        Redis(Pub/Sub)  Celery    MySQL 主从 / ES
                          │
             worker / beat（异步任务）
```

## 目录结构

```
app/            业务模块（users / posts / comments / likes / follows / feeds / notifications / chats / uploads）
core/           应用工厂、数据库、扩展、蓝图注册、可观测性接入
config/         分环境配置（development / production / testing）
services/       跨模块服务（搜索等）
middlewares/    鉴权、CORS、限流、日志、指标、安全头
tasks/          Celery 任务
migrations/     数据库迁移（Alembic）
monitoring/     Prometheus / Grafana / Loki / Jaeger / Alertmanager
web/            前端（Vue 3 + Vite）
docs/           设计与运维文档
tests/          单元 / 集成 / 冒烟 / 性能测试
```

## 快速开始（Docker Compose）

前置条件：Docker 与 Docker Compose v2；建议内存 ≥ 4GB（含 Elasticsearch）。

```bash
git clone https://github.com/sude46/cg.git
cd cg
cp .env.example .env      # 按需填写密钥与配置
docker compose up -d --build
```

启动后：

- 前端：http://localhost:8080
- 后端 API：http://localhost:5000
- 健康检查：http://localhost:5000/health

> 首次启动会自动初始化 MySQL 主从、Redis 哨兵与 Elasticsearch，需要几分钟。
> 中文搜索需将 `elasticsearch-analysis-ik-8.11.0.zip` 解压到 `elasticsearch/plugins/analysis-ik/`（详见 `docs/ELASTICSEARCH_SETUP.md`）。

## 环境变量

所有配置项及说明见 [`.env.example`](.env.example)。关键项：

| 变量 | 说明 |
|---|---|
| `SECRET_KEY` / `JWT_SECRET_KEY` | Flask / JWT 密钥，生产环境必须替换 |
| `DEV_DATABASE_URL` / `REPLICA_DATABASE_URL` | MySQL 主库 / 从库连接串 |
| `REDIS_URL` / `REDIS_SENTINEL_HOST` | Redis 与哨兵地址 |
| `ELASTICSEARCH_HOSTS` | Elasticsearch 地址 |
| `STORAGE_PUBLIC_BASE` | 图片回显基址（本地存储默认 `/uploads/files`） |
| `MAIL_*` | 邮件服务配置 |

## 本地开发

后端：

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
# 确保 MySQL / Redis / ES 可用（可直接用 docker compose 起依赖）
flask db upgrade
python wsgi.py
```

前端：

```bash
cd web
npm install
npm run dev        # http://localhost:5173，/api 代理到 localhost:5000
```

## 测试

```bash
pytest tests/unit -q                     # 单元测试（CI 使用，SQLite + FakeRedis）
pytest tests/integration -q              # 集成测试
locust -f tests/performance/locustfile.py  # 性能测试
```

代码风格与静态检查：

```bash
ruff check .
```

## API 文档

各模块提供 Swagger 文档，路径为 `<模块前缀>/docs`，例如：

- 用户：`/users/docs`
- 帖子：`/posts/docs`
- 通知：`/notifications/docs`

经前端 nginx 访问时前缀为 `/api`，例如 `/api/users/docs`。

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

指标来自应用 `/metrics`，链路来自 OpenTelemetry。SLI / SLO 定义见 [`docs/SLO.md`](docs/SLO.md)。

## 已知限制

- 事件总线为「尽力而为 + 对账兜底」，非投递保证
- 搜索在 ES 故障时降级为数据库 `LIKE`，召回与延迟不按 ES 目标承诺
- SSE 并发受 Gunicorn 线程数限制，需按容量调整
- 缓存整体为最终一致

详见 [`docs/SLO.md`](docs/SLO.md)。

## License

本项目采用 [MIT](LICENSE) 许可协议。
