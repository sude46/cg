"""
冒烟测试（Smoke Test）：针对运行中的服务跑核心主链路。

与单元测试的区别：
- 单元测试 mock 所有依赖，本测试直连真实 MySQL/Redis/ES/Docker 服务
- 覆盖"系统能不能站起来"：登录->发帖->详情->评论->通知->点赞->关注->feed->搜索

运行前提：
    docker compose up -d app   # 服务已在 localhost:5000 运行

用法：
    python -m pytest tests/smoke/test_smoke.py -v
    SMOKE_BASE=http://localhost:5000 python -m pytest tests/smoke/test_smoke.py
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = __import__('os').getenv('SMOKE_BASE', 'http://localhost:5000')


def _request(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {'_raw': raw[:200]}


def _expect(method, path, token=None, body=None, codes=(200, 201)):
    code, data = _request(method, path, token=token, body=body)
    assert code in codes, f'{method} {path} -> {code}: {data}'
    return code, data


def _new_user(seq):
    """注册一个新用户，返回 (token, user_id)。时间戳用户名保证每次运行幂等。"""
    suffix = str(int(time.time() * 1000))[-8:]
    username = f'smoke{seq}{suffix}'
    email = f'{username}@test.com'
    password = 'Smoke@2026x'
    _expect('POST', '/users/register', body={
        'username': username, 'email': email, 'password': password,
    }, codes=(200, 201))
    code, data = _expect('POST', '/users/login', body={
        'username': username, 'password': password,
    })
    token = data['data']['access_token']
    user_id = data['data']['user_info']['id']
    return username, password, token, user_id


def test_full_core_chain():
    # 1. 注册两个用户
    _, p1, t1, uid1 = _new_user(1)
    _, _, t2, uid2 = _new_user(2)

    # 2. 用户1发帖
    code, data = _expect('POST', '/posts', token=t1,
                         body={'content': 'smoke test post'}, codes=(200, 201))
    post = data['data']
    pid = post['id']
    assert post['created_at'], '发帖返回缺少 created_at'

    # 3. 帖子详情（曾出现 isoformat 500 的地方）
    code, data = _expect('GET', f'/posts/{pid}', token=t1)
    detail = data['data']['post']
    assert detail['id'] == pid
    assert detail['created_at'], '详情缺少 created_at（可能是二次序列化 bug）'

    # 4. 用户2评论 -> 触发通知
    code, data = _expect('POST', '/comments', token=t2, codes=(200, 201),
                         body={'content': 'nice post', 'post_id': pid})
    assert data['data'].get('id'), '评论创建返回缺少 id'

    # 5. 用户1查通知（事件总线异步，重试几次）
    got_notification = False
    for _ in range(5):
        code, data = _expect('GET', '/notifications', token=t1)
        if (data['data'].get('notifications') or data['data'].get('items')):
            got_notification = True
            break
        time.sleep(1)
    assert got_notification, '评论后 5 秒内未收到通知（事件消费可能故障）'

    # 6. 用户2点赞
    code, data = _expect('POST', f'/likes/posts/{pid}/likes', token=t2, codes=(200, 201))

    # 7. 用户1关注用户2 -> 刷新 feed
    _expect('POST', '/follows/following', token=t1, body={'followed_id': uid2}, codes=(200, 201))
    _expect('POST', '/feeds/refresh', token=t1)

    # 8. 时间线（曾出现裸 ORM 序列化 500 的地方）
    code, data = _expect('GET', '/feeds/timeline', token=t1)
    feed = data['data']
    items = feed.get('items') or []
    assert isinstance(items, list), 'feed items 不是 list'
    assert 'next_cursor' in feed, 'feed 缺少 next_cursor'
    for it in items:
        assert isinstance(it, dict), f'feed 返回了未序列化的对象: {type(it)}'
        assert 'created_at' in it, 'feed 帖子缺少 created_at'

    # 9. 搜索（ES 可用时走 elasticsearch 引擎）
    q = urllib.parse.quote('smoke')
    code, data = _expect('GET', f'/posts/search?q={q}', token=t1)
    assert data['data'].get('items') is not None, '搜索返回缺少 items 字段'

    # 10. restx 端点的 405 也走统一错误契约（桥接 flask-restx）
    code, err = _expect('DELETE', '/users/login', codes=(405,))
    assert err.get('code') == 10009, f'405 业务码应为 10009: {err}'
    assert 'request_id' in err, f'405 缺少 request_id: {err}'

    # 11. 改密后旧 access 立即失效（token_version 提升）
    _expect('PUT', '/users/me/password', token=t1,
            body={'old_password': p1, 'new_password': 'Smoke@2026z'})
    code, _ = _request('GET', '/users/me', token=t1)
    assert code == 401, f'改密后旧 access 应 401，实际 {code}'

    print(f'SMOKE OK: 全链路通过 (user1={uid1}, user2={uid2}, post={pid})')
