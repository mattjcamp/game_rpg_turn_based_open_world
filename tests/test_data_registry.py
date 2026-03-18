"""
Tests for src/data_registry.py — the centralized data registry.

Covers: class templates, casting-type mappings, loot tables,
effect/targeting enums, race helpers, and reload behaviour.
"""
import pytest
from src import data_registry as DR


# ── Fixture to reset caches between tests ──────────────────────────


@pytest.fixture(autouse=True)
def fresh_registry():
    """Clear all caches before each test so state doesn't leak."""
    DR._class_cache.clear()
    DR._loot_cache.clear()
    yield
    DR._class_cache.clear()
    DR._loot_cache.clear()


# ── Class template loading ─────────────────────────────────────────


class TestClassTemplates:

    def test_all_class_names_returns_sorted_list(self):
        names = DR.all_class_names()
        assert isinstance(names, list)
        assert len(names) >= 4  # at least Fighter, Wizard, Cleric, Thief
        assert names == sorted(names)

    def test_caster_class_names_subset_of_all(self):
        all_cls = set(DR.all_class_names())
        casters = set(DR.caster_class_names())
        assert casters.issubset(all_cls)
        # At least wizard and cleric should be casters
        assert len(casters) >= 2

    def test_caster_class_names_excludes_fighter(self):
        casters = DR.caster_class_names()
        # Fighter has spell_type "none" in the template
        assert "Fighter" not in casters

    def test_class_cache_populated_after_load(self):
        assert len(DR._class_cache) == 0
        DR.all_class_names()
        assert len(DR._class_cache) > 0


# ── Casting-type mappings ──────────────────────────────────────────


class TestCastingType:

    def test_classes_for_sorcerer(self):
        classes = DR.classes_for_casting_type("sorcerer")
        assert isinstance(classes, list)
        assert "Wizard" in classes

    def test_classes_for_priest(self):
        classes = DR.classes_for_casting_type("priest")
        assert isinstance(classes, list)
        assert "Cleric" in classes

    def test_classes_for_unknown_type_returns_only_dual_casters(self):
        """A type like 'psychic' should only match classes with
        spell_type='both', not sorcerer/priest-specific ones."""
        classes = DR.classes_for_casting_type("psychic")
        DR._ensure_classes()
        for name in classes:
            tmpl = DR._class_cache[name]
            assert tmpl.get("spell_type") == "both"

    def test_casting_type_label_sorcerer(self):
        assert DR.casting_type_label("sorcerer") == "Sorcerer"

    def test_casting_type_label_priest(self):
        assert DR.casting_type_label("priest") == "Cleric"

    def test_all_casting_types(self):
        types = DR.all_casting_types()
        assert "sorcerer" in types
        assert "priest" in types

    def test_casting_type_sort_order(self):
        order = DR.casting_type_sort_order()
        assert order["sorcerer"] < order["priest"]


# ── Spell field enums ──────────────────────────────────────────────


class TestSpellEnums:

    def test_all_effect_types_includes_base_set(self):
        types = DR.all_effect_types()
        assert isinstance(types, list)
        for expected in ("damage", "heal", "teleport", "sleep"):
            assert expected in types

    def test_all_effect_types_sorted(self):
        types = DR.all_effect_types()
        assert types == sorted(types)

    def test_all_targeting_types_nonempty(self):
        targets = DR.all_targeting_types()
        assert len(targets) >= 3
        assert "self" in targets
        assert "select_enemy" in targets

    def test_all_usable_locations(self):
        locs = DR.all_usable_locations()
        assert "battle" in locs
        assert "overworld" in locs


# ── Loot tables ────────────────────────────────────────────────────


class TestLootTable:

    def test_chest_loot_returns_list_of_tuples(self):
        loot = DR.chest_loot()
        assert isinstance(loot, list)
        assert len(loot) > 0
        for item, weight in loot:
            assert isinstance(weight, int)
            assert weight > 0

    def test_chest_loot_contains_none_entry(self):
        """Gold-only entry should be present."""
        loot = DR.chest_loot()
        items = [item for item, _ in loot]
        assert None in items

    def test_chest_loot_cached(self):
        loot1 = DR.chest_loot()
        loot2 = DR.chest_loot()
        assert loot1 is loot2  # same list object (cached)


# ── Race helpers ───────────────────────────────────────────────────


class TestRaceHelpers:

    def test_all_race_names_nonempty(self):
        races = DR.all_race_names()
        assert len(races) >= 1
        assert "Human" in races

    def test_all_race_names_excludes_comments(self):
        races = DR.all_race_names()
        for name in races:
            assert not name.startswith("_")

    def test_default_race_is_string(self):
        race = DR.default_race()
        assert isinstance(race, str)
        assert len(race) > 0


# ── Reload ─────────────────────────────────────────────────────────


class TestReload:

    def test_reload_clears_caches(self):
        # Populate caches
        DR.all_class_names()
        DR.chest_loot()
        assert len(DR._class_cache) > 0
        assert len(DR._loot_cache) > 0
        # Reload with no dir — clears caches
        DR.reload()
        assert len(DR._class_cache) == 0
        assert len(DR._loot_cache) == 0

    def test_reload_with_data_dir_repopulates_classes(self):
        import os
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data")
        DR.reload(data_dir)
        # Class cache should be repopulated
        assert len(DR._class_cache) > 0
