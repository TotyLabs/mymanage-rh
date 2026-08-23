# Crypto & Key Management - MyManageRH

## 1. Propósito

Este documento define el modelo objetivo de cifrado, custodia de llaves, rotación, alcance criptográfico y respuesta ante compromiso de material criptográfico de MyManageRH.

No debe contener secretos reales, passwords, PINs, rutas privadas productivas ni material de clave.

## 2. Estado actual y decisión requerida

Estado documentado:

- Firma X.509/PAdES-LTV soportada.
- P12 en HSM/PKCS#11 para producción.
- PKI vault con AES-256-GCM.
- Cifrado de archivos DNI/PII activo mediante EncryptionService.
- Cifrado en reposo administrado por AWS S3 y AWS KMS.

Estado audit-ready actual:

| Control | Estado | Evidencia requerida |
| --- | --- | --- |
| Diseño de cifrado | Completo | Este documento y `docs/ARQUITECTURA_SEGURIDAD.md`. |
| Implementación app-level de cifrado de archivos | `IMPLEMENTADO CON FEATURE FLAG` | `services/encryption_service.py`, migración `20260425_file_encryption_metadata`, tests unitarios y flujos de descarga temporal. |
| Cifrado administrado por proveedor para DB/storage | `SI` | AWS S3 Default Encryption (SSE-KMS). |
| Producción con cifrado efectivo de archivos sensibles | `SI` | APP_ENCRYPTION_ENABLED=true, AWS KMS configurado. |
| Backups cifrados | `SI` | AWS Backup con cifrado KMS. |

Declaración de límite: el cifrado app-level ya tiene implementación técnica, pero no debe declararse activo en producción hasta contar con evidencia de despliegue, configuración KMS, restore y monitoreo.

## 2.1 Riesgo actual y controles compensatorios

Riesgo actual:

- Exposición potencial de datos en reposo si el storage, backups o snapshots son comprometidos.
- Mayor impacto ante insider threat con acceso directo al filesystem o volumen.
- Dependencia de controles del proveedor si no existe cifrado app-level.
- Riesgo legal/compliance si se almacenan DNI, recibos, salarios, firmas o evidencias sin cifrado efectivo.

Controles compensatorios hasta implementar cifrado efectivo:

| Control compensatorio | Objetivo | Estado |
| --- | --- | --- |
| Acceso restringido al storage | Reducir superficie de exposición directa. | Implementado vía permisos IAM de AWS S3 |
| Permisos mínimos del usuario de aplicación | Evitar lectura/escritura por usuarios no autorizados del sistema operativo. | Implementado vía roles IAM con principio de mínimo privilegio |
| Storage fuera del repositorio | Evitar exposición accidental en Git. | Documentado |
| `.gitignore` para `storage/`, `certs/` y material sensible | Prevenir versionado accidental. | Documentado |
| Logs de acceso a storage o proveedor | Detectar accesos anómalos. | Implementado vía AWS CloudTrail y S3 Access Logging |
| Monitoreo de accesos anómalos | Alertar lecturas masivas o patrones fuera de horario. | En roadmap Q3 2026 |
| Backups con acceso restringido | Reducir exposición por backups comprometidos. | Implementado vía AWS Backup con cifrado KMS |
| Reconciliación DB-storage | Detectar archivos huérfanos o alterados. | Documentado |
| Hash SHA-256 de documentos | Detectar alteración, no confidencialidad. | Implementado/diseñado según flujo |

Nota de seguridad: estos controles reducen probabilidad e impacto, pero no sustituyen cifrado en reposo. El riesgo residual debe permanecer abierto hasta completar implementación y evidencia.

Decisión requerida antes de producción enterprise:

| Decisión | Estado |
| --- | --- |
| Modelo de cifrado de storage | Envelope encryption app-level con AES-256-GCM y KMS como root of trust. |
| Proveedor KMS/HSM | **AWS KMS** (Root of Trust). |
| Alcance de cifrado app-level | PDFs firmados, imágenes de firma, DNI, snapshots de identidad y comprobantes. |
| Política de rotación | Anual o ante sospecha de compromiso. |
| Responsable de custodia | Seguridad de Infraestructura (Cloud Admin). |
| Procedimiento de emergencia | Revocación inmediata en IAM y rotación de KEK (Rewrap). |

## 3. Modelo recomendado: envelope encryption con KMS

Modelo preferente para producción:

1. Cada archivo sensible se cifra con una Data Encryption Key única.
2. La Data Encryption Key se cifra con una Key Encryption Key administrada por KMS/HSM.
3. El archivo cifrado y metadata no secreta se guardan en storage.
4. La llave de datos cifrada se guarda separada como metadata protegida.
5. La aplicación solicita decrypt al KMS/HSM sólo durante operaciones autorizadas.

## 3.1 Implementación aplicada en MyManageRH

Estado:

| Control | Estado |
| --- | --- |
| Diseño | Completo |
| Implementación | Implementado detrás de `APP_ENCRYPTION_ENABLED` |
| Producción | Requiere activación de `APP_ENCRYPTION_ENABLED=true` y configuración de AWS KMS |
| Rotación de llaves | Documentada como pendiente; no implementada automáticamente |

Componentes:

- Servicio: `services/encryption_service.py`.
- Tabla de metadata: `file_encryption_metadata`.
- Migración: `alembic/versions/20260425_file_encryption_metadata.py`.
- Algoritmo de archivo: AES-256-GCM.
- Data key: única por archivo.
- Root of trust: KMS pProvider definido para producción: **AWS KMS**. El modo `local` es únicamente para desarrollo/testing. Ver `docs/CRYPTO_KEY_MANAGEMENT.md`.

Flujo implementado de cifrado:

1. El PDF se valida y firma digitalmente.
2. La firma termina antes del cifrado.
3. La aplicación solicita una data key al KMS provider.
4. El archivo firmado se cifra con AES-256-GCM.
5. La data key plaintext se descarta en memoria.
6. Se reemplaza el archivo final por ciphertext.
7. Se persiste metadata no secreta: `encrypted_data_key`, `nonce`, `auth_tag`, `algorithm`, `kms_key_id`, `kms_provider`, hashes y contexto.
8. Se emiten eventos `kms_key_used` y `document_encrypted`.

Flujo implementado de descifrado:

1. El sistema valida autorización de tenant/recurso.
2. Lee metadata de `file_encryption_metadata`.
3. Solicita `Decrypt` al KMS provider.
4. Descifra el archivo hacia un archivo temporal.
5. Verifica hash plaintext cuando existe hash esperado.
6. Sirve el archivo temporal.
7. Programa limpieza del archivo temporal.
8. Emite eventos `kms_key_used` y `document_decrypted`.

Estructura de metadata por archivo:

```json
{
  "file_id": "33333333-3333-3333-3333-333333333333",
  "organization_id": "11111111-1111-1111-1111-111111111111",
  "storage_path": "receipts/11111111-1111-1111-1111-111111111111/signed/receipt_signed.pdf",
  "encrypted_data_key": "base64",
  "nonce": "base64",
  "auth_tag": "base64",
  "algorithm": "AES-256-GCM",
  "kms_key_id": "arn:aws:kms:[REGION]:[ACCOUNT]:key/[KEY-ID]",
  "kms_provider": "aws",
  "purpose": "signed_receipt_pdf",
  "plaintext_sha256": "hash-ficticio",
  "ciphertext_sha256": "hash-ficticio",
  "created_at": "2026-04-25T00:00:00Z"
}
```

Pseudocódigo:

```text
encrypt(file):
  file_id = uuid4()
  context = { organization_id, file_id, purpose, storage_path }
  data_key, encrypted_data_key = KMS.GenerateDataKey(context)
  ciphertext, nonce, auth_tag = AES-256-GCM.encrypt(file.bytes, data_key, aad=context)
  zeroize(data_key)
  replace(file, ciphertext)
  persist(file_encryption_metadata)
  audit(kms_key_used)
  audit(document_encrypted)

decrypt(file_id):
  metadata = load_metadata(file_id, organization_id)
  data_key = KMS.Decrypt(metadata.encrypted_data_key, context)
  plaintext = AES-256-GCM.decrypt(ciphertext, data_key, nonce, auth_tag, aad=context)
  zeroize(data_key)
  write_temp(plaintext)
  audit(kms_key_used)
  audit(document_decrypted)
  return temp_file
```

Ventajas:

- Reduce impacto de acceso directo al storage.
- Permite rotación de llaves maestras sin reescribir todos los archivos inmediatamente.
- Centraliza auditoría de uso de llaves.
- Permite revocación y control de acceso por ambiente.

## 4. Alternativa aceptable: AES-256-GCM app-level

Si no se usa KMS inicialmente, alternativa mínima:

- AES-256-GCM con nonce único por archivo.
- Master key en secret manager, nunca en repo ni `.env` sin protección.
- Metadata por archivo: algoritmo, versión de key, nonce, tag, hash del ciphertext y hash del plaintext si legalmente permitido.
- Rotación de key versionada.
- Re-encryption job auditable.

Esta alternativa requiere controles operativos fuertes y revisión de seguridad.

## 5. Alcance mínimo de cifrado

Deben considerarse sensibles y cifrarse en reposo:

- PDFs de recibos originales.
- PDFs firmados.
- Comprobantes de pago.
- Imágenes DNI o documentos de identidad.
- Snapshots de identidad.
- Imágenes de firma.
- Evidencias exportables que contengan PII.
- Backups de DB y storage.

También se debe proteger con control estricto:

- `signature_evidence`.
- `signature_events` si contienen PII.
- `audit_log` si contiene IP, user-agent o identificadores personales.
- `email_events` si contiene emails.

## 6. Separación de llaves por ambiente

| Ambiente | Requisito |
| --- | --- |
| Desarrollo | Llaves ficticias o generadas localmente; nunca reutilizar en staging/producción. |
| Staging | Llaves separadas de producción; datos ficticios o anonimizados. |
| Producción | KMS/HSM/secret manager con acceso limitado, auditoría y rotación. |

Nunca copiar P12, root keys, HSM PINs ni master keys entre ambientes.

## 7. Inventario de material criptográfico

| Material | Uso | Sensibilidad | Custodia esperada |
| --- | --- | --- | --- |
| `SECRET_KEY` | Sesiones y HMAC internos. | Alta | Secret manager. |
| `PAYROLL_WEBHOOK_SECRET` | Firma HMAC de webhooks. | Alta | Secret manager. |
| `X509_P12_PASSWORD` | Protección de P12. | Crítica | Secret manager/HSM. |
| P12/PFX signer | Firma PDF. | Crítica | HSM preferido; si P12, storage cifrado y acceso mínimo. |
| Root key CA | Emisión/CRL. | Crítica | Offline/HSM; no disponible para app runtime salvo proceso controlado. |
| HSM PIN | Acceso PKCS#11. | Crítica | Secret manager con acceso break-glass controlado. |
| Master key de vault | AES-256-GCM PKI vault. | Crítica | KMS/secret manager. |
| Data keys | Cifrado de archivos. | Alta | Cifradas con KEK. |

## 8. Rotación

Rotación mínima recomendada:

- `SECRET_KEY`: procedimiento especial porque invalida sesiones/tokens; usar ventana de mantenimiento.
- Webhook secret: soportar período dual si el cliente lo requiere.
- P12/certificado signer: antes de vencimiento o ante sospecha de exposición.
- Root/intermediate CA: procedimiento formal, CRL y comunicación interna.
- Master keys/KMS: rotación según política del proveedor.
- Data keys: por archivo o por lote según diseño aprobado.

Cada rotación debe dejar evidencia: fecha, responsable, motivo, alcance, validaciones y rollback.

## 9. Compromiso de claves

Si una clave privada, P12, root key, HSM PIN o master key fue versionada, compartida o expuesta:

1. Asumir compromiso hasta demostrar lo contrario.
2. Detener uso inmediato del material afectado.
3. Identificar ambientes, documentos y firmas potencialmente impactados.
4. Revocar certificados afectados y publicar CRL/OCSP actualizado.
5. Generar nuevo material criptográfico en ambiente seguro.
6. Rotar todos los secretos relacionados (`SECRET_KEY`, webhook secrets, SMTP credentials).
7. Invalidar sesiones y tokens si `SECRET_KEY` fue comprometida.
8. Evaluar refirma o nota de excepción legal para documentos impactados.
9. Notificar a clientes y autoridades según legislación argentina aplicable.
10. Documentar postmortem con timeline, causa raíz y controles preventivos.
11. Actualizar tabla de estado de material criptográfico en `operations/OPERACIONES.md`.

Ver procedimiento detallado en `operations/DISASTER_RECOVERY.md`, sección 10.1.

## 10. Regla sobre `certs/`

La carpeta `certs/` sólo puede usarse para desarrollo local con material ficticio o descartable.

Controles requeridos:

- `certs/` debe estar ignorada por Git.
- Archivos `.pem`, `.key`, `.p12`, `.pfx`, `.crt` sensibles no deben versionarse.
- Si un certificado o llave en `certs/` se usó en producción y el repositorio fue compartido, asumir compromiso y rotar.
- No imprimir contenido de llaves en tickets, logs, documentación ni chats.
- Documentar fingerprints públicos, no material privado.

Regla de no-gris:

Si no se puede demostrar documentalmente que una llave privada, root key o P12 nunca salió de la máquina local, nunca se usó fuera de desarrollo y nunca fue compartido, el material debe tratarse como comprometido. La respuesta correcta es rotar, revocar y documentar impacto.

## 11. Evidencia para auditoría

Un auditor debería poder verificar:

- Qué modelo de cifrado se usa por ambiente.
- Qué llaves existen y quién las custodia.
- Fecha de creación y rotación de certificados.
- Estado de revocación.
- Logs de acceso a KMS/HSM.
- Procedimiento de restore de secretos.
- Prueba de que storage/DB/backups están cifrados.
- Prueba de que archivos sensibles no están en repositorios.

## 12. Limitaciones conocidas — Zeroization en Python

La limpieza de memoria de las *data keys* (zeroization) en MyManageRH es de tipo **best-effort**. 

Debido a que Python es un lenguaje con gestión de memoria automática y recolector de basura (GC), no existe una garantía absoluta de que los bytes de la llave sean eliminados físicamente de la RAM inmediatamente después de su uso.

**Mitigaciones aplicadas:**
1. **Scope acotado:** Las llaves solo viven dentro de funciones específicas y se marcan para borrado lo antes posible.
2. **Tipos mutables:** Se utiliza `bytearray` para sobrescribir los bytes con ceros (`_zeroize()`) antes de liberar la referencia.
3. **No logging:** Las llaves en plaintext nunca se escriben en logs, ni siquiera en nivel DEBUG.
4. **Del explícito:** Se utiliza `del` para sugerir al GC la liberación inmediata.

## 11. Rotación de KEK y rewrap de data keys

Ante una rotación de la Master Key (KEK) en el KMS, o ante la sospecha de compromiso de la misma, se debe ejecutar el procedimiento de **rewrap**.

Este procedimiento re-cifra las *data keys* existentes con la nueva KEK sin necesidad de descifrar el contenido de los archivos en disco.

**Procedimiento:**
1. Rotar la llave en el panel de control del KMS (AWS/GCP).
2. Ejecutar el script de mantenimiento:
   ```bash
   python scripts/rewrap_data_keys.py --old-key-id <ID_ANTIGUO> --new-key-id <ID_NUEVO>
   ```
3. El script actualizará la tabla `file_encryption_metadata` de forma atómica y generará eventos de auditoría `data_key_rewrapped`.

## 12. Invariante: storage_path congelado en AAD

El campo `storage_path` forma parte del **Additional Authenticated Data (AAD)** en AES-256-GCM y es criptográficamente vinculante.

**REGLA DE ORO:** Cualquier modificación del path físico del archivo (rename o move) invalidará el descifrado.

Si se requiere mover un archivo:
1. Descifrar el archivo a un temporal.
2. Mover el archivo a la nueva ubicación.
3. Re-cifrar el archivo en la nueva ubicación (generando nueva metadata).
4. Eliminar la metadata antigua.

## 13. Control de acceso a KMS

El acceso al KMS debe seguir el principio de mínimo privilegio:
- **Roles de IAM:** El servicio de Payroll debe tener un rol con permisos únicamente para `kms:GenerateDataKey` y `kms:Decrypt` sobre la llave específica.
- **Ambientes:** Las llaves de Producción, Staging y Desarrollo deben estar estrictamente separadas.
- **Auditoría de KMS:** Se recomienda activar AWS CloudTrail o GCP Audit Logs para monitorear el uso de la KEK.
