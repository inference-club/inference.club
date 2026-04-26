from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InferenceRequest, Provider, ProviderModel
from .pagination import StandardResultsSetPagination
from .serializers import (
    HeartbeatSerializer,
    InferenceRequestSerializer,
    ProviderSerializer,
)


class InferenceRequestView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InferenceRequestSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return InferenceRequest.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RetrieveInferenceRequestView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InferenceRequestSerializer
    lookup_field = "id"

    def get_queryset(self):
        return InferenceRequest.objects.filter(user=self.request.user)


class AgentHeartbeatView(APIView):
    """Receive a heartbeat from an inference-club-agent.

    Authenticated by the user's API key (Bearer token). Upserts the Provider
    keyed by ``(user, name)`` and replaces its model set with what the agent
    currently advertises.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        provider, _ = Provider.objects.update_or_create(
            user=request.user,
            name=data["name"],
            defaults={
                "callback_url": data["callback_url"],
                "last_heartbeat_at": timezone.now(),
                "is_active": True,
            },
        )

        # Replace the model set with what the agent reported. Cheap for MVP;
        # a diff-based approach can come later if churn matters.
        provider.models.all().delete()
        ProviderModel.objects.bulk_create(
            [
                ProviderModel(
                    provider=provider,
                    name=m["name"],
                    context_window=m.get("context_window"),
                )
                for m in data["models"]
            ]
        )

        return Response(
            ProviderSerializer(provider).data, status=status.HTTP_200_OK
        )


class ProviderListView(generics.ListAPIView):
    """List the authenticated user's providers (for the /providers UI page)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderSerializer

    def get_queryset(self):
        return (
            Provider.objects.filter(user=self.request.user)
            .prefetch_related("models")
        )
