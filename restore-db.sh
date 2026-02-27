#!/bin/sh
# Restore de la base de datos (SQLite o PostgreSQL)
# Uso: ./restore-db.sh [archivo]
#       ./restore-db.sh                    # usa el backup más reciente
#       ./restore-db.sh backups/dump_sqlite_20260226.sqlite3
#       ./restore-db.sh --drop backups/dump_base_20260226.sql   # PostgreSQL: borra BD antes

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
SQLITE_DB="${SQLITE_DB:-db.sqlite3}"
DROP_DB=0

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
  DUMP_FILE=$(ls -t "$BACKUP_DIR"/dump_*.* "$BACKUP_DIR"/dumpdata_*.* 2>/dev/null | head -1)
  if [ -z "$DUMP_FILE" ]; then
    echo "Error: No hay backups en $BACKUP_DIR. Ejecuta ./backup-db.sh primero."
    exit 1
  fi
  echo "Usando backup más reciente: $DUMP_FILE"
fi

if [ ! -f "$DUMP_FILE" ]; then
  echo "Error: No existe el archivo: $DUMP_FILE"
  exit 1
fi

# Detectar tipo por extensión
case "$DUMP_FILE" in
  *.json)
    echo "Restaurando desde dumpdata (JSON) a PostgreSQL..."
    if [ -f .env ]; then
      while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
          '#'*|'') continue ;;
          *=*)
            key="${line%%=*}"; key="${key% }"; key="${key# }"
            val="${line#*=}"; val="${val#\"}"; val="${val%\"}"
            export "$key=$val"
            ;;
        esac
      done < .env
    fi
    export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-restore-script}"

    COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
    COMPOSE_CMD="docker compose -f $COMPOSE_FILE"
    [ -f .env ] && COMPOSE_CMD="$COMPOSE_CMD --env-file .env"

    echo "Comprobando servicios..."
    $COMPOSE_CMD up -d db django
    echo "Esperando a que PostgreSQL esté listo..."
    DB_USER="${DATABASE_USER:-magoreal}"
    for i in 1 2 3 4 5 6 7 8 9 10; do
      if $COMPOSE_CMD exec -T db pg_isready -U "$DB_USER" -d postgres 2>/dev/null; then
        break
      fi
      sleep 2
    done

    [ "$DROP_DB" = 1 ] && echo "Limpiando datos existentes..." && $COMPOSE_CMD exec -T django python manage.py flush --no-input --settings=core.settings.prod
    echo "Aplicando migraciones..."
    $COMPOSE_CMD exec -T django python manage.py migrate --settings=core.settings.prod

    # Filtrar modelos obsoletos (ej. DocCarpeta eliminado) antes de cargar
    FILTERED="${BACKUP_DIR}/filtered_load_$$.json"
    python3 scripts/filter_fixture.py < "$DUMP_FILE" > "$FILTERED" 2>/dev/null || cp "$DUMP_FILE" "$FILTERED"
    trap "rm -f $FILTERED" EXIT

    echo "Cargando datos desde $DUMP_FILE..."
    LOAD_PATH="/app/${FILTERED#./}"
    $COMPOSE_CMD exec -T django python manage.py loaddata "$LOAD_PATH" --settings=core.settings.prod
    echo "Restore completado."
    ;;
  *.sqlite3|*.db)
    echo "Restaurando SQLite desde $DUMP_FILE..."
    cp "$DUMP_FILE" "$SQLITE_DB"
    echo "Restore completado en $SQLITE_DB"
    ;;
  *.sql)
    # PostgreSQL
    if [ -f .env ]; then
      while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
          '#'*|'') continue ;;
          *=*)
            key="${line%%=*}"; key="${key% }"; key="${key# }"
            val="${line#*=}"; val="${val#\"}"; val="${val%\"}"
            export "$key=$val"
            ;;
        esac
      done < .env
    fi
    export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-restore-script}"

    COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
    COMPOSE_CMD="docker compose -f $COMPOSE_FILE"
    [ -f .env ] && COMPOSE_CMD="$COMPOSE_CMD --env-file .env"

    DB_NAME="${DATABASE_NAME:-base}"
    DB_USER="${DATABASE_USER:-magoreal}"

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
    ;;
  *)
    echo "Error: Formato no reconocido. Usa .json (dumpdata→PostgreSQL), .sql (PostgreSQL) o .sqlite3 (SQLite)."
    exit 1
    ;;
esac
