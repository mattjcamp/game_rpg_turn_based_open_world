"""
Map representation and procedural overworld generator.

The map is a 2D grid of tile IDs (see settings.py for tile definitions).
The overworld is generated fresh each new game using layered value-noise
terrain with an island mask, rivers, paths, and hand-placed landmarks.
"""

import json
import math
import os
import random

from src.settings import *


class TileMap:
    """Holds a 2D grid of tile IDs and provides access methods."""

    def __init__(self, width, height, default_tile=TILE_GRASS,
                 oob_tile=None):
        self.width = width
        self.height = height
        # Tile returned for out-of-bounds queries (default: TILE_WATER)
        self.oob_tile = oob_tile if oob_tile is not None else TILE_WATER
        # 2D list: self.tiles[row][col]
        self.tiles = [[default_tile for _ in range(width)] for _ in range(height)]
        # Sprite overrides: (col, row) -> asset path from custom layouts
        # Used so the runtime renderer matches the editor's visuals.
        self.sprite_overrides = {}
        # Unique tiles: (col, row) -> tile definition dict from unique_tiles.json
        self.unique_tiles = {}
        # Tracks which unique tiles have already been triggered (one_time)
        self.triggered_unique = set()
        # Cooldown timers: tile_id -> remaining steps
        self.unique_cooldowns = {}
        # Overworld interior data (populated by load_static_overworld)
        self.overworld_interiors = [] # list of interior dicts

    def get_tile(self, col, row):
        """Get tile ID at (col, row). Returns oob_tile for out-of-bounds."""
        if 0 <= col < self.width and 0 <= row < self.height:
            return self.tiles[row][col]
        return self.oob_tile

    def set_tile(self, col, row, tile_id):
        """Set tile ID at (col, row)."""
        if 0 <= col < self.width and 0 <= row < self.height:
            self.tiles[row][col] = tile_id

    def is_walkable(self, col, row):
        """Check if a tile can be walked on."""
        tile_id = self.get_tile(col, row)
        return TILE_DEFS.get(tile_id, {}).get("walkable", False)

    def get_tile_name(self, col, row):
        """Get the display name of a tile."""
        tile_id = self.get_tile(col, row)
        return TILE_DEFS.get(tile_id, {}).get("name", "Unknown")

    # ── Unique tile methods ──────────────────────────────────────

    def place_unique(self, col, row, tile_id, tile_def):
        """Place a unique tile at (col, row).

        tile_id  : str — key from unique_tiles.json (e.g. "ancient_shrine")
        tile_def : dict — the full definition from the JSON
        """
        self.unique_tiles[(col, row)] = {
            "id": tile_id,
            **tile_def,
        }

    def get_unique(self, col, row):
        """Return the unique tile dict at (col, row), or None."""
        return self.unique_tiles.get((col, row))

    def is_unique_triggered(self, col, row):
        """Check if a one-time unique tile has already been triggered."""
        return (col, row) in self.triggered_unique

    def mark_unique_triggered(self, col, row):
        """Mark a one-time unique tile as triggered."""
        self.triggered_unique.add((col, row))

    def is_unique_on_cooldown(self, col, row):
        """Check if a unique tile is still on cooldown."""
        return self.unique_cooldowns.get((col, row), 0) > 0

    def set_unique_cooldown(self, col, row, steps):
        """Set cooldown for a unique tile."""
        self.unique_cooldowns[(col, row)] = steps

    def tick_cooldowns(self):
        """Decrement all unique tile cooldowns by 1 step (call each move)."""
        expired = []
        for key in self.unique_cooldowns:
            self.unique_cooldowns[key] -= 1
            if self.unique_cooldowns[key] <= 0:
                expired.append(key)
        for key in expired:
            del self.unique_cooldowns[key]


# ── Static overworld loader ────────────────────────────────────

def load_static_overworld(module_path):
    """Load a pre-generated static overworld map from a module.

    Checks two sources in order:
      1. ``static_overworld.json`` — a full static overworld with unique
         tiles, tile links, and interiors.
      2. ``overview_map.json`` — the module editor's overview map, which
         stores tiles inside a ``map_config`` wrapper.

    Returns a fully-populated :class:`TileMap`, or ``None`` so the caller
    can fall back to procedural generation.
    """
    # ── 1. Try static_overworld.json (full format) ──
    static_path = os.path.join(module_path, "static_overworld.json")
    if os.path.isfile(static_path):
        try:
            with open(static_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = None
        if data:
            w = data.get("width", 0)
            h = data.get("height", 0)
            tiles = data.get("tiles")
            if w > 0 and h > 0 and tiles and len(tiles) == h:
                tmap = TileMap(w, h, default_tile=TILE_GRASS)
                tmap.tiles = tiles
                tmap.seed = data.get("seed", 0)

                for ut in data.get("unique_tile_placements", []):
                    c, r = ut.get("col", 0), ut.get("row", 0)
                    uid = ut.get("id", "")
                    udef = ut.get("def", {})
                    if uid:
                        tmap.place_unique(c, r, uid, udef)

                tmap.overworld_interiors = data.get("interiors", [])
                tmap.tile_properties = data.get("tile_properties", {})
                return tmap

    # ── 2. Try overview_map.json (module editor format) ──
    overview_path = os.path.join(module_path, "overview_map.json")
    if os.path.isfile(overview_path):
        try:
            with open(overview_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = None
        if data:
            mc = data.get("map_config", {})
            w = mc.get("width", 0)
            h = mc.get("height", 0)
            tiles = data.get("tiles")
            if w > 0 and h > 0 and tiles and len(tiles) == h:
                tmap = TileMap(w, h, default_tile=TILE_GRASS)
                tmap.tiles = tiles
                # Store a seed so save/load can identify this map.
                # Static editor maps use seed 0 by convention; the
                # load path will prefer the static file over
                # procedural regeneration regardless of seed.
                tmap.seed = data.get("seed", mc.get("seed", 0))
                tmap.overworld_interiors = data.get("interiors", [])
                tmap.tile_properties = data.get("tile_properties", {})
                return tmap

    return None

def validate_module_links(module_path):
    """Stub — linking system removed. Returns no issues."""
    return []


def _DEAD_OLD_validate_module_links(module_path):  # pragma: no cover
    """DEAD CODE — kept temporarily for reference only.

    Scans the overworld (tile_links), towns, buildings, and dungeons
    in a module and warns about any one-way links that could trap the
    player at runtime.

    Returns a list of ``(severity, message)`` tuples.
    Severity is ``"warning"`` for missing return links or ``"info"``
    for structural notes.

    Designed to be called once at module load time — cheap enough to
    run every time without noticeable delay.
    """
    import logging
    log = logging.getLogger(__name__)
    issues = []

    if not module_path or not os.path.isdir(module_path):
        return issues

    # ── 1. Load all data sources ──────────────────────────────

    # Overworld tile_links  (overworld → town/dungeon/building)
    overworld_links = {}   # name -> target_type
    ow_data = None
    for fname in ("static_overworld.json", "overview_map.json"):
        fpath = os.path.join(module_path, fname)
        if os.path.isfile(fpath):
            try:
                with open(fpath, "r") as fh:
                    ow_data = json.load(fh)
                break
            except (json.JSONDecodeError, OSError):
                pass

    if ow_data:
        raw_tl = ow_data.get("tile_links", {})
        for pos_key, info in raw_tl.items():
            if isinstance(info, dict):
                name = info.get("interior", "")
                ltype = info.get("type", "")
                if name:
                    overworld_links[name] = ltype

    # Overworld interiors (inline interior definitions)
    ow_interiors = {}  # name -> tiles_dict
    if ow_data:
        for idef in ow_data.get("interiors", []):
            iname = idef.get("name", "")
            if iname:
                ow_interiors[iname] = idef.get("tiles", {})

    # Towns
    towns_by_name = {}     # name -> layout tiles dict
    town_interior_targets = {}  # town_name -> set of interior names
    towns_path = os.path.join(module_path, "towns.json")
    if os.path.isfile(towns_path):
        try:
            with open(towns_path, "r") as fh:
                towns_raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            towns_raw = []
        if isinstance(towns_raw, list):
            for t in towns_raw:
                tname = t.get("name", "")
                layout = t.get("layout", {})
                tiles = layout.get("tiles", {})
                if tname:
                    towns_by_name[tname] = tiles
                    targets = set()
                    for td in tiles.values():
                        if isinstance(td, dict) and td.get("interior"):
                            targets.add(td["interior"])
                    town_interior_targets[tname] = targets

    # Buildings
    buildings_by_name = {}  # name -> list of space dicts
    buildings_path = os.path.join(module_path, "buildings.json")
    if os.path.isfile(buildings_path):
        try:
            with open(buildings_path, "r") as fh:
                buildings_raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            buildings_raw = []
        if isinstance(buildings_raw, list):
            for b in buildings_raw:
                bname = b.get("name", "")
                if bname:
                    buildings_by_name[bname] = b.get("spaces", [])

    # Dungeons
    dungeon_names = set()
    dungeons_path = os.path.join(module_path, "dungeons.json")
    if os.path.isfile(dungeons_path):
        try:
            with open(dungeons_path, "r") as fh:
                dungeons_raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            dungeons_raw = []
        if isinstance(dungeons_raw, list):
            for d in dungeons_raw:
                dname = d.get("name", "")
                if dname:
                    dungeon_names.add(dname)
        elif isinstance(dungeons_raw, dict):
            for dname in dungeons_raw:
                dungeon_names.add(dname)

    # ── 2. Helper: check if a tile set has an exit back ───────

    def _has_exit_back(tiles_dict, exit_types=("to_overworld",)):
        """Return True if any tile in tiles_dict has a flag in exit_types."""
        for td in tiles_dict.values():
            if not isinstance(td, dict):
                continue
            for etype in exit_types:
                if td.get(etype):
                    return True
        return False

    # ── 3. Validate overworld → destination links ─────────────

    for target_name, target_type in overworld_links.items():

        if target_type == "town":
            # Town must exist and have an overworld exit.
            # Towns with no custom layout (empty tiles dict) are built
            # procedurally at runtime and always include exits, so we
            # only flag towns that have an explicit layout but are
            # missing exit tiles.
            if target_name in towns_by_name:
                tiles = towns_by_name[target_name]
                if tiles and not _has_exit_back(tiles, ("to_overworld",)):
                    issues.append((
                        "warning",
                        f"Overworld links to town '{target_name}' but the "
                        f"town layout has no to_overworld exit — player "
                        f"may be trapped."
                    ))

        elif target_type == "building":
            # Building must exist and have an exit back to overworld
            if target_name in buildings_by_name:
                spaces = buildings_by_name[target_name]
                has_exit = False
                for sp in spaces:
                    sp_tiles = sp.get("tiles", {})
                    if _has_exit_back(sp_tiles, ("to_overworld",)):
                        has_exit = True
                        break
                if not has_exit:
                    issues.append((
                        "warning",
                        f"Overworld links to building '{target_name}' but no "
                        f"space in the building has a to_overworld exit."
                    ))
            elif target_name in ow_interiors:
                # Overworld interior (inline) — check exit tiles
                tiles = ow_interiors[target_name]
                if not _has_exit_back(tiles, ("to_overworld",)):
                    issues.append((
                        "warning",
                        f"Overworld links to interior '{target_name}' but "
                        f"the interior has no to_overworld exit."
                    ))
            else:
                issues.append((
                    "warning",
                    f"Overworld links to building '{target_name}' but no "
                    f"building or interior with that name was found."
                ))

        elif target_type == "dungeon":
            # Dungeons always generate an exit staircase, so we just
            # check the dungeon data exists.
            if target_name not in dungeon_names:
                issues.append((
                    "info",
                    f"Overworld links to dungeon '{target_name}' — not "
                    f"found in dungeons.json (may be procedurally generated)."
                ))

    # ── 4. Validate town → interior links ─────────────────────

    for town_name, interior_names in town_interior_targets.items():
        for int_name in interior_names:
            if int_name in buildings_by_name:
                spaces = buildings_by_name[int_name]
                has_exit = False
                for sp in spaces:
                    sp_tiles = sp.get("tiles", {})
                    if _has_exit_back(sp_tiles, ("to_town", "to_overworld")):
                        has_exit = True
                        break
                if not has_exit:
                    issues.append((
                        "warning",
                        f"Town '{town_name}' links to building "
                        f"'{int_name}' but no space in the building "
                        f"has a to_town or to_overworld exit."
                    ))
            else:
                issues.append((
                    "warning",
                    f"Town '{town_name}' links to interior '{int_name}' "
                    f"but no building with that name was found."
                ))

    # ── 5. Validate building spaces have exits ────────────────

    for bname, spaces in buildings_by_name.items():
        for sp in spaces:
            sp_name = sp.get("name", "?")
            sp_tiles = sp.get("tiles", {})
            if not sp_tiles:
                continue
            if not _has_exit_back(sp_tiles, ("to_overworld", "to_town")):
                # Check if it has sub-interior links (chain exits)
                has_interior = any(
                    isinstance(td, dict) and td.get("interior")
                    for td in sp_tiles.values()
                )
                if not has_interior:
                    issues.append((
                        "warning",
                        f"Building '{bname}' space '{sp_name}' has no "
                        f"exit (to_overworld, to_town, or interior link)."
                    ))

    # ── 6. Validate link registry (links.json) ─────────────────

    links_path = os.path.join(module_path, "links.json")
    if os.path.isfile(links_path):
        try:
            with open(links_path, "r") as fh:
                links_raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            links_raw = []

        if isinstance(links_raw, list):
            links_by_id = {}
            for entry in links_raw:
                lid = entry.get("link_id", "")
                if lid:
                    links_by_id[lid] = entry

            # All known map addresses for quick existence checking
            known_maps = {"overworld"}
            for tname in towns_by_name:
                known_maps.add(f"town:{tname}")
            for bname, spaces in buildings_by_name.items():
                for sp in spaces:
                    sp_name = sp.get("name", "")
                    if sp_name:
                        known_maps.add(f"building:{bname}:{sp_name}")
            for dname in dungeon_names:
                known_maps.add(f"dungeon:{dname}")
            for iname in ow_interiors:
                known_maps.add(f"interior:{iname}")

            for entry in links_raw:
                lid = entry.get("link_id", "")
                src_map = entry.get("source_map", "")
                tgt_map = entry.get("target_map", "")
                partner = entry.get("partner_id", "")

                # Check partner exists
                if partner and partner not in links_by_id:
                    issues.append((
                        "warning",
                        f"Link '{lid}' references partner '{partner}' "
                        f"which does not exist in links.json."
                    ))

                # Check source map is known
                if src_map and src_map not in known_maps:
                    issues.append((
                        "info",
                        f"Link '{lid}' source map '{src_map}' is not a "
                        f"known map in this module."
                    ))

                # Check target map is known
                if tgt_map and tgt_map not in known_maps:
                    issues.append((
                        "info",
                        f"Link '{lid}' target map '{tgt_map}' is not a "
                        f"known map in this module."
                    ))

    # ── 7. Log results ────────────────────────────────────────

    for severity, msg in issues:
        if severity == "warning":
            log.warning("Link validation: %s", msg)
        else:
            log.info("Link validation: %s", msg)

    if not issues:
        log.info("Link validation: all links are bidirectional — OK")

    return issues


# ── Unique tile loader ──────────────────────────────────────────

def load_unique_tiles(data_dir=None):
    """Load unique tile definitions.

    Resolution order:
    1. ``module.json`` — ``unique_tiles`` key inside the manifest
       (this is where the module editor stores them).
    2. ``unique_tiles.json`` in the module directory.
    3. ``data/unique_tiles.json`` — the global fallback.
    """
    if data_dir is not None:
        # 1. Check module.json manifest first
        manifest_path = os.path.join(data_dir, "module.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                ut = manifest.get("unique_tiles")
                if ut:
                    return ut
            except (json.JSONDecodeError, OSError):
                pass

        # 2. Check standalone unique_tiles.json in module dir
        mod_path = os.path.join(data_dir, "unique_tiles.json")
        if os.path.exists(mod_path):
            with open(mod_path, "r") as f:
                data = json.load(f)
            return data.get("unique_tiles", {})

    # 3. Fallback to default data/ directory
    path = os.path.join(os.path.dirname(__file__), "..", "data", "unique_tiles.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("unique_tiles", {})


# ═══════════════════════════════════════════════════════════════════
# Value-noise helpers (no external dependencies)
# ═══════════════════════════════════════════════════════════════════

def _hash2d(x, y, seed=0):
    """Fast integer hash → float in [0, 1)."""
    n = x * 374761393 + y * 668265263 + seed * 1274126177
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return (n & 0x7FFFFFFF) / 0x7FFFFFFF


def _smooth_noise(x, y, seed=0):
    """Bilinearly interpolated value noise at fractional coords."""
    ix, iy = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - ix, y - iy
    # Smoothstep
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    n00 = _hash2d(ix, iy, seed)
    n10 = _hash2d(ix + 1, iy, seed)
    n01 = _hash2d(ix, iy + 1, seed)
    n11 = _hash2d(ix + 1, iy + 1, seed)
    nx0 = n00 + (n10 - n00) * fx
    nx1 = n01 + (n11 - n01) * fx
    return nx0 + (nx1 - nx0) * fy


def _fbm(x, y, octaves=4, seed=0):
    """Fractal Brownian Motion — layered value noise in [0, 1)."""
    value = 0.0
    amp = 0.5
    freq = 1.0
    for i in range(octaves):
        value += amp * _smooth_noise(x * freq, y * freq, seed + i * 31)
        amp *= 0.5
        freq *= 2.0
    return value


# ═══════════════════════════════════════════════════════════════════
# Procedural overworld generator
# ═══════════════════════════════════════════════════════════════════

# ── Default overworld constants (used when no module config given) ──
_MAP_W = 40
_MAP_H = 30

_TOWN_POS = (10, 14)
_DUNGEON_POS = (30, 8)
_HOUSE_DUNGEON_POS = (7, 10)
_START_POS = (14, 16)

# Tile type mapping for landmarks defined in overworld.json
_TILE_NAME_MAP = {
    "TILE_TOWN": TILE_TOWN,
    "TILE_DUNGEON": TILE_DUNGEON,
    "TILE_GRASS": TILE_GRASS,
}


def _get_overworld_params(overworld_cfg):
    """Extract generation parameters from an overworld config dict.

    Returns a flat dict of parameters with defaults for any missing keys.
    This lets create_test_map work identically with or without a module.
    """
    if overworld_cfg is None:
        overworld_cfg = {}

    size = overworld_cfg.get("size", {})
    noise = overworld_cfg.get("noise", {})
    mask = overworld_cfg.get("island_mask", {})
    thresh = overworld_cfg.get("terrain_thresholds", {})
    rivers = overworld_cfg.get("rivers", {})
    start = overworld_cfg.get("start_position", {})

    # Build landmarks list from JSON, or fall back to hardcoded positions
    landmarks_raw = overworld_cfg.get("landmarks")
    if landmarks_raw:
        landmarks = {}
        for lm in landmarks_raw:
            landmarks[lm["id"]] = {
                "col": lm["col"],
                "row": lm["row"],
                "tile": _TILE_NAME_MAP.get(lm.get("tile", ""), TILE_DUNGEON),
                "clear_radius": lm.get("clear_radius", 2),
            }
    else:
        landmarks = {
            "thornwall":     {"col": 10, "row": 14, "tile": TILE_TOWN, "clear_radius": 2},
            "shadow_keep":   {"col": 30, "row": 8,  "tile": TILE_DUNGEON, "clear_radius": 2},
            "house_dungeon": {"col": 7,  "row": 10, "tile": TILE_DUNGEON, "clear_radius": 2},
        }

    # Build paths list
    paths_raw = overworld_cfg.get("paths")
    if paths_raw:
        paths = [(tuple(p["from"]), tuple(p["to"])) for p in paths_raw]
    else:
        paths = [
            ((10, 14), (30, 8)),
            ((8, 12), (7, 10)),
            ((14, 16), (10, 14)),
        ]

    # Unique tile placements
    utp = overworld_cfg.get("unique_tile_placements", {})
    fixed_placements = {}
    for tile_id, pos in utp.get("fixed", {}).items():
        fixed_placements[tile_id] = (pos["col"], pos["row"])
    scatter_tiles = utp.get("scatter", None)  # resolved at placement time

    return {
        "map_w": size.get("width", _MAP_W),
        "map_h": size.get("height", _MAP_H),
        "seed": overworld_cfg.get("seed"),
        # Noise
        "elev_scale": noise.get("elevation_scale", 0.12),
        "elev_octaves": noise.get("elevation_octaves", 5),
        "moist_scale": noise.get("moisture_scale", 0.12),
        "moist_octaves": noise.get("moisture_octaves", 3),
        "moist_offset_x": noise.get("moisture_offset", {}).get("x", 100),
        "moist_offset_y": noise.get("moisture_offset", {}).get("y", 100),
        # Island mask
        "mask_x_squash": mask.get("x_squash", 0.9),
        "mask_y_squash": mask.get("y_squash", 1.1),
        "mask_edge_falloff": mask.get("edge_falloff", 0.95),
        "mask_blend_land": mask.get("blend_land", 0.35),
        "mask_blend_ocean": mask.get("blend_ocean", 0.65),
        "mask_ocean_penalty": mask.get("ocean_penalty", 0.15),
        # Terrain thresholds
        "water_max": thresh.get("water_max", 0.10),
        "sand_max": thresh.get("sand_max", 0.16),
        "mountain_min": thresh.get("mountain_min", 0.42),
        "forest_elev_min": thresh.get("forest_elevation_min", 0.28),
        "forest_moist_min": thresh.get("forest_moisture_min", 0.42),
        "forest_alt_moist_min": thresh.get("forest_alt_moisture_min", 0.52),
        "forest_alt_elev_min": thresh.get("forest_alt_elevation_min", 0.18),
        # Rivers
        "rivers_enabled": rivers.get("enabled", True),
        "river_start_range": rivers.get("start_offset_range", [-4, 4]),
        "river_meander": rivers.get("meander_options", [-1, 0, 0, 1]),
        "river_widen_chance": rivers.get("widen_chance", 0.3),
        "river_bridge": rivers.get("bridge", True),
        # Start position
        "start_col": start.get("col", _START_POS[0]),
        "start_row": start.get("row", _START_POS[1]),
        # World features
        "landmarks": landmarks,
        "paths": paths,
        "fixed_placements": fixed_placements if fixed_placements else {},
        "scatter_tiles": scatter_tiles,
    }


def create_test_map(seed=None, overworld_cfg=None, data_dir=None):
    """Generate a procedural island overworld.

    Parameters
    ----------
    seed : int or None
        RNG seed.  If None a random seed is chosen.
    overworld_cfg : dict or None
        Parsed ``overworld.json`` from the active module.  When None the
        hardcoded Realm-of-Shadow defaults are used.
    data_dir : str or None
        Module data directory for loading unique tiles with fallback.

    Each call produces a different layout (unless a fixed *seed* is given).
    Landmarks, paths, and unique tiles are read from the config so that
    different modules can define entirely different worlds.
    """
    p = _get_overworld_params(overworld_cfg)
    map_w, map_h = p["map_w"], p["map_h"]

    if seed is None:
        seed = p["seed"] if p["seed"] is not None else random.randint(0, 2 ** 31)

    tmap = TileMap(map_w, map_h, default_tile=TILE_GRASS)
    tmap.seed = seed  # store seed for save/load reproducibility

    # ── 1. Generate elevation / moisture noise fields ──
    elev = [[0.0] * map_w for _ in range(map_h)]
    moist = [[0.0] * map_w for _ in range(map_h)]

    for r in range(map_h):
        for c in range(map_w):
            elev[r][c] = _fbm(c * p["elev_scale"], r * p["elev_scale"],
                              octaves=p["elev_octaves"], seed=seed)
            moist[r][c] = _fbm(
                c * p["moist_scale"] + p["moist_offset_x"],
                r * p["moist_scale"] + p["moist_offset_y"],
                octaves=p["moist_octaves"], seed=seed + 7)

    # ── 2. Island mask — force ocean at edges, land in centre ──
    for r in range(map_h):
        for c in range(map_w):
            nx = (c / max(map_w - 1, 1)) * 2 - 1
            ny = (r / max(map_h - 1, 1)) * 2 - 1
            d = math.sqrt(nx * nx * p["mask_x_squash"]
                          + ny * ny * p["mask_y_squash"])
            mask = max(0.0, 1.0 - d * p["mask_edge_falloff"])
            elev[r][c] = (elev[r][c]
                          * (p["mask_blend_land"] + p["mask_blend_ocean"] * mask)
                          - (1.0 - mask) * p["mask_ocean_penalty"])

    # ── 3. Classify terrain from elevation + moisture ──
    for r in range(map_h):
        for c in range(map_w):
            e = elev[r][c]
            m = moist[r][c]
            if e < p["water_max"]:
                tmap.set_tile(c, r, TILE_WATER)
            elif e < p["sand_max"]:
                tmap.set_tile(c, r, TILE_SAND)
            elif e > p["mountain_min"]:
                tmap.set_tile(c, r, TILE_MOUNTAIN)
            elif e > p["forest_elev_min"] and m > p["forest_moist_min"]:
                tmap.set_tile(c, r, TILE_FOREST)
            elif m > p["forest_alt_moist_min"] and e > p["forest_alt_elev_min"]:
                tmap.set_tile(c, r, TILE_FOREST)

    # ── 4. Carve a meandering river ──
    if p["rivers_enabled"]:
        _carve_river(tmap, seed, p)

    # ── 5. Place landmarks ──
    start_pos = (p["start_col"], p["start_row"])
    _clear_area(tmap, start_pos[0], start_pos[1], radius=2)
    for lm in p["landmarks"].values():
        _clear_area(tmap, lm["col"], lm["row"], lm["clear_radius"])
        tmap.set_tile(lm["col"], lm["row"], lm["tile"])

    # ── 6. Carve paths between landmarks ──
    for i, (pfrom, pto) in enumerate(p["paths"]):
        _carve_path(tmap, pfrom, pto, seed + i * 42, map_w, map_h)

    # ── 7. Ensure start position is grass ──
    tmap.set_tile(start_pos[0], start_pos[1], TILE_GRASS)

    # ── 8. Place unique tiles ──
    unique_defs = load_unique_tiles(data_dir)
    _place_unique_tiles(tmap, unique_defs, seed, p)

    return tmap


def _clear_area(tmap, cx, cy, radius=2):
    """Set tiles in a small radius to TILE_GRASS so landmarks are reachable."""
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            c, r = cx + dc, cy + dr
            if 0 <= c < tmap.width and 0 <= r < tmap.height:
                tid = tmap.get_tile(c, r)
                if tid in (TILE_WATER, TILE_MOUNTAIN):
                    tmap.set_tile(c, r, TILE_GRASS)


def _carve_river(tmap, seed, p):
    """Carve a meandering river from top to bottom across the map."""
    map_w, map_h = tmap.width, tmap.height
    rng = random.Random(seed + 333)
    start_range = p.get("river_start_range", [-4, 4])
    col = map_w // 2 + rng.randint(start_range[0], start_range[1])

    margin = max(4, map_h // 8)
    for row in range(margin, map_h - margin):
        col += rng.choice(p.get("river_meander", [-1, 0, 0, 1]))
        col = max(6, min(map_w - 7, col))
        tmap.set_tile(col, row, TILE_WATER)
        if rng.random() < p.get("river_widen_chance", 0.3):
            tmap.set_tile(col + 1, row, TILE_WATER)

    if p.get("river_bridge", True):
        bridge_row = map_h // 2 + rng.randint(-2, 2)
        for c in range(map_w):
            if tmap.get_tile(c, bridge_row) == TILE_WATER:
                tmap.set_tile(c, bridge_row, TILE_BRIDGE)
                break


def _carve_path(tmap, start, end, seed, map_w=None, map_h=None):
    """Carve a winding path between two points.

    Uses a simple walk that moves toward the goal with occasional jitter,
    overwriting non-water tiles with TILE_PATH.
    """
    if map_w is None:
        map_w = tmap.width
    if map_h is None:
        map_h = tmap.height
    rng = random.Random(seed)
    cx, cy = start
    ex, ey = end

    visited = set()
    max_steps = abs(ex - cx) + abs(ey - cy) + 30

    for _ in range(max_steps):
        if (cx, cy) == (ex, ey):
            break
        visited.add((cx, cy))

        tid = tmap.get_tile(cx, cy)
        if tid not in (TILE_WATER, TILE_MOUNTAIN, TILE_TOWN, TILE_DUNGEON,
                       TILE_BRIDGE):
            tmap.set_tile(cx, cy, TILE_PATH)

        dx = ex - cx
        dy = ey - cy

        if rng.random() < 0.25:
            cx += rng.choice([-1, 0, 1])
            cy += rng.choice([-1, 0, 1])
        else:
            if abs(dx) >= abs(dy):
                cx += (1 if dx > 0 else -1)
            else:
                cy += (1 if dy > 0 else -1)

        cx = max(4, min(map_w - 5, cx))
        cy = max(4, min(map_h - 5, cy))

    tid = tmap.get_tile(ex, ey)
    if tid not in (TILE_WATER, TILE_MOUNTAIN, TILE_TOWN, TILE_DUNGEON):
        tmap.set_tile(ex, ey, TILE_PATH)


def _place_unique_tiles(tmap, unique_defs, seed, p):
    """Place unique tiles at random walkable locations.

    Reads fixed and scatter tile lists from the overworld params *p*.
    If no scatter list is specified, all unique tile IDs are scattered
    so that every module-defined tile appears on the map.
    """
    map_w, map_h = tmap.width, tmap.height
    rng = random.Random(seed + 777)

    fixed_placements = p.get("fixed_placements", {})
    scatter_tiles = p.get("scatter_tiles")
    if scatter_tiles is None:
        # Default: scatter every defined unique tile that isn't fixed
        scatter_tiles = [tid for tid in unique_defs
                         if tid not in fixed_placements]

    # Place fixed ones first
    for tile_id, (c, r) in fixed_placements.items():
        if tile_id in unique_defs:
            _clear_area(tmap, c, r, radius=1)
            tmap.place_unique(c, r, tile_id, unique_defs[tile_id])

    # Build a set of occupied positions (landmarks + fixed uniques + start)
    occupied = set(fixed_placements.values())
    occupied.add((p["start_col"], p["start_row"]))
    for lm in p["landmarks"].values():
        occupied.add((lm["col"], lm["row"]))

    # Candidate walkable positions for scatter tiles
    margin = max(2, min(5, map_w // 8))
    candidates = []
    for r in range(margin, map_h - margin):
        for c in range(margin, map_w - margin):
            if (c, r) in occupied:
                continue
            if tmap.is_walkable(c, r):
                candidates.append((c, r))

    rng.shuffle(candidates)

    idx = 0
    for tile_id in scatter_tiles:
        if tile_id not in unique_defs:
            continue
        if idx >= len(candidates):
            break
        c, r = candidates[idx]
        idx += 1
        tmap.place_unique(c, r, tile_id, unique_defs[tile_id])
        occupied.add((c, r))
