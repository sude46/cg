class TestCacheProtection:
    """缓存防护机制的通用测试"""
    def test_cache_penetration_protection(self, app, mock_redis):
        """缓存穿透保护：None 值缓存"""
        from app.posts.cache import PostCache
        with app.app_context():
            PostCache.set(1, None)
            assert PostCache.get(1) is None

    def test_cache_avalanche_protection(self, app, mock_redis):
        """防雪崩：随机 TTL 偏移"""
        from core.redis_cache import RedisCache
        with app.app_context():
            redis_cache = RedisCache()
            redis_cache.set("test_key", "value", expire=300)
            ttl1 = redis_cache.ttl("test_key")
            redis_cache.set("test_key2", "value", expire=300)
            ttl2 = redis_cache.ttl("test_key2")
            assert abs(ttl1 - ttl2) <= 60

    def test_cache_breakdown_protection(self, app, mock_redis):
        """防击穿，分布式锁"""
        from core.redis_cache import RedisCache
        with app.app_context():
            redis_cache = RedisCache()
            call_count = 0

            def slow_loader():
                nonlocal call_count
                call_count += 1
                return "loaded"

            result = redis_cache.cache_through(
                "breakdown_test",
                slow_loader,
                expire=300
            )
            assert result == "loaded"
            assert call_count == 1
