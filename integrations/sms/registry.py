from __future__ import annotations

from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string

from .base import SMSProvider


@cache
def get_provider(code: str) -> SMSProvider:
    try:
        return import_string(settings.SMS_PROVIDERS[code])()
    except KeyError as exc:
        raise LookupError(f"Unknown SMS provider: {code!r}") from exc


def provider_chain() -> list[str]:
    """Primary provider, then the fallback if configured."""
    chain = [settings.SMS_PROVIDER]
    if settings.SMS_FALLBACK_PROVIDER and settings.SMS_FALLBACK_PROVIDER != settings.SMS_PROVIDER:
        chain.append(settings.SMS_FALLBACK_PROVIDER)
    return chain
