"""Auto-generated Alembic script template.

Revision ID: 1cf1b90a7f2e
Revises: '20260130_add_sig_cols'
Create Date: 2026-02-01 15:43:33.906408
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1cf1b90a7f2e'
down_revision = '20260130_add_sig_cols'
branch_labels = None
depends_on = None



def upgrade():
    # PostgreSQL specific command to add value to Enum
    # We must run this outside of a transaction if possible, but alembic usually runs in transaction.
    # However, 'ALTER TYPE ... ADD VALUE' cannot run inside a transaction block in some postgres versions
    # IF it's not the first statement. But wait, it CAN run in a transaction in newer PG versions.
    # The safest way is to use autocommit_block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE receipt_status ADD VALUE IF NOT EXISTS 'pending_employee_signature'")
        op.execute("ALTER TYPE receipt_status ADD VALUE IF NOT EXISTS 'pending_employer_signature'")


def downgrade():
    # Enums cannot easily remove values in Postgres without recreating the type.
    pass


