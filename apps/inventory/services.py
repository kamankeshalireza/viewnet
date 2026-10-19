"""Stock rules (architecture §11). All mutations are atomic, idempotent and recorded in the ledger.

Reserve uses a conditional UPDATE (`WHERE on_hand - reserved >= qty`) so two buyers racing for the last
unit can never both succeed; the CHECK constraint is the last line of defence.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog import services as catalog_services
from apps.catalog.models import Product, ProductVariant

from .models import InventoryItem, InventoryTransaction, StockReservation

log = logging.getLogger("inventory")
T = InventoryTransaction.Type


class StockError(Exception):
    pass


class OutOfStock(StockError):
    def __init__(self, variant_id: int, available: int):
        super().__init__(f"variant {variant_id}: only {available} available")
        self.variant_id, self.available = variant_id, available


class InsufficientStock(StockError):
    """An adjustment would push on_hand below what is already reserved/in stock."""


class VariantUnavailable(StockError):
    pass


class ReservationConflict(StockError):
    pass


def is_tracked(variant: ProductVariant) -> bool:
    """Digital products (e.g. Apple ID) have no physical stock."""
    return variant.product.product_type == Product.Type.PHYSICAL


def ensure_item(variant_id: int) -> InventoryItem:
    try:
        return InventoryItem.objects.get(variant_id=variant_id)
    except InventoryItem.DoesNotExist:
        try:
            with transaction.atomic():
                return InventoryItem.objects.create(variant_id=variant_id)
        except IntegrityError:  # created concurrently
            return InventoryItem.objects.get(variant_id=variant_id)


def availability(variant_ids) -> dict[int, int | None]:
    """available quantity per variant; None = untracked (unlimited, e.g. digital)."""
    ids = list(variant_ids)
    out: dict[int, int | None] = {}
    tracked = {v.pk: v for v in ProductVariant.objects.filter(pk__in=ids).select_related("product")}
    stock = {i.variant_id: i.available for i in InventoryItem.objects.filter(variant_id__in=ids)}
    for vid in ids:
        v = tracked.get(vid)
        if v is None:
            continue
        out[vid] = stock.get(vid, 0) if is_tracked(v) else None
    return out


def _record(item, type_, on_hand_delta, reserved_delta, *, ref_type="", ref_id="", actor=None, note=""):
    item.refresh_from_db(fields=["on_hand", "reserved"])  # we still hold the row lock from our UPDATE
    InventoryTransaction.objects.create(
        item=item, type=type_, on_hand_delta=on_hand_delta, reserved_delta=reserved_delta,
        on_hand_after=item.on_hand, reserved_after=item.reserved, reference_type=ref_type,
        reference_id=str(ref_id), actor=actor, note=note,
    )


def _sync_flags(variant_ids) -> None:
    """Keep ProductVariant.is_in_stock (and the product's flag) in step with available stock."""
    changed_products = set()
    for item in InventoryItem.objects.filter(variant_id__in=set(variant_ids)).select_related("variant"):
        flag = item.available > 0
        if item.variant.is_in_stock != flag:
            ProductVariant.objects.filter(pk=item.variant_id).update(is_in_stock=flag)
            changed_products.add(item.variant.product_id)
    for pid in changed_products:
        transaction.on_commit(lambda pid=pid: catalog_services.recalc_product(pid))


# ---- adjustments -------------------------------------------------------------------------------------
def _change_on_hand(variant_id: int, delta: int, type_: str, *, ref_type="", ref_id="", actor=None, note=""):
    if delta == 0:
        raise ValueError("delta must not be 0")
    with transaction.atomic():
        item = ensure_item(variant_id)
        if delta > 0:
            InventoryItem.objects.filter(pk=item.pk).update(on_hand=F("on_hand") + delta)
        else:
            rows = InventoryItem.objects.filter(pk=item.pk, on_hand__gte=F("reserved") - delta).update(on_hand=F("on_hand") + delta)
            if rows == 0:
                item.refresh_from_db()
                raise InsufficientStock(f"on_hand={item.on_hand}, reserved={item.reserved}, requested {delta}")
        _record(item, type_, delta, 0, ref_type=ref_type, ref_id=ref_id, actor=actor, note=note)
        _sync_flags([variant_id])
        return InventoryItem.objects.get(pk=item.pk)


def receive_purchase(variant_id: int, qty: int, *, ref="", actor=None, note=""):
    if qty <= 0:
        raise ValueError("qty must be positive")
    return _change_on_hand(variant_id, qty, T.PURCHASE, ref_type="purchase" if ref else "", ref_id=ref, actor=actor, note=note)


def restock_return(variant_id: int, qty: int, *, ref: str, actor=None):
    if qty <= 0:
        raise ValueError("qty must be positive")
    return _change_on_hand(variant_id, qty, T.RETURN, ref_type="return", ref_id=ref, actor=actor)


def adjust(variant_id: int, delta: int, *, note: str, actor=None):
    """Manual correction (stock-take, damage). A reason is mandatory."""
    if not note.strip():
        raise ValueError("a reason (note) is required for manual adjustments")
    return _change_on_hand(variant_id, delta, T.ADJUSTMENT, actor=actor, note=note.strip())


# ---- reservations ------------------------------------------------------------------------------------
def reserve(ref: str, lines, *, ttl_minutes: int | None = None) -> list[StockReservation]:
    """Reserve [(variant_id, qty), ...] for `ref` (e.g. 'order:12'). All-or-nothing and idempotent per (ref, variant)."""
    merged: dict[int, int] = defaultdict(int)
    for vid, qty in lines:
        if qty <= 0:
            raise ValueError("qty must be positive")
        merged[int(vid)] += int(qty)
    expires = timezone.now() + timedelta(minutes=ttl_minutes or settings.STOCK_RESERVATION_TTL_MINUTES)
    made: list[StockReservation] = []
    with transaction.atomic():
        variants = ProductVariant.objects.select_related("product").in_bulk(merged)
        for vid in sorted(merged):  # fixed lock order => no deadlocks between concurrent orders
            qty, variant = merged[vid], variants.get(vid)
            if variant is None or not variant.is_active:
                raise VariantUnavailable(vid)
            if not is_tracked(variant):
                continue
            existing = StockReservation.objects.select_for_update().filter(ref=ref, variant_id=vid).first()
            if existing:
                if existing.status != StockReservation.Status.ACTIVE or existing.quantity != qty:
                    raise ReservationConflict(f"{ref}/{vid} already {existing.status} x{existing.quantity}")
                made.append(existing)
                continue
            item = ensure_item(vid)
            rows = InventoryItem.objects.filter(pk=item.pk, on_hand__gte=F("reserved") + qty).update(reserved=F("reserved") + qty)
            if rows == 0:
                item.refresh_from_db()
                raise OutOfStock(vid, max(item.available, 0))
            made.append(StockReservation.objects.create(ref=ref, variant_id=vid, quantity=qty, expires_at=expires))
            _record(item, T.RESERVATION, 0, qty, ref_type="order", ref_id=ref)
        _sync_flags(merged)
    return made


def _close(ref_filter: dict, new_status: str, ledger_type: str, *, consume: bool) -> list[StockReservation]:
    done = []
    with transaction.atomic():
        rows = list(StockReservation.objects.select_for_update().filter(status=StockReservation.Status.ACTIVE, **ref_filter)
                    .order_by("variant_id", "pk"))
        for r in rows:
            item = ensure_item(r.variant_id)
            if consume:
                InventoryItem.objects.filter(pk=item.pk).update(on_hand=F("on_hand") - r.quantity, reserved=F("reserved") - r.quantity)
                _record(item, ledger_type, -r.quantity, -r.quantity, ref_type="order", ref_id=r.ref)
            else:
                InventoryItem.objects.filter(pk=item.pk).update(reserved=F("reserved") - r.quantity)
                _record(item, ledger_type, 0, -r.quantity, ref_type="order", ref_id=r.ref)
            r.status = new_status
            r.save(update_fields=["status", "updated_at"])
            done.append(r)
        _sync_flags([r.variant_id for r in done])
    return done


def release(ref: str) -> int:
    """Give reserved stock back (payment failed / order cancelled). Safe to call repeatedly."""
    return len(_close({"ref": ref}, StockReservation.Status.RELEASED, T.RELEASE, consume=False))


def consume(ref: str) -> int:
    """Payment succeeded: reserved stock becomes a sale. Safe to call repeatedly."""
    return len(_close({"ref": ref}, StockReservation.Status.CONSUMED, T.SALE, consume=True))


def expire_overdue(now=None) -> list[str]:
    """Release reservations past their TTL. Returns the affected refs so orders can be cancelled."""
    done = _close({"expires_at__lt": now or timezone.now()}, StockReservation.Status.EXPIRED, T.RELEASE, consume=False)
    return sorted({r.ref for r in done})


def reservations_for(ref: str):
    return StockReservation.objects.filter(ref=ref)


def low_stock_items():
    return InventoryItem.objects.filter(on_hand__lte=F("reserved") + F("low_stock_threshold")).select_related("variant__product")
