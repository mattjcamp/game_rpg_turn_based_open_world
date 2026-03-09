"""
Module loader — scans the modules/ directory for available game modules.

Each module is a subdirectory containing a module.json manifest file.
The manifest provides metadata (name, author, description, version)
and references to all game data files needed to run a complete adventure.
"""

import json
import os


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


def create_module(name, author="Unknown", description=""):
    """Create a new module directory with a minimal module.json manifest.

    Parameters
    ----------
    name : str
        Display name for the module (e.g. "My Adventure").
    author : str
        Author name.
    description : str
        Short description.

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
            "map_width": 64,
            "map_height": 48,
            "viewport_cols": 30,
            "viewport_rows": 26,
            "max_party_size": 4,
            "max_roster_size": 20,
        },
        "data": {},
        "world": {
            "overworld": None,
            "towns": [
                {"id": "town_1", "name": "Town 1"},
            ],
            "dungeons": [],
        },
        "progression": {
            "win_condition": {
                "type": "collect_keys",
                "total_keys": 1,
                "deliver_to": "town_machine",
            },
            "starting_quests": [],
            "key_dungeons": [
                {
                    "id": "dungeon_key_1",
                    "name": "Dungeon 1",
                    "key_name": "Key 1",
                    "dungeon_number": 1,
                    "landmark_id": "dungeon_1",
                },
            ],
        },
    }

    manifest_path = os.path.join(mod_dir, "module.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

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
        world_size : str  — "Small", "Medium", "Large", or "Custom"
        num_towns  : int  — number of towns
        num_quests : int  — number of key-dungeon quests

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

    return {
        "world_size": _world_size_label(settings),
        "num_towns": len(world.get("towns", [])),
        "num_quests": len(progression.get("key_dungeons", [])),
    }


def update_module_settings(module_path, *, world_size=None,
                           num_towns=None, num_quests=None):
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
        # Grow or shrink the list
        while len(towns) < num_towns:
            idx = len(towns) + 1
            towns.append({
                "id": f"town_{idx}",
                "name": f"Town {idx}",
            })
        towns = towns[:num_towns]
        world["towns"] = towns

    # ── Number of quests (key dungeons) ──
    if num_quests is not None:
        num_quests = max(0, int(num_quests))
        progression = data.setdefault("progression", {})
        dungeons = progression.get("key_dungeons", [])
        while len(dungeons) < num_quests:
            idx = len(dungeons) + 1
            dungeons.append({
                "id": f"dungeon_key_{idx}",
                "name": f"Dungeon {idx}",
                "key_name": f"Key {idx}",
                "dungeon_number": idx,
                "landmark_id": f"dungeon_{idx}",
            })
        dungeons = dungeons[:num_quests]
        progression["key_dungeons"] = dungeons
        # Keep win_condition total_keys in sync
        win = progression.get("win_condition", {})
        if win.get("type") == "collect_keys":
            win["total_keys"] = num_quests

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
