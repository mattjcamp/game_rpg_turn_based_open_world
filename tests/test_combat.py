"""
Combat system tests — covers initialization, movement, melee, ranged,
turn flow, victory, defeat, and the loot phase.
"""

import pytest
from tests.conftest import make_event, tick, send_key


# ── Imports (safe because conftest installed the pygame mock) ────────
from src.states.combat import (
    PHASE_PLAYER, PHASE_MONSTER, PHASE_MELEE_ANIM, PHASE_PROJECTILE,
    PHASE_VICTORY, PHASE_DEFEAT, PHASE_LOOT, PHASE_SMITE,
    ACTION_SMITE, ACTION_LEAVE_ENCOUNTER,
    ARENA_COLS, ARENA_ROWS,
)
import pygame


# ====================================================================
#  Initialization
# ====================================================================

class TestCombatInit:
    def test_fighters_created(self, combat):
        assert len(combat.fighters) == 4

    def test_phase_is_player(self, combat):
        assert combat.phase == PHASE_PLAYER

    def test_fighter_positions_assigned(self, combat):
        for f in combat.fighters:
            pos = combat.fighter_positions.get(f)
            assert pos is not None, f"{f.name} has no position"
            col, row = pos
            assert 1 <= col < ARENA_COLS - 1
            assert 1 <= row < ARENA_ROWS - 1

    def test_monster_positions_assigned(self, combat):
        for m in combat.monsters:
            pos = combat.monster_positions.get(m)
            assert pos is not None, f"{m.name} has no position"

    def test_multi_monster_positions(self, combat_multi):
        assert len(combat_multi.monsters) == 3
        positions = set()
        for m in combat_multi.monsters:
            pos = combat_multi.monster_positions.get(m)
            assert pos is not None
            positions.add(pos)
        # All monsters should be at distinct positions
        assert len(positions) == 3


# ====================================================================
#  Movement
# ====================================================================

class TestMovement:
    def test_wasd_moves_fighter(self, combat):
        f = combat.active_fighter
        # Place in a safe open area
        combat.fighter_positions[f] = (8, 10)
        combat.moves_remaining = 5
        send_key(combat, pygame.K_d)
        assert combat.fighter_positions[f] == (9, 10)

    def test_cannot_walk_through_wall(self, combat):
        f = combat.active_fighter
        combat.fighter_positions[f] = (1, 5)
        combat.moves_remaining = 5
        send_key(combat, pygame.K_a)  # move left into wall col 0
        assert combat.fighter_positions[f] == (1, 5)  # didn't move

    def test_cannot_walk_onto_ally(self, combat):
        f0 = combat.fighters[0]
        f1 = combat.fighters[1]
        combat.fighter_positions[f0] = (5, 10)
        combat.fighter_positions[f1] = (6, 10)
        combat.active_idx = 0
        combat.moves_remaining = 5
        send_key(combat, pygame.K_d)  # try to walk into f1
        assert combat.fighter_positions[f0] == (5, 10)  # blocked


# ====================================================================
#  Melee (bump attack)
# ====================================================================

class TestMelee:
    def test_bump_triggers_melee_anim(self, combat):
        f = combat.active_fighter
        m = combat.monsters[0]
        mc, mr = combat.monster_positions[m]
        combat.fighter_positions[f] = (mc - 1, mr)
        combat.moves_remaining = 3
        send_key(combat, pygame.K_d)  # bump into monster
        assert combat.phase == PHASE_MELEE_ANIM

    def test_melee_anim_resolves(self, combat):
        f = combat.active_fighter
        m = combat.monsters[0]
        mc, mr = combat.monster_positions[m]
        combat.fighter_positions[f] = (mc - 1, mr)
        combat.moves_remaining = 3
        send_key(combat, pygame.K_d)
        assert combat.phase == PHASE_MELEE_ANIM
        # Tick until animation finishes
        tick(combat, dt=0.05, steps=30)
        assert combat.phase != PHASE_MELEE_ANIM


# ====================================================================
#  Victory flow
# ====================================================================

class TestVictory:
    def test_killing_monster_triggers_victory(self, combat):
        """Kill 1-HP monster → PHASE_VICTORY."""
        f = combat.active_fighter
        m = combat.monsters[0]
        assert m.hp == 1
        mc, mr = combat.monster_positions[m]
        combat.fighter_positions[f] = (mc - 1, mr)
        combat.moves_remaining = 3
        # Bump attack — monster has 1 HP so any hit kills it
        # We may need multiple attempts if attack misses
        for _ in range(20):
            if combat.phase in (PHASE_VICTORY, PHASE_LOOT):
                break
            if combat.phase == PHASE_PLAYER:
                f = combat.active_fighter
                if f:
                    combat.fighter_positions[f] = (mc - 1, mr)
                    combat.moves_remaining = 3
                    send_key(combat, pygame.K_d)
            tick(combat, dt=0.1, steps=5)
        assert combat.phase in (PHASE_VICTORY, PHASE_LOOT)

    def test_victory_transitions_to_loot(self, combat):
        """After PHASE_VICTORY timer expires, should enter PHASE_LOOT."""
        # Force victory directly
        combat._trigger_victory()
        assert combat.phase == PHASE_VICTORY
        # Tick until phase advances
        tick(combat, dt=0.1, steps=30)
        assert combat.phase == PHASE_LOOT

    def test_smite_all_kills_all_monsters(self, combat_multi):
        """Smite All debug action kills everything."""
        for m in combat_multi.monsters:
            assert m.is_alive()
        # Trigger smite via _confirm_action with ACTION_SMITE selected
        combat_multi.phase = "player"
        combat_multi.menu_actions = [(ACTION_SMITE, "\u26a1 Smite All")]
        combat_multi.selected_action = 0
        combat_multi._confirm_action()
        # Let flash animate
        tick(combat_multi, dt=0.1, steps=20)
        for m in combat_multi.monsters:
            assert not m.is_alive()

    def test_pending_xp_set_on_victory(self, combat, game):
        """Pending combat rewards should include XP."""
        combat._trigger_victory()
        rewards = game.pending_combat_rewards
        assert rewards is not None
        assert rewards["xp"] > 0
        # Gold should be 0 (picked up in loot phase now)
        assert rewards["gold"] == 0

    def test_flee_skips_loot_phase(self, combat):
        """Fleeing should NOT enter loot phase."""
        combat._fled = True
        combat.phase = PHASE_VICTORY
        combat.phase_timer = 100
        tick(combat, dt=0.2, steps=5)
        # Should have called _end_combat, not _enter_loot_phase
        assert combat.phase != PHASE_LOOT


# ====================================================================
#  Loot phase
# ====================================================================

class TestLootPhase:
    def _enter_loot(self, combat):
        """Helper: force into loot phase."""
        # Kill all monsters
        for m in combat.monsters:
            m.hp = 0
        combat._trigger_victory()
        # Advance past victory timer
        tick(combat, dt=0.1, steps=30)
        assert combat.phase == PHASE_LOOT
        return combat

    def test_loot_phase_entered(self, combat):
        self._enter_loot(combat)
        assert combat.phase == PHASE_LOOT

    def test_looter_is_alive_fighter(self, combat):
        self._enter_loot(combat)
        assert combat.looter_fighter is not None
        assert combat.looter_fighter.is_alive()
        assert combat.looter_fighter in combat.fighters

    def test_ground_items_generated(self, combat):
        self._enter_loot(combat)
        assert len(combat.ground_items) > 0

    def test_ground_items_on_separate_tiles(self, combat_multi):
        """Each loot drop should be on its own tile."""
        for m in combat_multi.monsters:
            m.hp = 0
        combat_multi._trigger_victory()
        tick(combat_multi, dt=0.1, steps=30)
        positions = list(combat_multi.ground_items.keys())
        assert len(positions) == len(set(positions)), "Duplicate positions found!"

    def test_looter_free_movement(self, combat):
        self._enter_loot(combat)
        f = combat.looter_fighter
        combat.fighter_positions[f] = (8, 10)
        # Move several times — should not run out of moves
        for _ in range(5):
            send_key(combat, pygame.K_d)
        assert combat.fighter_positions[f] == (13, 10)
        assert combat.phase == PHASE_LOOT  # still in loot phase

    def test_looter_picks_up_item(self, combat, game):
        self._enter_loot(combat)
        f = combat.looter_fighter
        # Place an item adjacent to the looter
        combat.fighter_positions[f] = (8, 10)
        combat.ground_items[(9, 10)] = {"item": "Torch", "gold": 0}
        initial_items = len(game.party.shared_inventory)
        send_key(combat, pygame.K_d)  # walk onto item
        assert (9, 10) not in combat.ground_items  # picked up
        assert len(game.party.shared_inventory) > initial_items or \
            any("Torch" in str(s) for s in game.party.shared_inventory)

    def test_looter_picks_up_gold(self, combat, game):
        self._enter_loot(combat)
        f = combat.looter_fighter
        combat.fighter_positions[f] = (8, 10)
        combat.ground_items[(9, 10)] = {"item": None, "gold": 50}
        gold_before = game.party.gold
        send_key(combat, pygame.K_d)
        assert game.party.gold == gold_before + 50
        assert (9, 10) not in combat.ground_items

    def test_leave_encounter_ends_combat(self, combat, game):
        self._enter_loot(combat)
        assert combat.menu_actions[0][0] == ACTION_LEAVE_ENCOUNTER
        combat.selected_action = 0
        send_key(combat, pygame.K_RETURN)
        # Combat should have ended — game state changed
        assert game.current_state != game.states["combat"] or combat.phase != PHASE_LOOT

    def test_pickup_logged_to_game_log(self, combat, game):
        self._enter_loot(combat)
        f = combat.looter_fighter
        combat.fighter_positions[f] = (8, 10)
        combat.ground_items[(9, 10)] = {"item": "Dagger", "gold": 0}
        log_len_before = len(game.game_log)
        send_key(combat, pygame.K_d)
        assert len(game.game_log) > log_len_before
        assert "Dagger" in game.game_log[-1]

    def test_menu_only_has_leave_encounter(self, combat):
        self._enter_loot(combat)
        assert len(combat.menu_actions) == 1
        assert combat.menu_actions[0][0] == ACTION_LEAVE_ENCOUNTER


# ====================================================================
#  Loot generation
# ====================================================================

class TestLootGeneration:
    def test_roll_loot_item_returns_string_or_none(self, combat):
        results = set()
        for _ in range(100):
            item = combat._roll_loot_item()
            results.add(type(item))
        # Should return str or None
        assert results <= {str, type(None)}

    def test_generate_ground_loot_places_gold(self, combat):
        for m in combat.monsters:
            m.hp = 0
        combat._generate_ground_loot(100)
        gold_tiles = [loot for loot in combat.ground_items.values()
                      if loot.get("gold", 0) > 0]
        assert len(gold_tiles) >= 1
        assert gold_tiles[0]["gold"] == 100

    def test_no_items_on_walls(self, combat):
        for m in combat.monsters:
            m.hp = 0
        combat._generate_ground_loot(50)
        for (col, row) in combat.ground_items:
            assert not combat._is_arena_wall(col, row), \
                f"Item placed on wall at ({col}, {row})"


# ====================================================================
#  Draw doesn't crash
# ====================================================================

class TestDraw:
    def test_draw_player_phase(self, combat, game):
        combat.draw(game.renderer)  # should not raise

    def test_draw_loot_phase(self, combat, game):
        for m in combat.monsters:
            m.hp = 0
        combat._trigger_victory()
        tick(combat, dt=0.1, steps=30)
        assert combat.phase == PHASE_LOOT
        combat.draw(game.renderer)  # should not raise

    def test_draw_victory_phase(self, combat, game):
        combat._trigger_victory()
        combat.draw(game.renderer)  # should not raise
