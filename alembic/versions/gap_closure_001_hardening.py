"""
Migration: gap_closure_hardening
Alembic revision for gap-closure hardening.

Adds:
  1. Partial unique index on signature_requests(receipt_id) WHERE status = 'pending'
     (GAP-001/020: ensures only one pending SR per receipt at all times)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'gap_closure_001'
down_revision = '3fa564c745c3'
branch_labels = None
depends_on = None


def upgrade():
    # GAP-001/020: Partial unique index     only one pending SR per receipt.
    # Uses WHERE clause so multiple historical (signed/rejected/expired) SRs
    # for the same receipt can still coexist for auditing.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sr_receipt_pending
        ON signature_requests (receipt_id)
        WHERE status = 'pending';
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_sr_receipt_pending;")
