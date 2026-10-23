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


def snapshot() -> dict:  # tests only: keep the app-registered handlers, undo what a test added
    return {k: list(v) for k, v in _handlers.items()}


def restore(saved: dict) -> None:  # tests only
    _handlers.clear()
    for k, v in saved.items():
        _handlers[k] = list(v)


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


@dataclass(frozen=True)
class UserLoggedIn:
    """Published right after login(). `guest_cart` is the session cart captured *before* login."""

    user_id: int
    request: Any
    guest_cart: dict


@dataclass(frozen=True)
class ReservationsExpired:
    refs: tuple


@dataclass(frozen=True)
class OrderPaid:
    order_id: int


@dataclass(frozen=True)
class OrderCancelled:
    order_id: int
    reason: str = ""
