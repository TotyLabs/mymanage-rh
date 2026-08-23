# Estimación de Capacidad en Producción

## Objetivo

Este documento describe cuánto puede soportar el sistema YouCompare Payroll en un entorno de producción basado en la configuración y el código actuales.
Se basa en la arquitectura existente, los parámetros de `config.py`, la configuración de `gunicorn.conf.py` y los patrones de carga del backend.

## 1. Configuración de producción actual

### 1.1 Arquitectura de ejecución

- Modo producción: `server.py` arranca `gunicorn` con `UvicornWorker`.
- Configuración por defecto de `gunicorn.conf.py`:
  - `workers = 4`
  - `worker_class = "uvicorn.workers.UvicornWorker"`
  - `timeout = 180`
  - `graceful_timeout = 120`
  - `max_requests = 2000`
  - `max_requests_jitter = 200`
- Cada worker ejecuta su propio event loop y su propio pool de conexiones SQLAlchemy.

### 1.2 Pool de conexiones PostgreSQL

En `config.py`:

- `DB_POOL_SIZE = 10`
- `DB_MAX_OVERFLOW = 15`

Cada worker tiene su propio pool de SQLAlchemy, lo que significa que el sistema puede abrir hasta:

- 25 conexiones por worker
- 4 workers × 25 conexiones = 100 conexiones PostgreSQL teóricas máximas

Este valor es el límite alto, y la cifra segura operativa debe ser menor si la base de datos comparte recursos con otros servicios.

### 1.3 Procesamiento de PDF / firma digital

En `modules/digital_signature.py`:

- El procesamiento PDF se descarga a un `ThreadPoolExecutor`.
- `max_workers = min(os.cpu_count() or 4, 9)` por worker.
- Con 4 workers, el total de threads de firma/PDF es de hasta 36.

Esto significa que la capacidad de trabajos pesados de firma está limitada por 36 hilos de procesamiento compartidos entre todos los workers.

### 1.4 Otros parámetros relevantes

- `keepalive = 5` segundos en Gunicorn.
- `backlog = 2048` conexiones entrantes.
- `limit_request_line = 8190` y `limit_request_field_size = 8190` para proteger contra abuso de cabeceras.

## 2. Capacidad teórica por tipo de carga

### 2.1 Operaciones ligeras (consulta, listados, autenticación)

Estas rutas son principalmente I/O-bound y suelen ejecutar consultas SQL de lectura.

- Límite principal: conexiones DB y latencia de consultas.
- Si se asume un promedio de 2-3 consultas por request y 100 ms de latencia por consulta,
  el sistema puede manejar hasta ~300-400 requests/s en condiciones ideales.
- Con 4 workers y 100 conexiones posibles, la capacidad de consultas concurrentes puede sostener entre 200 y 400 usuarios activos con navegaciones normales.

Estimación práctica:

- 150-250 usuarios concurrentes para dashboards, búsquedas y listados.
- 300-500 requests/s en condiciones de baja complejidad.

### 2.2 Operaciones pesadas (firma digital, PDF, sello)

Estas operaciones son CPU/IO-bound con procesamiento de PDF, generación de firmas y manipulación de imágenes.

- Hasta 36 hilos de PDF en paralelo.
- Si cada firma toma entre 2 y 6 segundos, el throughput es de aproximadamente 6-18 firmas por segundo.
- En términos de carga sostenida, esto equivale a 360-1,080 firmas por hora.

Estimación práctica:

- 30-36 firmas simultáneas activas en el peor caso.
- 360-1,080 firmas por hora en condiciones ideales; para producción debe esperarse menos por la carga de DB, disco, TSA y servicios externos.
- Si la carga de firma excede 36 tareas concurrentes, la espera de threads y el timeout de 180 s pueden empezar a degradar el servicio.

### 2.3 Carga de importación y procesamiento masivo

- Cargas masivas de Excel/PDF y procesos de importación utilizan a la vez CPU, disco y DB.
- Aunque el front-end es asíncrono, el procesamiento suele quedar limitado por la creación de registros y validaciones.
- Recomendación: limitar a 4-8 importaciones masivas concurrentes antes de observar degradación.

## 3. Estimación de capacidad por escenario

| Escenario | Capacidad aprox. | Comentarios |
|---|---|---|
| Navegación normal | 150-250 usuarios concurrentes | Consultas y listados, sin firmas simultáneas pesadas |
| Firma digital activa | 30-36 firmas concurrentes | Limite de thread pool PDF |
| Pico mixto realista | 80-120 usuarios concurrentes | 70% lectura, 20% firma, 10% operaciones administrativas |
| Carga extrema | 200-300 usuarios concurrentes | Latencias > 2s, posible saturación de DB y thread pool |
| Límite absoluto teórico | 400-500+ usuarios | Event loop y DB saturados, se degrada rápidamente |

## 4. Factores limitantes principales

### 4.1 Conexiones PostgreSQL

- El total teórico es 100 conexiones, pero no todas deben utilizarse al mismo tiempo.
- El DB pool de 25 por worker puede saturarse si hay muchas transacciones simultáneas.
- Consultas complejas o índices ausentes reducen la capacidad efectiva.

### 4.2 Hilos de PDF y firma

- El procesamiento de firma PDF es el cuello de botella más visible en cargas transaccionales.
- Con 36 hilos máximos, las solicitudes de firma se encolan cuando se excede la capacidad.
- Si la operación de firma tarda más de 6 segundos, la capacidad total desciende a 6-8 firmas/s.

### 4.3 Bloqueo de recursos en el event loop

- Aun siendo Uvicorn async, algunos componentes pueden bloquear:
  - manipulación de archivos grandes
  - uso pesado de PyMuPDF, Pillow o pyhanko
  - llamadas externas al SMS/Email sin timeout adecuado
- El uso de threads ayuda, pero no elimina por completo el riesgo de bloqueo en el worker.

### 4.4 Ausencia de cache compartida y cola de jobs

- El sistema no usa Redis ni cache compartida para reducir cargas repetitivas.
- No hay un backend de jobs separado para aislar firmas y exportaciones.
- Esto eleva la carga en el proceso web y amplifica los picos.

## 5. Recomendaciones para producción

1. Usar Gunicorn + 4 workers en lugar de Uvicorn directo en producción.
2. Colocar Nginx delante para:
   - SSL/TLS offload
   - gzip/brotli
   - buffering de clientes lentos
   - rate limiting básico por IP
3. Ajustar la base de datos si el servidor puede soportarlo:
   - `DB_POOL_SIZE=20`
   - `DB_MAX_OVERFLOW=30`
   - límite de conexiones de PostgreSQL >= 140 para permitir pools de app + otros servicios
4. Introducir Redis para:
   - rate limiting compartido entre workers
   - sesiones y cache de datos inmutables
   - coordinación de tareas y locks distribuidos
5. Separar firmas/PDF en un worker o cola de jobs dedicada.
6. Mantener `max_requests` y `max_requests_jitter` para reciclar workers y prevenir fugas de memoria.

## 6. ¿Cuántas organizaciones puede soportar?

Para un perfil típico de clientes payroll con 50-200 empleados cada uno:

- Configuración actual (4 workers, DB pool 10+15 por worker): 40-80 organizaciones pequeñas / medianas con 3,000-8,000 empleados totales en uso regular.
- Con ajustes de DB y Nginx: 80-150 organizaciones, 10,000-25,000 empleados totales.
- Con Redis y separación de firmas: 150-300 organizaciones, 30,000-70,000 empleados totales.

Estas cifras representan empleados acumulados entre todas las organizaciones, no empleados por organización. Son estimaciones operativas y suponen que las liquidaciones y firmas no ocurren todas exactamente al mismo tiempo.

## 7. Escenarios teóricos de ampliación

La siguiente tabla muestra qué podría soportar el sistema si se amplía la configuración. No son capacidades garantizadas: cada escenario requiere pruebas de carga y dimensionamiento de PostgreSQL, almacenamiento y servicios externos.

| Escenario | Configuración aproximada | Usuarios concurrentes | Firmas PDF simultáneas | Organizaciones | Empleados totales |
|---|---|---:|---:|---:|---:|
| Base productiva | 4 workers, pool DB 10+15, Nginx | 80-120 en pico mixto | 30-36 | 40-80 | 3,000-8,000 |
| Escalado del mismo servidor | 8 workers, pool DB 10+15, Nginx, PostgreSQL dimensionado | 150-250 en pico mixto | 60-72 | 80-160 | 8,000-20,000 |
| API y firmas separadas | 4-8 workers API, workers PDF independientes, Redis, Nginx | 300-600 en API | 100-200 en cola de procesamiento | 150-400 | 20,000-80,000 |
| Dos nodos de aplicación | 2 nodos con 4-8 workers cada uno, Redis compartido, DB dedicada | 600-1,200 | 200-400 en workers PDF | 300-800 | 50,000-160,000 |
| Plataforma multi-nodo | Autoescalado, cola distribuida, PostgreSQL de alta capacidad, object storage | 1,500-3,000 | 500-1,000 en workers PDF | 800-2,000 | 150,000-400,000 |

### Ejemplos de interpretación

#### Escenario A: duplicar workers en el mismo servidor

Pasar de 4 a 8 workers podría duplicar aproximadamente la capacidad de solicitudes web, siempre que CPU, PostgreSQL, disco y memoria tengan margen. No duplica automáticamente la capacidad de firma: también habría que aumentar el número de workers PDF y revisar el límite de conexiones de PostgreSQL.

En este escenario, una expectativa razonable sería:

- 150-250 usuarios concurrentes en un pico mixto.
- 60-72 firmas PDF en procesamiento simultáneo si se duplica también el pool PDF.
- 80-160 organizaciones.
- 8,000-20,000 empleados acumulados.

#### Escenario B: separar la API de la firma

La API atiende autenticación, consultas y operaciones administrativas mientras un grupo separado de workers procesa PDF. Esto evita que un pico de firmas consuma todos los recursos web.

Una estimación teórica sería:

- 300-600 usuarios concurrentes en la API.
- 100-200 firmas simultáneas en los workers PDF.
- 150-400 organizaciones.
- 20,000-80,000 empleados acumulados.

Las firmas que excedan la capacidad instantánea deben entrar en una cola persistente con estado, reintentos e idempotencia. En este modelo, "firmas simultáneas" significa trabajos procesándose; la cola puede contener más trabajos sin bloquear la API.

#### Escenario C: dos nodos de aplicación

Con dos nodos detrás de un balanceador, Redis compartido y una base PostgreSQL dimensionada para ambos nodos, se eliminan parte de los límites de un único servidor.

Una expectativa teórica sería:

- 600-1,200 usuarios concurrentes.
- 200-400 firmas PDF simultáneas.
- 300-800 organizaciones.
- 50,000-160,000 empleados acumulados.

Este escenario requiere sesiones/rate limits compartidos, almacenamiento compartido u object storage y una estrategia de despliegue que permita retirar un nodo sin perder trabajos.

#### Escenario D: plataforma multi-nodo

Con autoescalado, cola distribuida, PostgreSQL de alta capacidad, object storage y workers PDF independientes, el cuello de botella deja de ser solamente Gunicorn. Pasa a depender de la capacidad de la base de datos, del volumen de documentos y de la velocidad de procesamiento de la cola.

Como orden de magnitud, podría apuntarse a:

- 1,500-3,000 usuarios concurrentes.
- 500-1,000 firmas PDF simultáneas.
- 800-2,000 organizaciones.
- 150,000-400,000 empleados acumulados.

Estas cifras necesitan pruebas de carga, observabilidad por tenant y límites de consumo por organización para evitar que un cliente monopolice la capacidad.

## 8. Cómo optimizarlo para soportar mucho más

La mejora más grande no viene de un solo cambio, sino de una combinación de capas que reducen la presión sobre la aplicación y sobre PostgreSQL.

### 8.1 Nivel 1: optimizar la capa web

Acciones recomendadas:

- Mantener Gunicorn con 4 workers y aumentar a 8 si la CPU y la memoria lo permiten.
- Poner Nginx delante para offload TLS, compresión, buffering y rate limiting.
- Reducir la carga de endpoints pesados con cache de respuestas y caché de consultas frecuentes.
- Desacoplar el procesamiento de PDFs de la API para que el servicio web no se bloquee.

Impacto esperado:

- Usuarios concurrentes: de 80-120 a 150-250 en picos mixtos.
- Firmas simultáneas: de 30-36 a 40-60 si el cuello de botella sigue siendo el worker web.

### 8.2 Nivel 2: optimizar PostgreSQL

Acciones recomendadas:

- Crear índices adecuados para listados, búsquedas y filtros de negocio.
- Ajustar el pool de conexiones con valores más altos si el DB server tiene márgenes.
- Revisar consultas lentas y eliminar joins innecesarios o excesivos.
- Separar operaciones de lectura y escritura si el volumen crece mucho.

Impacto esperado:

- Menor latencia en cada request.
- Menos saturación del pool de conexiones.
- Mejor estabilidad con 80-150 organizaciones y miles de empleados.

### 8.3 Nivel 3: introducir Redis y cola de jobs

Acciones recomendadas:

- Usar Redis para sesiones, OTP, rate limiting y cache de datos frecuentes.
- Separar la firma digital en workers dedicados con una cola de jobs.
- Implementar reintentos, idempotencia y estados de procesamiento por job.
- Evitar que un pico de firmas bloquee la API.

Impacto esperado:

- Usuarios concurrentes en la API: 300-600.
- Firmas simultáneas procesadas por workers dedicados: 100-200.
- Menor degradación durante picos de liquidación o alta demanda.

### 8.4 Nivel 4: arquitectura multi-nodo

Acciones recomendadas:

- Balancear tráfico entre dos o más nodos de aplicación.
- Compartir sesiones y cache via Redis.
- Separar PostgreSQL de alta capacidad o usar replicas de lectura.
- Almacenar documentos en object storage en vez de depender únicamente del filesystem local.

Impacto esperado:

- Usuarios concurrentes: 600-1,200.
- Firmas simultáneas: 200-400.
- Capacidad de crecimiento para cientos de organizaciones y decenas de miles de empleados.

### 8.5 Nivel 5: arquitectura de escala empresarial

Acciones recomendadas:

- Autoescalado horizontal con colas distribuidas.
- Workers dedicados por tipo de carga: firma, importación, notificaciones y mantenimiento.
- Observabilidad por tenant, métricas de cola, SLA y alertas automáticas.
- Limitación de consumo por organización para evitar que un cliente monopolice los recursos.

Impacto esperado:

- Usuarios concurrentes: 1,500-3,000.
- Firmas simultáneas: 500-1,000.
- Organizaciones: 800-2,000 o más, dependiendo del tamaño real de cada cliente.

## 9. Resultado esperado si se aplican estas mejoras

En una ruta realista de escalado, el resultado podría ser:

- Configuración actual: 40-80 organizaciones y 3,000-8,000 empleados totales.
- Con Nginx + mejor DB + más workers: 80-150 organizaciones y 10,000-25,000 empleados.
- Con Redis + workers de firma separados: 150-400 organizaciones y 20,000-80,000 empleados.
- Con arquitectura multi-nodo: 300-800 organizaciones y 50,000-160,000 empleados.
- Con plataforma multi-nodo y cola distribuida: 800-2,000 organizaciones y 150,000-400,000 empleados.

## 10. Implementation Plan (3 fases)

El objetivo es ofrecer un roadmap compacto en tres fases prácticas y ejecutables: 1) estabilizar y optimizar el sistema actual; 2) desacoplar las cargas pesadas y poner workers/cola; 3) pasar a una plataforma multi-nodo y distribuida si el volumen lo requiere.

### Fase 1 — Estabilizar y optimizar (rápido impacto)

Objetivo:
- reducir riesgos operativos y ganar capacidad con cambios de configuración y optimización SQL.

Alcance:
- poner `Nginx` delante de `Gunicorn` (TLS offload, buffering, rate limiting);
- revisar `gunicorn.conf.py` y ajustar número de workers según CPU/memoria;
- ejecutar benchmarks (`k6`/`locust`) y recopilar baseline de métricas;
- identificar y optimizar consultas lentas; aplicar índices críticos en DB;
- habilitar health checks, métricas y logs estructurados.

Entregables:
- proxy Nginx y ajuste de workers en producción;
- baseline de métricas y un plan de índices SQL aplicado en staging/producción;
- playbook de despliegue y rollback.

Criterio de éxito:
- mejoras medibles en p95/p99 de endpoints principales;
- capacidad estable para ~80-150 organizaciones (10k-25k empleados) en condiciones razonables.

Riesgos:
- saturación de PostgreSQL si no se dimensiona; cambios de índices afectan writes.

### Fase 2 — Desacoplar cargas y establecer workers/cola

Objetivo:
- evitar que el procesamiento de firma y tareas pesadas consuman recursos de la API; mejorar resiliencia en picos.

Alcance:
- integrar Redis para sesiones, cache y rate limiting;
- elegir y desplegar una solución de cola (ej. Redis+RQ, Celery/Redis, o una cola persistente similar);
- implementar workers de firma independientes que consuman jobs de la cola;
- diseñar jobs idempotentes, con reintentos, métricas y DLQ;
- añadir control de concurrencia por tenant y límites configurables.

Entregables:
- Redis operativo para sesión/cache y cola;
- workers de firma en despliegue separado (systemd/container/worker pool);
- endpoints para encolar trabajos y dashboard básico de cola/latencia.

Criterio de éxito:
- la API mantiene baja latencia bajo picos de firma;
- soporte práctico para ~150-400 organizaciones (20k-80k empleados) con menores degradaciones.

Riesgos:
- nueva complejidad operativa (monitoring/alertas para la cola);
- garantizar consistencia entre DB y estado de jobs.

### Fase 3 — Plataforma multi-nodo y procesamiento distribuido

Objetivo:
- permitir crecimiento sostenido mediante escalado horizontal, observabilidad por tenant y aislamiento de recursos.

Alcance:
- desplegar múltiples nodos de aplicación detrás de un balanceador (o usar un orchestrator con servicio de carga);
- externalizar almacenamiento de documentos a object storage; usar replicas/replicación para PostgreSQL si procede;
- habilitar autoescalado para workers y nodos API según métricas de cola/CPU/memoria;
- construir observabilidad avanzada (trazas, métricas por tenant, dashboards de cola y SLAs);
- aplicar límites de consumo por organización y políticas de QoS.

Entregables:
- despliegue multi-nodo con storage compartido y Redis/cola distribuidos;
- políticas de autoescalado y aislamiento por tenant;
- dashboards, alertas y runbooks operativos.

Criterio de éxito:
- capacidad para escalar a cientos o miles de organizaciones según demanda (300+ hasta 2,000 organizaciones, dependiendo del perfil), y procesamiento masivo de firmas con baja degradación.

Riesgos:
- coste y complejidad elevados; necesidad de pruebas de carga y validación por tenant.

### Orden recomendado de ejecución

1. Fase 1: estabilizar y optimizar (rápido retorno, baja complejidad).
2. Fase 2: desacoplar firmas y poner cola + workers (reduce riesgo de degradación).
3. Fase 3: multi-nodo y plataforma distribuida (coste/operación justificable solo con demanda sostenida).

### Recomendación ejecutiva

Empieza por la Fase 1 para obtener datos reales y justificar inversión. Si tras Fase 1 persisten cuellos de botella por firmas o picos repetidos, avanzar a Fase 2; planificar Fase 3 solo si la demanda y los KPIs lo requieren.

## 11. Advertencias importantes

- Esta es una estimación teórica basada en el código y la configuración actuales.
- No sustituye un benchmark real con `locust`, `k6` o `wrk` sobre la infraestructura que se vaya a utilizar.
- La capacidad real depende de:
  - latencia de PostgreSQL
  - tipo de consultas
  - tamaño promedio de PDFs
  - uso del disco / I/O
  - latencia de servicios externos (SMS, email, TSA)

## 12. Conclusión

El sistema puede operar en producción con una configuración razonable si se mantiene:

- Gunicorn con 4 workers
- un pool de DB bien dimensionado
- un thread pool de firma limitado a 36 hilos totales
- una capa de reverse proxy como Nginx

En ese escenario, la plataforma puede soportar un volumen útil de clientes payroll corporativos, aunque para escalas superiores es recomendable introducir cache/cola y separar los procesos de firma digital.
