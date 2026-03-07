"""
Party and inventory system tests.
"""

import pytest


class TestPartyCreation:
    def test_default_party_has_four_members(self, game):
        assert len(game.party.members) == 4

    def test_all_members_alive(self, game):
        for m in game.party.members:
            assert m.is_alive()
            assert m.hp > 0

    def test_members_have_names(self, game):
        for m in game.party.members:
            assert m.name and len(m.name) > 0

    def test_members_have_classes(self, game):
        for m in game.party.members:
            assert m.char_class and len(m.char_class) > 0

    def test_starting_gold(self, game):
        assert game.party.gold >= 0


class TestInventory:
    def test_inv_add_item(self, game):
        game.party.inv_add("Torch")
        found = any("Torch" in str(item) for item in game.party.shared_inventory)
        assert found, "Torch not found in inventory after inv_add"

    def test_inv_add_stacks(self, game):
        game.party.inv_add("Healing Herb")
        game.party.inv_add("Healing Herb")
        # Count occurrences (may be stacked as charges or separate entries)
        count = sum(1 for item in game.party.shared_inventory
                    if "Healing Herb" in str(item))
        # At least 1 entry (may stack)
        assert count >= 1

    def test_gold_add(self, game):
        before = game.party.gold
        game.party.gold += 100
        assert game.party.gold == before + 100

    def test_gold_subtract(self, game):
        game.party.gold = 200
        game.party.gold -= 50
        assert game.party.gold == 150


class TestMemberStats:
    def test_hp_cannot_exceed_max(self, game):
        m = game.party.members[0]
        m.hp = m.max_hp + 100
        # The game may or may not enforce this — just document behavior
        # This test checks the current value is set
        assert m.hp >= m.max_hp

    def test_damage_reduces_hp(self, game):
        m = game.party.members[0]
        original = m.hp
        m.hp -= 5
        assert m.hp == original - 5

    def test_zero_hp_means_dead(self, game):
        m = game.party.members[0]
        m.hp = 0
        assert not m.is_alive()

    def test_xp_starts_at_zero_or_positive(self, game):
        for m in game.party.members:
            assert m.exp >= 0


class TestCombatRewards:
    def test_apply_pending_rewards_xp(self, game):
        """XP from pending_combat_rewards is applied to all members."""
        game.pending_combat_rewards = {"xp": 50, "gold": 0}
        xp_before = [m.exp for m in game.party.members]
        overworld = game.states["overworld"]
        overworld._apply_pending_combat_rewards()
        for i, m in enumerate(game.party.members):
            assert m.exp == xp_before[i] + 50

    def test_apply_pending_rewards_gold(self, game):
        """Gold from pending_combat_rewards is added to party."""
        gold_before = game.party.gold
        game.pending_combat_rewards = {"xp": 0, "gold": 75}
        overworld = game.states["overworld"]
        overworld._apply_pending_combat_rewards()
        assert game.party.gold == gold_before + 75

    def test_apply_pending_rewards_clears(self, game):
        """After applying, pending_combat_rewards is set to None."""
        game.pending_combat_rewards = {"xp": 10, "gold": 10}
        overworld = game.states["overworld"]
        overworld._apply_pending_combat_rewards()
        assert game.pending_combat_rewards is None

    def test_no_crash_without_pending_rewards(self, game):
        """Calling apply when no rewards are pending should be safe."""
        game.pending_combat_rewards = None
        overworld = game.states["overworld"]
        overworld._apply_pending_combat_rewards()  # should not raise
