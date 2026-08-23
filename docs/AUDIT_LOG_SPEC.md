# Audit Log Spec - MyManageRH

## 1. Propósito

Esta especificación define el modelo interno de logs de auditoría de MyManageRH. Su objetivo es responder de forma consistente: quién accedió, cuándo accedió, qué hizo, qué cambió, desde dónde y sobre qué recurso.

## 2. Alcance

Incluye eventos de autenticación, recibos, firma, empleados, administración, seguridad, webhooks y documentos. No reemplaza logs técnicos de infraestructura, aunque debe correlacionarse con ellos.

## 3. Principios

- Registrar eventos de negocio y seguridad relevantes.
- No guardar secretos ni tokens en texto plano.
- Redactar PII cuando el evento no requiera evidencia completa.
- Usar identificadores estables: `organization_id`, `actor_id`, `resource_id`, `receipt_id`.
- Mantener timestamps UTC.
- Diseñar logs como append-only.
- Separar auditoría legal de debugging operativo.

## 4. Campos obligatorios

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `event_id` | string/uuid | Identificador único del evento. |
| `event_type` | string | Tipo canónico de evento. |
| `occurred_at` | datetime | Fecha/hora UTC del evento. |
| `organization_id` | uuid/string | Tenant afectado. |
| `actor_type` | enum | `admin`, `employee`, `system` o `anonymous`. |
| `actor_id` | uuid/string/null | Usuario actor cuando existe. |
| `action` | string | Acción ejecutada. |
| `resource_type` | string | Tipo de recurso afectado. |
| `resource_id` | uuid/string/null | ID del recurso afectado. |
| `result` | enum | `success`, `failure`, `denied`, `pending`. |
| `source_ip` | string/null | IP de origen. |
| `user_agent` | string/null | User-agent truncado y seguro. |
| `request_id` | string/null | Correlación por request. |
| `event_hash` | string | Hash canónico del evento, excluyendo campos de cadena. |
| `previous_hash` | string/null | Hash del evento anterior en la cadena auditada. |
| `chain_hash` | string | Hash encadenado del evento actual. |

## 5. Campos opcionales

| Campo | Uso |
| --- | --- |
| `receipt_id` | Recibo afectado. |
| `employee_id` | Empleado afectado. |
| `batch_id` | Lote asociado. |
| `signature_request_id` | Solicitud/token de firma. |
| `verification_id` | Evidencia de firma o verificación. |
| `seal_id` | Sello QR. |
| `before` | Snapshot redactado antes del cambio. |
| `after` | Snapshot redactado después del cambio. |
| `changes` | Diff de campos modificados. |
| `file_hash_before` | SHA-256 anterior. |
| `file_hash_after` | SHA-256 posterior. |
| `certificate_fingerprint` | Fingerprint X.509. |
| `timestamp_source` | `TSA`, `LOCAL_FALLBACK`, `NONE`. |
| `error_code` | Código estable de error. |
| `risk_score` | Puntaje opcional para seguridad. |
| `metadata` | JSON adicional redactado. |
| `batch_signature` | Firma opcional de un lote de eventos exportado a almacenamiento externo. |

## 6. Tipos de eventos

### 6.1 Autenticación

- `AUTH_REGISTER_ORGANIZATION`.
- `AUTH_REGISTER_EMPLOYEE`.
- `AUTH_LOGIN_SUCCESS`.
- `AUTH_LOGIN_FAILURE`.
- `AUTH_ACCOUNT_LOCKED`.
- `AUTH_LOGOUT`.
- `AUTH_PASSWORD_RESET_REQUESTED`.
- `AUTH_PASSWORD_RESET_COMPLETED`.
- `AUTH_SESSION_EXPIRED`.

### 6.2 Recibos

- `RECEIPT_BATCH_UPLOADED`.
- `RECEIPT_CREATED`.
- `RECEIPT_MATCHED`.
- `RECEIPT_PENDING_MATCH`.
- `RECEIPT_DOWNLOADED`.
- `RECEIPT_DELETED_SOFT`.
- `RECEIPT_DELETE_DENIED_SIGNED`.
- `PAYMENT_RECEIPT_ATTACHED`.
- `PAYMENT_RECEIPT_DOWNLOADED`.

### 6.3 Firma

- `SIGNATURE_REQUEST_CREATED`.
- `SIGNATURE_TOKEN_VALIDATED`.
- `SIGNATURE_OTP_SENT`.
- `SIGNATURE_OTP_VERIFIED`.
- `EMPLOYER_SIGNATURE_STARTED`.
- `EMPLOYER_SIGNATURE_COMPLETED`.
- `EMPLOYEE_SIGNATURE_STARTED`.
- `EMPLOYEE_SIGNATURE_COMPLETED`.
- `DOCUMENT_SIGNED_X509`.
- `SIGNATURE_REJECTED`.
- `SIGNATURE_FAILED`.
- `DOCUMENT_LOCKED`.
- `SEAL_CREATED`.

### 6.4 Empleados

- `EMPLOYEE_CREATED`.
- `EMPLOYEE_UPDATED`.
- `EMPLOYEE_DELETED_SOFT`.
- `EMPLOYEE_BULK_IMPORT_PREVIEWED`.
- `EMPLOYEE_BULK_IMPORT_EXECUTED`.
- `EMPLOYEE_VERIFIED_AND_ACTIVATED`.
- `EMPLOYEE_DNI_UPLOADED`.
- `EMPLOYEE_RECORD_EXPORTED`.

### 6.5 Administración

- `ORG_CREATED`.
- `ORG_UPDATED`.
- `ORG_LOGO_UPLOADED`.
- `COMPANY_SIGNER_CREATED`.
- `COMPANY_SIGNER_TOGGLED`.
- `COMPANY_SIGNER_DELETED`.
- `DOCUMENT_ARCHIVED`.
- `DOCUMENT_RESTORED`.
- `DOCUMENT_DELETED`.

### 6.6 Seguridad

- `SECURITY_CSRF_DENIED`.
- `SECURITY_RATE_LIMITED`.
- `SECURITY_PATH_TRAVERSAL_BLOCKED`.
- `SECURITY_INVALID_MAGIC_BYTES`.
- `SECURITY_INTEGRITY_VIOLATION`.
- `SECURITY_RLS_CONTEXT_FAILED`.
- `SECURITY_SECRET_MISSING`.
- `SECURITY_CERTIFICATE_VALIDATION_FAILED`.

### 6.7 Cifrado y KMS

- `document_encrypted`.
- `document_decrypted`.
- `kms_key_used`.
- `kms_error`.

Campos mínimos para eventos de cifrado:

| Campo | Obligatorio | Descripción |
| --- | --- | --- |
| `actor_id` | Sí, salvo proceso `system` | Usuario o proceso que disparó la operación. |
| `organization_id` | Sí | Tenant propietario del archivo. |
| `file_id` | Sí | UUID del archivo cifrado en `file_encryption_metadata`. |
| `timestamp` | Sí | Fecha/hora del evento. |
| `purpose` | Sí | Uso canónico: `signed_receipt_pdf`, `signature_evidence_image`, `payment_receipt`, `identity_snapshot:dni_front`, etc. |
| `kms_key_id` | Sí para `kms_key_used` | Identificador no secreto de KEK/KMS. |
| `kms_provider` | Sí para `kms_key_used` | `aws`, `gcp` o `local`. |
| `error_code` | Sí para `kms_error` | Código técnico sin secretos ni payload sensible. |

### 6.8 Webhooks

- `WEBHOOK_ENQUEUED`.
- `WEBHOOK_DELIVERED`.
- `WEBHOOK_RETRY_SCHEDULED`.
- `WEBHOOK_DEAD_LETTER`.
- `WEBHOOK_SIGNATURE_INVALID`.

## 7. Ejemplos JSON

### 7.1 Login exitoso

```json
{
  "event_id": "evt_000001",
  "event_type": "AUTH_LOGIN_SUCCESS",
  "occurred_at": "2026-04-25T14:00:00Z",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "actor_type": "admin",
  "actor_id": "22222222-2222-4222-8222-222222222222",
  "action": "LOGIN",
  "resource_type": "user",
  "resource_id": "22222222-2222-4222-8222-222222222222",
  "result": "success",
  "source_ip": "203.0.113.10",
  "user_agent": "Mozilla/5.0 (ficticio)",
  "request_id": "req_demo_001",
  "metadata": {
    "auth_method": "session"
  }
}
```

### 7.2 Firma del empleado completada

```json
{
  "event_id": "evt_000145",
  "event_type": "EMPLOYEE_SIGNATURE_COMPLETED",
  "occurred_at": "2026-04-25T14:40:00Z",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "actor_type": "employee",
  "actor_id": "33333333-3333-4333-8333-333333333333",
  "action": "SIGN_RECEIPT",
  "resource_type": "receipt",
  "resource_id": "44444444-4444-4444-8444-444444444444",
  "receipt_id": "44444444-4444-4444-8444-444444444444",
  "employee_id": "55555555-5555-4555-8555-555555555555",
  "result": "success",
  "source_ip": "203.0.113.20",
  "user_agent": "Mozilla/5.0 (ficticio)",
  "file_hash_before": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "file_hash_after": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "seal_id": "AB12CD34EF56AB78",
  "verification_id": "verif_demo_20260425_001",
  "certificate_fingerprint": "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
  "timestamp_source": "TSA",
  "metadata": {
    "signature_method": "visual+x509",
    "identity_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  }
}
```

### 7.3 Intento de alteración detectado

```json
{
  "event_id": "evt_000211",
  "event_type": "SECURITY_INTEGRITY_VIOLATION",
  "occurred_at": "2026-04-25T15:05:00Z",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "actor_type": "system",
  "actor_id": null,
  "action": "VERIFY_DOCUMENT_HASH",
  "resource_type": "receipt",
  "resource_id": "44444444-4444-4444-8444-444444444444",
  "result": "failure",
  "source_ip": null,
  "user_agent": null,
  "file_hash_before": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "file_hash_after": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "error_code": "hash_mismatch",
  "metadata": {
    "action_blocked": true
  }
}
```

### 7.4 Documento cifrado

```json
{
  "event_id": "evt_000260",
  "event_type": "document_encrypted",
  "occurred_at": "2026-04-25T15:30:00Z",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "actor_type": "admin",
  "actor_id": "22222222-2222-4222-8222-222222222222",
  "action": "document_encrypted",
  "resource_type": "file",
  "resource_id": "33333333-3333-4333-8333-333333333333",
  "result": "success",
  "metadata": {
    "file_id": "33333333-3333-4333-8333-333333333333",
    "purpose": "signed_receipt_pdf",
    "algorithm": "AES-256-GCM",
    "plaintext_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "ciphertext_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
```

### 7.5 Uso de KMS

```json
{
  "event_id": "evt_000261",
  "event_type": "kms_key_used",
  "occurred_at": "2026-04-25T15:30:01Z",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "actor_type": "admin",
  "actor_id": "22222222-2222-4222-8222-222222222222",
  "action": "kms_key_used",
  "resource_type": "file",
  "resource_id": "33333333-3333-4333-8333-333333333333",
  "result": "success",
  "metadata": {
    "file_id": "33333333-3333-4333-8333-333333333333",
    "purpose": "signed_receipt_pdf",
    "kms_key_id": "arn:aws:kms:[REGION]:[ACCOUNT]:key/[KEY-ID]",
    "kms_provider": "aws",
    "operation": "generate_data_key"
  }
}
```

### 7.6 Error de KMS

```json
{
  "event_id": "evt_000262",
  "event_type": "kms_error",
  "occurred_at": "2026-04-25T15:31:00Z",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "actor_type": "admin",
  "actor_id": "22222222-2222-4222-8222-222222222222",
  "action": "kms_error",
  "resource_type": "file",
  "resource_id": "33333333-3333-4333-8333-333333333333",
  "result": "failure",
  "metadata": {
    "file_id": "33333333-3333-4333-8333-333333333333",
    "purpose": "signed_receipt_pdf",
    "error_code": "aws_kms_generate_data_key_failed"
  }
}
```

## 8. Política de retención

Pendiente: definir retención final por cliente/jurisdicción.

Base definida:

- Audit legal de recibos y firmas: conservar por 5 a 10 años según normativa laboral argentina.
- Logs técnicos: conservar por 1 año.
- Logs de incidentes: preservar hasta cierre legal/compliance.
- Evidencia vinculada a disputa: legal hold hasta resolución.

## 9. Inmutabilidad

Requisitos:

- `audit_log`, `signature_events`, `signature_evidence` y `receipt_seals` deben tratarse como append-only.
- Updates y deletes deben bloquearse por permisos o triggers en producción.
- La cadena `previous_hash`/`chain_hash` debe verificarse periódicamente si está habilitada.
- El usuario de aplicación no debe tener permisos directos para borrar evidencia crítica.

## 10. Redacción de PII

No registrar en claro: contraseñas, tokens raw, cookies, Authorization, firmas base64 completas, PDFs completos, CBU completo, DNI/CUIL completo salvo evidencia privada justificada.

| Dato | Redacción |
| --- | --- |
| Email | `a***@example.test` o hash. |
| DNI | últimos 3 o 4 dígitos. |
| CUIL/CUIT | últimos 3 o 4 dígitos. |
| IP | completa en evidencia privada; truncada en analytics. |
| Hashes | completos en evidencia; enmascarados en logs de soporte si no son necesarios. |

## 11. Uso en auditoría legal y debugging

| Uso | Fuente primaria | Precaución |
| --- | --- | --- |
| Probar firma | `signature_evidence`, PDF final, `receipt_seals`. | Verificar hash actual del archivo. |
| Probar acceso | `audit_log`, sesiones, logs de auth. | No exponer IP/user-agent innecesariamente. |
| Diagnosticar fallo | Logs técnicos, `signature_events`, `webhook_outbox`. | Redactar PII antes de compartir. |
| Investigar incidente | Audit chain, DB snapshots, backups, logs centralizados. | Activar legal hold. |
| Responder a cliente | Export de evidencia aprobado. | Validar permisos y jurisdicción. |

## 12. Verificabilidad externa y tamper evidence

La auditoría debe ser verificable por un tercero autorizado sin requerir confianza ciega en la aplicación. El objetivo es que cualquier modificación, eliminación o reordenamiento de eventos críticos sea detectable.

### 12.1 Hash por evento

Cada evento audit-crítico debe calcular un `event_hash` sobre una representación canónica del evento.

Reglas:

- Serializar JSON con orden estable de claves.
- Excluir `event_hash`, `previous_hash`, `chain_hash` y `batch_signature` del cálculo base.
- Incluir `event_type`, `occurred_at`, `organization_id`, `actor_type`, `actor_id`, `resource_type`, `resource_id`, `result` y `metadata` redactada.
- Usar SHA-256 o HMAC-SHA256 si se requiere autenticidad con secreto.

### 12.2 Encadenamiento

Cada evento debe incluir:

- `previous_hash`: `chain_hash` del evento anterior de la misma cadena.
- `chain_hash`: hash de `event_hash + previous_hash`.

Cadena recomendada:

- Cadena global para eventos de sistema.
- Cadena por organización para auditoría tenant.
- Cadena por recibo para reconstrucción legal de un documento.

El primer evento de cada cadena debe usar un valor genesis documentado, por ejemplo `GENESIS:{scope}:{scope_id}`.

### 12.3 Firma de lote o almacenamiento write-once

Para auditorías agresivas, se recomienda una capa adicional:

- Firma diaria de lote de logs con clave protegida en KMS/HSM.
- Export diario a almacenamiento append-only o write-once.
- Timestamp externo del lote si se requiere evidencia temporal robusta.
- Registro de manifest con conteo, rango de fechas, primer hash y último hash.

### 12.4 Procedimiento de verificación

Un auditor debe poder:

1. Exportar eventos de una organización, recibo o ventana temporal.
2. Recalcular `event_hash` de cada evento.
3. Recalcular `chain_hash` usando `previous_hash`.
4. Detectar gaps, reordenamientos o cambios de contenido.
5. Comparar último hash con manifest firmado o almacenamiento write-once si existe.
6. Registrar resultado de verificación como evidencia.

### 12.5 Declaración de límite

Hash chaining vuelve los logs tamper-evident, no tamper-proof. La resistencia fuerte requiere controles adicionales: permisos DB restrictivos, triggers append-only, backups, export externo, almacenamiento write-once y custodia independiente de llaves.
## 13. Correlación y Trazabilidad

Para permitir reconstrucciones forenses de operaciones complejas, cada evento de auditoría debe incluir:

- `request_id`: ID único de la petición HTTP (inyectado por middleware).
- `trace_id`: ID de la operación lógica (ej: un proceso de firma que genera múltiples eventos).

### Ejemplo JSON con correlación:

```json
{
  "timestamp": "2026-04-25T20:30:45Z",
  "level": "INFO",
  "logger": "dircom.payroll.encryption",
  "action": "document_encrypted",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "trace_id": "z9y8x7w6-v5u4-3210-fedc-ba0987654321",
  "data": {
    "file_id": "...",
    "purpose": "...",
    "kms_key_used": "..."
  }
}
```
