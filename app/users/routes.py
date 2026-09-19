import logging
from datetime import UTC, datetime

from flask import current_app, g, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource, fields

from middlewares import route_limit
from utils.decorators import validate_json
from utils.formatters import desensitize_data, desensitize_token
from utils.pagination import get_pagination_params
from utils.response import ResponseCode, fail_response, paginated_response, success_response

from . import users_bp
from .schemas import (
    ChangePasswordSchema,
    LoginSchema,
    RegisterSchema,
    UpdateProfileSchema,
)
from .services.auth_service import AuthService

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

api_restx=Api(
    users_bp,
    version='1.0',
    title='用户API',
    description='提供用户相关的API接口',
    authorizations=authorizations,
    security='Bearer',
    doc='/docs'
)
api=Namespace('',description='用户相关操作')
logger=logging.getLogger(__name__)

# 定义注册请求模型（用于Swagger文档）
register_model = api.model('RegisterRequest', {
    'username': fields.String(required=True, description='用户名（4-50字符）'),
    'email': fields.String(required=True, description='邮箱地址'),
    'password': fields.String(required=True, description='密码（8-20字符，需包含大小写字母和数字）')
})

login_model = api.model('LoginRequest', {
    'username': fields.String(required=True, description='用户名'),
    'password': fields.String(required=True, description='密码')
})

update_profile_model=api.model('UpdateProfileRequest',{
    'bio':fields.String(required=False,description='个人简介(最长200字符)'),
    'avatar_url':fields.String(required=False,description='头像URL')
    })
change_password_model=api.model('ChangePasswordRequest',{
    'old_password':fields.String(required=True,description='原密码'),
    'new_password':fields.String(required=True,description='新密码(8-20字符)')
    })


@api.route('/register')
class Register(Resource):
    @api.doc(description='用户注册')
    @api.expect(register_model, validate=False)  # 使用自定义验证
    @api.response(201,'用户注册成功')
    @validate_json(RegisterSchema)
    @route_limit("5 per minute")
    def post(self):
        data=request.get_json()

        result=AuthService.register_user(
                username=data['username'],
                email=data['email'],
                password=data['password']
                )
        return success_response(data=result,message='用户注册成功'),201


@api.route('/login')
class Login(Resource):
    @api.doc(description='用户登录')
    @api.expect(login_model, validate=False)
    @api.response(200,'登录成功')
    @validate_json(LoginSchema)
    @route_limit("10 per minute")
    def post(self):
        '''用户登录'''
        data=request.get_json()

        validated_data = getattr(g, 'validated_json', data)
        username = validated_data.get("username")
        password = validated_data.get("password")

                # 2. 脱敏敏感信息（密码）
        desensitized_data = desensitize_data(validated_data)
        logger.info(
                    f"Login attempt for username: {username}",
                    extra={**getattr(g, 'log_extra', {}), "request_data": desensitized_data}
                )

                # 3. 调用服务层逻辑
        auth_result = AuthService.authenticate_user(
                    username, password
                )

                # 4. 脱敏返回的Token（避免日志泄露）
        desensitized_tokens = {
                    "access_token": desensitize_token(auth_result['access_token']),
                    "refresh_token": desensitize_token(auth_result['refresh_token'])
                }
        logger.info(
                    f"Login success for username: {username}",
                    extra={**getattr(g, 'log_extra', {}), "tokens": desensitized_tokens}
                )

        return success_response(data={
                "user_info": auth_result['user'],
                "access_token": auth_result['access_token'],
                "refresh_token": auth_result['refresh_token']
            },
            message="登录成功")

@api.route('/refresh')
class RefreshToken(Resource):
    @api.doc(description='刷新访问令牌')
    @api.response(200,'令牌刷新成功')
    @jwt_required(refresh=True)
    def post(self):
        '''刷新访问令牌'''
        current_user_id=get_jwt_identity()

        result=AuthService.refresh_token(current_user_id)
        return success_response(data=result,message='令牌刷新成功'),200


@api.route('/me')
class CurrentUser(Resource):
    @api.doc(description='获取当前用户信息')
    @api.response(200,'获取成功')
    @jwt_required()
    def get(self):
        current_user_id=get_jwt_identity()

        result=AuthService.get_current_user(current_user_id)
        return success_response(data=result),200

    @api.doc(description='更新当前用户资料（bio / avatar_url）')
    @api.response(200, '更新成功')
    @jwt_required()
    @validate_json(UpdateProfileSchema)
    def put(self):
        """更新当前用户资料"""
        data = getattr(g, 'validated_json', request.get_json())
        result = AuthService.update_profile(get_jwt_identity(), data)
        return success_response(data=result, message='资料更新成功'), 200

@api.route('/search')
class UserSearch(Resource):
    @api.doc(description='按用户名搜索用户', params={'q': '关键词', 'page': '页码', 'per_page': '每页数量'})
    @api.response(200, '搜索成功')
    @jwt_required(optional=True)
    def get(self):
        """按用户名搜索用户（结果脱敏，不含 email）"""
        keyword = request.args.get('q', '').strip()
        if not keyword:
            return fail_response(ResponseCode.VALIDATION_ERROR, '搜索关键词不能为空'), 400
        page, per_page = get_pagination_params()
        result = AuthService.search_users(keyword, page=page, per_page=per_page)
        return paginated_response(result['items'], result['pagination'], message='搜索用户成功'), 200


@api.route('/<int:user_id>')
class UserProfile(Resource):
    @api.doc(description='获取用户公开资料', params={'user_id': '用户ID'})
    @api.response(200, '获取成功')
    @jwt_required(optional=True)
    def get(self,user_id):
        """获取用户公开资料（未登录也可访问）"""
        current_user_id=get_jwt_identity()
        result=AuthService.get_public_profile(user_id,current_user_id)
        return success_response(data=result,message='获取用户资料成功'),200

@api.route('/logout')
class Logout(Resource):
    @api.doc(description='用户登出')
    @api.response(200,'登出成功')
    @jwt_required()
    def post(self):

            # 1. 获取当前Token的信息
        jwt_payload = get_jwt()
        jti = jwt_payload["jti"]  # Token唯一标识
        token_type = jwt_payload.get("type", "access")
        exp = jwt_payload["exp"]  # Token过期时间（时间戳）

        # 2. 计算Token剩余有效期（秒）：避免黑名单永久存储，节省Redis空间
        now = datetime.now(UTC).timestamp()
        remain_seconds = max(0, int(exp - now))
        current_app.revoke_token(jti,remain_seconds)
            # 4. 返回统一响应
        return success_response(
                data=None,
                message=f"{token_type}令牌已失效，登出成功"
            ), 200

@api.route('/me/password')
class ChangePassword(Resource):
    @api.doc(description='修改当前用户密码')
    @api.response(200, '修改成功')
    @jwt_required()
    @validate_json(ChangePasswordSchema)
    @route_limit("5 per minute")
    def put(self):
        """修改密码"""
        data = getattr(g, 'validated_json', request.get_json())
        result = AuthService.change_password(
            get_jwt_identity(), data['old_password'], data['new_password']
        )
        return success_response(data=result, message='密码修改成功'), 200




api_restx.add_namespace(api)
