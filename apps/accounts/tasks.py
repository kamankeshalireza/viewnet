import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.core.text import mask_phone
from integrations.sms.registry import get_provider, provider_chain

log = logging.getLogger("otp")


@shared_task(bind=True, queue="otp", max_retries=2, default_retry_delay=3, ignore_result=True)
def send_otp_sms(self, challenge_id: int, code: str):
    from .models import OTPChallenge  # local import: avoid app-loading cycles

    ch = OTPChallenge.objects.filter(pk=challenge_id).first()
    now = timezone.now()
    if not ch or ch.consumed_at or ch.invalidated_at or ch.expires_at <= now:
        return
    ttl = max(int((ch.expires_at - now).total_seconds()), 1)
    for name in provider_chain():  # primary, then fallback
        try:
            result = get_provider(name).send_otp(ch.phone, code, ttl_seconds=ttl)
        except Exception:
            log.exception("sms provider %s crashed challenge=%s", name, ch.pk)
            continue
        if result.ok:
            OTPChallenge.objects.filter(pk=ch.pk).update(provider=name, provider_message_id=result.provider_message_id or "")
            return
        log.warning("sms provider %s failed challenge=%s code=%s phone=%s", name, ch.pk, result.error_code, mask_phone(ch.phone))
    if self.request.retries < self.max_retries:
        raise self.retry()
    log.error("otp delivery failed on all providers challenge=%s", ch.pk)


@shared_task(queue="default", ignore_result=True)
def cleanup_otp_challenges(days: int = 7):
    from .models import OTPChallenge

    OTPChallenge.objects.filter(created_at__lt=timezone.now() - timedelta(days=days)).delete()



