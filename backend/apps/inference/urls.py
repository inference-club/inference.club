from django.urls import path
from .views import (
    AgentManifestView,
    AgentRegisterView,
    AllInferenceRequestView,
    AllProvidersListView,
    InferenceRequestView,
    ProviderListView,
    ProviderManifestView,
    ProviderServiceListView,
    ProviderServiceUpdateView,
    RefreshProviderModelsView,
    RetrieveInferenceRequestView,
)

app_name = "inference"

urlpatterns = [
    path("requests/", InferenceRequestView.as_view(), name="inference-requests"),
    path(
        "requests/all/",
        AllInferenceRequestView.as_view(),
        name="inference-requests-all",
    ),
    path(
        "requests/<int:id>/",
        RetrieveInferenceRequestView.as_view(),
        name="inference-detail",
    ),
    path("agent/register/", AgentRegisterView.as_view(), name="agent-register"),
    path("agent/manifest/", AgentManifestView.as_view(), name="agent-manifest"),
    path("providers/", ProviderListView.as_view(), name="provider-list"),
    path("providers/all/", AllProvidersListView.as_view(), name="provider-list-all"),
    path("services/", ProviderServiceListView.as_view(), name="service-list"),
    path(
        "services/<int:id>/",
        ProviderServiceUpdateView.as_view(),
        name="service-detail",
    ),
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
