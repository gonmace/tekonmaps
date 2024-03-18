#!/bin/sh

echo 'Running collectstatic...'
python manage.py collectstatic --no-input --settings=config.settings.prod

echo 'Running migrations...'
python manage.py migrate --settings=config.settings.prod

echo 'Runing Server...'
gunicorn config.wsgi:application DJANGO_SETTINGS_MODULE=config.settings.prod --bind 0.0.0.0:8000