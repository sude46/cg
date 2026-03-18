from flask import request,jsonify,g
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from flask_restx import Resource, fields, Namespace,Api
from . import users_bp
from .services import AuthService
from .schemas import LoginSchema,RegisterSchema
from utils.decorators import validate_json,rate_limit
from app.common.exceptions import (
	ResourceNotFoundError,
	PermissionError,
	ValidationError,
	DatabaseError,
	ConflictError,
	AuthenticationError
	)
import logging
from utils.security_utils import desensitize_data
from utils.response import success_response,fail_response,ResponseCode
from datetime import datetime
from utils.redis_util import redis_client


api_restx=Api(
	users_bp,	
	version='1.0',
	title='用户API',
	description='提供用户相关的API接口',
	security='Bearer',
	doc='/docs'		
)
api=Namespace('',description='用户相关操作',security='Bearer')
logger=logging.getLogger(__name__)

@api.route('/register')
class Register(Resource):
	@api.doc(description='用户注册')
	@api.response(201,'用户注册成功')
	@api.response(400,'参数错误')
	@api.response(409,'用户名或邮箱已存在')
	@validate_json(RegisterSchema)
	@rate_limit(10)
	def post(self):
		data=request.get_json()
		try:
			result=AuthService.register_user(
				username=data['username'],
				email=data['email'],
				password=data['password']
				)
			return success_response(data=result,message='用户注册成功'),201
		except ConflictError as e:
			return fail_response(code=ResponseCode.CONFLICT,error_msg=str(e)),409
		except ValidationError as e:
			return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
		except Exception as e:
			return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),500

@api.route('/login')
class Login(Resource):
	@api.doc(description='用户登录')
	@api.response(200,'登录成功')
	@api.response(400,'参数错误')
	@api.response(401,'认证失败')
	@validate_json(LoginSchema)
	@rate_limit(20)
	def post(self):
		'''用户登录'''
		data=request.get_json()
		try:
			validated_data = g.validated_json
			username = validated_data.get("username")
			password = validated_data.get("password")

				# 2. 脱敏敏感信息（密码）
			desensitized_data = desensitize_data(validated_data)
			logger.info(
					f"Login attempt for username: {username}",
					extra={**g.log_extra, "request_data": desensitized_data}
				)

				# 3. 调用服务层逻辑
			user, access_token, refresh_token = AuthService.verify_user_and_generate_tokens(
					username, password
				)

				# 4. 脱敏返回的Token（避免日志泄露）
			desensitized_tokens = {
					"access_token": desensitize_data(access_token),
					"refresh_token": desensitize_data(refresh_token)
				}
			logger.info(
					f"Login success for username: {username}",
					extra={**g.log_extra, "tokens": desensitized_tokens}
				)

			return   success_response(data={
                "user_info": user,
                "access_token": access_token,
                "refresh_token": refresh_token
            },
            message="登录成功")
		except ValidationError as e:
			return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
		except PermissionError as e:
			return fail_response(code=ResponseCode.PERMISSION_DENIED,error_msg=str(e)),401
		except Exception as e:
			return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),500
@api.route('/refresh')
class RefreshToken(Resource):
	@api.doc(description='刷新访问令牌')
	@api.response(200,'令牌刷新成功')
	@api.response(401,'刷新令牌无效')
	@jwt_required(refresh=True)
	def post(self):
		'''刷新访问令牌'''
		current_user_id=get_jwt_identity()
		try:
			result=AuthService.refresh_token(current_user_id)
			return success_response(data=result,message='令牌刷新成功'),200
		except Exception as e:
			return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),401

@api.route('/me')
class CurrentUser(Resource):
	@api.doc(description='获取当前用户信息')
	@api.response(200,'获取成功')
	@api.response(401,'未认证')
	@api.response(404,'用户不存在')
	@jwt_required()
	def get(self):
		current_user_id=get_jwt_identity()
		try:
			result=AuthService.get_current_user(current_user_id)
			return success_response(data=result),200
		except ResourceNotFoundError as e:
			return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
		except Exception as e:
			return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg=str(e)),500
@api.route('/logout')
class Logout(Resource):
	@api.doc(description='用户登出')
	@api.response(200,'登出成功')
	@api.response(401,'未认证')
	@jwt_required()
	def post(self):
		try:
			# 1. 获取当前Token的信息
			jwt_payload = get_jwt()
			jti = jwt_payload["jti"]  # Token唯一标识
			token_type = jwt_payload.get("type", "access")
			exp = jwt_payload["exp"]  # Token过期时间（时间戳）
        
        # 2. 计算Token剩余有效期（秒）：避免黑名单永久存储，节省Redis空间
			now = datetime.utcnow().timestamp()
			remain_seconds = max(0, int(exp - now))
			
			# 3. 将Token加入黑名单（设置与剩余有效期一致的过期时间）
			redis_client.add_blacklist(jti, remain_seconds)
			
			# 4. 返回统一响应
			return success_response(
				data=None,
				message=f"{token_type}令牌已失效，登出成功"
			), 200
    
		except Exception as e:
			from flask import current_app
			current_app.logger.error(f"登出失败：{str(e)}")
			return fail_response(ResponseCode.SERVER_ERROR, "登出失败，请稍后再试"), 500



api_restx.add_namespace(api)
