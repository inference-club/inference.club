from django.urls import path

from apps.inference.views import (
    PublicCollectionDetailView,
    PublicUserCollectionsView,
    PublicUserProfileView,
    PublicUserRequestsView,
)

from . import anon_views, registration_views, views

urlpatterns = [
    path("account/", views.Profile.as_view(), name="user-profile"),
    path(
        "account/alias/regenerate/",
        views.AliasRegenerateView.as_view(),
        name="alias-regenerate",
    ),
    # Anonymous access (PRD 08): which sign-in pathways are live, one-click
    # guest accounts, and passcode login.
    path("auth/options/", anon_views.AuthOptionsView.as_view(), name="auth-options"),
    path("auth/guest/", anon_views.GuestLoginView.as_view(), name="auth-guest"),
    path(
        "auth/passcode/",
        anon_views.PasscodeLoginView.as_view(),
        name="auth-passcode",
    ),
    # Email sign-up + confirmation (home-lab auth path, PRD 20).
    path("register/", registration_views.RegisterView.as_view(), name="register"),
    path(
        "auth/confirm/",
        registration_views.ConfirmEmailView.as_view(),
        name="auth-confirm",
    ),
    path(
        "auth/confirm/resend/",
        registration_views.ResendConfirmationView.as_view(),
        name="auth-confirm-resend",
    ),
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
        "users/<str:handle>/",
        PublicUserProfileView.as_view(),
        name="public-user-profile",
    ),
    path(
        "users/<str:handle>/requests/",
        PublicUserRequestsView.as_view(),
        name="public-user-requests",
    ),
    path(
        "users/<str:handle>/collections/",
        PublicUserCollectionsView.as_view(),
        name="public-user-collections",
    ),
    path(
        "users/<str:handle>/collections/<slug:slug>/",
        PublicCollectionDetailView.as_view(),
        name="public-user-collection-detail",
    ),
]
