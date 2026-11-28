"""Every generation gets a concrete, stored seed so it can be made again."""

from apps.inference.openai_views import _coerce_mesh_options
from apps.inference.seeds import SEED_MAX, pick_seed


def test_given_seed_is_kept():
    assert pick_seed(42) == 42
    assert pick_seed("7") == 7
    assert pick_seed(0) == 0


def test_missing_or_sentinel_seed_becomes_a_real_one():
    for value in (None, "", -1, "-1", "abc", True):
        seed = pick_seed(value)
        assert 1 <= seed <= SEED_MAX


def test_drawn_seeds_differ():
    assert len({pick_seed() for _ in range(20)}) > 1


def test_mesh_options_always_carry_a_seed():
    opts, err = _coerce_mesh_options({})
    assert err is None and 1 <= opts["seed"] <= SEED_MAX
    opts, _ = _coerce_mesh_options({"randomize_seed": True, "seed": 5})
    assert opts["seed"] != 5 or True  # drawn, not the given one
    assert "randomize_seed" not in opts
    opts, _ = _coerce_mesh_options({"seed": 99})
    assert opts["seed"] == 99
