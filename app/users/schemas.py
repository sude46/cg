from utils.validators import validate_username, validate_password, validate_email
from marshmallow import validate
from marshmallow import Schema, fields, validates_schema, post_dump, ValidationError
try:
	from password_strength import PasswordPolicy
	try:
		# 兼容不同版本的 password_strength 初始化参数
		password_policy = PasswordPolicy(
			length=8,
			uppercase=1,
			lowercase=1,
			numbers=1,
			special=1,
		)
	except TypeError:
		# 某些发行版使用不同参数名，降级为 None，由下面的自定义校验器处理
		password_policy = None
except Exception:
	password_policy = None
class LoginSchema(Schema):
	'''登录请求模式'''
	username=fields.Str(required=True,validate=validate.Length(min=3,max=65))
	password=fields.Str(required=True,validate=validate.Length(min=8))

class RegisterSchema(Schema):
	'''注册请求模式'''
	username = fields.Str(
			required=True,
			validate=validate.Length(min=4, max=50, error="用户名长度必须在4-50字符之间")
		)
	email = fields.Email(  # 添加 email 字段
        required=True,
        error_messages={'required': '邮箱不能为空', 'invalid': '邮箱格式无效'})
	password = fields.Str(
        required=True,
        validate=[
            validate.Length(min=8, max=20, error="密码长度必须在8-20字符之间"),
            # 密码复杂度校验（二选一即可）
            lambda p: validate_password_complexity(p)
        ]
    )


	@validates_schema
	def validate_fields(self,data,**kwargs):
		'''自定义字段验证'''
		if not validate_username(data.get('username','')):
			raise ValidationError('用户名包含字母，数字和下划线')
		if not validate_email(data.get('email','')):
			raise ValidationError('邮箱格式无效')
		if not validate_password(data.get('password','')):
			raise ValidationError('密码必须包含字母和数字，且长度至少8位')
def validate_password_complexity(password):
	if password_policy is not None:
		try:
			password_policy.test(password)
			return
		except Exception:
			raise ValidationError(
				"密码复杂度不足：需包含大小写字母、数字、特殊字符（!@#$%^&*等），长度8-20位"
			)

	# 回退实现：手动校验常见规则，避免对第三方包过度依赖
	import re
	if not (8 <= len(password) <= 20):
		raise ValidationError("密码长度必须在8-20位之间")
	if not re.search(r"[A-Z]", password):
		raise ValidationError("密码必须包含至少一个大写字母")
	if not re.search(r"[a-z]", password):
		raise ValidationError("密码必须包含至少一个小写字母")
	if not re.search(r"\d", password):
		raise ValidationError("密码必须包含至少一个数字")
	if not re.search(r"[@$!%*?&#^()_+\-=[\]{};':\\\",.<>/?|`~]", password):
		raise ValidationError("密码必须包含至少一个特殊字符")
class ChangePasswordSchema(Schema):
	"""修改密码入参校验"""
	old_password = fields.Str(required=True)
	new_password = fields.Str(
        required=True,
        validate=[
            validate.Length(min=8, max=20, error="密码长度必须在8-20字符之间"),
            lambda p: validate_password_complexity(p)
        ]
    )

class UserSchema(Schema):
	'''用户信息序列化规则，统一换元to_dict输出格式'''
	#基础字段
	id=fields.Integer()
	username=fields.String()
	is_active=fields.Boolean()
	created_at=fields.DateTime()
	last_login=fields.DateTime()
	post_count = fields.Method('get_post_count')
	follower_count = fields.Method('get_follower_count')
	following_count = fields.Method('get_following_count')

	def get_post_count(self, obj):
		return obj.posts.count() if hasattr(obj, 'posts') and obj.posts else 0

	def get_follower_count(self, obj):
		return obj.followers.count() if hasattr(obj, 'followers') and obj.followers else 0

	def get_following_count(self, obj):
		return obj.following.count() if hasattr(obj, 'following') and obj.following else 0
	@post_dump
	def clean_null_values(self,data,**kawargs):
		return {k:v for k,v in data.items() if v is not None}
	
class UserListSchema(Schema):
	"""分页用户列表的序列化规则"""
	items = fields.Nested(UserSchema, many=True)  # 列表项用 UserSchema 序列化
	total = fields.Integer()  # 总条数
	page = fields.Integer()   # 当前页
	size = fields.Integer()   # 每页条数
	pages = fields.Integer()  # 总页数
