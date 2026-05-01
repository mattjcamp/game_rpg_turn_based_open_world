"""End-to-end overworld map persistence tests.

The overworld ``tile_map`` is rebuilt from the static-map file or seed
on every load — it is not serialized verbatim. Anything the player
mutates during play (cleared dungeons, sailed boats, opened chests,
picked locks, picked-up ground items, triggered one-time shrines)
must be captured at save time and re-applied on load, otherwise the
world resets every reload.

Earlier per-feature deltas (``cleared_dungeons``, ``destroyed_spawns``,
``boat_positions``, ``building_interior_spawns``) were added one bug
at a time and missed several other mutation paths flagged in the
audit. This file exercises the new full-overworld snapshot
(``overworld_tiles`` + ``overworld_tile_props`` +
``overworld_triggered_unique`` + ``overworld_unique_cooldowns``) plus
the existing deltas so a regression in any of them surfaces here.
"""

import json
import os

import pytest

from src.settings import (
    TILE_GRASS, TILE_DUNGEON, TILE_DUNGEON_CLEARED, TILE_DDOOR,
    TILE_LOCKED_DOOR, TILE_PATH,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def isolated_save_dir(tmp_path, monkeypatch):
    """Redirect save_load to write into a temp directory."""
    from src import save_load
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    monkeypatch.setattr(save_load, "_SAVE_DIR", str(save_dir))
    return save_dir


# ── Generic tile mutations ──────────────────────────────────────────


class TestArbitraryTileMutationsRoundTrip:
    """The full overworld snapshot should make *any* runtime tile
    change survive save/load — not just the handful of mutations the
    per-feature deltas were written for.
    """

    def test_random_tile_change_persists(self, game, isolated_save_dir):
        from src import save_load
        # Pick a corner cell that won't collide with module landmarks
        # like roads or town pins. Flip it to a distinctive tile id.
        tm = game.tile_map
        target = (3, 3)
        original = tm.get_tile(*target)
        new_tile = TILE_PATH if original != TILE_PATH else TILE_GRASS
        tm.set_tile(*target, new_tile)

        assert save_load.save_game(1, game)
        # Wipe in-memory state to prove the load is doing the work.
        tm.set_tile(*target, original)
        assert save_load.load_game(1, game)

        assert game.tile_map.get_tile(*target) == new_tile, (
            "An arbitrary runtime tile change must survive save/load.")

    def test_unlocked_door_stays_unlocked(
            self, game, isolated_save_dir):
        # Doors picked or knocked at runtime previously re-locked on
        # reload because TILE_LOCKED_DOOR -> TILE_DDOOR was treated
        # as a transient change.
        from src import save_load
        tm = game.tile_map
        # Plant a locked door, then run the unlock the way lock_mixin
        # does it.
        tm.set_tile(2, 2, TILE_LOCKED_DOOR)
        if not hasattr(tm, "tile_properties"):
            tm.tile_properties = {}
        tm.tile_properties["2,2"] = {"locked": True}
        # Simulate the unlock.
        tm.set_tile(2, 2, TILE_DDOOR)
        del tm.tile_properties["2,2"]

        assert save_load.save_game(1, game)
        # Stomp the in-memory state back to locked so reload has work.
        tm.set_tile(2, 2, TILE_LOCKED_DOOR)
        tm.tile_properties["2,2"] = {"locked": True}
        assert save_load.load_game(1, game)

        assert game.tile_map.get_tile(2, 2) == TILE_DDOOR
        # The "locked" property must NOT be back on the tile.
        props = game.tile_map.tile_properties.get("2,2", {})
        assert "locked" not in props


# ── tile_properties (ground items, etc.) ───────────────────────────


class TestTilePropertiesRoundTrip:
    """``tile_properties`` carries authored data (links, walkability
    overrides, item drops). Pickups and other in-place mutations must
    survive the rebuild on load.
    """

    def test_picked_up_ground_item_stays_gone(
            self, game, isolated_save_dir):
        from src import save_load
        tm = game.tile_map
        if not hasattr(tm, "tile_properties"):
            tm.tile_properties = {}
        # Plant an item, then pop it — exactly what the runtime
        # ``pop_ground_item`` helper does.
        tm.tile_properties["6,6"] = {"item": "Health Potion"}
        popped = tm.pop_ground_item(6, 6)
        assert popped == "Health Potion"
        assert "6,6" not in tm.tile_properties

        assert save_load.save_game(1, game)
        # Re-plant the item to mimic the "static map says there's an
        # item here" scenario; reload must overwrite that with the
        # post-pickup state.
        tm.tile_properties["6,6"] = {"item": "Health Potion"}
        assert save_load.load_game(1, game)

        # The picked-up item should still be gone.
        assert game.tile_map.pop_ground_item(6, 6) is None, (
            "A ground item the player picked up should not respawn "
            "on load.")


# ── Unique-tile triggers and cooldowns ─────────────────────────────


class TestUniqueTilePersistence:
    """One-time unique tiles (e.g. ancient shrines that grant a
    permanent buff) must stay triggered across loads, and any per-tile
    cooldowns (e.g. the moongate's daily-use timer) must keep counting.
    """

    def test_triggered_unique_persists(self, game, isolated_save_dir):
        from src import save_load
        tm = game.tile_map
        tm.mark_unique_triggered(7, 8)
        assert (7, 8) in tm.triggered_unique

        assert save_load.save_game(1, game)
        # Reset the in-memory set so we can prove load restored it.
        tm.triggered_unique = set()
        assert save_load.load_game(1, game)

        assert (7, 8) in game.tile_map.triggered_unique, (
            "A one-time triggered tile should remain marked on reload "
            "so the player can't re-trigger it.")

    def test_unique_cooldown_persists(self, game, isolated_save_dir):
        from src import save_load
        tm = game.tile_map
        tm.set_unique_cooldown(4, 5, 12)
        assert tm.unique_cooldowns.get((4, 5)) == 12

        assert save_load.save_game(1, game)
        tm.unique_cooldowns = {}
        assert save_load.load_game(1, game)

        assert game.tile_map.unique_cooldowns.get((4, 5)) == 12


# ── Active-quest dungeon pin restoration (gap 5) ───────────────────


class TestActiveQuestDungeonPin:
    """An accepted inn-style quest plants a TILE_DUNGEON on the
    overworld so the player can find their target. Pre-fix, that pin
    disappeared on reload because the saved ``quest`` dict carried
    the coords but ``_restore_quest`` never re-stamped the tile.
    """

    def test_active_quest_dungeon_tile_restored(
            self, game, isolated_save_dir):
        from src import save_load
        # Stand up a minimal active legacy quest pointing at a
        # specific overworld tile.
        game.quest = {
            "status": "active",
            "dungeon_col": 5,
            "dungeon_row": 5,
            "artifact_name": "Test Crystal",
            "name": "Test Quest",
            "current_level": 0,
            "quest_type": "retrieve",
            "kill_target": None,
            "kill_count": 0,
            "kill_progress": 0,
            "exit_portal": True,
            "levels": [],
        }
        # Plant the dungeon tile the way the inn-quest accept code
        # does, then save.
        game.tile_map.set_tile(5, 5, TILE_DUNGEON)
        assert save_load.save_game(1, game)
        # Wipe the tile so the load path has work to do — even if
        # the v4 snapshot didn't run for some reason, the v3
        # back-compat path in _restore_quest must still re-stamp.
        game.tile_map.set_tile(5, 5, TILE_GRASS)

        # Strip the v4 snapshot fields from disk so we exclusively
        # exercise the back-compat re-stamp in _restore_quest.
        for fn in os.listdir(isolated_save_dir):
            path = os.path.join(isolated_save_dir, fn)
            with open(path) as f:
                data = json.load(f)
            data.pop("overworld_tiles", None)
            data.pop("overworld_tile_props", None)
            with open(path, "w") as f:
                json.dump(data, f)

        assert save_load.load_game(1, game)
        assert game.tile_map.get_tile(5, 5) == TILE_DUNGEON, (
            "Active quest's dungeon pin must be re-stamped onto the "
            "overworld tile_map on load — without it, the player "
            "loses sight of their objective after reloading.")


# ── Back-compat ────────────────────────────────────────────────────


class TestReturnToGamePreservesProgress:
    """The "RETURN TO GAME" button on the title menu must not clobber
    runtime tile mutations. The original implementation refreshed the
    overworld interior list AND overwrote ``tile_map.tiles`` with the
    static map's pristine data — wiping every quest-unlocked bridge,
    every sailed boat, every cleared dungeon every time the player
    bounced through the menu. Same applied to the dungeon cache.

    Module authors who want to live-test overworld / dungeon edits
    can start a new game from the modules screen.
    """

    def test_overworld_tile_mutations_survive_menu_return(
            self, game, tmp_path, monkeypatch):
        # Plant some module data on disk so
        # ``_refresh_overworld_interior_data`` actually engages
        # (it returns early when active_module_path is unset).
        import json
        import os
        mod_dir = tmp_path / "fake_module"
        mod_dir.mkdir()
        # Provide a static_overworld.json with a *different* tile
        # layout than what's in memory — if the function reads it
        # and overwrites tile_map.tiles, the test will catch it.
        bogus_tiles = [
            [TILE_GRASS for _ in range(game.tile_map.width)]
            for _ in range(game.tile_map.height)
        ]
        with open(mod_dir / "static_overworld.json", "w") as f:
            json.dump({
                "interiors": [],
                "tiles": bogus_tiles,
                "map_config": {
                    "width": game.tile_map.width,
                    "height": game.tile_map.height,
                },
            }, f)
        game.active_module_path = str(mod_dir)
        game._game_started = True

        # Simulate runtime mutations: a bridge tile from a quest
        # unlock, a boat the player has sailed.
        game.tile_map.set_tile(10, 10, TILE_PATH)
        game.tile_map.set_tile(15, 15, TILE_DUNGEON_CLEARED)
        # Also stash a non-empty dungeon cache so we can see it
        # survive the return.
        game.dungeon_cache[(20, 20)] = ["sentinel"]

        # Take the menu→return path.
        game.showing_title = True
        game._title_return_to_game()

        # Tile mutations must still be there.
        assert game.tile_map.get_tile(10, 10) == TILE_PATH, (
            "Quest-unlocked tile at (10,10) was wiped by menu return.")
        assert game.tile_map.get_tile(15, 15) == TILE_DUNGEON_CLEARED, (
            "Cleared dungeon pin at (15,15) was wiped by menu return.")
        # Dungeon cache must still be there.
        assert game.dungeon_cache.get((20, 20)) == ["sentinel"], (
            "Dungeon cache cleared by menu return — explored "
            "procedural dungeons should not reset.")
        # And the title screen should be dismissed.
        assert game.showing_title is False


class TestLegacySaveCompat:
    """v3 saves predate the full-overworld snapshot. They should still
    load without errors and continue to use the per-feature deltas.
    """

    def test_v3_save_loads_cleanly(self, game, isolated_save_dir):
        from src import save_load
        assert save_load.save_game(1, game)
        # Strip the v4 fields to mimic an older save.
        for fn in os.listdir(isolated_save_dir):
            path = os.path.join(isolated_save_dir, fn)
            with open(path) as f:
                data = json.load(f)
            for key in (
                    "overworld_tiles", "overworld_tile_props",
                    "overworld_triggered_unique",
                    "overworld_unique_cooldowns"):
                data.pop(key, None)
            data["version"] = 3
            with open(path, "w") as f:
                json.dump(data, f)
        # A v3-shaped save must still load cleanly. The per-feature
        # deltas (cleared_dungeons, boat_positions, etc.) cover the
        # mutations they always have; the v4-only mutations just
        # quietly revert to the rebuilt-map state.
        assert save_load.load_game(1, game)
