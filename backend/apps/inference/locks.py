"""Cross-process device locks — never hit a single-threaded model/device with
more than one request at a time (PRD 12: "one model per device at a time").

The Celery worker runs several slots and the Studio fans many segments out at
once, so without coordination N requests could land on (say) the single Dia
server simultaneously and overwhelm it. These locks serialize access *per
device*: a request waits its turn, then runs — i.e. a queue.

Backed by Redis (shared by the web process and every worker). The key mirrors
the capacity grouping the async-job dispatcher uses in ``jobs.py``: a provider's
GPU ``resource_group`` when set (so e.g. tts + asr sharing one box serialize
together), else the provider + service type. Without Redis configured the lock
degrades to a no-op so local/test runs keep working (they just don't serialize).
"""
import logging
from contextlib import contextmanager

from django.conf import settings

logger = logging.getLogger("django")

_client = None
_client_ready = False


def _redis():
    global _client, _client_ready
    if _client_ready:
        return _client
    _client_ready = True
    url = getattr(settings, "DEVICE_LOCK_REDIS_URL", "") or ""
    if not url:
        return None
    try:
        import redis

        _client = redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)
    except Exception:
        logger.warning("device_lock: Redis unavailable; locks are no-ops", exc_info=True)
        _client = None
    return _client


def provider_device_key(provider_model) -> str:
    """A stable lock key for the *device* behind a deployment. Shares one key
    across the service types in a GPU resource group, else keys per provider +
    service type — the same grouping ``jobs._resolve_capacity`` schedules on."""
    if provider_model is None:
        return ""
    provider = provider_model.provider
    svc = getattr(provider_model, "service", None)
    group = ((getattr(svc, "resource_group", "") or "").strip()) if svc else ""
    if group:
        return f"device:{provider.id}:{group}"
    stype = (getattr(svc, "service_type", "") or "") if svc else ""
    return f"device:{provider.id}:{stype or 'default'}"


@contextmanager
def device_lock(key, *, blocking_timeout=None, ttl=None, on_acquire=None):
    """Hold the device ``key`` for the duration of the block so only one request
    runs against that model/device at a time; concurrent callers wait their turn
    and then proceed (a queue).

    ``on_acquire`` (if given) is called the instant the lock is actually held —
    after any wait — which is the moment work truly starts on the device (used to
    flip a "queued" segment to "generating"). ``ttl`` auto-expires the lock if a
    holder dies, so a crash never deadlocks the device. ``blocking_timeout`` caps
    the wait (None waits indefinitely). Yields True if held; False only if it
    gave up waiting. No-ops (yields True, fires ``on_acquire``) without Redis."""
    def _fire():
        if on_acquire:
            try:
                on_acquire()
            except Exception:
                logger.warning("device_lock: on_acquire callback failed for %s", key, exc_info=True)

    client = _redis()
    if client is None or not key:
        _fire()
        yield True
        return
    ttl = ttl or getattr(settings, "DEVICE_LOCK_DEFAULT_TTL", 900)
    lock = client.lock(f"lock:{key}", timeout=ttl, blocking=True, blocking_timeout=blocking_timeout)
    acquired = False
    try:
        try:
            acquired = lock.acquire()
        except Exception:
            # Redis hiccup mid-acquire — don't wedge the pipeline; run unlocked.
            logger.warning("device_lock: acquire failed for %s; proceeding", key, exc_info=True)
            _fire()
            yield True
            return
        if not acquired:
            logger.warning("device_lock: timed out waiting for %s", key)
        else:
            _fire()
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                logger.warning("device_lock: release failed for %s", key, exc_info=True)
