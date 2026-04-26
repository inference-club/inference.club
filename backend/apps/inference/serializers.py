from rest_framework import serializers
from .models import InferenceRequest, Provider, ProviderModel


class HeartbeatModelSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    context_window = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class HeartbeatSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    callback_url = serializers.URLField()
    models = HeartbeatModelSerializer(many=True)
    health = serializers.JSONField(required=False)


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
            "callback_url",
            "is_active",
            "is_online",
            "last_heartbeat_at",
            "models",
            "created_on",
        ]


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
        # user is added via view's perform_create
        return InferenceRequest.objects.create(**validated_data)
