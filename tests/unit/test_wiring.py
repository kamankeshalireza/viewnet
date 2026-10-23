"""Guards against the bugs found when reviewing the pushed repo."""
import importlib

import pytest
from celery import current_app


def test_celery_app_is_loaded_with_django_project():
    """An empty config/__init__.py silently falls back to Celery's default AMQP app (OTP/image tasks then fail)."""
    config = importlib.import_module("config")
    assert getattr(config, "celery_app", None) is not None
    assert current_app.main == "viewnet" or config.celery_app.main == "viewnet"


def test_development_settings_run_tasks_inline(monkeypatch):
    """Without a worker the OTP code must still be printed to the console in development."""
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("CELERY_EAGER", raising=False)
    dev = importlib.import_module("config.settings.development")
    assert dev.CELERY_TASK_ALWAYS_EAGER is True


@pytest.mark.django_db
def test_otp_request_does_not_need_a_broker(client, django_capture_on_commit_callbacks, settings):
    from integrations.sms.fake import FakeSMSProvider
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post("/account/login/", {"phone": "09123456789"})
    assert r.status_code == 302 and FakeSMSProvider.last_code("09123456789")
