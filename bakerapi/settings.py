"""Django settings for bakerapi project."""

import os
from pathlib import Path

import dj_database_url

try:  # pragma: no cover - local development helper
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

if load_dotenv is not None:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-$b=pmh)5o0s+ebx5@d3halcj=xgw@@efkvb3_&7x@c__593ou*")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "false").lower() in {"1", "true", "yes", "on"}

raw_allowed_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [host.strip() for host in raw_allowed_hosts.split(",") if host.strip()]
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'accounts',
    'clients',
    'assessments',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'bakerapi.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'bakerapi.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

default_database_url = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")

DATABASES = {
    'default': dj_database_url.parse(default_database_url, conn_max_age=600, ssl_require=os.environ.get('RENDER', '').lower() == 'true')
}


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

default_cors_origins = {
    'http://127.0.0.1:5173',
    'http://localhost:5173',
}

FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')
if FRONTEND_BASE_URL:
    default_cors_origins.add(FRONTEND_BASE_URL)

extra_cors = os.environ.get('CORS_ALLOWED_ORIGINS', '')
for origin in extra_cors.split(','):
    cleaned = origin.strip().rstrip('/')
    if cleaned:
        default_cors_origins.add(cleaned)

CORS_ALLOWED_ORIGINS = sorted(default_cors_origins)

CSRF_TRUSTED_ORIGINS = [origin for origin in CORS_ALLOWED_ORIGINS if origin.startswith('https://')]

CORS_ALLOW_CREDENTIALS = True

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

if not DEBUG:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'


# Email delivery configuration
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', '').strip()
RESEND_REPLY_TO = os.environ.get('RESEND_REPLY_TO', '').strip()
FEEDBACK_TO_EMAIL = os.environ.get('FEEDBACK_TO_EMAIL', '').strip()


# Two-factor authentication defaults
TWO_FACTOR_CODE_LENGTH = int(os.environ.get('TWO_FACTOR_CODE_LENGTH', 6))
TWO_FACTOR_CODE_TTL_MINUTES = int(os.environ.get('TWO_FACTOR_CODE_TTL_MINUTES', 10))
TWO_FACTOR_MAX_ATTEMPTS = int(os.environ.get('TWO_FACTOR_MAX_ATTEMPTS', 5))
TWO_FACTOR_RESEND_INTERVAL_SECONDS = int(os.environ.get('TWO_FACTOR_RESEND_INTERVAL_SECONDS', 60))


# Password reset defaults
PASSWORD_RESET_TOKEN_TTL_MINUTES = int(os.environ.get('PASSWORD_RESET_TOKEN_TTL_MINUTES', 24 * 60))
PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS = int(os.environ.get('PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS', 5 * 60))
