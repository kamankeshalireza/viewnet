"""Pure discount math (no DB)."""
from apps.core.money import percent_of


def compute_discount(*, kind: str, percent: int | None, amount_rial: int | None, max_discount_rial: int | None, subtotal_rial: int) -> int:
    if kind == "percent":
        value = percent_of(subtotal_rial, (percent or 0) * 100, cap_rial=max_discount_rial)
    else:
        value = amount_rial or 0
        if max_discount_rial is not None:
            value = min(value, max_discount_rial)
    return max(min(value, subtotal_rial), 0)  # never more than the goods are worth
