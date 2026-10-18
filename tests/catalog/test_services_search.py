import pytest

from apps.catalog import services
from apps.catalog.models import Product
from apps.catalog.search.backend import SimpleSearchBackend, normalize_query

from .helpers import make_brand, make_category, make_color, make_device, make_product

pytestmark = pytest.mark.django_db


def test_recalc_prices_compare_and_stock():
    p = make_product(variants=[(100_000, None, None, 150_000), (250_000, None, None)])
    assert (p.min_price_rial, p.max_price_rial, p.compare_at_min_rial) == (1_000_000, 2_500_000, 1_500_000)
    assert p.in_stock and p.discount_percent == 34 and p.has_price_range


def test_inactive_variants_are_ignored_and_empty_product_is_not_in_stock():
    p = make_product(variants=[(100_000, None, None), (50_000, None, None)])
    p.variants.filter(price_rial=500_000).update(is_active=False)
    services.recalc_product(p.pk)
    p.refresh_from_db()
    assert p.min_price_rial == p.max_price_rial == 1_000_000
    p.variants.update(is_active=False)
    services.recalc_product(p.pk)
    p.refresh_from_db()
    assert not p.in_stock and p.min_price_rial == 0


def test_digital_product_does_not_require_shipping():
    p = make_product("ساخت اپل آیدی", product_type=Product.Type.DIGITAL)
    assert not p.requires_shipping
    assert make_product("کابل").requires_shipping


def test_normalize_query_handles_arabic_letters_digits_zwnj_and_case():
    assert normalize_query("  كيف  ۱۵ iPhone ") == ["کیف", "15", "iphone"]
    assert normalize_query("گوشی\u200cهای") == ["گوشی", "های"]
    assert normalize_query("") == [] and normalize_query(None) == []


def test_search_matches_aliases_models_brand_category_and_sku():
    apple = make_brand(aliases="اپل apple آیفون iphone")
    dm = make_device(apple, "iPhone 15", aliases="ایفون ۱۵ آیفون 15")
    color = make_color()
    p = make_product("قاب سیلیکونی", category=make_category("قاب گوشی"), brand=apple, variants=[(100_000, dm, [color])])
    make_product("کابل شارژ")
    be = SimpleSearchBackend()
    qs = Product.objects.all()
    for q in ["iphone", "آیفون ۱۵", "ایفون 15", "قاب", "اپل", "مشکی", p.variants.first().sku.lower(), "قاب آیفون"]:
        assert list(be.apply(qs, q)) == [p], q
    assert list(be.apply(qs, "گلس")) == []
    assert list(be.apply(qs, "   ")) == []


def test_all_tokens_must_match_and_title_hits_rank_first():
    cat = make_category("لوازم")
    a = make_product("شارژر فندکی", category=cat)
    b = make_product("کابل", category=make_category("شارژر"))  # 'شارژر' only via category
    ids = [p.pk for p in SimpleSearchBackend().apply(Product.objects.all(), "شارژر").order_by("search_rank", "pk")]
    assert ids == [a.pk, b.pk]
    assert list(SimpleSearchBackend().apply(Product.objects.all(), "شارژر کابل")) == [b]


def test_search_text_has_zwnj_both_forms():
    p = make_product("گوشی\u200cهای شیک")
    assert "گوشی های" in p.search_text and "گوشیهای" in p.search_text


def test_reindex_after_brand_rename():
    apple = make_brand(aliases="oldalias")
    p = make_product("قاب", brand=apple)
    assert "oldalias" in p.search_text
    apple.search_aliases = "newalias"
    apple.save()
    services.reindex_for(brand=apple)
    p.refresh_from_db()
    assert "newalias" in p.search_text and "oldalias" not in p.search_text
