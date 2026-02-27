# Tk Redline

Proyecto Django con Tailwind CSS v4 y DaisyUI v5.

## Desarrollo local

```bash
# 1. Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias Python
pip install -r requirements/dev.txt

# 3. Aplicar migraciones
python manage.py migrate

# 4. Correr servidor Django (terminal 1)
python manage.py runserver

# 5. Compilar CSS con watch (terminal 2)
cd static_src
npm install
npm run dev
```

- App en http://localhost:8000
- SQLite por defecto
- Recarga automática del navegador con django-browser-reload
- Tailwind reconstruye el CSS al cambiar templates

## Producción con Docker

```bash
# Copiar y editar variables de entorno
cp .env.sample .env

docker compose up -d --build
```

- App en http://localhost:8008
- Gunicorn + PostgreSQL
- El CSS se compila durante el build

```bash
# Crear superusuario
docker compose exec django python manage.py createsuperuser --settings=core.settings.prod

# Migraciones
docker compose exec django python manage.py migrate --settings=core.settings.prod
```

## Backup y restore de la base de datos

**Crear backup:**
```bash
./backup-db.sh
```
- Guarda el dump en `backups/dump_<nombre_db>_<timestamp>.sql`
- Inicia el servicio `db` automáticamente si no está corriendo

**Restaurar (usa el dump más reciente):**
```bash
./restore-db.sh
```

**Restaurar un archivo concreto:**
```bash
./restore-db.sh backups/dump_base_20260226_202534.sql
```

**Borrar la BD y restaurar desde cero:**
```bash
./restore-db.sh --drop backups/dump_base_20260226_202534.sql
```

## Desarrollo con MariaDB

```bash
# Instalar dependencias para MySQL/MariaDB
pip install -r requirements/mysql.txt

# Variables de entorno (o en .env)
export DATABASE_ENGINE=mysql
export DATABASE_NAME=tekonmaps
export DATABASE_USER=tekonmaps
export DATABASE_PASSWORD=tu-password
export DATABASE_HOST=localhost  # o 'db' si usas Docker
export DATABASE_PORT=3306

# Migraciones
python manage.py migrate
```

**Error 1071 "Specified key was too long; max key length is 767 bytes":**
- Usa MariaDB 10.2+ o MySQL 5.7.7+ (soporte nativo para índices largos).
- Si usas MariaDB < 10.2, añade a `my.cnf`:
  ```
  innodb_large_prefix=1
  innodb_file_format=barracuda
  innodb_file_per_table=1
  ```

**Con Docker:**
```bash
docker compose -f docker-compose.mariadb.yml up --build
```

## Estructura

- `core/` — Configuración Django (settings, urls, views)
- `templates/` — Plantillas HTML
- `static/` — Archivos estáticos (CSS compilado, imágenes)
- `static_src/` — Fuentes Tailwind (input.css, package.json)
- `docs/` — App de documentación
