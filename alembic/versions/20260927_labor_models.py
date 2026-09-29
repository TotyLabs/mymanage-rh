"""add labor model document instances and delivery events

Revision ID: 20260927_labor_models
Revises: gap_closure_009_resilience
"""

from alembic import op
import sqlalchemy as sa


revision = "20260927_labor_models"
down_revision = "gap_closure_009_resilience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "labor_model_documents",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("template_code", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False, server_default="1.0"),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="BORRADOR"),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("template_path", sa.Text(), nullable=False),
        sa.Column("rendered_pdf_path", sa.Text(), nullable=True),
        sa.Column("final_pdf_path", sa.Text(), nullable=True),
        sa.Column("rendered_pdf_sha256", sa.Text(), nullable=True),
        sa.Column("final_pdf_sha256", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("signed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["signed_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_labor_model_documents_org_created", "labor_model_documents", ["organization_id", "created_at"])
    op.create_index("ix_labor_model_documents_org_employee", "labor_model_documents", ["organization_id", "employee_id"])
    op.create_index("ix_labor_model_documents_org_status", "labor_model_documents", ["organization_id", "status"])

    op.create_table(
        "labor_model_email_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("labor_document_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("recipient_email", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["labor_document_id"], ["labor_model_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_labor_model_email_events_org_created", "labor_model_email_events", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_labor_model_email_events_org_created", table_name="labor_model_email_events")
    op.drop_table("labor_model_email_events")
    op.drop_index("ix_labor_model_documents_org_status", table_name="labor_model_documents")
    op.drop_index("ix_labor_model_documents_org_employee", table_name="labor_model_documents")
    op.drop_index("ix_labor_model_documents_org_created", table_name="labor_model_documents")
    op.drop_table("labor_model_documents")