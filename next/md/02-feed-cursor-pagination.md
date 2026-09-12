# 02 — Feed 改游标（cursor）分页（item 9）

## 为什么必须改

Feed 底层是 Redis ZSet（`feed:user:{uid}`，score=帖子时间）。用 `page/per_page` 翻页时，
高频新帖插入会导致 ZSet 整体前移，第 2 页 `ZREVRANGE start end` 的 rank 偏移错位 → **必漏必重**。
cursor 直接用上一页最后一条的 score，天然稳定。

---

## 1. 目标接口

`GET /feeds/timeline?limit=20&cursor=<float>`（Authorization 必填）

响应：

```json
{
  "code": 200,
  "data": {
    "items": [ { "id": 123, "created_at": "2026-09-11T07:30:00+00:00", ... } ],
    "next_cursor": 1757575800.123456,
    "has_more": true,
    "source": "cache"
  },
  "message": "获取时间线成功"
}
```

- 首页不传 `cursor`（等价 `max=+inf`）。
- `next_cursor`：本页返回的**最后一条 item 的 score**；无更多数据时为 `null`。
- 下一页传 `cursor=<next_cursor>`，后端用 `(cursor` **开区间**，避免重复。

---

## 2. Redis 层：新增 `ZREVRANGEBYSCORE`

`core/redis_cache.py` 目前只有 `zrevrange`（按 rank，第 172 行）。需新增：

```python
def zrevrangebyscore(self, key: str, max_score, min_score,
                     start: int = 0, num: int = None,
                     withscores: bool = False):
    """
    ZREVRANGEBYSCORE key max min [LIMIT start num] [WITHSCORES]
    max_score 可传 '+inf' / '(123.4'（开区间） / 123.4
    """
    conn = self.get_conn(for_write=False)   # 只读，走副本；注意 score 写路径仍走主
    return conn.zrevrangebyscore(
        key, max_score, min_score,
        start=start, num=num, withscores=withscores
    )
```

> 注意：写路径 `zadd` 必须 `for_write=True`（现有代码已是）。读路径走副本即可。
> 若封装类拿不到底层 `zrevrangebyscore`，在 `FeedCache` 里用 `redis_cache.get_conn(for_write=False)` 直取原生连接（项目里 `pull_feed` 已用 `redis_cache.exists/zcard` 这种直取法，见 `app/feeds/cache.py:120-128,279`）。

---

## 3. `FeedCache`：新增 cursor 拉取

`app/feeds/cache.py` 新增（保留旧 `pull_feed` 一段时间，或直接替换）：

```python
@classmethod
def pull_feed_by_cursor(cls, user_id: int, cursor: float | None, limit: int):
    """
    返回 (post_ids, next_cursor, has_more) 或 None(缓存未命中)
    - cursor=None 表示第一页
    - 开区间 '(cursor' 避免与上一页最后一条重复
    """
    key = cls._feed_key(user_id)
    empty_key = cls._empty_key(user_id)
    try:
        if redis_cache.exists(empty_key):
            return [], None, False
        if not redis_cache.exists(key):
            return None  # 未命中，交给 DB

        max_score = "+inf" if cursor is None else f"({float(cursor)}"
        # 多取 1 条判断 has_more
        rows = redis_cache.zrevrangebyscore(
            key, max_score, "-inf", start=0, num=limit + 1, withscores=True
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        if not rows:
            return [], None, False
        post_ids = [pid.decode() if isinstance(pid, bytes) else str(pid) for pid, _ in rows]
        next_cursor = float(rows[-1][1]) if has_more else None
        return post_ids, next_cursor, has_more
    except Exception as e:
        logger.error(f"用户{user_id}游标拉取时间线失败: {e}")
        return None
```

**score 精度坑**：现有写入用 `.timestamp()`（秒，float 有微秒），但 `posts.created_at` 存 MySQL `DATETIME(0)` 时会被截断到秒，同一秒多条帖子 score 相同。
开区间 `(cursor` 会把同秒的其它帖子一起跳过（漏）。两种加固方案（择一）：

1. **写 score 时放大到毫秒且拼 id 微偏移**（推荐，改动小）：score = `created_at_utc.timestamp()` 已足够，但同秒冲突仍在。改为在 `FeedCache.add_post_to_feed/push_to_followers` 用 `score = ts + (post_id % 1000) / 1_000_000`，保证同秒唯一且排序近似时间。
2. **复合游标**：`next_cursor = f"{score}:{last_id}"`，SQL/Redis 层遇到同分时再做一次 id 过滤。实现复杂，除非确实高频同秒。

本方案文档默认采用**方案 1**，并在 doc 里标注。同时修正 `app/feeds/handlers.py:13` 的时区问题（见 §6）。

---

## 4. `FeedService.get_timeline` 重构

`app/feeds/services.py:29-85` 改为：

```python
@classmethod
def get_timeline(cls, user_id: int, cursor: float | None = None, limit: int = 20):
    try:
        limit = min(max(1, limit), cls.MAX_PRE_PAGE)
        result = FeedCache.pull_feed_by_cursor(user_id, cursor, limit)

        if result is not None:
            cached_ids, next_cursor, has_more = result
            REDIS_HIT_RATE.labels(cache_type="feed").set(1)
            if not cached_ids:
                FEED_OPERATIONS.labels(action="timeline", result="success").inc()
                return {"items": [], "next_cursor": None, "has_more": False, "source": "empty"}
            posts = cls._get_posts_by_ids(cached_ids)
            FEED_OPERATIONS.labels(action="timeline", result="success").inc()
            return {
                "items": posts_schema.dump(posts),
                "next_cursor": next_cursor,
                "has_more": has_more,
                "source": "cache",
            }

        # 缓存未命中：DB 拉取（keyset）
        posts, has_more, next_cursor = FeedRepository.get_following_posts_cursor(
            user_id=user_id, cursor=cursor, limit=limit
        )
        REDIS_HIT_RATE.labels(cache_type="feed").set(0)
        if posts:
            cls._backfill_cache(user_id, posts)
        else:
            FeedCache.set_empty_cache(user_id)
        FEED_OPERATIONS.labels(action="timeline", result="success").inc()
        return {
            "items": posts_schema.dump(posts),
            "next_cursor": next_cursor,
            "has_more": has_more,
            "source": "db",
        }
    except Exception:
        FEED_OPERATIONS.labels(action="timeline", result="failed").inc()
        raise
```

同时 `refresh_user_feed`（`services.py:309`）里的 `get_timeline(user_id, page=1, ...)` 改为 `get_timeline(user_id, cursor=None, limit=cls.DEFAULT_PER_PAGE)`。

---

## 5. `FeedRepository`：新增 keyset 查询

`app/feeds/repository.py` 新增（保留旧 `get_following_posts` 或替换）：

```python
from datetime import UTC, datetime

@staticmethod
@monitor_db("select", "feeds")
def get_following_posts_cursor(user_id: int, cursor: float | None, limit: int):
    """keyset 分页：按 (created_at, id) 倒序，返回 (posts, has_more, next_cursor)"""
    session = FeedRepository._read_session()
    query = session.query(Post).join(
        Follow, Post.user_id == Follow.followed_id
    ).options(joinedload(Post.author)).filter(
        Follow.follower_id == user_id,
        Follow.deleted_at.is_(None),
        Post.deleted_at.is_(None),
        Post.is_published.is_(True),
    )
    if cursor is not None:
        cursor_dt = datetime.fromtimestamp(float(cursor), tz=UTC).replace(tzinfo=None)
        query = query.filter(Post.created_at < cursor_dt)   # 开区间

    rows = query.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        next_cursor = rows[-1].created_at.replace(tzinfo=UTC).timestamp()
    return rows, has_more, next_cursor
```

> `Post.created_at` 是 naive UTC，`datetime.fromtimestamp(ts, tz=UTC).replace(tzinfo=None)` 得到 naive UTC，比较正确。
> 复合排序 `(created_at desc, id desc)` 保证同秒稳定；但 cursor 只带时间戳，同秒仍可能漏——这就是 §3 要统一 score 精度的原因。

---

## 6. 顺带修：`app/feeds/handlers.py` 的 bug

该文件是新增（未 tracked），有两个问题：

```python
# 第 13 行：naive datetime.timestamp() 按本地时区解释，score 会偏移
created_at=datetime.fromisoformat(payload['created_at']).timestamp(),
# 应改为：
from datetime import UTC
dt = datetime.fromisoformat(payload["created_at"])
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=UTC)
created_at = dt.timestamp()

# 第 24 行：拼写错误，运行时 NameError
FeedServices.delete_post(...)   # → FeedService.delete_post(...)
```

（`payload['created_at']` 来自 `app/posts/services.py:74` 的 `post.created_at.isoformat()`，是 naive UTC 串。）

---

## 7. 路由层

`app/feeds/routes.py:43-62`：

```python
timeline_parser.add_argument("cursor", type=float, default=None, location="args",
                             help="上一页返回的 next_cursor；首页不传")
timeline_parser.add_argument("limit", type=int, default=20, location="args",
                             help="每页数量，默认20，最大100")

@api.route("/timeline")
class TimelineResource(Resource):
    @jwt_required()
    def get(self):
        args = timeline_parser.parse_args()
        result = FeedService.get_timeline(
            user_id=get_jwt_identity(),
            cursor=args["cursor"],
            limit=args["limit"],
        )
        return success_response(data=result, message="获取时间线成功"), 200
```

> 是否保留 `page/per_page`？前端无存量，**直接删掉**，避免两套并存。`feed_parser` 删除或只留兼容日志。

---

## 8. 验证

单测（`tests/unit/test_feeds.py`）新增 cursor 用例：

```python
# 伪代码
posts = [FeedService.publish_post(...) for 3 posts]  # 或直接构造 ZSet
p1 = FeedService.get_timeline(user.id, cursor=None, limit=2)
assert p1["has_more"] is True
assert p1["next_cursor"] is not None
p2 = FeedService.get_timeline(user.id, cursor=p1["next_cursor"], limit=2)
ids1 = {x["id"] for x in p1["items"]}
ids2 = {x["id"] for x in p2["items"]}
assert not (ids1 & ids2), "翻页不可重复"
```

冒烟：`tests/smoke/test_smoke.py:106` 增加：

```python
assert "next_cursor" in feed
```

---

## 9. 上线注意

- **双写过渡**：改动 `score` 精度后，老 ZSet 里是秒级 score，新写入是毫秒级，混在同一 key 中排序仍按数值，问题不大；但同秒去重逻辑会短暂不一致。建议发布时对活跃用户 key 执行一次 `DEL`（下次读走 DB 回填），或直接接受短暂不一致（TTL 7 天自然过期）。
- 大 V 拉模式不写 ZSet，直接走 DB keyset，天然正确。
- `MAX_FEED_SIZE=500` 裁剪仍生效；cursor 只影响读取。
