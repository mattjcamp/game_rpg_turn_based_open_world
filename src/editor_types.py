"""
Shared data types for the game-features editor system.

Contains:
- FieldEntry       – replaces positional [label, key, value, type, editable]
                     lists with named attributes.
- Per-editor state dataclasses – group related editor variables together.
- FeaturesRenderState – single object passed from Game → Renderer, replacing
                        the 60+ keyword arguments on draw_features_screen().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─── Field entry ──────────────────────────────────────────────────────

@dataclass
class FieldEntry:
    """One row in an editor's field list.

    Replaces the ad-hoc ``[label, key, value, type, editable]`` lists.
    All access is now via named attributes instead of positional indices,
    which eliminates off-by-one bugs and makes the code self-documenting.
    """
    label: str
    key: str
    value: str = ""
    field_type: str = "text"      # text | int | choice | sprite | section
    editable: bool = True


# ─── Per-editor render state ──────────────────────────────────────────

@dataclass
class SpellEditorRS:
    """Render-state for the Spells editor."""
    list: Optional[List[dict]] = None
    cursor: int = 0
    scroll: int = 0
    editing: bool = False
    fields: Optional[List[FieldEntry]] = None
    field: int = 0
    buffer: str = ""
    field_scroll: int = 0
    nav: int = 0
    ctype_cursor: int = 0
    level_cursor: int = 0
    level_scroll: int = 0
    sel_ctype: Optional[str] = None
    sel_level: Optional[int] = None
    filtered: Optional[list] = None


@dataclass
class ItemEditorRS:
    """Render-state for the Items editor."""
    list: Optional[List[dict]] = None
    cursor: int = 0
    scroll: int = 0
    editing: bool = False
    fields: Optional[List[FieldEntry]] = None
    field: int = 0
    buffer: str = ""
    field_scroll: int = 0


@dataclass
class MonsterEditorRS:
    """Render-state for the Monsters editor."""
    list: Optional[List[dict]] = None
    cursor: int = 0
    scroll: int = 0
    editing: bool = False
    fields: Optional[List[FieldEntry]] = None
    field: int = 0
    buffer: str = ""
    field_scroll: int = 0


@dataclass
class TileEditorRS:
    """Render-state for the Tile Types editor."""
    list: Optional[list] = None
    folders: Optional[list] = None
    folder_cursor: int = 0
    folder_scroll: int = 0
    folder_tiles: Optional[list] = None
    cursor: int = 0
    scroll: int = 0
    editing: bool = False
    fields: Optional[List[FieldEntry]] = None
    field: int = 0
    buffer: str = ""
    field_scroll: int = 0


@dataclass
class GalleryEditorRS:
    """Render-state for the Tile Gallery editor."""
    list: Optional[list] = None
    cat_list: Optional[list] = None
    cat_cursor: int = 0
    cat_scroll: int = 0
    sprites: Optional[list] = None
    spr_cursor: int = 0
    spr_scroll: int = 0
    tag_cursor: int = 0
    all_cats: Optional[list] = None
    naming: bool = False
    name_buf: str = ""
    detail_cursor: int = 0


@dataclass
class PixelEditorRS:
    """Render-state for the Pixel Editor."""
    pixels: Optional[list] = None
    cx: int = 0
    cy: int = 0
    w: int = 32
    h: int = 32
    color_idx: int = 0
    palette: Optional[list] = None
    focus: str = "canvas"
    replacing: bool = False
    replace_src_color: tuple = (0, 0, 0, 255)
    replace_dst: int = 0
    replace_sel: str = "src"


@dataclass
class MapEditorHubRS:
    """Render-state for the Map Editor Hub."""
    editor_active: bool = False
    editor_data: Optional[dict] = None
    sections: Optional[list] = None
    cursor: int = 0
    scroll: int = 0
    nav_depth: int = 0
    folder_label: str = ""
    level: int = 0
    fields: Optional[List[FieldEntry]] = None
    field_cursor: int = 0
    field_buffer: str = ""
    field_scroll: int = 0
    naming: bool = False
    name_buf: str = ""
    naming_is_new: bool = False
    save_flash: float = 0.0


# ─── Top-level render state ──────────────────────────────────────────

@dataclass
class FeaturesRenderState:
    """Everything the renderer needs to draw the features editor.

    Replaces 60+ keyword arguments on ``draw_features_screen()``.
    New editors add a new sub-dataclass field here — the renderer
    signature never needs to grow.
    """
    categories: list = field(default_factory=list)
    cat_cursor: int = 0
    level: int = 0
    active_editor: Optional[str] = None

    spells: SpellEditorRS = field(default_factory=SpellEditorRS)
    items: ItemEditorRS = field(default_factory=ItemEditorRS)
    monsters: MonsterEditorRS = field(default_factory=MonsterEditorRS)
    tiles: TileEditorRS = field(default_factory=TileEditorRS)
    gallery: GalleryEditorRS = field(default_factory=GalleryEditorRS)
    pxedit: PixelEditorRS = field(default_factory=PixelEditorRS)
    meh: MapEditorHubRS = field(default_factory=MapEditorHubRS)
    overview_editor_data: Optional[dict] = None
