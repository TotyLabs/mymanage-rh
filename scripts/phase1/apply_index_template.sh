#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 'CREATE INDEX CONCURRENTLY ...'"
  exit 1
fi

SQL="$1"
PSQL=${PSQL:-psql}
DB_URL=${DATABASE_URL:-}

if [ -z "$DB_URL" ]; then
  echo "Exporta DATABASE_URL antes de ejecutar."
  exit 1
fi

echo "Ejecutando índice: $SQL"
${PSQL} "$DB_URL" -c "$SQL"
echo "Índice aplicado (si no hubo errores)."
