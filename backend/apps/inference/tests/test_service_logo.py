"""Per-service custom logo: the ServiceLogoView upload/delete endpoint and the
manifest-serializer enrichment that surfaces ``logo_url`` (and, for owners,
``service_id``) inside the parsed manifest the frontend renders."""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inference.models import Provider, ProviderService, ServiceManifest
from apps.inference.serializers import (
    PublicServiceManifestSerializer,
    ServiceManifestSerializer,
)

User = get_user_model()

# A minimal valid 1x1 PNG so ImageField accepts it.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def other(db):
    return User.objects.create_user(email="other@example.com", password="x")


@pytest.fixture
def provider(owner):
    return Provider.objects.create(
        user=owner, name="host", tailnet_hostname="h1",
        is_active=True, last_seen_at=timezone.now(),
    )


@pytest.fixture
def service(provider):
    return ProviderService.objects.create(provider=provider, name="vllm-main")


def _png():
    return SimpleUploadedFile("logo.png", PNG, content_type="image/png")


def _url(svc):
    return f"/api/inference/services/{svc.id}/logo/"


@pytest.mark.django_db
class TestServiceLogoUpload:
    def test_owner_uploads(self, owner, service):
        c = APIClient()
        c.force_authenticate(owner)
        res = c.post(_url(service), {"logo": _png()}, format="multipart")
        assert res.status_code == 200, res.data
        assert res.data["logo_url"]
        service.refresh_from_db()
        assert service.logo

    def test_non_owner_cannot_touch(self, other, service):
        c = APIClient()
        c.force_authenticate(other)
        res = c.post(_url(service), {"logo": _png()}, format="multipart")
        assert res.status_code == 404
        service.refresh_from_db()
        assert not service.logo

    def test_rejects_non_image(self, owner, service):
        c = APIClient()
        c.force_authenticate(owner)
        bad = SimpleUploadedFile("x.txt", b"hello", content_type="text/plain")
        res = c.post(_url(service), {"logo": bad}, format="multipart")
        assert res.status_code == 415

    def test_delete_clears(self, owner, service):
        c = APIClient()
        c.force_authenticate(owner)
        c.post(_url(service), {"logo": _png()}, format="multipart")
        res = c.delete(_url(service))
        assert res.status_code == 204
        service.refresh_from_db()
        assert not service.logo


@pytest.mark.django_db
class TestManifestLogoEnrichment:
    def _manifest(self, provider):
        return ServiceManifest.objects.create(
            provider=provider,
            raw_yaml="",
            parsed={"hosts": [{"id": "a", "services": [
                {"name": "vllm-main", "engine": "vllm"},
            ]}]},
        )

    def test_logo_url_surfaced_in_parsed(self, provider, service):
        service.logo.save("l.png", ContentFile(PNG), save=False)
        service.save()
        manifest = self._manifest(provider)

        public_svc = PublicServiceManifestSerializer(manifest).data[
            "parsed"]["hosts"][0]["services"][0]
        assert public_svc["logo_url"]
        # The public view never exposes the internal service id.
        assert "service_id" not in public_svc

        owner_svc = ServiceManifestSerializer(manifest).data[
            "parsed"]["hosts"][0]["services"][0]
        assert owner_svc["logo_url"]
        assert owner_svc["service_id"] == service.id

    def test_no_logo_leaves_parsed_untouched(self, provider, service):
        manifest = self._manifest(provider)
        svc = PublicServiceManifestSerializer(manifest).data[
            "parsed"]["hosts"][0]["services"][0]
        assert "logo_url" not in svc
