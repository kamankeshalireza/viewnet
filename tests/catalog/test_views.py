from urllib.parse import unquote

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import WishlistItem

from .helpers import make_brand, make_category, make_color, make_device, make_product

pytestmark = pytest.mark.django_db


def cards(resp):
    return resp.content.decode().count('class="product-card"')


def test_home_renders_with_dynamic_nav_and_sections(client):
    cat = make_category("قاب گوشی")
    make_product("قاب ویژه", category=cat, is_featured=True)
    html = client.get("/").content.decode()
    assert "قاب گوشی" in html and "قاب ویژه" in html and "جدیدترین محصولات" in html
    assert 'action="/search/"' in html and "NiceShop" not in html and "FashionStore" not in html


def test_category_page_and_404_for_unknown_or_inactive(client):
    root = make_category("قاب گوشی")
    sub = make_category("قاب آیفون", parent=root)
    make_product("a", category=sub)
    r = client.get(sub.get_absolute_url())
    assert r.status_code == 200 and cards(r) == 1
    assert cards(client.get(root.get_absolute_url())) == 1  # parent includes descendants
    assert "قاب آیفون" in client.get(root.get_absolute_url()).content.decode()  # subcategory link
    assert client.get("/category/nope/").status_code == 404
    make_category("مخفی", is_active=False)
    assert client.get("/category/مخفی/").status_code == 404


def test_listing_filters_via_query_string_and_noindex_rules(client):
    apple = make_brand()
    cat = make_category("قاب")
    make_product("اپلی", category=cat, brand=apple)
    make_product("بی‌نام", category=cat)
    plain = client.get(cat.get_absolute_url())
    assert cards(plain) == 2 and "noindex" not in plain.content.decode()
    f = client.get(cat.get_absolute_url(), {"brand": "apple"})
    assert cards(f) == 1 and 'content="noindex,follow"' in f.content.decode()
    assert 'content="noindex,follow"' in client.get(cat.get_absolute_url(), {"sort": "cheapest"}).content.decode()


def test_pagination(client):
    cat = make_category("قاب")
    for i in range(14):
        make_product(f"p{i}", category=cat)
    assert cards(client.get(cat.get_absolute_url())) == 12
    p2 = client.get(cat.get_absolute_url(), {"page": 2})
    assert cards(p2) == 2 and "page=1" in p2.content.decode()
    assert cards(client.get(cat.get_absolute_url(), {"page": 999})) == 2  # out of range -> last page


def test_search_page(client):
    make_product("قاب سیلیکونی")
    r = client.get("/search/", {"q": "قاب"})
    assert cards(r) == 1 and 'content="noindex,follow"' in r.content.decode()
    assert "پیدا نشد" in client.get("/search/", {"q": "هیچی"}).content.decode()
    assert cards(client.get("/search/")) == 0


def test_product_page_and_canonical_redirect(client):
    apple = make_brand()
    dm = make_device(apple, "iPhone 15")
    color = make_color()
    p = make_product("قاب سیلیکونی", brand=apple, variants=[(190_000, dm, [color], 250_000)], description="<p>سلام</p><script>x()</script>")
    r = client.get(p.get_absolute_url())
    html = r.content.decode()
    assert r.status_code == 200 and "۱۹۰٬۰۰۰ تومان" in html and "variants-data" in html and 'data-axis="device"' in html
    assert "<script>x()" not in html and "سلام" in html
    moved = client.get(f"/product/{p.pk}/old-slug/")
    assert moved.status_code == 301 and unquote(moved.url) == p.get_absolute_url()
    assert client.get(f"/product/{p.pk}/").status_code == 301
    p.is_active = False
    p.save()
    assert client.get(p.get_absolute_url()).status_code == 404


def test_variant_payload_shape(client):
    apple = make_brand()
    a, b = make_device(apple, "iPhone 15"), make_device(apple, "iPhone 14")
    black, white = make_color(), make_color("white", "سفید", "#fff")
    p = make_product("قاب", variants=[(100_000, a, [black]), (100_000, a, [white]), (90_000, b, [black])])
    ctx = client.get(p.get_absolute_url()).context
    payload = ctx["variants_payload"]
    assert [ax["label"] for ax in payload["axes"]] == ["مدل گوشی", "رنگ"]
    assert len(payload["variants"]) == 3 and all(set(v["axes"]) == {"device", f"attr{black.definition_id}"} for v in payload["variants"])
    assert ctx["default_variant"]["id"] == p.variants.get(is_default=True).pk


def test_digital_product_page_shows_no_shipping_badge(client):
    from apps.catalog.models import Product
    p = make_product("ساخت اپل آیدی", product_type=Product.Type.DIGITAL)
    assert "تحویل غیرحضوری" in client.get(p.get_absolute_url()).content.decode()


def test_wishlist_requires_login_and_toggles(client):
    p = make_product("قاب")
    r = client.post(reverse("catalog:wishlist_toggle", args=[p.pk]), {"next": "/category/"})
    assert r.status_code == 302 and r.url.startswith("/account/login/") and WishlistItem.objects.count() == 0
    user = User.objects.create_user("09123456789")
    client.force_login(user)
    r = client.post(reverse("catalog:wishlist_toggle", args=[p.pk]), {"next": "/category/"})
    assert r.url == "/category/" and WishlistItem.objects.filter(user=user, product=p).exists()
    assert cards(client.get(reverse("catalog:wishlist"))) == 1
    client.post(reverse("catalog:wishlist_toggle", args=[p.pk]))
    assert not WishlistItem.objects.exists()
    assert client.get(reverse("catalog:wishlist")).status_code == 200


def test_wishlist_next_is_not_an_open_redirect(client):
    p = make_product("قاب")
    client.force_login(User.objects.create_user("09123456789"))
    r = client.post(reverse("catalog:wishlist_toggle", args=[p.pk]), {"next": "https://evil.example/x"})
    assert r.url == "/"


def test_wishlist_page_requires_login_and_toggle_is_post_only(client):
    assert client.get(reverse("catalog:wishlist")).status_code == 302
    assert client.get(reverse("catalog:wishlist_toggle", args=[1])).status_code == 405


def test_favicon_redirects_to_static(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 301 and r.url.endswith("img/favicon.png")
