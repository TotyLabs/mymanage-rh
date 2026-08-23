#!/usr/bin/env bash

set -e

echo "=========================================="
echo "   MyManageRH - Inicialización"
echo "=========================================="
echo ""

# --------------------------------------------------
# 1. Verificar Python
# --------------------------------------------------
if ! command -v python3 &> /dev/null
then
    echo "❌ Python3 no está instalado"
    exit 1
fi

echo "✅ Python detectado:"
python3 --version
echo ""

# --------------------------------------------------
# 2. Crear entorno virtual
# --------------------------------------------------
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
else
    echo "ℹ️ Entorno virtual ya existe"
fi
echo ""

# --------------------------------------------------
# 3. Activar entorno virtual (Linux)
# --------------------------------------------------
echo "🔄 Activando entorno virtual..."
source venv/bin/activate
echo "✅ Entorno activado"
echo ""

# --------------------------------------------------
# 4. Cargar variables desde .env
# --------------------------------------------------
if [ -f ".env" ]; then
    echo "📄 Cargando variables desde .env"

    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^#.*$ ]] || [[ -z "$line" ]] && continue
        export "$(echo "$line" | tr -d '\r')"
    done < ".env"

else
    echo "⚠️ No se encontró archivo .env"
fi
echo ""

# --------------------------------------------------
# 5. Actualizar pip
# --------------------------------------------------
echo "⬆️ Actualizando pip..."
python3 -m pip install --upgrade pip
echo ""

# --------------------------------------------------
# 6. Instalar dependencias
# --------------------------------------------------
if [ -f "requirements.txt" ]; then
    echo "📥 Instalando dependencias..."
    pip install -r requirements.txt
else
    echo "⚠️ No se encontró requirements.txt"
fi
echo ""

# --------------------------------------------------
# 7. Verificar DATABASE_URL
# --------------------------------------------------
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL no está definida."
    echo ""
    echo "Ejemplo:"
    echo "DATABASE_URL=postgresql://postgres:TU_PASSWORD@localhost:5432/payroll_db"
else
    echo "✅ DATABASE_URL detectada"
fi
echo ""

# --------------------------------------------------
# 8. Crear storage
# --------------------------------------------------
STORAGE_PATH=${STORAGE_PATH:-"./storage"}

if [ ! -d "$STORAGE_PATH" ]; then
    echo "📂 Creando storage en $STORAGE_PATH"
    mkdir -p "$STORAGE_PATH"
else
    echo "ℹ️ Storage ya existe"
fi
echo ""

# --------------------------------------------------
# 9. Instalar Root CA (Opcional)
# --------------------------------------------------
echo "🔐 Seguridad: Certificados de Firma"
read -p "Install Root CA? (y/n): " c

if [ "$c" = "y" ]; then
    python3 tools/install_root_ca.py
fi
echo ""

# --------------------------------------------------
# 10. Verificar conexión a PostgreSQL
# --------------------------------------------------
echo "🧪 Verificando conexión a base de datos..."

python3 << END
import os
from sqlalchemy import create_engine, text

db_url = os.getenv("DATABASE_URL")

if not db_url:
    print("❌ DATABASE_URL no definida.")
else:
    try:
        engine = create_engine(db_url)

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        print("✅ Conexión PostgreSQL OK")

    except Exception as e:
        print("❌ Error conectando a PostgreSQL:")
        print(e)
END

echo ""

# --------------------------------------------------
# 11. Restaurar dump automáticamente (Opcional)
# --------------------------------------------------
if [ -f "backup/payroll_db_migration_dump.sql" ]; then
    echo "📥 Dump SQL detectado"

    read -p "¿Restaurar dump ahora? (y/n): " restore

    if [ "$restore" = "y" ]; then
        export PGPASSWORD=$(echo $DATABASE_URL | sed -n 's|.*://.*:\(.*\)@.*|\1|p')

        psql \
          -U postgres \
          -d payroll_db \
          -h localhost \
          -f backup/payroll_db_migration_dump.sql

        echo "✅ Dump restaurado"
    fi
else
    echo "ℹ️ No se encontró dump SQL"
fi

echo ""

# --------------------------------------------------
# 12. Iniciar servidor
# --------------------------------------------------
echo "🚀 Iniciando / actualizando el servidor..."
echo ""

if [ "$PRODUCTION" = "true" ]; then
    # Verificar si el servicio systemd existe
    if systemctl list-unit-files | grep -q "^youcompare-payroll.service"; then
        echo "⚙️ Detectado entorno de producción y servicio systemd (youcompare-payroll.service)."
        echo "🔄 Reiniciando el servicio para aplicar los cambios..."
        sudo systemctl restart youcompare-payroll
        echo "✅ Servicio reiniciado."
        echo ""
        echo "📋 Últimos logs del servicio:"
        sudo journalctl -u youcompare-payroll -n 10 --no-pager
        echo ""
        echo "💡 Podés seguir los logs en tiempo real con: sudo journalctl -u youcompare-payroll -f"
    else
        echo "⚠️ PRODUCTION=true pero no se encontró el servicio systemd 'youcompare-payroll.service'."
        echo "🚀 Iniciando server.py manualmente..."
        python3 server.py
    fi
else
    echo "💻 Modo desarrollo detectado (PRODUCTION=false)."
    echo "🚀 Iniciando server.py manualmente..."
    python3 server.py
fi
