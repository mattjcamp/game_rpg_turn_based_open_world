"""
Tests for the "World Unlock" quest reward type.

A quest can grant ``reward_world_unlocks`` — a list of tile-mutation
ops applied to the overworld tile map when the quest is turned in.
This makes it possible to model rewards like "build a bridge" or
"clear a rockslide" that reshape the map permanently.

Coverage here:
  * ``apply_world_unlocks`` mutates the tile map and skips bad ops.
  * The kind→tile picker offers passable-only tiles for
    ``remove_obstacle`` and the broader set for ``add_tile``.
  * ``_replay_world_unlocks`` re-applies unlocks for every quest with
    status ``turned_in`` after a load and ignores other statuses —
    this is how the change persists across save/load without storing
    a separate world diff.
"""

from types import SimpleNamespace

import pytest

from src.module_editor_quest import (
    apply_world_unlocks,
    world_unlock_tile_options,
    world_unlock_tile_name,
    WORLD_UNLOCK_KIND_REMOVE,
    WORLD_UNLOCK_KIND_ADD,
)
from src.save_load import _replay_world_unlocks
from src.settings import (
    TILE_BRIDGE, TILE_GRASS, TILE_MOUNTAIN, TILE_PATH, TILE_WATER,
    TILE_DEFS,
)
from src.tile_map import TileMap


# ── apply_world_unlocks ─────────────────────────────────────────────


class TestApplyWorldUnlocks:

    def test_single_set_tile_op_changes_tile(self):
        tmap = TileMap(width=10, height=10, default_tile=TILE_MOUNTAIN)
        ops = [{"kind": "remove_obstacle", "col": 4, "row": 5,
                "tile": TILE_GRASS}]
        applied = apply_world_unlocks(tmap, ops)
        assert tmap.get_tile(4, 5) == TILE_GRASS
        assert applied == [(4, 5, TILE_GRASS)]

    def test_multi_op_supports_two_wide_bridges(self):
        """A single quest can lay multiple tiles in one reward —
        useful for bridges that span two water columns."""
        tmap = TileMap(width=10, height=10, default_tile=TILE_WATER)
        ops = [
            {"kind": "add_tile", "col": 3, "row": 2, "tile": TILE_BRIDGE},
            {"kind": "add_tile", "col": 4, "row": 2, "tile": TILE_BRIDGE},
        ]
        applied = apply_world_unlocks(tmap, ops)
        assert tmap.get_tile(3, 2) == TILE_BRIDGE
        assert tmap.get_tile(4, 2) == TILE_BRIDGE
        assert applied == [(3, 2, TILE_BRIDGE), (4, 2, TILE_BRIDGE)]

    def test_out_of_bounds_op_silently_skipped(self):
        tmap = TileMap(width=10, height=10, default_tile=TILE_MOUNTAIN)
        ops = [{"kind": "add_tile", "col": 999, "row": 999,
                "tile": TILE_GRASS}]
        applied = apply_world_unlocks(tmap, ops)
        assert applied == []
        # Pre-existing tiles untouched
        assert tmap.get_tile(0, 0) == TILE_MOUNTAIN

    def test_malformed_op_silently_skipped(self):
        tmap = TileMap(width=10, height=10, default_tile=TILE_MOUNTAIN)
        ops = [
            None,
            {"kind": "add_tile"},  # no col/row/tile
            {"col": "not-a-number", "row": 0, "tile": TILE_GRASS},
            {"col": 1, "row": 1, "tile": TILE_GRASS},  # this one is valid
        ]
        applied = apply_world_unlocks(tmap, ops)
        assert applied == [(1, 1, TILE_GRASS)]
        assert tmap.get_tile(1, 1) == TILE_GRASS

    def test_empty_list_is_safe(self):
        tmap = TileMap(width=4, height=4, default_tile=TILE_GRASS)
        assert apply_world_unlocks(tmap, []) == []
        assert apply_world_unlocks(tmap, None) == []
        assert apply_world_unlocks(None, [{"col": 0, "row": 0,
                                            "tile": TILE_GRASS}]) == []


# ── tile-picker helpers ─────────────────────────────────────────────


class TestTilePickerOptions:

    def test_remove_obstacle_offers_only_passable_tiles(self):
        opts = world_unlock_tile_options(WORLD_UNLOCK_KIND_REMOVE)
        assert opts, "Remove Obstacle should offer at least one tile"
        for name, tid in opts:
            assert TILE_DEFS[tid]["walkable"], (
                f"Remove Obstacle picker offered impassable tile "
                f"'{name}' (tile_id={tid}); only walkable tiles "
                f"should appear here.")

    def test_add_tile_includes_water_and_mountain(self):
        opts = world_unlock_tile_options(WORLD_UNLOCK_KIND_ADD)
        ids = {tid for _, tid in opts}
        assert TILE_WATER in ids
        assert TILE_MOUNTAIN in ids
        assert TILE_BRIDGE in ids

    def test_unknown_kind_returns_empty(self):
        assert world_unlock_tile_options("") == []
        assert world_unlock_tile_options("nonexistent") == []

    def test_tile_name_lookup(self):
        # Real id round-trips through the TILE_DEFS table
        assert world_unlock_tile_name(TILE_GRASS) == TILE_DEFS[TILE_GRASS]["name"]
        # Unknown ids fall back to a stable "Tile <id>" string
        assert "1234" in world_unlock_tile_name(1234)
        # None / empty short-circuits
        assert world_unlock_tile_name(None) == "(none)"


# ── _replay_world_unlocks (the load-side persistence path) ──────────


def _fake_game(tile_width=20, tile_height=20, default_tile=TILE_MOUNTAIN,
               quest_defs=None, quest_states=None):
    """Build the minimum fake game object _replay_world_unlocks needs.

    Avoids spinning up the full Game class — we only care about three
    attributes (``tile_map``, ``_module_quest_defs``,
    ``module_quest_states``) on the load path.
    """
    return SimpleNamespace(
        tile_map=TileMap(tile_width, tile_height,
                         default_tile=default_tile),
        _module_quest_defs=quest_defs or [],
        module_quest_states=quest_states or {},
    )


class TestReplayWorldUnlocksOnLoad:

    def test_turned_in_quest_unlocks_are_replayed(self):
        """The one path that matters: a completed-and-turned-in quest's
        unlocks must re-apply on load, otherwise the world diff is
        lost between sessions."""
        game = _fake_game(
            quest_defs=[{
                "name": "Build the Bridge",
                "reward_world_unlocks": [
                    {"kind": "add_tile", "col": 5, "row": 5,
                     "tile": TILE_BRIDGE}
                ],
            }],
            quest_states={
                "Build the Bridge": {"status": "turned_in"},
            },
        )
        # Pre-condition: the bridge is *not* there yet (the tile_map
        # was just rebuilt from seed/static map by load_game).
        assert game.tile_map.get_tile(5, 5) == TILE_MOUNTAIN
        _replay_world_unlocks(game)
        assert game.tile_map.get_tile(5, 5) == TILE_BRIDGE

    @pytest.mark.parametrize("status", [
        "available", "active", "completed",  # "completed" = ready to turn in
    ])
    def test_non_turned_in_quests_are_skipped(self, status):
        """Only fully turned-in quests should mutate the world.  An
        active or ready-to-turn-in quest hasn't actually granted its
        reward yet — replaying it would double-apply the unlock once
        the player turns it in."""
        game = _fake_game(
            quest_defs=[{
                "name": "Pending Quest",
                "reward_world_unlocks": [
                    {"kind": "add_tile", "col": 3, "row": 3,
                     "tile": TILE_BRIDGE}
                ],
            }],
            quest_states={"Pending Quest": {"status": status}},
        )
        _replay_world_unlocks(game)
        assert game.tile_map.get_tile(3, 3) == TILE_MOUNTAIN

    def test_quests_without_unlocks_dont_crash(self):
        """Most quests don't have a world-unlock reward — replay must
        be a no-op for them, not raise."""
        game = _fake_game(
            quest_defs=[{"name": "Just XP", "reward_xp": 100}],
            quest_states={"Just XP": {"status": "turned_in"}},
        )
        # Should not raise.
        _replay_world_unlocks(game)

    def test_no_quest_defs_is_safe(self):
        """Modules without any quests authored shouldn't crash on
        load."""
        game = _fake_game(quest_defs=[], quest_states={})
        _replay_world_unlocks(game)  # must not raise

    def test_replay_is_idempotent(self):
        """Replaying twice should produce the same result as once —
        load → save → load should not double-apply anything."""
        game = _fake_game(
            quest_defs=[{
                "name": "Clear the Rockslide",
                "reward_world_unlocks": [
                    {"kind": "remove_obstacle", "col": 7, "row": 7,
                     "tile": TILE_PATH}
                ],
            }],
            quest_states={
                "Clear the Rockslide": {"status": "turned_in"},
            },
        )
        _replay_world_unlocks(game)
        first = game.tile_map.get_tile(7, 7)
        _replay_world_unlocks(game)
        second = game.tile_map.get_tile(7, 7)
        assert first == second == TILE_PATH


# ── End-to-end JSON round-trip ──────────────────────────────────────


class TestQuestJsonRoundTrip:

    def test_apply_works_on_quest_dict_loaded_from_json(self, tmp_path):
        """A quest authored with reward_world_unlocks should serialize
        cleanly to JSON and apply correctly when read back — i.e. the
        on-disk schema is what the runtime expects."""
        import json
        quest = {
            "name": "Open the Pass",
            "reward_xp": 50,
            "reward_world_unlocks": [
                {"kind": "remove_obstacle", "col": 8, "row": 4,
                 "tile": TILE_GRASS},
            ],
        }
        # Dump and re-read to make sure the JSON path doesn't drop or
        # mangle the new field.
        quests_path = tmp_path / "quests.json"
        quests_path.write_text(json.dumps([quest]))
        loaded = json.loads(quests_path.read_text())
        assert loaded[0]["reward_world_unlocks"][0]["tile"] == TILE_GRASS

        tmap = TileMap(width=20, height=20, default_tile=TILE_MOUNTAIN)
        applied = apply_world_unlocks(
            tmap, loaded[0]["reward_world_unlocks"])
        assert applied == [(8, 4, TILE_GRASS)]
        assert tmap.get_tile(8, 4) == TILE_GRASS
