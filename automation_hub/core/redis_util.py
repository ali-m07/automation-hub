"""
Optional Redis helper for Automation Hub.
When REDIS_URL is set, provides cache get/set and rate limiting.
Moved from top-level redis_util.py into automation_hub.core.
"""

import json
import os
import time
from typing import Any, Optional, Tuple

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def redis_available() -> bool:
    """Return True if Redis is configured and reachable."""
    return _get_redis() is not None


def rate_limit_check(
    key: str,
    limit: int,
    window_seconds: int,
) -> Tuple[bool, int, Optional[int]]:
    """
    Fixed-window rate limit. Returns (allowed, current_count, retry_after_seconds).
    When Redis is unavailable, returns (True, 0, None) so requests are not blocked.
    """
    r = _get_redis()
    if not r:
        return (True, 0, None)
    try:
        full_key = f"rl:{key}"
        pipe = r.pipeline()
        pipe.incr(full_key)
        pipe.ttl(full_key)
        results = pipe.execute()
        count = results[0]
        ttl = results[1]
        if ttl is None or ttl <= 0:
            r.expire(full_key, window_seconds)
            ttl = window_seconds
        if count > limit:
            return (False, count, ttl)
        return (True, count, None)
    except Exception:
        return (True, 0, None)


def cache_get(key: str) -> Optional[Any]:
    """Get value from Redis cache. Returns None if Redis unavailable or key missing."""
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
    """Set value in Redis cache. Returns True on success, False if Redis unavailable."""
    r = _get_redis()
    if not r:
        return False
    try:
        r.set(key, json.dumps(value), ex=ttl_seconds)
        return True
    except Exception:
        return False


def cache_delete(key: str) -> bool:
    """Delete key from Redis. Returns True on success."""
    r = _get_redis()
    if not r:
        return False
    try:
        r.delete(key)
        return True
    except Exception:
        return False
