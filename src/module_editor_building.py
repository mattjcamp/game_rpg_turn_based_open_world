"""Building editor mixin — extracted from game.py to reduce god-class size."""


class ModuleBuildingEditorMixin:
    """Mixin providing building editing functionality for the Game class."""

    def _mod_building_get_current(self):
        """Return the currently selected building dict, or None."""
        if 0 <= self._mod_building_cursor < len(self._mod_building_list):
            return self._mod_building_list[self._mod_building_cursor]
        return None

    # Valid options for choice fields
    def _mod_building_add_new(self, name):
        """Add a new blank building with one default space."""
        new_building = {
            "name": name,
            "description": "",
            "spaces": [
                {
                    "name": "Main Hall",
                    "width": 20,
                    "height": 20,
                    "entry_col": 0,
                    "entry_row": 0,
                    "tiles": {},
                    "encounters": [],
                },
            ],
        }
        self._mod_building_list.append(new_building)
        self._mod_building_cursor = len(self._mod_building_list) - 1
        self._save_module_buildings()

    def _mod_building_build_settings_fields(self):
        """Build FieldEntry list for the current building's settings."""
        from src.editor_types import FieldEntry
        building = self._mod_building_get_current()
        if not building:
            self._mod_building_fields = []
            return

        fields = [
            FieldEntry("Name", "name",
                       building.get("name", ""), "text", True),
            FieldEntry("Description", "description",
                       building.get("description", ""), "text", True),
        ]

        self._mod_building_choice_map = {}

        self._mod_building_fields = fields
        fe = self.features_editor
        self._mod_building_field = fe._next_editable_generic(
            self._mod_building_fields, 0)
        self._mod_building_buffer = self._mod_building_fields[
            self._mod_building_field].value
        self._mod_building_field_scroll = 0

    def _mod_building_cycle_choice(self, direction):
        """Cycle the current choice field left (-1) or right (+1)."""
        field = self._mod_building_fields[self._mod_building_field]
        options = self._mod_building_choice_map.get(field.key, [])
        if not options:
            return
        try:
            idx = options.index(field.value)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(options)
        field.value = options[idx]
        self._mod_building_buffer = field.value

    def _mod_building_save_settings_fields(self):
        """Write settings fields back into the current building dict."""
        building = self._mod_building_get_current()
        if not building:
            return
        for fe_entry in self._mod_building_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            building[key] = val

    # ── Space helpers (inside a building) ──

    def _mod_building_load_spaces(self):
        """Load space list from the current building."""
        building = self._mod_building_get_current()
        if not building:
            self._mod_building_space_list = []
            return
        self._mod_building_space_list = building.get("spaces", [])
        self._mod_building_space_cursor = 0
        self._mod_building_space_scroll = 0

    def _mod_building_get_current_space(self):
        """Return the currently selected space dict, or None."""
        if 0 <= self._mod_building_space_cursor < len(
                self._mod_building_space_list):
            return self._mod_building_space_list[
                self._mod_building_space_cursor]
        return None

    def _mod_building_add_space(self, name):
        """Add a new blank space to the current building."""
        new_space = {
            "name": name,
            "width": 20,
            "height": 20,
            "entry_col": 0,
            "entry_row": 0,
            "tiles": {},
            "encounters": [],
        }
        self._mod_building_space_list.append(new_space)
        self._mod_building_space_cursor = len(
            self._mod_building_space_list) - 1
        self._save_module_buildings()

    def _mod_building_delete_space(self):
        """Delete the currently selected space."""
        n = len(self._mod_building_space_list)
        if n == 0:
            return
        self._mod_building_space_list.pop(self._mod_building_space_cursor)
        n -= 1
        if n == 0:
            self._mod_building_space_cursor = 0
        elif self._mod_building_space_cursor >= n:
            self._mod_building_space_cursor = n - 1
        self._save_module_buildings()

    def _mod_building_open_enc_picker(self):
        """Open the enclosure template import picker for building spaces."""
        fe = self.features_editor
        saved = fe.load_map_templates()
        raw = saved.get("me_enclosure", [])
        blank = {"_blank": True, "label": "Create Blank Space",
                 "map_config": {"width": 20, "height": 20}}
        self._mod_building_enc_pick_list = [blank] + list(raw)
        self._mod_building_enc_pick_cursor = 0
        self._mod_building_enc_pick_scroll = 0
        self._mod_building_enc_picking = True

    def _mod_building_generate_space_from_template(self, name, template):
        """Create a new space from an enclosure template."""
        import copy
        mc = template.get("map_config", {})
        new_space = {
            "name": name,
            "width": mc.get("width", 20),
            "height": mc.get("height", 20),
            "entry_col": 0,
            "entry_row": 0,
            "tiles": copy.deepcopy(template.get("tiles", {})),
            "encounters": [],
        }
        self._mod_building_space_list.append(new_space)
        self._mod_building_space_cursor = len(
            self._mod_building_space_list) - 1
        self._save_module_buildings()

    def _mod_building_open_space_template_picker(self):
        """Open the template picker to import a template into the current space."""
        fe = self.features_editor
        saved = fe.load_map_templates()
        raw = saved.get("me_enclosure", [])
        if not raw:
            return
        self._mod_building_enc_pick_list = list(raw)
        self._mod_building_enc_pick_cursor = 0
        self._mod_building_enc_pick_scroll = 0
        self._mod_building_enc_picking = True
        self._mod_building_importing_to_space = True

    def _mod_building_apply_template_to_space(self, template):
        """Apply an enclosure template to the current space (overwrites tiles)."""
        import copy
        space = self._mod_building_get_current_space()
        if not space:
            return
        mc = template.get("map_config", {})
        space["width"] = mc.get("width", space.get("width", 20))
        space["height"] = mc.get("height", space.get("height", 20))
        space["tiles"] = copy.deepcopy(template.get("tiles", {}))
        self._save_module_buildings()

    # ── Encounter helpers (inside a space) ──

    def _mod_building_load_encounters(self):
        """Load encounter list from the current space."""
        space = self._mod_building_get_current_space()
        if not space:
            self._mod_building_encounter_list = []
            return
        self._mod_building_encounter_list = space.get("encounters", [])
        self._mod_building_encounter_cursor = 0
        self._mod_building_encounter_scroll = 0

    def _mod_building_save_encounters(self):
        """Write encounter list back into the current space dict."""
        space = self._mod_building_get_current_space()
        if not space:
            return
        space["encounters"] = list(self._mod_building_encounter_list)

    def _mod_building_add_encounter(self):
        """Add a new default encounter to the current space."""
        space = self._mod_building_get_current_space()
        ec = space.get("entry_col", 1) if space else 1
        er = space.get("entry_row", 1) if space else 1
        new_encounter = {
            "name": "New Encounter",
            "encounter_type": "npc",
            "col": ec,
            "row": er,
            "description": "",
        }
        self._mod_building_encounter_list.append(new_encounter)
        self._mod_building_encounter_cursor = len(
            self._mod_building_encounter_list) - 1
        self._mod_building_save_encounters()

    def _mod_building_delete_encounter(self):
        """Delete the currently selected encounter."""
        n = len(self._mod_building_encounter_list)
        if n == 0:
            return
        self._mod_building_encounter_list.pop(
            self._mod_building_encounter_cursor)
        n -= 1
        if n == 0:
            self._mod_building_encounter_cursor = 0
        elif self._mod_building_encounter_cursor >= n:
            self._mod_building_encounter_cursor = n - 1
        self._mod_building_save_encounters()

    def _mod_building_build_encounter_fields(self):
        """Build FieldEntry list for the selected encounter."""
        from src.editor_types import FieldEntry
        if not (0 <= self._mod_building_encounter_cursor < len(
                self._mod_building_encounter_list)):
            self._mod_building_encounter_fields = []
            return
        enc = self._mod_building_encounter_list[
            self._mod_building_encounter_cursor]
        self._mod_building_encounter_fields = [
            FieldEntry("Name", "name", enc.get("name", ""), "text", True),
            FieldEntry("Type", "encounter_type",
                       enc.get("encounter_type", "npc"), "text", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Col", "col", str(enc.get("col", 0)), "int", True),
            FieldEntry("Row", "row", str(enc.get("row", 0)), "int", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Description", "description",
                       enc.get("description", ""), "text", True),
        ]
        fe = self.features_editor
        self._mod_building_encounter_field = fe._next_editable_generic(
            self._mod_building_encounter_fields, 0)
        self._mod_building_encounter_buffer = (
            self._mod_building_encounter_fields[
                self._mod_building_encounter_field].value)
        self._mod_building_encounter_field_scroll = 0

    def _mod_building_save_encounter_fields(self):
        """Write encounter fields back into the encounter dict."""
        if not (0 <= self._mod_building_encounter_cursor < len(
                self._mod_building_encounter_list)):
            return
        enc = self._mod_building_encounter_list[
            self._mod_building_encounter_cursor]
        for fe_entry in self._mod_building_encounter_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            enc[key] = val

    # ── Map editor for a building space ──

    def _mod_building_launch_map_editor(self):
        """Launch the map editor for the current building space."""
        from src.map_editor import (
            MapEditorConfig, MapEditorState, MapEditorInputHandler,
            build_town_brushes,
            STORAGE_SPARSE, GRID_FIXED,
        )
        space = self._mod_building_get_current_space()
        if not space:
            return
        w = space.get("width", 20)
        h = space.get("height", 20)

        fe = self.features_editor
        saved_all = fe.load_map_templates()
        brushes = build_town_brushes(fe.TILE_CONTEXT,
                                     all_templates=saved_all)
        building = self._mod_building_get_current()
        building_name = building.get("name", "Building") if building else "Building"
        space_name = space.get("name", "Unnamed")

        # Build interior list from sibling spaces so they can link
        space_list = [
            {"name": sp.get("name", "?")}
            for sp in self._mod_building_space_list
        ]

        def on_save(state):
            space["tiles"] = state.tiles
            space["width"] = state.config.width
            space["height"] = state.config.height
            state.dirty = False
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5

        def on_exit(st):
            space["tiles"] = st.tiles
            self._save_module_buildings()
            self.showing_features = False
            self.showing_modules = True
            self.module_edit_mode = True
            self._mod_building_editor_active = False
            self._mod_building_map_editor_state = None
            self._mod_building_map_editor_handler = None

        config = MapEditorConfig(
            title=f"{building_name}: {space_name}",
            storage=STORAGE_SPARSE,
            grid_type=GRID_FIXED,
            width=w,
            height=h,
            tile_context="town",
            brushes=brushes,
            supports_interior_links=True,
            supports_replace=True,
            on_save=on_save,
            on_exit=on_exit,
            interior_exit_types=[
                {"label": u"\u2190 Return to Overworld",
                 "link_type": "to_overworld"},
            ],
        )
        existing_tiles = dict(space.get("tiles", {}))
        state = MapEditorState(config, tiles=existing_tiles,
                               interior_list=space_list)
        handler = MapEditorInputHandler(
            state, is_save_shortcut=self._is_save_shortcut)
        self._mod_building_map_editor_state = state
        self._mod_building_map_editor_handler = handler
        self._mod_building_editor_active = True
        self.module_edit_mode = False
        self.showing_modules = False
        self.showing_features = True
        fe = self.features_editor
        fe.active_editor = "mod_building_map"
        fe.level = 1

    # ── Building space NPC editing ──

    def _mod_building_space_load_npcs(self):
        """Load NPC list from the currently selected building space."""
        space = self._mod_building_get_current_space()
        if not space:
            self._mod_building_space_npc_list = []
            return
        self._mod_building_space_npc_list = list(
            space.get("npcs", []))
        self._mod_building_space_npc_cursor = 0
        self._mod_building_space_npc_scroll = 0

    def _mod_building_space_save_npcs(self):
        """Write NPC list back into the current building space dict."""
        space = self._mod_building_get_current_space()
        if not space:
            return
        space["npcs"] = list(self._mod_building_space_npc_list)

    def _mod_building_space_build_npc_fields(self):
        """Build FieldEntry list for the selected building space NPC."""
        from src.editor_types import FieldEntry
        if not (0 <= self._mod_building_space_npc_cursor
                < len(self._mod_building_space_npc_list)):
            self._mod_building_space_npc_fields = []
            return
        npc = self._mod_building_space_npc_list[
            self._mod_building_space_npc_cursor]

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

        self._mod_building_space_npc_fields = [
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
        self._mod_building_space_npc_choice_map = {
            "sprite": sprite_names,
        }
        self._mod_building_space_npc_sprite_name_to_file = (
            sprite_name_to_file)
        fe = self.features_editor
        self._mod_building_space_npc_field = (
            fe._next_editable_generic(
                self._mod_building_space_npc_fields, 0))
        self._mod_building_space_npc_buffer = (
            self._mod_building_space_npc_fields[
                self._mod_building_space_npc_field].value)
        self._mod_building_space_npc_field_scroll = 0

    def _mod_building_space_save_npc_fields(self):
        """Write NPC fields back into the building space NPC dict."""
        if not (0 <= self._mod_building_space_npc_cursor
                < len(self._mod_building_space_npc_list)):
            return
        npc = self._mod_building_space_npc_list[
            self._mod_building_space_npc_cursor]
        for fe_entry in self._mod_building_space_npc_fields:
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
                    self,
                    "_mod_building_space_npc_sprite_name_to_file", {})
                val = name_to_file.get(val, val)
            npc[key] = val

    def _mod_building_space_add_npc(self):
        """Add a new default NPC to the current building space."""
        space = self._mod_building_get_current_space()
        w = space.get("width", 20) if space else 10
        h = space.get("height", 20) if space else 10
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
        self._mod_building_space_npc_list.append(new_npc)
        self._mod_building_space_npc_cursor = (
            len(self._mod_building_space_npc_list) - 1)
        self._mod_building_space_save_npcs()

    def _mod_building_space_delete_npc(self):
        """Delete the currently selected building space NPC."""
        n = len(self._mod_building_space_npc_list)
        if n == 0:
            return
        self._mod_building_space_npc_list.pop(
            self._mod_building_space_npc_cursor)
        n -= 1
        if n == 0:
            self._mod_building_space_npc_cursor = 0
        elif self._mod_building_space_npc_cursor >= n:
            self._mod_building_space_npc_cursor = n - 1
        self._mod_building_space_save_npcs()

    def _mod_building_space_npc_cycle_choice(self, direction):
        """Cycle the current building space NPC choice field."""
        field = self._mod_building_space_npc_fields[
            self._mod_building_space_npc_field]
        options = self._mod_building_space_npc_choice_map.get(
            field.key, [])
        if not options:
            return
        try:
            idx = options.index(field.value)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(options)
        field.value = options[idx]
        self._mod_building_space_npc_buffer = field.value

    # ── Building space NPC input handlers ──

    def _handle_mod_building_space_npc_list_input(self, event):
        """Handle input for building space NPC list (level 20)."""
        import pygame
        n = len(self._mod_building_space_npc_list)
        fe = self.features_editor

        if event.key in (pygame.K_ESCAPE, pygame.K_LEFT):
            self._mod_building_space_save_npcs()
            self._save_module_buildings()
            self._mod_building_space_npc_edit_mode = 0
            return
        if self._is_new_shortcut(event):
            self._mod_building_space_add_npc()
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_building_space_delete_npc()
            return
        if self._is_save_shortcut(event):
            self._mod_building_space_save_npcs()
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_building_space_npc_cursor = (
                self._mod_building_space_npc_cursor - 1) % n
            self._mod_building_space_npc_scroll = (
                fe._adjust_scroll_generic(
                    self._mod_building_space_npc_cursor,
                    self._mod_building_space_npc_scroll))
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_building_space_npc_cursor = (
                self._mod_building_space_npc_cursor + 1) % n
            self._mod_building_space_npc_scroll = (
                fe._adjust_scroll_generic(
                    self._mod_building_space_npc_cursor,
                    self._mod_building_space_npc_scroll))
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_building_space_build_npc_fields()
            self._mod_building_space_npc_edit_mode = 2

    def _handle_mod_building_space_npc_field_input(self, event):
        """Handle input for building space NPC field editing (npc_edit_mode=2)."""
        import pygame
        fields = self._mod_building_space_npc_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self._mod_building_space_npc_edit_mode = 1
            return

        if self._is_save_shortcut(event):
            f = fields[self._mod_building_space_npc_field]
            if f.editable:
                f.value = self._mod_building_space_npc_buffer
            self._mod_building_space_save_npc_fields()
            self._mod_building_space_save_npcs()
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            f = fields[self._mod_building_space_npc_field]
            if f.editable:
                f.value = self._mod_building_space_npc_buffer
            self._mod_building_space_save_npc_fields()
            self._mod_building_space_save_npcs()
            self._mod_building_space_npc_edit_mode = 1
            return

        if event.key == pygame.K_UP:
            f = fields[self._mod_building_space_npc_field]
            if f.editable:
                f.value = self._mod_building_space_npc_buffer
            self._mod_building_space_npc_field = (
                fe._next_editable_generic(
                    fields,
                    (self._mod_building_space_npc_field - 1) % n))
            self._mod_building_space_npc_buffer = fields[
                self._mod_building_space_npc_field].value
            self._mod_building_space_npc_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_building_space_npc_field,
                    self._mod_building_space_npc_field_scroll))
        elif event.key == pygame.K_DOWN:
            f = fields[self._mod_building_space_npc_field]
            if f.editable:
                f.value = self._mod_building_space_npc_buffer
            self._mod_building_space_npc_field = (
                fe._next_editable_generic(
                    fields,
                    (self._mod_building_space_npc_field + 1) % n))
            self._mod_building_space_npc_buffer = fields[
                self._mod_building_space_npc_field].value
            self._mod_building_space_npc_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_building_space_npc_field,
                    self._mod_building_space_npc_field_scroll))
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            f = fields[self._mod_building_space_npc_field]
            if f.field_type == "choice":
                direction = (-1 if event.key == pygame.K_LEFT
                             else 1)
                self._mod_building_space_npc_cycle_choice(direction)
        elif event.key == pygame.K_BACKSPACE:
            f = fields[self._mod_building_space_npc_field]
            if f.field_type != "choice":
                self._mod_building_space_npc_buffer = (
                    self._mod_building_space_npc_buffer[:-1])
        elif event.unicode and event.unicode.isprintable():
            f = fields[self._mod_building_space_npc_field]
            if f.field_type != "choice":
                self._mod_building_space_npc_buffer += event.unicode

    # ── Building input handlers ──
