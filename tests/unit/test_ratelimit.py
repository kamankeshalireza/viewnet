from django.core.cache import cache

from apps.core import ratelimit


def setup_function():
    cache.clear()


def test_blocks_after_limit_and_hashes_key():
    results = [ratelimit.hit("otp:send", "09123456789", limit=3, window_seconds=60) for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert results[-1].retry_after == 60
    assert not any("09123456789" in k for k in getattr(cache, "_cache", {}))


def test_reset_and_independent_identifiers():
    ratelimit.hit("s", "a", limit=1, window_seconds=60)
    assert not ratelimit.hit("s", "a", limit=1, window_seconds=60).allowed
    assert ratelimit.hit("s", "b", limit=1, window_seconds=60).allowed
    ratelimit.reset("s", "a")
    assert ratelimit.hit("s", "a", limit=1, window_seconds=60).allowed
