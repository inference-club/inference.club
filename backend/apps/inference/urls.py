from django.urls import path
from .views import (
    AgentRegisterView,
    InferenceRequestView,
    ProviderListView,
    RefreshProviderModelsView,
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
    path("agent/register/", AgentRegisterView.as_view(), name="agent-register"),
    path("providers/", ProviderListView.as_view(), name="provider-list"),
    path(
        "providers/<int:id>/refresh-models/",
        RefreshProviderModelsView.as_view(),
        name="provider-refresh-models",
    ),
]
