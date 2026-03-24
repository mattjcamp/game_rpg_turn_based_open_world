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
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    """A single entry in the editor palette."""
    name: str
    tile_id: Optional[int]    # None for eraser
    path: Optional[str] = None  # sprite asset path (interior brushes)

    @property
    def is_eraser(self) -> bool:
        return self.tile_id is None


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

    # -- Link support --
    supports_tile_links: bool = False    # I key: interior link picker (overview map)
    supports_interior_links: bool = False  # I key: interior/overworld link (interior)
    supports_replace: bool = False       # R key: replace all of tile type

    # -- Eraser behaviour --
    eraser_tile_id: int = TILE_GRASS  # dense: what eraser paints
    # sparse: eraser deletes the key

    # -- Tile size override (None = TILE_SIZE constant) --
    tile_size: Optional[int] = None

    # -- Save callback (called with the editor state) --
    on_save: Optional[Callable] = None

    # -- Exit callback --
    on_exit: Optional[Callable] = None


# ─── State ────────────────────────────────────────────────────────────

class MapEditorState:
    """Live editing state for one editor instance.

    Wraps cursor, camera, brush selection, tile data, and dirty flag.
    The same public API works regardless of dense vs sparse storage.
    """

    def __init__(self, config: MapEditorConfig,
                 tiles: Any = None,
                 tile_links: Optional[Dict] = None,
                 interior_list: Optional[List] = None):
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

        # Tile links (overview map: "col,row" -> {"interior": name})
        self.tile_links: Dict = tile_links if tile_links is not None else {}

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

        # Overlay states
        self.int_picking: bool = False       # overview map interior picker
        self.int_pick_cursor: int = 0
        self.int_pick_scroll: int = 0

        self.int_link_picking: bool = False  # interior link picker
        self.int_link_pick_list: List = []
        self.int_link_pick_cursor: int = 0

        self.replacing: bool = False         # replace tile overlay
        self.replace_src_tile: Optional[int] = None
        self.replace_src_name: str = ""
        self.replace_src_empty: bool = False
        self.replace_dst_idx: int = 0

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

    @property
    def current_brush(self) -> Brush:
        brushes = self.config.brushes
        if not brushes:
            return Brush(name="(none)", tile_id=None)
        return brushes[self.brush_idx % len(brushes)]

    def cycle_brush(self, delta: int = 1):
        n = len(self.config.brushes)
        if n == 0:
            return
        self.brush_idx = (self.brush_idx + delta) % n

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
        """Apply the current brush at the cursor position."""
        brush = self.current_brush
        col, row = self.cursor_col, self.cursor_row

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
                # Preserve existing link fields
                old = self.tiles.get(f"{col},{row}", {})
                if isinstance(old, dict):
                    for lk in ("interior", "to_overworld"):
                        if lk in old:
                            td[lk] = old[lk]
                self.set_tile(col, row, td)

    # -- Link helpers (overview map) --

    def get_tile_link(self, col: int, row: int) -> Optional[Dict]:
        return self.tile_links.get(f"{col},{row}")

    def set_tile_link(self, col: int, row: int, link: Optional[Dict]):
        pos_key = f"{col},{row}"
        if link is None:
            if pos_key in self.tile_links:
                del self.tile_links[pos_key]
                self.dirty = True
        else:
            self.tile_links[pos_key] = link
            self.dirty = True

    # -- Interior tile link helpers (sparse interiors) --

    def set_interior_link(self, col: int, row: int,
                          link_type: Optional[str],
                          link_value: Any = None):
        """Set/clear an interior or to_overworld link on a sparse tile."""
        pos_key = f"{col},{row}"
        td = self.tiles.get(pos_key)
        if td is None or not isinstance(td, dict):
            return  # need a tile to attach link to

        # Clear existing link types
        for lk in ("interior", "to_overworld"):
            td.pop(lk, None)

        if link_type == "to_overworld":
            td["to_overworld"] = True
            self.dirty = True
        elif link_type == "interior" and link_value:
            td["interior"] = link_value
            self.dirty = True
        else:
            self.dirty = True  # cleared links

    def remove_interior_link(self, col: int, row: int):
        """Remove any interior/to_overworld link from tile at (col, row)."""
        pos_key = f"{col},{row}"
        td = self.tiles.get(pos_key)
        if td is None or not isinstance(td, dict):
            return
        changed = False
        for lk in ("interior", "to_overworld"):
            if lk in td:
                del td[lk]
                changed = True
        if changed:
            self.dirty = True

    # -- Replace all (sparse interiors) --

    def replace_all_tiles(self, src_tile_id: Optional[int],
                          src_empty: bool,
                          dst_brush: Brush):
        """Replace all tiles matching source with destination brush."""
        if self.config.storage != STORAGE_SPARSE:
            return
        tiles = self.tiles
        w, h = self.config.width, self.config.height

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
            "dirty": self.dirty,
            "tile_links": self.tile_links,
            "tile_context": cfg.tile_context,
            # Overlay states
            "int_picking": self.int_picking,
            "int_pick_cursor": self.int_pick_cursor,
            "int_pick_list": self.interior_list,
            "int_link_picking": self.int_link_picking,
            "int_link_pick_list": self.int_link_pick_list,
            "int_link_pick_cursor": self.int_link_pick_cursor,
            "replacing": self.replacing,
            "replace_src_tile": self.replace_src_tile,
            "replace_src_name": self.replace_src_name,
            "replace_src_empty": self.replace_src_empty,
            "replace_dst_idx": self.replace_dst_idx,
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
        if st.int_picking:
            return self._handle_int_picker(event)
        if st.int_link_picking:
            return self._handle_int_link_picker(event)
        if st.replacing:
            return self._handle_replace_overlay(event)

        # ── Escape ──
        if event.key == pygame.K_ESCAPE:
            if st.dirty and cfg.on_save:
                cfg.on_save(st)
            if cfg.on_exit:
                cfg.on_exit(st)
            return "exit"

        # ── Cursor movement ──
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
            st.move_cursor(dc, dr)
            return None

        # ── Brush cycling ──
        if event.key == pygame.K_TAB:
            mods = getattr(event, 'mod', 0) or pygame.key.get_mods()
            st.cycle_brush(-1 if (mods & pygame.KMOD_SHIFT) else 1)
            return None
        if event.key in (pygame.K_LEFTBRACKET, pygame.K_COMMA):
            st.cycle_brush(-1)
            return None
        if event.key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
            st.cycle_brush(1)
            return None

        # ── Paint ──
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            st.paint()
            return None

        # ── Link interior (I key) — overview map ──
        if event.key == pygame.K_i and cfg.supports_tile_links:
            st.int_picking = True
            st.int_pick_cursor = 0
            st.int_pick_scroll = 0
            return None

        # ── Link interior (I key) — interior editor ──
        if event.key == pygame.K_i and cfg.supports_interior_links:
            self._open_interior_link_picker()
            return None

        # ── Remove link (X key) ──
        if event.key == pygame.K_x:
            if cfg.supports_tile_links:
                st.set_tile_link(st.cursor_col, st.cursor_row, None)
            elif cfg.supports_interior_links:
                st.remove_interior_link(st.cursor_col, st.cursor_row)
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
            return "save"

        return None

    # ── Interior picker (overview map: pick which interior to link) ──

    def _handle_int_picker(self, event) -> Optional[str]:
        st = self.state
        interiors = st.interior_list
        n_options = 1 + len(interiors)

        if event.key == pygame.K_ESCAPE:
            st.int_picking = False
            return None
        if event.key == pygame.K_UP:
            st.int_pick_cursor = max(0, st.int_pick_cursor - 1)
        elif event.key == pygame.K_DOWN:
            st.int_pick_cursor = min(n_options - 1, st.int_pick_cursor + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            col, row = st.cursor_col, st.cursor_row
            if st.int_pick_cursor == 0:
                # "(none)" — remove link
                st.set_tile_link(col, row, None)
            else:
                idx = st.int_pick_cursor - 1
                if idx < len(interiors):
                    st.set_tile_link(col, row, {
                        "interior": interiors[idx].get("name",
                                                       f"Interior {idx}"),
                    })
            st.int_picking = False
        return None

    # ── Interior link picker (inside interior: link to sibling/overworld) ──

    def _open_interior_link_picker(self):
        st = self.state
        # Build pick list: sibling interiors (exclude current)
        current_name = st.config.title  # interior name stored in title
        st.int_link_pick_list = [
            intr for intr in st.interior_list
            if intr.get("name", "") != current_name
        ]
        st.int_link_picking = True
        # Pre-select based on current tile's link
        td = st.get_tile(st.cursor_col, st.cursor_row)
        if isinstance(td, dict):
            if td.get("to_overworld"):
                st.int_link_pick_cursor = 1
            elif td.get("interior"):
                iname = td["interior"]
                for pi, intr in enumerate(st.int_link_pick_list):
                    if intr.get("name") == iname:
                        st.int_link_pick_cursor = pi + 2
                        return
                st.int_link_pick_cursor = 0
            else:
                st.int_link_pick_cursor = 0
        else:
            st.int_link_pick_cursor = 0

    def _handle_int_link_picker(self, event) -> Optional[str]:
        st = self.state
        pick_list = st.int_link_pick_list
        n_options = 2 + len(pick_list)

        if event.key == pygame.K_ESCAPE:
            st.int_link_picking = False
            return None
        if event.key == pygame.K_UP:
            st.int_link_pick_cursor = max(0, st.int_link_pick_cursor - 1)
        elif event.key == pygame.K_DOWN:
            st.int_link_pick_cursor = min(n_options - 1,
                                          st.int_link_pick_cursor + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            idx = st.int_link_pick_cursor
            col, row = st.cursor_col, st.cursor_row
            if idx == 0:
                st.set_interior_link(col, row, None)
            elif idx == 1:
                st.set_interior_link(col, row, "to_overworld")
            else:
                pi = idx - 2
                if pi < len(pick_list):
                    st.set_interior_link(col, row, "interior",
                                         pick_list[pi]["name"])
            st.int_link_picking = False
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


# ─── Builder helpers ──────────────────────────────────────────────────

def build_overworld_brushes(tile_context_map: Dict[int, str]) -> List[Brush]:
    """Build brush list for the overview map editor.

    Filters TILE_DEFS by tile_context == "overworld", appends eraser.
    """
    ow_ids = sorted(
        tid for tid, ctx in tile_context_map.items()
        if ctx == "overworld" and tid in TILE_DEFS
    )
    brushes = [Brush(name=TILE_DEFS[tid]["name"], tile_id=tid)
               for tid in ow_ids]
    brushes.append(Brush(name="Eraser", tile_id=None))
    return brushes


def build_interior_brushes(tile_context_map: Dict[int, str],
                           feat_tiles_path: str = "",
                           manifest: Optional[Dict] = None,
                           feat_tile_list: Optional[List] = None,
                           ) -> List[Brush]:
    """Build brush list for overview interior editors.

    Filters by tile_context == "dungeon", resolves sprite paths.
    """
    brushes = [Brush(name="Eraser", tile_id=None, path=None)]

    dungeon_ids = sorted(
        tid for tid, ctx in tile_context_map.items()
        if ctx == "dungeon"
    )

    # Load saved tile defs for sprite key resolution
    saved_tile_defs: Dict = {}
    if feat_tiles_path:
        try:
            with open(feat_tiles_path, "r") as f:
                saved_tile_defs = json.load(f)
        except (OSError, ValueError):
            pass

    if manifest is None:
        manifest = {}

    def _resolve_sprite_path(tid: int) -> Optional[str]:
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
        # Check feature tile list
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
        # Manifest fallback
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

    for tid in dungeon_ids:
        td = TILE_DEFS.get(tid)
        if not td:
            continue
        brushes.append(Brush(
            name=td.get("name", f"Tile {tid}"),
            tile_id=tid,
            path=_resolve_sprite_path(tid),
        ))

    return brushes
