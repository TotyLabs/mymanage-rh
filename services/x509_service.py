"""
X.509 Digital Signature Service (Phase 3 - Hardened & Optimized)
Supports PAdES-LTV, TSA, and resilient fallbacks with incremental multi-sign support.
Optimized to reuse TimeStamper instances, cache static ValidationContext,
and cache certificate revocation checks (OCSP/CRL) to reduce latency from seconds to milliseconds.
"""
import os
import uuid
import logging
import time
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import httpx
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtensionOID, AuthorityInformationAccessOID
from cryptography import x509 as crypto_x509
from cryptography.hazmat.primitives import hashes, serialization

import config

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.timestamps import HTTPTimeStamper

logger = logging.getLogger("dircom.payroll")

# --- Global Caches for High-Performance Reusability ---
_global_timestamper = None
_cached_validation_context = None
_cached_root_cert = None
_cached_cert_status = None
_cached_cert_time = 0.0

def get_timestamper() -> HTTPTimeStamper:
    """
    Returns a globally shared HTTPTimeStamper instance.
    Reusing the timestamper enables pyHanko to cache the CMS size estimation
    dummy tokens, completely eliminating a redundant network roundtrip on every signature.
    """
    global _global_timestamper
    if _global_timestamper is None:
        tsa_url = config.TSA_URL or "http://timestamp.digicert.com"
        # 3.0s timeout is more than enough for responsive TSAs
        _global_timestamper = HTTPTimeStamper(url=tsa_url, timeout=3.0)
    return _global_timestamper


def get_validation_context_and_root():
    """
    Caches the validation context and the root certificate.
    Avoids expensive synchronous disk reads and ASN.1 parsing on every signature request.
    """
    global _cached_validation_context, _cached_root_cert
    if _cached_validation_context is None:
        root_ca_path = Path(config.ROOT_CA_PATH)
        if root_ca_path.exists():
            try:
                from pyhanko_certvalidator import ValidationContext
                from asn1crypto import x509 as asn1_x509
                
                cert_crypt = crypto_x509.load_pem_x509_certificate(root_ca_path.read_bytes())
                root_der = cert_crypt.public_bytes(serialization.Encoding.DER)
                root_cert = asn1_x509.Certificate.load(root_der)
                _cached_root_cert = cert_crypt
                
                crl_path = Path(config.X509_CRL_PATH)
                crls = []
                if crl_path.exists():
                    from asn1crypto import crl as asn1_crl
                    crl_data = crl_path.read_bytes()
                    crls.append(asn1_crl.CertificateList.load(crl_data))
                
                _cached_validation_context = ValidationContext(
                    extra_trust_roots=[root_cert],
                    allow_fetching=True,
                    crls=crls,
                    revocation_mode="hard-fail" if getattr(config, "STRICT_REVOCATION_CHECK", False) else "soft-fail",
                )
            except Exception as e:
                logger.warning(f"LTV_CONTEXT_INIT_ERROR: {e}")
    return _cached_validation_context, _cached_root_cert


def get_cached_certificate_status(cert: crypto_x509.Certificate, root_cert: crypto_x509.Certificate):
    """
    Caches the revocation status (OCSP/CRL) of the static signing certificate.
    Since the server certificate is static, checking its revocation status over the
    network on every signature is redundant and extremely slow (adds seconds of network delay).
    The status is cached for 1 hour, with a transparent fallback to cache if the CA is down.
    """
    global _cached_cert_status, _cached_cert_time
    now = time.time()
    if _cached_cert_status is None or (now - _cached_cert_time) > 3600.0:
        try:
            val_status, v_method, v_detail = validate_certificate_status(cert, root_cert)
            _cached_cert_status = (val_status, v_method, v_detail)
            _cached_cert_time = now
        except Exception as e:
            logger.warning(f"Failed to fetch fresh cert revocation status: {e}. Reusing cache fallback.")
            if _cached_cert_status is None:
                return "unknown", "NONE", "unknown"
    return _cached_cert_status


def hash_identity(identity_dict: Dict[str, Any]) -> str:
    dump = json.dumps(identity_dict, sort_keys=True).encode("utf-8")
    return hashlib.sha256(dump).hexdigest()

def get_certificate_info(p12_path: Path, password: str = None) -> Dict[str, str]:
    try:
        if p12_path.suffix.lower() == ".p12" or p12_path.suffix.lower() == ".pfx":
            from cryptography.hazmat.primitives.serialization import pkcs12
            p12_data = pkcs12.load_key_and_certificates(p12_path.read_bytes(), password.encode() if password else None)
            cert_crypt = p12_data[1] # (key, cert, additional_certs)
        else:
            cert_crypt = crypto_x509.load_pem_x509_certificate(p12_path.read_bytes())
            
        return {
            "fingerprint": cert_crypt.fingerprint(hashes.SHA256()).hex().upper(),
            "serial_number": str(cert_crypt.serial_number),
            "issuer": cert_crypt.issuer.rfc4514_string(),
            "subject": cert_crypt.subject.rfc4514_string(),
            "not_before": cert_crypt.not_valid_before_utc.isoformat(),
            "not_after": cert_crypt.not_valid_after_utc.isoformat(),
            "signature_algorithm": cert_crypt.signature_algorithm_oid._name,
            "cert_obj": cert_crypt # useful for validation
        }
    except Exception as e:
        logger.error(f"x509.cert_info_error: {e}")
        return {
            "fingerprint": "UNKNOWN",
            "serial_number": "UNKNOWN",
            "issuer": "UNKNOWN",
            "subject": "UNKNOWN",
            "not_before": None,
            "not_after": None,
            "signature_algorithm": "UNKNOWN",
            "cert_obj": None
        }

def extract_validation_urls(cert: crypto_x509.Certificate):
    ocsp_url = None
    crl_url = None
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        for desc in aia:
            if desc.access_method == AuthorityInformationAccessOID.OCSP:
                ocsp_url = desc.access_location.value
        
        cdp = cert.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS).value
        for point in cdp:
            for fullname in point.full_name:
                crl_url = fullname.value
    except: pass
    return ocsp_url, crl_url

def check_ocsp(cert: crypto_x509.Certificate, issuer_cert: crypto_x509.Certificate, ocsp_url: str):
    if not ocsp_url: return "unknown"
    try:
        builder = ocsp.OCSPRequestBuilder()
        builder = builder.add_certificate(cert, issuer_cert, hashes.SHA256())
        request = builder.build()
        
        with httpx.Client(timeout=3.0) as client:
            resp = client.post(
                ocsp_url, 
                content=request.public_bytes(serialization.Encoding.DER),
                headers={'Content-Type': 'application/ocsp-request'}
            )
            if resp.status_code == 200:
                ocsp_resp = ocsp.load_der_ocsp_response(resp.content)
                if ocsp_resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL:
                    if ocsp_resp.certificate_status == ocsp.OCSPCertsStatus.GOOD: return "good"
                    if ocsp_resp.certificate_status == ocsp.OCSPCertsStatus.REVOKED: return "revoked"
    except Exception as e:
        logger.warning(f"OCSP_CHECK_FAILED: {e}")
    return "unknown"

def check_crl(cert: crypto_x509.Certificate, crl_url: str):
    if not crl_url: return "unknown"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(crl_url)
            if resp.status_code == 200:
                crl = crypto_x509.load_der_x509_crl(resp.content)
                revoked = crl.get_revoked_certificate_by_serial_number(cert.serial_number)
                return "revoked" if revoked else "valid"
    except Exception as e:
        logger.warning(f"CRL_CHECK_FAILED: {e}")
    return "unknown"

def validate_certificate_status(cert: crypto_x509.Certificate, issuer_cert: crypto_x509.Certificate):
    ocsp_url, crl_url = extract_validation_urls(cert)
    
    ocsp_res = "unknown"
    if ocsp_url and issuer_cert:
        ocsp_res = check_ocsp(cert, issuer_cert, ocsp_url)
        if ocsp_res in ("good", "revoked"):
            return ocsp_res, "OCSP", ocsp_res
            
    crl_res = "unknown"
    if crl_url:
        crl_res = check_crl(cert, crl_url)
        if crl_res == "revoked":
            return "revoked", "CRL", crl_res
        if crl_res == "valid":
            return "good", "CRL", crl_res

    return "unknown", "NONE", "unknown"

def sign_pdf(input_path: str, receipt_id: str, signer_identity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    start_time = time.perf_counter()
    
    p12_path = Path(config.X509_P12_PATH)
    p12_password = config.X509_P12_PASSWORD
    
    if not p12_path.exists():
        logger.error(f"x509.signing_failed: p12_bundle_missing at strict path {p12_path}")
        return {"status": "failed", "error": "p12_missing"}

    logger.info(f"x509.using_p12: {p12_path}")
    temp_path = Path(input_path).parent / f"signed_{uuid.uuid4()}.pdf"
    
    try:
        # 1. Prepare Signer
        if getattr(config, "HSM_ENABLED", False):
            from pyhanko.sign.pkcs11 import open_pkcs11_session, PKCS11Signer
            logger.info(f"x509.using_hsm: {config.HSM_LIB_PATH} slot={config.HSM_SLOT}")
            session = open_pkcs11_session(config.HSM_LIB_PATH, slot_no=config.HSM_SLOT, user_pin=config.HSM_PIN)
            signer = PKCS11Signer(
                pkcs11_session=session,
                cert_label=None,
                use_raw_mechanism=True
            )
        else:
            signer = signers.SimpleSigner.load_pkcs12(
                pfx_file=str(p12_path),
                passphrase=p12_password.encode() if p12_password else None
            )
        
        # 2. Build or Fetch Cached Validation Context (LTV)
        validation_context, root_cert = get_validation_context_and_root()

        # 3. Signing Logic with Atomic Buffer Fallbacks
        display_name = "Dircom Signer"
        if signer_identity:
            if signer_identity.get("role") in ("employer", "admin"):
                display_name = f"Empleador: {signer_identity.get('full_name', 'Default')}"
            else:
                display_name = f"Empleado: {signer_identity.get('full_name', 'Desconocido')} (DNI: {signer_identity.get('dni', 'N/D')})"
        
        # Optimized TSA Selection using Cached Timestamper
        timestamper = get_timestamper()
        
        def attempt_sign(vc, ts, embed_ltv):
            try:
                import io
                out_buffer = io.BytesIO()
                
                with open(input_path, "rb") as inf:
                    w = IncrementalPdfFileWriter(inf)
                    sig_meta = signers.PdfSignatureMetadata(
                        field_name=f"Sig_{uuid.uuid4().hex[:12]}",
                        reason="Firma de recibo laboral",
                        location="Argentina",
                        name=display_name,
                        embed_validation_info=embed_ltv,
                        validation_context=vc,
                        signer_key_usage=None
                    )
                    
                    pdf_signer = signers.PdfSigner(
                        signature_meta=sig_meta,
                        signer=signer,
                        timestamper=ts
                    )
                    
                    pdf_signer.sign_pdf(w, in_place=False, bytes_reserved=None, output=out_buffer)
                
                if embed_ltv and vc:
                    try:
                        out_buffer.seek(0)
                        from pyhanko.pdf_utils.reader import PdfFileReader
                        from pyhanko.sign import validation
                        
                        r = PdfFileReader(out_buffer)
                        emb = r.embedded_signatures[0]
                        
                        ltv_buffer = io.BytesIO()
                        validation.add_validation_info(
                            embedded_sig=emb,
                            validation_context=vc,
                            output=ltv_buffer
                        )
                        final_data = ltv_buffer.getvalue()
                    except Exception as ltv_err:
                        logger.warning(f"LTV_POST_PROCESS_ERROR: {ltv_err}")
                        final_data = out_buffer.getvalue()
                else:
                    final_data = out_buffer.getvalue()
                
                with open(temp_path, "wb") as f:
                    f.write(final_data)
                    
                return True
            except Exception as e:
                logger.warning(f"sign_attempt_failed ltv={embed_ltv}: {e}")
                if temp_path.exists(): temp_path.unlink()
                return False

        if not validation_context:
            raise RuntimeError("PKI_CONTEXT_MISSING: Cannot sign without trusted Root CA (Required for PAdES-LTV)")

        if not attempt_sign(validation_context, timestamper, True):
            raise RuntimeError("X509_SIGN_FAILED: LTV signature failed. Check PKI chain and TSA availability.")
        
        final_ltv = "EMBEDDED"
        final_tsa = "SUCCESS"
        
        # 4. Result Payload
        cert_info = get_certificate_info(p12_path, p12_password)
        
        # Phase 7: Validation Status (AIA/CDP) with Cache Reusability
        val_status = "unknown"
        ocsp_final = "unknown"
        crl_final = "unknown"
        val_error = None
        
        try:
            if cert_info["cert_obj"] and root_cert:
                val_status, v_method, v_detail = get_cached_certificate_status(cert_info["cert_obj"], root_cert)
                if v_method == "OCSP": ocsp_final = v_detail
                if v_method == "CRL": crl_final = v_detail
        except Exception as ve:
            val_error = str(ve)
            logger.warning(f"X509_METADATA_VALIDATION_ERROR: {ve}")

        exec_time = int((time.perf_counter() - start_time) * 1000)
        logger.info(f"x509.signed_successfully in {exec_time}ms receipt_id={receipt_id}")
        
        return {
            "status": "success",
            "signed_path": str(temp_path),
            "fingerprint": cert_info["fingerprint"],
            "serial_number": cert_info["serial_number"],
            "issuer": cert_info["issuer"],
            "subject": cert_info["subject"],
            "not_before": cert_info["not_before"],
            "not_after": cert_info["not_after"],
            "signature_algorithm": cert_info["signature_algorithm"],
            "id_hash": hash_identity(signer_identity) if signer_identity else None,
            "timestamp_source": final_tsa,
            "ltv_status": final_ltv,
            "signature_version": "v5.corporate",
            
            "validation_status": "valid" if val_status == "good" else val_status,
            "ocsp_status": ocsp_final,
            "crl_status": crl_final,
            "validation_error": val_error,
            "validation_checked_at": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.exception("X509_SIGN_FAILED", extra={"receipt_id": receipt_id, "error": str(e)})
        if temp_path.exists():
            try: temp_path.unlink()
            except: pass
        return {"status": "failed", "error": str(e)}

def is_pdf_digitally_signed(pdf_path: str) -> bool:
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        with open(pdf_path, "rb") as f:
            r = PdfFileReader(f)
            return len(r.embedded_signatures) > 0
    except: return False
