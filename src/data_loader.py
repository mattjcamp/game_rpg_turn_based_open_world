"""
Data loader – reads JSON config files from the data/ folder and
populates the game's runtime dictionaries.

This keeps all game-balance numbers in editable text files while
the rest of the code continues to use the same dict lookups as before.
"""

import json
import os

# Resolve the project root (one level up from src/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")


def _load_json(filename):
    """Load and return a parsed JSON file from the data/ folder."""
    path = os.path.join(_DATA_DIR, filename)
    with open(path, "r") as f:
        return json.load(f)


def load_items():
    """Load data/items.json and return (WEAPONS, ARMORS, ITEM_INFO, SHOP_INVENTORY).

    Each returned dict matches the format the rest of the code expects,
    so this is a drop-in replacement for the old hardcoded tables.
    """
    raw = _load_json("items.json")

    weapons = {}
    armors = {}
    item_info = {}
    shop_inventory = {}

    # ── Weapons ──
    for name, data in raw.get("weapons", {}).items():
        # Combat stats (what WEAPONS needs)
        entry = {"power": data["power"], "ranged": data.get("ranged", False)}
        if data.get("melee"):
            entry["melee"] = True
        if data.get("throwable"):
            entry["throwable"] = True
        if data.get("ammo"):
            entry["ammo"] = data["ammo"]
        if data.get("slots"):
            entry["slots"] = data["slots"]
        if data.get("item_type"):
            entry["item_type"] = data["item_type"]
        weapons[name] = entry

        # Description & icon (what ITEM_INFO needs)
        if "description" in data or "icon" in data:
            info = {
                "desc": data.get("description", ""),
                "icon": data.get("icon", "sword"),
                "party_can_equip": data.get("party_can_equip", False),
                "character_can_equip": data.get("character_can_equip", False),
            }
            if "charges" in data:
                info["charges"] = data["charges"]
            item_info[name] = info

        # Shop prices (what SHOP_INVENTORY needs)
        if "buy" in data:
            shop_inventory[name] = {
                "buy": data["buy"],
                "sell": data.get("sell", data["buy"] // 2),
            }

    # ── Armors ──
    for name, data in raw.get("armors", {}).items():
        entry = {"evasion": data["evasion"]}
        if data.get("slots"):
            entry["slots"] = data["slots"]
        if data.get("item_type"):
            entry["item_type"] = data["item_type"]
        armors[name] = entry

        if "description" in data or "icon" in data:
            info = {
                "desc": data.get("description", ""),
                "icon": data.get("icon", "armor_light"),
                "party_can_equip": data.get("party_can_equip", False),
                "character_can_equip": data.get("character_can_equip", False),
            }
            if "charges" in data:
                info["charges"] = data["charges"]
            item_info[name] = info

        if "buy" in data:
            shop_inventory[name] = {
                "buy": data["buy"],
                "sell": data.get("sell", data["buy"] // 2),
            }

    # ── General items ──
    for name, data in raw.get("general", {}).items():
        if "description" in data or "icon" in data:
            info = {
                "desc": data.get("description", ""),
                "icon": data.get("icon", "tool"),
                "party_can_equip": data.get("party_can_equip", False),
                "character_can_equip": data.get("character_can_equip", False),
            }
            if "charges" in data:
                info["charges"] = data["charges"]
            if data.get("stackable"):
                info["stackable"] = True
            if data.get("throwable"):
                info["throwable"] = True
            if data.get("usable"):
                info["usable"] = True
            if data.get("effect"):
                info["effect"] = data["effect"]
            if "power" in data:
                info["power"] = data["power"]
            item_info[name] = info

        if "buy" in data:
            shop_inventory[name] = {
                "buy": data["buy"],
                "sell": data.get("sell", data["buy"] // 2),
            }

    return weapons, armors, item_info, shop_inventory


def load_races():
    """Load data/races.json and return a dict keyed by race name.

    Each entry contains:
      - description (str)
      - stat_modifiers (dict of stat → int)
      - effects (list of str)
    """
    raw = _load_json("races.json")
    races = {}
    for name, data in raw.items():
        if name.startswith("_"):
            continue  # skip _comment
        races[name] = {
            "description": data.get("description", ""),
            "stat_modifiers": data.get("stat_modifiers", {}),
            "effects": list(data.get("effects", [])),
        }
    return races
