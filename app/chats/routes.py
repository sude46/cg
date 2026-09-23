from flask import Response, current_app, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restx import Api, Namespace, Resource, fields

from middlewares import route_limit
from utils.decorators import validate_json
from utils.response import paginated_response, success_response

from . import chats_bp
from .schemas import CreateConversationSchema, MarkReadSchema, SendMessageSchema
from .services import ChatService
from .stream import iter_events

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'JWT Token (Bearer token)'
    }
}

api_restx = Api(
    chats_bp,
    version='1.0',
    title='私信API',
    description='提供私信（会话/消息）相关接口',
    authorizations=authorizations,
    security='Bearer',
    doc='/docs'
)
api = Namespace('chats', description='私信相关操作', path='/')

create_conv_model = api.model('ChatCreate', {
    'peer_id': fields.Integer(required=True, description='对方用户ID'),
})
send_model = api.model('ChatSend', {
    'content': fields.String(required=True, description='私信内容（1-500字符）'),
    'client_msg_id': fields.String(required=False, description='客户端幂等键（可选）'),
})
mark_read_model = api.model('ChatMarkRead', {
    'conversation_id': fields.Integer(required=True, description='会话ID'),
    'last_read_id': fields.Integer(required=False, description='已读位点（可选）'),
})

msg_parser = api.parser()
msg_parser.add_argument('cursor', type=str, default=None, help='上一页 next_cursor；首页不传', location='args')
msg_parser.add_argument('limit', type=int, default=20, help='每页数量(默认20，最大100)', location='args')


@api.route('')
class ConversationList(Resource):
    @api.doc('list_conversations', params={'page': '页码', 'per_page': '每页数量'})
    @api.response(200, '获取成功')
    @jwt_required()
    def get(self):
        '''会话列表（按最近消息倒序）'''
        current_user_id = get_jwt_identity()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        result = ChatService.list_conversations(current_user_id, page, per_page)
        return paginated_response(
            result['items'], result['pagination'], message='获取会话列表成功'
        ), 200

    @api.doc('create_conversation')
    @api.expect(create_conv_model, validate=False)
    @api.response(201, '会话已就绪')
    @jwt_required()
    @validate_json(CreateConversationSchema)
    def post(self):
        '''发起会话（幂等：同对端只会有一个会话）'''
        current_user_id = get_jwt_identity()
        result = ChatService.create_conversation(current_user_id, request.get_json())
        return success_response(data=result, message='会话已就绪'), 201


@api.route('/<int:conversation_id>/messages')
@api.param('conversation_id', '会话ID')
class MessageList(Resource):
    @api.doc('list_messages')
    @api.expect(msg_parser)
    @api.response(200, '获取成功')
    @jwt_required()
    def get(self, conversation_id):
        '''消息列表（游标分页，最新在前）'''
        current_user_id = get_jwt_identity()
        args = msg_parser.parse_args()
        result = ChatService.list_messages(
            current_user_id, conversation_id,
            cursor=args.get('cursor'), limit=args.get('limit', 20),
        )
        return success_response(data=result, message='获取消息成功'), 200

    @api.doc('send_message')
    @api.expect(send_model, validate=False)
    @api.response(201, '发送成功')
    @jwt_required()
    @validate_json(SendMessageSchema)
    @route_limit('30 per minute')
    def post(self, conversation_id):
        '''发送消息'''
        current_user_id = get_jwt_identity()
        result = ChatService.send_message(current_user_id, conversation_id, request.get_json())
        return success_response(data=result, message='发送成功'), 201


@api.route('/messages/read')
class MessageRead(Resource):
    @api.doc('mark_conversation_read')
    @api.expect(mark_read_model, validate=False)
    @api.response(200, '已读成功')
    @jwt_required()
    @validate_json(MarkReadSchema)
    def patch(self):
        '''标记会话内我收到的消息全部已读'''
        current_user_id = get_jwt_identity()
        result = ChatService.mark_read(current_user_id, request.get_json())
        return success_response(data=result, message='已读成功'), 200


@api.route('/unread-count')
class ChatUnreadCount(Resource):
    @api.doc('get_chat_unread_count')
    @api.response(200, '获取成功')
    @jwt_required()
    def get(self):
        '''私信未读数'''
        current_user_id = get_jwt_identity()
        result = ChatService.get_unread_count(current_user_id)
        return success_response(data=result, message='获取成功'), 200


@api.route('/stream')
class ChatStream(Resource):
    @api.doc('chat_stream')
    @api.response(200, 'SSE 私信流（text/event-stream）')
    @jwt_required()
    def get(self):
        '''实时私信流（SSE；fetch 带 Bearer，同通知流）'''
        current_user_id = get_jwt_identity()
        current_app.logger.info(f'用户{current_user_id}订阅私信流')
        resp = Response(
            stream_with_context(iter_events(current_user_id)),
            mimetype='text/event-stream'
        )
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['X-Accel-Buffering'] = 'no'
        resp.headers['Connection'] = 'keep-alive'
        return resp


api_restx.add_namespace(api)
