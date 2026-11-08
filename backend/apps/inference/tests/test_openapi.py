"""The public OpenAPI spec endpoints that power the API reference page."""
import re

import pytest
from django.urls import URLPattern, URLResolver
from rest_framework.test import APIClient

from apps.inference import openai_urls


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def spec(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    return resp.json()


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


# Django path converter → OpenAPI templated segment: `<int:id>` / `<id>` → `{id}`.
_CONVERTER_RE = re.compile(r"<(?:[^:>]+:)?([^>]+)>")


def _walk_routes(patterns, prefix=""):
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _walk_routes(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield route


def _routed_openapi_paths():
    """Every route in the ``openai`` (/v1) namespace, in OpenAPI form, with the
    duplicate trailing-slash variants collapsed."""
    out = set()
    for route in _walk_routes(openai_urls.urlpatterns):
        path = "/" + _CONVERTER_RE.sub(r"{\1}", route).strip("/")
        out.add(path)
    return out


def test_every_v1_route_is_documented(spec):
    """The spec must never silently fall behind the router: every routed /v1
    path has to appear in ``spec["paths"]`` (the spec may document extras)."""
    routed = _routed_openapi_paths()
    assert len(routed) > 40  # sanity: the walker actually found the router
    missing = sorted(routed - set(spec["paths"]))
    assert not missing, f"Routed /v1 paths missing from openapi.yaml: {missing}"


def test_every_operation_is_agent_ready(spec):
    """Each operation has a unique operationId, a summary, a description and a
    tag — agents generate calls from these."""
    seen = set()
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            where = f"{method.upper()} {path}"
            assert op.get("operationId"), where
            assert op["operationId"] not in seen, f"duplicate operationId at {where}"
            seen.add(op["operationId"])
            assert op.get("summary"), where
            assert op.get("description"), where
            assert op.get("tags"), where


def test_refs_resolve(spec):
    """Every local ``$ref`` points at something that exists."""
    def lookup(ref):
        node = spec
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return node

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/"):
                lookup(ref)  # KeyError → broken ref
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(spec)


def test_spec_validates(spec):
    validator = pytest.importorskip("openapi_spec_validator")
    validator.validate(spec)
