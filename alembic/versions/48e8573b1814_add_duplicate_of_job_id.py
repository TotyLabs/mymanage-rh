"""add_duplicate_of_job_id

Revision ID: 48e8573b1814
Revises: 0617d24ec52f
Create Date: 2026-03-21 23:58:48.096237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = '48e8573b1814'
down_revision: Union[str, Sequence[str], None] = '0617d24ec52f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("duplicate_of_job_id", PG_UUID(as_uuid=False), sa.ForeignKey("import_jobs.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("import_jobs", "duplicate_of_job_id")
