from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restx import Resource, fields, Namespace,Api
from . import likes_bp
from .services import LikeService
from .schemas import like_schema, likes_schema, like_create_schema
from utils.decorators import validate_json, rate_limit
from app.common.exceptions import ResourceNotFoundError, ValidationError, ConflictError  # 导入冲突异常
from utils.response import success_response, fail_response, ResponseCode
 
api_restx=Api(
    likes_bp,
    version='1.0',
    title='点赞API',
    description='提供点赞相关的API接口',
    security='Bearer',
    doc='/docs'  
)
api=Namespace('likes', description='点赞相关操作', security='Bearer')

@api.route('')
class LikeOperation(Resource):
    @api.doc(description='点赞（兼容路由，推荐使用 /posts/{id}/likes）')
    @api.response(201, '点赞成功')
    @api.response(400, '参数错误（post_id/comment_id二选一）')
    @api.response(404, '点赞对象不存在')
    @api.response(409, '已点赞（冲突）')  # 修正：新增409状态码
    @jwt_required()
    @validate_json(like_create_schema)
    @rate_limit(60)
    def post(self):
        """创建点赞"""
        data = request.get_json()
        current_user_id = get_jwt_identity()

        try:
            result = LikeService.create_like(
                user_id=current_user_id, post_id=data.get('post_id'), comment_id=data.get('comment_id')
            )
            return success_response(
                data=result,
                message='点赞成功'
            ), 201
        except ConflictError as e:  # 处理已点赞冲突
            return fail_response(
                code=ResponseCode.CONFLICT,
                error_msg=str(e)
            ), 409
        except ResourceNotFoundError as e:  # 处理点赞对象不存在
            return fail_response(
                code=ResponseCode.RESOURCE_NOT_FOUND,
                error_msg=str(e)
            ), 404
        except ValidationError as e:  # 处理参数错误
            return fail_response(
                code=ResponseCode.VALIDATION_ERROR,
                error_msg=str(e)
            ), 400
        except Exception as e:
            return fail_response(
                code=ResponseCode.INTERNAL_ERROR,
                error_msg='服务器内部错误'
            ), 500

    @api.doc(description='取消点赞（兼容路由，推荐使用 /posts/{id}/likes/{like_id}）')
    @api.response(200, '取消点赞成功')
    @api.response(400, '参数错误')
    @api.response(404, '未找到点赞记录')
    @jwt_required()
    @validate_json(like_create_schema)
    def delete(self):
        """取消点赞"""
        data = request.get_json()
        current_user_id = get_jwt_identity()

        try:
            result = LikeService.delete_like(
                user_id=current_user_id, post_id=data.get('post_id'), comment_id=data.get('comment_id')
            )
            return success_response(
                data=result,
                message='取消点赞成功'
            ), 200
        except ResourceNotFoundError as e:  # 处理未找到点赞记录
            return fail_response(
                code=ResponseCode.RESOURCE_NOT_FOUND,
                error_msg=str(e)
            ), 404
        except ValidationError as e:
            return fail_response(
                code=ResponseCode.VALIDATION_ERROR,
                error_msg=str(e)
            ), 400
        except Exception as e:
            return fail_response(
                code=ResponseCode.INTERNAL_ERROR,
                error_msg='服务器内部错误'
            ), 500
@api.route('/posts/<int:post_id>/likes')
class PostLikeResource(Resource):
    @api.doc('点赞帖子')
    @api.response(201, '点赞成功')
    @api.response(401, '未认证')
    @api.response(404, '帖子不存在')
    @api.response(409, '已点赞')
    @jwt_required()
    @rate_limit(60)
    def post(self, post_id):
        """点赞帖子（/posts/{post_id}/likes）"""
        current_user_id = get_jwt_identity()
        try:
            result = LikeService.create_like(user_id=current_user_id, post_id=post_id)
            return success_response(
                data=result,
                message='点赞成功'
            ), 201
        except ConflictError as e:
            return fail_response(
                code=ResponseCode.CONFLICT,
                error_msg=str(e)
            ), 409
        except ResourceNotFoundError as e:
            return fail_response(
                code=ResponseCode.RESOURCE_NOT_FOUND,
                error_msg=str(e)
            ), 404
        except Exception as e:
            return fail_response(
                code=ResponseCode.INTERNAL_ERROR,
                error_msg='服务器内部错误'
            ), 500

# 取消点赞带like_id（符合 /posts/{id}/likes/{like_id} 规范）
@api.route('/posts/<int:post_id>/likes/<int:like_id>')
class PostUnlikeResource(Resource):
    @api.doc('取消帖子点赞')
    @api.response(200, '取消点赞成功')
    @api.response(401, '未认证')
    @api.response(403, '无权限取消该点赞')
    @api.response(404, '点赞记录/帖子不存在')
    @jwt_required()
    def delete(self, post_id, like_id):
        """取消帖子点赞"""
        current_user_id = get_jwt_identity()
        try:
            result = LikeService.delete_like_by_id(user_id=current_user_id, like_id=like_id, post_id=post_id)
            return success_response(
                data=result,
                message='取消点赞成功'
            ), 200
        except PermissionError as e:
            return fail_response(
                code=ResponseCode.PERMISSION_DENIED,
                error_msg=str(e)
            ), 403
        except ResourceNotFoundError as e:
            return fail_response(
                code=ResponseCode.RESOURCE_NOT_FOUND,
                error_msg=str(e)
            ), 404
        except Exception as e:
            return fail_response(
                code=ResponseCode.INTERNAL_ERROR,
                error_msg='服务器内部错误'
            ), 500

@api.route('/my-likes')
class UserLikes(Resource):
    @api.doc(
        description='查询当前用户的所有点赞记录',
        params={'page': '页码', 'per_page': '每页数量（默认20，最大100）'},
    )
    @api.response(200, '查询成功')
    @api.response(401, '未认证')
    @api.response(400, '参数错误')
    @jwt_required()
    def get(self):
        """获取当前用户的点赞列表"""
        current_user_id = get_jwt_identity()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        # 限制per_page最大值
        per_page = min(per_page, 100)
        try:
            result = LikeService.get_user_likes(user_id=current_user_id, page=page, per_page=per_page)
            return success_response(data=result), 200
        except ValidationError as e:
            return fail_response(code=ResponseCode.VALIDATION_ERROR, error_msg=str(e)), 400
        except Exception as e:
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg='服务器内部错误'), 500

api_restx.add_namespace(api)

        



