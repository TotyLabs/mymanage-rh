"""Add cuit column to organizations.

Revision ID: gap_closure_003_org_cuit
Revises: gap_closure_002_cols
Create Date: 2026-03-14 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'gap_closure_003_org_cuit'
down_revision = 'gap_closure_002_cols'
branch_labels = None
depends_on = None


def upgrade():
    # Helper to check if column exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    existing_cols = [c['name'] for c in inspector.get_columns('organizations')]
    
    if 'cuit' not in existing_cols:
        op.add_column('organizations', sa.Column('cuit', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('organizations', 'cuit')
