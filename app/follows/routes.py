from flask import request,jsonify
from flask_jwt_extended import jwt_required,get_jwt_identity
from flask_restx import Api,Resource,fields,Namespace
from . import follows_bp
from .services import FollowService
from .schemas import FollowCreateSchema
from utils.decorators import validate_json,rate_limit,inject_current_user
from app.common.exceptions import ResourceNotFoundError, ConflictError, PermissionError ,ValidationError # 导入异常
from utils.response import success_response,fail_response,ResponseCode
from utils.pagination import get_pagination_params

api_restx=Api(
        follows_bp,
        version='1.0',
        title='关注API',
        description='提供关注相关的API接口',
        security='Bearer',
        doc='/docs'
)

#创建命名空间
api=Namespace('follows',description='关注相关操作',security='Bearer')

@api.route('/following')  # 修正：路由语义化
class FollowOperation(Resource):
    @api.doc(
            description='关注用户',
            security='apiKey'
            )
    @api.response(201,'关注成功')
    @api.response(400,'参数错误' )
    @api.response(401,'未认证' )
    @api.response(404,'被关注用户不存在')
    @api.response(409,'已关注该用户（冲突）')  # 新增409状态码
    @jwt_required()
    @validate_json(FollowCreateSchema)
    @rate_limit(30)
    def post(self):
        '''创建关注关系'''
        try:
            data=request.get_json()
            current_user_id=get_jwt_identity()
            result=FollowService.follow_user(
                    follower_id=current_user_id,
                    followed_id=data['followed_id']
                    )
            return success_response(data=result,message='关注成功'),201
        except ValidationError as e:
            return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
        except ResourceNotFoundError as e:  # 被关注用户不存在
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except ConflictError as e:  # 已关注
            return fail_response(code=ResponseCode.CONFLICT,error_msg=str(e)),409
        except Exception as e:
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500

# 修正：取消关注路由语义化，添加followed_id
@api.route('/following/<int:followed_id>')
class UnfollowOperation(Resource):
    @api.doc(
            description='取消关注用户',
            params={'followed_id':'被取消关注的用户ID'},
            security='apiKey'
            )
    @api.response(200,'取消成功' )
    @api.response(401,'未认证' )
    @api.response(404,'未关注该用户/用户不存在' )
    @jwt_required()
    def delete(self,followed_id):
        try:
            current_user_id=get_jwt_identity()
            result=FollowService.unfollow_user(
                    follower_id=current_user_id,
                    followed_id=followed_id
                    )
            return success_response(data=result,message='取消关注成功'),200
        except ResourceNotFoundError as e:  # 未关注/用户不存在
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except Exception as e:
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500
@api.route('/following/list')  # 修正：路由语义化，避免与关注操作冲突
class Following(Resource):
    @api.doc(
            description='获取当前用户关注的列表',
            params={
                'page':'页码，默认1',
                'per_page':'每页数量，默认20'
                },
            security='apiKey'
            )
    @api.response(200,'获取成功' )
    @api.response(401,'未认证' )
    @api.response(400,'参数获取错误' )
    @jwt_required()
    def get(self):
        '''查询当前用户的关注列表'''
        try:
            # 修正：request.arg.get -> request.args.get
            page,per_page=get_pagination_params()
            current_user_id=get_jwt_identity()
            result=FollowService.get_following(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page
                    )
            return success_response(data=result),200
        except ValidationError as e:
            return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
        except Exception as e:
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500
@api.route('/followers')
class FollowerList(Resource):
    @api.doc(
            description='获取当前用户的粉丝列表',
            params={
                'page':'页码,默认1',
                'per_page':'每页数量，默认20'
                },
            security='apiKey'
            )
    @api.response(200,'获取成功')
    @api.response(401,'未认证')
    @api.response(400,'参数错误')
    @jwt_required()
    def get(self):
        try:
            page,per_page=get_pagination_params()
            current_user_id=get_jwt_identity()
            result=FollowService.get_followers(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page
                    )
            return success_response(data=result,message='获取成功'),200
        except ValidationError as e:
            return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
        except Exception as e:
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500
@api.route('/following/mutual')
class MutualFollowList(Resource):
    @api.doc(
            description='获取当前用户的互相关注的用户列表(双向关注)',
            params={
                'page':'页码，默认1',
                'per_page':'每页数量,默认20'
                },
            security='apiKey'
            )
    @api.response(200,'获取成功')
    @api.response(401,'未认证')
    @api.response(400,'参数错误')
    @api.response(404,'用户不存在')
    @jwt_required()
    def get(self):
        '''获取当前用户的互相关注用户列表'''
        try:
            page,per_page=get_pagination_params()
            current_user_id=get_jwt_identity()
            result=FollowService.get_mutual_follows(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page
                    )
            return success_response(data=result,message='获取成功'),200
        except ResourceNotFoundError as e:
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND,error_msg=str(e)),404
        except ValidationError as e:
            return fail_response(code=ResponseCode.VALIDATION_ERROR,error_msg=str(e)),400
        except Exception as e:
            return fail_response(code=ResponseCode.INTERNAL_ERROR,error_msg='服务器内部错误'),500

api_restx.add_namespace(api)














