"""Hardening: AuditLog immutability and EmailEvent cascade delete

Revision ID: gap_closure_004_immutability
Revises: gap_closure_003_org_cuit
Create Date: 2026-03-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'gap_closure_004_immutability'
down_revision = 'gap_closure_003_org_cuit'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update EmailEvent Foreign Keys for CASCADE DELETE
    # Drop existing FKs if they exist
    op.execute("ALTER TABLE email_events DROP CONSTRAINT IF EXISTS email_events_receipt_id_fkey")
    op.execute("ALTER TABLE email_events DROP CONSTRAINT IF EXISTS email_events_employee_id_fkey")
    
    # Re-create with CASCADE
    op.create_foreign_key(
        "email_events_receipt_id_fkey", "email_events", "payroll_receipts",
        ["receipt_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "email_events_employee_id_fkey", "email_events", "employees",
        ["employee_id"], ["id"], ondelete="CASCADE"
    )

    # 2. Add Immutability Trigger to AuditLog
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'protect_audit_log') THEN
            CREATE OR REPLACE FUNCTION protect_audit_log()
            RETURNS TRIGGER AS $fn$
            BEGIN
                IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'audit_log_immutable: cannot update';
                ELSIF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'audit_log_immutable: cannot delete'; END IF;
                RETURN NULL;
            END;
            $fn$ LANGUAGE plpgsql;
        END IF;

        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'audit_log' AND relkind = 'r') THEN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_protect_audit_log') THEN
                CREATE TRIGGER trg_protect_audit_log
                    BEFORE UPDATE OR DELETE ON audit_log
                    FOR EACH ROW EXECUTE FUNCTION protect_audit_log();
            END IF;
        END IF;
    END
    $$;
    """)


def downgrade():
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS trg_protect_audit_log ON audit_log;")
    
    # Revert FKs (no-op or explicit revert if needed, but in prod we keep cascade)
    pass
