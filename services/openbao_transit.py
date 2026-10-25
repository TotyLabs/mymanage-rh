"""Cliente OpenBao Transit para MyManage."""

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path


class TransitError(RuntimeError):
    """Error de operación criptográfica."""


class OpenBaoTransit:
    def __init__(
        self,
        address=None,
        key_name="mymanage-general",
        token_file=None,
        ca_cert=None,
    ):
        self.address = (
            address or os.environ.get("VAULT_ADDR", "https://127.0.0.1:8200")
        ).rstrip("/")
        if not self.address.startswith("https://"):
            raise ValueError("OpenBao address must use HTTPS")
        self.ssl_context = ssl.create_default_context(
            cafile=(
                ca_cert
                or os.environ.get("VAULT_CACERT")
                or str(Path.home() / ".config/mymanage/openbao/ca.crt")
            )
        )
        self.key_name = key_name
        self.token_file = Path(
            token_file
            or os.environ.get(
                "OPENBAO_TOKEN_FILE",
                str(
                    Path.home()
                    / ".config/mymanage/openbao/client_token"
                ),
            )
        )

    def _token(self):
        token = self.token_file.read_text().strip()
        if not token:
            raise TransitError("Token OpenBao vacío")
        return token

    def _request(self, operation, payload):
        url = (
            f"{self.address}/v1/transit/"
            f"{operation}/{self.key_name}"
        )

        body = json.dumps(payload).encode("utf-8")

        for attempt in range(2):
            token = self._token()

            request = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "X-Vault-Token": token,
                    "Content-Type": "application/json",
                },
            )

            try:
                with urllib.request.urlopen(
                    request, timeout=10, context=self.ssl_context
                ) as response:
                    result = json.load(response)

                return result["data"]

            except urllib.error.HTTPError as exc:
                # Reintentar únicamente si el agente
                # reemplazó el token durante la operación.
                if (
                    exc.code in (401, 403)
                    and attempt == 0
                    and self._token() != token
                ):
                    continue

                raise TransitError(
                    f"OpenBao rechazó {operation}: "
                    f"HTTP {exc.code}"
                ) from None

            except (OSError, ValueError, KeyError) as exc:
                raise TransitError(
                    f"Error de comunicación con OpenBao: "
                    f"{type(exc).__name__}"
                ) from exc

        raise TransitError("No se pudo completar la operación")

    def encrypt(self, plaintext: str) -> str:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext debe ser str")

        encoded = base64.b64encode(
            plaintext.encode("utf-8")
        ).decode("ascii")

        result = self._request(
            "encrypt",
            {"plaintext": encoded},
        )
        return result["ciphertext"]

    def decrypt(self, ciphertext: str) -> str:
        if not isinstance(ciphertext, str):
            raise TypeError("ciphertext debe ser str")

        result = self._request(
            "decrypt",
            {"ciphertext": ciphertext},
        )

        return base64.b64decode(
            result["plaintext"],
            validate=True,
        ).decode("utf-8")
