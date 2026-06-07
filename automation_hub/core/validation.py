"""Validation and rate limiting utilities."""

from fastapi import HTTPException, Request

from automation_hub.core.settings import get_upload_limits

try:
    from automation_hub.core.redis_util import redis_available, rate_limit_check
except ImportError:

    def redis_available() -> bool:
        return False

    def rate_limit_check(key: str, limit: int, window_seconds: int):
        return (True, 0, None)


def check_upload_size(request: Request) -> None:
    """Raise 413 if request body exceeds admin-configured max upload size."""
    max_bytes, _ = get_upload_limits()
    cl = request.headers.get("content-length")
    if cl and int(cl) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413, detail=f"File too large. Maximum size is {mb} MB."
        )


def rate_limit_abort(
    request: Request, scope: str, identifier: str, limit: int, window_seconds: int = 60
) -> None:
    """If Redis is available and limit exceeded, raise HTTP 429. identifier is e.g. IP or username."""
    if not redis_available():
        return
    key = f"{scope}:{identifier}"
    allowed, count, retry_after = rate_limit_check(key, limit, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry_after or 60)},
        )
