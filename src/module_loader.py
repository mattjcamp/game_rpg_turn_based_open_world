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
