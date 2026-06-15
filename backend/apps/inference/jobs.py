"""Async job queue: enqueue, dispatch, execute, retry, cancel.

A "job" is an ``InferenceRequest`` with ``is_async=True``, created in the
``QUEUED`` state and run later by a worker when a provider has a free capacity
slot. Postgres is the source of truth; the dispatcher claims work with
``SELECT … FOR UPDATE SKIP LOCKED`` and enforces concurrency by counting the
jobs already PROCESSING on each provider/service/resource-group.

Execution reuses the per-modality runners already written for in-place retries
(``openai_views._RETRY_RUNNERS``): they reconstruct a modality's upstream call
from ``ir.payload`` (+ any stored INPUT_* asset) and finalize the same row.
That is exactly what a worker needs, so the async path adds scheduling and
retry/backoff around them rather than a second copy of the proxy logic.

See docs/prd/10-async-jobs-and-workflows.md.
"""
import logging

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

logger = logging.getLogger("django")

# inference_type → routing service_type (mirrors openai_views._RETRY_SERVICE_TYPE;
# "" means the LLM path, no restriction). Modalities the executor can run async.
JOB_SERVICE_TYPE = {
    "LLM": "", "STT": "stt", "TTS": "tts",
    "IMAGE": "image", "MESH": "mesh", "MUSIC": "music", "VIDEO": "video",
    "SCRAPE": "scrape",
}
# Modalities accepted over the async API directly. File-input modalities
# (STT/MESH/VOICE/image-edits) need an uploaded blob and stay synchronous for
# now; workflows still drive them via stored input assets where applicable.
# SCRAPE is JSON-bodied ({url}) and re-runnable, so it's async-submittable.
ASYNC_SUBMIT_TYPES = {"LLM", "IMAGE", "VIDEO", "MUSIC", "TTS", "SCRAPE"}

MAX_BACKOFF_SECONDS = 600


class AsyncDisabled(Exception):
    """Raised when an async submission arrives but no broker is configured."""


def async_enabled() -> bool:
    return bool(getattr(settings, "ASYNC_ENABLED", False))


# --- dispatch trigger & heartbeat -------------------------------------------
# The dispatcher runs on two triggers: a periodic Celery beat tick (a safety
# net for retry backoff + reaping) AND an immediate "kick" whenever work is
# enqueued or a job finishes. The kick makes the *worker* self-draining, so the
# queue moves even if beat isn't running — the most common cause of a workflow
# appearing to hang.

HEARTBEAT_KEY = "jobs:last_dispatch"


def record_dispatch_heartbeat():
    from django.core.cache import cache

    try:
        cache.set(HEARTBEAT_KEY, timezone.now().isoformat(), 600)
    except Exception:
        pass


def last_dispatch_at():
    from django.core.cache import cache

    try:
        return cache.get(HEARTBEAT_KEY)
    except Exception:
        return None


def kick_dispatch():
    """Ask a worker to run the dispatcher now. No-op when async is disabled or
    Celery is eager (tests/inline drive dispatch themselves). Never raises —
    a failed kick just means the next beat tick picks the work up."""
    if not async_enabled():
        return
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return
    try:
        from .tasks import dispatch_queued
        dispatch_queued.delay()
    except Exception:
        logger.warning("kick_dispatch failed; relying on the beat tick", exc_info=True)


def auto_model_for(user, service_type):
    """The canonical id of the first model ``user`` can route to for
    ``service_type`` (own nodes first, then accessible shared services). Lets a
    workflow step omit an explicit model and stay portable across users.
    Returns '' when nothing is available."""
    from .models import ProviderModel
    from .openai_views import _model_accessible, _model_slug, _online_providers
    from .serializers import _user_real_github_login

    stype = service_type or "llm"
    for provider in _online_providers(user):
        pm = (
            provider.models.filter(is_active=True, service__service_type=stype)
            .select_related("provider", "service", "catalog_model")
            .first()
        )
        if pm is not None:
            return _model_slug(pm)
    github_login = _user_real_github_login(user)
    candidates = (
        ProviderModel.objects.filter(
            is_active=True, provider__is_active=True,
            provider__accepting_requests=True, service__service_type=stype,
        )
        .exclude(provider__tailnet_hostname="")
        .select_related("provider", "service", "catalog_model")
    )
    for pm in candidates:
        if _model_accessible(pm, user, github_login) and pm.provider.is_online:
            return _model_slug(pm)
    return ""


# --- enqueue -----------------------------------------------------------------


def enqueue_job(
    user,
    inference_type,
    payload,
    *,
    model_name="",
    visibility="",
    collection_name=None,
    batch=None,
    step_run=None,
    idempotency_key="",
    priority=0,
    max_attempts=3,
):
    """Create a QUEUED async job (an ``InferenceRequest``) and return it.

    ``payload`` must be the *stored* payload shape the matching retry runner
    expects (the same dict the synchronous view persists). If an
    ``idempotency_key`` is given and a job already exists for this user+key,
    that existing job is returned untouched.
    """
    from .models import InferenceRequest
    from .sharing import file_into_collection

    if idempotency_key:
        existing = InferenceRequest.objects.filter(
            user=user, idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            return existing

    job = InferenceRequest.objects.create(
        user=user,
        model_name=model_name or (payload or {}).get("model") or "",
        inference_type=inference_type,
        payload=payload,
        status="QUEUED",
        is_async=True,
        job_service_type=JOB_SERVICE_TYPE.get(inference_type, ""),
        queued_at=timezone.now(),
        priority=priority,
        max_attempts=max_attempts,
        idempotency_key=idempotency_key or "",
        visibility=visibility or "",
        batch=batch,
        step_run=step_run,
    )
    if collection_name:
        file_into_collection(user, job, collection_name)
    return job


# --- capacity ----------------------------------------------------------------


def _resolve_capacity(provider_model):
    """For a resolved deployment, return the scheduling parameters:
    ``(provider_id, service_type, service_max, group, group_max, group_types)``.

    ``group_types`` is the set of service_types that share the resource group on
    this provider — used to count group-wide concurrency from the real
    ``job_service_type`` column without reading dispatch_meta JSON.
    """
    from .models import ResourceGroup

    provider = provider_model.provider
    service = provider_model.service
    if service is None:
        # Live-discovered LLM with no manifest service: a conservative pool of
        # one, keyed on the provider + empty type.
        return provider.id, "", 1, "", 0, set()

    service_max = max(1, service.max_concurrent or 1)
    group = (service.resource_group or "").strip()
    if not group:
        return provider.id, service.service_type, service_max, "", 0, set()

    rg = ResourceGroup.objects.filter(provider=provider, name=group).first()
    group_max = max(1, rg.max_concurrent if rg else 1)
    group_types = set(
        provider.services.filter(is_active=True, resource_group=group).values_list(
            "service_type", flat=True
        )
    )
    return provider.id, service.service_type, service_max, group, group_max, group_types


def _running_counts():
    """Snapshot of in-flight async jobs per (provider_id, service_type), as a
    dict keyed ``(provider_id, service_type)`` → count. The dispatcher seeds its
    tally from this and increments as it assigns within the tick."""
    from django.db.models import Count

    from .models import InferenceRequest

    rows = (
        InferenceRequest.objects.filter(is_async=True, status="PROCESSING")
        .values("provider_id", "job_service_type")
        .annotate(n=Count("id"))
    )
    return {(r["provider_id"], r["job_service_type"]): r["n"] for r in rows}


def _service_load(tally, provider_id, service_type):
    return tally.get((provider_id, service_type), 0)


def _group_load(tally, provider_id, group_types):
    return sum(tally.get((provider_id, t), 0) for t in group_types)


# --- dispatch ----------------------------------------------------------------


def _claim_queryset(now):
    """QUEUED async jobs that are due (run_after passed), newest priority first.
    Uses SKIP LOCKED where the DB supports it so multiple dispatchers (or a
    re-fire) never hand the same job out twice."""
    from django.db.models import Q

    from .models import InferenceRequest

    qs = (
        InferenceRequest.objects.filter(is_async=True, status="QUEUED")
        .filter(Q(run_after__isnull=True) | Q(run_after__lte=now))
        .filter(canceled_at__isnull=True)
        .order_by("-priority", "queued_at", "id")
    )
    if connection.features.has_select_for_update_skip_locked:
        qs = qs.select_for_update(skip_locked=True)
    return qs


def dispatch_due_jobs(limit=50):
    """Claim up to ``limit`` queued jobs that can start now, mark them
    PROCESSING against a chosen provider, and return their ids. Capacity is
    enforced atomically inside the locking transaction. Returns the list of
    claimed job ids (the caller is responsible for actually running them)."""
    from .openai_views import _find_provider_for_model

    record_dispatch_heartbeat()
    now = timezone.now()
    claimed = []
    no_provider_cutoff = now - timezone.timedelta(
        seconds=settings.JOB_NO_PROVIDER_TIMEOUT_SECONDS
    )

    with transaction.atomic():
        tally = _running_counts()
        jobs = list(_claim_queryset(now)[:limit])
        for job in jobs:
            model_name = job.model_name or (job.payload or {}).get("model") or ""
            service_type = job.job_service_type or None
            provider_model = _find_provider_for_model(
                job.user, model_name, service_type=service_type
            )
            if provider_model is None:
                # No online provider for this model right now. Keep waiting,
                # unless we've waited past the no-provider deadline.
                if job.queued_at and job.queued_at < no_provider_cutoff:
                    _mark_failed(
                        job,
                        message=(
                            f"No online provider served '{model_name}' within "
                            f"the queue window."
                        ),
                        kind="no_provider",
                    )
                continue

            (
                provider_id,
                svc_type,
                svc_max,
                group,
                group_max,
                group_types,
            ) = _resolve_capacity(provider_model)

            if _service_load(tally, provider_id, svc_type) >= svc_max:
                continue  # service is at capacity; try this job next tick
            if group and _group_load(tally, provider_id, group_types) >= group_max:
                continue  # the shared GPU group is busy

            job.provider = provider_model.provider
            job.status = "PROCESSING"
            job.started_at = now
            job.attempts = (job.attempts or 0) + 1
            job.error = None
            job.dispatch_meta = {
                "provider_model_id": provider_model.id,
                "provider_id": provider_id,
                "service_type": svc_type,
                "resource_group": group,
                "served_name": provider_model.name,
            }
            job.save(
                update_fields=[
                    "provider", "status", "started_at", "attempts", "error",
                    "dispatch_meta", "modified_on",
                ]
            )
            tally[(provider_id, svc_type)] = (
                _service_load(tally, provider_id, svc_type) + 1
            )
            claimed.append(job.id)
    return claimed


# --- execution ---------------------------------------------------------------


def run_job(ir_id):
    """Execute a single claimed (PROCESSING) job to completion, then apply the
    retry/backoff or terminal-failure policy and notify any workflow waiting on
    it. Safe to call from a Celery worker or inline (tests)."""
    from .models import InferenceRequest
    from .openai_views import _RETRY_RUNNERS, _find_provider_for_model

    job = InferenceRequest.objects.filter(id=ir_id).select_related("provider").first()
    if job is None or job.status != "PROCESSING":
        return  # canceled, reaped, or already handled
    if job.canceled_at is not None:
        _finalize_canceled(job)
        return

    runner = _RETRY_RUNNERS.get(job.inference_type)
    if runner is None:
        _mark_failed(job, f"Async execution isn't supported for {job.inference_type}.",
                     kind="unsupported")
        _notify_step(job)
        return

    # Bind to the deployment chosen at dispatch; re-resolve if it vanished.
    pm = None
    pm_id = (job.dispatch_meta or {}).get("provider_model_id")
    if pm_id:
        from .models import ProviderModel
        pm = (
            ProviderModel.objects.filter(id=pm_id)
            .select_related("provider", "service", "catalog_model")
            .first()
        )
    if pm is None:
        model_name = job.model_name or (job.payload or {}).get("model") or ""
        pm = _find_provider_for_model(
            job.user, model_name, service_type=(job.job_service_type or None)
        )
    if pm is None:
        _requeue_or_fail(job, "Provider went offline before the job ran.",
                         kind="no_provider")
        _notify_step(job)
        return

    try:
        ok, err = runner(job, pm)
    except Exception as e:  # a runner crash must not strand the job PROCESSING
        logger.exception("run_job %s crashed", ir_id)
        ok, err = False, str(e)

    job.refresh_from_db()
    if job.canceled_at is not None:
        _finalize_canceled(job)
        _notify_step(job)
        return

    if ok:
        job.status = "PROCESSED"
        job.finished_at = timezone.now()
        job.error = None
        job.save(update_fields=["status", "finished_at", "error", "modified_on"])
    else:
        _requeue_or_fail(job, err or "Upstream call failed.", kind="upstream")

    _notify_step(job)
    # A slot just freed (and a workflow may have enqueued downstream jobs) —
    # nudge the dispatcher so the queue keeps draining without waiting on beat.
    kick_dispatch()


def _is_permanent(job) -> bool:
    """A failure that retrying won't fix — a deterministic upstream rejection
    (4xx other than 429). Everything else (connection, 5xx, timeout) is
    transient and worth a retry."""
    results = job.results if isinstance(job.results, dict) else {}
    code = results.get("upstream_status")
    if isinstance(code, int):
        return 400 <= code < 500 and code != 429
    return False


def _requeue_or_fail(job, message, *, kind="upstream"):
    """Apply the retry policy after a failed run: re-queue with backoff if
    attempts remain and the failure looks transient, else fail terminally."""
    attempts = job.attempts or 0
    if job.canceled_at is not None:
        _finalize_canceled(job)
        return
    if attempts < (job.max_attempts or 1) and not _is_permanent(job):
        backoff = min(MAX_BACKOFF_SECONDS, 60 * (2 ** max(0, attempts - 1)))
        job.status = "QUEUED"
        job.provider = None
        job.started_at = None
        job.run_after = timezone.now() + timezone.timedelta(seconds=backoff)
        job.error = {"message": message, "kind": kind, "attempt": attempts,
                     "retry_in_seconds": backoff}
        job.save(update_fields=[
            "status", "provider", "started_at", "run_after", "error", "modified_on",
        ])
        return
    _mark_failed(job, message, kind=kind)


def _mark_failed(job, message, *, kind="error"):
    job.status = "FAILED"
    job.finished_at = timezone.now()
    job.error = {"message": message, "kind": kind, "attempt": job.attempts or 0}
    job.save(update_fields=["status", "finished_at", "error", "modified_on"])


def _finalize_canceled(job):
    if job.status not in ("CANCELED",):
        job.status = "CANCELED"
        if job.finished_at is None:
            job.finished_at = timezone.now()
        job.save(update_fields=["status", "finished_at", "modified_on"])


def _notify_step(job):
    """If this job is part of a workflow, let the engine react to its outcome."""
    if job.step_run_id:
        try:
            from . import workflows
            workflows.on_job_finished(job)
        except Exception:  # workflow advance must never strand a finished job
            logger.exception("workflow advance failed for job %s", job.id)


# --- cancel / retry ----------------------------------------------------------


def cancel_job(job) -> bool:
    """Cancel a queued or running job. QUEUED → CANCELED immediately. A
    PROCESSING job is marked with intent (it finishes its current attempt but
    won't be retried). Terminal jobs are left alone. Returns True if changed."""
    if job.status in ("QUEUED",):
        job.status = "CANCELED"
        job.canceled_at = timezone.now()
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "canceled_at", "finished_at", "modified_on"])
        _notify_step(job)
        return True
    if job.status == "PROCESSING" and job.canceled_at is None:
        job.canceled_at = timezone.now()
        job.save(update_fields=["canceled_at", "modified_on"])
        return True
    return False


def retry_job(job) -> bool:
    """Re-queue a FAILED/CANCELED job for another run. Resets the attempt
    counter and clears stale outputs. Returns True if it was re-queued."""
    from .models import MediaAsset

    if job.status not in ("FAILED", "CANCELED"):
        return False
    job.assets.filter(kind__in=[
        MediaAsset.OUTPUT_AUDIO, MediaAsset.OUTPUT_IMAGE,
        MediaAsset.OUTPUT_MODEL, MediaAsset.OUTPUT_VIDEO,
    ]).delete()
    job.status = "QUEUED"
    job.is_async = True
    job.provider = None
    job.attempts = 0
    job.error = None
    job.results = None
    job.canceled_at = None
    job.started_at = None
    job.finished_at = None
    job.run_after = None
    job.queued_at = timezone.now()
    job.save(update_fields=[
        "status", "is_async", "provider", "attempts", "error", "results",
        "canceled_at", "started_at", "finished_at", "run_after", "queued_at",
        "modified_on",
    ])
    return True


# --- reaper ------------------------------------------------------------------


def reap_stuck_jobs():
    """Reclaim jobs stuck PROCESSING past the running timeout (a worker died
    mid-run). They're re-queued (or failed if out of attempts) so the queue
    never wedges. Returns the count reclaimed."""
    from .models import InferenceRequest

    cutoff = timezone.now() - timezone.timedelta(
        seconds=settings.JOB_RUNNING_TIMEOUT_SECONDS
    )
    stuck = InferenceRequest.objects.filter(
        is_async=True, status="PROCESSING", started_at__lt=cutoff
    )
    n = 0
    for job in stuck:
        _requeue_or_fail(job, "Worker timed out; job reclaimed.", kind="timeout")
        _notify_step(job)
        n += 1
    return n


# --- inline driver (tests / eager dev) ---------------------------------------


def process_jobs_inline(max_rounds=50, limit=50):
    """Dispatch and run queued jobs synchronously until the queue makes no more
    progress. For tests and eager local runs — production uses Celery beat +
    workers. Returns the number of jobs run."""
    ran = 0
    for _ in range(max_rounds):
        claimed = dispatch_due_jobs(limit=limit)
        if not claimed:
            break
        for ir_id in claimed:
            run_job(ir_id)
            ran += 1
    return ran
