"""
Data loader – reads JSON config files from a module directory or
the default ``data/`` folder and populates the game's runtime
dictionaries.

All public load functions accept an optional *data_dir* parameter.
When omitted they fall back to the project-level ``data/`` folder.
"""

import json
import os

# Resolve the project root (one level up from src/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")


def _load_json(filename, data_dir=None):
    """Load and return a parsed JSON file.

    If *data_dir* is given the file is looked up there first; if it
    doesn't exist, the default ``data/`` folder is used as a fallback.
    """
    if data_dir is not None:
        mod_path = os.path.join(data_dir, filename)
        if os.path.isfile(mod_path):
            with open(mod_path, "r") as f:
                return json.load(f)
    # Fallback to default data/ directory
    path = os.path.join(_DATA_DIR, filename)
    with open(path, "r") as f:
        return json.load(f)


def load_items(data_dir=None):
    """Load items.json and return (WEAPONS, ARMORS, ITEM_INFO, SHOP_INVENTORY).

    Looks in *data_dir* first (if given), then falls back to ``data/``.
    """
    raw = _load_json("items.json", data_dir)

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
            if data.get("item_type"):
                info["item_type"] = data["item_type"]
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
            if data.get("item_type"):
                info["item_type"] = data["item_type"]
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
            if data.get("item_type"):
                info["item_type"] = data["item_type"]
            if data.get("quest_item"):
                info["quest_item"] = True
            # Poison potion fields
            if data.get("poison_type"):
                info["poison_type"] = data["poison_type"]
            if "poison_damage" in data:
                info["poison_damage"] = data["poison_damage"]
            if "poison_mp_drain" in data:
                info["poison_mp_drain"] = data["poison_mp_drain"]
            if "poison_debilitate" in data:
                info["poison_debilitate"] = data["poison_debilitate"]
            if "poison_duration" in data:
                info["poison_duration"] = data["poison_duration"]
            if "save_dc" in data:
                info["save_dc"] = data["save_dc"]
            item_info[name] = info

        if "buy" in data:
            shop_inventory[name] = {
                "buy": data["buy"],
                "sell": data.get("sell", data["buy"] // 2),
            }

    return weapons, armors, item_info, shop_inventory


def load_counters(data_dir=None):
    """Load counters.json and return a dict mapping shop_type → list of item names.

    Looks in *data_dir* first (if given), then falls back to ``data/``.
    Each key in the JSON is a shop type (e.g. "general", "weapon")
    and the value contains a "items" list of item names sold there.
    """
    try:
        raw = _load_json("counters.json", data_dir)
    except (OSError, ValueError):
        return {}
    counters = {}
    for key, entry in raw.items():
        counters[key] = list(entry.get("items", []))
    return counters


def load_races(data_dir=None):
    """Load races.json and return a dict keyed by race name.

    Looks in *data_dir* first (if given), then falls back to ``data/``.
    """
    raw = _load_json("races.json", data_dir)
    races = {}
    for name, data in raw.items():
        if name.startswith("_"):
            continue  # skip _comment
        info = {
            "description": data.get("description", ""),
            "stat_modifiers": data.get("stat_modifiers", {}),
            "effects": list(data.get("effects", [])),
        }
        # Preserve optional XP-per-level override (e.g. Humans level faster)
        if "exp_per_level" in data:
            info["exp_per_level"] = data["exp_per_level"]
        races[name] = info
    return races
