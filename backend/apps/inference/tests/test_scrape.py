"""Web scrape modality (PRD 12): the /v1/scrape proxy, OUTPUT_DOC storage, and
the workflow output exposing markdown as `text`. The provider agent is mocked.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.inference import workflows
from apps.inference.models import (
    InferenceRequest, MediaAsset, Provider, ProviderModel, ProviderService,
    link_catalog_model,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return User.objects.create_user(email="scrape@example.com", password="x")


def _online_provider(u, host="n1"):
    return Provider.objects.create(
        user=u, name=f"node-{host}", tailnet_hostname=host,
        is_active=True, accepting_requests=True, last_seen_at=timezone.now(),
    )


def _scrape_model(p, name="firecrawl"):
    svc = ProviderService.objects.create(
        provider=p, name="firecrawl", engine="other", service_type="scrape",
        access_policy=ProviderService.ACCESS_AUTHENTICATED,
    )
    pm = ProviderModel(provider=p, name=name, service=svc)
    link_catalog_model(pm)
    pm.save()
    return pm


def _client(u):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=u)
    return c


class _FakeMarkdownResp:
    """Mimics the agent's serveScrape reply: markdown body + headers."""

    def __init__(self, md, title="", source_url="", status=200):
        self.text = md
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = {
            "content-type": "text/markdown; charset=utf-8",
            "X-Scrape-Title": title,
            "X-Scrape-Source-Url": source_url,
        }

    def json(self):
        raise ValueError("not json")


# --- the /v1/scrape proxy ----------------------------------------------------


def test_scrape_returns_markdown_and_stores_doc_asset(user):
    pm = _scrape_model(_online_provider(user))
    c = _client(user)
    resp = _FakeMarkdownResp(
        "# Title\n\nbody text", title="My Page", source_url="https://ex.com/p"
    )
    with patch("apps.inference.openai_views.requests.post", return_value=resp):
        r = c.post("/v1/scrape", {"url": "https://ex.com/p", "model": "firecrawl"}, format="json")

    assert r.status_code == 200, r.content
    body = r.json()
    assert body["markdown"] == "# Title\n\nbody text"
    assert body["title"] == "My Page"
    assert body["source_url"] == "https://ex.com/p"
    assert body["chars"] == len("# Title\n\nbody text")

    ir = InferenceRequest.objects.get(id=body["request_id"])
    assert ir.inference_type == "SCRAPE" and ir.status == "PROCESSED"
    # the markdown was persisted as an OUTPUT_DOC asset linked to the request
    doc = MediaAsset.objects.get(id=body["doc_asset_id"])
    assert doc.kind == MediaAsset.OUTPUT_DOC
    assert doc.inference_request_id == ir.id
    assert doc.metadata["title"] == "My Page"


def test_scrape_requires_url(user):
    _scrape_model(_online_provider(user))
    r = _client(user).post("/v1/scrape", {"model": "firecrawl"}, format="json")
    assert r.status_code == 400


def test_scrape_no_provider_is_404(user):
    # no scrape service registered for this user
    r = _client(user).post("/v1/scrape", {"url": "https://ex.com", "model": "firecrawl"}, format="json")
    assert r.status_code == 404


def test_scrape_upstream_error_is_502(user):
    _scrape_model(_online_provider(user))
    bad = _FakeMarkdownResp("nope", status=500)
    with patch("apps.inference.openai_views.requests.post", return_value=bad):
        r = _client(user).post("/v1/scrape", {"url": "https://ex.com", "model": "firecrawl"}, format="json")
    assert r.status_code in (502, 500)
    # the request is left non-PROCESSED so it can be retried
    ir = InferenceRequest.objects.filter(inference_type="SCRAPE").latest("created_on")
    assert ir.status != "PROCESSED"


def test_scrape_tolerates_firecrawl_json_passthrough(user):
    """If the agent ever returns Firecrawl's JSON envelope, we still extract it."""
    _scrape_model(_online_provider(user))

    class _JsonResp:
        status_code = 200
        ok = True
        headers = {"content-type": "application/json"}
        text = ""

        def json(self):
            return {"success": True, "data": {
                "markdown": "# J", "metadata": {"title": "T", "sourceURL": "https://j.com"}}}

    with patch("apps.inference.openai_views.requests.post", return_value=_JsonResp()):
        r = _client(user).post("/v1/scrape", {"url": "https://j.com", "model": "firecrawl"}, format="json")
    assert r.status_code == 200
    assert r.json()["markdown"] == "# J" and r.json()["title"] == "T"


# --- workflow integration ----------------------------------------------------


def test_job_output_exposes_markdown_as_text(user):
    ir = InferenceRequest.objects.create(
        user=user, inference_type="SCRAPE", payload={}, status="PROCESSED",
        results={"markdown": "# md\n\ntext", "title": "T", "source_url": "https://x", "doc_asset_id": 7},
    )
    out = workflows._job_output(ir)
    assert out["text"] == "# md\n\ntext"
    assert out["title"] == "T" and out["url"] == "https://x"
    assert out["asset_id"] == 7
