"""add notification event_id for idempotency

Revision ID: 9b1c4d7e2f30
Revises: 2c9a2bae521c
Create Date: 2026-10-27 08:20:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '9b1c4d7e2f30'  # pragma: allowlist secret
down_revision = '2c9a2bae521c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('event_id', sa.String(length=64), nullable=True))
        batch_op.create_index('uq_notification_event_id', ['event_id'], unique=True)


def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('uq_notification_event_id')
        batch_op.drop_column('event_id')
