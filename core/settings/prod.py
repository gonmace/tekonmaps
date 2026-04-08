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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
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