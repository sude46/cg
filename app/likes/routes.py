from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource, fields

from middlewares import route_limit
from utils.decorators import validate_json
from utils.response import paginated_response, success_response

from . import likes_bp
from .schemas import like_create_schema
from .services import LikeService

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

api_restx=Api(
    likes_bp,
    version='1.0',
    title='点赞API',
    description='提供点赞相关的API接口',
    authorizations=authorizations,
    security='Bearer',
    doc='/docs'
)
api=Namespace('likes', description='点赞相关操作', path='/')

# Swagger请求模型
like_create_model = api.model('LikeCreate', {
    'post_id': fields.Integer(required=False, description='帖子ID（post_id和comment_id二选一）'),
    'comment_id': fields.Integer(required=False, description='评论ID（post_id和comment_id二选一）')
})

@api.route('')
class LikeOperation(Resource):
    @api.doc(description='点赞（兼容路由，推荐使用 /posts/{id}/likes）')
    @api.expect(like_create_model, validate=False)
    @api.response(201, '点赞成功')
    @jwt_required()
    @validate_json(like_create_schema)
    @route_limit("30 per minute")
    def post(self):
        """创建点赞"""
        data = request.get_json()
        current_user_id = get_jwt_identity()


        result = LikeService.create_like(
                user_id=current_user_id, post_id=data.get('post_id'), comment_id=data.get('comment_id')
            )
        return success_response(
                data=result,
                message='点赞成功'
            ), 201

    @api.doc(description='取消点赞（兼容路由，推荐使用 /posts/{id}/likes/{like_id}）')
    @api.response(200, '取消点赞成功')
    @jwt_required()
    @validate_json(like_create_schema)
    def delete(self):
        """取消点赞"""
        data = request.get_json()
        current_user_id = get_jwt_identity()


        result = LikeService.delete_like(
                user_id=current_user_id, post_id=data.get('post_id'), comment_id=data.get('comment_id')
            )
        return success_response(
                data=result,
                message='取消点赞成功'
            ), 200

@api.route('/posts/<int:post_id>/likes')
class PostLikeResource(Resource):
    @api.doc('点赞帖子')
    @api.response(201, '点赞成功')
    @jwt_required()
    @route_limit("60 per minute")
    def post(self, post_id):
        """点赞帖子（/posts/{post_id}/likes）"""
        current_user_id = get_jwt_identity()

        result = LikeService.create_like(user_id=current_user_id, post_id=post_id)
        return success_response(
                data=result,
                message='点赞成功'
            ), 201


# 取消点赞带like_id（符合 /posts/{id}/likes/{like_id} 规范）
@api.route('/posts/<int:post_id>/likes/<int:like_id>')
class PostUnlikeResource(Resource):
    @api.doc('取消帖子点赞')
    @api.response(200, '取消点赞成功')
    @jwt_required()
    def delete(self, post_id, like_id):
        """取消帖子点赞"""
        current_user_id = get_jwt_identity()

        result = LikeService.delete_like_by_id(user_id=current_user_id, like_id=like_id, post_id=post_id)
        return success_response(
                data=result,
                message='取消点赞成功'
            ), 200

@api.route('/my-likes')
class UserLikes(Resource):
    @api.doc(
        description='查询当前用户的所有点赞记录',
        params={'page': '页码', 'per_page': '每页数量（默认20，最大100）'},
    )
    @api.response(200, '查询成功')
    @jwt_required()
    def get(self):
        """获取当前用户的点赞列表"""
        current_user_id = get_jwt_identity()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        # 限制per_page最大值
        per_page = min(per_page, 100)

        result = LikeService.get_user_likes(user_id=current_user_id, page=page, per_page=per_page)
        return paginated_response(result['items'], result['pagination'], message='查询成功'), 200


api_restx.add_namespace(api)





