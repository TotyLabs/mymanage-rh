"""industrial_resilience_hardening

Revision ID: gap_closure_009_resilience
Revises: 69203b3818c1
Create Date: 2026-04-06 15:32:58.162287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'gap_closure_009_resilience'
down_revision: Union[str, Sequence[str], None] = '69203b3818c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add Chaining Columns to AuditLog (BLK-001) - Idempotent
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='audit_log' AND column_name='previous_hash') THEN
                ALTER TABLE audit_log ADD COLUMN previous_hash TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='audit_log' AND column_name='chain_hash') THEN
                ALTER TABLE audit_log ADD COLUMN chain_hash TEXT;
                CREATE INDEX idx_audit_chain_hash ON audit_log (chain_hash);
            END IF;
        END $$;
    """)

    # 2. Defense in Depth: REVOKE permissions (BLK-001 / SSoT)
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON payroll_receipts FROM PUBLIC;")

    # 3. Ensure extensions exist
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")


def downgrade() -> None:
    # Restore permissions
    op.execute("GRANT UPDATE, DELETE ON audit_log TO PUBLIC;")
    op.execute("GRANT INSERT, UPDATE, DELETE ON payroll_receipts TO PUBLIC;")

    # We keep the columns in downgrade to avoid data loss in production chains
    pass
