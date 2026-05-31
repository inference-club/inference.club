"""Phase 2 — enrich CatalogModel rows from the HuggingFace Hub.

Given a catalog model's ``hf_repo_id``, fetch the Hub's model card + the
repo's ``config.json`` and derive display metadata: architecture, native
context length, input/output modalities, and supported features. Everything
is best-effort: if the Hub is unreachable we fall back to keyword heuristics
on the slug so the catalog still shows *something*, and we stamp
``hf_synced_at`` either way so we don't re-fetch on every page view (operators
force a re-sync with ``manage.py enrich_catalog --force``).
"""
import logging
from datetime import timedelta

import requests
from django.utils import timezone

logger = logging.getLogger("django")

HF_API = "https://huggingface.co/api/models/"
HF_CONFIG = "https://huggingface.co/{repo}/resolve/main/config.json"
SYNC_TTL = timedelta(days=7)
_TIMEOUT = 8

# Keyword hints, matched against id + HF tags/pipeline_tag + config arch/type.
_IMAGE_HINTS = ("image-text", "visual", "-vl", "vl-", "vlm", "vision", "multimodal", "omni", "image-to-text")
_AUDIO_HINTS = ("audio", "speech", "asr", "omni", "voice", "whisper")
_VIDEO_HINTS = ("video",)
_REASONING_HINTS = ("reasoning", "-think", "thinking", "qwq", "deepseek-r1", "-r1", "o1", " cot")
_TOOL_HINTS = ("tool-use", "tool_use", "function-cal", "function_cal", "function-calling")


def _fetch(repo):
    """Return ``(api_json, config_json)`` — either may be None on failure."""
    api = config = None
    try:
        r = requests.get(HF_API + repo, timeout=_TIMEOUT)
        if r.ok:
            api = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.info("HF model-card fetch failed for %s: %s", repo, e)
    try:
        r = requests.get(HF_CONFIG.format(repo=repo), timeout=_TIMEOUT)
        if r.ok:
            config = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.info("HF config fetch failed for %s: %s", repo, e)
    return api, config


def _haystack(api, config, slug) -> str:
    parts = [(slug or "").lower()]
    if isinstance(api, dict):
        parts.append((api.get("pipeline_tag") or "").lower())
        parts += [str(t).lower() for t in (api.get("tags") or [])]
    if isinstance(config, dict):
        parts.append((config.get("model_type") or "").lower())
        parts += [str(a).lower() for a in (config.get("architectures") or [])]
    return " ".join(parts)


def _is_asr(api, config, slug) -> bool:
    """An automatic-speech-recognition model (audio-in → text-out), detected
    from the HF pipeline tag or strong ASR keywords in the id/tags."""
    pipeline = (api or {}).get("pipeline_tag") if isinstance(api, dict) else None
    if pipeline == "automatic-speech-recognition":
        return True
    hay = _haystack(api, config, slug)
    return any(h in hay for h in ("asr", "whisper", "-stt", "speech-recognition"))


def _is_text_to_image(api, config, slug) -> bool:
    """A text-to-image generation model (text → image out)."""
    pipeline = (api or {}).get("pipeline_tag") if isinstance(api, dict) else None
    if pipeline in ("text-to-image", "image-to-image"):
        return True
    hay = _haystack(api, config, slug)
    return any(h in hay for h in ("text-to-image", "stable-diffusion", "-sdxl", "flux.1", "diffusion-image"))


def infer_modalities(api, config, slug):
    """(input, output) modality lists. Output is text-only for the
    text-generating endpoints we proxy; input grows with vision/audio/video.
    ASR (audio→text) and image-generation (text→image) are the exceptions."""
    if _is_asr(api, config, slug):
        return ["audio"], ["text"]
    if _is_text_to_image(api, config, slug):
        return ["text", "image"], ["image"]
    cfg = config if isinstance(config, dict) else {}
    hay = _haystack(api, config, slug)
    inp = ["text"]
    if "vision_config" in cfg or any(h in hay for h in _IMAGE_HINTS):
        inp.append("image")
    if "audio_config" in cfg or any(h in hay for h in _AUDIO_HINTS):
        inp.append("audio")
    if any(h in hay for h in _VIDEO_HINTS):
        inp.append("video")
    return inp, ["text"]


def infer_features(api, config, slug):
    hay = _haystack(api, config, slug)
    feats = []
    if any(h in hay for h in _REASONING_HINTS):
        feats.append("reasoning")
    if any(h in hay for h in _TOOL_HINTS):
        feats.append("tools")
    # Whisper-family ASR servers expose word/segment timestamps via
    # verbose_json; flag it so the playground offers the timestamp UI (and the
    # proxy keeps verbose_json) only where it actually works.
    if "whisper" in hay:
        feats.append("timestamps")
    return feats


def _architecture(api, config) -> str:
    cfg = config if isinstance(config, dict) else {}
    if cfg.get("architectures"):
        return str(cfg["architectures"][0])
    acfg = (api or {}).get("config") if isinstance(api, dict) else None
    if isinstance(acfg, dict) and acfg.get("architectures"):
        return str(acfg["architectures"][0])
    return ""


def enrich_catalog_model(catalog, force=False) -> bool:
    """Best-effort populate ``catalog`` from the Hub. Returns True if a sync
    was attempted (and ``hf_synced_at`` stamped), False if skipped (no HF id,
    or fresh and not forced)."""
    if not catalog.hf_repo_id:
        return False
    if (
        not force
        and catalog.hf_synced_at
        and timezone.now() - catalog.hf_synced_at < SYNC_TTL
    ):
        return False

    api, config = _fetch(catalog.hf_repo_id)
    cfg = config if isinstance(config, dict) else {}

    inp, out = infer_modalities(api, config, catalog.slug)
    feats = infer_features(api, config, catalog.slug)
    ctx = cfg.get("max_position_embeddings")
    arch = _architecture(api, config)

    # Prefer the repo basename as the display name (cleaner than the full
    # "org/repo" path, which is what live-discovery seeded it with in Phase 0).
    if not catalog.display_name or catalog.display_name == catalog.hf_repo_id:
        catalog.display_name = catalog.hf_repo_id.split("/")[-1]
    if arch:
        catalog.architecture = arch
    if isinstance(ctx, int) and ctx > 0:
        catalog.native_context_length = ctx
    catalog.input_modalities = inp
    catalog.output_modalities = out
    catalog.supported_features = feats

    md = dict(catalog.metadata or {})
    if isinstance(api, dict):
        for k in ("pipeline_tag", "library_name", "gated", "downloads", "likes"):
            md[k] = api.get(k)
    if cfg.get("model_type"):
        md["model_type"] = cfg["model_type"]
    md["hf_ok"] = bool(api or config)
    catalog.metadata = md
    catalog.hf_synced_at = timezone.now()
    catalog.save()
    return True
