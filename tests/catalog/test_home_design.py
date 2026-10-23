import pytest

from apps.catalog.templatetags.catalog_extras import category_icon

from .helpers import make_brand, make_category, make_device, make_product

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("name,icon", [("قاب گوشی", "bi-phone"), ("گلس", "bi-shield-check"), ("کابل", "bi-usb-plug"),
                                       ("شارژر", "bi-lightning-charge"), ("ایرپاد", "bi-earbuds"), ("فندکی ماشین", "bi-car-front"),
                                       ("پاوربانک", "bi-battery-charging"), ("اپل آیدی", "bi-apple"), ("چیز دیگر", "bi-grid"), ("", "bi-grid")])
def test_category_icons(name, icon):
    assert category_icon(name) == icon


def test_home_has_phone_finder_grouped_by_brand(client):
    apple = make_brand()
    dm = make_device(apple, "iPhone 15")
    make_product("قاب", category=make_category("قاب گوشی"), variants=[(100_000, dm, None)])
    html = client.get("/").content.decode()
    assert 'name="device"' in html and '<optgroup label="اپل">' in html and f'value="{dm.slug}"' in html
    assert f"/category/?device={dm.slug}" in html  # quick chips


def test_home_hides_empty_sections_gracefully(client):
    html = client.get("/").content.decode()
    assert "هنوز محصولی ثبت نشده" in html and "محصولات ویژه" not in html


@pytest.mark.parametrize("url", ["/", "/category/", "/search/?q=قاب"])
def test_product_cards_are_inside_the_template_style_scope(client, url):
    """The template only styles .product-card inside .category-product-list; without it cards look broken."""
    make_product("قاب سیلیکونی", is_featured=True)
    html = client.get(url).content.decode()
    assert 'class="product-card"' in html and "category-product-list" in html


def test_detail_and_wishlist_cards_are_scoped_too(client, django_user_model):
    cat = make_category("قاب")
    a, b = make_product("الف", category=cat), make_product("ب", category=cat)
    assert "category-product-list" in client.get(a.get_absolute_url()).content.decode()
    from apps.catalog.models import WishlistItem
    u = django_user_model.objects.create_user("09123456789")
    WishlistItem.objects.create(user=u, product=b)
    client.force_login(u)
    assert "category-product-list" in client.get("/account/wishlist/").content.decode()
