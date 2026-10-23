from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        AWAITING_PAYMENT = "awaiting_payment", "در حال پرداخت"
        PAID = "paid", "پرداخت‌شده"
        PROCESSING = "processing", "در حال پردازش"
        PACKED = "packed", "بسته‌بندی شد"
        SHIPPED = "shipped", "ارسال شد"
        DELIVERED = "delivered", "تحویل داده شد"
        CANCELLED = "cancelled", "لغو شد"
        RETURN_REQUESTED = "return_requested", "درخواست مرجوعی"
        RETURNED = "returned", "مرجوع شد"
        REFUNDED = "refunded", "وجه بازگردانده شد"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "پرداخت‌نشده"
        PAID = "paid", "پرداخت‌شده"
        REFUND_PENDING = "refund_pending", "در انتظار بازگشت وجه"
        PARTIALLY_REFUNDED = "partially_refunded", "بخشی از وجه بازگردانده شد"
        REFUNDED = "refunded", "وجه بازگردانده شد"

    BADGE = {"pending": "warning", "awaiting_payment": "warning", "paid": "success", "processing": "info", "packed": "info",
             "shipped": "primary", "delivered": "success", "cancelled": "secondary", "return_requested": "warning",
             "returned": "secondary", "refunded": "secondary"}

    number = models.CharField("شمارهٔ سفارش", max_length=12, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name="مشتری")
    status = models.CharField("وضعیت", max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment_status = models.CharField("وضعیت پرداخت", max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    checkout_token = models.UUIDField(unique=True, editable=False)
    requires_shipping = models.BooleanField(default=True)

    # Address snapshot: later edits/deletes of the saved address never change an existing order.
    receiver_name = models.CharField("گیرنده", max_length=100)
    receiver_phone = models.CharField("موبایل گیرنده", max_length=11)
    ship_province = models.CharField(max_length=60, blank=True)
    ship_city = models.CharField(max_length=80, blank=True)
    ship_address = models.TextField(blank=True)
    ship_plaque = models.CharField(max_length=10, blank=True)
    ship_unit = models.CharField(max_length=10, blank=True)
    ship_postal_code = models.CharField(max_length=10, blank=True)
    shipping_method = models.ForeignKey("shipping.ShippingMethod", null=True, blank=True, on_delete=models.SET_NULL)
    shipping_method_name = models.CharField(max_length=80, blank=True)

    subtotal_rial = models.PositiveBigIntegerField("جمع کالاها")
    coupon_discount_rial = models.PositiveBigIntegerField("تخفیف", default=0)
    shipping_rial = models.PositiveBigIntegerField("هزینهٔ ارسال", default=0)
    tax_rial = models.PositiveBigIntegerField("مالیات", default=0)
    total_rial = models.PositiveBigIntegerField("مبلغ قابل پرداخت")
    coupon_code = models.CharField(max_length=30, blank=True)
    customer_note = models.CharField("توضیحات مشتری", max_length=300, blank=True)

    placed_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    needs_review = models.BooleanField("نیازمند بررسی", default=False)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "سفارش", "سفارش‌ها", ["-placed_at", "-pk"]
        constraints = [
            models.CheckConstraint(name="order_total_formula", condition=Q(
                total_rial=F("subtotal_rial") - F("coupon_discount_rial") + F("shipping_rial") + F("tax_rial"))),
            models.CheckConstraint(name="order_discount_lte_subtotal", condition=Q(coupon_discount_rial__lte=F("subtotal_rial"))),
        ]
        indexes = [models.Index(fields=["user", "-placed_at"]), models.Index(fields=["status", "expires_at"])]

    def __str__(self):
        return f"سفارش {self.number}"

    @property
    def badge_class(self) -> str:
        return self.BADGE.get(self.status, "secondary")

    @property
    def stock_ref(self) -> str:
        return f"order:{self.number}"

    @property
    def is_unpaid_open(self) -> bool:
        return self.status in (self.Status.PENDING, self.Status.AWAITING_PAYMENT)

    def get_absolute_url(self):
        return f"/orders/{self.number}/"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.ProductVariant", null=True, on_delete=models.PROTECT, related_name="order_items")
    product_title = models.CharField(max_length=200)
    variant_title = models.CharField(max_length=200, blank=True)
    sku = models.CharField(max_length=50)
    unit_price_rial = models.PositiveBigIntegerField()
    quantity = models.PositiveSmallIntegerField()
    discount_rial = models.PositiveBigIntegerField("سهم از تخفیف سفارش", default=0)
    line_total_rial = models.PositiveBigIntegerField()
    weight_g = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name, verbose_name_plural = "قلم سفارش", "اقلام سفارش"
        constraints = [
            models.CheckConstraint(name="order_item_line_total", condition=Q(
                line_total_rial=F("unit_price_rial") * F("quantity") - F("discount_rial"))),
            models.CheckConstraint(name="order_item_qty_positive", condition=Q(quantity__gte=1)),
        ]

    def __str__(self):
        return f"{self.product_title} × {self.quantity}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "تاریخچهٔ وضعیت", "تاریخچهٔ وضعیت‌ها", ["created_at", "pk"]
