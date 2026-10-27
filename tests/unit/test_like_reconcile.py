"""FIX-01: 点赞对账不能把 DB 大数覆盖成 Redis 小数。"""

from app.likes.models import Like
from app.posts.models import Post
from tests.unit.factories import PostFactory, UserFactory


def _seed_db_likes(db_session, post_id: int, count: int) -> None:
    users = [UserFactory() for _ in range(count)]
    db_session.add_all([Like(user_id=u.id, post_id=post_id) for u in users])
    db_session.commit()


def test_reconcile_does_not_shrink_db_count(app, db_session, mock_redis):
    """Redis 计数残缺（1）而 DB 有 5 条：应以 DB 重建 Redis，不能把 DB 改成 1。"""
    from app.likes.cache import LikeCache
    from core.redis_cache import redis_cache
    from tasks.like_reconcile import DIRTY_LIKES_KEY, reconcile_like_counts

    with app.app_context():
        post = PostFactory(like_count=5)
        _seed_db_likes(db_session, post.id, 5)

        # 模拟 Redis 被淘汰后只剩一次点赞的计数；dirty_key 不存在 => 没有在途任务
        LikeCache.set_like_count(post.id, 1, "post")
        redis_cache.sadd(DIRTY_LIKES_KEY, f"post:{post.id}")

        reconcile_like_counts()

        db_session.expire_all()
        assert db_session.get(Post, post.id).like_count == 5
        assert LikeCache.get_like_count(post.id, "post") == 5
        assert f"post:{post.id}" not in redis_cache.smembers(
            DIRTY_LIKES_KEY, for_write=True
        )


def test_reconcile_keeps_dirty_when_commit_fails(
    app, db_session, mock_redis, monkeypatch
):
    """DB 提交失败时不能提前清 dirty，否则差异永久失去重试机会。"""
    from app.likes.cache import LikeCache
    from core import db as core_db
    from core.redis_cache import redis_cache
    from tasks.like_reconcile import DIRTY_LIKES_KEY, reconcile_like_counts

    with app.app_context():
        post = PostFactory(like_count=3)
        _seed_db_likes(db_session, post.id, 3)

        # 让 Redis 看起来完整且比 DB 多：触发 Redis -> DB 的更新路径
        LikeCache.set_like_count(post.id, 5, "post")
        for member in range(5):
            redis_cache.sadd(f"post:{post.id}:likers", str(member))
        redis_cache.sadd(DIRTY_LIKES_KEY, f"post:{post.id}")

        def fail_commit():
            raise RuntimeError("commit boom")

        monkeypatch.setattr(core_db.session, "commit", fail_commit)

        reconcile_like_counts()

        db_session.expire_all()
        assert db_session.get(Post, post.id).like_count == 3
        assert f"post:{post.id}" in redis_cache.smembers(
            DIRTY_LIKES_KEY, for_write=True
        )
