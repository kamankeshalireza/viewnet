import threading
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant
from apps.core import events
from apps.inventory import services as inv
from apps.inventory.models import InventoryItem, InventoryTransaction, StockReservation
from apps.inventory.tasks import expire_stock_reservations
from tests.catalog.helpers import make_product

pytestmark = pytest.mark.django_db


def variant(price=100_000, stock=0, digital=False, title="کالا", **kw):
    p = make_product(title, variants=[(price, None, None)], in_stock=False,
                     product_type=Product.Type.DIGITAL if digital else Product.Type.PHYSICAL, **kw)
    v = p.variants.get()
    if stock:
        inv.receive_purchase(v.pk, stock)
    return v


def item(v):
    return InventoryItem.objects.get(variant=v)


def test_receive_purchase_updates_ledger_and_in_stock_flags(django_capture_on_commit_callbacks):
    v = variant()
    assert not v.product.in_stock
    with django_capture_on_commit_callbacks(execute=True):
        inv.receive_purchase(v.pk, 5, ref="PO-1", note="خرید")
    v.refresh_from_db(), v.product.refresh_from_db()
    assert (item(v).on_hand, item(v).available) == (5, 5) and v.is_in_stock and v.product.in_stock
    tx = InventoryTransaction.objects.get()
    assert (tx.type, tx.on_hand_delta, tx.on_hand_after, tx.reference_id) == ("purchase", 5, 5, "PO-1")


def test_adjust_requires_reason_and_cannot_cut_into_reserved_stock():
    v = variant(stock=5)
    with pytest.raises(ValueError):
        inv.adjust(v.pk, -1, note="  ")
    inv.reserve("order:1", [(v.pk, 4)])
    with pytest.raises(inv.InsufficientStock):
        inv.adjust(v.pk, -2, note="شکستگی")  # 5 on hand, 4 reserved -> only 1 free
    inv.adjust(v.pk, -1, note="شکستگی")
    assert (item(v).on_hand, item(v).reserved) == (4, 4)


def test_reserve_is_idempotent_and_records_ledger():
    v = variant(stock=5)
    inv.reserve("order:1", [(v.pk, 2)])
    inv.reserve("order:1", [(v.pk, 2)])  # same call again: no double reservation
    assert (item(v).reserved, StockReservation.objects.count()) == (2, 1)
    assert InventoryTransaction.objects.filter(type="reservation").count() == 1
    with pytest.raises(inv.ReservationConflict):
        inv.reserve("order:1", [(v.pk, 3)])  # same ref, different quantity


def test_reserve_is_all_or_nothing():
    a, b = variant(stock=5, title="a"), variant(stock=1, title="b")
    with pytest.raises(inv.OutOfStock) as e:
        inv.reserve("order:1", [(a.pk, 2), (b.pk, 2)])
    assert e.value.variant_id == b.pk and e.value.available == 1
    assert (item(a).reserved, item(b).reserved, StockReservation.objects.count()) == (0, 0, 0)


def test_last_unit_goes_to_exactly_one_buyer():
    v = variant(stock=1)
    inv.reserve("order:1", [(v.pk, 1)])
    with pytest.raises(inv.OutOfStock):
        inv.reserve("order:2", [(v.pk, 1)])
    v.refresh_from_db()
    assert not v.is_in_stock and item(v).available == 0


def test_digital_products_are_never_reserved():
    v = variant(digital=True)
    assert inv.reserve("order:1", [(v.pk, 3)]) == [] and not InventoryItem.objects.exists()
    assert inv.availability([v.pk]) == {v.pk: None}


def test_inactive_or_unknown_variant_cannot_be_reserved():
    v = variant(stock=2)
    ProductVariant.objects.filter(pk=v.pk).update(is_active=False)
    with pytest.raises(inv.VariantUnavailable):
        inv.reserve("order:1", [(v.pk, 1)])
    with pytest.raises(inv.VariantUnavailable):
        inv.reserve("order:1", [(999_999, 1)])
    with pytest.raises(ValueError):
        inv.reserve("order:1", [(v.pk, 0)])


def test_release_returns_stock_and_is_idempotent():
    v = variant(stock=3)
    inv.reserve("order:1", [(v.pk, 3)])
    v.refresh_from_db()
    assert not v.is_in_stock
    assert inv.release("order:1") == 1 and inv.release("order:1") == 0
    v.refresh_from_db()
    assert item(v).available == 3 and v.is_in_stock
    assert StockReservation.objects.get().status == "released"
    assert InventoryTransaction.objects.filter(type="release").count() == 1


def test_consume_turns_reservation_into_sale_once():
    v = variant(stock=3)
    inv.reserve("order:1", [(v.pk, 2)])
    assert inv.consume("order:1") == 1 and inv.consume("order:1") == 0
    assert (item(v).on_hand, item(v).reserved) == (1, 0)
    sale = InventoryTransaction.objects.get(type="sale")
    assert (sale.on_hand_delta, sale.reserved_delta, sale.on_hand_after) == (-2, -2, 1)
    assert inv.release("order:1") == 0  # a sold reservation can't be released afterwards


def test_expiry_releases_only_overdue_reservations():
    a, b = variant(stock=2, title="a"), variant(stock=2, title="b")
    inv.reserve("order:1", [(a.pk, 1)], ttl_minutes=1)
    inv.reserve("order:2", [(b.pk, 1)], ttl_minutes=60)
    StockReservation.objects.filter(ref="order:1").update(expires_at=timezone.now() - timedelta(seconds=1))
    assert inv.expire_overdue() == ["order:1"]
    assert (item(a).reserved, item(b).reserved) == (0, 1)
    assert StockReservation.objects.get(ref="order:1").status == "expired"
    assert inv.expire_overdue() == []


def test_expiry_task_publishes_event():
    v = variant(stock=2)
    inv.reserve("order:9", [(v.pk, 1)])
    StockReservation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    seen = []
    events.subscribe(events.ReservationsExpired, seen.append)
    assert expire_stock_reservations() == 1
    assert seen[0].refs == ("order:9",)


def test_database_refuses_inconsistent_stock_and_duplicate_ledger_rows():
    v = variant(stock=2)
    with pytest.raises(IntegrityError), transaction.atomic():
        InventoryItem.objects.filter(variant=v).update(reserved=3)  # reserved > on_hand
    inv.reserve("order:1", [(v.pk, 1)])
    with pytest.raises(IntegrityError), transaction.atomic():
        InventoryTransaction.objects.create(item=item(v), type="reservation", on_hand_delta=0, reserved_delta=1,
                                            on_hand_after=2, reserved_after=2, reference_type="order", reference_id="order:1")


def test_availability_and_low_stock():
    a, b = variant(stock=1, title="a"), variant(stock=10, title="b")
    c = variant(title="c")
    assert inv.availability([a.pk, b.pk, c.pk]) == {a.pk: 1, b.pk: 10, c.pk: 0}
    assert [i.variant_id for i in inv.low_stock_items()] == [a.pk]


def test_return_restocks():
    v = variant(stock=1)
    inv.reserve("order:1", [(v.pk, 1)])
    inv.consume("order:1")
    inv.restock_return(v.pk, 1, ref="order:1")
    assert item(v).on_hand == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        InventoryTransaction.objects.create(item=item(v), type="return", on_hand_delta=1, reserved_delta=0,
                                            on_hand_after=2, reserved_after=0, reference_type="return", reference_id="order:1")


@pytest.mark.skipif(connection.vendor != "postgresql", reason="needs real row-level concurrency (run in CI on PostgreSQL)")
@pytest.mark.django_db(transaction=True)
def test_concurrent_buyers_never_oversell_last_unit():
    v = variant(stock=1)
    results = []

    def buy(n):
        try:
            inv.reserve(f"order:{n}", [(v.pk, 1)])
            results.append("ok")
        except inv.OutOfStock:
            results.append("sold-out")
        finally:
            connection.close()

    threads = [threading.Thread(target=buy, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok"] + ["sold-out"] * 7 and item(v).reserved == 1
