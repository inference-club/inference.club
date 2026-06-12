from django.urls import path

from .staff_views import (
    AdminAccessCodeDetailView,
    AdminAccessCodeListView,
    AdminAccessPolicyView,
    AdminGuestListView,
    AdminGuestPurgeView,
    AdminGuestRevokeView,
)

app_name = "accounts_staff"

urlpatterns = [
    path(
        "access-codes/",
        AdminAccessCodeListView.as_view(),
        name="admin-access-code-list",
    ),
    path(
        "access-codes/<int:id>/",
        AdminAccessCodeDetailView.as_view(),
        name="admin-access-code-detail",
    ),
    path("guests/", AdminGuestListView.as_view(), name="admin-guest-list"),
    path(
        "guests/<int:id>/revoke/",
        AdminGuestRevokeView.as_view(),
        name="admin-guest-revoke",
    ),
    path(
        "guests/<int:id>/purge/",
        AdminGuestPurgeView.as_view(),
        name="admin-guest-purge",
    ),
    path(
        "access-policy/",
        AdminAccessPolicyView.as_view(),
        name="admin-access-policy",
    ),
]
