# Fase 1 — Playbook de ejecución

Objetivo: estabilizar y optimizar el sistema para obtener datos reales y aumentar capacidad con bajo riesgo.

Resumen de tareas (orden ejecutable):

1. Desplegar Nginx como reverse-proxy (configuración de ejemplo en `deployment/nginx/payroll_nginx.conf`).
2. Revisar y aplicar ajustes de Gunicorn según CPU/memoria (guía en `docs/gunicorn_tuning.md`).
3. Activar health checks y métricas básicas (ver `docs/health_checks.md`).
4. Ejecutar benchmarks controlados (`scripts/benchmarks/k6/payroll_test.js` y `scripts/benchmarks/locust/locustfile.py`).
5. Identificar consultas lentas y aplicar índices críticos (ver pasos y comandos abajo).
6. Recolectar baseline y revisar resultados; si hay mejoras, promover a staging y repetir.

Comandos rápidos para benchmarks

K6 (JS):
```
k6 run --vus 50 --duration 2m scripts/benchmarks/k6/payroll_test.js
```

Locust (Python):
```
locust -f scripts/benchmarks/locust/locustfile.py --host=http://localhost:8000
```

Pasos básicos para identificación de queries lentas

- Habilitar `pg_stat_statements` en PostgreSQL (si no está activado).
- Ejecutar consultas: SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 20;
- Revisar y planificar índices para las consultas más costosas; aplicarlos en staging y medir impacto.

Rollback rápido

- Restaurar configuración de Nginx anterior y reiniciar Gunicorn.
- Revertir índices si impactan negativamente (hacer en ventana de mantenimiento).

Puntos de decisión

- Si tras optimizaciones la latencia y p95 mejoran significativamente, avanzar a Fase 2.
- Si PostgreSQL sigue saturado, evaluar aumento de recursos o réplica de lectura.
