# YouCompare Payroll — Modelo Teórico de Capacidad y Métricas Detalladas

## 1. Infraestructura Actual del Servidor

| Recurso | Valor |
|---|---|
| CPU | AMD EPYC (18 cores, 1 socket, sin HT) |
| RAM | 94 GB total / 90 GB disponibles |
| Disco | 678 GB total / 656 GB libre (4% uso) |
| OS | Linux x86_64 |
| Runtime | Python + Uvicorn (single worker, sin gunicorn) |
| DB | PostgreSQL (psycopg2-binary) |
| Memoria del Proceso | ~214 MB (pico: 181 MB reportado por systemd) |
| Uptime | 7+ días continuo (estable) |

---

## 2. Métricas del Codebase

### Volumen General

| Métrica | Valor |
|---|---|
| Líneas de código (Python) | 34,109 |
| Archivos .py | 255 |
| Imports totales | 1,339 |
| Funciones (`def`) | 567 |
| Clases (`class`) | 149 |
| Funciones async | 132 |
| Endpoints API | 119 decorators (`@app` / `@router`) |
| Consultas SQL | 857 llamadas `db.execute` / `text()` |
| Dependencias externas | 51 paquetes |
| Variables de entorno | 13 únicas via `os.getenv` |

### Top 10 Archivos Más Grandes (por líneas)

| Archivo | Líneas | Función |
|---|---|---|
| `receipts.py` | 1,756 | API de recibos |
| `digital_signature.py` | 1,651 | Motor de firma digital |
| `employees.py` | 1,390 | API de empleados |
| `signature.py` | 1,123 | Lógica de firmas |
| `payroll_core.py` | 1,059 | Core de negocio |
| `tables.py` | 1,025 | Modelos ORM (23 tablas) |
| `encryption_service.py` | 919 | Encriptación envelope |
| `normalizer.py` | 823 | Normalización legajo |
| `main.py` | 724 | App FastAPI + startup |
| `auth.py` | 686 | Autenticación |

---

## 3. Métricas de Firmas Digitales

| Métrica | Valor |
|---|---|
| Referencias a firma/signature | 1,170 menciones en todo el código |
| Motor PDF | PyMuPDF (`fitz`) + `pikepdf` + `pyhanko` + `reportlab` |
| Operaciones PDF | 93 llamadas a motores PDF |
| Thread Pool para PDF | `ThreadPoolExecutor(max_workers=36)` (cpu_count * 2 = 18*2) |
| Versiones de firma | `v1` (manuscrita PNG + sello) y `v2` (FES QR + Info) |
| Modo de firma | hybrid (texto inteligente + fallback coordenadas) |
| Evidencia capturada | IP, User-Agent, SHA-256 pre/post, hash imagen, token |
| PKI | X.509, p12 bundle, CRL, TSA (`timestamp.digicert.com`) |
| HSM | Soporte PKCS#11 (SoftHSM) — desactivado actualmente |
| Anti-doble firma | `PREVENT_DOUBLE_SIGNING=true` |
| Timeout PDF | 30 segundos máx por procesamiento |
| Páginas máx | 1000 páginas por PDF |

---

## 4. Métricas de Importación y Dependencias

### Dependencias Críticas

| Paquete | Versión | Propósito |
|---|---|---|
| FastAPI | 0.103.0 | Framework web |
| Uvicorn | 0.34.0 | Servidor ASGI |
| SQLAlchemy | 2.0.25 | ORM + Pool de conexiones |
| psycopg2-binary | 2.9.10 | Driver PostgreSQL |
| PyMuPDF | 1.27.1 | Manipulación PDF principal |
| pikepdf | ≥10.0.0 | Operaciones PDF alternativo |
| pyhanko | 0.23.0 | Firma digital PAdES/CAdES |
| cryptography | 45.0.7 | Criptografía (AES, RSA, X.509) |
| bcrypt | 4.1.2 | Hashing de contraseñas |
| Pillow | 10.1.0 | Procesamiento de imágenes |
| slowapi | 0.1.9 | Rate limiting |
| reportlab | 4.0.7 | Generación PDF |
| pytesseract | 0.3.10 | OCR |
| aiosmtplib | 3.0.1 | Envío email async |
| Twilio (via requests) | — | SMS OTP |

### Estructura de Imports por Módulo

| Módulo | Imports Estimados |
|---|---|
| `api/` (17 archivos) | ~350 |
| `modules/` (8 archivos) | ~200 |
| `services/` (18 archivos) | ~350 |
| `models/` (7 archivos) | ~80 |
| Core (`main.py`, `payroll_core.py`, `config.py`) | ~150 |
| Resto (`scripts`, `tools`, etc.) | ~209 |

---

## 5. Métricas de Seguridad y Optimizaciones

### Seguridad

| Métrica | Valor |
|---|---|
| Patrones de seguridad | 334 (hash, bcrypt, SHA-256, HMAC, CSRF, sanitize) |
| Middlewares activos | 5 (CORS, CSRF, RequestID, MIME Fix, Diagnostic) |
| Rate limits activos | 19 endpoints protegidos |
| Validadores/Regex | 121 patrones de validación |
| Error handlers globales | 8 (`ValidationError`, `IntegrityError`, `OperationalError`, etc.) |
| PII Masking | Automático en logs (DNI, CUIL, tokens, SHA-256) |
| Sesiones | SHA-256 token hash + TTL 168h (admins) / OTP grace 5min |

### Detalle de Rate Limits

| Endpoint | Límite | Propósito |
|---|---|---|
| Login/Auth | 5/min | Anti brute-force |
| Password Reset | 3-5/min | Anti abuso |
| Verificación OTP | 2-3/min | Anti spam |
| Firma GET | 30/min | Carga de vista |
| Firma POST | 20/min | Submisión |
| Firma Accept | 3/min | Confirmación final |
| Bulk employee | 5/min (IP+User) | Anti DDoS importación |

### Optimizaciones Existentes

| Optimización | Detalle |
|---|---|
| Connection Pooling | `pool_size=10`, `max_overflow=15`, total=25 conexiones máx |
| `pool_pre_ping` | Auto-validación de conexiones antes de uso |
| `pool_recycle` | 300s (evita conexiones stale) |
| PDF Offloading | `run_in_executor` con 36 threads (no bloquea event loop) |
| Health Cache | `/health/deep` cacheado 60s (anti-DDoS) |
| Atomic File Writes | `tempfile` + `os.replace` con retry |
| Batch Session GC | `LIMIT 1000` en `DELETE` para evitar locks largos |
| Structured Logging | JSON formatter en producción (ELK-ready) |
| Rotating Logs | 10MB max, 5 backups por archivo |
| Background Tasks | 3 async supervisors (maintenance, webhook, storage integrity) |

---

## 6. Modelo de Base de Datos

### 23 Tablas ORM

| Tabla | Función |
|---|---|
| `users` | Usuarios del sistema |
| `verification_codes` | Códigos OTP |
| `user_sessions` | Sesiones activas |
| `password_reset_tokens` | Reset de contraseñas |
| `user_signatures` | Firmas almacenadas |
| `organizations` | Organizaciones/Empresas |
| `employees` | Empleados |
| `company_signers` | Firmantes empresa |
| `payroll_batches` | Lotes de recibos |
| `payroll_receipts` | Recibos individuales |
| `signature_requests` | Solicitudes de firma |
| `signature_evidence` | Evidencia criptográfica |
| `signing_logs` | Log de firmas |
| `signature_events` | Eventos de firma |
| `receipt_seals` | Sellos QR validables |
| `file_encryption_metadata` | Metadata de encriptación |
| `webhook_outbox` | Cola de webhooks |
| `audit_log` | Auditoría completa |
| `email_events` | Eventos de email |
| `employee_extra_data` | Data extra empleados |
| `import_jobs` | Jobs de importación |
| `import_job_rows` | Filas de importación |
| `notifications` | Notificaciones |

---

## 7. Modelo Teórico de Capacidad en Producción

### Arquitectura Actual: Single-Process Uvicorn

```text
┌─────────────────────────────┐
│       Uvicorn (1 worker)     │
│      asyncio event loop      │
│                              │
│  ┌─────────────────────────┐ │
│  │  FastAPI App (v4.2.3)   │ │
│  │  119 endpoints          │ │
│  │  5 middlewares           │ │
│  └─────────────────────────┘ │
│                              │
│  ┌──────────┐ ┌───────────┐  │
│  │ DB Pool  │ │PDF Thread │  │
│  │ 10+15=25 │ │Pool (36)  │  │
│  └──────────┘ └───────────┘  │
│                              │
│  ┌─────────────────────────┐ │
│  │  3 Background Tasks     │ │
│  │  (maintenance/webhook/  │ │
│  │   storage integrity)    │ │
│  └─────────────────────────┘ │
└─────────────────────────────┘
          │
┌─────────┴─────────┐
│    PostgreSQL      │
│  (max_conn ~100)   │
└───────────────────┘
```

### Cálculo Teórico de Usuarios Concurrentes

#### A. Operaciones Ligeras (Login, Listados, Dashboard)

| Factor | Valor | Notas |
|---|---|---|
| Event loop capacity | ~1,000 req/s | FastAPI async puro (I/O bound) |
| DB pool (25 conn) | ~500 queries/s | Asumiendo 50ms avg query time |
| Rate limits | No limitantes aquí | 30/min por IP |
| Cuello de botella | DB Pool | 25 conexiones |

Resultado: ~150-250 usuarios simultáneos pueden operar el dashboard, consultar recibos y navegar sin degradación.

#### B. Operaciones Pesadas (Firma Digital + PDF)

| Factor | Valor | Notas |
|---|---|---|
| PDF ThreadPool | 36 threads | Procesa PDFs en paralelo |
| Tiempo promedio firma | ~2-5 seg | PyMuPDF + pyhanko + QR + stamp |
| Throughput firma | ~7-18 firmas/seg | 36 threads / 2-5s avg |
| Timeout PDF | 30s max | Protección contra docs gigantes |
| Páginas máx | 1000 páginas | |

Resultado: ~7-18 firmas simultáneas procesándose en paralelo, con un throughput sostenido de ~420-1,080 firmas/hora.

#### C. Operaciones de Importación (Excel/XLS)

| Factor | Valor | Notas |
|---|---|---|
| Rate limit bulk | 5/min per IP+User | Protección |
| Procesamiento | Sync en request | Bloquea el event loop parcialmente |
| Tamaño max archivo | 50 MB | Configurable |

Resultado: ~3-5 importaciones masivas simultáneas antes de degradación.

### Resumen: Capacidad Teórica Total

| Escenario | Usuarios Concurrentes | Notas |
|---|---|---|
| Navegación / Dashboard | 150-250 | Operaciones ligeras (SELECT, listados) |
| Firma Digital activa | 30-50 | Procesamiento PDF pesado, 36 threads |
| Pico mixto realista | 80-120 | 70% lectura + 20% firma + 10% admin |
| Carga extrema (degradada) | 200-300 | Latencia >2s, posibles timeouts en firma |
| Límite absoluto (caída) | ~500+ | DB pool agotado, event loop saturado |

### Carga por Período (modelo de uso SaaS payroll)

| Período | Patrón | Estimación |
|---|---|---|
| Día normal | Admins suben lotes, empleados consultan | ~20-40 concurrentes |
| Día de liquidación | Subida masiva de PDFs + envío notificaciones | ~50-80 concurrentes |
| Pico de firma | Empleados firmando post-notificación | ~80-150 concurrentes |
| Fin de mes | Todas las organizaciones simultáneamente | ~100-200 concurrentes |

---

## 8. Factores Limitantes (Cuellos de Botella)

### WARNING

#### Factor #1: Single Worker Uvicorn

El servidor corre con 1 solo worker (proceso). Esto significa:

- Un solo event loop de Python
- Si cualquier operación sincrónica bloquea, TODO se frena
- No aprovecha los 18 cores del CPU (solo usa ~1-2 para el event loop)

### WARNING

#### Factor #2: DB Pool Size = 25

Con 25 conexiones máximas a PostgreSQL:

- Cada request que hace queries "ocupa" una conexión por su duración
- Consultas lentas (JOINs pesados, importación Excel) agotan el pool rápido
- Las 3 background tasks también consumen conexiones

### IMPORTANT

#### Factor #3: Sin Reverse Proxy / Load Balancer

No hay nginx/HAProxy delante:

- Sin buffering de slow clients
- Sin compresión gzip de respuestas
- Sin serving estático optimizado (el CSS/JS pasa por Python)
- Sin protección contra Slowloris u otros ataques L7

---

## 9. Optimizaciones Recomendadas para Escalar

### Nivel 1: Cambios de configuración (sin código)

| Cambio | Impacto | Esfuerzo |
|---|---|---|
| Agregar `--workers 4` a uvicorn | 4x capacidad instantánea | 1 línea en systemd |
| Poner Nginx delante | +30% throughput, SSL offloading, gzip | 30 min config |
| `DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=30` | +100% capacity DB | 2 env vars |
| Habilitar Gunicorn + Uvicorn workers | Multi-proceso robusto | 1 archivo config |

### Nivel 2: Cambios menores de código

| Cambio | Impacto | Esfuerzo |
|---|---|---|
| Redis para rate limiting (en vez de in-memory) | Rate limits compartidos entre workers | 2-3h |
| Redis para session cache | -50% queries de auth | 4-6h |
| Async DB (`asyncpg` + `encode/databases`) | Event loop nunca bloquea por DB | 8-16h |

### Nivel 3: Arquitectura

| Cambio | Impacto | Esfuerzo |
|---|---|---|
| Worker separado para firmas (Celery/RQ) | Firma no impacta al API | 2-3 días |
| CDN para assets estáticos | 0 carga de Python para UI | 2h |
| Read replicas PostgreSQL | Lectura distribuida | 4-8h |

---

## 10. Estimación Final: ¿Cuántas Organizaciones Soporta?

Asumiendo perfil típico de empresa de 50-200 empleados que liquida 1x por mes:

| Config | Organizaciones | Empleados Totales | Notas |
|---|---|---|---|
| Actual (1 worker) | 15-30 | ~3,000-6,000 | Funciona bien si no firman todos al mismo tiempo |
| Con 4 workers + nginx | 50-100 | ~10,000-20,000 | Configuración productiva básica |
| Con Celery + Redis | 200-500 | ~40,000-100,000 | Setup empresarial |
| Full scale (K8s) | 1,000+ | ~200,000+ | Requiere re-arquitectura |

### TIP

Para la configuración actual (1 worker, 214 MB RAM, 18 cores desperdiciados), el sistema puede manejar cómodamente ~20-30 empresas con 3,000-5,000 empleados totales, siempre que no todos firmen a la vez. El recurso más subutilizado son los 17 cores libres — agregar workers multiplicaría la capacidad casi linealmente.
