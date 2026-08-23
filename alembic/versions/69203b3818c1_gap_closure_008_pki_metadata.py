"""gap_closure_008_pki_metadata

Revision ID: 69203b3818c1
Revises: 72d2ed2c2f0b
Create Date: 2026-04-06 14:31:44.084273

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69203b3818c1'
down_revision: Union[str, Sequence[str], None] = '72d2ed2c2f0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pki_key_metadata',
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('key_id', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('encrypted_path', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint'),
        sa.UniqueConstraint('key_id', 'version', name='uq_pki_key_id_version')
    )
    op.create_index('idx_pki_key_id', 'pki_key_metadata', ['key_id'])


def downgrade() -> None:
    op.drop_index('idx_pki_key_id', table_name='pki_key_metadata')
    op.drop_table('pki_key_metadata')
