from .base import *
import os
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "Esto_es_desarrollo"

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = []

INSTALLED_APPS += [
    # "django_extensions",
    # 'django_browser_reload',
    # "debug_toolbar",
    ]  

MIDDLEWARE += [
    # "debug_toolbar.middleware.DebugToolbarMiddleware",
    # "django_browser_reload.middleware.BrowserReloadMiddleware",
    ]  

INTERNAL_IPS = [
    # "127.0.0.1",
]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'base',
#         'USER': 'magoreal',
#         'PASSWORD': 'ojalaque',
#         'HOST': '127.0.0.1',  # Asegúrate de que esto coincida con el nombre del servicio en docker-compose.yml
#         'PORT': '5432',
#     }
# }

# DATABASES = {
#     'default': env.db('DATABASE_URL', default='psql://Gonzalo:ojalaque@127.0.0.1:5432/tekon'),
# }