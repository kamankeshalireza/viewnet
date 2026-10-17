from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import OTPChallenge
from apps.accounts.services.otp import request_otp, verify_otp
from integrations.sms.fake import FakeSMSProvider

PHONE = "09123456789"
pytestmark = pytest.mark.django_db


@pytest.fixture
def issue(django_capture_on_commit_callbacks):
    def _issue(phone=PHONE, ip="1.1.1.1"):
        with django_capture_on_commit_callbacks(execute=True):
            res = request_otp(phone, ip)
        return res, FakeSMSProvider.last_code(phone)
    return _issue


def test_issue_and_verify_success(issue):
    res, code = issue()
    assert res.sent and code and len(code) == 6
    assert verify_otp(PHONE, code, "1.1.1.1").ok


def test_code_never_stored_in_plaintext(issue):
    _, code = issue()
    ch = OTPChallenge.objects.get()
    assert code not in (ch.code_hash, ch.salt) and len(ch.code_hash) == 64


def test_code_is_single_use(issue):
    _, code = issue()
    assert verify_otp(PHONE, code, "1.1.1.1").ok
    assert verify_otp(PHONE, code, "1.1.1.1").reason == "invalid"


def test_wrong_code_then_lock_after_max_attempts(issue):
    _, code = issue()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert verify_otp(PHONE, wrong, "1.1.1.1").reason == "invalid"
    assert verify_otp(PHONE, wrong, "1.1.1.1").reason == "locked"
    assert verify_otp(PHONE, code, "1.1.1.1").reason == "invalid"  # even the right code is dead now


def test_expired_code(issue):
    _, code = issue()
    OTPChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert verify_otp(PHONE, code, "1.1.1.1").reason == "expired"


def test_resend_cooldown_then_new_code_invalidates_old(issue):
    _, first = issue()
    res, _ = issue()
    assert res.reason == "cooldown" and 0 < res.retry_after <= 120
    OTPChallenge.objects.update(created_at=timezone.now() - timedelta(seconds=500))
    res, second = issue()
    assert res.sent
    if first != second:
        assert verify_otp(PHONE, first, "1.1.1.1").reason == "invalid"
    assert verify_otp(PHONE, second, "1.1.1.1").ok


def test_phone_hourly_limit(issue, settings):
    settings.OTP_SEND_LIMIT_PHONE_HOURLY = 2
    for _ in range(2):
        assert issue()[0].sent
        OTPChallenge.objects.update(created_at=timezone.now() - timedelta(seconds=500))
    assert issue()[0].reason == "throttled"


def test_ip_limit_across_phones(issue, settings):
    settings.OTP_SEND_LIMIT_IP_HOURLY = 2
    assert issue("09120000001", "9.9.9.9")[0].sent
    assert issue("09120000002", "9.9.9.9")[0].sent
    assert issue("09120000003", "9.9.9.9")[0].reason == "throttled"
    assert issue("09120000004", "8.8.8.8")[0].sent


def test_global_budget_circuit_breaker(issue, settings):
    settings.OTP_GLOBAL_PER_MINUTE = 1
    assert issue("09120000001", "1.1.1.1")[0].sent
    assert issue("09120000002", "2.2.2.2")[0].reason == "throttled"


def test_verify_throttle(issue, settings):
    settings.OTP_VERIFY_LIMIT_PHONE = 2
    issue()
    verify_otp(PHONE, "000000", "1.1.1.1")
    verify_otp(PHONE, "000000", "1.1.1.1")
    assert verify_otp(PHONE, "000000", "1.1.1.1").reason == "throttled"


def test_fail_closed_when_limiter_down(monkeypatch, django_capture_on_commit_callbacks):
    from apps.core import ratelimit

    def boom(*a, **k):
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "hit", boom)
    with django_capture_on_commit_callbacks(execute=True):
        assert request_otp(PHONE, "1.1.1.1").reason == "unavailable"
    assert FakeSMSProvider.sent == [] and OTPChallenge.objects.count() == 0


def test_verify_unknown_phone_is_just_invalid():
    assert verify_otp("09999999999", "123456", "1.1.1.1").reason == "invalid"
