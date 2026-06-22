#!/bin/bash
# check-ports.sh — verifica que los puertos necesarios estén disponibles
# Uso: bash check-ports.sh

set -e

if [ ! -f .env ]; then
    echo "Error: no se encontró el archivo .env"
    exit 1
fi
set -a
source .env
set +a

POSTGRES_MODE=${POSTGRES_MODE:-container}
POSTGRES_DB=${POSTGRES_DB:-}

# Lista de "servicio:puerto" separados por espacio
CHECKS="Django(APP_PORT):${APP_PORT:-8000}"
[ -n "${POSTGRES_DB}" ] && [ "${POSTGRES_MODE}" = "container" ] && CHECKS="${CHECKS} PostgreSQL(POSTGRES_HOST_PORT):${POSTGRES_HOST_PORT:-5432}"

echo "Verificando disponibilidad de puertos..."
echo ""

ALL_OK=true
for ITEM in ${CHECKS}; do
    SERVICE="${ITEM%%:*}"
    PORT="${ITEM##*:}"
    if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        echo "  ✗ OCUPADO  Puerto ${PORT} — ${SERVICE}"
        ALL_OK=false
    else
        echo "  ✓ libre    Puerto ${PORT} — ${SERVICE}"
    fi
done

echo ""
if ${ALL_OK}; then
    echo "Todos los puertos están disponibles."
    exit 0
else
    echo "Hay conflictos de puertos. Ajusta APP_PORT en .env."
    exit 1
fi
