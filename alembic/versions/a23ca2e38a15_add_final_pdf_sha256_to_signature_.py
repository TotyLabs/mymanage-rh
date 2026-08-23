"""Auto-generated Alembic script template.

Revision ID: a23ca2e38a15
Revises: '1cf1b90a7f2e'
Create Date: 2026-02-01 16:43:28.895010
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a23ca2e38a15'
down_revision = '1cf1b90a7f2e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('signature_evidence', sa.Column('final_pdf_sha256', sa.CHAR(length=64), nullable=True))
    # We make it nullable first to avoid issues with existing rows, 
    # but ideally it should be populated. For now, nullable is safer.


def downgrade():
    op.drop_column('signature_evidence', 'final_pdf_sha256')


