"""
Cross-cutting data integrity tests.

Validates that JSON data files are consistent with each other and that
the data registry, party module, and game systems agree on shared data.
"""
import json
import os
import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename)) as f:
        return json.load(f)


# ── JSON file validity ─────────────────────────────────────────────


class TestJsonFilesValid:

    DATA_FILES = [
        "items.json", "races.json", "monsters.json",
        "encounters.json", "spells.json", "loot.json",
    ]

    @pytest.mark.parametrize("filename", DATA_FILES)
    def test_json_file_parses(self, filename):
        data = _load(filename)
        assert isinstance(data, (dict, list))

    def test_class_templates_all_valid(self):
        classes_dir = os.path.join(_DATA_DIR, "classes")
        assert os.path.isdir(classes_dir)
        for fname in os.listdir(classes_dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(classes_dir, fname)
            with open(path) as f:
                tmpl = json.load(f)
            assert "name" in tmpl, f"Class template {fname} missing 'name'"
            assert "spell_type" in tmpl, f"Class template {fname} missing 'spell_type'"


# ── Spell data integrity ──────────────────────────────────────────


class TestSpellIntegrity:

    @pytest.fixture(autouse=True)
    def load_spells(self):
        self.spells = _load("spells.json").get("spells", [])

    def test_all_spells_have_id(self):
        for s in self.spells:
            assert "id" in s, f"Spell missing 'id': {s.get('name', '?')}"

    def test_unique_spell_ids(self):
        ids = [s["id"] for s in self.spells]
        assert len(ids) == len(set(ids)), "Duplicate spell IDs found"

    def test_spells_have_required_fields(self):
        required = {"id", "name", "mp_cost", "effect_type", "casting_type"}
        for s in self.spells:
            for field in required:
                assert field in s, (
                    f"Spell '{s.get('id', '?')}' missing '{field}'")

    def test_casting_type_values_valid(self):
        from src import data_registry as DR
        valid = set(DR.all_casting_types())
        for s in self.spells:
            ct = s.get("casting_type")
            assert ct in valid, (
                f"Spell '{s['id']}' has invalid casting_type '{ct}'")


# ── Loot table integrity ──────────────────────────────────────────


class TestLootIntegrity:

    def test_loot_items_exist_in_items_json(self):
        loot = _load("loot.json").get("chest_loot", [])
        items_data = _load("items.json")
        # Build a set of all known item names
        all_items = set()
        for section in ("weapons", "armors", "general"):
            all_items.update(items_data.get(section, {}).keys())

        for entry in loot:
            item = entry.get("item")
            if item is not None:  # None means gold-only
                assert item in all_items, (
                    f"Loot item '{item}' not found in items.json")

    def test_loot_weights_positive(self):
        loot = _load("loot.json").get("chest_loot", [])
        for entry in loot:
            assert entry.get("weight", 0) > 0, (
                f"Loot entry '{entry.get('item')}' has non-positive weight")


# ── Encounter → monster integrity ─────────────────────────────────


class TestEncounterIntegrity:

    def test_encounter_monsters_exist(self):
        encounters = _load("encounters.json").get("encounters", {})
        monsters = _load("monsters.json").get("monsters", {})
        for area, pool in encounters.items():
            for enc in pool:
                for mname in enc.get("monsters", []):
                    assert mname in monsters, (
                        f"Encounter '{enc.get('name', '?')}' in '{area}' "
                        f"references unknown monster '{mname}'")


# ── Registry ↔ party module agreement ─────────────────────────────


class TestRegistryPartyAgreement:

    def test_spells_data_matches_json(self):
        """SPELLS_DATA in party.py should contain same spells as file."""
        from src.party import SPELLS_DATA
        file_spells = _load("spells.json").get("spells", [])
        file_ids = {s["id"] for s in file_spells}
        assert set(SPELLS_DATA.keys()) == file_ids

    def test_registry_classes_match_templates(self):
        """data_registry class names should match class JSON files."""
        from src import data_registry as DR
        DR._class_cache.clear()
        registry_names = set(DR.all_class_names())

        classes_dir = os.path.join(_DATA_DIR, "classes")
        file_names = set()
        for fname in os.listdir(classes_dir):
            if fname.endswith(".json"):
                with open(os.path.join(classes_dir, fname)) as f:
                    tmpl = json.load(f)
                file_names.add(tmpl["name"])

        assert registry_names == file_names
