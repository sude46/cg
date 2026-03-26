from core import db
from datetime import datetime, timezone


class Like(db.Model):
    __tablename__ = 'likes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'), nullable=True, index=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # 关系定义
    user = db.relationship('User', backref=db.backref('user_likes', lazy='dynamic', overlaps='likes'))
    post = db.relationship('Post', backref=db.backref('post_likes', lazy='dynamic', overlaps='likes'))
    comment = db.relationship('Comment', backref=db.backref('comment_likes', lazy='dynamic', overlaps='likes'))

    __table_args__ = (
        db.CheckConstraint(
            "(post_id IS NOT NULL OR comment_id IS NOT NULL) AND NOT (post_id IS NOT NULL AND comment_id IS NOT NULL)",
            name="like_post_or_comment_check",
        ),
        db.UniqueConstraint('user_id', 'post_id', name='user_post_unique'),
        db.UniqueConstraint('user_id', 'comment_id', name='user_comment_unique'),
    )
    def __repr__(self):
        return f'<Like user={self.user_id} post={self.post_id} comment={self.comment_id}>'
