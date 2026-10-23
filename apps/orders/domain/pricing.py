"""Order totals (pure). total = subtotal - discount + shipping + tax."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderTotals:
    subtotal_rial: int
    coupon_discount_rial: int
    shipping_rial: int
    tax_rial: int

    @property
    def total_rial(self) -> int:
        return self.subtotal_rial - self.coupon_discount_rial + self.shipping_rial + self.tax_rial


def compute_totals(*, subtotal_rial: int, coupon_discount_rial: int = 0, shipping_rial: int = 0, tax_rial: int = 0) -> OrderTotals:
    if min(subtotal_rial, coupon_discount_rial, shipping_rial, tax_rial) < 0:
        raise ValueError("amounts must not be negative")
    return OrderTotals(subtotal_rial, min(coupon_discount_rial, subtotal_rial), shipping_rial, tax_rial)
