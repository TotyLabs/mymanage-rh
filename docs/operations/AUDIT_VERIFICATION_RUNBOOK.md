# Audit Verification Runbook - MyManageRH

## 1. Propósito

Este runbook define cómo verificar periódicamente que la cadena de auditoría de MyManageRH no fue alterada, truncada, reordenada o regenerada sin autorización.

Objetivo auditor: poder responder con evidencia a la pregunta: “muestre que la cadena de logs no fue alterada en los últimos 30 días”.

## 2. Estado actual

| Control | Estado | Comentario |
| --- | --- | --- |
| Diseño de `event_hash` | Documentado | Ver `docs/AUDIT_LOG_SPEC.md`. |
| Diseño de `previous_hash` / `chain_hash` | Documentado | Ver `docs/AUDIT_LOG_SPEC.md`. |
| Job diario de verificación | `[PENDIENTE]` | Debe implementarse antes de declarar tamper-evidence operativo. |
| Reporte diario de integridad | `[PENDIENTE]` | Debe generarse y conservarse. |
| Alerta automática ante falla | `[PENDIENTE]` | Debe integrarse con monitoreo/incidentes. |
| Export write-once o firma de lote | `[PENDIENTE]` | Recomendado para auditoría enterprise. |

Declaración de límite: hasta implementar y operar este runbook, la documentación describe el diseño de verificabilidad, no una garantía operativa continua.

## 3. Alcance de verificación

Verificar diariamente:

- `audit_log`.
- `signature_events`.
- `signature_evidence` si se encadena o exporta.
- `receipt_seals` si se usa como evidencia pública.
- Manifiestos o exports write-once si existen.

Ventana mínima recomendada:

- Últimas 24 horas para verificación diaria.
- Últimos 30 días para verificación de control mensual.
- Rango completo ante auditoría, disputa legal o incidente.

## 4. Job diario de verificación

Frecuencia recomendada: diaria, fuera de hora pico.

Entrada:

- Rango temporal a verificar.
- Scope: global, por organización o por recibo.
- Último `chain_hash` validado del día anterior.
- Configuración de algoritmo y versión.

Proceso:

1. Leer eventos ordenados por `occurred_at` y `event_id` o ID secuencial estable.
2. Recalcular `event_hash` de cada evento usando JSON canónico.
3. Recalcular `chain_hash` usando `event_hash + previous_hash`.
4. Confirmar continuidad de `previous_hash`.
5. Detectar gaps de IDs, timestamps fuera de orden o eventos faltantes.
6. Comparar último hash contra manifest firmado o export externo si existe.
7. Emitir reporte firmado o almacenado en ubicación append-only.

Salida esperada:

- `status`: `passed` o `failed`.
- Cantidad de eventos verificados.
- Primer evento y último evento.
- Primer hash y último hash.
- Gaps detectados.
- Errores de recomputación.
- Scope y rango temporal.
- Timestamp de verificación.
- Versión del verificador.

## 5. Reporte de integridad

Formato mínimo recomendado:

```json
{
  "report_id": "audit_integrity_2026-04-25",
  "scope": "organization",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "range_start": "2026-04-24T00:00:00Z",
  "range_end": "2026-04-25T00:00:00Z",
  "status": "passed",
  "events_verified": 1284,
  "first_event_id": "evt_000001",
  "last_event_id": "evt_001284",
  "first_chain_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "last_chain_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "gaps_detected": 0,
  "verification_version": "audit-verifier-v1",
  "verified_at": "2026-04-25T03:00:00Z"
}
```

El reporte no debe incluir PII innecesaria. Si se exporta a clientes, debe pasar revisión de privacidad.

## 5.1 Evidencia exportable estándar

Nombre recomendado:

```text
audit_integrity_report.json
```

Schema mínimo:

```json
{
  "report_id": "audit_integrity_2026-04-25_org_demo",
  "report_type": "audit_integrity",
  "schema_version": "1.0",
  "environment": "staging",
  "scope": "organization",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "range_start": "2026-01-25T00:00:00Z",
  "range_end": "2026-04-25T00:00:00Z",
  "chain_valid": true,
  "last_verified_at": "2026-04-25T03:00:00Z",
  "events_verified": 98234,
  "first_event_id": "evt_000001",
  "last_event_id": "evt_098234",
  "first_chain_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "last_chain_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "gaps_detected": 0,
  "mismatches_detected": 0,
  "verification_algorithm": "sha256-canonical-json-chain-v1",
  "verifier_version": "audit-verifier-v1",
  "generated_by": "system",
  "report_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "signature": {
    "type": "none",
    "status": "not_configured",
    "key_id": null
  }
}
```

Recomendación enterprise:

- Firmar `audit_integrity_report.json` con KMS/HSM o clave dedicada de auditoría.
- Guardar el reporte y su hash en storage append-only o write-once.
- Conservar reportes diarios por 2 años.
- Poder exportar los últimos 90 días bajo pedido de auditoría.

Campos obligatorios para auditoría:

- `chain_valid`.
- `last_verified_at`.
- `range_start`.
- `range_end`.
- `events_verified`.
- `last_chain_hash`.
- `report_hash`.
- `verifier_version`.

## 6. Alertas

Generar alerta Sev 1 o Sev 2 si ocurre cualquiera de los siguientes eventos:

- `event_hash` no coincide.
- `previous_hash` no coincide con evento anterior.
- `chain_hash` no recalcula.
- Faltan eventos esperados.
- Hay IDs salteados no explicados.
- Se detectan updates/deletes en tablas append-only.
- El último hash no coincide con manifest externo.
- El job diario no corre dentro de la ventana esperada.

## 7. Respuesta ante falla

1. Clasificar como incidente de integridad.
2. Preservar DB, logs, backups y exports externos.
3. Suspender destrucción o rotación de logs afectados.
4. Identificar scope: global, organización, recibo o ventana temporal.
5. Comparar contra backup o export write-once.
6. Revisar accesos administrativos y cambios DB.
7. Notificar a Seguridad, Legal y Operaciones.
8. Determinar si corresponde comunicación a cliente.
9. Documentar postmortem.

## 8. Evidencia para auditor

Entregar bajo autorización:

- Reportes diarios de integridad del período solicitado.
- Manifiestos firmados o write-once si existen.
- Procedimiento de recomputación.
- Versión del verificador.
- Últimos hashes de cadena.
- Evidencia de alertas y resolución si hubo fallas.

## 9. Requisito para declarar control activo

No declarar audit chain como control operativo activo hasta que existan:

- Job implementado.
- Reporte diario conservado.
- Alertas configuradas.
- Prueba de falla controlada.
- Evidencia de ejecución por al menos 30 días continuos.
