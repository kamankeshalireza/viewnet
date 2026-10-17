import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import Address, User
from apps.accounts.services.addresses import set_default_address
from apps.locations.models import City, Province

pytestmark = pytest.mark.django_db


def test_user_manager_normalizes_and_validates():
    assert User.objects.create_user("+989121112233").phone == "09121112233"
    with pytest.raises(ValueError):
        User.objects.create_user("123")
    with pytest.raises(ValueError):
        User.objects.create_superuser("09121112244")  # admins need a password
    assert User.objects.create_superuser("09121112244", "s3cret-Passw0rd").is_staff


def test_db_rejects_bad_phone_and_duplicate_email():
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(phone="12345")])
    User.objects.create_user("09121112233", email="x@y.ir")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("09121112234", email="x@y.ir")
    User.objects.create_user("09121112235")  # blank emails may repeat
    User.objects.create_user("09121112236")


def _addr(user, city, **kw):
    return Address.objects.create(user=user, province=city.province, city=city, address_line="x",
                                  postal_code="1234567890", receiver_name="r", receiver_phone="09121112233", **kw)


def test_single_default_address_enforced_in_db_and_service():
    p = Province.objects.create(name="تهران", slug="tehran")
    c = City.objects.create(province=p, name="تهران", slug="tehran")
    u = User.objects.create_user("09121112233")
    a1, a2 = _addr(u, c, is_default=True), _addr(u, c)
    with pytest.raises(IntegrityError), transaction.atomic():
        Address.objects.filter(pk=a2.pk).update(is_default=True)
    set_default_address(a2)
    a1.refresh_from_db()
    assert not a1.is_default and Address.objects.get(pk=a2.pk).is_default


def test_postal_code_check_constraint():
    p = Province.objects.create(name="تهران", slug="tehran")
    c = City.objects.create(province=p, name="تهران", slug="tehran")
    u = User.objects.create_user("09121112233")
    with pytest.raises(IntegrityError), transaction.atomic():
        Address.objects.create(user=u, province=p, city=c, address_line="x", postal_code="12ab",
                               receiver_name="r", receiver_phone="09121112233")
