"""
Services package for business logic.

Este paquete contiene servicios que encapsulan lÃ³gica de dominio,
separÃ¡ndola de las utilities tÃ©cnicas puras en core.py.

MÃ³dulos:
- signature_service: LÃ³gica de firma digital de recibos
- signed_resource_service: firma de token de recursos protegidos
- resource_resolver: resolución de recursos opacos sin tabla nueva
- download_policy_service: política de acceso a descargas sensibles
"""

__all__ = [
    "signature_service",
    "signed_resource_service",
    "resource_resolver",
    "download_policy_service",
]
