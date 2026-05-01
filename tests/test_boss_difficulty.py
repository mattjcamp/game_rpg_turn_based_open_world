"""Tests for the new ``"boss"`` per-monster difficulty tier.

A monster tagged ``difficulty: "boss"`` is unique — it must be filtered
out of every random spawn pool (random encounters in dungeons, random
overworld / town encounters, and weighted spawn-table draws) so the
only time the player meets it is via an explicit quest placement.
This was driven by a player report that the climactic Dragon fight was
deflated by random Dragon encounters earlier in the world.

Coverage here:
  * ``DIFFICULTY_TIERS`` includes ``"boss"`` so the monster editor
    offers it as a choice; ``DIFFICULTY_PROFILES`` does NOT (boss is
    not a whole-dungeon difficulty).
  * ``create_random_monster`` skips boss-tagged monsters even when
    they're on the active spawn table.
  * ``create_encounter`` strips encounters containing a boss across
    every difficulty filter setting (None / easy / hard / etc.).
  * Non-boss monsters retain their existing difficulty behaviour.
"""

import random

import pytest

from src import monster as monster_mod
from src.dungeon_generator import (
    DIFFICULTY_TIERS, DIFFICULTY_PROFILES, DIFFICULTY_BOSS,
)


# ── Tier constant integrity ────────────────────────────────────────


class TestTierConstants:
    def test_boss_is_in_tiers(self):
        assert "boss" in DIFFICULTY_TIERS, (
            "Boss tier must surface in the monster editor's "
            "difficulty dropdown.")

    def test_boss_is_not_a_dungeon_profile(self):
        # A whole dungeon's difficulty selector cannot be "boss" —
        # boss is a per-monster designation only. If this fires, the
        # dungeon-level difficulty dropdown would let an author build
        # an entire "boss" dungeon, which has no defined room counts /
        # encounter rates.
        assert "boss" not in DIFFICULTY_PROFILES

    def test_easy_normal_hard_deadly_unchanged(self):
        for tier in ("easy", "normal", "hard", "deadly"):
            assert tier in DIFFICULTY_TIERS
            assert tier in DIFFICULTY_PROFILES

    def test_difficulty_boss_constant(self):
        assert DIFFICULTY_BOSS == "boss"


# ── Random monster spawning ────────────────────────────────────────


class TestCreateRandomMonsterSkipsBoss:
    def test_boss_excluded_from_weighted_pool(self, monkeypatch):
        # Build a tiny mock world: a spawn table containing a boss
        # and a regular monster, plus matching MONSTERS entries.
        monkeypatch.setattr(monster_mod, "MONSTERS", {
            "Slime": {"hp": 5, "spawn_weight": 1, "difficulty": "easy"},
            "Hargorn": {"hp": 999, "spawn_weight": 99,
                         "difficulty": "boss"},
        })
        monkeypatch.setattr(monster_mod, "SPAWN_TABLES", {
            "dungeon": ["Slime", "Hargorn"],
        })
        # Stub create_monster so we don't depend on full monster
        # construction — we just need the name back.
        monkeypatch.setattr(
            monster_mod, "create_monster",
            lambda name: type("M", (), {"name": name})())

        # Many draws: even with the boss carrying a 99x weight versus
        # the slime's 1x, every draw should still return Slime.
        for _ in range(100):
            mon = monster_mod.create_random_monster("dungeon")
            assert mon.name == "Slime", (
                "Boss monsters must never come out of the random "
                "spawn pool, even when their spawn_weight dominates.")


# ── Encounter pool filtering ───────────────────────────────────────


@pytest.fixture
def boss_encounters_world(monkeypatch):
    """Mock encounter pool: one regular encounter + one boss encounter."""
    monkeypatch.setattr(monster_mod, "MONSTERS", {
        "Goblin": {"hp": 10, "difficulty": "normal"},
        "Hargorn": {"hp": 999, "difficulty": "boss"},
    })
    monkeypatch.setattr(monster_mod, "ENCOUNTERS", {
        "dungeon": [
            {"name": "Goblin Pack", "monsters": ["Goblin", "Goblin"],
             "level": 1, "weight": 10, "terrain": "land"},
            {"name": "Lone Dragon", "monsters": ["Hargorn"],
             "level": 1, "weight": 1000, "terrain": "land"},
        ],
        "overworld": [
            {"name": "Goblin Pack", "monsters": ["Goblin"],
             "level": 1, "weight": 10, "terrain": "land"},
            {"name": "Lone Dragon", "monsters": ["Hargorn"],
             "level": 1, "weight": 1000, "terrain": "land"},
        ],
    })
    monkeypatch.setattr(
        monster_mod, "create_monster",
        lambda name: type("M", (), {"name": name})())


class TestCreateEncounterFiltersBoss:
    def test_dungeon_pool_strips_boss(self, boss_encounters_world):
        # Even with the boss encounter weighted 100x heavier than the
        # goblin one, every roll has to land on Goblin Pack. If it
        # doesn't, the boss leaked into the random pool.
        for _ in range(50):
            enc = monster_mod.create_encounter(area="dungeon")
            assert enc is not None
            assert enc["name"] == "Goblin Pack"

    def test_overworld_pool_strips_boss(self, boss_encounters_world):
        # Same check for overworld pools — the boss filter runs before
        # the dungeon-difficulty filter so it covers areas where no
        # tier filtering normally happens.
        for _ in range(50):
            enc = monster_mod.create_encounter(area="overworld")
            assert enc is not None
            assert enc["name"] == "Goblin Pack"

    def test_difficulty_filter_still_applies(
            self, boss_encounters_world):
        # The boss filter must not break the existing tier filter.
        # Goblin is "normal", so an "easy" pool with the boss removed
        # has no eligible encounters and create_encounter returns None.
        enc = monster_mod.create_encounter(
            area="dungeon", dungeon_difficulty="easy")
        assert enc is None

    def test_normal_difficulty_picks_goblin(
            self, boss_encounters_world):
        # A "normal" pool keeps the goblin encounter and still strips
        # the boss — the regression we're locking in is that bosses
        # don't leak through the existing filter when a tier is set.
        enc = monster_mod.create_encounter(
            area="dungeon", dungeon_difficulty="normal")
        assert enc is not None
        assert enc["name"] == "Goblin Pack"


# ── Live data: Dragon should now be a boss ─────────────────────────


class TestLiveDragonIsBoss:
    def test_dragon_difficulty_is_boss(self):
        """Migration check: data/monsters.json marks Dragon as boss
        so the climactic encounter at the end of The Dragon of
        Hargorn module is the only Dragon the player meets."""
        from src.monster import MONSTERS
        assert MONSTERS["Dragon"]["difficulty"] == "boss"
