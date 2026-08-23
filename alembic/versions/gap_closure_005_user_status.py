"""add user status and verification columns

Revision ID: gap_closure_005_user_status
Revises: d3b90e9b555a
Create Date: 2026-03-24 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'gap_closure_005_user_status'
down_revision = 'd3b90e9b555a'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Create UserStatus enum
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_status') THEN
            CREATE TYPE user_status AS ENUM ('full', 'lightweight');
        END IF;
    END
    $$;
    """)

    # 2. Add columns to users table
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'user_status' not in columns:
        op.add_column('users', sa.Column('user_status', sa.Enum('full', 'lightweight', name='user_status'), server_default='full', nullable=False))
    if 'is_verified' not in columns:
        op.add_column('users', sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False))

def downgrade():
    op.drop_column('users', 'is_verified')
    op.drop_column('users', 'user_status')
    op.execute("DROP TYPE user_status;")
