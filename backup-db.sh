#!/bin/sh
# Respaldo de la base de datos, SIN preguntas: el motor se detecta por .env.
#   ./backup-db.sh          # sin POSTGRES_DB → copia de db.sqlite3
#                           # con POSTGRES_DB → pg_dump (.sql) del contenedor `postgres`
#   ./backup-db.sh --json   # dumpdata portable (para migrar SQLite → PostgreSQL)
# Conserva los últimos BACKUP_KEEP (20) respaldos del motor activo.

set -e

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_KEEP="${BACKUP_KEEP:-20}"
SQLITE_DB="${SQLITE_DB:-db.sqlite3}"
PYTHON="${PYTHON:-python3}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Cargar .env (parser simple: no ejecuta el archivo, solo exporta KEY=VAL)
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

mkdir -p "$BACKUP_DIR"

# Borra los respaldos más antiguos que coincidan con el patrón, dejando BACKUP_KEEP.
podar() {
  # shellcheck disable=SC2012
  ls -t $1 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | while IFS= read -r f; do rm -f -- "$f"; done
}

# ── Modo JSON: dumpdata portable ──────────────────────────────────────────────
if [ "$1" = "--json" ]; then
  OUT="${BACKUP_DIR}/dumpdata_${TIMESTAMP}.json"
  # Sin historial del admin (apunta a modelos que pueden no existir), sesiones ni axes.
  EXCL="-e contenttypes -e auth.Permission -e admin.LogEntry -e sessions -e axes"
  echo "Creando dumpdata (JSON) en ${OUT}..."
  if docker compose ps --status running --services 2>/dev/null | grep -qx django; then
    # shellcheck disable=SC2086
    docker compose exec -T django python manage.py dumpdata --natural-foreign --natural-primary $EXCL --indent 2 > "$OUT" \
      || { rm -f "$OUT"; echo "Error: falló dumpdata en el contenedor."; exit 1; }
  else
    # shellcheck disable=SC2086
    "$PYTHON" manage.py dumpdata --natural-foreign --natural-primary $EXCL --indent 2 > "$OUT" \
      || { rm -f "$OUT"; echo "Error: falló dumpdata."; exit 1; }
  fi
  echo "Backup completado."
  ls -lh "$OUT"
  exit 0
fi

# ── PostgreSQL ────────────────────────────────────────────────────────────────
if [ -n "${POSTGRES_DB:-}" ]; then
  : "${POSTGRES_USER:?POSTGRES_USER no está definido en .env}"
  DC="docker compose --profile postgres"
  OUT="${BACKUP_DIR}/dump_${POSTGRES_DB}_${TIMESTAMP}.sql"

  echo "Comprobando servicio postgres..."
  $DC up -d postgres
  ok=0
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if $DC exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  [ "$ok" = 1 ] || { echo "Error: PostgreSQL no responde."; exit 1; }

  echo "Creando backup de ${POSTGRES_DB} en ${OUT}..."
  $DC exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl > "$OUT" \
    || { rm -f "$OUT"; echo "Error: falló pg_dump."; exit 1; }
  echo "Backup completado: $(wc -l < "$OUT") líneas"
  ls -lh "$OUT"
  podar "${BACKUP_DIR}/dump_${POSTGRES_DB}_*.sql"
  exit 0
fi

# ── SQLite ────────────────────────────────────────────────────────────────────
if [ ! -f "$SQLITE_DB" ]; then
  echo "Error: No existe $SQLITE_DB. Ejecuta 'python manage.py migrate' primero."
  exit 1
fi
OUT="${BACKUP_DIR}/dump_sqlite_${TIMESTAMP}.sqlite3"
cp "$SQLITE_DB" "$OUT"
echo "Backup completado (SQLite):"
ls -lh "$OUT"
podar "${BACKUP_DIR}/dump_sqlite_*.sqlite3"
