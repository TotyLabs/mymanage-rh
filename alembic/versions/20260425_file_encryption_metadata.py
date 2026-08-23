"""Add file encryption metadata for envelope encryption.

Revision ID: 20260425_file_encryption_metadata
Revises: add_password_reset_tokens
Create Date: 2026-04-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260425_file_encryption_metadata"
down_revision: Union[str, Sequence[str], None] = "add_password_reset_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS file_encryption_metadata (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            file_id UUID NOT NULL UNIQUE,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            storage_path TEXT NOT NULL,
            encrypted_data_key TEXT NOT NULL,
            nonce TEXT NOT NULL,
            auth_tag TEXT NOT NULL,
            algorithm TEXT NOT NULL DEFAULT 'AES-256-GCM',
            kms_key_id TEXT NOT NULL,
            kms_provider TEXT NOT NULL,
            purpose TEXT NOT NULL,
            plaintext_sha256 CHAR(64),
            ciphertext_sha256 CHAR(64),
            encryption_context JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_decrypted_at TIMESTAMPTZ,
            CONSTRAINT uq_file_encryption_org_path UNIQUE (organization_id, storage_path),
            CONSTRAINT ck_file_encryption_algorithm CHECK (algorithm = 'AES-256-GCM')
        );

        CREATE INDEX IF NOT EXISTS idx_file_encryption_org
            ON file_encryption_metadata (organization_id);

        CREATE INDEX IF NOT EXISTS idx_file_encryption_purpose
            ON file_encryption_metadata (organization_id, purpose);

        CREATE INDEX IF NOT EXISTS idx_file_encryption_storage_path
            ON file_encryption_metadata (storage_path);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS file_encryption_metadata;")
