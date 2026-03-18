from core import db
from typing import Optional, Dict, Any
from sqlalchemy.exc import IntegrityError
from app.common.exceptions import ValidationError, ResourceNotFoundError, DatabaseError,ConflictError
from app.users.repositories import user_repository
from app.comments.repositories import comment_repository
from app.likes.repositories import like_repository
from app.posts.repositories import post_repository
import logging
from .schemas import like_schema, likes_schema

logger = logging.getLogger(__name__)


class LikeService:
    @staticmethod
    def create_like(user_id: int, post_id: int = None, comment_id: int = None):
        """创建点赞，返回序列化字典"""
        if not (post_id or comment_id) or (post_id and comment_id):
            raise ValidationError('只能传入 post_id 或 comment_id')

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
                # 更新计数（简单策略：+1）
                post.like_count = getattr(post, 'like_count', 0) + 1
            else:
                like = like_repository.create_comment_like(user_id=user_id, comment_id=comment_id)
                comment.like_count = getattr(comment, 'like_count', 0) + 1

            db.session.commit()
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
            if like.post_id and like.post:
                like.post.like_count = max(0, getattr(like.post, 'like_count', 0) - 1)
            if like.comment_id and like.comment:
                like.comment.like_count = max(0, getattr(like.comment, 'like_count', 0) - 1)

            like_repository.delete_like(like)
            db.session.commit()
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
            if like.post_id and like.post:
                like.post.like_count = max(0, getattr(like.post, 'like_count', 0) - 1)
            if like.comment_id and like.comment:
                like.comment.like_count = max(0, getattr(like.comment, 'like_count', 0) - 1)

            like_repository.delete_like(like)
            db.session.commit()
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
        from app.likes.models import Like
        pag=Like.query.filter_by(user_id=user_id).order_by(Like.created_at.desc()).paginate(
                page=page,per_page=per_page,error_out=False
                )
        likes_data=likes_schema.dump(pag.items,many=True)
        return {
                'items':likes_data,
                'pagination':{
                    'page':pag.page,
                    'per_page':pag.per_page,
                    'total':pag.total,
                    'pages':pag.pages
                    }
                }
    
