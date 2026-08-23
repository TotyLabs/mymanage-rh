"""add_metadata_to_receipts

Revision ID: b2286a2bdd10
Revises: a119592bdd0f
Create Date: 2026-04-02 19:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2286a2bdd10'
down_revision = 'a119592bdd0f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('receipts', sa.Column('receipt_metadata', sa.JSON(), server_default='{}', nullable=False))


def downgrade():
    op.drop_column('receipts', 'receipt_metadata')
