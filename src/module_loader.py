"""
Module loader — scans the modules/ directory for available game modules.

Each module is a subdirectory containing a module.json manifest file.
The manifest provides metadata (name, author, description, version)
and references to all game data files needed to run a complete adventure.
"""

import json
import math
import os
import random


_MODULES_DIR = os.path.join(os.path.dirname(__file__), "..", "modules")


def scan_modules():
    """Scan the modules/ directory and return a list of module info dicts.

    Each dict contains:
        id          : str — unique module identifier
        name        : str — display name
        author      : str — module creator
        description : str — short description of the adventure
        version     : str — semver string
        path        : str — absolute path to the module directory
    """
    if not os.path.isdir(_MODULES_DIR):
        return []

    results = []
    for entry in sorted(os.listdir(_MODULES_DIR)):
        mod_path = os.path.join(_MODULES_DIR, entry)
        manifest = os.path.join(mod_path, "module.json")
        if not os.path.isdir(mod_path) or not os.path.isfile(manifest):
            continue
        try:
            with open(manifest, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue  # skip broken manifests silently

        meta = data.get("metadata", {})
        results.append({
            "id": meta.get("id", entry),
            "name": meta.get("name", entry),
            "author": meta.get("author", "Unknown"),
            "description": meta.get("description", ""),
            "version": meta.get("version", "0.0.0"),
            "path": os.path.abspath(mod_path),
        })

    return results


# ── Content generators ───────────────────────────────────────────────
# These produce unique, flavourful names for towns, dungeons, and keys
# so that every new module feels fresh.

_TOWN_PREFIXES = [
    "Thorn", "Iron", "Stone", "Ember", "Frost", "Storm", "Raven",
    "Oak", "Willow", "Copper", "Silver", "Amber", "Ash", "Briar",
    "Cedar", "Drift", "Elder", "Fern", "Gale", "Hallow", "Ivy",
    "Jade", "Kestrel", "Lark", "Maple", "Nettle",
]
_TOWN_SUFFIXES = [
    "wall", "haven", "ford", "vale", "brook", "shire", "hold",
    "gate", "moor", "field", "crest", "reach", "march", "dale",
    "wood", "glen", "port", "keep", "ridge", "hollow",
]

_DUNGEON_ADJECTIVES = [
    "Sunken", "Forsaken", "Howling", "Silent", "Burning", "Frozen",
    "Rotting", "Crumbling", "Forgotten", "Cursed", "Hidden", "Lost",
    "Ruined", "Shattered", "Twisted", "Flooded", "Blighted", "Iron",
    "Obsidian", "Crimson", "Ashen",
]
_DUNGEON_NOUNS = [
    "Crypt", "Cavern", "Warren", "Tunnels", "Depths", "Mines",
    "Tomb", "Lair", "Vaults", "Catacombs", "Halls", "Pit",
    "Stronghold", "Sanctum", "Barrow", "Grotto", "Keep",
    "Labyrinth", "Den", "Ruins",
]

# ── Quest types ────────────────────────────────────────────────────
QUEST_TYPE_NAMES = ["Retrieve Artifact", "Kill Monsters"]
QUEST_TYPE_KEYS = ["retrieve", "kill"]  # internal keys matching names

QUEST_STYLE_NAMES = ["Elder", "Gnome Machine"]
QUEST_STYLE_KEYS = ["elder", "gnome_machine"]  # internal keys matching names

# Monsters that can be targets for kill quests
KILL_QUEST_MONSTERS = [
    "Giant Rat", "Skeleton", "Orc", "Goblin", "Zombie",
    "Wolf", "Dark Mage", "Troll", "Orc Shaman",
]

# All monsters available for encounter editing (includes Skeleton Archer)
ENCOUNTER_MONSTERS = [
    "Giant Rat", "Skeleton", "Skeleton Archer", "Orc", "Goblin",
    "Zombie", "Wolf", "Dark Mage", "Troll", "Orc Shaman",
]

# Items available for starting loot selection in the module editor
LOOT_ITEMS = [
    "Healing Herb", "Healing Potion", "Antidote", "Torch",
    "Lockpick", "Rock", "Stones", "Arrows", "Bolts",
    "Camping Supplies", "Fire Oil", "Spring Water",
    "Glowcap Mushroom", "Moonpetal", "Serpent Root", "Brimite Ore",
    "Smoke Bomb", "Holy Water", "Mana Potion", "Rope",
    "Elixir of Strength", "Elixir of Warding",
    "Poison Vial", "Lingering Venom", "Paralytic Poison",
    "Weakening Poison",
    "Dagger", "Club", "Sword", "Axe", "Mace", "Spear",
    "Short Bow", "Long Bow", "Sling", "Crossbow",
    "Cloth", "Leather", "Chain", "Gloves",
]

_KEY_MATERIALS = [
    "Iron", "Bronze", "Silver", "Gold", "Crystal", "Ruby",
    "Obsidian", "Diamond", "Jade", "Onyx", "Amber", "Ivory",
    "Copper", "Platinum", "Emerald", "Sapphire", "Coral",
    "Moonstone", "Opal", "Amethyst",
]

# Per-dungeon description templates — shown when the player approaches.
# {name} is replaced with the dungeon's generated name.
_DUNGEON_DESCRIPTIONS = [
    "The entrance to {name} gapes like a wound in the hillside. "
    "A cold draught carries the scent of damp stone.",
    "Crumbling pillars mark the way into {name}. "
    "Faint scratching echoes from deep within.",
    "Thick vines choke the mouth of {name}. "
    "Beyond them, torchlight flickers in the gloom.",
    "A rusted iron gate bars the path into {name}. "
    "It swings open with a tortured groan at your touch.",
    "Water seeps from the walls near {name}'s entrance. "
    "The stone steps descend into darkness.",
    "Bones litter the threshold of {name}. "
    "Whatever guards this place does not welcome visitors.",
    "The air around {name} shimmers with faint heat. "
    "Strange runes glow along the doorframe.",
    "A narrow crevice leads into {name}. "
    "The sound of dripping water echoes endlessly below.",
    "Moss-covered statues flank the entrance to {name}. "
    "Their blank eyes seem to follow you.",
    "A spiral staircase carved from bedrock descends into {name}. "
    "The temperature drops with every step.",
]

# Individual quest objective templates — one assigned per dungeon so each
# quest feels unique.  {key} is replaced with the key/artifact name.
# {dungeon} is replaced with the dungeon name.
_QUEST_OBJECTIVES = [
    {
        "objective": "Retrieve the {key} from {dungeon}",
        "hint": "A powerful artifact lies in the deepest chamber.",
    },
    {
        "objective": "Slay the guardian of {dungeon} and claim the {key}",
        "hint": "A fearsome creature guards the prize.",
    },
    {
        "objective": "Explore {dungeon} and recover the lost {key}",
        "hint": "The artifact was hidden here long ago by a forgotten order.",
    },
    {
        "objective": "Brave the depths of {dungeon} for the {key}",
        "hint": "Few who enter these halls return unchanged.",
    },
    {
        "objective": "Purge {dungeon} of evil and secure the {key}",
        "hint": "Dark forces have claimed this place as their own.",
    },
    {
        "objective": "Descend into {dungeon} and find the {key}",
        "hint": "The passage grows more treacherous with every floor.",
    },
    {
        "objective": "Search {dungeon} for the hidden {key}",
        "hint": "Rumors say it was sealed away behind deadly traps.",
    },
    {
        "objective": "Venture into {dungeon} and liberate the {key}",
        "hint": "The artifact pulses with ancient energy.",
    },
]

# Quest themes — each defines a narrative arc different from the gnome quest.
# The win_condition remains "collect_keys" for now, but the flavour changes.
_QUEST_THEMES = [
    {
        "quest_prefix": "restore",
        "deliver_to": "town_altar",
        "description_template": (
            "Ancient seals have been scattered across the land. "
            "Recover them from dangerous dungeons and return them "
            "to the altar in {town} to restore the protective ward."
        ),
    },
    {
        "quest_prefix": "reclaim",
        "deliver_to": "town_vault",
        "description_template": (
            "The royal treasury was plundered and its relics hidden "
            "in dungeons across the realm. Reclaim them and return "
            "them to the vault in {town}."
        ),
    },
    {
        "quest_prefix": "awaken",
        "deliver_to": "town_shrine",
        "description_template": (
            "The land sleeps under an enchantment. Gather the "
            "awakening crystals from the dungeons and bring them "
            "to the shrine in {town} to break the spell."
        ),
    },
    {
        "quest_prefix": "defend",
        "deliver_to": "town_armory",
        "description_template": (
            "An invasion threatens the realm. Forge powerful "
            "weapons from artifacts hidden in treacherous dungeons "
            "and deliver them to the armory in {town}."
        ),
    },
    {
        "quest_prefix": "purify",
        "deliver_to": "town_fountain",
        "description_template": (
            "A creeping corruption poisons the rivers and fields. "
            "Find the purification stones in the dungeons and "
            "cleanse the sacred fountain in {town}."
        ),
    },
]


_TOWN_DESCRIPTIONS = [
    "A bustling market town where traders from distant lands hawk exotic wares.",
    "A quiet hamlet nestled among rolling hills, known for its warm hearths.",
    "A fortified settlement perched on a rocky bluff overlooking the valley.",
    "A riverside town whose docks hum with the comings and goings of barges.",
    "A sleepy village surrounded by ancient oaks and whispering meadows.",
    "A crossroads town where adventurers gather to share rumours and ale.",
    "A walled outpost on the frontier, always on guard against the wilds.",
    "A seaside port battered by salt winds and rich with the smell of fish.",
    "A hillside town whose cobbled streets wind between stone cottages.",
    "A forest clearing settlement where druids and woodsmen live side by side.",
]


def _generate_town_names(count):
    """Return *count* unique town names."""
    names = set()
    attempts = 0
    while len(names) < count and attempts < 200:
        name = random.choice(_TOWN_PREFIXES) + random.choice(_TOWN_SUFFIXES)
        names.add(name)
        attempts += 1
    # Fall back to numbered names if we somehow can't get enough unique ones
    result = list(names)
    while len(result) < count:
        result.append(f"Town {len(result) + 1}")
    return result[:count]


def _generate_dungeon_entries(count, key_materials=None):
    """Return *count* dungeon dicts with unique names, keys, descriptions,
    and quest objectives so every dungeon feels individual."""
    if key_materials is None:
        key_materials = list(_KEY_MATERIALS)
        random.shuffle(key_materials)

    # Shuffle descriptions and objectives so each dungeon gets a unique one
    descriptions = list(_DUNGEON_DESCRIPTIONS)
    random.shuffle(descriptions)
    objectives = list(_QUEST_OBJECTIVES)
    random.shuffle(objectives)

    used_names = set()
    entries = []
    for i in range(count):
        # Pick a unique dungeon name
        attempts = 0
        while attempts < 100:
            adj = random.choice(_DUNGEON_ADJECTIVES)
            noun = random.choice(_DUNGEON_NOUNS)
            dname = f"{adj} {noun}"
            if dname not in used_names:
                used_names.add(dname)
                break
            attempts += 1
        else:
            dname = f"Dungeon {i + 1}"

        # Pick a key material (cycle if we run out)
        material = key_materials[i % len(key_materials)]
        key_name = f"{material} Key"

        # Unique description for this dungeon
        desc = descriptions[i % len(descriptions)].format(name=dname)

        # Unique quest objective for this dungeon
        obj = objectives[i % len(objectives)]
        quest_objective = obj["objective"].format(key=key_name, dungeon=dname)
        quest_hint = obj["hint"]

        entries.append({
            "id": f"dungeon_key_{i + 1}",
            "name": dname,
            "key_name": key_name,
            "dungeon_number": i + 1,
            "landmark_id": f"dungeon_{i + 1}",
            "description": desc,
            "quest_type": "retrieve",
            "quest_objective": quest_objective,
            "quest_hint": quest_hint,
            "kill_target": "",
            "kill_count": 0,
        })
    return entries


def _generate_overworld_json(map_w, map_h, towns, key_dungeons,
                             deliver_to="town_altar"):
    """Build an overworld.json dict with procedurally placed landmarks.

    Landmarks are arranged radially:
    - Towns near the map center
    - Dungeons fanning outward in order of dungeon_number
    - A delivery-point landmark beside the first town

    Also generates paths from the start position to the first town,
    from each town to nearby dungeons, etc.
    """
    cx, cy = map_w // 2, map_h // 2
    # Keep landmarks inside a safe margin so they're not in the ocean
    margin_x = max(6, map_w // 6)
    margin_y = max(5, map_h // 6)

    def _clamp(col, row):
        return (max(margin_x, min(map_w - margin_x, col)),
                max(margin_y, min(map_h - margin_y, row)))

    landmarks = []
    paths = []

    # ── Place towns in a ring close to center ──
    town_radius = min(map_w, map_h) // 6
    town_positions = []
    for i, town in enumerate(towns):
        angle = (2 * math.pi * i / max(len(towns), 1)) - math.pi / 2
        tc = int(cx + town_radius * math.cos(angle))
        tr = int(cy + town_radius * math.sin(angle))
        tc, tr = _clamp(tc, tr)
        town_positions.append((tc, tr))
        landmarks.append({
            "id": town["id"],
            "type": "town",
            "col": tc,
            "row": tr,
            "tile": "TILE_TOWN",
            "clear_radius": 3,
        })

    # ── Place delivery point next to first town ──
    if town_positions:
        dc = town_positions[0][0] + 2
        dr = town_positions[0][1]
        dc, dr = _clamp(dc, dr)
    else:
        dc, dr = cx + 2, cy
    landmarks.append({
        "id": deliver_to,
        "type": "machine",
        "col": dc,
        "row": dr,
        "tile": "TILE_MACHINE",
        "clear_radius": 1,
    })

    # ── Place dungeons in an outer ring ──
    dungeon_radius_base = min(map_w, map_h) // 4
    for i, dung in enumerate(key_dungeons):
        angle = (2 * math.pi * i / max(len(key_dungeons), 1))
        # Dungeons spread further out as dungeon_number increases
        spread = dungeon_radius_base + (i * 2)
        dc2 = int(cx + spread * math.cos(angle))
        dr2 = int(cy + spread * math.sin(angle))
        dc2, dr2 = _clamp(dc2, dr2)
        landmarks.append({
            "id": dung["landmark_id"],
            "type": "dungeon",
            "col": dc2,
            "row": dr2,
            "tile": "TILE_DUNGEON",
            "clear_radius": 2,
        })
        # Path from nearest town to this dungeon
        if town_positions:
            nearest = min(town_positions,
                          key=lambda p: abs(p[0]-dc2) + abs(p[1]-dr2))
            paths.append({"from": list(nearest), "to": [dc2, dr2]})

    # ── Paths between towns ──
    for i in range(len(town_positions) - 1):
        paths.append({
            "from": list(town_positions[i]),
            "to": list(town_positions[i + 1]),
        })

    # ── Start position near first town ──
    if town_positions:
        start_col = town_positions[0][0]
        start_row = min(town_positions[0][1] + 2, map_h - margin_y)
    else:
        start_col, start_row = cx, cy + 2

    # Path from start to first town
    if town_positions:
        paths.append({
            "from": [start_col, start_row],
            "to": list(town_positions[0]),
        })

    return {
        "size": {"width": map_w, "height": map_h},
        "start_position": {"col": start_col, "row": start_row},
        "landmarks": landmarks,
        "paths": paths,
    }


def create_module(name, author="Unknown", description="",
                  world_size="Medium", num_towns=1, num_quests=1,
                  season="Summer", time_of_day="Noon"):
    """Create a new module directory with a fully scaffolded module.json.

    Parameters
    ----------
    name : str
        Display name for the module (e.g. "My Adventure").
    author : str
        Author name.
    description : str
        Short description.
    world_size : str
        One of "Small", "Medium", "Large".
    num_towns : int
        Number of towns to scaffold.
    num_quests : int
        Number of key-dungeon quests to scaffold.
    season : str
        Starting season — "Spring", "Summer", "Autumn", or "Winter".
    time_of_day : str
        Starting time — "Dawn", "Noon", "Dusk", or "Midnight".

    Returns
    -------
    str
        Absolute path to the newly created module directory.
    """
    # Derive a filesystem-safe id from the name
    mod_id = name.lower().replace(" ", "_")
    mod_id = "".join(c for c in mod_id if c.isalnum() or c == "_")
    if not mod_id:
        mod_id = "new_module"

    mod_dir = os.path.join(_MODULES_DIR, mod_id)
    # Ensure unique directory name
    base_dir = mod_dir
    counter = 2
    while os.path.exists(mod_dir):
        mod_dir = f"{base_dir}_{counter}"
        mod_id = os.path.basename(mod_dir)
        counter += 1

    os.makedirs(mod_dir, exist_ok=True)

    # Resolve world-size dimensions
    dims = WORLD_SIZE_PRESETS.get(world_size, WORLD_SIZE_PRESETS["Medium"])

    # Resolve start_time from season + time_of_day
    start_time = _build_start_time(season, time_of_day)

    # Build towns list with unique generated names and descriptions
    num_towns = max(0, int(num_towns))
    town_names = _generate_town_names(num_towns)
    town_descs = list(_TOWN_DESCRIPTIONS)
    random.shuffle(town_descs)
    towns = []
    for i, tname in enumerate(town_names):
        town_id = tname.lower().replace(" ", "_")
        tdesc = town_descs[i % len(town_descs)] if town_descs else ""
        towns.append({"id": town_id, "name": tname,
                      "description": tdesc})

    # Build key_dungeons with unique dungeon/key names
    num_quests = max(0, int(num_quests))
    key_dungeons = _generate_dungeon_entries(num_quests)

    # Pick a quest theme and auto-generate a description if empty
    theme = random.choice(_QUEST_THEMES)
    hub_town = town_names[0] if town_names else "the capital"
    if not description:
        description = theme["description_template"].format(town=hub_town)

    manifest = {
        "metadata": {
            "id": mod_id,
            "name": name,
            "author": author,
            "description": description,
            "version": "0.1.0",
        },
        "settings": {
            "tile_size": 32,
            "map_width": dims["map_width"],
            "map_height": dims["map_height"],
            "viewport_cols": 30,
            "viewport_rows": 26,
            "max_party_size": 4,
            "max_roster_size": 20,
            "start_time": start_time,
        },
        "data": {},
        "world": {
            "overworld": "overworld.json",
            "towns": towns,
            "dungeons": [],
        },
        "progression": {
            "win_condition": {
                "type": "collect_keys",
                "total_keys": num_quests,
                "deliver_to": theme["deliver_to"],
            },
            "starting_quests": [theme["quest_prefix"]],
            "key_dungeons": key_dungeons,
        },
    }

    manifest_path = os.path.join(mod_dir, "module.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # ── Generate the overworld.json with landmarks ──
    overworld = _generate_overworld_json(
        dims["map_width"], dims["map_height"],
        towns, key_dungeons,
        deliver_to=theme["deliver_to"],
    )
    overworld_path = os.path.join(mod_dir, "overworld.json")
    with open(overworld_path, "w") as f:
        json.dump(overworld, f, indent=2)

    return os.path.abspath(mod_dir)


def delete_module(module_path):
    """Delete a module directory and all its contents.

    Parameters
    ----------
    module_path : str
        Absolute path to the module directory.

    Returns
    -------
    bool
        True if the module was deleted, False otherwise.
    """
    import shutil
    # Safety: only delete directories inside the modules/ folder
    modules_abs = os.path.abspath(_MODULES_DIR)
    target_abs = os.path.abspath(module_path)
    if not target_abs.startswith(modules_abs + os.sep):
        return False
    if not os.path.isdir(target_abs):
        return False
    try:
        shutil.rmtree(target_abs)
        return True
    except OSError:
        return False


def update_module_metadata(module_path, **kwargs):
    """Update metadata fields in a module's module.json.

    Supported keyword arguments: name, author, description, version.
    Only provided fields are updated; others are left untouched.

    Returns True on success, False on failure.
    """
    manifest_path = os.path.join(module_path, "module.json")
    if not os.path.isfile(manifest_path):
        return False
    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    meta = data.setdefault("metadata", {})
    for key in ("name", "author", "description", "version"):
        if key in kwargs:
            meta[key] = kwargs[key]

    with open(manifest_path, "w") as f:
        json.dump(data, f, indent=2)
    return True


# ── World-size presets ──────────────────────────────────────────────
WORLD_SIZE_PRESETS = {
    "Small":  {"map_width": 32, "map_height": 24},
    "Medium": {"map_width": 64, "map_height": 48},
    "Large":  {"map_width": 128, "map_height": 96},
}

WORLD_SIZE_NAMES = list(WORLD_SIZE_PRESETS.keys())   # ["Small", "Medium", "Large"]

# ── Season / time-of-day presets ────────────────────────────────────
SEASON_NAMES = ["Spring", "Summer", "Autumn", "Winter"]
TIME_OF_DAY_NAMES = ["Dawn", "Noon", "Dusk", "Midnight"]

_SEASON_MONTHS = {"Spring": 3, "Summer": 6, "Autumn": 9, "Winter": 12}
_TIME_HOURS = {"Dawn": 6, "Noon": 12, "Dusk": 18, "Midnight": 0}


def _build_start_time(season, time_of_day):
    """Return a start_time dict from human-readable season + time."""
    return {
        "year": 1,
        "month": _SEASON_MONTHS.get(season, 6),
        "day": 1,
        "hour": _TIME_HOURS.get(time_of_day, 12),
        "minute": 0,
    }


def _season_from_month(month):
    """Return the season name for a given month number."""
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    if month in (9, 10, 11):
        return "Autumn"
    return "Winter"


def _time_of_day_from_hour(hour):
    """Return the closest time-of-day label for an hour."""
    if 3 <= hour < 9:
        return "Dawn"
    if 9 <= hour < 15:
        return "Noon"
    if 15 <= hour < 21:
        return "Dusk"
    return "Midnight"


def _world_size_label(settings):
    """Return the preset label that matches map_width/map_height, or 'Custom'."""
    w = settings.get("map_width")
    h = settings.get("map_height")
    for label, dims in WORLD_SIZE_PRESETS.items():
        if dims["map_width"] == w and dims["map_height"] == h:
            return label
    return "Custom"


def get_module_settings(module_path):
    """Read settings and progression from a module manifest.

    Returns a dict with:
        world_size  : str  — "Small", "Medium", "Large", or "Custom"
        num_towns   : int  — number of towns
        num_quests  : int  — number of key-dungeon quests
        season      : str  — "Spring", "Summer", "Autumn", or "Winter"
        time_of_day : str  — "Dawn", "Noon", "Dusk", or "Midnight"

    Returns None on failure.
    """
    manifest_path = os.path.join(module_path, "module.json")
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    settings = data.get("settings", {})
    world = data.get("world", {})
    progression = data.get("progression", {})

    start_time = settings.get("start_time", {})
    month = start_time.get("month", 6)
    hour = start_time.get("hour", 12)

    return {
        "world_size": _world_size_label(settings),
        "num_towns": len(world.get("towns", [])),
        "num_quests": len(progression.get("key_dungeons", [])),
        "season": _season_from_month(month),
        "time_of_day": _time_of_day_from_hour(hour),
    }


def update_module_settings(module_path, *, world_size=None,
                           num_towns=None, num_quests=None,
                           season=None, time_of_day=None):
    """Update world/gameplay settings in a module's module.json.

    Parameters
    ----------
    module_path : str
        Absolute path to the module directory.
    world_size : str, optional
        One of "Small", "Medium", "Large".  Sets map_width and map_height.
    num_towns : int, optional
        Desired number of towns.  Adjusts the ``world.towns`` list length
        (adds placeholder entries or trims from the end).
    num_quests : int, optional
        Desired number of key-dungeon quests.  Adjusts
        ``progression.key_dungeons`` list length.
    season : str, optional
        One of "Spring", "Summer", "Autumn", "Winter".
    time_of_day : str, optional
        One of "Dawn", "Noon", "Dusk", "Midnight".

    Returns True on success, False on failure.
    """
    manifest_path = os.path.join(module_path, "module.json")
    if not os.path.isfile(manifest_path):
        return False
    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    # ── World size ──
    if world_size and world_size in WORLD_SIZE_PRESETS:
        settings = data.setdefault("settings", {})
        dims = WORLD_SIZE_PRESETS[world_size]
        settings["map_width"] = dims["map_width"]
        settings["map_height"] = dims["map_height"]

    # ── Number of towns ──
    if num_towns is not None:
        num_towns = max(0, int(num_towns))
        world = data.setdefault("world", {})
        towns = world.get("towns", [])
        # Grow — generate unique names for new towns
        if len(towns) < num_towns:
            existing_names = {t.get("name", "") for t in towns}
            needed = num_towns - len(towns)
            new_names = _generate_town_names(needed + 10)
            descs = list(_TOWN_DESCRIPTIONS)
            random.shuffle(descs)
            added = 0
            for tname in new_names:
                if added >= needed:
                    break
                if tname in existing_names:
                    continue
                town_id = tname.lower().replace(" ", "_")
                tdesc = descs[added % len(descs)] if descs else ""
                towns.append({"id": town_id, "name": tname,
                              "description": tdesc})
                existing_names.add(tname)
                added += 1
        towns = towns[:num_towns]
        world["towns"] = towns

    # ── Number of quests (key dungeons) ──
    if num_quests is not None:
        num_quests = max(0, int(num_quests))
        progression = data.setdefault("progression", {})
        dungeons = progression.get("key_dungeons", [])
        # Grow — generate unique dungeon entries
        if len(dungeons) < num_quests:
            needed = num_quests - len(dungeons)
            existing_names = {d.get("name", "") for d in dungeons}
            existing_keys = {d.get("key_name", "") for d in dungeons}
            new_entries = _generate_dungeon_entries(needed + 10)
            added = 0
            for entry in new_entries:
                if added >= needed:
                    break
                if entry["name"] in existing_names:
                    continue
                if entry["key_name"] in existing_keys:
                    continue
                # Re-number to follow existing entries
                idx = len(dungeons) + 1
                entry["id"] = f"dungeon_key_{idx}"
                entry["dungeon_number"] = idx
                entry["landmark_id"] = f"dungeon_{idx}"
                dungeons.append(entry)
                existing_names.add(entry["name"])
                existing_keys.add(entry["key_name"])
                added += 1
        dungeons = dungeons[:num_quests]
        progression["key_dungeons"] = dungeons
        # Keep win_condition total_keys in sync
        win = progression.get("win_condition", {})
        if win.get("type") == "collect_keys":
            win["total_keys"] = num_quests

    # ── Season / time of day ──
    if season or time_of_day:
        settings = data.setdefault("settings", {})
        start_time = settings.setdefault("start_time", {
            "year": 1, "month": 6, "day": 1, "hour": 12, "minute": 0,
        })
        if season and season in _SEASON_MONTHS:
            start_time["month"] = _SEASON_MONTHS[season]
        if time_of_day and time_of_day in _TIME_HOURS:
            start_time["hour"] = _TIME_HOURS[time_of_day]

    with open(manifest_path, "w") as f:
        json.dump(data, f, indent=2)
    return True


def get_default_module_path():
    """Return the absolute path to the default module (keys_of_shadow)."""
    return os.path.abspath(os.path.join(_MODULES_DIR, "keys_of_shadow"))


def load_module_data(module_path):
    """Load (or reload) all game data from a module directory.

    Reads the module's ``module.json`` manifest to determine which data
    files to load.  For any file missing from the module, the loaders
    automatically fall back to the default ``data/`` directory.

    This function calls the reload helpers on every data-owning module
    so that their module-level globals are updated in place:

    - ``party.reload_module_data()``  — items, races, effects, spells,
      class templates
    - ``monster.reload_module_data()`` — monsters, spawn tables, encounters

    Parameters
    ----------
    module_path : str
        Absolute path to the module directory (containing ``module.json``).

    Returns
    -------
    dict
        The parsed ``module.json`` manifest, which callers can use to
        read settings, world definitions, progression info, etc.
    """
    manifest_path = os.path.join(module_path, "module.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # The module's data files live alongside module.json
    data_dir = module_path

    # ── Reload party data (items, races, effects, spells, classes) ──
    from src.party import reload_module_data as _reload_party
    _reload_party(data_dir)

    # ── Reload monster & encounter data ─────────────────────────────
    from src.monster import reload_module_data as _reload_monsters
    _reload_monsters(data_dir)

    # ── Load overworld config if referenced in the manifest ──────────
    world = manifest.get("world", {})
    overworld_file = world.get("overworld")
    if overworld_file:
        ow_path = os.path.join(module_path, overworld_file)
        if os.path.isfile(ow_path):
            with open(ow_path, "r") as f:
                manifest["_overworld_cfg"] = json.load(f)

    return manifest
