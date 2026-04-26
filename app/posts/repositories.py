from typing import Optional, Dict, Any
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import selectinload

from core import db
from app.posts.models import Post
from app.common.database import pagination_utils
from sqlalchemy import case


class PostRepository:
    @staticmethod
    def get_by_id(post_id: int,lock:bool=False) -> Optional[Post]:
        '''
        根据ID获取帖子
        lock=True:,使用Select for update,必须在是事务内调用
        '''
        query=Post.query.options(joinedload(Post.author)).filter_by(id=post_id,is_deleted=False)
        if lock:
            query=query.with_for_update()
        return query.first()

    @staticmethod
    def create_post(user_id: int, content: str, image_url: str = None) -> Post:
        post = Post(content=content, image_url=image_url, user_id=user_id, is_published=True)
        db.session.add(post)
        return post

    @staticmethod
    def list_posts(page: int = 1, per_page: int = 20, user_id: Optional[int] = None):
        query=Post.query.options(
            joinedload(Post.author)
        ).filter_by(is_deleted=False,is_published=True)
        if user_id:
            query=query.filter_by(user_id=user_id)
        query=query.order_by(Post.created_at.desc())
        result=pagination_utils.paginate(query,page=page,per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }

    @staticmethod
    def search_posts(query_str: str, page: int = 1, per_page: int = 20):
        query=Post.query.options(
            joinedload(Post.author)
            ).filter(
            Post.is_deleted==False,
            Post.is_published==True,
            Post.content.ilike(f'%{query_str}%')
        ).order_by(Post.created_at.desc())
        result=pagination_utils.paginate(query,page=page,per_page=per_page)
        return{
            'items':result['items'],
            'pagination':result['pagination']
        }

    @staticmethod
    def soft_delete_post(post: Post) -> None:
        """软删除帖子及相关评论（Like 是硬删除关系，不设置 is_deleted）"""
        post.is_deleted = True
        for comment in post.comments.all():
            comment.is_deleted = True
        # Like 模型没有 is_deleted 字段，需要硬删除
        for like in post.likes.all():
            db.session.delete(like)
        db.session.add(post)

    @staticmethod
    def increment_like_count(post_id: int) -> None:
        """原子操作：增加帖子点赞计数"""
        Post.query.filter_by(id=post_id).update({
            'like_count': Post.like_count + 1
        })

    @staticmethod
    def decrement_like_count(post_id: int) -> None:
        """原子操作：减少帖子点赞计数（不小于0）"""

        Post.query.filter_by(id=post_id).update({
            'like_count': case((Post.like_count > 0, Post.like_count - 1), else_=0)
        })

    @staticmethod
    def increment_comment_count(post_id:int):
        '''原子操作:增加帖子评论计数'''
        Post.query.filter_by(id=post_id).update({
            'comment_count':Post.comment_count+1
        })

    @staticmethod
    def decrement_comment_count(post_id:int):
        '''原子操作：减少帖子评论计数（不小于0）'''
        Post.query.filter_by(id=post_id).update({
            'comment_count':case((Post.comment_count>0,Post.comment_count-1),else_=0)
        })

post_repository = PostRepository()
