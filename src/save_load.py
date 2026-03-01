"""
Save and load game state to/from JSON files.

Serializes the party (members, equipment, inventory, gold, position),
party-level equipment and effects, and the current game state name.
Save files are stored in data/saves/.
"""

import json
import os
import time

from src.party import Party, PartyMember

# ── Save directory ────────────────────────────────────────────────
_SAVE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "saves")

# Number of save slots
NUM_SAVE_SLOTS = 3


def _ensure_save_dir():
    """Create the saves directory if it doesn't exist."""
    os.makedirs(_SAVE_DIR, exist_ok=True)


def _save_path(slot):
    """Return the file path for a given save slot (1-based)."""
    return os.path.join(_SAVE_DIR, f"save_{slot}.json")


# ── Serialization helpers ─────────────────────────────────────────

def _serialize_member(member):
    """Convert a PartyMember to a JSON-safe dict."""
    return {
        "name": member.name,
        "class": member.char_class,
        "race": member.race,
        "max_hp": member.max_hp,
        "hp": member.hp,
        "strength": member.strength,
        "dexterity": member.dexterity,
        "intelligence": member.intelligence,
        "wisdom": member.wisdom,
        "level": member.level,
        "exp": member.exp,
        "equipped": dict(member.equipped),
        "inventory": list(member.inventory),
        "current_mp": member._current_mp,
        "bonus_mp": member._bonus_mp,
        "ammo": dict(member.ammo),
    }


def _serialize_party(party):
    """Convert a Party to a JSON-safe dict."""
    return {
        "col": party.col,
        "row": party.row,
        "gold": party.gold,
        "members": [_serialize_member(m) for m in party.members],
        "shared_inventory": list(party.shared_inventory),
        "equipped": dict(party.equipped),
        "effects": dict(party.effects),
    }


def _deserialize_member(data):
    """Reconstruct a PartyMember from saved data."""
    member = PartyMember(
        name=data["name"],
        char_class=data["class"],
        race=data.get("race", "Human"),
        hp=data.get("max_hp", 20),
        strength=data.get("strength", 10),
        dexterity=data.get("dexterity", 10),
        intelligence=data.get("intelligence", 10),
        wisdom=data.get("wisdom", 10),
        level=data.get("level", 1),
    )
    member.hp = data.get("hp", member.max_hp)
    member.max_hp = data.get("max_hp", member.max_hp)
    member.exp = data.get("exp", 0)

    # Equipment slots
    equip = data.get("equipped", {})
    member.equipped = {
        "right_hand": equip.get("right_hand", "Fists"),
        "left_hand": equip.get("left_hand"),
        "body": equip.get("body", "Cloth"),
        "head": equip.get("head"),
    }
    member._sync_legacy_fields()

    # Personal inventory
    member.inventory = list(data.get("inventory", []))

    # MP state
    member._current_mp = data.get("current_mp")
    member._bonus_mp = data.get("bonus_mp", 0)

    # Ammo tracking
    member.ammo = dict(data.get("ammo", {}))

    return member


def _deserialize_party(data):
    """Reconstruct a Party from saved data."""
    party = Party(data.get("col", 30), data.get("row", 11))
    party.gold = data.get("gold", 100)

    # Rebuild members
    for member_data in data.get("members", []):
        member = _deserialize_member(member_data)
        party.add_member(member)

    # Shared inventory (already in correct format — strings and dicts)
    party.shared_inventory = list(data.get("shared_inventory", []))

    # Party-level equipment slots
    saved_eq = data.get("equipped", {})
    for slot in party.PARTY_SLOTS:
        entry = saved_eq.get(slot)
        party.equipped[slot] = entry  # None or {"name": ..., "charges": ...}

    # Party-level passive effects
    saved_eff = data.get("effects", {})
    for slot in party.EFFECT_SLOTS:
        party.effects[slot] = saved_eff.get(slot)

    return party


# ── Public API ────────────────────────────────────────────────────

def save_game(slot, game):
    """Save the current game state to a numbered slot (1-based).

    Parameters
    ----------
    slot : int
        Save slot number (1 to NUM_SAVE_SLOTS).
    game : Game
        The main Game object whose state will be saved.

    Returns
    -------
    bool
        True if saved successfully, False on error.
    """
    _ensure_save_dir()
    try:
        # Determine current state name
        state_name = "overworld"
        for name, state_obj in game.states.items():
            if state_obj is game.current_state:
                state_name = name
                break

        save_data = {
            "version": 1,
            "timestamp": time.time(),
            "state": state_name,
            "party": _serialize_party(game.party),
        }

        path = _save_path(slot)
        with open(path, "w") as f:
            json.dump(save_data, f, indent=2)
        return True
    except Exception:
        return False


def load_game(slot, game):
    """Load game state from a numbered slot (1-based).

    Restores party data (members, equipment, inventory, position, gold)
    and switches to the saved game state.

    Parameters
    ----------
    slot : int
        Save slot number (1 to NUM_SAVE_SLOTS).
    game : Game
        The main Game object to restore state into.

    Returns
    -------
    bool
        True if loaded successfully, False on error.
    """
    path = _save_path(slot)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r") as f:
            save_data = json.load(f)

        # Restore the party
        game.party = _deserialize_party(save_data["party"])

        # Switch to the saved game state (always return to overworld
        # to avoid loading mid-combat or mid-dungeon complications)
        game.change_state("overworld")
        game.camera.update(game.party.col, game.party.row)

        return True
    except Exception:
        return False


def get_save_info(slot):
    """Return summary info about a save slot, or None if empty.

    Returns
    -------
    dict or None
        {"slot": int, "timestamp": float, "state": str,
         "party_names": list[str], "gold": int, "level_avg": float}
    """
    path = _save_path(slot)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        party_data = data.get("party", {})
        members = party_data.get("members", [])
        names = [m.get("name", "???") for m in members]
        levels = [m.get("level", 1) for m in members]
        avg_level = sum(levels) / len(levels) if levels else 1

        return {
            "slot": slot,
            "timestamp": data.get("timestamp", 0),
            "state": data.get("state", "overworld"),
            "party_names": names,
            "gold": party_data.get("gold", 0),
            "level_avg": avg_level,
        }
    except Exception:
        return None


def delete_save(slot):
    """Delete a save file. Returns True if deleted."""
    path = _save_path(slot)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
