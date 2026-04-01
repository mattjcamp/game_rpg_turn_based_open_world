"""Dungeon editor mixin — extracted from game.py to reduce god-class size."""


class ModuleDungeonEditorMixin:
    """Mixin providing dungeon editing functionality for the Game class."""

    def _mod_dungeon_get_current(self):
        """Return the currently selected dungeon dict, or None."""
        if 0 <= self._mod_dungeon_cursor < len(self._mod_dungeon_list):
            return self._mod_dungeon_list[self._mod_dungeon_cursor]
        return None

    # Valid options for choice fields
    _DUNGEON_MODE_OPTIONS = ["procedural", "custom"]
    _DUNGEON_STYLE_OPTIONS = ["cave", "crypt", "sewer", "mine", "ruins",
                              "temple", "fortress"]
    _DUNGEON_SIZE_OPTIONS = ["small", "medium", "large"]
    _DUNGEON_DIFFICULTY_OPTIONS = ["easy", "normal", "hard", "deadly"]
    _DUNGEON_TORCH_OPTIONS = ["none", "sparse", "moderate", "abundant"]

    def _mod_dungeon_add_new(self, name):
        """Add a new blank dungeon with one default level."""
        new_dungeon = {
            "name": name,
            "description": "",
            "mode": "procedural",
            "dungeon_style": "cave",
            # Procedural parameters
            "num_levels": 3,
            "difficulty": "normal",
            "level_size": "medium",
            "torch_density": "moderate",
            # Custom dungeons use levels array
            "levels": [
                {
                    "name": "Level 1",
                    "width": 20,
                    "height": 20,
                    "entry_col": 0,
                    "entry_row": 0,
                    "tiles": {},
                    "encounters": [],
                },
            ],
        }
        self._mod_dungeon_list.append(new_dungeon)
        self._mod_dungeon_cursor = len(self._mod_dungeon_list) - 1
        self._save_module_dungeons()

    def _mod_dungeon_build_settings_fields(self):
        """Build FieldEntry list for the current dungeon's top-level settings.

        The field list changes based on the dungeon mode:
        - 'procedural': shows generation parameters (# Levels, Difficulty,
          Level Size, Torch Density)
        - 'custom': shows only Name, Description, Style (levels are edited
          via the Levels sub-screen)
        """
        from src.editor_types import FieldEntry
        dungeon = self._mod_dungeon_get_current()
        if not dungeon:
            self._mod_dungeon_fields = []
            return

        mode = dungeon.get("mode", "procedural")

        # Common fields
        fields = [
            FieldEntry("Name", "name",
                       dungeon.get("name", ""), "text", True),
            FieldEntry("Description", "description",
                       dungeon.get("description", ""), "text", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Mode", "mode", mode, "choice", True),
            FieldEntry("Style", "dungeon_style",
                       dungeon.get("dungeon_style", "cave"), "choice", True),
        ]

        if mode == "procedural":
            fields.extend([
                FieldEntry("", "", "", "section", False),
                FieldEntry("# Levels", "num_levels",
                           str(dungeon.get("num_levels", 3)), "int", True),
                FieldEntry("Difficulty", "difficulty",
                           dungeon.get("difficulty", "normal"),
                           "choice", True),
                FieldEntry("Level Size", "level_size",
                           dungeon.get("level_size", "medium"),
                           "choice", True),
                FieldEntry("Torch Density", "torch_density",
                           dungeon.get("torch_density", "moderate"),
                           "choice", True),
            ])

        # Map field keys to their valid options for choice cycling
        self._mod_dungeon_choice_map = {
            "mode": self._DUNGEON_MODE_OPTIONS,
            "dungeon_style": self._DUNGEON_STYLE_OPTIONS,
            "difficulty": self._DUNGEON_DIFFICULTY_OPTIONS,
            "level_size": self._DUNGEON_SIZE_OPTIONS,
            "torch_density": self._DUNGEON_TORCH_OPTIONS,
        }

        self._mod_dungeon_fields = fields
        fe = self.features_editor
        self._mod_dungeon_field = fe._next_editable_generic(
            self._mod_dungeon_fields, 0)
        self._mod_dungeon_buffer = self._mod_dungeon_fields[
            self._mod_dungeon_field].value
        self._mod_dungeon_field_scroll = 0

    def _mod_dungeon_cycle_choice(self, direction):
        """Cycle the current choice field left (-1) or right (+1)."""
        field = self._mod_dungeon_fields[self._mod_dungeon_field]
        options = self._mod_dungeon_choice_map.get(field.key, [])
        if not options:
            return
        try:
            idx = options.index(field.value)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(options)
        field.value = options[idx]
        self._mod_dungeon_buffer = field.value

        # If "mode" changed, rebuild the field list to show/hide
        # procedural parameters
        if field.key == "mode":
            self._mod_dungeon_save_settings_fields()
            self._mod_dungeon_build_settings_fields()

    def _mod_dungeon_save_settings_fields(self):
        """Write settings fields back into the current dungeon dict."""
        dungeon = self._mod_dungeon_get_current()
        if not dungeon:
            return
        for fe_entry in self._mod_dungeon_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            dungeon[key] = val

    # ── Level helpers (inside a dungeon) ──

    def _mod_dungeon_load_levels(self):
        """Load level list from the current dungeon."""
        dungeon = self._mod_dungeon_get_current()
        if not dungeon:
            self._mod_dungeon_level_list = []
            return
        self._mod_dungeon_level_list = dungeon.get("levels", [])
        self._mod_dungeon_level_cursor = 0
        self._mod_dungeon_level_scroll = 0

    def _mod_dungeon_get_current_level(self):
        """Return the currently selected level dict, or None."""
        if 0 <= self._mod_dungeon_level_cursor < len(
                self._mod_dungeon_level_list):
            return self._mod_dungeon_level_list[
                self._mod_dungeon_level_cursor]
        return None

    def _mod_dungeon_add_level(self, name):
        """Add a new blank level to the current dungeon."""
        new_level = {
            "name": name,
            "width": 20,
            "height": 20,
            "entry_col": 0,
            "entry_row": 0,
            "tiles": {},
            "encounters": [],
        }
        self._mod_dungeon_level_list.append(new_level)
        self._mod_dungeon_level_cursor = len(
            self._mod_dungeon_level_list) - 1
        self._save_module_dungeons()

    def _mod_dungeon_delete_level(self):
        """Delete the currently selected level."""
        n = len(self._mod_dungeon_level_list)
        if n == 0:
            return
        self._mod_dungeon_level_list.pop(self._mod_dungeon_level_cursor)
        n -= 1
        if n == 0:
            self._mod_dungeon_level_cursor = 0
        elif self._mod_dungeon_level_cursor >= n:
            self._mod_dungeon_level_cursor = n - 1
        self._save_module_dungeons()

    # ── Encounter helpers (inside a level) ──

    def _mod_dungeon_load_encounters(self):
        """Load encounter list from the current level."""
        level = self._mod_dungeon_get_current_level()
        if not level:
            self._mod_dungeon_encounter_list = []
            return
        self._mod_dungeon_encounter_list = level.get("encounters", [])
        self._mod_dungeon_encounter_cursor = 0
        self._mod_dungeon_encounter_scroll = 0

    def _mod_dungeon_save_encounters(self):
        """Write encounter list back into the current level dict."""
        level = self._mod_dungeon_get_current_level()
        if not level:
            return
        level["encounters"] = list(self._mod_dungeon_encounter_list)

    def _mod_dungeon_add_encounter(self):
        """Add a new default encounter to the current level."""
        new_encounter = {
            "name": "New Encounter",
            "placement": "procedural",
            "monsters": [],
            "level": 1,
        }
        self._mod_dungeon_encounter_list.append(new_encounter)
        self._mod_dungeon_encounter_cursor = len(
            self._mod_dungeon_encounter_list) - 1
        self._mod_dungeon_save_encounters()

    def _mod_dungeon_delete_encounter(self):
        """Delete the currently selected encounter."""
        n = len(self._mod_dungeon_encounter_list)
        if n == 0:
            return
        self._mod_dungeon_encounter_list.pop(
            self._mod_dungeon_encounter_cursor)
        n -= 1
        if n == 0:
            self._mod_dungeon_encounter_cursor = 0
        elif self._mod_dungeon_encounter_cursor >= n:
            self._mod_dungeon_encounter_cursor = n - 1
        self._mod_dungeon_save_encounters()

    def _mod_dungeon_open_encounter_editor(self):
        """Prepare state for the encounter editor screen."""
        if not (0 <= self._mod_dungeon_encounter_cursor < len(
                self._mod_dungeon_encounter_list)):
            return
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        # Migrate legacy format if needed
        if "monsters" not in enc:
            mid = enc.get("monster_id", "")
            cnt = max(1, int(enc.get("count", 1)))
            enc["monsters"] = [mid] * cnt if mid else []
            enc.setdefault("placement", "procedural")
        enc.setdefault("placement", "procedural")
        enc.setdefault("monsters", [])
        # Reset cursor state
        self._mod_dungeon_enc_cursor = 0
        self._mod_dungeon_enc_editing = False
        self._mod_dungeon_enc_buffer = ""
        self._mod_dungeon_enc_monster_cursor = 0

    def _mod_dungeon_get_enc_rows(self):
        """Return the list of row descriptors for the encounter editor.

        Each row is a dict with 'type' and relevant keys:
          {'type': 'name', 'value': str}
          {'type': 'position'}   — toggle Procedural/Manual, Enter toggles
          {'type': 'place_on_map'}  — action row to open placement view
                                     (only when placement == manual)
          {'type': 'section'}
          {'type': 'monster', 'index': int, 'name': str}
        """
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        placement = enc.get("placement", "procedural")
        rows = [
            {"type": "name", "value": enc.get("name", "")},
            {"type": "position"},
        ]
        if placement == "manual":
            rows.append({"type": "place_on_map"})
        rows.append({"type": "section"})
        for i, mname in enumerate(enc.get("monsters", [])):
            rows.append({"type": "monster", "index": i, "name": mname})
        return rows

    def _mod_dungeon_save_enc_field(self, row_desc, value):
        """Save a single encounter field back to the encounter dict."""
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        rt = row_desc["type"]
        if rt == "name":
            enc["name"] = value

    def _mod_dungeon_enc_open_placement(self):
        """Open the map placement view for the current encounter."""
        level = self._mod_dungeon_get_current_level()
        if not level:
            return
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        # Start cursor at existing position or level entry point
        if enc.get("placement") == "manual":
            self._mod_dungeon_enc_place_col = enc.get("col", 0)
            self._mod_dungeon_enc_place_row = enc.get("row", 0)
        else:
            self._mod_dungeon_enc_place_col = level.get("entry_col", 0)
            self._mod_dungeon_enc_place_row = level.get("entry_row", 0)
        self._mod_dungeon_enc_placing = True

    def _mod_dungeon_enc_set_position(self, col, row):
        """Set the current encounter to manual placement at (col, row)."""
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        enc["placement"] = "manual"
        enc["col"] = col
        enc["row"] = row

    def _mod_dungeon_enc_clear_position(self):
        """Clear placement — set encounter back to procedural."""
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        enc["placement"] = "procedural"
        enc.pop("col", None)
        enc.pop("row", None)

    def _mod_dungeon_enc_add_monster(self, monster_name):
        """Add a monster to the current encounter's monster list."""
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        enc.setdefault("monsters", []).append(monster_name)

    def _mod_dungeon_enc_remove_monster(self):
        """Remove the selected monster from the encounter's monster list."""
        enc = self._mod_dungeon_encounter_list[
            self._mod_dungeon_encounter_cursor]
        monsters = enc.get("monsters", [])
        rows = self._mod_dungeon_get_enc_rows()
        if self._mod_dungeon_enc_cursor >= len(rows):
            return
        row = rows[self._mod_dungeon_enc_cursor]
        if row["type"] == "monster" and row["index"] < len(monsters):
            monsters.pop(row["index"])

    def _mod_dungeon_get_all_monster_names(self):
        """Return sorted list of all available monster names."""
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "monsters.json")
        try:
            with open(path) as f:
                data = json.load(f)
            return sorted(data.get("monsters", {}).keys())
        except (OSError, ValueError):
            return []

    def _mod_dungeon_open_monster_picker(self):
        """Open the monster picker overlay."""
        self._mod_dungeon_enc_picker_monsters = (
            self._mod_dungeon_get_all_monster_names())
        self._mod_dungeon_enc_picker_cursor = 0
        self._mod_dungeon_enc_picker_scroll = 0

    # ── Map editor for a dungeon level ──

    def _mod_dungeon_launch_map_editor(self):
        """Launch the map editor for the current dungeon level."""
        from src.map_editor import (
            MapEditorConfig, MapEditorState, MapEditorInputHandler,
            build_town_brushes,
            STORAGE_SPARSE, GRID_FIXED,
        )
        level = self._mod_dungeon_get_current_level()
        if not level:
            return
        w = level.get("width", 20)
        h = level.get("height", 20)

        fe = self.features_editor
        saved_all = fe.load_map_templates()
        brushes = build_town_brushes(fe.TILE_CONTEXT,
                                     all_templates=saved_all)
        dungeon = self._mod_dungeon_get_current()
        dungeon_name = dungeon.get("name", "Dungeon") if dungeon else "Dungeon"
        level_name = level.get("name", "Unnamed")

        # Build interior list from sibling levels so they can link
        level_list = [
            {"name": lv.get("name", "?")}
            for lv in self._mod_dungeon_level_list
        ]

        def on_save(state):
            level["tiles"] = state.tiles
            level["width"] = state.config.width
            level["height"] = state.config.height
            state.dirty = False
            self._save_module_dungeons()
            self._mod_dungeon_save_flash = 1.5

        def on_exit(st):
            level["tiles"] = st.tiles
            self._save_module_dungeons()
            self.showing_features = False
            self.showing_modules = True
            self.module_edit_mode = True
            self._mod_dungeon_editor_active = False
            self._mod_dungeon_map_editor_state = None
            self._mod_dungeon_map_editor_handler = None

        config = MapEditorConfig(
            title=f"{dungeon_name}: {level_name}",
            storage=STORAGE_SPARSE,
            grid_type=GRID_FIXED,
            width=w,
            height=h,
            tile_context="town",
            brushes=brushes,
            supports_interior_links=True,
            supports_connecting_links=True,
            map_address=f"dungeon:{dungeon_name}:{level_name}",
            link_registry=getattr(self, 'link_registry', None),
            module_maps=getattr(self, '_mod_module_maps', []),
            supports_replace=True,
            on_save=on_save,
            on_exit=on_exit,
            interior_exit_types=[
                {"label": u"\u2190 Return to Overworld",
                 "link_type": "to_overworld"},
            ],
        )
        existing_tiles = dict(level.get("tiles", {}))
        state = MapEditorState(config, tiles=existing_tiles,
                               interior_list=level_list)
        handler = MapEditorInputHandler(
            state, is_save_shortcut=self._is_save_shortcut)
        self._mod_dungeon_map_editor_state = state
        self._mod_dungeon_map_editor_handler = handler
        self._mod_dungeon_editor_active = True
        self.module_edit_mode = False
        self.showing_modules = False
        self.showing_features = True
        fe = self.features_editor
        fe.active_editor = "mod_dungeon_map"
        fe.level = 1

    # ── Dungeon input handlers ──

    def _handle_dungeon_edit_input(self, event):
        """Dispatch dungeon editor input based on module_edit_level.

        Levels:
        8  = dungeon list browser
        9  = dungeon sub-screen (Settings / Levels)
        10 = settings fields OR level list
        11 = level sub-screen (Edit Map / Encounters)
        12 = encounter list
        13 = encounter field editor
        """
        import pygame

        # ── Map editor active (takes over everything) ──
        if self._mod_dungeon_editor_active:
            if self._mod_dungeon_map_editor_handler:
                result = self._mod_dungeon_map_editor_handler.handle(event)
                if result == "exit":
                    self._mod_dungeon_editor_active = False
                    self._mod_dungeon_map_editor_state = None
                    self._mod_dungeon_map_editor_handler = None
            return

        if self.module_edit_level == 13:
            if self._mod_dungeon_enc_placing:
                self._handle_mod_dungeon_enc_placement_input(event)
            elif self._mod_dungeon_enc_picker_active:
                self._handle_mod_dungeon_monster_picker_input(event)
            else:
                self._handle_mod_dungeon_encounter_field_input(event)
            return
        if self.module_edit_level == 12:
            self._handle_mod_dungeon_encounter_list_input(event)
            return
        if self.module_edit_level == 11:
            self._handle_mod_dungeon_level_sub_input(event)
            return
        if self.module_edit_level == 10:
            if self._mod_dungeon_sub_cursor == 0:
                self._handle_mod_dungeon_settings_field_input(event)
            elif self._mod_dungeon_sub_cursor == 1:
                self._handle_mod_dungeon_level_list_input(event)
            return
        if self.module_edit_level == 9:
            self._handle_mod_dungeon_sub_input(event)
            return

        # ── Level 8: Dungeon list ──
        if self._mod_dungeon_naming:
            self._handle_mod_dungeon_naming_input(event)
            return

        layouts = self._mod_dungeon_list
        n = len(layouts)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE:
            self._save_module_dungeons()
            self.module_edit_level = 0
            return
        if self._is_new_shortcut(event):
            self._mod_dungeon_naming = True
            self._mod_dungeon_naming_is_new = True
            self._mod_dungeon_naming_target = "dungeon"
            self._mod_dungeon_name_buf = ""
            return
        if self._is_delete_shortcut(event) and n > 0:
            layouts.pop(self._mod_dungeon_cursor)
            n -= 1
            if n == 0:
                self._mod_dungeon_cursor = 0
            elif self._mod_dungeon_cursor >= n:
                self._mod_dungeon_cursor = n - 1
            self._save_module_dungeons()
            return
        if self._is_save_shortcut(event):
            self._save_module_dungeons()
            self._mod_dungeon_save_flash = 1.5
            return
        if event.key == pygame.K_F2 and n > 0:
            dungeon = self._mod_dungeon_get_current()
            if dungeon:
                self._mod_dungeon_naming = True
                self._mod_dungeon_naming_is_new = False
                self._mod_dungeon_naming_target = "dungeon"
                self._mod_dungeon_name_buf = dungeon.get("name", "")
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_dungeon_cursor = (self._mod_dungeon_cursor - 1) % n
            self._mod_dungeon_scroll = fe._adjust_scroll_generic(
                self._mod_dungeon_cursor, self._mod_dungeon_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_dungeon_cursor = (self._mod_dungeon_cursor + 1) % n
            self._mod_dungeon_scroll = fe._adjust_scroll_generic(
                self._mod_dungeon_cursor, self._mod_dungeon_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_dungeon_sub_cursor = 0
            self.module_edit_level = 9

    def _handle_mod_dungeon_naming_input(self, event):
        """Handle text input while naming/renaming a dungeon or level."""
        import pygame
        if event.key == pygame.K_ESCAPE:
            self._mod_dungeon_naming = False
            return
        if event.key == pygame.K_RETURN:
            name = self._mod_dungeon_name_buf.strip()
            if name:
                target = self._mod_dungeon_naming_target
                if target == "dungeon":
                    if self._mod_dungeon_naming_is_new:
                        self._mod_dungeon_add_new(name)
                    else:
                        dungeon = self._mod_dungeon_get_current()
                        if dungeon:
                            dungeon["name"] = name
                            self._save_module_dungeons()
                elif target == "level":
                    if self._mod_dungeon_naming_is_new:
                        self._mod_dungeon_add_level(name)
                    else:
                        level = self._mod_dungeon_get_current_level()
                        if level:
                            level["name"] = name
                            self._save_module_dungeons()
            self._mod_dungeon_naming = False
            return
        if event.key == pygame.K_BACKSPACE:
            self._mod_dungeon_name_buf = self._mod_dungeon_name_buf[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self._mod_dungeon_name_buf += event.unicode

    def _mod_dungeon_refresh_sub_items(self):
        """Rebuild the sub-screen item list based on dungeon mode.

        Procedural dungeons show only Settings.
        Custom dungeons show Settings + Levels.
        """
        dungeon = self._mod_dungeon_get_current()
        mode = dungeon.get("mode", "procedural") if dungeon else "procedural"
        if mode == "custom":
            self._mod_dungeon_sub_items = ["Settings", "Levels"]
        else:
            self._mod_dungeon_sub_items = ["Settings"]
        if self._mod_dungeon_sub_cursor >= len(self._mod_dungeon_sub_items):
            self._mod_dungeon_sub_cursor = 0

