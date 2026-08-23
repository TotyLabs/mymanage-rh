# Guía de instalación - MyManageRH

## 1. Propósito

Esta guía describe cómo preparar un entorno de MyManageRH para desarrollo, staging o producción. No incluye secretos reales ni rutas privadas. Toda variable sensible debe definirse fuera del código fuente.

## 2. Requisitos

| Componente | Requisito |
| --- | --- |
| Python | 3.10+ recomendado. |
| Base de datos | PostgreSQL 14+ recomendado. |
| Migraciones | Alembic. |
| Sistema operativo | Linux/Windows/WSL2 según entorno; producción recomendada en Linux. |
| Storage | Volumen persistente para PDFs, firmas, importaciones y evidencia. |
| PDF tooling | PyMuPDF requerido; pikepdf y Ghostscript recomendados para optimización. |
| Firma criptográfica | pyHanko, certificado X.509/P12 o HSM si aplica. |
| Email | SMTP o modo consola/sandbox. |

## 3. Variables de entorno

No usar valores reales en documentación. Usar `.env.example` o `.env.template` como base y completar secretos en el gestor correspondiente.

| Variable | Uso | Sensible |
| --- | --- | --- |
| `PRODUCTION` | Activa comportamiento productivo. | No |
| `SYSTEM_NAME` | Nombre visible del sistema. | No |
| `SYSTEM_PUBLIC_URL` o `BASE_PUBLIC_URL` | URL pública para links y sellos QR. | No |
| `DATABASE_URL` | Conexión PostgreSQL. | Sí |
| `SECRET_KEY` | Sesiones, tokens y HMAC internos. | Sí |
| `STORAGE_PATH` | Directorio base de archivos. | No, pero no exponer ruta real pública |
| `APP_ENCRYPTION_ENABLED` | Activa cifrado app-level de archivos sensibles. | No |
| `APP_ENCRYPTION_PROVIDER` | Provider KMS: `aws`, `gcp` o `local`. | No |
| `APP_ENCRYPTION_KMS_KEY_ID` | Identificador de KEK/KMS. | No, pero tratar como configuración sensible |
| `APP_ENCRYPTION_AWS_REGION` | Región AWS KMS si aplica. | No |
| `APP_ENCRYPTION_LOCAL_MASTER_KEY` | Master key local sólo para dev/testing. | Sí |
| `MAX_UPLOAD_SIZE_MB` | Límite de carga. | No |
| `MAX_PDF_PAGES` | Límite de páginas. | No |
| `TOKEN_TTL_HOURS` | TTL de tokens de firma. | No |
| `SESSION_TTL_HOURS` | TTL de sesiones. | No |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` | Configuración SMTP. | Parcial |
| `SMTP_PASSWORD` | Password SMTP. | Sí |
| `EMAIL_FROM` | Remitente. | No |
| `PAYROLL_WEBHOOK_URL` | Endpoint externo del cliente. | Puede ser sensible |
| `PAYROLL_WEBHOOK_SECRET` | Firma HMAC de webhook. | Sí |
| `X509_P12_PATH` | Ruta del bundle de firma. | No publicar ruta real |
| `X509_P12_PASSWORD` | Password P12. | Sí |
| `ROOT_CA_PATH`, `X509_CRL_PATH` | Certificados públicos/CRL. | No si son públicos |
| `TSA_URL` | Servicio de timestamp. | No |
| `HSM_ENABLED`, `HSM_LIB_PATH`, `HSM_SLOT`, `HSM_PIN` | HSM/PKCS#11. | `HSM_PIN` sí |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | SMS OTP. | SID/token sí |

## 4. Dependencias

Instalación base:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

En Windows, activar el virtualenv según shell local. No documentar rutas absolutas de máquina.

Dependencias relevantes:

- `fastapi`, `uvicorn`, `gunicorn`.
- `SQLAlchemy`, `psycopg2-binary`, `alembic`.
- `PyMuPDF`, `pikepdf`, `pyhanko`, `cryptography`.
- `slowapi` para rate limiting.
- `openpyxl`, `xlrd` para importaciones.
- `qrcode` para sellos QR.

## 5. Base de datos

1. Crear base PostgreSQL para el ambiente.
2. Crear usuario de aplicación con privilegios mínimos.
3. Configurar `DATABASE_URL`.
4. Ejecutar migraciones.
5. Validar conexión con health check profundo.

## 6. Migraciones

Ejecutar:

```bash
alembic upgrade head
```

Validaciones posteriores:

- Tablas core creadas.
- Enums actualizados.
- `audit_log`, `signature_events`, `signature_evidence`, `receipt_seals` disponibles.
- `webhook_outbox` creada si se usan webhooks.
- Scripts de RLS/inmutabilidad aplicados si el ambiente lo requiere.

## 7. Storage

Crear volumen persistente apuntado por `STORAGE_PATH`.

Subdirectorios esperados:

- `batches`.
- `receipts`.
- `signatures/employer`.
- `signatures/employee`.
- `identity`.
- `imports`.
- `forensics/failed_signatures`.

Requisitos:

- Permisos de lectura/escritura sólo para el usuario de aplicación.
- Backup consistente con base de datos.
- Cifrado en reposo AES-256 o equivalente mediante AWS S3 con SSE-KMS.
- No almacenar el volumen dentro de un repo público.

## 8. Certificados y firma criptográfica

Para firma X.509/PAdES-LTV:

1. Producción usa HSM/PKCS#11 como signer, con fallback a P12 local solo para desarrollo. KMS: AWS KMS. TSA: RFC 3161 vía `TSA_URL`.
2. Configurar `X509_P12_PATH` y `X509_P12_PASSWORD` si se usa P12.
3. Configurar `ROOT_CA_PATH` y `X509_CRL_PATH` si aplica.
4. Configurar `TSA_URL`.
5. Probar firma en staging con PDF ficticio.
6. Confirmar que el fallo de PKI no cierra recibos como firmados.

Nunca versionar P12 real, llaves privadas, passwords ni PINs HSM.

## 8.1 Cifrado app-level de archivos sensibles

Antes de activar en staging o producción:

1. Ejecutar migración `20260425_file_encryption_metadata`.
2. Provider KMS productivo: AWS KMS (configurar `APP_ENCRYPTION_PROVIDER=aws`).
3. Configurar `APP_ENCRYPTION_ENABLED=true`.
4. Configurar `APP_ENCRYPTION_PROVIDER=aws` o `APP_ENCRYPTION_PROVIDER=gcp`.
5. Configurar `APP_ENCRYPTION_KMS_KEY_ID`.
6. Validar permisos mínimos del rol de aplicación para `GenerateDataKey`/`Decrypt` o equivalente.
7. Probar carga, firma, descarga y restore con datos ficticios.

Dependencias por provider:

- AWS KMS requiere SDK AWS (`boto3`) instalado en el ambiente.
- Google Cloud KMS requiere SDK Google Cloud KMS (`google-cloud-kms`) instalado en el ambiente.
- Local no requiere SDK externo, pero no está permitido para producción.

Modo local:

- Usar únicamente en desarrollo/testing.
- Generar `APP_ENCRYPTION_LOCAL_MASTER_KEY` como base64 de 32 bytes.
- No reutilizar la master key local en staging ni producción.

## 9. Configuración de email

Modos:

- `EMAIL_MODE=console` para desarrollo o pruebas sin envío real.
- `EMAIL_MODE=smtp` o valor definido para producción.

Validar:

- Host/puerto SMTP.
- TLS habilitado.
- Remitente autorizado.
- Templates no contienen PII innecesaria.
- Rebotes y fallos quedan observables.

## 10. Configuración de webhooks

Variables:

- `PAYROLL_WEBHOOK_URL`.
- `PAYROLL_WEBHOOK_SECRET`.
- `WEBHOOK_MAX_RETRIES`.
- `WEBHOOK_BACKOFF_BASE`.
- `WEBHOOK_DRAIN_INTERVAL`.
- `WEBHOOK_TIMEOUT`.

Validar con endpoint de prueba del cliente:

- Firma HMAC `X-Webhook-Signature`.
- `X-Idempotency-Key`.
- Reintentos.
- Estado `dead_letter`.

## 11. Arranque local

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Validar:

- `GET /health` responde `alive`.
- UI carga desde `/`.
- Login funciona con usuario de prueba ficticio.
- No hay secretos reales en logs.

## 12. Arranque producción

Opción típica:

```bash
gunicorn main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Requisitos:

- Reverse proxy con TLS 1.2/1.3.
- Variables cargadas desde secret manager.
- Storage persistente montado.
- Migraciones ejecutadas antes de publicar tráfico.
- Health checks configurados.
- Logs centralizados.
- Backups habilitados.

## 13. Health checks

| Endpoint | Uso |
| --- | --- |
| `/health` | Liveness simple. |
| `/health/deep` | Readiness con DB, storage y métricas operativas. |

El health profundo no debe exponerse públicamente sin controles de red o autenticación perimetral.

## 14. Troubleshooting

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| El sistema no arranca | Falta `SECRET_KEY` o `DATABASE_URL`. | Completar variables obligatorias. |
| Login falla para usuarios válidos | Cuenta no activa, no verificada o bloqueada. | Revisar estado de usuario e intentos fallidos. |
| Carga PDF falla | Formato inválido, tamaño excedido o magic bytes incorrectos. | Validar archivo y límites. |
| Firma queda procesando | Falla intermedia dejó `processing_signature=true`. | Ejecutar procedimiento de limpieza de locks zombies. |
| X.509 falla | Falta P12, password, Root CA, CRL, TSA o HSM. | Revisar configuración PKI. |
| Firma falla con `encryption_kms_failed_no_plaintext_persisted` | KMS inaccesible o permisos insuficientes. | Revisar provider, rol KMS, conectividad TLS y evento `kms_error`. |
| Descarga de archivo cifrado falla | Metadata faltante, KMS inaccesible o auth tag mismatch. | Bloquear acceso, revisar `file_encryption_metadata`, audit log y storage. |
| Webhooks no salen | `PAYROLL_WEBHOOK_URL` ausente o endpoint falla. | Revisar outbox y dead-letter. |
| No llegan emails | SMTP inválido o modo consola. | Revisar `EMAIL_MODE`, credenciales y logs. |
| Hash no coincide | Archivo alterado, restore incompleto o bug de storage. | Bloquear operación y abrir incidente. |


## 15. Configuración de Directorio Temporal Seguro

El sistema requiere un directorio para procesar archivos sensibles.

**Configuración recomendada (Linux Production):**
Montar un `tmpfs` en `/dev/shm` para que los archivos nunca toquen el disco físico:
```bash
# Generalmente ya viene montado en Linux.
# Verificar permisos:
ls -ld /dev/shm
```

**Fallback (Cross-platform):**
Si `/dev/shm` no está disponible, el sistema usará `<STORAGE_PATH>/.tmp_secure/`. 
Asegúrese de que el usuario que corre la app tenga permisos exclusivos.
