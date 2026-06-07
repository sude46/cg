from datetime import datetime,timezone
from app.common.database import utcnow
from core import db
from sqlalchemy.sql import func

class Comment(db.Model):
    __tablename__='comments'

    id=db.Column(db.Integer,primary_key=True)
    content=db.Column(db.Text,nullable=False)
    post_id=db.Column(
            db.Integer,
            db.ForeignKey('posts.id',ondelete='CASCADE'),
            nullable=False,
            index=True)
    user_id=db.Column(
            db.Integer,
            db.ForeignKey('users.id',ondelete='CASCADE'),
            nullable=False,
            index=True
            )
    like_count=db.Column(db.Integer,default=0)
    created_at=db.Column(db.DateTime,default=utcnow,nullable=False,index=True)
    updated_at=db.Column(db.DateTime,default=utcnow,onupdate=utcnow,nullable=False)
    deleted_at=db.Column(db.DateTime,nullable=True,default=None,index=True)

    version_id=db.Column(db.Integer,default=0,nullable=False)
    __mapper_args__={'version_id_col':version_id}

    author = db.relationship('User', back_populates='comments')
    post = db.relationship('Post', back_populates='comments')

    __table_args__=(
        #查询帖子评论列表（最常用）
        db.Index('idx_comment_post_created','post_id','deleted_at','created_at'),
        #查询用户评论历史
        db.Index('idx_comment_user_created','user_id','deleted_at','created_at'),
    )


    def __repr__(self):
        return f'<Comment{self.id} by User{self.user_id} on Post{self.post_id}>'
    


