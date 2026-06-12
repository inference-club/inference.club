"""Tests for content moderation: members reporting inference requests, and the
staff-only admin surface (activity dashboard + moderation queue)."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from social_django.models import UserSocialAuth

from apps.inference.models import (
    ContentReport,
    InferenceRequest,
    REPORT_STATUS_RESOLVED,
    VISIBILITY_SECRET,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def staff(db):
    # handle mirrors the GitHub login, as the social-auth pipeline guarantees
    # in production (attribution now reads the handle, PRD 08).
    u = User.objects.create_user(
        email="staff@example.com", password="pw", is_staff=True, handle="staffer"
    )
    UserSocialAuth.objects.create(
        user=u, provider="github", uid="10", extra_data={"login": "staffer"}
    )
    return u


@pytest.fixture
def alice(db):
    return User.objects.create_user(email="alice@example.com", password="pw")


@pytest.fixture
def bob(db):
    return User.objects.create_user(email="bob@example.com", password="pw")


def make_request(user, visibility="PUBLIC", **kw):
    return InferenceRequest.objects.create(
        user=user,
        inference_type="LLM",
        payload={"prompt": "hi"},
        visibility=visibility,
        **kw,
    )


@pytest.mark.django_db
class TestReporting:
    def test_member_can_report_visible_request(self, api_client, alice, bob):
        ir = make_request(alice)
        api_client.force_authenticate(bob)
        resp = api_client.post(
            f"/api/inference/requests/{ir.id}/report/",
            {"reason": "SPAM", "details": "junk"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["reported"] is True
        assert resp.data["already_reported"] is False
        report = ContentReport.objects.get(request=ir, reporter=bob)
        assert report.reason == "SPAM"
        assert report.status == "OPEN"

    def test_reporting_is_idempotent_per_member(self, api_client, alice, bob):
        ir = make_request(alice)
        api_client.force_authenticate(bob)
        first = api_client.post(
            f"/api/inference/requests/{ir.id}/report/",
            {"reason": "SPAM"},
            format="json",
        )
        second = api_client.post(
            f"/api/inference/requests/{ir.id}/report/",
            {"reason": "HATE"},
            format="json",
        )
        assert first.status_code == 201
        assert second.status_code == 200
        assert second.data["already_reported"] is True
        # Only one report, keeping the original reason.
        assert ContentReport.objects.filter(request=ir, reporter=bob).count() == 1
        assert ContentReport.objects.get(request=ir, reporter=bob).reason == "SPAM"

    def test_cannot_report_invisible_request(self, api_client, alice, bob):
        ir = make_request(alice, visibility=VISIBILITY_SECRET)
        api_client.force_authenticate(bob)
        resp = api_client.post(
            f"/api/inference/requests/{ir.id}/report/",
            {"reason": "SPAM"},
            format="json",
        )
        assert resp.status_code == 404
        assert not ContentReport.objects.filter(request=ir).exists()

    def test_anonymous_cannot_report(self, api_client, alice):
        ir = make_request(alice)
        resp = api_client.post(
            f"/api/inference/requests/{ir.id}/report/",
            {"reason": "SPAM"},
            format="json",
        )
        assert resp.status_code in (401, 403)

    def test_invalid_reason_rejected(self, api_client, alice, bob):
        ir = make_request(alice)
        api_client.force_authenticate(bob)
        resp = api_client.post(
            f"/api/inference/requests/{ir.id}/report/",
            {"reason": "NONSENSE"},
            format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAdminAccess:
    def test_member_forbidden_from_admin(self, api_client, alice):
        api_client.force_authenticate(alice)
        assert api_client.get("/api/admin/activity/").status_code == 403
        assert api_client.get("/api/admin/reports/").status_code == 403

    def test_anonymous_forbidden_from_admin(self, api_client):
        assert api_client.get("/api/admin/activity/").status_code in (401, 403)

    def test_staff_can_read_activity(self, api_client, staff, alice):
        make_request(alice)
        api_client.force_authenticate(staff)
        resp = api_client.get("/api/admin/activity/")
        assert resp.status_code == 200
        body = resp.data
        for key in ("users", "requests", "tokens", "network", "moderation", "daily"):
            assert key in body
        assert body["requests"]["total"] >= 1
        assert body["users"]["staff"] >= 1


@pytest.mark.django_db
class TestModerationQueue:
    def _report(self, alice, bob):
        ir = make_request(alice)
        return ir, ContentReport.objects.create(
            request=ir, reporter=bob, reason="SPAM"
        )

    def test_queue_lists_open_reports_with_preview(self, api_client, staff, alice, bob):
        ir, report = self._report(alice, bob)
        api_client.force_authenticate(staff)
        resp = api_client.get("/api/admin/reports/")
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        row = resp.data["results"][0]
        assert row["reporter"] == "bob"  # email local-part (no github handle)
        assert row["request"]["id"] == ir.id
        assert "prompt_preview" in row["request"]

    def test_resolve_stamps_resolver_and_leaves_queue(
        self, api_client, staff, alice, bob
    ):
        ir, report = self._report(alice, bob)
        api_client.force_authenticate(staff)
        resp = api_client.patch(
            f"/api/admin/reports/{report.id}/",
            {"status": "RESOLVED", "resolution_note": "ok"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "RESOLVED"
        assert resp.data["resolved_by"] == "staffer"
        report.refresh_from_db()
        assert report.resolved_at is not None
        # No longer in the default (open) queue, but visible under ?status=all.
        assert api_client.get("/api/admin/reports/").data["count"] == 0
        assert api_client.get("/api/admin/reports/?status=all").data["count"] == 1

    def test_hide_takes_content_down_and_resolves_reports(
        self, api_client, staff, alice, bob
    ):
        ir, report = self._report(alice, bob)
        api_client.force_authenticate(staff)
        resp = api_client.post(
            f"/api/admin/requests/{ir.id}/moderate/",
            {"action": "hide"},
            format="json",
        )
        assert resp.status_code == 200
        ir.refresh_from_db()
        assert ir.visibility == VISIBILITY_SECRET
        report.refresh_from_db()
        assert report.status == REPORT_STATUS_RESOLVED
        assert report.resolved_by == staff

    def test_delete_removes_request_and_reports(self, api_client, staff, alice, bob):
        ir, report = self._report(alice, bob)
        api_client.force_authenticate(staff)
        resp = api_client.post(
            f"/api/admin/requests/{ir.id}/moderate/",
            {"action": "delete"},
            format="json",
        )
        assert resp.status_code == 200
        assert not InferenceRequest.objects.filter(id=ir.id).exists()
        assert not ContentReport.objects.filter(id=report.id).exists()

    def test_member_cannot_moderate(self, api_client, alice, bob):
        ir = make_request(alice)
        api_client.force_authenticate(bob)
        resp = api_client.post(
            f"/api/admin/requests/{ir.id}/moderate/",
            {"action": "delete"},
            format="json",
        )
        assert resp.status_code in (403, 404)
        assert InferenceRequest.objects.filter(id=ir.id).exists()
