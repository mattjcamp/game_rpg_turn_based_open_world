"""
Building-interior monster persistence.

Building interiors rebuild their tile_map from the JSON definition on
every entry, so the per-tile_map ``_spawned_placement_positions`` set
that drives the spawn-once gate would normally be empty on every visit
— meaning a designer-placed encounter the party already killed would
respawn the next time they walked in the door. The fix caches the set
on ``game.building_interior_spawns`` (keyed by interior name) and
re-attaches it to each freshly-built interior tile_map by reference.

Coverage here:
  * The cache is initialised on a fresh ``Game`` and cleared on
    ``reset_for_new_game``.
  * ``_enter_overworld_interior`` attaches the cached set onto the
    interior tile_map *by reference* — not a copy — so additions made
    during a visit (i.e. when a placement is materialised) survive an
    exit/re-enter cycle.
  * Each interior gets its own cache slot, so clearing one building
    can't suppress encounters in another.
  * The cache round-trips through save/load, and older saves missing
    the field load cleanly with an empty cache.
"""

import json
import os

import pytest

from src.settings import TILE_GRASS


# ── Helpers ─────────────────────────────────────────────────────────


def _install_test_interior(game, name="Abandoned Building", w=8, h=8):
    """Attach a tiny grass-floored interior to the overworld map.

    ``_enter_overworld_interior`` looks up its target in
    ``tile_map.overworld_interiors`` and refuses to enter if no
    matching definition with non-empty ``tiles`` is present.
    """
    tiles = {}
    for y in range(h):
        for x in range(w):
            tiles[f"{x},{y}"] = {"tile_id": TILE_GRASS}
    interior = {
        "name": name,
        "width": w,
        "height": h,
        "entry_col": 1,
        "entry_row": 1,
        "tiles": tiles,
        "tile_properties": {},
        "npcs": [],
    }
    if not getattr(game.tile_map, "overworld_interiors", None):
        game.tile_map.overworld_interiors = []
    game.tile_map.overworld_interiors.append(interior)
    return interior


# ── Game state init / reset ─────────────────────────────────────────


class TestGameStateInit:

    def test_fresh_game_has_empty_spawn_cache(self, game):
        assert hasattr(game, "building_interior_spawns")
        assert game.building_interior_spawns == {}

    def test_new_game_clears_spawn_cache(self, game):
        """Starting a new game from the title screen must wipe the
        cache — otherwise "this lair is already cleared" markers from
        a previous playthrough would silently apply to the fresh
        world."""
        game.building_interior_spawns["Crypt"] = {(1, 2), (3, 4)}
        game._title_new_game()
        assert game.building_interior_spawns == {}


# ── Interior entry wiring ───────────────────────────────────────────


class TestInteriorEntryAttachesCachedSet:

    def test_entry_creates_cache_entry_and_aliases_it(self, game):
        """Entering an interior must attach the game-level cached set
        onto the freshly-built interior tile_map *by reference*. Aliasing
        (not copying) is the whole point — it's what makes mutations
        from ``_spawn_placed_encounters`` propagate back to the cache.
        """
        _install_test_interior(game, name="Abandoned Building")
        ow = game.states["overworld"]

        ow._enter_overworld_interior(
            "Abandoned Building", door_col=10, door_row=10,
            building_name="Abandoned Building")

        cached = game.building_interior_spawns.get("Abandoned Building")
        assert cached is not None, (
            "Entering an interior should auto-create a cache entry.")
        assert game.tile_map._spawned_placement_positions is cached, (
            "The interior tile_map's spawn-once set must be the same "
            "object as the cached set, not a copy.")

    def test_re_entry_after_exit_preserves_spawn_marks(self, game):
        """The whole point: a placement marked as already-spawned (i.e.
        a monster the party fought and killed) stays marked across an
        exit-and-re-enter cycle."""
        _install_test_interior(game, name="Abandoned Building")
        ow = game.states["overworld"]

        ow._enter_overworld_interior(
            "Abandoned Building", door_col=10, door_row=10,
            building_name="Abandoned Building")
        # Stand-in for ``_spawn_placed_encounters`` materialising a
        # placement at (4, 4) and the player then defeating it.
        game.tile_map._spawned_placement_positions.add((4, 4))
        ow._exit_overworld_interior()

        ow._enter_overworld_interior(
            "Abandoned Building", door_col=10, door_row=10,
            building_name="Abandoned Building")
        assert (4, 4) in game.tile_map._spawned_placement_positions, (
            "Spawn-once marks must persist across re-entry, otherwise "
            "killed monsters respawn when the party walks back in.")

    def test_each_interior_has_its_own_cache_entry(self, game):
        """Different interiors must not share a spawn-once set —
        clearing one building shouldn't suppress encounters in
        another."""
        _install_test_interior(game, name="Abandoned Building")
        _install_test_interior(game, name="Watch Tower")
        ow = game.states["overworld"]

        ow._enter_overworld_interior(
            "Abandoned Building", door_col=10, door_row=10,
            building_name="Abandoned Building")
        game.tile_map._spawned_placement_positions.add((1, 1))
        ow._exit_overworld_interior()

        ow._enter_overworld_interior(
            "Watch Tower", door_col=11, door_row=10,
            building_name="Watch Tower")
        # The Watch Tower's cache must not see the Abandoned
        # Building's mark.
        assert game.tile_map._spawned_placement_positions == set()


# ── save / load round-trip ──────────────────────────────────────────


@pytest.fixture
def isolated_save_dir(tmp_path, monkeypatch):
    """Redirect save_load to write into a temp directory."""
    from src import save_load
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    monkeypatch.setattr(save_load, "_SAVE_DIR", str(save_dir))
    return save_dir


class TestSaveLoadRoundTrip:

    def test_round_trip_preserves_per_interior_sets(
            self, game, isolated_save_dir):
        from src import save_load

        game.building_interior_spawns = {
            "Abandoned Building": {(2, 3), (5, 7)},
            "Watch Tower": {(0, 0)},
        }
        assert save_load.save_game(1, game), "save_game returned False"

        # Wipe the in-memory state so we know the load is doing the work.
        game.building_interior_spawns = {}
        assert save_load.load_game(1, game), "load_game returned False"

        restored = game.building_interior_spawns
        assert restored.get("Abandoned Building") == {(2, 3), (5, 7)}
        assert restored.get("Watch Tower") == {(0, 0)}

    def test_legacy_save_without_field_loads_cleanly(
            self, game, isolated_save_dir):
        """Saves predating the new field shouldn't crash on load —
        they should yield an empty cache."""
        from src import save_load

        assert save_load.save_game(1, game)

        # Strip the field from disk to mimic a legacy save.
        for fn in os.listdir(isolated_save_dir):
            path = os.path.join(isolated_save_dir, fn)
            with open(path) as f:
                data = json.load(f)
            data.pop("building_interior_spawns", None)
            with open(path, "w") as f:
                json.dump(data, f)

        # Pre-populate with stale data to confirm it gets overwritten,
        # not unioned, by the load.
        game.building_interior_spawns = {"stale": {(9, 9)}}
        assert save_load.load_game(1, game)
        assert game.building_interior_spawns == {}
