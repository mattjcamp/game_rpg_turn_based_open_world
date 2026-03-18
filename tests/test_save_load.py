"""
Tests for src/save_load.py — game serialization and config persistence.

Uses a temporary directory for all file I/O to avoid touching real saves.
"""
import json
import os
import tempfile
import pytest

from src.save_load import (
    _serialize_member, _serialize_party, _deserialize_member,
    _deserialize_party, save_config, load_config,
    _DEFAULT_CONFIG,
)
from src.party import Party, PartyMember


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def party():
    """Create a minimal party with one member for serialization tests."""
    p = Party(start_col=10, start_row=10)
    m = PartyMember("TestHero", "Fighter")
    p.roster.append(m)
    p.active_indices = [0]
    p.members = [m]
    return p


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config path to a temp directory."""
    cfg_path = str(tmp_path / "config.json")
    monkeypatch.setattr("src.save_load._CONFIG_PATH", cfg_path)
    return cfg_path


# ── Member serialization ──────────────────────────────────────────


class TestMemberSerialization:

    def test_serialize_member_has_required_keys(self, party):
        m = party.members[0]
        data = _serialize_member(m)
        for key in ("name", "class", "race", "hp", "max_hp",
                     "level", "exp", "equipped", "inventory"):
            assert key in data, f"Missing key '{key}'"

    def test_roundtrip_member(self, party):
        m = party.members[0]
        m.name = "TestHero"
        m.hp = 7
        m.exp = 42
        data = _serialize_member(m)
        restored = _deserialize_member(data)
        assert restored.name == "TestHero"
        assert restored.hp == 7
        assert restored.exp == 42
        assert restored.char_class == m.char_class

    def test_serialize_preserves_equipment(self, party):
        m = party.members[0]
        m.equipped["right_hand"] = "Sword"
        data = _serialize_member(m)
        assert data["equipped"]["right_hand"] == "Sword"


# ── Party serialization ───────────────────────────────────────────


class TestPartySerialization:

    def test_serialize_party_has_required_keys(self, party):
        data = _serialize_party(party)
        for key in ("col", "row", "gold", "roster", "shared_inventory",
                     "equipped", "effects", "clock"):
            assert key in data, f"Missing key '{key}'"

    def test_roundtrip_party(self, party):
        party.gold = 999
        party.col = 15
        party.row = 22
        data = _serialize_party(party)
        restored = _deserialize_party(data)
        assert restored.gold == 999
        assert restored.col == 15
        assert restored.row == 22
        assert len(restored.members) == len(party.members)

    def test_serialize_party_json_safe(self, party):
        """The serialized party should be JSON-encodable."""
        data = _serialize_party(party)
        json_str = json.dumps(data)
        assert isinstance(json_str, str)


# ── Config persistence ─────────────────────────────────────────────


class TestConfig:

    def test_load_missing_config_returns_defaults(self, tmp_config):
        config = load_config()
        assert config == _DEFAULT_CONFIG

    def test_save_and_load_roundtrip(self, tmp_config):
        cfg = {"music_enabled": False, "smite_enabled": True,
               "start_with_equipment": False, "active_module_path": "/test"}
        save_config(cfg)
        loaded = load_config()
        assert loaded["music_enabled"] is False
        assert loaded["smite_enabled"] is True
        assert loaded["active_module_path"] == "/test"

    def test_load_merges_with_defaults(self, tmp_config):
        """New config keys should appear even if the save file is old."""
        # Write a minimal config missing some keys
        with open(tmp_config, "w") as f:
            json.dump({"music_enabled": False}, f)
        loaded = load_config()
        assert loaded["music_enabled"] is False
        # Default keys should still be present
        assert "smite_enabled" in loaded
        assert "start_with_equipment" in loaded

    def test_load_corrupt_file_returns_defaults(self, tmp_config):
        with open(tmp_config, "w") as f:
            f.write("NOT VALID JSON {{{{")
        config = load_config()
        assert config == _DEFAULT_CONFIG
