"""add_missing_extra_data_columns

Revision ID: d3b90e9b555a
Revises: e199ebd9dfd9
Create Date: 2026-03-22 00:10:13.912219

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3b90e9b555a'
down_revision: Union[str, Sequence[str], None] = 'e199ebd9dfd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adding missing columns to employee_extra_data
    op.add_column("employee_extra_data", sa.Column("social_work_code", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("union_code", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("salary_amount", sa.Numeric(precision=18, scale=2)))
    op.add_column("employee_extra_data", sa.Column("salary_currency", sa.Text(), server_default=sa.text("'ARS'")))
    op.add_column("employee_extra_data", sa.Column("payment_method_code", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("bank_name", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("bank_branch", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("bank_cbu", sa.Text()))
    # bank_account_number was likely also missing
    op.add_column("employee_extra_data", sa.Column("bank_account_number", sa.Text()))
    
    # Address extensions
    op.add_column("employee_extra_data", sa.Column("address_street", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("address_city", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("address_province", sa.Text()))
    op.add_column("employee_extra_data", sa.Column("address_zip_code", sa.Text()))


def downgrade() -> None:
    op.drop_column("employee_extra_data", "address_zip_code")
    op.drop_column("employee_extra_data", "address_province")
    op.drop_column("employee_extra_data", "address_city")
    op.drop_column("employee_extra_data", "address_street")
    op.drop_column("employee_extra_data", "bank_account_number")
    op.drop_column("employee_extra_data", "bank_cbu")
    op.drop_column("employee_extra_data", "bank_branch")
    op.drop_column("employee_extra_data", "bank_name")
    op.drop_column("employee_extra_data", "payment_method_code")
    op.drop_column("employee_extra_data", "salary_currency")
    op.drop_column("employee_extra_data", "salary_amount")
    op.drop_column("employee_extra_data", "union_code")
    op.drop_column("employee_extra_data", "social_work_code")
