# Multi-Tenancy & RLS Test Plan - MyManageRH

## 1. Propósito

Este documento define pruebas mínimas para demostrar que MyManageRH aísla datos entre organizaciones y que un usuario de una organización no puede acceder, firmar, descargar o inferir datos de otra.

Objetivo auditor: convertir “RLS preparado” y “scoping por organización” en evidencia verificable.

## 2. Estado actual

| Control | Estado | Evidencia requerida |
| --- | --- | --- |
| Scoping por organización en aplicación | Implementado en múltiples endpoints | Revisión de queries y pruebas automatizadas. |
| RLS SQL preparado | Scripts disponibles | Confirmación de aplicación por ambiente. |
| RLS activo en desarrollo | NO | Desarrollo usa scoping app-level sin RLS DB. |
| RLS activo en staging | SI | Resultado de `setup_rls.sql` aplicado y prueba cross-tenant ejecutada 2026-04-25. |
| RLS activo en producción | SI | Resultado de `setup_rls.sql` aplicado y prueba cross-tenant ejecutada 2026-04-25. |
| Tests automatizados cross-tenant | En desarrollo | Suite CI planificada; validación manual mensual en staging. |

Declaración de límite: no declarar multi-tenancy DB-enforced hasta confirmar políticas RLS reales en la base del ambiente evaluado.

## 3. Datos ficticios de prueba

Crear dos organizaciones ficticias:

| Organización | Usuario admin | Empleado | Recibo |
| --- | --- | --- | --- |
| Organización A Demo | `admin.a@example.test` | `empleado.a@example.test` | `receipt_a_demo` |
| Organización B Demo | `admin.b@example.test` | `empleado.b@example.test` | `receipt_b_demo` |

Todos los datos deben ser ficticios. No usar recibos reales.

## 4. Casos de prueba obligatorios

### 4.1 Admin A intenta listar empleados de Organización B

Escenario:

- Login como admin de Organización A.
- Intentar acceder a endpoint o query de empleados de Organización B.

Resultado esperado:

- HTTP `403` o `404`.
- Ningún dato de Organización B en response.
- Evento auditado: `SECURITY_CROSS_TENANT_ACCESS_DENIED` o equivalente.
- El evento debe incluir `actor_id`, `target_org_id` si puede determinarse, `action=unauthorized_access_attempt` y `result=denied`.

### 4.2 Admin A intenta descargar recibo de Organización B

Escenario:

- Login como admin de Organización A.
- Usar `receipt_id` perteneciente a Organización B en `/api/receipts/{receipt_id}/download`.

Resultado esperado:

- HTTP `403` o `404`.
- No se descarga PDF.
- No se expone nombre, email, salario ni metadata de Organización B.
- Evento auditado con `actor_id`, `organization_id` de actor y `resource_id` solicitado.
- El evento debe incluir `target_org_id` si puede determinarse sin exponer datos al response.

### 4.3 Empleado A intenta acceder a recibo de Empleado B

Escenario:

- Login como empleado de Organización A.
- Intentar consultar o descargar recibo de otro empleado, incluso dentro de la misma organización si no está autorizado.

Resultado esperado:

- HTTP `403` o `404`.
- Evento auditado.
- No se revela si el recibo existe, salvo política explícita.
- El evento debe incluir `action=unauthorized_access_attempt` y `result=denied`.

### 4.4 Token de firma de A intenta firmar recibo B

Escenario:

- Obtener token válido para `receipt_a_demo`.
- Manipular request para intentar firmar `receipt_b_demo` o cambiar IDs en payload.

Resultado esperado:

- HTTP `400`, `403` o `409` según validación.
- Firma no aplicada.
- `processing_signature` no queda activo en recibo B.
- Evento auditado de intento inválido.
- El evento debe incluir token context redactado, nunca token raw.

### 4.5 Endpoint público de sello no expone PII sensible

Escenario:

- Consultar `/api/receipts/v/{seal_id}` con sello válido.

Resultado esperado:

- Devuelve estado, organización, rol, timestamp y hash permitido.
- No devuelve PDF, salario, CUIL completo, email, dirección, CBU ni recibo completo.

### 4.6 Query directa con RLS activo

Escenario:

- Iniciar sesión DB con usuario de aplicación.
- Setear `app.current_org_id` a Organización A.
- Ejecutar query sobre tablas multi-tenant intentando obtener filas de Organización B.

Resultado esperado:

- Cero filas de Organización B.
- Si se omite `app.current_org_id`, política fail-safe debe negar acceso o devolver cero filas.

## 5. Evidencia requerida por prueba

Cada prueba debe registrar:

- Fecha y ambiente.
- Commit o versión desplegada.
- Usuario actor ficticio.
- Organización actor.
- Recurso objetivo.
- Request ejecutado, sin secretos.
- HTTP status.
- Resultado observado.
- Evento auditado generado.
- Captura o log redactado.
- Responsable de ejecución.

## 5.1 Evento auditado esperado

Todo intento cross-tenant relevante debe generar un evento de auditoría. Evento recomendado:

```json
{
  "event_type": "SECURITY_CROSS_TENANT_ACCESS_DENIED",
  "action": "unauthorized_access_attempt",
  "result": "denied",
  "actor_id": "22222222-2222-4222-8222-222222222222",
  "actor_org_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "target_org_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "resource_type": "receipt",
  "resource_id": "44444444-4444-4444-8444-444444444444",
  "source_ip": "203.0.113.10",
  "request_id": "req_demo_cross_tenant_001"
}
```

Campos mínimos:

- `actor_id`.
- `actor_org_id`.
- `target_org_id` cuando pueda determinarse sin filtrar PII al usuario.
- `action=unauthorized_access_attempt`.
- `resource_type`.
- `resource_id`.
- `result=denied`.
- `source_ip`.
- `request_id`.

Si por diseño no se desea revelar ni resolver `target_org_id` en la capa de aplicación, el evento debe registrar `target_org_id="unknown_or_hidden"` y preservar internamente el contexto necesario para investigación.

## 6. Criterio de aprobación

La suite cross-tenant aprueba sólo si:

- Todos los accesos cruzados devuelven `403` o `404`.
- Ningún response contiene PII de otra organización.
- No se generan firmas, descargas ni cambios de estado no autorizados.
- Se genera evento de auditoría para intentos relevantes.
- RLS, si está declarado activo, bloquea también acceso directo por DB session.

## 7. Criterio de bloqueo de release

Bloquear release si:

- Una prueba devuelve datos de otra organización.
- Un recibo de otra organización puede descargarse o firmarse.
- RLS se declara activo pero no puede demostrarse.
- El sistema revela existencia de recursos ajenos de forma innecesaria.
- No se genera auditoría ante intentos cross-tenant relevantes.

## 8. Cadencia

- Ejecutar en cada release que modifique auth, empleados, recibos, firma, documentos, storage o auditoría.
- Ejecutar mensualmente en staging.
- Ejecutar ante cambios de RLS, migraciones o roles.
- Ejecutar antes de onboarding de cliente enterprise.

## 9. Relación con documentación de seguridad

Este plan complementa `docs/ARQUITECTURA_SEGURIDAD.md`. Si una prueba falla, actualizar riesgos residuales y abrir incidente o ticket de remediación.
