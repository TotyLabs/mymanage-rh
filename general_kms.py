#!/usr/bin/env python3
"""
MyManage - General Cloud KMS
LocalCloud Emulator

Crea o reutiliza una clave general para MyManage
y comprueba el cifrado y descifrado.

Uso exclusivo para desarrollo y pruebas.
"""

import os
import sys

import grpc

from google.cloud import kms_v1
from google.api_core.exceptions import (
    AlreadyExists,
    NotFound,
    GoogleAPICallError,
    RetryError,
)
from google.cloud.kms_v1.services.key_management_service.transports import (
    KeyManagementServiceGrpcTransport,
)


# ============================================================
# CONFIGURACION
# ============================================================

PROJECT_ID = os.getenv(
    "KMS_PROJECT_ID",
    "local-gcp-project",
)

LOCATION = os.getenv(
    "KMS_LOCATION",
    "global",
)

KEY_RING_ID = "mymanage-general"
CRYPTO_KEY_ID = "general-key"

KMS_ENDPOINT = os.getenv(
    "CLOUD_KMS_EMULATOR_HOST",
    "127.0.0.1:5380",
)

TIMEOUT = 15


# ============================================================
# CONEXION CON LOCALCLOUD
# ============================================================

def create_kms_client():
    print(f"[INFO] Conectando a LocalCloud: {KMS_ENDPOINT}")

    channel = grpc.insecure_channel(KMS_ENDPOINT)

    try:
        grpc.channel_ready_future(channel).result(
            timeout=TIMEOUT
        )
    except grpc.FutureTimeoutError:
        channel.close()
        raise RuntimeError(
            f"No se pudo conectar con LocalCloud en {KMS_ENDPOINT}"
        )

    transport = KeyManagementServiceGrpcTransport(
        channel=channel,
    )

    client = kms_v1.KeyManagementServiceClient(
        transport=transport,
    )

    print("[OK] Conexion gRPC establecida")

    return client, channel


# ============================================================
# CREAR O REUTILIZAR KEY RING
# ============================================================

def ensure_key_ring(client):
    parent = (
        f"projects/{PROJECT_ID}"
        f"/locations/{LOCATION}"
    )

    name = f"{parent}/keyRings/{KEY_RING_ID}"

    try:
        key_ring = client.get_key_ring(
            request={"name": name},
            timeout=TIMEOUT,
        )

        print(f"[OK] KeyRing existente: {key_ring.name}")
        return key_ring.name

    except NotFound:
        print("[INFO] KeyRing no encontrado. Creando...")

    try:
        key_ring = client.create_key_ring(
            request={
                "parent": parent,
                "key_ring_id": KEY_RING_ID,
                "key_ring": {},
            },
            timeout=TIMEOUT,
        )

        print(f"[OK] KeyRing creado: {key_ring.name}")
        return key_ring.name

    except AlreadyExists:
        print(f"[OK] KeyRing ya existente: {name}")
        return name


# ============================================================
# CREAR O REUTILIZAR CRYPTO KEY
# ============================================================

def ensure_crypto_key(client, key_ring_name):
    name = (
        f"{key_ring_name}"
        f"/cryptoKeys/{CRYPTO_KEY_ID}"
    )

    try:
        key = client.get_crypto_key(
            request={"name": name},
            timeout=TIMEOUT,
        )

        if key.purpose != (
            kms_v1.CryptoKey.CryptoKeyPurpose.ENCRYPT_DECRYPT
        ):
            raise RuntimeError(
                "La CryptoKey existente no permite ENCRYPT_DECRYPT"
            )

        print(f"[OK] CryptoKey existente: {key.name}")
        return key.name

    except NotFound:
        print("[INFO] CryptoKey no encontrada. Creando...")

    try:
        key = client.create_crypto_key(
            request={
                "parent": key_ring_name,
                "crypto_key_id": CRYPTO_KEY_ID,
                "crypto_key": {
                    "purpose": (
                        kms_v1.CryptoKey.CryptoKeyPurpose.ENCRYPT_DECRYPT
                    ),
                    "version_template": {
                        "algorithm": (
                            kms_v1.CryptoKeyVersion.CryptoKeyVersionAlgorithm.GOOGLE_SYMMETRIC_ENCRYPTION
                        ),
                        "protection_level": (
                            kms_v1.ProtectionLevel.SOFTWARE
                        ),
                    },
                },
            },
            timeout=TIMEOUT,
        )

        print(f"[OK] CryptoKey creada: {key.name}")
        return key.name

    except AlreadyExists:
        key = client.get_crypto_key(
            request={"name": name},
            timeout=TIMEOUT,
        )

        if key.purpose != (
            kms_v1.CryptoKey.CryptoKeyPurpose.ENCRYPT_DECRYPT
        ):
            raise RuntimeError(
                "La CryptoKey existente no permite ENCRYPT_DECRYPT"
            )

        print(f"[OK] CryptoKey ya existente: {key.name}")
        return key.name


# ============================================================
# PRUEBA DE CIFRADO
# ============================================================

def test_encryption(client, key_name):
    print("\n[TEST] Iniciando prueba de cifrado...")

    original = (
        b"MyManage - General KMS encryption test"
    )

    response = client.encrypt(
        request={
            "name": key_name,
            "plaintext": original,
        },
        timeout=TIMEOUT,
    )

    ciphertext = response.ciphertext

    if not ciphertext:
        raise RuntimeError(
            "KMS devolvio un ciphertext vacio"
        )

    if ciphertext == original:
        raise RuntimeError(
            "El contenido cifrado coincide con el original"
        )

    print("[OK] Mensaje cifrado correctamente")
    print(f"[INFO] Bytes cifrados: {len(ciphertext)}")


    # ========================================================
    # PRUEBA DE DESCIFRADO
    # ========================================================

    print("\n[TEST] Iniciando prueba de descifrado...")

    response = client.decrypt(
        request={
            "name": key_name,
            "ciphertext": ciphertext,
        },
        timeout=TIMEOUT,
    )

    decrypted = response.plaintext

    if decrypted != original:
        raise RuntimeError(
            "ERROR DE INTEGRIDAD: el mensaje no coincide"
        )

    print("[OK] Mensaje descifrado correctamente")
    print("[OK] Integridad de datos verificada")

    return True


# ============================================================
# FUNCION PRINCIPAL
# ============================================================

def main():
    print("=" * 60)
    print("MyManage - General Cloud KMS")
    print("=" * 60)

    channel = None

    try:
        client, channel = create_kms_client()

        print("\n[INFO] Verificando recursos KMS...")

        key_ring_name = ensure_key_ring(client)

        crypto_key_name = ensure_crypto_key(
            client,
            key_ring_name,
        )

        test_encryption(
            client,
            crypto_key_name,
        )

        print("\n" + "=" * 60)
        print("[SUCCESS] MyManage General KMS operativo")
        print("=" * 60)

        print(f"Proyecto: {PROJECT_ID}")
        print(f"Ubicacion: {LOCATION}")
        print(f"KeyRing: {KEY_RING_ID}")
        print(f"CryptoKey: {CRYPTO_KEY_ID}")

        print("\nRuta completa:")
        print(crypto_key_name)

        print("\n[OK] Todas las pruebas completadas")

    except (
        GoogleAPICallError,
        RetryError,
        grpc.RpcError,
        RuntimeError,
    ) as exc:
        print(
            f"\n[ERROR] {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    except Exception as exc:
        print(
            f"\n[ERROR INESPERADO] "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    finally:
        if channel is not None:
            channel.close()


if __name__ == "__main__":
    main()
