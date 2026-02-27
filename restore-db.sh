#!/bin/sh
# Restore de la base de datos PostgreSQL (pti-tekon-rl-cl)
# Uso: ./restore-db.sh [archivo.sql]
#       ./restore-db.sh                    # usa el dump más reciente en backups/
#       ./restore-db.sh backups/dump_base_20260226_202534.sql
#       ./restore-db.sh --drop backups/dump.sql   # borra la BD antes de restaurar

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
COMPOSE_CMD="docker compose -f $COMPOSE_FILE"
DROP_DB=0

# Cargar .env si existe
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
  COMPOSE_CMD="$COMPOSE_CMD --env-file .env"
fi
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-restore-script}"

DB_NAME="${DATABASE_NAME:-base}"
DB_USER="${DATABASE_USER:-magoreal}"

# Parsear argumentos
DUMP_FILE=""
for arg in "$@"; do
  case "$arg" in
    --drop) DROP_DB=1 ;;
    *)      DUMP_FILE="$arg" ;;
  esac
done

# Si no se pasó archivo, usar el más reciente
if [ -z "$DUMP_FILE" ]; then
  DUMP_FILE=$(ls -t "$BACKUP_DIR"/dump_*.sql 2>/dev/null | head -1)
  if [ -z "$DUMP_FILE" ]; then
    echo "Error: No hay dumps en $BACKUP_DIR. Ejecuta ./backup-db.sh primero."
    exit 1
  fi
  echo "Usando dump más reciente: $DUMP_FILE"
fi

if [ ! -f "$DUMP_FILE" ]; then
  echo "Error: No existe el archivo: $DUMP_FILE"
  exit 1
fi

# Asegurar que db esté corriendo
echo "Comprobando servicio db..."
$COMPOSE_CMD up -d db
echo "Esperando a que PostgreSQL esté listo..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if $COMPOSE_CMD exec -T db pg_isready -U "$DB_USER" -d postgres 2>/dev/null; then
    break
  fi
  sleep 2
done

if [ "$DROP_DB" = 1 ]; then
  echo "Terminando conexiones y eliminando base de datos ${DB_NAME}..."
  $COMPOSE_CMD exec -T db psql -U "$DB_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" 2>/dev/null || true
  $COMPOSE_CMD exec -T db psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
  echo "Creando base de datos ${DB_NAME}..."
  $COMPOSE_CMD exec -T db psql -U "$DB_USER" -d postgres -c "CREATE DATABASE ${DB_NAME};"
fi

echo "Restaurando desde $DUMP_FILE..."
$COMPOSE_CMD exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "'"$DB_NAME"'"' < "$DUMP_FILE"

echo "Restore completado."
