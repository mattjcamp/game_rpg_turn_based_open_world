"""
Tests for src/monster.py — monster creation, movement, and encounter generation.
"""
import pytest
from src.monster import (
    Monster, create_monster, create_random_monster,
    create_encounter, MONSTERS, SPAWN_TABLES,
)


# ── Monster data integrity ─────────────────────────────────────────


class TestMonsterData:

    def test_monsters_dict_loaded(self):
        assert isinstance(MONSTERS, dict)
        assert len(MONSTERS) > 0

    def test_every_monster_has_required_fields(self):
        required = {"hp", "ac", "attack_bonus"}
        for name, data in MONSTERS.items():
            for field in required:
                assert field in data, f"Monster '{name}' missing '{field}'"

    def test_spawn_tables_reference_valid_monsters(self):
        for table_name, pool in SPAWN_TABLES.items():
            for name in pool:
                assert name in MONSTERS, (
                    f"Spawn table '{table_name}' references unknown "
                    f"monster '{name}'")


# ── Monster creation ───────────────────────────────────────────────


class TestCreateMonster:

    def test_create_known_monster(self):
        name = list(MONSTERS.keys())[0]
        m = create_monster(name)
        assert isinstance(m, Monster)
        assert m.name == name
        assert m.hp > 0

    def test_create_unknown_monster_raises(self):
        with pytest.raises(ValueError, match="Unknown monster"):
            create_monster("Nonexistent Dragon XYZ")

    def test_monster_hp_matches_data(self):
        for name, data in list(MONSTERS.items())[:5]:
            m = create_monster(name)
            assert m.max_hp == data["hp"]
            assert m.hp == data["hp"]
            assert m.ac == data["ac"]

    def test_monster_is_alive_initially(self):
        m = create_monster(list(MONSTERS.keys())[0])
        assert m.is_alive() is True

    def test_monster_dead_at_zero_hp(self):
        m = create_monster(list(MONSTERS.keys())[0])
        m.hp = 0
        assert m.is_alive() is False

    def test_undead_flag(self):
        # Check that undead monsters have the flag set
        for name, data in MONSTERS.items():
            m = create_monster(name)
            assert m.undead == data.get("undead", False)


# ── Random monster creation ────────────────────────────────────────


class TestCreateRandomMonster:

    def test_returns_monster(self):
        m = create_random_monster()
        assert isinstance(m, Monster)
        assert m.is_alive()

    def test_from_specific_table(self):
        for table in SPAWN_TABLES:
            m = create_random_monster(table)
            assert isinstance(m, Monster)


# ── Monster movement ───────────────────────────────────────────────


class _FakeTileMap:
    """Minimal tile map stub for movement tests."""
    def __init__(self, width=10, height=10, blocked=None):
        self.width = width
        self.height = height
        self._blocked = blocked or set()

    def is_walkable(self, col, row):
        return (col, row) not in self._blocked

    def get_tile(self, col, row):
        return 0


class TestMonsterMovement:

    def test_move_toward_target(self):
        m = Monster("Test", hp=5, ac=10, attack_bonus=1)
        m.col, m.row = 3, 3
        tm = _FakeTileMap()
        m.try_move_toward(6, 3, tm, set())
        # Should move one step closer (col increases)
        assert m.col == 4

    def test_move_blocked_by_occupied(self):
        m = Monster("Test", hp=5, ac=10, attack_bonus=1)
        m.col, m.row = 3, 3
        tm = _FakeTileMap()
        # Block the only useful move
        occupied = {(4, 3), (3, 4), (2, 3), (3, 2)}
        m.try_move_toward(6, 3, tm, occupied)
        # Should stay put
        assert (m.col, m.row) == (3, 3)

    def test_dead_monster_does_not_move(self):
        m = Monster("Test", hp=0, ac=10, attack_bonus=1)
        m.col, m.row = 3, 3
        tm = _FakeTileMap()
        m.try_move_toward(6, 3, tm, set())
        assert (m.col, m.row) == (3, 3)

    def test_random_move_changes_position(self):
        m = Monster("Test", hp=5, ac=10, attack_bonus=1)
        m.col, m.row = 5, 5
        tm = _FakeTileMap()
        # Run many times — at least one should move
        moved = False
        for _ in range(20):
            m.col, m.row = 5, 5
            m.try_move_random(tm, set())
            if (m.col, m.row) != (5, 5):
                moved = True
                break
        assert moved

    def test_boundary_check(self):
        m = Monster("Test", hp=5, ac=10, attack_bonus=1)
        m.col, m.row = 0, 0
        tm = _FakeTileMap()
        # Try to move toward negative coords — should stay at boundary
        m.try_move_toward(-5, -5, tm, set())
        assert m.col >= 0 and m.row >= 0


# ── Encounter creation ─────────────────────────────────────────────


class TestCreateEncounter:

    def test_returns_dict_with_monsters(self):
        enc = create_encounter()
        assert isinstance(enc, dict)
        assert "monsters" in enc
        assert len(enc["monsters"]) > 0
        for m in enc["monsters"]:
            assert isinstance(m, Monster)

    def test_encounter_has_name(self):
        enc = create_encounter()
        assert "name" in enc
        assert isinstance(enc["name"], str)

    def test_sea_terrain_filter(self):
        enc = create_encounter(terrain="sea")
        # May return None if no sea encounters configured
        if enc is not None:
            for m in enc["monsters"]:
                assert m.terrain == "sea"
