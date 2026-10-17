from datetime import UTC, datetime

from django.template import Context, Template


def render(src, **ctx):
    return Template(src).render(Context(ctx))


def test_toman_filter():
    assert render("{{ v|toman }}", v=12_500_000) == "۱٬۲۵۰٬۰۰۰ تومان"
    assert render("{{ v|toman:False }}", v=10) == "۱"


def test_jalali_filter_uses_tehran_time():
    dt = datetime(2026, 3, 21, 0, 0, tzinfo=UTC)  # 1 Farvardin 1405, 03:30 Tehran
    assert render("{{ d|jalali }}", d=dt) == "۱۴۰۵/۰۱/۰۱"


def test_fa_digits():
    assert render("{{ v|fa_digits }}", v="a12") == "a۱۲"
