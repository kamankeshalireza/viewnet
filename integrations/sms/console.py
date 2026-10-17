import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import SMSProvider, SMSResult

log = logging.getLogger("otp.console")


class ConsoleSMSProvider(SMSProvider):
    """Development only: prints the code to the log. Refuses to run when DEBUG is off."""

    code = "console"

    def send_otp(self, phone, code, *, ttl_seconds):
        if not settings.DEBUG:
            raise ImproperlyConfigured("ConsoleSMSProvider must not be used in production")
        log.warning("DEV OTP for %s: %s (valid %ss)", phone, code, ttl_seconds)
        return SMSResult(ok=True, provider_message_id="console")
