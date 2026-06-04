from django.urls import path

from apps.inference.views import (
    PublicCollectionDetailView,
    PublicUserCollectionsView,
    PublicUserProfileView,
    PublicUserRequestsView,
)

from . import views

urlpatterns = [
    path("account/", views.Profile.as_view(), name="user-profile"),
    # path("social/<backend>/", views.exchange_token, name="social-auth-callback"),
    path("login/", views.login_view, name="login-view"),
    path("login-set-cookie/", views.login_set_cookie, name="login-view"),
    path("logout/", views.logout_view, name="logout-view"),
    path("token/", views.request_api_token, name="request-api-token"),
    path("token/list/", views.list_api_tokens, name="list-api-tokens"),
    # Public profile — unauthenticated. Mounted here so the URL lands at
    # /api/users/<login>/. The view lives in apps.inference because the
    # manifest data does.
    path(
        "users/<str:github_login>/",
        PublicUserProfileView.as_view(),
        name="public-user-profile",
    ),
    path(
        "users/<str:github_login>/requests/",
        PublicUserRequestsView.as_view(),
        name="public-user-requests",
    ),
    path(
        "users/<str:github_login>/collections/",
        PublicUserCollectionsView.as_view(),
        name="public-user-collections",
    ),
    path(
        "users/<str:github_login>/collections/<slug:slug>/",
        PublicCollectionDetailView.as_view(),
        name="public-user-collection-detail",
    ),
]
