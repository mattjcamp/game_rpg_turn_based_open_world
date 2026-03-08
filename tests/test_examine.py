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

    def test_sets_party_member_name(self, examine, game):
        alive = [m for m in game.party.members if m.is_alive()]
        assert examine.party_member_name == alive[0].name

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
        from src.states.examine import EXAMINE_LOOT
        from src.party import ITEM_INFO
        for tile_type, table in EXAMINE_LOOT.items():
            for item_name, weight in table:
                assert item_name in ITEM_INFO, \
                    f"{item_name} not found in ITEM_INFO (tile {tile_type})"
                assert weight > 0

    def test_default_fallback(self):
        """Unmapped tile types fall back to grass loot."""
        from src.states.examine import EXAMINE_LOOT, _DEFAULT_LOOT
        from src.settings import TILE_GRASS
        assert _DEFAULT_LOOT is EXAMINE_LOOT[TILE_GRASS]


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
