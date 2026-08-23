# Data Processing Agreement - MyManageRH

## Aviso legal

Este documento es una base operativa y debe ser revisado por un profesional legal antes de uso contractual.

## 1. Partes

Cliente: `[DEFINIR CLIENTE]`.

Proveedor/Encargado: TotyLabs, operador de MyManageRH.

## 2. Roles de tratamiento

Salvo acuerdo distinto:

- El Cliente actúa como Responsable del Tratamiento respecto de datos de empleados, recibos y datos laborales.
- TotyLabs/MyManageRH actúa como Encargado del Tratamiento, procesando datos conforme a instrucciones documentadas del Cliente.

Adecuar terminología a la legislación de la República Argentina (Ley 25.326).

## 3. Objeto y duración

El tratamiento tiene por objeto prestar el servicio SaaS de gestión de recibos, firma digital, evidencia, auditoría, notificaciones e integraciones.

Duración: vigencia del contrato SaaS y período de retención (5 a 10 años para recibos).

## 4. Categorías de datos

- Datos identificatorios: nombre, DNI, CUIL, email, teléfono.
- Datos laborales: legajo, puesto, fechas, estado, datos sindicales si se cargan.
- Datos salariales: recibos, remuneraciones, conceptos y comprobantes de pago.
- Datos bancarios: CBU, banco, cuenta si se cargan.
- Datos de firma: firma visual, token hasheado, OTP, timestamp, IP, user-agent, hash de PDF.
- Documentos: DNI, PDFs, documentos de RRHH si se cargan.
- Datos técnicos: logs, eventos, auditoría y webhooks.

## 5. Finalidad

- Operar el servicio MyManageRH.
- Gestionar recibos y firmas.
- Verificar identidad de firmantes.
- Generar evidencia y auditoría.
- Enviar notificaciones.
- Mantener seguridad, integridad y disponibilidad.
- Cumplir instrucciones del Cliente.

## 6. Medidas técnicas y organizativas

Medidas actuales o esperadas:

- Autenticación y control de roles.
- Sesiones/tokens hasheados.
- Rate limiting y bloqueo por intentos fallidos.
- Scoping por organización y RLS si se aplica.
- TLS 1.2/1.3 en producción.
- Hash SHA-256 de documentos.
- Inmutabilidad lógica de evidencia.
- Redacción de PII en logs.
- Backups cifrados mediante AWS Backup (KMS).
- Gestión de secretos fuera del código.
- Cifrado en reposo AES-256 o equivalente según proveedor.
- Cifrado real de archivos sensibles pendiente si se almacenan DNIs en producción.

## 7. Subprocesadores

Subprocesadores autorizados: AWS (Infra), Twilio (SMS), SendGrid/Google (Email).

TotyLabs deberá informar cambios materiales de subprocesadores según contrato y permitir objeciones razonables si la ley o acuerdo lo requiere.

## 8. Incidentes

TotyLabs notificará al Cliente incidentes de seguridad que afecten datos personales sin demora indebida y dentro de las 72 horas, aportando información razonable sobre naturaleza, alcance, medidas adoptadas y próximos pasos.

## 9. Retención y eliminación

Al terminar el servicio, TotyLabs deberá devolver, exportar, anonimizar o eliminar datos según instrucciones del Cliente, restricciones legales y política de retención (5-10 años).

Backups pueden conservarse hasta expiración del ciclo de backup, siempre protegidos y sin restauración productiva salvo necesidad autorizada.

## 10. Auditorías

TotyLabs deberá poner a disposición documentación razonable sobre medidas técnicas y organizativas. Auditorías externas o del Cliente deberán coordinarse, proteger seguridad de otros clientes y respetar confidencialidad.

## 11. Confidencialidad

Personal y contratistas con acceso a datos deberán estar sujetos a obligaciones de confidencialidad y acceso mínimo necesario.

## 12. Transferencias internacionales

Transferencias internacionales: AWS (EE.UU. / Irlanda), bajo Cláusulas Contractuales Estándar.

Deben documentarse mecanismos de transferencia, salvaguardas y subprocesadores involucrados.

## 13. Anexos

- Anexo A: Detalle de datos tratados.
- Anexo B: Medidas técnicas y organizativas.
- Anexo C: Subprocesadores.
- Anexo D: Retención y eliminación.
- Anexo E: Contactos de seguridad y privacidad.
