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


# ── Boat persistence ──────────────────────────────────────────────


@pytest.fixture
def isolated_save_dir(tmp_path, monkeypatch):
    """Redirect save_load to write into a temp directory."""
    from src import save_load as sl
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    monkeypatch.setattr(sl, "_SAVE_DIR", str(save_dir))
    return save_dir


class TestBoatPersistence:
    """Boats are mutable terrain — sailing one moves a TILE_BOAT marker
    on the overworld map. Because load_game rebuilds the tile_map from
    seed/static-map on every load, those mutations are wiped unless
    save_game snapshots them and load_game re-stamps them.

    Without this round-trip, a player who sails to the mainland and
    saves gets stranded on reload: the boat snaps back to its original
    spawn point and the party is left on land with no way back to it.
    """

    def _wipe_boats(self, tmap):
        """Clear all TILE_BOAT tiles from a fresh tile_map so the test
        controls the boat layout deterministically. Returns the list
        of (col, row) positions that were originally boats."""
        from src.settings import TILE_BOAT, TILE_WATER
        originals = []
        for r in range(tmap.height):
            for c in range(tmap.width):
                if tmap.get_tile(c, r) == TILE_BOAT:
                    originals.append((c, r))
                    tmap.set_tile(c, r, TILE_WATER)
        return originals

    def test_sailed_boat_position_survives_save_load(
            self, game, isolated_save_dir):
        """The bug: sail boat → save → load → boat is back at its
        original spawn point and the party is stranded.
        """
        from src import save_load
        from src.settings import TILE_BOAT, TILE_WATER

        # Start from a known empty-of-boats overworld so we can place
        # a single boat at a position we know is *not* in the procedural
        # spawn set. Test then re-checks the post-load map for that
        # exact position.
        original_boats = self._wipe_boats(game.tile_map)
        sailed_to = (4, 4)
        # Make sure the position we picked isn't where a boat would
        # naturally regenerate from the seed.
        assert sailed_to not in original_boats
        game.tile_map.set_tile(*sailed_to, TILE_BOAT)
        game.on_boat = True
        game.party.col, game.party.row = sailed_to

        assert save_load.save_game(1, game), "save_game returned False"
        assert save_load.load_game(1, game), "load_game returned False"

        # The sailed-to tile must still be a boat after reload.
        assert game.tile_map.get_tile(*sailed_to) == TILE_BOAT, (
            "Boat should still be at the sailed-to position after "
            "save/load round-trip.")
        # And the party should still be aboard at that tile.
        assert game.on_boat is True
        assert (game.party.col, game.party.row) == sailed_to

        # Original (procedural) boat spawns should NOT have a boat —
        # otherwise we'd be duplicating them on every load.
        for orig in original_boats:
            if orig == sailed_to:
                continue
            assert game.tile_map.get_tile(*orig) != TILE_BOAT, (
                f"Original boat spawn {orig} should be cleared after "
                "load — boats only exist where the saved snapshot put "
                "them.")

    def test_legacy_save_without_boat_field_loads_cleanly(
            self, game, isolated_save_dir):
        """Saves that predate the boat_positions field must still load
        — they fall back to the rebuilt map's original boat layout
        rather than crashing."""
        from src import save_load

        assert save_load.save_game(1, game)

        # Strip the field from disk to mimic a legacy save.
        for fn in os.listdir(isolated_save_dir):
            path = os.path.join(isolated_save_dir, fn)
            with open(path) as f:
                data = json.load(f)
            data.pop("boat_positions", None)
            with open(path, "w") as f:
                json.dump(data, f)

        assert save_load.load_game(1, game)
