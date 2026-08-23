from fastapi import Request
import os

def get_real_ip(request: Request) -> str:
    """
    GAP-005 FIX: Only trust proxy headers when request comes from a known-safe source.
    In development or if untrusted, use client.host.
    """
    PRODUCTION = os.getenv("PRODUCTION", "false").lower() == "true"
    client_ip = request.client.host if request.client else "unknown"
    
    trusted_proxies = ["127.0.0.1", "::1"]
    
    if PRODUCTION and client_ip in trusted_proxies:
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip: return cf_ip.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded: return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip: return real_ip.strip()

    return client_ip
