# Fix batch 部署说明

范围：2026-10 这一批一致性、事件可靠性和 Feed 修复。代码已合入 `main`，包括 13 个修复分支和随后的 SQLAlchemy 版本固定提交。

## 变更概要

- 点赞：对账方向守卫、任务按 Redis 当前状态收敛、Lua 原子覆盖全部 key、active 唯一约束 + 硬删除。
- Feed：关注/大 V 索引缓存 miss 时回源；大 V 降级先回填历史帖子再解除标记。
- JWT：refresh 轮换和 grace 结果写入同一个 Lua。
- 事件：业务事务写 `event_outbox`，relay 投递；消费端按 `event.id` 幂等；handler 不再吞异常；无订阅者的评论数事件已处理。
- Celery：late ack、`worker_prefetch_multiplier=1`、visibility timeout 7200s。
- 一致性：未读数在强一致窗口内先读主库；Feed 分层粉丝数和热评重建走主库。
- 依赖：`SQLAlchemy` 固定 2.0.46，匹配 `opentelemetry-instrumentation-sqlalchemy`。

## 上线前

1. 备份 MySQL。重点备份 `likes` 和 `notifications`。
2. 确认没有多个 Celery beat 同时运行。outbox relay 和多实例对账都依赖单 beat；重复执行通常幂等，但会增加无谓负载。
3. 预留维护窗口。FIX-12 的迁移会删除所有 `deleted_at IS NOT NULL` 的点赞，并对 active 重复点赞去重，只保留最小 id。这个操作不可逆。

```bash
docker compose exec -T mysql-master sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' \
  > backup_before_fix_batch.sql
```

## 迁移

app 容器入口会执行 `flask db upgrade`。手动执行也可以：

```bash
flask db upgrade
```

预期迁移顺序：

```text
9b1c4d7e2f30  notifications.event_id
c4a7e2f9b1d3  event_outbox
d8f2a6c1b9e4  likes active unique
```

迁移完成后确认版本：

```bash
flask db current
# 应输出 d8f2a6c1b9e4 (head)
```

## 部署

如果只改了 Python 依赖或代码：

```bash
docker compose build app
docker compose up -d --force-recreate app celery-worker celery-beat
```

`app`、`celery-worker`、`celery-beat` 共用 `weibo-platform-app:latest`，三个都要重启，worker 才会用上新代码。

## 部署后检查

```bash
curl -sS http://127.0.0.1:5000/health
docker compose ps app celery-worker celery-beat
python -m pytest tests/smoke/test_smoke.py -v
```

再看几个关键信号：

- `weibo_event_bus_dead_letter_length`：应为 0，或只出现真实 handler 失败。
- `event_outbox` 的 pending 数量：目前没有指标，先直接查表：
  ```sql
  SELECT status, COUNT(*) FROM event_outbox GROUP BY status;
  ```
  正常应该是 `sent` 增长，`pending` 接近 0。
- `dirty:likes`：应逐步清空。
- `weibo_reconcile_diff_count{resource_type="like"}`：不应持续增长。
- Celery 队列不应长期积压；late ack 后重复投递会比以前多，任务必须幂等。

## 回滚

代码回滚：

```bash
git checkout <上一个稳定提交>
docker compose build app
docker compose up -d --force-recreate app celery-worker celery-beat
```

数据库回滚要谨慎。FIX-12 已经删除了软删点赞，`flask db downgrade` 只能恢复约束，不能恢复数据。需要完整回滚时，用上线前的备份恢复 MySQL。只回滚代码、不回滚迁移，通常也能运行，因为新表和列对旧代码是兼容的；但旧代码不会写 outbox，也不会使用 `notifications.event_id`。

## 仍未解决

- `like.created` 和点赞数变化没进 outbox，点赞通知仍是 best-effort。
- outbox 没有 pending/oldest-age 指标，没有最大重试和 sent 数据清理。
- SSE 没有 `Last-Event-ID`/replay。
- 全量对账、WAL、大 target 重建还没做。
- 评论详情缓存没有 `recently_modified` 强一致窗口。
- fanout 的粉丝列表仍读从库，刚关注的新粉丝可能短暂漏推。
