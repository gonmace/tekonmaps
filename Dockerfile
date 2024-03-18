# syntax=docker/dockerfile:1
FROM python:3.10.4-alpine3.15

ENV PYTHONDONTWRITEBYTECODE=1

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements/base.txt ./
COPY requirements/prod.txt ./

RUN pip install -r prod.txt

COPY ./ ./

CMD ["sh", "entrypoint.sh"]