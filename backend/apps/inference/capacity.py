"""One capacity budget per device, shared by every path that can hit a GPU.

Each provider service declares ``max_concurrent`` (manifest
``services[].max_concurrent``, default 1) and may join a shared GPU
``resource_group`` with its own ``max_concurrent``. Before this module only the
async dispatcher honored those numbers — and it only counted *async* jobs — so
synchronous ``/v1`` calls, playground-agent tool calls and in-place retries
could pile any number of requests onto a single-slot device.

Now there is one ledger: ``InferenceRequest`` rows in ``PROCESSING``.

- Async jobs count while PROCESSING (the reaper reclaims dead ones).
- Synchronous requests count while PROCESSING *if they were admitted here*
  (``job_service_type`` set) and started within ``SYNC_SLOT_STALE_SECONDS`` —
  the bound keeps a crashed web worker from leaking a slot forever.

Check-and-claim happens under a single Postgres advisory transaction lock, so
two concurrent callers (sync views, the dispatcher, agent tools) can never both
see a free slot and both take it. The lock is held only for the count + insert
(milliseconds), never for the inference itself.

LLM services are exempt on the synchronous path by default
(``CAPACITY_EXEMPT_SERVICE_TYPES``): vLLM / LM Studio / NIM schedule concurrent
requests internally (continuous batching) and a chat stream can last minutes,
so serializing them here would only add latency. Async LLM jobs still respect
``max_concurrent`` via the dispatcher.
"""
import logging
import time
from contextlib import contextmanager

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger("django")

# Arbitrary, stable id for the Postgres advisory lock guarding the ledger.
_ADVISORY_LOCK_ID = 7_301_955_221

# Request-level async modes (the ``async`` body field).
MODE_SYNC = "sync"
MODE_ASYNC = "async"
MODE_AUTO = "auto"


def norm_type(service_type) -> str:
    """Normalize a service type for ledger keys: the LLM path is stored as ""
    on jobs but declared as "llm" on manifest services — treat them as one."""
    return service_type or "llm"


def exempt(service_type) -> bool:
    return norm_type(service_type) in set(getattr(settings, "CAPACITY_EXEMPT_SERVICE_TYPES", ("llm",)))


@contextmanager
def ledger_lock():
    """Serialize capacity check+claim across processes. Call inside
    ``transaction.atomic()``; released at commit. No-op off Postgres (tests on
    SQLite are single-writer anyway)."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", [_ADVISORY_LOCK_ID])
    yield


# --- liveness leases for synchronous slots ----------------------------------
#
# A sync request runs inside a web worker. If that worker dies mid-request
# (deploy, OOM, gunicorn restart, dev autoreload) its row stays PROCESSING and,
# without a liveness signal, would hold the device's slot until the stale
# window. So every admitted sync request holds a short-TTL lease key in the
# shared cache, refreshed by a heartbeat thread while it runs; the ledger only
# counts sync rows whose lease is alive. A dead process stops heartbeating and
# frees the slot within LEASE_TTL. Needs a shared cache (Redis); with a
# per-process cache we fall back to the stale window alone.

import threading

LEASE_TTL = 45
LEASE_REFRESH = 15


def _lease_key(ir_id):
    return f"ic:slot:{ir_id}"


def leases_enabled() -> bool:
    backend = (settings.CACHES.get("default") or {}).get("BACKEND", "")
    return "redis" in backend.lower() or getattr(settings, "CAPACITY_FORCE_LEASES", False)


class Lease:
    def __init__(self, ir_id):
        from django.core.cache import cache

        self.ir_id = ir_id
        self._stop = threading.Event()
        self._cache = cache
        self._touch()
        self._thread = threading.Thread(target=self._run, name=f"ic-lease-{ir_id}",
                                        daemon=True)
        self._thread.start()

    def _touch(self):
        try:
            self._cache.set(_lease_key(self.ir_id), 1, timeout=LEASE_TTL)
        except Exception:
            logger.warning("capacity: lease refresh failed for %s", self.ir_id, exc_info=True)

    def _run(self):
        while not self._stop.wait(LEASE_REFRESH):
            self._touch()

    def stop(self):
        self._stop.set()
        try:
            self._cache.delete(_lease_key(self.ir_id))
        except Exception:
            pass


def start_lease(ir_id):
    return Lease(ir_id) if leases_enabled() else None


def _live_sync_ids(ids):
    """Of these sync request ids, the ones whose lease is still alive."""
    if not ids:
        return set()
    from django.core.cache import cache

    try:
        found = cache.get_many([_lease_key(i) for i in ids])
    except Exception:
        logger.warning("capacity: lease lookup failed; counting all sync slots",
                       exc_info=True)
        return set(ids)
    return {i for i in ids if _lease_key(i) in found}


def _in_flight_q():
    stale = timezone.now() - timezone.timedelta(
        seconds=getattr(settings, "SYNC_SLOT_STALE_SECONDS", 900)
    )
    return Q(status="PROCESSING") & (
        Q(is_async=True)
        | (Q(is_async=False) & ~Q(job_service_type="") & Q(started_at__gte=stale))
    )


def running_counts() -> dict:
    """In-flight work per ``(provider_id, normalized service_type)``, sync and
    async together. The dispatcher seeds its tally from this."""
    from .models import InferenceRequest

    out = {}

    def _add(provider_id, stype, n=1):
        key = (provider_id, norm_type(stype))
        out[key] = out.get(key, 0) + n

    rows = (
        InferenceRequest.objects.filter(_in_flight_q(), is_async=True)
        .values("provider_id", "job_service_type")
        .annotate(n=Count("id"))
    )
    for r in rows:
        _add(r["provider_id"], r["job_service_type"], r["n"])
    sync_rows = list(
        InferenceRequest.objects.filter(_in_flight_q(), is_async=False)
        .values_list("id", "provider_id", "job_service_type")
    )
    if sync_rows and leases_enabled():
        live = _live_sync_ids([r[0] for r in sync_rows])
        sync_rows = [r for r in sync_rows if r[0] in live]
    for _id, pid, stype in sync_rows:
        _add(pid, stype)
    return out


def resolve(provider_model):
    """``(provider_id, service_type, service_max, group, group_max, group_types)``
    with types normalized. Mirrors ``jobs._resolve_capacity``."""
    from .jobs import _resolve_capacity

    pid, stype, smax, group, gmax, gtypes = _resolve_capacity(provider_model)
    return pid, norm_type(stype), smax, group, gmax, {norm_type(t) for t in gtypes}


def has_room(tally, cap) -> bool:
    pid, stype, smax, group, gmax, gtypes = cap
    if tally.get((pid, stype), 0) >= smax:
        return False
    if group and sum(tally.get((pid, t), 0) for t in gtypes) >= gmax:
        return False
    return True


def claim(provider_model, apply):
    """Atomically take a slot on ``provider_model``'s device and run ``apply()``
    (which creates or flips an InferenceRequest to PROCESSING with
    ``job_service_type`` + ``started_at`` set) while holding the ledger lock.
    Returns apply()'s result, or None if the device is full."""
    cap = resolve(provider_model)
    with transaction.atomic(), ledger_lock():
        if not has_room(running_counts(), cap):
            return None
        return apply(cap[1])


def raw_service_type(provider_model) -> str:
    svc = getattr(provider_model, "service", None)
    return (getattr(svc, "service_type", "") or "") if svc else ""


def queued_backlog(provider_model, model_slug) -> int:
    """Async jobs already waiting for this model — a new ``auto`` request joins
    the back of that line instead of jumping it."""
    from .models import InferenceRequest

    stype = raw_service_type(provider_model)
    q = InferenceRequest.objects.filter(
        is_async=True, status="QUEUED", canceled_at__isnull=True,
        job_service_type=("" if norm_type(stype) == "llm" else stype),
    )
    if model_slug:
        q = q.filter(model_name=model_slug)
    return q.count()


def retry_after_seconds(model_slug) -> int:
    """A rough 'try again in' hint: the average latency of the last few
    completed requests for this model, clamped to 5–120s."""
    from .models import InferenceRequest

    lat = list(
        InferenceRequest.objects.filter(model_name=model_slug, status="PROCESSED",
                                        latency_ms__isnull=False)
        .order_by("-id").values_list("latency_ms", flat=True)[:5]
    )
    avg = sum(lat) / len(lat) if lat else 15000
    return int(max(5, min(120, round(avg / 1000))))


def at_capacity_response(model_slug):
    from rest_framework import status
    from rest_framework.response import Response

    secs = retry_after_seconds(model_slug)
    resp = Response(
        {
            "error": {
                "message": (
                    f"Every GPU slot serving '{model_slug}' is busy right now. Retry after "
                    f"~{secs}s, or send \"async\": \"auto\" (or true) to queue the request "
                    "as a job instead of waiting."
                ),
                "type": "at_capacity",
                "retry_after": secs,
            }
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    resp["Retry-After"] = str(secs)
    return resp


def request_mode(request) -> str:
    """The caller's async mode, as parsed (and stripped) by ``_pop_async`` for
    JSON bodies, or read from the form for multipart uploads."""
    mode = getattr(request, "_ic_async_mode", None)
    if mode:
        return mode
    try:
        v = request.data.get("async")
    except Exception:
        v = None
    return parse_mode(v)


def parse_mode(v) -> str:
    if isinstance(v, bool):
        return MODE_ASYNC if v else MODE_SYNC
    if v is None:
        return MODE_SYNC
    s = str(v).strip().lower()
    if s == "auto":
        return MODE_AUTO
    return MODE_ASYNC if s in {"1", "true", "yes", "on"} else MODE_SYNC


def admit(request, provider_model, *, create, stored_payload=None, collection_name=None,
          on_queued=None):
    """Gate a synchronous request on device capacity, then create its
    InferenceRequest. Returns ``(ir, None)`` to proceed or ``(None, response)``.

    ``create`` is the kwargs dict for ``InferenceRequest.objects.create``. While
    the device is full:

    - ``async: "auto"`` on an async-submittable type → queue it as a job (202,
      ``queued_reason: at_capacity``); ``on_queued(job)`` runs first (e.g. to
      attach a first-frame image).
    - otherwise wait up to ``SYNC_CAPACITY_WAIT_SECONDS`` for a slot, then 429
      ``at_capacity`` with a Retry-After.
    """
    from .jobs import ASYNC_SUBMIT_TYPES, async_enabled
    from .models import InferenceRequest

    inference_type = create.get("inference_type") or ""
    stype = raw_service_type(provider_model)
    if provider_model is None or exempt(stype):
        return InferenceRequest.objects.create(**create), None

    model_slug = create.get("model_name") or ""
    mode = request_mode(request)
    can_queue = (
        mode == MODE_AUTO and inference_type in ASYNC_SUBMIT_TYPES
        and stored_payload is not None and async_enabled()
    )

    def _apply(_norm):
        return InferenceRequest.objects.create(
            **create, job_service_type=stype, started_at=timezone.now()
        )

    def _queue():
        request._ic_queued_reason = "at_capacity"
        from .job_views import submit_async

        resp = submit_async(
            request, inference_type, stored_payload,
            visibility=create.get("visibility") or "",
            collection_name=collection_name,
            model_name=model_slug,
            on_queued=on_queued,
        )
        return None, resp

    # "auto" joins the back of an existing line rather than jumping it.
    if can_queue and queued_backlog(provider_model, model_slug):
        return _queue()

    wait = 0 if can_queue else float(getattr(settings, "SYNC_CAPACITY_WAIT_SECONDS", 20))
    deadline = time.monotonic() + wait
    poll = float(getattr(settings, "SYNC_CAPACITY_POLL_SECONDS", 1.0))
    while True:
        ir = claim(provider_model, _apply)
        if ir is not None:
            request._ic_capacity_ir_id = ir.id
            request._ic_capacity_lease = start_lease(ir.id)
            return ir, None
        if can_queue:
            return _queue()
        if time.monotonic() >= deadline:
            logger.info("capacity: %s at capacity; rejecting sync request", model_slug)
            return None, at_capacity_response(model_slug)
        time.sleep(poll)


def claim_existing(ir, provider_model, *, wait_seconds=None) -> bool:
    """Take a slot for an *existing* request (in-place retry, agent tool run):
    flip it to PROCESSING under the ledger lock. Waits up to ``wait_seconds``
    (default SYNC_CAPACITY_WAIT_SECONDS). Returns False if no slot freed."""
    stype = raw_service_type(provider_model)
    if exempt(stype):
        if ir.status != "PROCESSING":
            ir.status = "PROCESSING"
            ir.save(update_fields=["status", "modified_on"])
        return True

    def _apply(_norm):
        ir.status = "PROCESSING"
        ir.job_service_type = stype
        ir.started_at = timezone.now()
        ir.save(update_fields=["status", "job_service_type", "started_at", "modified_on"])
        ir._ic_lease = start_lease(ir.id)
        return ir

    if wait_seconds is None:
        wait_seconds = float(getattr(settings, "SYNC_CAPACITY_WAIT_SECONDS", 20))
    deadline = time.monotonic() + wait_seconds
    while True:
        if claim(provider_model, _apply) is not None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(float(getattr(settings, "SYNC_CAPACITY_POLL_SECONDS", 1.0)))


def end_lease(obj):
    """Stop the heartbeat lease held by a request (``request`` or ``ir``)."""
    lease = getattr(obj, "_ic_capacity_lease", None) or getattr(obj, "_ic_lease", None)
    if lease is not None:
        lease.stop()


def release_if_abandoned(ir_id):
    """Safety net: if a sync view raised (or returned) without finalizing the
    request it was admitted for, mark it FAILED so its slot frees now instead
    of after SYNC_SLOT_STALE_SECONDS."""
    from .models import InferenceRequest

    if not ir_id:
        return
    n = InferenceRequest.objects.filter(id=ir_id, status="PROCESSING", is_async=False).update(
        status="FAILED", results={"error": "Request ended before completing."},
        modified_on=timezone.now(),
    )
    if n:
        logger.warning("capacity: released abandoned sync slot for request %s", ir_id)


def offline_placeholder(request, model_name, service_type=None):
    """For ``async: "auto"``: when no *online* provider serves ``model_name``,
    return an accessible deployment of it on an offline/busy-registered
    provider so the view can build its stored payload and queue the job. The
    dispatcher re-resolves a live provider at run time (and fails the job after
    JOB_NO_PROVIDER_TIMEOUT_SECONDS). None if the model is unknown to this user
    (a typo shouldn't sit in the queue for an hour)."""
    from .jobs import async_enabled
    from .models import ProviderModel
    from .openai_views import _model_accessible, _model_match_q, _service_type_q
    from .serializers import _user_real_github_login

    if not model_name or request_mode(request) != MODE_AUTO or not async_enabled():
        return None
    gh = _user_real_github_login(request.user)
    qs = (
        ProviderModel.objects.filter(is_active=True, provider__is_active=True)
        .filter(_model_match_q(model_name))
        .filter(_service_type_q(service_type))
        .select_related("provider", "service", "catalog_model")
    )
    for pm in qs:
        if _model_accessible(pm, request.user, gh):
            request._ic_queued_reason = "no_provider"
            return pm
    return None


def snapshot_for_user(user) -> list:
    """Live per-service load for everything ``user`` can route to (own nodes +
    shared services on online providers) — backs ``GET /v1/capacity``."""
    from .models import InferenceRequest, ProviderModel
    from .openai_views import _model_accessible, _model_slug
    from .serializers import _user_real_github_login

    gh = _user_real_github_login(user)
    tally = running_counts()
    queued = {
        (r["model_name"]): r["n"]
        for r in InferenceRequest.objects.filter(is_async=True, status="QUEUED")
        .values("model_name").annotate(n=Count("id"))
    }
    seen = set()
    out = []
    pms = (
        ProviderModel.objects.filter(is_active=True, provider__is_active=True)
        .exclude(provider__tailnet_hostname="")
        .select_related("provider", "service", "catalog_model")
        .order_by("provider_id", "id")
    )
    for pm in pms:
        if not pm.provider.is_online or not _model_accessible(pm, user, gh):
            continue
        slug = _model_slug(pm)
        key = (pm.provider_id, slug)
        if key in seen:
            continue
        seen.add(key)
        cap = resolve(pm)
        pid, stype, smax, group, gmax, gtypes = cap
        in_flight = tally.get((pid, stype), 0)
        out.append({
            "model": slug,
            "service_type": stype,
            "provider": pm.provider.name,
            "in_flight": in_flight,
            "max_concurrent": smax,
            "resource_group": group or None,
            "group_in_flight": (sum(tally.get((pid, t), 0) for t in gtypes) if group else None),
            "group_max_concurrent": gmax if group else None,
            "queued": queued.get(slug, 0),
            "gated": not exempt(stype),
            "available": has_room(tally, cap),
        })
    return out
