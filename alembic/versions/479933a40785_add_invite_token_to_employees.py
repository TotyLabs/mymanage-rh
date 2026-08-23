"""add_invite_token_to_employees

Revision ID: 479933a40785
Revises: gap_closure_004_immutability
Create Date: 2026-03-18 21:21:43.749615

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '479933a40785'
down_revision: Union[str, Sequence[str], None] = 'gap_closure_004_immutability'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('employees', sa.Column('invite_token', sa.Text(), nullable=True))
    op.add_column('employees', sa.Column('invite_token_expires_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_index(op.f('ix_employees_invite_token'), 'employees', ['invite_token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_employees_invite_token'), table_name='employees')
    op.drop_column('employees', 'invite_token_expires_at')
    op.drop_column('employees', 'invite_token')
