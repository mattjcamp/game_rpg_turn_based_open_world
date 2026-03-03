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

    def __init__(self, width, height, default_tile=TILE_GRASS):
        self.width = width
        self.height = height
        # 2D list: self.tiles[row][col]
        self.tiles = [[default_tile for _ in range(width)] for _ in range(height)]
        # Unique tiles: (col, row) -> tile definition dict from unique_tiles.json
        self.unique_tiles = {}
        # Tracks which unique tiles have already been triggered (one_time)
        self.triggered_unique = set()
        # Cooldown timers: tile_id -> remaining steps
        self.unique_cooldowns = {}

    def get_tile(self, col, row):
        """Get tile ID at (col, row). Returns TILE_WATER for out-of-bounds."""
        if 0 <= col < self.width and 0 <= row < self.height:
            return self.tiles[row][col]
        return TILE_WATER  # ocean beyond map edges

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


# ── Unique tile loader ──────────────────────────────────────────

def load_unique_tiles():
    """Load unique tile definitions from data/unique_tiles.json."""
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

_MAP_W = 40
_MAP_H = 30

# Fixed landmark positions that the quest system depends on.
_TOWN_POS = (10, 14)
_DUNGEON_POS = (30, 8)
_HOUSE_DUNGEON_POS = (7, 10)
_START_POS = (14, 16)


def create_test_map(seed=None):
    """Generate a procedural 40×30 island overworld.

    Each call produces a different layout (unless a fixed *seed* is given).
    Key landmarks (town, dungeons, start position) are placed at fixed
    coordinates so the quest system and party start location still work.
    """
    if seed is None:
        seed = random.randint(0, 2 ** 31)

    tmap = TileMap(_MAP_W, _MAP_H, default_tile=TILE_GRASS)

    # ── 1. Generate elevation / moisture noise fields ──
    elev = [[0.0] * _MAP_W for _ in range(_MAP_H)]
    moist = [[0.0] * _MAP_W for _ in range(_MAP_H)]
    scale = 0.12  # noise zoom

    for r in range(_MAP_H):
        for c in range(_MAP_W):
            elev[r][c] = _fbm(c * scale, r * scale, octaves=5, seed=seed)
            moist[r][c] = _fbm(c * scale + 100, r * scale + 100,
                                octaves=3, seed=seed + 7)

    # ── 2. Island mask — force ocean at edges, land in centre ──
    for r in range(_MAP_H):
        for c in range(_MAP_W):
            nx = (c / (_MAP_W - 1)) * 2 - 1   # -1..1
            ny = (r / (_MAP_H - 1)) * 2 - 1
            # Elliptical distance (wider map → squash y less)
            d = math.sqrt(nx * nx * 0.9 + ny * ny * 1.1)
            # Generous gradient: land covers most of the interior
            mask = max(0.0, 1.0 - d * 0.95)
            # Blend: keep most of the noise, just taper edges to ocean
            elev[r][c] = elev[r][c] * (0.35 + 0.65 * mask) - (1.0 - mask) * 0.15

    # ── 3. Classify terrain from elevation + moisture ──
    for r in range(_MAP_H):
        for c in range(_MAP_W):
            e = elev[r][c]
            m = moist[r][c]
            if e < 0.10:
                tmap.set_tile(c, r, TILE_WATER)
            elif e < 0.16:
                tmap.set_tile(c, r, TILE_SAND)
            elif e > 0.42:
                tmap.set_tile(c, r, TILE_MOUNTAIN)
            elif e > 0.28 and m > 0.42:
                tmap.set_tile(c, r, TILE_FOREST)
            elif m > 0.52 and e > 0.18:
                tmap.set_tile(c, r, TILE_FOREST)
            # else: stays TILE_GRASS

    # ── 4. Carve a meandering river ──
    _carve_river(tmap, seed)

    # ── 5. Place fixed landmarks ──
    # Clear a small walkable area around each landmark
    for pos in [_TOWN_POS, _DUNGEON_POS, _HOUSE_DUNGEON_POS, _START_POS]:
        _clear_area(tmap, pos[0], pos[1], radius=2)

    tmap.set_tile(*_TOWN_POS, TILE_TOWN)
    tmap.set_tile(*_DUNGEON_POS, TILE_DUNGEON)
    tmap.set_tile(*_HOUSE_DUNGEON_POS, TILE_DUNGEON)

    # ── 6. Path from town to dungeon ──
    _carve_path(tmap, _TOWN_POS, _DUNGEON_POS, seed)
    # Short path from Elara NPC area toward house dungeon
    _carve_path(tmap, (8, 12), _HOUSE_DUNGEON_POS, seed + 99)
    # Path from start toward town
    _carve_path(tmap, _START_POS, _TOWN_POS, seed + 42)

    # ── 7. Ensure start position is grass ──
    tmap.set_tile(_START_POS[0], _START_POS[1], TILE_GRASS)

    # ── 8. Place unique tiles ──
    unique_defs = load_unique_tiles()
    _place_unique_tiles(tmap, unique_defs, seed)

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


def _carve_river(tmap, seed):
    """Carve a meandering river from top to bottom across the map."""
    rng = random.Random(seed + 333)
    col = _MAP_W // 2 + rng.randint(-4, 4)

    for row in range(4, _MAP_H - 4):
        # Meander
        col += rng.choice([-1, 0, 0, 1])
        col = max(6, min(_MAP_W - 7, col))
        tmap.set_tile(col, row, TILE_WATER)
        # Occasionally widen
        if rng.random() < 0.3:
            tmap.set_tile(col + 1, row, TILE_WATER)

    # Place a bridge roughly in the middle
    bridge_row = _MAP_H // 2 + rng.randint(-2, 2)
    # Find the river column at that row
    for c in range(_MAP_W):
        if tmap.get_tile(c, bridge_row) == TILE_WATER:
            tmap.set_tile(c, bridge_row, TILE_BRIDGE)
            break


def _carve_path(tmap, start, end, seed):
    """Carve a winding path between two points.

    Uses a simple walk that moves toward the goal with occasional jitter,
    overwriting non-water tiles with TILE_PATH.
    """
    rng = random.Random(seed)
    cx, cy = start
    ex, ey = end

    visited = set()
    max_steps = abs(ex - cx) + abs(ey - cy) + 30

    for _ in range(max_steps):
        if (cx, cy) == (ex, ey):
            break
        visited.add((cx, cy))

        # Set tile to path if it's walkable (don't overwrite water/mountain)
        tid = tmap.get_tile(cx, cy)
        if tid not in (TILE_WATER, TILE_MOUNTAIN, TILE_TOWN, TILE_DUNGEON,
                       TILE_BRIDGE):
            tmap.set_tile(cx, cy, TILE_PATH)

        # Move toward target with some noise
        dx = ex - cx
        dy = ey - cy

        if rng.random() < 0.25:
            # Random jitter step
            cx += rng.choice([-1, 0, 1])
            cy += rng.choice([-1, 0, 1])
        else:
            # Move toward goal (prefer longer axis)
            if abs(dx) >= abs(dy):
                cx += (1 if dx > 0 else -1)
            else:
                cy += (1 if dy > 0 else -1)

        cx = max(4, min(_MAP_W - 5, cx))
        cy = max(4, min(_MAP_H - 5, cy))

    # Set the final tile
    tid = tmap.get_tile(ex, ey)
    if tid not in (TILE_WATER, TILE_MOUNTAIN, TILE_TOWN, TILE_DUNGEON):
        tmap.set_tile(ex, ey, TILE_PATH)


def _place_unique_tiles(tmap, unique_defs, seed):
    """Place unique tiles at random walkable locations.

    Some tiles (Elara, signpost) are placed near fixed landmarks.
    Others are scattered across the island on walkable terrain.
    """
    rng = random.Random(seed + 777)

    # Tiles that must be placed near specific landmarks
    fixed_placements = {
        "elara_npc":     (8, 12),
        "signpost":      (12, 14),
    }

    # All unique tile IDs we want to place
    scatter_tiles = [
        "ancient_shrine", "war_memorial", "whispering_stones",
        "old_campfire", "fairy_ring", "hermit_camp",
        "enchanted_spring", "oracle_pool", "forgotten_grave",
        "dragon_bones", "sunken_shipwreck", "wandering_ghost",
        "merchant_wagon", "bandit_cache", "shadow_mark",
        "ancient_battlefield", "moongate", "cursed_well",
        "poison_swamp",
    ]

    # Place fixed ones first
    for tile_id, (c, r) in fixed_placements.items():
        if tile_id in unique_defs:
            # Ensure the tile is walkable
            _clear_area(tmap, c, r, radius=1)
            tmap.place_unique(c, r, tile_id, unique_defs[tile_id])

    # Build a list of candidate walkable positions
    occupied = set(fixed_placements.values())
    occupied.add(_TOWN_POS)
    occupied.add(_DUNGEON_POS)
    occupied.add(_HOUSE_DUNGEON_POS)
    occupied.add(_START_POS)

    candidates = []
    for r in range(5, _MAP_H - 5):
        for c in range(5, _MAP_W - 5):
            if (c, r) in occupied:
                continue
            if tmap.is_walkable(c, r):
                candidates.append((c, r))

    rng.shuffle(candidates)

    # Place scatter tiles at random walkable spots
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
