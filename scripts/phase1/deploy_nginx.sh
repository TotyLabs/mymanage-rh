#!/usr/bin/env bash
# Despliega la configuración de Nginx y recarga el servicio.
set -euo pipefail

CONF_SRC="$(pwd)/deployment/nginx/payroll_nginx.conf"
CONF_DST="/etc/nginx/sites-available/payroll"

if [[ $EUID -ne 0 ]]; then
  echo "Este script requiere permisos root. Ejecuta con sudo."
  exit 1
fi

echo "Copiando $CONF_SRC -> $CONF_DST"
cp "$CONF_SRC" "$CONF_DST"
ln -sf "$CONF_DST" /etc/nginx/sites-enabled/payroll
echo "Probando configuración de nginx..."
nginx -t
echo "Recargando nginx..."
systemctl reload nginx
echo "Nginx desplegado y recargado."
