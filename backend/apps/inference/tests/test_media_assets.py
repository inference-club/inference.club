"""Media-asset provenance spine + JSON API (PRD 12 §5.1, V0).

Covers the ``GET /v1/assets/<id>`` metadata/provenance endpoint (public vs
owner-gated kinds) and the ``MediaAsset.record_derivation`` provenance helper.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.inference import workflows
from apps.inference.models import (
    InferenceRequest, MediaAsset, WorkflowRun, WorkflowStepRun,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@example.com", password="x")


@pytest.fixture
def other(db):
    return User.objects.create_user(email="other@example.com", password="x")


def _asset(user, kind, **kw):
    return MediaAsset.objects.create(
        user=user, kind=kind, file=f"{kind.lower()}/x.bin", **kw
    )


# --- the GET /v1/assets/<id> endpoint ---------------------------------------


def test_public_asset_readable_by_anyone(owner):
    asset = _asset(owner, MediaAsset.OUTPUT_VIDEO, duration_seconds=12.5)
    client = APIClient()  # anonymous
    resp = client.get(f"/v1/assets/{asset.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == asset.id
    assert body["kind"] == "OUTPUT_VIDEO"
    assert body["duration_seconds"] == 12.5
    assert "url" in body


def test_private_doc_is_owner_gated(owner, other):
    asset = _asset(owner, MediaAsset.OUTPUT_DOC)
    # owner: ok
    c = APIClient()
    c.force_authenticate(owner)
    assert c.get(f"/v1/assets/{asset.id}").status_code == 200
    # another member: forbidden
    c2 = APIClient()
    c2.force_authenticate(other)
    assert c2.get(f"/v1/assets/{asset.id}").status_code == 403
    # anonymous: forbidden
    assert APIClient().get(f"/v1/assets/{asset.id}").status_code == 403


def test_missing_asset_404(owner):
    c = APIClient()
    c.force_authenticate(owner)
    assert c.get("/v1/assets/999999").status_code == 404


def test_produced_by_surfaces_the_job(owner):
    job = InferenceRequest.objects.create(
        user=owner, inference_type="VIDEO", payload={}, status="PROCESSED"
    )
    asset = _asset(owner, MediaAsset.OUTPUT_VIDEO, inference_request=job)
    body = APIClient().get(f"/v1/assets/{asset.id}").json()
    assert body["produced_by"] == {"request_id": job.id, "type": "VIDEO"}


# --- provenance: derived_from / derivatives ---------------------------------


def test_record_derivation_links_and_serializes(owner):
    audio = _asset(owner, MediaAsset.OUTPUT_AUDIO)
    image = _asset(owner, MediaAsset.OUTPUT_IMAGE)
    subs = _asset(owner, MediaAsset.OUTPUT_SUBTITLE)
    video = _asset(owner, MediaAsset.OUTPUT_VIDEO)

    video.record_derivation([audio, image, subs])

    # the video lists its three sources
    body = APIClient().get(f"/v1/assets/{video.id}").json()
    src_ids = {s["id"] for s in body["derived_from"]}
    assert src_ids == {audio.id, image.id, subs.id}

    # each source lists the video as a derivative (reverse edge)
    audio_body = APIClient().get(f"/v1/assets/{audio.id}").json()
    assert [d["id"] for d in audio_body["derivatives"]] == [video.id]


def test_record_derivation_is_idempotent_and_ignores_self(owner):
    a = _asset(owner, MediaAsset.OUTPUT_AUDIO)
    v = _asset(owner, MediaAsset.OUTPUT_VIDEO)
    v.record_derivation([a, a, v, None])  # dupes + self + None
    assert list(v.derived_from.values_list("id", flat=True)) == [a.id]
    v.record_derivation([a])  # re-adding is a no-op
    assert v.derived_from.count() == 1


# --- workflow wiring: a compose step's output derives from its sources -------


def test_step_provenance_links_compose_output_to_its_sources(owner):
    audio = _asset(owner, MediaAsset.OUTPUT_AUDIO)
    img1 = _asset(owner, MediaAsset.OUTPUT_IMAGE)
    img2 = _asset(owner, MediaAsset.OUTPUT_IMAGE)

    run = WorkflowRun.objects.create(user=owner, spec={}, inputs={})
    step = WorkflowStepRun.objects.create(
        run=run, step_id="video", kind="inference",
        spec={
            "type": "compose",
            # one scalar ref + one list ref (a map's per-frame outputs)
            "derive_from": [
                "{{steps.tts.output.asset_id}}",
                "{{steps.images.output}}",
            ],
        },
    )
    context = {
        "inputs": {},
        "steps": {
            "tts": {"output": {"asset_id": audio.id}},
            "images": {"output": [{"asset_id": img1.id}, {"asset_id": img2.id}]},
        },
    }
    job = InferenceRequest.objects.create(
        user=owner, inference_type="RENDER", payload={}, status="PROCESSED",
        step_run=step,
    )
    video = _asset(owner, MediaAsset.OUTPUT_VIDEO, inference_request=job)

    workflows._record_step_provenance(step, [job], context)

    assert set(video.derived_from.values_list("id", flat=True)) == {
        audio.id, img1.id, img2.id,
    }


def test_step_provenance_is_a_noop_without_derive_from(owner):
    run = WorkflowRun.objects.create(user=owner, spec={}, inputs={})
    step = WorkflowStepRun.objects.create(
        run=run, step_id="img", kind="inference", spec={"type": "image"},
    )
    job = InferenceRequest.objects.create(
        user=owner, inference_type="IMAGE", payload={}, status="PROCESSED",
        step_run=step,
    )
    asset = _asset(owner, MediaAsset.OUTPUT_IMAGE, inference_request=job)
    workflows._record_step_provenance(step, [job], {"inputs": {}, "steps": {}})
    assert asset.derived_from.count() == 0
