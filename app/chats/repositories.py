import logging
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from app.common.database import get_read_session, utcnow
from app.feeds.cursor import encode_cursor, score_for
from app.users.models import User
from core import db
from core.metrics import monitor_db

from .models import Conversation, ConversationUser, Message

logger = logging.getLogger(__name__)
PREVIEW_MAX_LEN = 200


class ChatRepository:
    '''私信仓储层：封装会话/消息的数据库访问（读走从库路由）'''

    @staticmethod
    def _read_session():
        return get_read_session()

    # ---------- Conversation ----------

    @staticmethod
    @monitor_db("select", "conversations")
    def get_conversation(conversation_id: int, force_master: bool = False):
        session = db.session if force_master else ChatRepository._read_session()
        return session.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.deleted_at.is_(None),
        ).first()

    @staticmethod
    @monitor_db("select", "conversations")
    def find_by_pair(user_a: int, user_b: int, force_master: bool = False):
        low, high = Conversation.normalize_pair(user_a, user_b)
        session = db.session if force_master else ChatRepository._read_session()
        return session.query(Conversation).filter(
            Conversation.user_low_id == low,
            Conversation.user_high_id == high,
            Conversation.deleted_at.is_(None),
        ).first()

    @staticmethod
    @monitor_db("insert", "conversations")
    def create_conversation(user_a: int, user_b: int) -> Conversation:
        '''创建会话并初始化双方 ConversationUser（同一事务，调用方 commit）'''
        low, high = Conversation.normalize_pair(user_a, user_b)
        conv = Conversation(user_low_id=low, user_high_id=high)
        db.session.add(conv)
        db.session.flush()  # 取 id，不 commit
        db.session.add_all([
            ConversationUser(conversation_id=conv.id, user_id=low),
            ConversationUser(conversation_id=conv.id, user_id=high),
        ])
        return conv

    @staticmethod
    @monitor_db("select", "conversations")
    def list_conversations(user_id: int, page: int = 1, per_page: int = 20):
        session = ChatRepository._read_session()
        q = session.query(Conversation).join(
            ConversationUser, ConversationUser.conversation_id == Conversation.id
        ).filter(
            ConversationUser.user_id == user_id,
            ConversationUser.deleted_at.is_(None),
            Conversation.deleted_at.is_(None),
        )
        total = q.count()
        rows = (
            q.order_by(Conversation.last_message_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return rows, total

    @staticmethod
    @monitor_db("update", "conversations")
    def touch_conversation(conv: Conversation, content: str, message_id: int):
        conv.last_message_id = message_id
        conv.last_message_at = utcnow()
        conv.last_message_preview = content[:PREVIEW_MAX_LEN]

    # ---------- Message ----------

    @staticmethod
    @monitor_db("insert", "messages")
    def create_message(
        conversation_id: int,
        sender_id: int,
        receiver_id: int,
        content: str,
        client_msg_id: str | None = None,
        msg_type: int = 0,
        extra: dict | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            client_msg_id=client_msg_id,
            type=msg_type,
            extra=extra,
        )
        db.session.add(msg)
        db.session.flush()
        return msg

    @staticmethod
    @monitor_db("select", "messages")
    def list_messages_cursor(conversation_id: int, cursor, limit: int = 20):
        '''会话内 keyset 分页：按 (created_at, id) 倒序，返回 (rows, has_more, next_cursor)'''
        session = ChatRepository._read_session()
        query = session.query(Message).options(
            joinedload(Message.sender)
        ).filter(
            Message.conversation_id == conversation_id,
        )
        if cursor is not None:
            score, id_low = cursor
            sec = int(float(score))
            sec_dt = datetime.fromtimestamp(sec, tz=UTC).replace(tzinfo=None)
            query = query.filter(or_(
                Message.created_at < sec_dt,
                and_(Message.created_at == sec_dt, Message.id < int(id_low)),
            ))
        rows = query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            sec = int(last.created_at.replace(tzinfo=UTC).timestamp())
            next_cursor = encode_cursor(score_for(sec, last.id), last.id)
        return rows, has_more, next_cursor

    # ---------- ConversationUser（每用户状态） ----------

    @staticmethod
    @monitor_db("select", "conversation_users")
    def count_unread(user_id: int) -> int:
        session = ChatRepository._read_session()
        total = session.query(
            func.coalesce(func.sum(ConversationUser.unread_count), 0)
        ).filter(
            ConversationUser.user_id == user_id,
            ConversationUser.deleted_at.is_(None),
        ).scalar()
        # MySQL SUM 返回 Decimal，统一转 int（否则 JSON 序列化失败）
        return int(total or 0)

    @staticmethod
    @monitor_db("update", "conversation_users")
    def bump_unread(conversation_id: int, user_id: int):
        '''收件人未读 +1，并复活其被删除的会话'''
        db.session.query(ConversationUser).filter(
            ConversationUser.conversation_id == conversation_id,
            ConversationUser.user_id == user_id,
        ).update(
            {
                'unread_count': ConversationUser.unread_count + 1,
                'deleted_at': None,
            },
            synchronize_session=False,
        )

    @staticmethod
    @monitor_db("update", "conversation_users")
    def revive_user(conversation_id: int, user_id: int):
        '''发送方自己发消息时复活其会话（若曾单方删除）'''
        db.session.query(ConversationUser).filter(
            ConversationUser.conversation_id == conversation_id,
            ConversationUser.user_id == user_id,
        ).update({'deleted_at': None}, synchronize_session=False)

    @staticmethod
    @monitor_db("update", "conversation_users")
    def mark_conversation_read(conversation_id: int, user_id: int, last_read_id: int | None) -> int:
        '''把我在该会话的未读清零，并把已读位点推进到 last_read_id'''
        return db.session.query(ConversationUser).filter(
            ConversationUser.conversation_id == conversation_id,
            ConversationUser.user_id == user_id,
        ).update(
            {'last_read_id': last_read_id, 'unread_count': 0},
            synchronize_session=False,
        )

    # ---------- 其它 ----------

    @staticmethod
    @monitor_db("select", "users")
    def get_users_by_ids(user_ids: list[int]):
        '''批量取用户（会话列表补对端用户名/头像，避免 N+1）'''
        if not user_ids:
            return []
        session = ChatRepository._read_session()
        return session.query(User).filter(User.id.in_(user_ids)).all()
