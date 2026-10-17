import pytest

from apps.core.text import mask_phone, normalize_fa, normalize_phone, search_variants, to_ascii_digits


@pytest.mark.parametrize("raw", ["09123456789", "+989123456789", "00989123456789", "9123456789", "۰۹۱۲۳۴۵۶۷۸۹", "0912 345 6789", "0912-345-6789"])
def test_phone_formats(raw):
    assert normalize_phone(raw) == "09123456789"


@pytest.mark.parametrize("raw", ["", None, "0912345", "08123456789", "abc", "0912345678901"])
def test_phone_invalid(raw):
    assert normalize_phone(raw) is None


def test_normalize_fa_arabic_letters_and_diacritics():
    assert normalize_fa("كيف  موبايل") == "کیف موبایل"
    assert normalize_fa("قابٌ") == "قاب"


def test_zwnj_modes_and_variants():
    t = "گوشی\u200cهای هوشمند"
    assert normalize_fa(t, zwnj="space") == "گوشی های هوشمند"
    assert normalize_fa(t, zwnj="remove") == "گوشیهای هوشمند"
    assert "گوشیهای" in search_variants(t) and "گوشی های" in search_variants(t)


def test_digits_and_mask():
    assert to_ascii_digits("۱۲۳٤٥") == "12345"
    assert mask_phone("09123456789") == "0912***789"
