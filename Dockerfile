# Dockerfile para PRODUCCIÓN
# Uso: docker compose up -d

FROM node:22-alpine AS frontend

WORKDIR /app

# Copiar todo lo necesario para el build (templates para @source)
COPY static_src/ ./static_src/
COPY templates/ ./templates/

WORKDIR /app/static_src

# Build de Tailwind + DaisyUI
RUN npm install
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements/prod.txt ./
RUN pip install --no-cache-dir -r prod.txt

# Copiar proyecto
COPY . .

# Copiar CSS compilado desde stage frontend
COPY --from=frontend /app/static_src/../static/css/main.css /app/static/css/main.css

EXPOSE 8000

CMD ["sh", "entrypoint.sh"]
