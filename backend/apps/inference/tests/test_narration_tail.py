"""Stray sound after the last word is cut, clean endings are left alone, and
word timings still line up after every cut."""

from apps.inference.narration import (
    END_FADE,
    _trim_filter,
    last_script_word,
    remap_words,
    subtract_intervals,
    tail_artifact_cut,
)

WORDS = [{"word": "barely", "start": 0.4, "end": 0.9}, {"word": "inflation.", "start": 1.0, "end": 1.8}]


def test_sound_after_the_stretch_holding_the_last_word_is_cut():
    # speech 0.3–1.9, silence, a stray sound 3.2–4.0, silence to the end
    fine = [(0.0, 0.3), (1.9, 3.2), (4.0, 5.0)]
    cut = tail_artifact_cut(fine, WORDS, 5.0)
    assert cut is not None and 1.9 < cut <= 2.1 + 1e-6  # just after the real speech


def test_a_stretched_word_end_does_not_hide_a_stray_sound():
    # Recognition says the last word runs to 2.6, across the silence at
    # 1.9–2.4; the sound at 2.4–2.8 is still not that word.
    words = [WORDS[0], {"word": "inflation.", "start": 1.0, "end": 2.6}]
    assert tail_artifact_cut([(0.0, 0.3), (1.9, 2.4), (2.8, 5.0)], words, 5.0) is not None


def test_a_clean_ending_is_left_alone():
    assert tail_artifact_cut([(0.0, 0.3), (1.9, 5.0)], WORDS, 5.0) is None
    assert tail_artifact_cut([], [], 5.0) is None


def test_sound_joined_to_the_last_word_is_kept():
    # No silence between the word and what follows: it cannot be told apart.
    assert tail_artifact_cut([(0.0, 0.3), (2.6, 5.0)], WORDS, 5.0) is None


def test_a_gap_just_after_the_word_starts_is_not_trusted():
    # A split 0.1 s after the last word begins is more likely inside the word.
    assert tail_artifact_cut([(0.0, 0.3), (1.02, 1.15), (1.9, 5.0)], WORDS, 5.0) is None


def test_extra_words_after_the_script_ends_are_found():
    words = [{"word": "coming", "start": 1.0, "end": 1.2}, {"word": "in", "start": 1.3, "end": 1.4},
             {"word": "figure.", "start": 4.0, "end": 4.3}]
    assert last_script_word(words, "[S1] who still have money coming in. [S1]") == 1
    assert last_script_word(words[:2], "money coming in.") == 1
    assert last_script_word(words, "something else entirely.") is None
    # Cutting with only the script's words removes the babble's stretch.
    fine = [(0.0, 0.9), (1.5, 3.9), (4.4, 5.0)]
    assert tail_artifact_cut(fine, words[:2], 5.0) is not None
    assert tail_artifact_cut(fine, words, 5.0) is None


def test_word_times_follow_the_audio_through_head_middle_and_tail_cuts():
    # keep 0.5–2.0 and 3.0–4.0 of the source (lead-in, a pause and the tail removed)
    keep = subtract_intervals([(0.0, 6.0)], [(0.0, 0.5), (2.0, 3.0), (4.0, 6.0)])
    words = [
        {"word": "one", "start": 0.6, "end": 1.0},
        {"word": "two", "start": 1.5, "end": 1.9},
        {"word": "three", "start": 3.1, "end": 3.6},
        {"word": "stray", "start": 4.5, "end": 5.0},  # in the removed tail
    ]
    out = remap_words(words, keep)
    assert [w["word"] for w in out] == ["one", "two", "three"]
    assert [(w["start"], w["end"]) for w in out] == [(0.1, 0.5), (1.0, 1.4), (1.6, 2.1)]
    # Still in order, and inside the trimmed length (1.5 + 1.0 s).
    assert all(a["end"] <= b["start"] for a, b in zip(out, out[1:]))
    assert out[-1]["end"] <= 2.5


def test_the_end_of_a_take_fades_out_longer_than_an_inner_join():
    graph = _trim_filter([(0.0, 2.0), (3.0, 5.0)])
    first, last = graph.split(";")[0], graph.split(";")[1]
    assert f"d={END_FADE:.4f}" in last and f"d={END_FADE:.4f}" not in first
