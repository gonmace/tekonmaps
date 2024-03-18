# Dj-skeleton

```shell
python3 -m venv .venv
source .venv/bin/activate
```

```
pip install django
django-admin startproject config .

```

```
docker exec -it postgres psql -U magoreal -d base
python manage.py runserver --settings=config.settings.prod

python manage.py collectstatic --no-input --settings=config.settings.prod
python manage.py migrate --settings=config.settings.prod
gunicorn config.wsgi:application --bind 127.0.0.1:8000
```






