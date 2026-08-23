"""add_issuer_user_id_and_enterprise_support

Revision ID: e519a2f40413
Revises: 20260425_file_encryption_metadata
Create Date: 2026-05-02 23:09:14.942981

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e519a2f40413'
down_revision: Union[str, Sequence[str], None] = '20260425_file_encryption_metadata'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add issuer_user_id to signature_requests
    op.execute("ALTER TABLE signature_requests ADD COLUMN IF NOT EXISTS issuer_user_id UUID")
    
    # 2. Drop the restrictive foreign key to allow User IDs in the employee_id column (Enterprise mode)
    op.execute("ALTER TABLE signature_requests DROP CONSTRAINT IF EXISTS signature_requests_employee_id_fkey")
    
    # 3. Update validate_signature_request_org trigger function
    op.execute("""
    CREATE OR REPLACE FUNCTION public.validate_signature_request_org()
    RETURNS trigger AS $$
    DECLARE 
        r_org UUID; 
        e_org UUID;
    BEGIN
        -- 1. Validate Receipt and Org
        IF NEW.receipt_id IS NOT NULL THEN
            -- Legacy path
            SELECT organization_id INTO r_org FROM payroll_receipts WHERE id = NEW.receipt_id;
            IF r_org IS NULL THEN RAISE EXCEPTION 'receipt_not_found: %', NEW.receipt_id; END IF;
        ELSIF NEW.enterprise_receipt_id IS NOT NULL THEN
            -- Enterprise path
            SELECT company_id INTO r_org FROM receipts WHERE id = NEW.enterprise_receipt_id;
            IF r_org IS NULL THEN RAISE EXCEPTION 'enterprise_receipt_not_found: %', NEW.enterprise_receipt_id; END IF;
        ELSE
            RAISE EXCEPTION 'missing_receipt_reference: both receipt_id and enterprise_receipt_id are NULL';
        END IF;

        IF r_org IS DISTINCT FROM NEW.organization_id THEN 
            RAISE EXCEPTION 'org_mismatch_receipt: receipt_org=%, request_org=%', r_org, NEW.organization_id; 
        END IF;

        -- 2. Validate Employee/User and Org
        IF NEW.employee_id IS NOT NULL THEN
            -- Check both employees (Legacy) and users (Enterprise) tables
            SELECT organization_id INTO e_org FROM employees WHERE id = NEW.employee_id;
            
            IF e_org IS NULL THEN
                SELECT organization_id INTO e_org FROM users WHERE id = NEW.employee_id;
            END IF;

            IF e_org IS NULL THEN RAISE EXCEPTION 'signer_identity_not_found: %', NEW.employee_id; END IF;
            
            IF e_org IS DISTINCT FROM NEW.organization_id THEN 
                RAISE EXCEPTION 'org_mismatch_signer: signer_org=%, request_org=%', e_org, NEW.organization_id; 
            END IF;
        ELSE
            RAISE EXCEPTION 'missing_signer_identity: employee_id/user_id is mandatory';
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Revert validate_signature_request_org to legacy version
    op.execute("""
    CREATE OR REPLACE FUNCTION public.validate_signature_request_org() 
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
    """)
    
    # 2. Drop issuer_user_id
    op.drop_column('signature_requests', 'issuer_user_id')
