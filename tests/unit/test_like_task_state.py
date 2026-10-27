"""FIX-05: 点赞任务按 Redis 当前状态收敛，不按旧 action 盲执行。"""

from app.likes.cache import LikeCache
from app.likes.models import Like
from app.likes.repositories import like_repository
from app.posts.models import Post
from core.redis_cache import redis_cache
from tasks.like_tasks import async_like_to_do
from tests.unit.factories import PostFactory, UserFactory


def _active_like_count(db_session, user_id, post_id):
    return db_session.query(Like).filter(
        Like.user_id == user_id,
        Like.post_id == post_id,
        Like.deleted_at.is_(None),
    ).count()


def _set_redis_liked(user_id, post_id, liked=True):
    key = LikeCache._user_liked_key(user_id, 'post')
    if liked:
        redis_cache.sadd(key, str(post_id))
    else:
        redis_cache.srem(key, str(post_id))


def test_stale_create_converges_to_unliked(app, db_session, mock_redis):
    """Redis 已是未点赞，迟到的 create 任务不能把赞留下。"""
    with app.app_context():
        user = UserFactory()
        post = PostFactory(like_count=1)
        db_session.add(Like(user_id=user.id, post_id=post.id))
        db_session.commit()

        _set_redis_liked(user.id, post.id, liked=False)
        async_like_to_do(user.id, 'post', post.id, 'create', 'stale-create')

        db_session.expire_all()
        assert _active_like_count(db_session, user.id, post.id) == 0
        assert db_session.get(Post, post.id).like_count == 0


def test_stale_delete_converges_to_liked(app, db_session, mock_redis):
    """Redis 已是点赞，迟到的 delete 任务不能把赞删掉。"""
    with app.app_context():
        user = UserFactory()
        post = PostFactory(like_count=0)

        _set_redis_liked(user.id, post.id, liked=True)
        async_like_to_do(user.id, 'post', post.id, 'delete', 'stale-delete')

        db_session.expire_all()
        assert _active_like_count(db_session, user.id, post.id) == 1
        assert db_session.get(Post, post.id).like_count == 1


def test_delete_task_reads_master_not_replica(app, db_session, mock_redis, monkeypatch):
    """delete 任务必须从主库确认行存在，不能被从库延迟骗成 no-op。"""
    with app.app_context():
        user = UserFactory()
        post = PostFactory(like_count=1)
        db_session.add(Like(user_id=user.id, post_id=post.id))
        db_session.commit()

        _set_redis_liked(user.id, post.id, liked=False)

        original = like_repository.get_post_like

        def get_post_like(user_id, post_id, force_master=False):
            if not force_master:
                return None
            return original(user_id, post_id, force_master=True)

        monkeypatch.setattr(like_repository, 'get_post_like', get_post_like)

        async_like_to_do(user.id, 'post', post.id, 'delete', 'master-delete')

        db_session.expire_all()
        assert _active_like_count(db_session, user.id, post.id) == 0
        assert db_session.get(Post, post.id).like_count == 0
