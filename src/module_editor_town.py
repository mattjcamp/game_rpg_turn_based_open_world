"""Town editor mixin — extracted from game.py to reduce god-class size."""


class ModuleTownEditorMixin:
    """Mixin providing town editing functionality for the Game class."""

    def _mod_town_get_current(self):
        """Return the currently selected town dict, or None."""
        if 0 <= self._mod_town_cursor < len(self._mod_town_list):
            return self._mod_town_list[self._mod_town_cursor]
        return None

    def _mod_town_build_settings_fields(self):
        """Build FieldEntry list for the current town's settings."""
        from src.editor_types import FieldEntry
        town = self._mod_town_get_current()
        if not town:
            self._mod_town_fields = []
            return
        has_tiles = bool(town.get("tiles"))
        map_status = "Map assigned" if has_tiles else "No map"
        self._mod_town_fields = [
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
            FieldEntry("Map Generation", "", "", "section", False),
            FieldEntry("Import Town Template",
                       "_action_import", map_status, "action", True),
            FieldEntry("Generate Town Map",
                       "_action_generate", map_status, "action", True),
        ]
        fe = self.features_editor
        self._mod_town_field = fe._next_editable_generic(
            self._mod_town_fields, 0)
        self._mod_town_buffer = self._mod_town_fields[
            self._mod_town_field].value
        self._mod_town_field_scroll = 0

    def _mod_town_save_settings_fields(self):
        """Write settings fields back into the current town dict."""
        town = self._mod_town_get_current()
        if not town:
            return
        for fe_entry in self._mod_town_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            town[key] = val

    def _mod_town_load_npcs(self):
        """Load NPC list from the current town."""
        town = self._mod_town_get_current()
        if not town:
            self._mod_town_npc_list = []
            return
        self._mod_town_npc_list = list(town.get("npcs", []))
        self._mod_town_npc_cursor = 0
        self._mod_town_npc_scroll = 0

    def _mod_town_save_npcs(self):
        """Write NPC list back into the current town dict."""
        town = self._mod_town_get_current()
        if not town:
            return
        town["npcs"] = list(self._mod_town_npc_list)

    def _mod_town_build_npc_fields(self):
        """Build FieldEntry list for the selected NPC."""
        from src.editor_types import FieldEntry
        if not (0 <= self._mod_town_npc_cursor < len(
                self._mod_town_npc_list)):
            self._mod_town_npc_fields = []
            return
        npc = self._mod_town_npc_list[self._mod_town_npc_cursor]

        # Build sprite choice options from people tile manifest
        if not hasattr(self, "_cc_tiles") or not self._cc_tiles:
            self._cc_load_tiles()
        sprite_names = [t["name"] for t in self._cc_tiles]
        sprite_name_to_file = {t["name"]: t["file"] for t in self._cc_tiles}
        # Reverse lookup: file path -> display name
        sprite_file_to_name = {t["file"]: t["name"] for t in self._cc_tiles}
        current_sprite_file = npc.get("sprite", "")
        current_sprite_name = sprite_file_to_name.get(
            current_sprite_file, sprite_names[0] if sprite_names else "Default")

        self._mod_town_npc_fields = [
            FieldEntry("Name", "name", npc.get("name", ""), "text", True),
            FieldEntry("Type", "npc_type",
                       npc.get("npc_type", "villager"), "text", True),
            FieldEntry("Sprite", "sprite", current_sprite_name,
                       "choice", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Col", "col", str(npc.get("col", 0)), "int", True),
            FieldEntry("Row", "row", str(npc.get("row", 0)), "int", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Dialogue", "dialogue",
                       " | ".join(npc.get("dialogue", ["Hello."])),
                       "text", True),
            FieldEntry("God Name", "god_name",
                       npc.get("god_name", "The Divine"), "text", True),
            FieldEntry("Wander Range", "wander_range",
                       str(npc.get("wander_range", 4)), "int", True),
        ]
        self._mod_town_npc_choice_map = {
            "sprite": sprite_names,
        }
        self._mod_town_npc_sprite_name_to_file = sprite_name_to_file
        fe = self.features_editor
        self._mod_town_npc_field = fe._next_editable_generic(
            self._mod_town_npc_fields, 0)
        self._mod_town_npc_buffer = self._mod_town_npc_fields[
            self._mod_town_npc_field].value
        self._mod_town_npc_field_scroll = 0

    def _mod_town_save_npc_fields(self):
        """Write NPC fields back into the NPC dict."""
        if not (0 <= self._mod_town_npc_cursor < len(
                self._mod_town_npc_list)):
            return
        npc = self._mod_town_npc_list[self._mod_town_npc_cursor]
        for fe_entry in self._mod_town_npc_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            if key == "dialogue":
                val = [s.strip() for s in val.split("|") if s.strip()]
                if not val:
                    val = ["Hello."]
            # Convert sprite display name to file path for storage
            if key == "sprite":
                name_to_file = getattr(self, "_mod_town_npc_sprite_name_to_file", {})
                val = name_to_file.get(val, val)
            npc[key] = val

    def _mod_town_add_new(self, name):
        """Add a new blank town to the module."""
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
        self._mod_town_list.append(new_town)
        self._mod_town_cursor = len(self._mod_town_list) - 1
        self._save_module_towns()

    def _mod_town_add_npc(self):
        """Add a new default NPC to the current town."""
        # Place at the town's entry point so the NPC spawns in the
        # walkable area instead of the void at (1,1).
        town = self._mod_town_get_current()
        ec = town.get("entry_col", 1) if town else 1
        er = town.get("entry_row", 1) if town else 1
        new_npc = {
            "name": "New NPC",
            "npc_type": "villager",
            "sprite": "",
            "col": ec,
            "row": er,
            "dialogue": ["Hello there!"],
            "god_name": "The Divine",
            "wander_range": 4,
        }
        self._mod_town_npc_list.append(new_npc)
        self._mod_town_npc_cursor = len(self._mod_town_npc_list) - 1
        self._mod_town_save_npcs()

    def _mod_town_delete_npc(self):
        """Delete the currently selected NPC."""
        n = len(self._mod_town_npc_list)
        if n == 0:
            return
        self._mod_town_npc_list.pop(self._mod_town_npc_cursor)
        n -= 1
        if n == 0:
            self._mod_town_npc_cursor = 0
        elif self._mod_town_npc_cursor >= n:
            self._mod_town_npc_cursor = n - 1
        self._mod_town_save_npcs()

    def _mod_town_launch_map_editor(self):
        """Launch the map editor for the current town's tile grid."""
        from src.map_editor import (
            MapEditorConfig, MapEditorState, MapEditorInputHandler,
            build_town_brushes,
            STORAGE_SPARSE, GRID_FIXED,
        )
        town = self._mod_town_get_current()
        if not town:
            return
        w = town.get("width", 18)
        h = town.get("height", 19)

        fe = self.features_editor
        saved_all = fe.load_map_templates()
        brushes = build_town_brushes(fe.TILE_CONTEXT,
                                     all_templates=saved_all)

        def on_save(state):
            town["tiles"] = state.tiles
            town["width"] = state.config.width
            town["height"] = state.config.height
            state.dirty = False
            self._save_module_towns()
            self._mod_town_save_flash = 1.5

        def on_exit(st):
            town["tiles"] = st.tiles
            self._save_module_towns()
            # Return to module screen, town sub-selector
            self.showing_features = False
            self.showing_modules = True
            self.module_edit_mode = True
            self._mod_town_editor_active = False
            self._mod_town_map_editor_state = None
            self._mod_town_map_editor_handler = None

        town_name = town.get("name", "Unnamed")
        config = MapEditorConfig(
            title=f"Town: {town_name}",
            storage=STORAGE_SPARSE,
            grid_type=GRID_FIXED,
            width=w,
            height=h,
            tile_context="town",
            brushes=brushes,
            supports_interior_links=True,
            supports_connecting_links=True,
            map_address=f"town:{town_name}",
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
        existing_tiles = dict(town.get("tiles", {}))
        # Build interior_list from the live enclosure list so the "I" key
        # picker can offer them as link targets.  Use _mod_town_enclosures
        # (the in-memory copy) rather than town["interiors"] which may
        # not have been synced yet.
        enc_list = [{"name": e.get("name", "?")}
                    for e in self._mod_town_enclosures]
        state = MapEditorState(config, tiles=existing_tiles,
                               interior_list=enc_list)
        handler = MapEditorInputHandler(
            state, is_save_shortcut=self._is_save_shortcut)
        self._mod_town_map_editor_state = state
        self._mod_town_map_editor_handler = handler
        # Switch to features screen for the map editor
        self._mod_town_editor_active = True
        self.module_edit_mode = False
        self.showing_modules = False
        self.showing_features = True
        fe = self.features_editor
        fe.active_editor = "mod_town_map"
        fe.level = 1

    # ── Town input handlers ──

    def _handle_town_edit_input(self, event):
        """Dispatch town editor input based on module_edit_level.

        Levels:
        4 = town list browser
        5 = sub-screen selector (Settings/Townspeople/Edit Map)
        6 = settings fields OR townspeople NPC list
        7 = NPC field editor
        """
        import pygame

        # ── Map editor active ──
        if self._mod_town_editor_active:
            if self._mod_town_map_editor_handler:
                result = self._mod_town_map_editor_handler.handle(event)
                if result == "exit":
                    self._mod_town_editor_active = False
                    self._mod_town_map_editor_state = None
                    self._mod_town_map_editor_handler = None
            return

        if self.module_edit_level == 7:
            self._handle_mod_town_npc_field_input(event)
            return
        if self.module_edit_level == 6:
            if self._mod_town_sub_cursor == 0:
                self._handle_mod_town_settings_field_input(event)
            elif self._mod_town_sub_cursor == 1:
                self._handle_mod_town_npc_list_input(event)
            elif self._mod_town_sub_cursor == 2:
                if self._mod_town_enc_edit_mode == 3:
                    self._handle_mod_town_enc_npc_field_input(event)
                elif self._mod_town_enc_edit_mode == 2:
                    self._handle_mod_town_enc_npc_list_input(event)
                elif self._mod_town_enc_edit_mode == 1:
                    self._handle_mod_town_enc_sub_input(event)
                else:
                    self._handle_mod_town_enc_list_input(event)
            return
        if self.module_edit_level == 5:
            self._handle_mod_town_sub_input(event)
            return

        # ── Level 4: Town list ──
        if self._mod_town_naming:
            self._handle_mod_town_naming_input(event)
            return

        layouts = self._mod_town_list
        n = len(layouts)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE:
            self._save_module_towns()
            self.module_edit_level = 0
            return
        if self._is_new_shortcut(event):
            self._mod_town_naming = True
            self._mod_town_naming_is_new = True
            self._mod_town_name_buf = ""
            return
        if self._is_delete_shortcut(event) and n > 0:
            layouts.pop(self._mod_town_cursor)
            n -= 1
            if n == 0:
                self._mod_town_cursor = 0
            elif self._mod_town_cursor >= n:
                self._mod_town_cursor = n - 1
            self._save_module_towns()
            return
        if self._is_save_shortcut(event):
            self._save_module_towns()
            self._mod_town_save_flash = 1.5
            return
        if event.key == pygame.K_F2 and n > 0:
            town = self._mod_town_get_current()
            if town:
                self._mod_town_naming = True
                self._mod_town_naming_is_new = False
                self._mod_town_name_buf = town.get("name", "")
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_town_cursor = (self._mod_town_cursor - 1) % n
            self._mod_town_scroll = fe._adjust_scroll_generic(
                self._mod_town_cursor, self._mod_town_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_town_cursor = (self._mod_town_cursor + 1) % n
            self._mod_town_scroll = fe._adjust_scroll_generic(
                self._mod_town_cursor, self._mod_town_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_town_sub_cursor = 0
            self.module_edit_level = 5

    def _handle_mod_town_naming_input(self, event):
        """Handle text input while naming/renaming a town."""
        import pygame
        if event.key == pygame.K_ESCAPE:
            self._mod_town_naming = False
            return
        if event.key == pygame.K_RETURN:
            name = self._mod_town_name_buf.strip()
            if name:
                if self._mod_town_naming_is_new:
                    self._mod_town_add_new(name)
                else:
                    town = self._mod_town_get_current()
                    if town:
                        town["name"] = name
                        self._save_module_towns()
            self._mod_town_naming = False
            return
        if event.key == pygame.K_BACKSPACE:
            self._mod_town_name_buf = self._mod_town_name_buf[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self._mod_town_name_buf += event.unicode

    def _handle_mod_town_sub_input(self, event):
        """Handle input on the sub-screen selector (level 5)."""
        import pygame
        n = len(self._mod_town_sub_items)
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self.module_edit_level = 4
            return
        if event.key == pygame.K_UP:
            self._mod_town_sub_cursor = (self._mod_town_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._mod_town_sub_cursor = (self._mod_town_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self._mod_town_sub_cursor == 0:
                self._mod_town_build_settings_fields()
                self.module_edit_level = 6
            elif self._mod_town_sub_cursor == 1:
                self._mod_town_load_npcs()
                self.module_edit_level = 6
            elif self._mod_town_sub_cursor == 2:
                self._mod_town_load_enclosures()
                self.module_edit_level = 6
            elif self._mod_town_sub_cursor == 3:
                self._mod_town_load_enclosures()
                self._mod_town_launch_map_editor()

    def _handle_mod_town_settings_field_input(self, event):
        """Handle input for town settings field editing (level 6)."""
        import pygame

        # ── Overlay: template picker ──
        if self._mod_town_gen_mode == "pick_template":
            self._handle_mod_town_template_picker(event)
            return
        # ── Overlay: generate form ──
        if self._mod_town_gen_mode == "generate":
            self._handle_mod_town_generate_form(event)
            return

        fields = self._mod_town_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 5
            return

        current_field = fields[self._mod_town_field]

        if self._is_save_shortcut(event):
            if current_field.editable and current_field.field_type != "action":
                current_field.value = self._mod_town_buffer
            self._mod_town_save_settings_fields()
            self._save_module_towns()
            self._mod_town_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            if current_field.editable and current_field.field_type != "action":
                current_field.value = self._mod_town_buffer
            self._mod_town_save_settings_fields()
            self.module_edit_level = 5
            return

        # ── Enter on action fields ──
        if event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if current_field.field_type == "action":
                if current_field.key == "_action_import":
                    self._open_town_template_picker()
                elif current_field.key == "_action_generate":
                    self._open_town_generate_form()
                return

        if event.key == pygame.K_UP:
            if current_field.editable and current_field.field_type != "action":
                current_field.value = self._mod_town_buffer
            self._mod_town_field = fe._next_editable_generic(
                fields, (self._mod_town_field - 1) % n)
            nf = fields[self._mod_town_field]
            self._mod_town_buffer = nf.value if nf.field_type != "action" else ""
            self._mod_town_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_town_field, self._mod_town_field_scroll)
        elif event.key == pygame.K_DOWN:
            if current_field.editable and current_field.field_type != "action":
                current_field.value = self._mod_town_buffer
            self._mod_town_field = fe._next_editable_generic(
                fields, (self._mod_town_field + 1) % n)
            nf = fields[self._mod_town_field]
            self._mod_town_buffer = nf.value if nf.field_type != "action" else ""
            self._mod_town_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_town_field, self._mod_town_field_scroll)
        elif current_field.field_type == "action":
            # Don't allow typing on action fields
            pass
        elif event.key == pygame.K_BACKSPACE:
            self._mod_town_buffer = self._mod_town_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            self._mod_town_buffer += event.unicode

    def _handle_mod_town_npc_list_input(self, event):
        """Handle input for the townspeople NPC list (level 6)."""
        import pygame
        n = len(self._mod_town_npc_list)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._mod_town_save_npcs()
            self.module_edit_level = 5
            return
        if self._is_new_shortcut(event):
            self._mod_town_add_npc()
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_town_delete_npc()
            return
        if self._is_save_shortcut(event):
            self._mod_town_save_npcs()
            self._save_module_towns()
            self._mod_town_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_town_npc_cursor = (
                self._mod_town_npc_cursor - 1) % n
            self._mod_town_npc_scroll = fe._adjust_scroll_generic(
                self._mod_town_npc_cursor, self._mod_town_npc_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_town_npc_cursor = (
                self._mod_town_npc_cursor + 1) % n
            self._mod_town_npc_scroll = fe._adjust_scroll_generic(
                self._mod_town_npc_cursor, self._mod_town_npc_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_town_build_npc_fields()
            self.module_edit_level = 7

    def _mod_town_npc_cycle_choice(self, direction):
        """Cycle the current NPC choice field left (-1) or right (+1)."""
        field = self._mod_town_npc_fields[self._mod_town_npc_field]
        options = self._mod_town_npc_choice_map.get(field.key, [])
        if not options:
            return
        try:
            idx = options.index(field.value)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(options)
        field.value = options[idx]
        self._mod_town_npc_buffer = field.value

    def _handle_mod_town_npc_field_input(self, event):
        """Handle input for NPC field editing (level 7)."""
        import pygame
        fields = self._mod_town_npc_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 6
            return

        if self._is_save_shortcut(event):
            f = fields[self._mod_town_npc_field]
            if f.editable:
                f.value = self._mod_town_npc_buffer
            self._mod_town_save_npc_fields()
            self._mod_town_save_npcs()
            self._save_module_towns()
            self._mod_town_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            f = fields[self._mod_town_npc_field]
            if f.editable:
                f.value = self._mod_town_npc_buffer
            self._mod_town_save_npc_fields()
            self._mod_town_save_npcs()
            self.module_edit_level = 6
            return

        if event.key == pygame.K_UP:
            f = fields[self._mod_town_npc_field]
            if f.editable:
                f.value = self._mod_town_npc_buffer
            self._mod_town_npc_field = fe._next_editable_generic(
                fields, (self._mod_town_npc_field - 1) % n)
            self._mod_town_npc_buffer = fields[
                self._mod_town_npc_field].value
            self._mod_town_npc_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_town_npc_field,
                    self._mod_town_npc_field_scroll))
        elif event.key == pygame.K_DOWN:
            f = fields[self._mod_town_npc_field]
            if f.editable:
                f.value = self._mod_town_npc_buffer
            self._mod_town_npc_field = fe._next_editable_generic(
                fields, (self._mod_town_npc_field + 1) % n)
            self._mod_town_npc_buffer = fields[
                self._mod_town_npc_field].value
            self._mod_town_npc_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_town_npc_field,
                    self._mod_town_npc_field_scroll))
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            f = fields[self._mod_town_npc_field]
            if f.field_type == "choice":
                direction = -1 if event.key == pygame.K_LEFT else 1
                self._mod_town_npc_cycle_choice(direction)
        elif event.key == pygame.K_BACKSPACE:
            f = fields[self._mod_town_npc_field]
            if f.field_type != "choice":
                self._mod_town_npc_buffer = self._mod_town_npc_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            f = fields[self._mod_town_npc_field]
            if f.field_type != "choice":
                self._mod_town_npc_buffer += event.unicode

    # ── Town map generation ──

    def _open_town_template_picker(self):
        """Open the template picker showing town layouts and enclosures.

        Combines town templates from town_templates.json with enclosure
        templates from map_templates.json so the user can import either
        type as a town map.  Each entry is tagged with ``_source`` so
        ``_apply_town_template`` knows how to read its fields.
        """
        fe = self.features_editor
        combined = []

        # ── Town layouts ──
        fe.load_townlayouts()
        for tmpl in fe.town_lists.get("layouts", []):
            tmpl["_source"] = "town"
            combined.append(tmpl)

        # ── Enclosure templates ──
        saved_all = fe.load_map_templates()
        for tmpl in saved_all.get("me_enclosure", []):
            tmpl["_source"] = "enclosure"
            combined.append(tmpl)

        self._mod_town_gen_pick_list = combined
        self._mod_town_gen_pick_cursor = 0
        self._mod_town_gen_pick_scroll = 0
        self._mod_town_gen_mode = "pick_template"

    def _open_town_generate_form(self):
        """Open the procedural generation parameter form."""
        self._mod_town_gen_field = 0
        self._mod_town_gen_size_idx = 1  # medium
        self._mod_town_gen_style_idx = 0  # medieval
        self._mod_town_gen_mode = "generate"

    def _handle_mod_town_template_picker(self, event):
        """Handle input for the town template import picker overlay."""
        import pygame
        templates = self._mod_town_gen_pick_list
        n = len(templates)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE:
            self._mod_town_gen_mode = None
            return
        if not n:
            return
        if event.key == pygame.K_UP:
            self._mod_town_gen_pick_cursor = (
                self._mod_town_gen_pick_cursor - 1) % n
            self._mod_town_gen_pick_scroll = fe._adjust_scroll_generic(
                self._mod_town_gen_pick_cursor,
                self._mod_town_gen_pick_scroll)
        elif event.key == pygame.K_DOWN:
            self._mod_town_gen_pick_cursor = (
                self._mod_town_gen_pick_cursor + 1) % n
            self._mod_town_gen_pick_scroll = fe._adjust_scroll_generic(
                self._mod_town_gen_pick_cursor,
                self._mod_town_gen_pick_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._apply_town_template(
                templates[self._mod_town_gen_pick_cursor])
            self._mod_town_gen_mode = None

    def _handle_mod_town_generate_form(self, event):
        """Handle input for the procedural town generation form."""
        import pygame

        if event.key == pygame.K_ESCAPE:
            self._mod_town_gen_mode = None
            return

        n_fields = 3  # Size, Style, [Generate]
        if event.key == pygame.K_UP:
            self._mod_town_gen_field = (
                self._mod_town_gen_field - 1) % n_fields
        elif event.key == pygame.K_DOWN:
            self._mod_town_gen_field = (
                self._mod_town_gen_field + 1) % n_fields
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            delta = 1 if event.key == pygame.K_RIGHT else -1
            if self._mod_town_gen_field == 0:
                self._mod_town_gen_size_idx = (
                    self._mod_town_gen_size_idx + delta
                ) % len(self._MOD_TOWN_SIZES)
            elif self._mod_town_gen_field == 1:
                self._mod_town_gen_style_idx = (
                    self._mod_town_gen_style_idx + delta
                ) % len(self._MOD_TOWN_STYLES)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self._mod_town_gen_field == 2:
                # Generate!
                self._do_procedural_town_generate()
                self._mod_town_gen_mode = None
            elif self._mod_town_gen_field == 0:
                self._mod_town_gen_size_idx = (
                    self._mod_town_gen_size_idx + 1
                ) % len(self._MOD_TOWN_SIZES)
            elif self._mod_town_gen_field == 1:
                self._mod_town_gen_style_idx = (
                    self._mod_town_gen_style_idx + 1
                ) % len(self._MOD_TOWN_STYLES)

    def _apply_town_template(self, template):
        """Apply a town or enclosure template to the current town."""
        import copy
        town = self._mod_town_get_current()
        if not town:
            return
        town["tiles"] = copy.deepcopy(template.get("tiles", {}))

        source = template.get("_source", "town")
        if source == "enclosure":
            # Enclosure templates store dimensions inside map_config
            mc = template.get("map_config", {})
            town["width"] = mc.get("width", 16)
            town["height"] = mc.get("height", 14)
            # Enclosures have no entry point - default to centre
            town["entry_col"] = town["width"] // 2
            town["entry_row"] = town["height"] // 2
        else:
            town["width"] = template.get("width", 18)
            town["height"] = template.get("height", 19)
            town["entry_col"] = template.get("entry_col", 0)
            town["entry_row"] = template.get("entry_row", 0)
            town["town_style"] = template.get(
                "town_style", town.get("town_style", "medieval"))
            # Import NPCs if present
            if template.get("npcs"):
                town["npcs"] = copy.deepcopy(template["npcs"])
        self._save_module_towns()
        self._mod_town_save_flash = 1.5
        # Refresh the settings fields to show updated values
        self._mod_town_build_settings_fields()

    def _do_procedural_town_generate(self):
        """Procedurally generate a town map and apply it."""
        from src.town_generator import generate_town
        from src.settings import TILE_DEFS
        import random

        town = self._mod_town_get_current()
        if not town:
            return

        size = self._MOD_TOWN_SIZES[self._mod_town_gen_size_idx]
        style = self._MOD_TOWN_STYLES[self._mod_town_gen_style_idx]
        name = town.get("name", "Town")
        seed = random.randint(0, 2 ** 31)

        town_config = {"size": size, "style": style}
        td = generate_town(
            name=name, seed=seed, town_config=town_config,
            layout_index=self._mod_town_cursor)

        # Convert dense TileMap to sparse editor format
        sparse_tiles = {}
        tmap = td.tile_map
        for row in range(tmap.height):
            for col in range(tmap.width):
                tile_id = tmap.get_tile(col, row)
                if tile_id is not None and tile_id != 0:
                    tdef = TILE_DEFS.get(tile_id, {})
                    key = f"{col},{row}"
                    entry = {
                        "tile_id": tile_id,
                        "name": tdef.get("name", f"Tile {tile_id}"),
                    }
                    # Check for sprite overrides
                    if (col, row) in tmap.sprite_overrides:
                        entry["path"] = tmap.sprite_overrides[(col, row)]
                    sparse_tiles[key] = entry

        # Convert NPCs to editor format
        npc_list = []
        for npc in td.npcs:
            npc_dict = {
                "name": npc.name,
                "npc_type": npc.npc_type,
                "col": npc.col,
                "row": npc.row,
                "dialogue": list(npc.dialogue),
                "shop_type": getattr(npc, "shop_type", "general"),
                "god_name": getattr(npc, "god_name", "The Divine"),
                "wander_range": getattr(npc, "wander_range", 4),
            }
            npc_list.append(npc_dict)

        # Apply to current town
        town["tiles"] = sparse_tiles
        town["width"] = tmap.width
        town["height"] = tmap.height
        town["entry_col"] = td.entry_col
        town["entry_row"] = td.entry_row
        town["town_style"] = td.town_style
        town["npcs"] = npc_list

        self._save_module_towns()
        self._mod_town_save_flash = 1.5
        # Refresh the settings fields to show updated values
        self._mod_town_build_settings_fields()

    # ── Enclosure methods ──

    def _mod_town_load_enclosures(self):
        """Load enclosure instances from the current town dict."""
        town = self._mod_town_get_current()
        if not town:
            self._mod_town_enclosures = []
            return
        self._mod_town_enclosures = list(town.get("interiors", []))
        self._mod_town_enc_cursor = 0
        self._mod_town_enc_scroll = 0

    def _mod_town_save_enclosures(self):
        """Write enclosure instances back into the current town dict."""
        town = self._mod_town_get_current()
        if not town:
            return
        town["interiors"] = list(self._mod_town_enclosures)

    def _mod_town_open_enc_picker(self):
        """Open the import picker showing me_enclosure templates.

        A sentinel ``_blank`` entry is prepended so the user can create
        a fresh empty enclosure without choosing a template.
        """
        fe = self.features_editor
        saved = fe.load_map_templates()
        raw = saved.get("me_enclosure", [])
        blank = {"_blank": True, "label": "Create Blank Enclosure",
                 "map_config": {"width": 16, "height": 14}}
        self._mod_town_enc_pick_list = [blank] + list(raw)
        self._mod_town_enc_pick_cursor = 0
        self._mod_town_enc_pick_scroll = 0
        self._mod_town_enc_picking = True

    def _mod_town_generate_enclosure(self, name, template):
        """Create a new enclosure instance from a template."""
        import copy
        mc = template.get("map_config", {})
        instance = {
            "name": name,
            "width": mc.get("width", 16),
            "height": mc.get("height", 14),
            "tiles": copy.deepcopy(template.get("tiles", {})),
            "template_label": template.get("label", "Unknown"),
        }
        self._mod_town_enclosures.append(instance)
        self._mod_town_enc_cursor = len(self._mod_town_enclosures) - 1
        self._mod_town_save_enclosures()
        self._save_module_towns()
        self._mod_town_save_flash = 1.5

    def _mod_town_delete_enclosure(self):
        """Delete the currently selected enclosure instance."""
        n = len(self._mod_town_enclosures)
        if n == 0:
            return
        self._mod_town_enclosures.pop(self._mod_town_enc_cursor)
        n -= 1
        if n == 0:
            self._mod_town_enc_cursor = 0
        elif self._mod_town_enc_cursor >= n:
            self._mod_town_enc_cursor = n - 1
        self._mod_town_save_enclosures()
        self._save_module_towns()

    def _mod_town_launch_enc_editor(self):
        """Launch the map editor for the selected enclosure instance."""
        from src.map_editor import (
            MapEditorConfig, MapEditorState, MapEditorInputHandler,
            build_town_brushes,
            STORAGE_SPARSE, GRID_FIXED,
        )
        if not (0 <= self._mod_town_enc_cursor < len(
                self._mod_town_enclosures)):
            return
        enc = self._mod_town_enclosures[self._mod_town_enc_cursor]
        w = enc.get("width", 16)
        h = enc.get("height", 14)

        fe = self.features_editor
        saved_all = fe.load_map_templates()
        brushes = build_town_brushes(fe.TILE_CONTEXT,
                                     all_templates=saved_all)

        def on_save(state):
            enc["tiles"] = state.tiles
            enc["width"] = state.config.width
            enc["height"] = state.config.height
            state.dirty = False
            self._mod_town_save_enclosures()
            self._save_module_towns()
            self._mod_town_save_flash = 1.5

        def on_exit(st):
            enc["tiles"] = st.tiles
            self._mod_town_save_enclosures()
            self._save_module_towns()
            self.showing_features = False
            self.showing_modules = True
            self.module_edit_mode = True
            self._mod_town_editor_active = False
            self._mod_town_map_editor_state = None
            self._mod_town_map_editor_handler = None

        enc_display = enc.get("name", "Unnamed")
        # Determine parent town name for map address
        _parent_town = ""
        if 0 <= self._mod_town_cursor < len(self._mod_town_list):
            _parent_town = self._mod_town_list[
                self._mod_town_cursor].get("name", "")
        config = MapEditorConfig(
            title=f"Enclosure: {enc_display}",
            storage=STORAGE_SPARSE,
            grid_type=GRID_FIXED,
            width=w,
            height=h,
            tile_context="town",
            brushes=brushes,
            supports_interior_links=True,
            supports_connecting_links=True,
            map_address=f"building:{_parent_town}:{enc_display}",
            link_registry=getattr(self, 'link_registry', None),
            module_maps=getattr(self, '_mod_module_maps', []),
            supports_replace=True,
            on_save=on_save,
            on_exit=on_exit,
            interior_exit_types=[
                {"label": u"\u2190 Return to Town",
                 "link_type": "to_town"},
                {"label": u"\u2190 Return to Overworld",
                 "link_type": "to_overworld"},
            ],
        )
        existing_tiles = dict(enc.get("tiles", {}))
        # Build interior_list from sibling enclosures (excluding current)
        # so the "I" key picker lets this enclosure link to siblings or
        # back to the parent town.
        enc_name = enc.get("name", "")
        sibling_list = [{"name": e.get("name", "?")}
                        for e in self._mod_town_enclosures
                        if e.get("name", "") != enc_name]
        state = MapEditorState(config, tiles=existing_tiles,
                               interior_list=sibling_list)
        handler = MapEditorInputHandler(
            state, is_save_shortcut=self._is_save_shortcut)
        self._mod_town_map_editor_state = state
        self._mod_town_map_editor_handler = handler
        self._mod_town_editor_active = True
        self.module_edit_mode = False
        self.showing_modules = False
        self.showing_features = True
        fe = self.features_editor
        fe.active_editor = "mod_town_map"
        fe.level = 1

    # ── Enclosure sub-screen & NPC editing ──

    def _mod_town_enc_get_current(self):
        """Return the currently selected enclosure dict, or None."""
        if not (0 <= self._mod_town_enc_cursor
                < len(self._mod_town_enclosures)):
            return None
        return self._mod_town_enclosures[self._mod_town_enc_cursor]

    def _mod_town_enc_load_npcs(self):
        """Load NPC list from the currently selected enclosure."""
        enc = self._mod_town_enc_get_current()
        if not enc:
            self._mod_town_enc_npc_list = []
            return
        self._mod_town_enc_npc_list = list(enc.get("npcs", []))
        self._mod_town_enc_npc_cursor = 0
        self._mod_town_enc_npc_scroll = 0

    def _mod_town_enc_save_npcs(self):
        """Write NPC list back into the current enclosure dict."""
        enc = self._mod_town_enc_get_current()
        if not enc:
            return
        enc["npcs"] = list(self._mod_town_enc_npc_list)

    def _mod_town_enc_build_npc_fields(self):
        """Build FieldEntry list for the selected enclosure NPC."""
        from src.editor_types import FieldEntry
        if not (0 <= self._mod_town_enc_npc_cursor
                < len(self._mod_town_enc_npc_list)):
            self._mod_town_enc_npc_fields = []
            return
        npc = self._mod_town_enc_npc_list[self._mod_town_enc_npc_cursor]

        # Build sprite choice options from people tile manifest
        if not hasattr(self, "_cc_tiles") or not self._cc_tiles:
            self._cc_load_tiles()
        sprite_names = [t["name"] for t in self._cc_tiles]
        sprite_name_to_file = {t["name"]: t["file"]
                               for t in self._cc_tiles}
        sprite_file_to_name = {t["file"]: t["name"]
                               for t in self._cc_tiles}
        current_sprite_file = npc.get("sprite", "")
        current_sprite_name = sprite_file_to_name.get(
            current_sprite_file,
            sprite_names[0] if sprite_names else "Default")

        self._mod_town_enc_npc_fields = [
            FieldEntry("Name", "name",
                       npc.get("name", ""), "text", True),
            FieldEntry("Type", "npc_type",
                       npc.get("npc_type", "villager"), "text", True),
            FieldEntry("Sprite", "sprite", current_sprite_name,
                       "choice", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Col", "col",
                       str(npc.get("col", 0)), "int", True),
            FieldEntry("Row", "row",
                       str(npc.get("row", 0)), "int", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Dialogue", "dialogue",
                       " | ".join(npc.get("dialogue", ["Hello."])),
                       "text", True),
            FieldEntry("God Name", "god_name",
                       npc.get("god_name", "The Divine"), "text", True),
            FieldEntry("Wander Range", "wander_range",
                       str(npc.get("wander_range", 4)), "int", True),
        ]
        self._mod_town_enc_npc_choice_map = {
            "sprite": sprite_names,
        }
        self._mod_town_enc_npc_sprite_name_to_file = sprite_name_to_file
        fe = self.features_editor
        self._mod_town_enc_npc_field = fe._next_editable_generic(
            self._mod_town_enc_npc_fields, 0)
        self._mod_town_enc_npc_buffer = self._mod_town_enc_npc_fields[
            self._mod_town_enc_npc_field].value
        self._mod_town_enc_npc_field_scroll = 0

    def _mod_town_enc_save_npc_fields(self):
        """Write NPC fields back into the enclosure NPC dict."""
        if not (0 <= self._mod_town_enc_npc_cursor
                < len(self._mod_town_enc_npc_list)):
            return
        npc = self._mod_town_enc_npc_list[self._mod_town_enc_npc_cursor]
        for fe_entry in self._mod_town_enc_npc_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            if key == "dialogue":
                val = [s.strip() for s in val.split("|")
                       if s.strip()]
                if not val:
                    val = ["Hello."]
            if key == "sprite":
                name_to_file = getattr(
                    self, "_mod_town_enc_npc_sprite_name_to_file", {})
                val = name_to_file.get(val, val)
            npc[key] = val

    def _mod_town_enc_add_npc(self):
        """Add a new default NPC to the current enclosure."""
        enc = self._mod_town_enc_get_current()
        # Place near centre of enclosure
        w = enc.get("width", 16) if enc else 8
        h = enc.get("height", 14) if enc else 7
        new_npc = {
            "name": "New NPC",
            "npc_type": "villager",
            "sprite": "",
            "col": w // 2,
            "row": h // 2,
            "dialogue": ["Hello there!"],
            "god_name": "The Divine",
            "wander_range": 4,
        }
        self._mod_town_enc_npc_list.append(new_npc)
        self._mod_town_enc_npc_cursor = (
            len(self._mod_town_enc_npc_list) - 1)
        self._mod_town_enc_save_npcs()

    def _mod_town_enc_delete_npc(self):
        """Delete the currently selected enclosure NPC."""
        n = len(self._mod_town_enc_npc_list)
        if n == 0:
            return
        self._mod_town_enc_npc_list.pop(self._mod_town_enc_npc_cursor)
        n -= 1
        if n == 0:
            self._mod_town_enc_npc_cursor = 0
        elif self._mod_town_enc_npc_cursor >= n:
            self._mod_town_enc_npc_cursor = n - 1
        self._mod_town_enc_save_npcs()

    def _mod_town_enc_npc_cycle_choice(self, direction):
        """Cycle the current enclosure NPC choice field."""
        field = self._mod_town_enc_npc_fields[
            self._mod_town_enc_npc_field]
        options = self._mod_town_enc_npc_choice_map.get(
            field.key, [])
        if not options:
            return
        try:
            idx = options.index(field.value)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(options)
        field.value = options[idx]
        self._mod_town_enc_npc_buffer = field.value

    # ── Enclosure sub-screen input handler (level 8) ──

    def _handle_mod_town_enc_sub_input(self, event):
        """Handle input on the enclosure sub-screen (enc_edit_mode=1)."""
        import pygame
        n = len(self._mod_town_enc_sub_items)
        if event.key in (pygame.K_ESCAPE, pygame.K_LEFT):
            self._mod_town_enc_edit_mode = 0  # back to enclosure list
            return
        if event.key == pygame.K_UP:
            self._mod_town_enc_sub_cursor = (
                self._mod_town_enc_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._mod_town_enc_sub_cursor = (
                self._mod_town_enc_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self._mod_town_enc_sub_cursor == 0:
                # Townspeople
                self._mod_town_enc_load_npcs()
                self._mod_town_enc_edit_mode = 2
            elif self._mod_town_enc_sub_cursor == 1:
                # Edit Map
                self._mod_town_launch_enc_editor()

    # ── Enclosure NPC list input handler (level 9) ──

    def _handle_mod_town_enc_npc_list_input(self, event):
        """Handle input for the enclosure NPC list (enc_edit_mode=2)."""
        import pygame
        n = len(self._mod_town_enc_npc_list)
        fe = self.features_editor

        if event.key in (pygame.K_ESCAPE, pygame.K_LEFT):
            self._mod_town_enc_save_npcs()
            self._mod_town_save_enclosures()
            self._mod_town_enc_edit_mode = 1
            return
        if self._is_new_shortcut(event):
            self._mod_town_enc_add_npc()
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_town_enc_delete_npc()
            return
        if self._is_save_shortcut(event):
            self._mod_town_enc_save_npcs()
            self._mod_town_save_enclosures()
            self._save_module_towns()
            self._mod_town_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_town_enc_npc_cursor = (
                self._mod_town_enc_npc_cursor - 1) % n
            self._mod_town_enc_npc_scroll = fe._adjust_scroll_generic(
                self._mod_town_enc_npc_cursor,
                self._mod_town_enc_npc_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_town_enc_npc_cursor = (
                self._mod_town_enc_npc_cursor + 1) % n
            self._mod_town_enc_npc_scroll = fe._adjust_scroll_generic(
                self._mod_town_enc_npc_cursor,
                self._mod_town_enc_npc_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_town_enc_build_npc_fields()
            self._mod_town_enc_edit_mode = 3

    # ── Enclosure NPC field editor input handler (enc_edit_mode=3) ──

    def _handle_mod_town_enc_npc_field_input(self, event):
        """Handle input for enclosure NPC field editing (enc_edit_mode=3)."""
        import pygame
        fields = self._mod_town_enc_npc_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self._mod_town_enc_edit_mode = 2
            return

        if self._is_save_shortcut(event):
            f = fields[self._mod_town_enc_npc_field]
            if f.editable:
                f.value = self._mod_town_enc_npc_buffer
            self._mod_town_enc_save_npc_fields()
            self._mod_town_enc_save_npcs()
            self._mod_town_save_enclosures()
            self._save_module_towns()
            self._mod_town_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            f = fields[self._mod_town_enc_npc_field]
            if f.editable:
                f.value = self._mod_town_enc_npc_buffer
            self._mod_town_enc_save_npc_fields()
            self._mod_town_enc_save_npcs()
            self._mod_town_save_enclosures()
            self._mod_town_enc_edit_mode = 2
            return

        if event.key == pygame.K_UP:
            f = fields[self._mod_town_enc_npc_field]
            if f.editable:
                f.value = self._mod_town_enc_npc_buffer
            self._mod_town_enc_npc_field = fe._next_editable_generic(
                fields, (self._mod_town_enc_npc_field - 1) % n)
            self._mod_town_enc_npc_buffer = fields[
                self._mod_town_enc_npc_field].value
            self._mod_town_enc_npc_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_town_enc_npc_field,
                    self._mod_town_enc_npc_field_scroll))
        elif event.key == pygame.K_DOWN:
            f = fields[self._mod_town_enc_npc_field]
            if f.editable:
                f.value = self._mod_town_enc_npc_buffer
            self._mod_town_enc_npc_field = fe._next_editable_generic(
                fields, (self._mod_town_enc_npc_field + 1) % n)
            self._mod_town_enc_npc_buffer = fields[
                self._mod_town_enc_npc_field].value
            self._mod_town_enc_npc_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_town_enc_npc_field,
                    self._mod_town_enc_npc_field_scroll))
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            f = fields[self._mod_town_enc_npc_field]
            if f.field_type == "choice":
                direction = (-1 if event.key == pygame.K_LEFT
                             else 1)
                self._mod_town_enc_npc_cycle_choice(direction)
        elif event.key == pygame.K_BACKSPACE:
            f = fields[self._mod_town_enc_npc_field]
            if f.field_type != "choice":
                self._mod_town_enc_npc_buffer = (
                    self._mod_town_enc_npc_buffer[:-1])
        elif event.unicode and event.unicode.isprintable():
            f = fields[self._mod_town_enc_npc_field]
            if f.field_type != "choice":
                self._mod_town_enc_npc_buffer += event.unicode
