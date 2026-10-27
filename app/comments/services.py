import logging

from sqlalchemy.exc import IntegrityError

from app.comments.repositories import comment_repository
from app.common.database import utcnow
from app.common.exceptions import (
    DatabaseError,
    PermissionError,
    ResourceNotFoundError,
    ValidationError,
)
from app.common.outbox import enqueue_event
from app.posts.repositories import post_repository
from app.users.cache import UserCache
from app.users.repositories import user_repository
from core import db
from core.metrics import COMMENT_OPERATIONS

from .cache import CommentCache
from .schemas import comment_schema

logger = logging.getLogger(__name__)


class CommentService:
    #==============创建（写DB->预热缓存->发事件)==========
    @staticmethod
    def create_comment(user_id: int, data: dict) -> dict:
        post_id = data.get('post_id')
        content = (data.get('content') or '').strip()
        if not post_id:
            raise ValidationError('缺少 post_id')
        if not content or len(content) > 500:
            raise ValidationError('评论内容不能为空且长度不能超过500字符')

        #查帖子(走主库，确保帖子存在且未删除)
        post = post_repository.get_by_id(post_id,force_master=True)
        if not post or post.deleted_at:
            raise ResourceNotFoundError(f'帖子(ID:{post_id})不存在')

        try:
            comment = comment_repository.create_comment(post_id=post_id, user_id=user_id, content=content)
            post_repository.increment_comment_count(post_id)
            db.session.flush()
            db.session.refresh(post)

            # 通知事件 + 评论数事件与评论同事务写 outbox
            if post.user_id != user_id:
                enqueue_event('comment.created', {
                    'user_id': post.user_id,
                    'actor_id': user_id,
                    'type': 'comment',
                    'comment_id': comment.id,
                    'post_id': post_id,
                    'content': content
                })
            enqueue_event('post.comment_count_changed', {
                'post_id': post_id,
                'comment_count': post.comment_count,
            })
            db.session.commit()

            #预热评论详情缓存（主库写Redistribution，失败不影响主流程）
            comment_dict=comment_schema.dump(comment)
            CommentCache.set(comment.id,comment_dict)
            if CommentCache.get_count(post_id) is None:
                # Redis 未预热：用主库真实计数（increment_comment_count 已提交）
                fresh_post=post_repository.get_by_id(post_id,force_master=True)
                CommentCache.set_count(post_id, fresh_post.comment_count if fresh_post else 0)
            else:
                CommentCache.increment_count(post_id)

            logger.info('用户%d为帖子%d创建评论%d', user_id, post_id, comment.id)
            COMMENT_OPERATIONS.labels(action='create', result='success').inc()
            return {'message': '评论成功', 'comment': comment_dict}
        except IntegrityError:
            db.session.rollback()
            COMMENT_OPERATIONS.labels(action='create', result='error').inc()
            raise DatabaseError('创建评论失败，数据库约束错误')
        except Exception as e:
            db.session.rollback()
            logger.error('创建评论失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, ValidationError)):
                raise
            COMMENT_OPERATIONS.labels(action='create', result='error').inc()
            raise DatabaseError(f'创建评论失败: {e}')


    #==================查询单条(Cache-Aside)==============

    @staticmethod
    def get_comment_by_id(comment_id: int) -> dict:
        #查缓存(从库)
        cached = CommentCache.get(comment_id)
        if cached:
            return cached
        #miss查DB(从库)
        comment=comment_repository.get_by_id(comment_id,force_master=False)
        if not comment or comment.deleted_at:
            raise ResourceNotFoundError(f'评论(ID:{comment_id}不存在)')

        #回填缓存（主库）
        comment_dict=comment_schema.dump(comment)
        CommentCache.set(comment_id,comment_dict)
        COMMENT_OPERATIONS.labels(action='get', result='success').inc()
        return comment_dict


    #===============查询列表（不走缓存，查从库）============
    @staticmethod
    def get_comments_by_post_id(post_id: int, page: int = 1, per_page: int = 20) -> dict:
        post = post_repository.get_by_id(post_id,force_master=False)
        if not post or post.deleted_at:
            raise ResourceNotFoundError(f'帖子(ID:{post_id})不存在')

        result = comment_repository.list_by_post(post_id=post_id, page=page, per_page=per_page)
        items = comment_schema.dump(result.get('items', []), many=True)

        # 批量预热评论作者的用户资料缓存
        if items:
            author_ids = list(set(c['user_id'] for c in items if c.get('user_id')))
            if author_ids:
                UserCache.preload_profiles(author_ids)
        COMMENT_OPERATIONS.labels(action='list', result='success').inc()
        return {'items': items, 'pagination': result.get('pagination', {})}

    #===============更新（延迟双删）===============
    @staticmethod
    def update_comment(comment_id: int, user_id: int, data: dict) -> dict:
        try:
            #权限校验走主库(确保读到最新)
            comment = comment_repository.get_by_id(comment_id,force_master=True)
            if not comment or comment.deleted_at :
                raise ResourceNotFoundError(f'评论(ID:{comment_id})不存在')

            user = user_repository.get_by_id(user_id)
            if comment.user_id != user_id and not (user and getattr(user, 'is_admin', False)):
                raise PermissionError('没有权限更新此评论')

            content = (data.get('content') or '').strip()
            if not content or len(content) > 500:
                raise ValidationError('评论内容格式无效')

            comment.content = content
            comment.updated_at = utcnow()
            db.session.commit()

            #延迟双删：请评论详情缓存
            CommentCache.invalidate(comment_id)
            try:
                from celery import current_app as celery_app
                celery_app.send_task(
                    'tasks.post_tasks.delayed_invalidate_comment',
                    args=(comment_id,),
                    countdown=2
                )
            except Exception as e:
                logger.warning(f'调度延迟删除失败，降级为线程：{e}')
                CommentCache.double_invalidate(comment_id)
            logger.info('用户%d更新评论%d', user_id, comment_id)
            COMMENT_OPERATIONS.labels(action='update', result='success').inc()
            return {'message': '评论更新成功', 'comment': comment_schema.dump(comment)}
        except Exception as e:
            db.session.rollback()
            logger.error('更新评论失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, PermissionError, ValidationError)):
                raise
            COMMENT_OPERATIONS.labels(action='update', result='error').inc()
            raise DatabaseError(f'更新评论失败: {e}')



    #=========================删除（延迟双删+评论数减1）========================
    @staticmethod
    def delete_comment(comment_id: int, user_id: int) -> dict:
        try:
            #权限校验走主库
            comment = comment_repository.get_by_id(comment_id,force_master=True)
            if not comment:
                raise ResourceNotFoundError(f'评论(ID:{comment_id})不存在')

            user = user_repository.get_by_id(user_id)
            is_comment_author = comment.user_id == user_id
            is_post_author = comment.post and comment.post.user_id == user_id
            is_admin = user and getattr(user, 'is_admin', False)

            if not (is_comment_author or is_post_author or is_admin):
                raise PermissionError('没有权限删除此评论')
            post_id=comment.post_id

            #软删除+评论数-1
            comment_repository.soft_delete(comment)
            # 更新帖子统计
            if comment.post_id:
                post_repository.decrement_comment_count(comment.post_id)
                db.session.flush()
                db.session.refresh(comment.post)
                enqueue_event('post.comment_count_changed', {
                    'post_id': comment.post_id,
                    'comment_count': comment.post.comment_count,
                })
            db.session.commit()

            #清评论缓存+延迟双删
            CommentCache.invalidate(comment_id)
            try:
                from celery import current_app as celery_app
                celery_app.send_task(
                    'tasks.post_tasks.delayed_invalidate_comment',
                    args=(comment_id,),
                    countdown=2
                )
            except Exception as e:
                logger.warning(f'调度延迟删除失败，降级为线程:{e}')
                CommentCache.double_invalidate(comment_id)
            #更新Redis评论计数器
            if post_id:
                if CommentCache.get_count(post_id) is None:
                    # Redis 未预热：用主库真实计数（decrement_comment_count 已提交）
                    fresh_post=post_repository.get_by_id(post_id,force_master=True)
                    CommentCache.set_count(post_id, fresh_post.comment_count if fresh_post else 0)
                else:
                    CommentCache.decrement_count(post_id)
            logger.info('用户%d删除评论%d',user_id,comment_id)
            COMMENT_OPERATIONS.labels(action='delete', result='success').inc()
            return {'message': '评论删除成功'}
        except Exception as e:
            db.session.rollback()
            logger.error('删除评论失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, PermissionError)):
                raise
            COMMENT_OPERATIONS.labels(action='delete', result='error').inc()
            raise DatabaseError(f'删除评论失败: {e}')


    @staticmethod
    def get_hot_comments_by_post_id(post_id:int,page:int=1,per_page:int=20):
        '''获取帖子下的热评(按点赞数排序)'''
        comment_ids,total=CommentCache.get_hot_comments(post_id,page,per_page)

        #批量查评论详情缓存
        comments=[]
        for cid in comment_ids:
            comment_dict=CommentCache.get(cid)
            if comment_dict:
                comments.append(comment_dict)
            else:
                #miss查DB回填(防击穿)
                comment=comment_repository.get_by_id(cid,force_master=False)
                if comment and not comment.deleted_at:
                    comment_dict=comment_schema.dump(comment)
                    CommentCache.set(cid,comment_dict)
                    comments.append(comment_dict)
        COMMENT_OPERATIONS.labels(action='hot', result='success').inc()
        return {'items': comments, 'pagination': {'page': page, 'per_page': per_page, 'total': total}}



