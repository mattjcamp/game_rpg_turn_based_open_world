"""
Tests for the refactored combat helpers, buff system, effect phase table,
and Game accessor methods.

These cover the code introduced in refactoring items 1–6.
"""

import pytest
from unittest.mock import patch


# =====================================================================
# 1. _tick_buff_dict
# =====================================================================

class TestTickBuffDict:
    """Test the generic buff tick helper on CombatState."""

    def test_dict_of_dicts_decrements(self, combat):
        """Dict-of-dicts format: turns_left is decremented each tick."""
        entity_a = combat.fighters[0]
        combat.bless_buffs[entity_a] = {"attack_bonus": 2, "turns_left": 3}
        expired = []
        combat._tick_buff_dict(combat.bless_buffs, lambda e: expired.append(e))
        assert combat.bless_buffs[entity_a]["turns_left"] == 2
        assert expired == []

    def test_dict_of_dicts_expires(self, combat):
        """Dict-of-dicts: entry is removed and on_expire called at 0."""
        entity_a = combat.fighters[0]
        combat.bless_buffs[entity_a] = {"attack_bonus": 2, "turns_left": 1}
        expired = []
        combat._tick_buff_dict(combat.bless_buffs, lambda e: expired.append(e))
        assert entity_a not in combat.bless_buffs
        assert entity_a in expired

    def test_dict_of_ints_decrements(self, combat):
        """Dict-of-ints format: bare integer is decremented each tick."""
        monster = combat.monsters[0]
        combat.sleep_buffs[monster] = 3
        expired = []
        combat._tick_buff_dict(combat.sleep_buffs, lambda e: expired.append(e))
        assert combat.sleep_buffs[monster] == 2
        assert expired == []

    def test_dict_of_ints_expires(self, combat):
        """Dict-of-ints: entry removed and callback fires at 0."""
        monster = combat.monsters[0]
        combat.sleep_buffs[monster] = 1
        expired = []
        combat._tick_buff_dict(combat.sleep_buffs, lambda e: expired.append(e))
        assert monster not in combat.sleep_buffs
        assert monster in expired

    def test_skip_parameter(self, combat):
        """Entities in skip set are not decremented."""
        a = combat.fighters[0]
        b = combat.monsters[0]
        combat.sleep_buffs[a] = 2
        combat.sleep_buffs[b] = 2
        expired = []
        combat._tick_buff_dict(combat.sleep_buffs, lambda e: expired.append(e),
                               skip={a})
        # a should be untouched, b should be decremented
        assert combat.sleep_buffs[a] == 2
        assert combat.sleep_buffs[b] == 1

    def test_multiple_expire_same_tick(self, combat):
        """Multiple buffs can expire in the same tick."""
        a = combat.fighters[0]
        b = combat.monsters[0]
        combat.sleep_buffs[a] = 1
        combat.sleep_buffs[b] = 1
        expired = []
        combat._tick_buff_dict(combat.sleep_buffs, lambda e: expired.append(e))
        assert len(expired) == 2
        assert len(combat.sleep_buffs) == 0

    def test_empty_dict_no_crash(self, combat):
        """Ticking an empty dict is a no-op."""
        expired = []
        combat._tick_buff_dict({}, lambda e: expired.append(e))
        assert expired == []


# =====================================================================
# 2. _roll_attack_with_buffs & _apply_damage
# =====================================================================

class TestRollAttackWithBuffs:
    """Test the shared attack-roll helper."""

    def test_clears_defending_flag(self, combat):
        """Attacking always resets the defending flag."""
        f = combat.active_fighter
        combat.defending[f] = True
        target = combat.monsters[0]
        combat._roll_attack_with_buffs(f, target)
        assert combat.defending[f] is False

    def test_bless_increases_attack(self, combat):
        """With a bless buff, the attack bonus should be higher."""
        f = combat.active_fighter
        target = combat.monsters[0]
        # Patch roll_attack to capture the attack_bonus passed in
        captured = {}
        original_roll = __import__("src.combat_engine", fromlist=["roll_attack"]).roll_attack

        def spy_roll(atk_bonus, ac):
            captured["atk_bonus"] = atk_bonus
            return original_roll(atk_bonus, ac)

        # Roll without bless
        with patch("src.states.combat.roll_attack", side_effect=spy_roll):
            combat._roll_attack_with_buffs(f, target)
        base_bonus = captured["atk_bonus"]

        # Roll with bless
        combat.bless_buffs[f] = {"attack_bonus": 5, "turns_left": 3}
        with patch("src.states.combat.roll_attack", side_effect=spy_roll):
            combat._roll_attack_with_buffs(f, target)
        blessed_bonus = captured["atk_bonus"]

        assert blessed_bonus == base_bonus + 5

    def test_curse_reduces_target_ac(self, combat):
        """With a curse debuff on target, effective AC should be lower."""
        f = combat.active_fighter
        target = combat.monsters[0]
        captured = {}

        def spy_roll(atk_bonus, ac):
            captured["ac"] = ac
            return True, 15, 15, False

        # Without curse
        with patch("src.states.combat.roll_attack", side_effect=spy_roll):
            combat._roll_attack_with_buffs(f, target)
        base_ac = captured["ac"]

        # With curse
        combat.curse_buffs[target] = {"ac_penalty": 3, "attack_penalty": 2,
                                      "turns_left": 3}
        with patch("src.states.combat.roll_attack", side_effect=spy_roll):
            combat._roll_attack_with_buffs(f, target)
        cursed_ac = captured["ac"]

        assert cursed_ac == base_ac - 3

    def test_critical_hit_logged(self, combat):
        """A natural 20 logs a CRITICAL HIT."""
        f = combat.active_fighter
        target = combat.monsters[0]
        with patch("src.states.combat.roll_attack",
                   return_value=(True, 20, 25, True)):
            hit, crit = combat._roll_attack_with_buffs(f, target)
        assert hit is True
        assert crit is True
        assert any("CRITICAL" in msg for msg in combat.combat_log)

    def test_miss_logged(self, combat):
        """A miss logs 'Miss!'."""
        f = combat.active_fighter
        target = combat.monsters[0]
        with patch("src.states.combat.roll_attack",
                   return_value=(False, 3, 5, False)):
            hit, crit = combat._roll_attack_with_buffs(f, target)
        assert hit is False
        assert crit is False
        assert any("Miss" in msg for msg in combat.combat_log)


class TestApplyDamage:
    """Test the shared damage-application helper."""

    def test_basic_damage_reduces_hp(self, combat):
        """Target HP should decrease by the rolled damage."""
        f = combat.active_fighter
        target = combat.monsters[0]
        target.hp = 20
        target.max_hp = 20
        with patch("src.states.combat.roll_damage", return_value=7):
            dmg, holy = combat._apply_damage(f, target, 1, 8, 0, False,
                                             "Sword")
        assert dmg == 7
        assert target.hp == 13
        assert holy is False

    def test_hp_clamped_to_zero(self, combat):
        """Damage cannot reduce HP below zero."""
        f = combat.active_fighter
        target = combat.monsters[0]
        target.hp = 3
        with patch("src.states.combat.roll_damage", return_value=10):
            combat._apply_damage(f, target, 1, 8, 0, False, "Sword")
        assert target.hp == 0

    def test_holy_smite_doubles_dice(self, combat):
        """Paladin vs undead should double the dice count."""
        f = combat.active_fighter
        f.char_class = "Paladin"
        target = combat.monsters[0]
        target.undead = True
        target.hp = 50
        target.max_hp = 50

        captured = {}
        def spy_roll_damage(dice_count, dice_sides, bonus, critical=False):
            captured["dice_count"] = dice_count
            return 10  # arbitrary

        with patch("src.states.combat.roll_damage",
                   side_effect=spy_roll_damage):
            dmg, holy = combat._apply_damage(f, target, 2, 6, 1, False,
                                             "Mace")
        assert holy is True
        assert captured["dice_count"] == 4  # 2 * 2 = 4

    def test_holy_smite_not_triggered_non_paladin(self, combat):
        """Non-paladin should not trigger Holy Smite even vs undead."""
        f = combat.active_fighter
        f.char_class = "Fighter"
        target = combat.monsters[0]
        target.undead = True
        target.hp = 50

        captured = {}
        def spy(dice_count, dice_sides, bonus, critical=False):
            captured["dice_count"] = dice_count
            return 5

        with patch("src.states.combat.roll_damage", side_effect=spy):
            dmg, holy = combat._apply_damage(f, target, 2, 6, 0, False,
                                             "Sword")
        assert holy is False
        assert captured["dice_count"] == 2  # no doubling

    def test_holy_smite_not_triggered_non_undead(self, combat):
        """Paladin vs non-undead should not trigger Holy Smite."""
        f = combat.active_fighter
        f.char_class = "Paladin"
        target = combat.monsters[0]
        target.undead = False
        target.hp = 50

        captured = {}
        def spy(dice_count, dice_sides, bonus, critical=False):
            captured["dice_count"] = dice_count
            return 5

        with patch("src.states.combat.roll_damage", side_effect=spy):
            dmg, holy = combat._apply_damage(f, target, 2, 6, 0, False,
                                             "Sword")
        assert holy is False
        assert captured["dice_count"] == 2

    def test_hit_effect_spawned(self, combat):
        """A HitEffect should be added to combat.hit_effects."""
        f = combat.active_fighter
        target = combat.monsters[0]
        target.hp = 20
        before = len(combat.hit_effects)
        with patch("src.states.combat.roll_damage", return_value=5):
            combat._apply_damage(f, target, 1, 6, 0, False, "Dagger")
        assert len(combat.hit_effects) == before + 1

    def test_holy_smite_log_message(self, combat):
        """Holy Smite should produce a specific log message."""
        f = combat.active_fighter
        f.char_class = "Paladin"
        target = combat.monsters[0]
        target.undead = True
        target.hp = 50
        with patch("src.states.combat.roll_damage", return_value=12):
            combat._apply_damage(f, target, 2, 6, 0, False, "Mace")
        assert any("HOLY SMITES" in msg for msg in combat.combat_log)


# =====================================================================
# 3. _build_effect_phase_table & effect ticking
# =====================================================================

class TestEffectPhaseTable:
    """Test the data-driven effect phase table."""

    def test_table_built_on_first_update(self, combat):
        """The phase table should be None initially and built after update."""
        assert combat._effect_phase_table is None
        combat.update(0.016)
        assert combat._effect_phase_table is not None

    def test_table_has_correct_entry_count(self, combat):
        """The table should contain exactly 15 phase entries."""
        combat.update(0.016)
        assert len(combat._effect_phase_table) == 15

    def test_table_entries_are_tuples_of_three(self, combat):
        """Each entry should be (phase_constant, attr_name, callback)."""
        combat.update(0.016)
        for entry in combat._effect_phase_table:
            assert len(entry) == 3
            phase, attr_name, callback = entry
            assert isinstance(phase, str)
            assert isinstance(attr_name, str)
            assert callable(callback)

    def test_table_attrs_exist_on_combat(self, combat):
        """Every attr_name in the table should be a valid attribute."""
        combat.update(0.016)
        for _, attr_name, _ in combat._effect_phase_table:
            assert hasattr(combat, attr_name), \
                f"CombatState missing attribute: {attr_name}"

    def test_table_not_rebuilt_on_second_update(self, combat):
        """The table should be built once and reused."""
        combat.update(0.016)
        table_ref = combat._effect_phase_table
        combat.update(0.016)
        assert combat._effect_phase_table is table_ref


class TestTickEffectList:
    """Test the static effect list ticker."""

    def test_updates_alive_effects(self):
        """Alive effects should have update() called."""
        from src.states.combat_effects import HealEffect
        fx = HealEffect(3, 3)
        initial_timer = fx.timer
        from src.states.combat import CombatState
        CombatState._tick_effect_list([fx], 0.1)
        assert fx.timer < initial_timer

    def test_dead_effects_not_updated(self):
        """Dead effects should be skipped."""
        from src.states.combat_effects import HealEffect
        fx = HealEffect(3, 3)
        fx.alive = False
        fx.timer = 0.5  # set a value we can check
        from src.states.combat import CombatState
        CombatState._tick_effect_list([fx], 0.1)
        assert fx.timer == 0.5  # unchanged


class TestTimerEffect:
    """Test the _TimerEffect base class."""

    def test_progress_starts_at_zero(self):
        from src.states.combat_effects import _TimerEffect
        fx = _TimerEffect()
        assert fx.progress == pytest.approx(0.0, abs=0.01)

    def test_progress_reaches_one(self):
        from src.states.combat_effects import _TimerEffect
        fx = _TimerEffect()
        fx.update(fx.DURATION + 0.1)
        assert fx.progress == pytest.approx(1.0)
        assert fx.alive is False

    def test_progress_mid_animation(self):
        from src.states.combat_effects import _TimerEffect
        fx = _TimerEffect()
        fx.update(fx.DURATION / 2)
        assert 0.4 < fx.progress < 0.6


class TestTravelEffect:
    """Test the _TravelEffect base class."""

    def test_starts_at_origin(self):
        from src.states.combat_effects import _TravelEffect
        fx = _TravelEffect(0, 0, 10, 0)
        assert fx.progress == pytest.approx(0.0)
        assert fx.alive is True

    def test_arrives_at_destination(self):
        from src.states.combat_effects import _TravelEffect
        fx = _TravelEffect(0, 0, 1, 0)
        # Advance enough time to arrive (1 tile at PROJECTILE_SPEED)
        for _ in range(100):
            fx.update(0.05)
        assert fx.alive is False


# =====================================================================
# 4. Game accessor methods
# =====================================================================

@pytest.fixture
def started_game(game):
    """A Game with new-game state initialised (quest, keys, etc.)."""
    game.quest = None
    game.house_quest = None
    game.visited_dungeons = set()
    game.key_dungeons = {}
    game.keys_inserted = 0
    game.darkness_active = False
    game._gnome_quest_accepted = False
    return game


class TestGameAccessors:
    """Test the Game accessor methods for encapsulation."""

    # ── Dungeon visited ──

    def test_dungeon_not_visited_initially(self, started_game):
        assert started_game.is_dungeon_visited(5, 5) is False

    def test_mark_and_check_dungeon_visited(self, started_game):
        started_game.mark_dungeon_visited(5, 5)
        assert started_game.is_dungeon_visited(5, 5) is True

    def test_different_dungeon_not_visited(self, started_game):
        started_game.mark_dungeon_visited(5, 5)
        assert started_game.is_dungeon_visited(6, 6) is False

    # ── Key dungeons ──

    def test_get_key_dungeons_returns_dict(self, started_game):
        result = started_game.get_key_dungeons()
        assert isinstance(result, dict)

    def test_get_key_dungeon_missing(self, started_game):
        assert started_game.get_key_dungeon(99, 99) is None

    def test_get_key_dungeon_existing(self, started_game):
        started_game.key_dungeons[(1, 2)] = {"name": "Test Dungeon"}
        result = started_game.get_key_dungeon(1, 2)
        assert result is not None
        assert result["name"] == "Test Dungeon"

    # ── Keys inserted ──

    def test_keys_inserted_starts_at_zero(self, started_game):
        assert started_game.get_keys_inserted() == 0

    def test_insert_key_increments(self, started_game):
        count = started_game.insert_key()
        assert count == 1
        assert started_game.get_keys_inserted() == 1

    def test_insert_key_twice(self, started_game):
        started_game.insert_key()
        count = started_game.insert_key()
        assert count == 2

    # ── Total keys ──

    def test_total_keys_matches_key_dungeons(self, started_game):
        assert started_game.get_total_keys() == len(started_game.key_dungeons)

    # ── Darkness ──

    def test_set_darkness_on(self, started_game):
        started_game.set_darkness(True)
        assert started_game.darkness_active is True

    def test_set_darkness_off(self, started_game):
        started_game.darkness_active = True
        started_game.set_darkness(False)
        assert started_game.darkness_active is False

    # ── Quest ──

    def test_get_quest_initially_none(self, started_game):
        assert started_game.get_quest() is None

    def test_set_and_get_quest(self, started_game):
        started_game.set_quest({"name": "Find the Gem", "status": "active"})
        q = started_game.get_quest()
        assert q["name"] == "Find the Gem"

    def test_clear_quest(self, started_game):
        started_game.set_quest({"name": "Test"})
        started_game.set_quest(None)
        assert started_game.get_quest() is None

    # ── House quest ──

    def test_get_house_quest_initially_none(self, started_game):
        assert started_game.get_house_quest() is None

    def test_set_and_get_house_quest(self, started_game):
        started_game.set_house_quest({"name": "House Quest"})
        assert started_game.get_house_quest()["name"] == "House Quest"

    # ── Combat rewards ──

    def test_set_and_consume_combat_rewards(self, game):
        game.set_combat_rewards({"xp": 100, "gold": 50})
        rewards = game.consume_combat_rewards()
        assert rewards == {"xp": 100, "gold": 50}
        assert game.pending_combat_rewards is None

    def test_consume_with_no_rewards(self, game):
        game.pending_combat_rewards = None
        result = game.consume_combat_rewards()
        assert result is None

    def test_consume_clears_rewards(self, game):
        game.set_combat_rewards({"xp": 10, "gold": 0})
        game.consume_combat_rewards()
        second = game.consume_combat_rewards()
        assert second is None

    # ── Gnome quest ──

    def test_set_gnome_quest_accepted(self, started_game):
        started_game.set_gnome_quest_accepted()
        assert started_game._gnome_quest_accepted is True
