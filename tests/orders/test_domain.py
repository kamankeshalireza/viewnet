import pytest

from apps.discounts.domain import compute_discount
from apps.orders.domain.pricing import compute_totals
from apps.orders.domain.state_machine import ALLOWED, can_transition


def test_happy_path_is_allowed_and_skipping_steps_is_not():
    path = ["pending", "awaiting_payment", "paid", "processing", "packed", "shipped", "delivered"]
    assert all(can_transition(a, b) for a, b in zip(path, path[1:], strict=False))
    assert not can_transition("pending", "shipped") and not can_transition("paid", "delivered")
    assert not can_transition("cancelled", "pending") and not can_transition("refunded", "paid")


def test_failed_payment_can_retry_and_returns_flow():
    assert can_transition("awaiting_payment", "pending")
    assert can_transition("delivered", "return_requested") and can_transition("returned", "refunded")


def test_digital_orders_skip_packing_and_shipping():
    assert can_transition("processing", "delivered", requires_shipping=False)
    assert not can_transition("processing", "delivered", requires_shipping=True)


def test_every_state_is_covered_and_terminal_states_have_no_exits():
    assert ALLOWED["cancelled"] == set() and ALLOWED["refunded"] == set()
    assert all(t in ALLOWED for targets in ALLOWED.values() for t in targets)


def test_totals_formula_and_discount_never_exceeds_subtotal():
    t = compute_totals(subtotal_rial=1_000_000, coupon_discount_rial=2_000_000, shipping_rial=50_000, tax_rial=10_000)
    assert (t.coupon_discount_rial, t.total_rial) == (1_000_000, 60_000)
    with pytest.raises(ValueError):
        compute_totals(subtotal_rial=-1)


@pytest.mark.parametrize("kind,percent,amount,cap,sub,expected", [
    ("percent", 10, None, None, 1_234_560, 123_450),          # floor to a whole toman
    ("percent", 20, None, 1_000_000, 10_000_000, 1_000_000),  # capped
    ("fixed", None, 500_000, None, 2_000_000, 500_000),
    ("fixed", None, 5_000_000, None, 2_000_000, 2_000_000),   # fixed bigger than the goods
    ("fixed", None, 500_000, 300_000, 2_000_000, 300_000),
    ("percent", 100, None, None, 0, 0),
])
def test_discount_math(kind, percent, amount, cap, sub, expected):
    assert compute_discount(kind=kind, percent=percent, amount_rial=amount, max_discount_rial=cap, subtotal_rial=sub) == expected
