"""Add missing columns for Phase 5 hardening.

Revision ID: gap_closure_002_cols
Revises: e550d69cab8a
Create Date: 2026-03-14 13:58:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'gap_closure_002_cols'
down_revision = 'e550d69cab8a'
branch_labels = None
depends_on = None


def upgrade():
    # Helper to check if column exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # 1. Update payroll_receipts
    existing_receipt_cols = [c['name'] for c in inspector.get_columns('payroll_receipts')]
    
    if 'requires_employer' not in existing_receipt_cols:
        op.add_column('payroll_receipts', sa.Column('requires_employer', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    if 'requires_employee' not in existing_receipt_cols:
        op.add_column('payroll_receipts', sa.Column('requires_employee', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    if 'verification_id' not in existing_receipt_cols:
        op.add_column('payroll_receipts', sa.Column('verification_id', sa.Text(), nullable=True))
        op.create_index('idx_receipt_verification_id', 'payroll_receipts', ['verification_id'], unique=True)

    # 2. Update signature_evidence
    existing_evidence_cols = [c['name'] for c in inspector.get_columns('signature_evidence')]
    
    if 'receipt_id' not in existing_evidence_cols:
        op.add_column('signature_evidence', sa.Column('receipt_id', sa.UUID(as_uuid=False), sa.ForeignKey('payroll_receipts.id', ondelete='CASCADE'), index=True))
    if 'verification_id' not in existing_evidence_cols:
        op.add_column('signature_evidence', sa.Column('verification_id', sa.Text(), nullable=True))
        op.create_index('idx_evidence_verification_id', 'signature_evidence', ['verification_id'], unique=True)


def downgrade():
    op.drop_index('idx_evidence_verification_id', table_name='signature_evidence')
    op.drop_index('idx_receipt_verification_id', table_name='payroll_receipts')
    op.drop_column('signature_evidence', 'verification_id')
    op.drop_column('signature_evidence', 'receipt_id')
    op.drop_column('payroll_receipts', 'verification_id')
    op.drop_column('payroll_receipts', 'requires_employee')
    op.drop_column('payroll_receipts', 'requires_employer')
