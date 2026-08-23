"""Add missing signature_evidence columns

Revision ID: 20260130_add_sig_cols
Revises: 202601302208_3efdae12
Create Date: 2026-01-30 20:40:00.000000

This migration adds the missing columns that should have been created
by the autogenerate migration but were not applied to the database.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260130_add_sig_cols'
down_revision = '202601302208_3efdae12'
branch_labels = None
depends_on = None


def upgrade():
    # Add missing columns to signature_evidence table, if it exists.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'signature_evidence' not in inspector.get_table_names():
        return

    op.add_column('signature_evidence', sa.Column('signature_image_path', sa.Text(), nullable=False))
    op.add_column('signature_evidence', sa.Column('signature_image_sha256', sa.CHAR(length=64), nullable=False))


def downgrade():
    # Remove the added columns
    op.drop_column('signature_evidence', 'signature_image_sha256')
    op.drop_column('signature_evidence', 'signature_image_path')
