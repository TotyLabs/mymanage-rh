from fastapi import APIRouter, Request, Depends, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from payroll_core import get_db, logger, safe_transaction
from payroll_utils import get_real_ip
from datetime import datetime, timezone
import base64

router = APIRouter(tags=["tracking"])

import uuid

@router.get("/api/mail/open/{token}")
async def track_mail_open(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Registra la apertura de un correo electrÃƒÂ³nico.
    El token es el ID del EmailEvent (UUID).
    """
    # GAP-010: Validate UUID format to prevent DB crash
    try:
        uuid.UUID(token)
    except ValueError:
        return Response(status_code=400)

    ua_string = request.headers.get("User-Agent", "unknown")
    
    # Simple heuristic for device type inference
    device_type = "desktop"
    ua_lower = ua_string.lower()
    if any(m in ua_lower for m in ["ipad", "tablet", "playbook", "silk"]):
        device_type = "tablet"
    elif any(m in ua_lower for m in ["mobile", "android", "iphone", "ipod", "blackberry", "windows phone"]):
        device_type = "mobile"

    try:
        # I-007 FIX: Use safe_transaction instead of manual commit/rollback
        with safe_transaction(db):
            # Actualizamos el evento si estÃƒÂ¡ en estado 'sent'
            db.execute(text("""
                UPDATE email_events
                SET status = 'opened',
                    opened_at = :now,
                    ip_address = :ip,
                    user_agent = :ua,
                    device_type = :device
                WHERE id = :token AND status = 'sent'
            """), {
                "token": token,
                "now": datetime.now(timezone.utc),
                "ip": get_real_ip(request),
                "ua": ua_string[:500],
                "device": device_type
            })
    except Exception as e:
        logger.error(f"tracking.failed token={token} error={str(e)}")

    # Retornar pÃƒÂ­xel transparente 1x1 GIF
    # R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7 -> 1x1 transparent gif
    pixel = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    return Response(
        content=pixel, 
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
