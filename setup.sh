#!/bin/bash
# setup.sh — configuración inicial del proyecto. Genera el archivo .env.
# Uso: bash setup.sh   (o: make setup)

set -e
set -a  # auto-exportar para que el bloque Python las vea

gen_secret() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
get_env() {
    local val
    val=$(grep "^${1}=" .env 2>/dev/null | head -1 | cut -d'=' -f2-)
    echo "$val" | sed "s/^'//;s/'$//"
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Setup: Tk Redline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
[ -f .env ] && echo "  .env existente detectado — sus valores se usan como default." && echo ""

# ── Entorno ───────────────────────────────────────────────────────────────────
_ENV_DEFAULT=$(get_env DEBUG)
[ "${_ENV_DEFAULT}" = "True" ] && _ENV_DEFAULT=dev || _ENV_DEFAULT=prod
read -p "¿Entorno? (dev/prod) [${_ENV_DEFAULT}]: " ENV_TYPE
ENV_TYPE=${ENV_TYPE:-${_ENV_DEFAULT}}
echo ""

DIR_NAME=$(basename "$(pwd)")
_DEFAULT=$(get_env PROJECT_NAME)
read -p "Nombre del proyecto [${_DEFAULT:-${DIR_NAME}}]: " PROJECT_NAME
PROJECT_NAME=${PROJECT_NAME:-${_DEFAULT:-${DIR_NAME}}}
PROJECT_NAME=$(echo "${PROJECT_NAME}" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')
echo ""

_DEFAULT=$(get_env APP_PORT)
read -p "Puerto de la app Django [${_DEFAULT:-8000}]: " APP_PORT
APP_PORT=${APP_PORT:-${_DEFAULT:-8000}}
echo ""

# ── Base de datos ─────────────────────────────────────────────────────────────
echo "Base de datos:"
echo "  1) SQLite — por defecto (sin servicios extra)"
echo "  2) PostgreSQL en contenedor Docker"
_PG_CURRENT=$(get_env POSTGRES_DB)
[ -n "${_PG_CURRENT}" ] && _DB_OPT=2 || _DB_OPT=1
read -p "Opción [${_DB_OPT}]: " DB_CHOICE
DB_CHOICE=${DB_CHOICE:-${_DB_OPT}}
echo ""

POSTGRES_MODE=""; POSTGRES_DB=""; POSTGRES_USER=""; POSTGRES_PASSWORD=""
POSTGRES_HOST=""; POSTGRES_PORT=""; POSTGRES_HOST_PORT=""
if [ "${DB_CHOICE}" = "2" ]; then
    POSTGRES_MODE=container
    POSTGRES_HOST=postgres
    POSTGRES_DB="${PROJECT_NAME}_db"
    POSTGRES_USER="${PROJECT_NAME}_user"
    _PG_PASS=$(get_env POSTGRES_PASSWORD)
    POSTGRES_PASSWORD=${_PG_PASS:-$(gen_secret 24)}
    POSTGRES_PORT=5432
    POSTGRES_HOST_PORT=5432
fi

# ── Nextcloud ─────────────────────────────────────────────────────────────────
_DEFAULT=$(get_env NEXTCLOUD_FINAL_BASE)
read -p "URL base Nextcloud Docs. Finales (NEXTCLOUD_FINAL_BASE) [${_DEFAULT}]: " NEXTCLOUD_FINAL_BASE
NEXTCLOUD_FINAL_BASE=${NEXTCLOUD_FINAL_BASE:-${_DEFAULT}}
echo ""

# ── Django ────────────────────────────────────────────────────────────────────
_SK=$(get_env SECRET_KEY)
SECRET_KEY=${_SK:-$(gen_secret 50)}
if [ "${ENV_TYPE}" = "dev" ]; then
    DEBUG=True
    DOMAIN=localhost
    ALLOWED_HOSTS="localhost,127.0.0.1"
    CSRF_TRUSTED_ORIGINS="http://localhost:${APP_PORT}"
    ADMIN_URL=admin/
else
    DEBUG=False
    _DEFAULT=$(get_env DOMAIN)
    while true; do
        read -p "Dominio (ej: pti.tekon-rl.cl) [${_DEFAULT}]: " DOMAIN
        DOMAIN=${DOMAIN:-${_DEFAULT}}
        [ -n "${DOMAIN}" ] && break
        echo "  El dominio no puede estar vacío."
    done
    ALLOWED_HOSTS="${DOMAIN}"
    CSRF_TRUSTED_ORIGINS="https://${DOMAIN}"
    _DEFAULT=$(get_env ADMIN_URL)
    read -p "URL del panel admin [${_DEFAULT:-admin/}]: " ADMIN_URL
    ADMIN_URL=${ADMIN_URL:-${_DEFAULT:-admin/}}
    echo ""
fi

# ── Escribir .env ──────────────────────────────────────────────────────────────
python3 - << 'PYEOF'
import os

def kv(key, value):
    if value and any(c in value for c in '$`"\\'):
        value = "'" + value.replace("'", "'\\''") + "'"
    return f"{key}={value}"

g = os.environ.get
is_dev = g("ENV_TYPE", "prod") == "dev"

lines = [
    "# Generado por setup.sh — edita para ajustar la configuración.",
    "",
    "# ── Proyecto ──────────────────────────────────────────────────────────────",
    kv("PROJECT_NAME", g("PROJECT_NAME", "")),
]
if not is_dev:
    lines += [kv("DOMAIN", g("DOMAIN", ""))]
lines += [
    kv("APP_PORT", g("APP_PORT", "8000")),
    "",
    "# ── Django ────────────────────────────────────────────────────────────────",
    kv("SECRET_KEY", g("SECRET_KEY", "")),
    kv("DEBUG", g("DEBUG", "False")),
    kv("ALLOWED_HOSTS", g("ALLOWED_HOSTS", "")),
    kv("CSRF_TRUSTED_ORIGINS", g("CSRF_TRUSTED_ORIGINS", "")),
    kv("ADMIN_URL", g("ADMIN_URL", "admin/")),
    "",
    "# ── Nextcloud (Docs. Finales) ─────────────────────────────────────────────",
    kv("NEXTCLOUD_FINAL_BASE", g("NEXTCLOUD_FINAL_BASE", "")),
    "",
]

if g("POSTGRES_DB", ""):
    lines += [
        "# ── PostgreSQL (omitir = SQLite) ──────────────────────────────────────────",
        kv("POSTGRES_MODE", g("POSTGRES_MODE", "container")),
        kv("POSTGRES_DB", g("POSTGRES_DB", "")),
        kv("POSTGRES_USER", g("POSTGRES_USER", "")),
        kv("POSTGRES_PASSWORD", g("POSTGRES_PASSWORD", "")),
        kv("POSTGRES_HOST", g("POSTGRES_HOST", "postgres")),
        kv("POSTGRES_PORT", g("POSTGRES_PORT", "5432")),
        kv("POSTGRES_HOST_PORT", g("POSTGRES_HOST_PORT", "5432")),
        "",
    ]

with open(".env", "w") as f:
    f.write("\n".join(lines) + "\n")
PYEOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Configuración completada"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Proyecto:   ${PROJECT_NAME}"
echo "  Entorno:    ${ENV_TYPE}"
echo "  Base datos: $([ -n "${POSTGRES_DB}" ] && echo "PostgreSQL (${POSTGRES_MODE})" || echo "SQLite")"
echo ""
if [ "${ENV_TYPE}" = "dev" ]; then
    echo "Próximos pasos:"
    [ -n "${POSTGRES_DB}" ] && echo "  1. make dev-up   (levanta PostgreSQL)"
    echo "  2. make dev      (migrate + tailwind watch + runserver)"
else
    echo "Próximos pasos:"
    echo "  1. make nginx    (configura nginx — solo la primera vez)"
    echo "  2. sudo certbot --nginx -d ${DOMAIN}"
    echo "  3. make deploy   (build + arranque de contenedores)"
fi
echo ""
