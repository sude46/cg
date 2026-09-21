
from app.common.database import utcnow
from core import db


class Post(db.Model):
    '''帖子模型'''
    __tablename__='posts'
    id=db.Column(db.Integer,primary_key=True)
    content=db.Column(db.Text,nullable=False)
    image_url=db.Column(db.String(500))
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=utcnow,index=True)
    updated_at=db.Column(db.DateTime,default=utcnow,onupdate=utcnow)
    is_published=db.Column(db.Boolean,default=True,index=True)
    like_count=db.Column(db.Integer,default=0)
    comment_count=db.Column(db.Integer,default=0)
    deleted_at=db.Column(db.DateTime,nullable=True,default=None,index=True)


    version_id=db.Column(db.Integer,default=0,nullable=False)

    __mapper_args__={
        'version_id_col':version_id
    }

    #复合索引
    __table_args__=(
        #查询某个用户帖子列表(按时间倒序)
        db.Index('index_post_created','user_id','created_at'),
        #查询公开的帖子列表（按时间倒序）
        db.Index('idx_post_published_created','is_published','deleted_at','created_at'),
        #查询热门帖子（按点赞数倒序）
        db.Index('idx_post_hot','is_published','deleted_at','like_count'),
        #覆盖公共feed中按用户筛选的场景
        db.Index('idx_post_user_created','is_published','deleted_at','user_id'),


    )

    #关系定义
    author=db.relationship('User',back_populates='posts')
    comments=db.relationship('Comment',back_populates='post',lazy='dynamic',cascade='save-update')
    likes=db.relationship('Like',back_populates='post',lazy='dynamic',cascade='save-update')

    def __repr__(self):
        return f'<Post{self.id} by User{self.user_id}>'


