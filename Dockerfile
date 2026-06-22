# ── Stage 1: compilar CSS con Node (solo build, no va a producción) ─────────────
FROM node:22-slim AS css-builder

# Copiar todo el proyecto para que Tailwind escanee templates al compilar
COPY . /app/

WORKDIR /app/theme/static_src

# npm ci instala exactamente lo que dice package-lock.json
RUN npm ci && npm run build

# ── Stage 2: imagen Python de producción (sin Node ni módulos npm) ─────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=core.settings

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./ ./

# CSS ya compilado y minificado desde la stage anterior
COPY --from=css-builder /app/static/css/dist/ ./static/css/dist/

# Liveness: gunicorn debe estar aceptando conexiones en :8000. Se chequea por socket
# (sin curl en la imagen slim; evita los líos de ALLOWED_HOSTS/SSL-redirect de un GET HTTP).
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import socket,sys; socket.create_connection(('127.0.0.1',8000),timeout=4).close()" || exit 1

CMD ["sh", "entrypoint.sh"]
