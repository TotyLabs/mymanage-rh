# Arquitectura de seguridad - MyManageRH

## 1. Objetivo de seguridad

El objetivo de seguridad de MyManageRH es proteger datos laborales sensibles, recibos de sueldo, firmas, identidad del firmante y evidencia de auditoría en un entorno SaaS B2B multi-tenant.

Este documento es técnico. No es material de marketing y no afirma cumplimiento legal absoluto.

## 2. Modelo de amenazas

| Amenaza | Riesgo | Controles actuales o requeridos |
| --- | --- | --- |
| Acceso no autorizado a recibos | Exposición de salarios y PII. | Auth, roles, scoping por organización, RLS si aplica, storage seguro. |
| Cross-tenant data leak | Un cliente accede a datos de otro. | `organization_id`, filtros por tenant, path por organización, RLS preparado. |
| Robo de sesión | Suplantación de usuario. | Cookies HTTP-only, SameSite, Secure en producción, invalidación de sesiones previas. |
| Fuerza bruta de login | Toma de cuenta. | Rate limit, contador de intentos fallidos, lock temporal. |
| Reuso o filtración de token de firma | Firma no autorizada. | Token hasheado, TTL, OTP, rate limits y validación de contexto. |
| Alteración de PDF en storage | Evidencia inválida. | SHA-256, verificación antes de mutar, hashes finales y eventos. |
| Ejecución arbitraria vía archivo | Compromiso del host. | Validación de tipo/tamaño, magic bytes, sandboxing recomendado. |
| Fuga de secretos | Compromiso de firmas, sesiones o SMTP. | Variables de entorno, no hardcode, no logs de secretos, rotación. |
| Manipulación de auditoría | Pérdida de trazabilidad. | Triggers de inmutabilidad, hash chain y permisos DB si aplicados. |
| Webhook abuse | Reintentos, replay o payload falsificado. | HMAC, idempotency key, backoff, dead-letter. |

## 3. Límites del sistema

| Límite | Descripción |
| --- | --- |
| Usuario final | Navegador del empleado o administrador. No es confiable. |
| API pública | FastAPI expone endpoints autenticados, de firma por token y públicos limitados. |
| Base de datos | Fuente de verdad para estados, usuarios, auditoría y evidencia. |
| Storage | Guarda PDFs, firmas, logos, importaciones e identidad. Debe tratarse como sensible. |
| PKI/TSA/HSM | Boundary criptográfico. Su configuración define nivel de confianza. |
| Email/SMS | Canales de notificación y OTP. No deben transportar documentos sensibles sin control. |
| Webhook externo | Sistema del cliente. Debe validar firma HMAC e idempotencia. |

## 4. Aislamiento de procesamiento de archivos

Archivos procesados: PDF de recibos, imágenes de firma y logos, imágenes de DNI, Excel/legajo y ZIP generados on-demand.

Controles observados:

- Límites de tamaño por tipo de archivo.
- Validación MIME best-effort.
- Validación magic bytes para PDF en flujos críticos.
- Validación magic bytes PNG para preparación de firma.
- Optimización PDF con Ghostscript y pikepdf cuando están disponibles.
- Escritura atómica y limpieza de temporales.

Requisito de hardening: ejecutar procesamiento de archivos en un usuario sin privilegios y preferentemente en sandbox/contenedor con filesystem y red restringidos.

## 5. Sandboxing o diseño preparado para sandboxing

El diseño separa procesamiento de archivo en `file_processing`, `modules/signature` y `services/x509_service`, lo que permite mover esa ejecución a un sandbox dedicado.

Recomendaciones:

- Contenedor sin privilegios para procesamiento PDF.
- Directorio temporal aislado por job.
- Límite de CPU, memoria y tiempo.
- Sin acceso a secretos salvo los estrictamente requeridos.
- Sin acceso de red excepto TSA/OCSP/CRL cuando se firme criptográficamente.
- Eliminación segura de temporales al finalizar.

## 6. Prevención de ejecución arbitraria

El sistema no ejecuta código provisto por usuarios. Sin embargo, procesa archivos complejos mediante librerías y herramientas externas.

Controles requeridos:

- No abrir macros ni ejecutar contenido embebido de Office.
- Tratar PDF como contenido no confiable.
- Validar extensión y magic bytes.
- Limitar páginas, tamaño y tiempo de procesamiento.
- Mantener PyMuPDF, pikepdf, Ghostscript y pyHanko actualizados.
- Usar sandbox para reducir impacto de CVEs de parsers.

## 7. Manejo seguro de archivos temporales

- Crear temporales dentro del directorio destino o un temp controlado.
- Usar nombres aleatorios.
- Cerrar file descriptors antes de reemplazar.
- Reemplazar con operación atómica.
- Limpiar temporales en `finally` o background task.
- No registrar rutas privadas completas en logs de usuario.
- Mover fallos de firma a cuarentena forense si se necesita análisis.

## 8. Validación de extensiones y magic bytes

| Tipo | Validación observada | Gap |
| --- | --- | --- |
| PDF | Magic bytes `%PDF-`, tamaño, páginas. | Agregar validación estructural uniforme antes de todo procesamiento. |
| Firma PNG | Magic bytes PNG en preparación de imagen. | Validar JPEG/WebP si se aceptan. |
| Logo | MIME best-effort. | Validar magic bytes y sanitizar SVG si se acepta. |
| DNI | MIME best-effort y cifrado app-level al persistir. | Agregar validación estricta de magic bytes para JPEG/PNG. |
| Excel | MIME best-effort. | Validar extensión, magic bytes ZIP/OLE y bloquear macros si aplica. |

## 9. Cifrado en tránsito

Producción debe usar TLS 1.2 o TLS 1.3.

Requisitos:

- HTTPS obligatorio para UI/API pública.
- Cookies `Secure` en producción.
- HSTS si se opera bajo dominio propio.
- Certificados administrados por AWS Certificate Manager.
- Webhooks salientes únicamente hacia endpoints HTTPS salvo excepción documentada.

## 10. Cifrado en reposo

Estado observado:

- `pki_vault.py` implementa AES-256-GCM para llaves PKI versionadas bajo master key.
- `services/encryption_service.py` implementa envelope encryption app-level para archivos sensibles con AES-256-GCM.
- `file_processing/security.py` queda como placeholder legado; el cifrado efectivo se aplica en los bordes de persistencia/descarga.
- El cifrado general de storage administrado por proveedor depende de AWS S3 y AWS KMS.

Requisito enterprise: activar `APP_ENCRYPTION_ENABLED=true`, configurar KMS real, aplicar migración `file_encryption_metadata`, activar cifrado en reposo AES-256 o equivalente para DB/backups/storage y documentar rotación, custodia y recuperación de llaves.

Decisión de arquitectura adoptada para archivos sensibles: envelope encryption app-level con data key por archivo y AES-256-GCM.

Provider definido para producción: **AWS KMS**. El modo `local` es únicamente para desarrollo/testing. Ver `docs/CRYPTO_KEY_MANAGEMENT.md`.

Alcance mínimo que debe quedar cubierto antes de operar datos reales enterprise:

- PDFs originales de recibos.
- PDFs firmados.
- Comprobantes de pago.
- Imágenes DNI y documentos de identidad.
- Snapshots de identidad.
- Imágenes de firma.
- Evidencia exportable con PII.
- Backups de DB y storage.

Alcance implementado por aplicación:

- PDFs firmados después de firma digital y antes del storage final.
- Imágenes de evidencia de firma generadas durante el flujo de firma.
- Imágenes de DNI al finalizar OCR/procesamiento local.
- Comprobantes de pago cargados por RRHH.
- Documentos corporativos gestionados por `DocumentService`.

Fuera de alcance actual del cifrado app-level:

- Logs.
- Metadata no sensible.
- Campos PII persistidos en base de datos.
- Backups completos del proveedor, que deben cifrarse mediante controles de infraestructura.

## 11. Gestión de secretos

Secretos críticos: `SECRET_KEY`, `DATABASE_URL`, `SMTP_PASSWORD`, `PAYROLL_WEBHOOK_SECRET`, `X509_P12_PASSWORD`, `HSM_PIN`, credenciales Twilio y master key de PKI vault.

Reglas:

- No versionar `.env` real.
- No imprimir secretos en logs.
- Usar secret manager o variables protegidas en producción.
- Rotar secretos ante sospecha de exposición.
- Separar secretos por ambiente.
- No reutilizar `SECRET_KEY` para otros propósitos.

## 12. Control de acceso

Controles observados: roles `admin` y `employee`, dependencias `require_auth` y `require_admin`, sesión por cookie o bearer token, inyección de contexto RLS `app.current_org_id`, endpoints públicos limitados.

Requisitos adicionales: MFA para administradores (en roadmap), RBAC granular definido en `models/tables.py`, revisión periódica de usuarios activos y registro de accesos administrativos a documentos sensibles.

## 13. Multi-tenancy

Aislamiento por `organization_id`, `company_id` en `receipts`, storage con carpeta por organización, query scoping, unique constraints por organización y RLS preparado.

Validaciones obligatorias por release:

- Un admin de organización A no puede listar empleados de organización B.
- Un empleado sólo ve recibos propios.
- Una URL pública de sello no descarga PDFs ni expone salario.
- Una firma por token no permite cambiar `receipt_id` u organización.

## 14. Row Level Security si aplica

Existen scripts `scripts/setup_rls.sql` que habilitan RLS en tablas core y crean políticas por `app.current_org_id`.

Condiciones para declararlo activo:

- Script aplicado en base de datos productiva.
- Usuario de aplicación no tiene bypass RLS.
- `FORCE ROW LEVEL SECURITY` aplicado donde corresponda.
- Pruebas de aislamiento ejecutadas y registradas.

Estado documental: RLS Activo en Staging y Producción.

Estado de implementación requerido:

| Ambiente | RLS aplicado | Validación cruzada tenant | Fecha de última prueba | Responsable |
| --- | --- | --- | --- | --- |
| Desarrollo | `NO` | `NO` | `N/A` | `Dev Team` |
| Staging | `SI` | `SI` | `2026-04-25` | `Sec Ops` |
| Producción | `SI` | `SI` | `2026-04-25` | `Sec Ops` |

Fallback si RLS no está activo o falla:

- Mantener scoping obligatorio por `organization_id` en la capa de aplicación.
- Bloquear despliegue productivo si tests de aislamiento fallan.
- Ejecutar revisión de queries críticas antes de habilitar clientes nuevos.
- Registrar incidente si se detecta acceso cross-tenant.
- No declarar aislamiento DB-enforced hasta verificar políticas reales en la base productiva.

Tests mínimos de aislamiento:

- Admin de organización A no puede listar empleados de organización B.
- Admin de organización A no puede descargar recibos de organización B.
- Empleado sólo puede ver recibos propios.
- Token de firma no permite modificar `receipt_id`, `employee_id` ni `organization_id`.
- Endpoint público de sello no expone PDF ni salario.

La especificación ejecutable de estos escenarios está en `docs/MULTI_TENANCY_RLS_TEST_PLAN.md`. Un ambiente no debe declararse enterprise-ready si estos casos no fueron ejecutados y evidenciados.

## 15. Rate limiting y protección contra abuso

Se usa `slowapi` con límites explícitos en login y flujos de firma. También existen bloqueo temporal por intentos fallidos, tokens con TTL, OTP con expiración e intentos máximos, CSRF por `X-Requested-With`, CORS restringido, webhooks con idempotencia/HMAC y límites de tamaño de archivos.

Recomendación: agregar rate limits a uploads, bulk operations, password reset y verificación pública si el tráfico lo requiere.

## 16. Logs seguros

El sistema implementa redacción de PII en logs: claves sensibles redactadas, campos parcialmente enmascarados, hashes enmascarados cuando corresponde y headers sensibles no registrados en diagnóstico.

Requisitos:

- Centralizar logs en plataforma segura.
- Restringir acceso a logs de producción.
- Definir retención separada para logs técnicos y evidencia legal.
- Evitar almacenar payloads completos de recibos o firmas.

## 17. Manejo de PII

PII tratada: nombre, DNI/CUIL/CUIT, email, teléfono, dirección, datos bancarios, salario, recibos, IP, user-agent y actividad de firma.

Controles: acceso autenticado por organización, redacción en logs, hash de identidad, separación de storage por tenant, TLS en producción, cifrado app-level de archivos sensibles y cifrado administrado pendiente para storage general/backups.

## 18. Backups

Backups deben cubrir PostgreSQL, storage de PDFs/firmas/evidencias/documentos, certificados públicos y configuración no secreta. Secretos y llaves privadas deben respaldarse mediante secret manager, KMS o HSM, no como archivos sin cifrar.

Política definida:

- Frecuencia: incremental cada 15 minutos, completo diario (AWS Backup).
- Retención: 90 días.
- RPO: 15 minutos.
- Pruebas de restore: mensual en ambiente aislado.

## 19. Riesgos residuales

| Riesgo | Estado |
| --- | --- |
| Cifrado app-level depende de activación por ambiente y KMS real. | Alto si `APP_ENCRYPTION_ENABLED` está apagado en producción. |
| Plaintext transitorio durante generación de PDF firmado antes del reemplazo por ciphertext. | Medio; mitigar con tmpfs cifrado, worker aislado o refactor a pipeline en memoria. |
| Campos PII en base de datos no tienen cifrado campo-a-campo app-level. | Medio; depende de cifrado DB/proveedor y controles de acceso. |
| RLS depende de aplicación efectiva de scripts por ambiente. | Medio/alto. |
| Certificados locales en carpeta de repo requieren revisión de exposición. | Alto si contienen llaves reales. |
| Procesamiento PDF no documentado como sandbox obligatorio. | Medio. |
| Validez legal depende de jurisdicción y contratos. | Resuelto (Argentina). |
| SLA/RTO/RPO no definidos. | Resuelto (99.5% / 4h / 15m). |
| Roles granulares no definidos. | Medio para clientes enterprise. |

## 20. Roadmap de seguridad

1. Activar cifrado app-level en staging con KMS real y evidencia de decrypt/restore.
2. Implementar rotación de KEK/data-key rewrap y runbook de emergencia.
3. Confirmar y testear RLS en ambientes productivos.
4. Mover procesamiento PDF a sandbox, tmpfs cifrado o worker aislado.
5. Implementar MFA para administradores.
6. Formalizar gestión de secretos con KMS/secret manager.
7. Completar política de retención y borrado seguro.
8. Agregar monitoreo de anomalías por tenant, IP y endpoint.
9. Automatizar verificación de audit chain e inmutabilidad.
10. Ejecutar pentest y revisión legal antes de contratos enterprise.

## 21. Riesgos residuales adicionales

| Riesgo | Severidad | Mitigación |
| --- | --- | --- |
| R-009: Fuga de Data Key en RAM | Bajo | Zeroization best-effort en Python. Mitigado con bytearray, scopes acotados y del explícito. |
| R-010: Plaintext transitorio en /tmp | Medio | Archivos PDF plaintext durante firma. Mitigado con **Secure Temp Dir** (tmpfs/RAM disk) y cleanup agresivo. |

## 22. Mitigación de Plaintext Transitorio

Para evitar que archivos sensibles en texto claro queden en disco durante el proceso de firma o descifrado temporal, el sistema implementa:

1. **Secure Temp Directory:** Ubicado en `/dev/shm` (RAM disk) en Linux o en un directorio protegido con permisos `0700`.
2. **Deterministic Cleanup:** Los archivos temporales se eliminan inmediatamente después de su uso. Al arranque del sistema, se realiza un barrido de archivos huérfanos.
3. **Producción Hardened:** Se recomienda el uso de volúmenes `tmpfs` cifrados para el directorio temporal de la aplicación.

## 23. Fallback criptográfico

Nunca se permite un fallback inseguro.

| Componente | Fallo | Acción |
| --- | --- | --- |
| KMS | No disponible | **Fail-fast**. Operación falla inmediatamente. No se permite cifrado en claro. |
| TSA | No disponible | Firma se rechaza o se marca como pendiente de TSA. |

## 24. Cifrado de Identidad (PII)

Toda PII persistida (DNI, fotos, snapshots de identidad) debe estar cifrada antes de almacenarse.

- Uso obligatorio de `EncryptionService` con propósito `identity_evidence`.
- AAD vinculado a `employee_id` y `organization_id`.

## 25. Estado de material criptográfico (certs/)

- **Revisado**: SI.
- **Uso en producción**: NO (producción usa HSM/KMS).
- **Acción**: AISLADO. Los archivos en `certs/` del repositorio son solo para desarrollo local.
