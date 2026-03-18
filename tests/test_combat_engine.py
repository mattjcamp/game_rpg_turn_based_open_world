"""
Tests for src/combat_engine.py — dice rolling and attack resolution.
"""
import pytest
from src.combat_engine import (
    roll_dice, roll_d20, get_modifier, roll_initiative,
    roll_attack, roll_damage, format_modifier,
)


# ── Dice rolling ───────────────────────────────────────────────────


class TestDiceRolling:

    def test_roll_dice_range(self):
        for _ in range(100):
            result = roll_dice(2, 6)
            assert 2 <= result <= 12

    def test_roll_d20_range(self):
        for _ in range(100):
            result = roll_d20()
            assert 1 <= result <= 20

    def test_roll_dice_single(self):
        for _ in range(50):
            assert 1 <= roll_dice(1, 4) <= 4


# ── Ability modifier ───────────────────────────────────────────────


class TestModifier:

    def test_modifier_10_is_zero(self):
        assert get_modifier(10) == 0

    def test_modifier_below_10(self):
        assert get_modifier(8) == -1
        assert get_modifier(6) == -2

    def test_modifier_above_10(self):
        assert get_modifier(14) == 2
        assert get_modifier(18) == 4

    def test_format_positive(self):
        assert format_modifier(3) == "+3"

    def test_format_negative(self):
        assert format_modifier(-2) == "-2"

    def test_format_zero(self):
        assert format_modifier(0) == "+0"


# ── Initiative ─────────────────────────────────────────────────────


class TestInitiative:

    def test_initiative_returns_tuple(self):
        total, raw_roll = roll_initiative(2)
        assert isinstance(total, int)
        assert isinstance(raw_roll, int)
        assert total == raw_roll + 2

    def test_initiative_range(self):
        for _ in range(100):
            total, raw = roll_initiative(0)
            assert 1 <= raw <= 20
            assert total == raw


# ── Attack resolution ──────────────────────────────────────────────


class TestAttack:

    def test_attack_returns_four_values(self):
        hit, roll, total, crit = roll_attack(5, 15)
        assert isinstance(hit, bool)
        assert isinstance(roll, int)
        assert isinstance(total, int)
        assert isinstance(crit, bool)

    def test_natural_1_always_misses(self):
        """Simulate enough rolls to get a nat-1 (statistically guaranteed
        in 100 tries with near certainty)."""
        import random
        random.seed(42)  # deterministic
        found_nat1 = False
        for _ in range(200):
            hit, roll, total, crit = roll_attack(100, 1)
            if roll == 1:
                assert hit is False
                assert crit is False
                found_nat1 = True
                break
        assert found_nat1, "Did not observe nat-1 in 200 rolls"

    def test_natural_20_always_hits(self):
        import random
        random.seed(0)
        found_nat20 = False
        for _ in range(200):
            hit, roll, total, crit = roll_attack(-100, 999)
            if roll == 20:
                assert hit is True
                assert crit is True
                found_nat20 = True
                break
        assert found_nat20, "Did not observe nat-20 in 200 rolls"


# ── Damage rolling ─────────────────────────────────────────────────


class TestDamage:

    def test_damage_minimum_is_one(self):
        """Even with 0 bonus, minimum damage is 1."""
        for _ in range(50):
            dmg = roll_damage(1, 4, 0)
            assert dmg >= 1

    def test_critical_doubles_dice(self):
        import random
        random.seed(99)
        # With fixed seed, critical should generally be higher
        normal_rolls = [roll_damage(1, 6, 0) for _ in range(50)]
        random.seed(99)
        crit_rolls = [roll_damage(1, 6, 0, critical=True) for _ in range(50)]
        # Critical rolls 2d6 instead of 1d6 → higher average
        assert sum(crit_rolls) > sum(normal_rolls)

    def test_bonus_added(self):
        import random
        random.seed(42)
        dmg_no_bonus = roll_damage(1, 6, 0)
        random.seed(42)
        dmg_with_bonus = roll_damage(1, 6, 5)
        assert dmg_with_bonus == dmg_no_bonus + 5
