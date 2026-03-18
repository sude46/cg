from utils.pagination import get_pagination_params
from . import notifications_bp
from flask import request,current_app
from flask_jwt_extended import jwt_required,get_jwt_identity
from flask_restx import Api,Namespace,Resource,fields,reqparse
import traceback
from .import notifications_bp
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
        security='Bearer',
        doc='/docs'
        )
api=Namespace('notifications',description='通知相关操作',security='Bearer')

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
    @api.response(401,'未认证')
    @jwt_required()
    def get(self):
        '''获取当前用户的通知列表'''
        current_user_id=get_jwt_identity()
        args=notifications_parser.parse_args()
        page=args.get('page',1)
        unread_only=args.get('unread_only',False)
        try:
            notifications=NotificationService.get_user_notifications(
                    user_id=current_user_id,
                    page=page,
                    per_page=per_page,
                    unread_only=unread_only
                    )
            current_app.logger.info(f'用户{current_user_id}获取通知列表成功')
            return success_response(data=notifications, message='获取通知列表成功'), 200
        except ValidationError as e:
            current_app.logger.error(f'用户{current_user_id}获取通知列表失败:{e}\n{traceback.format_exc()}')
            return fail_response(code=ResponseCode.VALIDATION_ERROR, error_msg=str(e)), 400
        except Exception as e:
            current_app.logger.error(f'用户{current_user_id}获取通知列表失败:{e}\n{traceback.format_exc()}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg='服务器内部错误'), 500
    @api.doc('create_notification',security='Bearer')
    @api.expect(notification_create_schema,validate=True)
    @api.response(201,'通知创建成功',notification_response_model)
    @api.response(400,'参数错误')
    @api.response(401,'未认证')
    @api.response(409,'通知冲突')
    @jwt_required()
    @validate_json(notification_create_schema)
    def post(self):
        current_user_id=get_jwt_identity()
        data=request.get_json()
        current_app.logger.info(f'用户{current_user_id}尝试床架通知:{data}')
        try:
            notification=NotificationService.create_notification(data)
            current_app.logger.info(f'用户{current_user_id}成功创建通知,ID:{notification.id}')
            return success_response(data=notification, message='通知创建成功'), 201
        except ValidationError as e:
            current_app.logger.error(f'用户{current_user_id}创建通知失败:{e}')
            return fail_response(code=ResponseCode.VALIDATION_ERROR, error_msg=str(e)), 400
        except ResourceNotFoundError as e:
            current_app.logger.error(f'用户{current_user_id}创建通知失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND, error_msg=str(e)), 404
        except ConflictError as e:
            current_app.logger.warning(f'用户{current_user_id}创建通知失败:{e}')
            return fail_response(code=ResponseCode.CONFLICT, error_msg=str(e)), 409
        except DatabaseError as e:
            current_app.logger.error(f'用户{current_user_id}创建通知失败:{e}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg=str(e)), 500
        except Exception as e:
            current_app.logger.error(f'用户{current_user_id}创建通知失败:未知错误-{e}\n{traceback.format_exc()}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg='服务器内部错误'), 500


@api.route('/<int:notification_id>')
@api.param('notification_id','通知ID')
class NotificationResource(Resource):
    @api.doc('get_notification')
    @api.response(200,'获取通知详情成功',notification_response_model)
    @api.response(401,'未认证')
    @api.response(403,'无权访问该通知')
    @api.response(404,'通知不存在或无权访问')
    @jwt_required()
    def get(self,notification_id):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}请求获取通知详情,ID:{notification_id}')
        try:
            notification=NotificationService.get_notification_by_id(notification_id,current_user_id)
            current_app.logger.info(f'用户{current_user_id}成功获取通知详情,ID:{notification_id}')
            return success_response(data=notification, message='获取通知详情成功'), 200
        except ResourceNotFoundError as e:
            current_app.logger.warning(f'用户{current_user_id}获取通知详情失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND, error_msg=str(e)), 404
        except PermissionError as e:
            current_app.logger.warning(f'用户{current_user_id}无权访问通知详情,ID:{notification_id}')
            return fail_response(code=ResponseCode.PERMISSION_DENIED, error_msg=str(e)), 403
        except Exception as e:
            current_app.logger.error(f'用户{current_user_id}获取通知详情失败:{e}\n{traceback.format_exc()}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg='服务器内部错误'), 500
    @api.doc('delete_notification')
    @api.response(200,'通知删除成功')
    @api.response(401,'未认证')
    @api.response(403,'无权删除')
    @api.response(404,'通知不存在')
    @jwt_required()
    def delete(self,notification_id):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试删除通知,ID:{notification_id}')
        try:
            NotificationService.delete_notification(notification_id,current_user_id)
            current_app.logger.info(f'用户{current_user_id}成功删除通知,ID:{notification_id}')
            return success_response(message='通知删除成功'), 200
        except ResourceNotFoundError as e:
            current_app.logger.warning(f'用户{current_user_id}删除通知失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND, error_msg=str(e)), 404
        except PermissionError as e:
            current_app.logger.warning(f'用户{current_user_id}无权删除通知,ID:{notification_id}')
            return fail_response(code=ResponseCode.PERMISSION_DENIED, error_msg=str(e)), 403
        except DatabaseError as e:
            current_app.logger.error(f'用户{current_user_id}删除通知失败:{e}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg=str(e)), 500
        except Exception as e:
            current_app.logger.error(f'用户{current_user_id}删除通知失败:未知错误-{e}\n{traceback.format_exc()}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg='服务器内部错误'), 500        

@api.route('/<int:notification_id>/read')
@api.param('notification_id','通知ID')
class NotificationReadResource(Resource):
    @api.doc('mark_notification_as_read')
    @api.response(200,'标记通知为已读成功',notification_response_model)
    @api.response(401,'未认证')
    @api.response(404,'通知不存在')
    @api.response(403,'无权操作')
    @jwt_required()
    def patch(self,notification_id):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试标记通知已读,ID:{notification_id}')
        try:
            notification=NotificationService.mark_all_as_read(notification_id,current_user_id)
            current_app.logger.info(f'用户{current_user_id}成功标记通知为已读,ID:{notification_id}')
            return success_response(data=notification, message='标记通知为已读成功'), 200
        except ResourceNotFoundError as e:
            current_app.logger.warning(f'用户{current_user_id}标记为已读失败:{e}')
            return fail_response(code=ResponseCode.RESOURCE_NOT_FOUND, error_msg=str(e)), 404
        except PermissionError as e:
            current_app.logger.warning(f'用户{current_user_id}无权标记通知为已读,ID:{notification_id}')
            return fail_response(code=ResponseCode.PERMISSION_DENIED, error_msg=str(e)), 403
        except DatabaseError as e:
            current_app.logger.error(f'用户{current_user_id}标记通知为已读失败:{e}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg=str(e)), 500
        except Exception as e:
            current_app.logger.error(f'用户{current_user_id}标记通知为已读失败:未知错误-{e}\n{traceback.format_exc()}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg='服务器内部错误'), 500
@api.route('/read-all')
class NotificationReadAllResource(Resource):
    @api.doc('mar_all_notifications_as_read')
    @api.response(200,'标记所有通知为已读成功')
    @api.response(401,'未认证')
    @jwt_required()
    def patch(self):
        current_user_id=get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}尝试标记所有通知为已读')
        try:
            NotificationService.mark_all_as_read(current_user_id)
            current_app.logger.info(f'用户{current_user_id}成功标记所有通知为已读')
            return success_response(message='所有通知已标记为已读'), 200
        except DatabaseError as e:
            current_app.logger.error(f'用户{current_user_id}标记所有通知已读失败:{e}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg=str(e)), 500
        except Exception as e:
            current_app.logger.error(f'用户{current_user_id}标记所有通知为已读失败:未知错误-{e}\n{traceback.format_exc()}')
            return fail_response(code=ResponseCode.INTERNAL_ERROR, error_msg='服务器内部错误'), 500

api_restx.add_namespace(api)



























