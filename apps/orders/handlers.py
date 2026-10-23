import logging

from apps.core.events import ReservationsExpired

from .models import Order
from .services import orders

log = logging.getLogger("orders")


def on_reservations_expired(event: ReservationsExpired) -> None:
    """Stock holds that timed out belong to unpaid orders: cancel them (stock is already back on the shelf)."""
    for ref in event.refs:
        if not ref.startswith("order:"):
            continue
        order = Order.objects.filter(number=ref.split(":", 1)[1]).first()
        if order and order.is_unpaid_open:
            try:
                orders.transition(order.pk, Order.Status.CANCELLED, reason="انقضای مهلت پرداخت")
            except orders.OrderError:
                log.exception("expire handler failed for %s", ref)
