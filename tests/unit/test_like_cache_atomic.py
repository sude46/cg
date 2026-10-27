"""FIX-11: 点赞 Lua 必须原子覆盖 user/target/count/dirty 全部 key。"""

from app.likes.cache import LikeCache
from core.redis_cache import redis_cache


def test_add_like_atomic_when_pipeline_unavailable(app, mock_redis, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('pipeline down')

    monkeypatch.setattr(redis_cache, 'pipeline', boom)

    with app.app_context():
        assert LikeCache.add_like(1, 100, 'post') is True

        assert LikeCache.is_liked(1, 100, 'post') is True
        assert redis_cache.sismember('user:1:liked_posts', '100', for_write=True)
        assert redis_cache.sismember('post:100:likers', '1', for_write=True)
        assert LikeCache.get_like_count(100, 'post') == 1
        assert redis_cache.exists('post:100:like_count:dirty', for_write=True) == 1
        assert 'post:100' in redis_cache.smembers('dirty:likes', for_write=True)


def test_is_liked_missing_key_returns_none(app, mock_redis):
    with app.app_context():
        assert LikeCache.is_liked(1, 100, 'post') is None


def test_remove_like_already_absent_is_success(app, mock_redis):
    with app.app_context():
        assert LikeCache.remove_like(1, 100, 'post') is True


def test_add_like_initializes_missing_count(app, mock_redis):
    with app.app_context():
        assert LikeCache.add_like(1, 100, 'post', initial_count=5) is True
        # likers 集合只有本次用户，完整性校验会返回 None；原始计数必须是 6 而不是 1
        assert LikeCache.get_like_count_raw(100, 'post') == 6


def test_get_like_count_returns_none_on_mismatch(app, mock_redis):
    with app.app_context():
        redis_cache.set('post:100:like_count', 5, expire=60, for_write=True)
        redis_cache.sadd('post:100:likers', '1', '2')

        assert LikeCache.get_like_count(100, 'post') is None


def test_remove_like_initializes_missing_count(app, mock_redis):
    with app.app_context():
        redis_cache.sadd('post:100:likers', '1')

        assert LikeCache.remove_like(1, 100, 'post', initial_count=5) is True
        assert int(redis_cache.get('post:100:like_count', for_write=True)) == 4
