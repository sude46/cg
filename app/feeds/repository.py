from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from app.common.database import get_read_session
from app.follows.models import Follow
from app.posts.models import Post
from core.metrics import monitor_db

from .cursor import encode_cursor, score_for


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
    def get_following_posts_cursor(user_id:int,cursor,limit:int=20):
        '''拉模式 keyset 分页：按 (created_at, id) 倒序，返回 (posts, has_more, next_cursor)
        cursor: (sec, post_id) 元组或 None'''
        from datetime import UTC, datetime
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
            )
        if cursor is not None:
            score, id_low = cursor
            sec = int(float(score))
            sec_dt = datetime.fromtimestamp(sec, tz=UTC).replace(tzinfo=None)
            query = query.filter(or_(
                Post.created_at < sec_dt,
                and_(Post.created_at == sec_dt, Post.id < int(id_low)),
            ))
        rows=query.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit+1).all()
        has_more=len(rows)>limit
        rows=rows[:limit]
        next_cursor=None
        if has_more and rows:
            last=rows[-1]
            sec=int(last.created_at.replace(tzinfo=UTC).timestamp())
            next_cursor=encode_cursor(score_for(sec, last.id), last.id)
        return rows, has_more, next_cursor

    @staticmethod
    @monitor_db("select","feeds")
    def get_posts_by_ids(post_ids:list[int]):
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

    @staticmethod
    @monitor_db("select","feeds")
    def get_explore_posts_cursor(cursor,limit:int=20):
        '''广场keyset分页:全站帖子按(created_at,id)倒序，返回(posts,has_more,next_cursor)'''
        from datetime import UTC, datetime
        session=FeedRepository._read_session()
        query=session.query(Post).options(
                joinedload(Post.author)
                ).filter(
                        Post.deleted_at.is_(None),
                        Post.is_published.is_(True)
                        )
        if cursor is not None:
            score, id_low = cursor
            sec = int(float(score))
            sec_dt = datetime.fromtimestamp(sec, tz=UTC).replace(tzinfo=None)
            query = query.filter(or_(
                Post.created_at < sec_dt,
                and_(Post.created_at == sec_dt, Post.id < int(id_low)),
            ))
        rows=query.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit+1).all()
        has_more=len(rows)>limit
        rows=rows[:limit]
        next_cursor=None
        if has_more and rows:
            last=rows[-1]
            sec=int(last.created_at.replace(tzinfo=UTC).timestamp())
            next_cursor=encode_cursor(score_for(sec, last.id), last.id)
        return rows, has_more, next_cursor



