#!/usr/bin/env python3
"""ic — a tiny, dependency-free CLI for the inference.club API, built for AI agents.

Every command prints ONE JSON object on stdout (progress goes to stderr), so an
agent can parse the result. Generations use ``async: "auto"``: they run right
away if a GPU slot is free, otherwise they are queued server-side, and ``ic``
waits for the job (polling with backoff) up to ``--timeout`` seconds. It never
hammers a busy device: 429 responses are retried only after ``Retry-After``.

Auth / config (environment):
  INFERENCE_CLUB_API_KEY   required — Dashboard → Settings → Token
  INFERENCE_CLUB_BASE_URL  default https://api.inference.club (with or without /v1)

Examples:
  ic.py models --type image
  ic.py image "a watercolor fox" -o fox.png
  ic.py video "a timelapse of clouds over mountains" -o clouds.mp4
  ic.py music "lofi hip hop, mellow piano" --duration 60 -o song.mp3
  ic.py speech "Hello there" -o hello.wav
  ic.py chat "Summarize the plot of Hamlet in 2 sentences"
  ic.py job 123 --wait -o out/
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

VERSION = "1.0.0"
TERMINAL = ("PROCESSED", "FAILED", "CANCELED")


# --- plumbing -----------------------------------------------------------------


def log(*a):
    print("[ic]", *a, file=sys.stderr, flush=True)


def out(obj, code=0):
    print(json.dumps(obj, indent=1, ensure_ascii=False))
    sys.exit(code)


def fail(message, **extra):
    out({"ok": False, "error": message, **extra}, code=1)


def base_url():
    b = (os.environ.get("INFERENCE_CLUB_BASE_URL") or "https://api.inference.club").rstrip("/")
    if b.endswith("/v1"):
        b = b[:-3]
    return b


def api_key():
    k = os.environ.get("INFERENCE_CLUB_API_KEY") or os.environ.get("INFERENCE_CLUB_TOKEN")
    if not k:
        fail("INFERENCE_CLUB_API_KEY is not set. Get a key at "
             "https://inference.club/dashboard/settings/token and export it.")
    return k


class HTTPError(Exception):
    def __init__(self, status, body, headers):
        self.status, self.body, self.headers = status, body, headers
        super().__init__(f"HTTP {status}")

    def message(self):
        b = self.body
        if isinstance(b, dict):
            e = b.get("error")
            if isinstance(e, dict):
                return f"{e.get('type', 'error')}: {e.get('message', '')}"
            if isinstance(e, str):
                return e
            if b.get("detail"):
                return str(b["detail"])
        return f"HTTP {self.status}: {str(b)[:300]}"

    def etype(self):
        if isinstance(self.body, dict) and isinstance(self.body.get("error"), dict):
            return self.body["error"].get("type")
        return None


def _request(method, path, *, body=None, data=None, ctype=None, query=None, timeout=900):
    url = base_url() + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    headers = {"Authorization": f"Bearer {api_key()}", "Accept": "application/json",
               "User-Agent": f"inference-club-cli/{VERSION}"}
    if body is not None:
        data = json.dumps(body).encode()
        ctype = "application/json"
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            hdrs = dict(r.headers)
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw or b"null")
        except ValueError:
            parsed = raw.decode("utf-8", "replace")
        raise HTTPError(e.code, parsed, dict(e.headers)) from None
    except urllib.error.URLError as e:
        fail(f"Could not reach {base_url()}: {e.reason}")
    except (OSError, ConnectionError) as e:  # dropped connection, timeout
        fail(f"Connection to {base_url()} failed mid-request: {e!r}. If this was a "
             "generation, check `ic.py jobs --active` before retrying.")
    ct = hdrs.get("Content-Type", "")
    if "text/html" in ct:
        fail(f"{base_url()} answered {path} with an HTML page, not the API — check "
             "INFERENCE_CLUB_BASE_URL (it should point at the API host, e.g. "
             "https://api.inference.club).")
    if "json" in ct:
        return status, json.loads(raw or b"null"), hdrs
    return status, raw, hdrs


def call(method, path, *, retries=3, **kw):
    """HTTP call that honors 429 Retry-After (capacity or rate limit)."""
    for attempt in range(retries + 1):
        try:
            return _request(method, path, **kw)
        except HTTPError as e:
            if e.status == 429 and attempt < retries:
                wait = int(float(e.headers.get("Retry-After") or 10))
                log(f"{e.etype() or 'rate_limited'} — waiting {wait}s before retrying "
                    f"({attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise


def multipart(fields, files):
    """fields: [(name, value)], files: [(name, path)] → (bytes, content_type)."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                     f"{value}\r\n".encode())
    for name, path in files:
        with open(path, "rb") as f:
            content = f.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        fn = os.path.basename(path)
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                     f'filename="{fn}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


# --- models / defaults -------------------------------------------------------


def list_models(service_type=None):
    _, d, _ = call("GET", "/v1/models")
    rows = (d or {}).get("data", [])
    if service_type:
        rows = [m for m in rows if m.get("service_type") == service_type]
    return rows


def pick_model(service_type, explicit):
    if explicit:
        return explicit
    rows = list_models(service_type)
    if not rows:
        fail(f"No {service_type} model is available to this account right now.",
             hint="Run `ic.py models` to see what is online.")
    log(f"using {service_type} model {rows[0]['id']}")
    return rows[0]["id"]


# --- jobs / media ------------------------------------------------------------


def summarize_job(job):
    st = job.get("status")
    s = {"ok": st == "PROCESSED", "job_id": str(job.get("id")), "status": st,
         "inference_type": job.get("inference_type"), "model": job.get("model_name")}
    if st == "PROCESSED":
        s["media"] = job.get("media") or []
        if job.get("output_text"):
            s["text"] = job["output_text"]
    elif st in ("FAILED", "CANCELED"):
        s["error"] = job.get("error")
    else:
        s["hint"] = f"Still running. Check later with: ic.py job {job.get('id')} --wait"
    return s


def wait_job(job_id, timeout):
    deadline = time.monotonic() + timeout
    delay, last = 3.0, None
    while True:
        _, job, _ = call("GET", f"/v1/jobs/{job_id}")
        st = job.get("status")
        if st != last:
            log(f"job {job_id}: {st}")
            last = st
        if st in TERMINAL or time.monotonic() + delay > deadline:
            return job
        time.sleep(delay)
        delay = min(delay * 1.5, 15.0)


def download(media, dest):
    """Save media items. ``dest`` is a file path (single item) or a directory."""
    saved = []
    many = len(media) > 1 or dest.endswith(os.sep) or os.path.isdir(dest)
    for i, m in enumerate(media):
        url = m.get("url")
        if not url:
            continue
        if many:
            os.makedirs(dest, exist_ok=True)
            ext = mimetypes.guess_extension((m.get("content_type") or "").split(";")[0]) or ""
            path = os.path.join(dest, f"{m.get('kind', 'media')}-{m.get('id', i)}{ext}")
        else:
            path = dest
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        headers = {"User-Agent": f"inference-club-cli/{VERSION}"}
        # Only send our key to our own host (private assets are gated there).
        if urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(base_url()).netloc:
            headers["Authorization"] = f"Bearer {api_key()}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
            f.write(r.read())
        m["saved_to"] = os.path.abspath(path)
        saved.append(path)
    return saved


def finish(status, data, args, *, kind=None, model=None):
    """Turn a 200 / 202 generation response into the final JSON result."""
    if status == 202:
        log(f"queued as job {data['id']} ({data.get('queued_reason', 'requested')}); waiting…")
        job = wait_job(data["id"], args.timeout)
        res = summarize_job(job)
        if data.get("queued_reason"):
            res["queued_reason"] = data["queued_reason"]
    else:
        media = []
        for item in (data or {}).get("data") or []:
            if item.get("url"):
                m = dict(item)
                if kind and not m.get("kind"):
                    m["kind"] = kind
                m.pop("b64_json", None)
                media.append(m)
        res = {"ok": True, "status": "PROCESSED", "request_id": str(data.get("id") or
                                                                    data.get("request_id") or ""),
               "model": data.get("model") or model, "media": media}
    if res.get("ok") and getattr(args, "output", None) and res.get("media"):
        download(res["media"], args.output)
    out(res, 0 if res.get("ok") or res.get("status") not in ("FAILED", "CANCELED") else 1)


def extra_fields(pairs):
    """--set k=v (v parsed as JSON when possible)."""
    d = {}
    for p in pairs or []:
        if "=" not in p:
            fail(f"--set expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        try:
            d[k] = json.loads(v)
        except ValueError:
            d[k] = v
    return d


def share(args, body):
    if getattr(args, "visibility", None):
        body["visibility"] = args.visibility
    if getattr(args, "collection", None):
        body["collection"] = args.collection
    return body


def generate(path, body, args, *, kind=None):
    body["async"] = "auto"
    try:
        status, data, _ = call("POST", path, body=body)
    except HTTPError as e:
        fail(e.message(), status=e.status, type=e.etype())
    finish(status, data, args, kind=kind, model=body.get("model"))


def read_text(v):
    if v and v.startswith("@"):
        with open(v[1:], encoding="utf-8") as f:
            return f.read()
    return v


# --- commands ----------------------------------------------------------------


def cmd_models(a):
    rows = list_models(a.type)
    keep = ("id", "service_type", "supported_features", "input_modalities",
            "output_modalities", "context_length", "owned_by")
    out({"ok": True, "models": [{k: m[k] for k in keep if m.get(k) not in (None, [])}
                                for m in rows]})


def cmd_doctor(a):
    """Check config without printing secrets."""
    k = os.environ.get("INFERENCE_CLUB_API_KEY") or os.environ.get("INFERENCE_CLUB_TOKEN") or ""
    res = {"base_url": base_url(), "api_key_set": bool(k),
           "api_key": (k[:4] + "…" + k[-2:]) if len(k) > 8 else None}
    if not k:
        out({"ok": False, **res, "error": "INFERENCE_CLUB_API_KEY is not set."}, 1)
    try:
        rows = list_models()
    except HTTPError as e:
        out({"ok": False, **res, "error": e.message(), "status": e.status}, 1)
    types = {}
    for m in rows:
        types[m.get("service_type")] = types.get(m.get("service_type"), 0) + 1
    out({"ok": True, **res, "authenticated": True, "models_by_type": types})


def cmd_capacity(a):
    _, d, _ = call("GET", "/v1/capacity", query={"service_type": a.type})
    out({"ok": True, "capacity": d.get("data", [])})


def cmd_image(a):
    body = share(a, {"model": pick_model("image", a.model), "prompt": a.prompt,
                     **extra_fields(a.set)})
    for k in ("size", "n", "seed", "negative_prompt", "background", "steps"):
        if getattr(a, k, None) is not None:
            body[k] = getattr(a, k)
    generate("/v1/images/generations", body, a, kind="image")


def cmd_edit(a):
    fields = [("model", pick_model("image", a.model)), ("prompt", a.prompt)]
    for k, v in extra_fields(a.set).items():
        fields.append((k, v if isinstance(v, str) else json.dumps(v)))
    if a.size:
        fields.append(("size", a.size))
    name = "image[]" if len(a.image) > 1 else "image"
    data, ctype = multipart(fields, [(name, p) for p in a.image])
    try:
        status, d, _ = call("POST", "/v1/images/edits", data=data, ctype=ctype)
    except HTTPError as e:
        fail(e.message(), status=e.status, type=e.etype())
    finish(status, d, a, kind="image")


def _image_ref(v):
    if not v or v.startswith(("http://", "https://", "data:")):
        return v
    ctype = mimetypes.guess_type(v)[0] or "image/png"
    with open(v, "rb") as f:
        return f"data:{ctype};base64," + base64.b64encode(f.read()).decode()


def cmd_video(a):
    body = share(a, {"model": pick_model("video", a.model), "prompt": a.prompt,
                     "delivery": "url", **extra_fields(a.set)})
    if a.image:
        body["image"] = _image_ref(a.image)
    for k in ("width", "height", "num_frames", "fps", "seed"):
        if getattr(a, k, None) is not None:
            body[k] = getattr(a, k)
    generate("/v1/videos/generations", body, a, kind="video")


def cmd_music(a):
    body = share(a, {"model": pick_model("music", a.model), "prompt": a.prompt,
                     "lyrics": read_text(a.lyrics) or "[instrumental]", "delivery": "url",
                     **extra_fields(a.set)})
    if a.duration:
        body["audio_duration"] = a.duration
    if a.seed is not None:
        body["seed"] = a.seed
    generate("/v1/music/generations", body, a, kind="audio")


def _is_dialogue(m):
    feats = set(m.get("supported_features") or [])
    return bool(feats & {"dialogue", "voice-cloning"})


def cmd_speech(a):
    rows = list_models("tts")
    if a.model:
        chosen = next((m for m in rows if m["id"] == a.model), {"id": a.model})
    else:
        # Prefer a plain TTS voice model; dialogue models (Dia) are the fallback.
        rows.sort(key=_is_dialogue)
        if not rows:
            fail("No tts model is available to this account right now.")
        chosen = rows[0]
        log(f"using tts model {chosen['id']}")
    text = read_text(a.text)
    if _is_dialogue(chosen):
        # Dia-style dialogue models speak [S1]/[S2]-tagged scripts via
        # /v1/voice/generations (synchronous; ic retries on 429 at_capacity).
        if "[S1]" not in text and "[S2]" not in text:
            text = "[S1] " + text
        body = share(a, {"model": chosen["id"], "input": text, "delivery": "url",
                         **extra_fields(a.set)})
        generate("/v1/voice/generations", body, a, kind="audio")
    body = share(a, {"model": chosen["id"], "input": text, "delivery": "url",
                     **extra_fields(a.set)})
    if a.voice:
        body["voice"] = a.voice
    generate("/v1/audio/speech", body, a, kind="audio")


def cmd_voices(a):
    _, d, _ = call("GET", "/v1/audio/voices", query={"model": pick_model("tts", a.model)})
    out({"ok": True, **(d if isinstance(d, dict) else {"voices": d})})


def cmd_transcribe(a):
    fields = [("model", pick_model("stt", a.model))]
    if a.language:
        fields.append(("language", a.language))
    data, ctype = multipart(fields, [("file", a.file)])
    try:
        _, d, _ = call("POST", "/v1/audio/transcriptions", data=data, ctype=ctype)
    except HTTPError as e:
        fail(e.message(), status=e.status, type=e.etype())
    out({"ok": True, "text": (d or {}).get("text"), "response": d})


def cmd_chat(a):
    messages = []
    if a.system:
        messages.append({"role": "system", "content": read_text(a.system)})
    messages.append({"role": "user", "content": read_text(a.prompt)})
    body = {"model": pick_model("llm", a.model), "messages": messages, "stream": False,
            **extra_fields(a.set)}
    if a.max_tokens:
        body["max_tokens"] = a.max_tokens
    body["async"] = "auto"
    try:
        status, d, _ = call("POST", "/v1/chat/completions", body=body)
    except HTTPError as e:
        fail(e.message(), status=e.status, type=e.etype())
    if status == 202:
        out(summarize_job(wait_job(d["id"], a.timeout)))
    msg = ((d.get("choices") or [{}])[0].get("message") or {})
    out({"ok": True, "model": d.get("model") or body["model"], "text": msg.get("content"),
         "usage": d.get("usage")})


def cmd_scrape(a):
    body = {"url": a.url, "model": pick_model("scrape", a.model), "async": "auto"}
    try:
        status, d, _ = call("POST", "/v1/scrape", body=body)
    except HTTPError as e:
        fail(e.message(), status=e.status, type=e.etype())
    if status == 202:
        out(summarize_job(wait_job(d["id"], a.timeout)))
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(d.get("markdown") or "")
    out({"ok": True, "title": d.get("title"), "source_url": d.get("source_url"),
         "chars": d.get("chars"),
         "markdown": None if a.output else d.get("markdown"),
         **({"saved_to": os.path.abspath(a.output)} if a.output else {})})


def cmd_job(a):
    try:
        if a.wait:
            job = wait_job(a.id, a.timeout)
        else:
            _, job, _ = call("GET", f"/v1/jobs/{a.id}")
    except HTTPError as e:
        fail(e.message(), status=e.status)
    res = summarize_job(job)
    if res.get("ok") and a.output and res.get("media"):
        download(res["media"], a.output)
    out(res)


def cmd_jobs(a):
    _, d, _ = call("GET", "/v1/jobs", query={"active": "1" if a.active else None,
                                             "limit": str(a.limit)})
    rows = d.get("results", d) if isinstance(d, dict) else d
    out({"ok": True, "jobs": [summarize_job(j) for j in rows or []]})


def cmd_cancel(a):
    try:
        _, d, _ = call("POST", f"/v1/jobs/{a.id}/cancel")
    except HTTPError as e:
        fail(e.message(), status=e.status)
    out({"ok": True, **d})


def cmd_workflow(a):
    if a.action == "templates":
        _, d, _ = call("GET", "/v1/workflows/templates")
        out({"ok": True, **(d if isinstance(d, dict) else {"templates": d})})
    if a.action == "run":
        if not a.key:
            fail("usage: ic.py workflow run <template-key> --input k=v ...")
        body = share(a, {"template": a.key, "inputs": extra_fields(a.input)})
        try:
            _, d, _ = call("POST", "/v1/workflows/runs", body=body)
        except HTTPError as e:
            fail(e.message(), status=e.status)
        out({"ok": True, "run_id": d.get("id"), "status": d.get("status"),
             "hint": f"Check progress with: ic.py workflow status {d.get('id')}"})
    if a.action == "status":
        _, d, _ = call("GET", f"/v1/workflows/runs/{a.key}")
        steps = [{"step_id": s.get("step_id"), "status": s.get("status"),
                  "media": [m for j in s.get("jobs") or [] for m in j.get("media") or []]}
                 for s in d.get("steps") or []]
        out({"ok": d.get("status") == "DONE", "run_id": d.get("id"), "status": d.get("status"),
             "steps": steps})


# --- argparse ----------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(prog="ic.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    def gen(name, help_, fn):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--model", "-m")
        s.add_argument("--output", "-o", help="Save result to this file (or directory).")
        s.add_argument("--timeout", type=int, default=900,
                       help="Max seconds to wait for a queued job (default 900).")
        s.add_argument("--set", action="append", metavar="KEY=VALUE",
                       help="Extra model-specific field (repeatable).")
        s.add_argument("--visibility", choices=["PUBLIC", "UNLISTED", "PRIVATE", "SECRET"])
        s.add_argument("--collection")
        s.set_defaults(fn=fn)
        return s

    sp = sub.add_parser("doctor", help="Check API key + connectivity (key is masked).")
    sp.set_defaults(fn=cmd_doctor)
    sp = sub.add_parser("models", help="List available models.")
    sp.add_argument("--type", help="llm|image|video|music|tts|stt|mesh|scrape|audio-enhance")
    sp.set_defaults(fn=cmd_models)
    sp = sub.add_parser("capacity", help="Live GPU load per model.")
    sp.add_argument("--type")
    sp.set_defaults(fn=cmd_capacity)

    s = gen("image", "Text-to-image.", cmd_image)
    s.add_argument("prompt")
    s.add_argument("--size")
    s.add_argument("--n", type=int)
    s.add_argument("--seed", type=int)
    s.add_argument("--steps", type=int)
    s.add_argument("--negative-prompt", dest="negative_prompt")
    s.add_argument("--background", choices=["opaque", "transparent"])

    s = gen("edit", "Edit image(s) with a prompt.", cmd_edit)
    s.add_argument("prompt")
    s.add_argument("--image", "-i", action="append", required=True, help="Repeatable.")
    s.add_argument("--size")

    s = gen("video", "Text/image-to-video (slow).", cmd_video)
    s.add_argument("prompt")
    s.add_argument("--image", help="First frame: local file, URL or data: URI.")
    for k in ("width", "height", "num_frames", "fps", "seed"):
        s.add_argument(f"--{k.replace('_', '-')}", dest=k, type=int)

    s = gen("music", "Song / instrumental.", cmd_music)
    s.add_argument("prompt", help="Style tags, e.g. 'synthwave, female vocals'.")
    s.add_argument("--lyrics", help="Lyrics text or @file. Default [instrumental].")
    s.add_argument("--duration", type=float, help="Seconds.")
    s.add_argument("--seed", type=int)

    s = gen("speech", "Text-to-speech.", cmd_speech)
    s.add_argument("text", help="Text or @file.")
    s.add_argument("--voice")

    sp = sub.add_parser("voices", help="List voices for a TTS model.")
    sp.add_argument("--model", "-m")
    sp.set_defaults(fn=cmd_voices)

    sp = sub.add_parser("transcribe", help="Speech-to-text from an audio file.")
    sp.add_argument("file")
    sp.add_argument("--model", "-m")
    sp.add_argument("--language")
    sp.set_defaults(fn=cmd_transcribe)

    s = gen("chat", "Ask an LLM.", cmd_chat)
    s.add_argument("prompt", help="Text or @file.")
    s.add_argument("--system")
    s.add_argument("--max-tokens", dest="max_tokens", type=int)

    s = gen("scrape", "URL → markdown.", cmd_scrape)
    s.add_argument("url")

    sp = sub.add_parser("job", help="Get (or --wait for) a job.")
    sp.add_argument("id")
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--timeout", type=int, default=900)
    sp.add_argument("--output", "-o")
    sp.set_defaults(fn=cmd_job)
    sp = sub.add_parser("jobs", help="List recent jobs.")
    sp.add_argument("--active", action="store_true")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(fn=cmd_jobs)
    sp = sub.add_parser("cancel", help="Cancel a job.")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_cancel)

    sp = sub.add_parser("workflow", help="templates | run <key> --input k=v | status <run_id>")
    sp.add_argument("action", choices=["templates", "run", "status"])
    sp.add_argument("key", nargs="?")
    sp.add_argument("--input", action="append", metavar="KEY=VALUE")
    sp.add_argument("--visibility", choices=["PUBLIC", "UNLISTED", "PRIVATE", "SECRET"])
    sp.add_argument("--collection")
    sp.set_defaults(fn=cmd_workflow)

    a = p.parse_args()
    try:
        a.fn(a)
    except HTTPError as e:
        fail(e.message(), status=e.status, type=e.etype())
    except KeyboardInterrupt:
        fail("interrupted")


if __name__ == "__main__":
    main()
