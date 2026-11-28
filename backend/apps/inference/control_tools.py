"""Control tools: everything an assistant can do to an account besides plain
generation — read and edit the library, collections, covers, settings and
service access, play music, open pages, and call any other endpoint.

One definition serves every surface:

- the remote MCP server (``mcp_server.py``) lists them next to the generation
  tools, so Claude, Hermes and other MCP clients get them;
- the in-app assistant (``assistant.py``) offers the same set to the model that
  drives the assistant panel;
- the ``ic`` CLI reaches them through MCP ``tools/call``.

A tool never touches the ORM. It calls the same HTTP view the web app calls,
in-process, as the caller — so permissions, validation, visibility rules and
throttles are exactly the app's, and there is one place to change behaviour.

Every handler returns a dict with a ``summary``: one sentence, past tense,
saying what happened. Assistants read that back to the person.
"""
import json
import logging
import re

from django.conf import settings
from django.test import RequestFactory
from django.urls import Resolver404, resolve

logger = logging.getLogger("django")


class ToolError(Exception):
    """A handled failure. The message goes back to the model as the result."""


# --- calling the app's own views ---------------------------------------------


_FORWARDED_META = (
    "HTTP_AUTHORIZATION", "HTTP_HOST", "HTTP_X_FORWARDED_HOST",
    "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_FOR", "REMOTE_ADDR",
    "SERVER_NAME", "SERVER_PORT",
)


def internal(outer, method, path, body=None, query=None):
    """Call one of this app's views in-process as ``outer.user``.

    Returns ``(status_code, data, response)``; ``data`` is the parsed JSON body
    or None. The caller's host and scheme are carried over so absolute media
    URLs point at the address the client is really using. Authentication is
    forced to the already-authenticated caller, which makes this work the same
    for a Bearer-token MCP client and a cookie-session browser.
    """
    rf = RequestFactory()
    meta = {k: v for k, v in outer.META.items() if k in _FORWARDED_META}
    secure = outer.is_secure()
    method = method.upper()
    if method == "GET":
        req = rf.get(path, data=query or {}, secure=secure, **meta)
    else:
        if query:
            from urllib.parse import urlencode

            path = f"{path}?{urlencode(query)}"
        req = rf.generic(
            method, path, data=json.dumps(body if body is not None else {}),
            content_type="application/json", secure=secure, **meta,
        )
    req._force_auth_user = outer.user  # DRF: skip authenticators, use this user
    req._dont_enforce_csrf_checks = True
    req.user = outer.user
    match = resolve(req.path)
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


def err_text(code, data):
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
        if code == 400:
            return f"400: {json.dumps(data)[:400]}"
    if code == 404:
        return "404: not found (or not yours)."
    return f"HTTP {code}"


def _ok(outer, method, path, body=None, query=None, accept=(200, 201, 202, 204)):
    code, data, _ = internal(outer, method, path, body, query)
    if code not in accept:
        raise ToolError(err_text(code, data))
    return data


# --- schema helpers ----------------------------------------------------------


def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": False}


_S = {"type": "string"}
_I = {"type": "integer"}
_B = {"type": "boolean"}
_VIS = {"type": "string", "enum": ["PUBLIC", "UNLISTED", "PRIVATE", "SECRET"],
        "description": "PUBLIC: everyone, listed. UNLISTED: anyone with the link. "
                       "PRIVATE: signed-in members. SECRET: only the owner."}
_ITEM = {**_I, "description": "Item id (the number from search_library)."}
_COLL = {**_S, "description": "Collection name or slug."}

_KINDS = {
    "song": "MUSIC", "music": "MUSIC", "image": "IMAGE", "picture": "IMAGE",
    "video": "VIDEO", "speech": "TTS", "tts": "TTS", "voice": "VOICE",
    "chat": "LLM", "text": "LLM", "llm": "LLM", "transcript": "STT", "stt": "STT",
    "3d": "MESH", "mesh": "MESH", "scrape": "SCRAPE",
}
_KIND_NAME = {"MUSIC": "song", "IMAGE": "image", "VIDEO": "video", "TTS": "speech",
              "VOICE": "speech", "LLM": "chat", "STT": "transcript", "MESH": "3d model",
              "SCRAPE": "scrape", "RENDER": "video", "ENHANCE": "audio"}


def _frontend(path):
    return settings.FRONTEND_BASE_URL.rstrip("/") + path


def _row(r):
    """A library row an assistant can act on and describe."""
    kind = _KIND_NAME.get(r.get("inference_type"), (r.get("inference_type") or "").lower())
    media = (r.get("output_audio_url") or r.get("video_url")
             or (r.get("image_urls") or [None])[0] or r.get("model_url"))
    out = {
        "id": r.get("id"),
        "kind": kind,
        "title": r.get("title") or (r.get("prompt_preview") or "")[:80] or f"{kind} {r.get('id')}",
        "status": r.get("status"),
        "visibility": r.get("visibility"),
        "created": (r.get("created_on") or "")[:16].replace("T", " "),
        "page": _frontend(f"/dashboard/inference/requests/{r.get('public_id') or r.get('id')}"),
    }
    if media:
        out["url"] = media
    if r.get("cover_image_url"):
        out["cover"] = r["cover_image_url"]
    if r.get("audio_seconds"):
        out["seconds"] = round(r["audio_seconds"])
    if r.get("is_starred"):
        out["starred"] = True
    if r.get("is_bookmarked"):
        out["bookmarked"] = True
    if r.get("owner") and not r.get("is_owner"):
        out["owner"] = r["owner"]
    return out


def _item_id(args, key="id"):
    try:
        return int(str(args.get(key)).strip())
    except (TypeError, ValueError):
        raise ToolError(f"`{key}` must be the numeric item id from search_library.")


def _item(outer, item_id):
    return _ok(outer, "GET", f"/api/inference/requests/{item_id}/")


def _cap(text):
    return text[:1].upper() + text[1:]


def _label(r):
    kind = _KIND_NAME.get(r.get("inference_type"), "item")
    name = r.get("title") or ""
    return f"{kind} “{name}”" if name else f"{kind} {r.get('id')}"


# --- confirming deletes ------------------------------------------------------
# A delete takes two calls: the first describes what would go and records that
# the person was asked; only a later call with confirm: true deletes. Inside the
# in-app assistant the second call must also come in a later turn, so a model
# cannot ask and answer itself in one go.

_CONFIRM_TTL = 600


def _confirmed(outer, what, args):
    from django.core.cache import cache

    key = f"ic-confirm:{outer.user.pk}:{what}"
    turn = getattr(outer, "_ic_turn", None)
    asked = cache.get(key)
    if args.get("confirm") and asked is not None and (turn is None or asked != turn):
        cache.delete(key)
        return True
    cache.set(key, turn or "asked", _CONFIRM_TTL)
    return False


# --- library -----------------------------------------------------------------


def _search_library(outer, args):
    scope = (args.get("scope") or "mine").lower()
    path = {
        "mine": "/api/inference/requests/",
        "starred": "/api/inference/requests/starred/",
        "bookmarked": "/api/inference/requests/bookmarked/",
        "everyone": "/api/inference/requests/all/",
    }.get(scope)
    if path is None:
        raise ToolError("scope must be mine, starred, bookmarked or everyone.")
    limit = max(1, min(int(args.get("limit") or 10), 50))
    q = {"limit": str(limit)}
    kind = (args.get("kind") or "").lower().strip()
    if kind and kind != "any":
        if kind not in _KINDS:
            raise ToolError(f"kind must be one of: {', '.join(sorted(set(_KINDS)))}.")
        q["type"] = _KINDS[kind]
    if args.get("query"):
        q["search"] = str(args["query"])
    if args.get("collection"):
        q["collection"] = str(args["collection"])
    if args.get("sort") == "popular":
        q["sort"] = "popular"
    data = _ok(outer, "GET", path, query=q)
    rows = [_row(r) for r in (data.get("results") or [])]
    total = data.get("count", len(rows))
    what = kind if kind and kind != "any" else "item"
    plural = {"speech": "speech clips", "3d": "3D models", "tts": "speech clips",
              "music": "songs", "stt": "transcripts", "llm": "chats"}.get(what, what + "s")
    single = {"speech": "speech clip", "tts": "speech clip", "3d": "3D model",
              "music": "song", "stt": "transcript", "llm": "chat"}.get(what, what)
    return {
        "summary": f"Found {total} {single if total == 1 else plural}"
                   + (f" matching “{args['query']}”" if args.get("query") else "")
                   + (f"; showing the newest {len(rows)}." if total > len(rows) else "."),
        "total": total, "items": rows,
    }


def _get_item(outer, args):
    r = _item(outer, _item_id(args))
    out = _row(r)
    payload = r.get("payload") or {}
    for k in ("prompt", "lyrics", "input"):
        if payload.get(k):
            out[k] = str(payload[k])[:1500]
    if r.get("model_name"):
        out["model"] = r["model_name"]
    return {"summary": f"{_cap(_label(r))} is {r.get('visibility', '').lower()}, "
                       f"status {r.get('status')}.", "item": out}


def _update_item(outer, args):
    item_id = _item_id(args)
    done = []
    if args.get("title") is not None:
        _ok(outer, "PATCH", f"/api/inference/requests/{item_id}/title/",
            {"title": args["title"]})
        done.append(f"renamed it to “{args['title']}”")
    if args.get("visibility"):
        _ok(outer, "PATCH", f"/api/inference/requests/{item_id}/",
            {"visibility": args["visibility"]})
        done.append(f"made it {args['visibility'].lower()}")
    if args.get("starred") is not None:
        _ok(outer, "POST" if args["starred"] else "DELETE",
            f"/api/inference/requests/{item_id}/star/")
        done.append("starred it" if args["starred"] else "removed the star")
    if args.get("bookmarked") is not None:
        _ok(outer, "POST" if args["bookmarked"] else "DELETE",
            f"/api/inference/requests/{item_id}/bookmark/")
        done.append("bookmarked it" if args["bookmarked"] else "removed the bookmark")
    if args.get("cover_item_id") is not None:
        _ok(outer, "PATCH", f"/api/inference/requests/{item_id}/cover/",
            {"cover_request_id": args["cover_item_id"] or None})
        done.append("set its cover" if args["cover_item_id"] else "cleared its cover")
    if not done:
        raise ToolError("Nothing to change: give title, visibility, starred, bookmarked "
                        "or cover_item_id.")
    r = _item(outer, item_id)
    return {"summary": f"{_cap(_label(r))}: {', '.join(done)}.", "item": _row(r)}


def _update_many(outer, args):
    """Apply one visibility to many items — by explicit ids or by a search."""
    vis = args.get("visibility")
    if not vis:
        raise ToolError("visibility is required.")
    ids = [int(i) for i in (args.get("item_ids") or [])]
    if not ids:
        found = _search_library(outer, {
            "kind": args.get("kind"), "query": args.get("query"),
            "collection": args.get("collection"), "limit": 50,
        })
        ids = [r["id"] for r in found["items"] if r.get("visibility") != vis]
    changed, failed = [], []
    for i in ids[:50]:
        code, data, _ = internal(outer, "PATCH", f"/api/inference/requests/{i}/",
                                 {"visibility": vis})
        (changed if code == 200 else failed).append(i)
    out = {"summary": f"Made {len(changed)} item{'' if len(changed) == 1 else 's'} "
                      f"{vis.lower()}" + (f"; {len(failed)} could not be changed." if failed else "."),
           "changed": changed}
    if failed:
        out["failed"] = failed
    return out


def _delete_item(outer, args):
    item_id = _item_id(args)
    r = _item(outer, item_id)
    if not r.get("is_owner"):
        raise ToolError("You can only delete your own items.")
    if not _confirmed(outer, f"item:{item_id}", args):
        return {"summary": f"Not deleted. Deleting {_label(r)} cannot be undone — ask the "
                           "person to confirm, then call again with confirm: true.",
                "needs_confirmation": True, "item": _row(r)}
    _ok(outer, "DELETE", f"/api/inference/requests/{item_id}/")
    return {"summary": f"Deleted {_label(r)}.", "deleted": item_id}


def _missing_covers(outer, args):
    if args.get("generate"):
        data = _ok(outer, "POST", "/api/inference/covers/missing/",
                   {"limit": args.get("limit") or 25})
        n = data.get("queued", 0)
        return {"summary": f"Queued cover art for {n} song{'' if n == 1 else 's'}.", **data}
    data = _ok(outer, "GET", "/api/inference/covers/missing/")
    n = data.get("missing", 0)
    return {"summary": f"{n} song{'' if n == 1 else 's'} have no cover art.", **data}


# --- collections -------------------------------------------------------------


def _collections(outer):
    data = _ok(outer, "GET", "/api/inference/collections/")
    return data.get("results", data) if isinstance(data, dict) else (data or [])


def _find_collection(outer, ref):
    ref = str(ref or "").strip()
    if not ref:
        raise ToolError("Which collection? Give its name.")
    cols = _collections(outer)
    low = ref.lower()
    for c in cols:
        if c.get("slug") == ref or (c.get("name") or "").lower() == low:
            return c
    close = [c for c in cols if low in (c.get("name") or "").lower()]
    if len(close) == 1:
        return close[0]
    names = ", ".join(c.get("name", "") for c in cols[:20]) or "none yet"
    raise ToolError(f"No collection called “{ref}”. Your collections: {names}.")


def _col_row(c):
    return {k: c.get(k) for k in ("name", "slug", "visibility", "description", "item_count")
            if c.get(k) not in (None, "")}


def _list_collections(outer, args):
    cols = [_col_row(c) for c in _collections(outer)]
    return {"summary": f"You have {len(cols)} collection{'' if len(cols) == 1 else 's'}.",
            "collections": cols}


def _get_collection(outer, args):
    c = _find_collection(outer, args.get("collection"))
    data = _ok(outer, "GET", f"/api/inference/collections/{c['slug']}/")
    items = [_row(r) for r in (data.get("items") or [])]
    return {"summary": f"“{c['name']}” has {len(items)} item{'' if len(items) == 1 else 's'} "
                       f"and is {str(c.get('visibility', '')).lower()}.",
            "collection": _col_row(data), "items": items[:50]}


def _save_collection(outer, args):
    body = {k: args[k] for k in ("description", "visibility") if args.get(k) is not None}
    existing = None
    if args.get("collection"):
        try:
            existing = _find_collection(outer, args["collection"])
        except ToolError:
            if not args.get("name"):  # asked to change one that does not exist
                raise
    if existing is not None:
        c = existing
        if args.get("name") and args["name"] != c.get("name"):
            body["name"] = args["name"]
        if args.get("cover_item_id") is not None:
            body["cover_request_id"] = args["cover_item_id"] or None
        if not body:
            raise ToolError("Nothing to change.")
        data = _ok(outer, "PATCH", f"/api/inference/collections/{c['slug']}/", body)
        changes = ", ".join(f"{k} → {v}" for k, v in body.items())
        return {"summary": f"Updated collection “{c['name']}” ({changes}).",
                "collection": _col_row(data)}
    if not args.get("name"):
        raise ToolError("Give `name` to create a collection, or `collection` to change one.")
    body["name"] = args["name"]
    code, data, _ = internal(outer, "POST", "/api/inference/collections/", body)
    if code not in (200, 201):
        raise ToolError(err_text(code, data))
    verb = "Created" if code == 201 else "Already had"
    return {"summary": f"{verb} collection “{data.get('name')}”.", "collection": _col_row(data)}


def _delete_collection(outer, args):
    c = _find_collection(outer, args.get("collection"))
    if not _confirmed(outer, f"collection:{c['slug']}", args):
        return {"summary": f"Not deleted. Deleting collection “{c['name']}” cannot be undone "
                           "(its items are kept) — ask the person to confirm, then call again "
                           "with confirm: true.", "needs_confirmation": True}
    _ok(outer, "DELETE", f"/api/inference/collections/{c['slug']}/")
    return {"summary": f"Deleted collection “{c['name']}”. Its items were kept."}


def _collection_items(outer, args):
    name = args.get("collection")
    remove = bool(args.get("remove"))
    ids = [int(i) for i in (args.get("item_ids") or [])]
    if not ids:
        raise ToolError("item_ids is required.")
    try:
        c = _find_collection(outer, name)
    except ToolError:
        if remove:
            raise
        code, c, _ = internal(outer, "POST", "/api/inference/collections/", {"name": name})
        if code not in (200, 201):
            raise ToolError(err_text(code, c))
    done = 0
    for i in ids[:100]:
        code, _, _ = internal(outer, "DELETE" if remove else "POST",
                              f"/api/inference/collections/{c['slug']}/items/{i}/")
        done += code == 200
    verb = "Removed" if remove else "Added"
    prep = "from" if remove else "to"
    return {"summary": f"{verb} {done} item{'' if done == 1 else 's'} {prep} “{c['name']}”.",
            "collection": c.get("name"), "count": done}


# --- settings ----------------------------------------------------------------

_SETTING_FIELDS = {
    "default_visibility": "default_request_visibility",
    "default_collection": "default_collection_name",
    "fallback_model": "fallback_model",
    "routing_preference": "routing_preference",
    "public_profile": "public_profile_enabled",
    "use_alias": "use_anon_alias",
}


def _settings_view(acct):
    return {
        "handle": acct.get("handle"),
        "account_type": acct.get("account_type"),
        "default_visibility": acct.get("default_request_visibility"),
        "default_collection": acct.get("default_collection_name") or None,
        "fallback_model": acct.get("fallback_model") or None,
        "routing_preference": acct.get("routing_preference"),
        "public_profile": acct.get("public_profile_enabled"),
        "use_alias": acct.get("use_anon_alias"),
    }


def _get_settings(outer, args):
    acct = _ok(outer, "GET", "/api/account/")
    view = _settings_view(acct)
    code, keys, _ = internal(outer, "GET", "/api/inference/api-keys/")
    if code == 200:
        rows = keys.get("data", keys) if isinstance(keys, dict) else keys
        view["external_api_keys_set"] = sorted(
            k.get("service") for k in (rows or []) if k.get("is_set"))
    return {"summary": f"New generations default to {str(view['default_visibility']).lower()}"
                       + (f" and go into “{view['default_collection']}”" if view["default_collection"] else "")
                       + ".", "settings": view}


def _update_settings(outer, args):
    body = {api: args[name] for name, api in _SETTING_FIELDS.items()
            if args.get(name) is not None}
    if not body:
        raise ToolError("Nothing to change. Settable: " + ", ".join(_SETTING_FIELDS) + ".")
    acct = _ok(outer, "PATCH", "/api/account/", body)
    changes = ", ".join(f"{name} → {args[name]}" for name in _SETTING_FIELDS
                        if args.get(name) is not None)
    return {"summary": f"Updated settings: {changes}.", "settings": _settings_view(acct)}


def _services(outer, args):
    if args.get("service_id") is None:
        data = _ok(outer, "GET", "/api/inference/services/")
        rows = data.get("results", data) if isinstance(data, dict) else (data or [])
        out = [{"id": s.get("id"), "name": s.get("name"), "host": s.get("host_id"),
                "access_policy": s.get("access_policy"),
                "allowed_github_users": s.get("allowed_github_users") or [],
                "models": [m.get("name") if isinstance(m, dict) else m
                           for m in (s.get("models") or [])][:6]} for s in rows]
        return {"summary": f"You run {len(out)} service{'' if len(out) == 1 else 's'}.",
                "services": out}
    body = {k: args[k] for k in ("access_policy", "allowed_github_users")
            if args.get(k) is not None}
    if not body:
        raise ToolError("Give access_policy and/or allowed_github_users.")
    s = _ok(outer, "PATCH", f"/api/inference/services/{int(args['service_id'])}/", body)
    return {"summary": f"Service “{s.get('name')}” access is now {s.get('access_policy')}.",
            "service": {"id": s.get("id"), "name": s.get("name"),
                        "access_policy": s.get("access_policy"),
                        "allowed_github_users": s.get("allowed_github_users") or []}}


# --- playback and navigation (acted on by the web app; URLs for other clients)

_PAGES = {
    "home": "/dashboard", "music": "/dashboard/music", "watch": "/dashboard/watch",
    "gallery": "/dashboard/inference/gallery", "images": "/dashboard/inference/gallery",
    "media": "/dashboard/media", "chats": "/dashboard/chats", "queue": "/dashboard/queue",
    "models": "/dashboard/models", "cluster": "/dashboard/cluster",
    "leaderboard": "/dashboard/leaderboard", "playground": "/dashboard/playground",
    "playground-chat": "/dashboard/playground", "playground-images": "/dashboard/playground/images",
    "playground-music": "/dashboard/playground/music", "playground-videos": "/dashboard/playground/videos",
    "playground-speech": "/dashboard/playground/speech",
    "playground-transcribe": "/dashboard/playground/transcribe",
    "playground-agent": "/dashboard/playground/agent", "playground-voice": "/dashboard/playground/voice",
    "settings": "/dashboard/settings/general", "settings-token": "/dashboard/settings/token",
    "settings-api-keys": "/dashboard/settings/api-keys", "settings-access": "/dashboard/settings/access",
    "settings-routing": "/dashboard/settings/routing", "settings-usage": "/dashboard/settings/usage",
    "settings-fallback": "/dashboard/settings/fallback",
}


def _open_page(outer, args):
    if args.get("item_id") is not None:
        r = _item(outer, _item_id(args, "item_id"))
        path = f"/dashboard/inference/requests/{r.get('public_id') or r.get('id')}"
        name = _label(r)
    else:
        key = str(args.get("page") or "").lower().strip().replace(" ", "-")
        path = _PAGES.get(key)
        if path is None:
            raise ToolError("Unknown page. Pages: " + ", ".join(sorted(_PAGES)) + ".")
        name = f"the {key} page"
    return {"summary": f"Opened {name}.", "url": _frontend(path),
            "client_action": {"type": "navigate", "path": path}}


def _play_music(outer, args):
    if args.get("item_ids"):
        rows = []
        for i in args["item_ids"][:50]:
            code, r, _ = internal(outer, "GET", f"/api/inference/requests/{int(i)}/")
            if code == 200:
                rows.append(r)
    elif args.get("collection"):
        c = _find_collection(outer, args["collection"])
        rows = _ok(outer, "GET", f"/api/inference/collections/{c['slug']}/").get("items") or []
    else:
        q = {"type": "MUSIC", "limit": "50"}
        if args.get("query"):
            q["search"] = str(args["query"])
        scope = "/api/inference/requests/all/" if args.get("everyone") else "/api/inference/requests/"
        rows = _ok(outer, "GET", scope, query=q).get("results") or []
    tracks = []
    for r in rows:
        url = r.get("output_audio_url")
        if r.get("inference_type") != "MUSIC" or not url or r.get("status") != "PROCESSED":
            continue
        tracks.append({
            "id": r.get("id"), "title": r.get("title") or (r.get("prompt_preview") or "")[:80],
            "url": url, "cover": r.get("cover_image_url"), "seconds": r.get("audio_seconds"),
            "visibility": r.get("visibility"), "owner": r.get("owner"),
        })
    if not tracks:
        raise ToolError("No playable songs matched.")
    if args.get("shuffle"):
        import random

        random.shuffle(tracks)
    first = tracks[0]["title"]
    return {"summary": f"Playing {len(tracks)} song{'' if len(tracks) == 1 else 's'}, "
                       f"starting with “{first}”.",
            "tracks": tracks,
            "client_action": {"type": "play", "tracks": tracks}}


# --- one-shot: a song with pictures -----------------------------------------

_SONG_WRITER_SYSTEM = (
    "You write songs and art direction. Reply with ONE JSON object and nothing else: "
    '{"title": str, "style": str, "lyrics": str, "image_prompts": [str, ...]}. '
    "`style` is comma-separated genre, mood, instrument and vocal tags. `lyrics` uses "
    "[verse], [chorus], [bridge] section markers on their own lines, sized for the "
    "requested length (about 4 sung lines per 15 seconds). Each image prompt is one "
    "vivid, self-contained sentence illustrating one part of the lyrics, in a single "
    "consistent visual style that you name in every prompt; no text in the images."
)


def _json_from_text(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def _write_song(outer, topic, seconds, n_images, style, model):
    from .jobs import auto_model_for
    from .serializers import _extract_response_text

    model = model or auto_model_for(outer.user, "llm")
    if not model:
        raise ToolError("No language model is online to write the lyrics. Write the "
                        "lyrics yourself and pass them as `lyrics` (and `image_prompts`).")
    ask = (f"Song about: {topic}\nLength: {int(seconds)} seconds\n"
           f"Number of image prompts: {n_images}\n"
           + (f"Musical style to use: {style}\n" if style else ""))
    body = {"model": model, "stream": False, "temperature": 0.9, "max_tokens": 3000,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": _SONG_WRITER_SYSTEM},
                         {"role": "user", "content": ask}]}
    code, data, _ = internal(outer, "POST", "/v1/chat/completions", body)
    if code == 400:  # a provider that rejects chat_template_kwargs
        body.pop("chat_template_kwargs")
        code, data, _ = internal(outer, "POST", "/v1/chat/completions", body)
    if code != 200:
        raise ToolError("Could not write the lyrics (" + err_text(code, data) + "). Write "
                        "them yourself and pass `lyrics` and `image_prompts`.")
    plan = _json_from_text(_extract_response_text(data))
    if not plan or not plan.get("lyrics"):
        raise ToolError("The lyric writer returned something unusable. Write the lyrics "
                        "yourself and pass `lyrics` and `image_prompts`.")
    return plan, model


def _make_song(outer, args):
    from .jobs import auto_model_for

    seconds = float(args.get("duration_seconds") or 120)
    seconds = max(10.0, min(seconds, 300.0))
    n_images = max(0, min(int(args.get("images") if args.get("images") is not None else 4), 12))
    prompts = [str(p) for p in (args.get("image_prompts") or []) if str(p).strip()]
    lyrics, style, title = args.get("lyrics"), args.get("style"), args.get("title")
    writer = None
    need_prompts = n_images and not prompts
    if not lyrics or need_prompts or not style:
        topic = args.get("topic") or title or (lyrics or "")[:300]
        if not topic:
            raise ToolError("Give `topic` (what the song is about) or `lyrics`.")
        plan, writer = _write_song(outer, topic if not lyrics else
                                   f"{topic}\nUse exactly these lyrics:\n{lyrics}",
                                   seconds, n_images, style, args.get("writer_model"))
        lyrics = lyrics or plan.get("lyrics")
        style = style or plan.get("style") or "pop"
        title = title or plan.get("title")
        if need_prompts:
            prompts = [str(p) for p in (plan.get("image_prompts") or []) if str(p).strip()]
    prompts = prompts[:n_images] if n_images else []
    if args.get("instrumental"):
        lyrics = "[instrumental]"

    collection = args.get("collection") or (title or "Untitled song")
    share = {"collection": collection}
    if args.get("visibility"):
        share["visibility"] = args["visibility"]

    music_model = args.get("music_model") or auto_model_for(outer.user, "music")
    if not music_model:
        raise ToolError("No music model is online right now.")
    code, song, _ = internal(outer, "POST", "/v1/music/generations", {
        "model": music_model, "prompt": style, "lyrics": lyrics, "title": title or "",
        "audio_duration": seconds, "async": True, "delivery": "url", **share})
    if code != 202 or not isinstance(song, dict):
        raise ToolError("Could not start the song: " + err_text(code, song))

    image_jobs, image_error = [], None
    if prompts:
        image_model = args.get("image_model") or auto_model_for(outer.user, "image")
        if not image_model:
            image_error = "no image model is online"
        for p in prompts if image_model else []:
            code, job, _ = internal(outer, "POST", "/v1/images/generations", {
                "model": image_model, "prompt": p, "n": 1,
                "size": args.get("image_size") or "1024x1024", "async": True, **share})
            if code == 202 and isinstance(job, dict):
                image_jobs.append(str(job.get("id")))
            else:
                image_error = err_text(code, job)

    mins = f"{int(seconds // 60)}:{int(seconds % 60):02d}"
    summary = (f"Started the song “{title or 'Untitled'}” ({mins}, {style[:60]})"
               + (f" and {len(image_jobs)} image{'' if len(image_jobs) == 1 else 's'} "
                  f"for its lyrics" if image_jobs else "")
               + f". Everything is filed in the collection “{collection}”. "
                 "The song takes a minute or two.")
    if image_error:
        summary += f" Images could not all be started: {image_error}."
    return {
        "summary": summary, "title": title, "style": style, "lyrics": lyrics,
        "collection": collection, "song_job_id": str(song.get("id")),
        "image_job_ids": image_jobs, "image_prompts": prompts,
        "written_by": writer,
        "jobs": [{"job_id": str(song.get("id")), "kind": "song", "title": title}]
                + [{"job_id": j, "kind": "image"} for j in image_jobs],
        "page": _frontend("/dashboard/music"),
    }


# --- everything else: the raw API --------------------------------------------

# Never reachable through api_request: sign-in and credential flows, the node
# agent's own endpoints, Django admin, and the assistant itself.
_DENY = re.compile(
    r"^/(admin|oauth|mcp)(/|$)|^/api/(login|logout|login-set-cookie|token|register|auth|social)(/|$)"
    r"|^/api/inference/agent/|^/v1/agent(/|$)"
)
_SECRET_KEYS = {"api_token", "token", "key", "api_key", "secret", "password"}


def _redact(v):
    if isinstance(v, dict):
        return {k: ("[hidden]" if k in _SECRET_KEYS and isinstance(x, str) and x else _redact(x))
                for k, x in v.items()}
    if isinstance(v, list):
        return [_redact(x) for x in v]
    return v


def _api_request(outer, args):
    method = str(args.get("method") or "GET").upper()
    path = str(args.get("path") or "")
    if method not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
        raise ToolError("method must be GET, POST, PATCH, PUT or DELETE.")
    if not (path.startswith("/v1/") or path.startswith("/api/")) or ".." in path:
        raise ToolError("path must start with /v1/ or /api/.")
    if _DENY.search(path):
        raise ToolError("That endpoint is not available to assistants (sign-in, tokens "
                        "and credentials are managed in the web app).")
    if "/api-keys/" in path and method != "GET":
        raise ToolError("External API keys are set in Settings → API keys, not through "
                        "an assistant.")
    try:
        resolve(path.split("?")[0])
    except Resolver404:
        raise ToolError(f"No such endpoint: {path}. Use find_api to look one up.")
    query = args.get("query") if isinstance(args.get("query"), dict) else None
    if "?" in path and not query:
        from urllib.parse import parse_qsl

        path, qs = path.split("?", 1)
        query = dict(parse_qsl(qs))
    code, data, resp = internal(outer, method, path, args.get("body"), query)
    if data is None and code < 300 and resp.get("Content-Type", "").split(";")[0] not in ("", "application/json"):
        data = {"note": f"Non-JSON response ({resp.get('Content-Type')}); "
                        "use a media URL or the CLI to download it."}
    text = json.dumps(_redact(data))
    truncated = len(text) > 12000
    return {"summary": f"{method} {path} → {code}.", "status": code,
            "data": json.loads(text) if not truncated else None,
            **({"data_truncated": text[:12000]} if truncated else {})}


_API_INDEX = None


def _api_index():
    """``(method, path, summary)`` for every documented /v1 route, plus the web
    app's /api routes by name."""
    global _API_INDEX
    if _API_INDEX is None:
        rows = []
        try:
            import os

            import yaml

            with open(os.path.join(os.path.dirname(__file__), "openapi.yaml")) as fh:
                spec = yaml.safe_load(fh)
            for path, ops in (spec.get("paths") or {}).items():
                for method, op in ops.items():
                    if method in ("get", "post", "patch", "put", "delete"):
                        rows.append((method.upper(), path if path.startswith("/") else "/" + path,
                                     (op.get("summary") or op.get("description") or "")[:140]))
        except Exception:
            logger.warning("could not index openapi.yaml", exc_info=True)
        from .urls import urlpatterns

        for p in urlpatterns:
            route = "/api/inference/" + str(p.pattern)
            if "agent/" in route:
                continue
            doc = (getattr(getattr(p.callback, "view_class", None), "__doc__", "") or "")
            rows.append(("*", route, " ".join(doc.split())[:140]))
        rows.append(("GET/PATCH", "/api/account/", "The caller's profile and preferences."))
        _API_INDEX = rows
    return _API_INDEX


def _find_api(outer, args):
    words = [w for w in re.split(r"\W+", str(args.get("query") or "").lower()) if w]
    scored = []
    for method, path, summary in _api_index():
        hay = f"{path} {summary}".lower()
        score = sum(hay.count(w) for w in words)
        if score or not words:
            scored.append((score, method, path, summary))
    scored.sort(key=lambda r: -r[0])
    rows = [{"method": m, "path": p, "about": s} for _, m, p, s in scored[:15]]
    return {"summary": f"{len(rows)} matching endpoint{'' if len(rows) == 1 else 's'}. "
                       "Full spec at /openapi.json.", "endpoints": rows}


# --- the tool list -----------------------------------------------------------

RO = {"readOnlyHint": True}
DESTRUCTIVE = {"destructiveHint": True}

CONTROL_TOOLS = [
    {"name": "search_library", "annotations": RO, "handler": _search_library,
     "description": "Find things in the library (songs, images, videos, speech, chats). "
                    "Returns ids to use with the other tools.",
     "inputSchema": _obj({
         "kind": {**_S, "description": "song, image, video, speech, chat, 3d or any."},
         "query": {**_S, "description": "Words from the title or prompt."},
         "scope": {"type": "string", "enum": ["mine", "starred", "bookmarked", "everyone"]},
         "collection": _COLL, "sort": {"type": "string", "enum": ["newest", "popular"]},
         "limit": _I})},
    {"name": "get_item", "annotations": RO, "handler": _get_item,
     "description": "One library item in full: title, prompt, lyrics, visibility, links.",
     "inputSchema": _obj({"id": _ITEM}, ["id"])},
    {"name": "update_item", "handler": _update_item,
     "description": "Change one item: rename it, set who can see it, star or bookmark it, "
                    "or set its cover image.",
     "inputSchema": _obj({"id": _ITEM, "title": _S, "visibility": _VIS, "starred": _B,
                          "bookmarked": _B,
                          "cover_item_id": {**_I, "description": "An image item to use as "
                                                                 "cover; 0 clears it."}}, ["id"])},
    {"name": "set_visibility_many", "handler": _update_many,
     "description": "Set who can see many items at once: give item_ids, or a "
                    "kind/query/collection to match your own items.",
     "inputSchema": _obj({"visibility": _VIS, "item_ids": {"type": "array", "items": _I},
                          "kind": _S, "query": _S, "collection": _COLL}, ["visibility"])},
    {"name": "delete_item", "annotations": DESTRUCTIVE, "handler": _delete_item,
     "description": "Delete one of your items for good. Call without confirm first; only "
                    "pass confirm: true after the person says yes.",
     "inputSchema": _obj({"id": _ITEM, "confirm": _B}, ["id"])},
    {"name": "cover_art", "handler": _missing_covers,
     "description": "Count songs with no cover art, or (generate: true) queue covers for them.",
     "inputSchema": _obj({"generate": _B, "limit": _I})},
    {"name": "list_collections", "annotations": RO, "handler": _list_collections,
     "description": "Your collections (playlists and albums).",
     "inputSchema": _obj({})},
    {"name": "get_collection", "annotations": RO, "handler": _get_collection,
     "description": "A collection and the items in it.",
     "inputSchema": _obj({"collection": _COLL}, ["collection"])},
    {"name": "save_collection", "handler": _save_collection,
     "description": "Create a collection (give name) or change one (give collection plus "
                    "the new name, description, visibility or cover_item_id).",
     "inputSchema": _obj({"collection": _COLL, "name": _S, "description": _S,
                          "visibility": _VIS, "cover_item_id": _I})},
    {"name": "collection_items", "handler": _collection_items,
     "description": "Add items to a collection (created if new), or remove them with "
                    "remove: true.",
     "inputSchema": _obj({"collection": _COLL, "item_ids": {"type": "array", "items": _I},
                          "remove": _B}, ["collection", "item_ids"])},
    {"name": "delete_collection", "annotations": DESTRUCTIVE, "handler": _delete_collection,
     "description": "Delete a collection (its items are kept). Needs confirm: true after "
                    "the person says yes.",
     "inputSchema": _obj({"collection": _COLL, "confirm": _B}, ["collection"])},
    {"name": "get_settings", "annotations": RO, "handler": _get_settings,
     "description": "Account settings: default visibility and collection for new "
                    "generations, fallback model, routing, public profile, alias, and "
                    "which external API keys are set.",
     "inputSchema": _obj({})},
    {"name": "update_settings", "handler": _update_settings,
     "description": "Change account settings. Only the fields given are changed.",
     "inputSchema": _obj({
         "default_visibility": _VIS,
         "default_collection": {**_S, "description": "Collection new generations are filed "
                                                     "into; empty string for none."},
         "fallback_model": {**_S, "description": "Model id to use when the requested chat "
                                                 "model is offline; empty string for none."},
         "routing_preference": _S, "public_profile": _B, "use_alias": _B})},
    {"name": "services", "handler": _services,
     "description": "List the model services you host and who may use them, or change one "
                    "service's access (give service_id).",
     "inputSchema": _obj({"service_id": _I, "access_policy": _S,
                          "allowed_github_users": {"type": "array", "items": _S}})},
    {"name": "play_music", "handler": _play_music,
     "description": "Play songs in the web app's player (other clients get the audio "
                    "URLs): by item_ids, a collection, or a search of your songs.",
     "inputSchema": _obj({"item_ids": {"type": "array", "items": _I}, "collection": _COLL,
                          "query": _S, "shuffle": _B,
                          "everyone": {**_B, "description": "Search everyone's public songs."}})},
    {"name": "open_page", "handler": _open_page,
     "description": "Open a page of the web app (other clients get its URL): a named page "
                    "such as music, gallery, queue, settings-token, playground-images — or "
                    "an item by item_id.",
     "inputSchema": _obj({"page": _S, "item_id": _I})},
    {"name": "make_song", "handler": _make_song,
     "description": "One step for 'make a song about X, N minutes long, with pictures': "
                    "writes lyrics if you don't pass them, starts the song and one image "
                    "per image prompt, and files them all in one collection. Returns "
                    "job ids straight away.",
     "inputSchema": _obj({
         "topic": {**_S, "description": "What the song is about."},
         "duration_seconds": {"type": "number", "description": "10-300. 2m30s = 150."},
         "style": {**_S, "description": "Genre, mood, instruments, vocals."},
         "lyrics": {**_S, "description": "Your own lyrics with [verse]/[chorus] markers."},
         "title": _S, "instrumental": _B,
         "images": {**_I, "description": "How many pictures (0-12, default 4)."},
         "image_prompts": {"type": "array", "items": _S,
                           "description": "Your own picture prompts, one per image."},
         "image_size": _S, "collection": _COLL, "visibility": _VIS,
         "writer_model": {**_S, "description": "LLM id for the lyric writing."}})},
    {"name": "find_api", "annotations": RO, "handler": _find_api,
     "description": "Search the API for an endpoint to use with api_request.",
     "inputSchema": _obj({"query": _S}, ["query"])},
    {"name": "api_request", "annotations": DESTRUCTIVE, "handler": _api_request,
     "description": "Call any /v1/* or /api/* endpoint as the user, with a JSON body. Use "
                    "when no other tool fits (jobs, batches, workflows, files, voice "
                    "samples, hosts, chat threads, usage…).",
     "inputSchema": _obj({"method": {"type": "string",
                                     "enum": ["GET", "POST", "PATCH", "PUT", "DELETE"]},
                          "path": {**_S, "description": "Starts with /v1/ or /api/."},
                          "query": {"type": "object"}, "body": {"type": "object"}},
                         ["method", "path"])},
]

CONTROL_HANDLERS = {t["name"]: t.pop("handler") for t in CONTROL_TOOLS}
