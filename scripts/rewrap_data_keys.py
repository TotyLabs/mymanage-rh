#!/usr/bin/env python3
"""
Data Key Rewrap CLI — KEK rotation without re-encrypting files.

When the KMS master key (KEK) is rotated, this script re-wraps all existing
data keys with the new KEK. The actual file ciphertext is never touched.

Usage:
    python scripts/rewrap_data_keys.py --old-key-id <OLD_KEY> --new-key-id <NEW_KEY> [OPTIONS]

Options:
    --old-key-id        KMS key ID of the current (old) KEK.
    --new-key-id        KMS key ID of the new KEK.
    --organization-id   Optional: scope to a single organization.
    --batch-size        Number of records per batch (default: 100).
    --dry-run           Simulate without writing changes.
    --help              Show this help message.

Requires:
    - DATABASE_URL and encryption config in environment.
    - Appropriate KMS permissions for Decrypt (old key) and Encrypt (new key).

Audit:
    Each rewrapped data key generates a 'data_key_rewrapped' event in audit_log.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SECRET_KEY", os.environ.get("SECRET_KEY", ""))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("rewrap_data_keys")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrap encrypted data keys with a new KMS KEK.",
        epilog="This script never decrypts file content — only data keys.",
    )
    parser.add_argument(
        "--old-key-id",
        required=True,
        help="KMS key ID of the current (old) KEK.",
    )
    parser.add_argument(
        "--new-key-id",
        required=True,
        help="KMS key ID of the new KEK to wrap data keys with.",
    )
    parser.add_argument(
        "--organization-id",
        default=None,
        help="Optional: limit rewrap to a single organization UUID.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Records per batch (default: 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without persisting changes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.old_key_id == args.new_key_id:
        logger.error("old-key-id and new-key-id must be different.")
        sys.exit(1)

    # Late imports so env is loaded
    from sqlalchemy import text
    from payroll_core import SessionLocal, safe_transaction, audit

    from services.encryption_service import (
        EncryptionService,
        get_encryption_service,
        _zeroize,
    )

    service = get_encryption_service()
    provider = service.kms_provider

    logger.info(
        "rewrap.start old_key=%s new_key=%s org=%s dry_run=%s batch_size=%d",
        args.old_key_id,
        args.new_key_id,
        args.organization_id or "ALL",
        args.dry_run,
        args.batch_size,
    )

    db = SessionLocal()
    total_processed = 0
    total_rewrapped = 0
    total_errors = 0

    try:
        # Build query
        where_clauses = ["kms_key_id = :old_key_id"]
        params: dict = {"old_key_id": args.old_key_id}

        if args.organization_id:
            where_clauses.append("organization_id = CAST(:org AS UUID)")
            params["org"] = args.organization_id

        where_sql = " AND ".join(where_clauses)

        # Count total
        count_row = db.execute(
            text(f"SELECT COUNT(*) FROM file_encryption_metadata WHERE {where_sql}"),
            params,
        ).scalar()
        logger.info("rewrap.found_records count=%d", count_row)

        if count_row == 0:
            logger.info("rewrap.nothing_to_do")
            return

        # Process in batches
        offset = 0
        while offset < count_row:
            rows = db.execute(
                text(f"""
                    SELECT id, file_id, organization_id, storage_path,
                           encrypted_data_key, encryption_context,
                           kms_key_id, kms_provider, purpose
                    FROM file_encryption_metadata
                    WHERE {where_sql}
                    ORDER BY created_at
                    LIMIT :limit OFFSET :offset
                """),
                {**params, "limit": args.batch_size, "offset": offset},
            ).mappings().fetchall()

            for row in rows:
                total_processed += 1
                row_dict = dict(row)
                file_id = str(row_dict["file_id"])
                org_id = str(row_dict["organization_id"])

                try:
                    # Reconstruct encryption context
                    import json
                    enc_ctx = row_dict.get("encryption_context")
                    if isinstance(enc_ctx, str):
                        enc_ctx = json.loads(enc_ctx)
                    elif enc_ctx is None:
                        enc_ctx = {}
                    string_ctx = {str(k): str(v) for k, v in enc_ctx.items()}

                    # Decrypt data key with old KEK
                    plaintext_key = provider.decrypt_data_key(
                        row_dict["encrypted_data_key"],
                        string_ctx,
                        args.old_key_id,
                    )

                    # Re-encrypt with new KEK via generate + discard new key approach
                    # For production KMS: we'd use re-encrypt API if available
                    # Generic approach: encrypt the existing plaintext_key with new KEK
                    new_dk = provider.generate_data_key(string_ctx)
                    # We don't need the new plaintext key — we keep the original
                    _zeroize(new_dk.plaintext_key)

                    # For local provider: we need to wrap the original key with new KEK
                    # This requires a wrap operation. Since not all providers have ReEncrypt,
                    # we use the service-level rewrap method.
                    new_encrypted = service.rewrap_data_key(
                        plaintext_key=plaintext_key,
                        new_key_id=args.new_key_id,
                        encryption_context=string_ctx,
                    )
                    _zeroize(plaintext_key)

                    if args.dry_run:
                        logger.info(
                            "rewrap.dry_run file_id=%s org=%s OK",
                            file_id, org_id,
                        )
                    else:
                        with safe_transaction(db):
                            db.execute(
                                text("""
                                    UPDATE file_encryption_metadata
                                    SET encrypted_data_key = :new_edk,
                                        kms_key_id = :new_key_id
                                    WHERE id = :id
                                """),
                                {
                                    "new_edk": new_encrypted,
                                    "new_key_id": args.new_key_id,
                                    "id": row_dict["id"],
                                },
                            )
                            audit(
                                db, org_id, "system", None,
                                "data_key_rewrapped",
                                file_id,
                                {
                                    "file_id": file_id,
                                    "purpose": row_dict["purpose"],
                                    "old_kms_key_id": args.old_key_id,
                                    "new_kms_key_id": args.new_key_id,
                                    "storage_path": row_dict["storage_path"],
                                },
                            )

                    total_rewrapped += 1
                    if total_processed % 50 == 0:
                        logger.info(
                            "rewrap.progress processed=%d rewrapped=%d errors=%d",
                            total_processed, total_rewrapped, total_errors,
                        )

                except Exception as exc:
                    total_errors += 1
                    logger.error(
                        "rewrap.failed file_id=%s org=%s error=%s",
                        file_id, org_id, str(exc),
                    )

            offset += args.batch_size

    finally:
        db.close()

    logger.info(
        "rewrap.complete total_processed=%d rewrapped=%d errors=%d dry_run=%s",
        total_processed,
        total_rewrapped,
        total_errors,
        args.dry_run,
    )

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
