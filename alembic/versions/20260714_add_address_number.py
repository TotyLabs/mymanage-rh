"""Add address_number to employees

Revision ID: 20260714_add_address_number
Revises: 95e9518b161f
Create Date: 2026-07-14 00:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260714_add_address_number'
down_revision: Union[str, Sequence[str], None] = '95e9518b161f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('employees', sa.Column('address_number', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('employees', 'address_number')
