from utils.pagination import get_pagination_params
from . import notifications_bp
from flask import request,current_app
from flask_jwt_extended import jwt_required,get_jwt_identity
from flask_restx import Api,Namespace,Resource,fields,reqparse
import traceback

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

from .services import NotificationService
from .schemas import (
        notification_create_schema,
        notification_schema,
        notifications_schema
        )
from app.common.exceptions import (
        ResourceNotFoundError,
        PermissionError,
        ValidationError,
        DatabaseError,
        ConflictError
        )
from  utils.decorators import validate_json,inject_current_user
from utils.response import success_response, fail_response, ResponseCode

api_restx=Api(
        notifications_bp,
        version='1.0',
        title='通知API',
        description='提供通知相关的API接口',
        authorizations=authorizations,
        security='Bearer',
        doc='/docs'
        )
api=Namespace('notifications',description='通知相关操作')

notification_response_model=api.model('NotificationResponse',{
    'id':fields.Integer(readOnly=True,description='通知ID'),
    'user_id':fields.Integer(readOnly=True,description='接收通知的用户ID'),
    'actor_id':fields.Integer(readOnly=True,allow_none=True,description='触发通知的用户ID'),
    'type':fields.String(readOnly=True,description='通知类型'),
    'resource_id':fields.Integer(readOnly=True,allow_none=True,description='相关资源ID'),
    'resource_type':fields.String(readOnly=True,allow_none=True,description='相关资源类型'),
    'content':fields.String(readOnly=True,description='通知内容'),
    'is_read':fields.Boolean(readOnly=True,description='是否已读'),
    'created_at':fields.DateTime(readOnly=True,description='创建时间')
    })
pagination_model=api.model('Pagination',{
    'page':fields.Integer(description='当前页码'),
    'per_page':fields.Integer(description='每页数量'),
    'total':fields.Integer(description='总记录数'),
    'pages':fields.Integer(description='总页数'),
    'has_next':fields.Boolean(description='是否有下一页'),
    'has_prev':fields.Boolean(description='是否有上一页')
    })
notifications_list_response_model=api.model('NotificationsListResponse',{
    'items':fields.List(fields.Nested(notification_response_model),description='通知列表'),
    'pagination':fields.Nested(pagination_model,description='分页信息')
    })

notifications_parser=reqparse.RequestParser()
notifications_parser.add_argument('page',type=int,default=1,help='页码(默认1)',location='args')
notifications_parser.add_argument('per_page',type=int,default=20,help='每页数量(默认20)',location='args')
notifications_parser.add_argument('unread_only',type=bool,default=False,help='是否只显示未读通知',location='args')

@api.route('')
class NotificationListResource(Resource):
    @api.doc('get_user_notifications')
    @api.expect(notifications_parser)
    @api.response(200,'获取通知列表成功',notifications_list_response_model)
    @jwt_required()
    def get(self):
        '''获取当前用户的通知列表'''
        current_user_id=get_jwt_identity()
        args=notifications_parser.parse_args()
        page=args.get('page',1)
        per_page=args.get('per_page',20)
        unread_only=args.get('unread_only',False)
        notifications=NotificationService.get_user_notifications(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page,
                    unread_only=unread_only
                    )
        current_app.logger.info(f'用户{current_user_id}获取通知列表成功')
        return success_response(data=notifications, message='获取通知列表成功'), 200
    @api.doc('create_notification',security='Bearer')
    @api.expect(notification_create_schema,validate=True)
    @api.response(201,'通知创建成功',notification_response_model)
    @jwt_required()
    @validate_json(notification_create_schema)
    def post(self):
        current_user_id=get_jwt_identity()
        data=request.get_json()
        current_app.logger.info(f'用户{current_user_id}尝试创建通知:{data}')
        
        notification=NotificationService.create_notification(data)
        notification_id = notification.get('id') if isinstance(notification, dict) else getattr(notification, 'id', None)
        current_app.logger.info(f'用户{current_user_id}成功创建通知,ID:{notification_id}')
        return success_response(data=notification, message='通知创建成功'), 201


@api.route('/<int:notification_id>')
@api.param('notification_id','通知ID')
class NotificationResource(Resource):
    @api.doc('get_notification')
    @api.response(200,'获取通知详情成功',notification_response_model)
    @jwt_required()
    def get(self,notification_id):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}请求获取通知详情,ID:{notification_id}')
        
        notification=NotificationService.get_notification_by_id(notification_id,current_user_id)
        current_app.logger.info(f'用户{current_user_id}成功获取通知详情,ID:{notification_id}')
        return success_response(data=notification, message='获取通知详情成功'), 200
    @api.doc('delete_notification')
    @api.response(200,'通知删除成功')
    @jwt_required()
    def delete(self,notification_id):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试删除通知,ID:{notification_id}')
        
        NotificationService.delete_notification(notification_id,current_user_id)
        current_app.logger.info(f'用户{current_user_id}成功删除通知,ID:{notification_id}')
        return success_response(message='通知删除成功'), 200    

@api.route('/<int:notification_id>/read')
@api.param('notification_id','通知ID')
class NotificationReadResource(Resource):
    @api.doc('mark_notification_as_read')
    @api.response(200,'标记通知为已读成功',notification_response_model)
    @jwt_required()
    def patch(self,notification_id):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试标记通知已读,ID:{notification_id}')
        
        notification=NotificationService.mark_as_read(notification_id,current_user_id)
        current_app.logger.info(f'用户{current_user_id}成功标记通知为已读,ID:{notification_id}')
        return success_response(data=notification, message='标记通知为已读成功'), 200
@api.route('/read-all')
class NotificationReadAllResource(Resource):
    @api.doc('mark_all_notifications_as_read')
    @api.response(200,'标记所有通知为已读成功')
    @jwt_required()
    def patch(self):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试标记所有通知为已读')
        
        NotificationService.mark_all_as_read(current_user_id)
        current_app.logger.info(f'用户{current_user_id}成功标记所有通知为已读')
        return success_response(message='所有通知已标记为已读'), 200


api_restx.add_namespace(api)



























