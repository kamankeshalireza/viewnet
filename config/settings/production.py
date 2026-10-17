from .base import *  # noqa

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)  # raise gradually: 1 day -> 6 months  # noqa: F405
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

if len(OTP_HMAC_PEPPER) < 32:  # noqa: F405
    raise ImproperlyConfigured("OTP_HMAC_PEPPER must be set (>= 32 chars) in production")
if SMS_PROVIDER == "console":  # noqa: F405
    raise ImproperlyConfigured("SMS_PROVIDER=console is not allowed in production")
NUM_PROXIES = env.int("NUM_PROXIES", default=1)  # noqa: F405  (nginx in front)
