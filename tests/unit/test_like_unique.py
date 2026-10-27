"""FIX-12: active 点赞唯一，deleted_at NULL 不再绕过唯一约束。"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.likes.models import Like
from app.likes.repositories import like_repository
from tests.unit.factories import CommentFactory, PostFactory, UserFactory


def test_duplicate_active_post_like_rejected(app, db_session):
    with app.app_context():
        user = UserFactory()
        post = PostFactory()
        db_session.add(Like(user_id=user.id, post_id=post.id))
        db_session.commit()

        db_session.add(Like(user_id=user.id, post_id=post.id))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_duplicate_active_comment_like_rejected(app, db_session):
    with app.app_context():
        user = UserFactory()
        comment = CommentFactory()
        db_session.add(Like(user_id=user.id, comment_id=comment.id))
        db_session.commit()

        db_session.add(Like(user_id=user.id, comment_id=comment.id))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_delete_like_hard_deletes_row(app, db_session):
    with app.app_context():
        user = UserFactory()
        post = PostFactory()
        like = like_repository.create_post_like(user.id, post.id)
        db_session.commit()
        like_id = like.id

        like_repository.delete_like(like)
        db_session.commit()

        assert db_session.get(Like, like_id) is None


def test_like_unique_constraints_use_active_columns(app):
    constraints = {
        c.name: [col.name for col in c.columns]
        for c in Like.__table__.constraints
        if c.name
    }
    assert constraints['uq_like_user_post'] == ['user_id', 'post_id']
    assert constraints['uq_like_user_comment'] == ['user_id', 'comment_id']
