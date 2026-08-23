# Guia rápida de ajuste de Gunicorn

Puntos clave:

- `workers`: típicamente `2 x CPUs + 1` para sync workers. Para `uvicorn.workers.UvicornWorker` ajuste conservador según CPU.
- `timeout`: mantener en 120-180s según operaciones largas; reducir si no se espera trabajo largo.
- `max_requests` y `max_requests_jitter`: mantener para reciclar workers y mitigar fugas de memoria.

Ejemplo recomendado (si hay 4 CPUs):

```
workers = 9
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 180
graceful_timeout = 120
max_requests = 2000
max_requests_jitter = 200
```

Advertencia: aumentar `workers` incrementa consumo de conexiones DB (pool por worker). Ajustar `DB_POOL_SIZE` en `config.py` en consecuencia.
