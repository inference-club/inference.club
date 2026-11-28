#!/usr/bin/env python3
"""Make the homepage showcase from scripts/showcase/showcase.json.

Every item names its model, prompt and seed, so running this against another
deployment makes the same pieces there. Each result is titled, made public,
filed in the "Showcase" collection and (with --static) saved under
frontend/public/showcase/ with an index.json the homepage reads.

    scripts/showcase/generate.py --instance local --static
    scripts/showcase/generate.py --instance production          # same seeds
    scripts/showcase/generate.py --instance local --only brass-jack --force

Deployments come from the CLI's saved instances
(integrations/skills/inference-club/scripts/ic.py instance add ...). The index
records a SHA-256 of each raw output; a later run reports whether its output
is byte-identical to the recorded one.

Needs `cwebp` and `ffmpeg` on PATH for --static. Standard library only.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = os.path.join(ROOT, "scripts", "showcase", "showcase.json")
STATIC = os.path.join(ROOT, "frontend", "public", "showcase")
INDEX = os.path.join(STATIC, "index.json")
INSTANCES = os.path.expanduser("~/.config/inference-club/instances.json")


def say(*a):
    print(*a, file=sys.stderr, flush=True)


class Club:
    def __init__(self, name):
        cfg = json.load(open(INSTANCES))
        inst = cfg["instances"].get(name)
        if not inst:
            sys.exit(f"No saved instance '{name}'. Add it with ic.py instance add.")
        self.base, self.key = inst["base_url"].rstrip("/"), inst["api_key"]

    def call(self, method, path, body=None, timeout=900, raw=False):
        url = path if path.startswith("http") else self.base + path
        req = urllib.request.Request(url, method=method)
        # The key goes only to the deployment itself. Public media may be
        # served straight from a storage bucket, which rejects (and should
        # never be sent) the club's key.
        if url.startswith(self.base):
            req.add_header("Authorization", f"Bearer {self.key}")
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
                blob = r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} -> {e.code}: {e.read()[:300]!r}") from None
        if raw:
            return blob
        return json.loads(blob) if blob else {}

    def job(self, result):
        """Wait out a queued generation and return its finished result."""
        while result.get("object") == "job" or result.get("status") in ("QUEUED", "PROCESSING"):
            job_id = result.get("job_id") or result.get("id")
            time.sleep(4)
            result = self.call("GET", f"/v1/jobs/{job_id}")
            if result.get("status") in ("FAILED", "CANCELED", "REQUESTED"):
                raise RuntimeError(f"job {job_id} {result.get('status')}")
        return result


def generate(club, item):
    """Run one manifest item. Returns (request_id, output_url or None, text)."""
    kind, share = item["kind"], {"visibility": "PUBLIC"}
    if kind == "image":
        r = club.call("POST", "/v1/images/generations", {
            "model": item["model"], "prompt": item["prompt"],
            "size": item.get("size", "1024x1024"), "seed": item["seed"], **share})
        return str(r["request_id"]), r["data"][0]["url"], None
    if kind == "music":
        r = club.job(club.call("POST", "/v1/music/generations", {
            "model": item["model"], "prompt": item["prompt"], "lyrics": item["lyrics"],
            "audio_duration": item["duration"], "seed": item["seed"],
            "use_random_seed": False, "title": item["title"], "delivery": "url", **share}))
        return str(r["id"]), r["data"][0]["url"], None
    if kind == "video":
        r = club.job(club.call("POST", "/v1/videos/generations", {
            "model": item["model"], "prompt": item["prompt"], "duration": item["duration"],
            "seed": item["seed"], "async": "auto", "delivery": "url", **share}))
        return str(r["id"]), r["data"][0]["url"], None
    if kind == "speech":
        r = club.call("POST", "/v1/audio/speech", {
            "model": item["model"], "input": item["input"], "voice": item.get("voice"),
            "response_format": "wav", "delivery": "url", **share})
        return str(r["id"]), r["data"][0]["url"], None
    if kind == "chat":
        r = club.call("POST", "/v1/chat/completions", {
            "model": item["model"], "seed": item["seed"], "temperature": 0.7,
            "max_tokens": 300, "messages": [{"role": "user", "content": item["prompt"]}],
            "chat_template_kwargs": {"enable_thinking": False}, **share})
        text = r["choices"][0]["message"]["content"].strip()
        newest = club.call("GET", "/api/inference/requests/?limit=1&type=LLM")["results"][0]
        return str(newest["id"]), None, text
    if kind == "logprobs":
        # A short answer with the model's own probability for every token and
        # the alternatives it weighed; the homepage animates this.
        r = club.call("POST", "/v1/chat/completions", {
            "model": item["model"], "seed": item["seed"], "temperature": 0.8,
            "max_tokens": 40, "logprobs": True, "top_logprobs": 5,
            "messages": [{"role": "user", "content": item["prompt"]}],
            "chat_template_kwargs": {"enable_thinking": False}, **share})
        import math
        tokens = [
            {"t": t["token"], "p": round(math.exp(t["logprob"]), 4),
             "alts": [{"t": x["token"], "p": round(math.exp(x["logprob"]), 4)}
                      for x in t.get("top_logprobs", [])[:5]]}
            for t in (r["choices"][0].get("logprobs") or {}).get("content") or []
        ]
        newest = club.call("GET", "/api/inference/requests/?limit=1&type=LLM")["results"][0]
        return str(newest["id"]), None, json.dumps(tokens, ensure_ascii=False)
    raise ValueError(kind)


def save_static(item, blob):
    """Write web-sized copies under frontend/public/showcase/. Returns names."""
    os.makedirs(STATIC, exist_ok=True)
    stem = os.path.join(STATIC, item["id"])
    tmp = stem + ".src"
    open(tmp, "wb").write(blob)
    run = lambda *c: subprocess.run(c, check=True, capture_output=True)  # noqa: E731
    files = {}
    try:
        if item["kind"] == "image":
            run("cwebp", "-quiet", "-q", "82", "-resize", "1280", "0", tmp, "-o", stem + ".webp")
            run("cwebp", "-quiet", "-q", "78", "-resize", "560", "0", tmp, "-o", stem + "-sm.webp")
            files = {"src": f"{item['id']}.webp", "thumb": f"{item['id']}-sm.webp"}
        elif item["kind"] in ("music", "speech"):
            run("ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-b:a", "128k", stem + ".mp3")
            files = {"src": f"{item['id']}.mp3"}
        elif item["kind"] == "video":
            run("ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-vf", "scale=960:-2",
                "-c:v", "libx264", "-crf", "26", "-preset", "slow", "-movflags", "+faststart",
                "-c:a", "aac", "-b:a", "96k", stem + ".mp4")
            run("ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-frames:v", "1", stem + "-poster.png")
            run("cwebp", "-quiet", "-q", "80", stem + "-poster.png", "-o", stem + "-poster.webp")
            os.remove(stem + "-poster.png")
            files = {"src": f"{item['id']}.mp4", "poster": f"{item['id']}-poster.webp"}
    finally:
        os.remove(tmp)
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", "-I", required=True)
    ap.add_argument("--only", default="", help="Comma-separated item ids.")
    ap.add_argument("--force", action="store_true", help="Regenerate items already made here.")
    ap.add_argument("--static", action="store_true", help="Write frontend/public/showcase/.")
    a = ap.parse_args()

    club = Club(a.instance)
    manifest = json.load(open(MANIFEST))
    only = {s for s in a.only.split(",") if s}
    state_path = os.path.join(ROOT, ".captures", "showcase", f"{a.instance}.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    index = json.load(open(INDEX)) if os.path.exists(INDEX) else {"items": []}
    by_id = {e["id"]: e for e in index["items"]}

    # The collection everything is filed in.
    col = manifest["collection"]
    cols = club.call("GET", "/api/inference/collections/")
    cols = cols if isinstance(cols, list) else cols.get("results", [])
    found = next((c for c in cols if c["name"] == col["name"]), None)
    if not found:
        found = club.call("POST", "/api/inference/collections/", {**col, "visibility": "PUBLIC"})
    slug = found["slug"]

    # Pieces dropped from the manifest leave the collection (the requests
    # themselves stay in the library).
    wanted = {i["id"] for i in manifest["items"]}
    for gone in sorted(set(state) - wanted):
        try:
            club.call("DELETE", f"/api/inference/collections/{slug}/items/{state[gone]['request_id']}/")
        except RuntimeError:
            pass
        del state[gone]
        say(f"  gone  {gone} (no longer in the manifest)")
    json.dump(state, open(state_path, "w"), indent=1)

    for item in manifest["items"]:
        iid = item["id"]
        if only and iid not in only:
            continue
        if iid in state and not a.force:
            say(f"  have  {iid} (request {state[iid]['request_id']})")
            continue
        t0 = time.time()
        try:
            rid, url, text = generate(club, item)
        except Exception as e:  # noqa: BLE001 - keep going; report at the end
            say(f"  FAIL  {iid}: {str(e)[:200]}")
            continue
        if iid in state:  # --force: the earlier take leaves the collection
            try:
                club.call("DELETE", f"/api/inference/collections/{slug}/items/{state[iid]['request_id']}/")
            except RuntimeError:
                pass
        blob = club.call("GET", url, raw=True) if url else (text or "").encode()
        sha = hashlib.sha256(blob).hexdigest()
        club.call("PATCH", f"/api/inference/requests/{rid}/title/", {"title": item["title"]})
        club.call("PATCH", f"/api/inference/requests/{rid}/", {"visibility": "PUBLIC"})
        if not iid.startswith("cover-"):
            club.call("POST", f"/api/inference/collections/{slug}/items/{rid}/")
        cover = item.get("cover")
        if cover and cover in state:
            club.call("PATCH", f"/api/inference/requests/{rid}/cover/",
                      {"cover_request_id": int(state[cover]["request_id"])})
        d = club.call("GET", f"/api/inference/requests/{rid}/")
        host = d.get("host") or {}
        gpus = [host["gpu"]] if host.get("gpu") else host.get("gpus") or []
        entry = {
            "id": iid, "kind": item["kind"], "title": item["title"], "model": item["model"],
            "prompt": item.get("prompt") or item.get("input"),
            "seed": (d.get("payload") or {}).get("seed", item.get("seed")),
            "gpu": (gpus[0].get("model") if gpus else None),
            "seconds": round((d.get("latency_ms") or 0) / 1000, 1) or None,
            "length": d.get("audio_seconds") or (d.get("video") or {}).get("seconds"),
            "sha256": sha,
        }
        if item["kind"] == "image":
            # Lets the page reserve the picture's space before it loads.
            entry["size"] = item.get("size", "1024x1024")
        if item.get("lyrics") and item["lyrics"] != "[instrumental]":
            entry["lyrics"] = item["lyrics"]
        if text and item["kind"] == "logprobs":
            entry["tokens"] = json.loads(text)
            entry["text"] = "".join(t["t"] for t in entry["tokens"]).strip()
        elif text:
            entry["text"] = text
        if cover:
            entry["cover"] = f"{cover}.webp"
        same = by_id.get(iid, {}).get("sha256")
        verdict = "" if not same else (" identical to recorded" if same == sha else " DIFFERS from recorded")
        if a.static:
            if url:
                entry.update(save_static(item, blob))
            by_id[iid] = entry
        state[iid] = {"request_id": rid, "share_token": d.get("share_token"), "sha256": sha}
        json.dump(state, open(state_path, "w"), indent=1)
        say(f"  made  {iid} request {rid} in {time.time() - t0:.0f}s seed {entry['seed']} "
            f"on {entry['gpu']}{verdict}")

    if a.static:
        order = [i["id"] for i in manifest["items"]]
        for name in os.listdir(STATIC):
            stem = name.split(".")[0].removesuffix("-sm").removesuffix("-poster")
            if name != "index.json" and stem not in order:
                os.remove(os.path.join(STATIC, name))
        index = {"collection": col, "items": [by_id[i] for i in order if i in by_id]}
        json.dump(index, open(INDEX, "w"), indent=1, ensure_ascii=False)
        open(INDEX, "a").write("\n")
    print(json.dumps({"ok": True, "instance": a.instance, "collection": slug,
                      "made": sorted(state)}))


if __name__ == "__main__":
    main()
