"""Coupon rules. Usage is *reserved* at checkout and *redeemed* on payment so limits can't be raced."""
from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.text import to_ascii_digits

from .domain import compute_discount
from .models import Coupon, CouponRedemption

R = CouponRedemption.Status


class CouponError(Exception):
    """Message is shown to the shopper (Persian)."""


@dataclass(frozen=True)
class Evaluation:
    coupon: Coupon
    discount_rial: int


def normalize_code(code: str) -> str:
    return to_ascii_digits(code or "").strip().upper()


def _usage(coupon: Coupon, user=None) -> int:
    qs = CouponRedemption.objects.filter(coupon=coupon, status__in=[R.RESERVED, R.REDEEMED])
    return (qs.filter(user=user) if user is not None else qs).count()


def _check(coupon: Coupon, user, subtotal_rial: int, now, *, ignore_ref: str | None = None) -> int:
    if not coupon.is_active:
        raise CouponError("این کد تخفیف فعال نیست.")
    if coupon.starts_at and now < coupon.starts_at:
        raise CouponError("زمان استفاده از این کد هنوز شروع نشده است.")
    if coupon.ends_at and now > coupon.ends_at:
        raise CouponError("مهلت استفاده از این کد تمام شده است.")
    if subtotal_rial < coupon.min_order_rial:
        raise CouponError(f"حداقل مبلغ سفارش برای این کد {coupon.min_order_rial // 10:,} تومان است.")
    own = CouponRedemption.objects.filter(coupon=coupon, order_ref=ignore_ref).exists() if ignore_ref else False
    if not own:
        if coupon.max_uses_total is not None and _usage(coupon) >= coupon.max_uses_total:
            raise CouponError("ظرفیت استفاده از این کد تکمیل شده است.")
        if coupon.max_uses_per_user is not None and _usage(coupon, user) >= coupon.max_uses_per_user:
            raise CouponError("شما قبلاً از این کد استفاده کرده‌اید.")
    discount = compute_discount(kind=coupon.kind, percent=coupon.percent, amount_rial=coupon.amount_rial,
                                max_discount_rial=coupon.max_discount_rial, subtotal_rial=subtotal_rial)
    if discount <= 0:
        raise CouponError("این کد برای سبد شما تخفیفی ایجاد نمی‌کند.")
    return discount


def evaluate(code: str, user, subtotal_rial: int, *, now=None) -> Evaluation:
    """Read-only check used for the checkout preview."""
    coupon = Coupon.objects.filter(code=normalize_code(code)).first()
    if coupon is None:
        raise CouponError("کد تخفیف نامعتبر است.")
    return Evaluation(coupon, _check(coupon, user, subtotal_rial, now or timezone.now()))


def reserve(coupon_id: int, user, order_ref: str, subtotal_rial: int) -> CouponRedemption:
    """Count the usage against the limits under a row lock on the coupon (so two orders can't both take the last use)."""
    with transaction.atomic():
        coupon = Coupon.objects.select_for_update().get(pk=coupon_id)
        existing = CouponRedemption.objects.filter(coupon=coupon, order_ref=order_ref).first()
        if existing:
            return existing
        discount = _check(coupon, user, subtotal_rial, timezone.now())
        try:
            with transaction.atomic():
                return CouponRedemption.objects.create(coupon=coupon, user=user, order_ref=order_ref, discount_rial=discount)
        except IntegrityError:
            return CouponRedemption.objects.get(coupon=coupon, order_ref=order_ref)


def release(order_ref: str) -> int:
    return CouponRedemption.objects.filter(order_ref=order_ref, status=R.RESERVED).update(status=R.RELEASED, updated_at=timezone.now())


def redeem(order_ref: str) -> int:
    return CouponRedemption.objects.filter(order_ref=order_ref, status=R.RESERVED).update(status=R.REDEEMED, updated_at=timezone.now())
