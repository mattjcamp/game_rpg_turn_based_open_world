"""Tests for the optional spawn_col / spawn_row override on collect steps.

The module editor's collect-step screen now exposes ``Spawn Col`` and
``Spawn Row`` int fields.  When the author sets them they pin the
quest item to an exact tile in the destination map; when blank they
fall back to a random walkable tile (the legacy behaviour).

The runtime helper ``quest_manager.pick_quest_item_position`` enforces
the pin-or-fall-back rule and is exercised by all four item-spawning
paths (overworld, town interior, building space, dungeon floor).
"""

import io
import random
from contextlib import redirect_stdout

import pytest

from src.quest_manager import pick_quest_item_position, _coerce_int


# ── Walkable fixtures ────────────────────────────────────────────────

@pytest.fixture
def walkable_grid():
    """A 5x5 grid where every tile is walkable."""
    return {(c, r) for c in range(5) for r in range(5)}


@pytest.fixture
def deterministic_rng():
    return random.Random(42)


# ── _coerce_int ──────────────────────────────────────────────────────

def test_coerce_int_handles_blank_and_invalid():
    """Blank, None, and unparseable values map to None — used by the
    spawn-coord override to mean 'no override'."""
    assert _coerce_int("") is None
    assert _coerce_int(None) is None
    assert _coerce_int("abc") is None
    assert _coerce_int([1, 2]) is None


def test_coerce_int_passes_through_numeric():
    """Plain numbers and numeric strings round-trip to int."""
    assert _coerce_int(5) == 5
    assert _coerce_int("7") == 7
    assert _coerce_int(-1) == -1
    assert _coerce_int(0) == 0


# ── pick_quest_item_position — override path ────────────────────────

def test_override_used_when_valid(walkable_grid, deterministic_rng):
    """A valid (walkable + unoccupied) override is picked exactly."""
    item = {"item_name": "Sun Sword", "spawn_col": 3, "spawn_row": 2}
    pos = pick_quest_item_position(
        item, walkable_grid, occupied=set(), rng=deterministic_rng)
    assert pos == (3, 2)


def test_override_falls_back_when_unwalkable(deterministic_rng, capsys):
    """Override on a non-walkable tile triggers fallback + warning."""
    walkable = {(0, 0), (1, 0), (2, 0)}
    item = {"item_name": "Sun Sword", "spawn_col": 4, "spawn_row": 4}

    pos = pick_quest_item_position(
        item, walkable, occupied=set(), rng=deterministic_rng)

    assert pos in walkable, "must fall back to a walkable tile"
    captured = capsys.readouterr()
    assert "(4,4)" in captured.out
    assert "Sun Sword" in captured.out


def test_override_falls_back_when_occupied(walkable_grid,
                                            deterministic_rng, capsys):
    """An override pointing at an occupied tile falls back."""
    item = {"item_name": "Crown", "spawn_col": 1, "spawn_row": 1}
    occupied = {(1, 1)}

    pos = pick_quest_item_position(
        item, walkable_grid, occupied, deterministic_rng)

    assert pos != (1, 1)
    assert pos in walkable_grid
    assert pos not in occupied
    out = capsys.readouterr().out
    assert "occupied" in out.lower() or "invalid" in out.lower()


def test_negative_override_is_no_override(walkable_grid,
                                            deterministic_rng):
    """Negative coords (a common 'unset' sentinel) are treated as 'no
    override' — random fallback, no warning."""
    item = {"item_name": "Anchor", "spawn_col": -1, "spawn_row": -1}
    buf = io.StringIO()
    with redirect_stdout(buf):
        pos = pick_quest_item_position(
            item, walkable_grid, occupied=set(), rng=deterministic_rng)
    assert pos in walkable_grid
    assert "invalid" not in buf.getvalue().lower(), (
        "negative coords are silent — they're the unset sentinel")


def test_partial_override_is_no_override(walkable_grid,
                                          deterministic_rng):
    """Only one coord set = treat as no override (avoids bad pairings)."""
    # spawn_row missing — should be treated as 'no override' silently.
    item = {"item_name": "Charm", "spawn_col": 2}
    buf = io.StringIO()
    with redirect_stdout(buf):
        pos = pick_quest_item_position(
            item, walkable_grid, occupied=set(), rng=deterministic_rng)
    assert pos in walkable_grid
    assert "invalid" not in buf.getvalue().lower()


def test_string_coords_are_parsed(walkable_grid, deterministic_rng):
    """Coords stored as strings (e.g. round-tripped JSON) still work."""
    item = {"item_name": "Key", "spawn_col": "2", "spawn_row": "3"}
    pos = pick_quest_item_position(
        item, walkable_grid, occupied=set(), rng=deterministic_rng)
    assert pos == (2, 3)


# ── pick_quest_item_position — fallback path ─────────────────────────

def test_no_override_picks_random_walkable(walkable_grid,
                                             deterministic_rng):
    item = {"item_name": "Map"}
    pos = pick_quest_item_position(
        item, walkable_grid, occupied=set(), rng=deterministic_rng)
    assert pos in walkable_grid


def test_returns_none_when_no_walkable_tiles(deterministic_rng):
    """Empty walkable set → None (caller should skip placement)."""
    item = {"item_name": "Idol"}
    pos = pick_quest_item_position(
        item, walkable=set(), occupied=set(), rng=deterministic_rng)
    assert pos is None


def test_returns_none_when_all_occupied(walkable_grid, deterministic_rng):
    """Every walkable tile already taken → None."""
    item = {"item_name": "Relic"}
    pos = pick_quest_item_position(
        item, walkable_grid, occupied=set(walkable_grid),
        rng=deterministic_rng)
    assert pos is None


def test_walkable_can_be_list_or_set(deterministic_rng):
    """The helper accepts both list and set inputs for the walkable
    parameter — callers pass whichever shape is convenient."""
    walkable_list = [(0, 0), (1, 0), (2, 0)]
    item = {"item_name": "Hammer", "spawn_col": 1, "spawn_row": 0}
    pos = pick_quest_item_position(
        item, walkable_list, occupied=set(), rng=deterministic_rng)
    assert pos == (1, 0)


# ── Editor round-trip: spawn_col / spawn_row save/load ───────────────

def test_editor_blank_coords_round_trip_to_missing_keys(game):
    """Authors leaving Spawn Col/Row blank in the UI must NOT write a
    0-valued key into the quest step (which would be a real coord
    override pointing at the top-left tile).  Saving must pop the keys
    so the step truly has no override."""
    game._mod_quest_list = [{"name": "Q", "steps": [{
        "step_type": "collect",
        "description": "step",
        "collect_item": "King's Sword",
        "spawn_location": "",
        "target_count": 1,
    }]}]
    game._mod_quest_cursor = 0
    game._mod_quest_step_list = game._mod_quest_list[0]["steps"]
    game._mod_quest_step_cursor = 0

    game._mod_quest_build_step_fields()
    # Blank both coord fields, then save.
    for fld in game._mod_quest_step_fields:
        if fld.key in ("spawn_col", "spawn_row"):
            fld.value = ""
    game._mod_quest_save_step_fields()

    step = game._mod_quest_step_list[0]
    assert "spawn_col" not in step, "blank → key must be popped"
    assert "spawn_row" not in step


def test_editor_numeric_coords_round_trip_as_ints(game):
    """Typed numbers in the Spawn Col/Row fields persist as ints."""
    game._mod_quest_list = [{"name": "Q", "steps": [{
        "step_type": "collect",
        "description": "step",
        "collect_item": "King's Sword",
        "spawn_location": "",
        "target_count": 1,
    }]}]
    game._mod_quest_cursor = 0
    game._mod_quest_step_list = game._mod_quest_list[0]["steps"]
    game._mod_quest_step_cursor = 0

    game._mod_quest_build_step_fields()
    for fld in game._mod_quest_step_fields:
        if fld.key == "spawn_col":
            fld.value = "7"
        elif fld.key == "spawn_row":
            fld.value = "11"
    game._mod_quest_save_step_fields()

    step = game._mod_quest_step_list[0]
    assert step["spawn_col"] == 7
    assert step["spawn_row"] == 11
