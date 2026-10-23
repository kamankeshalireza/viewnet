import re

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.discounts.models import Coupon
from apps.inventory.models import InventoryItem
from apps.orders.models import Order
from apps.shipping.models import ShippingMethod

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(client, user, address, make_variant, fill_cart):
    client.force_login(user)
    v = make_variant(190_000, stock=5, title="قاب")
    fill_cart((v, 2))
    return client, v


def token(html):
    return re.search(r'name="token" value="([0-9a-f-]{36})"', html).group(1)


def submit(client, html, **extra):
    data = {"token": token(html), "accept_terms": "1", "address_id": extra.pop("address_id", ""), "shipping_code": "free"}
    data.update(extra)
    return client.post(reverse("orders:place"), data)


def test_checkout_requires_login_and_a_cart(client, user):
    assert client.get(reverse("orders:checkout")).url.startswith("/account/login/")
    client.force_login(user)
    r = client.get(reverse("orders:checkout"))
    assert r.status_code == 302 and r.url == reverse("cart:detail")


def test_checkout_page_shows_address_free_shipping_and_totals(shop, address):
    client, _ = shop
    html = client.get(reverse("orders:checkout")).content.decode()
    assert "ولیعصر" in html and "ارسال رایگان" in html and "۳۸۰٬۰۰۰ تومان" in html
    assert f'value="{address.pk}"' in html and 'name="accept_terms"' in html


def test_checkout_without_address_prompts_to_add_one(client, user, make_variant, fill_cart):
    client.force_login(user)
    fill_cart((make_variant(stock=2), 1))
    html = client.get(reverse("orders:checkout")).content.decode()
    assert "نشانی جدید" in html and "disabled" in html


def test_full_flow_places_order_and_shows_it(shop, address):
    client, v = shop
    html = client.get(reverse("orders:checkout")).content.decode()
    r = submit(client, html, address_id=address.pk, note="سلام")
    order = Order.objects.get()
    assert r.status_code == 302 and r.url == f"/orders/{order.number}/"
    page = client.get(r.url).content.decode()
    assert "در انتظار پرداخت" in page and "قاب" in page and "۳۸۰٬۰۰۰ تومان" in page and "لغو سفارش" in page
    assert InventoryItem.objects.get(variant=v).reserved == 2
    assert "خالی" in client.get(reverse("cart:detail")).content.decode()  # cart emptied


def test_double_submit_creates_one_order(shop, address):
    client, _ = shop
    html = client.get(reverse("orders:checkout")).content.decode()
    r1 = submit(client, html, address_id=address.pk)
    r2 = submit(client, html, address_id=address.pk)  # same token again
    assert Order.objects.count() == 1 and r1.url == r2.url


def test_terms_and_token_are_enforced(shop, address):
    client, _ = shop
    html = client.get(reverse("orders:checkout")).content.decode()
    r = client.post(reverse("orders:place"), {"token": token(html), "address_id": address.pk})
    assert r.url == reverse("orders:checkout") and not Order.objects.exists()
    r = client.post(reverse("orders:place"), {"token": "not-a-uuid", "accept_terms": "1", "address_id": address.pk})
    assert r.url == reverse("orders:checkout") and not Order.objects.exists()


def test_coupon_apply_show_discount_and_remove(shop, address):
    client, _ = shop
    Coupon.objects.create(code="OFF10", kind="percent", percent=10)
    client.post(reverse("orders:coupon"), {"code": "off10"})
    html = client.get(reverse("orders:checkout")).content.decode()
    assert "تخفیف (OFF10)" in html and "۳۴۲٬۰۰۰ تومان" in html
    submit(client, html, address_id=address.pk)
    order = Order.objects.get()
    assert order.coupon_discount_rial == 380_000 and order.total_rial == 3_420_000
    assert "checkout_coupon" not in client.session  # consumed
    client.post(reverse("orders:coupon"), {"code": "NOPE"})
    assert "checkout_coupon" not in client.session


def test_coupon_removal(shop):
    client, _ = shop
    Coupon.objects.create(code="OFF10", kind="percent", percent=10)
    client.post(reverse("orders:coupon"), {"code": "OFF10"})
    assert client.session["checkout_coupon"] == "OFF10"
    client.post(reverse("orders:coupon"), {"remove": "1"})
    assert "checkout_coupon" not in client.session


def test_order_pages_are_private_to_the_owner(shop, address):
    client, _ = shop
    submit(client, client.get(reverse("orders:checkout")).content.decode(), address_id=address.pk)
    order = Order.objects.get()
    other = User.objects.create_user("09120000009")
    client.force_login(other)
    assert client.get(order.get_absolute_url()).status_code == 404
    assert client.post(reverse("orders:cancel", args=[order.number])).status_code == 404
    assert order.number not in client.get(reverse("orders:list")).content.decode()
    client.logout()
    assert client.get(order.get_absolute_url()).status_code == 302


def test_customer_can_cancel_unpaid_order_and_stock_returns(shop, address):
    client, v = shop
    submit(client, client.get(reverse("orders:checkout")).content.decode(), address_id=address.pk)
    order = Order.objects.get()
    client.post(reverse("orders:cancel", args=[order.number]))
    order.refresh_from_db()
    assert order.status == "cancelled" and InventoryItem.objects.get(variant=v).reserved == 0
    assert "لغو شده" in client.get(order.get_absolute_url()).content.decode()


def test_order_list_and_paid_order_has_no_cancel_button(shop, address):
    client, _ = shop
    submit(client, client.get(reverse("orders:checkout")).content.decode(), address_id=address.pk)
    order = Order.objects.get()
    from apps.core.templatetags.core_tags import fa_digits
    assert fa_digits(order.number) in client.get(reverse("orders:list")).content.decode()
    from apps.orders.services import orders as svc
    svc.mark_paid(order.pk)
    page = client.get(order.get_absolute_url()).content.decode()
    assert "لغو سفارش" not in page and "پرداخت‌شده" in page


def test_paid_order_cannot_be_cancelled_by_customer(shop, address):
    client, _ = shop
    submit(client, client.get(reverse("orders:checkout")).content.decode(), address_id=address.pk)
    order = Order.objects.get()
    from apps.orders.services import orders as svc
    svc.mark_paid(order.pk)
    client.post(reverse("orders:cancel", args=[order.number]))
    order.refresh_from_db()
    assert order.status == "paid"


def test_shipping_method_is_free_by_default_and_methods_only_for_physical(db):
    assert list(ShippingMethod.objects.values_list("code", "price_rial")) == [("free", 0)]
    from apps.shipping import services as shipping
    assert shipping.available_methods(False) == [] and len(shipping.available_methods(True)) == 1
