import pytest

from apps.core import events


@pytest.fixture(autouse=True)
def _isolate_events():
    yield
    events.clear_handlers()
