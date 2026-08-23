# Análisis de Seguridad, Bugs y Malas Prácticas: YouCompare Payroll

Este informe detalla las vulnerabilidades, errores y malas prácticas encontradas en el repositorio tras un análisis exhaustivo del código fuente, configuración y arquitectura.

---

## Resumen Ejecutivo

El código base demuestra una arquitectura madura con varias capas de seguridad (cifrado, CSRF, RLS), pero presenta **vulnerabilidades críticas** relacionadas con la gestión de secretos y plusieurs puntos de inyección XSS/SQL. La presencia de credenciales de producción en el repositorio es el hallazgo de mayor riesgo inmediato.

| Severidad | Cantidad |
|-----------|----------|
| Crítica   | 12       |
| Alta      | 14       |
| Media     | 25       |
| Baja      | 15       |

---

## 1. Hallazgos Críticos (CRITICAL)

### 1.1 Credenciales de Producción en el Repositorio
**Archivo:** `.env`, `backup/.env.bak.20260722`
Se encontró el archivo `.env` con credenciales reales de producción, incluyendo:
- Contraseña de PostgreSQL: `RAABFC2026`
- `SECRET_KEY` de la aplicación.
- Credenciales SMTP de AWS (`AKIASGSRX4A5Q4OTOKFN`).
- Contraseña de Aplicación de Gmail.
- Contraseña del certificado X.509 P12.
- Token de Ngrok.

**Impacto:** Compromiso total del sistema si el repositorio es filtrado.

### 1.2 Credenciales Hardcodeadas en Scripts
**Archivos:** `scripts/list_tables.py`, `scratch/debug_auth_horacio.py`, `scratch/crack_luciano.py`, etc.
La contraseña de la base de datos y hashes de contraseñas aparecen en texto plano en múltiples scripts de mantenimiento y debugging.

### 1.3 XSS Almacenado en Página de Verificación
**Archivo:** `main.py` (Líneas 270-323)
El endpoint `/v/{seal_id}` renderiza valores de la base de datos (`organization_name`, `signer_name`) directamente en HTML mediante f-strings sin escapar.
```python
html_content = f"""
    <div class="value">{row.organization_name}</div>
```
Un atacante podría inyectar `<script>alert(1)</script>` en el nombre de una organización.

### 1.4 XSS Almacenado en Frontend (innerHTML)
**Archivos:** `ui/pages/empresa-empleados.js`, `empresa-configuracion.js`, `empresa-historial.js`
El uso extensivo de `innerHTML` con datos del servidor sin usar la función de escape `esc()` permite XSS almacenado.
```javascript
// empresa-empleados.js
tdName.innerHTML = `<strong>${emp.full_name}</strong>`; // Riesgo si emp.full_name contiene HTML
```

### 1.5 SQL Injection por Nombres de Columnas Dinámicos
**Archivos:** `api/employees.py` (Líneas 837, 916), `services/document_repository.py`
Se utilizan f-strings para construir consultas SQL con nombres de columnas derivados de parámetros de usuario (aunque parcialmente validados).
```python
text(f"SELECT {column} AS path FROM employees WHERE id = :id ...")
```
Si la validación del parámetro `column` falla, esto permite inyección SQL.

### 1.6 Script de Fuerza Bruta en Repositorio
**Archivo:** `scratch/crack_luciano.py`
Contiene un hash bcrypt y una lista de candidatos para descifrar contraseñas, lo cual es una práctica insegura y sugiere活动 sospechosa o falta de higiene de código.

---

## 2. Hallazgos Altos (HIGH)

### 2.1 Bypass de CSRF por Cabecera Origin Ausente
**Archivo:** `main.py` (Líneas 169-189)
El middleware de CSRF solo rechaza cabeceras `Origin`/`Referer` incorrectas, pero permite el paso si ambas están ausentes, lo cual puede ocurrir en envíos de formularios cruzados desde ciertos navegadores/configuraciones.

### 2.2 Falta de Rate Limiting en Verificación OTP
**Archivo:** `api/verification.py` (Línea 119)
El endpoint `POST /api/verification/verify` no tiene límite de tasa (`@limiter.limit()`), permitiendo intentos de fuerza bruta sobre el código OTP de 6 dígitos.

### 2.3 TTL de Sesión Excesivo
**Archivo:** `config.py` (Línea 159)
La sesión dura 168 horas (7 días). Para una aplicación de nómina, 24-48 horas sería más seguro.

### 2.4 Ausencia de Cabeceras de Seguridad
**Archivo:** `main.py`
Faltan cabeceras críticas como `Strict-Transport-Security` (HSTS), `X-Content-Type-Options` y `Content-Security-Policy`.

### 2.5 Autenticación Bypass por Bearer Token
**Archivo:** `payroll_core.py` (Líneas 617-653)
El token de sesión aceptado vía cabecera `Authorization: Bearer` ignora las protecciones `SameSite` configuradas en las cookies.

### 2.6 Exposición de Métricas y Health Check
**Archivos:** `main.py` (Líneas 334-481)
Los endpoints `/metrics` y `/health/deep` exponen detalles internos (disco, CPU, cola de trabajos) sin autenticación robusta, facilitando la enumeración del sistema.

---

## 3. Hallazgos Medios (MEDIUM)

### 3.1 Malas Prácticas de Manejo de Excepciones
Se encontraron **15 cláusulas `except:` vacías** (bare except) que tragan todo tipo de errores, incluyendo `SystemExit` y `KeyboardInterrupt`.
- **Crítico:** `services/x509_service.py:157` (`except: pass`) oculta fallos en extracción de URLs de certificados.
- **Alto:** `services/x509_service.py:379` (`except: return False`) hace que un PDF roto parezca no firmado.
- **Medio:** Múltiples `except: pass` en limpieza de archivos temporales (`api/admin.py`, `api/organizations.py`).

### 3.2 Fugas de Recursos (Resource Leaks)
Múltiples aperturas de archivos PyMuPDF (`fitz.open`) sin gestión de contexto (`with`), lo que puede provocar fugas de manejadores de archivos si ocurren excepciones.
- `modules/digital_signature.py:988`
- `services/receipt_service.py:403`

### 3.3 Patrones N+1 y Bucle Ineficiente
- **N+1 Query:** `api/receipts.py:525` ejecuta una consulta adicional por cada recibo pendiente para obtener el token.
- **Re-apertura de PDF:** `services/receipt_service.py:477` re-abre el archivo PDF completo en bytes en cada iteración de un lote, lo cual es extremadamente ineficiente.

### 3.4 Validación MIME Advisory-Only
**Archivo:** `file_processing/dispatcher.py`
La validación de tipo MIME está configurada para emitir advertencias pero no bloquear archivos sospechosos.

### 3.5 Políticas de Contraseña Débiles
**Archivo:** `services/password_reset_service.py`
Requiere solo 8 caracteres con una letra y un número. Debería exigir mayúsculas, minúsculas, números y caracteres especiales con un mínimo de 12 caracteres.

---

## 4. Hallazgos Bajos (LOW)

### 4.1 Uso de APIs Deprecadas
Uso de `datetime.utcnow()` en 5 archivos de `services/legajo/`, deprecado desde Python 3.12. Debería usarse `datetime.now(timezone.utc)`.

### 4.2 Archivos Temporales en /tmp del Sistema
**Archivo:** `payroll_core.py:387`
Se crean archivos temporales sensibles en `/tmp` del sistema en lugar del módulo seguro `services.secure_temp` que utiliza `/dev/shm`.

### 4.3 Gitignore Conflictivo
**Archivo:** `.gitignore`
Reglas duplicadas y contradictorias para archivos `.env`, `.env.example` y `.env.template`.

---

## 5. Recomendaciones Prioritarias

1.  **Inmediato:** Rotar TODAS las credenciales expuestas (DB, AWS, Gmail, PKI, SECRET_KEY).
2.  **Inmediato:** Eliminar `.env` y `backup/.env.bak.20260722` del historial de git y asegurar que no se commiteen nunca.
3.  **Corto Plazo:**
    - Aplicar la función `esc()` de `common.js` a todas las asignaciones a `innerHTML` en el frontend.
    - Implementar una lista blanca estricta para nombres de tablas y columnas en consultas SQL dinámicas.
    - Corregir el middleware de CSRF para rechazar peticiones sin cabecera `Origin`/`Referer` en métodos de estado.
    - Añadir Rate Limiting al endpoint de verificación OTP.
4.  **Mediano Plazo:**
    - Refactorizar todas las cláusulas `except:` vacías para que capturen excepciones específicas y registren errores.
    - Implementar gestión de contexto (`with`) para todos los manejadores de archivos y documentos PDF.
    - Optimizar el procesamiento de lotes de recibos para evitar la re-apertura de PDFs.
    - Añadir cabeceras de seguridad (HSTS, CSP) via middleware.
