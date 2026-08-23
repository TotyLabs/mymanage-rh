# Política de Privacidad - MyManageRH

## Aviso legal

Este documento es una base operativa y debe ser revisado por un profesional legal antes de uso contractual.

## 1. Responsable y servicio

MyManageRH es un SaaS B2B operado por TotyLabs para gestión de recibos de sueldo, firma digital, evidencia y auditoría. En la mayoría de los escenarios B2B, la organización cliente determina finalidades y medios esenciales del tratamiento, y TotyLabs procesa datos siguiendo instrucciones del cliente.

Definiciones finales sujetas a las leyes de la República Argentina (Ley 25.326) y al DPA aplicable.

## 2. Datos recolectados

El sistema puede tratar:

- Nombre y apellido.
- DNI.
- CUIL/CUIT.
- Email.
- Teléfono.
- Dirección.
- Datos de legajo.
- Datos bancarios, por ejemplo CBU.
- Recibos de sueldo y salarios.
- Firmas visuales.
- Evidencia de firma.
- IP, user-agent, timestamps y actividad.
- Credenciales hasheadas y sesiones hasheadas.
- Documentos de identidad si el cliente los carga.

## 3. Finalidad del tratamiento

Los datos se tratan para:

- Administrar empleados y usuarios.
- Cargar, asociar, firmar y consultar recibos.
- Verificar identidad en flujos de firma.
- Generar evidencia técnica y auditoría.
- Enviar emails, OTP o notificaciones.
- Operar webhooks e integraciones.
- Cumplir obligaciones contractuales, legales u operativas del cliente.
- Prevenir fraude, abuso y accesos no autorizados.

## 4. Base legal

Base legal: cumplimiento de obligaciones legales laborales, ejecución de contrato de trabajo y consentimiento del titular cuando corresponda.

Posibles bases a evaluar por asesoría legal: ejecución contractual, cumplimiento de obligación legal, interés legítimo, consentimiento u otra base aplicable.

## 5. Protección de datos

Controles técnicos documentados:

- Autenticación y roles.
- Sesiones y tokens hasheados.
- Scoping por organización.
- Logs con redacción de PII.
- Hashes SHA-256 para integridad documental.
- TLS 1.2/1.3 requerido en producción.
- Cifrado en reposo mediante AWS S3 y AWS KMS.
- PKI vault con AES-256-GCM para llaves cuando se usa.

Limitación actual: el módulo de cifrado de archivos DNI está documentado como placeholder y debe completarse antes de producción enterprise si se almacenan documentos de identidad.

## 6. Acceso restringido

El acceso a datos queda restringido a usuarios autorizados por organización, personal operativo autorizado de TotyLabs y subprocesadores necesarios para prestar el servicio.

## 7. Retención

Retención: Recibos y evidencia (5-10 años), Logs (1 año).

La retención debe considerar recibos laborales, evidencia de firma, logs técnicos, backups, obligaciones legales y terminación contractual.

## 8. Derechos ARCO y derechos del titular

Según la Ley 25.326 de Protección de Datos Personales (Argentina), los titulares pueden tener derechos de acceso, rectificación, cancelación, oposición u otros derechos equivalentes.

En un contexto B2B, TotyLabs podrá derivar solicitudes al cliente cuando éste actúe como responsable del tratamiento.

## 9. Transferencias a terceros y subprocesadores

Subprocesadores: Amazon Web Services (Infraestructura), Twilio (SMS), Google/SMTP (Email).

Posibles categorías:

- Hosting o infraestructura.
- Email transaccional SMTP.
- SMS/OTP.
- Storage o backup.
- TSA, HSM, KMS o proveedor PKI.
- Monitoreo y logging.

## 10. Transferencias internacionales

Transferencias internacionales: AWS (Regiones US-East o similares), protegidas por cláusulas contractuales estándar y medidas técnicas de cifrado (KMS).

## 11. Incidentes

Ante incidentes de seguridad o privacidad, TotyLabs deberá activar su procedimiento interno, preservar evidencia, mitigar impacto, comunicar al cliente según contrato y colaborar en notificaciones regulatorias si corresponden.

Plazos de notificación: < 72 horas desde la detección.

## 12. Contacto de privacidad

Contacto de privacidad: privacy@mymanagerh.com

## 13. Revisión legal pendiente

Esta política debe ser revisada y adaptada por profesional legal antes de publicación o incorporación contractual.
