from django.test import RequestFactory

from apps.core.http import get_client_ip


def req(xff=None, addr="10.0.0.1"):
    return RequestFactory().get("/", HTTP_X_FORWARDED_FOR=xff, REMOTE_ADDR=addr) if xff else RequestFactory().get("/", REMOTE_ADDR=addr)


def test_no_proxy_ignores_forged_header(settings):
    settings.NUM_PROXIES = 0
    assert get_client_ip(req("6.6.6.6")) == "10.0.0.1"


def test_one_proxy_uses_last_entry_not_client_forged_first(settings):
    settings.NUM_PROXIES = 1
    assert get_client_ip(req("6.6.6.6, 203.0.113.7")) == "203.0.113.7"


def test_falls_back_when_header_too_short(settings):
    settings.NUM_PROXIES = 2
    assert get_client_ip(req("203.0.113.7")) == "10.0.0.1"
