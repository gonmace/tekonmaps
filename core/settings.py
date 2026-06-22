import os

from decouple import config, Csv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

_SECRET_KEY_DEFAULT = 'django-insecure-default-only-for-dev-run-make-setup'
SECRET_KEY = config('SECRET_KEY', default=_SECRET_KEY_DEFAULT)

DEBUG = config('DEBUG', default=False, cast=bool)

# Validar solo cuando existe .env (entorno configurado) pero SECRET_KEY no fue definido.
# Sin .env = instalación inicial, el default es aceptable.
if SECRET_KEY == _SECRET_KEY_DEFAULT and os.path.exists(os.path.join(BASE_DIR, '.env')):
    raise ValueError("SECRET_KEY no está en .env. Ejecuta 'make setup' para generarlo.")

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=Csv())

ADMIN_URL = config('ADMIN_URL', default='admin/')

# Application definition

INSTALLED_APPS = [
    'accounts',
    'docs',
    'panel',
    'axes',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'csp.middleware.CSPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'axes.middleware.AxesMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Activa la zona horaria del navegador (cookie 'tz') para todas las fechas/horas.
    'core.middleware.TimezoneMiddleware',
]

INSTALLED_APPS += ['tailwind', 'theme']
TAILWIND_APP_NAME = 'theme'

if DEBUG:
    INSTALLED_APPS += ['django_browser_reload']
    MIDDLEWARE += ['django_browser_reload.middleware.BrowserReloadMiddleware']
    INTERNAL_IPS = ['127.0.0.1', '::1']
    import sys
    if sys.platform == 'win32':
        NPM_BIN_PATH = r'C:\Program Files\nodejs\npm.cmd'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

SITE_ID = 1

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'docs:index'
LOGOUT_REDIRECT_URL = 'home'

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database: SQLite por defecto; PostgreSQL si se define POSTGRES_DB en .env
if config('POSTGRES_DB', default=''):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('POSTGRES_DB'),
            'USER': config('POSTGRES_USER'),
            'PASSWORD': config('POSTGRES_PASSWORD'),
            'HOST': config('POSTGRES_HOST', default='postgres'),
            'PORT': config('POSTGRES_PORT', default='5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-bo'
# Fallback cuando el navegador no informa zona (la cookie 'tz' la sobreescribe por request,
# vía core.middleware.TimezoneMiddleware). Chile es la audiencia principal.
TIME_ZONE = config('TIME_ZONE', default='America/Santiago')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
WHITENOISE_MANIFEST_STRICT = not DEBUG  # True en prod: rechaza archivos sin entrada en manifest

STORAGES = {
    'staticfiles': {
        # CompressedManifestStaticFilesStorage: hashes en filenames (cache-busting seguro)
        # + archivos .gz pre-generados que nginx sirve con gzip_static on
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email: consola en dev, SMTP en prod si se configura EMAIL_HOST
if config('EMAIL_HOST', default=''):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST')
    EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
    EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
    EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ── Seguridad ──────────────────────────────────────────────────────────────────
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

X_FRAME_OPTIONS = 'DENY'

# ── Caché (filesystem, compartida entre workers, TTL 1 hora) ───────────────────
# Las sesiones siguen en la base de datos (backend por defecto de Django).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': os.path.join(BASE_DIR, '.cache', 'django'),
        'TIMEOUT': 3600,  # 1 hora
    }
}

# En tests, caché en memoria aislada: así `cache.clear()` de los tests NO borra el fast-path
# de seguimiento guardado en `.cache/django` (la caché real que comparten dev y prod).
import sys as _sys
if 'test' in _sys.argv:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# ── django-axes (protección brute force) ──────────────────────────────────────
# Handler de base de datos: no requiere Redis (la app usa caché de filesystem).
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hora
AXES_LOCKOUT_PARAMETERS = ['ip_address', 'username']
AXES_HANDLER = 'axes.handlers.database.AxesDatabaseHandler'

# ── Content Security Policy ───────────────────────────────────────────────────
# Permisiva: el sitio carga FontAwesome y Nunito por CDN y usa scripts/estilos
# inline (toggle de tema, toasts, DaisyUI). Endurecer con nonces si se requiere.
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net")
CSP_FONT_SRC = ("'self'", "data:", "https://fonts.gstatic.com", "https://cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:")
CSP_CONNECT_SRC = ("'self'",) if not DEBUG else ("'self'", "ws://localhost:*", "ws://127.0.0.1:*")

# ── Integración Nextcloud ─────────────────────────────────────────────────────
# URL base de Nextcloud para Docs. Finales (carpeta 20-PTI SP compartida).
NEXTCLOUD_FINAL_BASE = config('NEXTCLOUD_FINAL_BASE', default='')

# Acceso directo a Nextcloud vía WebDAV (usuario de servicio).
# BASE_URL apunta a la raíz de archivos del usuario:
#   https://cloud2.tekon-rl.cl/remote.php/dav/files/<usuario>/
# Usar un app-password (Ajustes → Seguridad), nunca la contraseña principal.
NEXTCLOUD_BASE_URL = config('NEXTCLOUD_BASE_URL', default='')
NEXTCLOUD_USER = config('NEXTCLOUD_USER', default='')
NEXTCLOUD_APP_PASSWORD = config('NEXTCLOUD_APP_PASSWORD', default='')
# Carpeta (relativa a la raíz del usuario) donde viven los templates descargables
# de los documentos esperados, ej. '/00-TEMPLATES'. Vacío = descarga deshabilitada.
NEXTCLOUD_TEMPLATES_PATH = config('NEXTCLOUD_TEMPLATES_PATH', default='')

# ── Admins y logging ──────────────────────────────────────────────────────────
ADMINS = [('Admin', 'admin@example.com')]
MANAGERS = ADMINS

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {'()': 'django.utils.log.RequireDebugFalse'}
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
