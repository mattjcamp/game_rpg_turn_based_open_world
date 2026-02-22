"""
Map representation and a hardcoded test map for initial development.

The map is a 2D grid of tile IDs (see settings.py for tile definitions).
Later, this will be replaced/augmented by procedural generation.
"""

from src.settings import *


class TileMap:
    """Holds a 2D grid of tile IDs and provides access methods."""

    def __init__(self, width, height, default_tile=TILE_GRASS):
        self.width = width
        self.height = height
        # 2D list: self.tiles[row][col]
        self.tiles = [[default_tile for _ in range(width)] for _ in range(height)]

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

    return tmap
