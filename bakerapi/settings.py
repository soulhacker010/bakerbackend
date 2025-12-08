"""Django settings for bakerapi project."""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

try:  # pragma: no cover - optional dependency
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
except ImportError:  # pragma: no cover - sentry optional
    sentry_sdk = None
    DjangoIntegration = None

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

SIGNUP_ENABLED = os.environ.get("SIGNUP_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
SENTRY_ENVIRONMENT = os.environ.get(
    "SENTRY_ENVIRONMENT",
    "development" if DEBUG else "production",
)
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
SENTRY_PROFILES_SAMPLE_RATE = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))

TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET", "").strip()
TURNSTILE_ENABLED = os.environ.get("TURNSTILE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

raw_allowed_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [host.strip() for host in raw_allowed_hosts.split(",") if host.strip()]
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

_admin_slug = os.environ.get("DJANGO_ADMIN_URL", "admin").strip().strip("/") or "admin"
ADMIN_URL = f"{_admin_slug}/"
ADMIN_ALLOWED_IPS = tuple(
    ip.strip()
    for ip in os.environ.get("ADMIN_ALLOWED_IPS", "").split(",")
    if ip.strip()
)
ADMIN_ACCESS_TOKEN = os.environ.get("ADMIN_ACCESS_TOKEN", "").strip()


if SENTRY_DSN and sentry_sdk is not None and DjangoIntegration is not None:  # pragma: no cover - external service
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
        environment=SENTRY_ENVIRONMENT,
        send_default_pii=False,
        with_locals=False,
    )


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
    'rest_framework_simplejwt.token_blacklist',
    'accounts',
    'clients',
    'assessments',
    'notifications',
    'status',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'bakerapi.middleware.AdminAccessMiddleware',
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

if not DEBUG and "DATABASE_URL" not in os.environ:
    raise RuntimeError("DATABASE_URL must be set when DEBUG is False.")

db_ssl_required = os.environ.get(
    "DATABASE_SSL_REQUIRE",
    "true" if not DEBUG else "false",
).lower() in {"1", "true", "yes", "on"}

database_config = dj_database_url.parse(
    default_database_url,
    conn_max_age=600,
    ssl_require=db_ssl_required,
)

if db_ssl_required and database_config.get("ENGINE", "").endswith("postgresql"):
    options = database_config.setdefault("OPTIONS", {})
    options.setdefault("sslmode", "require")

DATABASES = {
    'default': database_config
}


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'EXCEPTION_HANDLER': 'bakerapi.drf.custom_exception_handler',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': os.environ.get('DRF_THROTTLE_USER', '200/min'),
        'anon': os.environ.get('DRF_THROTTLE_ANON', '50/min'),
        'auth-login': os.environ.get('DRF_THROTTLE_AUTH_LOGIN', '10/min'),
        'auth-2fa': os.environ.get('DRF_THROTTLE_AUTH_2FA', '20/min'),
        'auth-refresh': os.environ.get('DRF_THROTTLE_AUTH_REFRESH', '30/min'),
        'auth-logout': os.environ.get('DRF_THROTTLE_AUTH_LOGOUT', '30/min'),
        'respondent-link': os.environ.get('DRF_THROTTLE_RESPONDENT_LINK', '30/min'),
        'respondent-link-client': os.environ.get('DRF_THROTTLE_RESPONDENT_LINK_CLIENT', '20/hour'),
        'respondent-assessment-detail': os.environ.get('DRF_THROTTLE_RESPONDENT_ASSESSMENT_DETAIL', '30/min'),
        'respondent-assessment-submit': os.environ.get('DRF_THROTTLE_RESPONDENT_ASSESSMENT_SUBMIT', '10/min'),
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.environ.get('JWT_ACCESS_MINUTES', '15'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.environ.get('JWT_REFRESH_DAYS', '7'))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

default_cors_origins: set[str] = set()

raw_frontend_base_urls = os.environ.get('FRONTEND_BASE_URL', '')
frontend_base_urls: list[str] = []
for origin in raw_frontend_base_urls.split(','):
    cleaned = origin.strip().rstrip('/')
    if cleaned:
        frontend_base_urls.append(cleaned)
        default_cors_origins.add(cleaned)

FRONTEND_BASE_URL = frontend_base_urls[0] if frontend_base_urls else ''

if DEBUG:
    default_cors_origins.update(
        {
            'http://127.0.0.1:5173',
            'http://localhost:5173',
        }
    )

extra_cors = os.environ.get('CORS_ALLOWED_ORIGINS', '')
for origin in extra_cors.split(','):
    cleaned = origin.strip().rstrip('/')
    if cleaned:
        default_cors_origins.add(cleaned)
        if not FRONTEND_BASE_URL:
            FRONTEND_BASE_URL = cleaned

if not FRONTEND_BASE_URL:
    FRONTEND_BASE_URL = 'http://localhost:5173' if DEBUG else ''

CORS_ALLOWED_ORIGINS = sorted(default_cors_origins)

CSRF_TRUSTED_ORIGINS = [origin for origin in CORS_ALLOWED_ORIGINS if origin.startswith('https://')]

CORS_ALLOW_CREDENTIALS = True

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 60 * 60 * 24 * 30))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

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
