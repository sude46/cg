from marshmallow import Schema, ValidationError, fields, post_dump, validate, validates_schema

from utils.schema_fields import UTCDateTime
from utils.validators import (
    validate_email,
    validate_password_complexity,
    validate_password_simple,
    validate_username,
)


class LoginSchema(Schema):
    '''登录请求模式'''
    username = fields.Str(required=True, validate=validate.Length(min=3, max=65))
    password = fields.Str(required=True, validate=validate.Length(min=8))


class RegisterSchema(Schema):
    '''注册请求模式'''
    username = fields.Str(
        required=True,
        validate=validate.Length(min=4, max=50, error="用户名长度必须在4-50字符之间")
    )
    email = fields.Email(
        required=True,
        error_messages={'required': '邮箱不能为空', 'invalid': '邮箱格式无效'})
    password = fields.Str(
        required=True,
        validate=[
            validate.Length(min=8, max=20, error="密码长度必须在8-20字符之间"),
            # 密码复杂度校验（SecurityManager 实现，不满足会抛 ValidationError）
            validate_password_complexity
        ]
    )

    @validates_schema
    def validate_fields(self, data, **kwargs):
        '''自定义字段验证'''
        if not validate_username(data.get('username', '')):
            raise ValidationError('用户名只能包含字母、数字和下划线')
        if not validate_email(data.get('email', '')):
            raise ValidationError('邮箱格式无效')
        if not validate_password_simple(data.get('password', '')):
            raise ValidationError('密码必须包含字母和数字，且长度至少8位')


class ChangePasswordSchema(Schema):
    """修改密码入参校验"""
    old_password = fields.Str(required=True)
    new_password = fields.Str(
        required=True,
        validate=[
            validate.Length(min=8, max=20, error="密码长度必须在8-20字符之间"),
            validate_password_complexity
        ]
    )


class UserSchema(Schema):
    '''用户信息序列化规则，统一换元to_dict输出格式'''
    # 基础字段
    id = fields.Integer()
    username = fields.String()
    email = fields.Email()
    bio = fields.String(allow_none=True)
    avatar_url = fields.String(allow_none=True)
    is_active = fields.Boolean()
    is_admin = fields.Boolean()
    created_at = UTCDateTime()
    last_login = UTCDateTime()
    post_count = fields.Integer(dump_default=0)
    follower_count = fields.Integer(dump_default=0)
    following_count = fields.Integer(dump_default=0)

    @post_dump
    def clean_null_values(self, data, **kwargs):
        return {k: v for k, v in data.items() if v is not None}


class PublicUserSchema(Schema):
    """用户公开资料（不含 email/is_admin/mfa 等隐私字段）"""
    id=fields.Int(dump_only=True)
    username=fields.Str(dump_only=True)
    avatar_url=fields.Str(dump_only=True,allow_none=True)
    bio=fields.Str(dump_only=True,allow_none=True)
    follower_count=fields.Int(dump_only=True,dump_default=0)
    following_count=fields.Int(dump_only=True,dump_default=0)
    post_count=fields.Int(dump_only=True,dump_default=0)
    created_at=UTCDateTime(dump_only=True)

class UpdateProfileSchema(Schema):
    username=fields.Str(required=False,validate=validate.Length(min=4,max=50,error='用户名长度必须在4-50字符之间'))
    email=fields.Email(required=False,error_messages={'invalid':'邮箱格式无效'})
    bio=fields.Str(required=False,validate=validate.Length(max=200))
    avatar_url=fields.Str(required=False,validate=validate.Length(max=500))

    @validates_schema
    def at_least_one(self,data,**kwargs):
        if not any(k in data for k in ('username','email','bio','avatar_url')):
            raise ValidationError("至少提供一个要修改的字段")


update_profile_schema=UpdateProfileSchema()
public_user_schema=PublicUserSchema()

