#!/bin/sh
# Backup de la base de datos (SQLite local o PostgreSQL en Docker)
# Uso: ./backup-db.sh

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SQLITE_DB="${SQLITE_DB:-db.sqlite3}"

mkdir -p "$BACKUP_DIR"

echo "¿Qué base de datos hacer backup?"
echo "  1) SQLite (local) → JSON portable para restaurar en PostgreSQL"
echo "  2) PostgreSQL (Docker) → dump SQL"
printf "Elige [1/2]: "
read -r choice

case "$choice" in
  1)
    if [ ! -f "$SQLITE_DB" ]; then
      echo "Error: No existe $SQLITE_DB. Ejecuta 'python manage.py migrate' primero."
      exit 1
    fi
    DUMP_FILE="${BACKUP_DIR}/dumpdata_${TIMESTAMP}.json"
    echo "Creando dumpdata (JSON) desde SQLite en ${DUMP_FILE}..."
    python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission --indent 2 > "$DUMP_FILE"
    echo "Backup completado. Usa este archivo con ./restore-db.sh para cargar en PostgreSQL."
    ls -lh "$DUMP_FILE"
    ;;
  2)
    # Cargar .env si existe
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
    export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-backup-script}"

    COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
    COMPOSE_CMD="docker compose -f $COMPOSE_FILE"
    [ -f .env ] && COMPOSE_CMD="$COMPOSE_CMD --env-file .env"

    DB_NAME="${DATABASE_NAME:-base}"
    DB_USER="${DATABASE_USER:-magoreal}"
    DUMP_FILE="${BACKUP_DIR}/dump_${DB_NAME}_${TIMESTAMP}.sql"

    echo "Comprobando servicio db..."
    $COMPOSE_CMD up -d db
    echo "Esperando a que PostgreSQL esté listo..."
    for i in 1 2 3 4 5 6 7 8 9 10; do
      if $COMPOSE_CMD exec -T db pg_isready -U "$DB_USER" -d "$DB_NAME" 2>/dev/null; then
        break
      fi
      sleep 2
    done

    echo "Creando backup de ${DB_NAME} en ${DUMP_FILE}..."
    $COMPOSE_CMD exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl > "$DUMP_FILE"
    echo "Backup completado: $(wc -l < "$DUMP_FILE") líneas"
    ls -lh "$DUMP_FILE"
    ;;
  *)
    echo "Opción no válida."
    exit 1
    ;;
esac
