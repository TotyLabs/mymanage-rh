"""Merge heads

Revision ID: e9b8869dfce9
Revises: 39b2d8b58333
Create Date: 2026-04-02 18:25:30.226968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9b8869dfce9'
down_revision: Union[str, Sequence[str], None] = '39b2d8b58333'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
