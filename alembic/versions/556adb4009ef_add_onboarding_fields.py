"""Auto-generated Alembic script template.

Revision ID: 556adb4009ef
Revises: 'a23ca2e38a15'
Create Date: 2026-02-19 17:01:02.514481
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.

# revision identifiers, used by Alembic.
revision = '556adb4009ef'
down_revision = 'a23ca2e38a15'
branch_labels = None
depends_on = None


import traceback

def upgrade():
    try:
        _upgrade()
    except Exception:
        with open("migration_debug.log", "w") as f:
            traceback.print_exc(file=f)
        raise

def _upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns_emp = [c['name'] for c in inspector.get_columns('employees')]
    existing_columns_users = [c['name'] for c in inspector.get_columns('users')]
    existing_tables = inspector.get_table_names()

    # 1. Create EmployeeStatus ENUM if missing
    res = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'employee_status'")).fetchone()
    if not res:
        # We need to execute outside of a transaction or just be careful. 
        # Actually, op.execute is usually fine if we don't catch and continue on error.
        op.execute("CREATE TYPE employee_status AS ENUM ('pre_registered', 'active')")

    # 2. Update Employees Table
    op.alter_column('employees', 'cuil', nullable=True)
    
    if 'dni' not in existing_columns_emp:
        op.add_column('employees', sa.Column('dni', sa.Text(), nullable=True))
    if 'status' not in existing_columns_emp:
        op.add_column('employees', sa.Column('status', postgresql.ENUM('pre_registered', 'active', name='employee_status', create_type=False), server_default='pre_registered', nullable=False))
    if 'profile_completed' not in existing_columns_emp:
        op.add_column('employees', sa.Column('profile_completed', sa.Boolean(), server_default='false', nullable=False))
    
    for col in ['marital_status', 'birth_date', 'address', 'phone', 'position', 'hire_date']:
        if col not in existing_columns_emp:
             op.add_column('employees', sa.Column(col, sa.Text() if col != 'birth_date' and col != 'hire_date' else sa.DateTime(timezone=True), nullable=True))

    # Constraints (check if exists)
    existing_ucs_emp = [uc['name'] for uc in inspector.get_unique_constraints('employees')]
    if 'uq_employee_org_dni' not in existing_ucs_emp:
        op.create_unique_constraint('uq_employee_org_dni', 'employees', ['organization_id', 'dni'])

    # 3. Update Users Table
    for col in ['dni', 'cuil', 'marital_status', 'birth_date', 'address', 'phone', 'position', 'hire_date']:
        if col not in existing_columns_users:
            op.add_column('users', sa.Column(col, sa.Text() if col != 'birth_date' and col != 'hire_date' else sa.DateTime(timezone=True), nullable=True))
    
    existing_ucs_users = [uc['name'] for uc in inspector.get_unique_constraints('users')]
    if 'idx_users_dni' not in existing_ucs_users:
        op.create_unique_constraint('idx_users_dni', 'users', ['dni'])

    # 4. Create Signature Events Table
    if 'signature_events' not in existing_tables:
        op.create_table(
            'signature_events',
            sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('receipt_id', sa.UUID(), nullable=False),
            sa.Column('organization_id', sa.UUID(), nullable=False),
            sa.Column('actor_type', postgresql.ENUM('admin', 'employee', 'system', name='actor_type', create_type=False), nullable=False),
            sa.Column('actor_id', sa.UUID(), nullable=True),
            sa.Column('action', sa.Text(), nullable=False),
            sa.Column('status_before', sa.Text(), nullable=True),
            sa.Column('status_after', sa.Text(), nullable=True),
            sa.Column('pdf_sha256_before', sa.CHAR(length=64), nullable=True),
            sa.Column('pdf_sha256_after', sa.CHAR(length=64), nullable=True),
            sa.Column('ip_address', sa.dialects.postgresql.INET(), nullable=True),
            sa.Column('user_agent', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('data', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['receipt_id'], ['payroll_receipts.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade():
    op.drop_constraint('idx_users_dni', 'users', type_='unique')
    op.drop_column('users', 'hire_date')
    op.drop_column('users', 'position')
    op.drop_column('users', 'phone')
    op.drop_column('users', 'address')
    op.drop_column('users', 'birth_date')
    op.drop_column('users', 'marital_status')
    op.drop_column('users', 'cuil')
    op.drop_column('users', 'dni')

    op.drop_constraint('uq_employee_org_dni', 'employees', type_='unique')
    op.drop_column('employees', 'hire_date')
    op.drop_column('employees', 'position')
    op.drop_column('employees', 'phone')
    op.drop_column('employees', 'address')
    op.drop_column('employees', 'birth_date')
    op.drop_column('employees', 'marital_status')
    op.drop_column('employees', 'profile_completed')
    op.drop_column('employees', 'status')
    op.drop_column('employees', 'dni')


