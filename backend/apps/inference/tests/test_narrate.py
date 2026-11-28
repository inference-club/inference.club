"""The "narrate this" path: the script that gets planned, the pronunciation
notes that are allowed through, fair grading of numbers and acronyms, and the
API's front door."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.inference import narrate
from apps.inference.article import Article, Block
from apps.inference.narration import _normalize_for_similarity, fallback_grade

User = get_user_model()


def _article():
    return Article(
        title="Why lighthouses still matter", author="Ada Marsh", published="2026-03-04",
        blocks=[
            Block("paragraph", "Ships have satellites now. The lights are still lit every night, and 40% of crews say they check them."),
            Block("heading", "A second system"),
            Block("paragraph", "The reason is redundancy — see https://example.com/charts for more."),
        ],
    )


def test_intro_line_reads_like_an_introduction():
    assert narrate.intro_line(_article()) == "Why lighthouses still matter. By Ada Marsh. Published March 4, 2026."
    assert narrate.intro_line(Article(title="Is it over?")) == "Is it over?"
    assert narrate.intro_line(Article()) == ""


def test_plan_puts_intro_first_and_keeps_headings_apart():
    pieces = narrate.plan_script(_article())
    assert [p["kind"] for p in pieces] == ["intro", "body", "heading", "body"]
    assert pieces[2]["text"] == "A second system."
    assert "40 percent" in pieces[1]["text"]
    assert "http" not in pieces[3]["text"] and pieces[3]["text"].startswith("The reason is redundancy, see")


def test_speakable_rewrites_only_what_reads_badly():
    assert narrate.speakable("Up 75% [3] — see https://x.example/a now") == "Up 75 percent, see now"
    assert narrate.speakable("Plain sentence.") == "Plain sentence."


def test_lexicon_keeps_only_safe_entries():
    text = "UBI and the K-shaped economy are discussed. NASA is mentioned."
    raw = 'Sure! {"UBI": "U B I", "K-shaped": "K shaped", "XYZ": "X Y Z", "NASA": "<b>nasa</b>", "economy": "economy"}'
    assert narrate.clean_lexicon(raw, text) == {"UBI": "U B I", "K-shaped": "K shaped"}
    assert narrate.clean_lexicon("not json", text) == {}


def test_numbers_dates_and_acronyms_are_not_speaking_mistakes():
    said = "A I focused P Ms now make $245,000, up 20% since 2023, on the 24th."
    heard = "AI focused PMs now make two hundred and forty five thousand dollars, up twenty percent since twenty twenty three on the twenty fourth"
    assert _normalize_for_similarity(said) == _normalize_for_similarity(heard)
    assert fallback_grade(said, heard)["score"] == 10.0
    # A real mistake still shows.
    assert fallback_grade("The lights are still lit every night.", "The fights are spilled with delight.")["score"] < 8


@pytest.mark.django_db
def test_narrations_endpoint_needs_something_to_read():
    user = User.objects.create_user(email="n@example.com", password="pw")
    client = APIClient()
    client.force_authenticate(user)
    r = client.post("/v1/narrations", {}, format="json")
    assert r.status_code == 400
    assert "link or some text" in r.data["detail"]


@pytest.mark.django_db
def test_narrate_tools_are_offered_over_mcp():
    from apps.inference.mcp_server import TOOLS

    names = {t["name"] for t in TOOLS}
    assert {"narrate", "get_narration"} <= names


@pytest.mark.django_db
def test_summary_reports_stage_and_fraction():
    from apps.inference.models import Episode, Segment

    user = User.objects.create_user(email="s@example.com", password="pw")
    ep = Episode.objects.create(user=user, title="T", production={"stage": "voicing", "events": []})
    for i, st in enumerate([Segment.STATUS_READY, Segment.STATUS_FLAGGED, Segment.STATUS_QUEUED, Segment.STATUS_QUEUED]):
        Segment.objects.create(episode=ep, position=i, text="x", status=st)
    s = narrate.summary(ep)
    assert s["stage"] == "voicing" and s["active"] is True
    assert s["counts"] == {"total": 4, "ready": 1, "flagged": 1, "error": 0, "working": 0, "waiting": 2}
    assert 0.5 < s["fraction"] < 0.6
