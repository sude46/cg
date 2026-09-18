from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource, fields

from middlewares import route_limit
from utils.decorators import validate_json
from utils.pagination import get_pagination_params
from utils.response import paginated_response, success_response

from . import follows_bp
from .schemas import FollowCreateSchema
from .services import FollowService

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

api_restx=Api(
        follows_bp,
        version='1.0',
        title='关注API',
        description='提供关注相关的API接口',
        authorizations=authorizations,
        security='Bearer',
        doc='/docs'
)

#创建命名空间
api=Namespace('follows',description='关注相关操作',path='/')

# Swagger请求模型
follow_create_model = api.model('FollowCreate', {
    'followed_id': fields.Integer(required=True, description='被关注用户ID')
})

@api.route('/following')  # 修正：路由语义化
class FollowOperation(Resource):
    @api.doc(
            description='关注用户',
            security='Bearer'
            )
    @api.expect(follow_create_model, validate=False)
    @api.response(201,'关注成功')
    @jwt_required()
    @validate_json(FollowCreateSchema)
    @route_limit("30 per minute")
    def post(self):
        '''创建关注关系'''

        data=request.get_json()
        current_user_id=get_jwt_identity()
        result=FollowService.follow_user(
                    follower_id=current_user_id,
                    followed_id=data['followed_id']
                    )
        return success_response(data=result,message='关注成功'),201



@api.route('/following/<int:followed_id>')
class UnfollowOperation(Resource):
    @api.doc(
            description='取消关注用户',
            params={'followed_id':'被取消关注的用户ID'},
            security='apiKey'
            )
    @api.response(200,'取消成功' )
    @jwt_required()
    def delete(self,followed_id):

        current_user_id=get_jwt_identity()
        result=FollowService.unfollow_user(
                    follower_id=current_user_id,
                    followed_id=followed_id
                    )
        return success_response(data=result,message='取消关注成功'),200

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

    @jwt_required()
    def get(self):
        '''查询当前用户的关注列表'''

        # 修正：request.arg.get -> request.args.get
        page,per_page=get_pagination_params()
        current_user_id=get_jwt_identity()
        result=FollowService.get_following(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page
                    )
        return paginated_response(result['items'], result['pagination'], message='获取成功'),200
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
    @jwt_required()
    def get(self):

        page,per_page=get_pagination_params()
        current_user_id=get_jwt_identity()
        result=FollowService.get_followers(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page
                    )
        return paginated_response(result['items'], result['pagination'], message='获取成功'),200
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
    @jwt_required()
    def get(self):
        '''获取当前用户的互相关注用户列表'''

        page,per_page=get_pagination_params()
        current_user_id=get_jwt_identity()
        result=FollowService.get_mutual_follows(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page
                    )
        return paginated_response(result['items'], result['pagination'], message='获取成功'),200
api_restx.add_namespace(api)














