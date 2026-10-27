"""likes active unique constraints

Revision ID: d8f2a6c1b9e4
Revises: c4a7e2f9b1d3
Create Date: 2026-10-27 10:40:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd8f2a6c1b9e4'  # pragma: allowlist secret
down_revision = 'c4a7e2f9b1d3'  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade():
    # 1) 取消点赞改为硬删除后，历史软删行不再需要
    op.execute("DELETE FROM likes WHERE deleted_at IS NOT NULL")

    # 2) 清理 active 重复行：帖子/评论分别保留最小 id
    op.execute("""
        DELETE FROM likes
        WHERE deleted_at IS NULL AND post_id IS NOT NULL
          AND id NOT IN (
              SELECT keep_id FROM (
                  SELECT MIN(id) AS keep_id
                  FROM likes
                  WHERE deleted_at IS NULL AND post_id IS NOT NULL
                  GROUP BY user_id, post_id
              ) AS keep_posts
          )
    """)
    op.execute("""
        DELETE FROM likes
        WHERE deleted_at IS NULL AND comment_id IS NOT NULL
          AND id NOT IN (
              SELECT keep_id FROM (
                  SELECT MIN(id) AS keep_id
                  FROM likes
                  WHERE deleted_at IS NULL AND comment_id IS NOT NULL
                  GROUP BY user_id, comment_id
              ) AS keep_comments
          )
    """)

    # 3) 唯一键不再包含 deleted_at（NULL 在 MySQL 中不参与去重）
    with op.batch_alter_table('likes', schema=None) as batch_op:
        batch_op.drop_constraint('user_post_unique', type_='unique')
        batch_op.drop_constraint('user_comment_unique', type_='unique')
        batch_op.create_unique_constraint(
            'uq_like_user_post', ['user_id', 'post_id']
        )
        batch_op.create_unique_constraint(
            'uq_like_user_comment', ['user_id', 'comment_id']
        )


def downgrade():
    with op.batch_alter_table('likes', schema=None) as batch_op:
        batch_op.drop_constraint('uq_like_user_comment', type_='unique')
        batch_op.drop_constraint('uq_like_user_post', type_='unique')
        batch_op.create_unique_constraint(
            'user_comment_unique', ['user_id', 'comment_id', 'deleted_at']
        )
        batch_op.create_unique_constraint(
            'user_post_unique', ['user_id', 'post_id', 'deleted_at']
        )
