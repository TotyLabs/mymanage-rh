#!/usr/bin/env bash
set -euo pipefail

PSQL=${PSQL:-psql}
DB_URL=${DATABASE_URL:-}

if [ -z "$DB_URL" ]; then
  echo "Por favor exporta DATABASE_URL con la conexión psql (ej: export DATABASE_URL=postgresql://user:pass@host:5432/db)"
  exit 1
fi

echo "Top 20 queries by total_time (pg_stat_statements must estar habilitado):"
${PSQL} "$DB_URL" -c "\x on" -c "SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY total_time DESC LIMIT 20;"
