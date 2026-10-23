from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405
OTP_HMAC_PEPPER = OTP_HMAC_PEPPER or "dev-only-pepper"  # noqa: F405
SMS_PROVIDER = "console"

# Run Celery tasks inline in development so OTP/image jobs work without a broker or worker.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_EAGER", default=True)  # noqa: F405
