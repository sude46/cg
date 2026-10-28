# Database Optimization Design

## 1. Index Strategy

### Current Composite Indexes (✓ Good)

| Table | Index | Columns | Coverage |
|-------|-------|---------|----------|
| posts | `idx_post_published_created` | `(is_published, deleted_at, created_at)` | Feed listing |
| posts | `idx_post_hot` | `(is_published, deleted_at, like_count)` | Hot ranking |
| posts | `idx_post_user_created` | `(is_published, deleted_at, user_id)` | User feed |
| comments | `idx_comment_post_created` | `(post_id, deleted_at, created_at)` | Comment list |
| notifications | `idx_notification_user_read_created` | `(user_id, deleted_at, is_read, created_at)` | Unread query |
| follows | `idx_follower_created` | `(follower_id, deleted_at, created_at)` | Following list |
| follows | `idx_followed_created` | `(followed_id, deleted_at, created_at)` | Follower list |

### Missing Indexes (✗ Add)

**Priority: High**

1. **`likes`** for active lookup and duplicate prevention:
   ```sql
   UNIQUE uq_like_user_post (user_id, post_id)
   UNIQUE uq_like_user_comment (user_id, comment_id)
   ```
   Likes are hard-deleted. Do not include `deleted_at` in the unique key: MySQL treats multiple NULLs as distinct, so the old `(user_id, post_id, deleted_at)` constraint did not prevent duplicate active rows. `likes.deleted_at` is kept for compatibility but is no longer used by the like path.

2. **`notifications`** for `mark_all_as_read` bulk update:
   ```sql
   INDEX idx_notification_user_read (user_id, is_read, deleted_at)
   ```
   The existing composite includes `created_at` which is unnecessary for the UPDATE filter.

**Priority: Medium**

3. **`password_histories`** for password reuse check:
   ```sql
   INDEX idx_password_history_user_created (user_id, created_at DESC)
   ```
   Used by `check_password_reuse` (limit N recent records).

4. **`likes`** for `count_likes_for_comment` / `count_likes_for_post`:
   ```sql
   INDEX idx_like_target (post_id)      -- covers post counts
   INDEX idx_like_comment (comment_id)  -- covers comment counts
   ```
   The count queries filter `deleted_at IS NULL` only for legacy data; likes are now hard-deleted.

### Index Maintenance

- Use `pt-duplicate-key-checker` (Percona Toolkit) to detect redundant indexes (e.g., `index_post_created` on `(user_id, created_at)` overlaps with `idx_post_user_created` on `(is_published, deleted_at, user_id)` — evaluate if former can be dropped).
- Monitor unused indexes via `performance_schema.table_io_waits_summary_by_index_usage`.

## 2. Query Optimization

### Pagination — Migrate to Keyset for Large Offset

Current: `OFFSET/LIMIT` in `paginate()` — degrades at high offset.

**Action**: Use `keyset_paginate()` (already implemented in `app/common/database.py`) for:
- Post feeds (cache first page, keyset beyond)
- Notification lists (keyset on `(created_at, id)`)
- Like lists (keyset on `(id)`)

**Migration**: Start with endpoints that regularly hit page > 100.

### Batch Loading — Already Implemented ✓

- `LikeRepository.get_liked_post_ids(post_ids)` — batch check for N+1 prevention
- `joinedload(Post.author)` / `selectinload(Like.user)` — eager loading on all list queries
- `NotificationCache.preload_unread_counts(user_ids)` — preload in service layer

**Remaining Gap**: `CommentService.get_comments_by_post_id` loads comments then accesses `comment.author` — confirm `joinedload(Comment.author)` is applied (verified: yes).

### Covering Index for Feed Queries

The feed query on `posts`:
```sql
SELECT id, content, image_url, user_id, like_count, comment_count, created_at
FROM posts
WHERE is_published = 1 AND deleted_at IS NULL
ORDER BY created_at DESC
LIMIT 20;
```
The index `idx_post_published_created(is_published, deleted_at, created_at)` covers the WHERE + ORDER BY but requires 7 extra lookups per row.

**Action**: Add a **covering index** for feed:
```sql
INDEX idx_post_feed_covering (is_published, deleted_at, created_at, id, user_id, like_count, comment_count)
```
Reduces InnoDB buffer pool traffic by ~60% for feed queries.

## 3. Schema Optimization

### Column Type Audit

| Table | Column | Current Type | Suggestion | Reason |
|-------|--------|-------------|------------|--------|
| posts | `content` | `Text` | Keep | Adequate |
| posts | `image_url` | `String(500)` | `VARCHAR(500)` | InnoDB handles both same; no change |
| likes | `post_id` | `Integer, nullable` | `NOT NULL` with `CHECK` | Schema enforces exactly one target; `post_id` should be `NOT NULL` when `comment_id IS NULL` but MySQL CHECK is not enforced without `sql_require_primary_key`. Keep nullable with application validation. |
| users | `login_fail_count` | `Integer` | Migrate to Redis (done in `account_service.py`) | Reduces unnecessary writes on master |
| users | `lock_until` | `DateTime, nullable` | Migrate to Redis (done in `account_service.py`) | Reduces unnecessary writes on master |

### Soft Delete — Unify Strategy

Current: Some models use `deleted_at` (DateTime), the `SoftDeleteQuery` filters `is_deleted` (Boolean).

**Issue**: `SoftDeleteQuery` in `core/database.py` checks `is_deleted`, but all models use `deleted_at IS NULL`. The global filter does not apply.

**Action**: Either:
1. Add `is_deleted` generated column (`deleted_at IS NOT NULL`) for global SoftDeleteQuery compatibility, or
2. Remove SoftDeleteQuery (repositories already filter `deleted_at.is_(None)` explicitly).

**Recommendation**: Option 2 — remove SoftDeleteQuery to avoid confusion. Repository-level filtering is explicit and testable.

Likes are the exception: they are hard-deleted, and `likes.deleted_at` is no longer used. The column remains only so existing databases do not need an immediate drop.

### Optimistic Locking — Evaluate Usage

Post and Comment have `version_id` with `__mapper_args__={'version_id_col': version_id}`.

**Current usage**: Updates use `update()` construct (bypasses ORM), so version_id is never checked. The locking provides **zero benefit** and wastes a column + UPDATE SET version_id.

**Action**: Either:
- Remove `version_id` from Post/Comment, or
- Route counter updates through ORM object load + save (worse for concurrency).

**Recommendation**: Remove `version_id` — counter updates go through `db.session.execute(update(...))` which does not check version_id, making it dead weight.

## 4. Connection Pool Tuning

### Current Settings

```
Pool size: 10
Max overflow: 20
Pool pre-ping: True
Pool recycle: 3600s (1 hour)
```

### Recommendation for Production (4 core / 16GB app server)

| Parameter | Current | Recommended | Rationale |
|-----------|---------|-------------|-----------|
| pool_size | 10 | 20 | Handle peak concurrency from gunicorn workers (4 workers × 5 conns each) |
| max_overflow | 20 | 30 | Burst buffer during traffic spikes |
| pool_recycle | 3600 | 1800 | Shorter recycle prevents `wait_timeout` disconnects (MySQL default 28800s, but safer with 30min) |
| pool_timeout | unset (default) | 5000ms | Fail fast if pool exhausted; 5s timeout before `QueuePool` error |
| pool_pre_ping | True | True | Keep; detects dead connections before use |

### Replica Pool

| Parameter | Current | Recommended |
|-----------|---------|-------------|
| pool_size | 5 (hardcoded in db_router.py) | Make configurable via `SQLALCHEMY_ENGINE_OPTIONS_REPLICA` |
| max_overflow | 10 | 20 |

## 5. Replication Architecture

### Current
- 1 Master (writes) + 1 Replica (reads, round-robin)
- GTID-based replication
- `_read_session()` routes all reads to replica
- `force_master=True` for critical reads

### Recommendations

**Semi-Sync Replication**
Enable `rpl_semi_sync_master_enabled=1` and `rpl_semi_sync_slave_enabled=1` to reduce data loss risk during master failover.

**Replica Lag Monitoring**
- Add `SHOW SLAVE STATUS` health check in `MasterSlaveRouter`
- Log `Seconds_Behind_Master` every 30s
- Auto-route to master if lag > 10s

**Read-after-Write Consistency**
Mark `force_master=True` for:
- `get_by_id` after `create_comment` / `create_post` — verified (Service layer calls `get_by_id(force_master=True)` after write)
- User profile after registration — verified (`auth_service.py`)

**Missing**: After `mark_all_as_read`, the next `count_unread` may read stale replica. Add `force_master` parameter to `count_unread` or invalidate notification unread cache.

## 6. Counter Strategy

### Current Design (✓ Good)
- Denormalized counters on Post (`like_count`, `comment_count`) and User (`following_count`, `follower_count`)
- Atomic `UPDATE ... SET count = count + 1` — no race condition
- Periodic reconciliation via Celery tasks (like_reconcile, post_reconcile, etc.)

### Refinements

**Batch decrement when deleting a post**

Deleting a post hard-deletes its likes and decrements `like_count` in the same transaction. Since likes are hard-deleted, the count query should not filter likes by `deleted_at`:

```sql
UPDATE posts SET like_count = like_count - (
    SELECT COUNT(*) FROM likes WHERE post_id = ?
) WHERE id = ?;
```

If the likes are deleted first, do the count before the delete or keep the count in the same transaction.

**Counter Reconciliation SLO**
| Task | Schedule | Tolerance | Action if Exceeds |
|------|----------|-----------|-------------------|
| like_reconcile | every 5min | ±5 | Correct + alert |
| post_reconcile | every 30min | ±20 | Alert only |
| hot_comment_reconcile | every 15min | ±3 | Correct |

## 7. Partitioning & Archival

### Recommendation: No Partitioning for Current Scale

The largest table is `likes` (polymorphic, high write throughput). Partitioning by `user_id % 16` or by `created_at` month adds complexity without tooling support in the current ORM.

**Alternative**: Use **application-level sharding** in the cache layer (Cache-Aside) and keep DB as single-node with proper indexes.

### Archival Strategy for `password_histories`

- Keep last 10 records per user; archive older records to `password_histories_archive` monthly.
- Implement in Celery task: `SELECT user_id, COUNT(*) ... GROUP BY user_id HAVING COUNT(*) > 10` → move excess to archive.

### Archival for `notifications`

- Notifications older than 90 days: move to `notifications_archive` table.
- Unread notifications: exempt from archival until read.
- Add `archived` column or separate table.

## 8. Slow Query Monitoring

### Add to `MasterSlaveRouter`

```python
@db.event.listens_for(db.engine, 'before_cursor_execute')
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info['query_start_time'] = time.time()

@db.event.listens_for(db.engine, 'after_cursor_execute')
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - conn.info['query_start_time']
    if total > 1.0:
        logger.warning(f'Slow query ({total:.2f}s): {statement[:200]}')
```

This logs all queries > 1s without requiring MySQL slow query log parsing.

### Recommended `long_query_time`

Set `long_query_time = 0.5` in MySQL config (down from default 10.0).

## 9. Migration Plan

### Phase 1 (Immediate — this round)
- Add missing indexes (likes bulk check, notifications mark_all_read, password_histories)
- Remove `version_id` from Post and Comment models
- Remove `SoftDeleteQuery` global filter (redundant with repository filtering)
- Add `force_master` parameter to `NotificationRepository.count_unread`

### Phase 2 (Next sprint)
- Migrate feed queries to covering index
- Enable semi-sync replication
- Add slow query event listeners
- Implement notification archival

### Phase 3 (Backlog)
- Batch decrement for cascade soft-delete
- Connection pool tuning per environment
- Replica lag monitoring with auto-fallback

## 10. Key Metrics to Monitor

| Metric | Target | Alert |
|--------|--------|-------|
| Query latency (p99) | < 200ms | > 1s |
| Connection pool utilization | < 70% | > 90% |
| Replica lag | < 2s | > 10s |
| Slow queries (> 1s) | 0 | > 5/min |
| Index miss ratio (Handler_read_rnd_next / Handler_read_rnd) | < 10% | > 30% |
| Lock wait timeout rate | < 0.1% | > 1% |
