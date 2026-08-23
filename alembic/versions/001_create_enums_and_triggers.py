"""Create extensions, enums and triggers safely

Revision ID: 001_create_enums_and_triggers
Revises: 000_initial
Create Date: 2026-01-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_create_enums_and_triggers'
down_revision = '000_initial'
branch_labels = None
depends_on = None


def upgrade():
    # Ensure extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")

    # Create enums if not exists (use pg_type check to support older Postgres)
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'receipt_status') THEN
            CREATE TYPE receipt_status AS ENUM ('pending_match','pending_signature','signed','rejected');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'signature_status') THEN
            CREATE TYPE signature_status AS ENUM ('pending','signed','rejected','expired');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'actor_type') THEN
            CREATE TYPE actor_type AS ENUM ('admin','employee','system');
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
            CREATE TYPE user_role AS ENUM ('admin','employee');
        END IF;
    END
    $$;
    """)

    # Functions and triggers: create if they don't exist
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'validate_signature_request_org') THEN
            CREATE OR REPLACE FUNCTION validate_signature_request_org() 
            RETURNS TRIGGER AS $fn$
            DECLARE 
                r_org UUID; 
                e_org UUID;
            BEGIN
                SELECT organization_id INTO r_org FROM payroll_receipts WHERE id = NEW.receipt_id;
                IF r_org IS NULL THEN RAISE EXCEPTION 'receipt_not_found: %', NEW.receipt_id; END IF;
                IF r_org IS DISTINCT FROM NEW.organization_id THEN RAISE EXCEPTION 'org_mismatch_receipt: receipt_org=%, request_org=%', r_org, NEW.organization_id; END IF;
                SELECT organization_id INTO e_org FROM employees WHERE id = NEW.employee_id;
                IF e_org IS NULL THEN RAISE EXCEPTION 'employee_not_found: %', NEW.employee_id; END IF;
                IF e_org IS DISTINCT FROM NEW.organization_id THEN RAISE EXCEPTION 'org_mismatch_employee: emp_org=%, request_org=%', e_org, NEW.organization_id; END IF;
                RETURN NEW;
            END;
            $fn$ LANGUAGE plpgsql;
        END IF;

        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'signature_requests' AND relkind = 'r') THEN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_validate_sig_req_org') THEN
                CREATE TRIGGER trg_validate_sig_req_org 
                    BEFORE INSERT OR UPDATE ON signature_requests
                    FOR EACH ROW EXECUTE FUNCTION validate_signature_request_org();
            END IF;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'protect_signed_receipts') THEN
            CREATE OR REPLACE FUNCTION protect_signed_receipts()
            RETURNS TRIGGER AS $fn$
            BEGIN
                IF OLD.status = 'signed' THEN
                    IF NEW.receipt_pdf_path IS DISTINCT FROM OLD.receipt_pdf_path THEN RAISE EXCEPTION 'immutable_field: receipt_pdf_path'; END IF;
                    IF NEW.receipt_pdf_sha256 IS DISTINCT FROM OLD.receipt_pdf_sha256 THEN RAISE EXCEPTION 'immutable_field: receipt_pdf_sha256'; END IF;
                    IF NEW.employee_id IS DISTINCT FROM OLD.employee_id THEN RAISE EXCEPTION 'immutable_field: employee_id'; END IF;
                    IF NEW.batch_id IS DISTINCT FROM OLD.batch_id THEN RAISE EXCEPTION 'immutable_field: batch_id'; END IF;
                    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN RAISE EXCEPTION 'immutable_field: organization_id'; END IF;
                    IF NEW.signed_at IS DISTINCT FROM OLD.signed_at THEN RAISE EXCEPTION 'immutable_field: signed_at'; END IF;
                END IF;
                RETURN NEW;
            END;
            $fn$ LANGUAGE plpgsql;
        END IF;

        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'payroll_receipts' AND relkind = 'r') THEN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_protect_signed_receipts') THEN
                CREATE TRIGGER trg_protect_signed_receipts
                    BEFORE UPDATE ON payroll_receipts
                    FOR EACH ROW EXECUTE FUNCTION protect_signed_receipts();
            END IF;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'protect_signature_evidence') THEN
            CREATE OR REPLACE FUNCTION protect_signature_evidence()
            RETURNS TRIGGER AS $fn$
            BEGIN
                IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'signature_evidence_immutable: cannot update';
                ELSIF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'signature_evidence_immutable: cannot delete'; END IF;
                RETURN NULL;
            END;
            $fn$ LANGUAGE plpgsql;
        END IF;

        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'signature_evidence' AND relkind = 'r') THEN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_protect_signature_evidence') THEN
                CREATE TRIGGER trg_protect_signature_evidence
                    BEFORE UPDATE OR DELETE ON signature_evidence
                    FOR EACH ROW EXECUTE FUNCTION protect_signature_evidence();
            END IF;
        END IF;
    END
    $$;
    """)


def downgrade():
    # No-op: do not drop types/triggers on downgrade to avoid data loss in production.
    pass
