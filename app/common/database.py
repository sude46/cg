import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Query

from core import db  # 直接复用core中初始化的SQLAlchemy实例


def utcnow():
    """返回 naive UTC datetime（兼容 SQLite + MySQL，替代废弃的 datetime.utcnow）"""
    return datetime.now(UTC).replace(tzinfo=None)


logger = logging.getLogger(__name__)
PAGINATION_DEFAULTS = {
    'PER_PAGE': 20,
    'MAX_PER_PAGE': 100
}

class TimestampMixin:
    """时间戳混入类（自动维护创建/更新时间）"""
    created_at = db.Column(
        db.DateTime,
        default=utcnow,
        nullable=False,
        index=True
    )
    updated_at = db.Column(
        db.DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False
    )

class SoftDeleteMixin(TimestampMixin):
    """软删除混入类（继承时间戳，添加删除标记）"""
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime)

    def soft_delete(self) -> None:
        """软删除当前记录"""
        self.is_deleted = True
        self.deleted_at = utcnow()
        db.session.add(self)

    def restore(self) -> None:
        """恢复软删除的记录"""
        self.is_deleted = False
        self.deleted_at = None
        db.session.add(self)

    @classmethod
    def query_active(cls) -> Query:
        """查询未删除的记录s（简化常用查询）"""
        return cls.query.filter_by(is_deleted=False)
class PaginationUtils:
    @staticmethod
    def paginate(
        query: Query,
        page: int = 1,
        per_page: int = PAGINATION_DEFAULTS['PER_PAGE']
    ) -> dict[str, Any]:
        page = max(1, page)
        per_page = min(PAGINATION_DEFAULTS['MAX_PER_PAGE'], max(1, per_page))

        total = query.count()
        items = query.limit(per_page).offset((page - 1) * per_page).all()
        pages = (total + per_page - 1) // per_page

        return {
            'items': items,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': pages,
                'has_next': page < pages,
                'has_prev': page > 1
            }
        }

    @staticmethod
    def keyset_paginate(
        query: Query,
        last_id: int | None = None,
        per_page: int = PAGINATION_DEFAULTS['PER_PAGE']
    ) -> dict[str, Any]:
        """
        游标分页（优化大数据量分页性能）
        :param query: SQLAlchemy查询对象
        :param last_id: 上一页最后一条记录的ID（用于定位）
        :param per_page: 每页数量
        :return: 包含数据和分页标记的字典
        """
        per_page = min(PAGINATION_DEFAULTS['MAX_PER_PAGE'], max(1, per_page))

        # 尝试从 query 中推断出模型类与主键列，以便安全地构造 keyset 分页
        model = None
        pk_col = None
        try:
            desc = getattr(query, 'column_descriptions', None)
            if desc and len(desc) > 0:
                model = desc[0].get('entity', None)
            if model is None:
                # 兼容性回退（某些 Query 实现）
                model = query._entity_zero().entity_zero.class_  # type: ignore
        except Exception:
            model = None

        if model is not None:
            try:
                pk_col = inspect(model).primary_key[0]
            except Exception:
                pk_col = None

        # 如果模型有 is_deleted 字段，默认过滤软删除记录；否则不加该过滤
        if model is not None and hasattr(model, 'is_deleted'):
            base_query = query.filter_by(is_deleted=False)
        else:
            base_query = query

        # 基于主键列进行游标定位；若无法推断主键，则退回到偏移/limit 风格（性能弱）
        if last_id is not None and pk_col is not None:
            filtered_query = base_query.filter(pk_col < last_id)
        else:
            filtered_query = base_query

        # 按主键降序获取下一页（若无主键则不指定 order_by）
        if pk_col is not None:
            items = filtered_query.order_by(pk_col.desc()).limit(per_page + 1).all()
        else:
            items = filtered_query.limit(per_page + 1).all()

        has_more = len(items) > per_page
        if has_more:
            items = items[:-1]

        # 计算 next_cursor：使用主键字段的值
        next_cursor = None
        if items and pk_col is not None and has_more:
            last_item = items[-1]
            # 尝试按属性名获取主键值
            try:
                next_cursor = getattr(last_item, pk_col.name)
            except Exception:
                # 最后回退：尝试访问属性名 'id'
                next_cursor = getattr(last_item, 'id', None)

        return {
            'items': items,
            'pagination': {
                'per_page': per_page,
                'has_more': has_more,
                'next_cursor': next_cursor
            }
        }


# 实例化分页工具（方便其他模块直接调用）
pagination_utils = PaginationUtils()


def get_read_session():
    """
    获取读操作会话。
    - 生产环境（MySQL + binds）：走 replica 从库
    - 测试 / 单库环境：降级为默认 session
    """
    try:
        from flask_sqlalchemy.session import Session
        engine = db.get_engine(bind='replica')
        return Session(db, bind=engine)
    except Exception:
        return db.session
