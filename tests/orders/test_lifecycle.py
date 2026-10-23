import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.core import events
from apps.discounts.models import Coupon, CouponRedemption
from apps.inventory import services as inv
from apps.inventory.models import InventoryItem, InventoryTransaction, StockReservation
from apps.inventory.tasks import expire_stock_reservations
from apps.orders.models import Order, OrderStatusHistory
from apps.orders.services import checkout
from apps.orders.services import orders as svc

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(user, address, make_variant, fill_cart):
    v = make_variant(100_000, stock=5, title="قاب")
    Coupon.objects.create(code="OFF10", kind="percent", percent=10)
    o, _ = checkout.place_order(user, fill_cart((v, 2)), address_id=address.pk, coupon_code="OFF10", checkout_token=uuid.uuid4())
    o.variant = v
    return o


def stock(order):
    return InventoryItem.objects.get(variant=order.variant)


def test_cancel_releases_stock_and_coupon_and_is_idempotent(order, django_capture_on_commit_callbacks):
    seen = []
    events.subscribe(events.OrderCancelled, seen.append)
    with django_capture_on_commit_callbacks(execute=True):
        svc.transition(order.pk, "cancelled", reason="انصراف")
    order.refresh_from_db()
    assert order.status == "cancelled" and order.cancelled_at and order.expires_at is None and order.cancel_reason == "انصراف"
    assert (stock(order).reserved, stock(order).on_hand) == (0, 5)
    assert CouponRedemption.objects.get().status == "released"
    assert svc.transition(order.pk, "cancelled").status == "cancelled"  # repeat is harmless
    assert OrderStatusHistory.objects.filter(order=order, to_status="cancelled").count() == 1
    assert [e.order_id for e in seen] == [order.pk]  # one event, published after commit


def test_cancel_by_customer_only_for_owner(order, user, django_user_model):
    stranger = django_user_model.objects.create_user("09120000009")
    with pytest.raises(svc.OrderError):
        svc.cancel_by_customer(order, stranger)
    assert svc.cancel_by_customer(order, user).status == "cancelled"


def test_mark_paid_consumes_stock_redeems_coupon_counts_sales(order):
    paid = svc.mark_paid(order.pk)
    assert (paid.status, paid.payment_status) == ("paid", "paid") and paid.paid_at and paid.expires_at is None
    assert (stock(order).on_hand, stock(order).reserved) == (3, 0)
    assert CouponRedemption.objects.get().status == "redeemed"
    assert Product.objects.get(variants=order.variant).sales_count == 2
    assert InventoryTransaction.objects.filter(type="sale").count() == 1


def test_mark_paid_is_idempotent(order):
    svc.mark_paid(order.pk)
    svc.mark_paid(order.pk)  # gateway callback delivered twice
    assert Product.objects.get(variants=order.variant).sales_count == 2 and stock(order).on_hand == 3
    assert OrderStatusHistory.objects.filter(order=order, to_status="paid").count() == 1


def test_mark_paid_after_stock_was_released_needs_manual_review(order):
    StockReservation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    inv.expire_overdue()  # reservation gone (customer paid too late)
    with pytest.raises(svc.ReservationLost):
        svc.mark_paid(order.pk)
    order.refresh_from_db()
    assert order.status == "pending"  # nothing half-applied
    svc.flag_for_review(order.pk, "پرداخت دیرهنگام")
    order.refresh_from_db()
    assert order.needs_review and "نیازمند بررسی" in order.history.last().reason


def test_paying_requires_mark_paid_and_cancelling_a_paid_order_is_not_yet_supported(order):
    with pytest.raises(svc.TransitionNotSupported):
        svc.transition(order.pk, "paid")
    svc.mark_paid(order.pk)
    with pytest.raises(svc.TransitionNotSupported, match="بازگشت وجه"):
        svc.transition(order.pk, "cancelled")


def test_fulfilment_path_and_invalid_jumps(order):
    svc.mark_paid(order.pk)
    with pytest.raises(svc.InvalidTransition):
        svc.transition(order.pk, "shipped")  # must pack first
    for to in ("processing", "packed", "shipped", "delivered"):
        assert svc.transition(order.pk, to).status == to
    assert list(order.history.values_list("to_status", flat=True)) == ["pending", "paid", "processing", "packed", "shipped", "delivered"]
    with pytest.raises(svc.InvalidTransition):
        svc.transition(order.pk, "pending")


def test_digital_order_goes_processing_to_delivered(user, make_variant, fill_cart):
    v = make_variant(300_000, digital=True)
    o, _ = checkout.place_order(user, fill_cart((v, 1)), address_id=None, checkout_token=uuid.uuid4())
    svc.mark_paid(o.pk)
    svc.transition(o.pk, "processing")
    assert svc.transition(o.pk, "delivered").status == "delivered"


def test_expire_unpaid_cancels_only_overdue_open_orders(order, user, address, make_variant, fill_cart):
    other, _ = checkout.place_order(user, fill_cart((make_variant(stock=3), 1)), address_id=address.pk, checkout_token=uuid.uuid4())
    Order.objects.filter(pk=order.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert svc.expire_unpaid() == 1
    order.refresh_from_db(), other.refresh_from_db()
    assert (order.status, other.status) == ("cancelled", "pending") and stock(order).reserved == 0


def test_stock_expiry_event_cancels_the_unpaid_order(order):
    StockReservation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert expire_stock_reservations() == 1  # inventory task publishes ReservationsExpired -> orders handler
    order.refresh_from_db()
    assert order.status == "cancelled" and order.cancel_reason == "انقضای مهلت پرداخت"
    assert CouponRedemption.objects.get().status == "released"


def test_expiry_handler_ignores_paid_and_foreign_refs(order):
    svc.mark_paid(order.pk)
    from apps.orders.handlers import on_reservations_expired
    on_reservations_expired(events.ReservationsExpired(refs=(f"order:{order.number}", "order:0000000000", "cart:1")))
    order.refresh_from_db()
    assert order.status == "paid"


def test_database_checks_reject_inconsistent_totals(order):
    from django.db import IntegrityError, transaction
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.filter(pk=order.pk).update(total_rial=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        order.items.update(line_total_rial=1)
