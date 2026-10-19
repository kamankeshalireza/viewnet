from django.conf import settings
from django.db import models
from django.db.models import F, Q


class InventoryItem(models.Model):
    """Stock of one variant (= one phone model/colour). available = on_hand - reserved."""

    variant = models.OneToOneField("catalog.ProductVariant", on_delete=models.CASCADE, related_name="inventory",
                                   verbose_name="تنوع کالا")
    on_hand = models.PositiveIntegerField("موجودی فیزیکی", default=0)
    reserved = models.PositiveIntegerField("رزرو شده", default=0)
    low_stock_threshold = models.PositiveIntegerField("آستانهٔ کمبود", default=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name, verbose_name_plural = "موجودی", "موجودی‌ها"
        constraints = [models.CheckConstraint(condition=Q(reserved__lte=F("on_hand")), name="inventory_reserved_lte_on_hand")]

    def __str__(self):
        return f"{self.variant.sku}: {self.available}"

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class InventoryTransaction(models.Model):
    """Append-only ledger. Every change to InventoryItem has exactly one row here."""

    class Type(models.TextChoices):
        PURCHASE = "purchase", "ورود کالا"
        RESERVATION = "reservation", "رزرو"
        RELEASE = "release", "آزادسازی رزرو"
        SALE = "sale", "فروش"
        RETURN = "return", "بازگشت کالا"
        ADJUSTMENT = "adjustment", "اصلاح انبار"

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=12, choices=Type.choices)
    on_hand_delta = models.IntegerField()
    reserved_delta = models.IntegerField()
    on_hand_after = models.PositiveIntegerField()
    reserved_after = models.PositiveIntegerField()
    reference_type = models.CharField(max_length=20, blank=True)
    reference_id = models.CharField(max_length=40, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "تراکنش انبار", "تراکنش‌های انبار", ["-created_at", "-pk"]
        constraints = [
            # Idempotency: the same business event (e.g. order 12 reservation) can be recorded only once.
            models.UniqueConstraint(fields=["item", "type", "reference_type", "reference_id"],
                                    condition=~Q(reference_id=""), name="uniq_inventory_tx_per_reference"),
        ]

    def __str__(self):
        return f"{self.get_type_display()} {self.on_hand_delta:+d}/{self.reserved_delta:+d}"


class StockReservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        CONSUMED = "consumed", "مصرف‌شده (فروخته شد)"
        RELEASED = "released", "آزادشده"
        EXPIRED = "expired", "منقضی"

    ref = models.CharField("مرجع", max_length=40, db_index=True, help_text="مثلاً شمارهٔ سفارش")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="reservations")
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name, verbose_name_plural = "رزرو موجودی", "رزروهای موجودی"
        constraints = [
            models.UniqueConstraint(fields=["ref", "variant"], name="uniq_reservation_per_ref_variant"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="reservation_qty_positive"),
        ]
        indexes = [models.Index(fields=["expires_at"], condition=Q(status="active"), name="resv_active_expiry_idx")]

    def __str__(self):
        return f"{self.ref} × {self.quantity}"
