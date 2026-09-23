#!/usr/bin/env python3
"""清理开发环境里的测试数据。

跑完 smoke / E2E 后执行一次，恢复干净状态：
- 软删测试用户（用户名以 smoke/sse/probe 开头，可用 --keep 指定保留）的帖子（走 PostService.delete_post，联动 ES/缓存/Feed/热榜）
- 软删这些测试用户
- 软删涉及测试用户的通知（作为接收方或触发方）
- 删除测试用户的点赞、软删关注关系
- 清除 hot:searches 里的测试关键词（test/smoke 等）
- 清空 hot:posts:* 榜单（下轮 calculate-hot-posts 会按真实数据重建）

在 app 容器内运行（需要 DB/Redis 连接）：
    docker exec -i weibo-app python scripts/cleanup_dev_data.py
    docker exec -i weibo-app python scripts/cleanup_dev_data.py --keep zenith --keep admin
"""
import argparse
import logging
import os
import sys
import time

# 允许从任意目录直接运行本脚本
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import or_

from app import create_app
from app.chats.models import Conversation, ConversationUser, Message
from app.common.database import utcnow
from app.follows.models import Follow
from app.likes.models import Like
from app.notifications.cache import NotificationCache
from app.notifications.models import Notification
from app.posts.models import Post
from app.posts.services import PostService
from app.users.cache import UserCache
from app.users.models import User
from app.users.repositories import user_repository
from core.database import db
from core.redis_cache import redis_cache

logger = logging.getLogger(__name__)

TEST_PREFIXES = ('smoke', 'sse', 'probe')
DEFAULT_KEEP = ('zenith',)
HOT_SEARCH_BLOCK = ('test', 'smoke')
HOT_POST_KEYS = ('hot:posts:daily', 'hot:posts:weekly')


def _is_test_user(user: User, keep: set[str]) -> bool:
    if user.username.lower() in keep:
        return False
    return any(user.username.lower().startswith(p) for p in TEST_PREFIXES)


def _clean_hot_searches() -> int:
    removed = 0
    for raw in redis_cache.zrevrange('hot:searches', 0, -1) or []:
        keyword = raw.decode() if isinstance(raw, bytes) else str(raw)
        low = keyword.lower()
        if low in HOT_SEARCH_BLOCK or any(low.startswith(p) for p in TEST_PREFIXES):
            redis_cache.zrem('hot:searches', keyword)
            removed += 1
    return removed


def run(keep: set[str]) -> None:
    app = create_app()
    with app.app_context():
        test_users = [
            u for u in db.session.query(User).filter(User.deleted_at.is_(None)).all()
            if _is_test_user(u, keep)
        ]
        if not test_users:
            print('没有匹配的测试用户')
        test_ids = [u.id for u in test_users]
        print(f'测试用户 {len(test_users)} 个: {[u.username for u in test_users]}')

        # 1. 删除测试用户的帖子（正规服务，联动 ES/缓存/Feed/热榜）
        deleted_posts = 0
        for user in test_users:
            posts = db.session.query(Post).filter(
                Post.user_id == user.id,
                Post.deleted_at.is_(None),
            ).all()
            for post in posts:
                try:
                    PostService.delete_post(post.id, user.id)
                    deleted_posts += 1
                except Exception as e:
                    print(f'  删帖失败 post={post.id}: {e}')

        # 2. 处理涉及测试用户的通知（软删），记录受影响的真实接收者
        affected_recipients = set()
        if test_ids:
            rows = db.session.query(Notification).filter(
                or_(Notification.user_id.in_(test_ids), Notification.actor_id.in_(test_ids)),
                Notification.deleted_at.is_(None),
            ).all()
            for n in rows:
                if n.user_id not in test_ids:
                    affected_recipients.add(n.user_id)
                n.deleted_at = utcnow()

            # 3. 测试用户的点赞（硬删，与软删帖一致）
            db.session.query(Like).filter(Like.user_id.in_(test_ids)).delete(synchronize_session=False)

            # 4. 涉及测试用户的关注关系（逐条软删，避免唯一约束撞车）
            follows = db.session.query(Follow).filter(
                or_(Follow.follower_id.in_(test_ids), Follow.followed_id.in_(test_ids)),
                Follow.deleted_at.is_(None),
            ).all()
            for f in follows:
                f.deleted_at = utcnow()

            # 4.5 私信：删除涉及测试用户的会话及其消息/参与者
            conv_ids = [
                c.id for c in db.session.query(Conversation.id).filter(or_(
                    Conversation.user_low_id.in_(test_ids),
                    Conversation.user_high_id.in_(test_ids),
                )).all()
            ]
            if conv_ids:
                db.session.query(Message).filter(
                    Message.conversation_id.in_(conv_ids)
                ).delete(synchronize_session=False)
                db.session.query(ConversationUser).filter(
                    ConversationUser.conversation_id.in_(conv_ids)
                ).delete(synchronize_session=False)
                db.session.query(Conversation).filter(
                    Conversation.id.in_(conv_ids)
                ).delete(synchronize_session=False)

            db.session.commit()
            print(f'清理通知 {len(rows)} 条、点赞、关注 {len(follows)} 条、私信会话 {len(conv_ids)} 个')

        # 5. 软删测试用户 + 清缓存
        for user in test_users:
            username, email, uid = user.username, user.email, user.id
            user_repository.soft_delete(user)
            db.session.commit()
            try:
                UserCache.invalidate(uid)
                UserCache.invalidate_by_username(username)
                UserCache.invalidate_by_email(email)
            except Exception as e:
                logger.warning('清用户缓存失败 %s: %s', uid, e)

        # 6. 清真实用户的未读缓存（其通知里可能有来自测试用户的）
        for uid in affected_recipients:
            try:
                NotificationCache.invalidate_unread(uid)
            except Exception as e:
                logger.warning('清未读缓存失败 %s: %s', uid, e)

        # 7. 清热搜关键词 + 清空热榜
        removed_keywords = _clean_hot_searches()
        for key in HOT_POST_KEYS:
            redis_cache.delete(key)

        print(f'已软删帖子 {deleted_posts} 条、用户 {len(test_users)} 个；'
              f'热搜关键词移除 {removed_keywords} 个；热榜键已清空')
        # 给事件总线一点时间消费 post.deleted（同步 ES/Feed）
        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description='清理开发环境测试数据')
    parser.add_argument('--keep', action='append', default=[],
                        help='要保留的用户名（可多次指定）')
    args = parser.parse_args()
    keep = {k.lower() for k in (list(DEFAULT_KEEP) + args.keep)}
    run(keep)


if __name__ == '__main__':
    main()
