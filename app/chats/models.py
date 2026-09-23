from sqlalchemy import BigInteger, CheckConstraint, Integer

from app.common.database import utcnow
from core import db


def _bigint():
    """MySQL 用 BIGINT 自增；SQLite（单测内存库）退回 INTEGER 以获得 rowid 自增。"""
    return BigInteger().with_variant(Integer, 'sqlite')


class Conversation(db.Model):
    """会话主体：只存双方共享的信息。

    采用 (user_low_id, user_high_id) 且 low<high 的规范对，保证 A→B 与 B→A 是同一会话。
    """
    __tablename__ = 'conversations'

    id = db.Column(_bigint(), primary_key=True)
    user_low_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    user_high_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    last_message_id = db.Column(_bigint(), nullable=True)
    last_message_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    last_message_preview = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True, default=None)

    __table_args__ = (
        db.Index('uq_conversation_pair', 'user_low_id', 'user_high_id', unique=True),
        CheckConstraint('user_low_id < user_high_id', name='ck_conversation_ordered_pair'),
    )

    user_low = db.relationship('User', foreign_keys=[user_low_id])
    user_high = db.relationship('User', foreign_keys=[user_high_id])
    participants = db.relationship(
        'ConversationUser',
        back_populates='conversation',
        cascade='all,delete-orphan',
        passive_deletes=True,
    )

    @staticmethod
    def normalize_pair(a: int, b: int) -> tuple[int, int]:
        if a == b:
            raise ValueError('cannot converse with self')
        return (a, b) if a < b else (b, a)


class ConversationUser(db.Model):
    """每个用户在会话中的私有状态（丙方案精简版）。

    只保留 MVP 必需的：未读计数、已读位点、单方删除。
    置顶/免打扰/最后阅读等后续按需在此扩展。
    """
    __tablename__ = 'conversation_users'

    conversation_id = db.Column(
        _bigint(),
        db.ForeignKey('conversations.id', ondelete='CASCADE'),
        primary_key=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True,
    )
    unread_count = db.Column(db.Integer, default=0, nullable=False)
    last_read_id = db.Column(_bigint(), nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True, default=None)

    __table_args__ = (
        db.Index('idx_conv_user_list', 'user_id', 'deleted_at'),
    )

    conversation = db.relationship('Conversation', back_populates='participants')


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(_bigint(), primary_key=True)
    conversation_id = db.Column(
        _bigint(),
        db.ForeignKey('conversations.id', ondelete='CASCADE'),
        nullable=False,
    )
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    # 0 文本，1 图片，2 语音，3 视频，4 文件，9 系统（MVP 只用 0，列先留好）
    type = db.Column(db.SmallInteger, default=0, nullable=False)
    content = db.Column(db.Text, nullable=False)
    extra = db.Column(db.JSON, nullable=True)
    # 客户端幂等去重键（MVP 不强制，列保留）
    client_msg_id = db.Column(db.String(64), nullable=True)

    revoked_at = db.Column(db.DateTime, nullable=True)
    edited_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        db.Index('idx_msg_conv_id', 'conversation_id', 'id'),
        db.Index('uq_msg_client', 'conversation_id', 'client_msg_id', unique=True),
    )

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])
