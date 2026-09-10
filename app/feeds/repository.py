from typing import List,Optional
from sqlalchemy.orm import joinedload
from core import db
from app.posts.models import Post
from app.follows.models import Follow
from app.common.database import get_read_session
from core.metrics import monitor_db

class FeedRepository:
    '''
    Feed仓储层：封装时间线相关的数据库访问
    '''
    @staticmethod
    def _read_session():
        return get_read_session()
    
    #===========关注关系查询================
    @staticmethod
    @monitor_db("select","feeds")
    def get_followers(followed_id:int):
        '''获取某用户的全部粉丝'''
        session=FeedRepository._read_session()
        return session.query(Follow).filter(
            Follow.followed_id==followed_id,
            Follow.deleted_at.is_(None) 
        ).all()
    
    @staticmethod
    @monitor_db("select","feeds")
    def get_following_ids(follower_id:int):
        '''获取某用户关注的人ID列表'''
        session=FeedRepository._read_session()
        rows=session.query(Follow.followed_id).filter(
            Follow.follower_id==follower_id,
            Follow.deleted_at.is_(None)
        ).all()
        return [r[0] for r in rows]
    
    #帖子查询
    @staticmethod
    @monitor_db("select","feeds")
    def get_following_posts(
        user_id:int,
        offset:int,
        limit:int
    ):
        '''拉模式核心：查询关注用户的帖子（分页、倒序）
        返回：（posts_list,total_count）'''
        session=FeedRepository._read_session()
        query=session.query(Post).join(
            Follow,Post.user_id==Follow.followed_id
            ).options(
                joinedload(Post.author)
            ).filter(
                Follow.follower_id==user_id,
                Follow.deleted_at.is_(None),
                Post.deleted_at.is_(None),
                Post.is_published.is_(True)
            ).order_by(Post.created_at.desc())
        total=query.count()
        posts=query.offset(offset).limit(limit).all()
        return (posts,total)


    @staticmethod
    @monitor_db("select","feeds")
    def get_posts_by_ids(post_ids:List[int]):
        '''批量查询帖子(用于缓存命中后补全)'''
        if not post_ids:
            return []
        session=FeedRepository._read_session()
        return session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.id.in_(post_ids),
            Post.deleted_at.is_(None),
            Post.is_published.is_(True)
        ).all()
