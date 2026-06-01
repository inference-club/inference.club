"""The public OpenAPI spec endpoints that power the API reference page."""
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


def test_openapi_json_public_and_valid(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "inference.club API"
    # The public inference surface is documented.
    for path in (
        "/models",
        "/chat/completions",
        "/audio/transcriptions",
        "/images/generations",
        "/images/edits",
    ):
        assert path in spec["paths"], path
    # Bearer auth is declared.
    assert "bearerAuth" in spec["components"]["securitySchemes"]


def test_openapi_yaml_served(client):
    resp = client.get("/openapi.yaml")
    assert resp.status_code == 200
    assert "application/yaml" in resp.headers.get("content-type", "")
    assert b"openapi:" in resp.content
