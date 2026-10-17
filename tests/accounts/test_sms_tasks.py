import pytest

from apps.accounts.models import OTPChallenge
from apps.accounts.services.otp import request_otp
from integrations.sms.base import SMSResult
from integrations.sms.fake import FakeSMSProvider

pytestmark = pytest.mark.django_db


def test_failover_to_second_provider(settings, monkeypatch, django_capture_on_commit_callbacks):
    settings.SMS_PROVIDERS = {**settings.SMS_PROVIDERS, "broken": "tests.accounts.test_sms_tasks.Broken"}
    settings.SMS_PROVIDER, settings.SMS_FALLBACK_PROVIDER = "broken", "fake"
    with django_capture_on_commit_callbacks(execute=True):
        request_otp("09123456789", "1.1.1.1")
    assert FakeSMSProvider.last_code("09123456789")
    assert OTPChallenge.objects.get().provider == "fake"


class Broken(FakeSMSProvider):
    code = "broken"

    def send_otp(self, phone, code, *, ttl_seconds):
        return SMSResult(ok=False, error_code="down", retryable=True)


def test_expired_challenge_is_not_sent(django_capture_on_commit_callbacks):
    from datetime import timedelta

    from django.utils import timezone

    from apps.accounts.tasks import send_otp_sms

    with django_capture_on_commit_callbacks(execute=False):
        request_otp("09123456789", "1.1.1.1")
    FakeSMSProvider.reset()
    OTPChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    send_otp_sms(OTPChallenge.objects.get().pk, "123456")
    assert FakeSMSProvider.sent == []
