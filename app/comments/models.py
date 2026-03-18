from datetime import datetime,timezone
from core import db
from sqlalchemy.sql import func

class Comment(db.Model):
    __tablename__='comments'

    id=db.Column(db.Integer,primary_key=True)
    content=db.Column(db.Text,nullable=False)
    post_id=db.Column(
            db.Integer,
            db.ForeignKey('posts.id',ondelete='CASCADE'),
            nullable=False
            )
    user_id=db.Column(
            db.Integer,
            db.ForeignKey('users.id',ondelete='CASCADE'),
            nullable=False
            )
    like_count=db.Column(db.Integer,default=0)
    created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),nullable=False)
    updated_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc),nullable=False)
    is_deleted=db.Column(db.Boolean,default=False)

    author = db.relationship('User', back_populates='comments')
    post = db.relationship('Post', back_populates='comments')

    def __repr__(self):
        return f'<Comment{self.id} by User{self.user_id} on Post{self.post_id}>'
    


