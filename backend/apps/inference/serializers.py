from rest_framework import serializers

from .models import InferenceRequest, Provider, ProviderModel, ServiceManifest


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
            "registered_at",
            "last_seen_at",
            "models",
            "manifest",
            "created_on",
        ]


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


class InferenceRequestSerializer(serializers.ModelSerializer):
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
