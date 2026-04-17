"""
Interior visibility and lighting for hand-authored enclosed spaces.

Computes fog-of-war visibility for town building interiors and overworld
building interiors.  Uses recursive shadowcasting with a per-source
range cap, so the party's own vision is finite and each in-world light
only illuminates up to its authored radius.

This module is intentionally separate from the procedural-dungeon
visibility code in ``src/states/dungeon.py``.  Dungeons are generated
and use procedurally-placed torches, while building interiors are
hand-authored in the map editor with per-tile ``light_source`` and
``light_range`` attributes — different authoring paths with different
tuning knobs.  Keeping the two systems separate lets them evolve
independently.

Visibility rules
----------------
- No equipped light → party sees only the 3×3 tiles around themselves
  (Chebyshev radius 1).
- Equipped light → party shadowcasts outward to ``PARTY_LIT_RADIUS``
  tiles, with walls/closed doors blocking.
- Any in-world light whose tile is within the party's **unbounded**
  line of sight contributes its own shadowcast illumination, capped
  at that light's range.  "Unbounded LOS" means a distant light
  across a long unobstructed room is visible regardless of the
  party's own carried-light range — the glow reaches the eye even
  though the party couldn't illuminate that area themselves.  Walls
  and closed doors still block LOS, so a light behind a wall stays
  invisible.  One pass — no fixed-point iteration.

Light sources are gathered from two places and merged:
- ``tile_defs.json`` ``flags.light_source`` (plus ``flags.light_radius``)
  — permanent tile-type lights like wall torches.
- ``tile_properties["col,row"]["light_source"]`` (plus ``light_range``,
  stored as a string) — per-tile lights authored in the map editor's
  Attributes panel.

Line-of-sight blockers
----------------------
A tile blocks light when it's not walkable, or when it is a closed
door (``TILE_DDOOR``).  Matches the predicate used by the dungeon
visibility system for consistency.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Set, Tuple

from src.settings import TILE_DDOOR, TILE_DEFS


# ── Tunables ──────────────────────────────────────────────────────

# Chebyshev radius the party can see with no equipped light.  "Only
# one tile in every direction" from the design brief → 1.
PARTY_DARK_RADIUS: int = 1

# Shadowcast range when the party has any equipped/active light
# (torch, infravision, Galadriel's Light, etc.).  Matches the
# pre-rewrite lighting.py constants (1.0 base + 3.0 bonus = 4).
# Can be made per-item later when more light items are added.
PARTY_LIT_RADIUS: int = 4

# Fallback radius for a light source that has ``light_source`` set
# but no explicit range — matches the tile_defs.json default for
# wall torches.
DEFAULT_LIGHT_RANGE: int = 5


# Type alias for a light-source illumination cache.  Keyed by
# (col, row, range) so a range change on an editor-placed light
# naturally invalidates its old entry.
LightCache = Dict[Tuple[int, int, int], Set[Tuple[int, int]]]


# ── LOS predicate ─────────────────────────────────────────────────

def _is_opaque(tile_map, x: int, y: int) -> bool:
    """True when a tile blocks light and sight.

    Non-walkable tiles (walls, void, etc.) are always opaque.  Closed
    doors are walkable but opaque — you see the door itself but not
    what's behind it.
    """
    if not tile_map.is_walkable(x, y):
        return True
    return tile_map.get_tile(x, y) == TILE_DDOOR


# ── Shadowcasting ─────────────────────────────────────────────────

# One row per octant (xx, xy, yx, yy) — identical to the dungeon
# implementation, kept local so the two systems stay decoupled.
_OCTANTS: Tuple[Tuple[int, int, int, int], ...] = (
    ( 1,  0,  0,  1), ( 0,  1,  1,  0),
    ( 0, -1,  1,  0), (-1,  0,  0,  1),
    (-1,  0,  0, -1), ( 0, -1, -1,  0),
    ( 0,  1, -1,  0), ( 1,  0,  0, -1),
)


def _cast_light(visible: Set[Tuple[int, int]], tile_map,
                cx: int, cy: int, row: int,
                start_slope: float, end_slope: float,
                max_radius: int,
                xx: int, xy: int, yx: int, yy: int) -> None:
    """Recursive shadowcasting for one octant, capped at *max_radius*.

    Adds visible tiles (including the walls/doors that terminate each
    ray) to *visible*.  Walls don't pass light; closed doors are walls
    for this purpose (see ``_is_opaque``).
    """
    if start_slope < end_slope:
        return
    for j in range(row, max_radius + 1):
        blocked = False
        new_start = start_slope
        dx = -j - 1
        dy = -j
        while dx <= 0:
            dx += 1
            map_x = cx + dx * xx + dy * xy
            map_y = cy + dx * yx + dy * yy
            l_slope = (dx - 0.5) / (dy + 0.5)
            r_slope = (dx + 0.5) / (dy - 0.5)
            if start_slope < r_slope:
                continue
            if end_slope > l_slope:
                break
            visible.add((map_x, map_y))
            is_wall = _is_opaque(tile_map, map_x, map_y)
            if blocked:
                if is_wall:
                    new_start = r_slope
                else:
                    blocked = False
                    start_slope = new_start
            else:
                if is_wall and j < max_radius:
                    blocked = True
                    _cast_light(visible, tile_map, cx, cy,
                                j + 1, start_slope, l_slope, max_radius,
                                xx, xy, yx, yy)
                    new_start = r_slope
        if blocked:
            break


def shadowcast_from(tile_map, cx: int, cy: int,
                    max_radius: int) -> Set[Tuple[int, int]]:
    """Return every tile visible from (cx, cy) within *max_radius*.

    The origin tile is always included, regardless of its own
    opacity (so a torch placed on a wall tile still "knows" where
    it is).
    """
    visible: Set[Tuple[int, int]] = {(cx, cy)}
    for xx, xy, yx, yy in _OCTANTS:
        _cast_light(visible, tile_map, cx, cy, 1,
                    1.0, 0.0, max_radius, xx, xy, yx, yy)
    return visible


# ── Light-source discovery ────────────────────────────────────────

def scan_light_sources(tile_map) -> Iterable[Tuple[int, int, int]]:
    """Yield ``(col, row, range_tiles)`` for every light on the map.

    Two input paths, merged:

    1.  Tile-type lights from ``tile_defs.json``: any tile whose
        ``flags.light_source`` is True contributes a light at that
        position with radius ``flags.light_radius`` (default
        ``DEFAULT_LIGHT_RANGE``).  Wall torches are the canonical
        example.
    2.  Per-tile lights from ``tile_properties`` authored in the map
        editor: any cell with ``light_source: True`` contributes a
        light using ``light_range`` (stored as a string; non-numeric
        values fall back to ``DEFAULT_LIGHT_RANGE``).

    If the same (col, row) appears in both paths, both entries are
    yielded — the caller's cache keys on range, so duplicates at the
    same range produce a single cache hit.  In practice this is
    harmless because the authoring flows are mutually exclusive.
    """
    # Path 1 — tile-type lights
    for wr in range(tile_map.height):
        for wc in range(tile_map.width):
            tid = tile_map.get_tile(wc, wr)
            flags = TILE_DEFS.get(tid, {}).get("flags", {})
            if flags.get("light_source"):
                r_raw = flags.get("light_radius", DEFAULT_LIGHT_RANGE)
                try:
                    r = max(1, int(r_raw))
                except (TypeError, ValueError):
                    r = DEFAULT_LIGHT_RANGE
                yield (wc, wr, r)

    # Path 2 — per-tile lights from the editor Attributes panel
    tprops = getattr(tile_map, "tile_properties", None) or {}
    for key, props in tprops.items():
        if not isinstance(props, dict) or not props.get("light_source"):
            continue
        try:
            wc_str, wr_str = key.split(",")
            wc, wr = int(wc_str), int(wr_str)
        except (ValueError, AttributeError):
            continue
        r_raw = props.get("light_range", DEFAULT_LIGHT_RANGE)
        try:
            r = max(1, int(str(r_raw).strip() or DEFAULT_LIGHT_RANGE))
        except (TypeError, ValueError):
            r = DEFAULT_LIGHT_RANGE
        yield (wc, wr, r)


# ── Public entry point ────────────────────────────────────────────

def compute_visible_tiles(
    tile_map,
    party_col: int,
    party_row: int,
    has_party_light: bool,
    light_cache: Optional[LightCache] = None,
) -> Tuple[Set[Tuple[int, int]], LightCache]:
    """Compute the set of tiles visible inside a building interior.

    Parameters
    ----------
    tile_map
        The interior's tile map.
    party_col, party_row
        Current party position in map coordinates.
    has_party_light
        True if the party carries any equipped/active light
        (torch item, Infravision effect, Galadriel's Light, …).
        The caller is responsible for rolling up those checks.
    light_cache
        Per-light-source illumination cache.  Pass the same dict
        across frames to avoid re-shadowcasting static lights on
        every frame.  The cache is mutated in-place and returned.
        ``None`` means "allocate a fresh cache".

    Returns
    -------
    visible : set of (col, row)
        Every tile currently visible to the party.  Includes the
        party's own tile, the party's shadowcast area, and the
        illuminated area around any in-world light the party can see.
    light_cache : LightCache
        The (possibly-updated) cache — store it and pass it back on
        the next frame.
    """
    if light_cache is None:
        light_cache = {}

    # ── Party's own visibility (range depends on equipped light) ──
    # This is what the party can illuminate themselves; bounded by
    # PARTY_DARK_RADIUS (1) or PARTY_LIT_RADIUS (4).  Walls/doors
    # block as usual.
    radius = PARTY_LIT_RADIUS if has_party_light else PARTY_DARK_RADIUS
    visible = shadowcast_from(tile_map, party_col, party_row, radius)

    # ── Unbounded line-of-sight from the party ──
    # Separate from the party's own illumination radius: this is
    # whether an unobstructed ray reaches a tile, regardless of
    # how far away.  Used to decide which in-world lights the
    # party can *see* — a distant lantern across a long hall is
    # visible to the party even without their own torch, because
    # its glow reaches the eye along a clear sightline.
    max_dim = max(tile_map.width, tile_map.height)
    full_los = shadowcast_from(tile_map, party_col, party_row, max_dim)

    # ── In-world light contributions ──
    # A light source contributes its illumination if its own tile
    # is in the party's *unbounded* line of sight (full_los), not
    # just within the party's own carried-light range.  This is
    # the key rule from the design brief: "If other light sources
    # are in line of sight the party will see them illuminate
    # the space around them based on their range."  Single pass —
    # a light revealed only by another light's glow does NOT
    # cascade.  Walls still block: a light behind a wall stays
    # invisible because full_los doesn't reach it.
    for lc, lr, lrange in scan_light_sources(tile_map):
        if (lc, lr) not in full_los:
            continue
        key = (lc, lr, lrange)
        lit = light_cache.get(key)
        if lit is None:
            lit = shadowcast_from(tile_map, lc, lr, lrange)
            light_cache[key] = lit
        visible.update(lit)

    return visible, light_cache


def party_has_light(party) -> bool:
    """Convenience predicate used by state callers.

    Centralised so the party-side "do you have a light?" rule stays
    in one place.  Mirrors the check used by the dungeon state.
    """
    if party.get_equipped_name("light") is not None:
        return True
    if party.has_effect("Infravision"):
        return True
    if (party.has_effect("Galadriel's Light")
            and getattr(party, "galadriels_light_steps", 0) > 0):
        return True
    return False
