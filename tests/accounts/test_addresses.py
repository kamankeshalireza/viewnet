import pytest
from django.urls import reverse

from apps.accounts.models import Address, User
from apps.locations.models import City, Province

pytestmark = pytest.mark.django_db


@pytest.fixture
def places(db):
    tehran = Province.objects.create(name="تهران", slug="tehran")
    fars = Province.objects.create(name="فارس", slug="fars")
    return {"tehran": tehran, "fars": fars, "tehran_city": City.objects.create(province=tehran, name="تهران", slug="tehran"),
            "shiraz": City.objects.create(province=fars, name="شیراز", slug="shiraz")}


@pytest.fixture
def logged(client):
    user = User.objects.create_user("09123456789", first_name="علی", last_name="رضایی")
    client.force_login(user)
    return user


def form(places, **kw):
    data = {"receiver_name": "علی رضایی", "receiver_phone": "۰۹۱۲۳۴۵۶۷۸۹", "province": places["tehran"].pk, "city": places["tehran_city"].pk,
            "address_line": "خیابان ولیعصر", "plaque": "۱۲", "unit": "۳", "postal_code": "۱۲۳۴۵۶۷۸۹۰"}
    data.update(kw)
    return data


def test_pages_require_login(client, places):
    for url in ("addresses", "address_new", "address_cities"):
        assert client.get(reverse(f"accounts:{url}")).status_code == 302


def test_create_normalizes_input_and_first_address_becomes_default(client, logged, places):
    r = client.post(reverse("accounts:address_new"), form(places))
    assert r.status_code == 302
    a = Address.objects.get()
    assert (a.receiver_phone, a.postal_code, a.is_default, a.user) == ("09123456789", "1234567890", True, logged)
    assert "ولیعصر" in client.get(reverse("accounts:addresses")).content.decode()


def test_only_one_default_and_switching(client, logged, places):
    client.post(reverse("accounts:address_new"), form(places))
    client.post(reverse("accounts:address_new"), form(places, address_line="دوم", is_default="on"))
    assert list(Address.objects.filter(is_default=True).values_list("address_line", flat=True)) == ["دوم"]
    first = Address.objects.get(address_line="خیابان ولیعصر")
    client.post(reverse("accounts:address_default", args=[first.pk]))
    assert list(Address.objects.filter(is_default=True)) == [first]


@pytest.mark.parametrize("bad,field", [({"postal_code": "123"}, "postal_code"), ({"postal_code": "12345abcde"}, "postal_code"),
                                         ({"receiver_phone": "123"}, "receiver_phone"), ({"address_line": ""}, "address_line")])
def test_validation_errors_keep_the_form(client, logged, places, bad, field):
    r = client.post(reverse("accounts:address_new"), form(places, **bad))
    assert r.status_code == 200 and field in r.context["form"].errors and not Address.objects.exists()


def test_city_must_belong_to_province(client, logged, places):
    r = client.post(reverse("accounts:address_new"), form(places, city=places["shiraz"].pk))
    assert r.status_code == 200 and "city" in r.context["form"].errors


def test_cities_endpoint_returns_only_that_provinces_options(client, logged, places):
    html = client.get(reverse("accounts:address_cities"), {"province": places["fars"].pk}).content.decode()
    assert "شیراز" in html and "تهران" not in html
    assert "<option" in client.get(reverse("accounts:address_cities"), {"province": "x"}).content.decode()


def test_cannot_touch_other_users_addresses(client, logged, places):
    other = User.objects.create_user("09120000009")
    a = Address.objects.create(user=other, province=places["tehran"], city=places["tehran_city"], address_line="x", postal_code="1234567890",
                               receiver_name="r", receiver_phone="09120000009")
    for name in ("address_edit", "address_delete", "address_default"):
        assert client.post(reverse(f"accounts:{name}", args=[a.pk]), form(places)).status_code == 404
    assert client.get(reverse("accounts:address_edit", args=[a.pk])).status_code == 404


def test_delete_is_soft_and_hides_the_address(client, logged, places):
    client.post(reverse("accounts:address_new"), form(places))
    a = Address.objects.get()
    client.post(reverse("accounts:address_delete", args=[a.pk]))
    a.refresh_from_db()
    assert a.is_deleted and not a.is_default
    assert "ولیعصر" not in client.get(reverse("accounts:addresses")).content.decode()
    assert client.get(reverse("accounts:address_edit", args=[a.pk])).status_code == 404


def test_next_param_redirects_back_to_checkout_but_not_off_site(client, logged, places):
    r = client.post(reverse("accounts:address_new"), form(places, next="/checkout/"))
    assert r.url == "/checkout/"
    r = client.post(reverse("accounts:address_new"), form(places, next="https://evil.example/"))
    assert r.url == reverse("accounts:addresses")
