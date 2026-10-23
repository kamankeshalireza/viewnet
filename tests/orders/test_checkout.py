import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.cart.stores import DbStore
from apps.core.models import SiteSetting
from apps.discounts.models import Coupon, CouponRedemption
from apps.inventory.models import InventoryItem, StockReservation
from apps.orders.models import Order, OrderStatusHistory
from apps.orders.services import checkout

pytestmark = pytest.mark.django_db


def place(user, store, address=None, **kw):
    kw.setdefault("checkout_token", uuid.uuid4())
    return checkout.place_order(user, store, address_id=address.pk if address else None, **kw)


def test_places_a_physical_order_end_to_end(user, address, make_variant, fill_cart):
    v = make_variant(190_000, stock=5, title="قاب")
    store = fill_cart((v, 2))
    order, created = place(user, store, address, note="  سریع  ")
    assert created and len(order.number) == 10 and order.status == "pending" and order.payment_status == "unpaid"
    assert (order.subtotal_rial, order.shipping_rial, order.total_rial) == (3_800_000, 0, 3_800_000)  # free shipping
    assert order.expires_at > timezone.now() and order.customer_note == "سریع" and order.requires_shipping
    assert (order.ship_city, order.ship_postal_code, order.receiver_phone, order.shipping_method_name) == ("تهران", "1234567890", "09123456789", "ارسال رایگان")
    item = order.items.get()
    assert (item.product_title, item.sku, item.quantity, item.unit_price_rial, item.line_total_rial) == ("قاب", v.sku, 2, 1_900_000, 3_800_000)
    assert InventoryItem.objects.get(variant=v).reserved == 2 and StockReservation.objects.get().ref == f"order:{order.number}"
    assert DbStore(user).items() == {}  # cart emptied
    assert OrderStatusHistory.objects.get(order=order).to_status == "pending"


def test_address_snapshot_survives_later_edits(user, address, make_variant, fill_cart):
    order, _ = place(user, fill_cart((make_variant(), 1)), address)
    Address.objects.filter(pk=address.pk).update(address_line="جای دیگر", is_deleted=True)
    order.refresh_from_db()
    assert order.ship_address == "خیابان ولیعصر"


def test_same_token_returns_the_same_order_without_double_reserving(user, address, make_variant, fill_cart):
    v = make_variant(stock=5)
    token = uuid.uuid4()
    first, created = place(user, fill_cart((v, 2)), address, checkout_token=token)
    second, created2 = place(user, fill_cart((v, 2)), address, checkout_token=token)  # double click / retry
    assert created and not created2 and first.pk == second.pk
    assert Order.objects.count() == 1 and InventoryItem.objects.get(variant=v).reserved == 2
    other = User.objects.create_user("09120000009")
    with pytest.raises(checkout.CheckoutError):
        place(other, DbStore(other), None, checkout_token=token)  # someone else's token


def test_out_of_stock_rolls_everything_back(user, address, make_variant, fill_cart):
    ok, scarce = make_variant(stock=5, title="الف"), make_variant(stock=1, title="ب")
    store = fill_cart((ok, 2), (scarce, 1))
    from apps.inventory import services as inv
    inv.reserve("order:someone-else", [(scarce.pk, 1)])  # the last unit gets taken after the cart was filled
    with pytest.raises(checkout.CheckoutError):
        place(user, store, address)
    assert not Order.objects.exists() and InventoryItem.objects.get(variant=ok).reserved == 0
    assert store.items() == {ok.pk: 2, scarce.pk: 1}  # cart untouched so the customer can fix it


def test_cart_with_stale_items_is_refused(user, address, make_variant, fill_cart):
    v = make_variant(stock=5)
    store = fill_cart((v, 5))
    from apps.inventory import services as inv
    inv.adjust(v.pk, -3, note="شمارش")  # only 2 left but the cart wants 5
    with pytest.raises(checkout.CheckoutError, match="تغییر کرده"):
        place(user, store, address)


@pytest.mark.parametrize("case", ["empty", "no_address", "foreign_address", "deleted_address"])
def test_validation_errors(case, user, address, city, make_variant, fill_cart):
    store = fill_cart() if case == "empty" else fill_cart((make_variant(), 1))
    addr = {"empty": address, "no_address": None, "foreign_address": None, "deleted_address": address}[case]
    if case == "foreign_address":
        other = User.objects.create_user("09120000009")
        addr = Address.objects.create(user=other, province=city.province, city=city, address_line="x", postal_code="1234567890",
                                      receiver_name="r", receiver_phone="09120000009")
    if case == "deleted_address":
        Address.objects.filter(pk=address.pk).update(is_deleted=True)
    with pytest.raises(checkout.CheckoutError):
        place(user, store, addr)
    assert not Order.objects.exists()


def test_kill_switch_and_minimum_order(user, address, make_variant, fill_cart):
    v = make_variant(50_000)
    store = fill_cart((v, 1))
    SiteSetting.load()
    SiteSetting.objects.filter(pk=1).update(min_order_rial=1_000_000)
    with pytest.raises(checkout.CheckoutError, match="حداقل"):
        place(user, store, address)
    SiteSetting.objects.filter(pk=1).update(min_order_rial=0, purchases_enabled=False)
    with pytest.raises(checkout.CheckoutError, match="غیرفعال"):
        place(user, store, address)


def test_coupon_discount_is_allocated_across_items_and_reserved(user, address, make_variant, fill_cart):
    a, b = make_variant(100_000, title="الف"), make_variant(300_000, title="ب")
    Coupon.objects.create(code="OFF10", kind="percent", percent=10)
    order, _ = place(user, fill_cart((a, 1), (b, 1)), address, coupon_code="off10")
    assert (order.subtotal_rial, order.coupon_discount_rial, order.total_rial, order.coupon_code) == (4_000_000, 400_000, 3_600_000, "OFF10")
    discounts = sorted(order.items.values_list("discount_rial", flat=True))
    assert discounts == [100_000, 300_000] and sum(discounts) == 400_000  # proportional, exact sum
    assert sum(order.items.values_list("line_total_rial", flat=True)) == order.total_rial
    r = CouponRedemption.objects.get()
    assert (r.order_ref, r.status, r.discount_rial) == (order.number, "reserved", 400_000)


def test_invalid_coupon_blocks_the_order(user, address, make_variant, fill_cart):
    store = fill_cart((make_variant(), 1))
    with pytest.raises(checkout.CheckoutError, match="نامعتبر"):
        place(user, store, address, coupon_code="NOPE")
    assert not Order.objects.exists()


def test_coupon_race_for_last_use_rolls_back_the_order(user, address, make_variant, fill_cart):
    v = make_variant(stock=5)
    c = Coupon.objects.create(code="ONE", kind="percent", percent=10, max_uses_total=1)
    other = User.objects.create_user("09120000009")
    CouponRedemption.objects.create(coupon=c, user=other, order_ref="999", discount_rial=1)  # taken meanwhile
    store = fill_cart((v, 1))
    q = checkout.build_quote  # preview still thinks it's valid only if usage < limit; force past the preview
    try:
        checkout.build_quote = lambda *a, **k: _quote_with_coupon(q, c, *a, **k)
        with pytest.raises(checkout.CheckoutError, match="ظرفیت"):
            place(user, store, address, coupon_code="ONE")
    finally:
        checkout.build_quote = q
    assert not Order.objects.exists() and InventoryItem.objects.get(variant=v).reserved == 0


def _quote_with_coupon(real, coupon, user, store, **kw):
    from apps.discounts.services import Evaluation
    quote = real(user, store, shipping_code=kw.get("shipping_code", ""))
    quote.coupon = Evaluation(coupon, 1_000)
    return quote


def test_digital_only_order_needs_no_address_or_shipping(user, make_variant, fill_cart):
    v = make_variant(300_000, digital=True, title="اپل آیدی")
    order, _ = place(user, fill_cart((v, 1)))
    assert not order.requires_shipping and order.shipping_method is None and order.shipping_rial == 0
    assert order.ship_address == "" and order.receiver_phone == user.phone
    assert not StockReservation.objects.exists() and not InventoryItem.objects.exists()


def test_mixed_cart_requires_address(user, address, make_variant, fill_cart):
    phys, dig = make_variant(title="قاب"), make_variant(digital=True, title="اپل آیدی")
    with pytest.raises(checkout.CheckoutError, match="نشانی"):
        place(user, fill_cart((phys, 1), (dig, 1)))
    order, _ = place(user, fill_cart((phys, 1), (dig, 1)), address)
    assert order.requires_shipping and order.items.count() == 2


def test_prices_are_snapshotted_not_linked(user, address, make_variant, fill_cart):
    from apps.catalog.models import ProductVariant
    v = make_variant(100_000)
    order, _ = place(user, fill_cart((v, 1)), address)
    ProductVariant.objects.filter(pk=v.pk).update(price_rial=9_999_999)
    assert order.items.get().unit_price_rial == 1_000_000


def test_expiry_window_matches_payment_timeout(user, address, make_variant, fill_cart, settings):
    settings.ORDER_PAYMENT_TIMEOUT_MINUTES = 5
    order, _ = place(user, fill_cart((make_variant(), 1)), address)
    assert timedelta(minutes=4) < order.expires_at - timezone.now() <= timedelta(minutes=5)
    assert StockReservation.objects.get().expires_at - timezone.now() <= timedelta(minutes=5)
