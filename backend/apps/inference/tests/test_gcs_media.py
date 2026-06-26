"""Tests for the GCS media path: kind-prefix bucket routing, direct public
URLs in serializers, and the asset route's 302-to-bucket behavior. No GCS
network access — the routed storage builds its backends lazily, so routing
is asserted on bucket names, and the URL/redirect tests run on the test
filesystem storage with MEDIA_DIRECT_PUBLIC_URLS forced on."""
import pytest
from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from apps.inference.models import MediaAsset
from apps.inference.serializers import asset_url
from backend.storage import KindRoutedGCSStorage

User = get_user_model()


class TestKindRoutedGCSStorage:
    @pytest.fixture(autouse=True)
    def _gcs_settings(self, settings):
        settings.GCS_PUBLIC_BUCKET = "pub-bucket"
        settings.GCS_PRIVATE_BUCKET = "priv-bucket"
        settings.GCS_CREDENTIALS_B64 = ""

    def test_input_audio_routes_to_private_bucket(self):
        storage = KindRoutedGCSStorage()
        backend = storage._backend("input_audio/42/abc123/clip.wav")
        assert backend.bucket_name == "priv-bucket"
        assert backend.querystring_auth is True

    def test_public_kinds_route_to_public_bucket(self):
        storage = KindRoutedGCSStorage()
        for key in (
            "output_image/42/abc123/img.png",
            "output_audio/42/abc123/song.mp3",
            "output_video/42/abc123/clip.mp4",
            "output_model/42/abc123/mesh.glb",
            "input_image/42/abc123/in.png",
        ):
            backend = storage._backend(key)
            assert backend.bucket_name == "pub-bucket", key
            assert backend.querystring_auth is False

    def test_public_uploads_get_immutable_cache_control(self):
        storage = KindRoutedGCSStorage()
        params = storage._backend("output_image/x").object_parameters
        assert params["cache_control"] == "public, max-age=31536000, immutable"

    def test_non_public_kinds_route_to_the_private_bucket(self):
        # Inputs + intermediate text documents are owner-gated, never world-
        # readable. This pins the classification so a newly-added kind can't be
        # made public by omission.
        non_public = {k for k, _ in MediaAsset.KIND_CHOICES} - MediaAsset.PUBLIC_KINDS
        assert non_public == {"INPUT_AUDIO", "INPUT_DOC", "OUTPUT_DOC"}
        storage = KindRoutedGCSStorage()
        for k in non_public:
            backend = storage._backend(f"{k.lower()}/42/abc123/file.bin")
            assert backend.bucket_name == "priv-bucket", k
            assert backend.querystring_auth is True

    def test_unknown_prefix_fails_closed_to_private(self):
        # A key with no recognized public kind prefix must not leak to public.
        backend = KindRoutedGCSStorage()._backend("mystery/42/x.bin")
        assert backend.bucket_name == "priv-bucket"


def _asset(user, kind, name="f.bin", body=b"x"):
    asset = MediaAsset(user=user, kind=kind, content_type="application/octet-stream",
                       size_bytes=len(body))
    asset.file.save(name, ContentFile(body), save=False)
    asset.save()
    return asset


@pytest.mark.django_db
class TestAssetUrls:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(email="gcs@example.com", password="x")

    def test_asset_url_is_always_the_gated_app_route(self, user):
        # Even for a public kind under GCS, the URL is the owner-gated app route
        # keyed by the opaque public_id — never a direct storage URL (PRD 17
        # §4.3). The byte route itself decides whether to redirect to the CDN.
        from rest_framework.test import APIRequestFactory

        asset = _asset(user, MediaAsset.OUTPUT_IMAGE, "img.png")
        req = APIRequestFactory().get("/")
        with override_settings(MEDIA_DIRECT_PUBLIC_URLS=True):
            url = asset_url(asset, req)
        assert url.endswith(f"/api/inference/assets/{asset.public_id}/")
        # ...and it needs a request to build an absolute URL.
        assert asset_url(asset, None) is None

    def test_private_asset_url_stays_on_app_route(self, user):
        asset = _asset(user, MediaAsset.INPUT_AUDIO, "clip.wav")
        with override_settings(MEDIA_DIRECT_PUBLIC_URLS=True):
            assert asset_url(asset, None) is None  # never a direct URL

    def test_asset_route_redirects_world_public_to_storage(self, user):
        # A world-public asset (here, explicitly PUBLIC) whose bytes sit in the
        # public bucket 302s straight to the CDN.
        asset = _asset(user, MediaAsset.OUTPUT_IMAGE, "img.png")
        asset.visibility = "PUBLIC"
        asset.save(update_fields=["visibility"])
        with override_settings(MEDIA_DIRECT_PUBLIC_URLS=True):
            resp = APIClient().get(f"/api/inference/assets/{asset.public_id}/")
        assert resp.status_code == 302
        assert resp["Location"] == asset.file.url
        assert resp["Cache-Control"] == "public, max-age=31536000, immutable"

    def test_asset_route_still_streams_private_kind(self, user):
        asset = _asset(user, MediaAsset.INPUT_AUDIO, "clip.wav", b"audio")
        client = APIClient()
        client.force_authenticate(user=user)
        with override_settings(MEDIA_DIRECT_PUBLIC_URLS=True):
            resp = client.get(f"/api/inference/assets/{asset.id}/")
        assert resp.status_code == 200
        assert b"".join(resp.streaming_content) == b"audio"
