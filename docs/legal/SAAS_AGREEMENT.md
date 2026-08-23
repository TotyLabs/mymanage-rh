# Contrato SaaS B2B - MyManageRH

## Aviso legal

Este documento es una base operativa y debe ser revisado por un profesional legal antes de uso contractual.

## 1. Partes

Proveedor: TotyLabs, operador de MyManageRH.

Cliente: `[DEFINIR CLIENTE]`.

## 2. Servicio contratado

MyManageRH es un SaaS B2B para gestión de recibos de sueldo, empleados, firma digital, evidencia, auditoría, notificaciones e integraciones.

El alcance exacto se define en la orden comercial, propuesta o anexo correspondiente.

## 3. Planes

Planes disponibles:

| Plan | Descripción |
| --- | --- |
| Starter | Hasta 50 empleados, firma visual, storage 5 GB, soporte email hábil. |
| Professional | Hasta 200 empleados, firma visual + X.509/PAdES-LTV, storage 20 GB, webhooks, soporte prioritario. |
| Enterprise | Empleados ilimitados, firma X.509/PAdES-LTV con HSM, storage escalable, API completa, webhooks, SLA extendido, soporte dedicado. |

Variables posibles:

- Cantidad de empleados.
- Cantidad de recibos por período.
- Storage incluido.
- Firma X.509/PAdES-LTV.
- Integraciones API/webhook.
- Soporte y SLA.
- Retención extendida.

## 4. SLA

SLA Objetivo:
- 99.5% mensual (MVP)
- 99.9% (Infraestructura escalada)

Exclusiones: mantenimiento programado, fallas de terceros (KMS, email, cloud).
RTO: 4 horas.
RPO: 15 minutos.

## 5. Soporte

Canales: Email y Portal de Soporte.
Horario: Hábil (Lunes a Viernes, 09:00 a 18:00 ART).
Respuesta inicial: < 24h.
Severidades: Crítica, Alta, Media, Baja.

## 6. Pagos

Condiciones comerciales:

- Moneda: Pesos argentinos (ARS) o dólares estadounidenses (USD), según acuerdo.
- Facturación: mensual anticipada o anual con descuento.
- Vencimiento: 10 días corridos desde la fecha de factura.
- Mora: interés equivalente a 1.5 veces la tasa activa del Banco Nación Argentina.
- Suspensión: TotyLabs podrá suspender el acceso tras 30 días de mora, previa notificación.
- Impuestos: cada parte asume los impuestos correspondientes a su jurisdicción.

## 7. Renovación

Renovación:

- El contrato se renueva automáticamente por períodos iguales al contratado.
- Preaviso de no renovación: 30 días antes del vencimiento.
- Actualización de precios: TotyLabs podrá ajustar precios con 60 días de anticipación al inicio del nuevo período.
- El cliente podrá terminar al final de cualquier período sin penalidad, respetando el preaviso.

## 8. Terminación

Causales:

- Vencimiento sin renovación.
- Incumplimiento material.
- Falta de pago si aplica.
- Riesgo de seguridad.
- Decisión unilateral según preaviso pactado.

Al finalizar la relación, los datos se conservarán según la Política de Retención (5 a 10 años para recibos). El cliente podrá solicitar exportación masiva antes de la eliminación definitiva.

## 9. Seguridad

TotyLabs mantendrá medidas razonables y documentadas para proteger el servicio, incluyendo control de acceso, gestión de secretos, logs, backups, TLS, integridad de documentos y auditoría.

Medidas específicas se detallan en anexos técnicos y pueden variar según plan y configuración.

## 10. Protección de datos

El tratamiento de datos personales y laborales se regirá por la Política de Privacidad y DPA anexos. El Cliente deberá contar con base legal y autorizaciones necesarias para cargar y procesar datos de empleados.

## 11. Responsabilidades del cliente

El Cliente debe:

- Administrar usuarios y permisos.
- Cargar datos correctos y autorizados.
- Revisar matching de recibos.
- Mantener canales de contacto actualizados.
- Cumplir sus obligaciones laborales y de privacidad.
- No cargar archivos maliciosos ni datos innecesarios.

## 12. Responsabilidades de TotyLabs

TotyLabs debe:

- Operar el servicio conforme al contrato.
- Mantener documentación razonable.
- Proteger secretos bajo su control.
- Informar incidentes según DPA y contrato.
- Proveer soporte según plan.
- Mantener controles técnicos proporcionales al servicio.

## 13. Limitación de responsabilidad

La limitación de responsabilidad se rige por las leyes de la República Argentina.

No se afirman garantías absolutas sobre disponibilidad continua, ausencia total de errores, suficiencia legal universal de firmas o cumplimiento normativo sin revisión profesional.

## 14. Propiedad intelectual

TotyLabs conserva propiedad de MyManageRH, código, marca, documentación, diseño, know-how y mejoras generales. El Cliente conserva propiedad de sus datos, documentos, logos y contenido.

## 15. Confidencialidad

Las partes protegerán información confidencial conforme al NDA o cláusula equivalente.

## 16. Anexos

- Anexo 1: SLA 99.5%.
- Anexo 2: DPA.
- Anexo 3: Soporte 24h.
- Anexo 4: Seguridad y arquitectura.
- Anexo 5: Subprocesadores (AWS S3, AWS KMS, Twilio).
- Anexo 6: Retención (5-10 años).

## 17. Jurisdicción

Jurisdicción y ley aplicable: Argentina.
