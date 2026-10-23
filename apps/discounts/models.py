from django.conf import settings
from django.db import models
from django.db.models import Q


class Coupon(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "درصدی"
        FIXED = "fixed", "مبلغ ثابت"

    code = models.CharField("کد", max_length=30, unique=True, help_text="حروف انگلیسی و عدد؛ بدون حساسیت به بزرگی حروف")
    kind = models.CharField("نوع", max_length=8, choices=Kind.choices, default=Kind.PERCENT)
    percent = models.PositiveSmallIntegerField("درصد", null=True, blank=True)
    amount_rial = models.PositiveBigIntegerField("مبلغ تخفیف (ریال)", null=True, blank=True)
    max_discount_rial = models.PositiveBigIntegerField("سقف تخفیف (ریال)", null=True, blank=True)
    min_order_rial = models.PositiveBigIntegerField("حداقل مبلغ سفارش (ریال)", default=0)
    starts_at = models.DateTimeField("شروع", null=True, blank=True)
    ends_at = models.DateTimeField("پایان", null=True, blank=True)
    max_uses_total = models.PositiveIntegerField("سقف کل استفاده", null=True, blank=True)
    max_uses_per_user = models.PositiveIntegerField("سقف استفاده برای هر کاربر", null=True, blank=True, default=1)
    is_active = models.BooleanField("فعال", default=True)
    note = models.CharField("یادداشت داخلی", max_length=200, blank=True)

    class Meta:
        verbose_name, verbose_name_plural = "کد تخفیف", "کدهای تخفیف"
        constraints = [
            models.CheckConstraint(name="coupon_kind_value", condition=(
                Q(kind="percent", percent__gte=1, percent__lte=100) | Q(kind="fixed", amount_rial__gt=0))),
            models.CheckConstraint(name="coupon_dates_ordered", condition=(
                Q(starts_at__isnull=True) | Q(ends_at__isnull=True) | Q(starts_at__lt=models.F("ends_at")))),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class CouponRedemption(models.Model):
    class Status(models.TextChoices):
        RESERVED = "reserved", "رزرو (در انتظار پرداخت)"
        REDEEMED = "redeemed", "استفاده‌شده"
        RELEASED = "released", "آزاد شد"

    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="coupon_redemptions")
    order_ref = models.CharField("شمارهٔ سفارش", max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RESERVED)
    discount_rial = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name, verbose_name_plural = "استفاده از کد تخفیف", "استفاده‌ها از کد تخفیف"
        constraints = [models.UniqueConstraint(fields=["coupon", "order_ref"], name="uniq_redemption_per_order")]
        indexes = [models.Index(fields=["coupon", "user", "status"])]
