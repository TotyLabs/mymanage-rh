"""
modules/signature.py

Módulo centralizado para la lógica de firma electrónica y automática de recibos.
Responsabilidades:
- Cargar y validar firmas (PNG)
- Detectar posición de firma (híbrido: búsqueda de texto + fallback coordinado)
- Estampar firmas en PDF (empresa y empleado)
- Generar placeholder de firma si no existe
- Calcular y validar integridad de PDF (SHA256)
- Persistencia de firmas en storage estructurado

Sin dependencias de FastAPI/HTTP/DB; las interacciones vienen desde modules/digital_signature.py
"""

import os
import hashlib
import base64
import logging
from typing import Optional, Dict, Tuple, List
from pathlib import Path
from datetime import datetime
import re
import unicodedata
from io import BytesIO
import uuid
import qrcode
import time
import json

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from PIL import Image, ImageDraw, ImageFont

# Cryptography for industrial-grade signing (Phase 15)
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization


logger = logging.getLogger("dircom.payroll.signature")


# =============================================================================
# EXCEPTIONS
# =============================================================================

class SignatureError(Exception):
    """Base exception for signature operations."""
    pass


class SignatureAlreadyExistsError(SignatureError):
    """Raised when trying to sign a receipt that's already been signed."""
    pass


class SignatureNotFoundError(SignatureError):
    """Raised when signature file cannot be found."""
    pass


class SignatureIntegrityError(SignatureError):
    """Raised when signature or PDF integrity check fails."""
    pass


# =============================================================================
# CONFIGURATION (Injected from config.py)
# =============================================================================

DEFAULT_SIGNATURE_POSITIONS = {
    "employer": {"x": 420, "y": 120},
    "employee": {"x": 100, "y": 120},
}

import config
DEFAULT_SIGNATURE_STORAGE_PATH = config.SIGNATURE_STORAGE_PATH


# =============================================================================
# SignatureService: Core business logic
# =============================================================================

# =============================================================================
# SignatureEngine: Core business logic (Physical PDF/Image manipulation)
# =============================================================================

class SignatureEngine:
    """
    Engine central de manipulación de archivos para firmas.
    Esta clase es agnóstica a la base de datos y HTTP.
    
    HARDENING IMPLEMENTADO:
    - Límite de páginas (config.MAX_PDF_PAGES)
    - Timeouts de procesamiento (config.PDF_PROCESSING_TIMEOUT)
    - Validaciones de tamaño de imagen
    """
    
    def __init__(self, storage_path: str = None, 
                 signature_positions: Dict = None, signature_mode: str = None):
        """
        Args:
            storage_path: Ruta base para almacenar firmas (fallback a config)
            signature_positions: Dict con coordenadas por rol (fallback a config)
            signature_mode: "hybrid" o "coordinates_only" (fallback a config)
        """
        import config
        self.signature_version = config.SIGNATURE_VERSION
        self.allow_v1_fallback = config.ALLOW_V1_FALLBACK
        self.production = os.getenv("ENV", "development").lower() == "production"

        # V4.1 BLINDAJE: Production Guard for Signature Version
        if self.production and self.signature_version != "v2":
            if not self.allow_v1_fallback:
                logger.critical(f"SECURITY ALERT: Invalid signature version '{self.signature_version}' in production without fallback enabled!")
                raise Exception(f"Signature version {self.signature_version} is forbidden in production.")
            else:
                logger.warning(f"EMERGENCY: Using legacy signature version '{self.signature_version}' in production (fallback mode active)")
        elif self.signature_version != "v2":
            logger.warning(f"Signature engine: using legacy version '{self.signature_version}' (v2 recommended)")
        else:
            logger.info("Signature engine: v2 active (seal only mode)")

        self.storage_path = Path(storage_path or config.SIGNATURE_STORAGE_PATH)
        self.signature_positions = signature_positions or config.SIGNATURE_POSITIONS
        self.signature_mode = signature_mode or config.SIGNATURE_MODE
        self.max_pages = config.MAX_PDF_PAGES
        self.timeout = config.PDF_PROCESSING_TIMEOUT
        self._ensure_storage_dirs()
    
    def _ensure_storage_dirs(self):
        """Asegura que existan los directorios de almacenamiento."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        (self.storage_path / "employer").mkdir(parents=True, exist_ok=True)
        (self.storage_path / "employee").mkdir(parents=True, exist_ok=True)
    
    def search_text_robust(self, page, term: str) -> list:
        """
        Locates text coordinates on a page case-insensitively and ignoring diacritics.
        Uses unicodedata NFKD normalization.
        """
        import unicodedata
        import re
        import fitz
        def clean_word(w):
            w_norm = "".join(c for c in unicodedata.normalize('NFKD', w) if not unicodedata.combining(c))
            return re.sub(r'[^a-z0-9]', '', w_norm.lower())
        
        norm_parts = [clean_word(p) for p in term.split() if clean_word(p)]
        if not norm_parts:
            return []
        
        words = page.get_text("words")
        # Sort words by y0 first, then x0
        words.sort(key=lambda w: (w[1], w[0]))
        
        n_parts = len(norm_parts)
        matches = []
        for i in range(len(words) - n_parts + 1):
            match_found = True
            for j in range(n_parts):
                w_clean = clean_word(words[i+j][4])
                if w_clean != norm_parts[j]:
                    match_found = False
                    break
            if match_found:
                x0 = min(words[i+j][0] for j in range(n_parts))
                y0 = min(words[i+j][1] for j in range(n_parts))
                x1 = max(words[i+j][2] for j in range(n_parts))
                y1 = max(words[i+j][3] for j in range(n_parts))
                matches.append(fitz.Rect(x0, y0, x1, y1))
                
        return matches

    # =========================================================================
    # Core Signature Operations
    # =========================================================================
    
    def load_signature_image(self, path: str) -> bytes:
        """Carga una imagen de firma desde disco."""
        if not os.path.exists(path):
            raise SignatureNotFoundError(f"Signature image not found: {path}")
        
        with open(path, "rb") as f:
            return f.read()
    
    def stamp_signature_on_pdf(self, pdf_path: str, signature_image_path: str, 
                                role: str, signer_name: str = None, 
                                signer_tax_id: str = None,
                                timestamp: datetime = None) -> str:
        """Estampa una firma PNG sobre un PDF, usando imagen desde archivo."""
        sig_bytes = self.load_signature_image(signature_image_path)
        return self.stamp_signature_from_bytes(
            pdf_path=pdf_path, 
            signature_bytes=sig_bytes, 
            role=role, 
            signer_name=signer_name, 
            signer_tax_id=signer_tax_id,
            timestamp=timestamp
        )

    # =========================================================================
    # Industrial-Grade Helpers (Phase 15)
    # =========================================================================

    def calculate_bytes_sha256(self, data: bytes) -> str:
        """Calcula hash SHA256 de un bloque de bytes."""
        return hashlib.sha256(data).hexdigest()

    def sign_document_hash(self, hash_bytes: bytes, private_key_path: str) -> str:
        """
        Firma un hash de documento usando una clave privada RSA.
        Retorna la firma en formato Base64.
        """
        try:
            with open(private_key_path, "rb") as key_file:
                private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                )
            
            signature = private_key.sign(
                hash_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode('utf-8')
        except Exception as e:
            logger.error(f"signature.cryptography.sign_failed: {e}")
            return ""

    def verify_document_hash(self, hash_bytes: bytes, signature_b64: str, public_key_path: str) -> bool:
        """Verifica una firma criptográfica contra un hash."""
        try:
            with open(public_key_path, "rb") as key_file:
                public_key = serialization.load_pem_public_key(key_file.read())
            
            signature = base64.b64decode(signature_b64)
            public_key.verify(
                signature,
                hash_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False

    def _generate_industrial_id(self) -> str:
        """Genera un ID de firma según estándar: FES-YYYYMMDD-XXXX."""
        date_part = datetime.utcnow().strftime("%Y%m%d")
        rand_part = uuid.uuid4().hex[:4].upper()
        return f"FES-{date_part}-{rand_part}"

    def _cleanup_signature_background(self, image_bytes: bytes) -> bytes:
        """
        Limpia el fondo de la firma convirtiendo blancos/grises claros en transparencia.
        Garantiza que la firma se 'funda' con el papel del PDF.
        """
        try:
            img = Image.open(BytesIO(image_bytes)).convert("RGBA")
            datas = img.getdata()

            new_data = []
            for item in datas:
                # Si el pixel es muy blanco (R, G, B > 240), lo hacemos transparente
                if item[0] > 240 and item[1] > 240 and item[2] > 240:
                    new_data.append((255, 255, 255, 0))
                else:
                    new_data.append(item)

            img.putdata(new_data)
            output = BytesIO()
            img.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            logger.warning(f"signature.cleanup_failed: {e}")
            return image_bytes

    def stamp_signature_from_bytes(self, pdf_path: str, signature_bytes: bytes, 
                                    role: str, signer_name: str = None, 
                                    signer_tax_id: str = None,
                                    timestamp: datetime = None,
                                    output_path: str = None,
                                    logo_bytes: bytes = None,
                                    verification_url: str = None,
                                    private_key_path: str = None,
                                    signer_identity: Dict = None,
                                    signature_level: str = "X509",
                                    doc_type: str = None,
                                    source: str = None) -> Dict:
        
        # GAP-L2-01: Fail-fast resource limits (Large file protection)
        import config
        file_size = os.path.getsize(pdf_path)
        if file_size > config.MAX_FILE_SIZE:
            raise SignatureError(f"PDF exceeds maximum size limit ({config.MAX_FILE_SIZE // 1024 // 1024}MB)")

        # 1. Deterministic Flow: Hash del archivo original (Phase 15)
        hash_original = self.calculate_file_sha256(pdf_path)
        
        # 2. Cryptographic Evidence: Firma del hash (Phase 15)
        crypto_signature = ""
        if private_key_path and os.path.exists(private_key_path):
            crypto_signature = self.sign_document_hash(hash_original.encode(), private_key_path)

        # Determine active signature engine version flag
        is_v2 = (getattr(self, 'signature_version', None) == 'v2')

        if signature_bytes is not None:
            if len(signature_bytes) < config.MIN_SIGNATURE_IMAGE_SIZE:
                raise SignatureError("Signature image too small")
            if len(signature_bytes) > config.MAX_SIGNATURE_IMAGE_SIZE:
                raise SignatureError("Signature image too large")

            # 3. Limpieza de fondo (White-to-Alpha)
            signature_bytes = self._cleanup_signature_background(signature_bytes)
        else:
            # Contingency Mode (Phase 26) - Allowed for v2 seals
            if not is_v2:
                raise SignatureError("Signature image required for legacy v1 mode")
            logger.info(f"signature.engine.contingency_mode: generating seal without manuscript for role={role}")

        try:
            from services.x509_service import is_pdf_digitally_signed
            is_signed_crypto = is_pdf_digitally_signed(pdf_path)
        except Exception:
            is_signed_crypto = False

        start_time = time.time()
        doc = None
        temp_pdf = None
        output_path = output_path or pdf_path.replace(".pdf", f"_{role}_signed.pdf")
        
        try:
            if is_signed_crypto:
                import tempfile
                import shutil
                out_dir = os.path.dirname(output_path)
                fd, temp_pdf = tempfile.mkstemp(dir=out_dir, prefix="tmp_pdf_", suffix=".pdf")
                os.close(fd)
                shutil.copy2(pdf_path, temp_pdf)
                doc = fitz.open(temp_pdf)
            else:
                doc = fitz.open(pdf_path)
                
            if doc.page_count > self.max_pages:
                raise SignatureError(f"PDF too many pages: {doc.page_count} > {self.max_pages}")
            
            # 3.5. SealID Generation (Sha256 binding)
            # Deterministic, unique, and traceable (receipt_id + dni + role + timestamp)
            signer_dni = signer_identity.get("dni") if signer_identity else (signer_tax_id or "N/D")
            id_seed = f"{pdf_path}_{signer_dni}_{role}_{timestamp.isoformat()}"
            sig_id = hashlib.sha256(id_seed.encode()).hexdigest()[:16].upper()
            signatures_applied = 0
            
            # 4. Inyección de Metadatos Extendidos (Audit Trail - Phase 15)
            # We use keywords as a structured store for seal IDs and positions
            meta = doc.metadata
            existing_keywords = meta.get("keywords", "")
            
            # Clean up metadata and prepare for new seal
            meta["author"] = "MyManageRH Engine"
            meta["subject"] = f"Electronically Signed by {signer_name or 'Auto-Signer'}"
            meta["creator"] = "MyManageRH SaaS v1.0"
            meta["producer"] = "MyManageRH Signature Engine (Industrial-Grade)"
            meta["creationDate"] = timestamp.isoformat()
            meta["modDate"] = datetime.utcnow().isoformat()
            
            # Note: keywords will be updated during sealing
            doc.set_metadata(meta)
            
            seal_applied = False
            occupied_rects_by_page = {}

            # Iterate through ALL pages
            for page_num in range(doc.page_count):
                if time.time() - start_time > self.timeout:
                    raise SignatureError("PDF processing timeout")
                
                page = doc.load_page(page_num)
                
                # Pre-verificación de texto (Scanned PDF Check)
                if not page.get_text("text").strip():
                    logger.warning(f"signature.warning: Page {page_num} seems to be a scanned image (no text layer).")

                # Prepare an optional anchor override for the validation seal when
                # we detect the explicit word 'Firma' in UNEMPLOYMENT documents.
                override_anchor_rect = None
                try:
                    if doc_type and str(doc_type).upper() == "UNEMPLOYMENT":
                        firma_rects = self.search_text_robust(page, "Firma")
                        if firma_rects:
                            # Use the first robust match as the anchor for the seal.
                            r = firma_rects[0]
                            override_anchor_rect = fitz.Rect(r.x0, r.y0, r.x1, r.y1)
                            logger.info(f"signature.seal_position: priority anchor 'FIRMA' detected for UNEMPLOYMENT page={page_num} x={int(override_anchor_rect.x0)}")
                            # Intentionally DO NOT insert the manuscript signature image here.
                            # The requirement is to place only the validation seal for UNEMPLOYMENT.
                except Exception as e:
                    logger.warning(f"signature.unemployment_heuristic_failed: {e}")

                # Detect ALL positions using Layout-Aware engine
                positions = self.detect_signature_positions(page, role)
                
                # Removed Disambiguation Fallback (Phase 21: Abolish Anchor Theft)
                # Each role must now rely on its own anchor labels to prevent misplacement.
                
                # Sign all detected positions (e.g. Original and Duplicado)
                # Removed the [0] slice to support multi-copy receipts
                
                if page_num not in occupied_rects_by_page:
                    occupied_rects_by_page[page_num] = []

                # Phase 25: Hard Singularization - Only process the single best match per page
                # This removes the duplicate signature from the other sector.
                # Phase 25/Modernization: Logic based on Signature Version
                if not is_v2:
                    for pos in positions[:1]:
                        anchor_bbox = pos["bbox"]
                        anchor_x0, anchor_y0 = anchor_bbox[0], anchor_bbox[1]
                        anchor_x1, anchor_y1 = anchor_bbox[2], anchor_bbox[3]
                        anchor_w = anchor_x1 - anchor_x0
                        
                        # 1. Limpieza y Recorte Quirúrgico de la Firma
                        cleaned_sig_bytes = self._prepare_signature_image(signature_bytes)
                        
                        # 2. Cálculo de Dimensiones Preciso (Phase 19 Refinement)
                        sig_w = min(config.SIGNATURE_MAX_WIDTH, max(config.SIGNATURE_MIN_WIDTH, anchor_w * config.SIGNATURE_WIDTH_RATIO)) 
                        sig_h = config.SIGNATURE_HEIGHT
                        
                        # 3. Alineación Horizontal (Centro Matemático)
                        center_x = anchor_x0 + (anchor_w / 2)
                        x0 = center_x - (sig_w / 2)
                        x1 = x0 + sig_w
                        
                        # 4. Alineación Vertical (Justo encima del texto sin tocarlo)
                        y1 = anchor_y0 - 6.5
                        y0 = y1 - sig_h
                        
                        sig_rect = fitz.Rect(x0, y0, x1, y1)
                        
                        # Prevención de Colisiones
                        for occ in occupied_rects_by_page.get(page_num, []):
                            if sig_rect.intersects(occ):
                                sig_rect.y0 -= 5
                                sig_rect.y1 -= 5
                        
                        page.insert_image(sig_rect, stream=cleaned_sig_bytes, keep_proportion=True)
                        if page_num not in occupied_rects_by_page: occupied_rects_by_page[page_num] = []
                        occupied_rects_by_page[page_num].append(sig_rect)
                        signatures_applied += 1
                else:
                    # In V2, we count the "seal" as the signature application
                    signatures_applied += 1

                # 6. Sello de Validación Decoupled (Precision Overhaul - Phase 26)
                # Sólo aplicamos el sello una vez por página.
                # Explicit anchor_rect is only used for UNEMPLOYMENT override anchors.
                if not seal_applied:
                    anchor_rect = override_anchor_rect

                    if anchor_rect:
                        self._stamp_validation_seal(
                            page, sig_id, signer_name, signer_tax_id, 
                            timestamp, logo_bytes, verification_url,
                            document_hash=hash_original,
                            signer_identity=signer_identity,
                            signature_level=signature_level, role=role,
                            signature_bytes=signature_bytes,
                            doc=doc,
                            anchor_rect=anchor_rect,
                            occupied_rects=occupied_rects_by_page.get(page_num, [])
                        )
                        seal_applied = True
                    else:
                        # If no explicit override anchor exists, let the seal engine
                        # choose the usual fallback position (Observaciones or header).
                        self._stamp_validation_seal(
                            page, sig_id, signer_name, signer_tax_id, 
                            timestamp, logo_bytes, verification_url,
                            document_hash=hash_original,
                            signer_identity=signer_identity,
                            signature_level=signature_level, role=role,
                            signature_bytes=signature_bytes,
                            doc=doc,
                            occupied_rects=occupied_rects_by_page.get(page_num, [])
                        )
                        seal_applied = True
                

            # Fallback (Si no se encontró el ancla en ninguna página del documento)
            if not seal_applied:
                page = doc.load_page(0)
                current_keywords = doc.metadata.get("keywords", "") or ""
                # Deduplication check before fallback
                if f"seal:{role}:" not in current_keywords:
                    self._stamp_validation_seal(
                        page, sig_id, signer_name, signer_tax_id, 
                        timestamp, logo_bytes, verification_url,
                        document_hash=hash_original,
                        signer_identity=signer_identity,
                        signature_level=signature_level, role=role,
                        signature_bytes=signature_bytes,
                        doc=doc,
                        occupied_rects=occupied_rects_by_page.get(0, [])
                    )
                    seal_applied = True
                else:
                    logger.info(f"signature.seal_skip_fallback: {role} seal already exists")
                    seal_applied = True

            # Save modified PDF atomically
            try:
                if is_signed_crypto:
                    doc.saveIncr()
                else:
                    import tempfile
                    out_dir = os.path.dirname(output_path)
                    fd, temp_pdf2 = tempfile.mkstemp(dir=out_dir, prefix="tmp_pdf_", suffix=".pdf")
                    os.close(fd)
                    temp_pdf = temp_pdf2
                    doc.save(temp_pdf, garbage=4, deflate=True)
                    
                if doc and not getattr(doc, 'is_closed', True):
                    doc.close()
                doc = None # Guard against double close
                
                # Windows robustness: Retry replace a few times if it fails (OneDrive/Antivirus lock)
                MAX_RETRIES = 5
                for i in range(MAX_RETRIES):
                    try:
                        os.replace(temp_pdf, output_path)
                        break
                    except PermissionError:
                        if i == MAX_RETRIES - 1: raise
                        time.sleep(0.1 * (i + 1))
            except Exception as e:
                logger.error(f"signature.engine.error: {str(e)}", exc_info=True)
                if doc and not doc.is_closed:
                    doc.close()
                doc = None
                if os.path.exists(temp_pdf):
                    try:
                        os.remove(temp_pdf)
                    except:
                        pass
                raise            
            # 7. Final Hash (Phase 15)
            hash_signed = self.calculate_file_sha256(output_path)
            
            # 8. Structured Audit Record
            audit_record = {
                "signature_id": sig_id,
                "timestamp": timestamp.isoformat(),
                "signer_name": signer_name,
                "signer_tax_id": signer_tax_id,
                "hash_original_pdf": hash_original,
                "hash_signed_pdf": hash_signed,
                "cryptographic_signature": crypto_signature
            }
            
            logger.info(f"signature.engine.stamped id={sig_id} role={role} applied={signatures_applied}")
            
            return {
                "signed_pdf_path": output_path,
                "signature_id": sig_id,
                "hash_original_pdf": hash_original,
                "hash_signed_pdf": hash_signed,
                "audit_record": audit_record,
                "generated_seal_id": sig_id
            }
        finally:
            if doc and not getattr(doc, 'is_closed', True):
                try:
                    doc.close()
                except:
                    pass
    def _stamp_validation_seal(self, page, sig_id, signer_name, signer_tax_id, 
                               timestamp, logo_bytes, verification_url, 
                               document_hash="", signer_identity=None,
                               signature_level="X509", role="employee",
                               signature_bytes=None, doc=None,
                               anchor_rect=None, occupied_rects=None):
        """
        Dibuja el sello de validación MyManageRH en la página siguiendo estándares industriales.
        Diseño: Badge horizontal [ QR ] FIRMA ELECTRÓNICA VERIFICADA + Info
        """
        # 0. Deduplicación del Sello (Phase 26: Allow multiple seals if they don't overlap)
        # We only skip if there's already a seal near the target anchor
        keywords = (doc.metadata.get("keywords", "") or "") if doc else ""
        
        # If no anchor_rect is provided, we use global deduplication for Header Fallback
        if not anchor_rect and f"seal:{role}:" in keywords:
             logger.info(f"signature.seal_skip_header: {role} header seal already exists.")
             return

        title = "FIRMA ELECTRÓNICA - EMPLEADO" if role == "employee" else "FIRMA ELECTRÓNICA - EMPLEADOR"
        
        import config
        page_rect = page.rect
        margin = 3 
        seal_w = config.SIGNATURE_SEAL_WIDTH
        seal_h = config.SIGNATURE_SEAL_HEIGHT
        
        # 1. Posicionamiento Dinámico (Precisión Quirúrgica - Phase 26)
        found_anchor = False

        # If an explicit anchor_rect was provided (e.g. detected 'Firma' for UNEMPLOYMENT),
        # prefer it over searching for 'Observaciones' so the seal is placed next to that anchor.
        if anchor_rect:
            # Place the seal to the right of the detected anchor when possible
            try:
                is_left_anchor = anchor_rect.x0 < (page_rect.width / 2)
                # Prefer placing next to the anchor (to the right)
                seal_x0 = min(anchor_rect.x1 + 6, page_rect.width - seal_w - margin)
                seal_y0 = anchor_rect.y0 - (seal_h / 2)
                # Bounds
                if seal_y0 < margin:
                    seal_y0 = margin
                if seal_y0 + seal_h > page_rect.height:
                    seal_y0 = page_rect.height - seal_h - margin

                found_anchor = True
                logger.info(f"signature.seal_position: explicit anchor_rect used x0={int(seal_x0)} y0={int(seal_y0)}")
            except Exception:
                found_anchor = False

        # PRIORIDAD: Buscar "Observaciones"
        if not found_anchor:
            obs_rects = self.search_text_robust(page, "Observaciones")
            if obs_rects:
                # Si hay "Observaciones", lo ponemos un poco más abajo de ahí
                anchor = obs_rects[0]
                # Alineación horizontal: derecha para empleador, izquierda para empleado
                seal_x0 = page_rect.width - seal_w - margin if role == "employer" else margin
                seal_y0 = anchor.y1 + 5 # Justo debajo de la línea de observaciones

                # Garantizar que no se salga de la página por abajo
                if seal_y0 + seal_h > page_rect.height: 
                    seal_y0 = page_rect.height - seal_h - margin

                found_anchor = True
                logger.info(f"signature.seal_position: priority anchor 'OBSERVACIONES' found at y={int(seal_y0)}")

        if not found_anchor and anchor_rect:
            # FALLBACK DEFAULT: Usar el anchor detectado para determinar el lado
            is_left = anchor_rect.x0 < (page_rect.width / 2)
            
            if is_left:
                seal_x0 = margin
            else:
                seal_x0 = page_rect.width - seal_w - margin
                
            seal_y0 = margin # Comportamiento original: Esquina superior
            
            # Apilado automático si ya hay sellos
            existing_seals = keywords.count(f"seal:{role}:")
            if existing_seals > 0:
                seal_y0 += (seal_h + margin) * existing_seals
            
            found_anchor = True
            logger.info(f"signature.seal_position: fallback anchor role={role} top-corner")
        
        if not found_anchor:
            # Fallback 2: Header Stack (Top Corners)
            seal_x0 = page_rect.width - seal_w - margin if role == "employer" else margin
            seal_y0 = margin
            
            existing_seals = keywords.count("seal:")
            if existing_seals > 0:
                seal_y0 += (seal_h + margin) * existing_seals
                
            logger.info(f"signature.seal_position: global fallback header-stack role={role}")

        # 2. Prevención de Solapamiento (Phase 26 Anti-Collision)
        seal_rect = fitz.Rect(seal_x0, seal_y0, seal_x0 + seal_w, seal_y0 + seal_h)
        
        # Collision objects: anchors + manuscript signatures
        collision_targets = []
        if anchor_rect: collision_targets.append(anchor_rect)
        if occupied_rects: collision_targets.extend(occupied_rects)
        
        for target in collision_targets:
            if seal_rect.intersects(target):
                # Desplazamiento vertical (arriba o abajo según espacio)
                if seal_rect.y1 + (seal_h + 5) < page_rect.height:
                    seal_rect.y0 = target.y1 + 5
                    seal_rect.y1 = seal_rect.y0 + seal_h
                else:
                    seal_rect.y1 = target.y0 - 5
                    seal_rect.y0 = seal_rect.y1 - seal_h
                
                # Safe boundary
                if seal_rect.y0 < margin: seal_rect.y0 = margin; seal_rect.y1 = margin + seal_h
                
                logger.info(f"signature.seal_collision_avoided role={role} new_y0={int(seal_rect.y0)}")
                break # We only shift once per collision detection pass for now

        # seal_rect is now final (collision adjustments applied above)
        
        # 3. Estética Badge - Identity Colors
        stroke_color = (0.6, 0.6, 0.6) # Gris Empleado
        if role == "employer":
            stroke_color = (0.0, 0.3, 0.7) # Azul Empleador
            
        page.draw_rect(seal_rect, color=stroke_color, fill=(1, 1, 1), width=1.0)
        
        # 3.5. Imagen de la firma embebida en el sello
        if signature_bytes:
            sig_img_w = 55 # Reducido de 70
            sig_img_h = seal_h - 4
            sig_img_x0 = seal_rect.x0 + seal_w - sig_img_w - 2
            sig_img_y0 = seal_rect.y0 + 2
            sig_img_rect = fitz.Rect(sig_img_x0, sig_img_y0, sig_img_x0 + sig_img_w, sig_img_y0 + sig_img_h)
            page.insert_image(sig_img_rect, stream=signature_bytes, keep_proportion=True)
        
        # Layout metrics - QR Maximize
        qr_padding = 3 # Padding mínimo para QR más grande
        qr_size = seal_h - (qr_padding * 2) 
        qr_x0 = seal_rect.x0 + qr_padding
        qr_y0 = seal_rect.y0 + qr_padding

        text_margin_left = qr_x0 + qr_size + 6
        fields_x = text_margin_left
        fields_y = seal_rect.y0 + 7 # Ajustado de 10
        line_spacing = 5.5 # Reducido de 7.5
        
        title_color = (0.3, 0.3, 0.3) if role == "employee" else (0.0, 0.2, 0.5)
        text_color = (0.1, 0.1, 0.1)
        sub_text_color = (0.5, 0.5, 0.5)
        
        # 4. Título Principal (Role-Aware)
        page.insert_text((fields_x, fields_y), title, fontsize=6.5, color=title_color, fontname="hebo")
        
        # 5. Datos de Identidad
        fields_y += 9
        
        # Signer identity binding (Phase 3.5 Reinforcement)
        signer_display = signer_name or 'N/A'
        if signer_identity and signer_identity.get("dni"):
            signer_display = f"{signer_display} (DNI: {signer_identity['dni']})"
        
        page.insert_text((fields_x, fields_y), f"Firmante: {signer_display}", fontsize=5.5, color=text_color)
        fields_y += line_spacing
        
        page.insert_text((fields_x, fields_y), f"Nivel: {signature_level}", fontsize=5.5, color=title_color, fontname="hebo")
        fields_y += line_spacing
        
        page.insert_text((fields_x, fields_y), f"Documento: Recibo de Haberes", fontsize=5.5, color=text_color)
        fields_y += line_spacing
        
        page.insert_text((fields_x, fields_y), f"CUIL: {signer_tax_id or 'N/A'}", fontsize=5.5, color=text_color)
        fields_y += line_spacing
        
        date_str = timestamp.strftime('%d/%m/%Y %H:%M UTC') if timestamp else "N/A"
        page.insert_text((fields_x, fields_y), f"Fecha: {date_str}", fontsize=5.5, color=text_color)
        fields_y += line_spacing
        
        page.insert_text((fields_x, fields_y), f"ID: {sig_id}", fontsize=5.5, color=text_color)
        fields_y += line_spacing
        
        # Truncado extendido (32 chars) para persistencia visual
        extended_hash = (document_hash or "N/A")[:32]
        page.insert_text((fields_x, fields_y), f"Hash: {extended_hash}", fontsize=5.5, color=text_color)
        
        # 6. Disclaimer
        footer_y = seal_rect.y0 + seal_h - 2
        page.insert_text((fields_x - 1, footer_y), "Documento auténtico - Registro oficial MyManageRH.", fontsize=3.5, color=sub_text_color)
        
        # 7. QR Content - URL Larga de Verificación (Plain text)
        qr_url = f"{config.BASE_PUBLIC_URL}/v/{sig_id}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=1
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white")
        qr_io = BytesIO()
        img_qr.save(qr_io, format="PNG")
        
        qr_rect = fitz.Rect(qr_x0, qr_y0, qr_x0 + qr_size, qr_y0 + qr_size)
        page.insert_image(qr_rect, stream=qr_io.getvalue())
        
        # 8. Update Metadata with Seal Registry (Role:ID:Position)
        if doc:
            meta = doc.metadata
            new_seal_key = f"seal:{role}:{sig_id}:{int(seal_rect.x0)},{int(seal_rect.y0)};"
            current_keywords = meta.get("keywords", "") or ""
            if new_seal_key not in current_keywords:
                meta["keywords"] = (current_keywords + " " + new_seal_key).strip()
                doc.set_metadata(meta)
                logger.info(f"signature.metadata_updated role={role} sig_id={sig_id} new_keywords='{meta['keywords']}'")

    # =========================================================================
    # Position Detection (Intent-Based: Multi-anchor scanning)
    # =========================================================================
    
    def _normalize_text(self, text_str: str) -> str:
        """Normaliza texto para búsqueda: minúsculas, sin acentos, sin dobles espacios."""
        if not text_str:
            return ""
        nks = unicodedata.normalize('NFKD', text_str)
        text_no_accents = "".join([c for c in nks if not unicodedata.combining(c)])
        clean = " ".join(text_no_accents.lower().split())
        return clean

    def detect_signature_positions(self, page, role: str) -> List[Dict]:
        """
        Busca TODAS las posiciones de firma para un rol usando diccionarios de anclas.
        Implementa detección robusta con Layout Awareness (Phase 15).
        Ranking: 1. Sector, 2. Proximidad al fondo, 3. Ancho de texto.
        """
        if not fitz:
            return []
        
        ANCHORS = {
            "employer": [
                r"\[\[firma_rpr\]\]",
                r"\bfirma del empleador\b", 
                r"\bfirma del responsable\b", 
                r"\bfirma empleador\b", 
                r"\baclaracion empleador\b"
            ],
            "employee": [
                r"\[\[firma_emp\]\]",
                r"\bfirma del empleado\b", 
                r"\bfirma del recibidor\b", 
                r"\bfirme el empleado\b", 
                r"\bfirma de conformidad\b",
                r"\brecibi conforme\b",
                r"\bfirma empleado\b"
            ]
        }
        
        patterns = ANCHORS.get(role, [])
        matches = []
        page_width = page.rect.width
        page_height = page.rect.height

        try:
            # Warm-up (Phase 15)
            blocks = page.get_text("blocks")
            page_text = self._normalize_text(page.get_text("text"))
            
            # Method 1: search_for (High precision with Regex boundaries)
            import re
            for p_pattern in patterns:
                # Compile regex for case-insensitive word boundary match
                # Use escaped pattern for literal brackets if they exist
                regex = re.compile(p_pattern, re.IGNORECASE)
                
                # Check if it exists in safe way
                # PyMuPDF search_for doesn't support regex directly in all versions, 
                # so we find coordinates of matches if the text is present.
                if regex.search(page_text):
                    # We use search_for with the literal text (un-regexed for fitz)
                    # BUT only if it matches our regex.
                    # This prevents 'empleado' matching 'empleador'.
                    search_term = p_pattern.replace(r"\b", "").replace(r"\[", "[").replace(r"\]", "]")
                    robust_rects = self.search_text_robust(page, search_term)
                    rects = robust_rects if robust_rects else [q.rect for q in page.search_for(search_term, quads=True)]
                    if rects:
                        for r in rects:
                            # Extra validation: ensure the rect content exactly matches (normalized)
                            # or strictly contains the word.
                            found_text = self._normalize_text(page.get_text("text", clip=r))
                            if regex.search(found_text) and not any(m["bbox"] == (r.x0, r.y0, r.x1, r.y1) for m in matches):
                                matches.append({
                                    "bbox": (r.x0, r.y0, r.x1, r.y1), 
                                    "pattern": search_term,
                                    "method": "search_for",
                                    "score": 100
                                })
            
            # Method 2: Layout blocks (Robustness fallback)
            # Only use this if Method 1 found nothing, to avoid "phantom" centerings on wide blocks.
            if not matches:
                for b in blocks:
                    # b = (x0, y0, x1, y1, "text", block_no, block_type)
                    b_text = self._normalize_text(b[4])
                    for p in patterns:
                        # Strip regex syntax before normalizing for plain text comparison
                        clean_p = p.replace(r"\b", "").replace(r"\[", "[").replace(r"\]", "]")
                        norm_p = self._normalize_text(clean_p)
                        if norm_p and norm_p in b_text:
                            matches.append({
                                "bbox": b[:4],
                                "pattern": clean_p,
                                "method": "layout_block",
                                "score": 60
                            })

            # Method 2.5: Observaciones Fallback
            if not matches:
                obs_rects = self.search_text_robust(page, "Observaciones")
                if obs_rects:
                    obs_rects.sort(key=lambda r: r.y1, reverse=True)
                    obs_rect = obs_rects[0]
                    y_pos = obs_rect.y1 + 15
                    found_obs = True
                else:
                    obs_quads = page.search_for("Observaciones", quads=True)
                    if obs_quads:
                        obs_quads.sort(key=lambda q: q.rect.y1, reverse=True)
                        obs_rect = obs_quads[0].rect
                        y_pos = obs_rect.y1 + 15
                        found_obs = True
                    else:
                        found_obs = False

                if found_obs:
                    if role == "employee":
                        matches.append({
                            "bbox": (50, y_pos, 250, y_pos + 60),
                            "pattern": "observaciones_fallback",
                            "method": "observaciones_zone",
                            "score": 55
                        })
                    elif role == "employer":
                        matches.append({
                            "bbox": (page_width - 250, y_pos, page_width - 50, y_pos + 60),
                            "pattern": "observaciones_fallback",
                            "method": "observaciones_zone",
                            "score": 55
                        })

            # Method 3: Fixed Zones Fallback (Employee Left, Employer Right)
            # Argentine payroll: Original (employee) = LEFT, Duplicado (employer) = RIGHT
            if not matches:
                y_pos = page_height - 120
                if role == "employee":
                    matches.append({
                        "bbox": (50, y_pos, 250, y_pos + 60),
                        "pattern": "fixed_zone",
                        "method": "fixed_zone",
                        "score": 50
                    })
                elif role == "employer":
                    matches.append({
                        "bbox": (page_width - 250, y_pos, page_width - 50, y_pos + 60),
                        "pattern": "fixed_zone",
                        "method": "fixed_zone",
                        "score": 50
                    })

            # Phase 21 & 25: Sector-Aware Ranking & Strict Bounding
            def rank_anchor(m):
                x0, y0, x1, y1 = m["bbox"]
                center_x = x0 + (x1 - x0) / 2
                
                is_left = center_x < (page_width * 0.55)
                is_right = center_x > (page_width * 0.45)
                
                # Strict enforcement: if role doesn't match sector, penalize heavily or skip
                sector_score = 0
                if role == "employer":
                    if is_right: sector_score = 100
                    else: sector_score = -500 # Heavy penalty for cross-sector match
                if role == "employee":
                    if is_left: sector_score = 100
                    else: sector_score = -500 # Heavy penalty for cross-sector match
                
                # 2. Distance from bottom (Recibos usually have signatures at the bottom)
                bottom_score = (y0 / page_height) * 40 
                
                # 3. Horizontal centering / width heuristic
                width_score = min(10, (x1 - x0) / 10)
                
                return sector_score + bottom_score + width_score

            matches.sort(key=rank_anchor, reverse=True)

            # Phase 25 Enhancement: Filter out anchors on the wrong sector entirely.
            filtered_matches = []
            for m in matches:
                x0, y0, x1, y1 = m["bbox"]
                center_x = x0 + (x1 - x0) / 2
                if role == "employer" and center_x <= page_width * 0.55:
                    continue
                if role == "employee" and center_x >= page_width * 0.45:
                    continue
                filtered_matches.append(m)

            if filtered_matches:
                matches = filtered_matches
            else:
                logger.info(f"signature.detection.filtered_out_wrong_sector role={role} page_width={int(page_width)} matches={len(matches)}")

        except Exception as e:
            logger.warning(f"signature.detection.error role={role}: {str(e)}")
            
        return matches

    def detect_signature_position(self, page, role: str) -> Optional[Dict]:
        """Fallback compatibility for single position detection."""
        positions = self.detect_signature_positions(page, role)
        return positions[0] if positions else None

    # =========================================================================
    # Signature File Storage
    # =========================================================================
    
    def save_signature_image(self, role: str, entity_id: str, image_bytes: bytes, 
                             parent_id: str = None) -> Dict[str, str]:
        """Guarda la imagen de firma en storage estructurado."""
        import config
        if len(image_bytes) < config.MIN_SIGNATURE_IMAGE_SIZE:
            raise SignatureError("Signature image too small")
        
        if role == "employer":
            dir_path = self.storage_path / "employer"
            file_path = dir_path / f"{entity_id}.png"
        else:
            if not parent_id:
                raise ValueError("parent_id (receipt_id) is required for employee signature")
            dir_path = self.storage_path / "employee" / str(parent_id)
            file_path = dir_path / f"{entity_id}.png"
            
        dir_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Clean and crop internal storage too
            clean_bytes = self._prepare_signature_image(image_bytes)
            
            # Atomic write for signature images
            import tempfile
            import os
            fd, temp_path = tempfile.mkstemp(dir=str(dir_path), prefix="tmp_sig_", suffix=".png")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(clean_bytes)
                os.replace(temp_path, str(file_path))
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
            
            sha = self.calculate_file_sha256(str(file_path))
            logger.info(f"signature.engine.saved role={role} path={file_path} (cleaned/cropped)")
            
            return {"path": str(file_path), "sha256": sha}
        except Exception as e:
            logger.error(f"signature.engine.save_failed: {str(e)}")
            raise SignatureError(f"Failed to save signature image: {str(e)}")
    
    def get_employer_signature_path(self, organization_id: str) -> str:
        """Obtiene la firma de empresa. Genera placeholder si no existe."""
        org_dir = self.storage_path / "employer"
        file_path = org_dir / f"{organization_id}.png"
        
        if not file_path.exists():
            self.generate_placeholder_signature(str(file_path), organization_id)
        
        return str(file_path)
    
    def generate_placeholder_signature(self, output_path: str, label: str):
        """Genera un PNG placeholder para firma."""
        import tempfile
        import os
        out_dir = os.path.dirname(output_path)
            
        try:
            img = Image.new("RGBA", (200, 80), color=(255, 255, 255, 0))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", 12)
            except:
                font = ImageFont.load_default()
            
            draw.text((10, 20), f"FIRMA AUTOMÁTICA\n{label}", fill=(100, 100, 100, 255), font=font)
            draw.line([(10, 60), (190, 60)], fill=(100, 100, 100, 200), width=1)
            
            os.makedirs(out_dir, exist_ok=True)
            
            # Atomic save
            fd, temp_path = tempfile.mkstemp(dir=out_dir, prefix="tmp_placeholder_", suffix=".png")
            os.close(fd)
            img.save(temp_path, "PNG")
            os.replace(temp_path, output_path)
            
        except Exception as e:
            logger.error(f"signature.engine.placeholder_failed: {e}")
            # Minimal file (also atomic)
            img = Image.new("RGB", (50, 20), color="white")
            fd, temp_path = tempfile.mkstemp(dir=out_dir, prefix="tmp_placeholder_err_", suffix=".png")
            os.close(fd)
            img.save(temp_path, "PNG")
            os.replace(temp_path, output_path)
    
    # =========================================================================
    # Integrity Utils
    # =========================================================================
    
    def calculate_file_sha256(self, file_path: str) -> str:
        """Calcula hash SHA256 de un archivo."""
        if not os.path.exists(file_path):
            raise SignatureIntegrityError(f"File not found: {file_path}")
        
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def validate_pdf_integrity(self, pdf_path: str, expected_sha256: str) -> bool:
        """Valida que el PDF no fue alterado."""
        try:
            actual_sha = self.calculate_file_sha256(pdf_path)
            return actual_sha == expected_sha256
        except Exception:
            return False

    def _prepare_signature_image(self, image_bytes: bytes) -> bytes:
        """
        Limpia el fondo blanco, recorta márgenes vacíos y devuelve PNG optimizado con transparencia.
        GAP-011 FIX: Added magic byte validation (PNG signature) to prevent crashes on malformed files.
        """
        from PIL import Image, ImageChops
        try:
            # Magic byte validation for PNG: \x89PNG\r\n\x1a\n
            if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                logger.error("signature.prepare_failed: invalid magic bytes (not PNG)")
                return image_bytes # Fallback
                
            img = Image.open(BytesIO(image_bytes)).convert("RGBA")
            
            # 1. Convertir "blancos" en transparentes (Umbral de ruido 230+)
            datas = img.getdata()
            new_data = []
            for item in datas:
                if item[0] > 230 and item[1] > 230 and item[2] > 230:
                    new_data.append((255, 255, 255, 0))
                else:
                    new_data.append(item)
            img.putdata(new_data)
            
            # 2. Autocrop: Eliminar márgenes vacíos
            bg = Image.new(img.mode, img.size, (255, 255, 255, 0))
            diff = ImageChops.difference(img, bg)
            diff = ImageChops.add(diff, diff, 2.0, -100)
            bbox = diff.getbbox()
            
            if bbox:
                # Pequeño margen de 3px para naturalidad
                bbox = (max(0, bbox[0]-3), max(0, bbox[1]-3), 
                        min(img.size[0], bbox[2]+3), min(img.size[1], bbox[3]+3))
                img = img.crop(bbox)
            
            out_io = BytesIO()
            img.save(out_io, format="PNG")
            return out_io.getvalue()
        except Exception as e:
            logger.error(f"signature.engine.prepare_failed: {e}")
            return image_bytes # Fallback

# =============================================================================
# Global Factory (Lazy Singleton)
# =============================================================================

# NOTA DE CONCURRENCIA (Phase 15): 
# Este singleton es seguro para runtimes de proceso único (SaaS estándar).
# En entornos como Gunicorn/Uvicorn con múltiples workers, cada worker 
# instanciará su propia copia del motor. Esto es el comportamiento esperado.
_engine_instance: Optional[SignatureEngine] = None

def get_signature_engine() -> SignatureEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = SignatureEngine()
    return _engine_instance
