# Plan de implementación: firma electrónica de legajos

## Objetivo

Permitir que una empresa envíe el PDF del legajo de un empleado para su firma electrónica. El empleado confirma su CUIL, firma con la firma que ya tiene registrada en MyManageRH y el sistema aplica el sello a todas las páginas del documento. El legajo firmado queda disponible en el historial de la empresa; en la cuenta del empleado solo se muestra mientras está pendiente.

## Flujo propuesto

1. **Empresa — iniciar envío:** en cada fila de empleados se agrega un menú de tres puntos con la acción **Enviar legajo para firmar**. Se solicita confirmación explícita **¿Enviar? Sí / No**; elegir No no crea solicitudes ni envía correo.
2. **Empresa — crear solicitud:** al confirmar Sí, el servidor valida que el empleado pertenezca a la organización, que tenga email y CUIL registrado y que exista un PDF de legajo válido. Se guarda una copia inmutable del PDF y su hash para que el documento no cambie mientras se firma.
3. **Notificación:** se envía un correo al empleado informando que tiene un legajo pendiente y con un enlace personal y expirable. Se reutilizan el servicio de correo y la infraestructura de notificaciones existentes; la entrega usa el transporte configurado (SMTP principal/Gmail de respaldo si está habilitado).
4. **Empleado — revisar y firmar:** aparece una sección **Legajos** en Mis Documentos, con solo solicitudes pendientes. El empleado abre el documento, confirma su CUIL contra el dato registrado en el legajo y firma usando la firma guardada. Si aún no tiene una firma registrada, se lo guía al flujo actual para configurarla.
5. **Aplicar firma y cerrar:** el servidor verifica identidad, pertenencia a la organización, vigencia y estado de la solicitud, y que el PDF conserve su hash. Aplica la misma firma/sello a cada página en una única operación lógica e idempotente. Una vez firmado, el registro deja de aparecer en la cuenta del empleado.
6. **Historial de empresa:** se agrega la pestaña **Legajos** al Hub de Historial. Allí se conserva la solicitud y se puede consultar/descargar el PDF firmado, su estado, fechas y evidencia de firma. La copia firmada no se agrega al historial del empleado.

## Integración con el proyecto

El proyecto ya cuenta con:

- Tabla de empleados y generación del PDF de legajo mediante `GET /api/employees/{id}/record-pdf`.
- Menú y render de empleados en `ui/pages/empresa-empleados/`.
- Hub de historial empresarial en `ui/pages/empresa-historial.js` y documentos del empleado en `ui/pages/empleado-recibos.js`.
- Firma guardada del usuario (`user_signatures`), captura/reutilización de firma en `ui/pages/sign.js` y motor PDF en `modules/digital_signature.py`.
- Solicitudes con token y flujo de firma para recibos, notificaciones y servicio de correo.

El flujo existente de solicitudes está acoplado a recibos: la solicitud se asocia a recibos y su aceptación actual procesa y actualiza esos registros. Por eso, no conviene registrar un legajo como recibo ni reutilizar sin cambios un endpoint que altere el estado de recibos. Se debe compartir/reutilizar el motor de PDF, la firma almacenada y los mecanismos comunes de seguridad, pero dar al legajo su propio registro y ciclo de vida.

## Cambios previstos por capa

### Persistencia y migración

- Crear una entidad de solicitud/documento de legajo firmado, con organización, empleado, estado (`pending`, `signed`, `expired`/`cancelled` según el flujo acordado), referencias a PDF original y firmado, hash de cada versión, timestamps y datos mínimos de evidencia.
- Guardar el snapshot del PDF en storage controlado al crear la solicitud. No regenerar el legajo al firmar: debe firmarse exactamente lo que recibió el empleado.
- Registrar actor/emisor, firmante, IP, user-agent, hash de la firma utilizada y resultado de la operación según las prácticas actuales de auditoría.
- Mantener una única solicitud pendiente activa por empleado y legajo; una nueva emisión debe ser una acción explícita y auditable, no duplicar solicitudes al reintentar.

### API y backend

- Agregar un endpoint autenticado de empresa para crear la solicitud. Autorizar por organización/rol y validar email, CUIL y PDF.
- Emitir token aleatorio de un solo uso, persistiendo solo su hash y expiración. Reutilizar el patrón existente de tokens de firma, sin exponer tokens en listados.
- Agregar endpoints para listar legajos pendientes del empleado, consultar/visualizar el PDF solicitado y aceptar la firma.
- En aceptación, exigir que el CUIL ingresado coincida con el CUIL registrado para ese empleado; no aceptar el valor ingresado como sustituto si falta el dato registrado. Comparar valores normalizados y no devolver el CUIL completo en errores/logs.
- Validar que el usuario autenticado corresponda al empleado de la solicitud, dentro de la misma organización. Aplicar bloqueo/idempotencia para impedir firmas dobles o carreras.
- Extender el motor de firma solo en lo necesario para aceptar el PDF snapshot del legajo y generar el sello en todas las páginas. Finalizar en forma atómica: PDF firmado y verificado antes de marcar la solicitud como firmada.
- Ante fallo del correo, la firma o la persistencia, informar el error y conservar un estado recuperable; no presentar la operación como exitosa. Usar la infraestructura existente de notificaciones/outbox si corresponde.

### Interfaz

- **Empleados de empresa:** incorporar el menú de tres puntos en cada fila y el diálogo Sí/No. Mostrar confirmación de envío y errores del servidor; deshabilitar temporalmente la acción para evitar doble envío.
- **Cuenta del empleado:** sumar la pestaña **Legajos**, separada de Recibos/Fondo de Desempleo/Varios. Mostrar únicamente legajos pendientes, con vista previa, estado y acción **Firmar ahora**.
- **Firma:** aprovechar la firma almacenada y la confirmación de CUIL. La pantalla debe explicar que una sola acción firma el documento completo y mostrar el PDF entero antes de confirmar.
- **Historial de empresa:** sumar **Legajos** como categoría del Hub, con pendientes y firmados, filtros/identificación del empleado y acceso al PDF. No agregar legajos firmados a la respuesta/listado de documentos del empleado.

### Documentación y pruebas

- Actualizar la referencia de API y la documentación del modelo de firmas para distinguir el flujo de legajos del de recibos.
- Agregar pruebas de autorización multiempresa, CUIL correcto/incorrecto/no registrado, token vencido o reutilizado, reintentos/idempotencia, envío fallido, integridad del PDF y ausencia del legajo firmado en el historial del empleado.
- Probar PDFs de una y varias páginas para comprobar que todas reciben el sello y que el archivo final puede abrirse y verificarse.
- Añadir pruebas de interfaz para confirmación Sí/No, estados pendientes/firmados y visibilidad distinta en ambas cuentas.

## Criterios de aceptación

- No se envía correo ni se crea una solicitud si la empresa elige No.
- Al elegir Sí se crea una solicitud asociada al empleado correcto y se envía el correo a su dirección registrada.
- Solo el empleado asociado puede consultar y firmar su solicitud; el CUIL debe coincidir con el registrado.
- La firma almacenada se aplica a todas las páginas del PDF snapshot; una solicitud no puede firmarse dos veces.
- Antes de firmar, el legajo aparece como pendiente en la cuenta del empleado. Después de firmar desaparece de esa cuenta.
- El legajo y su versión firmada se conservan en el historial de la empresa, con estado y evidencia verificables.
- Los flujos existentes de firma de recibos conservan su comportamiento.

## Secuencia sugerida

1. Definir la entidad y migración; implementar almacenamiento inmutable y creación segura de solicitudes.
2. Añadir endpoints de consulta, vista previa y firma, reutilizando el motor existente sin acoplar el legajo al estado de recibos.
3. Incorporar el envío de correo y manejar expiración, errores y reintentos.
4. Añadir las acciones de empresa, la pestaña Legajos del empleado y la pestaña Legajos del historial de empresa.
5. Completar pruebas de backend e interfaz, ejecutar migraciones en entorno de prueba y verificar regresión de firma de recibos.

## Decisiones aplicadas

- **Origen del PDF:** se genera el legajo con los datos vigentes al enviarlo y se conserva una copia inmutable cifrada; no se regenera al firmar.
- **Nueva solicitud:** se bloquea un segundo envío mientras haya una solicitud pendiente. Si vence o falla el envío del correo, la solicitud pasa a un estado no pendiente y la empresa puede iniciar un envío nuevo.
- **Firma guardada:** se reutiliza la firma activa del empleado. El CUIL y la confirmación final se solicitan en cada firma; si falta la firma guardada, primero debe configurarse desde Mi Perfil.
- **Estados empresariales:** se conservan los estados pendiente, firmado, vencido y cancelado. El historial permite ver el snapshot enviado y, una vez firmado, el PDF firmado.

La firma visual existente y los controles técnicos del sistema no sustituyen una revisión legal de la validez y evidencia requerida para el uso contractual de legajos.
