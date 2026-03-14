"""
Tests for the Examine state — zoomed-in local area view.
"""

import sys
import os
import pytest
import pygame

# conftest helpers aren't importable as a module; inline what we need.
sys.path.insert(0, os.path.dirname(__file__))
from conftest import make_event, tick


# ── Helpers ──────────────────────────────────────────────────────

@pytest.fixture
def examine(game):
    """Enter the examine state from overworld."""
    game.change_state("examine")
    return game.states["examine"]


# =====================================================================
# State setup
# =====================================================================

class TestExamineSetup:
    def test_examine_state_registered(self, game):
        assert "examine" in game.states

    def test_grid_dimensions(self):
        from src.states.examine import EXAMINE_COLS, EXAMINE_ROWS
        assert EXAMINE_COLS == 12
        assert EXAMINE_ROWS == 14

    def test_initial_player_position(self, examine):
        from src.states.examine import _START_COL, _START_ROW
        assert examine.player_col == _START_COL
        assert examine.player_row == _START_ROW


# =====================================================================
# enter() behaviour
# =====================================================================

class TestExamineEnter:
    def test_sets_tile_type(self, examine, game):
        expected = game.tile_map.get_tile(game.party.col, game.party.row)
        assert examine.examined_tile_type == expected

    def test_sets_tile_name(self, examine):
        assert isinstance(examine.tile_name, str)
        assert len(examine.tile_name) > 0

    def test_party_member_name_is_empty(self, examine, game):
        """Examine screen should not display an individual member name."""
        assert examine.party_member_name == ""

    def test_spawns_items_within_bounds(self, examine):
        from src.states.examine import EXAMINE_COLS, EXAMINE_ROWS
        for (c, r) in examine.ground_items:
            assert 1 <= c <= EXAMINE_COLS - 2
            assert 1 <= r <= EXAMINE_ROWS - 2

    def test_items_not_on_player_start(self, examine):
        from src.states.examine import _START_COL, _START_ROW
        assert (_START_COL, _START_ROW) not in examine.ground_items

    def test_spawns_at_most_one_item(self, examine):
        # Run enter() many times to verify the max
        for _ in range(50):
            examine.enter()
            assert len(examine.ground_items) <= 1

    def test_items_not_on_obstacles(self, examine):
        for _ in range(50):
            examine.enter()
            for pos in examine.ground_items:
                assert pos not in examine.obstacles


# =====================================================================
# Movement
# =====================================================================

class TestExamineMovement:
    def test_move_down(self, examine):
        examine.obstacles.clear()
        start_row = examine.player_row
        examine.handle_input([make_event(pygame.K_DOWN)], [0] * 512)
        assert examine.player_row == start_row + 1

    def test_move_up(self, examine):
        examine.obstacles.clear()
        examine.player_row = 5
        examine.handle_input([make_event(pygame.K_UP)], [0] * 512)
        assert examine.player_row == 4

    def test_move_left(self, examine):
        examine.obstacles.clear()
        examine.player_col = 5
        examine.handle_input([make_event(pygame.K_LEFT)], [0] * 512)
        assert examine.player_col == 4

    def test_move_right(self, examine):
        examine.obstacles.clear()
        start_col = examine.player_col
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert examine.player_col == start_col + 1

    def test_wasd_movement(self, examine):
        examine.obstacles.clear()
        examine.player_col = 5
        examine.player_row = 5
        examine.handle_input([make_event(pygame.K_w)], [0] * 512)
        assert examine.player_row == 4
        examine.handle_input([make_event(pygame.K_s)], [0] * 512)
        assert examine.player_row == 5
        examine.handle_input([make_event(pygame.K_a)], [0] * 512)
        assert examine.player_col == 4
        examine.handle_input([make_event(pygame.K_d)], [0] * 512)
        assert examine.player_col == 5

    def test_blocked_by_obstacle(self, examine):
        examine.obstacles.clear()
        target = (examine.player_col + 1, examine.player_row)
        examine.obstacles[target] = "tree"
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert examine.player_col != target[0]  # didn't move

    def test_blocked_at_top_edge(self, examine):
        examine.player_row = 1
        examine.handle_input([make_event(pygame.K_UP)], [0] * 512)
        assert examine.player_row == 1  # can't move into row 0 (edge)

    def test_blocked_at_left_edge(self, examine):
        examine.player_col = 1
        examine.handle_input([make_event(pygame.K_LEFT)], [0] * 512)
        assert examine.player_col == 1

    def test_blocked_at_bottom_edge(self, examine):
        from src.states.examine import EXAMINE_ROWS
        examine.player_row = EXAMINE_ROWS - 2
        examine.handle_input([make_event(pygame.K_DOWN)], [0] * 512)
        assert examine.player_row == EXAMINE_ROWS - 2

    def test_blocked_at_right_edge(self, examine):
        from src.states.examine import EXAMINE_COLS
        examine.player_col = EXAMINE_COLS - 2
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert examine.player_col == EXAMINE_COLS - 2


# =====================================================================
# Item pickup
# =====================================================================

class TestExaminePickup:
    def test_walking_on_item_picks_it_up(self, examine, game):
        examine.obstacles.clear()
        item_col = examine.player_col + 1
        item_row = examine.player_row
        examine.ground_items[(item_col, item_row)] = {
            "item": "Torch", "gold": 0}
        inv_before = game.party.inv_count("Torch")
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert (item_col, item_row) not in examine.ground_items
        assert game.party.inv_count("Torch") == inv_before + 1

    def test_pickup_sets_message(self, examine):
        examine.obstacles.clear()
        item_col = examine.player_col + 1
        examine.ground_items[(item_col, examine.player_row)] = {
            "item": "Stones", "gold": 0}
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert "Stones" in examine.pickup_message
        assert examine.pickup_msg_timer > 0

    def test_pickup_message_fades(self, examine):
        examine.obstacles.clear()
        item_col = examine.player_col + 1
        examine.ground_items[(item_col, examine.player_row)] = {
            "item": "Stones", "gold": 0}
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert examine.pickup_msg_timer > 0
        examine.update(3.0)
        assert examine.pickup_msg_timer == 0
        assert examine.pickup_message == ""

    def test_gold_pickup(self, examine, game):
        examine.obstacles.clear()
        item_col = examine.player_col + 1
        examine.ground_items[(item_col, examine.player_row)] = {
            "item": None, "gold": 25}
        gold_before = game.party.gold
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert game.party.gold == gold_before + 25

    def test_no_pickup_on_empty_tile(self, examine):
        examine.obstacles.clear()
        examine.ground_items.clear()
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert examine.pickup_message == ""


# =====================================================================
# State transitions
# =====================================================================

class TestExamineTransitions:
    def test_esc_returns_to_overworld(self, examine, game):
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        assert game.current_state is game.states["overworld"]

    def test_party_position_unchanged(self, game):
        col_before = game.party.col
        row_before = game.party.row
        game.change_state("examine")
        examine = game.states["examine"]
        # Move around
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        examine.handle_input([make_event(pygame.K_DOWN)], [0] * 512)
        # Leave
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        assert game.party.col == col_before
        assert game.party.row == row_before


# =====================================================================
# Loot tables
# =====================================================================

class TestExamineLootTables:
    def test_all_terrain_tables_exist(self):
        from src.states.examine import EXAMINE_LOOT
        from src.settings import TILE_GRASS, TILE_FOREST, TILE_SAND, TILE_PATH
        for tile in (TILE_GRASS, TILE_FOREST, TILE_SAND, TILE_PATH):
            assert tile in EXAMINE_LOOT
            assert len(EXAMINE_LOOT[tile]) > 0

    def test_loot_entries_are_valid_items(self):
        """All non-placeholder entries must exist in ITEM_INFO."""
        from src.states.examine import EXAMINE_LOOT, FORAGE_REAGENTS
        from src.party import ITEM_INFO
        for tile_type, table in EXAMINE_LOOT.items():
            for item_name, weight in table:
                if item_name == "_reagent_":
                    # Placeholder — the actual reagents are checked below
                    continue
                assert item_name in ITEM_INFO, \
                    f"{item_name} not found in ITEM_INFO (tile {tile_type})"
                assert weight > 0

    def test_forage_reagents_are_valid_items(self):
        """Every reagent in the forage list must exist in ITEM_INFO."""
        from src.states.examine import FORAGE_REAGENTS
        from src.party import ITEM_INFO
        for reagent in FORAGE_REAGENTS:
            assert reagent in ITEM_INFO, \
                f"Forage reagent {reagent} not found in ITEM_INFO"

    def test_default_fallback(self):
        """Unmapped tile types fall back to grass loot."""
        from src.states.examine import EXAMINE_LOOT, _DEFAULT_LOOT
        from src.settings import TILE_GRASS
        assert _DEFAULT_LOOT is EXAMINE_LOOT[TILE_GRASS]

    def test_loot_contains_rocks_reagents_herbs(self):
        """Each terrain table should have Rock, _reagent_, and Healing Herb."""
        from src.states.examine import EXAMINE_LOOT
        for tile_type, table in EXAMINE_LOOT.items():
            names = [name for name, _ in table]
            assert "Rock" in names, f"Rock missing from tile {tile_type}"
            assert "_reagent_" in names, f"_reagent_ missing from tile {tile_type}"
            assert "Healing Herb" in names, \
                f"Healing Herb missing from tile {tile_type}"

    def test_rock_is_most_common(self):
        """Rock should have the highest weight in every terrain."""
        from src.states.examine import EXAMINE_LOOT
        for tile_type, table in EXAMINE_LOOT.items():
            by_name = {name: w for name, w in table}
            assert by_name["Rock"] > by_name["_reagent_"], \
                f"Rock not more common than reagents in tile {tile_type}"
            assert by_name["Rock"] > by_name["Healing Herb"], \
                f"Rock not more common than herbs in tile {tile_type}"

    def test_reagent_more_common_than_herb(self):
        """Reagents should be more common than Healing Herb."""
        from src.states.examine import EXAMINE_LOOT
        for tile_type, table in EXAMINE_LOOT.items():
            by_name = {name: w for name, w in table}
            assert by_name["_reagent_"] > by_name["Healing Herb"], \
                f"Reagent not more common than herb in tile {tile_type}"


# =====================================================================
# Herbalist class ability (Ranger / Alchemist reagent boost)
# =====================================================================

class TestExamineHerbalist:
    def test_has_herbalist_false_by_default(self, examine, game):
        """Default party (fighters, etc.) has no herbalist."""
        # Default test party classes are unlikely to be ranger/alchemist
        # but let's set them explicitly to be safe
        for m in game.party.members:
            m.char_class = "Fighter"
        assert examine._has_herbalist() is False

    def test_has_herbalist_with_ranger(self, examine, game):
        game.party.members[0].char_class = "Ranger"
        assert examine._has_herbalist() is True

    def test_has_herbalist_with_alchemist(self, examine, game):
        game.party.members[0].char_class = "Alchemist"
        assert examine._has_herbalist() is True

    def test_herbalist_doubles_reagent_weight(self, examine, game):
        """When a herbalist is present, _reagent_ weight should be doubled."""
        from src.states.examine import EXAMINE_LOOT
        from src.settings import TILE_GRASS
        examine.examined_tile_type = TILE_GRASS
        base_table = EXAMINE_LOOT[TILE_GRASS]
        base_reagent_w = next(w for name, w in base_table if name == "_reagent_")

        # No herbalist
        for m in game.party.members:
            m.char_class = "Fighter"
        _, weights_no = examine._build_loot_table()
        reagent_idx = next(
            i for i, (name, _) in enumerate(base_table) if name == "_reagent_")
        assert weights_no[reagent_idx] == base_reagent_w

        # With herbalist
        game.party.members[0].char_class = "Ranger"
        _, weights_yes = examine._build_loot_table()
        assert weights_yes[reagent_idx] == base_reagent_w * 2

    def test_resolve_item_name_reagent(self, examine):
        """_reagent_ placeholder resolves to a valid reagent name."""
        from src.states.examine import FORAGE_REAGENTS
        for _ in range(20):
            name = examine._resolve_item_name("_reagent_")
            assert name in FORAGE_REAGENTS

    def test_resolve_item_name_passthrough(self, examine):
        """Non-placeholder names pass through unchanged."""
        assert examine._resolve_item_name("Rock") == "Rock"
        assert examine._resolve_item_name("Healing Herb") == "Healing Herb"


# =====================================================================
# Obstacles
# =====================================================================

class TestExamineObstacles:
    def test_obstacles_within_bounds(self, examine):
        from src.states.examine import EXAMINE_COLS, EXAMINE_ROWS
        for (c, r) in examine.obstacles:
            assert 1 <= c <= EXAMINE_COLS - 2
            assert 1 <= r <= EXAMINE_ROWS - 2

    def test_obstacles_not_on_player_start(self, examine):
        from src.states.examine import _START_COL, _START_ROW
        assert (_START_COL, _START_ROW) not in examine.obstacles

    def test_forest_has_many_obstacles(self, examine):
        """Forest terrain should generate several tree obstacles."""
        from src.settings import TILE_FOREST
        examine.examined_tile_type = TILE_FOREST
        counts = []
        for _ in range(30):
            examine._spawn_obstacles()
            counts.append(len(examine.obstacles))
        assert max(counts) >= 6  # forest min is 6

    def test_grass_has_few_obstacles(self, examine):
        """Grass terrain should be mostly open."""
        from src.settings import TILE_GRASS
        examine.examined_tile_type = TILE_GRASS
        for _ in range(30):
            examine._spawn_obstacles()
            assert len(examine.obstacles) <= 2

    def test_obstacle_kinds_match_terrain(self):
        from src.states.examine import TERRAIN_OBSTACLES
        from src.settings import TILE_FOREST, TILE_SAND
        assert TERRAIN_OBSTACLES[TILE_FOREST][0] == "tree"
        assert TERRAIN_OBSTACLES[TILE_SAND][0] == "rock"


# =====================================================================
# Tile persistence
# =====================================================================

class TestExaminePersistence:
    def test_exit_saves_layout(self, examine, game):
        """Exiting examine should persist obstacles and ground_items."""
        examine.obstacles.clear()
        examine.obstacles[(3, 4)] = "tree"
        examine.ground_items[(7, 8)] = {"item": "Torch", "gold": 0}
        col, row = game.party.col, game.party.row
        # Exit to overworld
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        saved = game.get_examined_tile(col, row)
        assert saved is not None
        assert (3, 4) in saved["obstacles"] or "3,4" in saved["obstacles"]

    def test_reenter_restores_layout(self, examine, game):
        """Re-entering the same overworld tile restores the saved layout."""
        examine.obstacles.clear()
        examine.obstacles[(3, 4)] = "bush"
        examine.ground_items.clear()
        examine.ground_items[(7, 8)] = {"item": "Stones", "gold": 0}
        # Exit (saves layout)
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        # Re-enter
        game.change_state("examine")
        ex2 = game.states["examine"]
        assert (3, 4) in ex2.obstacles
        assert ex2.obstacles[(3, 4)] == "bush"
        assert (7, 8) in ex2.ground_items
        assert ex2.ground_items[(7, 8)]["item"] == "Stones"

    def test_fresh_tile_generates_new_layout(self, game):
        """First visit to a tile should generate a fresh random layout."""
        col, row = game.party.col, game.party.row
        assert game.get_examined_tile(col, row) is None
        game.change_state("examine")
        # State has been populated by _spawn_obstacles / _spawn_examine_items
        examine = game.states["examine"]
        assert examine.examined_tile_type is not None

    def test_different_tiles_have_independent_layouts(self, game):
        """Two different overworld tiles have separate saved layouts."""
        # Visit tile at current position
        game.change_state("examine")
        ex = game.states["examine"]
        ex.obstacles.clear()
        ex.obstacles[(2, 2)] = "tree"
        ex.ground_items.clear()
        ex.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        old_col, old_row = game.party.col, game.party.row

        # Move party and visit a different tile
        game.party.col += 1
        game.change_state("examine")
        ex2 = game.states["examine"]
        ex2.obstacles.clear()
        ex2.obstacles[(9, 9)] = "rock"
        ex2.ground_items.clear()
        ex2.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)

        # Verify both are saved independently
        saved1 = game.get_examined_tile(old_col, old_row)
        saved2 = game.get_examined_tile(old_col + 1, old_row)
        assert saved1 is not None
        assert saved2 is not None
        # They should have different obstacle layouts
        obs1_keys = set(saved1["obstacles"].keys())
        obs2_keys = set(saved2["obstacles"].keys())
        assert obs1_keys != obs2_keys

    def test_picked_up_items_not_restored(self, examine, game):
        """If the player picks up an item then leaves,
        the item should NOT reappear on re-entry."""
        examine.obstacles.clear()
        examine.ground_items.clear()
        item_col = examine.player_col + 1
        item_row = examine.player_row
        examine.ground_items[(item_col, item_row)] = {
            "item": "Torch", "gold": 0}
        # Pick up the item
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        assert (item_col, item_row) not in examine.ground_items
        # Exit
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        # Re-enter
        game.change_state("examine")
        ex2 = game.states["examine"]
        # Item was picked up, so it should not be restored
        assert (item_col, item_row) not in ex2.ground_items

    def test_dropped_item_persists_across_visits(self, examine, game):
        """Dropping an item and returning should show it still on the ground."""
        examine.obstacles.clear()
        examine.ground_items.clear()
        # Add an item to party inventory
        game.party.inv_add("Torch")
        # Drop it via the drop mechanism
        examine._enter_drop_mode()
        assert examine.drop_mode is True
        # Select the item (it should be in the list)
        examine._confirm_drop()
        pos = (examine.player_col, examine.player_row)
        assert pos in examine.ground_items
        assert examine.ground_items[pos]["item"] == "Torch"

        # Exit and re-enter
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        game.change_state("examine")
        ex2 = game.states["examine"]
        # The dropped item should still be there (at saved position)
        # Player starts at _START_COL, _START_ROW again,
        # but the item was at that position — check ground_items
        from src.states.examine import _START_COL, _START_ROW
        assert (_START_COL, _START_ROW) in ex2.ground_items
        assert ex2.ground_items[(_START_COL, _START_ROW)]["item"] == "Torch"

    def test_obstacles_persist_across_visits(self, examine, game):
        """Obstacle positions should be the same on re-entry."""
        examine.obstacles.clear()
        examine.obstacles[(4, 5)] = "tree"
        examine.obstacles[(8, 3)] = "bush"
        examine.ground_items.clear()
        # Exit
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        # Re-enter
        game.change_state("examine")
        ex2 = game.states["examine"]
        assert (4, 5) in ex2.obstacles
        assert ex2.obstacles[(4, 5)] == "tree"
        assert (8, 3) in ex2.obstacles
        assert ex2.obstacles[(8, 3)] == "bush"

    def test_game_examined_tiles_dict_exists(self, game):
        """Game should have an examined_tiles dict."""
        assert hasattr(game, "examined_tiles")
        assert isinstance(game.examined_tiles, dict)

    def test_save_and_get_examined_tile(self, game):
        """Accessor methods for examined tiles should work."""
        assert game.get_examined_tile(10, 20) is None
        game.save_examined_tile(10, 20, {"obstacles": {}, "ground_items": {}})
        result = game.get_examined_tile(10, 20)
        assert result is not None
        assert "obstacles" in result


# =====================================================================
# Item dropping
# =====================================================================

class TestExamineDrop:
    def test_l_opens_drop_mode(self, examine, game):
        """Pressing L with items in inventory opens drop mode."""
        game.party.inv_add("Torch")
        examine.handle_input([make_event(pygame.K_l)], [0] * 512)
        assert examine.drop_mode is True
        assert len(examine.drop_items) > 0

    def test_l_with_empty_inventory_shows_message(self, examine, game):
        """Pressing L with no inventory shows a 'nothing to drop' message."""
        game.party.shared_inventory.clear()
        examine.handle_input([make_event(pygame.K_l)], [0] * 512)
        assert examine.drop_mode is False
        assert "empty" in examine.pickup_message.lower()

    def test_drop_mode_cursor_navigation(self, examine, game):
        """Up/Down arrows navigate the drop cursor."""
        game.party.inv_add("Torch")
        game.party.inv_add("Stones")
        examine._enter_drop_mode()
        assert examine.drop_cursor == 0
        examine.handle_input([make_event(pygame.K_DOWN)], [0] * 512)
        assert examine.drop_cursor == 1
        examine.handle_input([make_event(pygame.K_UP)], [0] * 512)
        assert examine.drop_cursor == 0

    def test_drop_mode_cursor_clamps(self, examine, game):
        """Cursor shouldn't go below 0 or above last item."""
        game.party.shared_inventory.clear()
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        assert examine.drop_cursor == 0
        examine.handle_input([make_event(pygame.K_UP)], [0] * 512)
        assert examine.drop_cursor == 0  # can't go negative
        examine.handle_input([make_event(pygame.K_DOWN)], [0] * 512)
        # Only one item, so cursor stays at 0
        assert examine.drop_cursor == 0

    def test_escape_cancels_drop_mode(self, examine, game):
        """ESC while in drop mode cancels without dropping."""
        game.party.shared_inventory.clear()
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        assert examine.drop_mode is True
        examine.handle_input([make_event(pygame.K_ESCAPE)], [0] * 512)
        assert examine.drop_mode is False
        # Item still in inventory
        assert game.party.inv_count("Torch") == 1

    def test_confirm_drop_places_item(self, examine, game):
        """RETURN drops the selected item at player's feet."""
        examine.obstacles.clear()
        examine.ground_items.clear()
        game.party.shared_inventory.clear()
        game.party.inv_add("Stones")
        assert game.party.inv_count("Stones") == 1
        examine._enter_drop_mode()
        examine.handle_input([make_event(pygame.K_RETURN)], [0] * 512)
        pos = (examine.player_col, examine.player_row)
        assert pos in examine.ground_items
        assert examine.ground_items[pos]["item"] == "Stones"
        assert game.party.inv_count("Stones") == 0
        assert examine.drop_mode is False

    def test_drop_sets_message(self, examine, game):
        """Dropping an item shows a drop confirmation message."""
        examine.obstacles.clear()
        examine.ground_items.clear()
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        examine._confirm_drop()
        assert "Dropped" in examine.drop_message
        assert "Torch" in examine.drop_message
        assert examine.drop_msg_timer > 0

    def test_drop_message_fades(self, examine, game):
        """Drop message should fade after timer expires."""
        examine.obstacles.clear()
        examine.ground_items.clear()
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        examine._confirm_drop()
        assert examine.drop_msg_timer > 0
        examine.update(3.0)
        assert examine.drop_msg_timer == 0
        assert examine.drop_message == ""

    def test_cant_drop_on_occupied_tile(self, examine, game):
        """Can't drop an item where one already exists."""
        examine.obstacles.clear()
        pos = (examine.player_col, examine.player_row)
        examine.ground_items[pos] = {"item": "Stones", "gold": 0}
        game.party.shared_inventory.clear()
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        examine._confirm_drop()
        # Should not have been dropped — item still in inventory
        assert game.party.inv_count("Torch") == 1
        assert examine.ground_items[pos]["item"] == "Stones"
        assert "already" in examine.drop_message.lower()

    def test_cant_drop_on_obstacle(self, examine, game):
        """Can't drop an item on an obstacle tile."""
        pos = (examine.player_col, examine.player_row)
        examine.obstacles[pos] = "tree"
        examine.ground_items.clear()
        game.party.shared_inventory.clear()
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        examine._confirm_drop()
        assert game.party.inv_count("Torch") == 1
        assert pos not in examine.ground_items

    def test_drop_deduplicates_inventory(self, examine, game):
        """Drop list should show unique item names, not duplicates."""
        game.party.shared_inventory.clear()
        game.party.inv_add("Stones")
        game.party.inv_add("Stones")
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        # Should have 2 unique items (Stones, Torch), not 3
        assert len(examine.drop_items) == 2
        assert "Stones" in examine.drop_items
        assert "Torch" in examine.drop_items

    def test_movement_blocked_in_drop_mode(self, examine, game):
        """Arrow keys shouldn't move the player during drop mode."""
        examine.obstacles.clear()
        game.party.inv_add("Torch")
        examine._enter_drop_mode()
        start_col = examine.player_col
        start_row = examine.player_row
        examine.handle_input([make_event(pygame.K_RIGHT)], [0] * 512)
        # Player shouldn't move (RIGHT is consumed by drop mode)
        assert examine.player_col == start_col
        assert examine.player_row == start_row

    def test_default_party_has_items_for_drop(self, game):
        """A fresh game should have shared inventory items available to drop."""
        # Verify the default party has items in shared_inventory
        assert len(game.party.shared_inventory) > 0, \
            "Default party should have items in shared_inventory"
        names = game.party.inv_names()
        assert len(names) > 0, "inv_names() should return items"
        assert "Rock" in names, "Default inventory should include Rock"

        # Enter examine and verify drop mode works
        game.change_state("examine")
        examine = game.states["examine"]
        examine.handle_input([make_event(pygame.K_l)], [0] * 512)
        assert examine.drop_mode is True, \
            "Drop mode should activate with items in inventory"
        assert len(examine.drop_items) > 0, \
            "Drop list should contain items"
        assert "Rock" in examine.drop_items, \
            "Drop list should include Rock"
