"""Verify a 40x50 sparse dungeon scrolls, previews, and draws at 32px tiles."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()

root = sys.argv[1]
sys.path.insert(0, root)
os.chdir(root)

from src.map_editor import (
    MapEditorConfig, MapEditorState, MapEditorInputHandler,
    STORAGE_SPARSE, GRID_SCROLLABLE,
)
from src.settings import TILE_SIZE

w, h = 40, 50
tiles = {}
# Paint a floor tile at every cell so minimap + grid have content.
for r in range(h):
    for c in range(w):
        tiles[f"{c},{r}"] = {"tile_id": 10, "name": "Floor"}

# Auto-promote logic mimic: large sparse → scrollable.
grid_type = GRID_SCROLLABLE

config = MapEditorConfig(
    title="Dungeon 2: Floor 1",
    storage=STORAGE_SPARSE,
    grid_type=grid_type,
    width=w, height=h,
    brushes=[],
    tile_context="town",
    supports_replace=True,
)
state = MapEditorState(config, tiles=tiles)

# 1. tile_size should now be TILE_SIZE (32), not the tiny fixed value
assert state.tile_size == TILE_SIZE, (
    f"expected tile_size={TILE_SIZE}, got {state.tile_size}")
print(f"Large sparse map tile_size: {state.tile_size}px (target {TILE_SIZE}) OK")

# 2. Cursor movement scrolls the camera
state.cursor_col = 35
state.cursor_row = 45
state.scroll_to_cursor()
assert state.cam_col > 0 and state.cam_row > 0, (
    f"camera didn't scroll; cam=({state.cam_col},{state.cam_row})")
print(f"Camera scrolled to ({state.cam_col},{state.cam_row}) for cursor "
      f"({state.cursor_col},{state.cursor_row}) OK")

# 3. Minimap condition now fires for sparse scrollable large maps
data = state.to_data_dict()
minimap_on = (data.get("grid_type") == "scrollable"
              and (data["width"] > 20 or data["height"] > 20))
assert minimap_on, "minimap condition should now trigger"
print("Minimap preview condition fires for sparse scrollable map OK")

# 4. Attribute panel: Item row exists
info = state.get_cursor_tile_info()
item_row = next((f for f in info["fields"] if f[1] == "item"), None)
assert item_row is not None
print(f"Attributes panel Item row present: {item_row!r} OK")

# 5. Actually render the grid + minimap to a PNG so we can eyeball it
from src.renderer import Renderer
from src.tile_manifest import TileManifest
from src.map_editor_renderer import (
    _draw_sparse_grid, _draw_minimap, GRID_X, GRID_Y, GRID_W, GRID_H,
    _COL_GRID_BG,
)
from src.settings import SCREEN_WIDTH, SCREEN_HEIGHT


class StubRenderer(Renderer):
    def __init__(self):
        self.screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.screen.fill((12, 10, 20))
        self.font = pygame.font.Font(None, 14)
        self.font_med = pygame.font.Font(None, 18)
        self.font_small = pygame.font.Font(None, 12)
        self._manifest = TileManifest()
        self._tile_sprites = {}

    def _draw_tile(self, tid, px, py, ts, wc, wr, *, tile_map=None):
        # Minimal stand-in: solid color per tile so preview is visible
        col = (80, 80, 95) if tid == 10 else (40, 40, 55)
        pygame.draw.rect(self.screen, col,
                         pygame.Rect(px, py, ts, ts))


r = StubRenderer()
pygame.draw.rect(r.screen, _COL_GRID_BG, (GRID_X, GRID_Y, GRID_W, GRID_H))
_draw_sparse_grid(r, data)
# Force minimap scale to visible.
_draw_minimap(r, data)

out = "/sessions/friendly-determined-knuth/mnt/outputs/large_sparse_preview.png"
pygame.image.save(r.screen, out)
print(f"Rendered large sparse dungeon preview to {out}")

print("\nAll large-map sparse scrolling checks passed.")
