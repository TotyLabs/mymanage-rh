"""add_duplicate_group_id

Revision ID: e199ebd9dfd9
Revises: 48e8573b1814
Create Date: 2026-03-21 23:59:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = 'e199ebd9dfd9'
down_revision: Union[str, Sequence[str], None] = '48e8573b1814'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("duplicate_group_id", PG_UUID(as_uuid=False), nullable=True))
    op.create_index(op.f("ix_import_jobs_duplicate_group_id"), "import_jobs", ["duplicate_group_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_import_jobs_duplicate_group_id"), table_name="import_jobs")
    op.drop_column("import_jobs", "duplicate_group_id")
