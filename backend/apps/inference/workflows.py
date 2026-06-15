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
    # --- media pipeline (PRD 12); runners deferred to the agent ---
    "/v1/audio/transcriptions": ("STT", "stt"),
    "/v1/scrape": ("SCRAPE", "scrape"),
    "/v1/videos/compose": ("RENDER", "render"),
    "/v1/audio/enhance": ("ENHANCE", "audio-enhance"),
}
_SHORT_TYPE = {
    "llm": ("LLM", ""), "chat": ("LLM", ""),
    "image": ("IMAGE", "image"), "video": ("VIDEO", "video"),
    "music": ("MUSIC", "music"), "tts": ("TTS", "tts"),
    # --- media pipeline (PRD 12) ---
    "stt": ("STT", "stt"), "transcribe": ("STT", "stt"),
    "scrape": ("SCRAPE", "scrape"),
    "compose": ("RENDER", "render"), "render": ("RENDER", "render"),
    "clean": ("ENHANCE", "audio-enhance"), "enhance": ("ENHANCE", "audio-enhance"),
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
        if kind not in _STEP_KINDS:
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


_STEP_KINDS = {"inference", "map", "transform", "collect", "gate", "prompt"}


def validate_spec_shape(spec):
    """Permissive check used when *saving* a workflow draft (PRD 11 builder),
    where a half-built graph is normal. Unlike ``validate_spec`` (which the
    engine runs at launch and which enforces every per-kind requirement), this
    only rejects gross structural errors: spec must be an object with a list of
    steps, and every step needs a unique string ``id`` and a known ``kind``.
    Returns the spec unchanged. Raises WorkflowError otherwise."""
    if not isinstance(spec, dict):
        raise WorkflowError("Workflow spec must be an object.")
    steps = spec.get("steps", [])
    if not isinstance(steps, list):
        raise WorkflowError("`steps` must be a list.")
    ids = set()
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise WorkflowError(f"Step #{i} must be an object.")
        sid = raw.get("id")
        if not sid or not isinstance(sid, str):
            raise WorkflowError(f"Step #{i} needs a string `id`.")
        if sid in ids:
            raise WorkflowError(f"Duplicate step id {sid!r}.")
        ids.add(sid)
        if raw.get("kind") not in _STEP_KINDS:
            raise WorkflowError(f"Step {sid!r} has unknown kind {raw.get('kind')!r}.")
    return spec


def _resolve_kind(step):
    """(inference_type, service_type) for an inference/map/prompt step, or None.
    A ``prompt`` step is always an LLM call (it writes a prompt for a downstream
    modality), so it routes like chat regardless of its ``target``."""
    if step.get("kind") == "prompt":
        return ("LLM", "")
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
    # Ask a worker to start the now-queued first steps immediately (don't wait
    # for the periodic beat tick).
    from . import jobs
    jobs.kick_dispatch()
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
    if kind in ("inference", "map", "prompt"):
        _enqueue_step_jobs(run, step, context)
        _set_step(step, WF_RUNNING)
        return True
    return False


def _enqueue_step_jobs(run, step, context):
    """Create the queued job(s) for an inference/map/prompt step."""
    from . import jobs

    itype, stype = _resolve_kind(step.spec)
    model = render(step.spec.get("model", ""), context) or ""
    # Portable templates omit the model; resolve one the user can actually
    # route to for this modality at run time.
    if not model:
        model = jobs.auto_model_for(run.user, stype)
    priority = step.spec.get("priority", 0)

    # A declared JSON response_schema means parse the reply as JSON (persist the
    # flag so on_job_finished, which reloads the step, sees it).
    if isinstance(step.spec.get("response_schema"), dict) and step.spec.get("extract") != "json":
        step.spec["extract"] = "json"
        step.save(update_fields=["spec", "modified_on"])

    def _make(body):
        body = _maybe_structured(step.spec, body)
        payload = _payload_for(itype, body, model)
        job = jobs.enqueue_job(
            run.user, itype, payload, model_name=str(model),
            step_run=step, priority=priority,
        )
        _maybe_attach_image(job, body)
        return job

    if step.kind == "prompt":
        # Meta-prompting: an LLM writes one (or N) prompt(s) for a downstream
        # modality. Build the chat body from a preset, then enqueue one job.
        _make(_prompt_body(step, context))
        return

    if step.kind == "inference":
        _make(render(step.spec.get("body", {}), context) or {})
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
        _make(render(step.spec.get("body", {}), scope) or {})


# --- meta-prompting (prompt node) --------------------------------------------

# System presets that turn a rough brief into a polished prompt for one
# downstream modality. The on-ramp to meta-prompting: a `prompt` step picks a
# preset by its `target` and emits a prompt (or a list) the next step consumes.
_PROMPT_PRESETS = {
    "image": (
        "You are an expert prompt engineer for text-to-image models. Turn the "
        "user's brief into a single vivid, concrete image prompt: subject, "
        "composition, lighting, lens, mood and style. No camera settings jargon "
        "unless useful, no preamble."
    ),
    "video": (
        "You are an expert prompt engineer for text-to-video models. Turn the "
        "user's brief into a single prompt describing the scene AND its motion "
        "(camera movement, subject action, pacing). Keep it concrete and short."
    ),
    "music": (
        "You are an expert music director. Turn the user's brief into a single "
        "production brief for a music model: genre, mood, instrumentation, tempo "
        "and structure. No preamble."
    ),
    "tts": (
        "You are a scriptwriter for narration. Turn the user's brief into a "
        "single clean line of spoken narration — natural, friendly, no stage "
        "directions, no quotes."
    ),
    "text": (
        "You are an expert prompt engineer. Rewrite the user's brief into a "
        "single clearer, richer prompt for a language model. No preamble."
    ),
}


def _prompt_body(step, context):
    """Build the chat body for a ``prompt`` step. ``target`` selects the preset
    modality; ``count`` > 1 asks for a JSON list so a downstream map can fan out
    over ``{{steps.<id>.output.prompts}}``."""
    spec = step.spec
    target = (spec.get("target") or "image").lower()
    preset = _PROMPT_PRESETS.get(target, _PROMPT_PRESETS["image"])
    brief = render(spec.get("input") or spec.get("brief") or "", context)
    extra = render(spec.get("instructions") or "", context)
    try:
        count = int(spec.get("count") or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(count, settings.WORKFLOW_MAX_FANOUT))

    system = preset
    if count > 1:
        system += (
            f' Produce exactly {count} distinct options. Return ONLY valid JSON: '
            '{"prompts":["...", ...]} — no prose, no code fences.'
        )
        # extract:json so _job_output parses {"prompts":[...]} into the output.
        spec["extract"] = "json"
        step.save(update_fields=["spec", "modified_on"])
    else:
        system += " Respond with ONLY the prompt text — no preamble, no quotes."

    user = str(brief)
    if extra:
        user += f"\n\nAdditional direction: {extra}"
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]}


def _maybe_structured(spec, body):
    """If an LLM step declares a JSON ``response_schema``, attach an OpenAI-style
    ``response_format`` (passed through to the provider untouched by the runner).
    Pure — the caller persists ``extract:json`` on the step so ``_job_output``
    parses the reply. Capable models honor the schema; for the rest the merged
    JSON-extract still applies."""
    schema = spec.get("response_schema")
    if not isinstance(schema, dict) or not isinstance(body, dict):
        return body
    if "messages" not in body and "prompt" not in body:
        return body  # not a chat/completions body — ignore
    body = dict(body)
    body["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": spec.get("schema_name") or "output",
                        "schema": schema, "strict": True},
    }
    return body


def _maybe_attach_image(job, body):
    """Materialize an upstream image into a job's conditioning input.

    A video (or image-edit) step can reference a previous step's produced image
    by its asset id — e.g. ``"image_asset_id": "{{item.frame.asset_id}}"``. The
    async executor reads conditioning images from a *stored* INPUT_IMAGE asset
    (not a URL), so here we copy the referenced asset's bytes onto this job and
    flip ``has_image`` on, which is exactly what ``_rerun_video`` expects. This
    is what makes image-to-video (storyboard → clips) work inside a workflow."""
    if not isinstance(body, dict):
        return
    aid = body.get("image_asset_id")
    if not aid:
        return
    from django.core.files.base import ContentFile

    from .models import MediaAsset

    src = MediaAsset.objects.filter(id=aid, user=job.user).first()
    if src is None or not src.file:
        return
    try:
        with src.file.open("rb") as f:
            data = f.read()
    except Exception:
        logger.warning("workflow: could not read image asset %s for job %s", aid, job.id)
        return
    try:
        asset = MediaAsset(
            user=job.user, inference_request=job, kind=MediaAsset.INPUT_IMAGE,
            content_type=src.content_type or "image/png", size_bytes=len(data),
        )
        ext = (src.content_type or "image/png").rsplit("/", 1)[-1] or "png"
        asset.file.save(f"frame.{ext}", ContentFile(data), save=False)
        asset.save()
    except Exception:
        logger.warning("workflow: could not attach image to job %s", job.id, exc_info=True)
        return
    p = job.payload or {}
    p["has_image"] = True
    if p.get("image_strength") is None:
        p["image_strength"] = body.get("image_strength", 1.0)
    job.payload = p
    job.save(update_fields=["payload", "modified_on"])


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
    - ``split_sections`` — group lines into sections of ``size`` (default 2),
      the hn.fm dialog-section shape: ``[{index, lines, text}]`` (PRD 12).
    - ``subtitle`` — render word timestamps into a ``format`` (vtt|ass)
      subtitle string (PRD 12).
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
    if op == "zip":
        # Pair multiple lists element-wise → [[a0,b0],[a1,b1],...] so a map can
        # iterate over both (e.g. each storyboard shot + its rendered frame),
        # referenced as {{item.0...}} / {{item.1...}}.
        lists = [render(x, context) for x in (spec.get("inputs") or [])]
        lists = [x if isinstance(x, list) else [] for x in lists]
        n = min((len(x) for x in lists), default=0)
        return [[col[i] for col in lists] for i in range(n)]
    if op == "split_sections":
        return _split_sections(value, spec.get("size", 2))
    if op == "subtitle":
        return _render_subtitle(value, spec.get("format", "vtt"))
    return value


# --- media pipeline transforms (PRD 12) --------------------------------------


def _split_sections(value, size):
    """Group lines into sections of ``size`` (hn.fm: 2 dialog lines per
    section). ``value`` may be a list of strings or a newline string. Returns
    ``[{index, lines, text}]`` — a ``map`` step can then fan one TTS/image job
    per section, and ``index`` keeps audio/images/subtitles aligned."""
    try:
        size = max(1, int(size))
    except (TypeError, ValueError):
        size = 2
    if isinstance(value, str):
        lines = [ln.strip() for ln in value.splitlines() if ln.strip()]
    elif isinstance(value, list):
        lines = [str(x).strip() for x in value if str(x).strip()]
    else:
        return []
    sections = []
    for i in range(0, len(lines), size):
        chunk = lines[i:i + size]
        sections.append({
            "index": len(sections),
            "lines": chunk,
            "text": "\n".join(chunk),
        })
    return sections


def _subtitle_cues(words):
    """Normalize ASR word timestamps to ``(start_s, end_s, text)`` cues.
    Accepts hn.fm's ``{word, start_ms, duration_ms}`` or ``{text, start, end}``
    (seconds); skips blanks and gives zero-length words a small floor."""
    cues = []
    for w in words:
        if not isinstance(w, dict):
            continue
        text = str(w.get("word") or w.get("text") or "").strip()
        if not text:
            continue
        if "start_ms" in w or "duration_ms" in w:
            start = float(w.get("start_ms") or 0) / 1000.0
            end = start + float(w.get("duration_ms") or 0) / 1000.0
        else:
            start = float(w.get("start") or 0)
            end = float(w.get("end") or start)
        if end <= start:
            end = start + 0.3
        cues.append((start, end, text))
    return cues


def _fmt_ts_vtt(s):
    s = max(0.0, float(s))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    return f"{h:02d}:{m:02d}:{s % 60:06.3f}"


def _fmt_ts_ass(s):
    s = max(0.0, float(s))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    cs = int(round((s - int(s)) * 100))
    return f"{h:d}:{m:02d}:{sec:02d}.{cs:02d}"


_ASS_HEADER = (
    "[Script Info]\n"
    "ScriptType: v4.00+\n\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment, MarginV\n"
    "Style: Default,Arial,48,&H00FFFFFF,1,2,40\n\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Text"
)


def _render_subtitle(value, fmt):
    """Word timestamps → a subtitle string. ``value`` may be a ``{words:[...]}``
    dict (our STT shape) or a bare word list. ``fmt`` is ``vtt`` (default) or
    ``ass`` (word-synced, for the slideshow renderer)."""
    words = value.get("words") if isinstance(value, dict) else value
    if not isinstance(words, list):
        return ""
    cues = _subtitle_cues(words)
    if (fmt or "vtt").lower() == "ass":
        lines = [_ASS_HEADER]
        for start, end, text in cues:
            lines.append(
                f"Dialogue: 0,{_fmt_ts_ass(start)},{_fmt_ts_ass(end)},Default,{text}"
            )
        return "\n".join(lines) + "\n"
    out = ["WEBVTT", ""]
    for i, (start, end, text) in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{_fmt_ts_vtt(start)} --> {_fmt_ts_vtt(end)}")
        out.append(text)
        out.append("")
    return "\n".join(out).strip() + "\n"


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
        # inference/prompt issue one job → unwrap; map fans out → keep the list.
        out = outputs[0] if step.kind in ("inference", "prompt") else outputs
        ctx = run.context or {"inputs": run.inputs, "steps": {}}
        ctx.setdefault("steps", {})[step.step_id] = {"output": out}
        run.context = ctx
        run.save(update_fields=["context", "modified_on"])
        _set_step(step, WF_DONE, output=out)
        _record_step_provenance(step, sibling_jobs, ctx)

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
        # Alias for prompt/chat steps: read either {{...output.text}} or .prompt.
        out["prompt"] = text.strip() if isinstance(text, str) else text
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


# --- provenance (PRD 12 §5.1) ------------------------------------------------


def _extract_asset_ids(value):
    """Pull MediaAsset ids out of a resolved ``derive_from`` reference. Accepts
    a bare id, a job-output dict (``{asset_id|id: N, ...}``), or arbitrarily
    nested lists/dicts of those — so ``{{steps.images.output}}`` (a map's list
    of per-item outputs) yields every frame's asset id."""
    ids = []

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, int):
            ids.append(v)
        elif isinstance(v, dict):
            # Prefer an explicit asset id; don't also harvest request_id etc.
            for key in ("asset_id", "id"):
                if isinstance(v.get(key), int) and not isinstance(v.get(key), bool):
                    ids.append(v[key])
                    return
            for sub in v.values():
                walk(sub)
        elif isinstance(v, list):
            for sub in v:
                walk(sub)

    walk(value)
    return ids


def _record_step_provenance(step, jobs, context):
    """Link a step's produced assets to the upstream assets it derived from,
    declared on the step as ``derive_from`` (a ref or list of refs resolved
    against the run context). Best-effort: provenance is metadata, so any error
    here must never fail the run."""
    refs = step.spec.get("derive_from")
    if not refs:
        return
    try:
        source_ids = set()
        for ref in (refs if isinstance(refs, list) else [refs]):
            source_ids.update(_extract_asset_ids(render(ref, context)))
        if not source_ids:
            return
        for job in jobs:
            for asset in job.assets.exclude(kind__startswith="INPUT"):
                asset.record_derivation(source_ids)
    except Exception:
        logger.exception("provenance recording failed for step %s", step.step_id)


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
    from . import jobs
    jobs.kick_dispatch()
    return True, None


def _descendants(steps, root_id):
    """All step ids reachable from ``root_id`` by following depends_on edges
    forward (root included). Used to invalidate downstream work on a re-run."""
    children = {}
    for s in steps:
        for dep in s.depends_on or []:
            children.setdefault(dep, []).append(s.step_id)
    seen, stack = set(), [root_id]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(children.get(cur, []))
    return seen


def rerun_step(run, step_id):
    """Re-run a single step (e.g. re-roll an image) against the run's existing
    context, then re-flow everything downstream of it. The step and its
    descendants reset to PENDING; their old jobs are detached (kept in the
    gallery, not deleted) and fresh ones enqueue. Returns (ok, error)."""
    from .models import (
        InferenceRequest, WF_PENDING, WF_RUNNING, WorkflowRun,
    )

    with transaction.atomic():
        run = WorkflowRun.objects.select_for_update().filter(id=run.id).first()
        if run is None:
            return False, "No such run."
        steps = list(run.steps.select_for_update().all())
        target = next((s for s in steps if s.step_id == step_id), None)
        if target is None:
            return False, "No such step."
        if target.kind not in ("inference", "map", "prompt"):
            return False, "Only inference, map and prompt steps can be re-run."
        if target.status in (WF_RUNNING,):
            return False, "Step is still running."

        affected = _descendants(steps, step_id)
        ctx = run.context or {"inputs": run.inputs, "steps": {}}
        ctx_steps = ctx.setdefault("steps", {})
        for s in steps:
            if s.step_id not in affected:
                continue
            # Detach old jobs so generated media survives in the gallery.
            InferenceRequest.objects.filter(step_run=s).update(step_run=None)
            s.status = WF_PENDING
            s.output = None
            s.error = None
            s.started_at = None
            s.finished_at = None
            # Drop the cached _fanout marker so a map re-resolves its list.
            if isinstance(s.spec, dict):
                s.spec.pop("_fanout", None)
            s.save(update_fields=[
                "status", "output", "error", "started_at", "finished_at",
                "spec", "modified_on",
            ])
            ctx_steps.pop(s.step_id, None)
        run.context = ctx
        run.status = WF_RUNNING
        run.finished_at = None
        run.error = None
        run.save(update_fields=["context", "status", "finished_at", "error", "modified_on"])

    advance_run(run.id)
    from . import jobs
    jobs.kick_dispatch()
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
