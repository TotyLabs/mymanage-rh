"""add_legajo_import_tables

Revision ID: 0617d24ec52f
Revises: 0fad728e0601
Create Date: 2026-03-21 23:37:14.960005

Creates:
  - employee_extra_data (1:1 extension for legajo fields)
  - import_jobs (import session tracking with idempotency)
  - import_job_rows (per-row parse/validation result)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '0617d24ec52f'
down_revision: Union[str, Sequence[str], None] = '0fad728e0601'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # â”€â”€ employee_extra_data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    op.create_table(
        "employee_extra_data",
        sa.Column("id", PG_UUID(as_uuid=False), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("employee_id", PG_UUID(as_uuid=False), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, unique=True),

        # Identity extended
        sa.Column("document_type_code", sa.Text()),
        sa.Column("anses_doc_issue_place_code", sa.Text()),
        sa.Column("nationality_code", sa.Text()),
        sa.Column("marital_status_code", sa.Text()),
        sa.Column("sex_code", sa.Text()),

        # Address granular
        sa.Column("street_number", sa.Text()),
        sa.Column("floor", sa.Text()),
        sa.Column("apartment", sa.Text()),
        sa.Column("tower", sa.Text()),
        sa.Column("paraje", sa.Text()),
        sa.Column("locality_code", sa.Text()),
        sa.Column("province_code", sa.Text()),

        # Employment extended
        sa.Column("category_code", sa.Text()),
        sa.Column("section_code", sa.Text()),
        sa.Column("task_code", sa.Text()),
        sa.Column("position_code", sa.Text()),
        sa.Column("activity_code", sa.Text()),
        sa.Column("labor_condition_code", sa.Text()),
        sa.Column("contract_mode_code", sa.Text()),
        sa.Column("afip_revista_status_code", sa.Text()),
        sa.Column("afip_locality_province_code", sa.Text()),
        sa.Column("hazardous_task_code", sa.Text()),
        sa.Column("workday_type_code", sa.Text()),
        sa.Column("remuneration_type_code", sa.Text()),
        sa.Column("payment_place_code", sa.Text()),
        sa.Column("payroll_concept_group_code", sa.Text()),
        sa.Column("assigned_monthly_hours", sa.Integer()),

        # Union / agreement
        sa.Column("union_agreement_code", sa.Text()),
        sa.Column("agreement_type_code", sa.Text()),
        sa.Column("union_member_number", sa.Text()),

        # Payroll / legacy identifiers
        sa.Column("legajo_number", sa.Text()),
        sa.Column("card_number", sa.Text()),
        sa.Column("ieric_number", sa.Text()),

        # Social security
        sa.Column("health_insurance_code", sa.Text()),
        sa.Column("retirement_regime_code", sa.Text()),
        sa.Column("unemployment_fund_account", sa.Text()),

        # Import source metadata
        sa.Column("source_last_import_job_id", PG_UUID(as_uuid=False)),
        sa.Column("source_last_imported_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("source_last_format", sa.Text()),
        sa.Column("source_hash", sa.Text()),

        # Audit
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_employee_extra_data_employee_id", "employee_extra_data", ["employee_id"], unique=True)

    # â”€â”€ import_jobs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    op.create_table(
        "import_jobs",
        sa.Column("id", PG_UUID(as_uuid=False), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("organization_id", PG_UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", PG_UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL")),

        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text()),
        sa.Column("stored_file_path", sa.Text()),
        sa.Column("file_sha256", sa.CHAR(64)),

        sa.Column("parser_version", sa.Text(), server_default=sa.text("'1'")),
        sa.Column("mapping_version", sa.Text(), server_default=sa.text("'1'")),
        sa.Column("validator_version", sa.Text(), server_default=sa.text("'1'")),

        sa.Column("import_mode", sa.Text(), server_default=sa.text("'merge'")),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),

        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'uploaded'")),

        sa.Column("total_rows", sa.Integer(), server_default=sa.text("0")),
        sa.Column("valid_rows", sa.Integer(), server_default=sa.text("0")),
        sa.Column("invalid_rows", sa.Integer(), server_default=sa.text("0")),
        sa.Column("warning_rows", sa.Integer(), server_default=sa.text("0")),
        sa.Column("inserted_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("updated_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("skipped_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("conflicted_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer(), server_default=sa.text("0")),

        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),

        sa.Column("error_summary_json", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("warning_summary_json", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),

        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),

        sa.UniqueConstraint("organization_id", "file_sha256", name="uq_import_job_org_sha"),
    )
    op.create_index("idx_import_job_org_id", "import_jobs", ["organization_id"])
    op.create_index("idx_import_job_org_created", "import_jobs", ["organization_id", "created_at"])

    # â”€â”€ import_job_rows â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    op.create_table(
        "import_job_rows",
        sa.Column("id", PG_UUID(as_uuid=False), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("import_job_id", PG_UUID(as_uuid=False), sa.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False),

        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("external_key", sa.Text()),

        sa.Column("raw_data_json", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("normalized_data_json", JSONB, server_default=sa.text("'{}'::jsonb")),

        sa.Column("validation_errors_json", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("validation_warnings_json", JSONB, server_default=sa.text("'[]'::jsonb")),

        sa.Column("matching_result_json", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("planned_action", sa.Text()),
        sa.Column("resolution_status", sa.Text(), server_default=sa.text("'pending'")),

        sa.Column("matched_employee_id", PG_UUID(as_uuid=False)),

        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_import_row_job_id", "import_job_rows", ["import_job_id"])
    op.create_index("idx_import_row_job_rownum", "import_job_rows", ["import_job_id", "source_row_number"])
    op.create_index("idx_import_row_job_action", "import_job_rows", ["import_job_id", "planned_action"])


def downgrade() -> None:
    op.drop_table("import_job_rows")
    op.drop_table("import_jobs")
    op.drop_table("employee_extra_data")
