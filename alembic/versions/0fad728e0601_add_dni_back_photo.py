"""add_dni_back_photo

Revision ID: 0fad728e0601
Revises: 479933a40785
Create Date: 2026-03-21 12:25:47.891646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fad728e0601'
down_revision: Union[str, Sequence[str], None] = '479933a40785'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('employees', sa.Column('dni_back_image_path', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('employees', 'dni_back_image_path')
