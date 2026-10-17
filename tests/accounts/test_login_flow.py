import pytest
from django.urls import reverse

from apps.accounts.models import User
from integrations.sms.fake import FakeSMSProvider

pytestmark = pytest.mark.django_db
PHONE = "09123456789"


def start(client, phone=PHONE, **extra):
    return client.post(reverse("accounts:login"), {"phone": phone, **extra})


def test_full_flow_creates_user_and_logs_in(client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        r = start(client, "۰۹۱۲۳۴۵۶۷۸۹")  # Persian digits accepted
    assert r.status_code == 302 and r.url == reverse("accounts:verify")
    code = FakeSMSProvider.last_code(PHONE)
    old_key = client.session.session_key
    r = client.post(reverse("accounts:verify"), {"code": code})
    assert r.status_code == 302 and reverse("accounts:profile") in r.url  # new user -> complete profile
    assert User.objects.get(phone=PHONE).phone_verified_at
    assert client.session.session_key != old_key  # session cycled
    assert not User.objects.get(phone=PHONE).has_usable_password()


def test_existing_user_goes_to_next(client, django_capture_on_commit_callbacks):
    User.objects.create_user(PHONE, first_name="علی")
    with django_capture_on_commit_callbacks(execute=True):
        start(client, next="/cart/")
    r = client.post(reverse("accounts:verify"), {"code": FakeSMSProvider.last_code(PHONE)})
    assert r.url == "/cart/"


def test_open_redirect_is_blocked(client, django_capture_on_commit_callbacks):
    User.objects.create_user(PHONE, first_name="علی")
    with django_capture_on_commit_callbacks(execute=True):
        start(client, next="https://evil.example/steal")
    r = client.post(reverse("accounts:verify"), {"code": FakeSMSProvider.last_code(PHONE)})
    assert r.url == "/"


def test_known_and_unknown_numbers_are_indistinguishable(client, django_capture_on_commit_callbacks, client_class=None):
    from django.test import Client
    User.objects.create_user(PHONE)
    c2 = Client()
    with django_capture_on_commit_callbacks(execute=True):
        r1 = start(client, PHONE)
        r2 = start(c2, "09350000000")
    assert (r1.status_code, r1.url) == (r2.status_code, r2.url)
    assert [str(m) for m in r1.wsgi_request._messages] == [str(m) for m in r2.wsgi_request._messages]


def test_invalid_phone_shows_form_error(client):
    r = start(client, "123")
    assert r.status_code == 200 and "شمارهٔ موبایل را به‌صورت صحیح" in r.content.decode()


def test_wrong_code_stays_on_page(client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        start(client)
    r = client.post(reverse("accounts:verify"), {"code": "000000" if FakeSMSProvider.last_code(PHONE) != "000000" else "111111"})
    assert r.status_code == 200 and "صحیح نیست" in r.content.decode()
    assert "_auth_user_id" not in client.session


def test_verify_without_session_redirects_to_login(client):
    assert client.get(reverse("accounts:verify")).url == reverse("accounts:login")


def test_inactive_user_cannot_login(client, django_capture_on_commit_callbacks):
    User.objects.create_user(PHONE, is_active=False)
    with django_capture_on_commit_callbacks(execute=True):
        start(client)
    client.post(reverse("accounts:verify"), {"code": FakeSMSProvider.last_code(PHONE)})
    assert "_auth_user_id" not in client.session


def test_profile_requires_login_and_logout_is_post_only(client):
    assert client.get(reverse("accounts:profile")).status_code == 302
    assert client.get(reverse("accounts:logout")).status_code == 405


def test_profile_update(client):
    u = User.objects.create_user(PHONE)
    client.force_login(u)
    r = client.post(reverse("accounts:profile"), {"first_name": "علی", "last_name": "رضایی", "email": "a@b.ir"})
    assert r.status_code == 302
    u.refresh_from_db()
    assert u.get_full_name() == "علی رضایی"
