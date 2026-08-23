# Integridad y auditoría - MyManageRH

## 1. Propósito

Este documento define cómo MyManageRH preserva integridad documental, trazabilidad de acciones, evidencia de firma y reconstrucción del ciclo de vida de un recibo.

## 2. Principios de integridad

| Principio | Aplicación en el sistema |
| --- | --- |
| Trazabilidad | Cada acción relevante debe vincular actor, organización, recurso y timestamp. |
| Integridad criptográfica | PDFs y firmas se referencian por hashes SHA-256. |
| Inmutabilidad lógica | Recibos firmados, evidencia y eventos críticos no deben modificarse ni eliminarse físicamente. |
| Mínimo dato necesario | Logs y respuestas públicas deben redactar PII. |
| Separación tenant | Cada acción y consulta debe estar acotada por organización. |
| Reproducibilidad | Un auditor debe reconstruir la secuencia desde carga hasta firma final. |

## 3. Audit trail

| Fuente | Contenido |
| --- | --- |
| `audit_log` | Acciones transversales de usuarios y sistema. |
| `signature_events` | Eventos específicos de firma, hashes antes/después y metadata. |
| `signature_evidence` | Evidencia legal/técnica del acto de firma. |
| `receipt_seals` | Sellos QR verificables e integridad del recibo. |
| `email_events` | Envíos, aperturas, fallos y eventos de email. |
| `webhook_outbox` | Eventos de integración, reintentos y dead-letter. |
| Logs de aplicación | Diagnóstico operativo con redacción de PII. |

## 4. Eventos de firma

Eventos mínimos recomendados:

- `RECEIPT_UPLOADED`.
- `RECEIPT_MATCHED`.
- `RECEIPT_MATCH_FAILED`.
- `EMPLOYER_SIGNATURE_STARTED`.
- `EMPLOYER_SIGNATURE_COMPLETED`.
- `EMPLOYER_SIGNATURE_FAILED`.
- `SIGNATURE_REQUEST_CREATED`.
- `SIGNATURE_EMAIL_SENT`.
- `SIGNATURE_OTP_SENT`.
- `SIGNATURE_OTP_VERIFIED`.
- `EMPLOYEE_SIGNATURE_STARTED`.
- `DOCUMENT_SIGNED_X509`.
- `EMPLOYEE_SIGNATURE_COMPLETED`.
- `SIGNATURE_REJECTED`.
- `SIGNATURE_TOKEN_EXPIRED`.
- `DOCUMENT_LOCKED`.

## 5. Evidencia de firma

La evidencia debe responder quién firmó, en nombre de qué organización, qué recibo firmó, qué versión del PDF firmó, cuándo firmó, desde dónde firmó, con qué método y qué certificado, sello o token estuvo asociado.

| Campo | Uso |
| --- | --- |
| `receipt_id` | Recibo firmado. |
| `organization_id` | Tenant/empleador. |
| `employee_id` | Empleado asociado. |
| `actor_id` | Usuario que ejecuta acción cuando aplica. |
| `actor_type` | `admin`, `employee` o `system`. |
| `ip_address` | Origen de la acción. |
| `user_agent` | Cliente o navegador. |
| `receipt_sha256_at_sign_time` | Hash del PDF antes o durante firma. |
| `final_pdf_sha256` | Hash final del PDF firmado. |
| `signature_image_sha256` | Hash de firma visual cuando existe. |
| `certificate_fingerprint` | Fingerprint X.509 si se firmó criptográficamente. |
| `tsa_timestamp` | Timestamp TSA si existe. |
| `verification_id` | ID de verificación o evidencia. |
| `seal_id` | Sello QR cuando aplica. |

## 6. Inmutabilidad

La inmutabilidad se implementa por capas:

- Estados terminales (`signed`, `rejected`) para impedir transiciones indebidas.
- `document_locked=true` para documentos finalizados.
- Triggers de base de datos para impedir updates/deletes sobre tablas críticas cuando están aplicados.
- Hash chain en `audit_log` mediante `previous_hash` y `chain_hash` en migraciones de hardening.
- Soft delete en lugar de eliminación física para entidades sensibles.

Operaciones debe confirmar que migraciones y scripts de inmutabilidad están aplicados en cada ambiente productivo.

## 7. Protección contra alteraciones

- SHA-256 de PDF original y final.
- Validación de hash antes de mutar un PDF.
- Escrituras atómicas en storage.
- Cuarentena de archivos parciales ante fallos de firma.
- Triggers `protect_audit_log`, `protect_signature_evidence`, `protect_signature_events` y protecciones de recibos firmados si están aplicados.
- Logs con hashes enmascarados cuando corresponde.
- Endpoint público de sello que verifica contra `receipt_seals`.

## 8. Trazabilidad por usuario, organización y recibo

| Clave | Uso |
| --- | --- |
| `organization_id` | Aislamiento tenant. |
| `user_id` | Usuario autenticado. |
| `employee_id` | Empleado receptor del recibo. |
| `receipt_id` | Documento central de payroll. |
| `batch_id` | Lote de carga que originó el recibo. |
| `signature_request_id` | Solicitud/token de firma. |
| `verification_id` | Identificador de verificación de evidencia. |
| `seal_id` | Identificador público del sello QR. |
| `chain_hash` | Verificación de cadena de audit log. |

## 9. Retención de evidencia

Política definida:

Retención base:

- Recibos y evidencia de firma: 5 a 10 años según normativa laboral argentina.
- Logs técnicos y de debugging: 1 año.
- Logs de incidentes: preservar hasta cierre legal/compliance.
- Separar retención de PII, documentos salariales, certificados y logs de debugging.
- Documentar procedimientos de eliminación segura al terminar contrato.
- Preservar evidencia congelada ante disputa, auditoría o incidente.

## 10. Casos de auditoría

### 10.1 Recibo firmado correctamente

Verificar que el recibo pertenece a la organización correcta, tiene estado `signed` y `document_locked=true`, el hash final coincide con storage, existen eventos de firma de empleador y empleado, existe evidencia con IP/user-agent/timestamp/hash, la metadata X.509 se registró si corresponde y el `seal_id` público devuelve estado válido.

### 10.2 Recibo rechazado

Verificar evento `SIGNATURE_REJECTED`, actor, motivo si fue provisto, timestamp, IP, estado terminal `rejected` y ausencia de cierre posterior como `signed`.

### 10.3 Recibo alterado fuera del sistema

Señales esperadas: hash actual no coincide con DB, descarga o firma falla por integridad, aparece `INTEGRITY_VIOLATION` o equivalente y no se actualiza evidencia final como válida.

### 10.4 Falla de firma criptográfica

Verificar error de X.509, TSA, P12, HSM o contexto PKI, limpieza de `processing_signature`, recibo no marcado como firmado si la firma era requerida, cuarentena si aplica y log de falla.

## 11. Reconstrucción del ciclo de vida de un recibo

1. Buscar el recibo por `receipt_id`, `verification_id` o `seal_id`.
2. Confirmar `organization_id` y empleado asociado.
3. Obtener `batch_id` y metadata de carga.
4. Revisar hashes de PDF original y final.
5. Consultar `signature_requests` para token, expiración, estado y empleado.
6. Consultar `signature_events` ordenado por `created_at`.
7. Consultar `signature_evidence` por recibo o verificación.
8. Consultar `receipt_seals` para sellos aplicados.
9. Revisar `audit_log` por `organization_id`, `entity_id` y acción.
10. Validar cadena de `audit_log` si `previous_hash` y `chain_hash` están habilitados.
11. Verificar storage físico y hash del archivo actual.
12. Exportar evidencia según procedimiento aprobado.

## 12. Responsabilidades

| Responsable | Responsabilidad |
| --- | --- |
| Operaciones | Ejecutar backups, health checks, monitoreo de storage, webhooks y locks. |
| Seguridad | Revisar logs, incidentes, secretos, PKI, RLS y cifrado. |
| Legal/Compliance | Definir retención, acceso a evidencia y uso contractual. |
| RRHH cliente | Validar datos, empleados y firmas antes de cerrar procesos. |
