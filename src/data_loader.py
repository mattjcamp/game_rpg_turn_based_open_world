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
        # Durability system
        if "durability" in data:
            entry["durability"] = data["durability"]
        if data.get("indestructible"):
            entry["indestructible"] = True
        # Magic-item attributes — only emitted when present so mundane
        # weapons stay slim.  Combat reads these straight off WEAPONS.
        if data.get("damage_type"):
            entry["damage_type"] = data["damage_type"]
        if data.get("bonus_damage"):
            entry["bonus_damage"] = data["bonus_damage"]
        if data.get("ac_bonus"):
            entry["ac_bonus"] = data["ac_bonus"]
        if data.get("stat_bonuses"):
            entry["stat_bonuses"] = dict(data["stat_bonuses"])
        if data.get("grants_effect"):
            entry["grants_effect"] = data["grants_effect"]
        if data.get("on_hit"):
            entry["on_hit"] = dict(data["on_hit"])
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
            # Durability info for display
            if "durability" in data:
                info["durability"] = data["durability"]
            if data.get("indestructible"):
                info["indestructible"] = True
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
        # Durability system
        if "durability" in data:
            entry["durability"] = data["durability"]
        if data.get("indestructible"):
            entry["indestructible"] = True
        # Magic-item attributes (armors don't have on_hit/bonus_damage/
        # damage_type since those are weapon-only, but they share the
        # passive bonuses with weapons).
        if data.get("ac_bonus"):
            entry["ac_bonus"] = data["ac_bonus"]
        if data.get("stat_bonuses"):
            entry["stat_bonuses"] = dict(data["stat_bonuses"])
        if data.get("grants_effect"):
            entry["grants_effect"] = data["grants_effect"]
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
            # Durability info for display
            if "durability" in data:
                info["durability"] = data["durability"]
            if data.get("indestructible"):
                info["indestructible"] = True
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
            # combat_usable defaults to True for usable items;
            # set explicitly to False for items like Camping
            # Supplies that only work outside combat.
            if "combat_usable" in data:
                info["combat_usable"] = data["combat_usable"]
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


def load_spawn_points(data_dir=None):
    """Load spawn_points.json and return a dict mapping tile_id (int) → spawn config.

    Looks in *data_dir* first (if given), then falls back to ``data/``.
    Each spawn point has: spawn_monsters, spawn_chance, spawn_radius,
    max_spawned, boss_monsters, xp_reward, gold_reward, loot, description.
    """
    try:
        raw = _load_json("spawn_points.json", data_dir)
    except (OSError, ValueError):
        return {}
    points = {}
    for tid_str, entry in raw.get("spawn_points", {}).items():
        tid = int(tid_str)
        points[tid] = {
            "name": entry.get("name", "Monster Spawn"),
            "description": entry.get("description", "A monster lair."),
            "spawn_monsters": list(entry.get("spawn_monsters", [])),
            "spawn_chance": entry.get("spawn_chance", 20),
            "spawn_radius": entry.get("spawn_radius", 3),
            "max_spawned": entry.get("max_spawned", 2),
            "boss_monster": entry.get("boss_monster", ""),
            "boss_monsters": list(entry.get("boss_monsters", [])),
            "xp_reward": entry.get("xp_reward", 50),
            "gold_reward": entry.get("gold_reward", 25),
            "loot": list(entry.get("loot", [])),
            "background_tile": entry.get("background_tile", 0),
        }
    return points


def load_counters(data_dir=None):
    """Load counters.json and return a dict mapping shop_type → list of item names.

    Looks in *data_dir* first (if given), then falls back to ``data/``.
    Each key in the JSON is a shop type (e.g. "general", "weapon")
    and the value contains a "items" list of item names sold there.

    Service-kind counters (``kind == "service"``) are excluded from this
    mapping so the regular buy/sell shop UI never tries to show their
    (empty) item list as a real store.
    """
    try:
        raw = _load_json("counters.json", data_dir)
    except (OSError, ValueError):
        return {}
    counters = {}
    for key, entry in raw.items():
        if entry.get("kind") == "service":
            continue
        counters[key] = list(entry.get("items", []))
    return counters


def load_service_counters(data_dir=None):
    """Load service-kind counters from counters.json.

    Returns a dict mapping counter_key → {"name", "description", "services"}
    where each service is a dict with ``id``, ``name``, ``description``, ``cost``.
    Non-service counters are excluded. This is the source of truth for
    healing counters and any other interactive service stalls placed on maps.
    """
    try:
        raw = _load_json("counters.json", data_dir)
    except (OSError, ValueError):
        return {}
    services = {}
    for key, entry in raw.items():
        if entry.get("kind") != "service":
            continue
        services[key] = {
            "name": entry.get("name", key),
            "description": entry.get("description", ""),
            "services": [
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", s.get("id", "")),
                    "description": s.get("description", ""),
                    "cost": int(s.get("cost", 0)),
                }
                for s in entry.get("services", [])
            ],
        }
    return services


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
