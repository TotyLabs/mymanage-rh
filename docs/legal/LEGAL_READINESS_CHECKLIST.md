# Legal Readiness Checklist - MyManageRH

## Aviso legal

Este documento es una base operativa y debe ser revisado por un profesional legal antes de uso contractual.

## 1. Propósito

Este checklist define los mínimos legales y de compliance que deben cerrarse antes de vender, contratar o operar MyManageRH con datos reales de clientes enterprise.

## 2. Bloqueantes antes de uso contractual

| Bloqueante | Estado | Responsable |
| --- | --- | --- |
| Jurisdicción y ley aplicable definidas | DEFINIDA: República Argentina (CABA) | Legal |
| DPA adaptado al cliente y jurisdicción | BASE OPERATIVA LISTA (requiere revisión legal por cliente) | Legal/Privacidad |
| Política de Privacidad publicada o incorporada al contrato | BASE OPERATIVA LISTA (requiere revisión legal) | Legal/Privacidad |
| Subprocesadores listados | DEFINIDOS: AWS, Twilio, Google/SMTP | Legal/Operaciones |
| Transferencias internacionales evaluadas | DOCUMENTADAS: AWS (US-East), CCE aplicables | Legal/Privacidad |
| Base legal del tratamiento definida | DOCUMENTADA: Ley 25.326, contrato laboral, consentimiento | Cliente/Legal |
| Retención de recibos, evidencia y logs definida | DEFINIDA: 5-10 años recibos, 1 año logs | Legal/Compliance |
| SLA y soporte definidos | DEFINIDOS: 99.5% mensual, soporte hábil, respuesta <24h | Dirección/Operaciones |
| RTO/RPO definidos | DEFINIDOS: RTO 4h, RPO 15min | Operaciones |
| Modelo de cifrado en reposo definido | DEFINIDO: AES-256-GCM envelope encryption con AWS KMS | Seguridad/Legal |
| Procedimiento de incidentes y notificación definido | DOCUMENTADO: <72h, DR runbook completo | Seguridad/Legal |
| Titularidad de IP y marca clarificada | `[PENDIENTE de registro INPI y cesión formal]` | Dirección/Legal |

## 3. Documentos mínimos para cliente enterprise

- `legal/SAAS_AGREEMENT.md` adaptado y aprobado.
- `legal/DPA.md` adaptado y aprobado.
- `legal/PRIVACY.md` publicado o incorporado por referencia.
- Anexo de SLA: 99.5% mensual (MVP), RTO 4h, RPO 15min.
- Anexo de soporte: email y portal, hábil L-V 09:00-18:00 ART, respuesta <24h.
- Anexo de subprocesadores: AWS (Infra/S3/KMS), Twilio (SMS/OTP), Google/SendGrid (Email).
- Anexo de seguridad con alcance real de controles.
- Procedimiento de offboarding y retención.

## 4. Riesgos si se vende sin cerrar estos puntos

- Tratamiento de datos laborales sin base legal clara.
- DPA insuficiente ante cliente enterprise.
- Exposición por incidentes sin plazos de notificación definidos.
- Disputa por valor probatorio de firma.
- Ambigüedad sobre responsabilidad por datos ingresados.
- SLA prometido comercialmente sin capacidad operativa respaldada.
- Auditoría fallida por controles documentados pero no implementados.

## 5. Criterio de salida

MyManageRH puede considerarse legalmente listo para contratación enterprise sólo cuando:

- Los placeholders legales críticos fueron reemplazados por definiciones aprobadas.
- Legal validó jurisdicción, privacidad, DPA y responsabilidad.
- Operaciones validó SLA, soporte, RTO/RPO y DR.
- Seguridad validó cifrado, secretos, multi-tenancy, auditoría y respuesta a incidentes.
- Dirección aprobó pricing, planes, alcance y anexos comerciales.
