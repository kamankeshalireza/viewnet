"""Money helpers. Internal unit is integer RIAL; 1 Toman = 10 Rial. Never use float for money."""
from __future__ import annotations

RIAL_PER_TOMAN = 10


def toman_to_rial(toman: int) -> int:
    if isinstance(toman, float):
        raise TypeError("float is not allowed for money")
    return int(toman) * RIAL_PER_TOMAN


def rial_to_toman(rial: int) -> int:
    """Floor division: callers must keep prices as multiples of 10 rial."""
    if isinstance(rial, float):
        raise TypeError("float is not allowed for money")
    return int(rial) // RIAL_PER_TOMAN


def percent_of(amount_rial: int, basis_points: int, cap_rial: int | None = None) -> int:
    """Discount = floor(amount * bp / 10000), rounded down to a whole toman, optionally capped."""
    value = (amount_rial * basis_points) // 10_000
    value -= value % RIAL_PER_TOMAN
    if cap_rial is not None:
        value = min(value, cap_rial)
    return value


def allocate_proportionally(total_rial: int, weights: list[int]) -> list[int]:
    """Split `total_rial` across weights with the largest-remainder method (sum is exact)."""
    s = sum(weights)
    if s <= 0 or total_rial <= 0:
        return [0] * len(weights)
    shares = [total_rial * w // s for w in weights]
    remainders = sorted(range(len(weights)), key=lambda i: (total_rial * weights[i]) % s, reverse=True)
    for i in remainders[: total_rial - sum(shares)]:
        shares[i] += 1
    return shares
