import os
from .base import *
from core.logging import *


DEBUG = False

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY debe estar definida en producción")

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'pti.tekon-rl.cl').split(',')

INSTALLED_APPS += []  


EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

_db_password = os.environ.get('DATABASE_PASSWORD')
if not _db_password:
    raise ValueError("DATABASE_PASSWORD debe estar definida en producción")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DATABASE_NAME', 'tekonmaps'),
        'USER': os.environ.get('DATABASE_USER', 'tekonmaps'),
        'PASSWORD': _db_password,
        'HOST': os.environ.get('DATABASE_HOST', 'db'),
        'PORT': os.environ.get('DATABASE_PORT', '5432'),
    }
}

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', 'https://pti.tekon-rl.cl').split(',')

# HTTPS en producción (desactivar si el proxy ya redirige)
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'false').lower() == 'true'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True