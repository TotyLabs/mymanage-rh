"""add_notifications

Revision ID: 39b2d8b58333
Revises: cd5841f53c4c
Create Date: 2026-04-02 18:08:58.266749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39b2d8b58333'
down_revision: Union[str, Sequence[str], None] = 'cd5841f53c4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'notifications',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=False), server_default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('sender_user_id', sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.dialects.postgresql.UUID(as_uuid=False), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f('ix_notifications_sender_user_id'), 'notifications', ['sender_user_id'], unique=False)
    op.create_index(op.f('ix_notifications_company_id'), 'notifications', ['company_id'], unique=False)

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notifications_company_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_sender_user_id'), table_name='notifications')
    op.drop_table('notifications')
