"""
Game state transition tests — verifies state machine integrity.
"""

import pytest


class TestStateTransitions:
    def test_initial_state_exists(self, game):
        """Game should have states registered."""
        assert "overworld" in game.states
        assert "combat" in game.states
        assert "dungeon" in game.states
        assert "town" in game.states

    def test_change_to_overworld(self, game):
        game.change_state("overworld")
        assert game.current_state is game.states["overworld"]

    def test_change_to_combat_and_back(self, game):
        from src.monster import create_giant_rat
        monster = create_giant_rat()
        monster.col = 5
        monster.row = 5
        combat = game.states["combat"]
        combat.start_combat(game.party.members[0], monster,
                            source_state="overworld")
        game.change_state("combat")
        assert game.current_state is game.states["combat"]

    def test_combat_end_returns_to_source(self, game):
        from src.monster import create_giant_rat
        monster = create_giant_rat()
        monster.col = 5
        monster.row = 5
        combat = game.states["combat"]
        combat.start_combat(game.party.members[0], monster,
                            source_state="overworld")
        game.change_state("combat")
        combat._fled = True  # skip loot
        combat._end_combat(won=True)
        assert game.current_state is game.states["overworld"]


class TestGameLog:
    def test_log_starts_empty_or_with_entries(self, game):
        assert isinstance(game.game_log, list)

    def test_log_append(self, game):
        game.game_log.append("Test message")
        assert "Test message" in game.game_log

    def test_combat_victory_logs_message(self, game):
        from src.monster import create_giant_rat
        monster = create_giant_rat()
        monster.col = 5
        monster.row = 5
        combat = game.states["combat"]
        combat.start_combat(game.party.members[0], monster,
                            source_state="overworld")
        game.change_state("combat")
        # Force end combat
        combat._fled = True
        combat._end_combat(won=True)
        # Should have logged defeat message
        assert any("defeated" in entry.lower() or "fled" in entry.lower()
                    for entry in game.game_log)


class TestOverworld:
    def test_overworld_has_tile_map(self, game):
        assert game.tile_map is not None

    def test_overworld_enter_doesnt_crash(self, game):
        overworld = game.states["overworld"]
        overworld.enter()  # should not raise

    def test_overworld_update_doesnt_crash(self, game):
        game.change_state("overworld")
        overworld = game.states["overworld"]
        overworld.update(0.016)  # one frame at 60fps
