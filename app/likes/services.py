from core import db
from typing import Optional, Dict, Any
from sqlalchemy.exc import IntegrityError
from app.common.exceptions import ValidationError, ResourceNotFoundError, DatabaseError, ConflictError, PermissionError
from app.users.repositories import user_repository
from app.comments.repositories import comment_repository
from app.likes.repositories import like_repository
from app.posts.repositories import post_repository
from app.likes.cache import LikeCache
from services.search import PostSearchService
import logging
from .schemas import like_schema, likes_schema
from app.common import event_bus
logger = logging.getLogger(__name__)


class LikeService:
    @staticmethod
    def create_like(user_id: int, post_id: int = None, comment_id: int = None):
        """创建点赞，返回序列化字典"""
        if not (post_id or comment_id) or (post_id and comment_id):
            raise ValidationError('只能传入 post_id 或 comment_id')
        target_type='post' if post_id else 'comment'
        target_id=post_id or comment_id
        #Redis预检查
        if LikeCache.is_liked(user_id,target_id,target_type):
            raise ConflictError('你已经点过赞了(Redis校验)')
        
        user = user_repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError('用户不存在')

        if post_id:
            post = post_repository.get_by_id(post_id)
            if not post:
                raise ResourceNotFoundError('帖子不存在')
        else:
            comment = comment_repository.get_by_id(comment_id)
            if not comment:
                raise ResourceNotFoundError('评论不存在')

        try:
            if post_id:
                like = like_repository.create_post_like(user_id=user_id, post_id=post_id)
                # 更新计数（通过 Repository 原子操作，避免并发问题）
                post_repository.increment_like_count(post_id)
            else:
                like = like_repository.create_comment_like(user_id=user_id, comment_id=comment_id)
                # 更新计数（通过 Repository 原子操作，避免并发问题）
                comment_repository.increment_like_count(comment_id)

            db.session.commit()

            LikeCache.add_like(user_id,target_id,target_type)

            # 同步更新 ES 点赞数
            if post_id:
                post = post_repository.get_by_id(post_id)
                event_bus.publish('post.like_count_changed',{
                        'post_id':post_id,
                        'like_count':post.like_count if post else 0
                    })
            logger.info('用户%d点赞成功', user_id)
            return like_schema.dump(like)
        except IntegrityError as e:
            db.session.rollback()
            raise  ConflictError('您已点赞过了')  
        except Exception as e:
            db.session.rollback()
            logger.error('点赞失败: %s', e)
            raise DatabaseError('点赞操作失败，请稍后重试')

    @staticmethod
    def delete_like(user_id: int, post_id: int = None, comment_id: int = None):
        """取消点赞，返回 True/False"""
        if not (post_id or comment_id) or (post_id and comment_id):
            raise ValidationError('必须且只能传入 post_id 或 comment_id')

        if post_id:
            like = like_repository.get_post_like(user_id=user_id, post_id=post_id)
        else:
            like = like_repository.get_comment_like(user_id=user_id, comment_id=comment_id)

        if not like:
            target = '帖子' if post_id else '评论'
            raise ResourceNotFoundError(f'未找到该{target}的点赞记录')

        try:
            if like.post_id:
                # 更新计数（通过 Repository 原子操作，避免并发问题）
                post_repository.decrement_like_count(like.post_id)
            if like.comment_id:
                comment_repository.decrement_like_count(like.comment_id)

            like_repository.delete_like(like)
            db.session.commit()

            #删除Redis缓存
            target_type='post' if like.post_id else 'comment'
            target_id=like.post_id or like.comment_id
            LikeCache.remove_like(user_id,target_id,target_type)

            # 同步更新 ES 点赞数
            if like.post_id:
                post=post_repository.get_by_id(like.post_id)
                event_bus.publish('post.like_count_changed',{
                    'post_id':like.post_id,
                    'like_count':post.like_count if post else 0
                })
            logger.info('用户%d取消点赞成功', user_id)
            return True
        except Exception as e:
            db.session.rollback()
            logger.error('取消点赞失败: %s', e)
            raise DatabaseError('取消点赞操作失败，请稍后重试')

    @staticmethod
    def delete_like_by_id(user_id: int, like_id: int, post_id: int = None):
        """通过 like_id 删除点赞，需验证用户权限"""
        like = like_repository.get_by_id(like_id)  # 假设仓储有 get_by_id 方法
        if not like:
            raise ResourceNotFoundError('点赞记录不存在')
        if like.user_id != user_id:
            raise PermissionError('无权限取消该点赞')
        # 可选：验证 post_id 是否匹配（如果提供）
        if post_id and like.post_id != post_id:
            raise ResourceNotFoundError('点赞记录与帖子不匹配')

        # 复用 delete_like 的核心逻辑，但需要传入 like 对象
        try:
            if like.post_id:
                # 更新计数（通过 Repository 原子操作，避免并发问题）
                post_repository.decrement_like_count(like.post_id)
            if like.comment_id:
                comment_repository.decrement_like_count(like.comment_id)

            like_repository.delete_like(like)
            db.session.commit()
            # 同步更新 ES 点赞数
            if like.post_id:
                post=post_repository.get_by_id(like.post_id)
                event_bus.publish('post.like_count_changed',{
                    'post_id':like.post_id,
                    'like_count':post.like_count if post else 0
                })
            logger.info('用户%d取消点赞成功', user_id)
            return True
        except Exception as e:
            db.session.rollback()
            logger.error('取消点赞失败: %s', e)
            raise DatabaseError('取消点赞操作失败，请稍后重试')
    @staticmethod
    def get_user_likes(user_id: int, page: int = 1, per_page: int = 20):
        user = user_repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError('用户不存在')
        per_page = min(100, max(1, per_page))
        result = like_repository.list_by_user(user_id, page=page, per_page=per_page)
        likes_data = likes_schema.dump(result['items'], many=True)
        return {
            'items': likes_data,
            'pagination': result['pagination']
        }
    
