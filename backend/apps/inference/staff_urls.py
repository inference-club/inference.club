from django.urls import path

from .staff_views import (
    AdminActivityView,
    AdminReportDetailView,
    AdminReportListView,
    AdminRequestModerateView,
    AdminRoadmapView,
)

app_name = "staff"

urlpatterns = [
    path("activity/", AdminActivityView.as_view(), name="admin-activity"),
    path("roadmap/", AdminRoadmapView.as_view(), name="admin-roadmap"),
    path("reports/", AdminReportListView.as_view(), name="admin-report-list"),
    path(
        "reports/<int:id>/",
        AdminReportDetailView.as_view(),
        name="admin-report-detail",
    ),
    path(
        "requests/<int:id>/moderate/",
        AdminRequestModerateView.as_view(),
        name="admin-request-moderate",
    ),
]
