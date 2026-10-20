"""压测数据准备：批量创建 perf 用户 + 一个内容作者及其帖子，输出 access token。

在 app 容器内运行（走真实 DB/Redis，但不经过 HTTP 限流）：
    docker exec -i -e PYTHONPATH=/app weibo-app python - < tests/performance/seed_tokens.py

环境变量：
    PERF_USERS  并发用户数/ token 数（默认 40）
    PERF_POSTS  内容作者的种子帖数（默认 10）

stdout 会打印一行：PERF_TOKENS_JSON=[...]，供压测脚本读取。
用户名以 smoke_perf_ 开头，便于 scripts/cleanup_dev_data.py 清理。
"""
import json
import os
import uuid

from wsgi import app

N = int(os.getenv('PERF_USERS', '40'))
POSTS = int(os.getenv('PERF_POSTS', '10'))

with app.app_context():
    from app.follows.services import FollowService
    from app.posts.services import PostService
    from app.users.services import AuthService

    run = uuid.uuid4().hex[:6]

    author = AuthService.register_user(
        f'smoke_perf_author_{run}',
        f'smoke_pa_{run}@t.com',
        'Pass@w0rd!',
    )['user']

    for i in range(POSTS):
        PostService.create_post(author['id'], f'perf seed post {i}')

    tokens = []
    for i in range(N):
        reg = AuthService.register_user(
            f'smoke_perf_u{run}_{i}',
            f'smoke_pu{run}_{i}@t.com',
            'Pass@w0rd!',
        )
        # 关注内容作者：时间线首次读会从 DB 回填，后续命中缓存
        FollowService.follow_user(reg['user']['id'], author['id'])
        tokens.append(reg['access_token'])

    print('PERF_TOKENS_JSON=' + json.dumps(tokens))
