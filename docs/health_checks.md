# Health checks y métricas básicas

Endpoints recomendados:

- `/health` : devuelve 200 OK y estado básico (db reachable, queue reachable si aplica).
- `/ready` : readiness probe para indicar si la app puede atender tráfico.

Implementación mínima (FastAPI ejemplo):

```
from fastapi import FastAPI
import psycopg2

app = FastAPI()

@app.get('/health')
def health():
    # chequeo simple de DB (opcional, rápido)
    try:
        # ejecutar una consulta muy rápida o ping
        return {'status': 'ok'}
    except Exception:
        return {'status': 'unhealthy'}

@app.get('/ready')
def ready():
    return {'ready': True}
```

Métricas y recolección:

- Exponer métricas Prometheus usando `prometheus_client` o `fastapi-exporter`.
- Recolectar CPU, memoria, latencia por endpoint y p95/p99.
