from core import db


def commit_or_rollback():
    """提交当前事务，失败则回滚并抛出原异常。"""
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
