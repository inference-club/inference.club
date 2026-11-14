"""``GET /v1/catalog`` — every node, service and model the caller can reach
(issue #17).

Built purely from what the club already stores about agents: the manifest
sync (``sync_provider_models_from_manifest``) mirrors ``hosts[]`` into
Host/Gpu rows and ``services[]`` (with each model's declared id / name /
modalities / features / context length) into ProviderService, ProviderModel
and CatalogModel rows; heartbeats stamp ``Provider.last_seen_at``. Nothing here
dials an agent. When a recent ``/cluster/state`` snapshot is already in the
server cache (the cluster views put it there) it refines ``ready`` / ``online``
with live replica + node readiness; otherwise those are derived from liveness
alone.

Access mirrors ``/v1/models``: the caller's own providers in full, plus other
members' services that clear every access gate (cluster, node, service).
"""
from django.core.cache import cache
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Provider, ProviderService
from .openai_views import _RateLimitHeadersMixin, _model_caps, _model_slug
from .serializers import _user_real_github_login
from .throttling import AccountTypeScopedRateThrottle

# ProviderService.service_type → the catalog's public type vocabulary.
_TYPE_MAP = {
    ProviderService.TYPE_LLM: "llm",
    ProviderService.TYPE_STT: "asr",
    ProviderService.TYPE_TTS: "tts",
    ProviderService.TYPE_IMAGE: "image",
    ProviderService.TYPE_MESH: "3d",
    ProviderService.TYPE_MUSIC: "music",
    ProviderService.TYPE_VIDEO: "video",
}

# The /v1 endpoint each service type is routed from. Keyed on the stored
# service_type (what routing actually uses), NOT the inferred catalog type: an
# untyped text->audio service is listed as "tts" but still only routes from
# chat/completions until its manifest declares ``type: tts``.
_ENDPOINT_BY_TYPE = {
    ProviderService.TYPE_LLM: "/v1/chat/completions",
    ProviderService.TYPE_STT: "/v1/audio/transcriptions",
    ProviderService.TYPE_TTS: "/v1/audio/speech",
    ProviderService.TYPE_IMAGE: "/v1/images/generations",
    ProviderService.TYPE_MESH: "/v1/3d/generations",
    ProviderService.TYPE_MUSIC: "/v1/music/generations",
    ProviderService.TYPE_VIDEO: "/v1/videos/generations",
    ProviderService.TYPE_SCRAPE: "/v1/scrape",
    ProviderService.TYPE_RENDER: "/v1/videos/compose",
    ProviderService.TYPE_AUDIO_ENHANCE: "/v1/audio/enhance",
}


def _catalog_type(service, models) -> str:
    """Public type for a service. An explicit manifest type wins; ``llm`` is
    also the manifest *default*, so for it we look at what the models declare
    they produce before trusting the label."""
    stype = service.service_type
    if stype != ProviderService.TYPE_LLM:
        return _TYPE_MAP.get(stype, "other")
    ins = {m for x in models for m in x.get("input_modalities") or []}
    outs = {m for x in models for m in x.get("output_modalities") or []}
    if "image" in outs:
        return "image"
    if "video" in outs:
        return "video"
    if outs & {"model", "3d", "mesh"}:
        return "3d"
    if "audio" in outs:
        return "tts"
    if "audio" in ins and outs <= {"text"}:
        return "asr"
    return "llm"


def _cached_state(provider):
    """The agent's last ``/cluster/state`` snapshot, if one is cached. Never
    fetches (the catalog must not fan out to every agent on each call)."""
    state = cache.get(f"cluster_state:{provider.id}")
    return state if isinstance(state, dict) else None


def _live_service_ready(state, service_name):
    """True/False from a cached snapshot's deployments (or pods), or None when
    the snapshot says nothing about this service."""
    if not state:
        return None
    deps = [d for d in state.get("deployments") or []
            if (d.get("service") or d.get("name")) == service_name]
    if deps:
        return any(int(d.get("ready_replicas") or 0) > 0 for d in deps)
    pods = [p for p in state.get("pods") or [] if p.get("service") == service_name]
    if pods:
        return any(bool(p.get("ready")) for p in pods)
    return None


def _live_node_ready(state, host_id):
    if not state:
        return None
    for n in state.get("nodes") or []:
        if (n.get("host_id") or n.get("name")) == host_id and "ready" in n:
            return bool(n.get("ready"))
    return None


def _model_entry(pm) -> dict:
    caps = _model_caps(pm)
    cat = pm.catalog_model if pm.catalog_model_id else None
    entry = {
        "id": _model_slug(pm),
        "name": (cat.display_name if cat else "") or pm.name,
        "input_modalities": caps["input_modalities"],
        "output_modalities": caps["output_modalities"],
        "features": caps["supported_features"],
    }
    if caps["context_length"]:
        entry["context_length"] = caps["context_length"]
    return entry


def build_catalog(user) -> dict:
    github_login = _user_real_github_login(user)
    providers = (
        Provider.objects.filter(is_active=True)
        .exclude(tailnet_hostname="", tailnet_addr="")
        .prefetch_related("hosts__gpus")
        .order_by("id")
    )

    nodes, services = [], []
    by_type: dict[str, list[str]] = {}
    for provider in providers:
        own = provider.user_id == user.id
        if not own and not provider.grants_access_to(user, github_login):
            continue
        state = _cached_state(provider)
        provider_online = provider.is_online

        svc_qs = (
            provider.services.filter(is_active=True)
            .select_related("host", "provider")
            .prefetch_related("models__catalog_model")
            .order_by("name")
        )
        visible_hosts = set()
        for svc in svc_qs:
            if not own and not svc.grants_access_to(user, github_login):
                continue
            pms = [pm for pm in svc.models.all() if pm.is_active]
            models = [_model_entry(pm) for pm in pms]
            ready = bool(
                provider_online
                and provider.accepting_requests
                and models
                and (svc.host is None or svc.host.is_active)
            )
            live = _live_service_ready(state, svc.name)
            if ready and live is not None:
                ready = live
            stype = _catalog_type(svc, models)
            entry = {
                "type": stype,
                "name": svc.name,
                "node": svc.manifest_host_id,
                "provider": provider.name,
                "models": models,
                "ready": ready,
            }
            if svc.engine:
                entry["engine"] = svc.engine
            endpoint = _ENDPOINT_BY_TYPE.get(svc.service_type)
            if endpoint:
                entry["endpoint_kind"] = endpoint
            services.append(entry)
            visible_hosts.add(svc.manifest_host_id)
            ids = by_type.setdefault(stype, [])
            for m in models:
                if m["id"] not in ids:
                    ids.append(m["id"])

        for host in provider.hosts.all():
            if not host.is_active:
                continue
            if not own and (
                host.host_id not in visible_hosts
                or not host.grants_access_to(user, github_login)
            ):
                continue
            gpus = []
            for g in host.gpus.all():
                if not g.is_active:
                    continue
                gpu = {"name": g.model or g.vendor or "GPU"}
                if g.vram_gb is not None:
                    gpu["memory_gb"] = g.vram_gb
                gpus.append(gpu)
            online = provider_online
            live = _live_node_ready(state, host.host_id)
            if online and live is not None:
                online = live
            nodes.append({
                "name": host.host_id,
                "provider": provider.name,
                "gpus": gpus,
                "online": online,
                "last_seen": provider.last_seen_at,
            })

    return {
        "generated_at": timezone.now(),
        "nodes": nodes,
        "services": services,
        "by_type": {k: sorted(v) for k, v in sorted(by_type.items())},
    }


class CatalogView(_RateLimitHeadersMixin, APIView):
    """``GET /v1/catalog`` — nodes, services and models the caller can reach,
    grouped by type. Any valid API token; same throttle bucket as /v1/models."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountTypeScopedRateThrottle]
    throttle_scope = "models"

    def get(self, request):
        return Response(build_catalog(request.user))
