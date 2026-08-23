# Disaster Recovery - MyManageRH

## 1. Propósito

Este documento define procedimientos de recuperación ante incidentes mayores que afecten disponibilidad, integridad, confidencialidad o capacidad de firma de MyManageRH.

## 2. Objetivos pendientes

| Objetivo | Valor |
| --- | --- |
| RTO | 4 horas |
| RPO | 15 minutos |
| Retención de backups | 90 días |
| Frecuencia de backups | Incremental cada 15 minutos, completo diario |
| Responsable DR | Operaciones / DevOps (Cloud Admin) |

## 3. Tabla de severidades

| Severidad | Descripción | Ejemplos |
| --- | --- | --- |
| Sev 1 | Impacto crítico o legal inmediato. | Fuga de datos, pérdida de storage, corrupción DB, caída total prolongada. |
| Sev 2 | Servicio central degradado. | Firma caída, DB intermitente, PKI/TSA/HSM fuera de servicio. |
| Sev 3 | Función secundaria afectada. | Emails demorados, webhooks en dead-letter, importaciones fallando. |
| Sev 4 | Bajo impacto. | Incidente aislado, consulta operativa. |

## 4. Backup strategy

Backups requeridos:

- PostgreSQL: dump lógico o snapshot consistente.
- Storage: PDFs, firmas, identidad, importaciones, evidencia y cuarentena forense.
- Configuración no secreta.
- Certificados públicos y CRL.
- Secretos y llaves privadas mediante secret manager/KMS/HSM, no en archivos planos.

Reglas:

- DB y storage deben poder restaurarse a un punto consistente.
- Probar restore periódicamente.
- Registrar resultados de pruebas.
- Mantener backups cifrados y con acceso limitado.

## 5. Procedimiento general de restore

1. Declarar incidente y severidad.
2. Congelar cambios si hay riesgo de corrupción.
3. Preservar logs y evidencia.
4. Seleccionar punto de restauración según RPO.
5. Restaurar DB en ambiente aislado.
6. Restaurar storage correspondiente.
7. Validar migraciones y esquema.
8. Recalcular hashes de muestra crítica.
9. Validar login, carga, firma, descarga y auditoría.
10. Redirigir tráfico o promover ambiente restaurado.
11. Comunicar estado a clientes.
12. Documentar post-incidente.

## 6. Si cae el servidor

Acciones:

1. Verificar infraestructura, proceso y logs.
2. Reiniciar servicio si no hay señales de corrupción.
3. Confirmar conexión a DB y storage.
4. Revisar health checks.
5. Verificar que no quedaron firmas en progreso.
6. Limpiar locks zombies si corresponde y está aprobado.
7. Comunicar indisponibilidad si excede SLA de 99.5% mensual.

## 7. Si cae la base de datos

Acciones:

1. Declarar Sev 1 o Sev 2 según duración.
2. Bloquear operaciones de escritura si la API sigue activa.
3. Verificar disponibilidad del servidor DB o servicio administrado.
4. Restaurar desde réplica o backup según RTO/RPO.
5. Validar integridad de `audit_log`, `signature_events` y recibos firmados.
6. Confirmar que el outbox no duplicó eventos críticos.
7. Reanudar tráfico gradualmente.

## 8. Si se pierde storage

Acciones:

1. Declarar Sev 1.
2. Detener firmas y descargas para evitar evidencia inconsistente.
3. Restaurar storage desde backup consistente con DB.
4. Ejecutar reconciliación DB-storage.
5. Validar hashes de muestra representativa.
6. Identificar documentos no recuperables si los hubiera.
7. Activar Legal/Compliance si existe pérdida de evidencia o datos.

## 9. Si hay fuga de datos

Acciones inmediatas:

1. Activar respuesta a incidentes y legal hold.
2. Preservar logs, audit trail, snapshots y accesos.
3. Revocar secretos o sesiones comprometidas.
4. Identificar organizaciones, empleados y documentos afectados.
5. Bloquear vectores de exfiltración.
6. Notificar a clientes y autoridades según legislación de la República Argentina (Ley 25.326 y normativa aplicable).
7. Documentar timeline, causa raíz, alcance y mitigaciones.

No borrar evidencia durante la investigación.

## 10. Si falla TSA/HSM/PKI

Acciones:

1. Pausar firma criptográfica si la política exige X.509/PAdES-LTV.
2. Verificar disponibilidad de TSA, HSM, P12, PIN, certificados y CRL.
3. Revisar expiración o revocación de certificados.
4. Ejecutar prueba con PDF ficticio.
5. Si existe fallback local, validar aprobación legal antes de usarlo.
6. Identificar recibos afectados durante la ventana.
7. Documentar si el recibo quedó sin cerrar, falló correctamente o requiere refirma.

## 10.1 Si se expone material criptográfico

Aplica si se confirma o sospecha exposición de:

- Llaves privadas `.pem` o `.key`.
- Bundles `.p12` o `.pfx`.
- Root CA o intermediate CA privadas.
- Passwords de P12.
- PIN HSM.
- Master keys de vault/KMS.
- Secrets de webhook o `SECRET_KEY`.

Acciones inmediatas:

1. Declarar incidente Sev 1 si el material fue usado en producción.
2. Asumir compromiso hasta demostrar lo contrario.
3. Detener uso de la clave o certificado afectado.
4. Identificar ambientes, recibos y firmas impactadas.
5. Revocar certificados afectados y publicar CRL/OCSP actualizado si aplica.
6. Generar nuevo material criptográfico en ambiente seguro.
7. Rotar secretos relacionados.
8. Invalidar sesiones/tokens si `SECRET_KEY` o sesiones fueron afectados.
9. Evaluar refirma, reemisión de evidencia o nota de excepción legal para documentos impactados.
10. Notificar a clientes y autoridades si corresponde según legislación de la República Argentina.
11. Documentar postmortem con alcance, causa raíz, decisiones y controles preventivos.

Regla operativa: si una llave privada o P12 fue versionada, enviada por chat, incluida en backup no cifrado o compartida con terceros no autorizados, se debe tratar como comprometida.

Estado de cierre requerido:

| Material | Revisado | Uso en producción | Decisión | Estado final |
| --- | --- | --- | --- | --- |
| Llave privada local | SI | NO | AISLADO (solo desarrollo) | CERRADO |
| Root key local | SI | NO | AISLADO (solo desarrollo) | CERRADO |
| P12 signer local | SI | NO (Producción usa HSM/KMS) | AISLADO (solo desarrollo) | CERRADO |

No cerrar el incidente si `Uso en producción` permanece `DESCONOCIDO`.

## 11. Si falla el envío de emails

Acciones:

1. Confirmar `EMAIL_MODE`, SMTP y credenciales.
2. Revisar reputación, límites o bloqueo del proveedor.
3. Confirmar si OTP o links fueron enviados parcialmente.
4. Reintentar sólo si no genera duplicados peligrosos.
5. Comunicar a RRHH que las firmas pueden demorarse.
6. Activar proveedor alternativo si existe (SendGrid como fallback de SMTP primario).

## 12. Comunicación interna

Canales internos: Slack (#payroll-incidents), email de escalamiento (ops@totylabs.com), llamada directa para Sev 1.

Mensaje interno mínimo:

- Severidad.
- Impacto.
- Inicio del incidente.
- Servicios afectados.
- Responsable de coordinación.
- Próxima actualización.

## 13. Comunicación a clientes

Este documento es una base operativa y debe ser revisado por un profesional legal antes de uso contractual.

Contenido mínimo:

- Qué servicio está afectado.
- Desde cuándo.
- Impacto conocido.
- Acciones en curso.
- Workaround si existe.
- Próxima actualización.
- Contacto de soporte.

No incluir detalles técnicos explotables ni PII.

## 14. Evidencia post-incidente

Preservar:

- Logs de aplicación e infraestructura.
- Snapshots DB si aplica.
- Hashes de documentos afectados.
- Audit trail y signature events.
- Estados de webhook outbox.
- Configuración vigente al momento del incidente.
- Timeline de decisiones.

## 15. Checklist de recuperación

- [ ] Incidente clasificado.
- [ ] Responsable asignado.
- [ ] Cambios congelados si aplica.
- [ ] Logs preservados.
- [ ] DB restaurada o validada.
- [ ] Storage restaurado o validado.
- [ ] Secretos rotados si aplica.
- [ ] PKI/TSA/HSM validado si aplica.
- [ ] Health checks OK.
- [ ] Firmas en progreso revisadas.
- [ ] Webhooks revisados.
- [ ] Clientes comunicados si corresponde.
- [ ] Postmortem creado.
