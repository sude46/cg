"""事务性事件 outbox。

业务事务提交时同时写一条 outbox 记录，relay 任务再把它投递到 Redis 事件总线。
这样不会出现“DB 已提交、事件没入队”的静默丢失；relay 重复投递由 event_id 幂等兜底。
"""

import uuid

from app.common.database import utcnow
from core import db


class EventOutbox(db.Model):
    __tablename__ = 'event_outbox'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(64), nullable=False)
    event_name = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(16), nullable=False, default='pending')
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('event_id', name='uq_event_outbox_event_id'),
        db.Index('ix_event_outbox_event_name', 'event_name'),
        db.Index('ix_event_outbox_status', 'status'),
        db.Index('ix_event_outbox_next_retry_at', 'next_retry_at'),
        db.Index('ix_event_outbox_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<EventOutbox {self.id} {self.event_name} {self.status}>'


def enqueue_event(event_name: str, payload: dict) -> str:
    """在当前 DB 事务内加入一条待投递事件，返回 event_id。调用方负责 commit。"""
    event_id = uuid.uuid4().hex
    db.session.add(EventOutbox(
        event_id=event_id,
        event_name=event_name,
        payload=payload,
        status='pending',
    ))
    return event_id
