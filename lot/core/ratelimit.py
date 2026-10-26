import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache


def client_ip(request):
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def ip_hash(request):
    """Keyed hash of the client IP, so we can rate-limit without storing raw addresses."""
    return hmac.new(settings.SECRET_KEY.encode(), client_ip(request).encode(), hashlib.sha256).hexdigest()[:32]


def too_many(request, scope, limit, window):
    """Count this request against `scope`; True once the client goes over `limit` per `window` seconds.

    Uses the default cache. With several server processes, configure a shared cache (Redis or database)
    so the limit applies across all of them.
    """
    key = f"rl:{scope}:{ip_hash(request)}"
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count > limit
