"""gap_closure_008_industrial_hardening

Revision ID: 72d2ed2c2f0b
Revises: gap_closure_006_otp_verification
Create Date: 2026-04-06 14:30:55.640143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72d2ed2c2f0b'
down_revision: Union[str, Sequence[str], None] = 'gap_closure_006_otp_verification'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Ensure pgcrypto is available for hashing
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 1. Receipts Table Expansion (Unified Source of Truth)
    # Check existing columns to avoid errors if some already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_receipt_cols = [c['name'] for c in inspector.get_columns('receipts')]

    if 'employee_id' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employees.id', ondelete='SET NULL'), nullable=True))
    if 'page_number' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('page_number', sa.Integer(), nullable=True))
    if 'deleted_at' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    if 'receipt_metadata' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('receipt_metadata', sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    if 'employer_signed_at' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('employer_signed_at', sa.TIMESTAMP(timezone=True), nullable=True))
    if 'employee_signed_at' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('employee_signed_at', sa.TIMESTAMP(timezone=True), nullable=True))
    if 'is_signed' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('is_signed', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    if 'document_locked' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('document_locked', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    if 'processing_signature' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('processing_signature', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    if 'requires_employer' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('requires_employer', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    if 'requires_employee' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('requires_employee', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    if 'verification_id' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('verification_id', sa.Text(), nullable=True))
        op.create_index(op.f('ix_receipts_verification_id'), 'receipts', ['verification_id'], unique=True)
    if 'batch_id' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('batch_id', sa.UUID(), sa.ForeignKey('payroll_batches.id', ondelete='SET NULL'), nullable=True))
    if 'is_deleted' not in existing_receipt_cols:
        op.add_column('receipts', sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False))
        
    # 1.1 Ensure payroll_receipts also captures is_deleted (CRT-001)
    existing_payroll_cols = [c['name'] for c in inspector.get_columns('payroll_receipts')]
    if 'is_deleted' not in existing_payroll_cols:
        op.add_column('payroll_receipts', sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    op.alter_column('receipts', 'user_id', existing_type=sa.UUID(), nullable=True)
    
    # 2. Audit Log Chain
    op.add_column('audit_log', sa.Column('previous_hash', sa.Text(), nullable=True))
    op.add_column('audit_log', sa.Column('chain_hash', sa.Text(), nullable=True))
    
    # 3. Soft Delete Uniformity
    op.add_column('users', sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('employees', sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('employees', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))

    # 4. Data Migration: payroll_receipts -> receipts
    # Map organization_id -> company_id and extracted_fields -> receipt_metadata
    op.execute("""
        INSERT INTO receipts (
            id, user_id, company_id, employee_id, file_path, file_hash, 
            receipt_metadata, status, signed_at, created_at, 
            employer_signed_at, employee_signed_at, is_signed, 
            document_locked, processing_signature, requires_employer, 
            requires_employee, verification_id, batch_id, is_deleted, 
            page_number
        )
        SELECT 
            pr.id, u.id, pr.organization_id, pr.employee_id, pr.receipt_pdf_path, pr.receipt_pdf_sha256,
            pr.extracted_fields, 
            CASE WHEN pr.status::text = 'signed' THEN 'signed' ELSE 'pending' END,
            pr.signed_at, pr.created_at,
            pr.employer_signed_at, pr.employee_signed_at, 
            (pr.status::text = 'signed'), pr.document_locked, pr.processing_signature,
            pr.requires_employer, pr.requires_employee, pr.verification_id, pr.batch_id, pr.is_deleted,
            pr.page_number
        FROM payroll_receipts pr
        LEFT JOIN users u ON u.employee_id = pr.employee_id
        ON CONFLICT (id) DO NOTHING;
    """)

    # 5. Audit Log Hash Trigger Logic
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_hasher_func() RETURNS trigger AS $$
        DECLARE
            prev_hash TEXT;
        BEGIN
            -- Get context of previous record
            SELECT chain_hash INTO prev_hash FROM audit_log ORDER BY id DESC LIMIT 1;
            IF prev_hash IS NULL THEN
                prev_hash := 'GENESIS';
            END IF;
            
            NEW.previous_hash := prev_hash;
            NEW.chain_hash := encode(digest(NEW.data::text || prev_hash, 'sha256'), 'hex');
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER audit_log_hasher_trigger
        BEFORE INSERT ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_hasher_func();
    """)

    # 6. Append-Only Enforcement
    op.execute("""
        CREATE OR REPLACE FUNCTION protect_audit_log_full() RETURNS trigger AS $$
        BEGIN
            IF (TG_OP = 'DELETE' OR TG_OP = 'UPDATE' OR TG_OP = 'TRUNCATE') THEN
                RAISE EXCEPTION 'Audit log is append-only. Modification of history is strictly prohibited.';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER audit_log_immutability_trigger
        BEFORE DELETE OR UPDATE OR TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION protect_audit_log_full();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_hasher_trigger ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutability_trigger ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_hasher_func()")
    op.execute("DROP FUNCTION IF EXISTS protect_audit_log_full()")
    
    op.drop_column('employees', 'deleted_at')
    op.drop_column('employees', 'is_deleted')
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'is_deleted')
    
    op.drop_column('audit_log', 'chain_hash')
    op.drop_column('audit_log', 'previous_hash')
    
    op.drop_column('receipts', 'deleted_at')
    op.drop_column('receipts', 'page_number')
    op.drop_column('receipts', 'employee_id')
    op.alter_column('receipts', 'user_id', existing_type=sa.UUID(), nullable=False)
