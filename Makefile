# ── Configuración inicial ──────────────────────────────────────────────────────
setup:
	bash setup.sh

# ── Docker de desarrollo (PostgreSQL opcional) ─────────────────────────────────
# Solo levanta PostgreSQL si POSTGRES_DB está definido en .env.
# Por defecto (SQLite) no hay nada que levantar.
dev-up:
	@[ -f .env ] || { echo "Error: .env no encontrado. Ejecuta 'make setup' primero."; exit 1; }
	@set -a && . ./.env && set +a; \
	if [ -n "$${POSTGRES_DB}" ]; then \
		docker compose -f docker-compose.dev.yml --profile postgres up -d; \
	else \
		echo "Nada que levantar (SQLite). Inicia Django con 'make dev'."; \
	fi

dev-down:
	docker compose -f docker-compose.dev.yml down

dev-logs:
	docker compose -f docker-compose.dev.yml logs -f

dev-check:
	@echo "Verificando entorno de desarrollo..."
	@[ -f .env ] && echo "  ✓ .env existe" || echo "  ✗ .env no encontrado — ejecuta: make setup"
	@command -v python >/dev/null 2>&1 && echo "  ✓ Python disponible" || echo "  ✗ Python no encontrado"
	@command -v docker >/dev/null 2>&1 && echo "  ✓ Docker disponible" || echo "  ✗ Docker no encontrado"

# ── Django local ──────────────────────────────────────────────────────────────
install:
	pip install -r requirements-dev.txt
	python manage.py tailwind install
	@echo ""
	@[ -f .env ] || echo "  Siguiente paso: ejecuta 'make setup' para generar el .env"

# Tailwind en background + runserver con django-browser-reload.
# Python/templates: recarga automática. CSS: refrescar tras Tailwind recompilar.
dev:
	python manage.py migrate
	python manage.py tailwind start &
	python manage.py runserver

tailwind:
	python manage.py tailwind start

# ── Comandos Django (dev: directo | prod: dentro del container) ───────────────
MANAGE := $(shell [ -f .env ] && . ./.env && [ "$${DEBUG}" = "False" ] && echo "docker compose exec django python manage.py" || echo "python manage.py")

migrate:
	$(MANAGE) migrate

migrations:
	$(MANAGE) makemigrations

shell:
	$(MANAGE) shell

superuser:
	$(MANAGE) createsuperuser

collect:
	$(MANAGE) collectstatic --noinput

# ── Base de datos (dev) ────────────────────────────────────────────────────────
db-shell:
	@[ -f .env ] && . ./.env; \
	if [ -n "$${POSTGRES_DB}" ]; then \
		docker compose -f docker-compose.dev.yml exec postgres psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}; \
	else \
		echo "Modo SQLite — usa: sqlite3 db.sqlite3"; \
	fi

db-reset:
	@[ -f db.sqlite3 ] && rm db.sqlite3 && echo "SQLite eliminado." || true
	python manage.py migrate

# ── Producción ────────────────────────────────────────────────────────────────
deploy:
	bash deploy.sh

nginx:
	bash nginx-deploy.sh

check-ports:
	bash check-ports.sh

logs:
	docker compose logs -f django

down:
	docker compose down

.PHONY: setup dev-up dev-down dev-logs dev-check install dev tailwind \
        migrate migrations shell superuser collect db-shell db-reset \
        deploy nginx check-ports logs down
