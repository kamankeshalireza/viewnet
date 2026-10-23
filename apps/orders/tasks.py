from celery import shared_task

from .services import orders


@shared_task(queue="default", ignore_result=True)
def expire_unpaid_orders() -> int:
    return orders.expire_unpaid()
