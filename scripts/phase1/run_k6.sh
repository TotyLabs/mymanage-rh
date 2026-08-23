#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$(pwd)/scripts/benchmarks/k6/payroll_test.js"
VUS=${1:-50}
DURATION=${2:-2m}

command -v k6 >/dev/null 2>&1 || { echo "k6 no está instalado. Instalarlo antes de ejecutar."; exit 1; }

echo "Ejecutando k6: vus=$VUS duration=$DURATION"
k6 run --vus $VUS --duration $DURATION "$SCRIPT"
