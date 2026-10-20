# SLO.md — 服务等级目标与可观测性

> 范围：weibo 平台后端（Flask API + Celery 异步）及其依赖（MySQL 主从 / Redis 哨兵 / Elasticsearch）。
> 指标来自 `/metrics`（Prometheus），链路来自 OpenTelemetry → Jaeger。
> 目标值是**工程默认值**，按业务与容量可调。

---

## 1. 关键用户旅程

| 旅程 | 说明 | 同步/异步 |
|---|---|---|
| 登录/注册 | 认证、签发 token | 同步 |
| 发帖 / 编辑 / 删除 | 帖子 CRUD | 同步 + 异步（Feed 推送、ES 索引） |
| 时间线 / 广场 | 关注流、全站广场 | 同步（Redis + DB 兜底） |
| 关注 / 点赞 / 评论 | 社交互动 | 同步（Redis 优先）+ 异步落库 |
| 通知 / 私信 | 未读数、实时推送 | SSE（Redis Pub/Sub）+ 同步接口 |
| 搜索 | 全文/子串检索 | 同步（ES，故障降级 DB） |

---

## 2. SLI / SLO 总表

窗口：**30 天滚动**。可用性/延迟按非健康请求统计。

| 维度 | SLI（指标） | SLO | 错误预算(30d) |
|---|---|---|---|
| 可用性 | `1 - 5xx占比`（`weibo_http_requests_total`） | **≥ 99.5%** | 3h36m |
| API 延迟 | P95（`weibo_http_request_duration_seconds`） | **≤ 300ms** | — |
| API 延迟 | P99 | **≤ 800ms** | — |
| DB 延迟 | P99（`weibo_db_query_duration_seconds`） | **≤ 200ms** | — |
| 从库健康 | `weibo_db_replica_healthy == 1` | **≥ 99.9%** | — |
| 读回落率 | `rate(weibo_db_replica_failover_total[5m])` | **≈ 0**（< 1/s） | — |
| MySQL 主从延迟 | `mysql_slave_status_seconds_behind_master` P99 | **≤ 1s**（严重 > 3s） | — |
| Redis 主从延迟 | `redis_master_last_io_seconds_ago` P99 | **≤ 1s** | — |
| 强一致窗口代价 | `rate(weibo_read_forced_master_total[5m])` | 观察项（无硬目标） | — |
| 数据一致性 | `weibo_reconcile_diff_count` | **= 0** | 0 |
| 异步成功率 | Celery `success/(success+failure)`（`weibo_celery_tasks_total`） | **≥ 99%** | 7h12m |
| 异步积压 | `celery_queue_length` | **< 500**（瞬时 < 1000） | — |
| 缓存命中 | `weibo_redis_cache_hit_rate{cache_type}`（**当前是 Gauge 最后值，不是命中率 Counter**） | 观察项；改造为 hit/miss Counter 后再定 **≥ 0.7** | — |
| 业务成功率 | 各 `weibo_*_operations_total{result="success"}` 占比 | **≥ 99%** | — |
| 搜索一致性 | `weibo_reconcile_diff_count{resource_type="search"}` | **= 0** | 0 |

> 说明：当前代码实际写入的对账维度是 **like / post / search**：
> - `like` ← `reconcile_like_counts`
> - `post` ← `reconcile_post_cache`
> - `search` ← `reconcile_search_index`
>
> `user_reconcile` 与 `reconcile_hot_comments` 目前只写日志、不写 `weibo_reconcile_diff_count{resource_type=...}`；指标 label 里预留了 feed/comment/user，但没有对应任务写入，告警/看板不要假设这些维度存在。
>
> **实测基线（2 vCPU / 7.7GiB 单机、全依赖同机，2026-10-20）**：Feed 读路径**单请求 47–83ms**；并发 10/20/40 时吞吐约 **7 / 12 / 9 req/s**（P95 0.9s / 1.7s / 8.4s），**0 失败**。
> 瓶颈是单机 2 vCPU 的 CPU/线程竞争，**不作为生产容量承诺**；详见 [`PERF_REPORT.md`](PERF_REPORT.md)。

---

## 3. 错误预算与告警策略

### 3.1 预算计算（可用性 99.5% / 30d）
```
预算时长 = 30d × (1 - 0.995) = 3h36m
已消耗 = 5xx 请求数 / 总请求数 / (1 - 0.995)
```

### 3.2 多窗口燃烧率（示例，建议新增规则）
| 严重度 | 条件 | 含义 |
|---|---|---|
| 快烧 (page) | 1h 燃烧率 > 14.4 | 2 天内烧完预算 |
| 慢烧 (ticket) | 6h 燃烧率 > 6 | 30 天窗口告警 |
| 预算耗尽 | 30d 消耗 > 100% | 冻结发布、优先修复 |

```promql
# 1h 燃烧率（基于 5xx/总量）
(
  sum(rate(weibo_http_requests_total{status_code=~"5.."}[1h]))
  / sum(rate(weibo_http_requests_total[1h]))
) / (1 - 0.995)
```

### 3.3 与现有告警的对应
`monitoring/prometheus/rules/weibo_rules.yml` 已覆盖：
- `WeiboApiHighLatency`（P99>500ms, 2m）
- `WeiboApiHighErrorRate`（5xx>1%, 2m）
- `WeiboCeleryQueueBacklog`（`celery_queue_length>1000`, 1m）
- `WeiboRedisMemoryHigh`（>80%, 5m）
- `WeiboDbSlowQuery`（DB P99>500ms, 3m）
- `WeiboMysqlDown`（`up{job="mysql-master"}==0`, 1m）
- `WeiboReconcileDiff`（`weibo_reconcile_diff_count>0`, 1m）
- `WeiboMysqlReplicationLag`（从库延迟>1s, 2m）/ `WeiboMysqlReplicationLagCritical`（>3s, 1m）
- `WeiboMysqlReplicaNotRunning`（`Slave_IO/SQL_Running` 非 1, 1m）
- `WeiboRedisReplicationLag`（`redis_master_last_io_seconds_ago>1`, 2m）
- `WeiboRedisReplicaLinkDown`（`redis_master_link_up==0`, 1m）
- `WeiboEventBusBacklog`（`weibo_event_bus_queue_length>1000`, 2m）
- `WeiboEventBusDeadLetter`（`weibo_event_bus_dead_letter_length>0`, 1m）
- `WeiboEventBusProcessingStuck`（`weibo_event_bus_processing_length>100`, 2m）
- `WeiboEventBusHandlerFailures`（handler 失败速率>1/s, 5m）
- `WeiboEventBusReclaimStorm`（滞留回收速率>0.2/s, 5m）

**待补**：从库不健康（`weibo_db_replica_healthy==0`）、Celery 失败率、搜索对账差异（可用现有 `WeiboReconcileDiff` 覆盖，因它不区分 label）。

---

## 4. PromQL 速查

```promql
# 可用性（30d）
1 - (
  sum(increase(weibo_http_requests_total{status_code=~"5.."}[30d]))
  / sum(increase(weibo_http_requests_total[30d]))
)

# 接口 P95（5m）
histogram_quantile(0.95, sum(rate(weibo_http_request_duration_seconds_bucket[5m])) by (le, endpoint))

# 按接口的 5xx 比例
sum(rate(weibo_http_requests_total{status_code=~"5.."}[5m])) by (endpoint)
/ sum(rate(weibo_http_requests_total[5m])) by (endpoint)

# DB P99（按表）
histogram_quantile(0.99, sum(rate(weibo_db_query_duration_seconds_bucket[5m])) by (le, table))

# Celery 失败率（5m）
sum(rate(weibo_celery_tasks_total{status="failure"}[5m]))
/ clamp_min(sum(rate(weibo_celery_tasks_total[5m])), 1)

# 对账差异（各资源）
weibo_reconcile_diff_count

# 从库健康 / 回落
weibo_db_replica_healthy
rate(weibo_db_replica_failover_total[5m])

# 主从延迟（MySQL / Redis 从库 exporter）
mysql_slave_status_seconds_behind_master{job="mysql-replica"}
redis_master_last_io_seconds_ago{job=~"redis-replica-.*"}

# 强一致窗口代价（窗口内强制读主库的速率）
sum(rate(weibo_read_forced_master_total[5m])) by (resource)
```

---

## 5. 采集与展示

| 组件 | 地址 | 用途 |
|---|---|---|
| 应用 `/metrics` | `app:5000/metrics` | 业务/HTTP/DB/Redis/Celery 指标 |
| Prometheus | `:9090` | 抓取与告警规则 |
| Alertmanager | `:9093` | 告警路由（钉钉 webhook） |
| Grafana | `:3000` | 面板 |
| Loki | `:3100` | 日志（含 `request_id`；**`trace_id` 尚未加入日志格式**，需在 `core/logging_config.py` 的 `log_format` 中补充） |
| Jaeger | `:16686` | 分布式追踪（`weibo-api` / `weibo-worker`） |

抓取目标见 `monitoring/prometheus/prometheus.yml`：`weibo-api(app:5000)`、node、redis-business、mysql-master、mysql-replica、redis-replica-1/2、celery、alert-webhook。
追踪：HTTP → SQL → 自研事件总线 → Celery → ES 已贯通（见 `core/tracing.py`）。

> 采集注意：应用 `/metrics` 目前使用 prometheus_client 默认的进程内 registry，Gunicorn 多 worker 下不是聚合值。要么把 web 进程改成单 worker 专门暴露指标，要么启用 `PROMETHEUS_MULTIPROC_DIR` + `MultiProcessCollector`；在此之前，SLO 计算应使用 Prometheus 端的多实例聚合，或明确只对单 worker 生效。

---

## 6. 已知限制（SLO 不承诺的部分）

1. **异步事件为 at-least-once，非 exactly-once**：自研事件总线用 `LPUSH` + `BLMOVE(queue→processing)` + 处理完 `LREM` ack，reaper 回收超时在途事件；失败后重入队，超过阈值进死信队列（可用 `scripts/replay_event_dlq.py` 重放）。因此**可能重复投递**，handler 必须幂等（总线按 `event.id` 做幂等去重，TTL 默认 24h）。多进程（`gunicorn -w N`）共享队列，事件由哪个进程处理不确定。SSE 走 Pub/Sub，不在此列。
   - **“重试 3 次”的真实语义**：代码是 `retry_count += 1` 后判断 `< EVENT_BUS_MAX_RETRY`，所以 `EVENT_BUS_MAX_RETRY=3` 表示**总共 3 次处理机会（初始 1 次 + 重试 2 次）**，不是“初始 + 3 次重试”。若要 1 次初始 + 3 次重试，应配 `4` 或改比较逻辑。
   - **极端丢失窗口**：handler 失败后重入队本身失败时，`_dispatch` 只记日志，`_consume` 仍会 ack，事件可能丢失。当前靠 error 日志/指标发现，后续应改为进死信或保留 processing。
   - `EVENT_BUS_VISIBILITY_TIMEOUT=60s` 必须大于最慢 handler；小于 handler 耗时会重复投递。
2. **私信未读数**：`chats` 用 `ConversationUser.unread_count` 求和（DB SELECT）；尚未做 Redis 计数与对账，热点会话量大时延迟会上升。
3. **搜索依赖 ES**：ES 故障时降级为 DB `ILIKE`（短 TTL 缓存），召回与延迟都不能按 ES 目标承诺；重建索引期间结果可能暂缺。
4. **缓存一致性**：Cache-Aside + 延迟双删（写后立即删缓存，再由 Celery `delayed_invalidate` 在约 2s 后二次删）；窗口内读强制走主库，避免主从延迟回跳旧值。整体为**最终一致**，不接受强一致读承诺。
   - **帖子**：`PostCache.RECENT_MODIFY_TTL=60`，但 `create_post/update_post/delete_post` 显式传 `ttl=5`，所以**代码意图是 5s**。
   - **通知**：`NotificationCache.RECENT_MODIFY_TTL=60`。
   - **用户**：默认 60s，登录/注册/资料更新路径显式传 5s。
   - **重要偏差**：`mark_recently_modified` 调用的是 `RedisCache.set`，而 `set` 会加 `0–60s` 随机 jitter（防雪崩）。因此实际窗口是：帖子 **5–65s**、通知/用户默认 **60–120s**。这与“5s/60s 强一致窗口”的表述不一致；强一致窗口应改用 `set_exact`（`core/redis_cache.py` 已提供）或给 `set` 增加 `jitter=False` 参数。
   - 延迟双删的 `countdown=2s` 与窗口 TTL 目前是工程默认值，**应依据 `mysql_slave_status_seconds_behind_master` / `redis_master_last_io_seconds_ago` 的实测 P99 校准**（建议 `countdown = max(2s, 2×P99)`、`窗口 TTL = countdown + P99`，并用 `set_exact` 保证不被 jitter 放大）。
   - `PostCache.invalidate` 不应删除 `recent_modify` 标记，否则延迟双删的第二次删除会提前结束窗口；当前代码已修复（`app/posts/cache.py`）。
5. **无前端 RUM**：仅服务端指标，页面级可用性/交互延迟不在本 SLO 内。
6. **无自动 Trace-SLO**：Jaeger 用于排障与人工核对，暂未用 trace 数据自动计算 SLO。
7. **单实例 beat**：`beat_schedule` 依赖单个 `celery-beat`，多实例会重复触发；对账/热榜属幂等任务，可容忍。
8. **SSE 并发上限**：以当前仓库 `Dockerfile` 的实际启动命令 `gunicorn -w 4 -k gthread --threads 8` 计算，理论工作线程数 **4×8=32**；每条 SSE 长连接独占 1 个线程 + 1 条 Redis pub/sub 连接，因此**理论上限约 32**（通知流 + 私信流共用）。此前文档写的 `--threads 2 → 8` 与 Dockerfile 不一致，已按代码更正；实际容量仍需压测，不能只看线程数。
   - **Gunicorn 默认 `timeout=30s`** 未显式覆盖，长连接场景有被回收的风险；应按 worker 类型实测并显式配置。
   - 当前以 nginx `proxy_read_timeout 3600s` + 后端心跳（通知 20s / 私信 15s）保活。
   - 无 `Last-Event-ID`，断线期间增量不会自动补，只能重连后拉历史；每连接还占一条 Redis pub/sub 连接，连接数不是免费的。
   - 更高并发应改用 gevent/eventlet，或把实时层拆成独立 FastAPI WebSocket/SSE 网关。
9. **Prometheus 多进程指标未聚合**：`prometheus_client` 默认 registry 是进程内的，Gunicorn 多 worker 下 `/metrics` 每次可能由不同 worker 响应，Counter 会跳变、Gauge 只反映某个 worker。当前未启用 `PROMETHEUS_MULTIPROC_DIR` + `MultiProcessCollector`，所以：
   - 第 2 节的 API/DB/Celery 总量类 SLO 在多 worker 部署下**不能直接按单进程 `/metrics` 计算**；
   - `weibo_redis_cache_hit_rate` 是 Gauge 最后值，不是命中率；
   - worker 进程写的 Celery/事件总线指标不会被 web `/metrics` 看到。
   生产启用多进程采集前，这些指标只适合排障，不适合作为严格 SLO 依据。
10. **点赞缓存冷启动风险**：`LikeCache.add_like` 的 Lua 在计数 key 不存在时会 `INCR` 成 1；如果 DB 已有历史点赞但 Redis 未预热，随后对账“以 Redis 为准”可能把 DB 计数修正得过小。当前 Service 只在 Redis 异常（返回 None）时回填 DB 真值，`is_liked` 对“key 不存在”返回 False，不会触发回填。上线前应做冷启动预热或调整对账方向。
11. **搜索评论数可能滞后**：搜索事件只订阅了 `post.like_count_changed`，没有订阅 `post.comment_count_changed`，ES 文档的 `comment_count`/`hot_score` 可能落后于 DB；搜索排序的“热度”因此是近似值。

---

## 7. 文档维护

- 新增关键接口/异步链路时，同步更新第 1、2 节与 `weibo_rules.yml`。
- 调整 SLO 目标需评估错误预算与容量，并记录变更原因。
- 实现与文档不一致时，以代码为准并回写文档；不要保留“看起来有监控、实际没有”的描述。

### 7.1 本次同步记录（2026-10-20）

结合代码复核后修正：

1. SSE 并发上限从 `--threads 2 → 8` 更正为 Dockerfile 实际的 `-w4 --threads 8 → 32`，并补充 Gunicorn timeout/无 Last-Event-ID/Redis 连接占用风险。
2. 事件总线“重试 3 次”更正为“总共 3 次处理机会（初始 + 2 次重试）”，并补充重入队失败可能丢事件的极端窗口。
3. `recent_modify` 窗口补充 jitter 放大：帖子实际 5–65s、通知/用户默认 60–120s，强一致窗口应改用 `set_exact`。
4. 对账指标口径更正：当前代码只写 like/post/search，user/comment/feed 没有写 `reconcile_diff_count`。
5. 日志 `trace_id` 更正为尚未加入格式（当前只有 `request_id`）。
6. 缓存命中率指标标注为 Gauge 最后值，不能直接作为 SLO；补充 Prometheus 多进程未聚合的限制。
7. 补充点赞缓存冷启动、搜索评论数滞后两个一致性风险。

更完整的架构/数据/缓存/主从/面试题解析见 [`PROJECT_DEEP_DIVE_INTERVIEW.md`](PROJECT_DEEP_DIVE_INTERVIEW.md)。
