"""Add registration_keys table

Revision ID: 95e9518b161f
Revises: e519a2f40413
Create Date: 2026-05-04 19:30:50.370546

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95e9518b161f'
down_revision: Union[str, Sequence[str], None] = 'e519a2f40413'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'registration_keys',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=False), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('key_hash', sa.CHAR(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=12), nullable=False),
        sa.Column('key_type', sa.String(length=20), server_default=sa.text("'employer'"), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('max_uses', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('current_uses', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('created_by', sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('used_by_org_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('used_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['used_by_org_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_registration_keys_key_hash'), 'registration_keys', ['key_hash'], unique=True)
    op.create_index('idx_regkeys_active', 'registration_keys', ['is_active', 'is_revoked'], unique=False)

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_regkeys_active', table_name='registration_keys')
    op.drop_index(op.f('ix_registration_keys_key_hash'), table_name='registration_keys')
    op.drop_table('registration_keys')
