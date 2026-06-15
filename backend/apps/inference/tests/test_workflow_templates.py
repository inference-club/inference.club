"""Curated workflow templates (PRD 10 + 12).

A guard test that every shipped template is a spec the engine can actually run
(catches a typo'd ref or an unknown modality in any template, including the
PRD-12 ``url-to-video`` media pipeline).
"""
import pytest

from apps.inference import workflow_templates, workflows


@pytest.mark.parametrize("template", workflow_templates.TEMPLATES, ids=lambda t: t["key"])
def test_template_spec_validates(template):
    # validate_spec raises WorkflowError on anything the engine can't run
    # (unknown kind/modality, a depends_on/template ref to a missing step, …).
    steps = workflows.validate_spec(template["spec"])
    assert steps, f"{template['key']} produced no steps"


def test_url_to_video_template_is_present_and_shaped():
    t = workflow_templates.get_template("url-to-video")
    assert t is not None
    kinds = {s["id"]: s for s in t["spec"]["steps"]}
    # the media-pipeline nodes are wired in
    assert kinds["fetch"]["type"] == "scrape"
    assert kinds["sections"]["op"] == "split_sections"
    assert kinds["video"]["type"] == "compose"
    # provenance: the composed video derives from the per-section audio + art
    assert kinds["video"]["derive_from"] == [
        "{{steps.speech.output}}", "{{steps.art.output}}",
    ]
