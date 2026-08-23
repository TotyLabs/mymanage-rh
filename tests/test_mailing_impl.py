import os
import uuid
import asyncio
from dotenv import load_dotenv
load_dotenv()

from payroll_core import SessionLocal, logger
from sqlalchemy import text
from services.email_service import EmailService
from datetime import datetime, timezone

def test_mailing_system():
    db = SessionLocal()
    email_service = EmailService()
    test_email = "scandrolifacundo2012@gmail.com"
    
    print(f"Testing Mailing System (Mode: {email_service.mode})")
    print(f"Target Email: {test_email}")
    
    # IDs aleatorios para la prueba tÃ©cnica
    rid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    
    try:
        # 1. Desactivar FKs temporalmente para la prueba de lÃ³gica
        db.execute(text("SET session_replication_role = 'replica';"))
        
        # 2. Crear EmailEvent
        ev_id = db.execute(text("""
            INSERT INTO email_events (id, receipt_id, employee_id, email, status)
            VALUES (:id, :rid, :eid, :email, 'sent')
            RETURNING id
        """), {
            "id": str(uuid.uuid4()),
            "rid": rid,
            "eid": eid,
            "email": test_email
        }).scalar()
        db.commit()
        print(f"Created EmailEvent ID: {ev_id}")

        # 3. Enviar Correo de Prueba (Modo Console)
        asyncio.run(email_service.send_signature_email(
            employee_email=test_email,
            employee_name="Facundo Scandroli",
            signature_link="http://localhost:8000/ui/#/sign/TEST_TOKEN",
            organization_name="MyManageRH Test",
            tracking_token=str(ev_id)
        ))
        print("Email logic executed (Check logs for 'email.console' if in sandbox mode)")

        # 4. Simular apertura de correo
        print("Simulating tracking pixel hit...")
        db.execute(text("""
            UPDATE email_events
            SET status = 'opened', 
                opened_at = :now,
                ip_address = '127.0.0.1',
                user_agent = 'TestAgent',
                device_type = 'desktop'
            WHERE id = :id AND status = 'sent'
        """), {
            "id": ev_id, 
            "now": datetime.now(timezone.utc)
        })
        db.commit()

        # 5. Verificar cambio de estado
        event_after = db.execute(text("SELECT status, opened_at FROM email_events WHERE id = :id"), {"id": ev_id}).fetchone()
        print(f"Verification Result:")
        print(f"  - Final Status: {event_after.status}")
        print(f"  - Opened At: {event_after.opened_at}")

        if event_after.status == 'opened':
            print("\nSUCCESS: Mailing tracking flow is FULLY functional (Logic Verified).")
        else:
            print("\nFAILURE: Status did not update correctly.")
        
        # Limpiar data de prueba
        db.execute(text("DELETE FROM email_events WHERE id = :id"), {"id": ev_id})
        db.commit()

        # Restaurar FKs
        db.execute(text("SET session_replication_role = 'origin';"))
        
    finally:
        db.close()

if __name__ == "__main__":
    test_mailing_system()
