# API Reference - MyManageRH

## 1. Propósito

Este documento describe las convenciones y endpoints principales de la API de MyManageRH para integradores, equipos internos y auditores. Los ejemplos usan datos ficticios.

## 2. Convenciones de API

| Convención | Descripción |
| --- | --- |
| Base local | `http://localhost:8000` en desarrollo. |
| Base producción | `https://api.mymanagerh.com` (o URL provista al cliente). |
| Formato | JSON para requests/responses, salvo uploads `multipart/form-data` y descargas. |
| Fechas | ISO 8601 con zona horaria cuando aplique. |
| Identificadores | UUID string para organizaciones, empleados, recibos y documentos. |
| Errores | `detail` con código legible, sin stack traces ni secretos. |
| CSRF | En producción, requests mutables bajo `/api/` deben enviar `X-Requested-With`. |

## 3. Autenticación

La API soporta cookie de sesión `session` con `HttpOnly`, `SameSite=Strict` y `Secure` en producción, header `Authorization: Bearer <token>` cuando no existe cookie y tokens específicos para endpoints `/sign/{token}`.

### 3.1 Login

`POST /api/auth/login`

```json
{
  "username": "ana.rrhh@example.test",
  "password": "ContraseñaFicticia123!"
}
```

```json
{
  "status": "success",
  "user": {
    "id": "11111111-1111-4111-8111-111111111111",
    "email": "ana.rrhh@example.test",
    "role": "admin",
    "full_name": "Ana Pérez",
    "user_status": "active"
  }
}
```

Notas: el sistema registra intentos fallidos, puede bloquear temporalmente la cuenta e invalida sesiones previas al iniciar sesión correctamente.

## 4. Roles

| Rol | Uso |
| --- | --- |
| `admin` | Empleador/RRHH. Administra organización, empleados, recibos, firmantes y documentos. |
| `employee` | Empleado. Consulta y firma sus propios recibos. |
| `system` | Actor interno para eventos automáticos, jobs y webhooks. |

## 5. Endpoints principales

### 5.1 Autenticación

| Método | Endpoint | Descripción | Rol |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register` | Alta de organización y administrador. | Público controlado |
| `POST` | `/api/auth/register-employee` | Registro de empleado. | Público/controlado |
| `POST` | `/api/auth/register-lightweight` | Registro liviano. | Público/controlado |
| `POST` | `/api/auth/login` | Inicio de sesión. | Público |
| `POST` | `/api/auth/logout` | Cierre de sesión. | Autenticado |
| `GET` | `/api/auth/me` | Usuario actual. | Autenticado |
| `POST` | `/api/auth/forgot-password` | Solicitud de recuperación. | Público |
| `POST` | `/api/auth/reset-password` | Cambio con token de recuperación. | Público |

### 5.2 Recibos

| Método | Endpoint | Descripción | Rol |
| --- | --- | --- | --- |
| `POST` | `/api/batches/upload` | Carga lote PDF. | Admin |
| `GET` | `/api/receipts/summary` | Resumen de recibos. | Admin |
| `GET` | `/api/receipts/pending` | Recibos pendientes del usuario o empleado. | Autenticado |
| `GET` | `/api/receipts/history` | Historial de recibos de organización. | Admin |
| `GET` | `/api/receipts/employee/{employee_id}` | Recibos por empleado. | Autenticado con autorización |
| `GET` | `/api/receipts/my-history` | Historial propio del empleado. | Empleado |
| `GET` | `/api/receipts/pending-match` | Recibos sin matching automático. | Admin |
| `GET` | `/api/receipts/{receipt_id}/download` | Descarga de recibo. | Autenticado con autorización |
| `DELETE` | `/api/receipts/{receipt_id}` | Eliminación controlada si no viola reglas de integridad. | Admin |
| `POST` | `/api/receipts/bulk-delete` | Eliminación masiva controlada. | Admin |
| `POST` | `/api/receipts/{receipt_id}/payment-receipt` | Adjunta comprobante de pago. | Admin |
| `GET` | `/api/receipts/{receipt_id}/payment-receipt` | Descarga comprobante de pago. | Autenticado con autorización |
| `GET` | `/api/receipts/v/{seal_id}` | Verificación pública de sello QR. | Público |

### 5.3 Firma

| Método | Endpoint | Descripción | Rol |
| --- | --- | --- | --- |
| `POST` | `/api/receipts/{receipt_id}/sign-employer` | Firma del empleador. | Admin |
| `POST` | `/api/receipts/bulk-sign-employer` | Firma del empleador en lote. | Admin |
| `POST` | `/api/receipts/{receipt_id}/token` | Genera token de firma para empleado. | Admin |
| `POST` | `/api/receipts/{receipt_id}/token/me` | Genera token para el propio usuario cuando está permitido. | Autenticado |
| `GET` | `/sign/{token}` | Página de firma. | Token |
| `GET` | `/sign/{token}/info` | Metadata segura del flujo de firma. | Token |
| `POST` | `/sign/{token}/send-otp` | Envía OTP de verificación. | Token |
| `POST` | `/sign/{token}/verify-otp` | Verifica OTP y crea sesión temporal. | Token + OTP |
| `GET` | `/sign/{token}/verify-email` | Verificación por email cuando aplica. | Token |
| `GET` | `/sign/{token}/view` | Visualización del PDF a firmar. | Autenticado o token validado |
| `POST` | `/sign/{token}/accept` | Acepta y firma. | Token validado |
| `POST` | `/sign/{token}/reject` | Rechaza firma. | Token validado |

### 5.4 Firmas guardadas y firmantes

| Método | Endpoint | Descripción | Rol |
| --- | --- | --- | --- |
| `GET` | `/api/signatures/user/me` | Firma guardada del usuario. | Autenticado |
| `POST` | `/api/signatures/user/save` | Guarda firma visual del usuario. | Autenticado |
| `GET` | `/api/signatures/user/image` | Descarga imagen de firma propia. | Autenticado |
| `GET` | `/api/signatures/receipt/{receipt_id}/image` | Imagen de firma asociada a recibo. | Autenticado con autorización |
| `GET` | `/api/company-signers` | Lista firmantes de empresa. | Admin |
| `POST` | `/api/company-signers` | Crea firmante de empresa. | Admin |
| `DELETE` | `/api/company-signers/{signer_id}` | Elimina o desactiva firmante. | Admin |
| `POST` | `/api/company-signers/{signer_id}/toggle` | Activa/desactiva firmante. | Admin |
| `GET` | `/api/company-signers/{signer_id}/image` | Imagen del firmante. | Admin |

### 5.5 Empleados y legajo

| Método | Endpoint | Descripción | Rol |
| --- | --- | --- | --- |
| `GET` | `/api/employees` | Lista empleados de la organización. | Admin |
| `POST` | `/api/employees` | Crea empleado. | Admin |
| `GET` | `/api/employees/{employee_id}` | Consulta empleado. | Autenticado con autorización |
| `PATCH` | `/api/employees/{employee_id}` | Actualiza empleado. | Admin |
| `DELETE` | `/api/employees/{employee_id}` | Baja controlada. | Admin |
| `POST` | `/api/employees/bulk-import` | Importación masiva. | Admin |
| `POST` | `/api/employees/bulk-delete` | Baja masiva controlada. | Admin |
| `GET` | `/api/employees/pending-verification/list` | Empleados pendientes de verificación. | Admin |
| `POST` | `/api/employees/{employee_id}/verify-and-activate` | Verifica y activa empleado. | Admin |
| `POST` | `/api/employees/{employee_id}/dni-upload` | Carga imagen DNI. | Admin |
| `GET` | `/api/employees/{employee_id}/dni-image` | Consulta imagen DNI. | Admin |
| `GET` | `/api/employees/{emp_id}/record-pdf` | Genera PDF de legajo. | Autenticado con autorización |
| `POST` | `/api/legajo/preview` | Previsualiza importación de legajo. | Autenticado |
| `POST` | `/api/legajo/execute` | Ejecuta importación. | Autenticado |
| `GET` | `/api/legajo/export` | Exporta legajo. | Autenticado |

### 5.6 Administración, documentos, auditoría y PKI

| Método | Endpoint | Descripción | Rol |
| --- | --- | --- | --- |
| `POST` | `/api/admin/upload-employer-signature` | Carga firma del empleador. | Admin |
| `POST` | `/api/admin/upload-logo` | Carga logo. | Admin |
| `GET` | `/api/admin/logo` | Obtiene logo. | Admin |
| `GET` | `/api/admin/organization` | Datos de organización. | Admin |
| `PATCH` | `/api/admin/organization` | Actualiza organización. | Admin |
| `GET` | `/api/documents/list` | Lista documentos no payroll. | Admin |
| `GET` | `/api/documents/{document_id}/download` | Descarga documento con verificación hash. | Admin |
| `POST` | `/api/documents/{document_id}/archive` | Archiva documento. | Admin |
| `POST` | `/api/documents/{document_id}/restore` | Restaura documento. | Admin |
| `DELETE` | `/api/documents/{document_id}` | Elimina según lifecycle. | Admin |
| `GET` | `/api/audit/{document_id}` | Consulta evidencia/auditoría. | Autenticado |
| `GET` | `/api/audit/{verification_id}/pdf` | Descarga evidencia PDF. | Autenticado |
| `GET` | `/pki/root_ca.crt` | Certificado público root CA. | Público |
| `GET` | `/pki/root_ca.crl` | Lista CRL pública. | Público |
| `GET/POST` | `/pki/ocsp` | Endpoint OCSP o servicio PKI. | Público |
| `GET` | `/health` | Liveness. | Público/controlado |
| `GET` | `/health/deep` | Readiness y métricas básicas. | Operaciones |

## 6. Rate limits observados

| Endpoint o grupo | Límite observado |
| --- | --- |
| `/api/auth/login` | `5/minute` |
| `/sign/{token}` | `30/minute` |
| `/sign/{token}/info` | `20/minute` |
| `/sign/{token}/send-otp` | `3/minute` |
| `/sign/{token}/verify-otp` | `5/minute` |
| `/sign/{token}/verify-email` | `20/minute` |
| `/sign/{token}/view` | `15/minute` |
| `/sign/{token}/accept` | `5/minute` |
| `/sign/{token}/reject` | `5/minute` |

Confirmar límites finales por ambiente y documentar overrides si se agregan variables específicas.

## 7. Ejemplos ficticios

### 7.1 Carga de lote PDF

`POST /api/batches/upload`

```text
period_label=2026-03
file=@recibos_demo.pdf
```

```json
{
  "status": "ok",
  "batch_id": "22222222-2222-4222-8222-222222222222",
  "processed_pages": 24,
  "matched_receipts": 22,
  "pending_match": 2
}
```

### 7.2 Firma del empleador

`POST /api/receipts/33333333-3333-4333-8333-333333333333/sign-employer`

```json
{
  "company_signer_id": "44444444-4444-4444-8444-444444444444"
}
```

```json
{
  "status": "ok",
  "signed_at": "2026-04-25T14:30:00Z",
  "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "employee_email": "empleado@example.test",
  "employee_name": "Juan Demo"
}
```

### 7.3 Aceptación de firma del empleado

`POST /sign/tkn_demo_123/accept`

```json
{
  "signature_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA...",
  "acceptance_text": "Declaro haber revisado el recibo ficticio y aceptar su firma digital.",
  "identity_snapshot": {
    "document_type": "DNI",
    "document_number_last4": "1234"
  }
}
```

```json
{
  "status": "signed",
  "receipt_id": "33333333-3333-4333-8333-333333333333",
  "verification_id": "verif_demo_20260425_001",
  "seal_id": "AB12CD34EF56AB78",
  "signed_at": "2026-04-25T14:40:00Z"
}
```

### 7.4 Verificación pública de sello

`GET /api/receipts/v/AB12CD34EF56AB78`

```json
{
  "status": "valid",
  "seal_id": "AB12CD34EF56AB78",
  "document_id": "33333333-3333-4333-8333-333333333333",
  "organization": "Empresa Demo S.A.",
  "signer": {
    "name": "Juan Demo",
    "dni": "********",
    "role": "employee"
  },
  "timestamp": "2026-04-25T14:40:00Z",
  "integrity_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
```

## 8. Errores comunes

| HTTP | Código/Detalle | Significado |
| --- | --- | --- |
| `400` | `invalid_pdf_format` | El archivo no parece PDF válido por magic bytes. |
| `400` | `invalid_signature_format` | Firma visual no cumple formato esperado. |
| `400` | `malformed_signature_data_url` | Data URL de firma no se pudo decodificar. |
| `401` | `not_authenticated` | No hay sesión o bearer token válido. |
| `401` | `credenciales_invalidas` | Usuario/clave inválidos. |
| `403` | `admin_required` | El endpoint requiere rol administrador. |
| `403` | `csrf_protection_triggered` | Falta header requerido en request mutable de producción. |
| `403` | `cuenta_bloqueada_temporalmente_por_multiples_intentos` | Bloqueo por fuerza bruta. |
| `404` | `receipt_not_found` | Recibo inexistente o fuera del alcance del usuario. |
| `404` | `seal_not_found` | Sello QR no existe. |
| `409` | `receipt_busy` o estado inválido | Recibo bloqueado o transición no permitida. |
| `410` | `token_expired` | Token vencido. |
| `413` | `file_too_large` | Archivo supera límite configurado. |
| `422` | validación Pydantic | Payload incompleto o inválido. |
| `429` | rate limit | Exceso de requests. |
| `500` | `error_al_firmar_recibo_empresa` | Falla interna no expuesta al usuario. |

## 9. Consideraciones de seguridad

- No registrar tokens, cookies, firmas base64, documentos ni payloads completos con PII.
- Usar HTTPS/TLS 1.2 o 1.3 en producción.
- Validar `X-Webhook-Signature` con secreto compartido si se consumen webhooks.
- Tratar `seal_id` como identificador verificable, no como autorización de descarga.
- Mantener `PAYROLL_WEBHOOK_SECRET`, `SECRET_KEY`, `X509_P12_PASSWORD`, `HSM_PIN` y credenciales SMTP fuera del código fuente.
- Respetar límites de rate limiting y backoff en integraciones.
- Usar IDs de organización/empleado/recibo sólo del tenant autorizado.
- No depender de endpoints públicos para obtener PII completa.
