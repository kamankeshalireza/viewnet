from django.conf import settings
from django.db import models
from django.db.models import Q


class Cart(models.Model):
    """Persistent cart of a logged-in user. Guests use the session (see stores.SessionStore)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name, verbose_name_plural = "سبد خرید", "سبدهای خرید"

    def __str__(self):
        return f"cart of {self.user_id}"


class CartItem(models.Model):
    """Only variant + quantity are stored; prices are always computed live."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="cart_items")
    quantity = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name, verbose_name_plural = "آیتم سبد", "آیتم‌های سبد"
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="uniq_cart_variant"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_item_qty_gte_1"),
        ]
