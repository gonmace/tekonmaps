#!/bin/sh
# Restore de la base de datos (SQLite o PostgreSQL); el destino lo fija .env.
# Uso: ./restore-db.sh [--drop] [archivo]
#   ./restore-db.sh                                  # usa el backup más reciente
#   ./restore-db.sh backups/dump_sqlite_X.sqlite3    # SQLite: copia el archivo a db.sqlite3
#   ./restore-db.sh --drop backups/dump_BD_X.sql     # PostgreSQL: recrea la BD y carga el .sql
#   ./restore-db.sh --drop backups/dumpdata_X.json   # PostgreSQL: migrate + flush + loaddata
# `--drop` es obligatorio para .json (reemplaza TODOS los datos de PostgreSQL).

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
SQLITE_DB="${SQLITE_DB:-db.sqlite3}"
PYTHON="${PYTHON:-python3}"
DROP_DB=0
DUMP_FILE=""
for arg in "$@"; do
  case "$arg" in
    --drop) DROP_DB=1 ;;
    *)      DUMP_FILE="$arg" ;;
  esac
done

# Cargar .env (parser simple: solo exporta KEY=VAL)
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

if [ -z "$DUMP_FILE" ]; then
  # shellcheck disable=SC2012
  DUMP_FILE=$(ls -t "$BACKUP_DIR"/dump_*.* "$BACKUP_DIR"/dumpdata_*.* 2>/dev/null | head -1)
  if [ -z "$DUMP_FILE" ]; then
    echo "Error: No hay backups en $BACKUP_DIR. Ejecuta ./backup-db.sh primero."
    exit 1
  fi
  echo "Usando backup más reciente: $DUMP_FILE"
fi
[ -f "$DUMP_FILE" ] || { echo "Error: No existe el archivo: $DUMP_FILE"; exit 1; }

DC="docker compose --profile postgres"

# Arranca el contenedor postgres y espera a que acepte conexiones.
esperar_postgres() {
  : "${POSTGRES_DB:?POSTGRES_DB no está definido en .env (¿restaurar a PostgreSQL?)}"
  : "${POSTGRES_USER:?POSTGRES_USER no está definido en .env}"
  echo "Comprobando servicio postgres..."
  $DC up -d postgres
  ok=0
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if $DC exec -T postgres pg_isready -U "$POSTGRES_USER" -d postgres >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  [ "$ok" = 1 ] || { echo "Error: PostgreSQL no responde."; exit 1; }
}

case "$DUMP_FILE" in
  *.sqlite3|*.db)
    echo "Restaurando SQLite desde $DUMP_FILE..."
    cp "$DUMP_FILE" "$SQLITE_DB"
    echo "Restore completado en $SQLITE_DB"
    ;;

  *.sql)
    esperar_postgres
    if [ "$DROP_DB" = 1 ]; then
      echo "Terminando conexiones y recreando ${POSTGRES_DB}..."
      $DC exec -T postgres psql -U "$POSTGRES_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
      $DC exec -T postgres psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\";"
      $DC exec -T postgres psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \"${POSTGRES_DB}\" OWNER \"${POSTGRES_USER}\";"
    fi
    echo "Restaurando desde $DUMP_FILE..."
    $DC exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$DUMP_FILE"
    echo "Restore completado."
    ;;

  *.json)
    if [ "$DROP_DB" != 1 ]; then
      echo "Error: un .json reemplaza TODOS los datos de PostgreSQL. Repite con --drop para confirmarlo."
      exit 1
    fi
    esperar_postgres

    # Contenedor de un solo uso: toma POSTGRES_* del .env y alcanza `postgres` por la red.
    RUN="$DC run --rm -T django"
    echo "Aplicando migraciones..."
    $RUN python manage.py migrate --no-input
    echo "Vaciando datos sembrados por las migraciones..."
    $RUN python manage.py flush --no-input

    # Filtrar modelos obsoletos (ej. DocCarpeta eliminado) antes de cargar
    FILTERED="${BACKUP_DIR}/filtered_load_$$.json"
    trap 'rm -f "$FILTERED"' EXIT
    "$PYTHON" scripts/filter_fixture.py < "$DUMP_FILE" > "$FILTERED" 2>/dev/null || cp "$DUMP_FILE" "$FILTERED"

    echo "Cargando datos desde $DUMP_FILE..."
    $RUN python manage.py loaddata --format=json - < "$FILTERED"
    echo "Restore completado."
    ;;

  *)
    echo "Error: Formato no reconocido. Usa .sqlite3 (SQLite), .sql (PostgreSQL) o .json (dumpdata→PostgreSQL)."
    exit 1
    ;;
esac
