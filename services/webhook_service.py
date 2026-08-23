"""
services/webhook_service.py

Idempotent webhook dispatcher for notifying external payroll systems
about receipt signature state changes (signed, rejected, expired).

- Stores outbound events in `webhook_outbox` (transactional outbox pattern).
- Background coroutine drains the outbox with exponential backoff retries.
- Dead-letter after MAX_RETRIES so the outbox never grows unbounded.
"""

import os
import json
import asyncio
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("dircom.payroll.webhooks")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WEBHOOK_URL: Optional[str] = os.getenv("PAYROLL_WEBHOOK_URL")  # None = disabled
WEBHOOK_SECRET: str = os.getenv("PAYROLL_WEBHOOK_SECRET", "")
MAX_RETRIES: int = int(os.getenv("WEBHOOK_MAX_RETRIES", "5"))
BASE_BACKOFF_SECONDS: float = float(os.getenv("WEBHOOK_BACKOFF_BASE", "2.0"))
DRAIN_INTERVAL_SECONDS: float = float(os.getenv("WEBHOOK_DRAIN_INTERVAL", "10.0"))
REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("WEBHOOK_TIMEOUT", "10.0"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _idempotency_key(receipt_id: str, action: str) -> str:
    """Deterministic key so the same event is never enqueued twice."""
    raw = f"{receipt_id}:{action}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _sign_payload(payload_bytes: bytes) -> str:
    """HMAC-SHA256 signature for the webhook payload."""
    import hmac as _hmac
    return _hmac.new(
        WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# Transactional outbox writer  (call inside safe_transaction)
# ---------------------------------------------------------------------------

def enqueue_webhook(
    db: Session,
    receipt_id: str,
    organization_id: str,
    action: str,
    payload: Dict[str, Any],
) -> None:
    """
    Insert an event into the webhook_outbox table.

    MUST be called inside an existing safe_transaction block so the event
    is committed atomically with the state change it describes.
    If PAYROLL_WEBHOOK_URL is not configured the call is a silent no-op.
    """
    if not WEBHOOK_URL:
        return

    if "issued_at" not in payload:
        payload["issued_at"] = datetime.now(timezone.utc).isoformat()

    idem_key = _idempotency_key(receipt_id, action)
    db.execute(text("""
        INSERT INTO webhook_outbox (
            idempotency_key, receipt_id, organization_id,
            action, payload, status, retries, created_at
        )
        VALUES (
            :idem, :rid, :oid,
            :action, CAST(:payload AS jsonb), 'pending', 0, :now
        )
        ON CONFLICT (idempotency_key) DO NOTHING
    """), {
        "idem": idem_key,
        "rid": receipt_id,
        "oid": organization_id,
        "action": action,
        "payload": json.dumps(payload, default=str),
        "now": datetime.now(timezone.utc),
    })


# ---------------------------------------------------------------------------
# Background outbox drain
# ---------------------------------------------------------------------------

async def _deliver(client: httpx.AsyncClient, row: dict) -> bool:
    """Attempt delivery of a single outbox entry. Returns True on success."""
    payload_bytes = json.dumps(row["payload"], default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Idempotency-Key": row["idempotency_key"],
        "X-Webhook-Signature": _sign_payload(payload_bytes),
    }
    try:
        resp = await client.post(
            WEBHOOK_URL,
            content=payload_bytes,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if 200 <= resp.status_code < 300:
            return True
        logger.warning(
            "webhook.delivery_failed",
            extra={"status": resp.status_code, "id": row["id"]},
        )
        return False
    except httpx.RequestError as exc:
        logger.warning(
            "webhook.delivery_error",
            extra={"error": str(exc), "id": row["id"]},
        )
        return False


async def drain_outbox_once(db_session_factory) -> int:
    """
    Process pending webhook entries. Returns count of successfully delivered.
    Fetches one by one with SKIP LOCKED to prevent transaction contention across workers.
    """
    if not WEBHOOK_URL:
        return 0

    db: Session = db_session_factory()
    delivered = 0
    try:
        async with httpx.AsyncClient() as client:
            # Procesar hasta 50 por ciclo pero 1 a 1 para locks eficientes
            for _ in range(50):
                now_sched = datetime.now(timezone.utc)
                row_raw = db.execute(text("""
                    SELECT id, idempotency_key, receipt_id, organization_id,
                           action, payload, retries
                    FROM webhook_outbox
                    WHERE status = 'pending'
                      AND retries < :max
                      AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """), {
                    "max": MAX_RETRIES,
                    "now": now_sched
                }).mappings().fetchone()

                if not row_raw:
                    break

                row = dict(row_raw)
                
                # GAP-004 Fix: Release DB lock before slow HTTP call to prevent connection pool exhaustion.
                # We set a temporary lease so other workers ignore it if this process crashes.
                # Uses exponential backoff based on retries, minimum 60s to allow HTTP completion.
                lease_seconds = max(60, BASE_BACKOFF_SECONDS * (2 ** row["retries"]))
                temp_lease = now_sched + timedelta(seconds=lease_seconds)
                db.execute(text("UPDATE webhook_outbox SET next_attempt_at = :lease WHERE id = :id"), 
                           {"lease": temp_lease, "id": row["id"]})
                db.commit()

                logger.debug(f"webhook.processing: id={row['id']} action={row['action']} attempt={row['retries']+1}/{MAX_RETRIES}")
                success = await _deliver(client, row)
                now = datetime.now(timezone.utc)

                if success:
                    logger.info(f"webhook.delivered: id={row['id']} action={row['action']}")
                    db.execute(text("""
                        UPDATE webhook_outbox
                        SET status = 'delivered', delivered_at = :now
                        WHERE id = :id
                    """), {"now": now, "id": row["id"]})
                    delivered += 1
                else:
                    new_retries = row["retries"] + 1
                    is_dead = new_retries >= MAX_RETRIES
                    new_status = "dead_letter" if is_dead else "pending"
                    
                    if is_dead:
                        logger.error(f"webhook.dead_letter: id={row['id']} action={row['action']} max_retries_reached={MAX_RETRIES}")
                    else:
                        logger.warning(f"webhook.retry_scheduled: id={row['id']} action={row['action']} next_attempt_in_secs={BASE_BACKOFF_SECONDS * (2 ** row['retries'])}")

                    next_attempt = now + timedelta(
                        seconds=BASE_BACKOFF_SECONDS * (2 ** row["retries"])
                    )
                    db.execute(text("""
                        UPDATE webhook_outbox
                        SET retries = :r, status = :s,
                            next_attempt_at = :nxt, last_error_at = :now
                        WHERE id = :id
                    """), {
                        "r": new_retries,
                        "s": new_status,
                        "nxt": next_attempt,
                        "now": now,
                        "id": row["id"],
                    })
                db.commit() # Commit the single lock update safely
    except Exception:
        logger.exception("webhook.drain_error")
        db.rollback()
    finally:
        db.close()

    return delivered


async def start_outbox_drain_loop(db_session_factory):
    """Long-running coroutine for the FastAPI lifespan. Exits on cancellation."""
    if not WEBHOOK_URL:
        logger.info("webhook.disabled (PAYROLL_WEBHOOK_URL not set)")
        return

    logger.info("webhook.drain_loop_started")
    while True:
        try:
            await drain_outbox_once(db_session_factory)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("webhook.drain_loop_error")
        await asyncio.sleep(DRAIN_INTERVAL_SECONDS)
