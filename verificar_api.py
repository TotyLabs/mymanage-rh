import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def main() -> None:
    email = os.getenv("AWS_SES_VERIFY_EMAIL")
    region = os.getenv("AWS_REGION", "us-east-1")
    if not email:
        raise SystemExit("Configure AWS_SES_VERIFY_EMAIL con la dirección autorizada que desea verificar.")

    client = boto3.client("ses", region_name=region)
    try:
        client.verify_email_identity(EmailAddress=email)
    except (BotoCoreError, ClientError) as exc:
        raise SystemExit(f"No se pudo solicitar la verificación SES: {type(exc).__name__}") from exc

    print("Solicitud de verificación aceptada. Revise el buzón de la dirección configurada.")


if __name__ == "__main__":
    main()
