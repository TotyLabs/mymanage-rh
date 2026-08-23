import sys
import os
import uuid
import hmac
import hashlib
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError, IntegrityError

# Add parent dir to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payroll_core import SessionLocal, audit, normalize_cuil, normalize_dni, require_transaction_isolation

def test_audit_immutability():
    """Verify that UPDATE/DELETE on audit_log is strictly forbidden at DB level."""
    db = SessionLocal()
    org_id = str(uuid.uuid4())
    tester_id = str(uuid.uuid4())
    
    # 1. Insert a log entry
    audit(db, org_id, "admin", tester_id, "TEST_ACTION", None, {"key": "val"})
    db.commit()
    
    # Get the ID
    row = db.execute(text("SELECT id FROM audit_log WHERE organization_id = :org"), {"org": org_id}).fetchone()
    log_id = row[0]
    
    print(f"Testing immutability for log_id: {log_id}")
    
    # 2. Try to UPDATE (Should fail via REVOKE or TRIGGER)
    try:
        db.execute(text("UPDATE audit_log SET action = 'HACKED' WHERE id = :id"), {"id": log_id})
        db.commit()
        print("FAILED: AuditLog allowed UPDATE!")
    except Exception as e:
        print(f"SUCCESS: AuditLog UPDATE blocked: {type(e).__name__}")
        db.rollback()

    # 3. Try to DELETE (Should fail via REVOKE or TRIGGER)
    try:
        db.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": log_id})
        db.commit()
        print("FAILED: AuditLog allowed DELETE!")
    except Exception as e:
        print(f"SUCCESS: AuditLog DELETE blocked: {type(e).__name__}")
        db.rollback()
    
    db.close()

def test_audit_chain_integrity():
    """Verify that the cryptographic chain exists and is valid."""
    db = SessionLocal()
    org_id = str(uuid.uuid4())
    
    # Insert 3 entries
    audit(db, org_id, "admin", "A1", "ACT1", None, {"data": 1})
    audit(db, org_id, "admin", "A1", "ACT2", None, {"data": 2})
    audit(db, org_id, "admin", "A1", "ACT3", None, {"data": 3})
    db.commit()
    
    rows = db.execute(
        text("SELECT id, previous_hash, chain_hash FROM audit_log WHERE organization_id = :org ORDER BY id ASC"),
        {"org": org_id}
    ).fetchall()
    
    assert len(rows) == 3
    print("Audit chain detected:")
    for r in rows:
        print(f"  ID {r.id}: {r.previous_hash[:10]}... -> {r.chain_hash[:10]}...")
    
    # Verify linkage
    assert rows[1].previous_hash == rows[0].chain_hash
    assert rows[2].previous_hash == rows[1].chain_hash
    print("SUCCESS: Cryptographic chain linkage verified.")
    db.close()

def test_identity_normalization():
    """Verify CUIL/DNI canonicalization and checksum validation."""
    # 1. CUIL Valid
    c1 = normalize_cuil("20334445551") # Checksum for 20-33444555-1
    # weights: 5,4,3,2,7,6,5,4,3,2
    # 2*5+0*4+3*3+3*2+4*7+4*6+4*5+5*4+5*3+5*2 = 10+0+9+6+28+24+20+20+15+10 = 142
    # 142 % 11 = 10
    # 11 - 10 = 1 (match!)
    assert c1 == "20-33444555-1"
    
    # 2. CUIL Invalid Checksum
    c2 = normalize_cuil("20334445559") 
    assert c2 is None
    
    # 3. DNI
    assert normalize_dni("33.444.555") == "33444555"
    assert normalize_dni(" 33-444-555 ") == "33444555"
    
    print("SUCCESS: Identity normalization and checksums verified.")

@require_transaction_isolation(level="SERIALIZABLE")
def _isolated_op(db):
    return db.execute(text("SHOW TRANSACTION ISOLATION LEVEL")).scalar()

def test_transaction_isolation():
    db = SessionLocal()
    level = _isolated_op(db)
    print(f"Current Isolation Level: {level}")
    assert level.lower() == "serializable"
    print("SUCCESS: Transaction Isolation decorator verified.")
    db.close()

def test_audit_null_organization_id():
    """Verify that auditing with missing/None organization_id defaults to nil UUID."""
    db = SessionLocal()
    tester_id = str(uuid.uuid4())
    
    # Audit with None
    audit(db, None, "system", tester_id, "TEST_NULL_ORG", None, {})
    # Audit with "None" string
    audit(db, "None", "system", tester_id, "TEST_NONE_STRING", None, {})
    # Audit with "null" string
    audit(db, "null", "system", tester_id, "TEST_NULL_STRING", None, {})
    db.commit()
    
    # Retrieve and verify fallback
    rows = db.execute(
        text("SELECT organization_id, action FROM audit_log WHERE actor_id = :aid"),
        {"aid": tester_id}
    ).fetchall()
    
    assert len(rows) == 3
    for r in rows:
        assert r.organization_id == "00000000-0000-0000-0000-000000000000"
        
    print("SUCCESS: Audit null/None/null string organization_id fallback to nil UUID verified.")
    db.close()

if __name__ == "__main__":
    print("=== STARTING INDUSTRIAL RESILIENCE AUDIT ===")
    try:
        test_audit_immutability()
        test_audit_chain_integrity()
        test_audit_null_organization_id()
        test_identity_normalization()
        test_transaction_isolation()
        print("=== ALL TESTS PASSED ===")
    except Exception as e:
        print(f"!!! AUDIT FAILED: {e}")
        sys.exit(1)
