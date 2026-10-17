from .base import *  # noqa

DEBUG = False
SECRET_KEY = "test-only-secret-key-not-for-production-0123456789abcdef"
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = True
