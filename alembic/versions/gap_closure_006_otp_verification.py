"""add_verification_status

Revision ID: gap_closure_006_otp_verification
Revises: b2286a2bdd10
Create Date: 2026-04-05 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'gap_closure_006_otp_verification'
down_revision = 'b2286a2bdd10'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Update UserStatus enum
    # We must commit after ALTER TYPE ADD VALUE before using it in the same session
    op.execute("COMMIT;")
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'pending_verification';")
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'active';")
    op.execute("COMMIT;")

    # 2. Data Migration
    op.execute("""
        UPDATE users 
        SET user_status = 'active', is_verified = true 
        WHERE user_status IS NULL OR user_status IN ('full', 'lightweight');
    """)

    # 3. Update server default for new users
    op.execute("ALTER TABLE users ALTER COLUMN user_status SET DEFAULT 'pending_verification';")

def downgrade():
    # Data migration back (optional/best effort)
    op.execute("UPDATE users SET user_status = 'full' WHERE user_status = 'active';")
    
    # We can't easily remove ENUM values in Postgres without recreating the type, 
    # which is risky if many tables use it.
    pass
