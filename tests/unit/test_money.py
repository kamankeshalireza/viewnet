import pytest

from apps.core.money import allocate_proportionally, percent_of, rial_to_toman, toman_to_rial


def test_conversion_roundtrip():
    assert toman_to_rial(125_000) == 1_250_000
    assert rial_to_toman(1_250_000) == 125_000


def test_float_rejected():
    with pytest.raises(TypeError):
        toman_to_rial(10.5)
    with pytest.raises(TypeError):
        rial_to_toman(10.5)


def test_percent_rounds_down_to_whole_toman_and_caps():
    assert percent_of(1_234_560, 1000) == 123_450  # 10% = 123456 -> floor to multiple of 10
    assert percent_of(10_000_000, 2000, cap_rial=1_000_000) == 1_000_000


def test_allocate_sum_is_exact():
    parts = allocate_proportionally(1000, [1, 1, 1])
    assert sum(parts) == 1000 and sorted(parts) == [333, 333, 334]
    assert allocate_proportionally(0, [1, 2]) == [0, 0]
    assert allocate_proportionally(10, [0, 0]) == [0, 0]
