"""add_unique_email_constraint_to_users

Revision ID: e468b5e58daf
Revises: gap_closure_005_user_status
Create Date: 2026-03-24 16:44:13.099047

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e468b5e58daf'
down_revision: Union[str, Sequence[str], None] = 'gap_closure_005_user_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if constraint exists before creating
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints('users')
    constraint_names = [c['name'] for c in constraints]
    
    if 'uq_users_email' not in constraint_names:
        op.create_unique_constraint('uq_users_email', 'users', ['email'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_email', 'users', type_='unique')
