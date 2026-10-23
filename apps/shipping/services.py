from __future__ import annotations

from .models import ShippingMethod


def available_methods(requires_shipping: bool) -> list[ShippingMethod]:
    """Orders made only of digital goods (e.g. Apple ID) need no shipping at all."""
    if not requires_shipping:
        return []
    return list(ShippingMethod.objects.filter(is_active=True))


def quote(method: ShippingMethod) -> int:
    """Shipping price in Rial. Free for everyone today (all methods are priced 0)."""
    return method.price_rial
