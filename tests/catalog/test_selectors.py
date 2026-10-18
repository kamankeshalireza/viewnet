import pytest

from apps.catalog import selectors
from apps.catalog.models import ProductAttributeValue

from .helpers import make_brand, make_category, make_color, make_device, make_product

pytestmark = pytest.mark.django_db


def ids(params=None, category=None, **kw):
    params = params or selectors.ListingParams(**kw)
    return [p.pk for p in selectors.listing_queryset(params, category)]


def test_params_parse_persian_digits_and_reject_bad_sort():
    from django.http import QueryDict

    p = selectors.ListingParams.from_request(QueryDict("min_price=۱۰۰۰&max_price=abc&sort=hax&page=۲&opt=3&opt=x&in_stock=1"))
    assert (p.min_toman, p.max_toman, p.page, p.options, p.in_stock, p.sort) == (1000, None, 2, [3], True, "newest")
    assert selectors.ListingParams.from_request(QueryDict("q=قاب")).sort == "relevance"


def test_only_active_products_in_active_categories_are_listed():
    cat = make_category("الف")
    shown = make_product("الف", category=cat)
    make_product("مخفی", category=cat, active=False)
    make_product("در دستهٔ مخفی", category=make_category("ب", is_active=False))
    assert ids() == [shown.pk]


def test_category_includes_descendants():
    root = make_category("قاب")
    sub = make_category("آیفون", parent=root)
    other = make_category("گلس")
    a, b, c = make_product("a", category=root), make_product("b", category=sub), make_product("c", category=other)
    assert set(ids(category=root)) == {a.pk, b.pk} and ids(category=sub) == [b.pk] and ids(category=other) == [c.pk]


def test_brand_device_price_stock_filters():
    apple, samsung = make_brand(), make_brand("سامسونگ", "Samsung")
    i15, s24 = make_device(apple, "iPhone 15"), make_device(samsung, "Galaxy S24")
    a = make_product("a", brand=apple, variants=[(100_000, i15, None)])
    b = make_product("b", brand=samsung, variants=[(300_000, s24, None)])
    assert ids(brands=["apple"]) == [a.pk] and ids(brands=["samsung"]) == [b.pk]
    assert ids(devices=[i15.slug]) == [a.pk] and ids(devices=[s24.slug]) == [b.pk]
    assert ids(min_toman=200_000) == [b.pk] and ids(max_toman=200_000) == [a.pk] and set(ids(min_toman=100_000, max_toman=300_000)) == {a.pk, b.pk}
    b.variants.update(is_active=False)
    from apps.catalog import services
    services.recalc_product(b.pk)
    assert ids(in_stock=True) == [a.pk]


def test_inactive_variant_does_not_match_device_filter():
    apple = make_brand()
    dm = make_device(apple, "iPhone 15")
    p = make_product("a", variants=[(100_000, dm, None)])
    p.variants.update(is_active=False)
    assert ids(devices=[dm.slug]) == []


def test_option_filter_via_variant_and_via_product_attribute_without_duplicates():
    black, white = make_color(), make_color("white", "سفید", "#fff")
    a = make_product("a", variants=[(1000, None, [black]), (2000, None, [black])])
    b = make_product("b")
    ProductAttributeValue.objects.create(product=b, option=white)
    make_product("c", variants=[(1000, None, [white])])
    assert ids(options=[black.pk]) == [a.pk]  # distinct even with 2 matching variants
    assert len(ids(options=[white.pk])) == 2
    assert len(ids(options=[black.pk, white.pk])) == 3


def test_sorting():
    cat = make_category("x")
    cheap, mid, dear = (make_product(t, category=cat, variants=[(p, None, None)]) for t, p in (("cheap", 10_000), ("mid", 50_000), ("dear", 90_000)))
    from apps.catalog.models import Product
    Product.objects.filter(pk=mid.pk).update(sales_count=9)
    assert ids(sort="cheapest") == [cheap.pk, mid.pk, dear.pk]
    assert ids(sort="expensive") == [dear.pk, mid.pk, cheap.pk]
    assert ids(sort="bestseller")[0] == mid.pk
    assert ids(sort="newest")[0] == dear.pk


def test_facets_scoped_to_category_with_counts():
    apple = make_brand()
    dm = make_device(apple, "iPhone 15")
    black = make_color()
    cat, other = make_category("قاب"), make_category("کابل")
    make_product("a", category=cat, brand=apple, variants=[(100_000, dm, [black]), (120_000, dm, [black])])
    make_product("b", category=other, brand=make_brand("سامسونگ", "Samsung"))
    f = selectors.listing_facets(cat)
    assert [(b.name, b.n) for b in f["brands"]] == [("اپل", 1)]
    assert [(d.name, d.n) for d in f["devices"]] == [("iPhone 15", 1)]
    assert [(o.label, o.n) for g in f["option_groups"] for o in g["options"]] == [("مشکی", 1)]
    assert f["price"]["lo"] == 1_000_000
    assert len(selectors.listing_facets(None)["brands"]) == 2


def test_listing_uses_constant_number_of_queries(django_assert_max_num_queries):
    cat = make_category("x")
    for i in range(6):
        make_product(f"p{i}", category=cat, brand=make_brand(f"b{i}", f"B{i}"))
    with django_assert_max_num_queries(4):
        for p in selectors.listing_queryset(selectors.ListingParams(), cat):
            _ = (p.category.name, p.brand.name, p.primary_image)


def test_home_sections():
    p = make_product("ویژه", is_featured=True)
    s = selectors.home_sections()
    assert [x.pk for x in s["featured_products"]] == [p.pk] and s["bestsellers"] == [] and len(s["new_products"]) == 1
