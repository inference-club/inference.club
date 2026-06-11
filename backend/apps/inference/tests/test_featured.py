"""Tests for staff-curated featured content (home-page showcase): the
staff-only feature toggle and the public per-modality featured listing."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.inference.models import InferenceRequest, Provider, ServiceManifest

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email="admin@example.com", password="pw", is_staff=True
    )


@pytest.fixture
def alice(db):
    return User.objects.create_user(email="alice@example.com", password="pw")


def make_request(user, inference_type="LLM", visibility="PUBLIC", **kw):
    return InferenceRequest.objects.create(
        user=user,
        inference_type=inference_type,
        payload={"prompt": "hi"},
        visibility=visibility,
        **kw,
    )


def feature_url(ir):
    return reverse("inference:inference-request-feature", args=[ir.id])


@pytest.mark.django_db
class TestFeatureToggle:
    def test_staff_can_feature_and_unfeature(self, api_client, admin, alice):
        ir = make_request(alice)
        api_client.force_authenticate(admin)
        r = api_client.post(feature_url(ir))
        assert r.status_code == 200 and r.data == {"is_featured": True}
        ir.refresh_from_db()
        assert ir.featured_at is not None

        r = api_client.delete(feature_url(ir))
        assert r.status_code == 200 and r.data == {"is_featured": False}
        ir.refresh_from_db()
        assert ir.featured_at is None

    def test_non_staff_cannot_feature(self, api_client, alice):
        ir = make_request(alice)
        api_client.force_authenticate(alice)
        assert api_client.post(feature_url(ir)).status_code == 403
        assert api_client.delete(feature_url(ir)).status_code == 403

    def test_anonymous_cannot_feature(self, api_client, alice):
        ir = make_request(alice)
        assert api_client.post(feature_url(ir)).status_code in (401, 403)

    def test_only_public_can_be_featured(self, api_client, admin, alice):
        for vis in ("UNLISTED", "PRIVATE", "SECRET"):
            ir = make_request(alice, visibility=vis)
            api_client.force_authenticate(admin)
            assert api_client.post(feature_url(ir)).status_code == 400

    def test_is_featured_in_serializers(self, api_client, admin, alice):
        ir = make_request(alice)
        api_client.force_authenticate(admin)
        api_client.post(feature_url(ir))
        r = api_client.get(reverse("inference:inference-detail", args=[ir.id]))
        assert r.data["is_featured"] is True


@pytest.mark.django_db
class TestFeaturedListing:
    url = "/api/inference/featured/"

    def test_latest_per_type_public_only_anonymous(self, api_client, admin, alice):
        old_llm = make_request(alice, "LLM")
        new_llm = make_request(alice, "LLM")
        music = make_request(alice, "MUSIC")
        secret_video = make_request(alice, "VIDEO", visibility="SECRET")
        not_featured = make_request(alice, "IMAGE")

        staff = APIClient()
        staff.force_authenticate(admin)
        for ir in (old_llm, new_llm, music):
            assert staff.post(feature_url(ir)).status_code == 200
        # SECRET can't be featured via the API; simulate a later visibility
        # change after featuring — read path must still exclude it.
        public_then_hidden = make_request(alice, "VIDEO")
        staff.post(feature_url(public_then_hidden))
        public_then_hidden.visibility = "SECRET"
        public_then_hidden.save(update_fields=["visibility"])

        r = api_client.get(self.url)  # anonymous
        assert r.status_code == 200
        by_type = {item["inference_type"]: item for item in r.data}
        assert set(by_type) == {"LLM", "MUSIC"}
        assert by_type["LLM"]["id"] == new_llm.id  # most recent wins
        assert str(not_featured.id) not in {str(i["id"]) for i in r.data}
        assert str(secret_video.id) not in {str(i["id"]) for i in r.data}
        # The card needs the share link + star metadata for everyone.
        assert by_type["MUSIC"]["share_token"] == music.share_token
        assert "star_count" in by_type["MUSIC"]

    def test_empty_when_nothing_featured(self, api_client, alice):
        make_request(alice, "LLM")
        r = api_client.get(self.url)
        assert r.status_code == 200 and r.data == []

    def test_gpus_from_provider_manifest(self, api_client, admin, alice):
        provider = Provider.objects.create(
            user=alice, name="rig", tailnet_hostname="rig-1", agent_port=443
        )
        ServiceManifest.objects.create(
            provider=provider,
            schema_version=1,
            raw_yaml="",
            parsed={
                "hosts": [
                    {"gpus": [{"model": "RTX 4090", "vram_gb": 24}]},
                    {"gpus": [{"model": "RTX 3090"}, {"model": "RTX 4090"}]},
                ]
            },
            is_valid=True,
            validation_errors=[],
        )
        ir = make_request(alice, "LLM", provider=provider)
        staff = APIClient()
        staff.force_authenticate(admin)
        staff.post(feature_url(ir))

        r = api_client.get(self.url)
        assert r.data[0]["gpus"] == ["RTX 4090", "RTX 3090"]
