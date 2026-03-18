from marshmallow import Schema, fields, validate, validates_schema, ValidationError
from utils.validators import validate_content_length, validate_image_url
from datetime  import datetime



class IsoDateTime(fields.DateTime):
	def _serialize(self,value,attr,obj,**kwargs):
		if value is None:
			return None
		if not isinstance(value,datetime):
			raise ValidationError('Invalid datetime object')
		return value.isoformat()
class CreatePostSchema(Schema):
	"""创建帖子请求模式"""
	content = fields.Str(
		required=True,
		validate=[validate.Length(min=1, max=1000, error="帖子内容长度必须在1-1000字符之间")],
	)
	image_url = fields.Str(
		required=False,
		validate=[validate.Length(max=500, error="图片URL长度不能超过500个字符")],
	)

	@validates_schema
	def validate_fields(self, data, **kwargs):
		content = (data.get("content") or "").strip()
		image_url = data.get("image_url")
		if not content:
			raise ValidationError("帖子内容不能为空")
		if not validate_content_length(content, max_length=1000):
			raise ValidationError("帖子内容长度不符合要求")


class UpdatePostSchema(Schema):
	"""更新帖子请求模式"""
	content = fields.Str(
		required=False,
		validate=[validate.Length(min=1, max=1000, error="帖子内容长度必须在1-1000个字符之间")],

	)
	image_url = fields.Str(
		required=False,
		validate=[validate.Length(max=500, error="图片URL长度不能超过500个字符")],
	)

	@validates_schema
	def validate_fields(self, data, **kwargs):
		content = data.get("content")
		image_url = data.get("image_url")
		if content is None and image_url is None:
			raise ValidationError("至少提供一个更新内容")
		if content is not None:
			content = content.strip()
			if not content:
				raise ValidationError("帖子内容不能为空")
			if not validate_content_length(content, max_length=1000):
				raise ValidationError("帖子内容不能超过1000个字符")
		if image_url is not None and image_url != "":
			if not validate_image_url(image_url):
				raise ValidationError("图片URL格式无效")


class AuthorSchema(Schema):
	id = fields.Int()
	username = fields.Str()


class PostSchema(Schema):
	id = fields.Int()
	content = fields.Str()
	image_url = fields.Str(allow_none=True)
	user_id = fields.Int()
	author = fields.Nested(AuthorSchema, allow_none=True)
	created_at = fields.DateTime(attribute="created_at")
	updated_at = fields.DateTime(attribute="updated_at")
	is_published = fields.Bool()
	like_count = fields.Int()
	comment_count = fields.Int()
	has_liked = fields.Bool(load_default=False)
	def dump_with_options(self,include_author=True,include_stats=True):
		base_fields=["id","content","image_url","user_id","created_at","updated_at","is_published"]
		if include_author:
			base_fields.append("author")
		if include_stats:
			base_fields.extend(["like_count","comment_count","has_liked"])
		return self.dump(only=base_fields)


class PostListSchema(Schema):
	posts = fields.List(fields.Nested(PostSchema))
	pagination = fields.Dict()


# 实例化 schema
create_post_schema = CreatePostSchema()
update_post_schema = UpdatePostSchema()
post_schema = PostSchema()
post_list_schema = PostListSchema()

