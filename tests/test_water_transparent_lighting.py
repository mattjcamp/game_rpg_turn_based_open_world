"""Water tiles must not block light.

Regression test for the bug where the bottom level of the Sea Shrine
appeared dark on the far side of a water tile: the lighting
shadowcasters in src/interior_lighting.py and src/states/dungeon.py
were treating any non-walkable tile as opaque, which mistakenly
included water.  Both code paths now consult ``flags.transparent`` on
the tile def, and water carries that flag in data/tile_defs.json.
"""

from src.tile_map import TileMap
from src.settings import (
    TILE_FLOOR, TILE_WATER, TILE_DDOOR, TILE_DWALL, TILE_DFLOOR,
)
from src import interior_lighting


# ── _is_opaque predicate (interior_lighting) ─────────────────────────

def test_water_is_not_opaque():
    """Water is non-walkable but flagged transparent — does not block light."""
    tm = TileMap(5, 5, default_tile=TILE_FLOOR)
    tm.set_tile(2, 2, TILE_WATER)
    assert interior_lighting._is_opaque(tm, 2, 2) is False


def test_wall_remains_opaque():
    """Sanity check: walls (non-walkable, no transparent flag) still block."""
    tm = TileMap(5, 5, default_tile=TILE_DFLOOR)
    tm.set_tile(2, 2, TILE_DWALL)
    assert interior_lighting._is_opaque(tm, 2, 2) is True


def test_closed_door_remains_opaque():
    """Doors are walkable but explicitly opaque — unchanged."""
    tm = TileMap(5, 5, default_tile=TILE_DFLOOR)
    tm.set_tile(2, 2, TILE_DDOOR)
    assert interior_lighting._is_opaque(tm, 2, 2) is True


# ── compute_visible_tiles end-to-end (interior shadowcaster) ─────────

def test_torch_across_water_illuminates_far_side():
    """A torch tile two tiles away across water should still light the party.

    Layout (15x3, party at (1,1), torch tile placed at (10,1), with
    water filling the strip between them):

        . . . . . . . . . . . . . . .
        . P w w w w w w w w T . . . .
        . . . . . . . . . . . . . . .

    Without the fix, water was treated as a wall, so the shadowcast
    from the torch terminated at column 2 and the party was in the
    dark (no torch contribution to the visible set).
    """
    tm = TileMap(15, 3, default_tile=TILE_FLOOR)
    # Strip of water between party and torch
    for c in range(2, 10):
        tm.set_tile(c, 1, TILE_WATER)
    # Place a per-tile editor light at column 10
    tm.tile_properties = {
        "10,1": {"light_source": True, "light_range": "8"},
    }

    visible, _cache = interior_lighting.compute_visible_tiles(
        tm, party_col=1, party_row=1, has_party_light=False,
    )

    # The torch's own tile is in unobstructed LOS, so it contributes
    # its illumination disc.  The party tile (1,1) is within that
    # disc (distance 9 tiles) — but more importantly, tiles on the
    # party's side of the water (e.g. (3,1)) should be lit.
    assert (10, 1) in visible, "torch tile must be visible"
    assert (5, 1) in visible, "water tile under the torch glow must be visible"
    assert (2, 1) in visible, "party-side water edge must be lit"


def test_water_in_los_does_not_block_distant_torch():
    """The party's own LOS should reach across water to spot a torch."""
    tm = TileMap(10, 3, default_tile=TILE_FLOOR)
    # Water column at x=4
    tm.set_tile(4, 1, TILE_WATER)
    # Torch at x=8
    tm.tile_properties = {
        "8,1": {"light_source": True, "light_range": "3"},
    }

    visible, _cache = interior_lighting.compute_visible_tiles(
        tm, party_col=1, party_row=1, has_party_light=True,
    )

    # The torch tile itself should be visible (unbounded LOS reaches
    # through water), and the torch's surrounding glow should be in
    # the visible set as well.
    assert (8, 1) in visible
    assert (7, 1) in visible


# ── Dungeon shadowcaster regression ──────────────────────────────────

def test_dungeon_shadowcaster_treats_water_as_transparent(game):
    """DungeonState._cast_light must not stop at water tiles."""
    tm = TileMap(15, 3, default_tile=TILE_DFLOOR)
    for c in range(3, 10):
        tm.set_tile(c, 1, TILE_WATER)

    dungeon = game.states["dungeon"]

    visible: set = set()
    # Cast light from the party's position (1, 1) eastward through water.
    # Octant ( 1, 0, 0, 1) sweeps the +x / +y quadrant.
    for xx, xy, yx, yy in [
        ( 1,  0,  0,  1), ( 0,  1,  1,  0),
        ( 0, -1,  1,  0), (-1,  0,  0,  1),
        (-1,  0,  0, -1), ( 0, -1, -1,  0),
        ( 0,  1, -1,  0), ( 1,  0,  0, -1),
    ]:
        dungeon._cast_light(visible, tm, 1, 1, 1,
                            1.0, 0.0, max_radius=20,
                            xx=xx, xy=xy, yx=yx, yy=yy)

    # Without the fix, the cast would terminate at column 3 (the first
    # water tile).  With the fix, light reaches the far side.
    assert (5, 1) in visible, "shadowcast must pass through water"
    assert (12, 1) in visible, "shadowcast must reach the far floor"
