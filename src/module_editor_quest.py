"""Quest editor mixin — extracted from game.py to reduce god-class size."""


# ── Reward "World Unlock" tile choices ─────────────────────────────────
# A world-unlock reward mutates one overworld tile when the quest is
# turned in.  Two designer-facing kinds share the same underlying op
# (``set_tile``) but expose different tile-pickers:
#
# * ``remove_obstacle`` — replace an impassable tile (mountain, water)
#   with something the party can walk on.  The picker only offers
#   passable terrain.
# * ``add_tile`` — paint an arbitrary new tile at a coordinate
#   (e.g. dropping a TILE_BRIDGE on water, or carving a TILE_PATH).
#   The picker offers the full set of overworld tile types.
#
# Both are just integer tile ids in the quest JSON; the ``kind`` field
# is preserved purely so the editor can re-open the right picker.
WORLD_UNLOCK_KIND_NONE = ""
WORLD_UNLOCK_KIND_REMOVE = "remove_obstacle"
WORLD_UNLOCK_KIND_ADD = "add_tile"

WORLD_UNLOCK_KIND_LABELS = {
    WORLD_UNLOCK_KIND_NONE: "(none)",
    WORLD_UNLOCK_KIND_REMOVE: "Remove Obstacle",
    WORLD_UNLOCK_KIND_ADD: "Add Tile",
}
WORLD_UNLOCK_LABEL_TO_KIND = {v: k for k, v in WORLD_UNLOCK_KIND_LABELS.items()}
WORLD_UNLOCK_KIND_OPTIONS = [
    WORLD_UNLOCK_KIND_LABELS[WORLD_UNLOCK_KIND_NONE],
    WORLD_UNLOCK_KIND_LABELS[WORLD_UNLOCK_KIND_REMOVE],
    WORLD_UNLOCK_KIND_LABELS[WORLD_UNLOCK_KIND_ADD],
]


def world_unlock_tile_options(kind):
    """Return the (display_name, tile_id) options for the Tile picker.

    The list returned depends on the unlock *kind*:

    * ``remove_obstacle`` — only passable overworld terrain so the
      designer can't accidentally swap a boulder for another boulder.
    * ``add_tile`` — every overworld-relevant tile type, including
      walls/water/etc., so the designer can place bridges, mountains,
      towns, etc.
    * any other / empty kind — empty list (the field is disabled).
    """
    from src.settings import (
        TILE_GRASS, TILE_PATH, TILE_SAND, TILE_BRIDGE, TILE_FOREST,
        TILE_WATER, TILE_MOUNTAIN, TILE_TOWN, TILE_DUNGEON,
        TILE_DUNGEON_CLEARED, TILE_DEFS,
    )
    passable = [TILE_GRASS, TILE_PATH, TILE_SAND, TILE_BRIDGE, TILE_FOREST]
    all_overworld = passable + [
        TILE_WATER, TILE_MOUNTAIN, TILE_TOWN, TILE_DUNGEON,
        TILE_DUNGEON_CLEARED,
    ]
    if kind == WORLD_UNLOCK_KIND_REMOVE:
        ids = passable
    elif kind == WORLD_UNLOCK_KIND_ADD:
        ids = all_overworld
    else:
        return []
    options = []
    for tid in ids:
        info = TILE_DEFS.get(tid)
        if info:
            options.append((info.get("name", f"Tile {tid}"), tid))
    return options


def world_unlock_tile_name(tile_id):
    """Return the display name for a tile id (or "(none)" if missing)."""
    from src.settings import TILE_DEFS
    if tile_id is None or tile_id == "":
        return "(none)"
    info = TILE_DEFS.get(tile_id)
    if info:
        return info.get("name", f"Tile {tile_id}")
    return f"Tile {tile_id}"


def apply_world_unlocks(tile_map, unlocks):
    """Apply a list of ``reward_world_unlocks`` ops to *tile_map*.

    Each op is ``{"kind": ..., "col": int, "row": int, "tile": int}``.
    Only ops with valid in-bounds coordinates and an integer tile id
    are applied — bad entries are skipped silently so a malformed
    quest file never crashes a game on load.

    Returns the list of ``(col, row, tile_id)`` triples that were
    actually applied, useful for building reward-summary text.
    """
    applied = []
    if not tile_map or not unlocks:
        return applied
    for op in unlocks:
        if not isinstance(op, dict):
            continue
        try:
            c = int(op.get("col"))
            r = int(op.get("row"))
            t = int(op.get("tile"))
        except (TypeError, ValueError):
            continue
        if not (0 <= c < tile_map.width and 0 <= r < tile_map.height):
            continue
        tile_map.set_tile(c, r, t)
        applied.append((c, r, t))
    return applied


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

        # ── World Unlock fields ──
        # Edit only the FIRST entry in reward_world_unlocks via 4
        # inline fields (kind / col / row / tile). The data model is a
        # list so authors can hand-edit quests.json to add multi-tile
        # unlocks (e.g. a 2-wide bridge); the editor surfaces one
        # entry to keep the UI simple.
        unlocks = quest.get("reward_world_unlocks") or []
        first_unlock = unlocks[0] if unlocks else {}
        u_kind = first_unlock.get("kind", WORLD_UNLOCK_KIND_NONE)
        u_kind_label = WORLD_UNLOCK_KIND_LABELS.get(u_kind,
                                                    WORLD_UNLOCK_KIND_LABELS[
                                                        WORLD_UNLOCK_KIND_NONE])
        u_col = first_unlock.get("col", "")
        u_row = first_unlock.get("row", "")
        u_tile_id = first_unlock.get("tile")
        # Tile picker contents depend on the kind; cache them so
        # cycling Left/Right hits the right list.
        u_tile_options = world_unlock_tile_options(u_kind)
        u_tile_names = [name for name, _tid in u_tile_options]
        u_tile_name_to_id = {name: tid for name, tid in u_tile_options}
        u_tile_id_to_name = {tid: name for name, tid in u_tile_options}
        # Cache for the save/load side
        self._mod_quest_unlock_tile_name_to_id = u_tile_name_to_id
        if u_tile_id in u_tile_id_to_name:
            u_tile_display = u_tile_id_to_name[u_tile_id]
        elif u_tile_names:
            u_tile_display = u_tile_names[0]
        else:
            u_tile_display = "(none)"
        # If the kind is "(none)" the tile choice is disabled; show
        # that explicitly so the row doesn't look broken.
        u_tile_choices = (u_tile_names if u_kind != WORLD_UNLOCK_KIND_NONE
                          else ["(none)"])
        if u_tile_display not in u_tile_choices:
            u_tile_choices.append(u_tile_display)

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
            # Item rewards — pressing Enter on this row opens a grid
            # picker that toggles items in/out of quest.reward_items.
            # Display shows a summary (count + a few names).
            FieldEntry("Reward Items", "reward_items",
                       self._mod_quest_format_reward_items(
                           quest.get("reward_items", [])),
                       "item_list", True),
            # ── World Unlock reward (mutates the overworld map) ──
            FieldEntry("World Unlock", "", "", "section", False),
            FieldEntry("Unlock Kind", "unlock_kind",
                       u_kind_label, "choice", True),
            FieldEntry("Unlock Col", "unlock_col",
                       str(u_col), "int",
                       u_kind != WORLD_UNLOCK_KIND_NONE),
            FieldEntry("Unlock Row", "unlock_row",
                       str(u_row), "int",
                       u_kind != WORLD_UNLOCK_KIND_NONE),
            FieldEntry("Unlock Tile", "unlock_tile",
                       u_tile_display, "choice",
                       u_kind != WORLD_UNLOCK_KIND_NONE),
        ]

        self._mod_quest_choice_map = {
            "giver_sprite": sprite_names,
            "giver_location": loc_options,
            "unlock_kind": WORLD_UNLOCK_KIND_OPTIONS,
            "unlock_tile": u_tile_choices,
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
        # Buffer the world-unlock virtual fields here; they don't map
        # 1:1 to quest keys — they're consolidated into a single
        # ``reward_world_unlocks`` list at the end.
        unlock_kind_label = None
        unlock_col_str = None
        unlock_row_str = None
        unlock_tile_label = None
        for fe_entry in self._mod_quest_fields:
            if not fe_entry.editable or fe_entry.field_type == "section":
                continue
            # Item lists own their own save path (via the picker's
            # toggle handler); the field.value here is just a display
            # summary, not the real data.
            if fe_entry.field_type == "item_list":
                continue
            key = fe_entry.key
            val = fe_entry.value
            # Capture world-unlock virtual fields and skip the generic
            # ``quest[key] = val`` write — they're consolidated below.
            if key == "unlock_kind":
                unlock_kind_label = val
                continue
            if key == "unlock_col":
                unlock_col_str = val
                continue
            if key == "unlock_row":
                unlock_row_str = val
                continue
            if key == "unlock_tile":
                unlock_tile_label = val
                continue
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

        # ── Consolidate the world-unlock virtual fields ──
        kind_value = WORLD_UNLOCK_LABEL_TO_KIND.get(
            unlock_kind_label or "", WORLD_UNLOCK_KIND_NONE)
        if kind_value == WORLD_UNLOCK_KIND_NONE:
            # No unlock authored — drop the list entirely so the JSON
            # stays clean.
            existing = quest.get("reward_world_unlocks") or []
            # Preserve any extra entries authored by hand (we only
            # manage the first one through the editor).
            if len(existing) > 1:
                quest["reward_world_unlocks"] = existing[1:]
            else:
                quest.pop("reward_world_unlocks", None)
        else:
            try:
                col_int = int(unlock_col_str) if unlock_col_str not in (
                    None, "") else 0
            except ValueError:
                col_int = 0
            try:
                row_int = int(unlock_row_str) if unlock_row_str not in (
                    None, "") else 0
            except ValueError:
                row_int = 0
            tile_map_lookup = getattr(
                self, "_mod_quest_unlock_tile_name_to_id", {}) or {}
            tile_id = tile_map_lookup.get(unlock_tile_label)
            if tile_id is None:
                # Best-effort fallback — keep the previously stored id
                # if the label can't be resolved (e.g. tiles list out
                # of sync mid-edit).  Otherwise default to grass.
                from src.settings import TILE_GRASS
                existing = quest.get("reward_world_unlocks") or []
                if existing and isinstance(existing[0], dict):
                    tile_id = existing[0].get("tile", TILE_GRASS)
                else:
                    tile_id = TILE_GRASS
            new_first = {
                "kind": kind_value,
                "col": col_int,
                "row": row_int,
                "tile": int(tile_id),
            }
            existing = quest.get("reward_world_unlocks") or []
            if existing:
                quest["reward_world_unlocks"] = [new_first] + list(existing[1:])
            else:
                quest["reward_world_unlocks"] = [new_first]

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

    def _mod_quest_load_encounter_names(self):
        """Load encounter names from the module's encounters.json for the
        quest step editor's encounter picker.

        Populates two attributes:
          * ``_mod_quest_encounter_names`` — ``["(none)", "Rat Pack", ...]``
          * ``_mod_quest_encounter_tiles`` — ``{"Rat Pack": "rats.png"}``
            mapping each encounter's display name to its
            ``monster_party_tile`` so the renderer can show a preview.

        Encounters from all buckets (dungeon / overworld / house / …)
        are flattened into one picker list.
        """
        import json, os
        if getattr(self, "_mod_quest_encounter_names", None) is not None:
            return
        self._mod_quest_encounter_names = ["(none)"]
        self._mod_quest_encounter_tiles = {}
        mod_path = None
        if self.module_list:
            mod = self.module_list[self.module_cursor]
            mod_path = mod.get("path")
        paths_to_try = []
        if mod_path:
            paths_to_try.append(
                os.path.join(mod_path, "encounters.json"))
        paths_to_try.append(os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "encounters.json"))
        for p in paths_to_try:
            if not os.path.isfile(p):
                continue
            try:
                with open(p, "r") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            buckets = data.get("encounters", {})
            if not isinstance(buckets, dict):
                break
            # Flatten every bucket into one sorted list (stable
            # across sessions).
            entries = []
            for cat in sorted(buckets.keys()):
                bucket = buckets.get(cat) or []
                if not isinstance(bucket, list):
                    continue
                for entry in bucket:
                    if isinstance(entry, dict):
                        entries.append(entry)
            for entry in sorted(entries,
                                key=lambda e: e.get("name", "").lower()):
                name = entry.get("name", "")
                if not name or name in self._mod_quest_encounter_names:
                    continue
                self._mod_quest_encounter_names.append(name)
                tile = entry.get("monster_party_tile", "")
                if tile:
                    self._mod_quest_encounter_tiles[name] = tile
            break  # use first found file

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

        # Ensure encounter names and artifact tiles are loaded.
        # (Monster names are still loaded for legacy previews, but the
        # pickers below now use encounters.)
        self._mod_quest_load_monster_names()
        self._mod_quest_load_encounter_names()
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

        common_bottom = []

        if step_type == "kill":
            # Kill: Encounter, Spawn Location, Target Count
            current_encounter = step.get("encounter", "")
            if not current_encounter:
                current_encounter = "(none)"
            type_fields = [
                FieldEntry("Encounter", "encounter",
                           current_encounter, "choice", True),
                FieldEntry("Spawn Location", "spawn_location",
                           spawn_loc_display, "choice", True),
                FieldEntry("Target Count", "target_count",
                           str(step.get("target_count", 1)), "int", True),
            ]
        else:
            # Collect: Item, Spawn Location, Spawn Col/Row,
            # Target Count, Guardian, Guardian Encounter
            current_item = step.get("collect_item", "")
            if not current_item:
                current_item = "(none)"
            has_guardian = step.get("has_guardian", "no")
            # Spawn col/row are optional overrides on top of Spawn
            # Location.  Blank in the UI = "any walkable tile" (the
            # default random placement).  Same convention as the
            # quest-giver giver_col/giver_row fields above.
            type_fields = [
                FieldEntry("Item", "collect_item",
                           current_item, "choice", True),
                FieldEntry("Spawn Location", "spawn_location",
                           spawn_loc_display, "choice", True),
                FieldEntry("Spawn Col", "spawn_col",
                           str(step.get("spawn_col", "")), "int", True),
                FieldEntry("Spawn Row", "spawn_row",
                           str(step.get("spawn_row", "")), "int", True),
                FieldEntry("Target Count", "target_count",
                           str(step.get("target_count", 1)), "int", True),
                FieldEntry("", "", "", "section", False),
                FieldEntry("Guardian", "has_guardian",
                           has_guardian, "choice", True),
            ]
            if has_guardian == "yes":
                guardian_encounter = step.get("guardian_encounter", "")
                if not guardian_encounter:
                    guardian_encounter = "(none)"
                type_fields.append(
                    FieldEntry("Guardian Encounter", "guardian_encounter",
                               guardian_encounter, "choice", True))

        self._mod_quest_step_fields = common_top + type_fields + common_bottom
        self._mod_quest_step_choice_map = {
            "step_type": self._QUEST_STEP_TYPES,
            "encounter": getattr(self, "_mod_quest_encounter_names",
                                 ["(none)"]),
            "guardian_encounter": getattr(self, "_mod_quest_encounter_names",
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
                # spawn_col / spawn_row: blank means "any walkable tile"
                # — pop the key so the runtime spawner falls back to
                # random placement.  Same convention as giver_col /
                # giver_row on quest-giver settings.
                if key in ("spawn_col", "spawn_row") and (
                        val == "" or val is None):
                    step.pop(key, None)
                    continue
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            # Store "(none)" as empty string for choice fields
            if key in ("encounter", "guardian_encounter",
                       "collect_item") and val == "(none)":
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
            "reward_items": [],
            "reward_world_unlocks": [],
            "steps": [],
        }
        self._mod_quest_list.append(new_quest)
        self._mod_quest_cursor = len(self._mod_quest_list) - 1
        self._save_module_quests()

    # ── Reward item picker helpers ──

    @staticmethod
    def _mod_quest_format_reward_items(items):
        """Return a short summary string for the Reward Items field.

        Shown inline in the settings panel so the editor can see the
        current rewards at a glance without opening the picker.
        """
        if not items:
            return "(none)  [Enter to pick]"
        if len(items) == 1:
            return items[0]
        preview = ", ".join(items[:3])
        if len(items) > 3:
            preview += f", +{len(items) - 3} more"
        return f"{len(items)}: {preview}"

    def _mod_quest_load_item_names(self):
        """Load all item names from party.WEAPONS / ARMORS / ITEM_INFO.

        Cached on first call; invalidate via
        ``self._mod_quest_item_picker_list = None`` when item data
        might have changed (e.g., module switch).
        """
        if getattr(self, "_mod_quest_item_picker_list", None):
            return self._mod_quest_item_picker_list
        try:
            from src.party import WEAPONS, ARMORS, ITEM_INFO
            names = sorted(set(list(WEAPONS.keys())
                               + list(ARMORS.keys())
                               + list(ITEM_INFO.keys())))
        except Exception:
            names = []
        self._mod_quest_item_picker_list = names
        return names

    def _mod_quest_open_item_picker(self):
        """Open the reward item grid picker for the current quest."""
        quest = self._mod_quest_get_current()
        if not quest:
            return
        self._mod_quest_load_item_names()
        self._mod_quest_item_picker_active = True
        self._mod_quest_item_picker_cursor = 0
        self._mod_quest_item_picker_scroll = 0

    def _mod_quest_toggle_reward_item(self, item_name):
        """Add or remove *item_name* from the current quest's
        reward_items list."""
        quest = self._mod_quest_get_current()
        if not quest:
            return
        items = list(quest.get("reward_items", []))
        if item_name in items:
            items.remove(item_name)
        else:
            items.append(item_name)
        quest["reward_items"] = items
        self._save_module_quests()
        # Refresh the field display so the summary updates live.
        for fe in self._mod_quest_fields:
            if fe.key == "reward_items":
                fe.value = self._mod_quest_format_reward_items(items)
                break

    def _mod_quest_add_step(self):
        """Add a new default step to the current quest."""
        new_step = {
            "description": "New Step",
            "step_type": "collect",
            "encounter": "",
            "collect_item": "",
            "has_guardian": "no",
            "guardian_encounter": "",
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

        # Changing the Unlock Kind toggles whether Col/Row/Tile are
        # editable and what tile types are offered — rebuild the field
        # list (same pattern used for step_type / has_guardian on the
        # step editor).
        if field.key == "unlock_kind":
            # Persist current values so the rebuild picks them up,
            # then re-emit the field list.
            self._mod_quest_save_settings_fields()
            current_idx = self._mod_quest_field
            self._mod_quest_build_settings_fields()
            # _build_ resets cursor to first editable field; restore
            # the position the user was on so cycling feels stable.
            if current_idx < len(self._mod_quest_fields):
                cur = self._mod_quest_fields[current_idx]
                if cur.editable and cur.field_type != "section":
                    self._mod_quest_field = current_idx
                    self._mod_quest_buffer = (
                        cur.value if cur.field_type
                        not in ("choice", "item_list") else "")

    def _handle_mod_quest_settings_field_input(self, event):
        """Handle input for quest settings field editing (level 22)."""
        import pygame

        # Intercept reward-items picker overlay first so it captures
        # all input while open.
        if getattr(self, "_mod_quest_item_picker_active", False):
            self._handle_mod_quest_item_picker_input(event)
            return

        fields = self._mod_quest_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 21
            return

        current_field = fields[self._mod_quest_field]

        # Enter on an "item_list" field opens the reward-items picker.
        if (event.key in (pygame.K_RETURN, pygame.K_SPACE)
                and current_field.field_type == "item_list"
                and current_field.editable):
            self._mod_quest_open_item_picker()
            return

        if self._is_save_shortcut(event):
            if current_field.editable and current_field.field_type not in ("choice", "item_list"):
                current_field.value = self._mod_quest_buffer
            self._mod_quest_save_settings_fields()
            self._save_module_quests()
            self._mod_quest_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            if current_field.editable and current_field.field_type not in ("choice", "item_list"):
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
            if current_field.editable and current_field.field_type not in ("choice", "item_list"):
                current_field.value = self._mod_quest_buffer
            self._mod_quest_field = fe._next_editable_generic(
                fields, (self._mod_quest_field - 1) % n)
            nf = fields[self._mod_quest_field]
            self._mod_quest_buffer = (
                nf.value
                if nf.field_type not in ("choice", "item_list")
                else "")
            self._mod_quest_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_quest_field, self._mod_quest_field_scroll)
        elif event.key == pygame.K_DOWN:
            if current_field.editable and current_field.field_type not in ("choice", "item_list"):
                current_field.value = self._mod_quest_buffer
            self._mod_quest_field = fe._next_editable_generic(
                fields, (self._mod_quest_field + 1) % n)
            nf = fields[self._mod_quest_field]
            self._mod_quest_buffer = (
                nf.value
                if nf.field_type not in ("choice", "item_list")
                else "")
            self._mod_quest_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_quest_field, self._mod_quest_field_scroll)
        elif current_field.field_type in ("choice", "item_list"):
            # Don't allow typing on choice or item-list fields
            pass
        elif event.key == pygame.K_BACKSPACE:
            self._mod_quest_buffer = self._mod_quest_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            self._mod_quest_buffer += event.unicode

    def _handle_mod_quest_item_picker_input(self, event):
        """Handle input for the reward-items picker overlay.

        Grid navigation (Up/Down/Left/Right/PgUp/PgDn/Home/End) moves
        the cursor. Enter toggles the focused item in/out of the
        current quest's ``reward_items`` list. Esc closes the picker.
        """
        import pygame
        from src.settings import SCREEN_WIDTH
        names = getattr(self, "_mod_quest_item_picker_list", None) or []
        n = len(names)
        if not n:
            self._mod_quest_item_picker_active = False
            return

        # Grid width must match the renderer's modal sizing exactly.
        # Renderer formula:
        #   pw = min(SCREEN_WIDTH - 40, 760)
        #   cols = max(1, (pw - pad_in*2) // cell_w)   pad_in=14, cell_w=64
        # Mirrored here so Up/Down jumps the same row height the
        # user actually sees on screen.
        pw = min(SCREEN_WIDTH - 40, 760)
        cols_per_row = max(1, (pw - 28) // 64)

        if event.key == pygame.K_ESCAPE:
            self._mod_quest_item_picker_active = False
            return
        if event.key == pygame.K_UP:
            self._mod_quest_item_picker_cursor = max(
                0, self._mod_quest_item_picker_cursor - cols_per_row)
        elif event.key == pygame.K_DOWN:
            self._mod_quest_item_picker_cursor = min(
                n - 1,
                self._mod_quest_item_picker_cursor + cols_per_row)
        elif event.key == pygame.K_LEFT:
            self._mod_quest_item_picker_cursor = max(
                0, self._mod_quest_item_picker_cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self._mod_quest_item_picker_cursor = min(
                n - 1, self._mod_quest_item_picker_cursor + 1)
        elif event.key == pygame.K_PAGEUP:
            self._mod_quest_item_picker_cursor = max(
                0, self._mod_quest_item_picker_cursor - cols_per_row * 4)
        elif event.key == pygame.K_PAGEDOWN:
            self._mod_quest_item_picker_cursor = min(
                n - 1,
                self._mod_quest_item_picker_cursor + cols_per_row * 4)
        elif event.key == pygame.K_HOME:
            self._mod_quest_item_picker_cursor = 0
        elif event.key == pygame.K_END:
            self._mod_quest_item_picker_cursor = n - 1
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            idx = self._mod_quest_item_picker_cursor
            if 0 <= idx < n:
                self._mod_quest_toggle_reward_item(names[idx])

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

