"""Unit tests for the voice-cloning script normalization (PRD 09). Pure
function — no DB. Covers the single-speaker [S1] default, two-speaker
pass-through, the must-start-with-[S1] rule, the [S3]+ rejection, and the
Dia end-of-sequence trailing tag (which markedly improves audio quality)."""
from apps.inference.openai_views import _append_dia_end_tag, _normalize_script


def test_untagged_single_line_defaults_to_s1():
    text, used, err = _normalize_script("Hey, welcome to the show.")
    assert err is None
    # single speaker → ends with a dangling [S1]
    assert text == "[S1] Hey, welcome to the show.\n[S1]"
    assert used == {"S1"}


def test_untagged_strips_whitespace_before_tagging():
    text, used, err = _normalize_script("  hello  ")
    assert err is None
    assert text == "[S1] hello\n[S1]"


def test_two_speaker_passthrough():
    src = "[S1] Hi there. [S2] Hello back."
    text, used, err = _normalize_script(src)
    assert err is None
    # last turn is [S2], so the dangling end tag is the other speaker, [S1]
    assert text == src + "\n[S1]"
    assert used == {"S1", "S2"}


def test_single_tagged_speaker_reports_only_s1():
    text, used, err = _normalize_script("[S1] Just me talking. [S1] Still me.")
    assert err is None
    assert text.endswith("\n[S1]")
    assert used == {"S1"}


def test_dia_end_tag_rules():
    # multi-speaker ending on S2 → next is S1; ending on S1 → next is S2
    assert _append_dia_end_tag("[S1] a [S2] b") == "[S1] a [S2] b\n[S1]"
    assert _append_dia_end_tag("[S1] a [S2] b [S1] c") == "[S1] a [S2] b [S1] c\n[S2]"
    # single speaker repeats itself
    assert _append_dia_end_tag("[S1] just me") == "[S1] just me\n[S1]"
    # already ends on a dangling tag → unchanged; no tags → unchanged
    assert _append_dia_end_tag("[S1] hi\n[S1]") == "[S1] hi\n[S1]"
    assert _append_dia_end_tag("plain text") == "plain text"


def test_must_start_with_s1():
    text, used, err = _normalize_script("[S2] starting on two is invalid")
    assert text is None
    assert "start with [S1]" in err


def test_rejects_third_speaker():
    text, used, err = _normalize_script("[S1] a [S2] b [S3] c")
    assert text is None
    assert "[S3]" in err
