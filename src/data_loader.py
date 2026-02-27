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
        if data.get("consumable"):
            entry["consumable"] = True
        weapons[name] = entry

        # Description & icon (what ITEM_INFO needs)
        if "description" in data or "icon" in data:
            item_info[name] = {
                "desc": data.get("description", ""),
                "icon": data.get("icon", "sword"),
            }

        # Shop prices (what SHOP_INVENTORY needs)
        if "buy" in data:
            shop_inventory[name] = {
                "buy": data["buy"],
                "sell": data.get("sell", data["buy"] // 2),
            }

    # ── Armors ──
    for name, data in raw.get("armors", {}).items():
        armors[name] = {"evasion": data["evasion"]}

        if "description" in data or "icon" in data:
            item_info[name] = {
                "desc": data.get("description", ""),
                "icon": data.get("icon", "armor_light"),
            }

        if "buy" in data:
            shop_inventory[name] = {
                "buy": data["buy"],
                "sell": data.get("sell", data["buy"] // 2),
            }

    # ── General items ──
    for name, data in raw.get("general", {}).items():
        if "description" in data or "icon" in data:
            item_info[name] = {
                "desc": data.get("description", ""),
                "icon": data.get("icon", "tool"),
            }

        if "buy" in data:
            shop_inventory[name] = {
                "buy": data["buy"],
                "sell": data.get("sell", data["buy"] // 2),
            }

    return weapons, armors, item_info, shop_inventory
