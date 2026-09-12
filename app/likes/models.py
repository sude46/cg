
from app.common.database import utcnow
from core import db


class Like(db.Model):
    __tablename__ = 'likes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'), nullable=True, index=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    deleted_at=db.Column(db.DateTime,nullable=True,index=True)
    # 关系定义
    user = db.relationship('User', backref=db.backref('user_likes', lazy='dynamic', overlaps='likes'))
    post = db.relationship('Post', backref=db.backref('post_likes', lazy='dynamic', overlaps='likes'))
    comment = db.relationship('Comment', backref=db.backref('comment_likes', lazy='dynamic', overlaps='likes'))

    __table_args__ = (
        db.CheckConstraint(
            "(post_id IS NOT NULL OR comment_id IS NOT NULL) AND NOT (post_id IS NOT NULL AND comment_id IS NOT NULL)",
            name="like_post_or_comment_check",
        ),
        db.UniqueConstraint('user_id', 'post_id','deleted_at', name='user_post_unique'),
        db.UniqueConstraint('user_id', 'comment_id','deleted_at', name='user_comment_unique'),
        #覆盖'用户点赞列表按时间倒序'
        db.Index('idx_like_user_created','user_id','created_at'),
    )
    def __repr__(self):
        return f'<Like user={self.user_id} post={self.post_id} comment={self.comment_id}>'
