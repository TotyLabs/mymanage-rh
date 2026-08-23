"""
Migration: create webhook_outbox table for transactional outbox pattern.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "b1f0a0c00001"
down_revision = "556adb4009ef"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "webhook_outbox",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("receipt_id", UUID(as_uuid=False), sa.ForeignKey("payroll_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("retries", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_error_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("idx_webhook_outbox_pending", "webhook_outbox", ["status", "created_at"], postgresql_where=sa.text("status = 'pending'"))


def downgrade():
    op.drop_index("idx_webhook_outbox_pending", table_name="webhook_outbox")
    op.drop_table("webhook_outbox")
