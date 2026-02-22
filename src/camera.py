"""
Camera / viewport system.

The camera tracks the party and determines which portion of the map
is visible on screen. It keeps the party centered and clamps to map
edges so we never show out-of-bounds areas (they'd just be ocean anyway,
but it looks cleaner to clamp).
"""

from src.settings import VIEWPORT_COLS, VIEWPORT_ROWS


class Camera:
    """Tracks which portion of the map is visible."""

    def __init__(self, map_width, map_height):
        self.map_width = map_width
        self.map_height = map_height
        # Top-left corner of the viewport in tile coordinates
        self.offset_col = 0
        self.offset_row = 0

    def update(self, target_col, target_row):
        """
        Center the camera on the target (usually the party).
        Clamps so the viewport doesn't go outside the map.
        """
        # Desired offset: center the target in the viewport
        self.offset_col = target_col - VIEWPORT_COLS // 2
        self.offset_row = target_row - VIEWPORT_ROWS // 2

        # Clamp to map boundaries
        max_col = self.map_width - VIEWPORT_COLS
        max_row = self.map_height - VIEWPORT_ROWS
        self.offset_col = max(0, min(self.offset_col, max_col))
        self.offset_row = max(0, min(self.offset_row, max_row))

    def world_to_screen(self, col, row):
        """Convert world tile coords to screen tile coords."""
        return (col - self.offset_col, row - self.offset_row)

    def is_visible(self, col, row):
        """Check if a world tile is within the current viewport."""
        sc, sr = self.world_to_screen(col, row)
        return 0 <= sc < VIEWPORT_COLS and 0 <= sr < VIEWPORT_ROWS
