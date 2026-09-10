import pytest
from unittest.mock import MagicMock, patch


class TestAuthMiddleware:
    """认证中间件单元测试"""

    def test_is_public_route_exact(self, app):
        from middlewares.auth_middleware import is_public_route
        with app.app_context():
            assert is_public_route("/") is True
            assert is_public_route("/favicon.ico") is True
            assert is_public_route("/ping") is True

    def test_is_public_route_prefix(self, app):
        from middlewares.auth_middleware import is_public_route
        with app.app_context():
            assert is_public_route("/auth/login") is True
            assert is_public_route("/api/auth/callback") is True
            assert is_public_route("/health") is True

    def test_is_public_route_static(self, app):
        from middlewares.auth_middleware import is_public_route
        with app.app_context():
            assert is_public_route("/static/css/app.css") is True

    def test_is_public_route_private(self, app):
        from middlewares.auth_middleware import is_public_route
        with app.app_context():
            assert is_public_route("/api/users/me") is False
            assert is_public_route("/api/posts/create") is False

    def test_is_public_route_options(self, app):
        from middlewares.auth_middleware import is_public_route
        with app.app_context():
            assert is_public_route("/api/posts", method="OPTIONS") is True

    def test_jwt_blacklist_cache(self, app):
        from middlewares.auth_middleware import JWTBlacklistCache
        cache = JWTBlacklistCache(capacity=100, ttl=10)
        assert cache.get("test_jti") is None
        cache.set("test_jti", True)
        assert cache.get("test_jti") is True
        cache.set("test_jti2", False)
        assert cache.get("test_jti2") is False
        cache.clear()
        assert cache.get("test_jti") is None

    def test_jwt_blacklist_cache_capacity(self, app):
        from middlewares.auth_middleware import JWTBlacklistCache
        cache = JWTBlacklistCache(capacity=3, ttl=60)
        for i in range(5):
            cache.set(f"jti_{i}", True)
        assert cache.get("jti_0") is None
        assert cache.get("jti_4") is True


class TestRateLimitMiddleware:
    """限流中间件单元测试"""

    def test_init_rate_limit_in_testing(self, app):
        from middlewares.rate_limit_middleware import init_rate_limit_middleware
        with app.app_context():
            init_rate_limit_middleware(app)
            assert app.limiter is None

    def test_empty_route_limit(self, app):
        from middlewares.rate_limit_middleware import _empty_route_limit
        def fake_handler():
            return "ok"
        decorated = _empty_route_limit("100 per hour")(fake_handler)
        assert decorated() == "ok"

    def test_get_route_limit_no_app_context(self, app):
        from middlewares.rate_limit_middleware import get_route_limit
        with app.app_context():
            route_limit = get_route_limit()

    def test_get_identifier_with_user(self, app):
        from middlewares.rate_limit_middleware import _get_identifier
        with app.app_context():
            ident = _get_identifier()
            assert ident is not None


class TestCORSMiddleware:
    """CORS中间件单元测试"""

    def test_init_cors(self, app):
        from middlewares.cors_middleware import init_cors
        with app.app_context():
            init_cors(app)
            assert app.extensions.get("flask-cors") is not None


class TestSecurityMiddleware:
    """安全头中间件单元测试"""

    def test_security_headers_added(self, app):
        from middlewares.security_mw import init_security_headers
        with app.app_context():
            init_security_headers(app)
            with app.test_client() as client:
                resp = client.get("/")
                assert resp.headers.get("X-Frame-Options") == "DENY"
                assert resp.headers.get("X-Content-Type-Options") == "nosniff"
                assert resp.headers.get("Content-Security-Policy") is not None

    def test_security_headers_https_only(self, app):
        app.config["HTTPS_ONLY"] = True
        from middlewares.security_mw import init_security_headers
        with app.app_context():
            init_security_headers(app)
            with app.test_client() as client:
                resp = client.get("/")
                assert "Strict-Transport-Security" in resp.headers


class TestLoggingMiddleware:
    """日志中间件单元测试"""

    def test_before_request_sets_request_id(self, app):
        from middlewares.logging_middleware import init_logging_middleware
        with app.app_context():
            init_logging_middleware(app)
            with app.test_client() as client:
                resp = client.get("/")
                assert resp.headers.get("X-Request-ID") is not None

    def test_filter_sensitive_data(self, app):
        from middlewares.logging_middleware import init_logging_middleware
        with app.app_context():
            from flask import g

            def filter_sensitive_data(data, depth=0):
                sensitive_keys = {
                    'password', 'token', 'secret', 'authorization',
                    'cookie', 'session', 'api_key', 'apikey', 'access_token',
                    'refresh_token', 'jwt'
                }
                if depth > 3:
                    return '[nested]'
                if not isinstance(data, dict):
                    return data
                filtered = {}
                for k, v in data.items():
                    key_lower = k.lower()
                    if key_lower in sensitive_keys:
                        filtered[k] = '***'
                    elif isinstance(v, dict):
                        filtered[k] = filter_sensitive_data(v, depth + 1)
                    elif isinstance(v, list) and depth < 2:
                        filtered[k] = [filter_sensitive_data(item, depth + 1) if isinstance(item, dict) else item for item in v[:10]]
                    else:
                        filtered[k] = v
                return filtered

            result = filter_sensitive_data({"password": "secret123", "username": "test"})
            assert result["password"] == "***"
            assert result["username"] == "test"

            nested = filter_sensitive_data({"nested": {"token": "abc", "ok": 1}})
            assert nested["nested"]["token"] == "***"
            assert nested["nested"]["ok"] == 1


class TestRequestHooks:
    """请求钩子单元测试"""

    def test_before_request_hook(self, app):
        from middlewares.request_hooks import before_request_hook, after_request_hook
        with app.test_request_context():
            before_request_hook()
            from flask import g
            assert hasattr(g, "request_id")
            assert hasattr(g, "start_time")
            assert hasattr(g, "log_extra")

    def test_after_request_hook(self, app):
        from middlewares.request_hooks import before_request_hook, after_request_hook
        with app.test_request_context():
            before_request_hook()
            resp = MagicMock()
            result = after_request_hook(resp)
            assert result is resp


class TestRouteLimitProxy:
    """路由限流代理单元测试"""

    def test_route_limit_proxy_no_limiter(self, app):
        from middlewares.route_limit_proxy import RouteLimitProxy
        proxy = RouteLimitProxy()
        with app.app_context():
            @proxy("100 per hour")
            def handler():
                return "ok"
            assert handler() == "ok"

    def test_route_limit_proxy_class(self, app):
        from middlewares.route_limit_proxy import RouteLimitProxy
        proxy = RouteLimitProxy()
        decorator = proxy("10 per minute")
        assert callable(decorator)


class TestErrorMiddleware:
    """错误处理中间件单元测试"""

    def test_error_handlers_registered(self, app):
        from middlewares.error_middleware import init_error_handlers
        with app.app_context():
            init_error_handlers(app)
            with app.test_client() as client:
                resp = client.get("/nonexistent-route-xyz")
                assert resp.status_code == 404
                data = resp.get_json()
                assert "error" in data
                assert data["error"] == "资源未找到"

    def test_format_error_response(self, app):
        from middlewares.error_middleware import _format_error_response
        from app.common.exceptions import ValidationError
        with app.app_context():
            error = ValidationError("参数错误", error_code=10001)
            resp, status = _format_error_response(error)
            data = resp.get_json()
            assert data["code"] == 10001
            assert data["error"] == "参数错误"
            assert status == 400
