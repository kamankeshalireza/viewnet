"""Order lifecycle (architecture §8.5). Payment state is a separate axis (payments app)."""
from __future__ import annotations

S = {
    "pending": "pending", "awaiting": "awaiting_payment", "paid": "paid", "processing": "processing", "packed": "packed",
    "shipped": "shipped", "delivered": "delivered", "cancelled": "cancelled", "return_requested": "return_requested",
    "returned": "returned", "refunded": "refunded",
}

ALLOWED: dict[str, set[str]] = {
    "pending": {"awaiting_payment", "cancelled"},
    "awaiting_payment": {"paid", "pending", "cancelled"},  # back to pending = payment failed, can retry
    "paid": {"processing", "cancelled"},
    "processing": {"packed", "cancelled"},
    "packed": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": {"return_requested"},
    "return_requested": {"returned", "delivered"},
    "returned": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}
OPEN_UNPAID = {"pending", "awaiting_payment"}


def can_transition(current: str, target: str, *, requires_shipping: bool = True) -> bool:
    if target in ALLOWED.get(current, set()):
        return True
    # Digital orders have nothing to pack or ship: processing can complete directly.
    return (not requires_shipping) and current == "processing" and target == "delivered"
