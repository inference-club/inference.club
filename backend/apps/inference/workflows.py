"""Workflow engine: run a DAG of inference steps as queued jobs.

A workflow ``spec`` is plain data (JSON) a human or an agent can author. Each
step is one of:

- ``inference`` — render a request body from the run context and enqueue ONE
  job (e.g. chat/completions, an image, a video).
- ``map`` — resolve a list from the context and enqueue ONE job per item
  (dynamic fan-out: an LLM that returns 8 sections → 8 image jobs).
- ``transform`` — a pure data step run inline (split / pluck / passthrough).
- ``collect`` — gather a fan-out step's per-item outputs into one list.
- ``gate`` — pause for human approval, then resume.

Edges are data dependencies: a step runs once every step it references (via
``{{steps.<id>...}}`` templates or an explicit ``depends_on``) is DONE. The
engine reuses the job queue for execution, so every step inherits capacity
scheduling, retries, and durability. Jobs link back to their step via
``InferenceRequest.step_run``; ``on_job_finished`` drives the run forward as
each job completes. See docs/prd/10-async-jobs-and-workflows.md.
"""
import json
import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("django")

# endpoint / short type → (inference_type, routing service_type)
_ENDPOINT_TYPE = {
    "/v1/chat/completions": ("LLM", ""),
    "/v1/completions": ("LLM", ""),
    "/v1/images/generations": ("IMAGE", "image"),
    "/v1/videos/generations": ("VIDEO", "video"),
    "/v1/music/generations": ("MUSIC", "music"),
    "/v1/audio/speech": ("TTS", "tts"),
}
_SHORT_TYPE = {
    "llm": ("LLM", ""), "chat": ("LLM", ""),
    "image": ("IMAGE", "image"), "video": ("VIDEO", "video"),
    "music": ("MUSIC", "music"), "tts": ("TTS", "tts"),
}

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
_STEP_REF_RE = re.compile(r"steps\.([A-Za-z0-9_\-]+)")


class WorkflowError(ValueError):
    """A spec the engine can't run (bad shape, unknown step kind, …)."""


# --- templating --------------------------------------------------------------


def _lookup(scope, path):
    """Resolve a dotted ``path`` (``steps.outline.output.sections``,
    ``item.text``, ``inputs.x``) against ``scope``. List indices are numeric
    segments. Returns None for any missing segment."""
    cur = scope
    for seg in path.split("."):
        seg = seg.strip()
        if seg == "":
            return None
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


def render(value, scope):
    """Recursively substitute ``{{ path }}`` templates in ``value`` against
    ``scope``. A string that is *exactly* one template resolves to the raw
    value (which may be a list/dict/number); embedded templates stringify."""
    if isinstance(value, str):
        m = _TEMPLATE_RE.fullmatch(value.strip())
        if m:
            return _lookup(scope, m.group(1))
        def _sub(mo):
            v = _lookup(scope, mo.group(1))
            return "" if v is None else (v if isinstance(v, str) else json.dumps(v))
        return _TEMPLATE_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: render(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, scope) for v in value]
    return value


def _referenced_steps(step):
    """Step ids referenced by this step's templates (for auto dependency
    derivation), excluding the step's own id."""
    blob = json.dumps(step)
    refs = set(_STEP_REF_RE.findall(blob))
    refs.discard(step.get("id"))
    return refs


# --- spec validation ---------------------------------------------------------


def validate_spec(spec):
    """Validate a workflow spec, returning the normalized list of steps. Raises
    WorkflowError on anything the engine can't run."""
    if not isinstance(spec, dict):
        raise WorkflowError("Workflow spec must be an object.")
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise WorkflowError("Workflow spec needs a non-empty `steps` list.")
    ids = set()
    norm = []
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise WorkflowError(f"Step #{i} must be an object.")
        sid = raw.get("id")
        if not sid or not isinstance(sid, str):
            raise WorkflowError(f"Step #{i} needs a string `id`.")
        if sid in ids:
            raise WorkflowError(f"Duplicate step id {sid!r}.")
        ids.add(sid)
        kind = raw.get("kind")
        if kind not in {"inference", "map", "transform", "collect", "gate"}:
            raise WorkflowError(f"Step {sid!r} has unknown kind {kind!r}.")
        if kind in ("inference", "map") and not _resolve_kind(raw):
            raise WorkflowError(
                f"Step {sid!r} needs an `endpoint` or `type` "
                f"(one of chat/image/video/music/tts)."
            )
        if kind == "map" and "over" not in raw:
            raise WorkflowError(f"Map step {sid!r} needs an `over` list reference.")
        if kind == "collect" and "from" not in raw:
            raise WorkflowError(f"Collect step {sid!r} needs a `from` step id.")
        norm.append(raw)
    # Validate dependency references resolve to real steps.
    for raw in norm:
        for dep in set(raw.get("depends_on") or []) | _referenced_steps(raw):
            if dep not in ids:
                raise WorkflowError(
                    f"Step {raw['id']!r} depends on unknown step {dep!r}."
                )
    return norm


def _resolve_kind(step):
    """(inference_type, service_type) for an inference/map step, or None."""
    ep = step.get("endpoint")
    if ep in _ENDPOINT_TYPE:
        return _ENDPOINT_TYPE[ep]
    t = (step.get("type") or "").lower()
    return _SHORT_TYPE.get(t)


# --- run lifecycle -----------------------------------------------------------


def start_run(user, spec, inputs=None, name="", workflow=None):
    """Create a WorkflowRun + its step rows from ``spec`` and kick it off.
    Returns the WorkflowRun."""
    from .models import WorkflowRun, WorkflowStepRun, WF_RUNNING

    steps = validate_spec(spec)
    inputs = inputs or {}
    run = WorkflowRun.objects.create(
        user=user, workflow=workflow, name=name or spec.get("name") or "",
        spec=spec, inputs=inputs, context={"inputs": inputs, "steps": {}},
        status=WF_RUNNING, started_at=timezone.now(),
    )
    for pos, step in enumerate(steps):
        deps = sorted(set(step.get("depends_on") or []) | _referenced_steps(step))
        WorkflowStepRun.objects.create(
            run=run, step_id=step["id"], kind=step["kind"],
            title=step.get("title") or step["id"], depends_on=deps,
            spec=step, position=pos,
        )
    advance_run(run.id)
    return WorkflowRun.objects.get(id=run.id)


def advance_run(run_id):
    """Start every step whose dependencies are satisfied, then recompute the
    run status. Idempotent and safe to call repeatedly (steps flip
    PENDING→RUNNING under a row lock, so a step is never started twice)."""
    from .models import (
        WorkflowRun, WF_AWAITING, WF_CANCELED, WF_DONE, WF_FAILED, WF_PENDING,
        WF_RUNNING, WF_SKIPPED,
    )

    with transaction.atomic():
        run = WorkflowRun.objects.select_for_update().filter(id=run_id).first()
        if run is None or run.status in (WF_DONE, WF_FAILED, WF_CANCELED):
            return
        steps = list(run.steps.select_for_update().all())
        by_id = {s.step_id: s for s in steps}
        context = run.context or {"inputs": run.inputs, "steps": {}}

        progressed = True
        while progressed:
            progressed = False
            for step in steps:
                if step.status != WF_PENDING:
                    continue
                dep_states = [by_id[d].status for d in step.depends_on if d in by_id]
                if any(d in (WF_FAILED, WF_CANCELED, WF_SKIPPED) for d in dep_states):
                    _set_step(step, WF_SKIPPED, error={"message": "Upstream step did not complete."})
                    progressed = True
                    continue
                if not all(d == WF_DONE for d in dep_states):
                    continue  # deps still running
                # All deps done → start this step.
                started = _start_step(run, step, context)
                if started:
                    progressed = True
            # Refresh context view after inline (transform/collect) steps.
            run.context = context

        _recompute_run_status(run, steps)
        run.save(update_fields=["context", "status", "finished_at", "error", "modified_on"])


def _start_step(run, step, context):
    """Begin one step whose deps are satisfied. Inline steps (transform/collect)
    complete immediately and update ``context``; inference/map enqueue jobs and
    go RUNNING; a gate goes AWAITING. Returns True if the step's status changed."""
    from .models import WF_AWAITING, WF_DONE, WF_RUNNING

    kind = step.kind
    if kind == "gate":
        _set_step(step, WF_AWAITING)
        return True
    if kind == "transform":
        out = _run_transform(step.spec, context)
        _complete_step(step, out, context)
        return True
    if kind == "collect":
        src = step.spec.get("from")
        out = context.get("steps", {}).get(src)
        _complete_step(step, out if isinstance(out, list) else [out], context)
        return True
    if kind in ("inference", "map"):
        _enqueue_step_jobs(run, step, context)
        _set_step(step, WF_RUNNING)
        return True
    return False


def _enqueue_step_jobs(run, step, context):
    """Create the queued job(s) for an inference/map step."""
    from . import jobs

    itype, stype = _resolve_kind(step.spec)
    model = render(step.spec.get("model", ""), context) or ""
    if step.kind == "inference":
        body = render(step.spec.get("body", {}), context) or {}
        payload = _payload_for(itype, body, model)
        jobs.enqueue_job(
            run.user, itype, payload, model_name=str(model),
            step_run=step, priority=step.spec.get("priority", 0),
        )
        return
    # map: fan out over a resolved list.
    items = render(step.spec.get("over"), context)
    if not isinstance(items, list):
        items = [] if items is None else [items]
    cap = settings.WORKFLOW_MAX_FANOUT
    if len(items) > cap:
        logger.warning("workflow map %s capped %d→%d items", step.step_id, len(items), cap)
        items = items[:cap]
    step.spec["_fanout"] = len(items)
    step.save(update_fields=["spec", "modified_on"])
    for idx, item in enumerate(items):
        scope = dict(context)
        scope["item"] = item
        scope["index"] = idx
        body = render(step.spec.get("body", {}), scope) or {}
        payload = _payload_for(itype, body, model)
        jobs.enqueue_job(
            run.user, itype, payload, model_name=str(model),
            step_run=step, priority=step.spec.get("priority", 0),
        )


def _payload_for(itype, body, model):
    """The stored payload shape the matching retry runner expects: the rendered
    request body with the model id set."""
    payload = dict(body) if isinstance(body, dict) else {"input": body}
    if model:
        payload.setdefault("model", model)
    return payload


# --- step transitions --------------------------------------------------------


def _set_step(step, status, *, output=None, error=None):
    from .models import WF_AWAITING, WF_DONE, WF_FAILED, WF_RUNNING, WF_SKIPPED

    step.status = status
    if status == WF_RUNNING and step.started_at is None:
        step.started_at = timezone.now()
    if status in (WF_DONE, WF_FAILED, WF_SKIPPED):
        step.finished_at = timezone.now()
    if output is not None:
        step.output = output
    if error is not None:
        step.error = error
    step.save(update_fields=[
        "status", "started_at", "finished_at", "output", "error", "modified_on",
    ])


def _complete_step(step, output, context):
    """Mark a step DONE and publish its output into the run context. Stored
    under ``steps.<id>.output`` so templates read ``{{steps.x.output...}}``."""
    from .models import WF_DONE

    _set_step(step, WF_DONE, output=output)
    context.setdefault("steps", {})[step.step_id] = {"output": output}


def _run_transform(spec, context):
    """Inline data transforms. ``op`` selects the operation:
    - ``passthrough`` — return the resolved ``input``.
    - ``pluck`` — map a list, taking ``field`` from each item.
    - ``split_lines`` — split a string on newlines (drops blanks).
    - ``join`` — join a list with ``sep`` (default newline).
    """
    op = (spec.get("op") or "passthrough").lower()
    value = render(spec.get("input"), context)
    if op == "passthrough":
        return value
    if op == "pluck":
        field = spec.get("field")
        if isinstance(value, list):
            return [
                (v.get(field) if isinstance(v, dict) else None) for v in value
            ]
        return []
    if op == "split_lines":
        if isinstance(value, str):
            return [ln.strip() for ln in value.splitlines() if ln.strip()]
        return []
    if op == "join":
        sep = spec.get("sep", "\n")
        if isinstance(value, list):
            return sep.join(str(v) for v in value)
        return str(value)
    return value


# --- job completion hook -----------------------------------------------------


def on_job_finished(job):
    """Called when a workflow-owned job reaches a terminal status. Updates the
    step (for a map step, only once all its jobs are terminal), then advances
    the run."""
    from .models import WF_DONE, WF_FAILED, WF_RUNNING, WorkflowStepRun

    step = WorkflowStepRun.objects.filter(id=job.step_run_id).select_related("run").first()
    if step is None or step.status not in (WF_RUNNING,):
        return
    run = step.run

    sibling_jobs = list(step.jobs.all())
    if any(j.status not in ("PROCESSED", "FAILED", "CANCELED") for j in sibling_jobs):
        return  # other jobs in this step still running

    failed = [j for j in sibling_jobs if j.status in ("FAILED", "CANCELED")]
    if failed:
        _set_step(step, WF_FAILED, error={
            "message": f"{len(failed)} of {len(sibling_jobs)} job(s) failed.",
        })
    else:
        ordered = sorted(sibling_jobs, key=lambda j: j.id)
        outputs = [_job_output(j) for j in ordered]
        out = outputs[0] if step.kind == "inference" else outputs
        ctx = run.context or {"inputs": run.inputs, "steps": {}}
        ctx.setdefault("steps", {})[step.step_id] = {"output": out}
        run.context = ctx
        run.save(update_fields=["context", "modified_on"])
        _set_step(step, WF_DONE, output=out)

    advance_run(run.id)


def _job_output(job):
    """Templating-friendly output for a finished job: parsed JSON / text for an
    LLM, asset urls for media. The DAG viewer also re-derives live URLs from the
    job itself, so this only needs to carry values later steps template on."""
    out = {"request_id": job.id, "type": job.inference_type}
    results = job.results if isinstance(job.results, dict) else {}
    if job.inference_type == "LLM":
        text = _llm_text(results)
        out["text"] = text
        if (job.step_run and (job.step_run.spec or {}).get("extract") == "json"):
            parsed = _try_json(text)
            if isinstance(parsed, dict):
                out.update(parsed)
            elif isinstance(parsed, list):
                out["items"] = parsed
        return out
    # media: surface the first stored asset id + a best-effort url.
    asset = job.assets.exclude(kind__startswith="INPUT").order_by("id").first()
    if asset is not None:
        out["asset_id"] = asset.id
        out["url"] = _asset_url_safe(asset)
    return out


def _llm_text(results):
    for ch in (results.get("choices") or []):
        if isinstance(ch, dict):
            msg = ch.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
            if isinstance(ch.get("text"), str):
                return ch["text"]
    return ""


def _try_json(text):
    if not isinstance(text, str):
        return None
    s = text.strip()
    # Tolerate a ```json fenced block.
    if s.startswith("```"):
        s = s.strip("`")
        s = s[4:] if s.lower().startswith("json") else s
        s = s.strip()
    try:
        return json.loads(s)
    except ValueError:
        return None


def _asset_url_safe(asset):
    try:
        from .serializers import asset_url
        return asset_url(asset, None)
    except Exception:
        return None


# --- run status + gate -------------------------------------------------------


def _recompute_run_status(run, steps):
    from .models import (
        WF_AWAITING, WF_DONE, WF_FAILED, WF_PENDING, WF_RUNNING, WF_SKIPPED,
    )

    states = [s.status for s in steps]
    if all(s in (WF_DONE, WF_SKIPPED) for s in states):
        # A run is FAILED if any required step was skipped due to an upstream
        # failure; DONE only when everything that could run did.
        run.status = WF_DONE
        if run.finished_at is None:
            run.finished_at = timezone.now()
        return
    if any(s == WF_FAILED for s in states) and not any(
        s in (WF_RUNNING, WF_AWAITING, WF_PENDING) for s in states
    ):
        run.status = WF_FAILED
        if run.finished_at is None:
            run.finished_at = timezone.now()
        return
    if any(s == WF_AWAITING for s in states) and not any(
        s == WF_RUNNING for s in states
    ):
        run.status = WF_AWAITING
        return
    run.status = WF_RUNNING


def resolve_gate(run, step_id, action, edit=None):
    """Resolve an AWAITING gate. ``approve`` marks it DONE (output = its edited
    value or the passthrough of its single dependency) and resumes the run;
    ``reject`` fails it. Returns (ok, error)."""
    from .models import WF_AWAITING, WF_DONE, WF_FAILED

    step = run.steps.filter(step_id=step_id, kind="gate").first()
    if step is None:
        return False, "No such gate step."
    if step.status != WF_AWAITING:
        return False, "This gate isn't awaiting input."
    if action == "approve":
        if edit is not None:
            out = edit
        elif step.depends_on:
            dep_ctx = (run.context or {}).get("steps", {}).get(step.depends_on[0]) or {}
            out = dep_ctx.get("output") if isinstance(dep_ctx, dict) else None
        else:
            out = {"approved": True}
        ctx = run.context or {"inputs": run.inputs, "steps": {}}
        ctx.setdefault("steps", {})[step.step_id] = {"output": out}
        run.context = ctx
        run.save(update_fields=["context", "modified_on"])
        _set_step(step, WF_DONE, output=out)
    elif action == "reject":
        _set_step(step, WF_FAILED, error={"message": "Rejected by reviewer."})
    else:
        return False, "Action must be 'approve' or 'reject'."
    advance_run(run.id)
    return True, None


def advance_ready_runs():
    """Safety-net pass over non-terminal runs (used by the beat tick) so any run
    with newly-ready steps that no job-completion event covered still moves —
    e.g. initial transform chains or post-gate resumes."""
    from .models import WF_RUNNING, WorkflowRun

    for run in WorkflowRun.objects.filter(status=WF_RUNNING):
        try:
            advance_run(run.id)
        except Exception:
            logger.exception("advance_ready_runs failed for run %s", run.id)
