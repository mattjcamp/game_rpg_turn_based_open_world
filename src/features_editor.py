"""
FeaturesEditor class extracted from game.py.

Handles all game features editing: spells, items, monsters, tiles, gallery, pixel editor, and map editor hub.
"""

import json
import os
import pygame
from collections import Counter
from src.editor_types import (
    FieldEntry, FeaturesRenderState, SpellEditorRS, ItemEditorRS,
    MonsterEditorRS, TileEditorRS, GalleryEditorRS, PixelEditorRS,
    MapEditorHubRS, TownEditorRS, CounterEditorRS,
)


class FeaturesEditor:
    """Manages the Game Features editor system.

    Handles state and input for editing:
    - Spells (3-tier folder navigation)
    - Items (weapons, armors, general)
    - Monsters (with stats)
    - Tile Types (folder hierarchy)
    - Tile Gallery (sprite browser + pixel editor)
    - Map Editor Hub (templates and launch)
    """

    def __init__(self, game):
        """Initialize the FeaturesEditor with reference to the Game instance.

        Parameters
        ----------
        game : Game
            The Game instance, used for accessing renderer, active_module_path, etc.
        """
        self.game = game

        # --- Map Editor Hub state ---
        self.meh_editor_active = False      # True when map editor launched from hub
        self.meh_sections = []              # section list
        self.meh_cursor = 0                 # section cursor
        self.meh_scroll = 0                 # scroll offset
        self.meh_nav_stack = []             # folder navigation stack
        self.meh_folder_label = ""          # current folder label
        self.meh_level = 0                  # 0=sections, 1=fields
        self.meh_fields = []                # field list when editing
        self.meh_field = 0                  # field cursor
        self.meh_buffer = ""                # field edit buffer
        self.meh_field_scroll = 0           # field scroll offset
        self.meh_naming = False             # True when typing a template name
        self.meh_name_buf = ""              # text buffer for naming/renaming
        self.meh_naming_is_new = False      # True if naming a new template, False if renaming
        self.meh_save_flash = 0.0           # countdown for "Saved!" flash in hub
        self._meh_settings_target = None    # template dict being edited in settings

        # Default map_config per folder type (used when adding new templates).
        # Values are plain dicts; the actual STORAGE_*/GRID_* constants are
        # resolved in _meh_folder_default_config() at runtime.
        self._MEH_FOLDER_DEFAULTS = {
            "me_enclosure": {"storage": "sparse", "grid": "fixed",
                             "ctx": "town",      "w": 16, "h": 14},
        }

        # --- Spell editor state ---
        self.spell_list = []                # list of spell dicts
        self.spell_cursor = 0               # which spell is highlighted
        self.spell_scroll = 0
        self.spell_editing = False          # True when editing spell fields
        self.spell_field = 0                # active field index
        self.spell_fields = []              # [FieldEntry, ...]
        self.spell_buffer = ""              # text being typed
        self.spell_scroll_f = 0             # field list scroll
        # Spell folder navigation (3-tier: casting_type → level → spells)
        self.spell_nav = 0                  # 0=casting types, 1=levels, 2=spells
        self.spell_ctype_cursor = 0         # cursor within casting type list
        self.spell_level_cursor = 0         # cursor within level list
        self.spell_level_scroll = 0
        self.spell_sel_ctype = None         # selected casting type string
        self.spell_sel_level = None         # selected level number
        self.spell_filtered = []            # indices into spell_list
        self.spell_filter_pos = 0           # cursor position within filtered
        self.level = 0                      # 0=categories, 1=list, 2=field editor
        # Which editor is active: "spells", "items", "monsters", "tiles"
        self.active_editor = None
        self.launched_from_maps = False     # True when tiles/gallery opened via Maps

        # --- Items editor state ---
        self.item_list = []                 # list of (name, section, data) tuples
        self.item_cursor = 0
        self.item_scroll = 0
        self.item_editing = False
        self.item_field = 0
        self.item_fields = []
        self.item_buffer = ""
        self.item_scroll_f = 0

        # --- Counters editor state ---
        self.counter_list = []              # list of counter-type dicts
        self.counter_cursor = 0
        self.counter_scroll = 0
        self.counter_editing = False
        self.counter_field = 0
        self.counter_fields = []
        self.counter_buffer = ""
        self.counter_scroll_f = 0
        self.counter_item_list = []         # item names in selected counter
        self.counter_item_cursor = 0
        self.counter_item_scroll = 0

        # --- Monsters editor state ---
        self.mon_list = []                  # list of (name, data) tuples
        self.mon_cursor = 0
        self.mon_scroll = 0
        self.mon_editing = False
        self.mon_field = 0
        self.mon_fields = []
        self.mon_buffer = ""
        self.mon_scroll_f = 0

        # --- Tile Types editor state ---
        self.tile_list = []                 # all tiles (flat)
        self.tile_folders = []              # folder dicts: name, label, count
        self.tile_folder_cursor = 0
        self.tile_folder_scroll = 0
        self.tile_folder_tiles = []         # tiles in current folder
        self.tile_cursor = 0
        self.tile_scroll = 0
        self.tile_editing = False
        self.tile_field = 0
        self.tile_fields = []
        self.tile_buffer = ""
        self.tile_scroll_f = 0
        self.tile_in_folder = False         # True when browsing inside a folder

        # Spawn point data — extended config for tiles with context "spawns"
        # Keyed by tile_id (int) → spawn config dict
        self.spawn_data = {}

        # Spawn sub-list editor state (level 4 within tile editing)
        self.spawn_sublist_mode = None      # "monsters" or "loot" or None
        self.spawn_sublist = []             # current list being edited
        self.spawn_sublist_cursor = 0
        self.spawn_sublist_scroll = 0
        self._spawn_all_monsters = None     # cached monster name list
        self._spawn_all_items = None        # cached item name list

        # Classification of tile IDs into context folders
        self.TILE_CONTEXT = {
            0: "overworld", 1: "overworld", 2: "overworld",
            3: "overworld", 4: "overworld", 5: "overworld",
            6: "overworld", 7: "overworld", 8: "overworld",
            9: "overworld",
            10: "town", 11: "town", 12: "town", 13: "town",
            14: "town", 35: "town", 36: "town",
            30: "town", 31: "town",
            20: "dungeon", 21: "dungeon", 22: "dungeon",
            23: "dungeon", 24: "dungeon", 25: "dungeon",
            26: "dungeon", 27: "dungeon", 28: "dungeon",
            29: "dungeon",
            32: "dungeon", 33: "dungeon", 34: "dungeon",
            66: "spawns",
        }
        self.TILE_FOLDER_ORDER = [
            {"name": "overworld", "label": "Overworld"},
            {"name": "town", "label": "Town"},
            {"name": "dungeon", "label": "Dungeon"},
            {"name": "spawns", "label": "Spawns"},
            {"name": "artifacts", "label": "Artifacts"},
            {"name": "battle", "label": "Battle Screen"},
            {"name": "examine", "label": "Examine Screen"},
        ]

        # Restore user-created / edited tile defs from disk so the
        # rest of the game (town rendering etc.) sees them at startup.
        self.restore_tile_defs_from_disk()

        # --- Tile Gallery state ---
        self.gallery_list = []              # unique sprite entries (for saving)
        self.gallery_cat_list = []          # categories with counts
        self.gallery_cat_cursor = 0         # which category folder
        self.gallery_cat_scroll = 0
        self.gallery_sprites = []           # sprites for current category
        self.gallery_spr_cursor = 0         # which sprite in category
        self.gallery_spr_scroll = 0
        self.gallery_tag_cursor = 0         # which tag row in editor
        self.gallery_all_cats = [
            "overworld", "town", "dungeon", "people",
            "monsters", "objects", "unique_tiles",
            "items", "spells", "unassigned",
        ]
        self.gallery_naming = False         # True when typing a new name
        self.gallery_name_buf = ""          # text buffer for renaming
        self.gallery_detail_cursor = 0      # 0=Name, 1=Categories, 2=Edit Pixels

        # --- Pixel editor state ---
        self.pxedit_pixels = None           # 2D list of (r,g,b,a) tuples
        self.pxedit_cx = 0                  # cursor x on canvas
        self.pxedit_cy = 0                  # cursor y on canvas
        self.pxedit_color_idx = 0           # selected palette index
        self.pxedit_focus = "canvas"        # "canvas" or "palette"
        self.pxedit_w = 32                  # canvas width
        self.pxedit_h = 32                  # canvas height
        self.pxedit_path = ""               # file path for saving
        self.pxedit_undo_stack = []         # list of pixel snapshots for undo
        # Color replace mode
        self.pxedit_painting = False         # True when continuous paint active
        self.pxedit_replacing = False       # True when in replace mode
        self.pxedit_replace_src_color = (0, 0, 0, 255)  # actual RGBA from canvas
        self.pxedit_replace_dst = 0         # target palette index ("to")
        self.pxedit_replace_sel = "dst"     # which selector is active ("src" or "dst")

        self.pxedit_palette = [
            (0, 0, 0, 255),        # Black
            (255, 255, 255, 255),  # White
            (200, 50, 50, 255),    # Red
            (50, 160, 50, 255),    # Green
            (50, 80, 200, 255),    # Blue
            (255, 200, 60, 255),   # Gold
            (255, 140, 40, 255),   # Orange
            (160, 80, 200, 255),   # Purple
            (100, 200, 200, 255),  # Cyan
            (180, 130, 60, 255),   # Brown
            (140, 100, 40, 255),   # Dark Brown
            (180, 190, 200, 255),  # Steel
            (120, 130, 140, 255),  # Dark Steel
            (60, 55, 65, 255),     # Dark Gray
            (130, 130, 130, 255),  # Gray
            (200, 200, 200, 255),  # Light Gray
            (34, 139, 34, 255),    # Forest Green
            (30, 90, 180, 255),    # Ocean Blue
            (210, 190, 130, 255),  # Sand
            (80, 0, 0, 255),       # Dark Red
            (0, 80, 0, 255),       # Dark Green
            (255, 220, 180, 255),  # Skin
            (220, 180, 140, 255),  # Parchment
            (0, 0, 0, 0),          # Transparent
        ]

        # --- Dirty flag and categories ---
        self.dirty = False                  # True when editor has unsaved changes
        self.cursor = 0                     # top-level category cursor
        self.categories = [
            {"label": "Modules", "icon": "M"},
            {"label": "Spells", "icon": "S"},
            {"label": "Items", "icon": "I"},
            {"label": "Counters", "icon": "C"},
            {"label": "Monsters", "icon": "X"},
            {"label": "Maps", "icon": "E"},
        ]

        # Town layout data
        self.town_lists = {
            "layouts": [], "features": [], "interiors": [],
        }

        # --- Town editor state ---
        self.town_cursor = 0                # which town layout is highlighted
        self.town_scroll = 0                # scroll offset in town list
        self.town_sub_cursor = 0            # 0=Settings, 1=Townspeople, 2=Edit Map
        self.town_sub_items = ["Settings", "Townspeople", "Edit Map"]
        # Settings fields
        self.town_fields = []               # list of field entries for settings
        self.town_field = 0                 # field cursor
        self.town_buffer = ""               # field edit buffer
        self.town_field_scroll = 0          # field scroll offset
        # Townspeople (NPC list)
        self.town_npc_list = []             # list of NPC dicts for current town
        self.town_npc_cursor = 0            # NPC cursor
        self.town_npc_scroll = 0            # NPC list scroll
        # NPC field editor
        self.town_npc_fields = []           # field entries for selected NPC
        self.town_npc_field = 0             # NPC field cursor
        self.town_npc_buffer = ""           # NPC field edit buffer
        self.town_npc_field_scroll = 0      # NPC field scroll
        # Map editor
        self.town_editor_active = False     # True when map editor launched
        self._town_map_editor_state = None  # MapEditorState instance
        self._town_map_editor_handler = None  # MapEditorInputHandler instance
        # Naming overlay
        self.town_naming = False
        self.town_name_buf = ""
        self.town_naming_is_new = False
        # Save flash
        self.town_save_flash = 0.0
        # NPC type/shop type options
        self._NPC_TYPES = ["villager", "shopkeep", "innkeeper", "priest", "elder"]
        self._SHOP_TYPES = ["general", "weapons", "armor", "reagent", "potion", "book", "map"]

        # Gallery render modes
        self._GALLERY_RENDER_MODE = {
            # Overworld: all sprites used directly
            ("overworld", "grass"): "sprite",
            ("overworld", "water"): "sprite",
            ("overworld", "forest"): "sprite",
            ("overworld", "mountain"): "sprite",
            ("overworld", "town"): "sprite",
            ("overworld", "dungeon"): "sprite",
            ("overworld", "dungeon_cleared"): "sprite+procedural",
            ("overworld", "path"): "sprite",
            ("overworld", "sand"): "sprite",
            ("overworld", "bridge"): "sprite",
            # Town: sprites used in medieval style, procedural otherwise
            ("town", "floor"): "sprite+procedural",
            ("town", "wall"): "sprite+procedural",
            ("town", "counter"): "sprite+procedural",
            ("town", "door"): "sprite+procedural",
            ("town", "exit"): "sprite",
            ("town", "altar"): "procedural",
            # Dungeon: base sprites with procedural environmental overlay
            ("dungeon", "dfloor"): "sprite+procedural",
            ("dungeon", "dwall"): "sprite+procedural",
            ("dungeon", "chest"): "sprite",
            ("dungeon", "artifact"): "sprite+procedural",
            ("dungeon", "portal"): "sprite+procedural",
            ("dungeon", "wall_torch"): "sprite+procedural",
            ("dungeon", "moss"): "sprite+procedural",
            ("dungeon", "puddle"): "sprite+procedural",
            ("dungeon", "ddoor"): "sprite+procedural",
            ("dungeon", "locked_door"): "sprite+procedural",
            ("dungeon", "stairs"): "procedural",
            ("dungeon", "stairs_down"): "procedural",
            ("dungeon", "trap"): "procedural",
        }

        # Town template defaults
        self._TOWN_SUB_DEFAULTS = {
            "layouts":   {"name_prefix": "Town Layout",   "width": 18, "height": 19},
            "features":  {"name_prefix": "Town Feature",  "width": 8,  "height": 8},
            "interiors": {"name_prefix": "Interior",      "width": 14, "height": 15},
        }

    # ══════════════════════════════════════════════════════════
    # ── Town Template Methods ─────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def town_templates_path(self):
        """Return path to the standalone town_templates.json file."""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "town_templates.json")

    def load_townlayouts(self):
        """Load all town sub-editor lists from town_templates.json."""
        data = {}
        path = self.town_templates_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        for sub_key in ("layouts", "features", "interiors"):
            items = []
            defaults = self._TOWN_SUB_DEFAULTS[sub_key]
            raw = data.get(sub_key, [])
            for tl in raw:
                item = {
                    "name": tl.get("name", "Unnamed"),
                    "width": tl.get("width", defaults["width"]),
                    "height": tl.get("height", defaults["height"]),
                    "tiles": dict(tl.get("tiles", {})),
                }
                if sub_key == "layouts":
                    item["description"] = tl.get("description", "")
                    item["town_style"] = tl.get("town_style", "medieval")
                    item["entry_col"] = tl.get("entry_col", 0)
                    item["entry_row"] = tl.get("entry_row", 0)
                    item["npcs"] = list(tl.get("npcs", []))
                if sub_key == "interiors":
                    item["parent_town"] = tl.get("parent_town", "")
                items.append(item)
            self.town_lists[sub_key] = items

    # ══════════════════════════════════════════════════════════
    # ── Town Editor Methods ──────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def load_towns(self):
        """Load town layouts from town_templates.json for the town editor."""
        self.load_townlayouts()
        self.town_cursor = 0
        self.town_scroll = 0

    def save_towns(self):
        """Save town layouts back to town_templates.json."""
        path = self.town_templates_path()
        data = {}
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        # Write back layouts with npcs attached
        out_layouts = []
        for town in self.town_lists.get("layouts", []):
            entry = {
                "name": town.get("name", "Unnamed"),
                "width": town.get("width", 18),
                "height": town.get("height", 19),
                "tiles": town.get("tiles", {}),
                "description": town.get("description", ""),
                "town_style": town.get("town_style", "medieval"),
                "entry_col": town.get("entry_col", 0),
                "entry_row": town.get("entry_row", 0),
                "npcs": town.get("npcs", []),
            }
            out_layouts.append(entry)
        data["layouts"] = out_layouts
        # Preserve features and interiors as-is
        if "features" not in data:
            data["features"] = []
        if "interiors" not in data:
            data["interiors"] = []
        for sub_key in ("features", "interiors"):
            if self.town_lists.get(sub_key):
                data[sub_key] = self.town_lists[sub_key]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _town_get_current(self):
        """Return the currently selected town layout dict, or None."""
        layouts = self.town_lists.get("layouts", [])
        if 0 <= self.town_cursor < len(layouts):
            return layouts[self.town_cursor]
        return None

    def _town_build_settings_fields(self):
        """Build FieldEntry list for the current town's settings."""
        town = self._town_get_current()
        if not town:
            self.town_fields = []
            return
        self.town_fields = [
            FieldEntry("Name", "name", town.get("name", ""), "text", True),
            FieldEntry("Description", "description",
                       town.get("description", ""), "text", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Width", "width",
                       str(town.get("width", 18)), "int", True),
            FieldEntry("Height", "height",
                       str(town.get("height", 19)), "int", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Style", "town_style",
                       town.get("town_style", "medieval"), "text", True),
            FieldEntry("Entry Col", "entry_col",
                       str(town.get("entry_col", 0)), "int", True),
            FieldEntry("Entry Row", "entry_row",
                       str(town.get("entry_row", 0)), "int", True),
        ]
        self.town_field = self._next_editable_generic(self.town_fields, 0)
        self.town_buffer = self.town_fields[self.town_field].value
        self.town_field_scroll = 0

    def _town_save_settings_fields(self):
        """Write settings fields back into the current town dict."""
        town = self._town_get_current()
        if not town:
            return
        for fe in self.town_fields:
            if not fe.editable or fe.field_type == "section":
                continue
            key = fe.key
            val = fe.value
            if fe.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            town[key] = val

    def _town_load_npcs(self):
        """Load NPC list from the current town layout."""
        town = self._town_get_current()
        if not town:
            self.town_npc_list = []
            return
        self.town_npc_list = list(town.get("npcs", []))
        self.town_npc_cursor = 0
        self.town_npc_scroll = 0

    def _town_save_npcs(self):
        """Write NPC list back into the current town dict."""
        town = self._town_get_current()
        if not town:
            return
        town["npcs"] = list(self.town_npc_list)

    def _town_build_npc_fields(self):
        """Build FieldEntry list for the selected NPC."""
        if not (0 <= self.town_npc_cursor < len(self.town_npc_list)):
            self.town_npc_fields = []
            return
        npc = self.town_npc_list[self.town_npc_cursor]
        npc_type = npc.get("npc_type", "villager")
        self.town_npc_fields = [
            FieldEntry("Name", "name", npc.get("name", ""), "text", True),
            FieldEntry("Type", "npc_type", npc_type, "text", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Col", "col", str(npc.get("col", 0)), "int", True),
            FieldEntry("Row", "row", str(npc.get("row", 0)), "int", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Dialogue", "dialogue",
                       ", ".join(npc.get("dialogue", ["Hello."])), "text", True),
            FieldEntry("Shop Type", "shop_type",
                       npc.get("shop_type", "general"), "text", True),
            FieldEntry("God Name", "god_name",
                       npc.get("god_name", "The Divine"), "text", True),
            FieldEntry("Wander Range", "wander_range",
                       str(npc.get("wander_range", 4)), "int", True),
        ]
        self.town_npc_field = self._next_editable_generic(
            self.town_npc_fields, 0)
        self.town_npc_buffer = self.town_npc_fields[self.town_npc_field].value
        self.town_npc_field_scroll = 0

    def _town_save_npc_fields(self):
        """Write NPC fields back into the NPC dict."""
        if not (0 <= self.town_npc_cursor < len(self.town_npc_list)):
            return
        npc = self.town_npc_list[self.town_npc_cursor]
        for fe in self.town_npc_fields:
            if not fe.editable or fe.field_type == "section":
                continue
            key = fe.key
            val = fe.value
            if fe.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            if key == "dialogue":
                # Parse comma-separated dialogue lines
                val = [s.strip() for s in val.split(",") if s.strip()]
                if not val:
                    val = ["Hello."]
            npc[key] = val

    def _town_add_new(self, name):
        """Add a new blank town layout."""
        new_town = {
            "name": name,
            "width": 18,
            "height": 19,
            "tiles": {},
            "description": "",
            "town_style": "medieval",
            "entry_col": 0,
            "entry_row": 0,
            "npcs": [],
        }
        self.town_lists["layouts"].append(new_town)
        self.town_cursor = len(self.town_lists["layouts"]) - 1
        self.save_towns()

    def _town_add_npc(self):
        """Add a new default NPC to the current town."""
        # Place at the town's entry point so the NPC spawns in the
        # walkable area instead of the void at (1,1).
        town = self._town_get_current()
        ec = town.get("entry_col", 1) if town else 1
        er = town.get("entry_row", 1) if town else 1
        new_npc = {
            "name": "New NPC",
            "npc_type": "villager",
            "col": ec,
            "row": er,
            "dialogue": ["Hello there!"],
            "shop_type": "general",
            "god_name": "The Divine",
            "wander_range": 4,
        }
        self.town_npc_list.append(new_npc)
        self.town_npc_cursor = len(self.town_npc_list) - 1
        self._town_save_npcs()

    def _town_delete_npc(self):
        """Delete the currently selected NPC."""
        n = len(self.town_npc_list)
        if n == 0:
            return
        self.town_npc_list.pop(self.town_npc_cursor)
        n -= 1
        if n == 0:
            self.town_npc_cursor = 0
        elif self.town_npc_cursor >= n:
            self.town_npc_cursor = n - 1
        self._town_save_npcs()

    def _town_launch_map_editor(self):
        """Launch the map editor for the current town's tile grid."""
        from src.map_editor import (
            MapEditorConfig, MapEditorState, MapEditorInputHandler,
            build_town_brushes,
            STORAGE_SPARSE, GRID_FIXED,
        )
        town = self._town_get_current()
        if not town:
            return
        w = town.get("width", 18)
        h = town.get("height", 19)

        saved_all = self.load_map_templates()
        brushes = build_town_brushes(self.TILE_CONTEXT,
                                     all_templates=saved_all)

        def on_save(state):
            # Sparse tiles are already the same dict reference,
            # but reassign to be safe
            town["tiles"] = state.tiles
            town["width"] = state.config.width
            town["height"] = state.config.height
            state.dirty = False
            self.save_towns()
            self.town_save_flash = 1.5

        def on_exit(st):
            # Save tiles on exit
            town["tiles"] = st.tiles
            self.save_towns()
            self.town_editor_active = False
            self._town_map_editor_state = None
            self._town_map_editor_handler = None

        config = MapEditorConfig(
            title=f"Town: {town.get('name', 'Unnamed')}",
            storage=STORAGE_SPARSE,
            grid_type=GRID_FIXED,
            width=w,
            height=h,
            tile_context="town",
            brushes=brushes,
            supports_replace=True,
            on_save=on_save,
            on_exit=on_exit,
        )
        # Pass existing tiles directly — sparse storage uses a dict
        existing_tiles = dict(town.get("tiles", {}))
        state = MapEditorState(config, tiles=existing_tiles)
        handler = MapEditorInputHandler(state)
        self._town_map_editor_state = state
        self._town_map_editor_handler = handler
        self.town_editor_active = True

    # ══════════════════════════════════════════════════════════
    # ── Tile Editor Methods ────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def restore_tile_defs_from_disk(self):
        """Called once at startup to merge saved tile_defs.json into
        the in-memory settings.TILE_DEFS and TILE_CONTEXT so the rest
        of the game (town rendering, map, etc.) sees user-created tiles."""
        from src import settings
        try:
            with open(self.tiles_path(), "r") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return  # no saved file yet — nothing to restore
        for tid_str, entry in saved.items():
            tid = int(tid_str)
            color = entry.get("color", [128, 128, 128])
            if isinstance(color, list):
                color = tuple(color)
            tdef = {
                "name": entry.get("name", f"Tile {tid}"),
                "walkable": entry.get("walkable", True),
                "color": color,
            }
            # Carry interaction fields into TILE_DEFS for runtime access
            itype = entry.get("interaction_type", "")
            if itype and itype != "none":
                tdef["interaction_type"] = itype
                idata = entry.get("interaction_data", "")
                if idata:
                    tdef["interaction_data"] = idata
            # Carry behavior flags (light_source, feature_light, etc.)
            # so engine subsystems can do data-driven dispatch instead
            # of hardcoded tile_id checks.
            flags = entry.get("flags")
            if flags:
                tdef["flags"] = dict(flags)
            settings.TILE_DEFS[tid] = tdef
            ctx = entry.get("context")
            if ctx:
                self.TILE_CONTEXT[tid] = ctx

    def tiles_path(self):
        """Path to tile_defs.json."""
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "tile_defs.json")

    def spawn_points_path(self):
        """Path to spawn_points.json."""
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "spawn_points.json")

    def load_tiles(self):
        """Load tile types from disk (tile_defs.json) merged with
        hardcoded settings.TILE_DEFS into the editor."""
        import json
        from src.settings import TILE_DEFS
        from src import settings

        # --- Load saved overrides / additions from JSON ----------------
        saved = {}
        try:
            with open(self.tiles_path(), "r") as f:
                saved = json.load(f)          # {str(tile_id): {...}, ...}
        except (OSError, ValueError):
            saved = {}

        # Apply saved data back into the in-memory TILE_DEFS and
        # TILE_CONTEXT so the rest of the game sees them too.
        for tid_str, entry in saved.items():
            tid = int(tid_str)
            color = entry.get("color", [128, 128, 128])
            if isinstance(color, list):
                color = tuple(color)
            tdef = {
                "name": entry.get("name", f"Tile {tid}"),
                "walkable": entry.get("walkable", True),
                "color": color,
            }
            # Carry interaction fields into TILE_DEFS for runtime access
            itype = entry.get("interaction_type", "")
            if itype and itype != "none":
                tdef["interaction_type"] = itype
                idata = entry.get("interaction_data", "")
                if idata:
                    tdef["interaction_data"] = idata
            # Carry behavior flags (light_source, feature_light, etc.)
            # so engine subsystems can do data-driven dispatch instead
            # of hardcoded tile_id checks.
            flags = entry.get("flags")
            if flags:
                tdef["flags"] = dict(flags)
            settings.TILE_DEFS[tid] = tdef
            ctx = entry.get("context")
            if ctx:
                self.TILE_CONTEXT[tid] = ctx

        # --- Build editor list from the (now-merged) TILE_DEFS --------
        tiles = []
        for tile_id in sorted(settings.TILE_DEFS.keys()):
            tdef = settings.TILE_DEFS[tile_id]
            context = self.TILE_CONTEXT.get(tile_id, "overworld")
            # Carry over saved sprite key if present; for tiles that
            # were never edited, resolve from the manifest so every
            # tile carries an explicit _sprite for reliable rendering.
            sprite_key = ""
            s = saved.get(str(tile_id))
            if s:
                sprite_key = s.get("sprite", "")
            if not sprite_key:
                sprite_key = self.tile_sprite_key(tile_id) or ""
            # Load interaction fields from saved data
            interact_type = ""
            interact_data = ""
            if s:
                interact_type = s.get("interaction_type", "none")
                interact_data = s.get("interaction_data", "")
            if not interact_type:
                interact_type = "none"
            tiles.append({
                "_tile_id": tile_id,
                "name": tdef.get("name", f"Tile {tile_id}"),
                "walkable": tdef.get("walkable", True),
                "color": list(tdef.get("color", (128, 128, 128))),
                "_context": context,
                "_sprite": sprite_key,
                "interaction_type": interact_type,
                "interaction_data": interact_data,
            })
        self.tile_list = tiles
        self.tile_in_folder = False
        self.tile_folder_cursor = 0
        self.tile_folder_scroll = 0
        self._rebuild_tile_folders()

        # Load spawn point extended data
        try:
            with open(self.spawn_points_path(), "r") as f:
                sp_raw = json.load(f)
            self.spawn_data = {}
            for tid_str, entry in sp_raw.get("spawn_points", {}).items():
                self.spawn_data[int(tid_str)] = dict(entry)
        except (OSError, ValueError):
            self.spawn_data = {}

    def _rebuild_tile_folders(self):
        """Build folder list with tile counts per context."""
        # Examine screen reuses overworld tiles (Grass, Forest, Sand, Path)
        examine_ids = {0, 2, 7, 6}  # GRASS, FOREST, SAND, PATH
        folders = []
        for fdef in self.TILE_FOLDER_ORDER:
            fname = fdef["name"]
            if fname == "examine":
                count = sum(1 for t in self.tile_list
                            if t["_tile_id"] in examine_ids)
            elif fname == "battle":
                count = 0  # battle uses procedural tiles
            else:
                count = sum(1 for t in self.tile_list
                            if t.get("_context") == fname)
            folders.append({
                "name": fname,
                "label": fdef["label"],
                "count": count,
            })
        self.tile_folders = folders

    def tile_enter_folder(self):
        """Enter the selected tile folder — build tile list."""
        if self.tile_folder_cursor >= len(self.tile_folders):
            return
        fname = self.tile_folders[self.tile_folder_cursor]["name"]
        examine_ids = {0, 2, 7, 6}
        if fname == "examine":
            self.tile_folder_tiles = [
                i for i, t in enumerate(self.tile_list)
                if t["_tile_id"] in examine_ids]
        elif fname == "battle":
            self.tile_folder_tiles = []
        else:
            self.tile_folder_tiles = [
                i for i, t in enumerate(self.tile_list)
                if t.get("_context") == fname]
        self.tile_cursor = 0
        self.tile_scroll = 0
        self.tile_in_folder = True

    def save_tiles(self):
        """Write tile definitions back to settings.TILE_DEFS, update
        the TILE_CONTEXT map, persist to tile_defs.json, and update
        the tile manifest for new / changed tiles."""
        from src import settings

        disk_data = {}  # what goes to tile_defs.json

        for tile in self.tile_list:
            tid = tile["_tile_id"]
            color = tile.get("color", [128, 128, 128])
            if isinstance(color, list):
                color = tuple(color)
            if tid in settings.TILE_DEFS:
                settings.TILE_DEFS[tid]["name"] = tile["name"]
                settings.TILE_DEFS[tid]["walkable"] = tile["walkable"]
                settings.TILE_DEFS[tid]["color"] = color
            else:
                # New tile — add to TILE_DEFS
                settings.TILE_DEFS[tid] = {
                    "name": tile["name"],
                    "walkable": tile["walkable"],
                    "color": color,
                }
            # Sync interaction fields into TILE_DEFS for runtime access
            itype = tile.get("interaction_type", "none")
            if itype and itype != "none":
                settings.TILE_DEFS[tid]["interaction_type"] = itype
                idata = tile.get("interaction_data", "")
                if idata:
                    settings.TILE_DEFS[tid]["interaction_data"] = idata
            else:
                # Clear stale interaction fields if type was set to "none"
                settings.TILE_DEFS[tid].pop("interaction_type", None)
                settings.TILE_DEFS[tid].pop("interaction_data", None)
            # Keep TILE_CONTEXT in sync
            ctx = tile.get("_context")
            if ctx:
                self.TILE_CONTEXT[tid] = ctx

            # Build the JSON entry for this tile
            entry_data = {
                "name": tile["name"],
                "walkable": tile["walkable"],
                "color": list(color) if isinstance(color, tuple) else color,
                "context": tile.get("_context", "overworld"),
                "sprite": tile.get("_sprite", ""),
            }
            # Only persist interaction fields if they have meaningful values
            itype = tile.get("interaction_type", "none")
            if itype and itype != "none":
                entry_data["interaction_type"] = itype
                idata = tile.get("interaction_data", "")
                if idata:
                    entry_data["interaction_data"] = idata
            # Preserve behavior flags (light_source, feature_light, etc.).
            # These aren't editable in the in-game tile editor yet, so we
            # carry them through from the in-memory TILE_DEFS so a
            # re-save doesn't strip them.
            existing_flags = settings.TILE_DEFS.get(tid, {}).get("flags")
            if existing_flags:
                entry_data["flags"] = dict(existing_flags)
            disk_data[str(tid)] = entry_data

        # Write to data/tile_defs.json
        try:
            with open(self.tiles_path(), "w") as f:
                json.dump(disk_data, f, indent=2)
        except OSError:
            pass

        # Persist sprite assignments to the tile manifest
        self._save_tile_sprites()
        # Save spawn point data
        self._save_spawn_data()
        # Invalidate cached town brushes so new/changed tiles appear
        self.townlayout_brushes = None
        return True

    def _save_spawn_data(self):
        """Persist spawn_data to spawn_points.json and reload runtime data."""
        sp_json = {
            "_comment": "Monster spawn point definitions. Keyed by tile ID.",
            "spawn_points": {str(k): v for k, v in self.spawn_data.items()},
        }
        try:
            with open(self.spawn_points_path(), "w") as f:
                json.dump(sp_json, f, indent=2)
                f.write("\n")
        except OSError:
            pass
        # Reload runtime spawn data
        from src.party import reload_module_data as _reload
        from src import party as _party_mod
        from src.data_loader import load_spawn_points
        _party_mod.SPAWN_POINTS = load_spawn_points()

    def _save_tile_sprites(self):
        """Update tile_manifest.json with sprite ↔ tile_id bindings.

        Before writing new assignments, clear any stale tile_id entries
        so that each tile_id maps to exactly one manifest sprite.
        """
        mpath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "tile_manifest.json")
        try:
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return

        # Build sprite_key → lowest tile_id mapping.  When multiple
        # tiles share the same sprite, the manifest tile_id goes to the
        # lowest (original) tile_id so existing lookups keep working.
        sprite_to_tid = {}   # "cat/name" → lowest tile_id
        assigned_tids = set()
        for tile in self.tile_list:
            sprite_key = tile.get("_sprite", "")
            if sprite_key and "/" in sprite_key:
                tid = tile["_tile_id"]
                assigned_tids.add(tid)
                if sprite_key not in sprite_to_tid or tid < sprite_to_tid[sprite_key]:
                    sprite_to_tid[sprite_key] = tid

        # First pass: clear stale tile_id assignments for any tile_id
        # that is about to be reassigned, so only one entry ends up
        # owning each tile_id.
        for cat in manifest:
            if cat.startswith("_"):
                continue
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for _name, entry in section.items():
                if isinstance(entry, dict) and entry.get("tile_id") in assigned_tids:
                    del entry["tile_id"]

        # Second pass: assign the lowest tile_id per sprite key
        for sprite_key, tid in sprite_to_tid.items():
            parts = sprite_key.split("/", 1)
            if len(parts) != 2:
                continue
            cat, name = parts
            section = manifest.get(cat)
            if isinstance(section, dict) and name in section:
                entry = section[name]
                if isinstance(entry, dict):
                    entry["tile_id"] = tid
        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            pass
        # Reload the renderer's manifest cache so sprite lookups pick up
        # the new tile_id assignments immediately.
        self.game.renderer.reload_sprites()

    def build_tile_fields(self, tile):
        """Build editable field list for a single tile type."""
        from src.settings import TILE_DEFS
        FE = FieldEntry
        color = tile.get("color", [128, 128, 128])
        color_str = f"{color[0]}, {color[1]}, {color[2]}" \
            if isinstance(color, (list, tuple)) else str(color)
        # Resolve current sprite from manifest via tile_id
        sprite_key = tile.get("_sprite", "")
        if not sprite_key:
            sprite_key = self.tile_sprite_key(
                tile.get("_tile_id"))
        # Interaction fields
        interact = tile.get("interaction_type", "none")
        interact_data = tile.get("interaction_data", "")
        fields = [
            FE("-- Tile Type --", "_hdr1", "", "section", False),
            FE("ID", "_tile_id",
               str(tile.get("_tile_id", 0)), "int", False),
            FE("Name", "name", tile.get("name", "")),
            FE("Sprite", "_sprite", sprite_key, "sprite"),
            FE("Walkable", "walkable",
               str(tile.get("walkable", True)), "choice"),
            FE("Color (R,G,B)", "_color", color_str),
            FE("-- Interaction --", "_hdr2", "", "section", False),
            FE("Interaction", "interaction_type", interact, "choice"),
        ]
        # Conditionally show the data field based on interaction type
        if interact == "shop":
            fields.append(
                FE("Shop Type", "interaction_data", interact_data, "choice"))
        elif interact == "sign":
            fields.append(
                FE("Sign Text", "interaction_data", interact_data))
        elif interact == "spawn":
            # Spawn-specific fields — loaded from spawn_data
            tid = tile.get("_tile_id", 0)
            sp = self.spawn_data.get(tid, {})
            fields.append(
                FE("-- Spawn Config --", "_hdr_sp1", "", "section", False))
            # Background tile — which terrain to draw behind the spawn
            bg_tid = sp.get("background_tile", 0)
            bg_name = TILE_DEFS.get(bg_tid, {}).get("name", "Grass")
            fields.append(
                FE("Background", "_sp_background_tile",
                   bg_name, "choice"))
            fields.append(
                FE("Description", "_sp_description",
                   sp.get("description", "A monster lair.")))
            # Spawn monsters — clickable sub-list editor
            _n_mon = len(sp.get("spawn_monsters", []))
            fields.append(
                FE("Edit Monsters", "_sp_edit_monsters",
                   f"{_n_mon} monster{'s' if _n_mon != 1 else ''} [>]",
                   "choice"))
            fields.append(
                FE("Spawn Chance %", "_sp_spawn_chance",
                   str(sp.get("spawn_chance", 20)), "int"))
            fields.append(
                FE("Spawn Radius", "_sp_spawn_radius",
                   str(sp.get("spawn_radius", 3)), "int"))
            fields.append(
                FE("Max Spawned", "_sp_max_spawned",
                   str(sp.get("max_spawned", 2)), "int"))
            fields.append(
                FE("-- Boss & Rewards --", "_hdr_sp2", "", "section", False))
            # Boss monsters — clickable sub-list editor (like Edit Monsters)
            _boss_list = sp.get("boss_monsters", [])
            # Backwards compat: migrate old single boss_monster string
            if not _boss_list and sp.get("boss_monster"):
                _boss_list = [sp["boss_monster"]]
            _n_boss = len(_boss_list)
            fields.append(
                FE("Edit Boss Encounter", "_sp_edit_boss",
                   f"{_n_boss} monster{'s' if _n_boss != 1 else ''} [>]",
                   "choice"))
            fields.append(
                FE("XP Reward", "_sp_xp_reward",
                   str(sp.get("xp_reward", 50)), "int"))
            fields.append(
                FE("Gold Reward", "_sp_gold_reward",
                   str(sp.get("gold_reward", 25)), "int"))
            # Loot items — clickable sub-list editor
            _n_loot = len(sp.get("loot", []))
            fields.append(
                FE("Edit Loot", "_sp_edit_loot",
                   f"{_n_loot} item{'s' if _n_loot != 1 else ''} [>]",
                   "choice"))
        elif interact != "none":
            fields.append(
                FE("Data", "interaction_data", interact_data))
        self.tile_fields = fields
        idx, buf = self.finalize_fields(fields)
        self.tile_field = idx
        self.tile_scroll_f = 0
        self.tile_buffer = buf

    def tile_real_index(self):
        """Resolve the folder-relative cursor to a real tile_list index."""
        if (self.tile_in_folder
                and self.tile_folder_tiles
                and self.tile_cursor < len(self.tile_folder_tiles)):
            return self.tile_folder_tiles[self.tile_cursor]
        return self.tile_cursor

    def save_tile_fields(self):
        """Apply edited fields back to the tile dict."""
        from src.settings import TILE_DEFS
        real_idx = self.tile_real_index()
        if real_idx >= len(self.tile_list):
            return
        tile = self.tile_list[real_idx]
        if self.tile_fields:
            entry = self.tile_fields[self.tile_field]
            entry.value = self.tile_buffer
        # Collect spawn field changes to apply in one pass
        spawn_changes = {}
        for entry in self.tile_fields:
            key, val = entry.key, entry.value
            # Handle spawn-specific fields (skip sub-list launchers)
            if key.startswith("_sp_") and key not in (
                    "_sp_edit_monsters", "_sp_edit_loot", "_sp_edit_boss"):
                spawn_changes[key] = val
                continue
            if key in ("_sp_edit_monsters", "_sp_edit_loot", "_sp_edit_boss"):
                continue  # read-only display fields
            if key.startswith("_") and key not in ("_color", "_sprite"):
                continue
            if key == "_sprite":
                tile["_sprite"] = val
            elif key == "_color":
                try:
                    parts = [int(p.strip()) for p in val.split(",")]
                    if len(parts) == 3:
                        tile["color"] = parts
                except ValueError:
                    pass
            elif key == "walkable":
                tile[key] = val == "True"
            elif key == "name":
                tile[key] = val
            elif key == "interaction_type":
                old_type = tile.get("interaction_type", "none")
                tile["interaction_type"] = val
                # When interaction type changes, reset interaction_data
                # and rebuild fields to show/hide the conditional field
                if val != old_type:
                    tile["interaction_data"] = ""
                    # Rebuild fields so the conditional data field updates
                    self.build_tile_fields(tile)
                    # Re-position cursor on the interaction_type field
                    for fi, fe in enumerate(self.tile_fields):
                        if fe.key == "interaction_type":
                            self.tile_field = fi
                            self.tile_buffer = val
                            break
                    # Break out of the for loop — the old field list is
                    # stale after rebuild, continuing would overwrite data
                    break
            elif key == "interaction_data":
                tile["interaction_data"] = val

        # Apply collected spawn field changes to spawn_data
        if spawn_changes:
            tid = tile.get("_tile_id", 0)
            sp = self.spawn_data.setdefault(tid, {})
            sp["name"] = tile.get("name", "Monster Spawn")
            for skey, sval in spawn_changes.items():
                field_name = skey[4:]  # strip "_sp_" prefix
                if field_name in ("spawn_chance", "spawn_radius",
                                  "max_spawned", "xp_reward", "gold_reward"):
                    try:
                        sp[field_name] = int(sval)
                    except ValueError:
                        pass
                elif field_name == "background_tile":
                    # Convert tile name back to tile ID
                    bg_id = 0  # default to grass
                    for _tid, _td in TILE_DEFS.items():
                        if _td.get("name") == sval:
                            bg_id = _tid
                            break
                    sp[field_name] = bg_id
                else:
                    sp[field_name] = sval

    @staticmethod
    def tile_sprite_key(tile_id):
        """Resolve a tile_id to its manifest 'category/name' key."""
        if tile_id is None:
            return ""
        try:
            mpath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "tile_manifest.json")
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return ""
        for cat in ("overworld", "town", "dungeon",
                     "unique_tiles", "objects"):
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for name, entry in section.items():
                if (isinstance(entry, dict)
                        and entry.get("tile_id") == tile_id):
                    return f"{cat}/{name}"
        return ""

    def get_tile_choices(self, key):
        """Return choice options for a tile field."""
        from src.settings import TILE_DEFS
        if key == "_sprite":
            from src import data_registry as DR
            # Use sprites from the category matching the tile's context
            context = None
            if (self.tile_folder_tiles
                    and self.tile_cursor < len(self.tile_folder_tiles)):
                ti = self.tile_folder_tiles[self.tile_cursor]
                if ti < len(self.tile_list):
                    context = self.tile_list[ti].get("_context")
            if not context:
                # Fallback: use the current folder name
                if (self.tile_folders
                        and self.tile_folder_cursor < len(
                            self.tile_folders)):
                    context = self.tile_folders[
                        self.tile_folder_cursor]["name"]
            # Map context to gallery categories
            if context in ("overworld", "town", "dungeon"):
                cats = [context]
            elif context == "artifacts":
                cats = ["objects"]
            else:
                cats = ["overworld", "town", "dungeon"]
            seen = set()
            result = []
            for cat in cats:
                for s in DR.sprites_for_category(cat):
                    if s not in seen:
                        seen.add(s)
                        result.append(s)
            return sorted(result)
        if key == "walkable":
            return ["True", "False"]
        if key == "interaction_type":
            return ["none", "shop", "sign", "spawn"]
        if key == "interaction_data":
            # When interaction_type is "shop", offer shop type choices
            real_idx = self.tile_real_index()
            if real_idx < len(self.tile_list):
                tile = self.tile_list[real_idx]
                if tile.get("interaction_type") == "shop":
                    return ["general", "reagent", "weapon", "armor",
                            "magic", "inn", "guild"]
            return []
        # Background tile choice — overworld terrain tiles
        if key == "_sp_background_tile":
            return [td["name"] for tid, td in sorted(TILE_DEFS.items())
                    if self.TILE_CONTEXT.get(tid) == "overworld"
                    and td.get("walkable", False)]
        # Sub-list launchers — no cycling, Enter/Right opens the list
        if key in ("_sp_edit_monsters", "_sp_edit_loot", "_sp_edit_boss"):
            return []  # handled by level intercept, not choice cycling
        return []

    def add_tile(self):
        """Add a new tile type with the next available ID in the current folder."""
        used_ids = {t["_tile_id"] for t in self.tile_list}
        new_id = max(used_ids) + 1 if used_ids else 100
        # Determine context from the currently selected folder
        context = "overworld"
        if (self.tile_folders
                and self.tile_folder_cursor < len(self.tile_folders)):
            context = self.tile_folders[
                self.tile_folder_cursor]["name"]
        # Don't add tiles to virtual folders (examine reuses overworld,
        # battle uses procedural tiles).
        if context in ("examine", "battle"):
            context = "overworld"
        # Spawn tiles default to "spawn" interaction type
        if context == "spawns":
            interact = "spawn"
            tile_color = [180, 40, 40]
            tile_name = f"Monster Spawn {new_id}"
        else:
            interact = "none"
            tile_color = [128, 128, 128]
            tile_name = f"New Tile {new_id}"
        new_tile = {
            "_tile_id": new_id,
            "name": tile_name,
            "walkable": True,
            "color": tile_color,
            "_context": context,
            "interaction_type": interact,
            "interaction_data": "",
        }
        self.tile_list.append(new_tile)
        # Initialize spawn data for new spawn tiles
        if context == "spawns":
            self.spawn_data[new_id] = {
                "name": tile_name,
                "description": "A monster lair.",
                "spawn_monsters": [],
                "spawn_chance": 20,
                "spawn_radius": 3,
                "max_spawned": 2,
                "boss_monster": "",
                "boss_monsters": [],
                "xp_reward": 50,
                "gold_reward": 25,
                "loot": [],
            }
        self.tile_cursor = len(self.tile_list) - 1

    def duplicate_tile(self):
        """Duplicate the currently selected tile type with a new ID."""
        if not self.tile_list:
            return
        real_idx = self.tile_real_index()
        if real_idx < 0 or real_idx >= len(self.tile_list):
            return
        src = self.tile_list[real_idx]
        used_ids = {t["_tile_id"] for t in self.tile_list}
        new_id = max(used_ids) + 1 if used_ids else 100
        # Resolve sprite: use explicit _sprite if set, otherwise look up
        # from the manifest via the source tile's tile_id.
        sprite_key = src.get("_sprite", "")
        if not sprite_key:
            sprite_key = self.tile_sprite_key(src.get("_tile_id"))
        dup = {
            "_tile_id": new_id,
            "name": f"{src['name']} Copy",
            "walkable": src.get("walkable", True),
            "color": list(src.get("color", [128, 128, 128])),
            "_context": src.get("_context", "overworld"),
            "_sprite": sprite_key or "",
        }
        self.tile_list.append(dup)
        self.tile_cursor = len(self.tile_list) - 1

    def remove_tile(self):
        """Remove the currently selected tile type."""
        if not self.tile_list:
            return
        real_idx = self.tile_real_index()
        if 0 <= real_idx < len(self.tile_list):
            self.tile_list.pop(real_idx)
            # Keep the folder-relative cursor in bounds after removal
            folder_len = len(self.tile_folder_tiles) - 1 \
                if self.tile_in_folder else len(self.tile_list)
            if self.tile_cursor >= folder_len:
                self.tile_cursor = max(0, folder_len - 1)

    # ── Spawn sub-list editor (monsters / loot) ──────────────

    def _get_all_monster_names(self):
        """Return sorted list of all monster names from monsters.json."""
        if self._spawn_all_monsters is not None:
            return self._spawn_all_monsters
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "monsters.json")
        try:
            with open(path) as f:
                data = json.load(f)
            self._spawn_all_monsters = sorted(
                data.get("monsters", {}).keys())
        except (OSError, ValueError):
            self._spawn_all_monsters = []
        return self._spawn_all_monsters

    def _get_all_item_names_for_spawn(self):
        """Return sorted list of all item names from items.json."""
        if self._spawn_all_items is not None:
            return self._spawn_all_items
        path = self.items_path()
        try:
            with open(path) as f:
                data = json.load(f)
            names = []
            for section in ("weapons", "armors", "general"):
                names.extend(data.get(section, {}).keys())
            self._spawn_all_items = sorted(set(names))
        except (OSError, ValueError):
            self._spawn_all_items = []
        return self._spawn_all_items

    def spawn_open_sublist(self, mode):
        """Open the spawn sub-list editor for 'monsters' or 'loot'.

        Enters level 4 within the tile field editor.
        """
        real_idx = self.tile_real_index()
        if real_idx >= len(self.tile_list):
            return
        tile = self.tile_list[real_idx]
        tid = tile.get("_tile_id", 0)
        sp = self.spawn_data.setdefault(tid, {})

        self.spawn_sublist_mode = mode
        if mode == "monsters":
            self.spawn_sublist = list(sp.get("spawn_monsters", []))
        elif mode == "boss":
            boss_list = list(sp.get("boss_monsters", []))
            # Backwards compat: migrate old single boss_monster string
            if not boss_list and sp.get("boss_monster"):
                boss_list = [sp["boss_monster"]]
            self.spawn_sublist = boss_list
        else:
            self.spawn_sublist = list(sp.get("loot", []))
        self.spawn_sublist_cursor = 0
        self.spawn_sublist_scroll = 0
        # Invalidate caches so fresh data is loaded
        self._spawn_all_monsters = None
        self._spawn_all_items = None
        self.level = 4

    def spawn_save_sublist(self):
        """Save the current sub-list back to spawn_data."""
        real_idx = self.tile_real_index()
        if real_idx >= len(self.tile_list):
            return
        tile = self.tile_list[real_idx]
        tid = tile.get("_tile_id", 0)
        sp = self.spawn_data.setdefault(tid, {})
        if self.spawn_sublist_mode == "monsters":
            sp["spawn_monsters"] = list(self.spawn_sublist)
        elif self.spawn_sublist_mode == "boss":
            sp["boss_monsters"] = list(self.spawn_sublist)
        else:
            sp["loot"] = list(self.spawn_sublist)

    def spawn_sublist_add(self):
        """Add a new entry to the spawn sub-list."""
        if self.spawn_sublist_mode in ("monsters", "boss"):
            options = self._get_all_monster_names()
        else:
            options = self._get_all_item_names_for_spawn()
        if options:
            self.spawn_sublist.append(options[0])
            self.spawn_sublist_cursor = len(self.spawn_sublist) - 1
            self.spawn_save_sublist()

    def spawn_sublist_remove(self):
        """Remove the selected entry from the spawn sub-list."""
        if not self.spawn_sublist:
            return
        idx = self.spawn_sublist_cursor
        if 0 <= idx < len(self.spawn_sublist):
            self.spawn_sublist.pop(idx)
            if self.spawn_sublist_cursor >= len(self.spawn_sublist):
                self.spawn_sublist_cursor = max(
                    0, len(self.spawn_sublist) - 1)
            self.spawn_save_sublist()

    def spawn_sublist_cycle(self, direction=1):
        """Cycle the selected entry through available options."""
        if not self.spawn_sublist:
            return
        idx = self.spawn_sublist_cursor
        if idx < 0 or idx >= len(self.spawn_sublist):
            return
        if self.spawn_sublist_mode in ("monsters", "boss"):
            options = self._get_all_monster_names()
        else:
            options = self._get_all_item_names_for_spawn()
        if not options:
            return
        current = self.spawn_sublist[idx]
        try:
            ci = options.index(current)
        except ValueError:
            ci = 0
        ci = (ci + direction) % len(options)
        self.spawn_sublist[idx] = options[ci]
        self.spawn_save_sublist()

    def _handle_spawn_sublist_input(self, event):
        """Handle input for the spawn sub-list editor (level 4)."""
        items = self.spawn_sublist
        n = len(items)

        if self._is_save_shortcut(event):
            self.spawn_save_sublist()
            self.save_tiles()
            self.dirty = False
            return

        if event.key == pygame.K_ESCAPE:
            self.spawn_save_sublist()
            # Rebuild tile fields to update the count display
            real_idx = self.tile_real_index()
            if real_idx < len(self.tile_list):
                self.build_tile_fields(self.tile_list[real_idx])
            self.spawn_sublist_mode = None
            self.level = 3
            return

        if event.key == pygame.K_UP and n > 0:
            self.spawn_sublist_cursor = (
                self.spawn_sublist_cursor - 1) % n
            self.spawn_sublist_scroll = self._adjust_scroll_generic(
                self.spawn_sublist_cursor, self.spawn_sublist_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self.spawn_sublist_cursor = (
                self.spawn_sublist_cursor + 1) % n
            self.spawn_sublist_scroll = self._adjust_scroll_generic(
                self.spawn_sublist_cursor, self.spawn_sublist_scroll)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            if n > 0:
                direction = 1 if event.key == pygame.K_RIGHT else -1
                self.spawn_sublist_cycle(direction)
        elif self._is_new_shortcut(event):
            self.spawn_sublist_add()
            self.spawn_sublist_scroll = self._adjust_scroll_generic(
                self.spawn_sublist_cursor, self.spawn_sublist_scroll)
        elif self._is_delete_shortcut(event):
            self.spawn_sublist_remove()

    # ══════════════════════════════════════════════════════════
    # ── Spell Editor Methods ───────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def spells_path(self):
        """Return the path to the spells.json file that the game
        actually uses — module directory first, then default data/."""
        if self.game.active_module_path:
            mod_path = os.path.join(self.game.active_module_path,
                                    "spells.json")
            if os.path.isfile(mod_path):
                return mod_path
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "spells.json")

    def load_spells(self):
        """Load spells from the active spells.json into the editor."""
        path = self.spells_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
            spells = data.get("spells", [])
        except (OSError, ValueError):
            spells = []
        # Sort: sorcerer first, then priest/cleric, each by level
        from src import data_registry as DR
        type_order = DR.casting_type_sort_order()
        spells.sort(key=lambda s: (
            type_order.get(s.get("casting_type", "sorcerer"), 2),
            s.get("min_level", 1),
            s.get("name", ""),
        ))
        self.spell_list = spells
        self.spell_cursor = 0
        self.spell_scroll = 0
        # Reset folder navigation to top level
        self.spell_nav = 0
        self.spell_ctype_cursor = 0
        self.spell_level_cursor = 0
        self.spell_level_scroll = 0
        self.spell_sel_ctype = None
        self.spell_sel_level = None
        self.spell_filtered = []

    def spell_casting_types(self):
        """Return sorted list of distinct casting types in the spell list."""
        from src import data_registry as DR
        order = DR.casting_type_sort_order()
        seen = {}
        for s in self.spell_list:
            ct = s.get("casting_type", "sorcerer")
            if ct not in seen:
                seen[ct] = order.get(ct, 99)
        return sorted(seen.keys(), key=lambda c: seen[c])

    def spell_levels_for_ctype(self, ctype):
        """Return sorted list of (level, count) for a casting type."""
        counts = Counter()
        for s in self.spell_list:
            if s.get("casting_type", "sorcerer") == ctype:
                counts[s.get("min_level", 1)] += 1
        return sorted(counts.items())

    def spell_filter(self, ctype, level):
        """Build filtered index list for a casting type + level.

        Resets cursor and scroll to 0.  Callers may adjust cursor
        afterwards if they need to restore a position.
        """
        self.spell_filtered = [
            i for i, s in enumerate(self.spell_list)
            if s.get("casting_type", "sorcerer") == ctype
            and s.get("min_level", 1) == level
        ]
        self.spell_cursor = min(
            self.spell_filter_pos,
            max(0, len(self.spell_filtered) - 1))
        self.spell_scroll = 0

    def save_spells(self):
        """Write current spell list back to the active spells.json
        and refresh the in-memory spell registry so changes are
        immediately available in gameplay."""
        path = self.spells_path()
        data = {"spells": self.spell_list}
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        # Refresh the runtime spell registry used by combat/casting.
        # Pass the active module directory so _load_spells_config
        # reads from the correct location.
        try:
            from src.party import reload_module_data as _reload
            _reload(self.game.active_module_path)
        except Exception:
            pass
        return True

    @staticmethod
    def default_classes(casting_type):
        """Return the default allowable_classes for a casting type."""
        from src import data_registry as DR
        return DR.classes_for_casting_type(casting_type)

    @staticmethod
    def finalize_fields(fields, start=0):
        """Advance to the first editable field and return (idx, buffer).

        Shared by all build_fields methods to eliminate the duplicated
        7-line init block.
        """
        n = len(fields)
        if n == 0:
            return 0, ""
        idx = start % n
        for _ in range(n):
            if fields[idx].editable:
                return idx, fields[idx].value
            idx = (idx + 1) % n
        return 0, ""

    def build_spell_fields(self, spell):
        """Build the editable field list for a single spell."""
        from src import data_registry as DR
        FE = FieldEntry

        ev = spell.get("effect_value", {})
        dice = ev.get("dice", "")
        if not dice:
            dc = ev.get("dice_count", "")
            ds = ev.get("dice_sides", "")
            if dc and ds:
                dice = f"{dc}d{ds}"

        fields = [
            # -- Identity --
            FE("-- Identity --", "_hdr1", "", "section", False),
            FE("Name", "name", spell.get("name", "")),
            FE("ID", "id", spell.get("id", "")),
            FE("Description", "description",
               spell.get("description", "")),
            # -- Class & Level --
            FE("-- Class & Level --", "_hdr2", "", "section", False),
            FE("Casting Type", "casting_type",
               spell.get("casting_type", "sorcerer"), "choice"),
            FE("Min Level", "min_level",
               str(spell.get("min_level", 1)), "int"),
            FE("Classes", "allowable_classes",
               ", ".join(spell.get("allowable_classes", []))),
            # -- Cost & Effect --
            FE("-- Cost & Effect --", "_hdr3", "", "section", False),
            FE("MP Cost", "mp_cost",
               str(spell.get("mp_cost", 3)), "int"),
            FE("Effect Type", "effect_type",
               spell.get("effect_type", "damage"), "choice"),
            FE("Dice", "dice", dice),
            FE("Duration", "duration",
               str(spell.get("duration", "instant"))),
            # -- Targeting --
            FE("-- Targeting --", "_hdr4", "", "section", False),
            FE("Targeting", "targeting",
               spell.get("targeting", "select_enemy"), "choice"),
            FE("Range", "range",
               str(spell.get("range", 99)), "int"),
            FE("Usable In", "usable_in",
               ", ".join(spell.get("usable_in", ["battle"]))),
            # -- Visual --
            FE("-- Visual --", "_hdr5", "", "section", False),
            FE("Icon", "icon",
               spell.get("icon", ""), "sprite"),
            # -- Audio --
            FE("-- Audio --", "_hdr6", "", "section", False),
            FE("SFX", "sfx", spell.get("sfx", "")),
            FE("Hit SFX", "hit_sfx",
               spell.get("hit_sfx", "") or ""),
        ]
        self.spell_fields = fields
        idx, buf = self.finalize_fields(fields)
        self.spell_field = idx
        self.spell_scroll_f = 0
        self.spell_buffer = buf

    def resort_spells(self):
        """Re-sort spell list and update cursor to follow the
        previously-selected spell."""
        if not self.spell_list:
            return
        # Remember selected spell by identity
        cur_spell = (self.spell_list[self.spell_cursor]
                     if 0 <= self.spell_cursor
                     < len(self.spell_list) else None)
        from src import data_registry as DR
        type_order = DR.casting_type_sort_order()
        self.spell_list.sort(key=lambda s: (
            type_order.get(s.get("casting_type", "sorcerer"), 2),
            s.get("min_level", 1),
            s.get("name", ""),
        ))
        # Restore cursor
        if cur_spell:
            for i, s in enumerate(self.spell_list):
                if s is cur_spell:
                    self.spell_cursor = i
                    return

    def save_spell_fields(self):
        """Apply edited fields back to the spell dict."""
        if self.spell_cursor >= len(self.spell_list):
            return
        spell = self.spell_list[self.spell_cursor]
        if self.spell_fields:
            entry = self.spell_fields[self.spell_field]
            entry.value = self.spell_buffer
        for entry in self.spell_fields:
            key, val = entry.key, entry.value
            if key == "name":
                spell["name"] = val
            elif key == "id":
                spell["id"] = val
            elif key == "description":
                spell["description"] = val
            elif key == "casting_type":
                spell["casting_type"] = val
            elif key == "min_level":
                try:
                    spell["min_level"] = int(val)
                except ValueError:
                    pass
            elif key == "allowable_classes":
                spell["allowable_classes"] = [
                    c.strip() for c in val.split(",") if c.strip()]
            elif key == "mp_cost":
                try:
                    spell["mp_cost"] = int(val)
                except ValueError:
                    pass
            elif key == "effect_type":
                spell["effect_type"] = val
            elif key == "dice":
                if val:
                    parts = val.split("d")
                    if len(parts) == 2:
                        try:
                            spell.setdefault("effect_value", {})["dice_count"] = int(parts[0])
                            spell["effect_value"]["dice_sides"] = int(parts[1])
                            spell["effect_value"]["dice"] = val
                        except ValueError:
                            pass
            elif key == "duration":
                spell["duration"] = val
            elif key == "targeting":
                spell["targeting"] = val
            elif key == "range":
                try:
                    spell["range"] = int(val)
                except ValueError:
                    pass
            elif key == "usable_in":
                spell["usable_in"] = [
                    c.strip() for c in val.split(",") if c.strip()]
            elif key == "icon":
                spell["icon"] = val
            elif key == "sfx":
                spell["sfx"] = val
            elif key == "hit_sfx":
                spell["hit_sfx"] = val

    def add_spell(self):
        """Add a new blank spell."""
        new_spell = {
            "name": f"New Spell {len(self.spell_list) + 1}",
            "id": f"new_spell_{len(self.spell_list) + 1}",
            "description": "A new spell.",
            "casting_type": "sorcerer",
            "min_level": 1,
            "allowable_classes": [],
            "mp_cost": 3,
            "effect_type": "damage",
            "range": 99,
            "usable_in": ["battle"],
            "icon": "",
            "sfx": "",
        }
        self.spell_list.append(new_spell)
        self.spell_cursor = len(self.spell_list) - 1

    def remove_spell(self):
        """Remove the currently selected spell."""
        if not self.spell_list:
            return
        idx = self.spell_cursor
        if 0 <= idx < len(self.spell_list):
            self.spell_list.pop(idx)
            if self.spell_cursor >= len(self.spell_list):
                self.spell_cursor = max(0, len(self.spell_list) - 1)

    def get_spell_choices(self, key):
        """Return choice options for a spell field."""
        if key == "casting_type":
            from src import data_registry as DR
            return DR.all_casting_types()
        if key == "effect_type":
            return ["damage", "heal", "buff", "debuff"]
        if key == "targeting":
            return ["select_enemy", "select_ally", "all_enemies", "all_allies", "self"]
        return []

    def spell_on_choice_change(self, entry, new_value):
        """Hook called when a choice field changes in spells editor."""
        pass

    def spell_on_save_exit(self):
        """Hook called on save+exit in spells editor."""
        pass

    def spell_on_discard_exit(self):
        """Hook called on discard+exit in spells editor."""
        pass

    def spell_on_clean_exit(self):
        """Hook called on clean exit in spells editor."""
        pass

    # ══════════════════════════════════════════════════════════
    # ── Items Editor Methods ───────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def items_path(self):
        """Path to items.json (module dir first, then default)."""
        if self.game.active_module_path:
            p = os.path.join(self.game.active_module_path, "items.json")
            if os.path.isfile(p):
                return p
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "items.json")

    def load_items(self):
        """Load items from items.json into the editor."""
        path = self.items_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        items = []
        for section in ("weapons", "armors", "general"):
            section_items = data.get(section, {})
            if isinstance(section_items, dict):
                for name, entry in sorted(section_items.items()):
                    items.append({
                        "_name": name,
                        "_section": section,
                        **entry
                    })
        self.item_list = items
        self.item_cursor = 0
        self.item_scroll = 0

    def save_items(self):
        """Write item list back to JSON and reload."""
        path = self.items_path()
        data = {"weapons": {}, "armors": {}, "general": {}}
        for item in self.item_list:
            name = item["_name"]
            section = item["_section"]
            entry = {k: v for k, v in item.items()
                     if not k.startswith("_")}
            data[section][name] = entry
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        try:
            from src.party import reload_module_data as _reload
            _reload(self.game.active_module_path)
        except Exception:
            pass
        return True

    def build_item_fields(self, item):
        """Build editable field list for a single item."""
        FE = FieldEntry
        section = item.get("_section", "general")
        fields = [
            FE("-- Identity --", "_hdr1", "", "section", False),
            FE("Name", "_name", item.get("_name", "")),
            FE("Section", "_section", section, "choice"),
            FE("Description", "description",
               item.get("description", "")),
            FE("Icon", "icon", item.get("icon", ""), "sprite"),
            FE("Item Type", "item_type",
               item.get("item_type", "")),
        ]
        if section == "weapons":
            fields += [
                FE("-- Weapon Stats --", "_hdr2", "", "section", False),
                FE("Power", "power",
                   str(item.get("power", 0)), "int"),
                FE("Ranged", "ranged",
                   str(item.get("ranged", False)), "choice"),
                FE("Melee", "melee",
                   str(item.get("melee", False)), "choice"),
                FE("Throwable", "throwable",
                   str(item.get("throwable", False)), "choice"),
                FE("Slots", "_slots",
                   ", ".join(item.get("slots", []))),
                FE("-- Durability --", "_hdr_dur", "", "section", False),
                FE("Durability", "durability",
                   str(item.get("durability", 0)), "int"),
                FE("Indestructible", "indestructible",
                   str(item.get("indestructible", False)), "choice"),
            ]
        elif section == "armors":
            fields += [
                FE("-- Armor Stats --", "_hdr2", "", "section", False),
                FE("Evasion", "evasion",
                   str(item.get("evasion", 50)), "int"),
                FE("Slots", "_slots",
                   ", ".join(item.get("slots", []))),
                FE("-- Durability --", "_hdr_dur", "", "section", False),
                FE("Durability", "durability",
                   str(item.get("durability", 0)), "int"),
                FE("Indestructible", "indestructible",
                   str(item.get("indestructible", False)), "choice"),
            ]
        else:
            fields += [
                FE("-- General --", "_hdr2", "", "section", False),
                FE("Usable", "usable",
                   str(item.get("usable", False)), "choice"),
                FE("Effect", "effect",
                   item.get("effect", "")),
                FE("Power", "power",
                   str(item.get("power", 0)), "int"),
                FE("Stackable", "stackable",
                   str(item.get("stackable", False)), "choice"),
            ]
        fields += [
            FE("-- Shop --", "_hdr3", "", "section", False),
            FE("Buy Price", "buy",
               str(item.get("buy", 0)), "int"),
            FE("Sell Price", "sell",
               str(item.get("sell", 0)), "int"),
            FE("-- Equip --", "_hdr4", "", "section", False),
            FE("Party Equip", "party_can_equip",
               str(item.get("party_can_equip", False)), "choice"),
            FE("Char Equip", "character_can_equip",
               str(item.get("character_can_equip", False)), "choice"),
        ]
        self.item_fields = fields
        idx, buf = self.finalize_fields(fields)
        self.item_field = idx
        self.item_scroll_f = 0
        self.item_buffer = buf

    def save_item_fields(self):
        """Apply edited fields back to the item dict in memory."""
        if self.item_cursor >= len(self.item_list):
            return
        item = self.item_list[self.item_cursor]
        if self.item_fields:
            entry = self.item_fields[self.item_field]
            entry.value = self.item_buffer
        for entry in self.item_fields:
            key, val = entry.key, entry.value
            if key.startswith("_") and key not in ("_name", "_section",
                                                    "_slots"):
                continue
            if key == "_slots":
                item["slots"] = [s.strip() for s in val.split(",")
                                 if s.strip()]
            elif key in ("power", "evasion", "buy", "sell", "durability"):
                try:
                    item[key] = int(val)
                except ValueError:
                    pass
            elif key in ("ranged", "melee", "throwable", "usable",
                         "stackable", "party_can_equip",
                         "character_can_equip", "indestructible"):
                item[key] = val == "True"
            else:
                item[key] = val

    def get_item_choices(self, key):
        """Return choice options for an item field."""
        if key == "_section":
            return ["weapons", "armors", "general"]
        if key == "icon":
            from src import data_registry as DR
            # Procedural icons always available, plus any manifest
            # sprites the user has tagged with the "items" category
            procedural = DR.all_item_icons()
            tagged = DR.sprites_for_category("items")
            return procedural + tagged
        if key in ("ranged", "melee", "throwable", "usable",
                   "stackable", "party_can_equip",
                   "character_can_equip", "indestructible"):
            return ["True", "False"]
        return []

    def add_item(self):
        """Add a new blank item."""
        new_item = {
            "_name": f"New Item {len(self.item_list) + 1}",
            "_section": "general",
            "description": "A new item.",
            "icon": "tool",
            "item_type": "misc",
            "buy": 10,
            "sell": 5,
            "party_can_equip": False,
            "character_can_equip": False,
        }
        self.item_list.append(new_item)
        self.item_cursor = len(self.item_list) - 1

    def remove_item(self):
        """Remove the currently selected item."""
        if not self.item_list:
            return
        idx = self.item_cursor
        if 0 <= idx < len(self.item_list):
            self.item_list.pop(idx)
            if self.item_cursor >= len(self.item_list):
                self.item_cursor = max(
                    0, len(self.item_list) - 1)

    # ══════════════════════════════════════════════════════════
    # ── Counters Editor Methods ────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def counters_path(self):
        """Path to counters.json (module dir first, then default)."""
        if self.game.active_module_path:
            p = os.path.join(self.game.active_module_path, "counters.json")
            if os.path.isfile(p):
                return p
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "counters.json")

    def load_counters(self):
        """Load counters from counters.json into the editor."""
        path = self.counters_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        counters = []
        for key in sorted(data.keys()):
            entry = data[key]
            counters.append({
                "_key": key,
                "_name": entry.get("name", key),
                "description": entry.get("description", ""),
                "items": list(entry.get("items", [])),
            })
        self.counter_list = counters
        self.counter_cursor = 0
        self.counter_scroll = 0
        self.counter_item_list = []
        self.counter_item_cursor = 0
        self.counter_item_scroll = 0

    def save_counters(self):
        """Write counter list back to JSON."""
        path = self.counters_path()
        data = {}
        for counter in self.counter_list:
            key = counter["_key"]
            data[key] = {
                "name": counter["_name"],
                "description": counter.get("description", ""),
                "items": list(counter.get("items", [])),
            }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        return True

    def build_counter_fields(self, counter):
        """Build editable field list for a single counter type.

        Only includes counter-type settings (name, description).
        Items are managed in a dedicated sub-list at level 3.
        """
        FE = FieldEntry
        n_items = len(counter.get("items", []))
        fields = [
            FE("-- Counter Type --", "_hdr1", "", "section", False),
            FE("Key", "_key", counter.get("_key", ""), "text", False),
            FE("Name", "_name", counter.get("_name", "")),
            FE("Description", "description",
               counter.get("description", "")),
            FE("-- Items for Sale --", "_hdr2", "", "section", False),
            FE(f"Items ({n_items})", "_edit_items",
               "Enter to edit >", "text", True),
        ]
        self.counter_fields = fields
        idx, buf = self.finalize_fields(fields)
        self.counter_field = idx
        self.counter_scroll_f = 0
        self.counter_buffer = buf

    def save_counter_fields(self):
        """Apply edited fields back to the counter dict in memory."""
        if self.counter_cursor >= len(self.counter_list):
            return
        counter = self.counter_list[self.counter_cursor]
        if self.counter_fields:
            entry = self.counter_fields[self.counter_field]
            entry.value = self.counter_buffer
        for entry in self.counter_fields:
            key, val = entry.key, entry.value
            if key.startswith("_"):
                if key == "_name":
                    counter["_name"] = val
                continue
            counter[key] = val

    def get_counter_choices(self, key):
        """Return choice options for a counter field."""
        if key == "_edit_items":
            # Not a real choice — handled by entering the item sub-list
            return []
        return []

    def _get_all_item_names(self):
        """Return a sorted list of all item names from items.json."""
        path = self.items_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        names = []
        for section in ("weapons", "armors", "general"):
            section_items = data.get(section, {})
            if isinstance(section_items, dict):
                names.extend(sorted(section_items.keys()))
        return sorted(set(names))

    def _get_item_info(self, item_name):
        """Return (section, icon, buy_price) for an item name."""
        path = self.items_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        for section in ("weapons", "armors", "general"):
            section_items = data.get(section, {})
            if item_name in section_items:
                entry = section_items[item_name]
                return (section, entry.get("icon", ""),
                        entry.get("buy", 0))
        return ("unknown", "", 0)

    def _load_items_cache(self):
        """Load items data for use by the counter item editor.

        Returns a dict mapping item_name → {section, icon, buy}.
        """
        path = self.items_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        cache = {}
        for section in ("weapons", "armors", "general"):
            for name, entry in data.get(section, {}).items():
                cache[name] = {
                    "section": section,
                    "icon": entry.get("icon", ""),
                    "buy": entry.get("buy", 0),
                }
        return cache

    def counter_open_items(self):
        """Open the item sub-list for the selected counter (enters level 3)."""
        if self.counter_cursor >= len(self.counter_list):
            return
        counter = self.counter_list[self.counter_cursor]
        self.counter_item_list = list(counter.get("items", []))
        self.counter_item_cursor = 0
        self.counter_item_scroll = 0
        self._counter_items_cache = self._load_items_cache()
        self._counter_all_items = self._get_all_item_names()
        self.level = 3

    def counter_save_items(self):
        """Save the item sub-list back to the counter dict."""
        if self.counter_cursor >= len(self.counter_list):
            return
        counter = self.counter_list[self.counter_cursor]
        counter["items"] = list(self.counter_item_list)

    def add_counter(self):
        """Add a new blank counter type."""
        key = f"custom_{len(self.counter_list) + 1}"
        new_counter = {
            "_key": key,
            "_name": f"New Counter {len(self.counter_list) + 1}",
            "description": "A new shop counter.",
            "items": [],
        }
        self.counter_list.append(new_counter)
        self.counter_cursor = len(self.counter_list) - 1

    def remove_counter(self):
        """Remove the currently selected counter type."""
        if not self.counter_list:
            return
        idx = self.counter_cursor
        if 0 <= idx < len(self.counter_list):
            self.counter_list.pop(idx)
            if self.counter_cursor >= len(self.counter_list):
                self.counter_cursor = max(
                    0, len(self.counter_list) - 1)

    def counter_add_item(self):
        """Add a new item to the counter's item list (first available item)."""
        all_items = getattr(self, '_counter_all_items', None)
        if not all_items:
            all_items = self._get_all_item_names()
            self._counter_all_items = all_items
        if all_items:
            self.counter_item_list.append(all_items[0])
            self.counter_item_cursor = len(self.counter_item_list) - 1
            self.counter_save_items()
            self.dirty = True

    def counter_remove_item(self):
        """Remove the currently selected item from the counter's list."""
        if not self.counter_item_list:
            return
        idx = self.counter_item_cursor
        if 0 <= idx < len(self.counter_item_list):
            self.counter_item_list.pop(idx)
            if self.counter_item_cursor >= len(self.counter_item_list):
                self.counter_item_cursor = max(
                    0, len(self.counter_item_list) - 1)
            self.counter_save_items()
            self.dirty = True

    def counter_cycle_item(self, direction=1):
        """Cycle the currently selected item through all available items."""
        if not self.counter_item_list:
            return
        idx = self.counter_item_cursor
        if idx < 0 or idx >= len(self.counter_item_list):
            return
        all_items = getattr(self, '_counter_all_items', None)
        if not all_items:
            all_items = self._get_all_item_names()
            self._counter_all_items = all_items
        if not all_items:
            return
        current = self.counter_item_list[idx]
        try:
            ci = all_items.index(current)
        except ValueError:
            ci = 0
        ci = (ci + direction) % len(all_items)
        self.counter_item_list[idx] = all_items[ci]
        self.counter_save_items()
        self.dirty = True

    def _handle_counter_items_input(self, event):
        """Handle input for the counter item sub-list (level 3)."""
        items = self.counter_item_list
        n = len(items)

        if self._is_save_shortcut(event):
            self.counter_save_items()
            self.save_counters()
            self.dirty = False
            return

        if event.key == pygame.K_ESCAPE:
            self.counter_save_items()
            # Rebuild the counter fields to update the item count
            if self.counter_cursor < len(self.counter_list):
                self.build_counter_fields(
                    self.counter_list[self.counter_cursor])
            self.level = 2
            return

        if event.key == pygame.K_UP and n > 0:
            self.counter_item_cursor = (
                self.counter_item_cursor - 1) % n
            self.counter_item_scroll = self._adjust_scroll_generic(
                self.counter_item_cursor, self.counter_item_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self.counter_item_cursor = (
                self.counter_item_cursor + 1) % n
            self.counter_item_scroll = self._adjust_scroll_generic(
                self.counter_item_cursor, self.counter_item_scroll)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            # Cycle the selected item through all available items
            if n > 0:
                direction = 1 if event.key == pygame.K_RIGHT else -1
                self.counter_cycle_item(direction)
        elif self._is_new_shortcut(event):
            self.counter_add_item()
            self.counter_item_scroll = self._adjust_scroll_generic(
                self.counter_item_cursor, self.counter_item_scroll)
        elif self._is_delete_shortcut(event):
            self.counter_remove_item()

    # ══════════════════════════════════════════════════════════
    # ── Monsters Editor Methods ────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def monsters_path(self):
        """Path to monsters.json (module dir first, then default)."""
        if self.game.active_module_path:
            p = os.path.join(self.game.active_module_path, "monsters.json")
            if os.path.isfile(p):
                return p
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "monsters.json")

    def load_monsters(self):
        """Load monsters from monsters.json into the editor."""
        path = self.monsters_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        monsters = []
        for name, entry in sorted(
                data.get("monsters", {}).items()):
            monsters.append({"_name": name, **entry})
        self.mon_list = monsters
        self.mon_cursor = 0
        self.mon_scroll = 0
        # Stash spawn_tables so we can preserve them on save
        self.mon_spawn_tables = data.get("spawn_tables", {})

    def save_monsters(self):
        """Write monster list back to JSON and reload."""
        path = self.monsters_path()
        monsters = {}
        for mon in self.mon_list:
            name = mon["_name"]
            entry = {k: v for k, v in mon.items()
                     if not k.startswith("_")}
            monsters[name] = entry
        data = {
            "monsters": monsters,
            "spawn_tables": getattr(self, "mon_spawn_tables", {}),
        }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        try:
            from src.monster import reload_module_data as _reload
            _reload(self.game.active_module_path)
        except Exception:
            pass
        return True

    # ── Spell helper utilities for the monster editor ──

    @staticmethod
    def _spell_val(mon, spell_type, key, default):
        """Return a value from an existing spell entry, or *default*."""
        for s in (mon.get("spells") or []):
            if s.get("type") == spell_type:
                return s.get(key, default)
        return default

    # Wizard spell templates by level (1-5).  Each level provides a
    # sleep + curse pair with scaled stats.
    _WIZARD_LEVELS = {
        1: {"sleep": {"save_dc": 10, "duration": 2, "max_target_hp": 20,
                       "cast_chance": 25, "range": 5},
            "curse": {"duration": 2, "ac_penalty": 1, "attack_penalty": 1,
                      "cast_chance": 20, "range": 5}},
        2: {"sleep": {"save_dc": 12, "duration": 3, "max_target_hp": 25,
                       "cast_chance": 30, "range": 6},
            "curse": {"duration": 3, "ac_penalty": 2, "attack_penalty": 2,
                      "cast_chance": 25, "range": 6}},
        3: {"sleep": {"save_dc": 14, "duration": 3, "max_target_hp": 35,
                       "cast_chance": 35, "range": 7},
            "curse": {"duration": 4, "ac_penalty": 3, "attack_penalty": 3,
                      "cast_chance": 30, "range": 7}},
        4: {"sleep": {"save_dc": 16, "duration": 4, "max_target_hp": 50,
                       "cast_chance": 40, "range": 8},
            "curse": {"duration": 5, "ac_penalty": 4, "attack_penalty": 3,
                      "cast_chance": 35, "range": 8}},
        5: {"sleep": {"save_dc": 18, "duration": 5, "max_target_hp": 70,
                       "cast_chance": 45, "range": 9},
            "curse": {"duration": 6, "ac_penalty": 5, "attack_penalty": 4,
                      "cast_chance": 40, "range": 9}},
    }

    # Healer spell templates by level (1-5).
    _HEALER_LEVELS = {
        1: {"heal_self": {"heal_dice": 1, "heal_sides": 4, "heal_bonus": 0,
                          "cast_chance": 35},
            "heal_ally": {"heal_dice": 1, "heal_sides": 4, "heal_bonus": 0,
                          "cast_chance": 30, "range": 4}},
        2: {"heal_self": {"heal_dice": 1, "heal_sides": 6, "heal_bonus": 1,
                          "cast_chance": 40},
            "heal_ally": {"heal_dice": 1, "heal_sides": 6, "heal_bonus": 1,
                          "cast_chance": 35, "range": 5}},
        3: {"heal_self": {"heal_dice": 1, "heal_sides": 8, "heal_bonus": 2,
                          "cast_chance": 40},
            "heal_ally": {"heal_dice": 1, "heal_sides": 8, "heal_bonus": 2,
                          "cast_chance": 40, "range": 6}},
        4: {"heal_self": {"heal_dice": 2, "heal_sides": 6, "heal_bonus": 2,
                          "cast_chance": 45},
            "heal_ally": {"heal_dice": 2, "heal_sides": 6, "heal_bonus": 2,
                          "cast_chance": 45, "range": 7}},
        5: {"heal_self": {"heal_dice": 2, "heal_sides": 8, "heal_bonus": 3,
                          "cast_chance": 50},
            "heal_ally": {"heal_dice": 2, "heal_sides": 8, "heal_bonus": 3,
                          "cast_chance": 50, "range": 8}},
    }

    @classmethod
    def _wizard_level_from_spells(cls, mon):
        """Infer wizard level from existing sleep/curse spell stats."""
        for s in (mon.get("spells") or []):
            if s.get("type") == "sleep":
                dc = s.get("save_dc", 10)
                for lvl in (5, 4, 3, 2, 1):
                    if dc >= cls._WIZARD_LEVELS[lvl]["sleep"]["save_dc"]:
                        return lvl
        return 2  # default

    @classmethod
    def _healer_level_from_spells(cls, mon):
        """Infer healer level from existing heal spell stats."""
        for s in (mon.get("spells") or []):
            if s.get("type") in ("heal_self", "heal_ally"):
                dice = s.get("heal_dice", 1)
                sides = s.get("heal_sides", 4)
                for lvl in (5, 4, 3, 2, 1):
                    t = cls._HEALER_LEVELS[lvl].get(s["type"], {})
                    if dice >= t.get("heal_dice", 1) and sides >= t.get("heal_sides", 4):
                        return lvl
        return 2  # default

    def build_mon_fields(self, mon):
        """Build editable field list for a single monster."""
        FE = FieldEntry
        color = mon.get("color", [200, 50, 50])
        color_str = f"{color[0]}, {color[1]}, {color[2]}" \
            if isinstance(color, (list, tuple)) else str(color)
        # ── Unpack on-hit effects from list into flat fields ──
        on_hit = {}
        for eff in (mon.get("on_hit_effects") or []):
            on_hit[eff.get("type", "")] = eff

        # ── Unpack passives from list into flat fields ──
        passive_map = {}
        for p in (mon.get("passives") or []):
            passive_map[p.get("type", "")] = p

        fields = [
            FE("-- Identity --", "_hdr1", "", "section", False),
            FE("Name", "_name", mon.get("_name", "")),
            FE("Description", "description",
               mon.get("description", "")),
            FE("Tile", "tile", mon.get("tile", ""), "sprite"),
            FE("Color (R,G,B)", "_color", color_str),
            FE("-- Combat Stats --", "_hdr2", "", "section", False),
            FE("Battle Scale", "battle_scale",
               str(mon.get("battle_scale", 1)) + "x", "choice"),
            FE("HP", "hp", str(mon.get("hp", 10)), "int"),
            FE("AC", "ac", str(mon.get("ac", 10)), "int"),
            FE("Attack Bonus", "attack_bonus",
               str(mon.get("attack_bonus", 1)), "int"),
            FE("Damage Dice", "damage_dice",
               str(mon.get("damage_dice", 1)), "int"),
            FE("Damage Sides", "damage_sides",
               str(mon.get("damage_sides", 4)), "int"),
            FE("Damage Bonus", "damage_bonus",
               str(mon.get("damage_bonus", 0)), "int"),
            FE("-- Movement --", "_hdr_move", "", "section", False),
            FE("Move Range", "move_range",
               str(mon.get("move_range", 1)), "int"),
            FE("Post-Atk Move", "post_attack_move",
               str(mon.get("post_attack_move", 0)), "int"),
            FE("-- Rewards --", "_hdr3", "", "section", False),
            FE("XP Reward", "xp_reward",
               str(mon.get("xp_reward", 25)), "int"),
            FE("Gold Min", "gold_min",
               str(mon.get("gold_min", 5)), "int"),
            FE("Gold Max", "gold_max",
               str(mon.get("gold_max", 15)), "int"),
            FE("Spawn Weight", "spawn_weight",
               str(mon.get("spawn_weight", 20)), "int"),
            FE("-- Flags --", "_hdr4", "", "section", False),
            FE("Undead", "undead",
               str(mon.get("undead", False)), "choice"),
            FE("Humanoid", "humanoid",
               str(mon.get("humanoid", False)), "choice"),
            FE("Terrain", "terrain",
               mon.get("terrain", "land"), "choice"),
            FE("-- Abilities --", "_hdr_abilities", "", "section", False),
            FE("Breath Fire", "_sp_breath_fire",
               str(any(s.get("type") == "breath_fire"
                       for s in (mon.get("spells") or []))), "choice"),
            FE("  Cast Chance %", "_sp_bf_chance",
               str(self._spell_val(mon, "breath_fire",
                                   "cast_chance", 30)), "int"),
            FE("  Range", "_sp_bf_range",
               str(self._spell_val(mon, "breath_fire", "range", 4)),
               "int"),
            FE("  Dmg Dice", "_sp_bf_dice",
               str(self._spell_val(mon, "breath_fire",
                                   "damage_dice", 3)), "int"),
            FE("  Dmg Sides", "_sp_bf_sides",
               str(self._spell_val(mon, "breath_fire",
                                   "damage_sides", 6)), "int"),
            FE("  Save DC", "_sp_bf_dc",
               str(self._spell_val(mon, "breath_fire",
                                   "save_dc", 13)), "int"),
            FE("Wizard Spells", "_sp_wizard",
               str(any(s.get("type") in ("sleep", "curse")
                       for s in (mon.get("spells") or []))), "choice"),
            FE("  Spell Level", "_sp_wiz_level",
               str(self._wizard_level_from_spells(mon)), "choice"),
            FE("Healer Spells", "_sp_healer",
               str(any(s.get("type") in ("heal_self", "heal_ally")
                       for s in (mon.get("spells") or []))), "choice"),
            FE("  Healer Level", "_sp_heal_level",
               str(self._healer_level_from_spells(mon)), "choice"),
            FE("Poison Spell", "_sp_poison",
               str(any(s.get("type") == "poison"
                       for s in (mon.get("spells") or []))), "choice"),
            FE("  Cast Chance %", "_sp_poi_chance",
               str(self._spell_val(mon, "poison",
                                   "cast_chance", 30)), "int"),
            FE("  Save DC", "_sp_poi_dc",
               str(self._spell_val(mon, "poison", "save_dc", 11)),
               "int"),
            FE("  Dmg/Turn", "_sp_poi_dpt",
               str(self._spell_val(mon, "poison",
                                   "damage_per_turn", 2)), "int"),
            FE("  Duration", "_sp_poi_dur",
               str(self._spell_val(mon, "poison", "duration", 4)),
               "int"),
            FE("-- On-Hit Effects --", "_hdr_onhit", "", "section", False),
            FE("Poison On Hit", "_oh_poison",
               str("poison" in on_hit), "choice"),
            FE("  Chance %", "_oh_poison_chance",
               str(on_hit.get("poison", {}).get("chance", 30)), "int"),
            FE("  Dmg/Turn", "_oh_poison_dpt",
               str(on_hit.get("poison", {}).get("damage_per_turn", 2)),
               "int"),
            FE("  Duration", "_oh_poison_dur",
               str(on_hit.get("poison", {}).get("duration", 3)), "int"),
            FE("Stun On Hit", "_oh_stun",
               str("stun" in on_hit), "choice"),
            FE("  Chance %", "_oh_stun_chance",
               str(on_hit.get("stun", {}).get("chance", 20)), "int"),
            FE("  Duration", "_oh_stun_dur",
               str(on_hit.get("stun", {}).get("duration", 1)), "int"),
            FE("Slow On Hit", "_oh_slow",
               str("slow" in on_hit), "choice"),
            FE("  Chance %", "_oh_slow_chance",
               str(on_hit.get("slow", {}).get("chance", 25)), "int"),
            FE("  Duration", "_oh_slow_dur",
               str(on_hit.get("slow", {}).get("duration", 2)), "int"),
            FE("Drain On Hit", "_oh_drain",
               str("drain" in on_hit), "choice"),
            FE("  Chance %", "_oh_drain_chance",
               str(on_hit.get("drain", {}).get("chance", 25)), "int"),
            FE("  Amount", "_oh_drain_amt",
               str(on_hit.get("drain", {}).get("amount", 3)), "int"),
            FE("-- Passives --", "_hdr_passives", "", "section", False),
            FE("Regen/Turn", "_pas_regen",
               str(passive_map.get("regen", {}).get("amount", 0)),
               "int"),
            FE("Fire Resist", "_pas_fire_res",
               str("fire_resistance" in passive_map), "choice"),
            FE("Ice Resist", "_pas_ice_res",
               str("ice_resistance" in passive_map), "choice"),
            FE("Poison Immune", "_pas_poison_imm",
               str("poison_immunity" in passive_map), "choice"),
        ]
        self.mon_fields = fields
        idx, buf = self.finalize_fields(fields)
        self.mon_field = idx
        self.mon_scroll_f = 0
        self.mon_buffer = buf

    def save_mon_fields(self):
        """Apply edited fields back to the monster dict."""
        if self.mon_cursor >= len(self.mon_list):
            return
        mon = self.mon_list[self.mon_cursor]
        if self.mon_fields:
            entry = self.mon_fields[self.mon_field]
            entry.value = self.mon_buffer

        # ── Collect all field values into a lookup dict ──
        fvals = {}
        for entry in self.mon_fields:
            fvals[entry.key] = entry.value

        # ── Standard flat fields ──
        for entry in self.mon_fields:
            key, val = entry.key, entry.value
            if key.startswith("_") and key not in ("_name", "_color"):
                continue
            if key == "_name":
                new_name = val.strip()
                if new_name:
                    mon["_name"] = new_name
            elif key == "_color":
                try:
                    parts = [int(p.strip()) for p in val.split(",")]
                    if len(parts) == 3:
                        mon["color"] = parts
                except ValueError:
                    pass
            elif key == "battle_scale":
                try:
                    mon[key] = int(val.rstrip("x"))
                except ValueError:
                    mon[key] = 1
            elif key in ("hp", "ac", "attack_bonus", "damage_dice",
                         "damage_sides", "damage_bonus", "xp_reward",
                         "gold_min", "gold_max", "spawn_weight",
                         "move_range", "post_attack_move"):
                try:
                    mon[key] = int(val)
                except ValueError:
                    pass
            elif key in ("undead", "humanoid"):
                mon[key] = val == "True"
            elif not key.startswith("_"):
                mon[key] = val

        # ── Rebuild spells list from ability fields ──
        spells = []
        if fvals.get("_sp_breath_fire") == "True":
            spells.append({
                "type": "breath_fire",
                "name": "Fire Breath",
                "cast_chance": int(fvals.get("_sp_bf_chance", "30")),
                "range": int(fvals.get("_sp_bf_range", "4")),
                "damage_dice": int(fvals.get("_sp_bf_dice", "3")),
                "damage_sides": int(fvals.get("_sp_bf_sides", "6")),
                "damage_bonus": 0,
                "save_dc": int(fvals.get("_sp_bf_dc", "13")),
            })
        if fvals.get("_sp_wizard") == "True":
            lvl = int(fvals.get("_sp_wiz_level", "2"))
            lvl = max(1, min(5, lvl))
            wt = self._WIZARD_LEVELS[lvl]
            sl = wt["sleep"]
            spells.append({
                "type": "sleep", "name": "Dark Slumber",
                "range": sl["range"], "cast_chance": sl["cast_chance"],
                "save_dc": sl["save_dc"], "duration": sl["duration"],
                "max_target_hp": sl["max_target_hp"],
            })
            cu = wt["curse"]
            spells.append({
                "type": "curse", "name": "Hex",
                "range": cu["range"], "cast_chance": cu["cast_chance"],
                "duration": cu["duration"],
                "ac_penalty": cu["ac_penalty"],
                "attack_penalty": cu["attack_penalty"],
            })
        if fvals.get("_sp_healer") == "True":
            lvl = int(fvals.get("_sp_heal_level", "2"))
            lvl = max(1, min(5, lvl))
            ht = self._HEALER_LEVELS[lvl]
            hs = ht["heal_self"]
            spells.append({
                "type": "heal_self", "name": "Self Heal",
                "cast_chance": hs["cast_chance"],
                "heal_dice": hs["heal_dice"],
                "heal_sides": hs["heal_sides"],
                "heal_bonus": hs["heal_bonus"],
            })
            ha = ht["heal_ally"]
            spells.append({
                "type": "heal_ally", "name": "Mend Wounds",
                "range": ha["range"], "cast_chance": ha["cast_chance"],
                "heal_dice": ha["heal_dice"],
                "heal_sides": ha["heal_sides"],
                "heal_bonus": ha["heal_bonus"],
            })
        if fvals.get("_sp_poison") == "True":
            spells.append({
                "type": "poison", "name": "Poison",
                "range": 5,
                "cast_chance": int(fvals.get("_sp_poi_chance", "30")),
                "save_dc": int(fvals.get("_sp_poi_dc", "11")),
                "damage_per_turn": int(fvals.get("_sp_poi_dpt", "2")),
                "duration": int(fvals.get("_sp_poi_dur", "4")),
            })
        mon["spells"] = spells if spells else None

        # ── Rebuild on_hit_effects list from flat _oh_ fields ──
        on_hit = []
        if fvals.get("_oh_poison") == "True":
            on_hit.append({
                "type": "poison",
                "chance": int(fvals.get("_oh_poison_chance", "30")),
                "damage_per_turn": int(fvals.get("_oh_poison_dpt", "2")),
                "duration": int(fvals.get("_oh_poison_dur", "3")),
            })
        if fvals.get("_oh_stun") == "True":
            on_hit.append({
                "type": "stun",
                "chance": int(fvals.get("_oh_stun_chance", "20")),
                "duration": int(fvals.get("_oh_stun_dur", "1")),
            })
        if fvals.get("_oh_slow") == "True":
            on_hit.append({
                "type": "slow",
                "chance": int(fvals.get("_oh_slow_chance", "25")),
                "duration": int(fvals.get("_oh_slow_dur", "2")),
            })
        if fvals.get("_oh_drain") == "True":
            on_hit.append({
                "type": "drain",
                "chance": int(fvals.get("_oh_drain_chance", "25")),
                "amount": int(fvals.get("_oh_drain_amt", "3")),
            })
        mon["on_hit_effects"] = on_hit if on_hit else None

        # ── Rebuild passives list from flat _pas_ fields ──
        passives = []
        regen_amt = int(fvals.get("_pas_regen", "0"))
        if regen_amt > 0:
            passives.append({"type": "regen", "amount": regen_amt})
        if fvals.get("_pas_fire_res") == "True":
            passives.append({"type": "fire_resistance"})
        if fvals.get("_pas_ice_res") == "True":
            passives.append({"type": "ice_resistance"})
        if fvals.get("_pas_poison_imm") == "True":
            passives.append({"type": "poison_immunity"})
        mon["passives"] = passives if passives else None

    def get_mon_choices(self, key):
        """Return choice options for a monster field."""
        if key == "tile":
            from src import data_registry as DR
            # All sprites tagged with the "monsters" category
            return DR.sprites_for_category("monsters")
        if key in ("undead", "humanoid"):
            return ["True", "False"]
        if key in ("_oh_poison", "_oh_stun", "_oh_slow", "_oh_drain",
                    "_pas_fire_res", "_pas_ice_res", "_pas_poison_imm",
                    "_sp_breath_fire", "_sp_wizard", "_sp_healer",
                    "_sp_poison"):
            return ["True", "False"]
        if key in ("_sp_wiz_level", "_sp_heal_level"):
            return ["1", "2", "3", "4", "5"]
        if key == "terrain":
            return ["land", "sea"]
        if key == "battle_scale":
            return ["1x", "2x", "3x", "4x"]
        return []

    def add_monster(self):
        """Add a new blank monster."""
        new_mon = {
            "_name": f"New Monster {len(self.mon_list) + 1}",
            "description": "A new creature.",
            "hp": 10,
            "ac": 10,
            "attack_bonus": 1,
            "damage_dice": 1,
            "damage_sides": 4,
            "damage_bonus": 0,
            "xp_reward": 20,
            "gold_min": 3,
            "gold_max": 10,
            "color": [200, 50, 50],
            "spawn_weight": 20,
            "undead": False,
            "humanoid": False,
            "terrain": "land",
            "tile": "",
        }
        self.mon_list.append(new_mon)
        self.mon_cursor = len(self.mon_list) - 1

    def remove_monster(self):
        """Remove the currently selected monster."""
        if not self.mon_list:
            return
        idx = self.mon_cursor
        if 0 <= idx < len(self.mon_list):
            self.mon_list.pop(idx)
            if self.mon_cursor >= len(self.mon_list):
                self.mon_cursor = max(
                    0, len(self.mon_list) - 1)

    # ══════════════════════════════════════════════════════════
    # ── Gallery Editor Methods ────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def load_gallery(self):
        """Load all manifest sprites into a flat list for browsing.

        Each entry includes a ``usable_in`` list and a ``rendering``
        note indicating how the game uses it.
        """
        mpath = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            manifest = {}

        all_cats = ("overworld", "town", "dungeon", "people",
                    "monsters", "objects", "unique_tiles",
                    "items", "unassigned")
        entries = []
        for cat in all_cats:
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for name in sorted(section.keys()):
                entry = section[name]
                if not (isinstance(entry, dict) and "path" in entry):
                    continue
                if "usable_in" in entry:
                    usable = list(entry["usable_in"])
                else:
                    usable = [cat]
                rendering = self._GALLERY_RENDER_MODE.get(
                    (cat, name), "sprite")
                # Hide purely procedural tiles (no meaningful sprite)
                if rendering == "procedural":
                    continue
                entries.append({
                    "category": cat,
                    "name": name,
                    "path": entry["path"],
                    "tile_id": entry.get("tile_id"),
                    "usable_in": sorted(usable),
                    "rendering": rendering,
                })

        self.gallery_list = entries
        self.gallery_cat_cursor = 0
        self.gallery_cat_scroll = 0
        self._rebuild_gallery_cats()

    def _rebuild_gallery_cats(self):
        """Rebuild the category folder list with sprite counts."""
        cats = []
        for cat in self.gallery_all_cats:
            count = sum(1 for e in self.gallery_list
                        if cat in e.get("usable_in", []))
            cats.append({"name": cat, "label": cat.replace("_", " ").title(),
                         "count": count})
        self.gallery_cat_list = cats

    def gallery_enter_cat(self):
        """Enter the selected category folder — build sprite list."""
        if self.gallery_cat_cursor >= len(self.gallery_cat_list):
            return
        cat = self.gallery_cat_list[
            self.gallery_cat_cursor]["name"]
        sprites = []
        for gi, entry in enumerate(self.gallery_list):
            if cat in entry.get("usable_in", []):
                sprites.append(gi)
        self.gallery_sprites = sprites
        self.gallery_spr_cursor = 0
        self.gallery_spr_scroll = 0

    def save_gallery(self):
        """Persist usable_in changes back to tile_manifest.json.

        For each gallery entry, if the user added or removed a category
        from usable_in, we store the custom list in a ``usable_in``
        key inside the manifest entry so it survives reloads.
        """
        mpath = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return False

        for entry in self.gallery_list:
            cat = entry["category"]
            name = entry["name"]
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            mentry = section.get(name)
            if isinstance(mentry, dict):
                mentry["usable_in"] = entry.get("usable_in", [])

        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            return False
        return True

    def gallery_cur_gi(self):
        """Get current gallery index from sprites list."""
        if self.gallery_sprites and 0 <= self.gallery_spr_cursor < len(self.gallery_sprites):
            return self.gallery_sprites[self.gallery_spr_cursor]
        return None

    def gallery_toggle_tag(self):
        """Toggle the current tag for the selected sprite."""
        gi = self.gallery_cur_gi()
        if gi is None:
            return
        entry = self.gallery_list[gi]
        tag = self.gallery_all_cats[self.gallery_tag_cursor]
        if tag in entry.get("usable_in", []):
            entry["usable_in"].remove(tag)
        else:
            entry["usable_in"].append(tag)
        entry["usable_in"] = sorted(entry["usable_in"])
        # Rebuild category counts and reload sprites
        self._rebuild_gallery_cats()
        self.game.renderer.reload_sprites()

    def gallery_duplicate(self):
        """Duplicate the selected sprite in the gallery.

        Copies the sprite PNG file, adds a new manifest entry, and
        refreshes the gallery view so the duplicate is immediately
        visible and editable.
        """
        import copy, shutil
        gi = self.gallery_cur_gi()
        if gi is None:
            return
        src = self.gallery_list[gi]
        base_name = src["name"]
        cat = src["category"]

        # ── Pick a unique name ──
        existing_names = {e["name"] for e in self.gallery_list}
        new_name = f"{base_name}_copy"
        counter = 2
        while new_name in existing_names:
            new_name = f"{base_name}_copy{counter}"
            counter += 1

        # ── Copy the PNG file ──
        root = os.path.dirname(os.path.dirname(__file__))
        src_path = os.path.join(root, src["path"])
        if os.path.isfile(src_path):
            ext = os.path.splitext(src_path)[1]
            dst_dir = os.path.dirname(src_path)
            dst_path = os.path.join(dst_dir, f"{new_name}{ext}")
            shutil.copy2(src_path, dst_path)
            new_rel_path = os.path.relpath(dst_path, root)
        else:
            new_rel_path = src["path"]

        # ── Add manifest entry ──
        mpath = os.path.join(root, "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            manifest = {}
        section = manifest.setdefault(cat, {})
        section[new_name] = {
            "path": new_rel_path,
            "usable_in": list(src.get("usable_in", [cat])),
        }
        # Copy tile_id if present (assign new unique id)
        if src.get("tile_id") is not None:
            all_ids = set()
            for sec in manifest.values():
                if isinstance(sec, dict):
                    for entry in sec.values():
                        if isinstance(entry, dict) and "tile_id" in entry:
                            all_ids.add(entry["tile_id"])
            new_tid = max(all_ids) + 1 if all_ids else 100
            section[new_name]["tile_id"] = new_tid
        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            pass

        # ── Add gallery list entry ──
        dup = copy.deepcopy(src)
        dup["name"] = new_name
        dup["path"] = new_rel_path
        if "tile_id" in section[new_name]:
            dup["tile_id"] = section[new_name]["tile_id"]
        self.gallery_list.append(dup)

        # ── Refresh view and reload sprites ──
        self._rebuild_gallery_cats()
        self.gallery_enter_cat()
        self.gallery_spr_cursor = max(0, len(self.gallery_sprites) - 1)
        self.gallery_spr_scroll = self._adjust_scroll_generic(
            self.gallery_spr_cursor, self.gallery_spr_scroll)
        self.game.renderer.reload_sprites()

    def gallery_delete(self):
        """Delete the selected sprite from the gallery (mark as unassigned)."""
        gi = self.gallery_cur_gi()
        if gi is None:
            return
        entry = self.gallery_list[gi]
        entry["usable_in"] = ["unassigned"]
        # Persist to manifest, rebuild the filtered view, and reload sprites
        self.save_gallery()
        self._rebuild_gallery_cats()
        self.gallery_enter_cat()
        # Keep cursor in bounds after removal from the current category
        n = len(self.gallery_sprites)
        if n > 0:
            self.gallery_spr_cursor = min(self.gallery_spr_cursor, n - 1)
        else:
            self.gallery_spr_cursor = 0
        self.gallery_spr_scroll = self._adjust_scroll_generic(
            self.gallery_spr_cursor, self.gallery_spr_scroll)
        self.game.renderer.reload_sprites()

    def gallery_rename(self, new_name):
        """Rename the selected gallery sprite."""
        gi = self.gallery_cur_gi()
        if gi is None:
            return
        entry = self.gallery_list[gi]
        # Update manifest too
        mpath = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return
        cat = entry["category"]
        old_name = entry["name"]
        section = manifest.get(cat, {})
        if isinstance(section, dict) and old_name in section:
            mentry = section[old_name]
            section[new_name] = mentry
            del section[old_name]
        entry["name"] = new_name
        # Save back
        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            pass
        # Rebuild category counts and reload sprites
        self._rebuild_gallery_cats()
        self.game.renderer.reload_sprites()

    def handle_gallery_naming_input(self, event):
        """Handle text input while renaming a gallery sprite."""
        if event.key == pygame.K_RETURN:
            new_name = self.gallery_name_buf.strip()
            # Sanitize: replace spaces with underscores, lowercase
            new_name = new_name.replace(" ", "_").lower()
            if new_name:
                self.gallery_rename(new_name)
            self.gallery_naming = False
            self.gallery_name_buf = ""
        elif event.key == pygame.K_ESCAPE:
            self.gallery_naming = False
            self.gallery_name_buf = ""
        elif event.key == pygame.K_BACKSPACE:
            self.gallery_name_buf = self.gallery_name_buf[:-1]
        else:
            ch = event.unicode
            if ch and ch.isprintable() and len(self.gallery_name_buf) < 40:
                self.gallery_name_buf += ch

    # ══════════════════════════════════════════════════════════
    # ── Pixel Editor Methods ───────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def pxedit_open(self):
        """Open the pixel editor for the currently selected gallery sprite."""
        gi = self.gallery_cur_gi()
        if gi is None:
            return False
        entry = self.gallery_list[gi]
        sprite_path = entry.get("path", "")
        # Load sprite pixels
        try:
            import pygame
            surf = pygame.image.load(sprite_path)
            w, h = surf.get_size()
            self.pxedit_w = w
            self.pxedit_h = h
            # Convert surface to RGBA pixel array
            pixels = []
            for y in range(h):
                row = []
                for x in range(w):
                    color = surf.get_at((x, y))
                    row.append(tuple(color))
                pixels.append(row)
            self.pxedit_pixels = pixels
            self.pxedit_cx = 0
            self.pxedit_cy = 0
            self.pxedit_color_idx = 0
            self.pxedit_path = sprite_path
            self.pxedit_undo_stack = []
            self.pxedit_painting = False
            self.pxedit_replacing = False
            return True
        except Exception:
            return False

    def pxedit_save(self):
        """Save the pixel editor canvas back to the sprite file."""
        if self.pxedit_pixels is None:
            return
        try:
            import pygame
            w, h = self.pxedit_w, self.pxedit_h
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for y in range(h):
                for x in range(w):
                    color = self.pxedit_pixels[y][x]
                    surf.set_at((x, y), color)
            pygame.image.save(surf, self.pxedit_path)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # ── Map Editor Hub Methods ────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def map_templates_path(self):
        """Return path to map_templates.json."""
        if self.game.active_module_path:
            mod_path = os.path.join(
                self.game.active_module_path, "map_templates.json")
            if os.path.isfile(mod_path):
                return mod_path
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "map_templates.json")

    def save_map_templates(self):
        """Persist all map template data to map_templates.json.

        Walks the top-level sections, collecting every template folder
        (skipping the Tiles folder and editor redirects) into a flat
        list grouped by category folder key.
        """
        from src.map_editor import STORAGE_DENSE, STORAGE_SPARSE
        top_sections = self._meh_top_sections()
        data = {}
        for sec in top_sections:
            folder_key = sec.get("folder", "")
            if folder_key == "me_tiles":
                continue  # Tiles folder is not a template container
            children = sec.get("children", [])
            templates = []
            for child in children:
                # Each child is now a template folder
                if child.get("folder") != "template":
                    continue
                mc = child.get("map_config")
                if not mc:
                    continue
                entry = {
                    "label": child.get("label", ""),
                    "subtitle": child.get("subtitle", ""),
                    "description": child.get("description", ""),
                    "canvas_type": child.get("canvas_type", "blank"),
                    "map_config": {
                        "storage": ("dense" if mc.get("storage") == STORAGE_DENSE
                                    else "sparse"),
                        "grid_type": str(mc.get("grid_type", "fixed")),
                        "tile_context": mc.get("tile_context", "dungeon"),
                        "width": mc.get("width", 12),
                        "height": mc.get("height", 10),
                    },
                }
                # Persist tile data if present
                tiles = child.get("tiles")
                if tiles is not None:
                    entry["tiles"] = tiles
                templates.append(entry)
            data[folder_key] = templates

        path = self.map_templates_path()
        # Ensure parent directory exists (for module paths)
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError:
                pass
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        return True

    def load_map_templates(self):
        """Load saved map template data from map_templates.json.

        Returns a dict keyed by folder_key (e.g. 'me_overview') with
        lists of template dicts, or an empty dict if no file exists.
        """
        path = self.map_templates_path()
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _meh_top_sections(self):
        """Return the top-level sections list.

        If we're inside a folder, walk back through the nav stack
        to get the root list. Otherwise return meh_sections directly.
        """
        if not self.meh_nav_stack:
            return self.meh_sections
        # The first entry on the stack is the top-level sections
        return self.meh_nav_stack[0][0]

    def _meh_current_folder_key(self):
        """Return the folder key (e.g. 'me_overview') of the folder we're
        currently browsing inside, or None if at the top level."""
        if not self.meh_nav_stack:
            return None
        # The parent sections list is on the stack; look at the section
        # that was selected to enter this folder.
        parent_secs, parent_cur, _, _ = self.meh_nav_stack[-1]
        if parent_cur < len(parent_secs):
            return parent_secs[parent_cur].get("folder")
        return None

    def _meh_folder_default_config(self):
        """Return a map_config dict for a new template in the current folder."""
        from src.map_editor import (
            STORAGE_DENSE, STORAGE_SPARSE, GRID_SCROLLABLE, GRID_FIXED,
        )
        folder_key = self._meh_current_folder_key()
        defaults = self._MEH_FOLDER_DEFAULTS.get(folder_key)
        if not defaults:
            # Fallback — generic small map
            return {
                "storage": STORAGE_SPARSE,
                "grid_type": GRID_FIXED,
                "tile_context": "dungeon",
                "width": 12, "height": 10,
            }
        storage_map = {"dense": STORAGE_DENSE, "sparse": STORAGE_SPARSE}
        grid_map = {"fixed": GRID_FIXED, "scrollable": GRID_SCROLLABLE}
        return {
            "storage": storage_map.get(defaults["storage"], STORAGE_SPARSE),
            "grid_type": grid_map.get(defaults["grid"], GRID_FIXED),
            "tile_context": defaults["ctx"],
            "width": defaults["w"],
            "height": defaults["h"],
        }

    def _meh_get_parent_template(self):
        """Return the parent template folder dict from the nav stack.

        When inside a template folder (Settings / Edit Map), the parent
        is the template folder itself — stored one level up on the nav stack.
        """
        if not self.meh_nav_stack:
            return None
        parent_secs, parent_cur, _, _ = self.meh_nav_stack[-1]
        if parent_cur < len(parent_secs):
            sec = parent_secs[parent_cur]
            if sec.get("folder") == "template":
                return sec
        return None

    def _meh_open_template_settings(self, tmpl):
        """Open the field editor for a template's settings."""
        mc = tmpl.get("map_config", {})
        canvas_type = tmpl.get("canvas_type", "blank")
        # Build field entries: (label, key, value, type, editable)
        self.meh_fields = [
            ["Name", "label", tmpl.get("label", ""), "text", True],
            ["Description", "description",
             tmpl.get("description", ""), "text", True],
            ["", "", "", "section", False],
            ["Width", "width", str(mc.get("width", 12)), "text", True],
            ["Height", "height", str(mc.get("height", 10)), "text", True],
            ["Canvas", "canvas_type", canvas_type, "cycle", True],
            ["", "", "", "section", False],
            ["Generate Map", "generate", "Press Enter to generate",
             "action", True],
        ]
        self.meh_field = 0
        self.meh_buffer = str(self.meh_fields[0][2])
        self.meh_level = 1
        # Store reference to the template being edited
        self._meh_settings_target = tmpl

    def meh_add_template(self, name):
        """Add a new map template with *name* to the current folder."""
        mc = self._meh_folder_default_config()
        new_sec = self._meh_wrap_template({
            "label": name,
            "subtitle": f"{mc['width']}x{mc['height']}",
            "description": "",
            "canvas_type": "blank",
            "map_config": mc,
        })
        self.meh_sections.append(new_sec)
        self.meh_cursor = len(self.meh_sections) - 1
        self._meh_update_parent_subtitle()
        self.save_map_templates()

    def meh_delete_template(self):
        """Delete the currently selected template from the current folder."""
        n = len(self.meh_sections)
        if n == 0:
            return
        sec = self.meh_sections[self.meh_cursor]
        # Only allow deleting template folders
        if sec.get("folder") != "template":
            return
        self.meh_sections.pop(self.meh_cursor)
        n -= 1
        if n == 0:
            self.meh_cursor = 0
        elif self.meh_cursor >= n:
            self.meh_cursor = n - 1
        self._meh_update_parent_subtitle()
        self.save_map_templates()

    def meh_rename_template(self, new_name):
        """Rename the currently selected template."""
        n = len(self.meh_sections)
        if n == 0:
            return
        sec = self.meh_sections[self.meh_cursor]
        if sec.get("folder") != "template":
            return
        sec["label"] = new_name
        self.save_map_templates()

    def _meh_update_parent_subtitle(self):
        """Update the parent folder's subtitle to reflect current child count."""
        if not self.meh_nav_stack:
            return
        parent_secs, parent_cur, _, _ = self.meh_nav_stack[-1]
        if parent_cur < len(parent_secs):
            parent = parent_secs[parent_cur]
            # Only update template folders (not the Tiles folder)
            if parent.get("folder", "").startswith("me_"):
                count = len(self.meh_sections)
                parent["subtitle"] = (
                    f"{count} template{'s' if count != 1 else ''}")

    def _meh_is_template_item(self):
        """Return True if the currently selected item is a template folder
        (not a category folder, editor redirect, or settings/edit-map child)."""
        n = len(self.meh_sections)
        if n == 0:
            return False
        sec = self.meh_sections[self.meh_cursor]
        return bool(sec.get("folder") == "template")

    def _meh_wrap_template(self, data):
        """Wrap a template data dict as a navigable folder.

        The returned dict acts as a folder with two children:
          - Settings  (opens field editor for name/desc/size/canvas)
          - Edit Map  (launches fullscreen map editor)

        The template's map_config, tiles, description, and canvas_type
        live on the folder dict itself so save/load can find them.
        """
        mc = data.get("map_config", {})
        w = mc.get("width", 12)
        h = mc.get("height", 10)
        folder = {
            "label": data.get("label", "Unnamed"),
            "subtitle": data.get("subtitle", f"{w}x{h}"),
            "description": data.get("description", ""),
            "canvas_type": data.get("canvas_type", "blank"),
            "folder": "template",
            "map_config": mc,
            "children": [
                {"label": "Settings",
                 "subtitle": "Name, size, and canvas options",
                 "_template_settings": True},
                {"label": "Edit Map",
                 "subtitle": f"{w}x{h} tile canvas",
                 "_template_edit_map": True},
            ],
        }
        tiles = data.get("tiles")
        if tiles is not None:
            folder["tiles"] = tiles
        return folder

    def _meh_children_from_saved(self, folder_key, saved_data):
        """Convert saved JSON template list back into section children dicts
        with live map_config constants, each wrapped as a template folder."""
        from src.map_editor import (
            STORAGE_DENSE, STORAGE_SPARSE, GRID_SCROLLABLE, GRID_FIXED,
        )
        storage_map = {"dense": STORAGE_DENSE, "sparse": STORAGE_SPARSE}
        grid_map = {"fixed": GRID_FIXED, "scrollable": GRID_SCROLLABLE}
        children = []
        for entry in saved_data:
            mc_raw = entry.get("map_config", {})
            data = {
                "label": entry.get("label", "Unnamed"),
                "subtitle": entry.get("subtitle", ""),
                "description": entry.get("description", ""),
                "canvas_type": entry.get("canvas_type", "blank"),
                "map_config": {
                    "storage": storage_map.get(
                        mc_raw.get("storage", "sparse"), STORAGE_SPARSE),
                    "grid_type": grid_map.get(
                        mc_raw.get("grid_type", "fixed"), GRID_FIXED),
                    "tile_context": mc_raw.get("tile_context", "dungeon"),
                    "width": mc_raw.get("width", 12),
                    "height": mc_raw.get("height", 10),
                },
            }
            tiles = entry.get("tiles")
            if tiles is not None:
                data["tiles"] = tiles
            children.append(self._meh_wrap_template(data))
        return children

    def build_map_editor_hub_sections(self):
        """Build the section list for the top-level Map Editor hub.

        Loads templates from map_templates.json if it exists, otherwise
        uses built-in defaults. Returns folder sections for each map
        type plus the Tiles folder.
        """
        from src.map_editor import (
            STORAGE_DENSE, STORAGE_SPARSE, GRID_SCROLLABLE, GRID_FIXED,
        )

        saved = self.load_map_templates()

        # Define folder metadata: (folder_key, label, default_children)
        folder_defs = [
            ("me_enclosure", "Templates", [
                {"label": "Blacksmith Shop",
                 "subtitle": "Interior space for a town building",
                 "map_config": {"storage": STORAGE_SPARSE,
                                "grid_type": GRID_FIXED,
                                "tile_context": "dungeon",
                                "width": 16, "height": 14}},
            ]),
        ]

        sections = []
        for folder_key, label, defaults in folder_defs:
            if folder_key in saved:
                children = self._meh_children_from_saved(
                    folder_key, saved[folder_key])
            else:
                children = [self._meh_wrap_template(d) for d in defaults]
            n = len(children)
            sections.append({
                "label": label,
                "folder": folder_key,
                "children": children,
                "subtitle": f"{n} template{'s' if n != 1 else ''}",
            })

        # ── 6) Tiles folder (Tile Types + Tile Gallery) ──
        tiles_sec = {
            "label": "Tiles",
            "folder": "me_tiles",
            "children": [
                {
                    "label": "Tile Types",
                    "subtitle": "Edit tile type properties",
                    "_editor_redirect": "tiles",
                },
                {
                    "label": "Tile Gallery",
                    "subtitle": "Browse all graphic tiles",
                    "_editor_redirect": "gallery",
                },
            ],
            "subtitle": "Tile types and gallery",
        }

        sections.append(tiles_sec)
        return sections

    def _meh_launch_editor(self, sec):
        """Launch the unified map editor for a Map Editor hub template."""
        from src.map_editor import (
            MapEditorConfig, MapEditorState, MapEditorInputHandler,
            build_overworld_brushes, build_town_brushes,
            STORAGE_DENSE, STORAGE_SPARSE,
        )

        mc = sec["map_config"]
        ctx = mc["tile_context"]
        w = mc["width"]
        h = mc["height"]
        storage = mc["storage"]
        grid_type = mc["grid_type"]

        # Load all templates for stamp brush folders
        saved_all = self.load_map_templates()

        # Build brushes based on tile context
        manifest = {}
        try:
            mpath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "tile_manifest.json")
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            pass

        if ctx == "overworld":
            brushes = build_overworld_brushes(
                self.TILE_CONTEXT,
                all_templates=saved_all,
            )
        else:
            # All non-overworld editors get every tile type,
            # organised into Town / Interior / Overworld folders.
            brushes = build_town_brushes(
                self.TILE_CONTEXT,
                feat_tiles_path=self.tiles_path(),
                manifest=manifest,
                feat_tile_list=getattr(self, "tile_list", None),
                all_templates=saved_all,
            )

        # Build initial tile data — reuse saved tiles when available
        canvas_type = sec.get("canvas_type", "blank")
        if storage == STORAGE_DENSE:
            existing = sec.get("tiles")
            if (existing is not None
                    and len(existing) == h
                    and all(len(row) == w for row in existing)):
                tiles = existing
            elif canvas_type == "procedural":
                tiles = self._meh_generate_procedural(ctx, w, h)
                sec["tiles"] = tiles
            else:
                # Fresh grid: grass for overworld, stone floor for dungeons
                default_tile = 0 if ctx == "overworld" else 10
                tiles = [[default_tile] * w for _ in range(h)]
                sec["tiles"] = tiles
        else:
            # Sparse: start with empty dict; store in the section
            tiles = sec.setdefault("tiles", {})

        def _on_save(st):
            # For hub templates we store tiles back into the section
            if storage == STORAGE_DENSE:
                sec["tiles"] = st.tiles
            # Sparse tiles are already the same dict reference
            st.dirty = False
            # Persist all templates to disk
            self.save_map_templates()

        def _on_exit(st):
            # Save tiles on exit (same as on_save)
            if storage == STORAGE_DENSE:
                sec["tiles"] = st.tiles
            self.save_map_templates()
            self.meh_editor_active = False
            self.game._map_editor_state = None

        config = MapEditorConfig(
            title=sec.get("label", "MAP EDITOR"),
            storage=storage,
            grid_type=grid_type,
            width=w,
            height=h,
            brushes=brushes,
            tile_context=ctx,
            supports_replace=(storage == STORAGE_SPARSE),
            on_save=_on_save,
            on_exit=_on_exit,
        )

        state = MapEditorState(config, tiles=tiles)
        if storage == STORAGE_SPARSE:
            state.cursor_col = 1
            state.cursor_row = 1

        self.meh_editor_active = True
        self.game._map_editor_state = state
        self._meh_input_handler = MapEditorInputHandler(state)

    def _meh_generate_procedural(self, ctx, w, h):
        """Generate a simple procedural tile map.

        For overworld: scatter water, forest, mountain, sand, path over grass.
        For dungeon: scatter floor patterns over stone.
        """
        import random
        from src.settings import (
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
            TILE_SAND, TILE_PATH,
        )
        rng = random.Random()
        if ctx == "overworld":
            tiles = [[TILE_GRASS] * w for _ in range(h)]
            # Scatter some water (lakes)
            lake_count = max(1, (w * h) // 40)
            for _ in range(lake_count):
                cx, cy = rng.randint(1, w - 2), rng.randint(1, h - 2)
                radius = rng.randint(1, min(3, w // 4, h // 4))
                for dy in range(-radius, radius + 1):
                    for dx in range(-radius, radius + 1):
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < w and 0 <= ny < h
                                and dx * dx + dy * dy <= radius * radius):
                            tiles[ny][nx] = TILE_WATER
            # Scatter forests
            for _ in range((w * h) // 8):
                x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
                if tiles[y][x] == TILE_GRASS:
                    tiles[y][x] = TILE_FOREST
            # Scatter mountains along edges
            for _ in range((w * h) // 20):
                x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
                if tiles[y][x] == TILE_GRASS:
                    tiles[y][x] = TILE_MOUNTAIN
            # A path through the middle
            mid_y = h // 2
            for x in range(w):
                py = mid_y + rng.randint(-1, 1)
                if 0 <= py < h and tiles[py][x] == TILE_GRASS:
                    tiles[py][x] = TILE_PATH
            return tiles
        else:
            # Dungeon — stone floor (10) with some variety
            tiles = [[10] * w for _ in range(h)]
            # Walls around edges
            for x in range(w):
                tiles[0][x] = 0
                tiles[h - 1][x] = 0
            for y in range(h):
                tiles[y][0] = 0
                tiles[y][w - 1] = 0
            return tiles

    def _meh_next_editable(self, start, direction=1):
        """Find next editable field index."""
        fields = self.meh_fields
        n = len(fields)
        if n == 0:
            return 0
        idx = start % n
        for _ in range(n):
            editable = fields[idx][4] if len(fields[idx]) > 4 else True
            ftype = fields[idx][3] if len(fields[idx]) > 3 else "text"
            if editable and ftype != "section":
                return idx
            idx = (idx + direction) % n
        return start % n

    _CANVAS_TYPE_OPTIONS = ["blank", "procedural"]

    def handle_meh_field_input(self, event):
        """Handle input in the Map Editor hub field editor."""
        if event.key == pygame.K_ESCAPE:
            # Apply pending text edits before leaving
            self._meh_commit_field_edit()
            # Write field values back to the template target
            self._meh_apply_settings()
            self.save_map_templates()  # persist changes to disk
            self.meh_level = 0
            self._meh_settings_target = None
            return

        fields = self.meh_fields
        n = len(fields)
        if n == 0:
            self.meh_level = 0
            return

        fi = self.meh_field
        ftype = fields[fi][3] if len(fields[fi]) > 3 else "text"
        editable = fields[fi][4] if len(fields[fi]) > 4 else True

        if event.key == pygame.K_UP:
            self._meh_commit_field_edit()
            self.meh_field = self._meh_next_editable(fi - 1, -1)
            self.meh_buffer = str(fields[self.meh_field][2])
        elif event.key == pygame.K_DOWN:
            self._meh_commit_field_edit()
            self.meh_field = self._meh_next_editable(fi + 1, 1)
            self.meh_buffer = str(fields[self.meh_field][2])
        elif event.key == pygame.K_RETURN:
            if ftype == "action" and editable:
                key = fields[fi][1]
                if key == "generate":
                    self._meh_commit_field_edit()
                    self._meh_apply_settings()
                    self._meh_generate_from_settings()
                return
            if editable and ftype == "text":
                fields[fi][2] = self.meh_buffer
        elif ftype == "cycle" and editable:
            # Left/Right or Enter cycles through options
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT,
                             pygame.K_RETURN, pygame.K_SPACE):
                cur = fields[fi][2]
                opts = self._CANVAS_TYPE_OPTIONS
                try:
                    idx = opts.index(cur)
                except ValueError:
                    idx = 0
                direction = -1 if event.key == pygame.K_LEFT else 1
                idx = (idx + direction) % len(opts)
                fields[fi][2] = opts[idx]
                self.meh_buffer = opts[idx]
        elif event.key == pygame.K_BACKSPACE:
            if editable and ftype == "text":
                self.meh_buffer = self.meh_buffer[:-1]
        elif event.unicode and editable and ftype == "text":
            self.meh_buffer += event.unicode

    def _meh_commit_field_edit(self):
        """Commit the current buffer to the active field."""
        if not self.meh_fields:
            return
        fi = self.meh_field
        if fi < len(self.meh_fields):
            ftype = (self.meh_fields[fi][3]
                     if len(self.meh_fields[fi]) > 3 else "text")
            if ftype == "text":
                self.meh_fields[fi][2] = self.meh_buffer

    def _meh_apply_settings(self):
        """Write field editor values back to the template target dict."""
        tmpl = getattr(self, '_meh_settings_target', None)
        if not tmpl:
            return
        fields = self.meh_fields
        mc = tmpl.get("map_config", {})
        old_w, old_h = mc.get("width", 12), mc.get("height", 10)
        for f in fields:
            key = f[1]
            val = f[2]
            if key == "label":
                tmpl["label"] = val
            elif key == "description":
                tmpl["description"] = val
            elif key == "width":
                try:
                    mc["width"] = max(4, min(128, int(val)))
                except (ValueError, TypeError):
                    pass
            elif key == "height":
                try:
                    mc["height"] = max(4, min(128, int(val)))
                except (ValueError, TypeError):
                    pass
            elif key == "canvas_type":
                tmpl["canvas_type"] = val
        # Update subtitle on the template folder
        w, h = mc.get("width", 12), mc.get("height", 10)
        tmpl["subtitle"] = f"{w}x{h}"
        # Update the Edit Map child's subtitle too
        for child in tmpl.get("children", []):
            if child.get("_template_edit_map"):
                child["subtitle"] = f"{w}x{h} tile canvas"
        # If dimensions changed, invalidate existing tile data
        if (w != old_w or h != old_h) and "tiles" in tmpl:
            del tmpl["tiles"]

    def _meh_generate_from_settings(self):
        """Generate (or regenerate) tile data for the current template
        based on its settings, then update the action field label."""
        from src.map_editor import STORAGE_DENSE, STORAGE_SPARSE
        tmpl = getattr(self, '_meh_settings_target', None)
        if not tmpl:
            return
        mc = tmpl.get("map_config", {})
        ctx = mc.get("tile_context", "dungeon")
        w = mc.get("width", 12)
        h = mc.get("height", 10)
        storage = mc.get("storage", STORAGE_SPARSE)
        canvas_type = tmpl.get("canvas_type", "blank")

        if storage == STORAGE_DENSE:
            if canvas_type == "procedural":
                tmpl["tiles"] = self._meh_generate_procedural(ctx, w, h)
            else:
                default_tile = 0 if ctx == "overworld" else 10
                tmpl["tiles"] = [[default_tile] * w for _ in range(h)]
        else:
            # Sparse: reset to empty
            tmpl["tiles"] = {}

        # Update the action field to show confirmation
        for f in self.meh_fields:
            if f[1] == "generate":
                f[2] = f"Generated {w}x{h} ({canvas_type})"

        # Auto-save
        self.save_map_templates()
        self.meh_save_flash = 1.5

    def return_to_maps_hub(self):
        """Return to the Maps hub from a sub-editor (tiles/gallery).

        Restores the mapeditor state and pops back into the Tiles folder
        so the user lands where they left off.
        """
        self.launched_from_maps = False
        self.active_editor = "mapeditor"
        # Rebuild sections and navigate into the Tiles folder
        self.meh_sections = self.build_map_editor_hub_sections()
        # Find the Tiles folder and enter it
        for i, sec in enumerate(self.meh_sections):
            if sec.get("folder") == "me_tiles":
                self.meh_nav_stack = [(
                    self.meh_sections,
                    i,
                    0,
                    "",
                )]
                children = sec.get("children")
                if children is None:
                    children = []
                    sec["children"] = children
                self.meh_sections = children
                self.meh_cursor = 0
                self.meh_scroll = 0
                self.meh_folder_label = sec.get("label", "Tiles")
                break
        else:
            self.meh_cursor = 0
            self.meh_scroll = 0
            self.meh_nav_stack = []
            self.meh_folder_label = ""
        self.meh_level = 0
        self.meh_fields = []
        self.meh_field = 0
        self.meh_buffer = ""
        self.meh_field_scroll = 0
        self.level = 1

    # ══════════════════════════════════════════════════════════
    # ── Generic Helpers ────────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def next_editable_generic(fields, start):
        """Find next editable field index from start in any field list.

        Supports both FieldEntry dataclass instances and legacy
        positional lists (used by the module editor).
        """
        n = len(fields)
        if n == 0:
            return 0
        idx = start % n
        for _ in range(n):
            entry = fields[idx]
            if isinstance(entry, FieldEntry):
                if entry.editable and entry.field_type != "section":
                    return idx
            else:
                # Legacy list format: [label, key, value, type, editable]
                if len(entry) > 4 and entry[4] and entry[3] != "section":
                    return idx
            idx = (idx + 1) % n
        return start % n

    @staticmethod
    def adjust_scroll_generic(cursor, scroll, max_visible=14):
        """Generic scroll adjustment. Returns new scroll value."""
        if cursor < scroll:
            return cursor
        if cursor >= scroll + max_visible:
            return cursor - max_visible + 1
        return scroll

    @staticmethod
    def adjust_field_scroll_generic(field_idx, scroll):
        """Generic field scroll adjustment."""
        row_h = 38
        panel_h = 500
        max_visible = panel_h // row_h
        if field_idx < scroll:
            return field_idx
        if field_idx >= scroll + max_visible:
            return field_idx - max_visible + 1
        return scroll

    def open_modules(self):
        """Open the module browser from within the features editor."""
        self.game._refresh_module_list()
        self.game.showing_features = False
        self.game.showing_modules = True
        self.game._modules_from_features = True
        self.game.module_message = None
        self.game.module_msg_timer = 0.0
        self.game.module_confirm_delete = False
        self.game.module_edit_mode = False
        self.game.module_edit_is_new = False

    # ══════════════════════════════════════════════════════════
    # ── Main Input Handlers ────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def handle_input(self, event):
        """Handle input for the Game Features editor.

        Uses active_editor to dispatch to the correct data
        structures while sharing the same level-1/level-2 navigation logic.
        """
        # ── Route mouse events to map editors that support them ──
        _MAP_EDITORS = {
            "mod_overview_map": "_mod_map_editor",
            "mod_town_map": "_mod_town_map_editor",
            "mod_dungeon_map": "_mod_dungeon_map_editor",
            "mod_building_map": "_mod_building_map_editor",
        }
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                          pygame.MOUSEWHEEL, pygame.MOUSEMOTION):
            prefix = _MAP_EDITORS.get(self.active_editor)
            if prefix:
                game = self.game
                handler = getattr(game, f"{prefix}_handler", None)
                state = getattr(game, f"{prefix}_state", None)
                if handler and state:
                    handler.handle_mouse(event)
            return

        if event.type != pygame.KEYDOWN:
            return

        # Intercept input when unsaved-changes dialog is showing
        if self.game._unsaved_dialog_active:
            self.game._handle_unsaved_dialog_input(event)
            return

        # Map Editor hub has its own section-browser input handler
        if self.active_editor == "mapeditor":
            self.handle_mapeditor_input(event)
            return

        # Module overview map editor (shared map editor instance)
        if self.active_editor == "mod_overview_map":
            game = self.game
            if (hasattr(game, '_mod_map_editor_state')
                    and game._mod_map_editor_state is not None):
                result = game._mod_map_editor_handler.handle(event)
                if result == "exit":
                    self.active_editor = None
                    self.level = 0
            return

        # Module town map editor (shared map editor instance)
        if self.active_editor == "mod_town_map":
            game = self.game
            if (hasattr(game, '_mod_town_map_editor_state')
                    and game._mod_town_map_editor_state is not None):
                result = game._mod_town_map_editor_handler.handle(event)
                if result == "exit":
                    self.active_editor = None
                    self.level = 0
            return

        # Module dungeon map editor (shared map editor instance)
        if self.active_editor == "mod_dungeon_map":
            game = self.game
            if (hasattr(game, '_mod_dungeon_map_editor_state')
                    and game._mod_dungeon_map_editor_state is not None):
                result = game._mod_dungeon_map_editor_handler.handle(event)
                if result == "exit":
                    self.active_editor = None
                    self.level = 0
            return

        # Module building map editor (shared map editor instance)
        if self.active_editor == "mod_building_map":
            game = self.game
            if (hasattr(game, '_mod_building_map_editor_state')
                    and game._mod_building_map_editor_state is not None):
                result = game._mod_building_map_editor_handler.handle(event)
                if result == "exit":
                    self.active_editor = None
                    self.level = 0
            return

        # ── Resolve active editor data pointers ──
        ed = self.active_editor
        # Build a context dict so the level-1 and level-2 code
        # can work generically across all editor types
        ctx = self.editor_ctx()

        # ── Level 3: counter item sub-list ──
        if self.level == 3 and ed == "counters":
            self._handle_counter_items_input(event)
            return

        # ── Level 2 counters: intercept Enter on "Edit Items" field ──
        if self.level == 2 and ed == "counters" and ctx:
            fields = ctx["fields"]()
            field_idx = ctx["field_idx"]()
            if (fields and 0 <= field_idx < len(fields)
                    and fields[field_idx].key == "_edit_items"
                    and event.key in (pygame.K_RETURN, pygame.K_RIGHT)):
                ctx["save_fields"]()
                self.counter_open_items()
                return

        # ── Level 2: editing individual fields ──
        # (tiles and gallery use level 2 for browsing, not field editing)
        if self.level == 2 and ctx and ed not in ("tiles", "gallery", "features"):
            self.handle_field_editing(event, ctx, ed, exit_level=1)
            return

        # ── Level 4: pixel editor ──
        if self.level == 5 and ed == "gallery":
            px = self.pxedit_pixels
            if px is None:
                self.level = 3
                return
            w = self.pxedit_w
            h = self.pxedit_h
            n_pal = len(self.pxedit_palette)
            pal_cols = 4  # palette grid columns

            # ── Color replace mode ──
            if self.pxedit_replacing:
                if event.key == pygame.K_ESCAPE:
                    self.pxedit_replacing = False
                elif event.key == pygame.K_LEFT:
                    self.pxedit_replace_dst = (
                        self.pxedit_replace_dst - 1) % n_pal
                elif event.key == pygame.K_RIGHT:
                    self.pxedit_replace_dst = (
                        self.pxedit_replace_dst + 1) % n_pal
                elif event.key == pygame.K_UP:
                    self.pxedit_replace_dst = (
                        self.pxedit_replace_dst - pal_cols) % n_pal
                elif event.key == pygame.K_DOWN:
                    self.pxedit_replace_dst = (
                        self.pxedit_replace_dst + pal_cols) % n_pal
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # Snapshot for undo before batch replace
                    self.pxedit_undo_stack.append(
                        [list(row) for row in px])
                    # Execute: match the exact pixel color from canvas
                    src_c = self.pxedit_replace_src_color
                    dst_c = self.pxedit_palette[
                        self.pxedit_replace_dst]
                    for row in px:
                        for xi in range(len(row)):
                            if tuple(row[xi]) == tuple(src_c):
                                row[xi] = dst_c
                    self.dirty = True
                    self.pxedit_replacing = False
                return

            if self._is_save_shortcut(event):
                # Save without leaving the pixel editor
                self.pxedit_save()
                self.game.renderer.reload_sprites()
                self.dirty = False
                return

            if event.key == pygame.K_ESCAPE:
                if self.pxedit_focus == "palette":
                    # Escape from palette returns to canvas
                    self.pxedit_focus = "canvas"
                else:
                    if self.dirty:
                        def _save_and_exit():
                            self.pxedit_save()
                            self.pxedit_pixels = None
                            self.game.renderer.reload_sprites()
                            self.level = 3
                            self.dirty = False
                        def _discard_and_exit():
                            self.pxedit_pixels = None
                            self.game.renderer.reload_sprites()
                            self.level = 3
                            self.dirty = False
                        self.game._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
                    else:
                        self.pxedit_pixels = None
                        self.game.renderer.reload_sprites()
                        self.level = 3
                return

            # Tab toggles focus between canvas and palette (cancels paint mode)
            if event.key == pygame.K_TAB:
                self.pxedit_painting = False
                if self.pxedit_focus == "canvas":
                    self.pxedit_focus = "palette"
                else:
                    self.pxedit_focus = "canvas"
                return

            if self.pxedit_focus == "palette":
                # ── Palette navigation (grid: 4 columns) ──
                ci = self.pxedit_color_idx
                if event.key == pygame.K_LEFT:
                    self.pxedit_color_idx = (ci - 1) % n_pal
                elif event.key == pygame.K_RIGHT:
                    self.pxedit_color_idx = (ci + 1) % n_pal
                elif event.key == pygame.K_UP:
                    self.pxedit_color_idx = (
                        ci - pal_cols) % n_pal
                elif event.key == pygame.K_DOWN:
                    self.pxedit_color_idx = (
                        ci + pal_cols) % n_pal
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # Confirm selection, return to canvas
                    self.pxedit_focus = "canvas"
                return

            # ── Canvas mode ──
            # Cursor movement
            moved = False
            if event.key == pygame.K_UP:
                self.pxedit_cy = (
                    self.pxedit_cy - 1) % h
                moved = True
            elif event.key == pygame.K_DOWN:
                self.pxedit_cy = (
                    self.pxedit_cy + 1) % h
                moved = True
            elif event.key == pygame.K_LEFT:
                self.pxedit_cx = (
                    self.pxedit_cx - 1) % w
                moved = True
            elif event.key == pygame.K_RIGHT:
                self.pxedit_cx = (
                    self.pxedit_cx + 1) % w
                moved = True
            # Continuous paint: auto-paint after each move
            if moved and self.pxedit_painting:
                color = self.pxedit_palette[
                    self.pxedit_color_idx]
                if tuple(px[self.pxedit_cy][self.pxedit_cx]) != tuple(color):
                    px[self.pxedit_cy][self.pxedit_cx] = color
                    self.dirty = True
            if moved:
                pass  # already handled
            # Enter: toggle continuous paint mode
            elif event.key == pygame.K_RETURN:
                if self.pxedit_painting:
                    self.pxedit_painting = False
                else:
                    self.pxedit_painting = True
                    # Snapshot for undo at the start of a paint stroke
                    self.pxedit_undo_stack.append(
                        [list(row) for row in px])
                    color = self.pxedit_palette[
                        self.pxedit_color_idx]
                    px[self.pxedit_cy][self.pxedit_cx] = color
                    self.dirty = True
            # Space: single paint (does not toggle mode)
            elif event.key == pygame.K_SPACE:
                # Snapshot for undo
                self.pxedit_undo_stack.append(
                    [list(row) for row in px])
                color = self.pxedit_palette[
                    self.pxedit_color_idx]
                px[self.pxedit_cy][self.pxedit_cx] = color
                self.dirty = True
            # Quick palette cycle: Q = prev, E = next (cancels paint mode)
            elif event.key == pygame.K_q:
                self.pxedit_painting = False
                self.pxedit_color_idx = (
                    self.pxedit_color_idx - 1) % n_pal
            elif event.key == pygame.K_e:
                self.pxedit_painting = False
                self.pxedit_color_idx = (
                    self.pxedit_color_idx + 1) % n_pal
            # Pick color from canvas (P = eyedropper, cancels paint mode)
            elif event.key == pygame.K_p:
                self.pxedit_painting = False
                picked = tuple(
                    px[self.pxedit_cy][self.pxedit_cx])
                best_i = 0
                best_d = float("inf")
                for pi, pc in enumerate(self.pxedit_palette):
                    d = sum((a - b) ** 2
                            for a, b in zip(picked[:3], pc[:3]))
                    if d < best_d:
                        best_d = d
                        best_i = pi
                self.pxedit_color_idx = best_i
            # Enter color replace mode (R, cancels paint mode)
            elif event.key == pygame.K_r:
                self.pxedit_painting = False
                picked = tuple(
                    px[self.pxedit_cy][self.pxedit_cx])
                self.pxedit_replacing = True
                self.pxedit_replace_src_color = picked
                self.pxedit_replace_dst = self.pxedit_color_idx
                self.pxedit_replace_sel = "dst"
            # Undo (Ctrl+Z or U, cancels paint mode)
            elif (event.key == pygame.K_z
                  and (event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))) \
                    or event.key == pygame.K_u:
                self.pxedit_painting = False
                if self.pxedit_undo_stack:
                    restored = self.pxedit_undo_stack.pop()
                    # Copy restored data back into the live pixel array
                    for yi in range(len(restored)):
                        px[yi][:] = restored[yi]
                    self.dirty = True
            return

        # ── Level 4: gallery tag editing ──
        if self.level == 4 and ed == "gallery":
            n_tags = len(self.gallery_all_cats)
            if self._is_save_shortcut(event):
                # Save without leaving the tag editor
                self.save_gallery()
                self.dirty = False
                return
            if event.key == pygame.K_ESCAPE:
                if self.dirty:
                    def _save_and_exit():
                        self.save_gallery()
                        self.level = 3
                        self._rebuild_gallery_cats()
                        self.dirty = False
                    def _discard_and_exit():
                        self.level = 3
                        self._rebuild_gallery_cats()
                        self.dirty = False
                    self.game._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
                else:
                    self.level = 3
                    self._rebuild_gallery_cats()
                return
            if event.key == pygame.K_UP:
                self.gallery_tag_cursor = (
                    self.gallery_tag_cursor - 1) % n_tags
            elif event.key == pygame.K_DOWN:
                self.gallery_tag_cursor = (
                    self.gallery_tag_cursor + 1) % n_tags
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE,
                               pygame.K_LEFT, pygame.K_RIGHT):
                self.gallery_toggle_tag()
                self.dirty = True
            return

        # ── Level 3: gallery tile detail / edit screen ──
        if self.level == 3 and ed == "gallery":
            # ── Naming mode: capture text input ──
            if self.gallery_naming:
                self.handle_gallery_naming_input(event)
                return
            n_fields = 3  # Name, Categories, Edit Pixels
            if event.key == pygame.K_ESCAPE:
                self.level = 2
                return
            if event.key == pygame.K_UP:
                self.gallery_detail_cursor = (
                    self.gallery_detail_cursor - 1) % n_fields
            elif event.key == pygame.K_DOWN:
                self.gallery_detail_cursor = (
                    self.gallery_detail_cursor + 1) % n_fields
            elif event.key == pygame.K_RETURN:
                cur = self.gallery_detail_cursor
                if cur == 0:
                    # Name → enter naming mode
                    gi = self.gallery_cur_gi()
                    if gi is not None:
                        self.gallery_naming = True
                        self.gallery_name_buf = \
                            self.gallery_list[gi]["name"]
                elif cur == 1:
                    # Categories → open tag editor (Level 4)
                    self.gallery_tag_cursor = 0
                    self.dirty = False
                    self.level = 4
                elif cur == 2:
                    # Edit Pixels → open pixel editor (Level 5)
                    if self.pxedit_open():
                        self.level = 5
            return

        # ── Level 2: gallery sprite list ──
        if self.level == 2 and ed == "gallery":
            n = len(self.gallery_sprites)
            if event.key == pygame.K_ESCAPE:
                self.save_gallery()
                self._rebuild_gallery_cats()
                self.level = 1
                return
            if event.key == pygame.K_UP and n > 0:
                self.gallery_spr_cursor = (
                    self.gallery_spr_cursor - 1) % n
                self.gallery_spr_scroll = \
                    self._adjust_scroll_generic(
                        self.gallery_spr_cursor,
                        self.gallery_spr_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self.gallery_spr_cursor = (
                    self.gallery_spr_cursor + 1) % n
                self.gallery_spr_scroll = \
                    self._adjust_scroll_generic(
                        self.gallery_spr_cursor,
                        self.gallery_spr_scroll)
            elif event.key == pygame.K_RETURN:
                # Enter → open tile detail / edit screen
                if n > 0:
                    self.gallery_detail_cursor = 0
                    self.level = 3
            elif self._is_copy_shortcut(event):
                if n > 0:
                    self.gallery_duplicate()
            elif self._is_delete_shortcut(event) and n > 0:
                self.gallery_delete()
            return

        # ── Level 1: gallery category folders ──
        if self.level == 1 and ed == "gallery":
            n = len(self.gallery_cat_list)
            if event.key == pygame.K_ESCAPE:
                self.save_gallery()
                if self.launched_from_maps:
                    self.return_to_maps_hub()
                else:
                    self.level = 0
                    self.active_editor = None
                return
            if event.key == pygame.K_UP and n > 0:
                self.gallery_cat_cursor = (
                    self.gallery_cat_cursor - 1) % n
                self.gallery_cat_scroll = \
                    self._adjust_scroll_generic(
                        self.gallery_cat_cursor,
                        self.gallery_cat_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self.gallery_cat_cursor = (
                    self.gallery_cat_cursor + 1) % n
                self.gallery_cat_scroll = \
                    self._adjust_scroll_generic(
                        self.gallery_cat_cursor,
                        self.gallery_cat_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    self.gallery_enter_cat()
                    self.dirty = False
                    self.level = 2
            return

        # ── Level 4: spawn sub-list editor (monsters / loot) ──
        if self.level == 4 and ed == "tiles":
            self._handle_spawn_sublist_input(event)
            return

        # ── Level 3: tile field editor (inside folder) ──
        # Intercept Enter/Right on spawn sub-list launcher fields
        if self.level == 3 and ed == "tiles" and ctx:
            fields = ctx["fields"]()
            field_idx = ctx["field_idx"]()
            if (fields and 0 <= field_idx < len(fields)):
                fkey = fields[field_idx].key
                if (fkey in ("_sp_edit_monsters", "_sp_edit_loot",
                            "_sp_edit_boss")
                        and event.key in (pygame.K_RETURN, pygame.K_RIGHT)):
                    ctx["save_fields"]()
                    if fkey == "_sp_edit_monsters":
                        mode = "monsters"
                    elif fkey == "_sp_edit_boss":
                        mode = "boss"
                    else:
                        mode = "loot"
                    self.spawn_open_sublist(mode)
                    return
            self.handle_field_editing(event, ctx, ed, exit_level=2)
            return

        # ── Level 2: tile list inside folder ──
        if self.level == 2 and ed == "tiles":
            tiles_in = self.tile_folder_tiles
            n = len(tiles_in)
            if event.key == pygame.K_ESCAPE:
                self.save_tiles()
                self.tile_in_folder = False
                self.level = 1
                return
            if event.key == pygame.K_UP and n > 0:
                self.tile_cursor = (
                    self.tile_cursor - 1) % n
                self.tile_scroll = \
                    self._adjust_scroll_generic(
                        self.tile_cursor,
                        self.tile_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self.tile_cursor = (
                    self.tile_cursor + 1) % n
                self.tile_scroll = \
                    self._adjust_scroll_generic(
                        self.tile_cursor,
                        self.tile_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    ti = tiles_in[self.tile_cursor]
                    tile = self.tile_list[ti]
                    self.build_tile_fields(tile)
                    self.tile_editing = True
                    self.dirty = False
                    self.level = 3
            elif self._is_new_shortcut(event):
                # Ctrl+N creates a brand-new tile in this folder
                self.add_tile()
                self.save_tiles()
                self._rebuild_tile_folders()
                self.tile_enter_folder()
            elif self._is_copy_shortcut(event):
                # Ctrl+C duplicates the selected tile
                self.duplicate_tile()
                self.save_tiles()
                self._rebuild_tile_folders()
                self.tile_enter_folder()
            elif self._is_delete_shortcut(event):
                self.remove_tile()
                self.save_tiles()
                self._rebuild_tile_folders()
                self.tile_enter_folder()
            return

        # ── Level 1: tile folder list ──
        if self.level == 1 and ed == "tiles":
            n = len(self.tile_folders)
            if event.key == pygame.K_ESCAPE:
                self.save_tiles()
                if self.launched_from_maps:
                    self.return_to_maps_hub()
                else:
                    self.level = 0
                    self.active_editor = None
                return
            if event.key == pygame.K_UP and n > 0:
                self.tile_folder_cursor = (
                    self.tile_folder_cursor - 1) % n
                self.tile_folder_scroll = \
                    self._adjust_scroll_generic(
                        self.tile_folder_cursor,
                        self.tile_folder_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self.tile_folder_cursor = (
                    self.tile_folder_cursor + 1) % n
                self.tile_folder_scroll = \
                    self._adjust_scroll_generic(
                        self.tile_folder_cursor,
                        self.tile_folder_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    self.tile_enter_folder()
                    self.level = 2
            elif self._is_new_shortcut(event):
                # Create a new tile in the selected folder and enter it
                self.add_tile()
                self.save_tiles()
                self._rebuild_tile_folders()
                self.tile_enter_folder()
                self.level = 2
            return

        # ── Level 1: list browser ──
        # (tiles and gallery have their own level-1 handlers above)
        # ── Spell 3-tier folder navigation ──
        if self.level == 1 and ed == "spells":
            nav = self.spell_nav
            if nav == 0:
                # Tier 0: casting type folders
                ctypes = self.spell_casting_types()
                n = len(ctypes)
                if event.key == pygame.K_ESCAPE:
                    self.save_spells()
                    self.level = 0
                    self.active_editor = None
                elif event.key == pygame.K_UP and n > 0:
                    self.spell_ctype_cursor = (
                        self.spell_ctype_cursor - 1) % n
                elif event.key == pygame.K_DOWN and n > 0:
                    self.spell_ctype_cursor = (
                        self.spell_ctype_cursor + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
                    self.spell_sel_ctype = ctypes[
                        self.spell_ctype_cursor]
                    self.spell_level_cursor = 0
                    self.spell_level_scroll = 0
                    self.spell_nav = 1
                elif self._is_save_shortcut(event):
                    self.save_spells()
            elif nav == 1:
                # Tier 1: level folders for selected casting type
                levels = self.spell_levels_for_ctype(
                    self.spell_sel_ctype)
                n = len(levels)
                if event.key in (pygame.K_ESCAPE, pygame.K_LEFT):
                    self.spell_nav = 0
                elif event.key == pygame.K_UP and n > 0:
                    self.spell_level_cursor = (
                        self.spell_level_cursor - 1) % n
                    self.spell_level_scroll = (
                        self._adjust_scroll_generic(
                            self.spell_level_cursor,
                            self.spell_level_scroll))
                elif event.key == pygame.K_DOWN and n > 0:
                    self.spell_level_cursor = (
                        self.spell_level_cursor + 1) % n
                    self.spell_level_scroll = (
                        self._adjust_scroll_generic(
                            self.spell_level_cursor,
                            self.spell_level_scroll))
                elif event.key in (pygame.K_RETURN,
                                   pygame.K_RIGHT) and n > 0:
                    lvl, _count = levels[self.spell_level_cursor]
                    self.spell_sel_level = lvl
                    self.spell_filter(
                        self.spell_sel_ctype, lvl)
                    self.spell_nav = 2
                elif self._is_new_shortcut(event):
                    # Add spell with current casting type + first
                    # available level
                    self.add_spell()
                    new_s = self.spell_list[-1]
                    new_s["casting_type"] = self.spell_sel_ctype
                    new_s["allowable_classes"] = (
                        self.default_classes(
                            self.spell_sel_ctype))
                    self.resort_spells()
                    self.save_spells()
                elif self._is_save_shortcut(event):
                    self.save_spells()
            elif nav == 2:
                # Tier 2: spells at selected casting type + level
                filt = self.spell_filtered
                n = len(filt)
                if event.key in (pygame.K_ESCAPE, pygame.K_LEFT):
                    self.spell_nav = 1
                elif event.key == pygame.K_UP and n > 0:
                    self.spell_cursor = (
                        self.spell_cursor - 1) % n
                    self.spell_scroll = (
                        self._adjust_scroll_generic(
                            self.spell_cursor,
                            self.spell_scroll))
                elif event.key == pygame.K_DOWN and n > 0:
                    self.spell_cursor = (
                        self.spell_cursor + 1) % n
                    self.spell_scroll = (
                        self._adjust_scroll_generic(
                            self.spell_cursor,
                            self.spell_scroll))
                elif event.key in (pygame.K_RETURN,
                                   pygame.K_RIGHT) and n > 0:
                    real_idx = filt[self.spell_cursor]
                    # Save filter position; point cursor at real
                    # index for the field editor
                    self.spell_filter_pos = (
                        self.spell_cursor)
                    self.spell_cursor = real_idx
                    spell = self.spell_list[real_idx]
                    self.build_spell_fields(spell)
                    self.spell_editing = True
                    self.dirty = False
                    self.level = 2
                elif self._is_new_shortcut(event):
                    self.add_spell()
                    new_s = self.spell_list[-1]
                    new_s["casting_type"] = self.spell_sel_ctype
                    new_s["min_level"] = self.spell_sel_level
                    new_s["allowable_classes"] = (
                        self.default_classes(
                            self.spell_sel_ctype))
                    self.resort_spells()
                    self.save_spells()
                    self.spell_filter(
                        self.spell_sel_ctype,
                        self.spell_sel_level)
                    self.spell_cursor = max(
                        0, len(self.spell_filtered) - 1)
                elif self._is_delete_shortcut(event) and n > 0:
                    real_idx = filt[self.spell_cursor]
                    self.spell_list.pop(real_idx)
                    self.save_spells()
                    self.spell_filter(
                        self.spell_sel_ctype,
                        self.spell_sel_level)
                    if self.spell_cursor >= len(
                            self.spell_filtered):
                        self.spell_cursor = max(
                            0, len(self.spell_filtered) - 1)
                    # If level is now empty, go back to level list
                    if not self.spell_filtered:
                        self.spell_nav = 1
                elif self._is_save_shortcut(event):
                    self.save_spells()
            return

        # ── Level 1: generic list (items, monsters) ──
        if self.level == 1 and ctx and ed not in (
                "tiles", "gallery", "spells", "features"):
            lst = ctx["list"]()
            n = len(lst)
            if event.key == pygame.K_ESCAPE:
                ctx["save_disk"]()
                self.level = 0
                self.active_editor = None
                return
            if event.key == pygame.K_UP and n > 0:
                ctx["set_cursor"]((ctx["cursor"]() - 1) % n)
                ctx["adjust_scroll"]()
            elif event.key == pygame.K_DOWN and n > 0:
                ctx["set_cursor"]((ctx["cursor"]() + 1) % n)
                ctx["adjust_scroll"]()
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    item = lst[ctx["cursor"]()]
                    ctx["build_fields"](item)
                    ctx["set_editing"](True)
                    self.dirty = False
                    self.level = 2
            elif self._is_new_shortcut(event):
                ctx["add"]()
                ctx["adjust_scroll"]()
            elif self._is_delete_shortcut(event):
                ctx["remove"]()
            elif self._is_save_shortcut(event):
                ctx["save_disk"]()
            return

        # ── Level 0: category list ──
        n = len(self.categories)
        if event.key == pygame.K_ESCAPE:
            self.game.showing_features = False
            self.game.showing_title = True
            return
        if event.key == pygame.K_UP:
            self.cursor = (self.cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self.cursor = (self.cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE,
                           pygame.K_RIGHT):
            cat = self.categories[self.cursor]
            if cat["label"] == "Modules":
                self.open_modules()
            elif cat["label"] == "Spells":
                self.active_editor = "spells"
                self.load_spells()
                self.level = 1
            elif cat["label"] == "Items":
                self.active_editor = "items"
                self.load_items()
                self.level = 1
            elif cat["label"] == "Counters":
                self.active_editor = "counters"
                self.load_counters()
                self.level = 1
            elif cat["label"] == "Monsters":
                self.active_editor = "monsters"
                self.load_monsters()
                self.level = 1
            elif cat["label"] == "Maps":
                self.active_editor = "mapeditor"
                self.meh_sections = self.build_map_editor_hub_sections()
                self.meh_cursor = 0
                self.meh_scroll = 0
                self.meh_nav_stack = []
                self.meh_folder_label = ""
                self.meh_level = 0
                self.meh_fields = []
                self.meh_field = 0
                self.meh_buffer = ""
                self.meh_field_scroll = 0
                self.level = 1

    def _handle_meh_naming_input(self, event):
        """Handle text input while naming/renaming a map template."""
        if event.key == pygame.K_ESCAPE:
            self.meh_naming = False
            return
        if event.key == pygame.K_RETURN:
            name = self.meh_name_buf.strip()
            if name:
                if self.meh_naming_is_new:
                    self.meh_add_template(name)
                else:
                    self.meh_rename_template(name)
            self.meh_naming = False
            return
        if event.key == pygame.K_BACKSPACE:
            self.meh_name_buf = self.meh_name_buf[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self.meh_name_buf += event.unicode

    # ══════════════════════════════════════════════════════════
    # ── Town Editor Input ────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def handle_town_input(self, event):
        """Handle input for the Town Editor.

        Navigation levels:
        - level 1: Town list (browse all towns)
        - level 2: Sub-screen selector (Settings / Townspeople / Edit Map)
        - level 3: Settings field editor OR Townspeople list
        - level 4: NPC field editor (when editing a single NPC)
        """
        if event.type != pygame.KEYDOWN:
            return

        # ── Fullscreen map editor active ──
        if self.town_editor_active:
            if self._town_map_editor_handler:
                result = self._town_map_editor_handler.handle(event)
                if result == "exit":
                    self.town_editor_active = False
                    self._town_map_editor_state = None
                    self._town_map_editor_handler = None
            return

        # ── NPC field editor (level 4) ──
        if self.level == 4:
            self._handle_town_npc_field_input(event)
            return

        # ── Settings fields or Townspeople list (level 3) ──
        if self.level == 3:
            if self.town_sub_cursor == 0:
                # Settings field editor
                self._handle_town_settings_field_input(event)
            elif self.town_sub_cursor == 1:
                # Townspeople list
                self._handle_town_npc_list_input(event)
            return

        # ── Sub-screen selector (level 2) ──
        if self.level == 2:
            self._handle_town_sub_input(event)
            return

        # ── Town naming overlay ──
        if self.town_naming:
            self._handle_town_naming_input(event)
            return

        # ── Town list (level 1) ──
        layouts = self.town_lists.get("layouts", [])
        n = len(layouts)

        if event.key == pygame.K_ESCAPE:
            self.save_towns()
            self.level = 0
            self.active_editor = None
            return

        # Add new town (Ctrl+N)
        if self._is_new_shortcut(event):
            self.town_naming = True
            self.town_naming_is_new = True
            self.town_name_buf = ""
            return

        # Delete town (Ctrl+D)
        if self._is_delete_shortcut(event) and n > 0:
            layouts.pop(self.town_cursor)
            n -= 1
            if n == 0:
                self.town_cursor = 0
            elif self.town_cursor >= n:
                self.town_cursor = n - 1
            self.save_towns()
            return

        # Save (Ctrl+S)
        if self._is_save_shortcut(event):
            self.save_towns()
            self.town_save_flash = 1.5
            return

        # Rename (F2)
        if event.key == pygame.K_F2 and n > 0:
            town = self._town_get_current()
            if town:
                self.town_naming = True
                self.town_naming_is_new = False
                self.town_name_buf = town.get("name", "")
            return

        if event.key == pygame.K_UP and n > 0:
            self.town_cursor = (self.town_cursor - 1) % n
            self.town_scroll = self._adjust_scroll_generic(
                self.town_cursor, self.town_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self.town_cursor = (self.town_cursor + 1) % n
            self.town_scroll = self._adjust_scroll_generic(
                self.town_cursor, self.town_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            # Enter sub-screen selector
            self.town_sub_cursor = 0
            self.level = 2

    def _handle_town_naming_input(self, event):
        """Handle text input while naming/renaming a town."""
        if event.key == pygame.K_ESCAPE:
            self.town_naming = False
            return
        if event.key == pygame.K_RETURN:
            name = self.town_name_buf.strip()
            if name:
                if self.town_naming_is_new:
                    self._town_add_new(name)
                else:
                    town = self._town_get_current()
                    if town:
                        town["name"] = name
                        self.save_towns()
            self.town_naming = False
            return
        if event.key == pygame.K_BACKSPACE:
            self.town_name_buf = self.town_name_buf[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self.town_name_buf += event.unicode

    def _handle_town_sub_input(self, event):
        """Handle input on the sub-screen selector (Settings/Townspeople/Edit Map)."""
        n = len(self.town_sub_items)
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self.level = 1
            return
        if event.key == pygame.K_UP:
            self.town_sub_cursor = (self.town_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self.town_sub_cursor = (self.town_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self.town_sub_cursor == 0:
                # Settings
                self._town_build_settings_fields()
                self.level = 3
            elif self.town_sub_cursor == 1:
                # Townspeople
                self._town_load_npcs()
                self.level = 3
            elif self.town_sub_cursor == 2:
                # Edit Map
                self._town_launch_map_editor()

    def _handle_town_settings_field_input(self, event):
        """Handle input for town settings field editing."""
        fields = self.town_fields
        n = len(fields)
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.level = 2
            return

        if self._is_save_shortcut(event):
            # Commit current buffer and save
            fe = fields[self.town_field]
            if fe.editable:
                fe.value = self.town_buffer
            self._town_save_settings_fields()
            self.save_towns()
            self.town_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            # Commit and go back to sub-screen
            fe = fields[self.town_field]
            if fe.editable:
                fe.value = self.town_buffer
            self._town_save_settings_fields()
            self.level = 2
            return

        if event.key == pygame.K_UP:
            fe = fields[self.town_field]
            if fe.editable:
                fe.value = self.town_buffer
            self.town_field = self._next_editable_generic(
                fields, (self.town_field - 1) % n)
            self.town_buffer = fields[self.town_field].value
            self.town_field_scroll = self._adjust_field_scroll_generic(
                self.town_field, self.town_field_scroll)
        elif event.key == pygame.K_DOWN:
            fe = fields[self.town_field]
            if fe.editable:
                fe.value = self.town_buffer
            self.town_field = self._next_editable_generic(
                fields, (self.town_field + 1) % n)
            self.town_buffer = fields[self.town_field].value
            self.town_field_scroll = self._adjust_field_scroll_generic(
                self.town_field, self.town_field_scroll)
        elif event.key == pygame.K_BACKSPACE:
            self.town_buffer = self.town_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            self.town_buffer += event.unicode

    def _handle_town_npc_list_input(self, event):
        """Handle input for the townspeople NPC list."""
        n = len(self.town_npc_list)

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._town_save_npcs()
            self.level = 2
            return

        # Add NPC (Ctrl+N)
        if self._is_new_shortcut(event):
            self._town_add_npc()
            return

        # Delete NPC (Ctrl+D)
        if self._is_delete_shortcut(event) and n > 0:
            self._town_delete_npc()
            return

        # Save (Ctrl+S)
        if self._is_save_shortcut(event):
            self._town_save_npcs()
            self.save_towns()
            self.town_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self.town_npc_cursor = (self.town_npc_cursor - 1) % n
            self.town_npc_scroll = self._adjust_scroll_generic(
                self.town_npc_cursor, self.town_npc_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self.town_npc_cursor = (self.town_npc_cursor + 1) % n
            self.town_npc_scroll = self._adjust_scroll_generic(
                self.town_npc_cursor, self.town_npc_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._town_build_npc_fields()
            self.level = 4

    def _handle_town_npc_field_input(self, event):
        """Handle input for NPC field editing."""
        fields = self.town_npc_fields
        n = len(fields)
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.level = 3
            return

        if self._is_save_shortcut(event):
            fe = fields[self.town_npc_field]
            if fe.editable:
                fe.value = self.town_npc_buffer
            self._town_save_npc_fields()
            self._town_save_npcs()
            self.save_towns()
            self.town_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            fe = fields[self.town_npc_field]
            if fe.editable:
                fe.value = self.town_npc_buffer
            self._town_save_npc_fields()
            self._town_save_npcs()
            self.level = 3
            return

        if event.key == pygame.K_UP:
            fe = fields[self.town_npc_field]
            if fe.editable:
                fe.value = self.town_npc_buffer
            self.town_npc_field = self._next_editable_generic(
                fields, (self.town_npc_field - 1) % n)
            self.town_npc_buffer = fields[self.town_npc_field].value
            self.town_npc_field_scroll = self._adjust_field_scroll_generic(
                self.town_npc_field, self.town_npc_field_scroll)
        elif event.key == pygame.K_DOWN:
            fe = fields[self.town_npc_field]
            if fe.editable:
                fe.value = self.town_npc_buffer
            self.town_npc_field = self._next_editable_generic(
                fields, (self.town_npc_field + 1) % n)
            self.town_npc_buffer = fields[self.town_npc_field].value
            self.town_npc_field_scroll = self._adjust_field_scroll_generic(
                self.town_npc_field, self.town_npc_field_scroll)
        elif event.key == pygame.K_BACKSPACE:
            self.town_npc_buffer = self.town_npc_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            self.town_npc_buffer += event.unicode

    def handle_mapeditor_input(self, event):
        """Handle input for the Map Editor inside the features screen.

        Reuses the meh_* state variables for section/folder/field browsing.
        When the actual map editor is active, delegates to its handler.
        """
        if event.type != pygame.KEYDOWN:
            return

        # ── Fullscreen map editor active (launched from a template) ──
        if self.meh_editor_active:
            self._meh_input_handler.handle(event)
            return

        # ── Field editor (Settings screen) ──
        if self.meh_level == 1:
            self.handle_meh_field_input(event)
            return

        # ── Naming/renaming overlay ──
        if self.meh_naming:
            self._handle_meh_naming_input(event)
            return

        # ── Section browsing mode ──
        n = len(self.meh_sections)

        if event.key == pygame.K_ESCAPE:
            if self.meh_nav_stack:
                # Pop up one folder level, auto-saving along the way
                (prev_secs, prev_cur, prev_scroll,
                 prev_label) = self.meh_nav_stack.pop()
                self.meh_sections = prev_secs
                self.meh_cursor = prev_cur
                self.meh_scroll = prev_scroll
                self.meh_folder_label = prev_label
                self.save_map_templates()
            else:
                # Auto-save templates, then return to categories
                self.save_map_templates()
                self.level = 0
                self.active_editor = None
            return

        # ── Add new template (Ctrl+N) — only inside a template folder ──
        if self._is_new_shortcut(event) and self.meh_nav_stack:
            folder_key = self._meh_current_folder_key()
            if folder_key and folder_key in self._MEH_FOLDER_DEFAULTS:
                self.meh_naming = True
                self.meh_naming_is_new = True
                self.meh_name_buf = ""
                return

        # ── Delete template (Ctrl+D) — only on template items ──
        if self._is_delete_shortcut(event) and self._meh_is_template_item():
            self.meh_delete_template()
            return

        # ── Rename template (F2) — only on template items ──
        if event.key == pygame.K_F2 and self._meh_is_template_item():
            sec = self.meh_sections[self.meh_cursor]
            self.meh_naming = True
            self.meh_naming_is_new = False
            self.meh_name_buf = sec.get("label", "")
            return

        # ── Save all templates (Ctrl+S) ──
        if self._is_save_shortcut(event):
            self.save_map_templates()
            self.meh_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self.meh_cursor = (self.meh_cursor - 1) % n
        elif event.key == pygame.K_DOWN and n > 0:
            self.meh_cursor = (self.meh_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            sec = self.meh_sections[self.meh_cursor]
            if sec.get("_editor_redirect"):
                # Redirect to a different editor (e.g. tiles, gallery)
                redirect = sec["_editor_redirect"]
                self.launched_from_maps = True
                if redirect == "tiles":
                    self.active_editor = "tiles"
                    self.game.renderer.reload_sprites()
                    self.load_tiles()
                    self.level = 1
                elif redirect == "gallery":
                    self.active_editor = "gallery"
                    self.game.renderer.reload_sprites()
                    self.load_gallery()
                    self.level = 1
            elif sec.get("_template_settings"):
                # Open settings field editor for the parent template
                tmpl = self._meh_get_parent_template()
                if tmpl:
                    self._meh_open_template_settings(tmpl)
            elif sec.get("_template_edit_map"):
                # Launch map editor for the parent template
                tmpl = self._meh_get_parent_template()
                if tmpl:
                    self._meh_launch_editor(tmpl)
            elif sec.get("folder"):
                # Enter folder — use the actual children list (not a copy)
                # so that additions/deletions are reflected in the parent.
                children = sec.get("children")
                if children is None:
                    children = []
                    sec["children"] = children
                self.meh_nav_stack.append((
                    self.meh_sections,
                    self.meh_cursor,
                    self.meh_scroll,
                    self.meh_folder_label,
                ))
                self.meh_sections = children
                self.meh_cursor = 0
                self.meh_scroll = 0
                self.meh_folder_label = sec.get("label", "")
        elif event.key == pygame.K_LEFT:
            if self.meh_nav_stack:
                (prev_secs, prev_cur, prev_scroll,
                 prev_label) = self.meh_nav_stack.pop()
                self.meh_sections = prev_secs
                self.meh_cursor = prev_cur
                self.meh_scroll = prev_scroll
                self.meh_folder_label = prev_label

    def editor_ctx(self):
        """Return a dict of lambdas/refs for the active editor,
        allowing generic level-1 and level-2 logic."""
        ed = self.active_editor
        if ed == "spells":
            return {
                "list": lambda: self.spell_list,
                "cursor": lambda: self.spell_cursor,
                "set_cursor": lambda v: setattr(self, "spell_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "spell_scroll",
                    self._adjust_scroll_generic(
                        self.spell_cursor, self.spell_scroll)),
                "fields": lambda: self.spell_fields,
                "field_idx": lambda: self.spell_field,
                "set_field_idx": lambda v: setattr(self, "spell_field", v),
                "buffer": lambda: self.spell_buffer,
                "set_buffer": lambda v: setattr(self, "spell_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "spell_scroll_f",
                    self._adjust_field_scroll_generic(
                        self.spell_field, self.spell_scroll_f)),
                "build_fields": self.build_spell_fields,
                "save_fields": self.save_spell_fields,
                "save_disk": self.save_spells,
                "set_editing": lambda v: setattr(self, "spell_editing", v),
                "add": self.add_spell,
                "remove": self.remove_spell,
                "get_choices": self.get_spell_choices,
                "needs_live_sync": False,
                "on_choice_change": self.spell_on_choice_change,
                "on_save_exit": self.spell_on_save_exit,
                "on_discard_exit": self.spell_on_discard_exit,
                "on_clean_exit": self.spell_on_clean_exit,
            }
        elif ed == "items":
            return {
                "list": lambda: self.item_list,
                "cursor": lambda: self.item_cursor,
                "set_cursor": lambda v: setattr(self, "item_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "item_scroll",
                    self._adjust_scroll_generic(
                        self.item_cursor, self.item_scroll)),
                "fields": lambda: self.item_fields,
                "field_idx": lambda: self.item_field,
                "set_field_idx": lambda v: setattr(self, "item_field", v),
                "buffer": lambda: self.item_buffer,
                "set_buffer": lambda v: setattr(self, "item_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "item_scroll_f",
                    self._adjust_field_scroll_generic(
                        self.item_field, self.item_scroll_f)),
                "build_fields": self.build_item_fields,
                "save_fields": self.save_item_fields,
                "save_disk": self.save_items,
                "set_editing": lambda v: setattr(self, "item_editing", v),
                "add": self.add_item,
                "remove": self.remove_item,
                "get_choices": self.get_item_choices,
                "needs_live_sync": False,
                "on_choice_change": None,
                "on_save_exit": None,
                "on_discard_exit": None,
                "on_clean_exit": None,
            }
        elif ed == "counters":
            return {
                "list": lambda: self.counter_list,
                "cursor": lambda: self.counter_cursor,
                "set_cursor": lambda v: setattr(self, "counter_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "counter_scroll",
                    self._adjust_scroll_generic(
                        self.counter_cursor, self.counter_scroll)),
                "fields": lambda: self.counter_fields,
                "field_idx": lambda: self.counter_field,
                "set_field_idx": lambda v: setattr(self, "counter_field", v),
                "buffer": lambda: self.counter_buffer,
                "set_buffer": lambda v: setattr(self, "counter_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "counter_scroll_f",
                    self._adjust_field_scroll_generic(
                        self.counter_field, self.counter_scroll_f)),
                "build_fields": self.build_counter_fields,
                "save_fields": self.save_counter_fields,
                "save_disk": self.save_counters,
                "set_editing": lambda v: setattr(self, "counter_editing", v),
                "add": self.add_counter,
                "remove": self.remove_counter,
                "get_choices": self.get_counter_choices,
                "needs_live_sync": False,
                "on_choice_change": None,
                "on_save_exit": None,
                "on_discard_exit": None,
                "on_clean_exit": None,
            }
        elif ed == "monsters":
            return {
                "list": lambda: self.mon_list,
                "cursor": lambda: self.mon_cursor,
                "set_cursor": lambda v: setattr(self, "mon_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "mon_scroll",
                    self._adjust_scroll_generic(
                        self.mon_cursor, self.mon_scroll)),
                "fields": lambda: self.mon_fields,
                "field_idx": lambda: self.mon_field,
                "set_field_idx": lambda v: setattr(self, "mon_field", v),
                "buffer": lambda: self.mon_buffer,
                "set_buffer": lambda v: setattr(self, "mon_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "mon_scroll_f",
                    self._adjust_field_scroll_generic(
                        self.mon_field, self.mon_scroll_f)),
                "build_fields": self.build_mon_fields,
                "save_fields": self.save_mon_fields,
                "save_disk": self.save_monsters,
                "set_editing": lambda v: setattr(self, "mon_editing", v),
                "add": self.add_monster,
                "remove": self.remove_monster,
                "get_choices": self.get_mon_choices,
                "needs_live_sync": False,
                "on_choice_change": None,
                "on_save_exit": None,
                "on_discard_exit": None,
                "on_clean_exit": None,
            }
        elif ed == "tiles":
            return {
                "list": lambda: self.tile_list,
                "cursor": lambda: self.tile_cursor,
                "set_cursor": lambda v: setattr(self, "tile_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "tile_scroll",
                    self._adjust_scroll_generic(
                        self.tile_cursor, self.tile_scroll)),
                "fields": lambda: self.tile_fields,
                "field_idx": lambda: self.tile_field,
                "set_field_idx": lambda v: setattr(self, "tile_field", v),
                "buffer": lambda: self.tile_buffer,
                "set_buffer": lambda v: setattr(self, "tile_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "tile_scroll_f",
                    self._adjust_field_scroll_generic(
                        self.tile_field, self.tile_scroll_f)),
                "build_fields": self.build_tile_fields,
                "save_fields": self.save_tile_fields,
                "save_disk": self.save_tiles,
                "set_editing": lambda v: setattr(self, "tile_editing", v),
                "add": self.add_tile,
                "remove": self.remove_tile,
                "get_choices": self.get_tile_choices,
                "needs_live_sync": True,
                "on_choice_change": None,
                "on_save_exit": None,
                "on_discard_exit": None,
                "on_clean_exit": None,
            }
        return None

    def handle_field_editing(self, event, ctx, ed, exit_level):
        """Unified field-editor input handler.

        Parameters
        ----------
        event      : pygame event (KEYDOWN)
        ctx        : editor context dict from editor_ctx()
        ed         : editor name string ("spells", "items", etc.)
        exit_level : level to return to on ESC (1 for most, 2 for tiles)
        """
        # Editors that need live-sync (save_fields on every change)
        # to support conditional fields or live list-preview updates.
        needs_live_sync = ctx.get("needs_live_sync", False)

        # Editor-specific hooks (may be None for editors that don't need them)
        on_choice_change = ctx.get("on_choice_change")
        on_save_exit = ctx.get("on_save_exit")
        on_discard_exit = ctx.get("on_discard_exit")
        on_clean_exit = ctx.get("on_clean_exit")

        # ── Save shortcut (Ctrl+S) ──
        if self._is_save_shortcut(event):
            ctx["save_fields"]()
            if on_save_exit:
                on_save_exit()
            else:
                ctx["save_disk"]()
            self.dirty = False
            return

        # ── Escape ──
        if event.key == pygame.K_ESCAPE:
            if self.dirty:
                def _save_and_exit():
                    ctx["save_fields"]()
                    if on_save_exit:
                        on_save_exit()
                    else:
                        ctx["save_disk"]()
                    ctx["set_editing"](False)
                    self.level = exit_level
                    self.dirty = False
                def _discard_and_exit():
                    if on_discard_exit:
                        on_discard_exit()
                    ctx["set_editing"](False)
                    self.level = exit_level
                    self.dirty = False
                self.game._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
            else:
                if on_clean_exit:
                    on_clean_exit()
                ctx["set_editing"](False)
                self.level = exit_level
            return

        # ── Read current field state ──
        fields = ctx["fields"]()
        n = len(fields)
        if n == 0:
            return
        field_idx = ctx["field_idx"]()
        entry = fields[field_idx]
        ftype = entry.field_type
        buf = ctx["buffer"]()

        # ── UP / DOWN navigation ──
        if event.key in (pygame.K_UP, pygame.K_DOWN):
            entry.value = buf
            self.dirty = True
            if needs_live_sync:
                ctx["save_fields"]()
                # Re-read — save may have triggered a field rebuild
                fields = ctx["fields"]()
                n = len(fields)
                field_idx = ctx["field_idx"]()
            direction = -1 if event.key == pygame.K_UP else 1
            idx = (field_idx + direction) % n
            idx = self._next_editable_generic(fields, idx)
            ctx["set_field_idx"](idx)
            ctx["set_buffer"](fields[idx].value)
            ctx["adjust_field_scroll"]()

        # ── Choice / Sprite cycling (LEFT / RIGHT) ──
        elif ftype in ("choice", "sprite"):
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                choices = ctx["get_choices"](entry.key)
                if choices:
                    try:
                        ci = choices.index(buf)
                    except ValueError:
                        ci = 0
                    if event.key == pygame.K_RIGHT:
                        ci = (ci + 1) % len(choices)
                    else:
                        ci = (ci - 1) % len(choices)
                    ctx["set_buffer"](choices[ci])
                    entry.value = choices[ci]
                    self.dirty = True
                    if needs_live_sync:
                        ctx["save_fields"]()
                    if on_choice_change:
                        on_choice_change(entry, choices[ci])

        # ── Int field editing ──
        elif ftype == "int":
            if event.key == pygame.K_BACKSPACE:
                ctx["set_buffer"](buf[:-1])
                self.dirty = True
            elif event.key == pygame.K_LEFT:
                try:
                    v = int(buf) - 1
                    ctx["set_buffer"](str(max(0, v)))
                    self.dirty = True
                except ValueError:
                    pass
            elif event.key == pygame.K_RIGHT:
                try:
                    v = int(buf) + 1
                    ctx["set_buffer"](str(v))
                    self.dirty = True
                except ValueError:
                    pass
            elif event.unicode and event.unicode.isdigit():
                ctx["set_buffer"](buf + event.unicode)
                self.dirty = True

        # ── Text field editing ──
        elif ftype == "text":
            if event.key == pygame.K_BACKSPACE:
                ctx["set_buffer"](buf[:-1])
                self.dirty = True
            elif event.unicode and event.unicode.isprintable():
                ctx["set_buffer"](buf + event.unicode)
                self.dirty = True

    def open_from_title(self):
        """Open the Game Features editor from the title screen."""
        self.game.showing_title = False
        self.game.showing_features = True
        self.level = 0
        self.cursor = 0
        self.spell_editing = False

    # ══════════════════════════════════════════════════════════
    # ── Render State ───────────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def get_render_state(self):
        """Build a FeaturesRenderState for the renderer."""
        # Tick down the save flash on the fullscreen map editor state
        mes = getattr(self.game, '_map_editor_state', None)
        if mes and mes.save_flash > 0:
            mes.save_flash = max(0, mes.save_flash - 1.0 / 60)
        # Tick down the hub save flash
        if self.meh_save_flash > 0:
            self.meh_save_flash = max(0, self.meh_save_flash - 1.0 / 60)
        # Tick down the town save flash
        if self.town_save_flash > 0:
            self.town_save_flash = max(0, self.town_save_flash - 1.0 / 60)
        return FeaturesRenderState(
            categories=self.categories,
            cat_cursor=self.cursor,
            level=self.level,
            active_editor=self.active_editor,
            spells=SpellEditorRS(
                list=self.spell_list,
                cursor=self.spell_cursor,
                scroll=self.spell_scroll,
                editing=self.spell_editing,
                fields=self.spell_fields,
                field=self.spell_field,
                buffer=self.spell_buffer,
                field_scroll=self.spell_scroll_f,
                nav=self.spell_nav,
                ctype_cursor=self.spell_ctype_cursor,
                level_cursor=self.spell_level_cursor,
                level_scroll=self.spell_level_scroll,
                sel_ctype=self.spell_sel_ctype,
                sel_level=self.spell_sel_level,
                filtered=self.spell_filtered,
            ),
            items=ItemEditorRS(
                list=self.item_list,
                cursor=self.item_cursor,
                scroll=self.item_scroll,
                editing=self.item_editing,
                fields=self.item_fields,
                field=self.item_field,
                buffer=self.item_buffer,
                field_scroll=self.item_scroll_f,
            ),
            counters=CounterEditorRS(
                list=self.counter_list,
                cursor=self.counter_cursor,
                scroll=self.counter_scroll,
                editing=self.counter_editing,
                fields=self.counter_fields,
                field=self.counter_field,
                buffer=self.counter_buffer,
                field_scroll=self.counter_scroll_f,
                item_list=self.counter_item_list,
                item_cursor=self.counter_item_cursor,
                item_scroll=self.counter_item_scroll,
                items_cache=getattr(self, '_counter_items_cache', None),
            ),
            monsters=MonsterEditorRS(
                list=self.mon_list,
                cursor=self.mon_cursor,
                scroll=self.mon_scroll,
                editing=self.mon_editing,
                fields=self.mon_fields,
                field=self.mon_field,
                buffer=self.mon_buffer,
                field_scroll=self.mon_scroll_f,
            ),
            tiles=TileEditorRS(
                list=self.tile_list,
                folders=self.tile_folders,
                folder_cursor=self.tile_folder_cursor,
                folder_scroll=self.tile_folder_scroll,
                folder_tiles=self.tile_folder_tiles,
                cursor=self.tile_cursor,
                scroll=self.tile_scroll,
                editing=self.tile_editing,
                fields=self.tile_fields,
                field=self.tile_field,
                buffer=self.tile_buffer,
                field_scroll=self.tile_scroll_f,
                spawn_sublist=self.spawn_sublist if self.spawn_sublist_mode else None,
                spawn_sublist_mode=self.spawn_sublist_mode,
                spawn_sublist_cursor=self.spawn_sublist_cursor,
                spawn_sublist_scroll=self.spawn_sublist_scroll,
            ),
            gallery=GalleryEditorRS(
                list=self.gallery_list,
                cat_list=self.gallery_cat_list,
                cat_cursor=self.gallery_cat_cursor,
                cat_scroll=self.gallery_cat_scroll,
                sprites=self.gallery_sprites,
                spr_cursor=self.gallery_spr_cursor,
                spr_scroll=self.gallery_spr_scroll,
                tag_cursor=self.gallery_tag_cursor,
                all_cats=self.gallery_all_cats,
                naming=self.gallery_naming,
                name_buf=self.gallery_name_buf,
                detail_cursor=self.gallery_detail_cursor,
            ),
            pxedit=PixelEditorRS(
                pixels=self.pxedit_pixels,
                cx=self.pxedit_cx,
                cy=self.pxedit_cy,
                w=self.pxedit_w,
                h=self.pxedit_h,
                color_idx=self.pxedit_color_idx,
                palette=self.pxedit_palette,
                focus=self.pxedit_focus,
                painting=self.pxedit_painting,
                replacing=self.pxedit_replacing,
                replace_src_color=self.pxedit_replace_src_color,
                replace_dst=self.pxedit_replace_dst,
                replace_sel=self.pxedit_replace_sel,
            ),
            meh=MapEditorHubRS(
                editor_active=self.meh_editor_active,
                editor_data=(
                    self.game._map_editor_state.to_data_dict()
                    if self.meh_editor_active
                    and self.game._map_editor_state is not None
                    else None),
                sections=self.meh_sections,
                cursor=self.meh_cursor,
                scroll=self.meh_scroll,
                nav_depth=len(self.meh_nav_stack),
                folder_label=self.meh_folder_label,
                level=self.meh_level,
                fields=self.meh_fields,
                field_cursor=self.meh_field,
                field_buffer=self.meh_buffer,
                field_scroll=self.meh_field_scroll,
                naming=self.meh_naming,
                name_buf=self.meh_name_buf,
                naming_is_new=self.meh_naming_is_new,
                save_flash=self.meh_save_flash,
            ),
            towns=TownEditorRS(
                towns=self.town_lists.get("layouts", []),
                cursor=self.town_cursor,
                scroll=self.town_scroll,
                sub_cursor=self.town_sub_cursor,
                sub_items=self.town_sub_items,
                fields=self.town_fields,
                field_cursor=self.town_field,
                field_buffer=self.town_buffer,
                field_scroll=self.town_field_scroll,
                npc_list=self.town_npc_list,
                npc_cursor=self.town_npc_cursor,
                npc_scroll=self.town_npc_scroll,
                npc_fields=self.town_npc_fields,
                npc_field_cursor=self.town_npc_field,
                npc_field_buffer=self.town_npc_buffer,
                npc_field_scroll=self.town_npc_field_scroll,
                editor_active=self.town_editor_active,
                editor_data=(
                    self._town_map_editor_state.to_data_dict()
                    if self.town_editor_active
                    and self._town_map_editor_state is not None
                    else None),
                naming=self.town_naming,
                name_buf=self.town_name_buf,
                naming_is_new=self.town_naming_is_new,
                save_flash=self.town_save_flash,
            ),
            overview_editor_data=(
                self.game._mod_map_editor_state.to_data_dict()
                if getattr(self.game, '_mod_map_editor_state', None) is not None
                else None),
            town_map_editor_data=(
                self.game._mod_town_map_editor_state.to_data_dict()
                if getattr(self.game, '_mod_town_map_editor_state', None) is not None
                else None),
            dungeon_map_editor_data=(
                self.game._mod_dungeon_map_editor_state.to_data_dict()
                if getattr(self.game, '_mod_dungeon_map_editor_state', None) is not None
                else None),
            building_map_editor_data=(
                self.game._mod_building_map_editor_state.to_data_dict()
                if getattr(self.game, '_mod_building_map_editor_state', None) is not None
                else None),
        )

    # ══════════════════════════════════════════════════════════
    # ── Helper Methods ─────────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _next_editable_generic(fields, start):
        """Find next editable field index from start in any field list.

        Supports both FieldEntry dataclass instances and legacy
        positional lists (used by the module editor).
        """
        n = len(fields)
        if n == 0:
            return 0
        idx = start % n
        for _ in range(n):
            entry = fields[idx]
            if isinstance(entry, FieldEntry):
                if entry.editable and entry.field_type != "section":
                    return idx
            else:
                # Legacy list format: [label, key, value, type, editable]
                if len(entry) > 4 and entry[4] and entry[3] != "section":
                    return idx
            idx = (idx + 1) % n
        return start % n

    @staticmethod
    def _adjust_scroll_generic(cursor, scroll, max_visible=14):
        """Generic scroll adjustment. Returns new scroll value."""
        if cursor < scroll:
            return cursor
        if cursor >= scroll + max_visible:
            return cursor - max_visible + 1
        return scroll

    @staticmethod
    def _adjust_field_scroll_generic(field_idx, scroll):
        """Generic field scroll adjustment."""
        row_h = 38
        panel_h = 500
        max_visible = panel_h // row_h
        if field_idx < scroll:
            return field_idx
        if field_idx >= scroll + max_visible:
            return field_idx - max_visible + 1
        return scroll

    @staticmethod
    def _is_save_shortcut(event):
        """Return True if the event is Ctrl+S or Cmd+S (universal save)."""
        if event.key != pygame.K_s:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))

    @staticmethod
    def _is_new_shortcut(event):
        """Return True if the event is Ctrl+N or Cmd+N (universal new)."""
        if event.key != pygame.K_n:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))

    @staticmethod
    def _is_delete_shortcut(event):
        """Return True if the event is Ctrl+D or Cmd+D (universal delete)."""
        if event.key != pygame.K_d:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))

    @staticmethod
    def _is_copy_shortcut(event):
        """Return True if the event is Ctrl+C or Cmd+C (universal copy/duplicate)."""
        if event.key != pygame.K_c:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))
