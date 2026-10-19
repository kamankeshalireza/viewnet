import pytest

from apps.accounts.models import User
from apps.inventory.models import InventoryItem, InventoryTransaction
from tests.catalog.helpers import make_product

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client, settings):
    client.force_login(User.objects.create_superuser("09121112244", "s3cret-Passw0rd"))
    return client, f"/{settings.ADMIN_URL_PREFIX}/inventory"


def test_pages_load(admin_client):
    c, base = admin_client
    for m in ("inventoryitem", "inventorytransaction", "stockreservation"):
        assert c.get(f"{base}/{m}/").status_code == 200
    assert c.get(f"{base}/inventoryitem/add/").status_code == 200
    assert c.get(f"{base}/inventorytransaction/add/").status_code == 403  # ledger is append-only via services


def test_add_stock_then_adjust_through_admin_writes_ledger(admin_client):
    c, base = admin_client
    v = make_product("x", in_stock=False).variants.get()
    r = c.post(f"{base}/inventoryitem/add/", {"variant": v.pk, "low_stock_threshold": 2, "delta": 7, "note": "ورود اولیه"})
    assert r.status_code == 302
    item = InventoryItem.objects.get(variant=v)
    assert item.on_hand == 7 and InventoryTransaction.objects.get().type == "purchase"
    r = c.post(f"{base}/inventoryitem/{item.pk}/change/", {"variant": v.pk, "low_stock_threshold": 2, "delta": -2, "note": "شکسته"})
    item.refresh_from_db()
    assert item.on_hand == 5 and InventoryTransaction.objects.filter(type="adjustment", note="شکسته").exists()


def test_admin_requires_reason_for_stock_change(admin_client):
    c, base = admin_client
    v = make_product("x", in_stock=False).variants.get()
    r = c.post(f"{base}/inventoryitem/add/", {"variant": v.pk, "low_stock_threshold": 2, "delta": 3, "note": ""})
    assert r.status_code == 200 and not InventoryItem.objects.exists()


def test_seed_demo_stock_is_idempotent_and_leaves_second_variant_sold_out(settings, tmp_path):
    from django.core.management import call_command

    from apps.catalog.models import ProductVariant
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_catalog", "--demo", verbosity=0)
    call_command("seed_demo_stock", verbosity=0)
    first = InventoryItem.objects.count()
    call_command("seed_demo_stock", verbosity=0)
    assert first > 0 and InventoryItem.objects.count() == first
    case = ProductVariant.objects.filter(product__title__startswith="قاب سیلیکونی").order_by("position", "pk")
    assert [v.is_in_stock for v in case] == [True, False, True, True]
