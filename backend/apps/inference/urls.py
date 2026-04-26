from django.urls import path
from .views import (
    AgentHeartbeatView,
    InferenceRequestView,
    ProviderListView,
    RetrieveInferenceRequestView,
)

app_name = "inference"

urlpatterns = [
    path("requests/", InferenceRequestView.as_view(), name="inference-requests"),
    path(
        "requests/<int:id>/",
        RetrieveInferenceRequestView.as_view(),
        name="inference-detail",
    ),
    path("agent/heartbeat/", AgentHeartbeatView.as_view(), name="agent-heartbeat"),
    path("providers/", ProviderListView.as_view(), name="provider-list"),
]
