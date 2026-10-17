import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_home_renders_rtl_persian_and_no_external_assets(client):
    html = client.get(reverse("catalog:home")).content.decode()
    assert '<html lang="fa" dir="rtl">' in html
    assert "bootstrap.rtl.min.css" in html and "main.rtl.css" in html
    assert "fonts.googleapis.com" not in html and "assets/" not in html
    assert "{%" not in html


@pytest.mark.django_db
def test_health_endpoints_and_404(client):
    assert client.get("/healthz/").status_code == 200
    assert client.get("/readyz/").status_code == 200
    r = client.get("/no-such-page/")
    assert r.status_code == 404 and "۴۰۴" in r.content.decode()


@pytest.mark.django_db
def test_request_id_header(client):
    assert client.get("/healthz/", HTTP_X_REQUEST_ID="abc123")["X-Request-ID"] == "abc123"
