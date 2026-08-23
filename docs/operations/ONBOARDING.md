# Onboarding y manual de usuario - MyManageRH

## 1. Propósito

Esta guía acompaña a equipos de RRHH y administradores durante el primer uso de MyManageRH. Evita detalles técnicos salvo cuando son necesarios para operar correctamente.

## 2. Alta de organización

1. Ingresar a la URL provista por TotyLabs: `https://app.mymanagerh.com` (o URL de staging provista durante implementación).
2. Crear la organización con nombre legal, CUIT, email de contacto y usuario administrador.
3. Verificar el email si el sistema lo solicita.
4. Cargar logo de la organización si corresponde.
5. Cargar o configurar firmantes autorizados del empleador.

Responsable: administrador de la organización o equipo de implementación.

## 3. Alta de empleados

Opciones:

- Alta manual desde la pantalla de empleados.
- Importación masiva desde archivo Excel/TXT según plantilla acordada.
- Alta liviana cuando el flujo del empleado completa datos pendientes.

Datos mínimos recomendados:

- Nombre y apellido.
- DNI.
- CUIL.
- Email.
- Estado laboral.
- Legajo o identificador interno si existe.

Buenas prácticas:

- Revisar duplicados antes de importar.
- Confirmar emails antes de enviar recibos.
- Mantener el estado `activo` sólo para empleados vigentes.
- No cargar documentos de identidad si no existe necesidad operativa y base legal.

## 4. Carga de recibos

1. Ir al módulo de recibos o lotes.
2. Seleccionar período, por ejemplo `Marzo 2026`.
3. Cargar el PDF de recibos.
4. Esperar procesamiento.
5. Revisar cantidad procesada, cantidad asociada automáticamente y pendientes.

Si un recibo queda pendiente, RRHH debe resolver el matching antes de iniciar la firma.

## 5. Revisión de datos

Antes de firmar:

- Confirmar que cada recibo pertenece al empleado correcto.
- Revisar período y organización.
- Verificar que el PDF se ve correctamente.
- Revisar pendientes de matching.
- Validar que el empleado tenga email correcto.

## 6. Firma del empleador

1. Seleccionar recibos listos para firma del empleador.
2. Elegir firmante de empresa autorizado.
3. Confirmar la firma.
4. Esperar el resultado.
5. Verificar que el estado cambia a pendiente de firma del empleado, si aplica.

No firmar recibos con matching dudoso o datos incompletos.

## 7. Firma del empleado

1. El empleado recibe link o accede desde su portal.
2. Revisa el recibo.
3. Completa verificación OTP si se solicita.
4. Firma en pantalla o usa firma guardada si está permitido.
5. Acepta o rechaza.
6. El sistema registra evidencia y actualiza el estado.

Si el empleado rechaza, RRHH debe revisar el motivo y determinar próximos pasos fuera del sistema o mediante procedimiento interno.

## 8. Consulta de recibos

RRHH puede consultar:

- Pendientes de matching.
- Pendientes de firma del empleador.
- Pendientes de firma del empleado.
- Firmados.
- Rechazados.
- Historial por empleado o período.

El empleado sólo debe ver sus propios recibos.

## 9. Descarga de evidencia

Cuando un recibo está firmado, RRHH o un auditor autorizado puede descargar o consultar evidencia según permisos:

- PDF final firmado.
- Verificación por sello QR.
- Eventos de firma.
- Hashes y timestamps.
- Evidencia de identidad cuando corresponda.

No compartir evidencia con terceros sin autorización del cliente y revisión de privacidad.

## 10. Errores frecuentes

| Error | Qué significa | Qué hacer |
| --- | --- | --- |
| Recibo pendiente de matching | No se identificó empleado automáticamente. | Asociar manualmente con el empleado correcto. |
| Email inválido | El empleado no recibirá notificación. | Corregir email y reenviar. |
| Token vencido | El link de firma expiró. | Generar nuevo token o reenviar invitación. |
| OTP incorrecto | Verificación fallida. | Reintentar dentro del límite permitido. |
| Recibo ya firmado | No se puede volver a firmar. | Consultar evidencia o abrir soporte si hay disputa. |
| PDF inválido | El archivo no cumple formato esperado. | Cargar un PDF válido. |
| Error de firma | Falló procesamiento o PKI. | Escalar a soporte. |

## 11. Buenas prácticas para RRHH

- Hacer una carga de prueba con datos ficticios antes del primer envío real.
- Revisar todos los pendientes de matching.
- Mantener firmantes de empresa actualizados.
- No reutilizar usuarios entre personas.
- Desactivar empleados y usuarios que ya no correspondan.
- Descargar evidencia sólo cuando sea necesario.
- No enviar recibos por canales no autorizados.
- Reportar cualquier acceso sospechoso.

## 12. Checklist de primer uso

- [ ] Organización creada.
- [ ] Usuario administrador verificado.
- [ ] Logo cargado si aplica.
- [ ] Firmante de empresa creado y probado.
- [ ] Empleados cargados y revisados.
- [ ] Emails de empleados validados.
- [ ] PDF de prueba procesado.
- [ ] Matching revisado.
- [ ] Firma de empleador probada.
- [ ] Firma de empleado probada con usuario ficticio.
- [ ] Evidencia descargada y revisada.
- [ ] Procedimiento de soporte comunicado a RRHH.
