# Índice maestro de documentación - MyManageRH

## Propósito

Este índice organiza la documentación oficial de MyManageRH, un SaaS B2B operado por TotyLabs para gestión de recibos de sueldo, firma digital, evidencia de firma, auditoría y operación multi-tenant.

La documentación está preparada para revisión por clientes enterprise, auditores, equipos legales, compliance, RRHH, integradores y operaciones. No reemplaza contratos, dictámenes legales ni auditorías externas.

## Principios documentales

- Usar Markdown como formato editable y auditable.
- Separar documentación técnica, operativa, legal y de negocio.
- No publicar secretos, tokens, claves privadas, certificados privados, datos reales de empleados ni rutas privadas del entorno.
- Usar ejemplos ficticios y placeholders explícitos cuando falte una decisión humana.
- Mantener consistencia terminológica: MyManageRH, TotyLabs, organización, empleador, empleado, recibo y firma digital.
- Tratar los documentos legales como base operativa sujeta a revisión profesional.

## Estructura

| Carpeta | Propósito | Audiencia principal |
| --- | --- | --- |
| `docs/` | Arquitectura, API, seguridad, firma digital, integridad y auditoría. | Ingeniería, Seguridad, Auditoría, Integraciones |
| `operations/` | Instalación, onboarding, operación diaria y recuperación ante desastres. | DevOps, Soporte, Operaciones, RRHH cliente |
| `legal/` | Bases contractuales, privacidad, DPA, NDA y contrato SaaS. | Legal, Compliance, Dirección |
| `business/` | Documentación corporativa y propiedad intelectual. | Dirección, Legal, Administración |

## Documentos técnicos

| Documento | Para qué sirve |
| --- | --- |
| `docs/00_OVERVIEW.md` | Presenta el sistema, problema, módulos, flujo general, alcance y glosario. |
| `docs/01_ARQUITECTURA.md` | Describe arquitectura real basada en FastAPI, PostgreSQL, storage, firma digital, webhooks y multi-tenancy. |
| `docs/03_API_REFERENCE.md` | Referencia de endpoints, autenticación, roles, errores, rate limits y ejemplos ficticios. |
| `docs/05_SEGURIDAD_Y_FIRMAS.md` | Modelo de firma visual y criptográfica, X.509, PAdES-LTV, TSA/HSM/PKI, sellos QR, evidencia y limitaciones. |
| `docs/06_INTEGRIDAD_Y_AUDITORIA.md` | Principios de integridad, audit trail, evidencia, inmutabilidad, retención y reconstrucción del ciclo de vida. |
| `docs/07_CACHE_AND_SCALABILITY_PLAN.md` | Plan de evolución para Redis, jobs, object storage y múltiples nodos. |
| `docs/08_ESTIMACION_CAPACIDAD_PRODUCCION.md` | Estimación de capacidad de producción del sistema, límites actuales y recomendaciones. |
| `docs/ARQUITECTURA_SEGURIDAD.md` | Documento técnico de amenazas, controles, archivos, PII, secretos, cifrado y riesgos residuales. |
| `docs/AUDIT_LOG_SPEC.md` | Especificación interna de eventos de auditoría, campos, ejemplos JSON, retención e inmutabilidad. |
| `docs/CRYPTO_KEY_MANAGEMENT.md` | Modelo objetivo de cifrado, custodia de llaves, rotación, alcance criptográfico y respuesta ante compromiso. |
| `docs/MULTI_TENANCY_RLS_TEST_PLAN.md` | Casos de prueba cross-tenant y RLS para demostrar aislamiento por organización. |

## Documentos operativos

| Documento | Para qué sirve |
| --- | --- |
| `operations/GUIA_INSTALACION.md` | Requisitos, variables de entorno, DB, migraciones, storage, certificados, email, webhooks y health checks. |
| `operations/ONBOARDING.md` | Guía simple para RRHH y usuarios: alta, empleados, carga, firma y evidencia. |
| `operations/OPERACIONES.md` | Rutinas, monitoreo, logs, métricas, limpieza, backups, incidentes y escalamiento. |
| `operations/DISASTER_RECOVERY.md` | Recuperación ante caída de servidor, DB, storage, fuga de datos, PKI/TSA/HSM y email. |
| `operations/AUDIT_VERIFICATION_RUNBOOK.md` | Procedimiento de verificación diaria/mensual de integridad de audit logs y hash chain. |

## Documentos legales

Todos los documentos de `legal/` son bases operativas y deben ser revisados por un profesional legal antes de uso contractual.

| Documento | Para qué sirve |
| --- | --- |
| `legal/TOS.md` | Términos y Condiciones base del servicio. |
| `legal/PRIVACY.md` | Política de Privacidad base para datos personales y laborales. |
| `legal/DPA.md` | Acuerdo de Tratamiento de Datos entre cliente y TotyLabs/MyManageRH. |
| `legal/NDA.md` | Acuerdo de Confidencialidad. |
| `legal/SAAS_AGREEMENT.md` | Contrato SaaS B2B base con anexos de SLA, DPA y soporte. |
| `legal/LEGAL_READINESS_CHECKLIST.md` | Checklist de bloqueantes legales/compliance antes de contratación enterprise. |

## Documentos de negocio

| Documento | Para qué sirve |
| --- | --- |
| `business/README.md` | Define qué documentos corporativos pertenecen a esta carpeta y qué no debe subirse a repos públicos. |
| `business/MARCA_INPI.md` | Estado y seguimiento del registro marcario ante INPI. |
| `business/ESTATUTOS.md` | Estructura societaria, relación TotyLabs/MyManageRH y titularidad de IP. |

## Placeholders que requieren decisión humana

| Placeholder | Responsable sugerido |
| --- | --- |
| `[DEFINIR JURISDICCIÓN]` | Legal externo o counsel interno |
| `[DEFINIR SLA]` | Dirección, Producto y Operaciones |
| `[DEFINIR RTO]` | Operaciones e Infraestructura |
| `[DEFINIR RPO]` | Operaciones e Infraestructura |
| `[DEFINIR RETENCIÓN]` | Legal, Compliance y Cliente |
| `[DEFINIR BASE LEGAL]` | Legal y Data Protection |
| `[DEFINIR SUBPROCESADORES]` | Operaciones, Seguridad y Legal |
| `[DEFINIR PROVEEDOR DE STORAGE]` | Infraestructura |
| `[DEFINIR KMS/HSM/TSA]` | Seguridad e Infraestructura |
| `[DEFINIR MODELO DE CIFRADO]` | Seguridad, Infraestructura y Legal |
| `[DEFINIR ESTADO RLS POR AMBIENTE]` | Seguridad, Infraestructura e Ingeniería |

## Control de cambios recomendado

- Revisar esta documentación antes de cada release funcional relevante.
- Versionar cambios legales con fecha, responsable y aprobación.
- Mantener ejemplos con datos ficticios.
- Registrar cambios materiales de seguridad en `docs/ARQUITECTURA_SEGURIDAD.md` y `operations/OPERACIONES.md`.
- Verificar que `.env`, certificados privados, llaves, P12 reales, dumps de DB y recibos reales no estén versionados.
