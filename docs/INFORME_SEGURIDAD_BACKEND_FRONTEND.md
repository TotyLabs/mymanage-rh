# Informe de seguridad: backend y frontend

**Fecha de revisión:** 25 de octubre de 2026
**Alcance:** revisión estática del código y configuración del backend y frontend presentes en este workspace.
**Estado:** revisión inicial y seguimiento de remediaciones de código; la validación del entorno desplegado sigue pendiente.

## 1. Resumen ejecutivo

Se observaron controles útiles —hash de contraseñas con bcrypt, cookies `HttpOnly`/`SameSite`, consultas parametrizadas, cifrado AES-GCM disponible y reglas de ignorado para secretos y datos locales—, pero hay debilidades que requieren atención prioritaria:

1. La configuración local indica modo de producción, pero el cifrado general de documentos está desactivado por defecto. El proveedor Vault configurado no cifra archivos por sí solo mientras `APP_ENCRYPTION_ENABLED` permanezca falso.
2. El inicio corporativo devuelve el token de sesión en el cuerpo JSON y el frontend lo guarda en `localStorage`, haciendo que el token sea accesible a JavaScript.
3. Los endpoints de restablecimiento aceptan un OTP activo del usuario sin comprobar que pertenezca al contexto de restablecimiento.
4. Los OTP son de seis dígitos y sus hashes almacenados son SHA-256 sin clave, lo que permite probar el espacio reducido de códigos offline ante una lectura de la base de datos.
5. El contador de intentos fallidos de OTP no cuenta códigos incorrectos, porque solo se incrementa después de encontrar una coincidencia.
6. Hay archivos locales con nombres/extensiones que corresponden a secretos, respaldos y datos laborales. Las reglas de Git los ignoran y la revisión de archivos versionados no encontró coincidencias en las categorías comprobadas, pero su presencia local sigue siendo un riesgo operativo.

No se confirmó una vulnerabilidad crítica en esta revisión estática. Se implementaron correcciones para varios hallazgos de código; el estado posterior figura en la sección 7. La revisión no equivale a una certificación, pentest ni confirmación del estado del servidor desplegado.

## 2. Alcance y límites

### Revisado

- Configuración central, autenticación, sesiones, restablecimiento de credenciales y verificación OTP.
- Enrutamiento y middleware de CORS/CSRF.
- Servicio de cifrado y controles de acceso a documentos/legajos.
- Código cliente de autenticación, almacenamiento de sesión y HTML base.
- Reglas de `.gitignore`, nombres de archivos locales y nombres de archivos versionados.
- Configuración Nginx incluida en el repositorio.

### No realizado

- No se inspeccionaron valores de secretos ni contenido de archivos locales sensibles.
- No se accedió al VPS, al balanceador, a la base de datos, a Redis, a Vault/OpenBao ni a otros servicios de producción.
- No se ejecutaron pruebas de penetración, DAST, SAST especializado, auditoría de dependencias ni pruebas sobre un entorno desplegado.
- La ausencia de patrones comunes en los archivos versionados no demuestra por sí sola que toda la historia Git, todos los logs o todos los respaldos externos estén libres de secretos.

Por lo tanto, cuando este informe se refiere a la configuración `.env`, se refiere únicamente al snapshot local observado, no a una lectura del entorno de producción.

## 3. Hallazgos priorizados

| ID | Severidad | Área | Confianza | Estado |
|---|---|---|---:|---|
| SEC-01 | 🔴 Alta | Cifrado de documentos almacenados | 9/10 | Activado por defecto para nuevas escrituras en producción; archivos históricos y despliegue pendientes |
| SEC-02 | 🔴 Alta | Exposición de token de sesión al frontend | 9/10 | Corregido en login y flujo OTP; requiere despliegue |
| SEC-03 | 🔴 Alta | OTP sin validación del propósito en recuperación | 10/10 | Corregido con contextos estrictos; requiere despliegue |
| SEC-04 | 🔴 Alta | Hash de OTP susceptible a búsqueda offline | 9/10 | Corregido con HMAC ligado al secreto de aplicación; requiere despliegue |
| SEC-05 | 🟠 Media | Intentos fallidos de OTP no contabilizados | 10/10 | Corregido con contador DB atómico; requiere despliegue |
| SEC-06 | 🟠 Media | Secretos y datos laborales presentes en el workspace | 8/10 | `.env` tiene permisos 0600; revisar/retener artefactos locales sigue pendiente |
| SEC-07 | 🟠 Media | Configuración Nginx incluida no termina TLS | 8/10 | Pendiente confirmar/activar TLS en el ingress real |
| SEC-08 | 🟡 Baja | Enumeración de cuentas en recuperación de contraseña | 10/10 | Corregido con respuesta genérica; requiere despliegue |
| SEC-09 | 🟡 Baja | Validación de origen CSRF permisiva | 8/10 | Corregido con comparación exacta; requiere despliegue |
| SEC-10 | 🟡 Baja | Encabezados de seguridad/CSP no definidos en los archivos revisados | 7/10 | Encabezados básicos y CSP Report-Only agregados; CSP de aplicación aún pendiente |
| SEC-11 | ⚪ Baja | Documentación de KMS incongruente con la configuración local | 8/10 | Documentación alineada; validar proveedor de producción |

### SEC-01 — Cifrado general de documentos almacenados desactivado

**Evidencia:** [`config.py`](../config.py#L221) establece `APP_ENCRYPTION_ENABLED` en `false` si no se define. El guardado de documentos de empresa y recibos solo cifra los archivos si esa bandera está activa ([`services/document_service.py`](../services/document_service.py#L118), [`api/receipts.py`](../api/receipts.py#L176)). En el snapshot `.env` local observado, el modo está configurado como producción, el proveedor es Vault y `APP_ENCRYPTION_ENABLED` no está definido; por lo tanto, se aplica el valor predeterminado desactivado.

**Impacto:** archivos laborales que pasan por esos flujos pueden quedar en claro en el almacenamiento del servidor o en sus respaldos. Configurar Vault Transit como proveedor no implica que todos los archivos se cifren automáticamente. El flujo de firma de legajos aplica cifrado explícito, pero no sustituye el cifrado general de los demás documentos.

**Recomendación:** definir explícitamente `APP_ENCRYPTION_ENABLED=true` después de verificar migraciones, permisos/políticas de Vault, recuperación y compatibilidad con archivos existentes. Antes del cambio, probar lectura, descarga, rotación y recuperación de backups en staging. Auditar archivos existentes para determinar cuáles requieren migración/cifrado; no asumir que activar la bandera cifra datos históricos.

### SEC-02 — Token de sesión accesible desde JavaScript

**Evidencia:** el endpoint de acceso corporativo establece una cookie `HttpOnly`, pero también devuelve `session_token` en el JSON ([`api/auth.py`](../api/auth.py#L198), [`api/auth.py`](../api/auth.py#L209)). El frontend lo persiste en `localStorage` ([`ui/pages/login.js`](../ui/pages/login.js#L92)); el cliente reutiliza ese valor como credencial para las solicitudes ([`ui/common.js`](../ui/common.js#L5)).

**Impacto:** cualquier XSS o script de terceros ejecutado en el mismo origen puede leer y exfiltrar el bearer token. El atributo `HttpOnly` de la cookie no protege la copia guardada en `localStorage`. La duración predeterminada de sesión es de siete días ([`config.py`](../config.py#L159)), aumentando el tiempo de uso de un token robado.

**Recomendación:** adoptar la cookie `HttpOnly`, `Secure` y `SameSite` como único mecanismo de sesión del navegador; dejar de devolver el token en el cuerpo de login y quitar el almacenamiento/lectura en `localStorage`. Revisar clientes API legítimos y compatibilidad antes de retirar el modo bearer. Al migrar, invalidar sesiones existentes que hayan quedado expuestas.

### SEC-03 — El restablecimiento no exige un OTP del propósito correcto

**Evidencia:** los endpoints de restablecimiento llaman `verify_code` proporcionando email y código, pero no el contexto esperado ([`api/password_reset.py`](../api/password_reset.py#L131), [`api/password_reset.py`](../api/password_reset.py#L190)). La consulta de códigos activos filtra por usuario, vigencia y estado, pero no por `context` ([`services/verification_service.py`](../services/verification_service.py#L154)). La validación flexible también compara códigos sin comprobar el propósito de la operación ([`services/verification_service.py`](../services/verification_service.py#L171)).

**Impacto:** cualquier OTP activo asociado al mismo usuario —por ejemplo, uno generado para registro o firma— puede resultar válido para restablecer su contraseña o clave corporativa. Esto mezcla factores y propósitos distintos y puede habilitar una recuperación usando un código recibido por un canal que no estaba previsto para esa recuperación.

**Recomendación:** hacer obligatorio un parámetro de contexto en la API de verificación y filtrar la consulta por él. El restablecimiento de contraseña debe aceptar solo `password_reset`; la clave corporativa debe tener un propósito separado. Mantener además el vínculo con usuario, destino/canal y, cuando aplique, transacción o solicitud concreta.

### SEC-04 — OTP de baja entropía almacenados con SHA-256 sin clave

**Evidencia:** el OTP tiene seis dígitos ([`services/verification_service.py`](../services/verification_service.py#L24)). Se guarda `code_hash = hash_token(raw_code)` y un `context_hash` ([`services/verification_service.py`](../services/verification_service.py#L113)). `hash_token` es SHA-256 simple, sin clave ([`payroll_core.py`](../payroll_core.py#L390)). Para códigos sin contexto adicional, `context_hash` se construye con campos nulos más el OTP ([`services/verification_service.py`](../services/verification_service.py#L25)).

**Impacto:** con acceso de lectura a una tabla o backup, un atacante puede probar el espacio de un millón de códigos fuera de línea y recuperar OTP todavía vigentes. SHA-256 no es adecuado para proteger un secreto de tan baja entropía frente a búsqueda exhaustiva.

**Recomendación:** almacenar un HMAC del código usando una clave secreta independiente de la base de datos, incluir el propósito y un salt/identificador por registro, y limitar estrictamente la vida útil. La verificación debería usar comparación constante y consumir el código de forma atómica. Si hubo exposición de la base o backups, invalidar OTP activos.

### SEC-05 — Los intentos incorrectos de OTP no incrementan el contador

**Evidencia:** los códigos candidatos se buscan comparando el hash de contexto con el código recibido; si no hay coincidencia, la función retorna antes de comprobar/incrementar `attempts` ([`services/verification_service.py`](../services/verification_service.py#L171), [`services/verification_service.py`](../services/verification_service.py#L187)). El contador se incrementa únicamente después de encontrar una coincidencia ([`services/verification_service.py`](../services/verification_service.py#L201)).

**Impacto:** el máximo de cinco intentos no limita los códigos incorrectos. Los endpoints tienen rate limit por IP, pero eso no reemplaza un límite acumulativo por cuenta/OTP y puede ser insuficiente en despliegues distribuidos o frente a solicitudes desde varias IP.

**Recomendación:** contabilizar cada intento fallido de forma atómica por registro y por cuenta, bloquear/invalidar el OTP al alcanzar el máximo, y sumar límites por IP y por destino. En producción, garantizar que el rate limiter use almacenamiento compartido (por ejemplo Redis) y no depender del fallback en memoria entre workers.

### SEC-06 — Archivos potencialmente sensibles presentes en el workspace local

**Evidencia:** el inventario del workspace contiene archivos locales bajo `.env`, `certs/`, `backup/`, `logs/` y hojas de cálculo; los nombres/extensiones sugieren credenciales, llaves, respaldos de base y datos de empleados. No se inspeccionó su contenido. `.gitignore` los cubre mediante reglas para secretos, certificados, respaldos, logs, SQL y hojas de cálculo ([`.gitignore`](../.gitignore#L6), [`.gitignore`](../.gitignore#L24), [`.gitignore`](../.gitignore#L72), [`.gitignore`](../.gitignore#L83)).

**Impacto:** el ignorado de Git evita el `git add` accidental normal, pero no protege esos archivos frente a otros usuarios del host, malware, backups del equipo o copias manuales. Un archivo ignorado también puede incluirse manualmente con `git add -f`.

**Recomendación:** confirmar propietario y permisos mínimos en archivos sensibles; mover secretos a un gestor de secretos y datos/respaldos a almacenamiento cifrado con acceso restringido. Eliminar o archivar de manera segura los artefactos obsoletos una vez validada su retención. Rotar cualquier secreto que pudiera haberse copiado a ubicaciones no confiables. Mantener el escaneo también sobre historia Git y artefactos de CI.

**Estado Git observado:** no se encontraron rutas versionadas con las extensiones/nombres de categorías sensibles examinadas; un escaneo básico de patrones comunes sobre fuentes versionadas tampoco encontró coincidencias. Esto no cubre todos los formatos de secretos ni demuestra el estado de la historia completa.

### SEC-07 — La configuración Nginx incluida no configura TLS

**Evidencia:** [`deployment/nginx/payroll_nginx.conf`](../deployment/nginx/payroll_nginx.conf#L1) declara únicamente `listen 80` y reenvía al backend por HTTP local; no incluye listener HTTPS, redirección a HTTPS ni configuración de certificados.

**Impacto:** si este archivo es el punto de entrada directo desde Internet, las credenciales, cookies y datos de nómina podrían transmitirse sin cifrado en el tramo cliente-servidor. No se verificó si un balanceador o proxy externo termina TLS antes de Nginx.

**Recomendación:** confirmar el recorrido real de red y que TLS se termine en un componente gestionado y obligatorio, con redirección HTTP→HTTPS y protocolos/cifrados actuales. Si existe un proxy externo, preservar de forma confiable el esquema original y restringir quién puede enviar `X-Forwarded-*`; no confiar esos headers desde clientes directos.

### SEC-08 — Enumeración de cuentas en recuperación de contraseña

**Evidencia:** `forgot-password` devuelve HTTP 404 y un mensaje explícito cuando no existe una cuenta para el correo ([`api/password_reset.py`](../api/password_reset.py#L66)).

**Impacto:** permite confirmar si un correo está registrado. En un sistema laboral, esto facilita recopilación de identidades de empleados/administradores y puede apoyar ataques de phishing.

**Recomendación:** devolver el mismo estado y mensaje genérico exista o no la cuenta, y aproximar los tiempos de respuesta. Mantener rate limits por IP y destino sin revelar cuál se activó.

### SEC-09 — Comparación permisiva de `Origin`/`Referer` en CSRF

**Evidencia:** en producción se usa `startswith(allowed_base)` para validar origen y referer; en desarrollo se aceptan coincidencias por subcadena ([`main.py`](../main.py#L178)). La configuración CORS de producción mantiene una lista más estricta de orígenes ([`main.py`](../main.py#L123)).

**Impacto:** la validación CSRF no compara el origen normalizado como tupla exacta de esquema, host y puerto. Es una defensa en profundidad débil. La configuración CORS y la cookie `SameSite=Strict` reducen el riesgo de un bypass desde navegador; no se demostró un bypass completo en el despliegue real.

**Recomendación:** parsear `Origin` y comparar igualdad exacta con una allowlist normalizada; validar `Referer` con la misma política. En desarrollo, permitir únicamente hosts/puertos explícitos en vez de subcadenas o rangos de red amplios.

### SEC-10 — No se encontraron CSP ni encabezados de endurecimiento

**Evidencia:** el HTML base incluye un script inline y no declara CSP ([`ui/index.html`](../ui/index.html#L31)); el archivo Nginx revisado no agrega encabezados de seguridad. En el backend tampoco se encontró middleware para `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy` o `Permissions-Policy`.

**Impacto:** no hay una política visible de navegador como defensa adicional ante inyección de scripts, carga de recursos externos no previstos o framing. La política CSP requerirá adaptar el script inline y validar las dependencias externas del frontend.

**Recomendación:** desplegar inicialmente CSP en modo `Report-Only`, revisar violaciones y luego aplicar una política con nonce/hash para scripts; evitar `unsafe-inline` como solución permanente. Agregar `X-Content-Type-Options: nosniff`, `Referrer-Policy` y `frame-ancestors`/protección equivalente. Configurar HSTS solo después de verificar que todos los dominios de producción soportan HTTPS.

### SEC-11 — Documentación de KMS no coincide con la configuración observada

**Evidencia:** la documentación describe AWS KMS como raíz de confianza para producción ([`docs/05_SEGURIDAD_Y_FIRMAS.md`](05_SEGURIDAD_Y_FIRMAS.md#L38)), mientras que la configuración `.env` local observada indica proveedor Vault. La guía de instalación permite varios proveedores, pero no fija cuál es el proveedor operativo aprobado.

**Impacto:** una discrepancia sobre proveedor, responsabilidades de rotación, recuperación y controles de acceso puede producir configuraciones incorrectas o declaraciones de seguridad inexactas.

**Recomendación:** documentar el proveedor efectivamente usado en cada entorno, el proceso de autenticación, permisos mínimos, rotación, backups y recuperación. No documentar un proveedor como activo hasta verificarlo en el host desplegado.

## 4. Controles observados favorables

- Las contraseñas se verifican con bcrypt ([`payroll_core.py`](../payroll_core.py#L724)).
- Las sesiones se generan con tokens aleatorios, se guarda su hash y la cookie se configura `HttpOnly`, `SameSite=Strict` y `Secure` cuando el backend está en producción o detecta HTTPS ([`payroll_core.py`](../payroll_core.py#L728), [`api/auth.py`](../api/auth.py#L198)).
- Las consultas revisadas usan parámetros SQL en lugar de concatenar datos de entrada.
- El servicio de cifrado implementa AES-256-GCM con claves de datos y proveedor de KMS; el flujo de legajos cifra explícitamente los archivos de origen y firmados.
- El flujo de firma de legajos revisado comprueba organización/empleado, limita rutas al almacenamiento permitido y verifica el CUIL antes de finalizar la firma.
- `.gitignore` contempla `.env`, claves privadas, certificados, respaldos, logs, dumps de SQL y hojas de cálculo. La revisión de nombres versionados no encontró esas clases de archivos.
- No se mostraron ni copiaron valores del `.env` a este informe.

Estos controles reducen riesgos, pero las correcciones de código no implican cierre operativo ni sustituyen pruebas integrales.

## 5. Plan de despliegue y cierre

### Prioridad inmediata

1. **Código aplicado; despliegue pendiente:** desplegar OTP ligado a operación/recurso, contador de intentos, HMAC y sesiones solo en cookies `HttpOnly`. Solicitar OTP nuevos tras el despliegue porque los códigos vigentes con el formato anterior no serán compatibles.
2. **Configuración aplicada localmente; confirmar por ambiente:** probar Vault/KMS en staging y desplegar el cifrado de nuevas escrituras. Inventariar/migrar archivos históricos solo con respaldo verificable y procedimiento reversible.
3. **Pendiente operativo:** revisar permisos y ubicación de certificados, backups, logs y hojas de cálculo; confirmar si alguna credencial fue expuesta y rotar cuando corresponda.
4. **Pendiente operativo:** confirmar TLS obligatorio en el punto de entrada real, no solo dentro de la red privada.

### Corto plazo

5. **Código aplicado; pendiente observar en staging:** recuperación con respuesta genérica y validación CSRF de origen exacta.
6. **Parcialmente aplicado:** encabezados básicos y CSP Report-Only están agregados. Evaluar reportes y definir una CSP aplicable sin romper recursos válidos.
7. **Documentación alineada al snapshot local; producción pendiente de confirmar:** verificar el proveedor efectivo por ambiente.
8. Ejecutar SAST/secret scanning sobre repositorio e historia, auditoría de dependencias, pruebas de aislamiento multi-tenant y DAST autorizado en staging.

## 6. Criterio de cierre

Antes de considerar cerrada la revisión, verificar en un entorno de staging que:

- La sesión no aparece en JSON, DOM, `localStorage`, URLs ni logs.
- Un OTP emitido para firma/registro no permite restablecer credenciales.
- Cada OTP inválido incrementa el contador y el límite persiste entre workers.
- La recuperación requiere el canal y propósito correctos.
- Los documentos de empresa, recibos y archivos de legajo quedan cifrados en almacenamiento y se restauran correctamente desde backup.
- Orígenes no allowlisted son rechazados por CSRF y CORS.
- El tráfico público redirige a HTTPS y las cookies de sesión llevan `Secure`.
- No hay secretos o datos reales en el árbol Git, historia remota, CI ni artefactos publicados.

## 7. Seguimiento de remediaciones

En este workspace quedaron aplicados cambios para:

- Cifrar por defecto los nuevos archivos sensibles en producción y activar `APP_ENCRYPTION_ENABLED` en el `.env` local. Los documentos históricos no se convierten automáticamente; deben inventariarse y migrarse con respaldo, prueba de lectura y verificación de integridad.
- Dejar de retornar sesiones bearer en JSON y de almacenarlas/usarlas desde `localStorage` o encabezados de frontend; el navegador usa la cookie `HttpOnly`. El token local heredado se elimina al cargar el cliente. El flujo OTP de firma también establece la cookie desde el servidor sin devolver el token.
- Separar OTP de registro, firma, descarga, recuperación de contraseña y recuperación de clave empresarial. El verificador filtra por operación/recurso, almacena HMAC y consume el código de forma atómica.
- Contar intentos incorrectos en base de datos y expirar el OTP al alcanzar el límite.
- Normalizar las comparaciones de `Origin`/`Referer`, devolver una respuesta genérica en recuperación de contraseña, agregar `X-Content-Type-Options` y `Referrer-Policy`, y desplegar CSP en modo `Report-Only` para no romper recursos existentes.
- Alinear la documentación: Vault Transit aparece como proveedor configurado en el snapshot local; no se declara como hecho verificado en producción.

Los OTP creados con el formato anterior no son compatibles con el verificador actualizado y deberán solicitarse nuevamente después del despliegue. La duración de esos códigos es corta y no se requiere modificar ni borrar registros de usuario para hacer el cambio.

Quedan pendientes acciones operativas que no se pueden completar con seguridad solo desde el código:

1. Verificar en staging y luego desplegar/reiniciar con Vault Transit accesible, migración de metadata aplicada y pruebas de cifrado/descifrado. No activar una migración masiva de archivos sin backup y reconciliación.
2. Revisar permisos/propietarios y política de retención de certificados, backups, logs y hojas de cálculo presentes localmente. No se borraron esos archivos porque su retención y dependencias no están confirmadas. El `.env` local se observó con modo `0600`.
3. Confirmar que el balanceador/ingress real termina TLS obligatoriamente. No se añadieron certificados ni se cambió Nginx a HTTPS sin conocer el dominio, certificados y topología.
4. Observar reportes CSP en staging y luego definir una CSP de aplicación aplicable; por ahora es Report-Only para preservar funcionalidad.
5. Ejecutar el suite completo de integración y un DAST autorizado en staging después del despliegue.
