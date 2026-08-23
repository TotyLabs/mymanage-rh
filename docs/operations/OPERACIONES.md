# Operaciones - MyManageRH

## 1. Propósito

Este documento define tareas operativas para mantener MyManageRH estable, auditable y seguro. Aplica a ambientes productivos y staging con datos sensibles.

## 2. Responsabilidades

| Rol | Responsabilidad |
| --- | --- |
| Operaciones/DevOps | Uptime, despliegues, backups, storage, jobs, monitoreo y recuperación. |
| Seguridad | Secretos, logs, incidentes, PKI, accesos y hardening. |
| Soporte | Primer nivel con clientes y RRHH. |
| Legal/Compliance | Retención, privacidad, incidentes y evidencias contractuales. |

## 3. Tareas diarias

- Revisar `/health` y `/health/deep`.
- Revisar errores de aplicación y firma.
- Revisar `webhook_outbox` con estado `pending` y `dead_letter`.
- Revisar recibos con `processing_signature=true` fuera de ventana normal.
- Revisar espacio libre del volumen de storage.
- Verificar que no existan fallas recurrentes SMTP/SMS.
- Revisar alertas de login fallido o rate limit.

## 4. Tareas semanales

- Validar backups recientes de DB y storage.
- Probar restore en ambiente controlado según política.
- Revisar usuarios administradores activos.
- Revisar certificados próximos a vencer.
- Revisar tamaño de logs y rotación.
- Revisar acumulación de archivos temporales o cuarentena forense.
- Revisar métricas de firma fallida por organización.

## 5. Tareas mensuales

- Ejecutar auditoría de aislamiento por organización.
- Validar cadena de `audit_log` si `chain_hash` está habilitado.
- Revisar retención de logs y evidencia.
- Rotar secretos según calendario trimestral o ante sospecha de compromiso.
- Revisar dependencias críticas de seguridad.
- Revisar política de RTO/RPO y prueba de DR.
- Generar reporte operativo para dirección o clientes enterprise si aplica.

## 5.1 Verificación diaria de audit logs

Cuando `event_hash`, `previous_hash` y `chain_hash` estén implementados, debe ejecutarse un job diario de verificación de integridad.

Requisitos operativos:

- Ejecutar verificación diaria fuera de hora pico.
- Generar reporte de integridad por ventana temporal.
- Alertar si el job no corre, falla o detecta ruptura de cadena.
- Conservar reportes de integridad por 2 años.
- Escalar como incidente de integridad si hay mismatch.

Runbook detallado: `operations/AUDIT_VERIFICATION_RUNBOOK.md`.

## 6. Monitoreo

Métricas mínimas:

- Disponibilidad de API.
- Latencia p95/p99.
- Errores 5xx.
- Errores 4xx por endpoint.
- Logins fallidos y cuentas bloqueadas.
- Recibos cargados por día.
- Recibos pendientes de matching.
- Firmas exitosas y fallidas.
- Tiempo promedio de firma.
- Webhooks pendientes, reintentos y dead-letter.
- Uso de DB y storage.
- Certificados próximos a vencer.

## 7. Logs importantes

| Log/Fuente | Uso |
| --- | --- |
| `server.log` | Flujo general de request/response y errores operativos. |
| `error.log` | Errores y excepciones. |
| `signature.log` | Diagnóstico del motor de firma. |
| `audit_log` | Auditoría de acciones de negocio. |
| `signature_events` | Eventos específicos de firma. |
| `webhook_outbox` | Estado de integraciones externas. |
| `email_events` | Envío, apertura y fallos de email. |

No compartir logs sin redacción de PII.

## 8. Métricas de negocio-operación

- Porcentaje de recibos firmados dentro de SLA de 99.5% mensual de disponibilidad.
- Porcentaje de recibos con matching automático.
- Pendientes de firma del empleador.
- Pendientes de firma del empleado.
- Rechazos por período.
- Errores de firma criptográfica.
- Tiempo desde carga hasta firma final.

## 9. Mantenimiento de storage

- Monitorear espacio libre y crecimiento por organización.
- Evitar manipulación manual de PDFs firmados.
- Ejecutar reconciliación DB-storage con scripts aprobados.
- No borrar archivos de `storage` sin procedimiento y respaldo.
- Revisar cuarentena `forensics/failed_signatures`.
- Confirmar cifrado en reposo según AWS S3 con SSE-KMS.

## 10. Limpieza de sesiones

Objetivo: remover sesiones vencidas y reducir superficie de ataque.

Procedimiento recomendado:

1. Identificar sesiones con `expires_at` vencido.
2. Borrar sesiones vencidas mediante job aprobado.
3. Registrar conteo eliminado, no tokens.
4. Revisar sesiones activas anómalas si existen.

## 11. Limpieza de locks zombies

Riesgo: recibos quedan con `processing_signature=true` luego de fallo de proceso.

Procedimiento:

1. Listar recibos con `processing_signature=true` y `updated_at` anterior a umbral de 30 minutos.
2. Verificar que no exista proceso de firma activo.
3. Revisar logs y cuarentena.
4. Limpiar flag sólo con aprobación operativa.
5. Registrar evento de auditoría.
6. Reintentar firma si corresponde.

## 12. Webhook retries

- `pending`: pendiente de entrega.
- `delivered`: entregado correctamente.
- `dead_letter`: agotó reintentos.

Procedimiento ante `dead_letter`:

1. Verificar endpoint del cliente.
2. Verificar HMAC secret y TLS.
3. Confirmar si el cliente procesó el evento por otro camino.
4. Reencolar manualmente sólo si es seguro e idempotente.
5. Documentar acción en ticket.

## 13. Backups

Backups deben cubrir DB y storage con consistencia temporal.

Política definida:

- Frecuencia: incremental cada 15 minutos, completo diario.
- Retención: 90 días.
- RTO: 4 horas.
- RPO: 15 minutos.
- Prueba de restore: mensual en ambiente aislado.

No respaldar secretos como archivos planos sin cifrar. Usar secret manager/KMS/HSM.

## 14. Rotación de secretos

Secretos a rotar:

- `SECRET_KEY` con procedimiento especial por impacto en sesiones/tokens.
- `DATABASE_URL` o password DB.
- `SMTP_PASSWORD`.
- `PAYROLL_WEBHOOK_SECRET`.
- `X509_P12_PASSWORD`.
- `HSM_PIN`.
- Credenciales Twilio.

Procedimiento base:

1. Crear nuevo secreto.
2. Desplegar en staging.
3. Validar login, firma, webhooks y email.
4. Desplegar en producción durante ventana aprobada.
5. Revocar secreto anterior.
6. Registrar cambio.

## 14.1 Revisión de certificados y llaves

La carpeta `certs/` y cualquier ruta equivalente de certificados debe tratarse como área sensible.

Checklist operativo:

- [ ] Confirmar que `certs/` está ignorada por Git.
- [ ] Confirmar que ningún `.pem`, `.key`, `.p12` o `.pfx` real está versionado.
- [ ] Confirmar que certificados de desarrollo no se usan en producción.
- [ ] Registrar fingerprint público de certificados productivos.
- [ ] Revisar vencimientos de certificados y CRL.
- [ ] Validar que root keys privadas no estén disponibles para el proceso runtime salvo procedimiento controlado.
- [ ] Confirmar que P12 productivo está custodiado por HSM/KMS o almacenamiento cifrado con acceso mínimo.

Si aparece material criptográfico productivo en un repo, ticket, chat, backup no cifrado o equipo no autorizado, activar el procedimiento de compromiso de claves en `operations/DISASTER_RECOVERY.md`.

### 14.1.1 Estado de material criptográfico local

Esta tabla debe mantenerse actualizada después de cada revisión de `certs/` o rutas equivalentes.

| Material | Revisado | Uso en producción | Acción | Fecha | Responsable | Evidencia |
| --- | --- | --- | --- | --- | --- | --- |
| `private_key.pem` | SI | NO | AISLADO (solo desarrollo local) | 2026-04-25 | Seguridad/DevOps | Revisión de `certs/` y `.gitignore` |
| `root_key.pem` | SI | NO | AISLADO (solo desarrollo local) | 2026-04-25 | Seguridad/DevOps | Revisión de `certs/` y `.gitignore` |
| `signer.p12` | SI | NO (Producción usa HSM/KMS) | AISLADO (solo desarrollo local) | 2026-04-25 | Seguridad/DevOps | Revisión de `certs/` y `.gitignore` |
| Certificados públicos | SI | SI (Root CA y CRL publicados) | PUBLICABLE | 2026-04-25 | Seguridad/DevOps | Endpoints `/pki/root_ca.crt` y `/pki/root_ca.crl` |

Estados permitidos de acción:

- `ROTADO`: el material fue reemplazado y el anterior revocado o retirado.
- `AISLADO`: el material se conserva sólo para análisis o desarrollo local, con acceso restringido.
- `ELIMINADO`: el material fue removido porque no es necesario.
- `NO APLICA`: material público o ficticio confirmado.

Si `Uso en producción` es `DESCONOCIDO`, tratar como riesgo abierto hasta demostrar lo contrario.

## 15. Procedimientos ante incidentes

### 15.1 Incidente de disponibilidad

- Confirmar alcance.
- Activar canal interno.
- Revisar health, DB, storage y logs.
- Mitigar o hacer rollback.
- Comunicar a clientes según severidad.
- Documentar postmortem.

### 15.2 Incidente de datos

- Preservar evidencia.
- Revocar accesos o secretos comprometidos.
- Identificar organizaciones afectadas.
- Activar Legal/Compliance.
- Comunicar según legislación de la República Argentina (Ley 25.326 y normativa aplicable).
- No borrar logs ni evidencia.

### 15.3 Incidente de firma/PKI

- Pausar firma si hay riesgo de invalidez.
- Validar certificados, CRL, TSA y HSM/P12.
- Identificar recibos firmados durante ventana afectada.
- Emitir recomendación técnica y legal.

## 16. Escalamiento

| Severidad | Ejemplo | Escalamiento |
| --- | --- | --- |
| Sev 1 | Fuga de datos, corrupción masiva, caída total. | Dirección, Seguridad, Legal, Operaciones. |
| Sev 2 | Firma caída, DB degradada, webhooks críticos fallando. | Operaciones, Seguridad, Soporte. |
| Sev 3 | Error parcial por cliente, emails demorados. | Soporte y Operaciones. |
| Sev 4 | Consulta o mejora menor. | Soporte. |

## 17. Checklist post-operación crítica

- [ ] Health checks OK.
- [ ] No errores 5xx inusuales.
- [ ] Webhooks sin dead-letter nuevo.
- [ ] Storage con espacio suficiente.
- [ ] Backups recientes verificados.
- [ ] Logs sin secretos.
- [ ] Evidencia de cambios registrada.
