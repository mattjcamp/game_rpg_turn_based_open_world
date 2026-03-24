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
    MapEditorHubRS,
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

        # Classification of tile IDs into context folders
        self.TILE_CONTEXT = {
            0: "overworld", 1: "overworld", 2: "overworld",
            3: "overworld", 4: "overworld", 5: "overworld",
            6: "overworld", 7: "overworld", 8: "overworld",
            9: "overworld",
            10: "town", 11: "town", 12: "town", 13: "town",
            14: "town", 35: "town",
            30: "town", 31: "town",
            20: "dungeon", 21: "dungeon", 22: "dungeon",
            23: "dungeon", 24: "dungeon", 25: "dungeon",
            26: "dungeon", 27: "dungeon", 28: "dungeon",
            29: "dungeon",
            32: "dungeon", 33: "dungeon", 34: "dungeon",
        }
        self.TILE_FOLDER_ORDER = [
            {"name": "overworld", "label": "Overworld"},
            {"name": "town", "label": "Town"},
            {"name": "dungeon", "label": "Dungeon"},
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
            {"label": "Monsters", "icon": "X"},
            {"label": "Maps", "icon": "E"},
        ]

        # Town layout data
        self.town_lists = {
            "layouts": [], "features": [], "interiors": [],
        }

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
            ("town", "machine"): "procedural",
            ("town", "keyslot"): "procedural",
        }

        # Town template defaults
        self._TOWN_SUB_DEFAULTS = {
            "layouts":   {"name_prefix": "Town Layout",   "width": 18, "height": 19},
            "features":  {"name_prefix": "Town Feature",  "width": 8,  "height": 8},
            "interiors": {"name_prefix": "Interior",      "width": 14, "height": 15},
        }

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
            settings.TILE_DEFS[tid] = tdef
            ctx = entry.get("context")
            if ctx:
                self.TILE_CONTEXT[tid] = ctx

    def tiles_path(self):
        """Path to tile_defs.json."""
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "tile_defs.json")

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
            disk_data[str(tid)] = entry_data

        # Write to data/tile_defs.json
        try:
            with open(self.tiles_path(), "w") as f:
                json.dump(disk_data, f, indent=2)
        except OSError:
            pass

        # Persist sprite assignments to the tile manifest
        self._save_tile_sprites()
        # Invalidate cached town brushes so new/changed tiles appear
        self.townlayout_brushes = None
        return True

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
        real_idx = self.tile_real_index()
        if real_idx >= len(self.tile_list):
            return
        tile = self.tile_list[real_idx]
        if self.tile_fields:
            entry = self.tile_fields[self.tile_field]
            entry.value = self.tile_buffer
        for entry in self.tile_fields:
            key, val = entry.key, entry.value
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
            return ["none", "shop", "sign"]
        if key == "interaction_data":
            # When interaction_type is "shop", offer shop type choices
            real_idx = self.tile_real_index()
            if real_idx < len(self.tile_list):
                tile = self.tile_list[real_idx]
                if tile.get("interaction_type") == "shop":
                    return ["general", "reagent", "weapon", "armor",
                            "magic", "inn", "guild"]
            return []
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
        new_tile = {
            "_tile_id": new_id,
            "name": f"New Tile {new_id}",
            "walkable": True,
            "color": [128, 128, 128],
            "_context": context,
            "interaction_type": "none",
            "interaction_data": "",
        }
        self.tile_list.append(new_tile)
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
            ]
        elif section == "armors":
            fields += [
                FE("-- Armor Stats --", "_hdr2", "", "section", False),
                FE("Evasion", "evasion",
                   str(item.get("evasion", 50)), "int"),
                FE("Slots", "_slots",
                   ", ".join(item.get("slots", []))),
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
            elif key in ("power", "evasion", "buy", "sell"):
                try:
                    item[key] = int(val)
                except ValueError:
                    pass
            elif key in ("ranged", "melee", "throwable", "usable",
                         "stackable", "party_can_equip",
                         "character_can_equip"):
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
                   "character_can_equip"):
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

    def build_mon_fields(self, mon):
        """Build editable field list for a single monster."""
        FE = FieldEntry
        color = mon.get("color", [200, 50, 50])
        color_str = f"{color[0]}, {color[1]}, {color[2]}" \
            if isinstance(color, (list, tuple)) else str(color)
        fields = [
            FE("-- Identity --", "_hdr1", "", "section", False),
            FE("Name", "_name", mon.get("_name", "")),
            FE("Description", "description",
               mon.get("description", "")),
            FE("Tile", "tile", mon.get("tile", ""), "sprite"),
            FE("Color (R,G,B)", "_color", color_str),
            FE("-- Combat Stats --", "_hdr2", "", "section", False),
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
        for entry in self.mon_fields:
            key, val = entry.key, entry.value
            if key.startswith("_") and key not in ("_name", "_color"):
                continue
            if key == "_color":
                try:
                    parts = [int(p.strip()) for p in val.split(",")]
                    if len(parts) == 3:
                        mon["color"] = parts
                except ValueError:
                    pass
            elif key in ("hp", "ac", "attack_bonus", "damage_dice",
                         "damage_sides", "damage_bonus", "xp_reward",
                         "gold_min", "gold_max", "spawn_weight"):
                try:
                    mon[key] = int(val)
                except ValueError:
                    pass
            elif key in ("undead", "humanoid"):
                mon[key] = val == "True"
            else:
                mon[key] = val

    def get_mon_choices(self, key):
        """Return choice options for a monster field."""
        if key == "tile":
            from src import data_registry as DR
            # All sprites tagged with the "monsters" category
            return DR.sprites_for_category("monsters")
        if key in ("undead", "humanoid"):
            return ["True", "False"]
        if key == "terrain":
            return ["land", "sea"]
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
        """Duplicate the selected sprite in the gallery."""
        gi = self.gallery_cur_gi()
        if gi is None:
            return
        src = self.gallery_list[gi]
        dup = dict(src)
        dup["name"] = f"{src['name']}_copy"
        self.gallery_list.append(dup)
        # Keep cursor on the original, move to end
        self.gallery_spr_cursor = min(
            self.gallery_spr_cursor, len(self.gallery_sprites) - 1)

    def gallery_delete(self):
        """Delete the selected sprite from the gallery (mark as unassigned)."""
        gi = self.gallery_cur_gi()
        if gi is None:
            return
        entry = self.gallery_list[gi]
        entry["usable_in"] = ["unassigned"]
        # Rebuild category counts and reload sprites
        self._rebuild_gallery_cats()
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

    def build_map_editor_hub_sections(self):
        """Build the section list for the top-level Map Editor hub.

        Returns 5 sub-folders — one per map type — each containing a
        placeholder example that launches the actual map editor.
        """
        from src.map_editor import (
            STORAGE_DENSE, STORAGE_SPARSE, GRID_SCROLLABLE, GRID_FIXED,
        )

        # Each child stores its editor config so we can launch it
        # ── 1) Overview ──
        overview_children = [
            {
                "label": "Overworld Template",
                "subtitle": "A base layout for the overworld map",
                "map_config": {
                    "storage": STORAGE_DENSE,
                    "grid_type": GRID_SCROLLABLE,
                    "tile_context": "overworld",
                    "width": 48, "height": 48,
                },
            },
        ]
        overview_sec = {
            "label": "Overview Templates",
            "folder": "me_overview",
            "children": overview_children,
            "subtitle": f"{len(overview_children)} template"
                        f"{'s' if len(overview_children) != 1 else ''}",
        }

        # ── 2) Dungeon ──
        dungeon_children = [
            {
                "label": "Goblin Cavern Floor 1",
                "subtitle": "A winding cave system",
                "map_config": {
                    "storage": STORAGE_DENSE,
                    "grid_type": GRID_SCROLLABLE,
                    "tile_context": "dungeon",
                    "width": 32, "height": 32,
                },
            },
        ]
        dungeon_sec = {
            "label": "Dungeon Templates",
            "folder": "me_dungeon",
            "children": dungeon_children,
            "subtitle": f"{len(dungeon_children)} template"
                        f"{'s' if len(dungeon_children) != 1 else ''}",
        }

        # ── 3) Examine Screen ──
        examine_children = [
            {
                "label": "Ancient Shrine",
                "subtitle": "Vignette for examining a tile",
                "map_config": {
                    "storage": STORAGE_SPARSE,
                    "grid_type": GRID_FIXED,
                    "tile_context": "dungeon",
                    "width": 12, "height": 10,
                },
            },
        ]
        examine_sec = {
            "label": "Examine Templates",
            "folder": "me_examine",
            "children": examine_children,
            "subtitle": f"{len(examine_children)} template"
                        f"{'s' if len(examine_children) != 1 else ''}",
        }

        # ── 4) Enclosure ──
        enclosure_children = [
            {
                "label": "Blacksmith Shop",
                "subtitle": "Interior space for a town building",
                "map_config": {
                    "storage": STORAGE_SPARSE,
                    "grid_type": GRID_FIXED,
                    "tile_context": "dungeon",
                    "width": 16, "height": 14,
                },
            },
        ]
        enclosure_sec = {
            "label": "Enclosure Templates",
            "folder": "me_enclosure",
            "children": enclosure_children,
            "subtitle": f"{len(enclosure_children)} template"
                        f"{'s' if len(enclosure_children) != 1 else ''}",
        }

        # ── 5) Battle Screen ──
        battle_children = [
            {
                "label": "Forest Clearing",
                "subtitle": "Battle arena with trees and obstacles",
                "map_config": {
                    "storage": STORAGE_SPARSE,
                    "grid_type": GRID_FIXED,
                    "tile_context": "dungeon",
                    "width": 20, "height": 16,
                },
            },
        ]
        battle_sec = {
            "label": "Battle Templates",
            "folder": "me_battle",
            "children": battle_children,
            "subtitle": f"{len(battle_children)} template"
                        f"{'s' if len(battle_children) != 1 else ''}",
        }

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

        return [overview_sec, dungeon_sec, examine_sec,
                enclosure_sec, battle_sec, tiles_sec]

    def _meh_launch_editor(self, sec):
        """Launch the unified map editor for a Map Editor hub template."""
        from src.map_editor import (
            MapEditorConfig, MapEditorState,
            build_overworld_brushes, build_interior_brushes,
            STORAGE_DENSE, STORAGE_SPARSE,
        )

        mc = sec["map_config"]
        ctx = mc["tile_context"]
        w = mc["width"]
        h = mc["height"]
        storage = mc["storage"]
        grid_type = mc["grid_type"]

        # Build brushes based on tile context
        if ctx == "overworld":
            brushes = build_overworld_brushes(self.TILE_CONTEXT)
        else:
            manifest = {}
            try:
                mpath = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "data", "tile_manifest.json")
                with open(mpath) as f:
                    manifest = json.load(f)
            except (OSError, ValueError):
                pass
            brushes = build_interior_brushes(
                self.TILE_CONTEXT,
                feat_tiles_path=self.tiles_path(),
                manifest=manifest,
                feat_tile_list=getattr(self, "tile_list", None),
            )

        # Build initial tile data
        if storage == STORAGE_DENSE:
            # Fill with grass (tile 0) for overworld or
            # stone floor for dungeons
            default_tile = 0 if ctx == "overworld" else 10
            tiles = [[default_tile] * w for _ in range(h)]
        else:
            # Sparse: start with empty dict; store in the section
            tiles = sec.setdefault("tiles", {})

        def _on_save(st):
            # For hub templates we store tiles back into the section
            if storage == STORAGE_DENSE:
                sec["tiles"] = st.tiles
            # Sparse tiles are already the same dict reference
            st.dirty = False

        def _on_exit(st):
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
            supports_tile_links=False,
            supports_interior_links=(storage == STORAGE_SPARSE),
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

    def handle_meh_field_input(self, event):
        """Handle input in the Map Editor hub field editor."""
        if event.key == pygame.K_ESCAPE:
            self.meh_level = 0
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
            self.meh_field = self._meh_next_editable(fi - 1, -1)
            self.meh_buffer = str(fields[self.meh_field][2])
        elif event.key == pygame.K_DOWN:
            self.meh_field = self._meh_next_editable(fi + 1, 1)
            self.meh_buffer = str(fields[self.meh_field][2])
        elif event.key == pygame.K_RETURN:
            if editable and ftype == "text":
                fields[fi][2] = self.meh_buffer
        elif event.key == pygame.K_BACKSPACE:
            if editable and ftype == "text":
                self.meh_buffer = self.meh_buffer[:-1]
        elif event.unicode and editable and ftype == "text":
            self.meh_buffer += event.unicode

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
                self.meh_sections = list(sec.get("children", []))
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

    # ══════════════════════════════════════════════════════════
    # ── Main Input Handlers ────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def handle_input(self, event):
        """Main input dispatcher for the features editor."""
        self.game._handle_features_input(event)

    def handle_mapeditor_input(self, event):
        """Handle input for the Map Editor inside the features screen."""
        self.game._handle_mapeditor_feat_input(event)

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
            ),
        )
