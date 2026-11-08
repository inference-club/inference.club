"""Narration autopilot (PRD 12 V3+): episode settings + lexicon, take scoring,
retake-until-good, multi-seed auditions, saving a take as a voice sample,
click-free level-matched trims, and the zip export."""
import io
import json
import zipfile

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.inference import narration
from apps.inference.models import Episode, InferenceRequest, Segment, Variant, VoiceSample

from test_narration import _audio_asset, _wav

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return User.objects.create_user(email="auto@example.com", password="x")


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _episode(user, *texts, **settings):
    ep = Episode.objects.create(user=user, title="Pilot", settings=settings)
    for i, t in enumerate(texts):
        Segment.objects.create(episode=ep, position=i, text=t)
    return ep


# --- settings + lexicon ------------------------------------------------------


def test_episode_settings_merge_defaults():
    ep = Episode(settings={"temperature": 1.1, "bogus": 1})
    cfg = narration.episode_settings(ep)
    assert cfg["temperature"] == 1.1 and cfg["max_attempts"] == 3
    assert "bogus" not in cfg
    assert narration.episode_settings(Episode(settings={"loudness_lufs": "off"}))["loudness_lufs"] is None


def test_validate_settings_rejects_unknown_and_out_of_range():
    assert narration.validate_settings({"nope": 1})[1]
    assert narration.validate_settings({"temperature": 9})[1]
    assert narration.validate_settings({"lexicon": {"a": 1}})[1]
    clean, err = narration.validate_settings({"max_attempts": "4", "lexicon": {" OTel ": "Oh-tel"}})
    assert not err and clean == {"max_attempts": 4, "lexicon": {"OTel": "Oh-tel"}}


def test_apply_lexicon_whole_words_longest_first():
    lex = {"OTel": "Oh-tel", "Hermes OTel": "Hermes Oh-tel", "OTLP": "O T L P"}
    assert narration.apply_lexicon("Hermes OTel speaks OTLP, not hotel.", lex) == \
        "Hermes Oh-tel speaks O T L P, not hotel."
    assert narration.apply_lexicon("otel!", lex) == "Oh-tel!"


def test_patch_settings_endpoint(client, user):
    ep = _episode(user, "a")
    r = client.patch(f"/v1/episodes/{ep.id}", {"settings": {"lexicon": {"OTel": "Oh-tel"},
                                                             "accept_score": 9}}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["settings"]["lexicon"] == {"OTel": "Oh-tel"}
    assert r.json()["settings"]["accept_score"] == 9
    r = client.patch(f"/v1/episodes/{ep.id}", {"settings": {"accept_score": None}}, format="json")
    assert r.json()["settings"]["accept_score"] == narration.DEFAULT_EPISODE_SETTINGS["accept_score"]
    assert client.patch(f"/v1/episodes/{ep.id}", {"settings": {"x": 1}}, format="json").status_code == 400


# --- trim filter -------------------------------------------------------------


def test_trim_filter_fades_each_piece_and_levels():
    g = narration._trim_filter([(0.0, 1.0), (2.0, 2.5)], loudness=-16)
    assert g.count("afade=t=in") == 2 and "concat=n=2" in g
    assert "loudnorm=I=-16.0" in g and g.endswith("[out]")
    assert "loudnorm" not in narration._trim_filter([(0, 1)])


def test_trim_audio_outputs_48k_and_levels(user, tmp_path):
    src = tmp_path / "in.wav"
    src.write_bytes(_wav([(0.3, 0), (1.0, 440), (0.6, 0), (1.0, 440), (0.3, 0)]))
    out = tmp_path / "out.wav"
    narration.trim_audio(str(src), str(out), [(0.25, 1.35), (1.85, 2.95)], loudness=-16)
    import wave
    with wave.open(str(out)) as w:
        assert w.getframerate() == 48000
        assert 2.0 < w.getnframes() / 48000 < 2.4


# --- take score + produce ----------------------------------------------------


def _fake_variant(seg, score, n_words=10, dur=4.0, regen=False, seed=1):
    ir = InferenceRequest.objects.create(user=seg.episode.user, inference_type="VOICE",
                                         status="PROCESSED", payload={"seed": seed})
    return Variant.objects.create(
        segment=seg, text="[S1] " + seg.text, inference_request=ir, duration_seconds=dur,
        words=[{"word": "w", "start": i * 0.3, "end": i * 0.3 + 0.2} for i in range(n_words)],
        grade={"score": score, "should_regenerate": regen})


def test_take_score_penalises_pace():
    ep = Episode(settings={})
    cfg = narration.episode_settings(ep)
    v = Variant(duration_seconds=4.0, words=[{}] * 10, grade={"score": 9.5})
    assert narration.take_score(v, cfg)["accepted"]                      # 2.5 wps
    slow = Variant(duration_seconds=10.0, words=[{}] * 10, grade={"score": 9.5})
    s = narration.take_score(slow, cfg)                                   # 1.0 wps drawl
    assert s["pace_penalty"] > 0 and not s["accepted"]
    assert narration.take_score(Variant(duration_seconds=3, words=[], grade={"score": 9}), cfg)["take_score"] == 4.0


def test_produce_segment_retakes_until_accepted_and_keeps_best(user, monkeypatch):
    ep = _episode(user, "one two three")
    seg = ep.segments.get()
    scores = iter([5.0, 9.6, 7.0])
    made = []

    def fake_generate(segment, seed=None, text_override=None):
        v = _fake_variant(segment, next(scores), seed=len(made) + 7)
        made.append(v)
        segment.selected_variant = v
        segment.save()
        return v

    monkeypatch.setattr(narration, "generate_take", fake_generate)
    monkeypatch.setattr(narration, "process_segment", lambda s: {"ok": True})
    res = narration.produce_segment(seg)
    assert res["attempts"] == 2 and res["accepted"]                       # stopped on 9.6
    seg.refresh_from_db()
    assert seg.selected_variant_id == made[1].id and seg.status == Segment.STATUS_READY
    assert seg.selected_variant.grade["attempt"] == 2 and seg.selected_variant.grade["seed"] == 8


def test_produce_segment_flags_when_nothing_passes(user, monkeypatch):
    ep = _episode(user, "x", max_attempts=2)
    seg = ep.segments.get()
    scores = iter([6.0, 7.0])

    def fake_generate(segment, seed=None, text_override=None):
        v = _fake_variant(segment, next(scores))
        segment.selected_variant = v
        segment.save()
        return v

    monkeypatch.setattr(narration, "generate_take", fake_generate)
    monkeypatch.setattr(narration, "process_segment", lambda s: {"ok": True})
    res = narration.produce_segment(seg)
    seg.refresh_from_db()
    assert res["attempts"] == 2 and not res["accepted"]
    assert seg.status == Segment.STATUS_FLAGGED and seg.selected_variant.grade["take_score"] == 7.0


def test_explore_runs_every_seed(user, monkeypatch):
    ep = _episode(user, "x")
    seg = ep.segments.get()
    seen = []

    def fake_generate(segment, seed=None, text_override=None):
        seen.append(seed)
        v = _fake_variant(segment, 9.9, seed=seed)
        segment.selected_variant = v
        segment.save()
        return v

    monkeypatch.setattr(narration, "generate_take", fake_generate)
    monkeypatch.setattr(narration, "process_segment", lambda s: {"ok": True})
    res = narration.produce_segment(seg, explore=True, seeds=[11, 22, 33])
    assert seen == [11, 22, 33] and res["attempts"] == 3


def test_produce_episode_skips_ready_unless_forced(user, monkeypatch):
    ep = _episode(user, "a", "b")
    first = ep.segments.order_by("position").first()
    first.status = Segment.STATUS_READY
    first.save()
    calls = []
    monkeypatch.setattr(narration, "produce_segment",
                        lambda s, **kw: calls.append(s.id) or {"ok": True})
    narration.produce_episode(ep)
    assert len(calls) == 1
    narration.produce_episode(ep, force=True)
    assert len(calls) == 3


def test_produce_and_takes_endpoints(client, user, monkeypatch, settings):
    settings.ASYNC_ENABLED = False
    ep = _episode(user, "a")
    seg = ep.segments.get()
    got = {}
    monkeypatch.setattr(narration, "produce_episode", lambda e, **kw: got.update(ep=kw))
    monkeypatch.setattr(narration, "produce_segment", lambda s, **kw: got.update(seg=kw))
    assert client.post(f"/v1/episodes/{ep.id}/produce", {"attempts": 2}, format="json").status_code == 202
    assert got["ep"]["attempts"] == 2
    r = client.post(f"/v1/segments/{seg.id}/takes", {"seeds": [1, 2]}, format="json")
    assert r.status_code == 202 and got["seg"]["seeds"] == [1, 2] and got["seg"]["explore"]
    assert client.post(f"/v1/segments/{seg.id}/takes", {"seeds": "x"}, format="json").status_code == 400
    assert client.post(f"/v1/episodes/{ep.id}/produce", {"attempts": 99}, format="json").status_code == 400


# --- voice sample + export ---------------------------------------------------


def _ready_variant(user, ep, text="Follow the messenger.", score=9.5):
    seg = Segment.objects.create(episode=ep, position=ep.segments.count(), text=text)
    v = _fake_variant(seg, score, seed=42)
    v.cleaned_audio = _audio_asset(user, _wav([(1.0, 440)]))
    v.transcript = "follow the messenger"
    v.grade = {**v.grade, "take_score": score}
    v.save()
    seg.selected_variant = v
    seg.status = Segment.STATUS_READY
    seg.save()
    return seg, v


def test_save_voice_endpoint_creates_default_sample_and_sets_episode(client, user):
    ep = Episode.objects.create(user=user, title="V")
    seg, v = _ready_variant(user, ep)
    r = client.post(f"/v1/segments/{seg.id}/variants/{v.id}/save-voice",
                    {"speaker_name": "Narrator", "use_for_episode": True}, format="json")
    assert r.status_code == 201, r.content
    sample = VoiceSample.objects.get(id=r.json()["id"])
    assert sample.is_default and sample.transcript == "Follow the messenger."   # graded well
    assert sample.audio.kind == "INPUT_AUDIO" and sample.metadata["seed"] == 42
    ep.refresh_from_db()
    assert ep.voice_sample_id == sample.id


def test_save_voice_uses_asr_transcript_for_weak_take(user):
    ep = Episode.objects.create(user=user, title="V")
    _seg, v = _ready_variant(user, ep, score=8.0)
    sample = narration.save_variant_as_voice_sample(v, speaker_name="N")
    assert sample.transcript == "follow the messenger"


def test_export_zip_has_clips_and_manifest(client, user):
    ep = Episode.objects.create(user=user, title="Hermes OTel film")
    _ready_variant(user, ep, "Line one.")
    _ready_variant(user, ep, "Line two.")
    Segment.objects.create(episode=ep, position=5, text="no take yet")
    r = client.get(f"/v1/episodes/{ep.id}/export")
    assert r.status_code == 200 and r["Content-Type"] == "application/zip"
    assert "hermes-otel-film.zip" in r["Content-Disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"01.wav", "02.wav", "manifest.json"} <= set(zf.namelist())
    m = json.loads(zf.read("manifest.json"))
    assert [s.get("file") for s in m["segments"]] == ["01.wav", "02.wav", None]
    assert m["segments"][0]["seed"] == 42 and m["segments"][0]["spoken"] == "Line one."


def test_editing_text_sends_a_ready_segment_back_to_pending(client, user):
    ep = Episode.objects.create(user=user, title="E")
    seg, _v = _ready_variant(user, ep, "Old line.")
    r = client.patch(f"/v1/segments/{seg.id}", {"text": "New line."}, format="json")
    assert r.status_code == 200 and r.json()["status"] == Segment.STATUS_PENDING
    r = client.patch(f"/v1/segments/{seg.id}", {"text": "New line."}, format="json")
    assert r.json()["status"] == Segment.STATUS_PENDING     # unchanged text: no-op
