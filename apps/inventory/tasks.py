import logging

from celery import shared_task

from apps.core.events import ReservationsExpired, publish

from . import services

log = logging.getLogger("inventory")


@shared_task(queue="default", ignore_result=True)
def expire_stock_reservations() -> int:
    refs = services.expire_overdue()
    if refs:
        log.info("expired reservations for %s", refs)
        publish(ReservationsExpired(refs=tuple(refs)))  # orders (Phase 5) cancel the matching unpaid orders
    return len(refs)
