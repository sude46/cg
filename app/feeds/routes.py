from flask import current_app, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource, fields

from utils.pagination import get_pagination_params
from utils.response import ResponseCode, fail_response, success_response

from . import feeds_bp
from .services import FeedService

authorizations={
    'Bearer':{
        'type':'apikey',
        'in':'header',
        'name':'Authorization',
        'description':'JWT TOKEN(Bearer token)'
    }
}

api_restx=Api(
    feeds_bp,
    version='1.0',
    title='Feed流API',
    description='提供用户时间线相关的API接口',
    security='Bearer',
    doc='/docs'
)

api=Namespace('feeds',description='时间线相关操作',path='/')

#Swagger请求模型
publish_model=api.model('FeedPublish',{
    'post_id':fields.Integer(required=True,description='帖子ID'),
    'created_at':fields.Float(required=True,description='帖子创建时间戳'),
})

#分页参数
feed_parser=api.parser()
feed_parser.add_argument('page',type=int,default=1,help='页码',location='args')
feed_parser.add_argument('per_page',type=int,default=20,help='每页数量(默认20，最大100)',location='args')


@api.route('/timeline')
class TimelineResource(Resource):
    @api.doc('get_timeline')
    @api.expect(feed_parser)
    @api.response(200,'获取时间线成功')
    @jwt_required()
    def get(self):
        '''获取当前用户的时间线（分页）'''
        current_user_id=get_jwt_identity()
        feed_parser.parse_args()
        page,per_page=get_pagination_params()
        current_app.logger.info(
            f'用户{current_user_id}获取时间线，页码:{page},每页数量:{per_page}'
        )
        result=FeedService.get_timeline(
            user_id=current_user_id,
            page=page,
            per_page=per_page
        )
        return success_response(data=result,message='获取时间线成功'),200

@api.route('/publish')
class FeedPublishResource(Resource):
    @api.doc('publish_post_to_feed')
    @api.expect(publish_model, validate=True)
    @api.response(201, '推送成功')
    @jwt_required()
    def post(self):
        '''发布帖子后触发粉丝推送'''
        current_user_id = get_jwt_identity()
        data = request.get_json()
        post_id = data.get('post_id')
        created_at = data.get('created_at')
        if not post_id or not created_at:
            return fail_response(ResponseCode.PARAM_ERROR, '缺少 post_id 或 created_at'), 400
        current_app.logger.info(
            f'用户{current_user_id}发布帖子{post_id}，开始推送Feed'
        )
        result = FeedService.publish_post(
            post_id=post_id,
            author_id=current_user_id,
            created_at=created_at
        )
        return success_response(data=result, message='推送成功'), 201


@api.route('/refresh')
class FeedRefreshResource(Resource):
    @api.doc('refresh_user_feed')
    @api.response(200, '刷新成功')
    @jwt_required()
    def post(self):
        '''手动刷新当前用户的时间线缓存'''
        current_user_id = get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}手动刷新时间线')
        result = FeedService.refresh_user_feed(user_id=current_user_id)
        return success_response(data=result, message='时间线刷新成功'), 200

api_restx.add_namespace(api)


