"""Tiny explicit in-process event dispatcher (instead of implicit ORM signals)."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)


def subscribe(event_type: type, handler: Callable[[Any], None]) -> None:
    if handler not in _handlers[event_type]:
        _handlers[event_type].append(handler)


def publish(event: Any) -> None:
    """Handlers must only enqueue work (via transaction.on_commit); never do I/O inline."""
    for handler in list(_handlers[type(event)]):
        handler(event)


def clear_handlers() -> None:  # tests only
    _handlers.clear()


@dataclass(frozen=True)
class UserRegistered:
    user_id: int


@dataclass(frozen=True)
class OrderCreated:
    order_id: int


@dataclass(frozen=True)
class PaymentSucceeded:
    order_id: int
    payment_id: int


@dataclass(frozen=True)
class PaymentFailed:
    order_id: int
    payment_id: int
