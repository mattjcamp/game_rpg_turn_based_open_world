"""
Centralised data registry — the single source of truth for all
game data that multiple systems need to share.

Other modules should import helpers from here instead of
hard-coding strings, duplicating lists, or reading JSON themselves.
"""

import json
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

# ── Internal loaders ─────────────────────────────────────────────

def _load(filename, data_dir=None):
    """Load a JSON file from *data_dir* (or default data/)."""
    if data_dir:
        p = os.path.join(data_dir, filename)
        if os.path.isfile(p):
            with open(p, "r") as f:
                return json.load(f)
    with open(os.path.join(_DATA_DIR, filename), "r") as f:
        return json.load(f)


# ── Class templates ──────────────────────────────────────────────

_class_cache = {}  # class_name -> template dict


def _ensure_classes(data_dir=None):
    """Load class templates if not yet cached."""
    if _class_cache:
        return
    classes_dir = os.path.join(data_dir or _DATA_DIR, "classes")
    if not os.path.isdir(classes_dir):
        classes_dir = os.path.join(_DATA_DIR, "classes")
    for fname in os.listdir(classes_dir):
        if fname.endswith(".json"):
            with open(os.path.join(classes_dir, fname), "r") as f:
                tmpl = json.load(f)
            name = tmpl.get("name", fname.replace(".json", "").title())
            _class_cache[name] = tmpl


def reload(data_dir=None):
    """Clear all caches so the next access re-reads from disk.

    Called by party.reload_module_data() and similar reloaders.
    """
    _class_cache.clear()
    _loot_cache.clear()
    if data_dir:
        _ensure_classes(data_dir)


# ── Casting-type ↔ class mappings (derived from class templates) ─

def classes_for_casting_type(casting_type, data_dir=None):
    """Return a list of class names whose spell_type matches
    *casting_type* (or 'both').

    E.g. classes_for_casting_type("priest") → ["Cleric", "Paladin", "Druid", "Ranger"]
    """
    _ensure_classes(data_dir)
    result = []
    for name, tmpl in sorted(_class_cache.items()):
        st = tmpl.get("spell_type", "none")
        if st == casting_type or st == "both":
            result.append(name)
    return result


def casting_type_label(raw_type):
    """Human-readable label for a casting_type value.

    "sorcerer" → "Sorcerer", "priest" → "Cleric"
    """
    return "Cleric" if raw_type == "priest" else "Sorcerer"


def all_casting_types():
    """Return the list of valid casting_type values."""
    return ["sorcerer", "priest"]


def casting_type_sort_order():
    """Return a dict mapping casting_type → sort key."""
    return {"sorcerer": 0, "priest": 1}


# ── Spell field enums (derived from data) ────────────────────────

def all_effect_types(data_dir=None):
    """Return sorted list of all known effect_type values,
    derived from spells.json."""
    try:
        spells = _load("spells.json", data_dir).get("spells", [])
    except (OSError, ValueError):
        spells = []
    types = set()
    for s in spells:
        et = s.get("effect_type", "")
        if et:
            types.add(et)
    # Include the well-known base set so the editor always has
    # the full list even if not all types are in current spells
    base = {
        "damage", "heal", "ac_buff", "range_buff", "sleep",
        "teleport", "charm", "invisibility", "summon_skeleton",
        "lightning_bolt", "aoe_fireball", "cure_poison",
        "magic_light", "undead_damage", "bless", "curse",
        "major_heal", "repel_monsters", "mass_heal", "restore",
        "knock",
    }
    return sorted(types | base)


def all_targeting_types():
    """Return the list of valid targeting values."""
    return [
        "directional_projectile", "select_enemy", "select_ally",
        "select_ally_or_self", "select_tile", "self", "auto_monster",
    ]


def all_usable_locations():
    """Return the list of valid usable_in values."""
    return ["battle", "overworld", "town", "dungeon"]


# ── Class list (derived from class template files) ───────────────

def all_class_names(data_dir=None):
    """Return sorted list of all class names from class templates."""
    _ensure_classes(data_dir)
    return sorted(_class_cache.keys())


def caster_class_names(data_dir=None):
    """Return sorted list of class names that can cast spells."""
    _ensure_classes(data_dir)
    return sorted(
        name for name, tmpl in _class_cache.items()
        if tmpl.get("spell_type", "none") != "none"
    )


# ── Loot tables (from data/loot.json) ───────────────────────────

_loot_cache = {}


def chest_loot(data_dir=None):
    """Return the chest loot table as a list of (item_name_or_None, weight) tuples."""
    if "chest" not in _loot_cache:
        try:
            data = _load("loot.json", data_dir)
            entries = data.get("chest_loot", [])
        except (OSError, ValueError):
            entries = []
        _loot_cache["chest"] = [
            (e.get("item"), e.get("weight", 1)) for e in entries
        ]
    return _loot_cache["chest"]


# ── Race helpers ────────────────────────────────────────────────

def all_race_names(data_dir=None):
    """Return list of valid race names from races.json."""
    try:
        races = _load("races.json", data_dir)
    except (OSError, ValueError):
        return ["Human"]
    return [k for k in races.keys() if not k.startswith("_")]


def default_race(data_dir=None):
    """Return the first race name (used as a default)."""
    names = all_race_names(data_dir)
    return names[0] if names else "Human"


# ── Monster helpers (derived from data/monsters.json) ─────────────


def all_monster_names(data_dir=None):
    """Return sorted list of all monster names from monsters.json."""
    try:
        data = _load("monsters.json", data_dir)
        return sorted(data.get("monsters", {}).keys())
    except (OSError, ValueError):
        return []


def killable_monster_names(data_dir=None):
    """Return monster names suitable for kill-quest targets.

    Excludes sea-only creatures since dungeons are land-based.
    """
    try:
        monsters = _load("monsters.json", data_dir).get("monsters", {})
    except (OSError, ValueError):
        return []
    return sorted(
        name for name, data in monsters.items()
        if data.get("terrain", "land") != "sea"
    )


# ── Item helpers (derived from data/items.json) ──────────────────


def all_item_names(data_dir=None):
    """Return sorted list of all item names from items.json."""
    try:
        raw = _load("items.json", data_dir)
    except (OSError, ValueError):
        return []
    names = set()
    for section in ("weapons", "armors", "general"):
        names.update(raw.get(section, {}).keys())
    return sorted(names)


# ── Sprite / icon helpers (for editors) ──────────────────────────


def all_item_icons(data_dir=None):
    """Return sorted list of all icon type strings used by items."""
    try:
        raw = _load("items.json", data_dir)
    except (OSError, ValueError):
        return []
    icons = set()
    for section in ("weapons", "armors", "general"):
        for entry in raw.get(section, {}).values():
            ic = entry.get("icon", "")
            if ic:
                icons.add(ic)
    return sorted(icons)


def all_monster_tiles(data_dir=None):
    """Return sorted list of all monster tile paths from monsters.json."""
    try:
        data = _load("monsters.json", data_dir)
    except (OSError, ValueError):
        return []
    tiles = set()
    for entry in data.get("monsters", {}).values():
        t = entry.get("tile", "")
        if t:
            tiles.add(t)
    return sorted(tiles)


def all_overworld_tile_names():
    """Return sorted list of overworld tile names from the manifest."""
    try:
        data = _load("tile_manifest.json")
    except (OSError, ValueError):
        return []
    ow = data.get("overworld", {})
    return sorted(k for k, v in ow.items()
                  if isinstance(v, dict) and "path" in v)


def all_tile_sprite_paths():
    """Return sorted list of all tile sprite paths from the manifest.

    Includes overworld, town, and dungeon categories — every sprite
    that can be assigned to a tile type.  Each entry is
    ``"category/name"`` (e.g. ``"overworld/grass"``).
    """
    try:
        data = _load("tile_manifest.json")
    except (OSError, ValueError):
        return []
    results = []
    for cat in ("overworld", "town", "dungeon", "unique_tiles", "objects"):
        section = data.get(cat, {})
        if not isinstance(section, dict):
            continue
        for name, entry in sorted(section.items()):
            if isinstance(entry, dict) and "path" in entry:
                results.append(f"{cat}/{name}")
    return results


def all_spell_icon_options():
    """Return sorted list of available spell icon identifiers.

    Currently includes effect-type names as placeholders since
    dedicated spell sprites don't exist yet.  As spell graphics
    are added to the manifest, this list will grow.
    """
    try:
        data = _load("tile_manifest.json")
    except (OSError, ValueError):
        data = {}

    # Pull any existing "spells" or "effects" manifest entries
    icons = set()
    for cat in ("spells", "effects"):
        section = data.get(cat, {})
        if isinstance(section, dict):
            for name, entry in section.items():
                if isinstance(entry, dict) and "path" in entry:
                    icons.add(name)

    # Also include all unique_tiles and objects as possible spell icons
    for cat in ("unique_tiles", "objects"):
        section = data.get(cat, {})
        if isinstance(section, dict):
            for name, entry in section.items():
                if isinstance(entry, dict) and "path" in entry:
                    icons.add(f"{cat}/{name}")

    # Include base effect-type names as placeholders
    base = {
        "damage", "heal", "ac_buff", "sleep", "teleport",
        "charm", "invisibility", "lightning_bolt", "aoe_fireball",
        "cure_poison", "magic_light", "undead_damage", "bless",
        "curse", "summon_skeleton",
    }
    icons.update(base)
    return sorted(icons)
