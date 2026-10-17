"""OTP issue/verify. See architecture §9. The same outward behaviour for known and unknown phones."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core import ratelimit
from apps.core.text import mask_phone

from ..models import OTPChallenge
from ..tasks import send_otp_sms

log = logging.getLogger("otp")


@dataclass(frozen=True)
class OTPRequestResult:
    reason: str  # "sent" | "cooldown" | "throttled" | "unavailable"
    retry_after: int = 0

    @property
    def sent(self) -> bool:
        return self.reason == "sent"


@dataclass(frozen=True)
class OTPVerifyResult:
    reason: str  # "ok" | "invalid" | "expired" | "locked" | "throttled" | "unavailable"

    @property
    def ok(self) -> bool:
        return self.reason == "ok"


def _hash(phone: str, purpose: str, code: str, salt: str) -> str:
    msg = f"{phone}|{purpose}|{code}|{salt}".encode()
    return hmac.new(settings.OTP_HMAC_PEPPER.encode(), msg, hashlib.sha256).hexdigest()


def _active(phone: str, purpose: str):
    return OTPChallenge.objects.filter(phone=phone, purpose=purpose, consumed_at__isnull=True,
                                       invalidated_at__isnull=True)


def request_otp(phone: str, ip: str, purpose: str = "login") -> OTPRequestResult:
    now = timezone.now()
    last = OTPChallenge.objects.filter(phone=phone, purpose=purpose).order_by("-created_at").first()
    if last and not last.invalidated_at:
        remaining = int(settings.OTP_RESEND_COOLDOWN - (now - last.created_at).total_seconds())
        if remaining > 0:
            return OTPRequestResult("cooldown", remaining)

    try:  # fail closed: if the limiter is down we do not send (SMS cost abuse)
        for scope, ident, limit, window in (
            ("otp:send:phone:h", phone, settings.OTP_SEND_LIMIT_PHONE_HOURLY, 3600),
            ("otp:send:phone:d", phone, settings.OTP_SEND_LIMIT_PHONE_DAILY, 86400),
            ("otp:send:ip:h", ip, settings.OTP_SEND_LIMIT_IP_HOURLY, 3600),
            ("otp:send:global:m", "all", settings.OTP_GLOBAL_PER_MINUTE, 60),
        ):
            res = ratelimit.hit(scope, ident, limit=limit, window_seconds=window)
            if not res.allowed:
                log.warning("otp send throttled scope=%s phone=%s ip=%s", scope, mask_phone(phone), ip)
                return OTPRequestResult("throttled", res.retry_after)
    except Exception:
        log.exception("rate limiter unavailable")
        return OTPRequestResult("unavailable")

    code = f"{secrets.randbelow(10**6):06d}"
    salt = secrets.token_hex(8)
    with transaction.atomic():
        _active(phone, purpose).update(invalidated_at=now)
        challenge = OTPChallenge.objects.create(
            phone=phone, purpose=purpose, salt=salt, code_hash=_hash(phone, purpose, code, salt),
            expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
            max_attempts=settings.OTP_MAX_ATTEMPTS, ip=ip if ip != "unknown" else None,
        )
        transaction.on_commit(lambda: send_otp_sms.delay(challenge.pk, code))
    log.info("otp issued challenge=%s phone=%s", challenge.pk, mask_phone(phone))
    return OTPRequestResult("sent", settings.OTP_RESEND_COOLDOWN)


def verify_otp(phone: str, code: str, ip: str, purpose: str = "login") -> OTPVerifyResult:
    try:
        for scope, ident, limit in (
            ("otp:verify:phone", phone, settings.OTP_VERIFY_LIMIT_PHONE),
            ("otp:verify:ip", ip, settings.OTP_VERIFY_LIMIT_IP),
        ):
            if not ratelimit.hit(scope, ident, limit=limit, window_seconds=900).allowed:
                return OTPVerifyResult("throttled")
    except Exception:
        log.exception("rate limiter unavailable")
        return OTPVerifyResult("unavailable")

    now = timezone.now()
    with transaction.atomic():
        challenge = _active(phone, purpose).select_for_update().order_by("-created_at").first()
        if challenge is None:
            _hash(phone, purpose, code, "0")  # keep timing similar for unknown phones
            return OTPVerifyResult("invalid")
        if challenge.expires_at <= now:
            challenge.invalidated_at = now
            challenge.save(update_fields=["invalidated_at"])
            return OTPVerifyResult("expired")
        challenge.attempts += 1
        if challenge.attempts > challenge.max_attempts:
            challenge.invalidated_at = now
            challenge.save(update_fields=["attempts", "invalidated_at"])
            return OTPVerifyResult("locked")
        if hmac.compare_digest(_hash(phone, purpose, code, challenge.salt), challenge.code_hash):
            challenge.consumed_at = now
            challenge.save(update_fields=["attempts", "consumed_at"])
            return OTPVerifyResult("ok")
        challenge.save(update_fields=["attempts"])
        return OTPVerifyResult("invalid")
