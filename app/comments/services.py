from sqlalchemy.exc import IntegrityError
from core import db
from .models import Comment
from app.posts.repositories import post_repository
from app.users.repositories import user_repository
from app.common.exceptions import (
    ResourceNotFoundError,
    PermissionError,
    ValidationError,
    DatabaseError,
)
from app.comments.repositories import comment_repository
from app.common.events import event_bus
from datetime import datetime, timezone
import logging
from .schemas import (comment_create_schema,comment_update_schema,comment_schema,comments_schema)

logger = logging.getLogger(__name__)


class CommentService:
    @staticmethod
    def create_comment(user_id: int, data: dict) -> dict:
        post_id = data.get('post_id')
        content = (data.get('content') or '').strip()
        if not post_id:
            raise ValidationError('缺少 post_id')
        if not content or len(content) > 500:
            raise ValidationError('评论内容不能为空且长度不能超过500字符')

        post = post_repository.get_by_id(post_id)
        if not post:
            raise ResourceNotFoundError(f'帖子(ID:{post_id})不存在')

        try:
            comment = comment_repository.create_comment(post_id=post_id, user_id=user_id, content=content)
            post_repository.increment_comment_count(post_id)
            db.session.commit()

            # 触发通知事件（排除作者自评论）
            if post.user_id != user_id:
                event_bus.publish('comment.created', {
                    'user_id': post.user_id,
                    'actor_id': user_id,
                    'type': 'comment',
                    'comment_id': comment.id,
                    'post_id': post_id,
                    'content': content
                })

            logger.info('用户%d为帖子%d创建评论%d', user_id, post_id, comment.id)
            return {'message': '评论成功', 'comment': comment_schema.dump(comment)}
        except IntegrityError:
            db.session.rollback()
            raise DatabaseError('创建评论失败，数据库约束错误')
        except Exception as e:
            db.session.rollback()
            logger.error('创建评论失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, ValidationError)):
                raise
            raise DatabaseError(f'创建评论失败: {e}')

    @staticmethod
    def get_comment_by_id(comment_id: int) -> dict:
        comment = comment_repository.get_by_id(comment_id)
        if not comment:
            raise ResourceNotFoundError(f'评论(ID:{comment_id})不存在')
        return comment_schema.dump(comment)

    @staticmethod
    def get_comments_by_post_id(post_id: int, page: int = 1, per_page: int = 20) -> dict:
        post = post_repository.get_by_id(post_id)
        if not post:
            raise ResourceNotFoundError(f'帖子(ID:{post_id})不存在')

        result = comment_repository.list_by_post(post_id=post_id, page=page, per_page=per_page)
        items = comment_schema.dump(result.get('items', []), many=True)
        return {'items': items, 'pagination': result.get('pagination', {})}

    @staticmethod
    def update_comment(comment_id: int, user_id: int, data: dict) -> dict:
        try:
            comment = comment_repository.get_by_id(comment_id)
            if not comment:
                raise ResourceNotFoundError(f'评论(ID:{comment_id})不存在')

            user = user_repository.get_by_id(user_id)
            if comment.user_id != user_id and not (user and getattr(user, 'is_admin', False)):
                raise PermissionError('没有权限更新此评论')

            content = (data.get('content') or '').strip()
            if not content or len(content) > 500:
                raise ValidationError('评论内容格式无效')

            comment.content = content
            comment.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return {'message': '评论更新成功', 'comment': comment_schema.dump(comment)}
        except Exception as e:
            db.session.rollback()
            logger.error('更新评论失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, PermissionError, ValidationError)):
                raise
            raise DatabaseError(f'更新评论失败: {e}')

    @staticmethod
    def delete_comment(comment_id: int, user_id: int) -> dict:
        try:
            comment = comment_repository.get_by_id(comment_id)
            if not comment:
                raise ResourceNotFoundError(f'评论(ID:{comment_id})不存在')

            user = user_repository.get_by_id(user_id)
            is_comment_author = comment.user_id == user_id
            is_post_author = comment.post and comment.post.user_id == user_id
            is_admin = user and getattr(user, 'is_admin', False)

            if not (is_comment_author or is_post_author or is_admin):
                raise PermissionError('没有权限删除此评论')

            comment_repository.soft_delete(comment)
            # 更新帖子统计
            if comment.post_id:
                post_repository.decrement_comment_count(comment.post_id)

            db.session.commit()
            return {'message': '评论删除成功'}
        except Exception as e:
            db.session.rollback()
            logger.error('删除评论失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, PermissionError)):
                raise
            raise DatabaseError(f'删除评论失败: {e}')

