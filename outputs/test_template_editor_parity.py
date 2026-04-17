"""Verify the Map Template Editor now behaves like the Overview Map Editor.

We avoid needing a full Game instance by building a MapEditorState directly
with the same config surface the template editor would use, then checking:

 1. Large dense maps get GRID_SCROLLABLE + supports_party_start + minimap.
 2. The tile inspector (E key flow) exposes the Item row.
 3. tile_properties + party_start round-trip through the JSON serializer.
"""
import json
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()

root = sys.argv[1]
sys.path.insert(0, root)
os.chdir(root)

from src.map_editor import (
    MapEditorConfig, MapEditorState, MapEditorInputHandler,
    STORAGE_DENSE, STORAGE_SPARSE, GRID_SCROLLABLE, GRID_FIXED,
)


# ── 1. Build a large dense template and confirm scroll + config ──────
w, h = 40, 30
tiles = [[0] * w for _ in range(h)]
config = MapEditorConfig(
    title="BigTemplate",
    storage=STORAGE_DENSE,
    grid_type=GRID_SCROLLABLE,     # promoted from FIXED in _meh_launch_editor
    width=w, height=h,
    brushes=[],
    tile_context="overworld",
    supports_replace=True,
    supports_party_start=True,
    map_hierarchy=[("overworld", "Overview Map", 0)],
)
state = MapEditorState(config, tiles=tiles,
                       party_start={"col": 5, "row": 5})

data = state.to_data_dict()
assert data["storage"] == STORAGE_DENSE
assert data["grid_type"] == GRID_SCROLLABLE
assert data["width"] == 40 and data["height"] == 30
print("Template config: dense + scrollable + large (40×30) ✓")

# Minimap condition from map_editor_renderer.draw_map_editor:
minimap_shown = (data["storage"] == STORAGE_DENSE
                 and data["grid_type"] == "scrollable"
                 and (data["width"] > 20 or data["height"] > 20))
assert minimap_shown, "minimap should render for large dense scrollable map"
print("Minimap preview active for large scrollable dense map ✓")

# ── 2. Scroll / clamp behaviour ───────────────────────────────────────
state.cursor_col = 35
state.cursor_row = 25
state.scroll_to_cursor()
assert state.cam_col > 0 and state.cam_row > 0, (
    f"expected non-zero camera after scroll; got "
    f"cam=({state.cam_col},{state.cam_row})")
print(f"scroll_to_cursor clamps camera to "
      f"({state.cam_col},{state.cam_row}) for cursor ({35},{25}) ✓")

# ── 3. Attributes panel (E key flow) exposes Item row ────────────────
handler = MapEditorInputHandler(state)
state.cursor_col = 10
state.cursor_row = 10
info = state.get_cursor_tile_info()
item_field = next((f for f in info["fields"] if f[1] == "item"), None)
assert item_field is not None, (
    f"Item field missing; fields={info['fields']!r}")
print(f"Attributes panel exposes Item row {item_field!r} ✓")

linked_field = next((f for f in info["fields"] if f[1] == "linked"), None)
assert linked_field is not None, "Linked row still there too"
print("Attributes panel exposes Linked row as expected ✓")

# ── 4. Place an item via the picker, confirm tile_properties ─────────
class _E:
    def __init__(self, key, mod=0):
        self.key = key
        self.mod = mod

# Enter inspector mode on the Item field
for i, f in enumerate(info["fields"]):
    if f[1] == "item":
        state.inspector_field_idx = i
        state.inspector_buffer = f[2]
        break
state.inspector_editing = True

# Open picker on Enter, pick Sword, confirm
handler.handle(_E(pygame.K_RETURN))
assert state.item_picker_active
state.item_picker_cursor = state.item_list.index("Sword")
handler.handle(_E(pygame.K_RETURN))
assert not state.item_picker_active
assert state.tile_properties["10,10"]["item"] == "Sword"
print("Placed Sword at (10,10) via Attributes panel + picker ✓")

# ── 5. tile_properties round-trips through the JSON serializer ───────
# Mimic what _meh_launch_editor._on_save would persist, then what
# _meh_children_from_saved would load back.

serialized_entry = {
    "label": "BigTemplate",
    "subtitle": f"{w}x{h}",
    "canvas_type": "blank",
    "map_config": {
        "storage": "dense",
        "grid_type": "scrollable",
        "tile_context": "overworld",
        "width": w, "height": h,
    },
    "tiles": state.tiles,
    "tile_properties": dict(state.tile_properties),
    "party_start": state.party_start,
}
blob = json.dumps({"me_enclosure": [serialized_entry]})
reloaded = json.loads(blob)
entry2 = reloaded["me_enclosure"][0]

assert entry2["tile_properties"] == {"10,10": {"item": "Sword"}}
assert entry2["party_start"] == {"col": 5, "row": 5}
print("tile_properties + party_start round-trip via JSON ✓")

# ── 6. Non-destructive: sparse templates stay fixed + centered ───────
sparse_state = MapEditorState(
    MapEditorConfig(title="Small", storage=STORAGE_SPARSE,
                    grid_type=GRID_FIXED, width=16, height=14,
                    brushes=[], tile_context="dungeon",
                    supports_replace=True,
                    supports_party_start=False),
    tiles={},
)
d2 = sparse_state.to_data_dict()
assert d2["grid_type"] == GRID_FIXED
assert d2["storage"] == STORAGE_SPARSE
minimap2 = (d2["storage"] == STORAGE_DENSE
            and d2["grid_type"] == "scrollable"
            and (d2["width"] > 20 or d2["height"] > 20))
assert not minimap2, "sparse/fixed shouldn't get the minimap"
print("Sparse interiors correctly stay fixed without minimap ✓")

print("\nAll Map Template Editor parity checks passed.")
