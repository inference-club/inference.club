import re

from django.conf import settings
from django.db.models import Sum
from rest_framework import serializers

from .models import (
    Collection,
    ContentReport,
    InferenceRequest,
    MediaAsset,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
    VISIBILITY_VALUES,
)

# Some reasoning models embed their thinking inline as <think>…</think> in the
# content rather than in a separate field; this lets us pull it out as a
# fallback. (The current Nemotron/vLLM setup uses a separate `reasoning`
# delta field, handled in openai_views._assemble_streamed_results.)
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


class AgentRegisterSerializer(serializers.Serializer):
    """Body of POST /api/inference/agent/register/.

    The agent says "here's the friendly name and the hostname I'd like to
    advertise"; the server picks a canonical hostname (per-provider) and
    returns a Tailscale auth key so the agent can join the tailnet.
    """

    name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    tailnet_hostname = serializers.CharField(max_length=255, required=False, allow_blank=True)
    agent_port = serializers.IntegerField(
        required=False, default=443, min_value=1, max_value=65535
    )


class ProviderModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderModel
        fields = ["id", "name", "context_window", "is_active"]


class PublicServiceManifestSerializer(serializers.ModelSerializer):
    """Public-facing manifest view — exposes the parsed structure but not
    the raw YAML (which may contain notes the operator wouldn't want
    on a public profile)."""

    class Meta:
        model = ServiceManifest
        fields = [
            "schema_version",
            "parsed",
            "uploaded_at",
            "is_valid",
        ]


class ServiceManifestSerializer(serializers.ModelSerializer):
    """Owner-facing manifest view — includes raw YAML and validation errors
    so the dashboard can show the operator exactly what they uploaded and
    what (if anything) the server rejected."""

    class Meta:
        model = ServiceManifest
        fields = [
            "schema_version",
            "raw_yaml",
            "parsed",
            "uploaded_at",
            "is_valid",
            "validation_errors",
        ]


class ProviderSerializer(serializers.ModelSerializer):
    # Only active models — inactive rows are kept for history (e.g. a model
    # removed from the manifest) but must not show in the dashboard / profile.
    models = serializers.SerializerMethodField()
    is_online = serializers.BooleanField(read_only=True)
    manifest = ServiceManifestSerializer(read_only=True)

    def get_models(self, obj):
        # Filter in Python to reuse the prefetched `models` and avoid an extra
        # query per provider.
        active = [m for m in obj.models.all() if m.is_active]
        return ProviderModelSerializer(active, many=True).data

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "tailnet_hostname",
            "agent_port",
            "is_active",
            "is_online",
            "accepting_requests",
            "registered_at",
            "last_seen_at",
            "models",
            "manifest",
            "created_on",
        ]


class ProviderUpdateSerializer(serializers.ModelSerializer):
    """Owner-editable provider settings — currently just the pause/kill switch."""

    class Meta:
        model = Provider
        fields = ["id", "name", "accepting_requests"]
        read_only_fields = ["id", "name"]


class PublicProviderSerializer(ProviderSerializer):
    """Network-wide listing. Adds ``github_login`` (the user's GitHub
    handle, since signup is GitHub-only) and ``owner`` (preferred display
    name — github_login when present, otherwise the email local-part as a
    safety net).

    Overrides ``manifest`` with the public-facing serializer so we don't
    leak the raw YAML or validation errors to other users on the
    network-wide listing or the public profile.
    """

    owner = serializers.SerializerMethodField()
    github_login = serializers.SerializerMethodField()
    manifest = PublicServiceManifestSerializer(read_only=True)

    class Meta(ProviderSerializer.Meta):
        fields = ProviderSerializer.Meta.fields + ["owner", "github_login"]

    def _github_social(self, obj):
        # social_django registers a reverse manager named ``social_auth`` on
        # the user. Iterate manually so prefetch_related kicks in.
        for sa in obj.user.social_auth.all():
            if sa.provider == "github":
                return sa
        return None

    def get_github_login(self, obj) -> str | None:
        sa = self._github_social(obj)
        if not sa:
            return None
        return (sa.extra_data or {}).get("login") or None

    def get_owner(self, obj) -> str:
        login = self.get_github_login(obj)
        if login:
            return login
        email = getattr(obj.user, "email", "") or ""
        return email.split("@", 1)[0]


# --- helpers shared by the inference-request serializers -----------------
#
# Normalize the heterogeneous OpenAI request/response shapes (chat vs legacy
# completions, string vs multimodal content, buffered vs streamed) into a few
# simple structures the dashboard can render uniformly.


def _stringify_content(content) -> str:
    """Flatten a message ``content`` (string, or list of multimodal parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                if isinstance(p.get("text"), str):
                    parts.append(p["text"])
                else:
                    parts.append(f"[{p.get('type', 'part')}]")
        return "\n".join(parts)
    return ""


def _extract_messages(payload) -> list[dict]:
    """Return the request as a list of ``{role, content}`` messages.

    Handles chat (``messages``) and legacy completions (``prompt``).
    """
    if not isinstance(payload, dict):
        return []
    msgs = payload.get("messages")
    if isinstance(msgs, list):
        out = []
        for m in msgs:
            if isinstance(m, dict):
                out.append(
                    {
                        "role": m.get("role", ""),
                        "content": _stringify_content(m.get("content")),
                    }
                )
        return out
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return []


def _response_choice_text(results) -> str:
    """Raw assistant text from a buffered or streamed result (may still
    contain inline <think> tags for models that embed reasoning that way)."""
    if not isinstance(results, dict):
        return ""
    choices = results.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        c0 = choices[0]
        msg = c0.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
        if isinstance(c0.get("text"), str):
            return c0["text"]
    # Speech-to-text responses are a flat {"text": "..."} (no choices), as are
    # some other non-chat endpoints.
    if isinstance(results.get("text"), str):
        return results["text"]
    if isinstance(results.get("content"), str):  # defensive fallback
        return results["content"]
    return ""


def _extract_response_text(results) -> str:
    """The assistant's final answer, with any inline <think> block removed so
    the visible response isn't polluted by reasoning."""
    text = _response_choice_text(results)
    return _THINK_RE.sub("", text).strip() if text else text


def _extract_reasoning(results) -> str:
    """The reasoning/thinking trace, if the model produced one.

    Checks the dedicated ``reasoning`` / ``reasoning_content`` field (on the
    message or top-level), then falls back to an inline <think>…</think> block.
    """
    if not isinstance(results, dict):
        return ""
    choices = results.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        msg = choices[0].get("message")
        if isinstance(msg, dict):
            for k in ("reasoning", "reasoning_content"):
                v = msg.get(k)
                if isinstance(v, str) and v.strip():
                    return v
    for k in ("reasoning", "reasoning_content"):
        v = results.get(k)
        if isinstance(v, str) and v.strip():
            return v
    m = _THINK_RE.search(_response_choice_text(results))
    return m.group(1).strip() if m else ""


def _extract_usage(results):
    if isinstance(results, dict) and isinstance(results.get("usage"), dict):
        u = results["usage"]
        return {
            "prompt_tokens": u.get("prompt_tokens"),
            "completion_tokens": u.get("completion_tokens"),
            "total_tokens": u.get("total_tokens"),
        }
    return None


def _is_streamed(obj) -> bool:
    if isinstance(obj.results, dict) and obj.results.get("streamed"):
        return True
    return bool(isinstance(obj.payload, dict) and obj.payload.get("stream"))


def _truncate(text: str, limit: int = 280) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _input_audio_url(obj, request) -> str | None:
    """The owner-gated URL to replay this request's stored input audio (STT),
    or None. Only exposed to the request's owner since the asset route is
    owner-only."""
    if request is None or not request.user.is_authenticated:
        return None
    if obj.user_id != request.user.id:
        return None
    asset = next(
        (a for a in obj.assets.all() if a.kind == "INPUT_AUDIO"),
        None,
    )
    if asset is None:
        return None
    path = f"/api/inference/assets/{asset.id}/"
    return request.build_absolute_uri(path)


def asset_url(asset, request) -> str | None:
    """Browser-facing URL for one asset. Public kinds stored on GCS get the
    direct public-bucket URL — browsers fetch from storage.googleapis.com
    with immutable caching instead of streaming through the app. Otherwise
    (MinIO/FS, or private kinds) fall back to the backend's asset route."""
    if settings.MEDIA_DIRECT_PUBLIC_URLS and asset.kind in MediaAsset.PUBLIC_KINDS:
        return asset.file.url
    if request is None:
        return None
    return request.build_absolute_uri(f"/api/inference/assets/{asset.id}/")


def _asset_urls(obj, request, kind: str) -> list[str]:
    """Browser-facing URLs for this request's assets of ``kind`` (e.g.
    OUTPUT_IMAGE). Output kinds are public, so no owner gate."""
    out = []
    for a in obj.assets.all():
        if a.kind == kind:
            url = asset_url(a, request)
            if url:
                out.append(url)
    return out


def _cover_image_url(obj, request) -> str | None:
    """Absolute URL to the square cover art linked via ``cover_request``
    (a request's track art or a collection's playlist art), or None."""
    if obj.cover_request_id is None:
        return None
    urls = _asset_urls(obj.cover_request, request, "OUTPUT_IMAGE")
    return urls[0] if urls else None


def _model_url(obj, request) -> str | None:
    """Absolute URL to this request's generated 3D model (the GLB), or None.
    OUTPUT_MODEL assets are public, like generated images."""
    urls = _asset_urls(obj, request, "OUTPUT_MODEL")
    return urls[0] if urls else None


def _mesh_meta(obj) -> dict | None:
    """The image-to-3D generation stats (seed, vertices, faces, timing) for a
    MESH request, mirrored from the upstream ``X-Trellis-Metadata``. None for
    other request types or when no metadata was captured."""
    if obj.inference_type != "MESH" or not isinstance(obj.results, dict):
        return None
    meta = obj.results.get("metadata")
    return meta if isinstance(meta, dict) and meta else None


def _video_url(obj, request) -> str | None:
    """Absolute URL to this request's generated video (the MP4), or None.
    OUTPUT_VIDEO assets are public, like generated images."""
    if obj.inference_type != "VIDEO":
        return None
    urls = _asset_urls(obj, request, "OUTPUT_VIDEO")
    return urls[0] if urls else None


def _video_meta(obj) -> dict | None:
    """The text/image-to-video generation stats (duration + resolved
    width/height/fps/frames/seed) for a VIDEO request, from the LTX
    ``X-LTX-Params``. None for other request types or when nothing was captured."""
    if obj.inference_type != "VIDEO" or not isinstance(obj.results, dict):
        return None
    out: dict = {}
    if obj.results.get("duration") is not None:
        out["seconds"] = obj.results["duration"]
    params = obj.results.get("params")
    if isinstance(params, dict):
        for key in ("width", "height", "fps", "num_frames", "seed"):
            if params.get(key) is not None:
                out[key] = params[key]
    return out or None


def _transcription(results) -> dict | None:
    """Structured transcription extras (segments/words/language/duration) from
    a verbose_json STT response, for the timestamp visualization. None when the
    response is plain text only."""
    if not isinstance(results, dict):
        return None
    out = {}
    for key in ("words", "segments"):
        v = results.get(key)
        if isinstance(v, list) and v:
            out[key] = v
    for key in ("language", "duration"):
        v = results.get(key)
        if v is not None:
            out[key] = v
    return out or None


def _user_github_login(user):
    # social_django exposes a `social_auth` reverse manager; iterate so
    # prefetch_related kicks in rather than issuing a query per row.
    for sa in user.social_auth.all():
        if sa.provider == "github":
            return (sa.extra_data or {}).get("login") or None
    return None


def _user_owner(user) -> str:
    """Preferred display handle for a request's owner: GitHub login if we
    have it, else the email local-part."""
    login = _user_github_login(user)
    if login:
        return login
    email = getattr(user, "email", "") or ""
    return email.split("@", 1)[0]


class OwnerAttributionMixin(serializers.Serializer):
    """Adds owner display fields + an is_owner flag (relative to the
    requesting user) to an inference-request serializer."""

    owner = serializers.SerializerMethodField()
    github_login = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()

    def get_owner(self, obj) -> str:
        return _user_owner(obj.user)

    def get_github_login(self, obj):
        return _user_github_login(obj.user)

    def get_is_owner(self, obj) -> bool:
        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and obj.user_id == request.user.id
        )


class SharingFieldsMixin(serializers.Serializer):
    """Adds visibility + curation fields to an inference-request serializer:
    the visibility level, the (owner-only) share token, the aggregate star
    count, and per-viewer ``is_starred`` / ``is_bookmarked`` flags.

    The flags read annotations (``user_has_starred`` / ``user_has_bookmarked``)
    when the view provides them, so list endpoints avoid an N+1; otherwise they
    fall back to a per-row existence check."""

    visibility = serializers.CharField(read_only=True)
    share_token = serializers.SerializerMethodField()
    star_count = serializers.IntegerField(read_only=True)
    is_starred = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()

    def _is_owner(self, obj) -> bool:
        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and obj.user_id == request.user.id
        )

    def get_share_token(self, obj):
        # Only the owner needs the token (to build share links); don't leak the
        # link handle for others' content on shared/profile views.
        return obj.share_token if self._is_owner(obj) else None

    def get_is_starred(self, obj) -> bool:
        if hasattr(obj, "user_has_starred"):
            return bool(obj.user_has_starred)
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.stars.filter(user=request.user).exists()

    def get_is_bookmarked(self, obj) -> bool:
        if hasattr(obj, "user_has_bookmarked"):
            return bool(obj.user_has_bookmarked)
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.bookmarks.filter(user=request.user).exists()


SHARING_FIELDS = [
    "visibility",
    "share_token",
    "star_count",
    "is_starred",
    "is_bookmarked",
]


class InferenceProviderMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = ["id", "name"]


class InferenceRequestSerializer(serializers.ModelSerializer):
    """Write serializer for POST /requests/ (kept for the create path)."""

    class Meta:
        model = InferenceRequest
        fields = [
            "id",
            "user",
            "inference_type",
            "payload",
            "status",
            "results",
            "created_on",
            "modified_on",
        ]
        read_only_fields = [
            "id",
            "user",
            "status",
            "results",
            "created_on",
            "modified_on",
        ]

    def create(self, validated_data):
        return InferenceRequest.objects.create(**validated_data)


class InferenceRequestListSerializer(
    SharingFieldsMixin, OwnerAttributionMixin, serializers.ModelSerializer
):
    """Slim card view — previews + counts, no full payload/results so the
    list stays cheap even when a request has a long message history.
    Includes owner attribution so the network-wide list can show who ran it."""

    provider = InferenceProviderMiniSerializer(read_only=True)
    usage = serializers.SerializerMethodField()
    prompt_preview = serializers.SerializerMethodField()
    response_preview = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    streamed = serializers.SerializerMethodField()
    has_reasoning = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    output_audio_url = serializers.SerializerMethodField()
    image_urls = serializers.SerializerMethodField()
    input_image_url = serializers.SerializerMethodField()
    model_url = serializers.SerializerMethodField()
    mesh = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    video = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = InferenceRequest
        fields = [
            "id",
            "inference_type",
            "status",
            "model_name",
            "provider",
            "owner",
            "github_login",
            "is_owner",
            *SHARING_FIELDS,
            "latency_ms",
            "usage",
            "audio_seconds",
            "audio_url",
            "output_audio_url",
            "image_count",
            "image_urls",
            "input_image_url",
            "model_url",
            "mesh",
            "video_url",
            "video",
            "cover_image_url",
            "prompt_preview",
            "response_preview",
            "message_count",
            "streamed",
            "has_reasoning",
            "created_on",
            "modified_on",
        ]

    def get_audio_url(self, obj):
        return _input_audio_url(obj, self.context.get("request"))

    def get_output_audio_url(self, obj):
        urls = _asset_urls(obj, self.context.get("request"), "OUTPUT_AUDIO")
        return urls[0] if urls else None

    def get_image_urls(self, obj):
        if obj.inference_type != "IMAGE":
            return []
        return _asset_urls(obj, self.context.get("request"), "OUTPUT_IMAGE")

    def get_input_image_url(self, obj):
        urls = _asset_urls(obj, self.context.get("request"), "INPUT_IMAGE")
        return urls[0] if urls else None

    def get_model_url(self, obj):
        return _model_url(obj, self.context.get("request"))

    def get_mesh(self, obj):
        return _mesh_meta(obj)

    def get_video_url(self, obj):
        return _video_url(obj, self.context.get("request"))

    def get_video(self, obj):
        return _video_meta(obj)

    def get_cover_image_url(self, obj):
        return _cover_image_url(obj, self.context.get("request"))

    def get_usage(self, obj):
        return _extract_usage(obj.results)

    def get_message_count(self, obj) -> int:
        return len(_extract_messages(obj.payload))

    def get_streamed(self, obj) -> bool:
        return _is_streamed(obj)

    def get_prompt_preview(self, obj) -> str:
        # Image / TTS (and other non-chat) requests carry a flat `prompt` /
        # `input` field instead of chat messages.
        if isinstance(obj.payload, dict) and not _extract_messages(obj.payload):
            for key in ("prompt", "input"):
                if isinstance(obj.payload.get(key), str):
                    return _truncate(obj.payload[key])
        msgs = _extract_messages(obj.payload)
        for m in reversed(msgs):
            if m["role"] == "user":
                return _truncate(m["content"])
        return _truncate(msgs[-1]["content"]) if msgs else ""

    def get_response_preview(self, obj) -> str:
        return _truncate(_extract_response_text(obj.results))

    def get_has_reasoning(self, obj) -> bool:
        return bool(_extract_reasoning(obj.results))


class InferenceRequestDetailSerializer(
    SharingFieldsMixin, OwnerAttributionMixin, serializers.ModelSerializer
):
    """Full detail view — normalized messages + response plus the raw
    payload/results so the dashboard can show everything, fully expanded."""

    provider = InferenceProviderMiniSerializer(read_only=True)
    usage = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    response_text = serializers.SerializerMethodField()
    reasoning = serializers.SerializerMethodField()
    streamed = serializers.SerializerMethodField()
    tokens_per_second = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    output_audio_url = serializers.SerializerMethodField()
    transcription = serializers.SerializerMethodField()
    image_urls = serializers.SerializerMethodField()
    input_image_url = serializers.SerializerMethodField()
    model_url = serializers.SerializerMethodField()
    mesh = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    video = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = InferenceRequest
        fields = [
            "id",
            "user",
            "inference_type",
            "status",
            "model_name",
            "provider",
            "owner",
            "github_login",
            "is_owner",
            *SHARING_FIELDS,
            "latency_ms",
            "ttft_ms",
            "tokens_per_second",
            "usage",
            "audio_seconds",
            "audio_url",
            "output_audio_url",
            "transcription",
            "image_count",
            "image_urls",
            "input_image_url",
            "model_url",
            "mesh",
            "video_url",
            "video",
            "cover_image_url",
            "messages",
            "response_text",
            "reasoning",
            "streamed",
            "payload",
            "results",
            "created_on",
            "modified_on",
        ]
        read_only_fields = fields

    def get_audio_url(self, obj):
        return _input_audio_url(obj, self.context.get("request"))

    def get_output_audio_url(self, obj):
        urls = _asset_urls(obj, self.context.get("request"), "OUTPUT_AUDIO")
        return urls[0] if urls else None

    def get_transcription(self, obj):
        return _transcription(obj.results)

    def get_image_urls(self, obj):
        if obj.inference_type != "IMAGE":
            return []
        return _asset_urls(obj, self.context.get("request"), "OUTPUT_IMAGE")

    def get_input_image_url(self, obj):
        urls = _asset_urls(obj, self.context.get("request"), "INPUT_IMAGE")
        return urls[0] if urls else None

    def get_model_url(self, obj):
        return _model_url(obj, self.context.get("request"))

    def get_mesh(self, obj):
        return _mesh_meta(obj)

    def get_video_url(self, obj):
        return _video_url(obj, self.context.get("request"))

    def get_video(self, obj):
        return _video_meta(obj)

    def get_cover_image_url(self, obj):
        return _cover_image_url(obj, self.context.get("request"))

    def get_usage(self, obj):
        return _extract_usage(obj.results)

    def get_messages(self, obj) -> list[dict]:
        return _extract_messages(obj.payload)

    def get_response_text(self, obj) -> str:
        return _extract_response_text(obj.results)

    def get_reasoning(self, obj) -> str:
        return _extract_reasoning(obj.results)

    def get_streamed(self, obj) -> bool:
        return _is_streamed(obj)

    def get_tokens_per_second(self, obj):
        # Throughput on generated tokens: completion_tokens / generation time
        # (total latency minus time-to-first-token), the OpenRouter definition.
        if not obj.completion_tokens or not obj.latency_ms:
            return None
        gen_ms = obj.latency_ms - (obj.ttft_ms or 0)
        if gen_ms <= 0:
            return None
        return round(obj.completion_tokens / (gen_ms / 1000), 1)


class ProviderServiceSerializer(serializers.ModelSerializer):
    """Owner-facing view of one of their services + its access policy."""

    provider = InferenceProviderMiniSerializer(read_only=True)
    models = serializers.SerializerMethodField()

    class Meta:
        model = ProviderService
        fields = [
            "id",
            "provider",
            "name",
            "host_id",
            "engine",
            "is_active",
            "access_policy",
            "allowed_github_users",
            "models",
        ]
        read_only_fields = [
            "id",
            "provider",
            "name",
            "host_id",
            "engine",
            "is_active",
            "models",
        ]

    def get_models(self, obj) -> list[str]:
        return [m.name for m in obj.models.all() if m.is_active]

    def validate_allowed_github_users(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list of GitHub usernames.")
        cleaned, seen = [], set()
        for entry in value:
            if not isinstance(entry, str):
                raise serializers.ValidationError("Each username must be a string.")
            handle = entry.strip().lstrip("@")
            key = handle.lower()
            if handle and key not in seen:
                seen.add(key)
                cleaned.append(handle)
        return cleaned

    def validate(self, attrs):
        # Normalize: only RESTRICTED keeps an allowlist.
        policy = attrs.get("access_policy", getattr(self.instance, "access_policy", None))
        if policy != ProviderService.ACCESS_RESTRICTED:
            attrs["allowed_github_users"] = []
        return attrs


class InferenceRequestVisibilitySerializer(serializers.ModelSerializer):
    """Owner-only write serializer to change a request's visibility from the
    edit-visibility modal (PATCH /requests/<id>/)."""

    class Meta:
        model = InferenceRequest
        fields = ["id", "visibility"]
        read_only_fields = ["id"]

    def validate_visibility(self, value):
        if value not in VISIBILITY_VALUES:
            raise serializers.ValidationError(
                f"Must be one of {sorted(VISIBILITY_VALUES)}."
            )
        return value


class CollectionSerializer(serializers.ModelSerializer):
    """Read view of a collection — metadata + counts + owner attribution. The
    items themselves are returned by the collection-detail endpoint."""

    item_count = serializers.SerializerMethodField()
    audio_count = serializers.SerializerMethodField()
    video_count = serializers.SerializerMethodField()
    total_audio_seconds = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    github_login = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "visibility",
            "item_count",
            "audio_count",
            "video_count",
            "total_audio_seconds",
            "cover_image_url",
            "owner",
            "github_login",
            "is_owner",
            "created_on",
            "modified_on",
        ]
        read_only_fields = [
            "id",
            "slug",
            "item_count",
            "audio_count",
            "video_count",
            "total_audio_seconds",
            "cover_image_url",
            "owner",
            "github_login",
            "is_owner",
            "created_on",
            "modified_on",
        ]

    def get_item_count(self, obj) -> int:
        if hasattr(obj, "item_count"):
            return obj.item_count
        return obj.items.count()

    def get_audio_count(self, obj) -> int:
        if hasattr(obj, "audio_count"):
            return obj.audio_count
        return obj.items.filter(request__inference_type="MUSIC").count()

    def get_video_count(self, obj) -> int:
        if hasattr(obj, "video_count"):
            return obj.video_count
        return obj.items.filter(request__inference_type="VIDEO").count()

    def get_total_audio_seconds(self, obj):
        if hasattr(obj, "total_audio_seconds"):
            return obj.total_audio_seconds
        return obj.items.filter(request__inference_type="MUSIC").aggregate(
            s=Sum("request__audio_seconds")
        )["s"]

    def get_cover_image_url(self, obj):
        return _cover_image_url(obj, self.context.get("request"))

    def get_owner(self, obj) -> str:
        return _user_owner(obj.user)

    def get_github_login(self, obj):
        return _user_github_login(obj.user)

    def get_is_owner(self, obj) -> bool:
        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and obj.user_id == request.user.id
        )


class CollectionWriteSerializer(serializers.ModelSerializer):
    """Create / update a collection. ``slug`` is derived server-side from the
    name (unique per user), so it isn't accepted from the client."""

    class Meta:
        model = Collection
        fields = ["name", "description", "visibility"]

    def validate_visibility(self, value):
        if value not in VISIBILITY_VALUES:
            raise serializers.ValidationError(
                f"Must be one of {sorted(VISIBILITY_VALUES)}."
            )
        return value

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name cannot be blank.")
        return value


# --- Content moderation ------------------------------------------------------


class ContentReportCreateSerializer(serializers.ModelSerializer):
    """Member-facing: file a report against a request. The request, reporter,
    and status are all set by the view, never accepted from the client."""

    class Meta:
        model = ContentReport
        fields = ["reason", "details"]

    def validate_reason(self, value):
        valid = {c[0] for c in ContentReport._meta.get_field("reason").choices}
        if value not in valid:
            raise serializers.ValidationError(f"Must be one of {sorted(valid)}.")
        return value

    def validate_details(self, value):
        return (value or "").strip()[:2000]


class ReportedRequestMiniSerializer(serializers.ModelSerializer):
    """Slim view of the reported request, embedded in the staff queue so a
    moderator can triage without opening each one. No full payload/results."""

    owner = serializers.SerializerMethodField()
    github_login = serializers.SerializerMethodField()
    prompt_preview = serializers.SerializerMethodField()

    class Meta:
        model = InferenceRequest
        fields = [
            "id",
            "inference_type",
            "model_name",
            "visibility",
            "status",
            "owner",
            "github_login",
            "prompt_preview",
            "created_on",
        ]

    def get_owner(self, obj) -> str:
        return _user_owner(obj.user)

    def get_github_login(self, obj):
        return _user_github_login(obj.user)

    def get_prompt_preview(self, obj) -> str:
        if isinstance(obj.payload, dict) and not _extract_messages(obj.payload):
            for key in ("prompt", "input"):
                if isinstance(obj.payload.get(key), str):
                    return _truncate(obj.payload[key])
        msgs = _extract_messages(obj.payload)
        for m in reversed(msgs):
            if m["role"] == "user":
                return _truncate(m["content"])
        return _truncate(msgs[-1]["content"]) if msgs else ""


class ContentReportSerializer(serializers.ModelSerializer):
    """Staff-facing report: the moderation record plus an embedded preview of
    the reported request and the reporter's handle."""

    request = ReportedRequestMiniSerializer(read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reporter = serializers.SerializerMethodField()
    resolved_by = serializers.SerializerMethodField()

    class Meta:
        model = ContentReport
        fields = [
            "id",
            "request",
            "reporter",
            "reason",
            "reason_display",
            "details",
            "status",
            "status_display",
            "resolution_note",
            "resolved_by",
            "resolved_at",
            "created_on",
        ]
        # Read-only view: skip the auto UniqueTogetherValidator DRF derives from
        # the (reporter, request) constraint — it would otherwise rewrite the
        # read-only `reporter` method field into a hidden write field.
        validators: list = []

    def get_reporter(self, obj):
        return _user_owner(obj.reporter) if obj.reporter else None

    def get_resolved_by(self, obj):
        return _user_owner(obj.resolved_by) if obj.resolved_by else None


class ContentReportUpdateSerializer(serializers.ModelSerializer):
    """Staff-facing: triage a report. Only the outcome fields are writable; the
    view stamps resolved_by/resolved_at when moving to a terminal status."""

    class Meta:
        model = ContentReport
        fields = ["status", "resolution_note"]

    def validate_status(self, value):
        valid = {c[0] for c in ContentReport._meta.get_field("status").choices}
        if value not in valid:
            raise serializers.ValidationError(f"Must be one of {sorted(valid)}.")
        return value
