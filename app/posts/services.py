from core.database import db
from .models import Post
from .schemas import post_schema, post_list_schema
from app.users.repositories import user_repository
from app.likes.repositories import like_repository
from app.common.exceptions import (
	ValidationError,
	ResourceNotFoundError,
	AuthenticationError,
	DatabaseError,
)
from typing import Dict, Any, Optional
from app.posts.repositories import post_repository
import logging

logger = logging.getLogger(__name__)


class PostService:
	'''帖子服务类（使用 repository 管理持久化）'''

	@staticmethod
	def create_post(user_id: int, content: str, image_url: str = None):
		if not content or len(content.strip()) == 0:
			raise ValidationError('帖子内容不能为空')
		if len(content.strip()) > 1000:
			raise ValidationError('帖子内容不能超过1000个字符')

		user = user_repository.get_by_id(user_id)
		if not user:
			raise ResourceNotFoundError('用户')

		try:
			post = post_repository.create_post(user_id=user_id, content=content.strip(), image_url=image_url)
			db.session.commit()
			logger.info('用户%d创建了帖子%d', user_id, post.id)
			return {'message': '帖子创建成功', 'post': post_schema.dump(post)}
		except Exception as e:
			db.session.rollback()
			logger.error('创建帖子失败: %s', e)
			if isinstance(e, (ValidationError, ResourceNotFoundError)):
				raise
			raise DatabaseError('创建帖子失败，请稍后重试')

	@staticmethod
	def _populate_has_liked(serialized_posts, current_user_id: int = None):
		"""辅助函数：为序列化后的帖子列表填充 has_liked 字段"""
		if current_user_id:
			from app.likes.models import Like as LikeModel
			# 获取当前用户点赞的所有帖子 ID 集合，优化查询效率
			post_ids = [p['id'] for p in serialized_posts]
			if not post_ids:
				return serialized_posts
			
			liked_ids = {
				l.post_id for l in LikeModel.query.filter(
					LikeModel.user_id == current_user_id,
					LikeModel.post_id.in_(post_ids)
				).all()
			}
			for p in serialized_posts:
				p['has_liked'] = p['id'] in liked_ids
		else:
			for p in serialized_posts:
				p['has_liked'] = False
		return serialized_posts

	@staticmethod
	def get_posts(page: int = 1, per_page: int = 20, user_id: int = None, current_user_id: int = None):
		per_page = min(100, max(1, per_page))
		page = max(1, page)
		try:
			result = post_repository.list_posts(page=page, per_page=per_page, user_id=user_id)
			posts = result.get('items', [])  # ORM对象列表
			# 先序列化
			serialized_posts = [post_schema.dump(p) for p in posts]
			# 填充 has_liked
			PostService._populate_has_liked(serialized_posts, current_user_id)

			return {
				'posts': serialized_posts,
				'pagination': result.get('pagination', {})
			}
		except Exception as e:
			logger.error('获取帖子列表失败: %s', e)
			if isinstance(e, ResourceNotFoundError):
				raise
			raise DatabaseError('获取列表失败，请稍后重试')

	@staticmethod
	def get_post(post_id: int, current_user_id: int = None):
		post = post_repository.get_by_id(post_id)
		if not post or not post.is_published:
			raise ResourceNotFoundError('帖子')
		post_data = post_schema.dump(post)
		if current_user_id:
			from app.likes.models import Like as LikeModel
			post_data['has_liked'] = (
				LikeModel.query.filter_by(user_id=current_user_id, post_id=post.id).first() is not None
			)
		else:
			post_data['has_liked'] = False
		return {'post': post_data}

	@staticmethod
	def update_post(post_id: int, user_id: int, content: str = None, image_url=None):
		post = post_repository.get_by_id(post_id)
		if not post:
			raise ResourceNotFoundError('帖子')
		if post.user_id != user_id:
			raise AuthenticationError('无权修改此帖子')
		if content is None and image_url is None:
			raise ValidationError('至少提供一个更新内容')
		
		try:
			if content is not None:
				if len(content.strip()) == 0:
					raise ValidationError('帖子内容不能为空')
				if len(content.strip()) > 1000:
					raise ValidationError('帖子内容不能超过1000个字符')
				post.content = content.strip()
			if image_url is not None:
				post.image_url = image_url
			
			db.session.commit()
			logger.info('用户%d更新了帖子%d', user_id, post_id)
			return {'message': '帖子更新成功', 'post': post_schema.dump(post)}
		except Exception as e:
			db.session.rollback()
			logger.error('更新帖子失败: %s', e)
			if isinstance(e, (ValidationError, ResourceNotFoundError)):
				raise
			raise DatabaseError('更新帖子失败,请稍后重试')

	@staticmethod
	def delete_post(post_id: int, user_id: int):
		post = post_repository.get_by_id(post_id)
		if not post:
			raise ResourceNotFoundError('帖子')
		if post.user_id != user_id:
			raise AuthenticationError('无权删除该帖子')
		try:
			post_repository.soft_delete_post(post)
			db.session.commit()
			logger.info('用户%d软删除了帖子%d', user_id, post_id)
			return {'message': '帖子删除成功'}
		except Exception as e:
			db.session.rollback()
			logger.error('删除帖子失败: %s', e)
			if isinstance(e, (ResourceNotFoundError, AuthenticationError)):
				raise
			raise DatabaseError('删除帖子失败，请稍后重试')

	@staticmethod
	def like_post(post_id: int, user_id: int):
		post = post_repository.get_by_id(post_id)
		if not post or not post.is_published:
			raise ResourceNotFoundError('帖子')
		existing = like_repository.get_post_like(user_id=user_id, post_id=post_id)
		if existing:
			raise ValidationError('已点赞该帖子')
		try:
			like_repository.create_post_like(user_id=user_id, post_id=post_id)
			# 使用 SQLAlchemy 的 F 表达式风格更新（此处简化处理，ORM 会自动追踪变化）
			post.like_count = (post.like_count or 0) + 1
			db.session.commit()
			logger.info('用户%d点赞了帖子%d', user_id, post_id)
			return {'message': '点赞成功'}
		except Exception as e:
			db.session.rollback()
			logger.error('点赞帖子失败: %s', e)
			if isinstance(e, (ValidationError, ResourceNotFoundError)):
				raise
			raise DatabaseError('点赞失败,请稍后重试')

	@staticmethod
	def unlike_post(post_id: int, user_id: int):
		like = like_repository.get_post_like(user_id=user_id, post_id=post_id)
		if not like:
			raise ResourceNotFoundError('点赞记录')
		try:
			like_repository.delete_like(like)
			post = post_repository.get_by_id(post_id)
			if post:
				post.like_count = max(0, (post.like_count or 0) - 1)
			db.session.commit()
			logger.info('用户%d取消点赞记录%d', user_id, post_id)
			return {'message': '取消点赞成功'}
		except Exception as e:
			db.session.rollback()
			logger.error('取消点赞失败: %s', e)
			if isinstance(e, ResourceNotFoundError):
				raise
			raise DatabaseError('取消点赞失败，请稍后重试')

	@staticmethod
	def search_posts(query: str, page: int = 1, per_page: int = 20, current_user_id: int = None):
		per_page = min(100, max(1, per_page))
		page = max(1, page)
		try:
			result = post_repository.search_posts(query, page=page, per_page=per_page)
			posts = [post_schema.dump(p) for p in result.get('items', [])]
			# 填充 has_liked
			PostService._populate_has_liked(posts, current_user_id)
			return {'posts': posts, 'pagination': result.get('pagination', {})}
		except Exception as e:
			logger.error('搜索帖子失败：%s', e)
			raise DatabaseError('搜索帖子失败，请稍后重试')
