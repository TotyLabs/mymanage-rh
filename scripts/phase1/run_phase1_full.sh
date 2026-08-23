#!/usr/bin/env bash
# Run Phase 1 full execution script
# Usage: sudo ./run_phase1_full.sh

set -euo pipefail

ROOT_PATH="$(cd "$(dirname "$0")/../.." && pwd)"
NGINX_SRC="$ROOT_PATH/deployment/nginx/payroll_nginx.conf"
NGINX_DST="/etc/nginx/sites-available/payroll"
NGINX_ENABLED_SYM="/etc/nginx/sites-enabled/payroll"
GUNICORN_SERVICE_SRC="$ROOT_PATH/deployment/gunicorn.service"
GUNICORN_SERVICE_DST="/etc/systemd/system/gunicorn.service"
LOGFILE="/var/log/youcompare_phase1_run.log"

echo "Phase 1 full runner" | tee -a "$LOGFILE"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root. Re-run with sudo." | tee -a "$LOGFILE"
  exit 1
fi

confirm(){
  read -r -p "$1 [y/N]: " resp
  case "$resp" in
    [yY][eE][sS]|[yY]) return 0 ;;
    *) return 1 ;;
  esac
}

timestamp(){ date +"%Y-%m-%d %H:%M:%S"; }

echo "--- $(timestamp) Starting Phase 1 run" | tee -a "$LOGFILE"

### 1) Deploy Nginx config
if [ -f "$NGINX_SRC" ]; then
  echo "Found Nginx config at $NGINX_SRC" | tee -a "$LOGFILE"
  if [ -f "$NGINX_DST" ]; then
    echo "Backup existing Nginx config to ${NGINX_DST}.bak" | tee -a "$LOGFILE"
    cp -a "$NGINX_DST" "${NGINX_DST}.bak.$(date +%s)"
  fi
  cp "$NGINX_SRC" "$NGINX_DST"
  ln -sf "$NGINX_DST" "$NGINX_ENABLED_SYM"
  echo "Testing Nginx config..." | tee -a "$LOGFILE"
  if nginx -t 2>/tmp/nginx_test.err; then
    echo "Nginx config OK. Reloading nginx..." | tee -a "$LOGFILE"
    systemctl reload nginx || systemctl restart nginx
    echo "Nginx reloaded." | tee -a "$LOGFILE"
  else
    echo "Nginx config test failed. See /tmp/nginx_test.err" | tee -a "$LOGFILE"
    cat /tmp/nginx_test.err | tee -a "$LOGFILE"
    if confirm "Proceed despite nginx test failure?"; then
      echo "User chose to continue." | tee -a "$LOGFILE"
    else
      echo "Aborting." | tee -a "$LOGFILE"
      exit 1
    fi
  fi
else
  echo "Nginx config not found at $NGINX_SRC. Skipping Nginx deploy." | tee -a "$LOGFILE"
fi

### 2) Deploy Gunicorn systemd unit
if [ -f "$GUNICORN_SERVICE_SRC" ]; then
  echo "Installing gunicorn systemd unit from $GUNICORN_SERVICE_SRC" | tee -a "$LOGFILE"
  if [ -f "$GUNICORN_SERVICE_DST" ]; then
    cp -a "$GUNICORN_SERVICE_DST" "${GUNICORN_SERVICE_DST}.bak.$(date +%s)"
  fi
  cp "$GUNICORN_SERVICE_SRC" "$GUNICORN_SERVICE_DST"
  systemctl daemon-reload
  systemctl enable --now gunicorn || true
  systemctl restart gunicorn || true
  echo "Gunicorn service installed and restarted (status may be shown below)." | tee -a "$LOGFILE"
  systemctl status --no-pager gunicorn | sed -n '1,6p' | tee -a "$LOGFILE"
else
  echo "Gunicorn service file not found at $GUNICORN_SERVICE_SRC. Skipping." | tee -a "$LOGFILE"
fi

### 3) Ensure Redis running (optional install)
REDIS_SERVICE_NAME="redis-server"
if systemctl list-units --type=service --all | grep -q "$REDIS_SERVICE_NAME"; then
  echo "Redis systemd unit found. Starting/enabling..." | tee -a "$LOGFILE"
  systemctl enable --now "$REDIS_SERVICE_NAME" || true
  systemctl restart "$REDIS_SERVICE_NAME" || true
  systemctl status --no-pager "$REDIS_SERVICE_NAME" | sed -n '1,6p' | tee -a "$LOGFILE"
else
  if confirm "Redis not found as service. Install redis-server via apt (Debian/Ubuntu)?"; then
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update && apt-get install -y redis-server
      systemctl enable --now redis-server
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y redis
      systemctl enable --now redis
    else
      echo "No supported package manager found. Please install Redis manually." | tee -a "$LOGFILE"
    fi
  else
    echo "Skipping Redis installation as per user choice." | tee -a "$LOGFILE"
  fi
fi

### 4) Run simple micro-benchmark (python script)
if command -v python3 >/dev/null 2>&1; then
  if confirm "Run simple local micro-benchmark against http://127.0.0.1:8000/health now?"; then
    python3 "$ROOT_PATH/scripts/phase1/simple_benchmark.py" http://127.0.0.1:8000/health 20 100 | tee -a "$LOGFILE"
  else
    echo "Skipping micro-benchmark." | tee -a "$LOGFILE"
  fi
else
  echo "python3 not found; cannot run micro-benchmark." | tee -a "$LOGFILE"
fi

### 5) Optional: run k6 if installed
if command -v k6 >/dev/null 2>&1; then
  if confirm "Run k6 smoke test (50 vus x 2m)?"; then
    k6 run --vus 50 --duration 2m "$ROOT_PATH/scripts/benchmarks/k6/payroll_test.js" | tee -a "$LOGFILE"
  fi
else
  echo "k6 not installed; skipping k6 test." | tee -a "$LOGFILE"
fi

### 6) DB stats and optional index application
if confirm "Run DB query stats using pg_stat_statements (requires DATABASE_URL env)?"; then
  read -r -p "Export DATABASE_URL (postgresql://user:pass@host:5432/db) and press Enter when ready..."
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL not set; aborting DB stats step." | tee -a "$LOGFILE"
  else
    su -s /bin/sh -c "${PSQL:-psql} \"$DATABASE_URL\" -c \"\x on\" -c \"SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY total_time DESC LIMIT 20;\"" $(logname) | tee -a "$LOGFILE" || true
    if confirm "Apply an index now? (you must provide a CREATE INDEX CONCURRENTLY ... statement)"; then
      read -r -p "Paste the CREATE INDEX CONCURRENTLY SQL statement: " SQL
      if [ -n "$SQL" ]; then
        su -s /bin/sh -c "${PSQL:-psql} \"$DATABASE_URL\" -c \"$SQL\"" $(logname) | tee -a "$LOGFILE" || true
      fi
    fi
  fi
fi

echo "--- $(timestamp) Phase 1 run finished" | tee -a "$LOGFILE"
echo "Logs written to $LOGFILE"

exit 0
