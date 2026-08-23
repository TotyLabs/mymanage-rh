# Seguridad y modelo de firmas - MyManageRH

## 1. Propósito

Este documento describe el modelo de firma de MyManageRH: firma visual, firma criptográfica X.509/PAdES-LTV, identidad del firmante, evidencia, sellos QR, fail-fast, validación de PDF, no repudio como objetivo probatorio y limitaciones.

No constituye asesoramiento legal. La validez contractual y probatoria debe revisarse según la legislación de la República Argentina (Ley 25.506 de Firma Digital, Ley 25.326 de Protección de Datos Personales) y el caso de uso del cliente.

## 2. Modelo de firma digital

MyManageRH implementa un modelo de firma por capas.

| Capa | Función | Evidencia asociada |
| --- | --- | --- |
| Autenticación | Usuario, sesión, token u OTP identifica al actor. | `user_id`, `employee_id`, `organization_id`, IP, user-agent, timestamps. |
| Firma visual | Representación visible en PDF. | Imagen/sello, hash de firma, posición, rol y sello QR. |
| Firma criptográfica | Firma X.509/PAdES-LTV sobre PDF si está configurada. | Certificado, fingerprint, TSA, validación OCSP/CRL, metadata PAdES. |
| Auditoría | Registro de eventos y cambios de estado. | `audit_log`, `signature_events`, `signature_evidence`, `receipt_seals`. |

## 3. Firma visual vs firma criptográfica

La firma visual es la marca visible insertada en el PDF. Puede incluir firma manuscrita capturada desde canvas o imagen PNG, sello de validación con nombre del firmante, rol, fecha y QR, sello del empleador o firmante de empresa y metadata interna del PDF para registrar `seal_id`.

La firma criptográfica se realiza mediante certificado X.509 y pyHanko cuando la configuración está disponible. El sistema contempla `.p12/.pfx` local o signer vía HSM/PKCS#11 si `HSM_ENABLED=true`, firma PDF con PAdES-LTV, TSA RFC 3161 mediante `TSA_URL`, CRL para validación offline y metadata de certificado.

La firma visual facilita lectura humana, pero por sí sola no equivale necesariamente a una firma criptográfica verificable.

## 4. PAdES-LTV

PAdES-LTV permite que un PDF firmado conserve material de validación a largo plazo, como cadena de certificados, CRL/OCSP y timestamp.

En MyManageRH:

- La firma se intenta con contexto de validación.
- Si falta contexto PKI confiable, el flujo criptográfico debe fallar en lugar de simular una firma válida.
- La metadata de resultado puede incluir `validation_status`, `ocsp_status`, `crl_status`, `tsa_timestamp`, `signature_algorithm`, `cert_serial` y `certificate_fingerprint`.

Pendiente: definir política final de revocación y aceptación de fallos de TSA. Producción usa AWS KMS como root of trust, HSM/PKCS#11 como signer y TSA RFC 3161 vía `TSA_URL`.

## 5. X.509, TSA, HSM y PKI

| Elemento | Descripción |
| --- | --- |
| Root CA | Certificado raíz publicado en `/pki/root_ca.crt` cuando aplica. |
| CRL | Lista de revocación publicada en `/pki/root_ca.crl`. |
| P12/PFX | Bundle local usado como signer si no se usa HSM. |
| HSM/PKCS#11 | Modo opcional para firmar sin exponer clave privada en disco. |
| TSA | Servicio RFC 3161 configurable mediante `TSA_URL`. |
| PKI vault | `pki_vault.py` usa AES-256-GCM para llaves versionadas bajo master key. |
| Fingerprint | Huella SHA-256 del certificado registrada como evidencia. |

Reglas operativas:

- `X509_P12_PASSWORD` es obligatorio en producción si se usa P12.
- Si `HSM_ENABLED=true`, `HSM_PIN` debe estar definido.
- No se deben versionar llaves privadas, P12 reales ni contraseñas.
- El certificado usado en ejemplos locales no debe reutilizarse para producción.

## 6. Fail-fast si falla la firma

El flujo de firma está diseñado para no cerrar un recibo como firmado si falla una etapa crítica.

Condiciones de fail-fast:

- PDF inexistente o alterado respecto del hash esperado.
- PDF excede tamaño o cantidad máxima de páginas.
- Imagen de firma inválida, demasiado pequeña o demasiado grande.
- Identidad mínima del firmante incompleta.
- Rol inválido para firma.
- Certificado P12 ausente cuando la firma X.509 es requerida.
- Contexto PKI/PAdES-LTV ausente cuando la política exige firma criptográfica.
- Error de escritura atómica o reemplazo del PDF final.

El sistema usa `processing_signature` para marcar el recibo durante procesamiento y luego limpiar el flag ante fallos. Las fallas pueden generar cuarentena forense de archivos parciales.

## 7. Sellos QR

Cada sello puede incluir un `seal_id` verificable mediante endpoint público:

```text
GET /api/receipts/v/{seal_id}
```

El sello QR apunta a una URL de verificación configurada por `BASE_PUBLIC_URL` y permite consultar estado del sello, documento asociado, organización, firmante, rol, timestamp y hash de integridad.

El QR no debe exponer datos salariales ni permitir descargar el recibo sin autorización.

## 8. Identidad del firmante

Para empleado, la identidad puede incluir `employee_id`, nombre completo, DNI/CUIL cuando corresponde, email, token o contexto OTP, IP y user-agent. Para empleador, puede incluir `organization_id`, usuario admin, firmante de empresa, CUIT y nombre de organización.

La documentación legal debe definir qué combinación de factores es suficiente para el uso contractual del cliente.

## 9. Snapshot de firma

El snapshot de firma puede incluir imagen capturada o sello aplicado, hash SHA-256, ubicación del archivo en storage controlado, metadata de rol, versión del motor y estado del PDF antes y después de firmar.

No se debe exponer la imagen de firma fuera de endpoints autorizados.

## 10. Snapshot de identidad

El snapshot de identidad debe preservar la información mínima necesaria para probar el acto de firma sin sobreexponer PII.

Campos recomendados:

- `signer_identity_hash`.
- Nombre completo si la política lo permite.
- DNI/CUIL enmascarado en logs y respuestas públicas.
- Email enmascarado en logs.
- `organization_id`, `employee_id`, `receipt_id`.
- IP y user-agent en evidencia privada, no pública.
- Timestamp de aceptación y timestamp TSA si existe.

## 11. No repudio

MyManageRH busca soportar no repudio mediante evidencia técnica, pero no debe afirmar no repudio absoluto sin revisión legal.

Controles que fortalecen la posición probatoria:

- Autenticación del usuario o token de firma.
- OTP y sesión temporal en el flujo de firma.
- Hash del PDF antes y después.
- Hash de firma visual.
- Firma X.509/PAdES-LTV si está configurada.
- Timestamp TSA si está disponible.
- Eventos append-only y triggers de inmutabilidad cuando están aplicados.
- Trazabilidad por organización, empleado, usuario, recibo y sello.

La suficiencia probatoria depende de la legislación de la República Argentina (Ley 25.506 y Ley 25.326), contrato, consentimiento, política de identidad y reglamentación laboral aplicable.

## 12. Validación de PDF

Controles observados:

- Validación de magic bytes `%PDF-` en carga crítica.
- Límite de tamaño mediante `MAX_FILE_SIZE`.
- Límite de páginas mediante `MAX_PDF_PAGES`.
- Cálculo SHA-256 por chunks.
- Rechazo de mutación si el hash esperado no coincide.
- Procesamiento con PyMuPDF, pikepdf y, opcionalmente, Ghostscript.
- Escrituras atómicas y reemplazo controlado.

Recomendaciones adicionales: ejecutar procesamiento PDF en sandbox, validar extensiones y magic bytes de todos los tipos de archivo, registrar versión del motor de firma y mantener librerías críticas actualizadas.

## 13. Limitaciones y supuestos

| Área | Limitación o supuesto |
| --- | --- |
| Cifrado de DNI | `file_processing/security.py` contiene placeholder; producción debe implementar cifrado real o storage cifrado. |
| Jurisdicción | Validez legal bajo legislación argentina (Ley 25.506 / Ley 25.326). Revisada por asesoría legal. |
| TSA | Proveedor RFC 3161 configurable vía `TSA_URL`. Política de fallback: fail-fast si firma criptográfica es requerida. |
| HSM/KMS | Producción usa HSM/PKCS#11 como signer y AWS KMS como root of trust para cifrado. |
| RLS | Scripts disponibles; confirmar aplicación real en cada DB. |
| Certificados locales | No usar certificados de desarrollo en producción. |
| Firma visual | No sustituye por sí sola a firma criptográfica validable. |
| QR público | Debe limitar datos expuestos para evitar filtración de PII. |
