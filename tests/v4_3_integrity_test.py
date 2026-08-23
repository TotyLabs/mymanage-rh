import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from services.document_service import DocumentService, DocumentIntegrityError
from payroll_core import (
    get_db, 
    DATABASE_URL,
    safe_transaction
)

def run_test():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # 1. Setup Mock Data
    org_id = "test_org_v43"
    user_info = {"id": "tester_1", "email": "tester@example.com", "role": "admin"}
    content = b"Contenido altamente secreto e integro"
    filename = "auditoria.pdf"
    
    print("--- [INICIO TEST V4.3 INTEGRIDAD] ---")
    
    try:
        # 2. Save Document
        print("1. Guardando documento con hash...")
        result = DocumentService.save_document(
            db=db,
            organization_id=org_id,
            doc_type="ART",
            file_bytes=content,
            original_filename=filename,
            uploaded_by=user_info
        )
        doc_id = result["id"]
        print(f"   [OK] ID: {doc_id} | Hash: {result['hash']}")
        
        # 3. Verify Download (Succeeds)
        print("2. Verificando descarga (debe pasar)...")
        path, name = DocumentService.get_document_file(db, doc_id, org_id)
        if path and os.path.exists(path):
            print(f"   [OK] Archivo recuperado e integro: {name}")
        
        # 4. SIMULATE CORRUPTION
        print("3. SIMULANDO CORRUPCION (modificando archivo en disco)...")
        with open(path, "wb") as f:
            f.write(b"Contenido CORRUPTO por agente externo")
        print("   [!] Archivo alterado físicamente.")
        
        # 5. Verify Download (Fails)
        print("4. Verificando descarga corrupta (DEBE FALLAR)...")
        try:
            DocumentService.get_document_file(db, doc_id, org_id)
            print("   [FALLO] El sistema NO detectó la corrupción.")
        except DocumentIntegrityError as e:
            print(f"   [EXITO] Alerta de integridad capturada: {str(e)}")
            
        # 6. Lifecycle: ARCHIVE
        print("5. Testeando Ciclo de Vida: ARCHIVE")
        DocumentService.update_status(db, doc_id, org_id, "ARCHIVED")
        row = db.execute(text("SELECT status FROM company_documents WHERE id = :id"), {"id": doc_id}).fetchone()
        print(f"   [OK] Estado en DB: {row[0]}")
        
    finally:
        # Cleanup (Soft delete and database removal for clean env)
        print("Limpiando datos de test...")
        db.execute(text("DELETE FROM company_documents WHERE organization_id = :org"), {"org": org_id})
        db.commit()
        db.close()
        print("--- [FIN TEST V4.3] ---")

if __name__ == "__main__":
    run_test()
