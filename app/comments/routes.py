
from flask import current_app, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource, fields, reqparse

from utils.decorators import validate_json
from utils.pagination import get_pagination_params
from utils.response import paginated_response, success_response

from . import comments_bp
from .schemas import comment_create_schema, comment_update_schema
from .services import CommentService

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

api_restx=Api(
        comments_bp,
        version='1.0',
        title='评论API',
        description='提供评论相关的API接口',
        authorizations=authorizations,
        security='Bearer',
        doc='/docs'
        )
api=Namespace('comments',description='评论相关操作',path='/')

# Swagger请求模型
comment_create_model = api.model('CommentCreate', {
    'post_id': fields.Integer(required=True, description='帖子ID'),
    'content': fields.String(required=True, description='评论内容（1-500字符）')
})

comment_update_model = api.model('CommentUpdate', {
    'content': fields.String(required=True, description='评论内容（1-500字符）')
})


comments_parser=reqparse.RequestParser()
comments_parser.add_argument('page',type=int,default=1,help='页码',location='args')
comments_parser.add_argument('per_page',type=int,default=20,help='每页数量（默认20，最大100）',location='args')


@api.route('')
class CommentListResource(Resource):
    @api.doc('create_comment')
    @api.expect(comment_create_model, validate=False)
    @api.response(201,'评论创建成功')
    @jwt_required()
    @validate_json(comment_create_schema)
    def post(self):
        '''创建新评论'''
        current_user_id=get_jwt_identity()
        data=request.get_json()
        current_app.logger.info(f'用户{current_user_id}尝试创建新评论:{data}')

        result=CommentService.create_comment(user_id=current_user_id,data=data)
        comment_id = result['comment'].get('id') if isinstance(result['comment'], dict) else getattr(result['comment'], 'id', None)
        current_app.logger.info(f'用户{current_user_id}成功创建评论,评论ID:{comment_id}')
        return success_response(data=result['comment']),201

@api.route('/<int:comment_id>')
@api.param('comment_id','评论ID')
class CommentResource(Resource):
    @api.doc('get_comment')
    @api.response(200,'获取评论成功')
    def get(self,comment_id):
        '''根据ID获取评论详情'''
        current_app.logger.debug(f'尝试获取评论详情，评论ID:{comment_id}')
        comment_data=CommentService.get_comment_by_id(comment_id)
        current_app.logger.info(f'成功获取评论详情，评论ID:{comment_id}')
        return success_response(data=comment_data),200

    @api.doc('update_comment')
    @api.response(200,'评论更新成功')
    @jwt_required()
    @validate_json(comment_update_schema)
    def put(self,comment_id):
        '''更新评论内容'''
        current_user_id=get_jwt_identity()
        data=request.get_json()
        current_app.logger.info(f'用户{current_user_id}尝试更新评论，评论ID:{comment_id},新内容{data}')

        result=CommentService.update_comment(comment_id=comment_id,user_id=current_user_id,data=data)
        current_app.logger.info(f'用户{current_user_id}成功更新评论,评论ID:{comment_id}')
        return success_response(data=result,message='评论更新成功'),200

    @api.doc('delete_comment')
    @api.response(200,'评论删除成功')
    @jwt_required()
    def delete(self,comment_id):
        '''删除评论'''
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试删除评论,评论ID:{comment_id}')

        CommentService.delete_comment(comment_id=comment_id,user_id=current_user_id)
        current_app.logger.info(f'用户{current_user_id}成功删除评论,评论ID:{comment_id}')
        return success_response(message='评论删除成功'),200

@api.route('/posts/<int:post_id>/comments')
@api.param('post_id','帖子ID')
class PostCommentsResource(Resource):
    @api.doc('get_post_comments')
    @api.expect(comments_parser)
    @api.response(200,'获取帖子评论成功')
    def get(self, post_id):
        '''根据帖子ID获取评论列表（符合 /posts/{id}/comments 层级）'''
        comments_parser.parse_args()
        page,per_page=get_pagination_params()
        current_app.logger.info(f'尝试获取帖子ID{post_id}的评论列表，页码:{page},每页数量:{per_page}')


        result=CommentService.get_comments_by_post_id(
                    post_id=post_id,
                    page=page,
                    per_page=per_page
                    )
        current_app.logger.info(f'成功获取帖子ID{post_id}的评论列表，共{result["pagination"]["total"]}条评论')
        return paginated_response(result['items'], result['pagination'], message='获取评论列表成功'),200

api_restx.add_namespace(api)


