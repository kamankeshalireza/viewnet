"""Checkout (architecture §7, §10, §11): quote → place order atomically (order + stock reservation + coupon)."""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Address
from apps.cart import services as cart_services
from apps.cart.stores import CartStore
from apps.core.events import OrderCreated, publish
from apps.core.models import SiteSetting
from apps.core.money import allocate_proportionally
from apps.discounts import services as coupons
from apps.inventory import services as inventory
from apps.shipping import services as shipping
from apps.shipping.models import ShippingMethod

from ..domain.pricing import OrderTotals, compute_totals
from ..models import Order, OrderItem, OrderStatusHistory


class CheckoutError(Exception):
    """Message is user-facing (Persian)."""


@dataclass
class Quote:
    cart: cart_services.CartView
    totals: OrderTotals
    requires_shipping: bool
    methods: list[ShippingMethod] = field(default_factory=list)
    method: ShippingMethod | None = None
    coupon: coupons.Evaluation | None = None
    coupon_error: str = ""

    @property
    def lines(self):
        return self.cart.lines


def build_quote(user, store: CartStore, *, coupon_code: str = "", shipping_code: str = "") -> Quote:
    cart = cart_services.build_cart(store, fix=False)
    if cart.is_empty:
        raise CheckoutError("سبد خرید شما خالی است.")
    if cart.issues:
        raise CheckoutError("موجودی یا قیمت برخی کالاها تغییر کرده است؛ سبد خرید را بررسی کنید.")
    requires_shipping = any(line.product.requires_shipping for line in cart.lines)
    methods = shipping.available_methods(requires_shipping)
    method = None
    if requires_shipping:
        if not methods:
            raise CheckoutError("در حال حاضر روش ارسالی فعال نیست.")
        method = next((m for m in methods if m.code == shipping_code), methods[0])
    subtotal = cart.totals.subtotal_rial
    coupon, coupon_error = None, ""
    if coupon_code:
        try:
            coupon = coupons.evaluate(coupon_code, user, subtotal)
        except coupons.CouponError as exc:
            coupon_error = str(exc)
    totals = compute_totals(subtotal_rial=subtotal, coupon_discount_rial=coupon.discount_rial if coupon else 0,
                            shipping_rial=shipping.quote(method) if method else 0)
    return Quote(cart, totals, requires_shipping, methods, method, coupon, coupon_error)


def _new_number() -> str:
    return str(secrets.randbelow(9 * 10**9) + 10**9)  # 10 digits, non-sequential (doesn't leak sales volume)


def place_order(user, store: CartStore, *, address_id: int | None, shipping_code: str = "", coupon_code: str = "",
                note: str = "", checkout_token: uuid.UUID) -> tuple[Order, bool]:
    """Returns (order, created). Submitting the same checkout_token twice returns the first order (idempotent)."""
    existing = Order.objects.filter(checkout_token=checkout_token).first()
    if existing:
        if existing.user_id != user.pk:
            raise CheckoutError("درخواست نامعتبر است.")
        return existing, False

    setting = SiteSetting.load()
    if not setting.purchases_enabled:
        raise CheckoutError("ثبت سفارش موقتاً غیرفعال است. لطفاً بعداً تلاش کنید.")

    quote = build_quote(user, store, coupon_code=coupon_code, shipping_code=shipping_code)
    if coupon_code and quote.coupon is None:
        raise CheckoutError(quote.coupon_error or "کد تخفیف نامعتبر است.")
    if quote.totals.subtotal_rial < setting.min_order_rial:
        raise CheckoutError(f"حداقل مبلغ سفارش {setting.min_order_rial // 10:,} تومان است.")

    address = None
    if quote.requires_shipping:
        address = Address.objects.filter(pk=address_id, user=user, is_deleted=False).select_related("province", "city").first() \
            if address_id else None
        if address is None:
            raise CheckoutError("لطفاً نشانی تحویل را انتخاب کنید.")

    now = timezone.now()
    discounts = allocate_proportionally(quote.totals.coupon_discount_rial, [line.total_rial for line in quote.lines])
    for _ in range(5):  # retry only on an (astronomically rare) order-number collision
        number = _new_number()
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    number=number, user=user, checkout_token=checkout_token, requires_shipping=quote.requires_shipping,
                    receiver_name=(address.receiver_name if address else user.get_full_name() or user.phone),
                    receiver_phone=(address.receiver_phone if address else user.phone),
                    ship_province=address.province.name if address else "", ship_city=address.city.name if address else "",
                    ship_address=address.address_line if address else "", ship_plaque=address.plaque if address else "",
                    ship_unit=address.unit if address else "", ship_postal_code=address.postal_code if address else "",
                    shipping_method=quote.method, shipping_method_name=quote.method.name if quote.method else "",
                    subtotal_rial=quote.totals.subtotal_rial, coupon_discount_rial=quote.totals.coupon_discount_rial,
                    shipping_rial=quote.totals.shipping_rial, tax_rial=quote.totals.tax_rial, total_rial=quote.totals.total_rial,
                    coupon_code=quote.coupon.coupon.code if quote.coupon else "", customer_note=note.strip()[:300],
                    placed_at=now, expires_at=now + timedelta(minutes=settings.ORDER_PAYMENT_TIMEOUT_MINUTES),
                )
                OrderItem.objects.bulk_create([
                    OrderItem(order=order, variant=line.variant, product_title=line.product.title, variant_title=line.variant.label,
                              sku=line.variant.sku, unit_price_rial=line.unit_price_rial, quantity=line.quantity,
                              discount_rial=disc, line_total_rial=line.total_rial - disc, weight_g=line.variant.weight_g)
                    for line, disc in zip(quote.lines, discounts, strict=True)
                ])
                try:
                    inventory.reserve(order.stock_ref, [(line.variant.pk, line.quantity) for line in quote.lines],
                                      ttl_minutes=settings.ORDER_PAYMENT_TIMEOUT_MINUTES)
                except inventory.OutOfStock as exc:
                    title = next((ln.product.title for ln in quote.lines if ln.variant.pk == exc.variant_id), "یکی از کالاها")
                    raise CheckoutError(f"موجودی «{title}» کافی نیست.") from exc
                if quote.coupon:
                    try:
                        coupons.reserve(quote.coupon.coupon.pk, user, order.number, quote.totals.subtotal_rial)
                    except coupons.CouponError as exc:
                        raise CheckoutError(str(exc)) from exc
                OrderStatusHistory.objects.create(order=order, from_status="", to_status=order.status, actor=user, reason="ثبت سفارش")
                transaction.on_commit(lambda o=order: publish(OrderCreated(order_id=o.pk)))
            break
        except IntegrityError:
            raced = Order.objects.filter(checkout_token=checkout_token).first()  # double submit that lost the race
            if raced:
                return raced, False
            continue
    else:
        raise CheckoutError("ثبت سفارش با خطا مواجه شد؛ دوباره تلاش کنید.")
    store.clear()
    return order, True
