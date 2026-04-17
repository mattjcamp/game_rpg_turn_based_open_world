"""
Unified map editor — configuration-driven tile editor used by all map
editing surfaces (overview map, overview interiors, town layouts, etc.).

Each editor instance is described by a :class:`MapEditorConfig` that tells
the system how the grid is stored (dense 2D array vs sparse dict), which
tile palette to use, what link types are available, and how to persist
changes.  :class:`MapEditorState` wraps the live editing state (cursor,
camera, brush, dirty flag) and exposes a common API regardless of storage
format.  :class:`MapEditorInputHandler` translates Pygame key events into
state mutations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import pygame

from src.settings import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    TILE_SIZE,
    TILE_DEFS,
    TILE_GRASS,
)


# ─── Brush definition ────────────────────────────────────────────────

@dataclass
class Brush:
    """A single entry in the editor palette.

    Regular brushes paint a single tile.  Object brushes (``object_data``
    is not None) stamp a multi-tile pattern from an Object Template.
    Folder-header brushes (``is_folder_header`` is True) are non-paintable
    separators that toggle group collapse in the palette.
    """
    name: str
    tile_id: Optional[int]    # None for eraser / folder headers
    path: Optional[str] = None  # sprite asset path (interior brushes)
    group: Optional[str] = None  # folder/category this brush belongs to
    is_folder_header: bool = False  # True → this entry is a collapsible header
    object_data: Optional[Dict] = None  # sparse tiles dict for object stamps
    object_w: int = 0  # object template width (cells)
    object_h: int = 0  # object template height (cells)

    @property
    def is_eraser(self) -> bool:
        return self.tile_id is None and not self.is_folder_header and self.object_data is None

    @property
    def is_object(self) -> bool:
        return self.object_data is not None


# ─── Configuration ────────────────────────────────────────────────────

STORAGE_DENSE = "dense"    # 2D list  [row][col] = tile_id
STORAGE_SPARSE = "sparse"  # dict     "col,row" -> {tile_id, name, path?, ...}

GRID_SCROLLABLE = "scrollable"  # overview map: cursor scrolls large map
GRID_FIXED = "fixed"            # interiors: whole grid fits on screen


@dataclass
class MapEditorConfig:
    """Describes *how* an editor instance should behave.

    Create one for each editor surface and pass it to
    :class:`MapEditorState`.
    """

    # -- Identity --
    title: str = "Map Editor"

    # -- Grid storage --
    storage: str = STORAGE_DENSE      # "dense" or "sparse"
    grid_type: str = GRID_SCROLLABLE  # "scrollable" or "fixed"

    # -- Dimensions (for dense: from loaded data; for sparse: from layout) --
    width: int = 30
    height: int = 23

    # -- Tile palette (list of Brush objects) --
    brushes: List[Brush] = field(default_factory=list)

    # -- Tile context filter (used when building palette dynamically) --
    tile_context: str = "overworld"  # "overworld", "dungeon", etc.

    supports_replace: bool = False       # R key: replace all of tile type
    supports_party_start: bool = False   # P key: place party start position

    # -- Eraser behaviour --
    eraser_tile_id: int = TILE_GRASS  # dense: what eraser paints
    # sparse: eraser deletes the key

    # -- Tile size override (None = TILE_SIZE constant) --
    tile_size: Optional[int] = None

    # -- Save callback (called with the editor state) --
    on_save: Optional[Callable] = None

    # -- Exit callback --
    on_exit: Optional[Callable] = None

    # -- Map hierarchy for tile link picker --
    # List of (map_id, display_label, indent_level) tuples.
    # Built by the caller from module data.
    map_hierarchy: List = field(default_factory=list)


# ─── State ────────────────────────────────────────────────────────────

class MapEditorState:
    """Live editing state for one editor instance.

    Wraps cursor, camera, brush selection, tile data, and dirty flag.
    The same public API works regardless of dense vs sparse storage.
    """

    def __init__(self, config: MapEditorConfig,
                 tiles: Any = None,
                 interior_list: Optional[List] = None,
                 party_start: Optional[Dict] = None):
        self.config = config

        # Grid data
        if tiles is None:
            if config.storage == STORAGE_DENSE:
                self.tiles = [[config.eraser_tile_id
                               for _ in range(config.width)]
                              for _ in range(config.height)]
            else:
                self.tiles = {}
        else:
            self.tiles = tiles

        # Party start position (overview map: {"col": int, "row": int} or None)
        self.party_start: Optional[Dict] = party_start

        # Interior list reference (for link picker options)
        self.interior_list: List = interior_list if interior_list is not None else []

        # Cursor
        self.cursor_col: int = config.width // 2
        self.cursor_row: int = config.height // 2

        # Camera (scrollable grids only)
        self.cam_col: int = 0
        self.cam_row: int = 0

        # Brush
        self.brush_idx: int = 0

        # Dirty flag
        self.dirty: bool = False

        # Save flash timer (seconds remaining, counts down each frame)
        self.save_flash: float = 0.0

        # Continuous paint mode — when True, moving the cursor also paints
        self.painting: bool = False

        # Mouse drag state (set by handle_mouse)
        self._mouse_dragging: bool = False
        self._middle_drag_start = None
        self._middle_drag_cam = None

        # Brush folder collapse state (group name → is_open)
        # All folders start open by default
        self.brush_folders: Dict[str, bool] = {}
        for b in config.brushes:
            if b.is_folder_header and b.name not in self.brush_folders:
                self.brush_folders[b.name] = True

        # Per-tile instance properties (dense maps).
        # Maps "col,row" → dict of editable properties for that tile.
        # Example: {"10,14": {"label": "New Haven", "target": "town:New Haven"}}
        # Tiles without an entry use defaults from TILE_DEFS.
        self.tile_properties: Dict[str, Dict] = {}
        if hasattr(config, '_initial_tile_properties'):
            self.tile_properties = dict(config._initial_tile_properties)

        # Tile inspector editing state
        self.inspector_editing: bool = False
        self.inspector_field_idx: int = 0
        self.inspector_buffer: str = ""

        # Map picker overlay (for choosing link target map)
        self.map_picker_active: bool = False
        self.map_picker_cursor: int = 0
        self.map_picker_scroll: int = 0

        # Replace tile overlay
        self.replacing: bool = False         # replace tile overlay
        self.replace_src_tile: Optional[int] = None
        self.replace_src_name: str = ""
        self.replace_src_empty: bool = False
        self.replace_dst_idx: int = 0

        # ── Item picker overlay state ──
        # When ``item_picker_active`` is True, a modal overlay lets the
        # user choose an item to place on the cursor tile. The choice
        # is written into tile_properties[pos]["item"]. Driven from the
        # Attributes panel's Item field (type "item_picker"), not a
        # global shortcut.
        self.item_list: List[str] = []       # item names (lazy-loaded)
        self.item_picker_active: bool = False
        self.item_picker_cursor: int = 0
        self.item_picker_scroll: int = 0

        # Centre camera on cursor
        if config.grid_type == GRID_SCROLLABLE:
            self.scroll_to_cursor()

    # -- Computed tile size --

    @property
    def tile_size(self) -> int:
        if self.config.tile_size is not None:
            return self.config.tile_size
        if self.config.grid_type == GRID_FIXED:
            return self._compute_fixed_tile_size()
        return TILE_SIZE

    def _compute_fixed_tile_size(self) -> int:
        header_h, footer_h, left_w = 36, 28, 180
        right_w = SCREEN_WIDTH - left_w - 4 - 4
        grid_w = right_w - 8
        grid_h = SCREEN_HEIGHT - header_h - footer_h - 4 - 8
        ts = min(grid_w // max(self.config.width, 1),
                 grid_h // max(self.config.height, 1),
                 24)
        return max(ts, 4)

    # -- Brush helpers --

    def _visible_indices(self) -> List[int]:
        """Return indices of brushes currently visible (not hidden by
        collapsed folders)."""
        brushes = self.config.brushes
        visible = []
        cur_group: Optional[str] = None
        collapsed = False
        for i, b in enumerate(brushes):
            if b.is_folder_header:
                cur_group = b.name
                collapsed = not self.brush_folders.get(b.name, True)
                visible.append(i)  # headers are always visible
            elif collapsed and b.group == cur_group:
                continue  # hidden by collapsed folder
            else:
                visible.append(i)
        return visible

    @property
    def current_brush(self) -> Brush:
        brushes = self.config.brushes
        if not brushes:
            return Brush(name="(none)", tile_id=None)
        return brushes[self.brush_idx % len(brushes)]

    def toggle_folder(self):
        """If the current brush is a folder header, toggle it."""
        brush = self.current_brush
        if brush.is_folder_header:
            self.brush_folders[brush.name] = not self.brush_folders.get(
                brush.name, True)

    def cycle_brush(self, delta: int = 1):
        n = len(self.config.brushes)
        if n == 0:
            return
        vis = self._visible_indices()
        if not vis:
            return
        # Find current position in visible list
        try:
            pos = vis.index(self.brush_idx)
        except ValueError:
            pos = 0
        pos = (pos + delta) % len(vis)
        self.brush_idx = vis[pos]

    # -- Cursor movement --

    def move_cursor(self, dc: int, dr: int):
        self.cursor_col = max(0, min(self.config.width - 1,
                                     self.cursor_col + dc))
        self.cursor_row = max(0, min(self.config.height - 1,
                                     self.cursor_row + dr))
        if self.config.grid_type == GRID_SCROLLABLE:
            self.scroll_to_cursor()

    def scroll_to_cursor(self):
        """Keep viewport centred around cursor (scrollable grids)."""
        header_h, footer_h, left_w = 36, 28, 180
        right_w = SCREEN_WIDTH - left_w - 4 - 4
        grid_w = right_w - 8
        grid_h = SCREEN_HEIGHT - header_h - footer_h - 4 - 8
        ts = self.tile_size
        vis_cols = grid_w // ts
        vis_rows = grid_h // ts
        self.cam_col = max(0, min(self.cursor_col - vis_cols // 2,
                                  self.config.width - vis_cols))
        self.cam_row = max(0, min(self.cursor_row - vis_rows // 2,
                                  self.config.height - vis_rows))

    def scroll_camera(self, dc: int, dr: int):
        """Nudge camera by (dc, dr) tiles, clamped to map bounds."""
        header_h, footer_h, left_w = 36, 28, 180
        right_w = SCREEN_WIDTH - left_w - 4 - 4
        grid_w = right_w - 8
        grid_h = SCREEN_HEIGHT - header_h - footer_h - 4 - 8
        ts = self.tile_size
        vis_cols = grid_w // ts
        vis_rows = grid_h // ts
        self.cam_col = max(0, min(self.cam_col + dc,
                                  self.config.width - vis_cols))
        self.cam_row = max(0, min(self.cam_row + dr,
                                  self.config.height - vis_rows))

    def pixel_to_grid(self, px: int, py: int):
        """Convert screen pixel (px, py) to grid (col, row) or None."""
        from src.map_editor_renderer import GRID_X, GRID_Y, GRID_W, GRID_H
        ts = self.tile_size
        map_w, map_h = self.config.width, self.config.height
        vis_cols = GRID_W // ts
        vis_rows = GRID_H // ts
        total_w = min(map_w, vis_cols) * ts
        total_h = min(map_h, vis_rows) * ts
        ox = GRID_X + (GRID_W - total_w) // 2
        oy = GRID_Y + (GRID_H - total_h) // 2
        if px < ox or py < oy:
            return None
        gc = (px - ox) // ts + self.cam_col
        gr = (py - oy) // ts + self.cam_row
        if 0 <= gc < map_w and 0 <= gr < map_h:
            return (gc, gr)
        return None

    # -- Tile access (works for both storage types) --

    def get_tile(self, col: int, row: int) -> Any:
        """Return tile data at (col, row).

        Dense: returns int tile_id.
        Sparse: returns dict or None.
        """
        if self.config.storage == STORAGE_DENSE:
            if 0 <= row < self.config.height and 0 <= col < self.config.width:
                return self.tiles[row][col]
            return None
        else:
            return self.tiles.get(f"{col},{row}")

    def set_tile(self, col: int, row: int, value: Any):
        """Set tile data at (col, row).

        Dense: value is int tile_id.
        Sparse: value is dict or None (None = delete).
        """
        if self.config.storage == STORAGE_DENSE:
            if 0 <= row < self.config.height and 0 <= col < self.config.width:
                if self.tiles[row][col] != value:
                    self.tiles[row][col] = value
                    self.dirty = True
        else:
            pos_key = f"{col},{row}"
            if value is None:
                if pos_key in self.tiles:
                    del self.tiles[pos_key]
                    self.dirty = True
            else:
                self.tiles[pos_key] = value
                self.dirty = True

    # -- Paint action (applies current brush at cursor) --

    def paint(self):
        """Apply the current brush at the cursor position.

        Regular brushes paint a single tile.  Object brushes stamp the
        full object template pattern relative to the cursor origin.
        Folder headers do nothing.
        """
        brush = self.current_brush
        if brush.is_folder_header:
            return
        col, row = self.cursor_col, self.cursor_row

        # ── Object stamp (multi-tile) ──
        if brush.is_object:
            self._paint_object(brush, col, row)
            return

        if self.config.storage == STORAGE_DENSE:
            if brush.is_eraser:
                tid = self.config.eraser_tile_id
            else:
                tid = brush.tile_id
            self.set_tile(col, row, tid)

        else:  # sparse
            if brush.is_eraser:
                self.set_tile(col, row, None)
            else:
                td = {"tile_id": brush.tile_id, "name": brush.name}
                if brush.path:
                    td["path"] = brush.path
                self.set_tile(col, row, td)

    def _paint_object(self, brush: 'Brush', origin_c: int, origin_r: int):
        """Stamp an object template onto the canvas at *origin_c, origin_r*.

        Tile positions are normalised so the top-left occupied cell of the
        object aligns with the cursor.  Works with both dense and sparse
        storage.
        """
        obj = brush.object_data  # sparse dict "c,r" -> tile dict
        if not obj:
            return

        # Find the top-left corner of actual content
        min_c, min_r = _object_origin(obj)

        for pos_key, td_src in obj.items():
            parts = pos_key.split(",")
            if len(parts) != 2:
                continue
            oc, orow = int(parts[0]), int(parts[1])
            tc = origin_c + (oc - min_c)
            tr = origin_r + (orow - min_r)
            if tc < 0 or tr < 0:
                continue
            if tc >= self.config.width or tr >= self.config.height:
                continue

            if self.config.storage == STORAGE_DENSE:
                tid = td_src.get("tile_id") if isinstance(td_src, dict) else td_src
                if tid is not None:
                    self.set_tile(tc, tr, tid)
            else:
                # Copy the tile dict so we don't mutate the brush
                if isinstance(td_src, dict):
                    td = dict(td_src)
                else:
                    td = {"tile_id": td_src}
                self.set_tile(tc, tr, td)


    # -- Tile instance properties --

    def get_tile_props(self, col: int, row: int) -> Dict:
        """Return per-instance properties for tile at (col, row).
        Returns empty dict if no custom properties are set."""
        return self.tile_properties.get(f"{col},{row}", {})

    def set_tile_prop(self, col: int, row: int, key: str, value):
        """Set a single instance property on the tile at (col, row)."""
        pos_key = f"{col},{row}"
        if pos_key not in self.tile_properties:
            self.tile_properties[pos_key] = {}
        self.tile_properties[pos_key][key] = value
        self.dirty = True

    def remove_tile_prop(self, col: int, row: int, key: str):
        """Remove a single instance property. Cleans up empty dicts."""
        pos_key = f"{col},{row}"
        props = self.tile_properties.get(pos_key)
        if props and key in props:
            del props[key]
            if not props:
                del self.tile_properties[pos_key]
            self.dirty = True

    # -- Items placement helpers (driven by the Attributes panel) --

    def _load_item_names(self) -> List[str]:
        """Collect every known item name from party data (lazy, cached).

        The picker shows every item ever defined in items.json, grouped
        by category via party.WEAPONS / ARMORS / ITEM_INFO. Uses a set
        union so names unique to any one table are still offered.
        """
        if self.item_list:
            return self.item_list
        try:
            from src.party import WEAPONS, ARMORS, ITEM_INFO
            names = sorted(set(list(WEAPONS.keys())
                               + list(ARMORS.keys())
                               + list(ITEM_INFO.keys())))
        except Exception:
            names = []
        self.item_list = names
        return names

    def place_item_at_cursor(self, name: str):
        """Write *name* into tile_properties[cursor]["item"]."""
        if not name:
            return
        self.set_tile_prop(self.cursor_col, self.cursor_row, "item", name)

    def clear_item_at_cursor(self):
        """Remove a placed item at the cursor position, if any."""
        self.remove_tile_prop(self.cursor_col, self.cursor_row, "item")

    def cursor_item_name(self) -> Optional[str]:
        """Return the item currently placed at the cursor, or None."""
        return self.get_tile_props(self.cursor_col,
                                   self.cursor_row).get("item")

    def get_cursor_tile_info(self) -> Dict:
        """Build a dict describing the tile under the cursor for the inspector.

        Returns a list of fields: (label, key, value, editable).
        Read-only fields have keys starting with '_'.
        Editable fields use plain keys that map into tile_properties.
        """
        from src.settings import (
            TILE_TOWN, TILE_DUNGEON, TILE_DUNGEON_CLEARED,
            TILE_SPAWN, TILE_SPAWN_CAMPFIRE, TILE_SPAWN_GRAVEYARD,
        )
        col, row = self.cursor_col, self.cursor_row
        tile_id = None

        if self.config.storage == STORAGE_DENSE:
            if 0 <= row < self.config.height and 0 <= col < self.config.width:
                tile_id = self.tiles[row][col]
        else:
            td = self.tiles.get(f"{col},{row}")
            if isinstance(td, dict):
                tile_id = td.get("tile_id")
            elif td is not None:
                tile_id = td

        tdef = TILE_DEFS.get(tile_id, {}) if tile_id is not None else {}
        tile_name = tdef.get("name", f"Tile {tile_id}" if tile_id is not None else "Empty")
        walkable = tdef.get("walkable", False)
        interaction = tdef.get("interaction_type", "")

        # Per-instance properties (user-edited overrides for this tile)
        props = self.get_tile_props(col, row)

        # Build fields list: (label, key, value, editable)
        fields = []
        if tile_id is None:
            return {"tile_id": None, "tile_name": "Empty",
                    "walkable": False, "fields": [], "props": {},
                    "col": col, "row": row}

        # ── Header: always show type ──
        fields.append(("Type", "_type", tile_name, False))

        # ── Spawn tiles: show all spawn attributes ──
        _SPAWN_IDS = {TILE_SPAWN, TILE_SPAWN_CAMPFIRE,
                      TILE_SPAWN_GRAVEYARD}
        # Also check tile_id 69 (Dragon) which may not have a constant
        if interaction == "spawn" or tile_id in _SPAWN_IDS:
            fields.append(("Monsters", "spawn_monsters",
                           props.get("spawn_monsters", ""), True))
            fields.append(("Spawn %", "spawn_chance",
                           props.get("spawn_chance", "20"), True))
            fields.append(("Radius", "spawn_radius",
                           props.get("spawn_radius", "3"), True))
            fields.append(("Max Spawned", "max_spawned",
                           props.get("max_spawned", "2"), True))

        # ── Town tile: which town does this connect to ──
        elif tile_id == TILE_TOWN:
            fields.append(("Town Name", "target",
                           props.get("target", ""), True))

        # ── Dungeon tile: which dungeon ──
        elif tile_id in (TILE_DUNGEON, TILE_DUNGEON_CLEARED):
            fields.append(("Dungeon Name", "target",
                           props.get("target", ""), True))

        # ── Sign tiles ──
        elif interaction == "sign":
            fields.append(("Sign Text", "sign_text",
                           props.get("sign_text",
                                     tdef.get("interaction_data", "")),
                           True))

        # ── Shop tiles ──
        elif interaction == "shop":
            fields.append(("Shop Type", "shop_type",
                           props.get("shop_type",
                                     tdef.get("interaction_data", "")),
                           True))

        # ── Any other tile: just show a label field ──
        else:
            fields.append(("Label", "label",
                           props.get("label", ""), True))

        # ── Universal: tile link (any tile can link to another map) ──
        is_linked = props.get("linked", False)
        # "toggle" type: press Enter to flip True/False
        fields.append(("Linked", "linked",
                       "yes" if is_linked else "no", "toggle"))
        if is_linked:
            link_map = props.get("link_map", "")
            fields.append(("Target Map", "link_map",
                           link_map, "map_picker"))
            # Procedural dungeons don't have meaningful coordinates —
            # the entry point is determined at generation time.
            # Only show X/Y for non-dungeon targets.
            _needs_coords = not link_map.startswith("dungeon:")
            if _needs_coords:
                fields.append(("Target X", "link_x",
                               props.get("link_x", "0"), True))
                fields.append(("Target Y", "link_y",
                               props.get("link_y", "0"), True))

        # ── Universal: placed item (opens a visual item picker) ──
        placed_item = props.get("item", "")
        fields.append(("Item", "item",
                       placed_item if placed_item else "(none)",
                       "item_picker"))

        return {
            "tile_id": tile_id,
            "tile_name": tile_name,
            "walkable": walkable,
            "fields": fields,
            "props": props,
            "col": col,
            "row": row,
        }

    # -- Replace all (sparse interiors) --

    def replace_all_tiles(self, src_tile_id: Optional[int],
                          src_empty: bool,
                          dst_brush: Brush):
        """Replace all tiles matching source with destination brush."""
        tiles = self.tiles
        w, h = self.config.width, self.config.height

        if self.config.storage == STORAGE_DENSE:
            # Dense: tiles[row][col] = tile_id (int)
            if src_tile_id is None or dst_brush.tile_id is None:
                return
            dst_id = dst_brush.tile_id if not dst_brush.is_eraser else self.config.eraser_tile_id
            for r in range(h):
                for c in range(w):
                    if tiles[r][c] == src_tile_id:
                        tiles[r][c] = dst_id
                        self.dirty = True
        elif self.config.storage == STORAGE_SPARSE:
            if src_empty:
                # Replace all empty cells with destination
                if dst_brush.tile_id is not None:
                    for r in range(h):
                        for c in range(w):
                            pk = f"{c},{r}"
                            if pk not in tiles:
                                td = {"tile_id": dst_brush.tile_id,
                                      "name": dst_brush.name}
                                if dst_brush.path:
                                    td["path"] = dst_brush.path
                                tiles[pk] = td
                    self.dirty = True
            elif dst_brush.is_eraser:
                # Replace source tiles with eraser (remove)
                to_del = [k for k, v in tiles.items()
                          if isinstance(v, dict)
                          and v.get("tile_id") == src_tile_id]
                for k in to_del:
                    del tiles[k]
                if to_del:
                    self.dirty = True
            else:
                # Replace source tile_id with destination
                for k, v in tiles.items():
                    if isinstance(v, dict) and v.get("tile_id") == src_tile_id:
                        v["tile_id"] = dst_brush.tile_id
                        v["name"] = dst_brush.name
                        if dst_brush.path:
                            v["path"] = dst_brush.path
                        elif "path" in v:
                            del v["path"]
                        self.dirty = True

    # -- Data export (for saving / renderer consumption) --

    def to_data_dict(self) -> Dict:
        """Return a dict summarising the editor state for the renderer."""
        cfg = self.config
        return {
            "title": cfg.title,
            "storage": cfg.storage,
            "grid_type": cfg.grid_type,
            "tiles": self.tiles,
            "width": cfg.width,
            "height": cfg.height,
            "cursor_col": self.cursor_col,
            "cursor_row": self.cursor_row,
            "cam_col": self.cam_col,
            "cam_row": self.cam_row,
            "tile_size": self.tile_size,
            "brushes": cfg.brushes,
            "brush_idx": self.brush_idx,
            "brush_name": self.current_brush.name,
            "brush_folders": self.brush_folders,
            "painting": self.painting,
            "dirty": self.dirty,
            "save_flash": self.save_flash,
            "party_start": self.party_start,
            "tile_context": cfg.tile_context,
            "replacing": self.replacing,
            "replace_src_tile": self.replace_src_tile,
            "replace_src_name": self.replace_src_name,
            "replace_src_empty": self.replace_src_empty,
            "replace_dst_idx": self.replace_dst_idx,
            # Tile inspector
            "tile_inspector": self.get_cursor_tile_info(),
            "inspector_editing": self.inspector_editing,
            "inspector_field_idx": self.inspector_field_idx,
            "inspector_buffer": self.inspector_buffer,
            "tile_properties": self.tile_properties,
            "map_picker_active": self.map_picker_active,
            "map_picker_cursor": self.map_picker_cursor,
            "map_picker_scroll": self.map_picker_scroll,
            "map_hierarchy": self.config.map_hierarchy,
            # Item picker overlay (opened from the Attributes panel)
            "item_picker_active": self.item_picker_active,
            "item_picker_cursor": self.item_picker_cursor,
            "item_picker_scroll": self.item_picker_scroll,
            "item_list": self.item_list,
            "cursor_item": self.cursor_item_name(),
        }


# ─── Input Handler ────────────────────────────────────────────────────

class MapEditorInputHandler:
    """Translates Pygame key events into MapEditorState mutations.

    Handles cursor movement, brush cycling, painting, link pickers,
    replace overlay, save, and exit — all driven by the config flags.
    """

    def __init__(self, state: MapEditorState,
                 is_save_shortcut: Optional[Callable] = None):
        self.state = state
        # Optional callback to check if an event is Ctrl+S / Cmd+S
        self._is_save = is_save_shortcut or self._default_is_save

    @staticmethod
    def _default_is_save(event) -> bool:
        mods = getattr(event, 'mod', 0) or pygame.key.get_mods()
        return (event.key == pygame.K_s
                and bool(mods & (pygame.KMOD_CTRL | pygame.KMOD_META)))

    def handle(self, event) -> Optional[str]:
        """Process a KEYDOWN event.  Returns an action string or None.

        Possible return values:
          "exit"  — editor should close
          "save"  — explicit save requested
          None    — normal key handled (or ignored)
        """
        st = self.state
        cfg = st.config

        # ── Overlay intercepts ──
        if st.inspector_editing:
            return self._handle_inspector_input(event)

        if st.replacing:
            return self._handle_replace_overlay(event)

        # ── Escape ──
        if event.key == pygame.K_ESCAPE:
            if st.dirty and cfg.on_save:
                cfg.on_save(st)
            if cfg.on_exit:
                cfg.on_exit(st)
            return "exit"

        # ── Cursor movement (Shift = fast-scroll 8 tiles) ──
        dc, dr = 0, 0
        if event.key in (pygame.K_UP, pygame.K_w):
            dr = -1
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            # Only treat s as down if Ctrl is NOT held (avoid Ctrl+S)
            if event.key == pygame.K_s:
                mods = getattr(event, 'mod', 0) or pygame.key.get_mods()
                if mods & (pygame.KMOD_CTRL | pygame.KMOD_META):
                    pass  # fall through to save check
                else:
                    dr = 1
            else:
                dr = 1
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            dc = -1
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            dc = 1

        if dc or dr:
            mods = getattr(event, 'mod', 0) or pygame.key.get_mods()
            if mods & pygame.KMOD_SHIFT:
                # Fast-scroll: jump 8 tiles at a time
                dc *= 8
                dr *= 8
            for _ in range(abs(dc) + abs(dr)):
                step_c = min(max(dc, -1), 1) if dc else 0
                step_r = min(max(dr, -1), 1) if dr else 0
                st.move_cursor(step_c, step_r)
                if st.painting:
                    st.paint()
                if step_c:
                    dc -= step_c
                if step_r:
                    dr -= step_r
            return None

        # ── Brush cycling (cancels painting mode) ──
        if event.key == pygame.K_TAB:
            st.painting = False
            mods = getattr(event, 'mod', 0) or pygame.key.get_mods()
            st.cycle_brush(-1 if (mods & pygame.KMOD_SHIFT) else 1)
            return None
        if event.key in (pygame.K_LEFTBRACKET, pygame.K_COMMA):
            st.painting = False
            st.cycle_brush(-1)
            return None
        if event.key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
            st.painting = False
            st.cycle_brush(1)
            return None

        # ── Enter: toggle continuous paint mode ──
        if event.key == pygame.K_RETURN:
            if st.current_brush.is_folder_header:
                st.toggle_folder()
            elif st.painting:
                # Already painting → stop
                st.painting = False
            else:
                # Start painting mode and paint current cell
                st.painting = True
                st.paint()
            return None

        # ── Space: single paint (does not toggle mode) ──
        if event.key == pygame.K_SPACE:
            if st.current_brush.is_folder_header:
                st.toggle_folder()
            else:
                st.paint()
            return None


        # ── Place party start (P key) — overview map ──
        if event.key == pygame.K_p and cfg.supports_party_start:
            cur = st.party_start
            # Toggle: if already at this position, remove it; otherwise place it
            if (cur and cur.get("col") == st.cursor_col
                    and cur.get("row") == st.cursor_row):
                st.party_start = None
            else:
                st.party_start = {"col": st.cursor_col,
                                  "row": st.cursor_row}
            st.dirty = True
            return None



        # ── Edit tile properties (E key) ──
        if event.key == pygame.K_e:
            info = st.get_cursor_tile_info()
            editable = [(i, f) for i, f in enumerate(info["fields"])
                        if f[3]]  # f[3] = editable flag
            if editable:
                first_idx = editable[0][0]
                st.inspector_editing = True
                st.inspector_field_idx = first_idx
                st.inspector_buffer = info["fields"][first_idx][2]
            return None

        # ── Replace tile (R key) — sparse only ──
        if event.key == pygame.K_r and cfg.supports_replace:
            self._open_replace_overlay()
            return None

        # ── Save (Ctrl+S) ──
        if self._is_save(event):
            if cfg.on_save:
                cfg.on_save(st)
            st.dirty = False
            st.save_flash = 1.5  # show "Saved!" for ~1.5 seconds
            return "save"

        return None


    # ── Replace overlay ──

    def _open_replace_overlay(self):
        st = self.state
        td = st.get_tile(st.cursor_col, st.cursor_row)
        st.replacing = True
        if isinstance(td, dict) and td:
            st.replace_src_tile = td.get("tile_id")
            st.replace_src_name = td.get("name",
                                         f"Tile {td.get('tile_id', '?')}")
            st.replace_src_empty = False
        elif isinstance(td, int):
            # Dense storage: tile is an int tile_id
            st.replace_src_tile = td
            # Look up name from brushes
            name = f"Tile {td}"
            for b in st.config.brushes:
                if b.tile_id == td:
                    name = b.name
                    break
            st.replace_src_name = name
            st.replace_src_empty = False
        else:
            st.replace_src_tile = None
            st.replace_src_name = "(Empty)"
            st.replace_src_empty = True
        st.replace_dst_idx = st.brush_idx

    def _handle_replace_overlay(self, event) -> Optional[str]:
        st = self.state
        brushes = st.config.brushes
        n = len(brushes)

        if event.key == pygame.K_ESCAPE:
            st.replacing = False
            return None
        if event.key == pygame.K_UP:
            st.replace_dst_idx = (st.replace_dst_idx - 1) % n
        elif event.key == pygame.K_DOWN:
            st.replace_dst_idx = (st.replace_dst_idx + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            dst_brush = brushes[st.replace_dst_idx]
            st.replace_all_tiles(st.replace_src_tile,
                                 st.replace_src_empty,
                                 dst_brush)
            st.replacing = False
        return None


    # ── Tile inspector editing ─────────────────────────────────

    def _handle_inspector_input(self, event) -> Optional[str]:
        """Handle keyboard input while editing a tile inspector field."""
        st = self.state

        # ── Map picker sub-overlay ──
        if st.map_picker_active:
            return self._handle_map_picker_input(event)

        # ── Item picker sub-overlay ──
        if st.item_picker_active:
            return self._handle_item_picker_input(event)

        info = st.get_cursor_tile_info()
        fields = info["fields"]
        idx = st.inspector_field_idx
        cur_field = fields[idx] if 0 <= idx < len(fields) else None
        field_type = cur_field[3] if cur_field else None

        if event.key == pygame.K_ESCAPE:
            st.inspector_editing = False
            return None

        if event.key in (pygame.K_UP, pygame.K_DOWN):
            # Navigate between editable fields (skip read-only _fields)
            editable = [i for i, f in enumerate(fields)
                        if f[3] and f[3] is not False]
            if not editable:
                return None
            try:
                pos = editable.index(idx)
            except ValueError:
                pos = 0
            if event.key == pygame.K_UP:
                pos = (pos - 1) % len(editable)
            else:
                pos = (pos + 1) % len(editable)
            self._commit_inspector_field(info)
            st.inspector_field_idx = editable[pos]
            new_field = fields[editable[pos]]
            st.inspector_buffer = new_field[2]
            return None

        # ── Toggle fields (Linked checkbox): Enter/Space flips ──
        if field_type == "toggle":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                col, row = info["col"], info["row"]
                key = cur_field[1]
                current = st.get_tile_props(col, row).get(key, False)
                new_val = not current
                if new_val:
                    st.set_tile_prop(col, row, key, True)
                else:
                    st.remove_tile_prop(col, row, key)
                    # Also clear link fields when unlinking
                    if key == "linked":
                        for lk in ("link_map", "link_x", "link_y"):
                            st.remove_tile_prop(col, row, lk)
                # Refresh field display
                new_info = st.get_cursor_tile_info()
                new_fields = new_info["fields"]
                st.inspector_buffer = (new_fields[st.inspector_field_idx][2]
                                       if st.inspector_field_idx < len(new_fields)
                                       else "")
            return None

        # ── Map picker fields: Enter opens the picker overlay ──
        if field_type == "map_picker":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                hierarchy = st.config.map_hierarchy
                if hierarchy:
                    st.map_picker_active = True
                    st.map_picker_cursor = 0
                    st.map_picker_scroll = 0
                    # Try to pre-select current value
                    current_map = cur_field[2]
                    for i, (mid, _, _) in enumerate(hierarchy):
                        if mid == current_map:
                            st.map_picker_cursor = i
                            break
            return None

        # ── Item picker: Enter opens the picker, Backspace clears ──
        if field_type == "item_picker":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                names = st._load_item_names()
                if not names:
                    return None
                st.item_picker_active = True
                st.item_picker_scroll = 0
                # Pre-select current value if one is placed
                cur_name = st.cursor_item_name() or ""
                st.item_picker_cursor = 0
                if cur_name in names:
                    st.item_picker_cursor = names.index(cur_name)
                return None
            if event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                st.clear_item_at_cursor()
                # Refresh the buffer so the field immediately shows "(none)"
                new_info = st.get_cursor_tile_info()
                new_fields = new_info["fields"]
                if st.inspector_field_idx < len(new_fields):
                    st.inspector_buffer = new_fields[st.inspector_field_idx][2]
                return None
            return None

        # ── Text/number fields: type to edit ──
        if event.key == pygame.K_RETURN:
            self._commit_inspector_field(info)
            st.inspector_editing = False
            return None

        if event.key == pygame.K_BACKSPACE:
            st.inspector_buffer = st.inspector_buffer[:-1]
            return None

        c = getattr(event, 'unicode', '')
        if c and c.isprintable():
            st.inspector_buffer += c
        return None

    def _handle_map_picker_input(self, event) -> Optional[str]:
        """Handle input for the map hierarchy picker overlay."""
        st = self.state
        hierarchy = st.config.map_hierarchy
        n = len(hierarchy)
        if not n:
            st.map_picker_active = False
            return None

        if event.key == pygame.K_ESCAPE:
            st.map_picker_active = False
            return None

        if event.key == pygame.K_UP:
            st.map_picker_cursor = (st.map_picker_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            st.map_picker_cursor = (st.map_picker_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Select this map as the link target
            map_id, label, indent = hierarchy[st.map_picker_cursor]
            info = st.get_cursor_tile_info()
            col, row = info["col"], info["row"]
            st.set_tile_prop(col, row, "link_map", map_id)
            st.map_picker_active = False
            # Update buffer to show the selection
            st.inspector_buffer = map_id

        return None

    def _handle_item_picker_input(self, event) -> Optional[str]:
        """Handle input for the visual item picker overlay."""
        st = self.state
        names = st._load_item_names()
        n = len(names)
        if not n:
            st.item_picker_active = False
            return None

        if event.key == pygame.K_ESCAPE:
            st.item_picker_active = False
            return None

        if event.key == pygame.K_UP:
            st.item_picker_cursor = (st.item_picker_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            st.item_picker_cursor = (st.item_picker_cursor + 1) % n
        elif event.key == pygame.K_LEFT:
            # Jump by a column width (6) for grid navigation
            st.item_picker_cursor = max(0, st.item_picker_cursor - 1)
        elif event.key == pygame.K_RIGHT:
            st.item_picker_cursor = min(n - 1, st.item_picker_cursor + 1)
        elif event.key == pygame.K_PAGEUP:
            st.item_picker_cursor = max(0, st.item_picker_cursor - 10)
        elif event.key == pygame.K_PAGEDOWN:
            st.item_picker_cursor = min(n - 1, st.item_picker_cursor + 10)
        elif event.key == pygame.K_HOME:
            st.item_picker_cursor = 0
        elif event.key == pygame.K_END:
            st.item_picker_cursor = n - 1
        elif event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            # Clear the item on the cursor tile and close the picker.
            st.clear_item_at_cursor()
            st.item_picker_active = False
            new_info = st.get_cursor_tile_info()
            new_fields = new_info["fields"]
            if st.inspector_field_idx < len(new_fields):
                st.inspector_buffer = new_fields[st.inspector_field_idx][2]
            return None
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            name = names[st.item_picker_cursor]
            st.place_item_at_cursor(name)
            st.item_picker_active = False
            st.inspector_buffer = name
        return None

    def _commit_inspector_field(self, info):
        """Write the current inspector buffer back to tile_properties."""
        st = self.state
        fields = info["fields"]
        idx = st.inspector_field_idx
        if idx < 0 or idx >= len(fields):
            return
        label, key, old_val, field_type = fields[idx]
        # Skip non-text fields (toggle/map_picker/item_picker handle their own commits)
        if field_type in (False, "toggle", "map_picker", "item_picker"):
            return
        if key.startswith("_"):
            return  # read-only
        new_val = st.inspector_buffer.strip()
        col, row = info["col"], info["row"]
        if new_val:
            st.set_tile_prop(col, row, key, new_val)
        else:
            st.remove_tile_prop(col, row, key)

    # ── Mouse input ──────────────────────────────────────────────

    def handle_mouse(self, event):
        """Process mouse events: click to place cursor, wheel to scroll,
        drag to paint.  Called from the features_editor dispatch."""
        st = self.state

        # Overlays active — ignore mouse
        if st.replacing or st.inspector_editing:
            return

        if event.type == pygame.MOUSEWHEEL:
            # Scroll the camera (vertical: y, horizontal: x if available)
            scroll_speed = 3
            st.scroll_camera(-event.x * scroll_speed if event.x else 0,
                             -event.y * scroll_speed)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = st.pixel_to_grid(*event.pos)
            if pos:
                st.cursor_col, st.cursor_row = pos
                if st.config.grid_type == GRID_SCROLLABLE:
                    st.scroll_to_cursor()
                st._mouse_dragging = True
                # Single-click paints current brush
                st.paint()
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            st._mouse_dragging = False
            return

        if event.type == pygame.MOUSEMOTION:
            if getattr(st, '_mouse_dragging', False):
                pos = st.pixel_to_grid(*event.pos)
                if pos and (pos[0] != st.cursor_col or pos[1] != st.cursor_row):
                    st.cursor_col, st.cursor_row = pos
                    st.paint()
            return

        # Middle-click drag: pan the camera
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            st._middle_drag_start = event.pos
            st._middle_drag_cam = (st.cam_col, st.cam_row)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            st._middle_drag_start = None
            return


def _object_origin(obj: Dict) -> Tuple[int, int]:
    """Return (min_col, min_row) of occupied cells in a sparse object dict."""
    min_c = min_r = 999999
    for pos_key in obj:
        parts = pos_key.split(",")
        if len(parts) == 2:
            c, r = int(parts[0]), int(parts[1])
            if c < min_c:
                min_c = c
            if r < min_r:
                min_r = r
    if min_c == 999999:
        return (0, 0)
    return (min_c, min_r)


# ─── Builder helpers ──────────────────────────────────────────────────

def _make_sprite_resolver(feat_tiles_path: str = "",
                          manifest: Optional[Dict] = None,
                          feat_tile_list: Optional[List] = None):
    """Return a callable ``resolve(tile_id) -> Optional[str]`` for sprite
    asset paths.  Shared by all brush builders."""
    saved_tile_defs: Dict = {}
    if feat_tiles_path:
        try:
            with open(feat_tiles_path, "r") as f:
                saved_tile_defs = json.load(f)
        except (OSError, ValueError):
            pass
    if manifest is None:
        manifest = {}

    def _resolve(tid: int) -> Optional[str]:
        saved = saved_tile_defs.get(str(tid), {})
        sprite_key = saved.get("sprite", "")
        if sprite_key and "/" in sprite_key:
            cat, name = sprite_key.split("/", 1)
            section = manifest.get(cat, {})
            if isinstance(section, dict):
                entry = section.get(name, {})
                if isinstance(entry, dict) and "path" in entry:
                    p = entry["path"]
                    if p.startswith("src/assets/"):
                        p = p[len("src/assets/"):]
                    return p
        if feat_tile_list:
            for tile in feat_tile_list:
                if tile.get("_tile_id") == tid:
                    sk = tile.get("_sprite", "")
                    if sk and "/" in sk:
                        cat, name = sk.split("/", 1)
                        section = manifest.get(cat, {})
                        if isinstance(section, dict):
                            entry = section.get(name, {})
                            if isinstance(entry, dict) and "path" in entry:
                                p = entry["path"]
                                if p.startswith("src/assets/"):
                                    p = p[len("src/assets/"):]
                                return p
                    break
        for cat in manifest:
            if cat.startswith("_"):
                continue
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for _name, entry in section.items():
                if (isinstance(entry, dict)
                        and entry.get("tile_id") == tid
                        and "path" in entry):
                    p = entry["path"]
                    if p.startswith("src/assets/"):
                        p = p[len("src/assets/"):]
                    return p
        return None
    return _resolve


def _build_tile_brushes(tile_ids: List[int], group: str,
                        resolve_path) -> List[Brush]:
    """Build Brush entries for a list of tile IDs, all tagged with *group*."""
    brushes = []
    for tid in tile_ids:
        td = TILE_DEFS.get(tid)
        if not td:
            continue
        brushes.append(Brush(
            name=td.get("name", f"Tile {tid}"),
            tile_id=tid,
            path=resolve_path(tid),
            group=group,
        ))
    return brushes


def build_town_brushes(tile_context_map: Dict[int, str],
                       feat_tiles_path: str = "",
                       manifest: Optional[Dict] = None,
                       feat_tile_list: Optional[List] = None,
                       object_templates: Optional[List] = None,
                       all_templates: Optional[Dict[str, List[Dict]]] = None,
                       ) -> List[Brush]:
    """Build brush list for town map editors.

    Includes Town tiles, Dungeon/Interior tiles (for buildings,
    altars, doors), and optionally template stamp folders.
    """
    resolve = _make_sprite_resolver(feat_tiles_path, manifest, feat_tile_list)

    town_ids = sorted(
        tid for tid, ctx in tile_context_map.items()
        if ctx == "town" and tid in TILE_DEFS
    )
    dungeon_ids = sorted(
        tid for tid, ctx in tile_context_map.items()
        if ctx == "dungeon" and tid in TILE_DEFS
    )
    overworld_ids = sorted(
        tid for tid, ctx in tile_context_map.items()
        if ctx == "overworld" and tid in TILE_DEFS
    )

    brushes: List[Brush] = []
    brushes.append(Brush(name="Eraser", tile_id=None, path=None))

    # ── Town tiles folder ──
    grp_town = "Town"
    brushes.append(Brush(name=grp_town, tile_id=None,
                         is_folder_header=True))
    brushes.extend(_build_tile_brushes(town_ids, grp_town, resolve))

    # ── Dungeon / Interior tiles folder ──
    grp_int = "Interior"
    brushes.append(Brush(name=grp_int, tile_id=None,
                         is_folder_header=True))
    brushes.extend(_build_tile_brushes(dungeon_ids, grp_int, resolve))

    # ── Overworld tiles folder ──
    grp_ow = "Overworld"
    brushes.append(Brush(name=grp_ow, tile_id=None,
                         is_folder_header=True))
    brushes.extend(_build_tile_brushes(overworld_ids, grp_ow, resolve))

    # ── Template stamp folders ──
    if all_templates:
        _append_all_template_brushes(brushes, all_templates)
    elif object_templates:
        _append_object_brushes(brushes, object_templates)

    return brushes


def build_overworld_brushes(tile_context_map: Dict[int, str],
                            object_templates: Optional[List] = None,
                            all_templates: Optional[Dict[str, List[Dict]]] = None,
                            ) -> List[Brush]:
    """Build brush list for the overview map editor.

    Includes folder headers for Tiles and (optionally) template stamp
    folders.
    """
    ow_ids = sorted(
        tid for tid, ctx in tile_context_map.items()
        if ctx == "overworld" and tid in TILE_DEFS
    )
    spawn_ids = sorted(
        tid for tid, ctx in tile_context_map.items()
        if ctx == "spawns" and tid in TILE_DEFS
    )

    brushes: List[Brush] = []

    # ── Eraser (always at top, outside any folder) ──
    brushes.append(Brush(name="Eraser", tile_id=None))

    # ── Tiles folder ──
    grp = "Tiles"
    brushes.append(Brush(name=grp, tile_id=None, is_folder_header=True))
    for tid in ow_ids:
        brushes.append(Brush(
            name=TILE_DEFS[tid]["name"], tile_id=tid, group=grp))

    # ── Spawn tiles folder ──
    if spawn_ids:
        sp_grp = "Spawns"
        brushes.append(Brush(name=sp_grp, tile_id=None,
                             is_folder_header=True))
        for tid in spawn_ids:
            brushes.append(Brush(
                name=TILE_DEFS[tid]["name"], tile_id=tid, group=sp_grp))

    # ── Template stamp folders ──
    if all_templates:
        _append_all_template_brushes(brushes, all_templates)
    elif object_templates:
        _append_object_brushes(brushes, object_templates)

    return brushes



def _append_object_brushes(brushes: List[Brush],
                           object_templates: List[Dict],
                           folder_name: str = "Objects"):
    """Append a folder header followed by one stamp brush per template.

    Each brush carries the sparse tiles dict so ``paint()`` can stamp it.
    Works for any template type (objects, enclosures, battles, etc.).
    """
    grp = folder_name
    brushes.append(Brush(name=grp, tile_id=None, is_folder_header=True))
    for tmpl in object_templates:
        mc = tmpl.get("map_config", {})
        tiles = tmpl.get("tiles")
        if not tiles or not isinstance(tiles, dict):
            continue  # skip empty / non-sparse objects
        brushes.append(Brush(
            name=tmpl.get("label", "Template"),
            tile_id=None,
            group=grp,
            object_data=tiles,
            object_w=mc.get("width", 8),
            object_h=mc.get("height", 8),
        ))


# Display names for each template category key.
_TEMPLATE_FOLDER_NAMES: Dict[str, str] = {
    "me_object":    "Objects",
    "me_enclosure": "Enclosures",
    "me_battle":    "Battles",
    "me_dungeon":   "Dungeons",
    "me_overview":  "Overviews",
    "me_examine":   "Examines",
}

# Order in which template folders appear in the palette.
_TEMPLATE_FOLDER_ORDER: List[str] = [
    "me_object", "me_enclosure", "me_battle",
    "me_dungeon", "me_overview", "me_examine",
]


def _append_all_template_brushes(brushes: List[Brush],
                                 all_templates: Dict[str, List[Dict]]):
    """Append stamp-brush folders for every non-empty template category."""
    for key in _TEMPLATE_FOLDER_ORDER:
        templates = all_templates.get(key)
        if not templates:
            continue
        folder = _TEMPLATE_FOLDER_NAMES.get(key, key)
        _append_object_brushes(brushes, templates, folder_name=folder)
