import pytest
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_admin_pages_load_for_superuser(client, settings):
    su = User.objects.create_superuser("09121112244", "s3cret-Passw0rd")
    client.force_login(su)
    prefix = settings.ADMIN_URL_PREFIX
    for path in ("", "accounts/user/", "accounts/user/add/", "accounts/otpchallenge/", "accounts/address/", "core/sitesetting/"):
        assert client.get(f"/{prefix}/{path}").status_code == 200, path
    assert reverse("accounts:login")
