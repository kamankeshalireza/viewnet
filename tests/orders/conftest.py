import pytest

from apps.accounts.models import Address, User
from apps.cart.stores import DbStore
from apps.catalog.models import Product
from apps.inventory import services as inv
from apps.locations.models import City, Province
from tests.catalog.helpers import make_product


@pytest.fixture
def user(db):
    return User.objects.create_user("09123456789", first_name="علی", last_name="رضایی")


@pytest.fixture
def city(db):
    p = Province.objects.create(name="تهران", slug="tehran")
    return City.objects.create(province=p, name="تهران", slug="tehran")


@pytest.fixture
def address(user, city):
    return Address.objects.create(user=user, province=city.province, city=city, address_line="خیابان ولیعصر", plaque="12", unit="3",
                                  postal_code="1234567890", receiver_name="علی رضایی", receiver_phone="09123456789", is_default=True)


@pytest.fixture
def make_variant(db):
    n = {"i": 0}

    def _make(price_toman=100_000, stock=10, digital=False, title=None):
        n["i"] += 1
        p = make_product(title or f"کالا {n['i']}", variants=[(price_toman, None, None)], in_stock=False,
                         product_type=Product.Type.DIGITAL if digital else Product.Type.PHYSICAL)
        v = p.variants.get()
        if stock and not digital:
            inv.receive_purchase(v.pk, stock)
        return v
    return _make


@pytest.fixture
def fill_cart(user):
    def _fill(*pairs):
        store = DbStore(user)
        for variant, qty in pairs:
            store.set_qty(variant.pk, qty)
        return store
    return _fill
