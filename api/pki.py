"""
api/pki.py

PKI Endpoints - Serves CRL, Root CA certificate, and OCSP responses.
These endpoints are referenced by CRLDistributionPoints and
AuthorityInfoAccess extensions in the signer certificate.
"""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import Response
import config

router = APIRouter(prefix="/pki", tags=["PKI"])


@router.get("/root_ca.crl")
async def get_crl():
    """Serve the current CRL in DER format."""
    crl_path = Path(config.X509_CRL_PATH)
    if not crl_path.exists():
        # Generate CRL on-the-fly if missing
        from services.pki_service import generate_crl
        generate_crl()
    
    crl_data = crl_path.read_bytes()
    return Response(
        content=crl_data,
        media_type="application/pkix-crl",
        headers={"Cache-Control": "public, max-age=86400"}
    )


@router.get("/root_ca.crt")
async def get_root_ca():
    """Serve the Root CA certificate in PEM (or DER) format."""
    root_path = Path(config.ROOT_CA_PATH)
    if not root_path.exists():
        return Response(content=b"Root CA not found", status_code=404)
    
    cert_data = root_path.read_bytes()
    return Response(
        content=cert_data,
        media_type="application/x-pem-file",
        headers={
            "Content-Disposition": "attachment; filename=root_ca.crt",
            "Cache-Control": "public, max-age=86400"
        }
    )


@router.post("/ocsp")
@router.get("/ocsp")
async def ocsp_responder():
    """Minimal OCSP stub - returns 'good' for all queries.
    
    For a private CA with no revocations, this satisfies Adobe Acrobat's
    OCSP check by indicating the certificate is not revoked.
    
    NOTE: A production system should implement full OCSP response
    generation using the Root CA key. For now, this returns a
    tryLater response which tells clients to fall back to CRL.
    """
    # OCSP tryLater response (RFC 6960 Section 4.2.1)
    # responseStatus = tryLater (3)
    # This is a valid OCSP response that tells the client to use CRL instead
    try_later_response = bytes([0x30, 0x03, 0x0a, 0x01, 0x03])
    return Response(
        content=try_later_response,
        media_type="application/ocsp-response",
    )

