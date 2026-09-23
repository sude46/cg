import logging

from sqlalchemy.exc import IntegrityError

from app.common import event_bus
from app.common.exceptions import (
    ConflictError,
    DatabaseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.feeds.cache import FeedCache
from app.users.repositories import user_repository
from app.users.schemas import public_user_schema
from core import db
from core.metrics import FOLLOW_OPERATIONS

from .cache import FollowCache
from .repositories import follow_repository
from .schemas import follow_response_schema

logger = logging.getLogger(__name__)


class FollowService:
    @staticmethod
    def follow_user(follower_id: int, followed_id: int):
        '''关注用户（分布式锁放并发重复关注+原子计数更新）'''
        if follower_id==followed_id:
            raise ValidationError('不能关注自己')
        if not FollowCache.acquire_lock(follower_id,followed_id):
            raise ConflictError('操作过于频繁，请稍后重试')
        try:
            follower=user_repository.get_by_id(follower_id)
            followed=user_repository.get_by_id(followed_id)
            if not follower or not getattr(follower,'is_active',True):
                raise ResourceNotFoundError('关注着用户不存在或已被禁用')
            if not followed or not getattr(followed,'is_active',True):
                raise ResourceNotFoundError('被关注者用户不存在或已被禁用')
            #主库+行锁校验是否已关注
            existing=follow_repository.get_relation(follower_id,followed_id,lock=1)
            if existing:
                raise ConflictError('已关注该用户')
             # 3. 创建关注关系（主库写）
            follow = follow_repository.create_follow(follower_id, followed_id)
            db.session.flush()
            user_repository.increment_follower_count(followed_id)
            user_repository.increment_following_count(follower_id)
            db.session.commit()

            # 5. 同步更新 Redis（失败不阻塞，清缓存兜底）
            if not FollowCache.add_relation(follower_id, followed_id):
                FollowCache.invalidate(follower_id)
                FollowCache.invalidate(followed_id)
            # 6. 清 Feed 时间线缓存（关注后时间线内容变了）
            FeedCache.invalidate_feed(follower_id)
            logger.info(f'用户{follower_id}关注了用户{followed_id}')
            FOLLOW_OPERATIONS.labels(action='follow', result='success').inc()
            # 通知模块订阅：给被关注者建通知（含 SSE 实时推送）
            try:
                event_bus.publish('follow.created', {
                    'user_id': followed_id,
                    'actor_id': follower_id,
                    'type': 'follow',
                })
            except Exception as e:
                logger.warning(f'发布关注事件失败（不影响主流程）：{e}')
            return {'message': '关注成功', 'follow': follow_response_schema.dump(follow)}

        except IntegrityError:
            db.session.rollback()
            logger.warning(f'用户{follower_id}重复关注用户{followed_id}')
            FOLLOW_OPERATIONS.labels(action='follow', result='duplicate').inc()
            raise ConflictError('已关注用户')

        except Exception as e:
            db.session.rollback()
            logger.error('关注用户失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, ValidationError, ConflictError)):
                raise
            FOLLOW_OPERATIONS.labels(action='follow', result='error').inc()
            raise DatabaseError('关注操作失败,请稍后重试')
        finally:
            # 释放锁调 FollowCache
            FollowCache.release_lock(follower_id, followed_id)

    @staticmethod
    def unfollow_user(follower_id: int, followed_id: int):
        '''取消关注'''
        if not FollowCache.acquire_lock(follower_id,followed_id):
            raise ConflictError('操作过于频繁，请稍后重试')
        try:
            follow = follow_repository.get_relation(follower_id, followed_id,lock=True)
            if not follow:
                raise ResourceNotFoundError('未关注该用户')
            follow_repository.delete_follow(follow)
            db.session.flush()
            user_repository.decrement_follower_count(followed_id)
            user_repository.decrement_following_count(follower_id)

            db.session.commit()

            # 同步清 Redis
            if not FollowCache.remove_relation(follower_id, followed_id):
                FollowCache.invalidate(follower_id)
                FollowCache.invalidate(followed_id)

            # 清 Feed 缓存
            FeedCache.invalidate_feed(follower_id)
            logger.info(f'用户{follower_id}取消关注用户{followed_id}')
            FOLLOW_OPERATIONS.labels(action='unfollow', result='success').inc()
            return {'message': '取消关注成功'}


        except Exception as e:
            db.session.rollback()
            logger.error('取消关注失败: %s', e)
            if isinstance(e, ResourceNotFoundError):
                raise
            FOLLOW_OPERATIONS.labels(action='unfollow', result='error').inc()
            raise DatabaseError('取消关注操作失败,请稍后重试')
        finally:
            FollowCache.release_lock(follower_id, followed_id)

    @staticmethod
    def _annotate_viewer_relation(items: list, viewer_id: int = None):
        '''给用户列表补 is_following（我是否关注他）/ is_mutual（互关），供前端按钮显示。'''
        if not viewer_id:
            for it in items:
                it['is_following'] = False
                it['is_mutual'] = False
            return
        following_ids = set(follow_repository.get_following_ids(viewer_id))
        follower_ids = set(follow_repository.get_follower_ids(viewer_id))
        for it in items:
            uid = it.get('id')
            is_following = uid in following_ids
            it['is_following'] = is_following
            it['is_mutual'] = is_following and (uid in follower_ids)

    @staticmethod
    def get_following(user_id: int, page: int = 1, per_page: int = 20, viewer_id: int = None):
        try:
            user = user_repository.get_by_id(user_id)
            if not user or not getattr(user, 'is_active', True):
                raise ResourceNotFoundError('用户不存在或已被禁用')

            result = follow_repository.list_following(user_id, page=page, per_page=per_page)
            users = [f.followed for f in result.get('items', []) if f.followed]
            items = public_user_schema.dump(users, many=True)
            FollowService._annotate_viewer_relation(items, viewer_id)
            FOLLOW_OPERATIONS.labels(action='list_following', result='success').inc()
            return {'items': items, 'pagination': result.get('pagination', {})}
        except Exception as e:
            logger.error('获取关注列表失败: %s', e)
            if isinstance(e, ResourceNotFoundError):
                raise
            raise DatabaseError('获取关注列表失败，请稍后重试')

    @staticmethod
    def get_followers(user_id: int, page: int = 1, per_page: int = 20, viewer_id: int = None):
        try:
            user = user_repository.get_by_id(user_id)
            if not user or not getattr(user, 'is_active', True):
                raise ResourceNotFoundError('用户不存在或已被禁用')

            result = follow_repository.list_followers(user_id, page=page, per_page=per_page)
            users = [f.follower for f in result.get('items', []) if f.follower]
            items = public_user_schema.dump(users, many=True)
            FollowService._annotate_viewer_relation(items, viewer_id)
            FOLLOW_OPERATIONS.labels(action='list_followers', result='success').inc()
            return {'items': items, 'pagination': result.get('pagination', {})}
        except Exception as e:
            logger.error('获取粉丝列表失败: %s', e)
            if isinstance(e, ResourceNotFoundError):
                raise
            raise DatabaseError('获取列表失败，请稍后重试')

    @staticmethod
    def get_mutual_follows(user_id: int, page: int = 1, per_page: int = 20):
        user = user_repository.get_by_id(user_id)
        if not user or not getattr(user, 'is_active', True):
            raise ResourceNotFoundError('目标用户不存在或已被禁用')

        result = follow_repository.get_mutual_follows(
            user_id=user_id,
            page=page,
            per_page=per_page
        )
        # 互关列表返回脱敏用户对象
        users = public_user_schema.dump(result.get('items', []), many=True)
        FOLLOW_OPERATIONS.labels(action='mutual', result='success').inc()
        return {'items': users, 'pagination': result.get('pagination', {})}

    @staticmethod
    def is_following(follower_id: int, followed_id: int) -> bool:
        cached = FollowCache.is_following(follower_id,followed_id)
        if cached is not None:
            return cached
        #miss / 故障 → 查 DB 从库
        follow=follow_repository.get_relation(follower_id, followed_id)
        if follow:
            # 回填缓存
            FollowCache.add_relation(follower_id, followed_id)
            return True
        return False
