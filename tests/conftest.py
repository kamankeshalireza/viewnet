import pytest
from django.core.cache import cache

from apps.core import events
from integrations.sms.fake import FakeSMSProvider


@pytest.fixture(autouse=True)
def _isolate():
    cache.clear()
    FakeSMSProvider.reset()
    yield
    events.clear_handlers()
