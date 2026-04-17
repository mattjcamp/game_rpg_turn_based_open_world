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
class EncounterEditorRS:
    """Render-state for the top-level Encounters editor.

    Encounters are reusable templates (group of monsters + custom
    XP/loot settings) stored in ``data/encounters.json``. Per-module
    overrides may live at ``<module>/encounters.json``. The editor
    displays a flat list — each entry carries a ``_category`` field
    ("dungeon"/"overworld"/"house_basement"/etc.) that controls which
    sub-bucket it serialises back into.
    """
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
    # Spawn sub-list (level 4)
    spawn_sublist: Optional[List[str]] = None
    spawn_sublist_mode: Optional[str] = None  # "monsters" or "loot"
    spawn_sublist_cursor: int = 0
    spawn_sublist_scroll: int = 0


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
    painting: bool = False
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


@dataclass
class TownEditorRS:
    """Render-state for the Town Editor.

    Supports three sub-screens per town:
    - Settings   (edit name, size, style, entry point)
    - Townspeople (manage NPC list)
    - Edit Map    (launch tile editor for the town layout)
    """
    # Town list (level 1)
    towns: Optional[List[dict]] = None
    cursor: int = 0
    scroll: int = 0
    # Sub-screen navigation (level 2): 0=Settings, 1=Townspeople, 2=Edit Map
    sub_cursor: int = 0
    sub_items: Optional[list] = field(default_factory=lambda: [
        "Settings", "Townspeople", "Edit Map",
    ])
    # Settings fields (level 3 - settings)
    fields: Optional[List[FieldEntry]] = None
    field_cursor: int = 0
    field_buffer: str = ""
    field_scroll: int = 0
    # Townspeople list (level 3 - townspeople)
    npc_list: Optional[List[dict]] = None
    npc_cursor: int = 0
    npc_scroll: int = 0
    # NPC field editor (level 4 - editing an NPC)
    npc_fields: Optional[List[FieldEntry]] = None
    npc_field_cursor: int = 0
    npc_field_buffer: str = ""
    npc_field_scroll: int = 0
    # Map editor active flag
    editor_active: bool = False
    editor_data: Optional[dict] = None
    # Naming overlay
    naming: bool = False
    name_buf: str = ""
    naming_is_new: bool = False
    # Save flash
    save_flash: float = 0.0


@dataclass
class DungeonEditorRS:
    """Render-state for the Dungeon Editor.

    Hierarchy:
    - Dungeon list          (level 0 / edit_level 8)
    - Dungeon sub-screen    (level 1 / edit_level 9)  Settings | Levels
    - Settings fields OR    (level 2 / edit_level 10) Level list
    - Level sub-screen      (level 3 / edit_level 11) Edit Map | Encounters
    - Encounter list        (level 4 / edit_level 12)
    - Encounter field editor(level 5 / edit_level 13)
    """
    # Dungeon list (level 0)
    dungeons: Optional[List[dict]] = None
    cursor: int = 0
    scroll: int = 0
    # Dungeon sub-screen (level 1): 0=Settings, 1=Levels
    sub_cursor: int = 0
    sub_items: Optional[list] = field(default_factory=lambda: [
        "Settings", "Levels",
    ])
    # Settings fields (level 2 / sub 0)
    fields: Optional[List[FieldEntry]] = None
    field_cursor: int = 0
    field_buffer: str = ""
    field_scroll: int = 0
    # Level list (level 2 / sub 1)
    level_list: Optional[List[dict]] = None
    level_cursor: int = 0
    level_scroll: int = 0
    # Level sub-screen (level 3): 0=Edit Map, 1=Encounters
    level_sub_cursor: int = 0
    level_sub_items: Optional[list] = field(default_factory=lambda: [
        "Edit Map", "Encounters",
    ])
    # Encounters list (level 4)
    encounter_list: Optional[List[dict]] = None
    encounter_cursor: int = 0
    encounter_scroll: int = 0
    # Encounter field editor (level 5)
    encounter_fields: Optional[List[FieldEntry]] = None
    encounter_field_cursor: int = 0
    encounter_field_buffer: str = ""
    encounter_field_scroll: int = 0
    # Map editor active flag
    editor_active: bool = False
    editor_data: Optional[dict] = None
    # Naming overlays
    naming: bool = False
    name_buf: str = ""
    naming_is_new: bool = False
    naming_target: str = ""  # "dungeon" or "level"
    # Save flash
    save_flash: float = 0.0


@dataclass
class BuildingEditorRS:
    """Render-state for the Building Editor.

    Hierarchy:
    - Building list          (level 0 / edit_level 14)
    - Building sub-screen    (level 1 / edit_level 15)  Settings | Spaces
    - Settings fields OR     (level 2 / edit_level 16) Space list
    - Space sub-screen       (level 3 / edit_level 17) Edit Map | Encounters
    - Encounter list         (level 4 / edit_level 18)
    - Encounter field editor (level 5 / edit_level 19)
    """
    # Building list (level 0)
    buildings: Optional[List[dict]] = None
    cursor: int = 0
    scroll: int = 0
    # Building sub-screen (level 1): 0=Settings, 1=Spaces
    sub_cursor: int = 0
    sub_items: Optional[list] = field(default_factory=lambda: [
        "Settings", "Spaces",
    ])
    # Settings fields (level 2 / sub 0)
    fields: Optional[List[FieldEntry]] = None
    field_cursor: int = 0
    field_buffer: str = ""
    field_scroll: int = 0
    # Space list (level 2 / sub 1)
    space_list: Optional[List[dict]] = None
    space_cursor: int = 0
    space_scroll: int = 0
    # Space sub-screen (level 3): 0=Edit Map, 1=Encounters
    space_sub_cursor: int = 0
    space_sub_items: Optional[list] = field(default_factory=lambda: [
        "Edit Map", "Encounters",
    ])
    # Encounters list (level 4)
    encounter_list: Optional[List[dict]] = None
    encounter_cursor: int = 0
    encounter_scroll: int = 0
    # Encounter field editor (level 5)
    encounter_fields: Optional[List[FieldEntry]] = None
    encounter_field_cursor: int = 0
    encounter_field_buffer: str = ""
    encounter_field_scroll: int = 0
    # Map editor active flag
    editor_active: bool = False
    editor_data: Optional[dict] = None
    # Naming overlays
    naming: bool = False
    name_buf: str = ""
    naming_is_new: bool = False
    naming_target: str = ""  # "building" or "space"
    # Save flash
    save_flash: float = 0.0


@dataclass
class CounterEditorRS:
    """Render-state for the Counters editor.

    Two-level hierarchy:
    - Counter type list     (level 1)
    - Counter item list     (level 2) – items sold at this counter
    - Item field editor     (level 3) – add/remove items from the list
    """
    list: Optional[List[dict]] = None       # list of counter-type dicts
    cursor: int = 0
    scroll: int = 0
    editing: bool = False
    fields: Optional[List[FieldEntry]] = None
    field: int = 0
    buffer: str = ""
    field_scroll: int = 0
    # Item sub-list for the selected counter
    item_list: Optional[List[str]] = None
    item_cursor: int = 0
    item_scroll: int = 0
    # Cache of item info for rendering (name → {section, icon, buy})
    items_cache: Optional[Dict[str, dict]] = None


@dataclass
class QuestEditorRS:
    """Render-state for the Quest Editor.

    Hierarchy:
    - Quest list           (level 0 / edit_level 20)
    - Quest sub-screen     (level 1 / edit_level 21)  Settings | Steps
    - Settings fields OR   (level 2 / edit_level 22)  Step list
    - Step field editor    (level 3 / edit_level 23)
    """
    # Quest list (level 0)
    quests: Optional[List[dict]] = None
    cursor: int = 0
    scroll: int = 0
    # Quest sub-screen (level 1): 0=Settings, 1=Steps
    sub_cursor: int = 0
    sub_items: Optional[list] = field(default_factory=lambda: [
        "Settings", "Quest Steps",
    ])
    # Settings fields (level 2 / sub 0)
    fields: Optional[List[FieldEntry]] = None
    field_cursor: int = 0
    field_buffer: str = ""
    field_scroll: int = 0
    # Step list (level 2 / sub 1)
    step_list: Optional[List[dict]] = None
    step_cursor: int = 0
    step_scroll: int = 0
    # Step field editor (level 3)
    step_fields: Optional[List[FieldEntry]] = None
    step_field_cursor: int = 0
    step_field_buffer: str = ""
    step_field_scroll: int = 0
    # Naming overlays
    naming: bool = False
    name_buf: str = ""
    naming_is_new: bool = False
    naming_target: str = ""  # "quest" or "step"
    # Save flash
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
    towns: TownEditorRS = field(default_factory=TownEditorRS)
    dungeons: DungeonEditorRS = field(default_factory=DungeonEditorRS)
    buildings: BuildingEditorRS = field(default_factory=BuildingEditorRS)
    overview_editor_data: Optional[dict] = None
    town_map_editor_data: Optional[dict] = None
    dungeon_map_editor_data: Optional[dict] = None
    building_map_editor_data: Optional[dict] = None
    counters: CounterEditorRS = field(default_factory=CounterEditorRS)
    encounters: EncounterEditorRS = field(default_factory=EncounterEditorRS)
    quests: 'QuestEditorRS' = field(default_factory=lambda: QuestEditorRS())
