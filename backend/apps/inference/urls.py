from django.urls import path
from .openai_views import RetryInferenceRequestView
from .views import (
    AgentManifestView,
    AgentRegisterView,
    AllInferenceRequestView,
    AllProvidersListView,
    BookmarkedRequestsView,
    CollectionDetailView,
    CollectionItemView,
    CollectionListCreateView,
    InferenceRequestView,
    LeaderboardView,
    MediaAssetView,
    ModelCatalogView,
    NetworkStatusView,
    ProviderListView,
    RateLimitUsageView,
    ProviderManifestView,
    ProviderModelsCatalogView,
    ProviderServiceListView,
    ProviderServiceUpdateView,
    ProviderUpdateView,
    RefreshProviderModelsView,
    RequestBookmarkView,
    RequestReportView,
    RequestStarView,
    RetrieveInferenceRequestView,
    SharedRequestView,
    StarredRequestsView,
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
        "requests/starred/",
        StarredRequestsView.as_view(),
        name="inference-requests-starred",
    ),
    path(
        "requests/bookmarked/",
        BookmarkedRequestsView.as_view(),
        name="inference-requests-bookmarked",
    ),
    path(
        "requests/<int:id>/",
        RetrieveInferenceRequestView.as_view(),
        name="inference-detail",
    ),
    path(
        "requests/<int:id>/star/",
        RequestStarView.as_view(),
        name="inference-request-star",
    ),
    path(
        "requests/<int:id>/bookmark/",
        RequestBookmarkView.as_view(),
        name="inference-request-bookmark",
    ),
    path(
        "requests/<int:id>/report/",
        RequestReportView.as_view(),
        name="inference-request-report",
    ),
    path(
        "requests/<int:id>/retry/",
        RetryInferenceRequestView.as_view(),
        name="inference-request-retry",
    ),
    path(
        "shared/<str:share_token>/",
        SharedRequestView.as_view(),
        name="inference-shared",
    ),
    path(
        "collections/",
        CollectionListCreateView.as_view(),
        name="collection-list",
    ),
    path(
        "collections/<slug:slug>/",
        CollectionDetailView.as_view(),
        name="collection-detail",
    ),
    path(
        "collections/<slug:slug>/items/<int:request_id>/",
        CollectionItemView.as_view(),
        name="collection-item",
    ),
    path("agent/register/", AgentRegisterView.as_view(), name="agent-register"),
    path("agent/manifest/", AgentManifestView.as_view(), name="agent-manifest"),
    path("providers/", ProviderListView.as_view(), name="provider-list"),
    path("providers/all/", AllProvidersListView.as_view(), name="provider-list-all"),
    path("providers/<int:id>/", ProviderUpdateView.as_view(), name="provider-detail"),
    path("network/", NetworkStatusView.as_view(), name="network-status"),
    path("models/", ModelCatalogView.as_view(), name="model-catalog"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("usage/", RateLimitUsageView.as_view(), name="rate-limit-usage"),
    path("assets/<int:id>/", MediaAssetView.as_view(), name="media-asset"),
    path(
        "provider/models/",
        ProviderModelsCatalogView.as_view(),
        name="provider-models-catalog",
    ),
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
