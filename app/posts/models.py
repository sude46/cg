from core import db 
from datetime import datetime, timezone
from typing import List,Optional
from .schemas import  post_schema
from app.common.database import pagination_utils

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

	def update_stats(self):
		'''更新统计信息'''
		self.like_count=self.likes.count()
		self.comment_count=self.comments.count()
		db.session.commit()
	def can_edit(self,user_id:int):
		'''检查用户是否有权限编辑'''
		return self.user_id==user_id


	@classmethod
	def get_user_posts(cls,user_id:int,page:int=1,per_page:int=20):
		'''获取用户的帖子'''
		query = cls.query.filter_by(user_id=user_id, is_published=True, is_deleted=False)
		return pagination_utils.paginate(query.order_by(cls.created_at.desc()), page=page, per_page=per_page)

	@classmethod
	def get_recent_posts(cls,page:int=1,per_page:int=20):
		'''获取最近的帖子'''
		return cls.query.filter_by(
			is_published=True,
			is_deleted=False
			).order_by(cls.created_at.desc()).paginate(
			page=page,
			per_page=per_page,
			error_out=False
			)

	@classmethod
	def search_posts(cls,query:str,page:int=1,per_page:int=20):
		return cls.query.filter(
			cls.is_published == True,
			cls.is_deleted==False,
			cls.content.ilike(f'%{query}%')
			).order_by(cls.created_at.desc()).paginate(
			page=page,
			per_page=per_page,
			error_out=False
			)
	def __repr__(self):
		return f'<Post{self.id} by User{self.user_id}>'
			
			
