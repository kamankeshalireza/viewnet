import pytest

from apps.accounts.models import User
from apps.cart import services as cart
from apps.cart.models import CartItem
from apps.cart.stores import DbStore, SessionStore
from apps.catalog.models import Product, ProductVariant
from apps.core.constants import GUEST_CART_SESSION_KEY
from apps.inventory import services as inv
from tests.catalog.helpers import make_product

pytestmark = pytest.mark.django_db


def variant(price=100_000, stock=5, digital=False, title="کالا"):
    p = make_product(title, variants=[(price, None, None)], in_stock=False,
                     product_type=Product.Type.DIGITAL if digital else Product.Type.PHYSICAL)
    v = p.variants.get()
    if stock and not digital:
        inv.receive_purchase(v.pk, stock)
    return v


@pytest.fixture(params=["session", "db"])
def store(request, client):
    if request.param == "session":
        return SessionStore(client.session)
    return DbStore(User.objects.create_user("09123456789"))


def test_add_increments_and_sets(store):
    v = variant()
    assert cart.add_item(store, v.pk, 2).quantity == 2
    assert cart.add_item(store, v.pk, 1).quantity == 3
    assert store.items() == {v.pk: 3}
    assert cart.set_quantity(store, v.pk, 1).quantity == 1
    assert cart.set_quantity(store, v.pk, 0).quantity == 0 and store.items() == {}


def test_max_quantity_per_item(store, settings):
    settings.CART_MAX_QTY_PER_ITEM = 3
    v = variant(stock=50)
    ch = cart.add_item(store, v.pk, 5)
    assert (ch.quantity, ch.reason) == (3, "max_qty") and store.items() == {v.pk: 3}
    assert cart.set_quantity(store, v.pk, 9).reason == "max_qty"


def test_stock_caps_quantity_and_sold_out_is_refused(store):
    v = variant(stock=2)
    ch = cart.add_item(store, v.pk, 5)
    assert (ch.quantity, ch.reason) == (2, "stock")
    sold_out = variant(stock=0, title="x")
    with pytest.raises(cart.OutOfStock):
        cart.add_item(store, sold_out.pk, 1)


def test_reserved_stock_is_not_available_to_the_cart(store):
    v = variant(stock=3)
    inv.reserve("order:1", [(v.pk, 2)])  # someone else is checking out with 2 of them
    assert cart.add_item(store, v.pk, 3).quantity == 1


def test_unavailable_variants_are_rejected(store):
    v = variant()
    ProductVariant.objects.filter(pk=v.pk).update(is_active=False)
    for bad in (v.pk, 999_999):
        with pytest.raises(cart.VariantNotFound):
            cart.add_item(store, bad, 1)
    with pytest.raises(cart.CartError):
        cart.add_item(store, variant().pk, 0)


def test_digital_products_ignore_stock_but_not_max(store, settings):
    settings.CART_MAX_QTY_PER_ITEM = 4
    v = variant(digital=True)
    assert cart.add_item(store, v.pk, 9).quantity == 4


def test_build_cart_prices_are_live_and_totals_correct(store):
    a, b = variant(100_000, title="a"), variant(250_000, title="b")
    cart.add_item(store, a.pk, 2)
    cart.add_item(store, b.pk, 1)
    view = cart.build_cart(store)
    assert [line.total_rial for line in view.lines] == [2_000_000, 2_500_000]
    assert (view.totals.subtotal_rial, view.totals.item_count) == (4_500_000, 3)
    ProductVariant.objects.filter(pk=a.pk).update(price_rial=1_500_000)  # shop changed the price
    assert cart.build_cart(store).totals.subtotal_rial == 2 * 1_500_000 + 2_500_000


def test_cart_heals_itself_when_things_change(store):
    a, b, c = variant(stock=5, title="a"), variant(stock=5, title="b"), variant(stock=5, title="c")
    for v in (a, b, c):
        cart.add_item(store, v.pk, 3)
    ProductVariant.objects.filter(pk=a.pk).update(is_active=False)  # unpublished
    inv.adjust(b.pk, -4, note="شمارش")  # only 1 left
    inv.adjust(c.pk, -5, note="تمام شد")  # none left
    view = cart.build_cart(store)
    assert [(line.variant.pk, line.quantity) for line in view.lines] == [(b.pk, 1)]
    assert len(view.issues) == 3
    assert store.items() == {b.pk: 1}
    assert cart.build_cart(store).issues == []  # healed: nothing to report next time


def test_build_cart_without_fix_does_not_mutate(store):
    v = variant(stock=5)
    cart.add_item(store, v.pk, 3)
    inv.adjust(v.pk, -5, note="تمام")
    assert cart.build_cart(store, fix=False).is_empty and store.items() == {v.pk: 3}


def test_empty_cart():
    class S:
        def items(self): return {}
    assert cart.build_cart(S()).is_empty


def test_session_store_survives_garbage(client):
    s = client.session
    s[GUEST_CART_SESSION_KEY] = {"abc": 1, "5": "x", "7": 2, "8": 0, "9": -1}
    s.save()
    assert SessionStore(client.session).items() == {7: 2}


def test_merge_sums_caps_and_drops_dead_items():
    user = User.objects.create_user("09123456789")
    a, b, dead = variant(stock=4, title="a"), variant(stock=10, title="b"), variant(title="d")
    ProductVariant.objects.filter(pk=dead.pk).update(is_active=False)
    store = DbStore(user)
    cart.add_item(store, a.pk, 3)
    adjusted = cart.merge_guest_into_user(user, {a.pk: 3, b.pk: 2, dead.pk: 1, 999: 1})
    assert store.items() == {a.pk: 4, b.pk: 2}  # a: 3+3 capped by stock 4
    assert adjusted == 3  # a capped, dead and unknown dropped


def test_merge_with_empty_guest_cart_is_a_noop():
    user = User.objects.create_user("09123456789")
    assert cart.merge_guest_into_user(user, {}) == 0 and not CartItem.objects.exists()
