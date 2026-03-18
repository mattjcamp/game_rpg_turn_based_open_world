"""
Tests for src/data_loader.py — JSON data loading functions.

Covers: item loading, race loading, fallback paths, and data integrity.
"""
import pytest
from src.data_loader import load_items, load_races, _load_json


# ── _load_json ─────────────────────────────────────────────────────


class TestLoadJson:

    def test_load_existing_file(self):
        data = _load_json("monsters.json")
        assert isinstance(data, dict)
        assert "monsters" in data

    def test_load_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            _load_json("nonexistent_file_xyz.json")

    def test_fallback_to_default_data_dir(self):
        """When data_dir is given but file doesn't exist there,
        falls back to the default data/ directory."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            # tmpdir has no monsters.json, so should fall back
            data = _load_json("monsters.json", data_dir=tmpdir)
            assert "monsters" in data


# ── load_items ─────────────────────────────────────────────────────


class TestLoadItems:

    def test_returns_four_dicts(self):
        weapons, armors, item_info, shop = load_items()
        assert isinstance(weapons, dict)
        assert isinstance(armors, dict)
        assert isinstance(item_info, dict)
        assert isinstance(shop, dict)

    def test_weapons_have_power(self):
        weapons, _, _, _ = load_items()
        assert len(weapons) > 0
        for name, data in weapons.items():
            assert "power" in data, f"Weapon {name} missing 'power'"

    def test_armors_have_evasion(self):
        _, armors, _, _ = load_items()
        assert len(armors) > 0
        for name, data in armors.items():
            assert "evasion" in data, f"Armor {name} missing 'evasion'"

    def test_shop_items_have_buy_and_sell(self):
        _, _, _, shop = load_items()
        assert len(shop) > 0
        for name, data in shop.items():
            assert "buy" in data, f"Shop item {name} missing 'buy'"
            assert "sell" in data, f"Shop item {name} missing 'sell'"

    def test_sell_price_less_than_or_equal_buy(self):
        _, _, _, shop = load_items()
        for name, data in shop.items():
            assert data["sell"] <= data["buy"], (
                f"{name}: sell ({data['sell']}) > buy ({data['buy']})")


# ── load_races ─────────────────────────────────────────────────────


class TestLoadRaces:

    def test_returns_dict_of_races(self):
        races = load_races()
        assert isinstance(races, dict)
        assert len(races) >= 1

    def test_human_race_exists(self):
        races = load_races()
        assert "Human" in races

    def test_race_has_required_fields(self):
        races = load_races()
        for name, data in races.items():
            assert "description" in data, f"Race {name} missing 'description'"
            assert "stat_modifiers" in data, f"Race {name} missing 'stat_modifiers'"
            assert "effects" in data, f"Race {name} missing 'effects'"

    def test_excludes_comment_keys(self):
        races = load_races()
        for name in races:
            assert not name.startswith("_"), f"Comment key '{name}' leaked through"
