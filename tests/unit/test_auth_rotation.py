import pytest
from flask_jwt_extended import decode_token

from app.common.exceptions import AuthenticationError
from app.users.services.auth_service import AuthService
from core.redis_cache import redis_cache


def _register(app, username):
    return AuthService.register_user(username, f'{username}@t.com', 'Str0ng!Pass')


def test_refresh_rotation_and_reuse_grace(app, db_session, mock_redis):
    """刷新会轮换出新 refresh；宽限期内重用旧 refresh 返回相同结果。"""
    with app.app_context():
        res = _register(app, 'rotuser')
        uid = res['user']['id']
        r1 = res['refresh_token']
        claims1 = decode_token(r1)

        out1 = AuthService.refresh_tokens(uid, claims1)
        r2 = out1.get('refresh_token')
        assert r2 and r2 != r1

        # 宽限窗口内重用 r1：应与首次轮换结果一致（不判为攻击）
        out2 = AuthService.refresh_tokens(uid, claims1)
        assert out2['refresh_token'] == r2


def test_refresh_reuse_beyond_grace_invalidates_family(app, db_session, mock_redis):
    """超过宽限窗口的重用 -> 判为复用，整族作废。"""
    with app.app_context():
        res = _register(app, 'reuseuser')
        uid = res['user']['id']
        r1 = res['refresh_token']
        claims1 = decode_token(r1)

        AuthService.refresh_tokens(uid, claims1)  # 轮换一次
        # 清掉宽限结果，模拟超过窗口
        redis_cache.delete(
            AuthService.REFRESH_GRACE_KEY.format(fid=claims1['fid'], jti=claims1['jti'])
        )
        with pytest.raises(AuthenticationError):
            AuthService.refresh_tokens(uid, claims1)


def test_refresh_degrades_when_redis_down(app, db_session, mock_redis, monkeypatch):
    """Redis 故障时降级：只发新 access，不轮换、不踢人。"""
    with app.app_context():
        res = _register(app, 'degradeuser')
        uid = res['user']['id']
        claims1 = decode_token(res['refresh_token'])

        def boom(*args, **kwargs):
            raise RuntimeError('redis down')

        monkeypatch.setattr('core.redis_cache.redis_cache.eval', boom)
        out = AuthService.refresh_tokens(uid, claims1)
        assert 'access_token' in out
        assert 'refresh_token' not in out


def test_change_password_bumps_token_version(app, db_session, mock_redis):
    """改密提升 token_version（旧 access/refresh 随之失效）。"""
    with app.app_context():
        res = _register(app, 'cwuser')
        uid = res['user']['id']
        key = AuthService.AUTH_VER_KEY.format(uid=uid)
        before = int(redis_cache.get(key, for_write=True) or 0)

        AuthService.change_password(uid, 'Str0ng!Pass', 'NewStr0ng!1')

        after = int(redis_cache.get(key, for_write=True) or 0)
        assert after == before + 1
