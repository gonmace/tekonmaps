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
python manage.py collectstatic --no-input --settings=config.settings.prod
python manage.py migrate --settings=config.settings.prod
gunicorn config.wsgi:application --bind 127.0.0.1:8000



```


sudo apt-get install -y jq


sudo docker-compose up --build
sudo docker-compose exec django python manage.py createsuperuser --settings=config.settings.prod


# Exportar base de datos de db.sqlite3
python manage.py dumpdata > datos.json

python manage.py dumpdata --exclude auth.permission --exclude contenttypes --exclude admin.LogEntry > datos.json

sudo docker-compose exec django python manage.py createsuperuser --settings=config.settings.prod

# Importar los datos
sudo docker-compose exec django python manage.py migrate --settings=config.settings.prod
sudo docker cp datos.json 4d3d20e2a2f4:/app/datos.json
<!-- sudo docker-compose exec django python manage.py remove_stale_contenttypes --settings=config.settings.prod -->
sudo docker-compose exec django python manage.py loaddata /app/datos.json --settings=config.settings.prod





