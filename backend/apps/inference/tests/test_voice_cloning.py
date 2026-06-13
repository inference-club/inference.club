"""Unit tests for the voice-cloning script normalization (PRD 09). Pure
function — no DB. Covers the single-speaker [S1] default, two-speaker
pass-through, the must-start-with-[S1] rule, and the [S3]+ rejection."""
from apps.inference.openai_views import _normalize_script


def test_untagged_single_line_defaults_to_s1():
    text, used, err = _normalize_script("Hey, welcome to the show.")
    assert err is None
    assert text == "[S1] Hey, welcome to the show."
    assert used == {"S1"}


def test_untagged_strips_whitespace_before_tagging():
    text, used, err = _normalize_script("  hello  ")
    assert err is None
    assert text == "[S1] hello"


def test_two_speaker_passthrough():
    src = "[S1] Hi there. [S2] Hello back."
    text, used, err = _normalize_script(src)
    assert err is None
    assert text == src
    assert used == {"S1", "S2"}


def test_single_tagged_speaker_reports_only_s1():
    text, used, err = _normalize_script("[S1] Just me talking. [S1] Still me.")
    assert err is None
    assert used == {"S1"}


def test_must_start_with_s1():
    text, used, err = _normalize_script("[S2] starting on two is invalid")
    assert text is None
    assert "start with [S1]" in err


def test_rejects_third_speaker():
    text, used, err = _normalize_script("[S1] a [S2] b [S3] c")
    assert text is None
    assert "[S3]" in err
