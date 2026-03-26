from datetime import datetime,timezone
from core import db
from sqlalchemy.sql import func

class Notification(db.Model):
    __tablename__='notifications'

    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(
            db.Integer,
            db.ForeignKey('users.id',ondelete='CASCADE'),
            nullable=False
            )
    actor_id=db.Column(
            db.Integer,
            db.ForeignKey('users.id',ondelete='CASCADE')
            )
    #通知类型
    type=db.Column(db.String(20),nullable=False)
    #相关资源ID,例如帖子ID或评论ID根据type不同而不同
    resource_id=db.Column(db.Integer,nullable=True)
    #相关资源类型,例如'post','comment'
    resource_type=db.Column(db.String,nullable=True)
    content=db.Column(db.Text,nullable=False)
    is_read=db.Column(db.Boolean,default=False)
    is_deleted=db.Column(db.Boolean,default=False,nullable=False,index=True)
    created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),nullable=False)

    #关系
    #接收通知的用户
    user=db.relationship('User',foreign_keys=[user_id],backref=db.backref('notifications',lazy='dynamic'))
    #触发通知的用户
    actor=db.relationship('User',foreign_keys=[actor_id])

    def __repr__(self):
        return f'<Notification{self.id}-Type:{self.type}-To:{self.user_id}>'


