"""add event outbox

Revision ID: c4a7e2f9b1d3
Revises: 9b1c4d7e2f30
Create Date: 2026-10-27 09:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4a7e2f9b1d3'  # pragma: allowlist secret
down_revision = '9b1c4d7e2f30'  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_outbox',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('event_name', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_event_outbox_event_id'),
    )
    with op.batch_alter_table('event_outbox', schema=None) as batch_op:
        batch_op.create_index('ix_event_outbox_event_name', ['event_name'], unique=False)
        batch_op.create_index('ix_event_outbox_status', ['status'], unique=False)
        batch_op.create_index('ix_event_outbox_next_retry_at', ['next_retry_at'], unique=False)
        batch_op.create_index('ix_event_outbox_created_at', ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('event_outbox', schema=None) as batch_op:
        batch_op.drop_index('ix_event_outbox_created_at')
        batch_op.drop_index('ix_event_outbox_next_retry_at')
        batch_op.drop_index('ix_event_outbox_status')
        batch_op.drop_index('ix_event_outbox_event_name')
    op.drop_table('event_outbox')
