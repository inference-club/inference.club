"""HTTP API for async jobs, batches and workflows (PRD 10).

These endpoints are additive. Synchronous inference is unchanged; a request
only becomes a queued job when the caller opts in (``async: true`` on a /v1/*
body, or by submitting a batch / workflow). Everything routes, meters, and is
owned exactly like a normal InferenceRequest.
"""
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import jobs, workflows
from .job_serializers import (
    BatchSerializer,
    JobSerializer,
    WorkflowRunListSerializer,
    WorkflowRunSerializer,
)
from .models import Batch, InferenceRequest, WorkflowRun
from .throttling import AccountTypeScopedRateThrottle

logger = logging.getLogger("django")

# Map a batch item's declared endpoint to (inference_type, the body the
# matching retry runner expects). Only the JSON-bodied, file-free modalities
# are async-submittable (see jobs.ASYNC_SUBMIT_TYPES).
_ENDPOINT_INFERENCE_TYPE = {
    "/v1/chat/completions": "LLM",
    "/v1/completions": "LLM",
    "/v1/images/generations": "IMAGE",
    "/v1/videos/generations": "VIDEO",
    "/v1/music/generations": "MUSIC",
    "/v1/audio/speech": "TTS",
}


def wants_async(request) -> bool:
    """Whether the caller asked for the async/queued path via an ``async`` flag
    on the request body."""
    data = getattr(request, "data", None)
    if not hasattr(data, "get"):
        return False
    v = data.get("async")
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "on"} if v is not None else False


def pop_async_flag(body) -> None:
    """Strip the ``async`` extension from a JSON body so it never reaches the
    upstream server."""
    if isinstance(body, dict):
        body.pop("async", None)


def accepted(job) -> Response:
    """The 202 returned to an async submitter: an OpenAI-ish job envelope."""
    return Response(
        {
            "id": str(job.id),
            "object": "inference.job",
            "status": job.status,
            "inference_type": job.inference_type,
            "model": job.model_name,
            "created": int(job.created_on.timestamp()),
            "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        },
        status=status.HTTP_202_ACCEPTED,
    )


def submit_async(request, inference_type, payload, *, visibility="", collection_name=None,
                 batch=None, model_name=""):
    """Create a queued job from an already-validated payload and return the 202
    Response (or a 503 if async is disabled). Used by the /v1 views' async
    branch."""
    if not jobs.async_enabled():
        return Response(
            {"error": {"message": "Async processing is not enabled on this server.",
                       "type": "async_disabled"}},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    idem = request.headers.get("Idempotency-Key", "") or ""
    job = jobs.enqueue_job(
        request.user, inference_type, payload,
        model_name=model_name, visibility=visibility, collection_name=collection_name,
        batch=batch, idempotency_key=idem,
    )
    jobs.kick_dispatch()
    return accepted(job)


# --- jobs --------------------------------------------------------------------


class _OwnedJobMixin:
    permission_classes = [IsAuthenticated]

    def get_job(self, request, id):
        job = InferenceRequest.objects.filter(id=id).select_related("provider").first()
        if job is None:
            return None, Response(
                {"error": {"message": "No such job.", "type": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if job.user_id != request.user.id:
            return None, Response(
                {"error": {"message": "Not your job.", "type": "forbidden"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return job, None


class JobDetailView(_OwnedJobMixin, APIView):
    """``GET /v1/jobs/<id>`` — a job's status, result, and media (owner only)."""

    def get(self, request, id):
        job, err = self.get_job(request, id)
        if err:
            return err
        return Response(JobSerializer(job, context={"request": request}).data)


class JobCancelView(_OwnedJobMixin, APIView):
    """``POST /v1/jobs/<id>/cancel``."""

    def post(self, request, id):
        job, err = self.get_job(request, id)
        if err:
            return err
        changed = jobs.cancel_job(job)
        job.refresh_from_db()
        return Response(
            {"id": str(job.id), "status": job.status, "canceled": changed}
        )


class JobRetryView(_OwnedJobMixin, APIView):
    """``POST /v1/jobs/<id>/retry`` — re-queue a failed/canceled job."""

    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "inference"

    def post(self, request, id):
        job, err = self.get_job(request, id)
        if err:
            return err
        if not jobs.retry_job(job):
            return Response(
                {"error": {"message": f"A {job.status} job can't be retried.",
                           "type": "conflict"}},
                status=status.HTTP_409_CONFLICT,
            )
        jobs.kick_dispatch()
        return accepted(job)


class JobListView(APIView):
    """``GET /v1/jobs`` — the caller's recent jobs, newest first. Optional
    ``status`` and ``active=1`` (queued+processing) filters."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = InferenceRequest.objects.filter(
            user=request.user, is_async=True
        ).select_related("provider").order_by("-created_on")
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st.upper())
        if request.query_params.get("active") in ("1", "true"):
            qs = qs.filter(status__in=["QUEUED", "PROCESSING"])
        qs = qs[: int(request.query_params.get("limit") or 50)]
        return Response({"data": JobSerializer(qs, many=True, context={"request": request}).data})


# --- batches -----------------------------------------------------------------


class BatchListCreateView(APIView):
    """``POST /v1/batches`` (submit a list of requests) / ``GET`` (list yours)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Batch.objects.filter(user=request.user).order_by("-created_on")[:50]
        return Response({"data": BatchSerializer(qs, many=True, context={"request": request}).data})

    def post(self, request):
        if not jobs.async_enabled():
            return Response(
                {"error": {"message": "Async processing is not enabled.",
                           "type": "async_disabled"}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        body = request.data if isinstance(request.data, dict) else {}
        requests_in = body.get("requests")
        if not isinstance(requests_in, list) or not requests_in:
            return Response(
                {"error": {"message": "`requests` must be a non-empty list.",
                           "type": "invalid_request"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(requests_in) > 256:
            return Response(
                {"error": {"message": "A batch is limited to 256 requests.",
                           "type": "too_large"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate every item up front so a bad item fails the whole batch
        # cleanly (no half-created batch).
        prepared = []
        for i, item in enumerate(requests_in):
            if not isinstance(item, dict):
                return self._bad_item(i, "must be an object")
            endpoint = item.get("endpoint")
            itype = _ENDPOINT_INFERENCE_TYPE.get(endpoint)
            if itype is None:
                return self._bad_item(
                    i, f"endpoint {endpoint!r} is not async-submittable"
                )
            ibody = item.get("body")
            if not isinstance(ibody, dict):
                return self._bad_item(i, "needs a `body` object")
            prepared.append((itype, dict(ibody)))

        batch = Batch.objects.create(user=request.user, label=body.get("label") or "")
        for itype, ibody in prepared:
            ibody.pop("async", None)
            jobs.enqueue_job(
                request.user, itype, ibody,
                model_name=str(ibody.get("model") or ""), batch=batch,
            )
        jobs.kick_dispatch()
        batch.refresh_from_db()
        return Response(
            BatchSerializer(batch, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )

    def _bad_item(self, i, msg):
        return Response(
            {"error": {"message": f"requests[{i}] {msg}.", "type": "invalid_request"}},
            status=status.HTTP_400_BAD_REQUEST,
        )


class BatchDetailView(APIView):
    """``GET /v1/batches/<id>`` / ``POST .../cancel`` via ?action=cancel."""

    permission_classes = [IsAuthenticated]

    def _get(self, request, id):
        batch = Batch.objects.filter(id=id, user=request.user).first()
        if batch is None:
            return None, Response(
                {"error": {"message": "No such batch.", "type": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return batch, None

    def get(self, request, id):
        batch, err = self._get(request, id)
        if err:
            return err
        return Response(BatchSerializer(batch, context={"request": request}).data)

    def post(self, request, id):
        batch, err = self._get(request, id)
        if err:
            return err
        for job in batch.jobs.filter(status__in=["QUEUED", "PROCESSING"]):
            jobs.cancel_job(job)
        batch.refresh_from_db()
        return Response(BatchSerializer(batch, context={"request": request}).data)


# --- workflows ---------------------------------------------------------------


class WorkflowRunListCreateView(APIView):
    """``POST /v1/workflows/runs`` — start a run from an inline ``spec`` (+
    ``inputs``). ``GET`` — list the caller's runs."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = WorkflowRun.objects.filter(user=request.user).order_by("-created_on")[:50]
        return Response(
            {"data": WorkflowRunListSerializer(qs, many=True, context={"request": request}).data}
        )

    def post(self, request):
        if not jobs.async_enabled():
            return Response(
                {"error": {"message": "Async processing is not enabled.",
                           "type": "async_disabled"}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        body = request.data if isinstance(request.data, dict) else {}
        inputs = body.get("inputs") or {}
        name = body.get("name") or ""

        # Two ways to start a run: from a curated template (+ inputs), or from
        # an inline spec (agents / power users).
        template_key = body.get("template")
        if template_key:
            from . import workflow_templates
            spec, tname, cleaned, err = workflow_templates.build_spec(template_key, inputs)
            if err:
                return Response(
                    {"error": {"message": err, "type": "invalid_request"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            inputs = cleaned
            name = name or tname
        else:
            spec = body.get("spec")
            if not isinstance(spec, dict):
                return Response(
                    {"error": {"message": "`spec` object or `template` key is required.",
                               "type": "invalid_request"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            run = workflows.start_run(request.user, spec, inputs=inputs, name=name)
        except workflows.WorkflowError as e:
            return Response(
                {"error": {"message": str(e), "type": "invalid_spec"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            WorkflowRunSerializer(run, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )


class WorkflowTemplateListView(APIView):
    """``GET /v1/workflows/templates`` — curated, ready-to-run workflows with
    their input schemas, for the gallery + dynamic form."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from . import workflow_templates
        return Response({"data": workflow_templates.list_templates()})


class WorkflowSuggestionListView(APIView):
    """``GET /v1/workflows/suggestions?template=key&n=5`` — random sample of
    LLM-generated prompt suggestions for a given workflow template key."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import WorkflowPromptSuggestion
        key = request.query_params.get("template", "")
        if not key:
            return Response(
                {"error": {"message": "`template` query param is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            n = max(1, min(20, int(request.query_params.get("n", 5))))
        except (TypeError, ValueError):
            n = 5
        qs = WorkflowPromptSuggestion.objects.filter(template_key=key).order_by("?")[:n]
        return Response({"data": [s.text for s in qs]})


class WorkflowRunDetailView(APIView):
    """``GET /v1/workflows/runs/<id>`` — the live DAG (steps, edges, media)."""

    permission_classes = [IsAuthenticated]

    def _get(self, request, id):
        run = WorkflowRun.objects.filter(id=id, user=request.user).first()
        if run is None:
            return None, Response(
                {"error": {"message": "No such run.", "type": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return run, None

    def get(self, request, id):
        run, err = self._get(request, id)
        if err:
            return err
        return Response(WorkflowRunSerializer(run, context={"request": request}).data)


class WorkflowGateView(APIView):
    """``POST /v1/workflows/runs/<id>/steps/<step_id>/<action>`` where action is
    ``approve`` or ``reject``. Optional ``edit`` body replaces the gate output
    on approve."""

    permission_classes = [IsAuthenticated]

    def post(self, request, id, step_id, action):
        run = WorkflowRun.objects.filter(id=id, user=request.user).first()
        if run is None:
            return Response(
                {"error": {"message": "No such run.", "type": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        edit = request.data.get("edit") if isinstance(request.data, dict) else None
        ok, err = workflows.resolve_gate(run, step_id, action, edit=edit)
        if not ok:
            return Response(
                {"error": {"message": err, "type": "conflict"}},
                status=status.HTTP_409_CONFLICT,
            )
        run.refresh_from_db()
        return Response(WorkflowRunSerializer(run, context={"request": request}).data)


# --- queue summary -----------------------------------------------------------


class QueueSummaryView(APIView):
    """``GET /api/inference/queue/summary`` — counts for the dashboard badge."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count

        rows = (
            InferenceRequest.objects.filter(user=request.user, is_async=True)
            .values("status")
            .annotate(n=Count("id"))
        )
        counts = {r["status"]: r["n"] for r in rows}
        active = counts.get("QUEUED", 0) + counts.get("PROCESSING", 0)
        runs = (
            WorkflowRun.objects.filter(user=request.user)
            .values("status")
            .annotate(n=Count("id"))
        )
        # Dispatcher liveness: when there's active work but the dispatcher
        # hasn't ticked recently, the queue is stalled (no worker running) —
        # the frontend warns instead of letting jobs hang silently.
        last = jobs.last_dispatch_at()
        worker_stalled = False
        if active and jobs.async_enabled():
            if not last:
                worker_stalled = True
            else:
                try:
                    from datetime import datetime
                    age = (timezone.now() - datetime.fromisoformat(last)).total_seconds()
                    worker_stalled = age > 60
                except Exception:
                    worker_stalled = False
        return Response(
            {
                "jobs": counts,
                "active": active,
                "runs": {r["status"]: r["n"] for r in runs},
                "async_enabled": jobs.async_enabled(),
                "last_dispatch": last,
                "worker_stalled": worker_stalled,
            }
        )
