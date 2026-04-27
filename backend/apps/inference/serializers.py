from rest_framework import serializers

from .models import InferenceRequest, Provider, ProviderModel


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


class ProviderSerializer(serializers.ModelSerializer):
    models = ProviderModelSerializer(many=True, read_only=True)
    is_online = serializers.BooleanField(read_only=True)

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
            "created_on",
        ]


class PublicProviderSerializer(ProviderSerializer):
    """Network-wide listing. Adds ``github_login`` (the user's GitHub
    handle, since signup is GitHub-only) and ``owner`` (preferred display
    name — github_login when present, otherwise the email local-part as a
    safety net).
    """

    owner = serializers.SerializerMethodField()
    github_login = serializers.SerializerMethodField()

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
