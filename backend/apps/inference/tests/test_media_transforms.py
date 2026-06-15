"""Inline media-pipeline transforms in the workflow engine (PRD 12).

``split_sections`` (hn.fm's 2-lines-per-section grouping) and ``subtitle``
(word timestamps → VTT/ASS) run inline via ``workflows._run_transform`` — no
provider/agent needed — so they're unit-tested directly here.
"""
from apps.inference import workflows


def _t(spec):
    """Run a transform spec against an empty context."""
    return workflows._run_transform(spec, {"inputs": {}, "steps": {}})


# --- split_sections ----------------------------------------------------------


def test_split_sections_groups_lines_in_pairs():
    out = _t({
        "op": "split_sections",
        "input": ["[S1] a", "[S2] b", "[S1] c", "[S2] d", "[S1] e"],
        "size": 2,
    })
    assert [s["index"] for s in out] == [0, 1, 2]
    assert out[0]["lines"] == ["[S1] a", "[S2] b"]
    assert out[0]["text"] == "[S1] a\n[S2] b"
    assert out[2]["lines"] == ["[S1] e"]  # trailing odd line


def test_split_sections_accepts_a_newline_string_and_default_size():
    out = _t({"op": "split_sections", "input": "one\n\ntwo\nthree"})
    # blanks dropped, default size 2
    assert [s["text"] for s in out] == ["one\ntwo", "three"]


def test_split_sections_bad_size_falls_back_to_two():
    out = _t({"op": "split_sections", "input": ["a", "b", "c"], "size": "x"})
    assert len(out) == 2 and out[0]["lines"] == ["a", "b"]


def test_split_sections_non_list_returns_empty():
    assert _t({"op": "split_sections", "input": 42}) == []


# --- subtitle ----------------------------------------------------------------

WORDS_MS = [
    {"word": "Hello", "start_ms": 0, "duration_ms": 500},
    {"word": "world", "start_ms": 500, "duration_ms": 750},
]


def test_subtitle_vtt_from_ms_timestamps():
    out = _t({"op": "subtitle", "input": WORDS_MS, "format": "vtt"})
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:00.500" in out
    assert "00:00:00.500 --> 00:00:01.250" in out
    assert "Hello" in out and "world" in out


def test_subtitle_defaults_to_vtt_and_accepts_words_dict():
    out = _t({"op": "subtitle", "input": {"words": WORDS_MS}})
    assert out.startswith("WEBVTT") and "Hello" in out


def test_subtitle_ass_format():
    out = _t({"op": "subtitle", "input": WORDS_MS, "format": "ass"})
    assert "[Script Info]" in out and "[Events]" in out
    assert "Dialogue: 0,0:00:00.00,0:00:00.50,Default,Hello" in out


def test_subtitle_seconds_timestamps_and_zero_length_floor():
    words = [{"text": "x", "start": 1.0, "end": 1.0}]  # zero length → +0.3 floor
    out = _t({"op": "subtitle", "input": words, "format": "vtt"})
    assert "00:00:01.000 --> 00:00:01.300" in out


def test_subtitle_non_list_returns_empty_string():
    assert _t({"op": "subtitle", "input": 5}) == ""


# --- media modality routing (PRD 12 option 1: authorable + validates) --------


def test_resolve_kind_for_media_short_types():
    rk = workflows._resolve_kind
    assert rk({"kind": "inference", "type": "scrape"}) == ("SCRAPE", "scrape")
    assert rk({"kind": "inference", "type": "transcribe"}) == ("STT", "stt")
    assert rk({"kind": "inference", "type": "compose"}) == ("RENDER", "render")
    assert rk({"kind": "inference", "type": "clean"}) == ("ENHANCE", "audio-enhance")


def test_resolve_kind_for_media_endpoints():
    rk = workflows._resolve_kind
    assert rk({"kind": "inference", "endpoint": "/v1/scrape"}) == ("SCRAPE", "scrape")
    assert rk({"kind": "inference", "endpoint": "/v1/videos/compose"}) == ("RENDER", "render")
    assert rk({"kind": "inference", "endpoint": "/v1/audio/enhance"}) == ("ENHANCE", "audio-enhance")


def test_extract_asset_ids_handles_ids_dicts_and_nesting():
    f = workflows._extract_asset_ids
    assert f(5) == [5]
    assert f({"asset_id": 7, "request_id": 99, "url": "x"}) == [7]  # prefers asset_id
    assert f({"id": 3}) == [3]
    assert f([{"asset_id": 1}, {"asset_id": 2}]) == [1, 2]  # a map's output list
    assert f({"output": {"asset_id": 4}}) == [4]  # nested
    assert f("nope") == []
    assert f(True) is not None and f(True) == []  # bool isn't an id


def test_validate_spec_accepts_a_media_pipeline_graph():
    spec = {
        "steps": [
            {"id": "fetch", "kind": "inference", "type": "scrape",
             "body": {"url": "{{inputs.url}}"}},
            {"id": "compose", "kind": "inference", "type": "compose",
             "body": {"audio": "{{steps.fetch.output.url}}"}},
        ]
    }
    norm = workflows.validate_spec(spec)
    assert [s["id"] for s in norm] == ["fetch", "compose"]
