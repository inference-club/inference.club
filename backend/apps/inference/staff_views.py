"""Staff-only admin surface: a site-activity dashboard and the content
moderation queue. Every view here is gated by ``IsStaff`` (see
apps.core.permissions); none of it is reachable by ordinary members.

Mounted at /api/admin/ (see apps.inference.staff_urls).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsStaff

from .models import (
    ContentReport,
    InferenceRequest,
    Provider,
    ProviderModel,
    ProviderService,
    REPORT_OPEN_STATUSES,
    REPORT_STATUS_DISMISSED,
    REPORT_STATUS_RESOLVED,
)
from .pagination import StandardResultsSetPagination
from .serializers import (
    ContentReportSerializer,
    ContentReportUpdateSerializer,
    _user_github_login,
    _user_owner,
)


class AdminActivityView(APIView):
    """GET /api/admin/activity/ — a staff snapshot of what's happening on the
    site: members, inference traffic, the live node network, and the moderation
    backlog. Aggregates only; no prompt/response content is returned here.
    """

    permission_classes = [IsStaff]

    def get(self, request):
        now = timezone.now()
        day = now - timedelta(hours=24)
        week = now - timedelta(days=7)
        month = now - timedelta(days=30)

        User = get_user_model()
        users_qs = User.objects.all()
        ir = InferenceRequest.objects.all()

        # --- users -----------------------------------------------------------
        active_24h = (
            ir.filter(created_on__gte=day).values("user").distinct().count()
        )
        guests_qs = users_qs.filter(account_type=User.AccountType.GUEST)
        users = {
            "total": users_qs.count(),
            "new_24h": users_qs.filter(date_joined__gte=day).count(),
            "new_7d": users_qs.filter(date_joined__gte=week).count(),
            "new_30d": users_qs.filter(date_joined__gte=month).count(),
            "active_24h": active_24h,
            "staff": users_qs.filter(is_staff=True).count(),
            # Anonymous access (PRD 08): rollout visibility for the dial.
            "guests_total": guests_qs.count(),
            "guests_active": guests_qs.filter(is_active=True).count(),
            "guests_new_24h": guests_qs.filter(date_joined__gte=day).count(),
            "guests_new_7d": guests_qs.filter(date_joined__gte=week).count(),
            "passcode_accounts": users_qs.filter(
                account_type=User.AccountType.PASSCODE
            ).count(),
        }

        # --- requests --------------------------------------------------------
        requests = {
            "total": ir.count(),
            "last_24h": ir.filter(created_on__gte=day).count(),
            "last_7d": ir.filter(created_on__gte=week).count(),
            "by_type": [
                {"type": row["inference_type"], "count": row["c"]}
                for row in ir.values("inference_type")
                .annotate(c=Count("id"))
                .order_by("-c")
            ],
        }

        # --- tokens ----------------------------------------------------------
        tokens = {
            "total": ir.aggregate(t=Sum("total_tokens"))["t"] or 0,
            "last_24h": ir.filter(created_on__gte=day).aggregate(
                t=Sum("total_tokens")
            )["t"]
            or 0,
            "last_7d": ir.filter(created_on__gte=week).aggregate(
                t=Sum("total_tokens")
            )["t"]
            or 0,
        }

        # --- nodes / services / models --------------------------------------
        providers = list(
            Provider.objects.filter(is_active=True).select_related("user")
        )
        online = [p for p in providers if p.is_online]
        active_deploys = ProviderModel.objects.filter(
            is_active=True, provider__is_active=True
        )
        network = {
            "providers_total": Provider.objects.count(),
            "providers_active": len(providers),
            "providers_online": len(online),
            "services_active": ProviderService.objects.filter(
                is_active=True, provider__is_active=True
            ).count(),
            "deployments_active": active_deploys.count(),
            "models_distinct": active_deploys.values("catalog_model")
            .distinct()
            .count(),
        }

        # --- moderation ------------------------------------------------------
        reports_qs = ContentReport.objects.all()
        moderation = {
            "open": reports_qs.filter(status__in=REPORT_OPEN_STATUSES).count(),
            "total": reports_qs.count(),
            "resolved": reports_qs.filter(status=REPORT_STATUS_RESOLVED).count(),
            "dismissed": reports_qs.filter(status=REPORT_STATUS_DISMISSED).count(),
        }

        # --- daily request series (last 14 days, zero-filled) ----------------
        start = (now - timedelta(days=13)).date()
        rows = (
            ir.filter(created_on__date__gte=start)
            .annotate(d=TruncDate("created_on"))
            .values("d")
            .annotate(c=Count("id"), t=Sum("total_tokens"))
        )
        by_day = {r["d"]: r for r in rows}
        daily = []
        for i in range(14):
            d = start + timedelta(days=i)
            row = by_day.get(d)
            daily.append(
                {
                    "date": d.isoformat(),
                    "requests": (row["c"] if row else 0),
                    "tokens": ((row["t"] or 0) if row else 0),
                }
            )

        # --- recent signups (handy "who just joined") -----------------------
        recent_users = (
            users_qs.order_by("-date_joined").prefetch_related("social_auth")[:8]
        )
        recent_signups = [
            {
                "owner": _user_owner(u),
                "github_login": _user_github_login(u),
                "joined": u.date_joined.isoformat(),
                "is_staff": u.is_staff,
                "account_type": u.account_type,
            }
            for u in recent_users
        ]

        return Response(
            {
                "generated_at": now.isoformat(),
                "users": users,
                "requests": requests,
                "tokens": tokens,
                "network": network,
                "moderation": moderation,
                "daily": daily,
                "recent_signups": recent_signups,
            }
        )


def _reports_queryset():
    return (
        ContentReport.objects.select_related(
            "request", "request__user", "reporter", "resolved_by"
        ).prefetch_related(
            "request__user__social_auth",
            "reporter__social_auth",
            "resolved_by__social_auth",
        )
    )


class AdminReportListView(generics.ListAPIView):
    """GET /api/admin/reports/ — the content-moderation queue.

    ``?status=OPEN`` (or REVIEWING/RESOLVED/DISMISSED) filters by triage state;
    ``?status=open`` is a convenience alias for "needs attention"
    (OPEN + REVIEWING). Defaults to the needs-attention queue so a moderator
    lands on the actionable items first.
    """

    permission_classes = [IsStaff]
    serializer_class = ContentReportSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = _reports_queryset()
        status_param = (self.request.query_params.get("status") or "").strip()
        if not status_param or status_param.lower() == "open":
            return qs.filter(status__in=REPORT_OPEN_STATUSES)
        if status_param.lower() == "all":
            return qs
        return qs.filter(status=status_param.upper())


class AdminReportDetailView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/admin/reports/<id>/ — triage one report.

    PATCH sets ``status`` and/or ``resolution_note``. Moving to a terminal
    status (RESOLVED / DISMISSED) stamps ``resolved_by`` + ``resolved_at``;
    moving back to an open status clears them.
    """

    permission_classes = [IsStaff]
    lookup_field = "id"

    def get_queryset(self):
        return _reports_queryset()

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return ContentReportUpdateSerializer
        return ContentReportSerializer

    def perform_update(self, serializer):
        report = serializer.save()
        new_status = serializer.validated_data.get("status", report.status)
        if new_status in (REPORT_STATUS_RESOLVED, REPORT_STATUS_DISMISSED):
            report.resolved_by = self.request.user
            report.resolved_at = timezone.now()
        else:
            report.resolved_by = None
            report.resolved_at = None
        report.save(update_fields=["resolved_by", "resolved_at", "modified_on"])

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        # Always return the full, staff-facing representation (with the embedded
        # request preview), not the slim update serializer's fields.
        instance = self.get_object()
        return Response(ContentReportSerializer(instance).data)


class AdminRequestModerateView(APIView):
    """POST /api/admin/requests/<id>/moderate/ — act on reported content.

    ``{"action": "hide"}`` takes the request down by flipping its visibility to
    SECRET (owner-only) so it disappears from every public/member surface while
    preserving it for the record. ``{"action": "delete"}`` removes it entirely
    (cascading its reports). Either way, any still-open reports on the request
    are marked RESOLVED and attributed to the acting moderator.
    """

    permission_classes = [IsStaff]

    def post(self, request, id):
        from .models import VISIBILITY_SECRET

        obj = get_object_or_404(InferenceRequest, id=id)
        action = (request.data.get("action") or "").lower()
        note = (request.data.get("resolution_note") or "").strip()[:2000]

        if action == "delete":
            obj.delete()  # cascades ContentReport rows
            return Response({"action": "delete", "deleted": True})

        if action == "hide":
            obj.visibility = VISIBILITY_SECRET
            obj.save(update_fields=["visibility", "modified_on"])
            obj.reports.filter(status__in=REPORT_OPEN_STATUSES).update(
                status=REPORT_STATUS_RESOLVED,
                resolved_by=request.user,
                resolved_at=timezone.now(),
                resolution_note=note or "Content hidden by moderator.",
            )
            return Response({"action": "hide", "visibility": obj.visibility})

        return Response(
            {"detail": "action must be 'hide' or 'delete'"}, status=400
        )


class AdminRoadmapView(APIView):
    """GET /api/admin/roadmap/ — the Media Pipeline & Narration Studio roadmap.

    Read-only staff view over the git-versioned tracker in ``apps.inference.
    roadmap`` (phases, tasks, status, progress log). The tracker module is the
    source of truth — edit ``roadmap.py`` to update; a future public roadmap
    (PRD 12 V5) can serve ``roadmap_payload(include_internal=False)`` without the
    staff gate. See docs/prd/12-media-pipeline-and-narration-studio.md.
    """

    permission_classes = [IsStaff]

    def get(self, request):
        from .roadmap import roadmap_payload

        return Response(roadmap_payload(include_internal=True))
