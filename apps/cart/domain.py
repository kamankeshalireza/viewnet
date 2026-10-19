"""Pure cart math (no DB). The same functions are reused by checkout in Phase 5."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineInput:
    unit_price_rial: int
    quantity: int

    @property
    def total_rial(self) -> int:
        return self.unit_price_rial * self.quantity


@dataclass(frozen=True)
class Totals:
    subtotal_rial: int
    item_count: int


def cart_totals(lines: list[LineInput]) -> Totals:
    return Totals(subtotal_rial=sum(line.total_rial for line in lines), item_count=sum(line.quantity for line in lines))
