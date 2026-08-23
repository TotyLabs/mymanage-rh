import os
from dotenv import load_dotenv
load_dotenv()

from payroll_core import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # Buscar tokens de longitud anormalmente corta
    res = db.execute(text("SELECT id, token, length(token) as len, status, receipt_id FROM signature_requests WHERE length(token) < 32")).fetchall()
    print("Tokens cortos (< 32 char):")
    for r in res:
        print(f"ID: {r.id}, Token: {r.token}, Len: {r.len}, Status: {r.status}, Receipt: {r.receipt_id}")

    # Buscar tokens que no matchean el regex urlsafe
    import re
    TOKEN_REGEX = re.compile(r"^[a-zA-Z0-9\-_]{32,128}$")
    
    res2 = db.execute(text("SELECT id, token, status FROM signature_requests WHERE status = 'pending'")).fetchall()
    print("\nTokens pendientes que no matchean el regex:")
    count = 0
    for r in res2:
        if not TOKEN_REGEX.match(r.token or ""):
            print(f"ID: {r.id}, Token: {r.token}, Status: {r.status}")
            count += 1
    if count == 0:
        print("Ninguno.")

except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
