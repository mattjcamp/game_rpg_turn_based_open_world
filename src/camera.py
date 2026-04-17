"""
Camera / viewport system.

The camera tracks the party and determines which portion of the map
is visible on screen. It keeps the party centered and clamps to map
edges so we never show out-of-bounds areas (they'd just be ocean anyway,
but it looks cleaner to clamp).

Free-look mode
--------------
When ``free_look`` is True, the camera stops following the party. The
player can pan the viewport independently using ``pan(dcol, drow)`` to
review previously explored tiles under the fog-of-war mask. While
free-look is active, ``update()`` becomes a no-op so party movement
(which shouldn't happen during free-look anyway) won't yank the view
back to center. Call ``exit_free_look()`` to return control to the
party; the next ``update()`` call will re-center on the party.

Viewport dimensions
-------------------
The camera's clamp and centering use ``viewport_cols`` / ``viewport_rows``.
These default to the values in ``settings`` but the actual visible map
area (the renderer's draw region) is a bit smaller because the renderer
reserves pixels at the bottom for the HUD. ``Game`` passes the renderer's
actual viewport dimensions so the camera clamps exactly to what the
renderer will display — keeping free-look panning in sync with the view.
"""

from src.settings import VIEWPORT_COLS, VIEWPORT_ROWS


class Camera:
    """Tracks which portion of the map is visible."""

    def __init__(self, map_width, map_height,
                 viewport_cols=None, viewport_rows=None):
        self.map_width = map_width
        self.map_height = map_height
        # Allow the caller (Game) to pass the renderer's actual tile-grid
        # dimensions; fall back to the full-screen theoretical values.
        self.viewport_cols = (
            viewport_cols if viewport_cols is not None else VIEWPORT_COLS
        )
        self.viewport_rows = (
            viewport_rows if viewport_rows is not None else VIEWPORT_ROWS
        )
        # Top-left corner of the viewport in tile coordinates
        self.offset_col = 0
        self.offset_row = 0
        # Free-look mode: when True, the camera is detached from the
        # party and pans only via ``pan()``.
        self.free_look = False

    def update(self, target_col, target_row):
        """
        Center the camera on the target (usually the party).
        Clamps so the viewport doesn't go outside the map.

        While ``free_look`` is active this is a no-op so the detached
        viewport stays wherever the player panned it.
        """
        if self.free_look:
            return

        # Desired offset: center the target in the viewport
        self.offset_col = target_col - self.viewport_cols // 2
        self.offset_row = target_row - self.viewport_rows // 2

        # Clamp to map boundaries
        self._clamp()

    def _clamp(self):
        """Clamp offset so the viewport stays inside the map."""
        max_col = self.map_width - self.viewport_cols
        max_row = self.map_height - self.viewport_rows
        # When the map is smaller than the viewport, clamp to 0 rather
        # than a negative max (which would wrap offsets off-screen).
        self.offset_col = max(0, min(self.offset_col, max(0, max_col)))
        self.offset_row = max(0, min(self.offset_row, max(0, max_row)))

    def pan(self, dcol, drow):
        """
        Shift the viewport by (dcol, drow) tiles, clamped to the map.
        Used by the free-look / map-scroll feature (Shift + arrows).
        """
        self.offset_col += dcol
        self.offset_row += drow
        self._clamp()

    def enter_free_look(self, start_col=None, start_row=None):
        """
        Detach the camera from its follow target.

        Optional ``start_col`` / ``start_row`` seed the viewport offset
        so free-look begins at a specific top-left position (used by
        states to match whatever the renderer was displaying).
        """
        if start_col is not None:
            self.offset_col = start_col
        if start_row is not None:
            self.offset_row = start_row
        self._clamp()
        self.free_look = True

    def exit_free_look(self):
        """Re-attach the camera. The next ``update()`` will re-center."""
        self.free_look = False

    def set_map_size(self, map_width, map_height):
        """Update map dimensions (e.g. when changing maps)."""
        self.map_width = map_width
        self.map_height = map_height
        self._clamp()

    def world_to_screen(self, col, row):
        """Convert world tile coords to screen tile coords."""
        return (col - self.offset_col, row - self.offset_row)

    def is_visible(self, col, row):
        """Check if a world tile is within the current viewport."""
        sc, sr = self.world_to_screen(col, row)
        return (0 <= sc < self.viewport_cols
                and 0 <= sr < self.viewport_rows)
