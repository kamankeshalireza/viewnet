"""Fixed-window rate limiter on Django's cache (Redis in production)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.core.cache import cache


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    retry_after: int


def key_hash(value: str) -> str:
    """Hash identifiers (phone, ip) so raw PII never lands in cache keys."""
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def hit(scope: str, identifier: str, *, limit: int, window_seconds: int) -> RateLimitResult:
    """Count one attempt. Atomic: cache.add creates the key with TTL, incr is atomic on Redis."""
    key = f"rl:{scope}:{key_hash(identifier)}"
    if cache.add(key, 1, timeout=window_seconds):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:  # key expired between add() and incr()
            cache.add(key, 1, timeout=window_seconds)
            count = 1
    return RateLimitResult(count <= limit, count, limit, window_seconds if count > limit else 0)


def reset(scope: str, identifier: str) -> None:
    cache.delete(f"rl:{scope}:{key_hash(identifier)}")
