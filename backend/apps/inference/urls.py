from django.urls import path
from .views import (
    AgentManifestView,
    AgentRegisterView,
    AllProvidersListView,
    InferenceRequestView,
    ProviderListView,
    ProviderManifestView,
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
    path("agent/manifest/", AgentManifestView.as_view(), name="agent-manifest"),
    path("providers/", ProviderListView.as_view(), name="provider-list"),
    path("providers/all/", AllProvidersListView.as_view(), name="provider-list-all"),
    path(
        "providers/<int:id>/refresh-models/",
        RefreshProviderModelsView.as_view(),
        name="provider-refresh-models",
    ),
    path(
        "providers/<int:id>/manifest/",
        ProviderManifestView.as_view(),
        name="provider-manifest",
    ),
]
