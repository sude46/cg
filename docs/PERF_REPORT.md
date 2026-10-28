# 压测报告 — Feed 读路径（Locust）

> 目标：给出可复现的实测数据，而不是只有脚本和拍脑袋的 SLO 目标。
> 脚本：`tests/performance/locustfile.py`、`load_test.js`（k6）、`seed_tokens.py`（造数据/发 token）。
>
> 测量时间：2026-10-20。该时间早于 fix-batch（outbox、Celery late ack、点赞 Lua/唯一约束、Feed 降级回填等）。读路径基线仍可参考；写路径和异步链路需要按新代码重测。

## 1. 测试环境

| 项 | 值 |
|---|---|
| 宿主机 | **2 vCPU / 7.7 GiB RAM** |
| Docker | 29.4.0 |
| 应用 | `gunicorn -w 4 -k gthread --threads 8`（32 工作线程）|
| 依赖（**同机**部署）| MariaDB 10.6 主 + 从、Redis 主 + 2 从 + 3 Sentinel、Elasticsearch 8.11、Celery worker `-c 4` + beat |
| 压测工具 | Locust 2.15.1（headless，**与所有服务同机**）|
| 读路径 | Repository → `db_router` → 从库 |

> 所有服务 + 压测客户端挤在一台 2 vCPU 机器上，**CPU 是硬约束**；这些数字是"受限单机基线"，不是生产容量承诺。

## 2. 场景与数据

- `seed_tokens.py`（走 DB/Redis，不经过 HTTP 限流）：
  - 1 个内容作者 + 10 篇帖；
  - 40 个压测用户关注该作者；
  - 生成 40 个 access token（production 配置下有效期 30 分钟）。
- 读操作混合（权重）：`/feeds/timeline` 5、`/feeds/explore` 3、`/posts` 2。
- 每用户 `wait_time` 0.8–1.5s（约 0.7–1.2 req/s/用户，低于默认 100/min/用户）。
- 认证用预生成 JWT（不压 login/register：它们有 10/min、5/min 的路由级硬限流）。

**单请求基线**（无并发，直接请求部署实例）：`timeline` 73ms / `explore` 47ms / `posts` 83ms，返回真实数据（3.8–7.5 KB）。

## 3. 结果：容量曲线（修复后，token 有效、返回真实数据）

| 并发 | 吞吐 | P50 | P95 | P99 | 错误率 |
|---|---|---|---|---|---|
| 10 | **7.0 req/s** | — | 890 ms | 1.1 s | 0% |
| 20 | **11.8 req/s** | — | 1.7 s | 2.4 s | 0% |
| 40 | **9.4 req/s** | 2.2 s | 8.4 s | 12 s | 0% |

40 并发分接口（`tests/performance/results/locust_feed_stats.csv`）：

| 接口 | 请求数 | req/s | P95 | P99 |
|---|---|---|---|---|
| `/feeds/timeline` | 272 | 4.60 | 5.3 s | 6.0 s |
| `/feeds/explore` | 180 | 3.04 | 5.3 s | 6.3 s |
| `/posts` | 104 | 1.76 | 12 s | 13 s |

**解读**：单请求 47–83ms，但并发一上来延迟迅速放大（10 并发 P95 已 890ms），说明瓶颈是**单机 2 vCPU + 全依赖同机**的 CPU/线程竞争，而不是某个接口报错（全程 0 失败）。40 并发已过拐点（吞吐反而下降）。要拿到有意义的容量数字，需要把应用与依赖/压测客户端分机部署。

## 4. 压测发现并修复的真实瓶颈

首轮 40 并发直接崩：**P95 33s、错误率 20.6%、仅 3.1 req/s**，日志为
`QueuePool limit of size 5 overflow 10 reached, connection timed out`。

- **根因**：`core/db_router.py:get_read_session()` 每次调用都 `Session(db, bind=...)` 新建会话，
  Repository 用完不 `close()`；一个请求会创建多个会话、连接迟迟不归还，
  高并发下把 SQLAlchemy 连接池（默认 `pool_size=5 + max_overflow=10`）耗尽 → 30s 超时 → 500。
- **修复**：读会话按请求复用（缓存到 `flask.g`），并在 `teardown_appcontext` 里 `close()` 归还连接。

| 40 并发 | 修复前 | 修复后 |
|---|---|---|
| 请求/失败 | 160 / **33（20.6%，500）** | 556 / **0** |
| 吞吐 | 3.1 req/s | 9.4 req/s |
| P95 | 33 s | 8.4 s |

> 修复的价值首先体现在**消除连接池耗尽导致的 500**；之后再谈吞吐。剩余延迟来自上述 2 vCPU 限制。

## 5. 压测方法上的坑（已规避，记录备查）

1. **token 有效期**：production access token 30 分钟。压测跨过 30 分钟会突然出现 **401**，看起来像"应用坏了"，实际是 token 过期。每次正式跑前重新 `seed_tokens.py`。
2. **空 feed 会虚高**：若压测用户的时间线为空，响应只有几百字节，吞吐会虚高。务必先确认单请求返回真实数据（本次 3.8–7.5 KB）。
3. **限流按用户计**：默认 100/min/用户；同一批 token 在短时间内连跑多轮会互相消耗预算（触发 429/401 混淆）。正式跑前保持 token 新鲜、不要同一批用户连续多次压。
4. **压测客户端不要和服务同机**：本次 Locust 与全部服务共享 2 vCPU，结果偏悲观。

## 6. 复现

```bash
# 1) 造数据 + 生成 token（在 app 容器内，走真实 DB/Redis）
docker exec -i -e PYTHONPATH=/app -e PERF_USERS=40 -e PERF_POSTS=10 \
  weibo-app python - < tests/performance/seed_tokens.py \
  | grep -o 'PERF_TOKENS_JSON=.*' | sed 's/^PERF_TOKENS_JSON=//' > /tmp/perf_tokens.json

# 2) 压测（建议把 locust 放到另一台机器，--host 指向应用）
PERF_TOKENS_FILE=/tmp/perf_tokens.json \
locust -f tests/performance/locustfile.py --headless \
       -u 40 -r 8 -t 60s --host http://127.0.0.1:5000 \
       --csv tests/performance/results/locust_feed

# 3) 清理压测数据（用户名以 smoke_perf_ 开头，cleanup 脚本会识别）
docker exec -i weibo-app python scripts/cleanup_dev_data.py
```

## 7. 结论

- 修复了高并发下 **DB 连接池耗尽 → 500** 的真实 bug。
- 在 2 vCPU 单机、全依赖同机的约束下，Feed 读路径单请求 **47–83ms**；并发 10/20/40 时吞吐约 7/12/9 req/s，延迟随并发快速上升，**瓶颈是 CPU 资源**。
- 本报告不覆盖：写路径（发帖/点赞）、搜索（ES）、SSE 长连接。
- 下一步若要给出生产容量：应用与依赖分机、压测客户端独立、放宽/关闭限流后重测。
