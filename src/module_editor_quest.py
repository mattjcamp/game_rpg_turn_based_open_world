"""Quest editor mixin — extracted from game.py to reduce god-class size."""


class ModuleQuestEditorMixin:
    """Mixin providing quest editing functionality for the Game class."""

    def _mod_quest_get_current(self):
        """Return the currently selected quest dict, or None."""
        if 0 <= self._mod_quest_cursor < len(self._mod_quest_list):
            return self._mod_quest_list[self._mod_quest_cursor]
        return None

    def _mod_quest_build_location_options(self):
        """Build the list of location options from the current module.

        Includes overview map, all towns (and their interiors),
        all dungeons, and all buildings (and their spaces).
        Returns (options_list, option_to_value_dict).
        """
        options = ["(none)"]
        option_to_value = {"(none)": ""}

        # Overview map
        options.append("Overview Map")
        option_to_value["Overview Map"] = "overview"

        # Towns and their interiors
        for town in self._mod_town_list:
            name = town.get("name", "Unnamed")
            label = f"Town: {name}"
            options.append(label)
            option_to_value[label] = f"town:{name}"

            for enc in town.get("interiors", []):
                enc_name = enc.get("name", "Unnamed")
                int_label = f"  Interior: {enc_name} ({name})"
                options.append(int_label)
                option_to_value[int_label] = f"interior:{name}/{enc_name}"

        # Dungeons
        for dungeon in self._mod_dungeon_list:
            name = dungeon.get("name", "Unnamed")
            label = f"Dungeon: {name}"
            options.append(label)
            option_to_value[label] = f"dungeon:{name}"

        # Buildings and their spaces
        for building in self._mod_building_list:
            name = building.get("name", "Unnamed")
            label = f"Building: {name}"
            options.append(label)
            option_to_value[label] = f"building:{name}"

            for space in building.get("spaces", []):
                space_name = space.get("name", "Unnamed")
                sp_label = f"  Space: {space_name} ({name})"
                options.append(sp_label)
                option_to_value[sp_label] = f"space:{name}/{space_name}"

        return options, option_to_value

    def _mod_quest_location_display(self, stored_value):
        """Convert a stored location value back to a display string."""
        if not stored_value:
            return "(none)"
        if stored_value == "overview":
            return "Overview Map"
        if stored_value.startswith("town:"):
            return f"Town: {stored_value[5:]}"
        if stored_value.startswith("interior:"):
            parts = stored_value[9:]
            if "/" in parts:
                town_name, enc_name = parts.split("/", 1)
                return f"  Interior: {enc_name} ({town_name})"
            return f"  Interior: {parts}"
        if stored_value.startswith("dungeon:"):
            return f"Dungeon: {stored_value[8:]}"
        if stored_value.startswith("building:"):
            return f"Building: {stored_value[9:]}"
        if stored_value.startswith("space:"):
            parts = stored_value[6:]
            if "/" in parts:
                bldg_name, space_name = parts.split("/", 1)
                return f"  Space: {space_name} ({bldg_name})"
            return f"  Space: {parts}"
        return stored_value

    def _mod_quest_build_settings_fields(self):
        """Build FieldEntry list for the current quest's settings."""
        from src.editor_types import FieldEntry
        quest = self._mod_quest_get_current()
        if not quest:
            self._mod_quest_fields = []
            return

        # ── Sprite choices ──
        if not hasattr(self, "_cc_tiles") or not self._cc_tiles:
            self._cc_load_tiles()
        sprite_names = [t["name"] for t in self._cc_tiles]
        sprite_name_to_file = {t["name"]: t["file"] for t in self._cc_tiles}
        sprite_file_to_name = {t["file"]: t["name"] for t in self._cc_tiles}
        current_sprite_file = quest.get("giver_sprite", "")
        current_sprite_name = sprite_file_to_name.get(
            current_sprite_file,
            sprite_names[0] if sprite_names else "Default")
        self._mod_quest_sprite_name_to_file = sprite_name_to_file

        # ── Location choices ──
        loc_options, loc_map = self._mod_quest_build_location_options()
        self._mod_quest_location_map = loc_map
        stored_loc = quest.get("giver_location", "")
        current_loc_display = self._mod_quest_location_display(stored_loc)
        # Ensure the current display value is in the options list
        if current_loc_display not in loc_options:
            loc_options.append(current_loc_display)

        self._mod_quest_fields = [
            FieldEntry("Name", "name", quest.get("name", ""), "text", True),
            FieldEntry("Description", "description",
                       quest.get("description", ""), "text", True),
            FieldEntry("Quest Giver", "", "", "section", False),
            FieldEntry("Giver NPC", "giver_npc",
                       quest.get("giver_npc", ""), "text", True),
            FieldEntry("Giver Sprite", "giver_sprite",
                       current_sprite_name, "choice", True),
            FieldEntry("Location", "giver_location",
                       current_loc_display, "choice", True),
            FieldEntry("Giver Col", "giver_col",
                       str(quest.get("giver_col", "")), "int", True),
            FieldEntry("Giver Row", "giver_row",
                       str(quest.get("giver_row", "")), "int", True),
            FieldEntry("Dialogue", "giver_dialogue",
                       quest.get("giver_dialogue", ""), "text", True),
            FieldEntry("Rewards", "", "", "section", False),
            FieldEntry("Reward XP", "reward_xp",
                       str(quest.get("reward_xp", 0)), "int", True),
            FieldEntry("Reward Gold", "reward_gold",
                       str(quest.get("reward_gold", 0)), "int", True),
        ]

        self._mod_quest_choice_map = {
            "giver_sprite": sprite_names,
            "giver_location": loc_options,
        }

        fe = self.features_editor
        self._mod_quest_field = fe._next_editable_generic(
            self._mod_quest_fields, 0)
        self._mod_quest_buffer = self._mod_quest_fields[
            self._mod_quest_field].value
        self._mod_quest_field_scroll = 0

    def _mod_quest_save_settings_fields(self):
        """Write settings fields back into the current quest dict."""
        quest = self._mod_quest_get_current()
        if not quest:
            return
        for fe_entry in self._mod_quest_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                # giver_col / giver_row: blank means "auto-place"
                if key in ("giver_col", "giver_row") and (
                        val == "" or val is None):
                    quest.pop(key, None)
                    continue
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            # Convert sprite display name back to file path
            if key == "giver_sprite":
                name_to_file = getattr(
                    self, "_mod_quest_sprite_name_to_file", {})
                val = name_to_file.get(val, val)
            # Convert location display name back to stored value
            if key == "giver_location":
                loc_map = getattr(self, "_mod_quest_location_map", {})
                val = loc_map.get(val, val)
            quest[key] = val

    def _mod_quest_load_steps(self):
        """Load step list from the current quest."""
        quest = self._mod_quest_get_current()
        if not quest:
            self._mod_quest_step_list = []
            return
        self._mod_quest_step_list = list(quest.get("steps", []))
        self._mod_quest_step_cursor = 0
        self._mod_quest_step_scroll = 0

    def _mod_quest_save_steps(self):
        """Write step list back into the current quest dict."""
        quest = self._mod_quest_get_current()
        if not quest:
            return
        quest["steps"] = list(self._mod_quest_step_list)

    _QUEST_STEP_TYPES = [
        "collect", "kill",
    ]

    def _mod_quest_load_monster_names(self):
        """Load monster names from the module's monsters.json for the
        quest step editor's monster picker."""
        import json, os
        if getattr(self, "_mod_quest_monster_names", None) is not None:
            return
        self._mod_quest_monster_names = ["(none)"]
        self._mod_quest_monster_tiles = {}  # name -> tile filename
        mod_path = None
        if self.module_list:
            mod = self.module_list[self.module_cursor]
            mod_path = mod.get("path")
        # Try module monsters.json first, then default
        paths_to_try = []
        if mod_path:
            paths_to_try.append(
                os.path.join(mod_path, "monsters.json"))
        paths_to_try.append(os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "monsters.json"))
        for p in paths_to_try:
            if not os.path.isfile(p):
                continue
            try:
                with open(p, "r") as f:
                    data = json.load(f)
                for name, entry in sorted(
                        data.get("monsters", {}).items()):
                    display = name.replace("_", " ").title()
                    self._mod_quest_monster_names.append(display)
                    tile = entry.get("tile", "")
                    if tile:
                        self._mod_quest_monster_tiles[display] = tile
                break  # use first found
            except (OSError, json.JSONDecodeError):
                continue

    def _mod_quest_load_artifact_tiles(self):
        """Load artifact tile names for the quest step editor's item picker.

        Reads directly from tile_defs.json on disk (merged into
        settings.TILE_DEFS at startup) so artifact tiles are available
        even when the tile editor hasn't been opened yet.
        """
        import json, os
        from src import settings

        self._mod_quest_artifact_names = ["(none)"]
        self._mod_quest_artifact_sprites = {}  # display name -> sprite key

        # Read saved tile defs from disk for context + sprite info
        defs_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "tile_defs.json")
        saved = {}
        if os.path.isfile(defs_path):
            try:
                with open(defs_path, "r") as f:
                    saved = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        fe = self.features_editor
        for tid_str, tdef in saved.items():
            if tdef.get("context") == "artifacts":
                name = tdef.get("name", "")
                if name:
                    self._mod_quest_artifact_names.append(name)
                    sprite = tdef.get("sprite", "")
                    if sprite:
                        self._mod_quest_artifact_sprites[name] = sprite

        # Also check features_editor.tile_list if populated (editor open)
        if fe.tile_list:
            for tile in fe.tile_list:
                if tile.get("_context") == "artifacts":
                    name = tile.get("name", "")
                    if name and name not in self._mod_quest_artifact_sprites:
                        self._mod_quest_artifact_names.append(name)
                        sprite = tile.get("_sprite", "")
                        if sprite:
                            self._mod_quest_artifact_sprites[name] = sprite

    def _mod_quest_build_step_fields(self, preserve_cursor=False):
        """Build FieldEntry list for the selected quest step."""
        from src.editor_types import FieldEntry
        if not (0 <= self._mod_quest_step_cursor < len(
                self._mod_quest_step_list)):
            self._mod_quest_step_fields = []
            return
        step = self._mod_quest_step_list[self._mod_quest_step_cursor]

        # Ensure monster names and artifact tiles are loaded
        self._mod_quest_load_monster_names()
        self._mod_quest_load_artifact_tiles()

        step_type = step.get("step_type", "collect")

        # Resolve spawn location display
        current_spawn_loc = step.get("spawn_location", "")
        spawn_loc_display = self._mod_quest_location_display(
            current_spawn_loc)

        # Build location options for spawn location picker
        loc_options, self._mod_quest_step_loc_map = (
            self._mod_quest_build_location_options())

        # Common fields: Description + Type
        common_top = [
            FieldEntry("Description", "description",
                       step.get("description", ""), "text", True),
            FieldEntry("", "", "", "section", False),
            FieldEntry("Type", "step_type",
                       step_type, "choice", True),
        ]

        # Common bottom: Optional
        common_bottom = [
            FieldEntry("", "", "", "section", False),
            FieldEntry("Optional", "optional",
                       step.get("optional", "no"), "choice", True),
        ]

        if step_type == "kill":
            # Kill: Monster, Spawn Location, Target Count
            current_monster = step.get("monster", "")
            if not current_monster:
                current_monster = "(none)"
            type_fields = [
                FieldEntry("Monster", "monster",
                           current_monster, "choice", True),
                FieldEntry("Spawn Location", "spawn_location",
                           spawn_loc_display, "choice", True),
                FieldEntry("Target Count", "target_count",
                           str(step.get("target_count", 1)), "int", True),
            ]
        else:
            # Collect: Item, Spawn Location, Guardian, Guardian Monster
            current_item = step.get("collect_item", "")
            if not current_item:
                current_item = "(none)"
            has_guardian = step.get("has_guardian", "no")
            type_fields = [
                FieldEntry("Item", "collect_item",
                           current_item, "choice", True),
                FieldEntry("Spawn Location", "spawn_location",
                           spawn_loc_display, "choice", True),
                FieldEntry("Target Count", "target_count",
                           str(step.get("target_count", 1)), "int", True),
                FieldEntry("", "", "", "section", False),
                FieldEntry("Guardian", "has_guardian",
                           has_guardian, "choice", True),
            ]
            if has_guardian == "yes":
                guardian_monster = step.get("guardian_monster", "")
                if not guardian_monster:
                    guardian_monster = "(none)"
                type_fields.append(
                    FieldEntry("Guardian Monster", "guardian_monster",
                               guardian_monster, "choice", True))

        self._mod_quest_step_fields = common_top + type_fields + common_bottom
        self._mod_quest_step_choice_map = {
            "step_type": self._QUEST_STEP_TYPES,
            "monster": getattr(self, "_mod_quest_monster_names",
                               ["(none)"]),
            "guardian_monster": getattr(self, "_mod_quest_monster_names",
                                       ["(none)"]),
            "collect_item": getattr(self, "_mod_quest_artifact_names",
                                    ["(none)"]),
            "spawn_location": loc_options,
            "optional": ["no", "yes"],
            "has_guardian": ["no", "yes"],
        }
        fe = self.features_editor
        if not preserve_cursor:
            self._mod_quest_step_field = fe._next_editable_generic(
                self._mod_quest_step_fields, 0)
            self._mod_quest_step_buffer = self._mod_quest_step_fields[
                self._mod_quest_step_field].value
            self._mod_quest_step_field_scroll = 0
        else:
            # Clamp cursor to valid range after rebuild
            if self._mod_quest_step_field >= len(self._mod_quest_step_fields):
                self._mod_quest_step_field = fe._next_editable_generic(
                    self._mod_quest_step_fields,
                    len(self._mod_quest_step_fields) - 1)
            cur = self._mod_quest_step_fields[self._mod_quest_step_field]
            if not cur.editable or cur.field_type == "section":
                self._mod_quest_step_field = fe._next_editable_generic(
                    self._mod_quest_step_fields,
                    self._mod_quest_step_field)
            self._mod_quest_step_buffer = self._mod_quest_step_fields[
                self._mod_quest_step_field].value

    def _mod_quest_save_step_fields(self):
        """Write step fields back into the step dict."""
        if not (0 <= self._mod_quest_step_cursor < len(
                self._mod_quest_step_list)):
            return
        step = self._mod_quest_step_list[self._mod_quest_step_cursor]
        loc_map = getattr(self, "_mod_quest_step_loc_map", {})
        for fe_entry in self._mod_quest_step_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            key = fe_entry.key
            val = fe_entry.value
            if fe_entry.field_type == "int":
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            # Store "(none)" as empty string for choice fields
            if key in ("monster", "guardian_monster", "collect_item") \
                    and val == "(none)":
                val = ""
            # Convert spawn location display name to stored value
            if key == "spawn_location":
                val = loc_map.get(val, "")
            step[key] = val

    def _mod_quest_add_new(self, name):
        """Add a new blank quest to the module."""
        new_quest = {
            "name": name,
            "description": "",
            "giver_npc": "",
            "giver_sprite": "",
            "giver_location": "",
            "giver_dialogue": "",
            "reward_xp": 0,
            "reward_gold": 0,
            "steps": [],
        }
        self._mod_quest_list.append(new_quest)
        self._mod_quest_cursor = len(self._mod_quest_list) - 1
        self._save_module_quests()

    def _mod_quest_add_step(self):
        """Add a new default step to the current quest."""
        new_step = {
            "description": "New Step",
            "step_type": "collect",
            "monster": "",
            "collect_item": "",
            "has_guardian": "no",
            "guardian_monster": "",
            "spawn_location": "",
            "target": "",
            "target_count": 1,
            "optional": "no",
        }
        self._mod_quest_step_list.append(new_step)
        self._mod_quest_step_cursor = len(self._mod_quest_step_list) - 1
        self._mod_quest_save_steps()

    def _mod_quest_delete_step(self):
        """Delete the currently selected step."""
        n = len(self._mod_quest_step_list)
        if n == 0:
            return
        self._mod_quest_step_list.pop(self._mod_quest_step_cursor)
        n -= 1
        if n == 0:
            self._mod_quest_step_cursor = 0
        elif self._mod_quest_step_cursor >= n:
            self._mod_quest_step_cursor = n - 1
        self._mod_quest_save_steps()

    # ── Quest input handlers ──

    def _handle_quest_edit_input(self, event):
        """Dispatch quest editor input based on module_edit_level.

        Levels:
        20 = quest list browser
        21 = sub-screen selector (Settings/Quest Steps)
        22 = settings fields OR step list
        23 = step field editor
        """
        import pygame

        if self.module_edit_level == 23:
            self._handle_mod_quest_step_field_input(event)
            return
        if self.module_edit_level == 22:
            if self._mod_quest_sub_cursor == 0:
                self._handle_mod_quest_settings_field_input(event)
            elif self._mod_quest_sub_cursor == 1:
                self._handle_mod_quest_step_list_input(event)
            return
        if self.module_edit_level == 21:
            self._handle_mod_quest_sub_input(event)
            return

        # ── Level 20: Quest list ──
        if self._mod_quest_naming:
            self._handle_mod_quest_naming_input(event)
            return

        quests = self._mod_quest_list
        n = len(quests)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE:
            self._save_module_quests()
            self.module_edit_level = 0
            return
        if self._is_new_shortcut(event):
            self._mod_quest_naming = True
            self._mod_quest_naming_is_new = True
            self._mod_quest_naming_target = "quest"
            self._mod_quest_name_buf = ""
            return
        if self._is_delete_shortcut(event) and n > 0:
            quests.pop(self._mod_quest_cursor)
            n -= 1
            if n == 0:
                self._mod_quest_cursor = 0
            elif self._mod_quest_cursor >= n:
                self._mod_quest_cursor = n - 1
            self._save_module_quests()
            return
        if self._is_save_shortcut(event):
            self._save_module_quests()
            self._mod_quest_save_flash = 1.5
            return
        if event.key == pygame.K_F2 and n > 0:
            quest = self._mod_quest_get_current()
            if quest:
                self._mod_quest_naming = True
                self._mod_quest_naming_is_new = False
                self._mod_quest_naming_target = "quest"
                self._mod_quest_name_buf = quest.get("name", "")
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_quest_cursor = (self._mod_quest_cursor - 1) % n
            self._mod_quest_scroll = fe._adjust_scroll_generic(
                self._mod_quest_cursor, self._mod_quest_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_quest_cursor = (self._mod_quest_cursor + 1) % n
            self._mod_quest_scroll = fe._adjust_scroll_generic(
                self._mod_quest_cursor, self._mod_quest_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_quest_sub_cursor = 0
            self.module_edit_level = 21

    def _handle_mod_quest_naming_input(self, event):
        """Handle text input while naming/renaming a quest."""
        import pygame
        if event.key == pygame.K_ESCAPE:
            self._mod_quest_naming = False
            return
        if event.key == pygame.K_RETURN:
            name = self._mod_quest_name_buf.strip()
            if name:
                if self._mod_quest_naming_is_new:
                    self._mod_quest_add_new(name)
                else:
                    quest = self._mod_quest_get_current()
                    if quest:
                        quest["name"] = name
                        self._save_module_quests()
            self._mod_quest_naming = False
            return
        if event.key == pygame.K_BACKSPACE:
            self._mod_quest_name_buf = self._mod_quest_name_buf[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self._mod_quest_name_buf += event.unicode

    def _handle_mod_quest_sub_input(self, event):
        """Handle input on the sub-screen selector (level 21)."""
        import pygame
        n = len(self._mod_quest_sub_items)
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self.module_edit_level = 20
            return
        if event.key == pygame.K_UP:
            self._mod_quest_sub_cursor = (self._mod_quest_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._mod_quest_sub_cursor = (self._mod_quest_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self._mod_quest_sub_cursor == 0:
                self._mod_quest_build_settings_fields()
                self.module_edit_level = 22
            elif self._mod_quest_sub_cursor == 1:
                self._mod_quest_load_steps()
                self.module_edit_level = 22

    def _mod_quest_cycle_choice(self, direction):
        """Cycle the current quest choice field left (-1) or right (+1)."""
        field = self._mod_quest_fields[self._mod_quest_field]
        options = self._mod_quest_choice_map.get(field.key, [])
        if not options:
            return
        try:
            idx = options.index(field.value)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(options)
        field.value = options[idx]
        self._mod_quest_buffer = field.value

    def _handle_mod_quest_settings_field_input(self, event):
        """Handle input for quest settings field editing (level 22)."""
        import pygame
        fields = self._mod_quest_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 21
            return

        current_field = fields[self._mod_quest_field]

        if self._is_save_shortcut(event):
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_buffer
            self._mod_quest_save_settings_fields()
            self._save_module_quests()
            self._mod_quest_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_buffer
            self._mod_quest_save_settings_fields()
            self.module_edit_level = 21
            return

        if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            if current_field.field_type == "choice":
                direction = -1 if event.key == pygame.K_LEFT else 1
                self._mod_quest_cycle_choice(direction)
                return

        if event.key == pygame.K_UP:
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_buffer
            self._mod_quest_field = fe._next_editable_generic(
                fields, (self._mod_quest_field - 1) % n)
            nf = fields[self._mod_quest_field]
            self._mod_quest_buffer = nf.value if nf.field_type != "choice" else ""
            self._mod_quest_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_quest_field, self._mod_quest_field_scroll)
        elif event.key == pygame.K_DOWN:
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_buffer
            self._mod_quest_field = fe._next_editable_generic(
                fields, (self._mod_quest_field + 1) % n)
            nf = fields[self._mod_quest_field]
            self._mod_quest_buffer = nf.value if nf.field_type != "choice" else ""
            self._mod_quest_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_quest_field, self._mod_quest_field_scroll)
        elif current_field.field_type == "choice":
            # Don't allow typing on choice fields
            pass
        elif event.key == pygame.K_BACKSPACE:
            self._mod_quest_buffer = self._mod_quest_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            self._mod_quest_buffer += event.unicode

    def _handle_mod_quest_step_list_input(self, event):
        """Handle input for the quest step list (level 22)."""
        import pygame
        n = len(self._mod_quest_step_list)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._mod_quest_save_steps()
            self.module_edit_level = 21
            return
        if self._is_new_shortcut(event):
            self._mod_quest_add_step()
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_quest_delete_step()
            return
        if self._is_save_shortcut(event):
            self._mod_quest_save_steps()
            self._save_module_quests()
            self._mod_quest_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_quest_step_cursor = (
                self._mod_quest_step_cursor - 1) % n
            self._mod_quest_step_scroll = fe._adjust_scroll_generic(
                self._mod_quest_step_cursor, self._mod_quest_step_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_quest_step_cursor = (
                self._mod_quest_step_cursor + 1) % n
            self._mod_quest_step_scroll = fe._adjust_scroll_generic(
                self._mod_quest_step_cursor, self._mod_quest_step_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_quest_build_step_fields()
            self.module_edit_level = 23

    def _mod_quest_step_cycle_choice(self, direction):
        """Cycle the current step choice field left (-1) or right (+1)."""
        field = self._mod_quest_step_fields[self._mod_quest_step_field]
        options = self._mod_quest_step_choice_map.get(field.key, [])
        if not options:
            return
        try:
            idx = options.index(field.value)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(options)
        field.value = options[idx]
        self._mod_quest_step_buffer = field.value

        # When step_type or has_guardian changes, save current values
        # then rebuild the field list to show/hide relevant fields
        if field.key in ("step_type", "has_guardian"):
            self._mod_quest_save_step_fields()
            self._mod_quest_build_step_fields(preserve_cursor=True)

