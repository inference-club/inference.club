import re

from rest_framework import serializers

from .models import (
    InferenceRequest,
    Provider,
    ProviderModel,
    ProviderService,
    ServiceManifest,
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
    models = ProviderModelSerializer(many=True, read_only=True)
    is_online = serializers.BooleanField(read_only=True)
    manifest = ServiceManifestSerializer(read_only=True)

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


class InferenceRequestListSerializer(OwnerAttributionMixin, serializers.ModelSerializer):
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
            "latency_ms",
            "usage",
            "prompt_preview",
            "response_preview",
            "message_count",
            "streamed",
            "has_reasoning",
            "created_on",
            "modified_on",
        ]

    def get_usage(self, obj):
        return _extract_usage(obj.results)

    def get_message_count(self, obj) -> int:
        return len(_extract_messages(obj.payload))

    def get_streamed(self, obj) -> bool:
        return _is_streamed(obj)

    def get_prompt_preview(self, obj) -> str:
        msgs = _extract_messages(obj.payload)
        for m in reversed(msgs):
            if m["role"] == "user":
                return _truncate(m["content"])
        return _truncate(msgs[-1]["content"]) if msgs else ""

    def get_response_preview(self, obj) -> str:
        return _truncate(_extract_response_text(obj.results))

    def get_has_reasoning(self, obj) -> bool:
        return bool(_extract_reasoning(obj.results))


class InferenceRequestDetailSerializer(OwnerAttributionMixin, serializers.ModelSerializer):
    """Full detail view — normalized messages + response plus the raw
    payload/results so the dashboard can show everything, fully expanded."""

    provider = InferenceProviderMiniSerializer(read_only=True)
    usage = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    response_text = serializers.SerializerMethodField()
    reasoning = serializers.SerializerMethodField()
    streamed = serializers.SerializerMethodField()

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
            "latency_ms",
            "usage",
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
