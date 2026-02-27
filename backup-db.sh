#!/bin/sh
# Backup de la base de datos PostgreSQL (pti-tekon-rl-cl)
# Uso: ./backup-db.sh
# Inicia el servicio db automáticamente si no está corriendo

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
COMPOSE_CMD="docker compose -f $COMPOSE_FILE"

# Cargar .env si existe (evita errores con caracteres especiales en valores)
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
  COMPOSE_CMD="$COMPOSE_CMD --env-file .env"
fi
# Evitar warning de DJANGO_SECRET_KEY al parsear compose (solo usamos db)
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-backup-script}"

DB_NAME="${DATABASE_NAME:-base}"
DB_USER="${DATABASE_USER:-magoreal}"
DUMP_FILE="${BACKUP_DIR}/dump_${DB_NAME}_${TIMESTAMP}.sql"

mkdir -p "$BACKUP_DIR"

# Asegurar que db esté corriendo (idempotente: no hace nada si ya está up)
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
