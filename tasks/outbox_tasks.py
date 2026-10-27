"""事件 outbox relay：把 DB 中 pending 的事件投递到 Redis 事件总线。"""

import logging
from datetime import timedelta

from celery import shared_task
from sqlalchemy import or_

from app.common.database import utcnow
from app.common.events import event_bus
from app.common.outbox import EventOutbox
from core import db
from core.metrics import EVENT_BUS_EVENTS

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 300


@shared_task
def relay_event_outbox(batch_size: int = 100):
    """扫描一批 pending outbox，逐条发布；成功标 sent，失败退避重试。"""
    batch_size = min(max(1, int(batch_size)), 1000)
    now = utcnow()
    rows = db.session.query(EventOutbox).filter(
        EventOutbox.status == 'pending',
        or_(
            EventOutbox.next_retry_at.is_(None),
            EventOutbox.next_retry_at <= now,
        ),
    ).order_by(EventOutbox.id.asc()).limit(batch_size).all()

    sent = failed = 0
    for row in rows:
        try:
            ok = event_bus.publish(
                row.event_name,
                row.payload,
                event_id=row.event_id,
            )
        except Exception as e:
            logger.error(f'[Outbox] 发布异常 event_id={row.event_id}: {e}')
            ok = False

        if ok:
            row.status = 'sent'
            row.sent_at = utcnow()
            sent += 1
            EVENT_BUS_EVENTS.labels(event=row.event_name, result='outbox_sent').inc()
        else:
            row.retry_count += 1
            delay = min(MAX_BACKOFF_SECONDS, 2 ** min(row.retry_count, 8))
            row.next_retry_at = now + timedelta(seconds=delay)
            failed += 1
            EVENT_BUS_EVENTS.labels(event=row.event_name, result='outbox_failed').inc()
            logger.warning(
                f'[Outbox] 投递失败 event_id={row.event_id} '
                f'event={row.event_name} retry={row.retry_count}'
            )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'[Outbox] 提交 relay 状态失败: {e}')
        raise

    return {'sent': sent, 'failed': failed, 'scanned': len(rows)}
