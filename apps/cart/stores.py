"""Where cart contents live. Guests: the session. Users: the database. Same tiny interface."""
from __future__ import annotations

from typing import Protocol

from django.db import transaction

from apps.core.constants import GUEST_CART_SESSION_KEY

from .models import Cart, CartItem


class CartStore(Protocol):
    def items(self) -> dict[int, int]: ...
    def set_qty(self, variant_id: int, qty: int) -> None: ...  # qty <= 0 removes
    def clear(self) -> None: ...


class SessionStore:
    def __init__(self, session):
        self.session = session

    def items(self) -> dict[int, int]:
        raw = self.session.get(GUEST_CART_SESSION_KEY) or {}
        out: dict[int, int] = {}
        for k, v in raw.items():
            try:
                k, v = int(k), int(v)
            except (TypeError, ValueError):
                continue  # a tampered/old session never crashes the page
            if v > 0:
                out[k] = v
        return out

    def _save(self, items: dict[int, int]) -> None:
        self.session[GUEST_CART_SESSION_KEY] = {str(k): v for k, v in items.items()}
        self.session.modified = True

    def set_qty(self, variant_id: int, qty: int) -> None:
        items = self.items()
        if qty <= 0:
            items.pop(variant_id, None)
        else:
            items[variant_id] = qty
        self._save(items)

    def clear(self) -> None:
        self.session.pop(GUEST_CART_SESSION_KEY, None)
        self.session.modified = True


class DbStore:
    def __init__(self, user):
        self.user = user

    def items(self) -> dict[int, int]:
        return dict(CartItem.objects.filter(cart__user=self.user).order_by("pk").values_list("variant_id", "quantity"))

    def set_qty(self, variant_id: int, qty: int) -> None:
        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(user=self.user)
            if qty <= 0:
                CartItem.objects.filter(cart=cart, variant_id=variant_id).delete()
            else:
                CartItem.objects.update_or_create(cart=cart, variant_id=variant_id, defaults={"quantity": qty})
            cart.save(update_fields=["updated_at"])

    def clear(self) -> None:
        CartItem.objects.filter(cart__user=self.user).delete()


def get_store(request) -> CartStore:
    return DbStore(request.user) if request.user.is_authenticated else SessionStore(request.session)
