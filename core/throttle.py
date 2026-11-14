"""Small cache-based rate limiter used on sign-in and one-time-code views."""
from django.core.cache import cache


def hit(key, limit, window_seconds):
    """Count one attempt. Return True if the caller is now over the limit."""
    full = f"throttle:{key}"
    added = cache.add(full, 1, window_seconds)
    count = 1 if added else cache.incr(full)
    return count > limit


def blocked(key, limit):
    return (cache.get(f"throttle:{key}") or 0) >= limit


def reset(key):
    cache.delete(f"throttle:{key}")
