"""add_bank_and_payment_receipt_fields

Revision ID: cd5841f53c4c
Revises: e468b5e58daf
Create Date: 2026-03-30 09:51:50.240231

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd5841f53c4c'
down_revision: Union[str, Sequence[str], None] = 'e468b5e58daf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to employees table
    op.add_column('employees', sa.Column('bank_code', sa.String(length=10), nullable=True))
    op.add_column('employees', sa.Column('bank_branch', sa.String(length=20), nullable=True))
    
    # Add columns to payroll_receipts table
    op.add_column('payroll_receipts', sa.Column('payment_receipt_path', sa.String(length=1000), nullable=True))
    op.add_column('payroll_receipts', sa.Column('payment_upload_date', sa.DateTime(), nullable=True))
    op.add_column('payroll_receipts', sa.Column('payment_uploaded_by', sa.UUID(), nullable=True))


def downgrade() -> None:
    # Remove columns from payroll_receipts table
    op.drop_column('payroll_receipts', 'payment_uploaded_by')
    op.drop_column('payroll_receipts', 'payment_upload_date')
    op.drop_column('payroll_receipts', 'payment_receipt_path')
    
    # Remove columns from employees table
    op.drop_column('employees', 'bank_branch')
    op.drop_column('employees', 'bank_code')
