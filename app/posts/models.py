from core import db 
from datetime import datetime, timezone
from typing import List,Optional

class Post(db.Model):
	'''帖子模型'''
	__tablename__='posts'
	id=db.Column(db.Integer,primary_key=True)
	content=db.Column(db.Text,nullable=False)
	image_url=db.Column(db.String(500))
	user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
	created_at=db.Column(db.DateTime,default=lambda: datetime.now(timezone.utc))
	updated_at=db.Column(db.DateTime,default=lambda: datetime.now(timezone.utc),onupdate=lambda: datetime.now(timezone.utc))
	is_published=db.Column(db.Boolean,default=True)
	like_count=db.Column(db.Integer,default=0)
	comment_count=db.Column(db.Integer,default=0)
	is_deleted=db.Column(db.Boolean,default=False)

	#关系定义
	author=db.relationship('User',back_populates='posts')
	comments=db.relationship('Comment',back_populates='post',lazy='dynamic',cascade='save-update')
	likes=db.relationship('Like',back_populates='post',lazy='dynamic',cascade='save-update')

	def __repr__(self):
		return f'<Post{self.id} by User{self.user_id}>'
			
			
