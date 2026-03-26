from core import db
from app.users.models import User
from .models import Follow
from .repositories import follow_repository
from .schemas import (
    follow_created_schema,
    follow_response_schema,
    follow_list_schema,
)
from app.users.schemas import UserListSchema
 
from app.common.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    AuthenticationError,
    DatabaseError,
)
import logging
from sqlalchemy.orm import aliased

from app.users.repositories import user_repository

logger = logging.getLogger(__name__)


class FollowService:
    @staticmethod
    def follow_user(follower_id: int, followed_id: int):
        try:
            if follower_id == followed_id:
                raise ValidationError('不能关注自己')

            follower = user_repository.get_by_id(follower_id)
            followed = user_repository.get_by_id(followed_id)
            
            if not follower or not getattr(follower, 'is_active', True):
                raise ResourceNotFoundError('关注者用户不存在或已被禁用')
            if not followed or not getattr(followed, 'is_active', True):
                raise ResourceNotFoundError('被关注用户不存在或已被禁用')

            existing = follow_repository.get_relation(follower_id, followed_id)
            if existing:
                raise ValidationError('已关注该用户')

            follow = follow_repository.create_follow(follower_id, followed_id)

            db.session.commit()
            logger.info(f'用户{follower_id}关注了用户{followed_id}')
            follow_data = follow_response_schema.dump(follow)
            return {'message': '关注成功', 'follow': follow_data}
        except Exception as e:
            db.session.rollback()
            logger.error('关注用户失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, ValidationError)):
                raise
            raise DatabaseError('关注操作失败,请稍后重试')

    @staticmethod
    def unfollow_user(follower_id: int, followed_id: int):
        try:
            follow = follow_repository.get_relation(follower_id, followed_id)
            if not follow:
                raise ResourceNotFoundError('未关注该用户')
            follow_repository.delete_follow(follow)
            db.session.commit()
            logger.info('用户%d取消关注用户%d', follower_id, followed_id)
            return {'message': '取消关注成功'}
        except Exception as e:
            db.session.rollback()
            logger.error('取消关注失败: %s', e)
            if isinstance(e, ResourceNotFoundError):
                raise
            raise DatabaseError('取消关注操作失败,请稍后重试')

    @staticmethod
    def get_following(user_id: int, page: int = 1, per_page: int = 20):
        try:
            user = user_repository.get_by_id(user_id)
            if not user or not getattr(user, 'is_active', True):
                raise ResourceNotFoundError('用户不存在或已被禁用')

            result = follow_repository.list_following(user_id, page=page, per_page=per_page)
            items = follow_response_schema.dump(result.get('items', []), many=True)
            return {'follows': items, 'pagination': result.get('pagination', {})}
        except Exception as e:
            logger.error('获取关注列表失败: %s', e)
            if isinstance(e, ResourceNotFoundError):
                raise
            raise DatabaseError('获取关注列表失败，请稍后重试')

    @staticmethod
    def get_followers(user_id: int, page: int = 1, per_page: int = 20):
        try:
            user = user_repository.get_by_id(user_id)
            if not user or not getattr(user, 'is_active', True):
                raise ResourceNotFoundError('用户不存在或已被禁用')

            result = follow_repository.list_followers(user_id, page=page, per_page=per_page)
            items = follow_response_schema.dump(result.get('items', []), many=True) 
            return {'follows': items, 'pagination': result.get('pagination', {})}
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
        
        # Service 只负责序列化
        users = UserListSchema().dump(result.get('items', []), many=True)
        return {'mutual_users': users, 'pagination': result.get('pagination', {})}

    @staticmethod
    def is_following(follower_id: int, followed_id: int) -> bool:
        follow = follow_repository.get_relation(follower_id, followed_id)
        return follow is not None