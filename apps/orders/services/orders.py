"""Order lifecycle operations. Every transition: lock the order row, validate, write history, publish an event."""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.events import OrderCancelled, OrderPaid, publish
from apps.discounts import services as coupons
from apps.inventory import services as inventory
from apps.inventory.models import StockReservation

from ..domain.state_machine import OPEN_UNPAID, can_transition
from ..models import Order, OrderStatusHistory

log = logging.getLogger("orders")
Status = Order.Status


class OrderError(Exception):
    pass


class InvalidTransition(OrderError):
    pass


class TransitionNotSupported(OrderError):
    pass


class ReservationLost(OrderError):
    """Payment arrived but the reserved stock is gone (order expired/cancelled). Needs manual review."""


def _lock(order_id: int) -> Order:
    return Order.objects.select_for_update().get(pk=order_id)


def _history(order: Order, from_status: str, to_status: str, actor, reason: str) -> None:
    OrderStatusHistory.objects.create(order=order, from_status=from_status, to_status=to_status, actor=actor, reason=reason[:200])


def transition(order_id: int, to: str, *, actor=None, reason: str = "") -> Order:
    """Move an order along its lifecycle. PAID goes through `mark_paid`; cancelling a paid order needs a refund (Phase 7)."""
    with transaction.atomic():
        order = _lock(order_id)
        current = order.status
        if current == to:
            return order  # idempotent: repeating a transition is harmless
        if to == Status.PAID:
            raise TransitionNotSupported("use mark_paid() — payment must be verified first")
        if not can_transition(current, to, requires_shipping=order.requires_shipping):
            raise InvalidTransition(f"{current} → {to} is not allowed")
        if to == Status.CANCELLED:
            if current not in OPEN_UNPAID:
                raise TransitionNotSupported("لغو سفارش پرداخت‌شده نیازمند بازگشت وجه است (فاز بعد).")
            inventory.release(order.stock_ref)
            coupons.release(order.number)
            order.cancelled_at, order.cancel_reason, order.expires_at = timezone.now(), reason[:200], None
        order.status = to
        order.save(update_fields=["status", "cancelled_at", "cancel_reason", "expires_at", "updated_at"])
        _history(order, current, to, actor, reason)
        if to == Status.CANCELLED:
            transaction.on_commit(lambda: publish(OrderCancelled(order_id=order.pk, reason=reason)))
        return order


def mark_paid(order_id: int, *, actor=None, reason: str = "پرداخت تأیید شد") -> Order:
    """Called by the payment service after the gateway verified the payment. Idempotent."""
    with transaction.atomic():
        order = _lock(order_id)
        if order.status == Status.PAID or order.payment_status == Order.PaymentStatus.PAID:
            return order
        if order.status not in OPEN_UNPAID:
            raise InvalidTransition(f"cannot pay an order in status {order.status}")
        if order.requires_shipping:
            reservations = list(StockReservation.objects.filter(ref=order.stock_ref))
            if not reservations or any(r.status != StockReservation.Status.ACTIVE for r in reservations):
                raise ReservationLost(order.number)
        inventory.consume(order.stock_ref)
        coupons.redeem(order.number)
        for item in order.items.all():
            if item.variant_id:
                Product.objects.filter(variants__pk=item.variant_id).update(sales_count=F("sales_count") + item.quantity)
        previous = order.status
        order.status, order.payment_status = Status.PAID, Order.PaymentStatus.PAID
        order.paid_at, order.expires_at = timezone.now(), None
        order.save(update_fields=["status", "payment_status", "paid_at", "expires_at", "updated_at"])
        _history(order, previous, Status.PAID, actor, reason)
        transaction.on_commit(lambda: publish(OrderPaid(order_id=order.pk)))
        return order


def flag_for_review(order_id: int, reason: str) -> None:
    """e.g. money arrived for an order whose stock was already released."""
    with transaction.atomic():
        order = _lock(order_id)
        order.needs_review = True
        order.save(update_fields=["needs_review", "updated_at"])
        _history(order, order.status, order.status, None, f"نیازمند بررسی: {reason}")


def expire_unpaid(now=None) -> int:
    """Cancel unpaid orders past their payment window. Returns how many were cancelled."""
    count = 0
    for oid in list(Order.objects.filter(status__in=OPEN_UNPAID, expires_at__lt=now or timezone.now()).values_list("pk", flat=True)):
        try:
            transition(oid, Status.CANCELLED, reason="انقضای مهلت پرداخت")
            count += 1
        except OrderError:
            log.exception("could not expire order %s", oid)
    return count


def cancel_by_customer(order: Order, user) -> Order:
    if order.user_id != user.pk:
        raise OrderError("not your order")
    return transition(order.pk, Status.CANCELLED, actor=user, reason="لغو توسط مشتری")
