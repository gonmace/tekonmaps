#!/bin/sh

echo 'Running collectstatic...'
python manage.py collectstatic --noinput --settings=core.settings.prod

echo 'Running migrations...'
python manage.py migrate --settings=core.settings.prod

echo 'Runing Server...'
export DJANGO_SETTINGS_MODULE=core.settings.prod
gunicorn core.wsgi:application --bind 0.0.0.0:8000