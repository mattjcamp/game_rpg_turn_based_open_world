"""
Map representation and a hardcoded test map for initial development.

The map is a 2D grid of tile IDs (see settings.py for tile definitions).
Later, this will be replaced/augmented by procedural generation.
"""

import json
import os

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


def create_test_map():
    """
    Create a small handcrafted test map for initial development.

    This is a 40x30 island map with some variety:
    - Ocean border
    - Grassland interior
    - A mountain range
    - A forest
    - A town
    - A dungeon entrance
    - A river with a bridge
    - Unique tiles scattered for lore and interaction
    """
    W = 40
    H = 30
    tmap = TileMap(W, H, default_tile=TILE_GRASS)

    # --- Ocean border (3 tiles thick on each side) ---
    for row in range(H):
        for col in range(W):
            # Distance from each edge
            dist_edge = min(col, row, W - 1 - col, H - 1 - row)
            if dist_edge < 3:
                tmap.set_tile(col, row, TILE_WATER)
            elif dist_edge == 3:
                # Sandy beaches at the shoreline
                tmap.set_tile(col, row, TILE_SAND)

    # --- Mountain range (upper-right area) ---
    for row in range(6, 12):
        for col in range(25, 34):
            if (col + row) % 3 != 0:  # Irregular shape
                tmap.set_tile(col, row, TILE_MOUNTAIN)

    # --- Forest (lower-left area) ---
    for row in range(18, 25):
        for col in range(6, 16):
            if (col * row) % 5 != 0:  # Irregular shape
                tmap.set_tile(col, row, TILE_FOREST)

    # --- River running north-south through the middle ---
    river_col = 20
    for row in range(4, 26):
        # River meanders a bit
        offset = (row % 7) // 3
        tmap.set_tile(river_col + offset, row, TILE_WATER)

    # --- Bridge across the river ---
    bridge_row = 15
    offset = (bridge_row % 7) // 3
    tmap.set_tile(river_col + offset, bridge_row, TILE_BRIDGE)

    # --- Path from town to dungeon ---
    for col in range(10, 20):
        tmap.set_tile(col, 14, TILE_PATH)
    for col in range(21, 30):
        tmap.set_tile(col, 14, TILE_PATH)
    # Path going north to dungeon
    for row in range(8, 14):
        tmap.set_tile(30, row, TILE_PATH)

    # --- Town (left side of map) ---
    tmap.set_tile(10, 14, TILE_TOWN)

    # --- Dungeon entrance (right side, in the mountains) ---
    tmap.set_tile(30, 8, TILE_DUNGEON)

    # --- House dungeon (near town, introductory quest) ---
    tmap.set_tile(7, 10, TILE_DUNGEON)

    # --- Place unique tiles ---
    unique_defs = load_unique_tiles()
    _place_unique_tiles(tmap, unique_defs)

    return tmap


def _place_unique_tiles(tmap, unique_defs):
    """Place unique tiles on the test map at hand-picked locations."""
    # Placements: (tile_id, col, row)
    placements = [
        # Near the town on the path — signpost
        ("signpost",            12, 14),
        # Shrine south of the path, easy to find early
        ("ancient_shrine",      15, 17),
        # War memorial along the path
        ("war_memorial",        18, 14),
        # Whispering stones in open grass north of path
        ("whispering_stones",   16, 10),
        # Old campfire between town and river
        ("old_campfire",        17, 12),
        # Fairy ring deep in the forest
        ("fairy_ring",          9,  21),
        # Hermit in the forest
        ("hermit_camp",         12, 22),
        # Enchanted spring in forest clearing
        ("enchanted_spring",    8,  19),
        # Oracle pool deeper in forest
        ("oracle_pool",         10, 23),
        # Forgotten grave on the beach
        ("forgotten_grave",     5,  15),
        # Dragon bones on the eastern sand
        ("dragon_bones",        35, 20),
        # Sunken shipwreck on the southern sand coast
        ("sunken_shipwreck",    20, 27),
        # Wandering ghost near the mountains
        ("wandering_ghost",     24, 13),
        # Merchant wagon on the path to dungeon
        ("merchant_wagon",      25, 14),
        # Bandit cache hidden in the forest
        ("bandit_cache",        14, 20),
        # Shadow mark — quest trigger in open grass
        ("shadow_mark",         22, 18),
        # Ancient battlefield in the wide grass east of river
        ("ancient_battlefield", 28, 18),
        # Moongate near the mountains
        ("moongate",            33, 13),
        # Cursed well in grass near forest edge
        ("cursed_well",         7,  17),
        # Poison swamp south-east area
        ("poison_swamp",        30, 22),
        # Elara — worried woman near town who gives the house quest
        ("elara_npc",           8,  12),
    ]

    for tile_id, col, row in placements:
        if tile_id in unique_defs:
            tmap.place_unique(col, row, tile_id, unique_defs[tile_id])
