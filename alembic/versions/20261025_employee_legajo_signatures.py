"""add employee legajo signature requests

Revision ID: 20261025_employee_legajo_signatures
Revises: 20260714_add_address_number, 20260927_labor_models
"""

from alembic import op
import sqlalchemy as sa


revision = "20261025_employee_legajo_signatures"
down_revision = ("20260714_add_address_number", "20260927_labor_models")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_legajo_signatures",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("signed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("employee_cuil", sa.Text(), nullable=False),
        sa.Column("employee_email", sa.Text(), nullable=False),
        sa.Column("employee_name", sa.Text(), nullable=False),
        sa.Column("source_pdf_path", sa.Text(), nullable=False),
        sa.Column("signed_pdf_path", sa.Text(), nullable=True),
        sa.Column("source_pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("signed_pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("signature_hash", sa.String(length=64), nullable=True),
        sa.Column("seal_id", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("processing_signature", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("issuer_ip", sa.Text(), nullable=True),
        sa.Column("issuer_ua", sa.Text(), nullable=True),
        sa.Column("signer_ip", sa.Text(), nullable=True),
        sa.Column("signer_ua", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["signed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name="uq_employee_legajo_signature_token_hash"),
        sa.UniqueConstraint("seal_id", name="uq_employee_legajo_signature_seal_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'signed', 'expired', 'cancelled')",
            name="ck_employee_legajo_signature_status",
        ),
    )
    op.create_index(
        "ix_employee_legajo_signature_org_created",
        "employee_legajo_signatures",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_employee_legajo_signature_employee_created",
        "employee_legajo_signatures",
        ["employee_id", "created_at"],
    )
    op.create_index(
        "uq_employee_legajo_signature_pending",
        "employee_legajo_signatures",
        ["organization_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_employee_legajo_signature_pending", table_name="employee_legajo_signatures")
    op.drop_index("ix_employee_legajo_signature_employee_created", table_name="employee_legajo_signatures")
    op.drop_index("ix_employee_legajo_signature_org_created", table_name="employee_legajo_signatures")
    op.drop_table("employee_legajo_signatures")
