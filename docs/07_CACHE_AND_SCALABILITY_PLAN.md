# Etapas de Evolución Backend — Redis, Jobs, Object Storage y Alta Disponibilidad

Este documento propone un roadmap más riguroso para escalar YouCompare Payroll sin reescribir el backend: evolucionar la arquitectura actual por etapas.

1. Etapa 3 — Redis como infraestructura compartida
2. Etapa 4 — Jobs asíncronos e idempotentes
3. Etapa 5 — Almacenamiento de objetos
4. Etapa 6 — Múltiples nodos y eliminación de puntos únicos de falla

---

## Evaluación general

La progresión lógica debe ser:

- Etapa 3: Redis como infraestructura compartida
- Etapa 4: Jobs asíncronos e idempotentes
- Etapa 5: Almacenamiento de objetos
- Etapa 6: Múltiples nodos y eliminación de puntos únicos de falla

No se trata de reescribir el backend, sino de evolucionar la arquitectura existente.

---

## Etapa 3 — Redis

> Inicio Etapa 3: Redis como infraestructura compartida

### Principio clave
Redis no debe convertirse en el origen de verdad.

- PostgreSQL sigue siendo el origen de datos transaccionales y de auditoría:
  - usuarios
  - organizaciones
  - permisos
  - recibos
  - firmas
  - auditoría

- Redis debe usarse para:
  - datos efímeros
  - cache
  - locks y coordinación
  - contadores
  - colas

- Object Storage debe usarse para documentos binarios.

### Sesiones

Primero hay que auditar el modelo actual de autenticación.

Si MyManage usa JWT stateless, no conviene forzar cada request a Redis.
Redis puede servir para:

- refresh tokens
- revocación de sesiones
- sesiones administrativas
- lista de tokens comprometidos
- control de dispositivos

Claves sugeridas:

- `session:{session_id}`
- `session:user:{user_id}:{session_id}`

Contenido mínimo:

```json
{
  "user_id": 123,
  "organization_id": 8,
  "role": "employer",
  "issued_at": "...",
  "expires_at": "...",
  "session_version": 2
}
```

No almacenar información sensible innecesaria.

### OTP

La operación debe ser atómica.

- Usar `GETDEL` o un script Lua atómico.
- No usar `GET` seguido de `DEL` en producción.
- Guardar hash del OTP, no el OTP en texto claro.
- Añadir contador máximo de intentos.
- Implementar bloqueo temporal tras fallos repetidos.
- Separar por propósito:
  - `otp:signature:{request_id}`
  - `otp:login:{user_id}`
  - `otp:reset:{token_id}`
- Asociar OTP con usuario, organización y operación.

### Rate limiting

Redis debe complementar, no duplicar, el rate limiting de Nginx.

- Nginx puede gestionar límites básicos por IP.
- Redis debe añadir límites de aplicación:
  - por usuario
  - por organización
  - por endpoint sensible
  - por acción de firma
  - por OTP

No conviene implementar el mismo límite IP en Nginx y Python.

### Implementación correcta

Evitar la implementación ingenua `INCR` + `EXPIRE` que puede dejar claves sin TTL.
Usar:

- script Lua atómico
- transacción Redis
- librerías probadas
- algoritmos token bucket o sliding window

### Caché

Usar patrón cache-aside:

1. Buscar en Redis
2. Si existe, responder
3. Si no existe, consultar PostgreSQL
4. Guardar resultado con TTL
5. Responder

Claves versionadas y multitenant:

- `mymanagerh:v1:org:{org_id}:config`
- `mymanagerh:v1:org:{org_id}:dashboard:summary`

Nunca usar claves globales como `dashboard:summary`.
Cada tenant debe tener su propio namespace.

### Redis operativo

El plan debe incluir configuración explícita en el servidor:

- instalación como servicio systemd
- `bind` solo a localhost o red privada
- contraseña o ACL
- `protected-mode yes`
- límites de memoria
- política de expulsión
- persistencia
- backup
- health check
- timeout de conexión
- comportamiento ante caída de Redis

Si el mismo Redis guarda cache, jobs y OTP, se debe mantener un namespace separado y, de ser posible, instancias separadas:

- Redis cache
- Redis jobs

En una primera fase pueden compartir host, pero no se debe usar un solo namespace indistinto.

### Redis opcional para seguridad crítica

Definir fallbacks claros:

- caché caída → consultar PostgreSQL
- rate limiter Redis caído → decidir fail-open o fail-closed según endpoint
- OTP Redis caído → no permitir validación insegura
- cola caída → no aceptar jobs que luego se puedan perder

> Fin Etapa 3: Redis como infraestructura compartida

---

## Etapa 4 — Procesos pesados

### Objetivo
Desacoplar la API REST de los procesos largos y críticos: PDF, firma, mail y almacenamiento.

### Tecnología de cola

Elegir una sola tecnología Python.
No mezclar RQ / Celery / Dramatiq / Huey / Bull.

Bull no es adecuado para este backend Python.
Las opciones razonables:

- Dramatiq: simple y limpio
- Celery: completo pero más complejo
- RQ: bueno para comenzar, pero limitado

Para MyManage, probablemente Dramatiq o Celery son las mejores opciones.

### Número de colas

No separar cuatro colas desde el primer día.
Una primera versión razonable:

- `documents`
- `notifications`

O incluso:

- `critical`
- `documents`
- `emails`
- `maintenance`

Separar cada microetapa en una cola distinta puede complicar demasiado el flujo inicial.

### Workflow inicial

Un job principal `process_signature_request` puede hacer internamente:

1. generar el PDF
2. firmar
3. almacenar
4. registrar evidencia
5. encolar el email

El email sí conviene separarlo, porque un fallo SMTP no debe invalidar una firma ya completada.

### Idempotencia

Este punto debe ser explícito:

- nunca firmar dos veces
- nunca crear dos recibos
- nunca enviar dos correos por el mismo evento
- nunca duplicar evidencias

Cada job debe tener:

- `job_id`
- `idempotency_key`
- `entity_id`
- `organization_id`
- `job_type`
- `status`
- `attempt`
- `created_at`
- `started_at`
- `completed_at`
- `last_error`

Y una restricción única sobre la clave de idempotencia.

### Transactional Outbox

Resolver el clásico problema de pérdida de job entre PostgreSQL y Redis.

Patrón recomendado:

1. En la transacción de PostgreSQL:
   - crear la solicitud
   - crear el registro outbox
   - commit
2. Dispatcher lee el outbox pendiente
3. publica el job
4. marca como publicado

Esto evita jobs perdidos o entidades referenciadas inexistentes.

### Reintentos y DLQ

Definir políticas por tipo de tarea:

- PDF: 3 intentos
- Firma criptográfica: 2-3 intentos en fallos recuperables
- TSA: backoff y retries con jitter
- Email: 5 intentos con backoff
- Error de validación: sin reintento

Agregar también:

- backoff exponencial
- jitter
- timeout por job
- dead-letter queue
- cancelación
- reintento manual vía CLI
- trazabilidad de errores

### Webhooks / callback_url

No incluir `callback_url` arbitraria desde el payload.

Esto puede abrir SSRF.
Mejor guardar:

- identificador de integración
- evento a emitir
- webhook registrado y validado en PostgreSQL

El worker consulta configuración segura, no ejecuta URLs arbitrarias.

### Flujo de estados

Estados claros:

- `pending`
- `queued`
- `processing`
- `generated`
- `signed`
- `stored`
- `completed`
- `failed`
- `cancelled`
- `retrying`

La API puede devolver:

- `HTTP/1.1 202 Accepted`
- `Location: /api/jobs/{job_id}`
- `Retry-After: 2`

Y debe existir un endpoint de consulta:

- `GET /api/jobs/{job_id}`

### Workers especializados

No confundir:

- workers HTTP de Gunicorn
- threads actuales de PDF
- workers asíncronos de la cola

Una vez que PDF y firma se muevan a jobs externos, el thread pool de Gunicorn debe revisarse. Probablemente ya no necesite el mismo nivel de capacidad que hoy.

---

## Etapa 5 — Almacenamiento de objetos

### Objetivo
Sacar los PDFs y binarios del VPS y usar un almacenamiento de objetos compatible con S3.

### Guardar referencias, no URLs firmadas

En PostgreSQL debe persistirse metadata:

- `provider`
- `bucket`
- `object_key`
- `version_id`
- `content_type`
- `size_bytes`
- `sha256`
- `created_at`
- `retention_until`
- `status`

Ejemplo de object key:

- `organization/8/receipts/2026/07/{receipt_id}.pdf`

La URL firmada se genera en runtime al descargar.

### Seguridad y privacidad

Los recibos y legajos contienen datos personales.
Debe incluirse:

- bucket privado
- acceso denegado públicamente
- URLs firmadas de corta duración
- cifrado en tránsito
- cifrado en reposo
- separación lógica por organización
- validación estricta de permisos
- auditoría de accesos
- comprobación de hash
- objetos no predecibles cuando corresponda

### Retención legal

No usar un TTL genérico para todos los documentos.
Diferenciar:

- temporales de procesamiento: horas o días
- archivos fallidos: retención corta
- documentos finales: retención contractual/legal
- evidencias/auditoría: retención reforzada

### Flujo seguro de subida

1. Worker genera archivo temporal
2. Calcula SHA-256
3. Sube al storage
4. Verifica respuesta, tamaño y metadata
5. Guarda referencia en PostgreSQL
6. Marca documento como `stored`
7. Elimina archivo temporal

No eliminar local hasta confirmar la subida.

### Migración de documentos existentes

La etapa debe contemplar:

- inventario de archivos
- checksums
- subida progresiva
- comparación
- actualización transaccional de referencias
- modo dual-read temporal
- rollback
- limpieza posterior del disco local

### Interfaz de almacenamiento

Diseñar una abstracción compatible con S3:

```python
class ObjectStorage:
    def upload(...)
    def download(...)
    def delete(...)
    def exists(...)
    def generate_presigned_url(...)
    def get_metadata(...)
```

Así se puede cambiar entre R2, B2, S3 o MinIO sin acoplar el dominio.

---

## Etapa 6 — Alta disponibilidad

> Inicio de Etapa 6: construir una plataforma con múltiples nodos API, workers resilientes y salud continua.

### Principio clave
Cuatro workers Gunicorn en un solo VPS no son alta disponibilidad.
Eso es escalado vertical / multiproceso, no HA.

### Topología realista

```text
Internet
                       │
             Load Balancer / Proxy HA
                       │
              ┌────────┴────────┐
              │                 │
          API Node A        API Node B
          Gunicorn          Gunicorn
              │                 │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
      PostgreSQL     Redis       Object Storage
       HA/Backup     HA/Backup      Externo
```

Y por separado:

- Worker Node A
- Worker Node B

### Orden realista de expansión

1. Dejar la API stateless.
2. Mover archivos fuera del disco local.
3. Compartir sesiones, caché y colas.
4. Crear un segundo nodo API.
5. Colocar un load balancer.
6. Crear workers externos para jobs.
7. Automatizar deploys y health checks.
8. Proteger PostgreSQL.
9. Proteger Redis.
10. Probar failover.

### Base de datos

Una réplica PostgreSQL no es HA automática.
Hay que definir:

- replicación
- promoción
- failover
- backups
- Point-in-Time Recovery
- WAL archiving
- monitoreo de lag
- reconexión de clientes

Al principio priorizaría:

- backups automáticos
- pruebas de restauración
- WAL
- réplica en otro host

antes que un failover complejo.

### Load balancer

Nginx en el mismo VPS que las APIs sigue siendo un punto único de falla.
A futuro conviene un balanceador administrado o un proxy en un tercer nodo.
Si se autogestiona, usar dos proxies con Keepalived.

### Despliegues

La etapa de HA debe incluir:

- rolling deploy
- health checks
- readiness
- graceful shutdown
- compatibilidad de migraciones
- no cortar jobs en curso
- rollback de versión
- configuración centralizada

---

## Plan final recomendado

### Etapa 3A — Redis base

- Instalar Redis de forma segura.
- Crear un `RedisService` centralizado.
- Añadir health checks y métricas.
- Mantener namespaces por entorno y organización.
- Cache de configuración y dashboard.
- Rate limit distribuido.
- OTP atómico.
- Revocación de sesiones.
- Fallbacks definidos.

### Etapa 3B — Validación

- Probar caída de Redis.
- Medir hit/miss.
- Comparar latencia.
- Verificar aislamiento multitenant.
- Validar TTL e invalidación.

### Etapa 4A — Sistema de jobs

- Elegir Dramatiq o Celery.
- Crear `background_jobs`.
- Implementar Transactional Outbox.
- Asegurar idempotencia.
- Comenzar con dos colas: `documents` y `notifications`.
- Añadir estado y endpoint de consulta.

### Etapa 4B — Migración gradual

1. Emails.
2. Generación de PDF.
3. Firma digital.
4. TSA.
5. Evidencias.
6. Procesamiento masivo.

Mover primero el correo porque es menos crítico y valida la infraestructura sin tocar de entrada el núcleo criptográfico.

### Etapa 5 — Storage

- Abstracción S3.
- Bucket privado.
- Hash y metadata.
- URLs firmadas temporales.
- Migración progresiva.
- Retención diferenciada.
- Verificación y rollback.

### Etapa 6 — HA

- API stateless.
- Segundo nodo API.
- Load balancer.
- Workers externos.
- Backups PostgreSQL y recuperación.
- Réplica PostgreSQL.
- Redis con persistencia/failover.
- Deploy gradual.
- Pruebas reales de caída.

> Implementación actual:
> - Todos los procesos de background usan advisory locks para evitar duplicación en múltiples worker nodes.
> - El servicio es compatible con múltiples instancias de FastAPI/Gunicorn mientras PostgreSQL mantiene la consistencia.
> - Health checks incluyen DB, Redis, y cola de jobs para detectar rápidamente SPOFs.
> - Se agregó un endpoint dedicado `/health/ha` que expone estado de supervisores y readiness completo.

### Estado actual de Etapa 6

- `main.py` crea supervisores protegidos por `pg_try_advisory_lock` para:
  - mantenimiento
  - outbox/webhooks
  - cola de import jobs
  - verificación de integridad de almacenamiento
- `app.state` mantiene los tasks activos para permitir observabilidad y detección de procesos detenidos.
- `deep_health_check` ya valida DB, disco, Redis, pipeline de firmas, cola de importación, carga de sistema, motor PDF y certificados PKI.
- Esta implementación cubre la base HA operativa necesaria para correr múltiples nodos API sin duplicar tareas de fondo.

---

## Veredicto

El plan original va en buena dirección, pero necesita correcciones para no generar falsas sensaciones de alta disponibilidad.

Puntos no negociables:

1. Redis como infraestructura efímera, no dueño de datos críticos.
2. OTP y rate limiting atómicos.
3. Claves de caché aisladas por organización.
4. Jobs idempotentes y con Transactional Outbox.
5. Reintentos, backoff y dead-letter queue.
6. Guardar claves de objetos, no URLs firmadas.
7. Retención legal diferenciada para documentos.
8. Reconocer que varios workers en un VPS no equivalen a alta disponibilidad.

Con estas correcciones, el roadmap pasa de ser una optimización de rendimiento a una evolución sólida hacia una plataforma escalable y segura.
