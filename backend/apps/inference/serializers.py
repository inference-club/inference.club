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
    """Network-wide listing. Adds an ``owner`` field (email local-part)
    so logged-in users can see whose node is whose without leaking the
    full email address.
    """

    owner = serializers.SerializerMethodField()

    class Meta(ProviderSerializer.Meta):
        fields = ProviderSerializer.Meta.fields + ["owner"]

    def get_owner(self, obj) -> str:
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
