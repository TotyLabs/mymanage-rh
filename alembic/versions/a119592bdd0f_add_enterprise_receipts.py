"""add_enterprise_receipts

Revision ID: a119592bdd0f
Revises: 716fda4aa427
Create Date: 2026-04-02 19:12:07.096427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a119592bdd0f'
down_revision: Union[str, Sequence[str], None] = '716fda4aa427'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema and migrate data."""
    # 1. Create receipts table
    op.create_table(
        'receipts',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=False), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('company_id', sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column('signed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('signature_snapshot', sa.LargeBinary(), nullable=True),
        sa.Column('signature_hash', sa.String(64), nullable=True),
        sa.Column('tsa_timestamp', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_receipts_user_status', 'receipts', ['user_id', 'status'], unique=False)
    op.create_index(op.f('ix_receipts_company_id'), 'receipts', ['company_id'], unique=False)
    op.create_index(op.f('ix_receipts_user_id'), 'receipts', ['user_id'], unique=False)

    # 2. Data Migration: payroll_receipts -> receipts
    # Link: payroll_receipts.employee_id -> employees.id <- users.employee_id
    op.execute("""
        INSERT INTO receipts (user_id, company_id, file_path, file_hash, status, signed_at, created_at)
        SELECT 
            u.id, 
            pr.organization_id, 
            pr.receipt_pdf_path, 
            pr.receipt_pdf_sha256,
            CASE WHEN pr.status = 'signed' THEN 'signed' ELSE 'pending' END,
            pr.signed_at,
            pr.created_at
        FROM payroll_receipts pr
        JOIN users u ON u.employee_id = pr.employee_id
        WHERE pr.employee_id IS NOT NULL;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_receipts_user_id'), table_name='receipts')
    op.drop_index(op.f('ix_receipts_company_id'), table_name='receipts')
    op.drop_index('idx_receipts_user_status', table_name='receipts')
    op.drop_table('receipts')

