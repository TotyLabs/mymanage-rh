"""Initial empty revision to mark baseline schema

Revision ID: 000_initial
Revises: 
Create Date: 2026-01-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '000_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # This migration intentionally left empty. Use `alembic stamp head` to mark
    # the existing database as baseline without applying DDL.
    pass


def downgrade():
    pass
