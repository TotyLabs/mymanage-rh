import os
import time
import logging
import argparse
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import text
from typing import Set
from dotenv import load_dotenv

# Load env variables before importing config
load_dotenv()

# Módulos del sistema
from payroll_core import SessionLocal, compute_file_sha256
from config import STORAGE_PATH
from file_processing.pdf import process_pdf  # para reoptimización (solo no firmados)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("maintenance")

# Parámetros Globales
STORAGE_ROOT = Path(STORAGE_PATH)
TEMP_DIR = Path("/tmp") if os.name != 'nt' else Path(os.environ.get("TEMP", "C:/Temp"))
MAX_TEMP_AGE_SECONDS = 24 * 60 * 60  # 24 horas
MAX_UNSIGNED_PDF_MB = 3  # PDFs > 3MB no firmados

# DRY RUN global status
DRY_RUN = True

def sha256_file(filepath: str) -> str:
    """Calcula hash SHA256 de un archivo"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_file_size_mb(filepath: str) -> float:
    try:
        return os.path.getsize(filepath) / (1024 * 1024)
    except OSError:
        return 0.0

def _get_all_storage_files(root_dir: Path) -> Set[str]:
    files = set()
    for root, _, filenames in os.walk(root_dir):
        for name in filenames:
            file_path = os.path.join(root, name)
            files.add(os.path.normpath(file_path))
    return files

def cleanup_temp_files():
    """1. Limpieza de archivos temporales antiguos."""
    logger.info("=== Limpiando archivos temporales ===")
    now = time.time()
    count = 0
    # Buscar en TEMP_DIR
    if TEMP_DIR.exists():
        for fpath in TEMP_DIR.glob("**/*"):
            if fpath.is_file():
                age = now - fpath.stat().st_mtime
                if age > MAX_TEMP_AGE_SECONDS:
                    logger.info(f"TEMP_CLEAN: {fpath} (Antigüedad: {age/3600:.1f}h)")
                    if not DRY_RUN:
                        try:
                            fpath.unlink()
                            count += 1
                        except Exception as e:
                            logger.error(f"Error borrando temp {fpath}: {e}")
    else:
        logger.warning(f"Directorio temporal no encontrado: {TEMP_DIR}")
    
    logger.info(f"Limpieza temporal completada. Archivos iterados/borrados: {count}")

def cleanup_temp_zips():
    """2. Limpieza de archivos ZIP antiguos (exports)."""
    logger.info("=== Limpiando ZIPs temporales ===")
    now = time.time()
    count = 0
    # Export zips were created via NamedTemporaryFile, so they should be in TEMP_DIR
    if TEMP_DIR.exists():
        for fpath in TEMP_DIR.glob("*.zip"):
            if fpath.is_file():
                age = now - fpath.stat().st_mtime
                if age > MAX_TEMP_AGE_SECONDS:
                    logger.info(f"ZIP_CLEAN: {fpath} (Antigüedad: {age/3600:.1f}h)")
                    if not DRY_RUN:
                        try:
                            fpath.unlink()
                            count += 1
                        except Exception as e:
                            logger.error(f"Error borrando zip {fpath}: {e}")
    logger.info(f"Limpieza de ZIPs completada: {count} archivos afectados.")

def validate_db_consistency(db):
    """3. Validar Consistencia DB <-> Storage."""
    logger.info("=== Validando consistencia de Base de Datos ===")
    
    # Check payroll_receipts
    receipts = db.execute(text("SELECT id, receipt_pdf_path FROM payroll_receipts WHERE receipt_pdf_path IS NOT NULL")).fetchall()
    missing_count = 0
    for r in receipts:
        if not os.path.exists(r.receipt_pdf_path):
            logger.error(f"DB_INCONSISTENCY: Archivo de recibo no encontrado para ID {r.id}: {r.receipt_pdf_path}")
            missing_count += 1
            
    # Check users signatures
    signatures = db.execute(text("SELECT user_id, signature_path FROM user_signatures WHERE is_active = true")).fetchall()
    for s in signatures:
        if not os.path.exists(s.signature_path):
            logger.error(f"DB_INCONSISTENCY: Firma de usuario no encontrada para User ID {s.user_id}: {s.signature_path}")
            missing_count += 1
            
    logger.info(f"Validación de consistencia finalizada. Inconsistencias: {missing_count}")

def cleanup_orphan_files(db):
    """4. Detectar archivos huérfanos en Storage que no figuran en DB."""
    logger.info("=== Detectando Archivos Huérfanos ===")
    
    storage_files = _get_all_storage_files(STORAGE_ROOT)
    logger.info(f"Archivos encontrados en storage: {len(storage_files)}")
    
    db_files = set()
    
    # Tablas con paths de archivos (hay que normalizar los paths para comparar de forma segura)
    queries = [
        "SELECT receipt_pdf_path FROM payroll_receipts WHERE receipt_pdf_path IS NOT NULL",
        "SELECT source_pdf_path FROM payroll_batches WHERE source_pdf_path IS NOT NULL",
        "SELECT signature_path FROM user_signatures WHERE signature_path IS NOT NULL",
        "SELECT signature_image_path FROM company_signers WHERE signature_image_path IS NOT NULL",
        "SELECT logo_path FROM organizations WHERE logo_path IS NOT NULL",
        "SELECT dni_image_path FROM employees WHERE dni_image_path IS NOT NULL"
    ]
    
    for q in queries:
        rows = db.execute(text(q)).fetchall()
        for r in rows:
            path_val = r[0]
            if path_val:
                db_files.add(os.path.normpath(path_val))
                
    orphans = storage_files - db_files
    
    # Filtrar directorios que puedan ser listados u otras estructuras necesarias (.gitignore, etc)
    orphans = {f for f in orphans if not f.endswith(".gitignore") and os.path.isfile(f)}
    
    for orphan in orphans:
        logger.warning(f"ORPHAN_FILE: Detectado archivo sin registro en BD - {orphan}")
        if not DRY_RUN:
            # OPTIONAL: No eliminamos huérfanos automáticamente por seguridad
            # logger.info(f"Eliminando huérfano: {orphan}")
            # os.remove(orphan)
            pass
            
    logger.info(f"Deteción completada. Total de huérfanos: {len(orphans)}")

def verify_signed_integrity(db):
    """5. Verificación de Integridad usando Hashes (Compliance ONTI)."""
    logger.info("=== Verificando Integridad Legal de Recibos Firmados ===")
    
    # Buscar registros que el sistema marca como firmados (status) o que tienen hashes definitivos
    signed_receipts = db.execute(text("""
        SELECT id, receipt_pdf_path, receipt_pdf_sha256 
        FROM payroll_receipts 
        WHERE status = 'signed'
    """)).fetchall()
    
    mismatch_count = 0
    for r in signed_receipts:
        try:
            current_hash = sha256_file(r.receipt_pdf_path)
            if current_hash != r.receipt_pdf_sha256:
                logger.critical(f"INTEGRITY_VIOLATION: Hash mismatch en recibo {r.id}.")
                logger.critical(f" > RUTA: {r.receipt_pdf_path}")
                logger.critical(f" > ESPERADO: {r.receipt_pdf_sha256}")
                logger.critical(f" > ACTUAL:   {current_hash}")
                mismatch_count += 1
        except Exception as e:
            logger.error(f"INTEGRITY_READ_ERROR: Recibo {r.id} no pudo ser verificado. Error: {e}")
            mismatch_count += 1
            
    if mismatch_count == 0:
        logger.info(f"Integridad Válida para {len(signed_receipts)} documentos vinculantes.")
    else:
        logger.critical(f"CRITICAL: {mismatch_count} documentos fallaron la validación de integridad!")

def reoptimize_unsigned_pdfs(db):
    """6. Re-optimización Segura (SÓLO en no-firmados mayores al umbral)."""
    logger.info("=== Re-optimizando PDFs Pesados No Firmados ===")
    
    unsigned_candidates = db.execute(text("""
        SELECT id, receipt_pdf_path, receipt_pdf_sha256
        FROM payroll_receipts 
        WHERE status != 'signed' 
        AND receipt_pdf_path IS NOT NULL
    """)).fetchall()
    
    optimized_count = 0
    for r in unsigned_candidates:
        if not os.path.exists(r.receipt_pdf_path):
            continue
            
        mb = get_file_size_mb(r.receipt_pdf_path)
        if mb > MAX_UNSIGNED_PDF_MB:
            logger.info(f"OPTIMIZAR_CANDIDATO: Recibo {r.id} pesa {mb:.2f}MB (> {MAX_UNSIGNED_PDF_MB}MB limit)")
            if not DRY_RUN:
                try:
                    old_path = r.receipt_pdf_path
                    new_path = process_pdf(old_path)
                    
                    if new_path != old_path:
                        # process_pdf generó un archivo nuevo
                        new_sha = sha256_file(new_path)
                        # Actualizar base de datos atómicamente
                        db.execute(text("""
                            UPDATE payroll_receipts 
                            SET receipt_pdf_path = :path, receipt_pdf_sha256 = :sha 
                            WHERE id = :id
                        """), {"path": new_path, "sha": new_sha, "id": r.id})
                        db.commit()
                        logger.info(f"OPTIMIZADO EXITOSAMENTE: {r.id}")
                        optimized_count += 1
                except Exception as e:
                    logger.error(f"Error al optimizar recibo {r.id}: {e}")
                    db.rollback()
    
    logger.info(f"Re-optimización completada. Total procesados: {optimized_count}")

def collect_metrics():
    """7. Métricas de Ocupación para monitoreo de Crecimiento."""
    logger.info("=== Recopilando Métricas de Storage ===")
    
    total_size = 0
    count = 0
    storage_dirs = {}
    
    for root, dirs, files in os.walk(STORAGE_ROOT):
        # Medir tamaño por subdirectorio principal del root
        rel_root = os.path.relpath(root, STORAGE_ROOT)
        top_level = rel_root.split(os.sep)[0] if rel_root != "." else "root"
        
        dir_size = sum(os.path.getsize(os.path.join(root, name)) for name in files)
        total_size += dir_size
        count += len(files)
        
        if top_level not in storage_dirs:
            storage_dirs[top_level] = 0
        storage_dirs[top_level] += dir_size
        
    logger.info(f"Total Files Storage: {count}")
    logger.info(f"Total Size: {total_size / (1024*1024):.2f} MB")
    
    logger.info("Distribución:")
    for d, s in storage_dirs.items():
        logger.info(f" - {d}/: {s / (1024*1024):.2f} MB")

def run():
    logger.info("=======================================")
    logger.info("       START MAINTENANCE RUN           ")
    logger.info(f"       DRY_RUN = {DRY_RUN}             ")
    logger.info("=======================================")
    
    with SessionLocal() as db:
        # 1. Temporales
        cleanup_temp_files()
        cleanup_temp_zips()
        
        # 2. Base de datos & Archivos
        validate_db_consistency(db)
        cleanup_orphan_files(db)
        
        # 3. Integridad Legal
        verify_signed_integrity(db)
        
        # 4. Optimización
        reoptimize_unsigned_pdfs(db)
        
        # 5. Métricas
        collect_metrics()

    logger.info("=======================================")
    logger.info("        END MAINTENANCE RUN            ")
    logger.info("=======================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mantenimiento y Auditoría de Integrity ONTI")
    parser.add_argument("--execute", action="store_true", help="Desactiva el DRY_RUN y aplica eliminaciones/modificaciones reales.")
    args = parser.parse_args()
    
    if args.execute:
        DRY_RUN = False
        logger.warning("! DRY_RUN ESTÁ DESACTIVADO. MODO PERMANENTE !")
        time.sleep(3) # Wait 3 secs as safeguard
        
    run()
