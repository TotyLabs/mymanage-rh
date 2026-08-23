"""Add user signatures system

Revision ID: 716fda4aa427
Revises: e9b8869dfce9
Create Date: 2026-04-02 18:30:11.799028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '716fda4aa427'
down_revision: Union[str, Sequence[str], None] = 'e9b8869dfce9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # 1. Create table
    op.create_table(
        'user_signatures',
        sa.Column('id', postgresql.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(), nullable=False),
        sa.Column('signature_path', sa.Text(), nullable=False),
        sa.Column('signature_hash', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_signatures_user_id'), 'user_signatures', ['user_id'], unique=False)

    # 2. Migrate data
    op.execute("""
        INSERT INTO user_signatures (id, user_id, signature_path, signature_hash, created_at, is_active, version)
        SELECT uuid_generate_v4(), u.id, e.signature_image_path, NULL, NOW(), true, 1
        FROM employees e
        JOIN users u ON u.employee_id = e.id
        WHERE e.signature_image_path IS NOT NULL
    """)

    # 3. Drop old column
    op.drop_column('employees', 'signature_image_path')

def downgrade() -> None:
    # 1. Add column back
    op.add_column('employees', sa.Column('signature_image_path', sa.Text(), nullable=True))

    # 2. Discarding precise reverse-migration because it's destructive mostly, but we can attempt:
    op.execute("""
        UPDATE employees e
        SET signature_image_path = us.signature_path
        FROM user_signatures us
        JOIN users u ON u.id = us.user_id
        WHERE e.id = u.employee_id AND us.is_active = true
    """)

    # 3. Drop table
    op.drop_index(op.f('ix_user_signatures_user_id'), table_name='user_signatures')
    op.drop_table('user_signatures')
