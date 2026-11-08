"""Remote MCP server for inference.club — ``POST /mcp``.

Model Context Protocol over Streamable HTTP, stateless JSON responses (no SSE
stream, no session state): every JSON-RPC request is answered in the POST
response. Authenticated with the same ``Authorization: Bearer <api key>`` as
``/v1``, so any MCP client (Claude Code, Claude Desktop, Hermes, Cursor…) can
generate with inference.club:

    claude mcp add --transport http inference-club https://api.inference.club/mcp \\
        --header "Authorization: Bearer $INFERENCE_CLUB_API_KEY"

Tools don't reimplement anything: each one dispatches *internally* to the real
``/v1`` view (same auth header), so capacity gating, throttling, sharing,
metering and storage behave exactly as for direct API calls. Generations always
use ``async: "auto"`` + ``delivery: "url"``: run now if a GPU slot is free, else
queue — and the tool waits up to ``MCP_TOOL_WAIT_SECONDS`` for the job before
handing back a job id to poll with ``get_job``. Results are URLs (plus MCP
``resource_link`` items), never inline base64, so agent context stays small.
"""
import json
import logging
import time

from django.conf import settings
from django.test import RequestFactory
from django.urls import resolve
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("django")

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_VERSION = "1.0.0"

INSTRUCTIONS = """\
inference.club runs open models on community GPUs (often a single home GPU per
model). Tools here generate images, video, music, speech and text, scrape web
pages, and run multi-step workflows.

- Call list_models first if you don't know which model to use; every generation
  tool picks a sensible default model when `model` is omitted.
- Generation tools return media URLs. Share the URL with the user (or download
  it); don't try to inline the bytes.
- Devices have limited concurrency. If a tool returns status QUEUED, the request
  is safely waiting its turn — call get_job(job_id) later (wait ~10-30s between
  checks for images, 30-90s for video/music) instead of resubmitting.
- Don't fire many generations at once. Prefer one at a time per model, and use
  run_workflow or several sequential calls for batches.
"""


def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": False}


_S = {"type": "string"}
_I = {"type": "integer"}
_N = {"type": "number"}
_OPTS = {
    "type": "object",
    "description": "Extra model-specific fields passed through to the /v1 endpoint "
                   "(see the API reference), e.g. {\"guidance\": 4}.",
    "additionalProperties": True,
}
_SHARE = {
    "visibility": {"type": "string", "enum": ["PUBLIC", "UNLISTED", "PRIVATE", "SECRET"],
                   "description": "Who can see the result (default UNLISTED)."},
    "collection": {"type": "string", "description": "Optional collection name to file it into."},
}
_MODEL = {"type": "string", "description": "Model id from list_models. Omit for a default."}


TOOLS = [
    {
        "name": "list_models",
        "description": "List the models this account can use, with service_type "
                       "(llm, image, video, music, tts, stt, mesh, scrape, audio-enhance) "
                       "and supported features.",
        "inputSchema": _obj({"service_type": {**_S, "description": "Filter by service type."}}),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_capacity",
        "description": "Live GPU load per model: in_flight vs max_concurrent, queued jobs, "
                       "and whether a slot is available right now.",
        "inputSchema": _obj({"service_type": _S}),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "generate_image",
        "description": "Text-to-image. Returns image URL(s).",
        "inputSchema": _obj({
            "prompt": _S, "model": _MODEL,
            "size": {**_S, "description": "WxH, e.g. 1024x1024 or 1344x768."},
            "n": {**_I, "minimum": 1, "maximum": 4},
            "seed": _I, "negative_prompt": _S,
            "background": {"type": "string", "enum": ["opaque", "transparent"]},
            "options": _OPTS, **_SHARE,
        }, ["prompt"]),
    },
    {
        "name": "generate_video",
        "description": "Text-to-video (or image-to-video with image_url). Slow (often "
                       "1-5 min); usually returns QUEUED — poll with get_job.",
        "inputSchema": _obj({
            "prompt": _S, "model": _MODEL,
            "image_url": {**_S, "description": "Optional first frame (http(s) URL or data: URI)."},
            "width": _I, "height": _I, "num_frames": _I, "fps": _I, "seed": _I,
            "options": _OPTS, **_SHARE,
        }, ["prompt"]),
    },
    {
        "name": "generate_music",
        "description": "Generate a song/instrumental from a style prompt and optional lyrics.",
        "inputSchema": _obj({
            "prompt": {**_S, "description": "Style/genre/mood tags."},
            "lyrics": {**_S, "description": "Optional lyrics with [verse]/[chorus] tags; "
                                            "use [instrumental] for none."},
            "duration": {**_N, "description": "Seconds (e.g. 30-240)."},
            "model": _MODEL, "seed": _I, "options": _OPTS, **_SHARE,
        }, ["prompt"]),
    },
    {
        "name": "generate_speech",
        "description": "Text-to-speech. Returns an audio URL.",
        "inputSchema": _obj({
            "input": {**_S, "description": "Text to speak."},
            "voice": {**_S, "description": "Voice id (see the model's voices)."},
            "model": _MODEL, "options": _OPTS, **_SHARE,
        }, ["input"]),
    },
    {
        "name": "chat",
        "description": "Ask an inference.club LLM. Give either `prompt` or `messages`. "
                       "Reasoning models think before answering — leave max_tokens unset "
                       "or generous (>=1024).",
        "inputSchema": _obj({
            "prompt": _S,
            "messages": {"type": "array", "items": {"type": "object"},
                         "description": "OpenAI-format chat messages."},
            "system": _S, "model": _MODEL, "max_tokens": _I, "temperature": _N,
            "options": _OPTS,
        }),
    },
    {
        "name": "scrape_url",
        "description": "Fetch a web page and return clean markdown.",
        "inputSchema": _obj({"url": _S, "model": _MODEL}, ["url"]),
    },
    {
        "name": "get_job",
        "description": "Status and result (media URLs / text) of a queued job.",
        "inputSchema": _obj({"job_id": _S}, ["job_id"]),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_jobs",
        "description": "Your recent jobs, newest first.",
        "inputSchema": _obj({"active": {"type": "boolean",
                                        "description": "Only QUEUED/PROCESSING."},
                             "limit": _I}),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "cancel_job",
        "description": "Cancel a queued or running job.",
        "inputSchema": _obj({"job_id": _S}, ["job_id"]),
        "annotations": {"destructiveHint": True},
    },
    {
        "name": "list_workflow_templates",
        "description": "Ready-made multi-step pipelines (e.g. illustrated-story, "
                       "song-and-cover, url-to-video) and their inputs.",
        "inputSchema": _obj({}),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "run_workflow",
        "description": "Start a workflow from a template key with inputs. Returns a run "
                       "id; check progress with get_workflow_run.",
        "inputSchema": _obj({"template": _S, "inputs": {"type": "object"}, **_SHARE},
                            ["template"]),
    },
    {
        "name": "get_workflow_run",
        "description": "A workflow run's status, steps and produced media.",
        "inputSchema": _obj({"run_id": _S}, ["run_id"]),
        "annotations": {"readOnlyHint": True},
    },
]
_TOOL_NAMES = {t["name"] for t in TOOLS}

_GEN_ENDPOINT = {
    "generate_image": ("/v1/images/generations", "image"),
    "generate_video": ("/v1/videos/generations", "video"),
    "generate_music": ("/v1/music/generations", "music"),
    "generate_speech": ("/v1/audio/speech", "tts"),
}


class ToolError(Exception):
    pass


# --- internal dispatch to the real /v1 views ---------------------------------


def _internal(outer, method, path, body=None, query=None):
    """Call a /v1 view in-process with the caller's own credentials. Returns
    ``(status_code, data, headers)``."""
    rf = RequestFactory()
    # Carry the caller's credentials AND its host/scheme (incl. proxy headers),
    # so absolute media URLs built by the views point at the real public host.
    meta = {k: v for k, v in outer.META.items() if k in (
        "HTTP_AUTHORIZATION", "HTTP_HOST", "HTTP_X_FORWARDED_HOST",
        "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_FOR", "REMOTE_ADDR", "SERVER_NAME",
        "SERVER_PORT",
    )}
    secure = outer.is_secure()
    if method == "GET":
        req = rf.get(path, data=query or {}, secure=secure, **meta)
    else:
        req = rf.post(path, data=json.dumps(body or {}), content_type="application/json",
                      secure=secure, **meta)
    match = resolve(path)
    resp = match.func(req, *match.args, **match.kwargs)
    if hasattr(resp, "render") and not getattr(resp, "is_rendered", True):
        resp.render()
    data = None
    ctype = resp.get("Content-Type", "") if hasattr(resp, "get") else ""
    if "json" in ctype:
        try:
            data = json.loads(resp.content or b"null")
        except ValueError:
            data = None
    return resp.status_code, data, resp


def _err_text(code, data):
    if isinstance(data, dict):
        e = data.get("error")
        if isinstance(e, dict):
            msg = e.get("message") or json.dumps(e)
            if e.get("type") == "at_capacity":
                msg += f" (retry after ~{e.get('retry_after')}s)"
            return f"{code} {e.get('type', '')}: {msg}".strip()
        if isinstance(e, str):
            return f"{code}: {e}"
        if data.get("detail"):
            return f"{code}: {data['detail']}"
    return f"HTTP {code}"


def _job_summary(job: dict) -> dict:
    st = job.get("status")
    out = {
        "job_id": str(job.get("id")),
        "status": st,
        "inference_type": job.get("inference_type"),
        "model": job.get("model_name"),
    }
    if st == "PROCESSED":
        out["media"] = job.get("media") or []
        if job.get("output_text"):
            out["text"] = job["output_text"]
    elif st in ("FAILED", "CANCELED"):
        out["error"] = job.get("error")
    else:
        out["hint"] = ("Still working — call get_job with this job_id later. "
                       "Do not resubmit the request.")
    return out


def _wait_for_job(outer, job_id, wait_s):
    deadline = time.monotonic() + max(0.0, wait_s)
    delay = 2.0
    while True:
        code, job, _ = _internal(outer, "GET", f"/v1/jobs/{job_id}")
        if code != 200 or not isinstance(job, dict):
            raise ToolError(_err_text(code, job))
        if job.get("status") in ("PROCESSED", "FAILED", "CANCELED"):
            return job
        if time.monotonic() + delay > deadline:
            return job
        time.sleep(delay)
        delay = min(delay * 1.5, 8.0)


def _default_model(user, service_type):
    from .jobs import auto_model_for

    m = auto_model_for(user, service_type)
    if not m:
        raise ToolError(f"No online {service_type} model is available to this account.")
    return m


# --- tool implementations ----------------------------------------------------


def _tool_list_models(outer, args):
    code, data, _ = _internal(outer, "GET", "/v1/models")
    if code != 200:
        raise ToolError(_err_text(code, data))
    st = args.get("service_type")
    rows = []
    for m in (data or {}).get("data", []):
        if st and m.get("service_type") != st:
            continue
        rows.append({k: m.get(k) for k in (
            "id", "service_type", "input_modalities", "output_modalities",
            "supported_features", "context_length", "owned_by",
        ) if m.get(k) not in (None, [], "")})
    return {"models": rows}


def _tool_get_capacity(outer, args):
    q = {"service_type": args["service_type"]} if args.get("service_type") else None
    code, data, _ = _internal(outer, "GET", "/v1/capacity", query=q)
    if code != 200:
        raise ToolError(_err_text(code, data))
    return {"capacity": (data or {}).get("data", [])}


def _generate(outer, name, args):
    path, stype = _GEN_ENDPOINT[name]
    body = dict(args.get("options") or {})
    for k, v in args.items():
        if k in ("options",) or v is None:
            continue
        body[k] = v
    if name == "generate_video" and body.get("image_url"):
        body["image"] = body.pop("image_url")
    if name == "generate_music":
        body.setdefault("lyrics", "[instrumental]")
        if "duration" in body:
            body["audio_duration"] = body.pop("duration")
    body.setdefault("model", None)
    if name == "generate_speech":
        path, body = _speech_route(outer, body)
    elif not body["model"]:
        body["model"] = _default_model(outer.user, stype)
    body["async"] = "auto"
    body["delivery"] = "url"
    code, data, _ = _internal(outer, "POST", path, body)
    if code == 202 and isinstance(data, dict):
        job = _wait_for_job(outer, data["id"], settings.MCP_TOOL_WAIT_SECONDS)
        out = _job_summary(job)
        if data.get("queued_reason") and out["status"] not in ("PROCESSED",):
            out["queued_reason"] = data["queued_reason"]
        return out
    if code != 200 or not isinstance(data, dict):
        raise ToolError(_err_text(code, data))
    # Images answer OpenAI-style {data:[{url}]}; binary modalities answer
    # inference.result {data:[MediaItem]}.
    media = []
    for item in data.get("data") or []:
        if item.get("url"):
            media.append({k: item.get(k) for k in ("id", "kind", "url", "content_type",
                                                   "duration_seconds", "seed")
                          if item.get(k) is not None} | ({"kind": "image"} if
                                                          name == "generate_image" else {}))
    return {"status": "PROCESSED", "model": body["model"],
            "request_id": data.get("id") or data.get("request_id"), "media": media}


def _speech_route(outer, body):
    """Pick the TTS endpoint for the model: plain voices → /v1/audio/speech;
    dialogue/voice-cloning models (Dia) → /v1/voice/generations with an
    [S1]-tagged script. Default model prefers plain TTS."""
    code, data, _ = _internal(outer, "GET", "/v1/models")
    rows = [m for m in ((data or {}).get("data") or []) if m.get("service_type") == "tts"]

    def dialogue(m):
        return bool(set(m.get("supported_features") or []) & {"dialogue", "voice-cloning"})

    if body.get("model"):
        chosen = next((m for m in rows if m.get("id") == body["model"]), {"id": body["model"]})
    else:
        if not rows:
            raise ToolError("No online tts model is available to this account.")
        chosen = sorted(rows, key=dialogue)[0]
        body["model"] = chosen["id"]
    if dialogue(chosen):
        text = body.get("input") or ""
        if "[S1]" not in text and "[S2]" not in text:
            body["input"] = "[S1] " + text
        body.pop("voice", None)
        return "/v1/voice/generations", body
    return "/v1/audio/speech", body


def _tool_chat(outer, args):
    messages = args.get("messages") or []
    if not messages:
        if not args.get("prompt"):
            raise ToolError("Give `prompt` or `messages`.")
        messages = [{"role": "user", "content": args["prompt"]}]
    if args.get("system"):
        messages = [{"role": "system", "content": args["system"]}] + list(messages)
    body = dict(args.get("options") or {})
    body.update({"messages": messages, "stream": False,
                 "model": args.get("model") or _default_model(outer.user, "llm")})
    for k in ("max_tokens", "temperature"):
        if args.get(k) is not None:
            body[k] = args[k]
    body["async"] = "auto"
    code, data, _ = _internal(outer, "POST", "/v1/chat/completions", body)
    if code == 202:
        return _job_summary(_wait_for_job(outer, data["id"], settings.MCP_TOOL_WAIT_SECONDS))
    if code != 200 or not isinstance(data, dict):
        raise ToolError(_err_text(code, data))
    from .serializers import _extract_response_text

    return {"model": body["model"], "text": _extract_response_text(data),
            "usage": data.get("usage")}


def _tool_scrape(outer, args):
    body = {"url": args["url"], "async": "auto",
            "model": args.get("model") or _default_model(outer.user, "scrape")}
    code, data, _ = _internal(outer, "POST", "/v1/scrape", body)
    if code == 202:
        return _job_summary(_wait_for_job(outer, data["id"], settings.MCP_TOOL_WAIT_SECONDS))
    if code != 200:
        raise ToolError(_err_text(code, data))
    md = (data or {}).get("markdown") or ""
    cap = 60_000
    return {"title": data.get("title"), "source_url": data.get("source_url"),
            "markdown": md[:cap], "truncated": len(md) > cap}


def _job_id(args):
    jid = str(args.get("job_id") or "").strip()
    if not jid.isdigit():
        raise ToolError("job_id must be the numeric id returned by a generation tool.")
    return jid


def _tool_get_job(outer, args):
    code, data, _ = _internal(outer, "GET", f"/v1/jobs/{_job_id(args)}")
    if code != 200:
        raise ToolError(_err_text(code, data))
    return _job_summary(data)


def _tool_list_jobs(outer, args):
    q = {"limit": str(min(int(args.get("limit") or 20), 100))}
    if args.get("active"):
        q["active"] = "1"
    code, data, _ = _internal(outer, "GET", "/v1/jobs", query=q)
    if code != 200:
        raise ToolError(_err_text(code, data))
    rows = data.get("results", data) if isinstance(data, dict) else data
    return {"jobs": [_job_summary(j) for j in (rows or [])]}


def _tool_cancel_job(outer, args):
    code, data, _ = _internal(outer, "POST", f"/v1/jobs/{_job_id(args)}/cancel")
    if code != 200:
        raise ToolError(_err_text(code, data))
    return data


def _tool_list_templates(outer, args):
    code, data, _ = _internal(outer, "GET", "/v1/workflows/templates")
    if code != 200:
        raise ToolError(_err_text(code, data))
    return data


def _tool_run_workflow(outer, args):
    body = {"template": args["template"], "inputs": args.get("inputs") or {}}
    for k in ("visibility", "collection"):
        if args.get(k):
            body[k] = args[k]
    code, data, _ = _internal(outer, "POST", "/v1/workflows/runs", body)
    if code not in (200, 201, 202):
        raise ToolError(_err_text(code, data))
    return {"run_id": str(data.get("id")), "status": data.get("status"),
            "hint": "Check progress with get_workflow_run (workflows take minutes)."}


def _tool_get_workflow_run(outer, args):
    rid = str(args.get("run_id") or "")
    if not rid.isdigit():
        raise ToolError("run_id must be numeric.")
    code, data, _ = _internal(outer, "GET", f"/v1/workflows/runs/{rid}")
    if code != 200:
        raise ToolError(_err_text(code, data))
    steps = []
    for s in data.get("steps") or []:
        media = []
        for j in s.get("jobs") or []:
            media.extend(j.get("media") or [])
        steps.append({"step_id": s.get("step_id"), "kind": s.get("kind"),
                      "status": s.get("status"), "error": s.get("error"), "media": media})
    return {"run_id": rid, "status": data.get("status"), "steps": steps}


_HANDLERS = {
    "list_models": _tool_list_models,
    "get_capacity": _tool_get_capacity,
    "chat": _tool_chat,
    "scrape_url": _tool_scrape,
    "get_job": _tool_get_job,
    "list_jobs": _tool_list_jobs,
    "cancel_job": _tool_cancel_job,
    "list_workflow_templates": _tool_list_templates,
    "run_workflow": _tool_run_workflow,
    "get_workflow_run": _tool_get_workflow_run,
}


def call_tool(outer, name, args):
    if name in _GEN_ENDPOINT:
        return _generate(outer, name, args)
    return _HANDLERS[name](outer, args)


def _tool_result(payload, is_error=False):
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=1)
    content = [{"type": "text", "text": text}]
    if isinstance(payload, dict):
        for m in payload.get("media") or []:
            if m.get("url"):
                content.append({
                    "type": "resource_link", "uri": m["url"],
                    "name": f"{m.get('kind', 'media')}-{m.get('id', '')}",
                    **({"mimeType": m["content_type"]} if m.get("content_type") else {}),
                })
    out = {"content": content, "isError": is_error}
    if isinstance(payload, dict) and not is_error:
        out["structuredContent"] = payload
    return out


# --- JSON-RPC endpoint -------------------------------------------------------


def _rpc_error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle_message(outer, msg):
    """One JSON-RPC message → a response dict, or None for notifications."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _rpc_error(None, -32600, "Invalid Request")
    method = msg.get("method")
    rid = msg.get("id")
    is_notification = "id" not in msg
    params = msg.get("params") or {}

    if is_notification:
        return None
    if method == "initialize":
        want = params.get("protocolVersion")
        version = want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "inference-club", "title": "inference.club",
                           "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        if name not in _TOOL_NAMES:
            return _rpc_error(rid, -32602, f"Unknown tool: {name}")
        args = params.get("arguments") or {}
        try:
            result = _tool_result(call_tool(outer, name, args))
        except ToolError as e:
            result = _tool_result(str(e), is_error=True)
        except Exception as e:  # never 500 an MCP client; report as a tool error
            logger.exception("mcp tool %s failed", name)
            result = _tool_result(f"Internal error running {name}: {e}", is_error=True)
        return {"jsonrpc": "2.0", "id": rid, "result": result}
    if method in ("resources/list", "prompts/list"):
        key = method.split("/")[0]
        return {"jsonrpc": "2.0", "id": rid, "result": {key: []}}
    return _rpc_error(rid, -32601, f"Method not found: {method}")


class MCPView(APIView):
    """``POST /mcp`` — stateless Streamable-HTTP MCP endpoint (JSON responses).
    ``GET`` (server→client SSE stream) isn't offered: 405, per the spec."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "This MCP server does not offer an SSE stream; POST "
                                   "JSON-RPC messages."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def post(self, request):
        msg = request.data
        outer = request._request
        outer.user = request.user
        if isinstance(msg, list):  # legacy JSON-RPC batch (2025-03-26)
            out = [r for r in (handle_message(outer, m) for m in msg) if r is not None]
            return Response(out) if out else Response(status=status.HTTP_202_ACCEPTED)
        resp = handle_message(outer, msg)
        if resp is None:
            return Response(status=status.HTTP_202_ACCEPTED)
        return Response(resp)
