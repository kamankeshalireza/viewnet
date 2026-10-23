from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.discounts import services as svc
from apps.discounts.models import Coupon, CouponRedemption

pytestmark = pytest.mark.django_db
SUB = 10_000_000  # 1,000,000 toman


@pytest.fixture
def u1():
    return User.objects.create_user("09120000001")


@pytest.fixture
def u2():
    return User.objects.create_user("09120000002")


def coupon(code="OFF10", **kw):
    kw.setdefault("kind", "percent")
    if kw["kind"] == "percent":
        kw.setdefault("percent", 10)
    return Coupon.objects.create(code=code, **kw)


def test_percent_and_fixed_discounts_and_code_normalization(u1):
    coupon("OFF10")
    coupon("FIX", kind="fixed", amount_rial=2_000_000)
    assert svc.evaluate("  off10 ", u1, SUB).discount_rial == 1_000_000
    assert svc.evaluate("fix", u1, SUB).discount_rial == 2_000_000
    assert Coupon.objects.get(code="OFF10").code == "OFF10"  # stored upper-case


def test_unknown_inactive_and_date_window(u1):
    now = timezone.now()
    with pytest.raises(svc.CouponError):
        svc.evaluate("NOPE", u1, SUB)
    coupon("OFF", is_active=False)
    with pytest.raises(svc.CouponError, match="فعال نیست"):
        svc.evaluate("OFF", u1, SUB)
    coupon("LATER", starts_at=now + timedelta(days=1))
    with pytest.raises(svc.CouponError, match="شروع نشده"):
        svc.evaluate("LATER", u1, SUB)
    coupon("OLD", ends_at=now - timedelta(days=1))
    with pytest.raises(svc.CouponError, match="تمام شده"):
        svc.evaluate("OLD", u1, SUB)


def test_min_order_and_cap(u1):
    coupon("BIG", min_order_rial=20_000_000)
    with pytest.raises(svc.CouponError, match="حداقل"):
        svc.evaluate("BIG", u1, SUB)
    coupon("CAPPED", percent=50, max_discount_rial=700_000)
    assert svc.evaluate("CAPPED", u1, SUB).discount_rial == 700_000


def test_per_user_limit_counts_reserved_and_redeemed(u1, u2):
    c = coupon("ONCE", max_uses_per_user=1)
    svc.reserve(c.pk, u1, "1001", SUB)
    with pytest.raises(svc.CouponError, match="قبلاً"):
        svc.evaluate("ONCE", u1, SUB)
    assert svc.evaluate("ONCE", u2, SUB).discount_rial > 0  # other users unaffected
    svc.release("1001")  # order cancelled -> the use is given back
    assert svc.evaluate("ONCE", u1, SUB).discount_rial > 0


def test_total_limit_blocks_everyone_until_released(u1, u2):
    c = coupon("TOTAL", max_uses_total=1, max_uses_per_user=None)
    svc.reserve(c.pk, u1, "1001", SUB)
    for user in (u1, u2):
        with pytest.raises(svc.CouponError, match="ظرفیت"):
            svc.evaluate("TOTAL", user, SUB)
    svc.release("1001")
    assert svc.evaluate("TOTAL", u2, SUB).discount_rial > 0


def test_reserve_is_idempotent_and_rechecks_limits_under_lock(u1, u2):
    c = coupon("LAST", max_uses_total=1)
    first = svc.reserve(c.pk, u1, "1001", SUB)
    assert svc.reserve(c.pk, u1, "1001", SUB).pk == first.pk and CouponRedemption.objects.count() == 1
    with pytest.raises(svc.CouponError):
        svc.reserve(c.pk, u2, "1002", SUB)  # someone else took the last use between preview and place-order


def test_redeem_and_release_only_touch_reserved_rows(u1):
    c = coupon("X", max_uses_per_user=None)
    svc.reserve(c.pk, u1, "1", SUB)
    svc.reserve(c.pk, u1, "2", SUB)
    assert svc.redeem("1") == 1 and svc.redeem("1") == 0
    assert svc.release("1") == 0  # already redeemed: can't be released
    assert svc.release("2") == 1
    assert dict(CouponRedemption.objects.values_list("order_ref", "status")) == {"1": "redeemed", "2": "released"}


def test_db_constraints():
    with pytest.raises(IntegrityError), transaction.atomic():
        Coupon.objects.create(code="BAD1", kind="percent", percent=150)
    with pytest.raises(IntegrityError), transaction.atomic():
        Coupon.objects.create(code="BAD2", kind="fixed", amount_rial=0)
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        Coupon.objects.create(code="BAD3", percent=10, starts_at=now, ends_at=now - timedelta(days=1))


def test_discount_that_would_be_zero_is_rejected(u1):
    coupon("TINY", percent=1)
    with pytest.raises(svc.CouponError):
        svc.evaluate("TINY", u1, 500)  # 1% of 500 rial floors to 0
