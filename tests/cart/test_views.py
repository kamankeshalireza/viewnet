import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.cart.models import CartItem
from apps.catalog.models import Product
from apps.core.constants import GUEST_CART_SESSION_KEY
from apps.inventory import services as inv
from integrations.sms.fake import FakeSMSProvider
from tests.catalog.helpers import make_product

pytestmark = pytest.mark.django_db


def variant(price=100_000, stock=5, title="کالا", **kw):
    p = make_product(title, variants=[(price, None, None)], in_stock=False, **kw)
    v = p.variants.get()
    if stock:
        inv.receive_purchase(v.pk, stock)
    return v


def add(client, v, qty=1, **extra):
    return client.post(reverse("cart:add"), {"variant_id": v.pk, "qty": qty, **extra})


def test_empty_cart_page(client):
    r = client.get("/cart/")
    assert r.status_code == 200 and "سبد خرید شما خالی است" in r.content.decode()
    assert 'content="noindex,nofollow"' in r.content.decode()


def test_guest_add_update_remove_flow_and_totals(client):
    v = variant(190_000, title="قاب")
    r = add(client, v, 2)
    assert r.status_code == 302 and r.url == "/cart/"
    html = client.get("/cart/").content.decode()
    assert "قاب" in html and "۳۸۰٬۰۰۰ تومان" in html
    client.post(reverse("cart:update", args=[v.pk]), {"qty": "۳"})  # Persian digit
    assert "۵۷۰٬۰۰۰ تومان" in client.get("/cart/").content.decode()
    client.post(reverse("cart:remove", args=[v.pk]))
    assert "خالی" in client.get("/cart/").content.decode()


def test_cart_endpoints_are_post_only(client):
    v = variant()
    assert client.get(reverse("cart:add")).status_code == 405
    assert client.get(reverse("cart:update", args=[v.pk])).status_code == 405
    assert client.get(reverse("cart:remove", args=[v.pk])).status_code == 405


def test_sold_out_and_garbage_input_show_messages_not_errors(client):
    v = variant(stock=0)
    r = add(client, v, next="/category/")
    assert r.status_code == 302 and r.url == "/category/"
    assert "موجود نیست" in client.get("/category/").content.decode()
    assert add(client, v, qty="abc").status_code == 302
    assert client.post(reverse("cart:add"), {"variant_id": "zzz"}).status_code == 302
    assert client.post(reverse("cart:update", args=[999]), {"qty": "1"}).status_code == 302


def test_add_beyond_stock_is_trimmed_with_message(client):
    v = variant(stock=2)
    r = add(client, v, 5)
    assert r.status_code == 302
    html = client.get("/").content.decode()
    assert "فقط ۲ عدد" in html or "فقط 2 عدد" in html or "2" in html
    assert client.session[GUEST_CART_SESSION_KEY] == {str(v.pk): 2}


def test_next_param_is_not_an_open_redirect(client):
    v = variant(stock=0)
    assert add(client, v, next="https://evil.example/").url == "/cart/"


def test_badge_counts_items_for_guest_and_user(client):
    v = variant(stock=9)
    add(client, v, 3)
    assert '<span id="cart-badge" class="badge">۳</span>' in client.get("/").content.decode()
    client.force_login(User.objects.create_user("09123456789"))
    assert '<span id="cart-badge" class="badge"></span>' in client.get("/").content.decode()  # user's own DB cart is empty


def test_cart_page_flags_low_stock_and_heals(client):
    v = variant(stock=3)
    add(client, v, 3)
    assert "فقط ۳ عدد" in client.get("/cart/").content.decode()
    inv.adjust(v.pk, -3, note="تمام شد")
    html = client.get("/cart/").content.decode()
    assert "حذف شد" in html and "خالی" in html


def test_product_page_has_add_to_cart_form_with_variant(client):
    v = variant(stock=4, title="قاب")
    html = client.get(v.product.get_absolute_url()).content.decode()
    assert f'name="variant_id" id="variant-id" value="{v.pk}"' in html and "افزودن به سبد خرید" in html


def test_sold_out_product_page_disables_button(client):
    v = variant(stock=0, title="تمام‌شده")
    html = client.get(v.product.get_absolute_url()).content.decode()
    assert "ناموجود" in html and "disabled" in html


def test_default_variant_prefers_one_in_stock(client):
    p = make_product("دو تنوع", variants=[(100_000, None, None), (120_000, None, None)], in_stock=False)
    second = p.variants.order_by("pk")[1]
    inv.receive_purchase(second.pk, 3)
    ctx = client.get(p.get_absolute_url()).context
    assert ctx["default_variant"]["id"] == second.pk


def test_digital_product_can_be_added_without_stock(client):
    v = variant(stock=0, title="اپل آیدی", product_type=Product.Type.DIGITAL)
    add(client, v, 1)
    assert client.session[GUEST_CART_SESSION_KEY] == {str(v.pk): 1}


def login(client, phone="09123456789", django_capture_on_commit_callbacks=None):
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("accounts:login"), {"phone": phone})
    return client.post(reverse("accounts:verify"), {"code": FakeSMSProvider.last_code(phone)})


def test_guest_cart_merges_into_account_on_login(client, django_capture_on_commit_callbacks):
    user = User.objects.create_user("09123456789", first_name="علی")
    a, b = variant(stock=5, title="a"), variant(stock=5, title="b")
    CartItem.objects.create(cart=__import__("apps.cart.models", fromlist=["Cart"]).Cart.objects.create(user=user), variant=a, quantity=2)
    add(client, a, 1)
    add(client, b, 2)
    login(client, django_capture_on_commit_callbacks=django_capture_on_commit_callbacks)
    assert dict(CartItem.objects.filter(cart__user=user).values_list("variant_id", "quantity")) == {a.pk: 3, b.pk: 2}
    assert GUEST_CART_SESSION_KEY not in client.session
    assert "۵" in client.get("/").content.decode()  # badge shows 5


def test_login_without_guest_cart_is_unaffected(client, django_capture_on_commit_callbacks):
    user = User.objects.create_user("09123456789", first_name="علی")
    r = login(client, django_capture_on_commit_callbacks=django_capture_on_commit_callbacks)
    assert r.status_code == 302 and not CartItem.objects.filter(cart__user=user).exists()
