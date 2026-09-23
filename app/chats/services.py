import logging

from sqlalchemy.exc import IntegrityError

from app.common.exceptions import (
    AuthenticationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.feeds.cursor import decode_cursor
from app.users.repositories import user_repository
from core import db
from core.metrics import CHAT_OPERATIONS

from .models import Conversation
from .repositories import ChatRepository
from .schemas import CreateConversationSchema, MarkReadSchema, SendMessageSchema
from .stream import publish_chat_event

logger = logging.getLogger(__name__)


class ChatService:
    '''私信服务：发起会话 / 会话列表 / 消息列表 / 发消息 / 已读 / 未读数。'''

    DEFAULT_PER_PAGE = 20
    MAX_PER_PAGE = 100

    # ---------- 内部校验 ----------

    @staticmethod
    def _peer_of(conv: Conversation, user_id: int) -> int:
        '''取会话对端 id（low<high 存储，故 low 用户的对端是 high）'''
        if conv.user_low_id == user_id:
            return conv.user_high_id
        if conv.user_high_id == user_id:
            return conv.user_low_id
        raise AuthenticationError('无权访问该会话')

    @staticmethod
    def _get_conversation_or_404(conversation_id: int, user_id: int) -> tuple[Conversation, int]:
        '''取会话 + 成员鉴权，返回 (conv, peer_id)。走主库，确保成员关系最新。'''
        conv = ChatRepository.get_conversation(conversation_id, force_master=True)
        if not conv:
            raise ResourceNotFoundError('会话')
        peer_id = ChatService._peer_of(conv, user_id)  # 非成员在这里被拒
        return conv, peer_id

    # ---------- 业务 ----------

    @staticmethod
    def create_conversation(user_id: int, data: dict) -> dict:
        '''发起/复用会话（幂等）。

        并发：A、B 同时发起 → 都查不到 → 都 INSERT → 唯一索引冲突 →
        输方回读**主库**拿到赢家创建的会话（从库有延迟，可能读不到）。
        '''
        parsed = CreateConversationSchema().load(data)
        peer_id = int(parsed['peer_id'])
        if peer_id == int(user_id):
            raise ValidationError('不能和自己私信')

        peer = user_repository.get_by_id(peer_id, force_master=True)
        if not peer or not getattr(peer, 'is_active', True):
            raise ResourceNotFoundError('用户')

        conv = ChatRepository.find_by_pair(user_id, peer_id)
        if conv:
            CHAT_OPERATIONS.labels(action='create_conversation', result='exists').inc()
            return {'conversation_id': conv.id, 'peer_id': peer_id}

        try:
            conv = ChatRepository.create_conversation(user_id, peer_id)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            conv = ChatRepository.find_by_pair(user_id, peer_id, force_master=True)
            if not conv:
                logger.error(f'[Chat] 创建会话冲突但回读不到 pair=({user_id},{peer_id})')
                CHAT_OPERATIONS.labels(action='create_conversation', result='error').inc()
                raise

        CHAT_OPERATIONS.labels(action='create_conversation', result='success').inc()
        return {'conversation_id': conv.id, 'peer_id': peer_id}

    @staticmethod
    def list_conversations(user_id: int, page: int = 1, per_page: int = 20) -> dict:
        per_page = min(max(1, per_page), ChatService.MAX_PER_PAGE)
        convs, total = ChatRepository.list_conversations(user_id, page, per_page)

        peer_ids = [
            (c.user_high_id if c.user_low_id == user_id else c.user_low_id) for c in convs
        ]
        users = {u.id: u for u in ChatRepository.get_users_by_ids(peer_ids)}

        items = []
        for conv, peer_id in zip(convs, peer_ids, strict=False):
            peer = users.get(peer_id)
            items.append({
                'conversation_id': conv.id,
                'peer_id': peer_id,
                'peer_username': peer.username if peer else None,
                'peer_avatar': peer.avatar_url if peer else None,
                'last_message_preview': conv.last_message_preview,
                'last_message_at': conv.last_message_at.isoformat() if conv.last_message_at else None,
            })

        CHAT_OPERATIONS.labels(action='list_conversations', result='success').inc()
        pages = (total + per_page - 1) // per_page if total else 0
        return {
            'items': items,
            'pagination': {
                'page': page, 'per_page': per_page, 'total': total,
                'pages': pages, 'has_next': page < pages, 'has_prev': page > 1,
            },
        }

    @staticmethod
    def send_message(user_id: int, conversation_id: int, data: dict) -> dict:
        '''发消息：落库 → commit → SSE 推送（顺序不可颠倒，避免"前端收到但库里没有"）'''
        parsed = SendMessageSchema().load(data)
        content = parsed['content'].strip()
        if not content:
            raise ValidationError('私信内容不能为空')

        conv, peer_id = ChatService._get_conversation_or_404(conversation_id, user_id)

        try:
            msg = ChatRepository.create_message(
                conversation_id=conversation_id,
                sender_id=user_id,
                receiver_id=peer_id,
                content=content,
                client_msg_id=parsed.get('client_msg_id'),
                msg_type=parsed.get('type', 0),
                extra=parsed.get('extra'),
            )
            ChatRepository.touch_conversation(conv, content, msg.id)
            ChatRepository.bump_unread(conversation_id, peer_id)  # 收件人未读 +1
            ChatRepository.revive_user(conversation_id, user_id)  # 发送方会话复活
            db.session.commit()
        except Exception:
            db.session.rollback()
            CHAT_OPERATIONS.labels(action='send', result='error').inc()
            raise

        message = {
            'id': msg.id,
            'conversation_id': conversation_id,
            'sender_id': user_id,
            'receiver_id': peer_id,
            'content': content,
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
        }
        # 在线推送（publish_chat_event 内部已 try/except，失败不影响主流程）
        publish_chat_event(peer_id, {'type': 'message.new', 'message': message})

        CHAT_OPERATIONS.labels(action='send', result='success').inc()
        return message

    @staticmethod
    def list_messages(user_id: int, conversation_id: int, cursor=None, limit: int = 20) -> dict:
        limit = min(max(1, limit), ChatService.MAX_PER_PAGE)
        ChatService._get_conversation_or_404(conversation_id, user_id)  # 鉴权

        cur = decode_cursor(cursor)
        rows, has_more, next_cursor = ChatRepository.list_messages_cursor(conversation_id, cur, limit)
        items = [{
            'id': m.id,
            'conversation_id': m.conversation_id,
            'sender_id': m.sender_id,
            'receiver_id': m.receiver_id,
            'content': m.content,
            'created_at': m.created_at.isoformat() if m.created_at else None,
        } for m in rows]

        CHAT_OPERATIONS.labels(action='list_messages', result='success').inc()
        return {'items': items, 'next_cursor': next_cursor, 'has_more': has_more}

    @staticmethod
    def mark_read(user_id: int, data: dict) -> dict:
        parsed = MarkReadSchema().load(data)
        conversation_id = int(parsed['conversation_id'])
        conv, _peer = ChatService._get_conversation_or_404(conversation_id, user_id)

        last_read_id = parsed.get('last_read_id') or conv.last_message_id
        try:
            updated = ChatRepository.mark_conversation_read(conversation_id, user_id, last_read_id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            CHAT_OPERATIONS.labels(action='mark_read', result='error').inc()
            raise

        CHAT_OPERATIONS.labels(action='mark_read', result='success').inc()
        return {'conversation_id': conversation_id, 'marked': updated, 'last_read_id': last_read_id}

    @staticmethod
    def get_unread_count(user_id: int) -> dict:
        # MVP：ConversationUser.unread_count 求和（一次 SELECT），不建 Redis 对账
        count = ChatRepository.count_unread(user_id)
        return {'unread_count': count}
