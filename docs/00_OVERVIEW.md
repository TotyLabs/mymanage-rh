# MyManageRH - Overview del sistema

## 1. Propósito

MyManageRH es una plataforma SaaS B2B operada por TotyLabs para gestionar recibos de sueldo, empleados, firmas digitales, evidencia de firma y auditoría documental en organizaciones empleadoras.

El sistema está orientado a procesos donde un empleador necesita cargar recibos, vincularlos con empleados, aplicar firma del empleador, solicitar firma del empleado, conservar evidencia y reconstruir el ciclo de vida del documento ante auditorías internas, clientes enterprise o revisiones legales.

## 2. Problema que resuelve

- Distribución manual de recibos PDF sin trazabilidad suficiente.
- Riesgo de asignar recibos al empleado incorrecto.
- Falta de evidencia sobre quién firmó, cuándo firmó y sobre qué versión del PDF.
- Ausencia de estados claros durante carga, validación, firma y cierre.
- Dificultad para auditar cambios, rechazos, descargas y eventos de notificación.
- Necesidad de separar datos sensibles por organización en un contexto multi-tenant.

## 3. Público objetivo

| Perfil | Necesidad principal |
| --- | --- |
| Organizaciones empleadoras | Gestionar empleados, recibos, firmas del empleador y evidencia. |
| Equipos de RRHH | Cargar recibos, resolver coincidencias, consultar estados y descargar comprobantes. |
| Empleados | Acceder a recibos propios, validar identidad y firmar digitalmente. |
| Auditores | Reconstruir ciclo de vida, verificar hashes, eventos y evidencia asociada. |
| Integradores | Consumir API, webhooks y endpoints de consulta. |
| Legal/Compliance | Revisar tratamiento de datos, evidencia, retención y términos contractuales. |

## 4. Módulos principales

| Módulo | Descripción |
| --- | --- |
| Autenticación y sesiones | Registro, login, logout, sesión por cookie HTTP-only o bearer token, bloqueo por intentos fallidos y verificación de usuario. |
| Organizaciones | Alta y configuración de organización, logo, CUIT y aislamiento tenant. |
| Empleados | Alta manual, importación masiva, legajo, datos laborales, datos bancarios, activación y verificación. |
| Carga de recibos | Carga de lotes PDF, extracción, deduplicación por SHA-256 y matching por DNI/CUIL cuando aplica. |
| Firma del empleador | Firma visual mediante firmante de empresa o firma dibujada, con control de organización y evidencia. |
| Firma del empleado | Flujo por token, OTP, sesión temporal, imagen de firma, snapshot de identidad y cierre del recibo. |
| Firma criptográfica | Integración con X.509, PAdES-LTV, TSA y HSM/PKCS#11 si se configura. |
| Evidencia y auditoría | `audit_log`, `signature_events`, `signature_evidence`, `receipt_seals`, hashes y snapshots. |
| Webhooks y email | Notificaciones, tracking de aperturas y outbox transaccional con reintentos. |
| Documentos complementarios | Gestión de documentos no payroll con hash, metadatos y estados de ciclo de vida. |

## 5. Flujo general del recibo

```text
Carga de recibos -> Validación y matching -> Firma empleador -> Firma empleado -> Auditoría y evidencia
```

### 5.1 Carga de recibos

1. El administrador carga un PDF de recibos o documentos asociados.
2. El backend valida tamaño, formato y magic bytes cuando aplica.
3. El sistema calcula hashes SHA-256 para trazabilidad e integridad.
4. Los archivos se almacenan bajo una estructura segregada por organización y categoría.

### 5.2 Validación y matching

1. El sistema intenta extraer DNI/CUIL mediante parsing/OCR o heurísticas de texto.
2. Si encuentra un empleado compatible dentro de la misma organización, asocia el recibo.
3. Si no puede resolver la identidad, el recibo queda pendiente de matching.
4. RRHH corrige manualmente la asociación antes de iniciar la firma.

### 5.3 Firma del empleador

1. El administrador selecciona un firmante de empresa o provee una firma visual.
2. El sistema bloquea el documento durante el procesamiento para evitar carreras.
3. Se estampa el sello visual y se actualizan hashes y eventos.
4. El recibo queda habilitado para firma del empleado si el flujo lo requiere.

### 5.4 Firma del empleado

1. El empleado accede mediante token de firma y validación de identidad/OTP cuando corresponde.
2. El sistema muestra el recibo y recopila aceptación, firma visual e información contextual.
3. Se aplica sello visual, QR de validación y firma criptográfica si la configuración X.509 está disponible.
4. Si falla una firma criptográfica requerida, el proceso debe fallar sin cerrar el recibo como firmado.

### 5.5 Auditoría

1. El sistema registra eventos de negocio y seguridad.
2. Se preservan hashes de PDF, identidad, firma, certificado y sello cuando corresponde.
3. El auditor puede reconstruir el ciclo de vida por organización, usuario, empleado, recibo y `verification_id` o `seal_id`.

## 6. Alcance actual

- Backend monolítico FastAPI con routers REST.
- Base de datos PostgreSQL administrada por SQLAlchemy y Alembic.
- UI web estática servida por FastAPI.
- Storage de archivos configurable mediante `STORAGE_PATH`.
- Firma visual sobre PDF con PyMuPDF y generación de sello QR.
- Firma criptográfica X.509/PAdES-LTV con pyHanko cuando PKI/TSA está configurado.
- Outbox de webhooks con reintentos y firma HMAC.
- Logs con redacción de PII y tablas de auditoría.
- Soporte de multi-tenancy por `organization_id` y scripts preparados para RLS.

## 7. Fuera de alcance

- Liquidación salarial o cálculo de haberes.
- Emisión oficial de certificados laborales ante organismos públicos.
- Asesoramiento legal definitivo sobre validez de firma en cada jurisdicción.
- Custodia certificada por tercero salvo integración explícita con proveedor definido.
- Garantía de cumplimiento regulatorio absoluto sin revisión legal y auditoría externa.
- Sustitución de políticas internas del cliente sobre RRHH, retención documental o seguridad.
- Operación productiva sin definir SLA, RTO, RPO, retención, subprocesadores y jurisdicción.

## 8. Responsabilidades

| Responsable | Responsabilidades |
| --- | --- |
| TotyLabs | Operar el software, mantener controles técnicos, documentar cambios y custodiar secretos bajo el modelo contratado. |
| Organización cliente | Cargar datos correctos, validar empleados, administrar usuarios autorizados y definir retención legal aplicable. |
| Administrador/RRHH | Revisar recibos, resolver matching, iniciar firmas y descargar evidencia cuando corresponda. |
| Empleado | Revisar el recibo propio, validar identidad y aceptar o rechazar la firma. |
| Legal/Compliance | Aprobar términos, privacidad, DPA, retención, jurisdicción y valor probatorio esperado. |

## 9. Glosario básico

| Término | Definición |
| --- | --- |
| Organización | Cliente empleador dentro del sistema. Actúa como tenant principal. |
| Empleador | Organización o representante autorizado que emite y firma recibos. |
| Empleado | Persona vinculada a una organización que recibe y firma recibos. |
| Recibo | Documento PDF de payroll asociado a un empleado y período. |
| Firma visual | Imagen o sello insertado en el PDF para representación visible de la firma. |
| Firma digital | Firma criptográfica basada en certificado X.509/PAdES cuando está configurada. |
| Token de firma | Valor que habilita un flujo de firma, almacenado en forma hasheada cuando aplica. |
| Evidencia de firma | Datos técnicos y contextuales asociados al acto de firma. |
| Audit trail | Secuencia de eventos que permite reconstruir accesos, cambios y estados. |
| Seal ID | Identificador de sello QR que permite verificar un evento de firma o recibo. |
| PII | Información personal identificable, por ejemplo DNI, CUIL, email, teléfono y dirección. |
| RLS | Row Level Security de PostgreSQL para aislamiento por organización, si está aplicado. |
