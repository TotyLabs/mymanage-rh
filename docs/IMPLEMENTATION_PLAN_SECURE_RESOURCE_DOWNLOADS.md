# Implementation Plan – Signed Resource Download Protection

## Objetivo

Implementar una política de descarga de archivos y recursos sensibles basada en un token firmado oponible al navegador, sin romper el flujo de autenticación, storage, ni signatures ya existentes en el backend FastAPI.

El patrón objetivo es:

- Mantener AES-GCM para cifrado de blobs y archivos a nivel de servicio de almacenamiento (ya implementado en `services/encryption_service.py`).
- Introducir una capa de firma de enlace de descarga basada en HMAC-SHA256 para escenarios de acceso directo a recursos protegidos.
- Rechazar cualquier entrega de archivo sensible que no pase por determinación de `resource_id` opaco y `scope` verificado.
- Restringir el `FileResponse`, `StreamingResponse` y rutas de entrega a un flujo de resolución backend-establecido sin permitir rutas físicas y sin exponer identificadores de archivo en la URL.

## Contexto técnico real del repositorio

Se observa una arquitectura ya compleja y funcional en el repositorio:

- `payroll_core.py` ofrece `get_current_user`, `require_auth`, `require_admin`, `safe_join_under_storage`, `resolve_storage_path`, límites de seguridad, hashing, cookies y sesión.
- `services/encryption_service.py` ya implementa AES-256-GCM envelope encryption de archivos con `encryption_metadata` y verificación de tenant boundary.
- `api/receipts.py`, `api/documents.py`, `api/signatures.py`, `api/notifications.py`, `api/organizations.py`, `api/employees.py`, `api/audit.py` sirven archivos o streams por `FileResponse`/`StreamingResponse` y contienen rutas de metadata/descarga.
- El backend usa `FastAPI` y `BaseHTTPMiddleware` y la app principal está centralizada en `main.py`.

El objetivo no es volver a construir esta base, sino integrar una nueva capa de protección sin romper el comportamiento de autenticación, usuario, org y sesiones.

## Principios de diseño

1. Nunca servir un archivo directo con `path` o `filename` visible en la URL.
2. Nunca aceptar un `resource_id` como un número o UUID visible en el navegador.
3. Todo recurso sensible debe resolverse por un `resource_id` opaco y un `scope` verificado.
4. El token de descarga debe tener `exp`, `jti`, `org`, `sub`, `scope`, `res`, `iss`, y un payload canónico serializado determinísticamente.
5. Los endpoints de metadata pueden seguir usando autenticación con `require_auth`, pero el endpoint de entrega del archivo debe pasar por firma de URL + scope + tenant + owner/user validation.
6. Mantener compatibilidad: la nueva capa no debe eliminar el flujo de upload o storage ya existente.

## Plan de implementación por fases

---

## Fase 0 – Aislar el riesgo y preparar la rama de seguridad

### Objetivo

Crear un punto de control seguro para introducir la funcionalidad.

### Tareas

1. Crear una rama de feature de seguridad (`secure-download-signing`).
2. Añadir un flag de entorno seguro:
   - `SECURE_DOWNLOAD_TOKENS_ENABLED = true`
   - `DOWNLOAD_SIGNING_SECRET = <secret>`
   - `DOWNLOAD_TOKEN_TTL_SECONDS = 60`
   - `DOWNLOAD_TOKEN_ALLOW_LEGACY = false` en producción.
3. Añadir un guard para no romper producción:
   - si el secreto no existe, el sistema debe seguir sirviendo archivos de forma legacy pero registrando una alerte de seguridad.

### Seguridad del rollout

- En prod, activar la protección con feature flag.
- En staging, lanzar con estado dual: validación de nueva ruta y fallback controlado.
- Mantener el modo legacy solo durante validación.

### Evidencias de verificación

- `$ python -m py_compile ...` para comprobar que no se hayan introducido errores de import.
- Route smoke test con una descarga de archivo de prueba: comprobar `401` cuando el token no existe.

---

## Fase 1 – Crear el servicio de signed resource token

### Objetivo

Centralizar la creación y validación de la firma del token de descarga.

### Nuevo archivo

`services/signed_resource_service.py`

### Contenido mínimo

- `SignedResourceTokenService` clase con:
  - `make_claims(resource_id, user_id, org_id, scope, purpose, nonce=None)`
  - `sign(token_payload)` con HMAC-SHA256
  - `verify(token)` con verificación de firma, `exp`, `iss`, `org`, `sub`, `scope`, `jti`
  - `build_signed_url(path, claims)`

### Reglas

- `resource_id` debe ser un recurso opaco UUID o un “resource_name opaque reference”.
- El payload debe serializarse con `sort_keys=True` y `separators=(",", ":")` para evitar diferencias de representación.
- Se recomienda evitar un `jti` persistente en memoria o en base de datos. El token debe ser `stateless` y depender de `exp`, `scope`, `org`, `sub`, `res` y de la firma HMAC-SHA256. Si se requiere anti-replay fuerte, debe usarse Redis compartido o una caché distribuida; no memoria local.
- El TTL debe ser corto: 30–120 segundos, con un límite configurable.

### Verificación

- Unit test de `encode/decode` con firma exacta.
- Unit test de `exp` y `scope` mismatch.
- Unit test de `jti` reuse.

---

## Fase 2 – Crear el resolutor opaco de recursos y la capa de acceso a rutas

### Objetivo

Eliminar la resolución de archivo a partir de un ID visible o un path visible sin introducir una nueva tabla SQL de enlaces o recursos temporales.

### Nuevo archivo

`services/resource_resolver.py`

### Contenido mínimo

- `FileResourceResolver` con:
  - `resolve(resource_id, org_id, user_id, scope)`
  - `check_scope(resource_id, scope)`
  - `revoke(resource_id)` opcional, solo a nivel de la entidad de negocio cuando el archivo es eliminado o el acceso debe revocarse.

### Política de compatibilidad

- No crear una tabla nueva de recursos ni un registro separado para cada enlace de descarga.
- Reusar las tablas y modelos ya existentes del backend: `payroll_receipts`, `company_documents`, `organizations`, `user_signatures`, `notifications`, etc.
- El `resource_id` opaco debe resolverse a un registro ya existente de la entidad de archivo. El `FileResponse` o `StreamingResponse` debe obtener la ruta real de archivo de la fila existente, con la validación de `scope`, `org_id` y `user_id` aplicadas sobre ese registro.
- Si una entidad de negocio no tiene un `resource_id` opaco propio, el servicio debe generar un identificador derivado de la entidad real con un hash stable y no reversible (por ejemplo, `sha256(resource_type + resource_pk + org_id)`), y usar ese valor solo como identificador de acceso, no como `id` de negocio visible. Ese identificador no se persiste en una nueva tabla; se construye determinísticamente y se usa solo en el token y la verificación.

### Verificación

- Test de resolución de `resource_id` opaco por una fila ya existente en la base de datos.
- Test de negar acceso a un recurso con `organization_id` o `scope` distinto.
- Test de no creación de una nueva tabla de recursos.

---

## Fase 3 – Centralizar el flujo de FileResponse y descargables

### Objetivo

No permitir que ningún endpoint de archivo maneje la entrega directa. Todas las descargas deben pasar por un único controlador de acceso central.

### Nuevos archivos o módulo

- `services/download_policy_service.py`
- `middleware/signed_download_middleware.py`

### Requerimientos

- Todos los endpoints de `FileResponse` y `StreamingResponse` de archivos pasan por `SignedDownloadPolicyService`.
- El servicio debe:
  1. leer `request.query_params['token']`
  2. verificar token
  3. resolver `resource_id` opaco
  4. comparar `scope`
  5. comprobar `org_id`
  6. comprobar `user_id`
  7. comprobar que la ruta está dentro de `ALLOWED_STORAGE_DIR`
  8. emitir la respuesta solo si todo se cumple

### Branch de compatibilidad

- Hay dos políticas de entrega:
  - legacy mode: en producción habilitado solo si env var `DOWNLOAD_TOKEN_ALLOW_LEGACY=true`
  - secure mode: endpoint exige token para cualquier `FileResponse`

### Verificación

- Ruta de prueba con `GET /api/receipts/download` sin token → `401`.
- Ruta con `token` correcto → file sent.
- Ruta con `scope` mismatched → `403`.
- Ruta con `org_id` mismatched → `403`.
- Ruta con archivo fuera de `ALLOWED_STORAGE_DIR` → `403`.

---

## Fase 4 – Adaptar los endpoints de archivos sensibles

### Objetivo

Ajustar de forma segura los endpoints que entregan archivos: recibos, documentos, firmas, logos y notificaciones.

### Áreas que deben integrarse

- [api/receipts.py](api/receipts.py)
- [api/documents.py](api/documents.py)
- [api/signatures.py](api/signatures.py)
- [api/notifications.py](api/notifications.py)
- [api/organizations.py](api/organizations.py)
- [api/employees.py](api/employees.py)
- [api/audit.py](api/audit.py)

### Orden recomendado

1. `api/documents.py` 
   - Fase 1: habilitar resolución opaca de archivo.
   - Fase 2: aceptar token y `scope=document:download`.

2. `api/receipts.py`
   - `scope=receipt:download`
   - bloquear acceso directo a `receipt_pdf_path`.

3. `api/signatures.py`
   - `scope=signature:download`
   - restringir descarga de imágenes o archivos de firma a un usuario y org.

4. `api/notifications.py`
   - `scope=notification:attachment`
   - evitar que el navegador descargue el archivo sin firma.

5. `api/organizations.py`
   - `scope=org:logo`
   - recurso de logo puede ser lo más simple al principio.

6. `api/audit.py`
   - `scope=audit:report`
   - descargar PDF de auditoría solo después de token y usuario.

### Política de implementación segura

- No castear ningún `FileResponse` de forma general dentro del endpoint viejo.
- Mantener el endpoint de metadata (JSON) intacto.
- Cambiar solo la entrega del recurso.
- Devolver el nombre real del archivo a través de `filename` solo cuando el `token` haya sido verificado.

---

## Fase 5 – Middleware global de verificación en `main.py`

### Objetivo

Centralizar la defensa y evitar que un solo endpoint haya que protegerse manualmente.

### Implementación

Añadir a `main.py` un middleware global:

```python
class SignedDownloadMiddleware(BaseHTTPMiddleware):
    async def dispatch(request, call_next):
        # 1. Detect if request is a sensitive file route.
        # 2. Extract token.
        # 3. If token missing: reject 401.
        # 4. Validate signature.
        # 5. Attach claims to request.state.
        # 6. Continue request.
```

### Qué debe hacer el middleware

- Detectar sólo rutas de descarga, o bien: 
  - `GET` + `path` de `/api/receipts/`, `/api/documents/`, `/api/signatures/`, `/api/notifications/`, `/api/organizations/`, `/api/audit/` con `download` o `file` route.
- Extraer `token` y leer claims.
- Verificar `exp`, `jti`, `scope`, `org`, `sub`, `resource_id`.
- Denegar conexión si el recurso no está en `ALLOWED_STORAGE_DIR`.
- Denegar si `request.state` indica que la org o el usuario no coincide.

### Protección adicional

- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`
- `Content-Security-Policy` rígida
- `Referrer-Policy: no-referrer`

---

## Fase 6 – Decoupling de contenido y frontend

### Objetivo

Evitar que el navegador sepa de la ubicación física o del identificador real del recurso.

### Frontend

- El frontend debe dejar de construir o mostrar ciertos enlaces de descarga directamente.
- Debe pedir una URL de descarga a una API de `issue`:

```http
GET /api/downloads/issue?resource_id=<opaque>\&scope=receipt:download
```

- El backend responderá con:

```http
/api/downloads/file?token=<signed_token>
```

### Reglas de validación

- El frontend nunca debe enviar un `resource_id` visible ni poner el query string con un path real.
- El frontend solo puede usar la URL emitida por el backend y no la firma.

### Seguridad adicional

- Poner `Content-Disposition: attachment` y no un nombre de archivo sin mapear.
- Rechazar descargas de `preview` si el usuario no tiene scope `preview` o `download`.

---

## Fase 7 – Pruebas de seguridad y regresión

### Objetivo

Verificar que la seguridad nueva no rompe los endpoints y el flujo de firma.

### Validaciones regulatorias

1. End-to-end test: un usuario autenticado con org y sesión válida recibe una descarga segura con token firmado.
2. End-to-end test: un usuario de otra org no obtiene acceso ni al token ni al archivo.
3. End-to-end test: un token con `scope` diferente da `403`.
4. End-to-end test: un archivo fuera de `ALLOWED_STORAGE_DIR` no se sirve.
5. End-to-end test: una ruta de documento o recibo con una URL de acceso sin token retorna `401` o `403`.

### Pruebas recomendadas en el repositorio

- Crear tests de integración para `api/receipts.py` y `api/documents.py` usando FastAPI TestClient.
- Agregar tests de seguridad en `tests/test_hardening_security.py` o un nuevo test de `signed_downloads`.

---

## Fase 8 – Rollout gradual y observabilidad

### Objetivo

Activar la protección sin causar cortes abruptos.

### Rollout

1. Modo shadow con logging de eventos `download_denied` y `download_granted`.
2. Activar para un solo tipo de recurso, por ejemplo recibos (`receipt:download`).
3. Activar para todos los documentos.
4. Activar para notificaciones, logos y auditorías.

### Observabilidad

- Registro de `request_id` en todo token validado/denegado.
- Registro de `scope`, `org`, `user`, `resource_type`, `jti`, `denied_reason`.
- Registro en `audit_log` del backend para acciones de descarga.

### Eventos de seguridad a capturar

- `download.token.missing`
- `download.token.expired`
- `download.token.scope_mismatched`
- `download.token.tenant_mismatch`
- `download.resource_not_found`
- `download.path_traversal_attempt`

---

## Reglas de implementación NO-NEGOCIABLES

1. No introducir una tabla SQL nueva para registrar enlaces temporales o recursos opacos.
2. No introducir un `jti` sólo en memoria, ni una memoria local de tokens que no comparta estado entre varias instancias.
3. No introducir un nuevo `FileResponse` directamente sin comprobar `resource_id`, `org_id` y `scope`.
4. No servir archivos con `absolute path` visible ni “relación directa con DB path”.
5. No exponer `storage_path` al frontend.
6. No permitir el acceso “legacy” al endpoint de descarga en producción si no hay una verificación de fallback controlada.
7. No usar `AES` para ocultar la URL de descarga: AES se usa para cifrar el contenido o el envelope, no para firmar el acceso a una URL.

## Prioridad de implementación

1. `SignedResourceTokenService`
2. `FileResourceResolver`
3. `DownloadPolicyService`
4. `SignedDownloadMiddleware`
5. Convertir endpoints de archivo a patrón tokenizado
6. Frontend integration
7. Significantly test and observability

## Criterio de salida

Se considera implementado cuando:

- Cualquier recurso sensible tiene un `scope` explícito y no usa el `id` visible.
- El token del enlace no puede construirse o decodificarse sin firma.
- La descarga de archivo rechaza rutas fuera de `ALLOWED_STORAGE_DIR`.
- La API de metadata sigue funcionando y el recurso se sirve solo con token válido.
- Los logs y auditoría muestran cada intento de descarga con org y autorización adecuada.
