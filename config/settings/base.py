"""Base settings. All environment-specific values come from env vars (see .env.example)."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")  # no-op if the file does not exist

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
SITE_URL = env("SITE_URL", default="http://localhost:8000")
ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", default="admin").strip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.locations",
    "apps.accounts",
    "apps.catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
                "apps.catalog.context_processors.nav_categories",
            ],
            "builtins": ["apps.core.templatetags.core_tags"],
        },
    }
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# i18n / time: DB stores UTC; Asia/Tehran only for interpreting/displaying input.
LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = env("MEDIA_URL", default="/media/")
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}

# Cache / sessions. Redis in real envs; cached_db keeps guest carts if Redis is flushed.
CACHES = {"default": env.cache("REDIS_CACHE_URL", default="locmemcache://")}
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_SAMESITE = "Lax"  # Lax (not Strict): users return from the payment gateway

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="memory://")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=None)
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_DEFAULT_QUEUE = "default"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.middleware.RequestIDLogFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["request_id"]}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

# Business defaults (overridable via SiteSetting later)
ORDER_PAYMENT_TIMEOUT_MINUTES = env.int("ORDER_PAYMENT_TIMEOUT_MINUTES", default=30)
STOCK_RESERVATION_TTL_MINUTES = env.int("STOCK_RESERVATION_TTL_MINUTES", default=30)

# Reverse proxies in front of Django (nginx = 1). Needed to see the real client IP for rate limits.
NUM_PROXIES = env.int("NUM_PROXIES", default=0)

# SMS / OTP (architecture §9). Pepper is separate from SECRET_KEY and required in production.
SMS_PROVIDERS = {
    "console": "integrations.sms.console.ConsoleSMSProvider",
    "fake": "integrations.sms.fake.FakeSMSProvider",
}
SMS_PROVIDER = env("SMS_PROVIDER", default="console")
SMS_FALLBACK_PROVIDER = env("SMS_FALLBACK_PROVIDER", default="")
OTP_HMAC_PEPPER = env("OTP_HMAC_PEPPER", default="")
OTP_TTL_SECONDS = env.int("OTP_TTL_SECONDS", default=120)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RESEND_COOLDOWN = env.int("OTP_RESEND_COOLDOWN", default=120)
OTP_SEND_LIMIT_PHONE_HOURLY = env.int("OTP_SEND_LIMIT_PHONE_HOURLY", default=5)
OTP_SEND_LIMIT_PHONE_DAILY = env.int("OTP_SEND_LIMIT_PHONE_DAILY", default=10)
OTP_SEND_LIMIT_IP_HOURLY = env.int("OTP_SEND_LIMIT_IP_HOURLY", default=20)
OTP_GLOBAL_PER_MINUTE = env.int("OTP_GLOBAL_PER_MINUTE", default=60)
OTP_VERIFY_LIMIT_PHONE = env.int("OTP_VERIFY_LIMIT_PHONE", default=10)
OTP_VERIFY_LIMIT_IP = env.int("OTP_VERIFY_LIMIT_IP", default=30)

CELERY_TASK_ROUTES = {"apps.accounts.tasks.send_otp_sms": {"queue": "otp"}}
CELERY_BEAT_SCHEDULE = {
    "cleanup-otp-challenges": {"task": "apps.accounts.tasks.cleanup_otp_challenges", "schedule": 86400.0},
}

SEARCH_BACKEND = "apps.catalog.search.backend.SimpleSearchBackend"
CELERY_TASK_ROUTES["apps.catalog.images.process_product_image"] = {"queue": "images"}
