"""
Dungeon state - exploring a procedurally generated dungeon.

The party navigates dark corridors and rooms, finds treasure chests,
avoids traps, and can exit via the stairs back to the overworld.
"""

import random

import pygame

from src.states.base_state import BaseState
from src.states.inventory_mixin import InventoryMixin
from src.states.lock_mixin import LockInteractionMixin
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_STAIRS, TILE_CHEST, TILE_TRAP, TILE_DFLOOR,
    TILE_STAIRS_DOWN, TILE_ARTIFACT, TILE_PORTAL, TILE_LOCKED_DOOR, TILE_DDOOR,
    TILE_DUNGEON_CLEARED, TILE_PUDDLE, TILE_MOSS, TILE_WALL_TORCH,
    GUARDIAN_LEASH, GUARDIAN_INTERCEPT_RANGE_INTERIOR,
)


class DungeonState(LockInteractionMixin, InventoryMixin, BaseState):
    """Handles exploration inside a dungeon."""

    def __init__(self, game):
        super().__init__(game)
        self.dungeon_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        self._init_inventory_state()
        # Pick-lock / Knock dialog state lives on the mixin so the
        # same UX works for legacy TILE_LOCKED_DOOR tiles AND any
        # designer-placed tile with tile_properties['locked']=True.
        self._init_lock_interaction()

        # Torch lighting system
        self.torch_active = False
        self.torch_steps = 0

        # Save overworld position for when we leave
        self.overworld_col = 0
        self.overworld_row = 0

        # Quest dungeon multi-level support
        self.quest_levels = None   # list of DungeonData if this is a quest dungeon
        self.current_level = 0     # 0 or 1
        self._torch_lit_cache = None  # cached set of tiles lit by wall torches

        # Message queued by combat state on return
        self.pending_combat_message = None
        # Track if we've already entered (so re-entry from combat doesn't reset position)
        self._entered = False

        # ── Encounter action screen (Fight / Flee) ──
        self.encounter_action_active = False
        self.encounter_action_cursor = 0   # 0=Engage, 1=Flee
        self.encounter_action_monster = None
        self.encounter_action_result = None   # None, "fled", "fled_far", "failed"
        self.encounter_result_timer = 0
        self._encounter_flee_distance = 0

        # ── Help overlay ──
        self.showing_help = False

        # ── Artifact pickup animation ──
        self.artifact_pickup_anim = None  # {"col", "row", "timer", "duration", "name"}
        # (door_unlock_anim is managed by LockInteractionMixin; see
        # self._init_lock_interaction() above.)

    def reset_for_new_game(self):
        """Drop all dungeon-local state so a fresh game doesn't inherit
        torch timers, queued combat messages, or door/encounter overlays
        from a previous session. The state instance is cached on the
        Game so it must be explicitly scrubbed on new-game."""
        self.dungeon_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        self.torch_active = False
        self.torch_steps = 0
        self.overworld_col = 0
        self.overworld_row = 0
        self.quest_levels = None
        self.current_level = 0
        self._torch_lit_cache = None
        self.pending_combat_message = None
        self._entered = False
        # Lock-dialog + unlock-animation state is owned by the mixin.
        if hasattr(self, "_init_lock_interaction"):
            self._init_lock_interaction()
        self.encounter_action_active = False
        self.encounter_action_cursor = 0
        self.encounter_action_monster = None
        self.encounter_action_result = None
        self.encounter_result_timer = 0
        self._encounter_flee_distance = 0
        self.showing_help = False
        self.artifact_pickup_anim = None
        if hasattr(self, "_init_inventory_state"):
            self._init_inventory_state()

    def enter_dungeon(self, dungeon_data, overworld_col, overworld_row):
        """
        Set up the dungeon state with dungeon-specific data.
        Called before change_state.
        """
        self.dungeon_data = dungeon_data
        self.overworld_col = overworld_col
        self.overworld_row = overworld_row
        self.quest_levels = None
        self.current_level = 0
        self._entered = False
        self.pending_combat_message = None
        self._invalidate_torch_cache()

    def _get_active_quest(self):
        """Return the quest dict that owns this dungeon, or None."""
        oc, orow = self.overworld_col, self.overworld_row
        # Check key dungeons first (Keys of Shadow module)
        # Include "undiscovered" so the artifact pickup still works
        # if the player explores before accepting the quest.
        kd = self.game.get_key_dungeon(oc, orow)
        if kd and kd.get("status") in ("undiscovered", "active", "artifact_found"):
            return kd
        # Check standard quests
        for q in (self.game.get_quest(), self.game.get_house_quest()):
            if (q and q.get("status") in ("active", "artifact_found")
                    and q.get("dungeon_col") == oc
                    and q.get("dungeon_row") == orow):
                return q
        return None

    def _check_kill_quest_progress(self):
        """After combat, check if killed monsters count toward a kill quest.

        Reads ``game.pending_killed_monsters`` (set by combat victory),
        increments the quest's ``kill_progress``, and spawns a portal
        when the required kill count is reached.
        Also checks module quest kill steps.
        """
        killed = getattr(self.game, "pending_killed_monsters", [])
        if not killed:
            return

        # Check module quest kills BEFORE consuming the list
        mod_msg = self._check_module_quest_kills()
        if mod_msg:
            self.show_message(mod_msg, 4000)

        # Consume the list so it doesn't get counted again
        self.game.pending_killed_monsters = []
        self.game.pending_combat_location = ""

        active_q = self._get_active_quest()
        if not active_q or active_q.get("quest_type") != "kill":
            return

        target = active_q.get("kill_target", "")
        if not target:
            return

        count = sum(1 for name in killed if name == target)
        if count <= 0:
            return

        progress = active_q.get("kill_progress", 0) + count
        active_q["kill_progress"] = progress
        needed = active_q.get("kill_count", 1)

        if progress >= needed and active_q.get("status") != "artifact_found":
            active_q["status"] = "artifact_found"
            pcol, prow = self.game.party.col, self.game.party.row
            # Only spawn a portal if exit_portal is enabled
            if active_q.get("exit_portal", True):
                self._place_portal(pcol, prow)
                self.game.sfx.play("critical")
                self.show_message(
                    f"Quest complete! {progress}/{needed} {target}s defeated! "
                    f"A portal appears!", 3500)
            else:
                self.game.sfx.play("critical")
                self.show_message(
                    f"Quest complete! {progress}/{needed} {target}s defeated!",
                    3500)
        else:
            self.show_message(
                f"{target} defeated! ({progress}/{needed})", 2000)

    def _check_module_quest_kills(self):
        """After combat in a dungeon, check if killed monsters count
        toward any active module quest kill steps.

        Works like the overworld / town version but runs inside the
        dungeon state so kills are credited immediately.
        """
        from src.quest_manager import check_quest_kills
        result_msg = check_quest_kills(self.game)
        return result_msg

    def _inject_quest_dungeon_monsters(self):
        """Add quest-registered monsters to the dungeon's monster list.

        Reads ``game.quest_dungeon_monsters`` for entries matching this
        dungeon's name, creates Monster objects and adds them to
        ``dungeon_data.monsters`` on walkable tiles.

        Quest monsters only spawn on the **lowest** floor of a
        multi-level dungeon so the player must descend all the way
        before encountering the boss.
        """
        import random as _rng
        import re
        from src.monster import create_monster, MONSTERS

        # Only place quest monsters on the lowest floor
        if self.quest_levels:
            if self.current_level < len(self.quest_levels) - 1:
                return  # not the lowest floor yet

        dname = getattr(self.dungeon_data, "name", "")
        monsters_dict = getattr(self.game, "quest_dungeon_monsters", {})

        # Try exact floor name first, then base dungeon name
        entries = monsters_dict.get(dname, [])
        if not entries:
            # Strip " - Floor N" suffix to match base name
            base_name = re.sub(r"\s*-\s*Floor\s+\d+$", "", dname)
            if base_name != dname:
                entries = monsters_dict.get(base_name, [])
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})
        tmap = self.dungeon_data.tile_map

        # Collect walkable floor tiles
        walkable = []
        for wy in range(tmap.height):
            for wx in range(tmap.width):
                if tmap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = {(m.col, m.row) for m in self.dungeon_data.monsters
                    if m.is_alive()}
        occupied.add((self.dungeon_data.entry_col,
                       self.dungeon_data.entry_row))

        rng = _rng.Random(hash(dname) & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            monster_key = entry["monster_key"]
            count = entry.get("count", 1)

            # Skip if quest is no longer active
            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            # Skip if this step is already complete
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue
            # Skip if quest monsters for this step are already present
            already = any(
                getattr(m, "_quest_name", None) == qname
                and getattr(m, "_quest_step_idx", None) == step_idx
                for m in self.dungeon_data.monsters)
            if already:
                continue

            for i in range(count):
                mon = create_monster(monster_key)
                mon._quest_name = qname
                mon._quest_step_idx = step_idx

                free = [p for p in walkable if p not in occupied]
                if free:
                    col, row = rng.choice(free)
                else:
                    col = self.dungeon_data.entry_col + 3 + i
                    row = self.dungeon_data.entry_row
                mon.col = col
                mon.row = row
                mon.encounter_template = {
                    "name": f"Quest: {mon.name}",
                    "monster_names": [monster_key],
                    "monster_party_tile": monster_key,
                }
                self.dungeon_data.monsters.append(mon)
                occupied.add((col, row))

    def _inject_quest_dungeon_collect_items(self):
        """Place quest collect items on the current dungeon floor.

        Items only spawn on the **lowest** floor of a multi-level dungeon.
        Guardian monsters are also placed near the item and anchored to it.
        """
        import random as _rng
        import re
        from src.monster import create_monster, MONSTERS
        from src.town_generator import NPC

        # Only place items on the lowest floor
        if self.quest_levels:
            if self.current_level < len(self.quest_levels) - 1:
                return  # not the lowest floor yet

        dname = getattr(self.dungeon_data, "name", "")
        items_dict = getattr(self.game, "quest_collect_items", {})

        # Match both exact floor name and base dungeon name
        key = f"dungeon:{dname}"
        entries = items_dict.get(key, [])
        if not entries:
            base_name = re.sub(r"\s*-\s*Floor\s+\d+$", "", dname)
            if base_name != dname:
                entries = items_dict.get(f"dungeon:{base_name}", [])
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})
        tmap = self.dungeon_data.tile_map

        # Ensure quest_items list exists on dungeon data
        if not hasattr(self.dungeon_data, "quest_items"):
            self.dungeon_data.quest_items = []

        # Skip if items are already placed on this floor
        if self.dungeon_data.quest_items:
            return

        # Collect walkable floor tiles
        walkable = set()
        for wy in range(tmap.height):
            for wx in range(tmap.width):
                if tmap.is_walkable(wx, wy):
                    walkable.add((wx, wy))

        occupied = {(m.col, m.row) for m in self.dungeon_data.monsters
                    if m.is_alive()}
        occupied.add((self.dungeon_data.entry_col,
                       self.dungeon_data.entry_row))

        rng = _rng.Random(hash(("collect", dname)) & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            item_name = entry["item_name"]
            item_sprite = entry.get("item_sprite", "")
            has_guardian = entry.get("has_guardian", False)
            guardian_key = entry.get("guardian_key")

            # Skip if quest is no longer active
            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            # Skip if this step is already complete
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue

            # Place the collect item
            free = [p for p in walkable if p not in occupied]
            if not free:
                continue
            col, row = rng.choice(free)
            occupied.add((col, row))

            item_obj = {
                "col": col,
                "row": row,
                "quest_name": qname,
                "step_idx": step_idx,
                "item_name": item_name,
                "item_sprite": item_sprite,
            }
            self.dungeon_data.quest_items.append(item_obj)

            # Place guardian monster near the item
            if has_guardian and guardian_key:
                # Find a free tile adjacent to the item
                nearby = [(col + dc, row + dr)
                          for dc in range(-2, 3)
                          for dr in range(-2, 3)
                          if (dc, dr) != (0, 0)
                          and (col + dc, row + dr) in walkable
                          and (col + dc, row + dr) not in occupied]
                if nearby:
                    gc, gr = rng.choice(nearby)
                else:
                    gfree = [p for p in walkable if p not in occupied]
                    if gfree:
                        gc, gr = rng.choice(gfree)
                    else:
                        continue

                mon = create_monster(guardian_key)
                mon._quest_name = qname
                mon._quest_step_idx = step_idx
                mon._guardian_anchor = (col, row)
                mon._guardian_leash = GUARDIAN_LEASH
                mon.col = gc
                mon.row = gr
                mon.encounter_template = {
                    "name": f"Quest: {mon.name}",
                    "monster_names": [guardian_key],
                    "monster_party_tile": guardian_key,
                }
                self.dungeon_data.monsters.append(mon)
                occupied.add((gc, gr))

    def _get_quest_item_at(self, col, row):
        """Return the quest collect item dict at (col, row), or None."""
        if not hasattr(self.dungeon_data, "quest_items"):
            return None
        for item in self.dungeon_data.quest_items:
            if item["col"] == col and item["row"] == row:
                return item
        return None

    def _collect_dungeon_quest_item(self, item_obj):
        """Pick up a quest collectible item in the dungeon."""
        from src.quest_manager import collect_quest_item
        qname = item_obj["quest_name"]
        step_idx = item_obj["step_idx"]
        item_name = item_obj["item_name"]

        if hasattr(self.dungeon_data, "quest_items"):
            if item_obj in self.dungeon_data.quest_items:
                self.dungeon_data.quest_items.remove(item_obj)

        msg = collect_quest_item(
            self.game, qname, step_idx, item_name)
        self.show_message(msg, 3000 if "complete" in msg.lower() else 2500)

    def _spawn_placed_encounters(self):
        """Materialize designer-placed encounter templates as monsters.

        Matches the overworld pattern: scans the current dungeon
        level's ``tile_map.tile_properties`` for ``"encounter"``
        entries and creates one party-leader Monster per placement,
        attaching ``encounter_template`` so the existing bump-to-
        fight / Attack-Run dialog (see :meth:`_show_encounter_action`
        and :meth:`_start_combat`) handles the fight downstream —
        including the template's custom XP override and loot.

        **Spawn-once semantics.** Every placement materialises at
        most once per dungeon_data lifetime. The set of spawned
        positions is stashed on ``dungeon_data`` so it survives
        state re-entries (returning from combat, descending and
        ascending levels, exiting and re-entering the dungeon) as
        long as the same dungeon_data instance is in play. A
        defeated placement therefore stays defeated — no respawns.
        """
        from src.monster import find_encounter_template, create_monster
        if not self.dungeon_data:
            return
        tile_map = self.dungeon_data.tile_map
        tprops = getattr(tile_map, "tile_properties", None) or {}
        if not tprops:
            return
        # Stash the spawn-once set on dungeon_data so it persists
        # across state re-entries for this dungeon instance.
        spawned = getattr(
            self.dungeon_data, "_spawned_placement_positions", None)
        if spawned is None:
            spawned = set()
            self.dungeon_data._spawned_placement_positions = spawned
        for pos_key, props in tprops.items():
            if not isinstance(props, dict):
                continue
            enc_name = props.get("encounter")
            if not enc_name:
                continue
            parts = pos_key.split(",")
            if len(parts) != 2:
                continue
            try:
                c, r = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            # Spawn-once gate.
            if (c, r) in spawned:
                continue
            if not (0 <= c < tile_map.width
                    and 0 <= r < tile_map.height):
                continue
            tmpl = find_encounter_template(enc_name)
            if tmpl is None:
                continue
            party_tile = (tmpl.get("monster_party_tile")
                          or (tmpl.get("monsters") or [""])[0])
            if not party_tile:
                continue
            mon = create_monster(party_tile)
            mon.col = c
            mon.row = r
            mon.encounter_template = {
                "name": tmpl.get("name", enc_name),
                "monster_names": list(tmpl.get("monsters") or []),
                "monster_party_tile": party_tile,
                "xp_override": tmpl.get("xp_override"),
                "loot": tmpl.get("loot"),
            }
            mon._placement_pos = (c, r)
            self.dungeon_data.monsters.append(mon)
            spawned.add((c, r))

    def enter_quest_dungeon(self, levels, overworld_col, overworld_row):
        """
        Set up a multi-level quest dungeon.
        levels is a list of DungeonData [level_0, level_1].
        """
        self.quest_levels = levels
        self.current_level = 0
        self.dungeon_data = levels[0]
        self.overworld_col = overworld_col
        self.overworld_row = overworld_row
        self._entered = False
        self.pending_combat_message = None
        self._invalidate_torch_cache()

    def enter(self):
        """Called when this state becomes active."""
        self._apply_pending_combat_rewards()
        self._check_kill_quest_progress()
        # Returning from combat — keep party position, just show message
        if self._entered and self.dungeon_data:
            if self.pending_combat_message:
                self.show_message(self.pending_combat_message, 2500)
                self.pending_combat_message = None
            # Refresh camera to current party position
            self.game.camera.map_width = self.dungeon_data.tile_map.width
            self.game.camera.map_height = self.dungeon_data.tile_map.height
            self.game.camera.update(self.game.party.col, self.game.party.row)
            return

        # First entry into dungeon
        if self.dungeon_data:
            self._entered = True
            # Inject quest monsters and collect items for this dungeon
            self._inject_quest_dungeon_monsters()
            self._inject_quest_dungeon_collect_items()
            # Materialize designer-placed encounter markers from the
            # dungeon map's tile_properties so they behave like any
            # other dungeon monster (bump-to-fight, standard Attack/
            # Run dialog, template-driven combat).
            self._spawn_placed_encounters()
            # Try to light the equipped torch automatically
            if self._activate_torch():
                self.show_message(
                    f"You descend into {self.dungeon_data.name}... Torch lit!", 2500
                )
            else:
                self.show_message(
                    f"You descend into {self.dungeon_data.name}... No torch equipped!", 2500
                )
            # Move party to dungeon entry point.
            # entry_col/entry_row is already resolved by the
            # overworld loader (using to_overworld exits).
            # Just verify it is walkable as a safety net.
            ecol = self.dungeon_data.entry_col
            erow = self.dungeon_data.entry_row
            tmap = self.dungeon_data.tile_map
            from src.settings import TILE_DEFS as _TD
            if not _TD.get(tmap.get_tile(ecol, erow),
                           {}).get("walkable", False):
                for r in range(tmap.height):
                    for c in range(tmap.width):
                        if _TD.get(tmap.get_tile(c, r),
                                   {}).get("walkable", False):
                            ecol, erow = c, r
                            break
                    else:
                        continue
                    break
            self.game.party.col = ecol
            self.game.party.row = erow
            # Update camera for the dungeon map
            self.game.camera.map_width = self.dungeon_data.tile_map.width
            self.game.camera.map_height = self.dungeon_data.tile_map.height
            self.game.camera.update(self.game.party.col, self.game.party.row)

    def exit(self):
        """Called when leaving this state."""
        pass

    def handle_input(self, events, keys_pressed):
        """Handle movement and interactions."""
        for event in events:
            if event.type == pygame.KEYDOWN:
                # ── Help overlay input ──
                if self.showing_help:
                    if event.key in (pygame.K_h, pygame.K_ESCAPE):
                        self.showing_help = False
                    return

                # ── Log overlay input ──
                if self.showing_log:
                    if event.key == pygame.K_l or event.key == pygame.K_ESCAPE:
                        self.showing_log = False
                    elif event.key == pygame.K_UP:
                        self.log_scroll += 3
                    elif event.key == pygame.K_DOWN:
                        self.log_scroll = max(0, self.log_scroll - 3)
                    return

                # ── Encounter action screen input ──
                if self.encounter_action_active:
                    self._handle_encounter_action_input(event)
                    return

                # ── Door interaction prompt input ──
                if self.door_interact_active:
                    self._handle_lock_interact_input(event)
                    return

                # ── Party inventory screen input ──
                if self.showing_party_inv:
                    self._handle_party_inv_input(event)
                    return

                # ── Action menu input ──
                if self.char_action_menu and self.showing_char_detail is not None:
                    self._handle_char_action_input(event)
                    return

                if event.key == pygame.K_p:
                    if self.showing_char_detail is not None:
                        origin = self.char_sheet_origin
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = None
                        if origin == "inventory":
                            self.showing_party_inv = True
                        elif origin == "party":
                            self.showing_party = True
                        return
                    if self.showing_party_inv:
                        self.showing_party_inv = False
                        return
                    if self.showing_party:
                        self.showing_party = False
                        return
                    self.showing_party_inv = True
                    self.party_inv_cursor = 0
                    self.party_inv_choosing = False
                    self.party_inv_member = 0
                    return
                if event.key == pygame.K_ESCAPE:
                    if self.showing_char_detail is not None:
                        origin = self.char_sheet_origin
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = None
                        if origin == "inventory":
                            self.showing_party_inv = True
                        elif origin == "party":
                            self.showing_party = True
                        return
                    if self.showing_party:
                        self.showing_party = False
                        return
                    # Only allow escape if standing on stairs or a custom exit door
                    tile_id = self.dungeon_data.tile_map.get_tile(
                        self.game.party.col, self.game.party.row
                    )
                    pcol, prow = self.game.party.col, self.game.party.row
                    custom_exits = getattr(
                        self.dungeon_data.tile_map, "_custom_exit_doors", None
                    )
                    on_custom_exit = (
                        custom_exits and (pcol, prow) in custom_exits
                    )
                    if tile_id == TILE_STAIRS:
                        if self.quest_levels and self.current_level > 0:
                            # Ascend one level up in a multi-level dungeon
                            self._ascend_level()
                        else:
                            # Already on top floor (level 0) — exit to overworld
                            self._exit_dungeon()
                    elif on_custom_exit:
                        if self.quest_levels and self.current_level > 0:
                            self._ascend_level()
                        else:
                            self._exit_dungeon()
                    else:
                        self.show_message(
                            "Find the exit to escape!", 1500
                        )
                    return
                if event.key == pygame.K_l:
                    self.showing_log = True
                    self.log_scroll = 0
                    return
                if event.key == pygame.K_h:
                    self.showing_help = True
                    return
                # Character sheet cursor navigation
                if self.showing_char_detail is not None:
                    member = self.game.party.members[self.showing_char_detail]
                    total_rows = 4 + len(member.inventory)
                    if event.key == pygame.K_UP:
                        self.char_sheet_cursor = (self.char_sheet_cursor - 1) % total_rows
                        return
                    elif event.key == pygame.K_DOWN:
                        self.char_sheet_cursor = (self.char_sheet_cursor + 1) % total_rows
                        return
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._handle_equip_action(member)
                        return
                # 1-4 keys to open character detail from party screen
                if self.showing_party and self.showing_char_detail is None:
                    num = None
                    if event.key == pygame.K_1:
                        num = 0
                    elif event.key == pygame.K_2:
                        num = 1
                    elif event.key == pygame.K_3:
                        num = 2
                    elif event.key == pygame.K_4:
                        num = 3
                    if num is not None and num < len(self.game.party.members):
                        self.showing_char_detail = num
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = "party"
                        return
                    if event.key == pygame.K_5:
                        self.showing_party_inv = True
                        self.party_inv_cursor = 0
                        self.party_inv_choosing = False
                        self.party_inv_member = 0
                        return

        # If showing party screen, character detail, party inventory,
        # door prompt, or encounter action, block movement
        if (self.showing_party or self.showing_char_detail is not None
                or self.showing_party_inv or self.door_interact_active
                or self.door_unlock_anim or self.encounter_action_active):
            return

        # ── Free-look / map-scroll mode (Shift + arrows) ──────
        # Holding Shift detaches the camera from the party so the
        # player can pan across the dungeon to review previously
        # explored tiles. Panning does NOT advance game time and
        # does NOT move the party. Releasing Shift snaps the
        # camera back to the party on the next frame.
        mods = pygame.key.get_mods()
        shift_held = bool(mods & pygame.KMOD_SHIFT)
        if shift_held and not self.game.camera.free_look:
            self.game.camera.enter_free_look()
        elif not shift_held and self.game.camera.free_look:
            self.game.camera.exit_free_look()

        # Movement
        if self.move_cooldown > 0:
            return

        dcol, drow = 0, 0
        if keys_pressed[pygame.K_LEFT] or keys_pressed[pygame.K_a]:
            dcol = -1
        elif keys_pressed[pygame.K_RIGHT] or keys_pressed[pygame.K_d]:
            dcol = 1
        elif keys_pressed[pygame.K_UP] or keys_pressed[pygame.K_w]:
            drow = -1
        elif keys_pressed[pygame.K_DOWN] or (
                keys_pressed[pygame.K_s]
                and not ((pygame.key.get_mods()
                          & ~(pygame.KMOD_CAPS | pygame.KMOD_NUM))
                         & (pygame.KMOD_CTRL | pygame.KMOD_META
                            | getattr(pygame, "KMOD_GUI", 0)))):
            drow = 1

        # In free-look mode, arrow keys pan the camera instead of
        # moving the party.
        if shift_held:
            if dcol != 0 or drow != 0:
                self.game.camera.pan(dcol, drow)
                self.move_cooldown = MOVE_REPEAT_DELAY
            return

        if dcol != 0 or drow != 0:
            self._try_move(dcol, drow)

    def _try_move(self, dcol, drow):
        """Move the party within the dungeon, then let monsters take a step."""
        party = self.game.party
        target_col = party.col + dcol
        target_row = party.row + drow

        # Check for quest collect item at target (bump-to-collect)
        quest_item = self._get_quest_item_at(target_col, target_row)
        if quest_item:
            self._collect_dungeon_quest_item(quest_item)
            self.move_cooldown = MOVE_REPEAT_DELAY
            return

        # Check for monster at target position (bump-to-encounter)
        monster = self._get_monster_at(target_col, target_row)
        if monster:
            self._show_encounter_action(monster)
            self.move_cooldown = MOVE_REPEAT_DELAY
            return

        # Check for locked door — legacy TILE_LOCKED_DOOR OR any tile
        # with tile_properties['locked']=True. The mixin routes both
        # through the same Pick Lock / Cast Knock dialog.
        if self._try_open_locked(self.dungeon_data.tile_map,
                                  target_col, target_row):
            self.move_cooldown = MOVE_REPEAT_DELAY
            return

        if self.dungeon_data.tile_map.is_walkable(target_col, target_row):
            party.col = target_col
            party.row = target_row
            self.move_cooldown = MOVE_REPEAT_DELAY
            self._check_tile_events()
            self._attempt_trap_detection()
            # Check contact BEFORE monsters move so the player only
            # enters combat with monsters they could see as adjacent
            # (matches overworld behaviour).
            self._check_monster_contact()
            if not self.encounter_action_active:
                self._move_monsters()
                # A monster may have walked adjacent — check again
                self._check_monster_contact()
            # Burn torch after each successful step
            self._tick_torch()
            # Tick Galadriel's Light step counter
            self._tick_galadriels_light()
        else:
            self.move_cooldown = MOVE_REPEAT_DELAY

    # ── InventoryMixin hook overrides (torch handling) ───────────

    def _on_effect_assigned(self, effect_name):
        """Auto-activate torch when assigned to an effect slot in dungeon."""
        if effect_name == "Torch":
            self._activate_torch()

    def _on_effect_removed(self, effect_name):
        """Deactivate torch when removed from an effect slot in dungeon."""
        if effect_name == "Torch":
            self.torch_active = False
            self.torch_steps = 0

    def _on_item_equipped(self, item_name):
        """Auto-activate torch when equipped from stash in dungeon."""
        if item_name == "Torch":
            self._activate_torch()

    # ── Torch system ───────────────────────────────────────────

    def _activate_torch(self):
        """Activate the torch equipped in the party LIGHT slot.

        Returns True if a torch is equipped and was activated, False otherwise.
        Uses the item's charges to determine burn duration.
        """
        party = self.game.party
        if party.get_equipped_name("light") == "Torch":
            charges = party.get_equipped_charges("light")
            self.torch_active = True
            self.torch_steps = charges if charges is not None else 10
            return True
        return False

    def _consume_torch(self):
        """Remove the burned-out torch from the party LIGHT slot and effect."""
        party = self.game.party
        if party.get_equipped_name("light") == "Torch":
            party.equipped["light"] = None
        # Clear the Torch from whichever effect slot it occupies
        for slot_key in party.EFFECT_SLOTS:
            if party.get_effect(slot_key) == "Torch":
                party.effects[slot_key] = None
                break

    def _has_torch_equipped(self):
        """Check if a torch is equipped in the party LIGHT slot."""
        return self.game.party.get_equipped_name("light") == "Torch"

    def _tick_torch(self):
        """Decrement torch charges and handle burnout after a step."""
        if not self.torch_active:
            return
        self.torch_steps -= 1
        # Sync charges back to the equipped item
        party = self.game.party
        entry = party.equipped.get("light")
        if entry and entry.get("charges") is not None:
            entry["charges"] = max(0, self.torch_steps)
        if self.torch_steps <= 0:
            self.torch_active = False
            self._consume_torch()  # Remove the burned-out torch
            # Try to reactivate if somehow another torch is equipped
            if self._activate_torch():
                self.show_message("Lit a new torch!", 2000)
            else:
                self.show_message("Your torch has burned out!", 2500)

    def _tick_galadriels_light(self):
        """Decrement Galadriel's Light step counter and auto-remove when expired."""
        party = self.game.party
        if not party.has_effect("Galadriel's Light"):
            return
        if party.galadriels_light_steps <= 0:
            return
        party.galadriels_light_steps -= 1
        if party.galadriels_light_steps <= 0:
            # Remove the effect from whichever slot it occupies
            for slot_key in party.EFFECT_SLOTS:
                if party.get_effect(slot_key) == "Galadriel's Light":
                    party.set_effect(slot_key, None)
                    break
            self.show_message("Galadriel's Light fades away...", 3000)

    def _on_spell_magic_light(self, steps):
        """Override: activate the torch system using the Light spell's step count."""
        self.torch_active = True
        self.torch_steps = steps

    def _compute_visible_tiles(self):
        """Compute the set of (col, row) world tiles visible to the party.

        Without a light source: only the 8 adjacent tiles + party tile (radius 1).
        With a torch: recursive shadowcasting reveals all tiles in line of sight,
        with walls blocking light naturally.  Walls themselves are visible if a
        ray reaches them, but light does not pass through.

        Wall torches on the dungeon walls illuminate their surroundings
        once the party has discovered them (the torch tile is in the
        party's current or previously-explored visible set).
        """
        party = self.game.party
        pc, pr = party.col, party.row
        visible = {(pc, pr)}

        tile_map = self.dungeon_data.tile_map
        max_radius = max(tile_map.width, tile_map.height)

        octants = [
            ( 1,  0,  0,  1),   # ENE
            ( 0,  1,  1,  0),   # NNE
            ( 0, -1,  1,  0),   # NNW
            (-1,  0,  0,  1),   # WNW
            (-1,  0,  0, -1),   # WSW
            ( 0, -1, -1,  0),   # SSW
            ( 0,  1, -1,  0),   # SSE
            ( 1,  0,  0, -1),   # ESE
        ]

        # Always compute full line-of-sight so we know which torches
        # the party could see (even without their own light source,
        # a torch down a corridor is visible from its glow).
        full_los = {(pc, pr)}
        for xx, xy, yx, yy in octants:
            self._cast_light(full_los, tile_map, pc, pr,
                             1, 1.0, 0.0, max_radius,
                             xx, xy, yx, yy)

        has_light = (self.torch_active or self._has_torch_equipped()
                     or party.has_effect("Infravision")
                     or (party.has_effect("Galadriel's Light")
                         and party.galadriels_light_steps > 0))
        if not has_light:
            # Minimal visibility — just the 8 neighbours
            for dc in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    visible.add((pc + dc, pr + dr))
        else:
            # Party carries light — they can see everything in LOS
            visible.update(full_los)

        # ── Wall torches illuminate their surroundings ──
        # A torch activates when it falls within the party's full
        # line-of-sight (unobstructed path exists), regardless of
        # whether the party carries their own light.  You can see
        # a torch's glow from far down a corridor.  When the party
        # moves away and LOS is broken, the torch-lit area fades
        # back to the normal explored (dimmed) state via fog of war.
        torch_map = self._get_torch_lit_map()
        for torch_pos, lit_tiles in torch_map.items():
            if torch_pos in full_los:
                visible.update(lit_tiles)

        return visible

    def _get_torch_lit_map(self):
        """Return cached per-torch illumination map.

        Returns a dict: ``{(torch_col, torch_row): set_of_lit_tiles}``.
        Computed once per dungeon level and cached.  Uses the same
        shadowcasting algorithm with a limited radius so walls properly
        block the torch light.
        """
        if hasattr(self, '_torch_lit_cache') and self._torch_lit_cache is not None:
            return self._torch_lit_cache

        tile_map = self.dungeon_data.tile_map
        torch_radius = 4
        result = {}

        octants = [
            ( 1,  0,  0,  1), ( 0,  1,  1,  0),
            ( 0, -1,  1,  0), (-1,  0,  0,  1),
            (-1,  0,  0, -1), ( 0, -1, -1,  0),
            ( 0,  1, -1,  0), ( 1,  0,  0, -1),
        ]

        from src.settings import TILE_DEFS as _TD_TORCH
        for wr in range(tile_map.height):
            for wc in range(tile_map.width):
                _tid = tile_map.get_tile(wc, wr)
                if _TD_TORCH.get(_tid, {}).get(
                        "flags", {}).get("light_source"):
                    lit = {(wc, wr)}
                    for xx, xy, yx, yy in octants:
                        self._cast_light(lit, tile_map, wc, wr,
                                         1, 1.0, 0.0, torch_radius,
                                         xx, xy, yx, yy)
                    result[(wc, wr)] = lit

        self._torch_lit_cache = result
        return result

    def _invalidate_torch_cache(self):
        """Clear the wall-torch visibility cache (call on level change)."""
        self._torch_lit_cache = None

    def _cast_light(self, visible, tile_map, cx, cy,
                    row, start_slope, end_slope, max_radius,
                    xx, xy, yx, yy):
        """Recursive shadowcasting for one octant.

        Scans row by row outward from the origin. When a wall is found the
        visible arc is narrowed; when transitioning from wall to open space
        a recursive call handles the remaining sub-arc.
        """
        if start_slope < end_slope:
            return

        for j in range(row, max_radius + 1):
            blocked = False
            new_start = start_slope
            dx = -j - 1
            dy = -j

            while dx <= 0:
                dx += 1
                # Map octant-local (dx, dy) to world coordinates
                map_x = cx + dx * xx + dy * xy
                map_y = cy + dx * yx + dy * yy

                # Slopes for this cell
                l_slope = (dx - 0.5) / (dy + 0.5)
                r_slope = (dx + 0.5) / (dy - 0.5)

                if start_slope < r_slope:
                    continue
                if end_slope > l_slope:
                    break

                # This tile is visible (including walls — you can see them)
                visible.add((map_x, map_y))

                # Check if this tile blocks light — walls and closed
                # doors are opaque (you can see the door itself but
                # not through it).
                tid = tile_map.get_tile(map_x, map_y)
                is_wall = (not tile_map.is_walkable(map_x, map_y)
                           or tid == TILE_DDOOR)

                if blocked:
                    if is_wall:
                        new_start = r_slope
                    else:
                        blocked = False
                        start_slope = new_start
                else:
                    if is_wall and j < max_radius:
                        blocked = True
                        self._cast_light(visible, tile_map, cx, cy,
                                         j + 1, start_slope, l_slope,
                                         max_radius, xx, xy, yx, yy)
                        new_start = r_slope

            if blocked:
                break

    def _has_line_of_sight(self, x0, y0, x1, y1):
        """Check if there is a clear line of sight between two tiles.

        Uses Bresenham's line algorithm to walk from (x0,y0) to (x1,y1).
        Returns True if no wall tiles block the path.
        """
        tile_map = self.dungeon_data.tile_map
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        cx, cy = x0, y0

        while True:
            # Reached the target — line of sight is clear
            if cx == x1 and cy == y1:
                return True
            # Check if the current tile is walkable (walls block LOS)
            if (cx, cy) != (x0, y0) and not tile_map.is_walkable(cx, cy):
                return False
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy

    def _move_monsters(self):
        """Move each alive monster: pursue if it can see the party, else wander."""
        if not self.dungeon_data:
            return
        party = self.game.party
        alive = [m for m in self.dungeon_data.monsters if m.is_alive()]
        # Build set of occupied positions (other monsters + party)
        occupied = {(m.col, m.row) for m in alive}
        occupied.add((party.col, party.row))
        for monster in alive:
            # Remove self from occupied so it can move
            occupied.discard((monster.col, monster.row))

            anchor = getattr(monster, "_guardian_anchor", None)
            if anchor:
                # ── Guardian: stay near artifact, intercept when party close ──
                ax, ay = anchor
                leash = getattr(monster, "_guardian_leash", GUARDIAN_LEASH)
                dist_party_to_anchor = (abs(party.col - ax)
                                        + abs(party.row - ay))
                if (dist_party_to_anchor <= GUARDIAN_INTERCEPT_RANGE_INTERIOR
                        and self._has_line_of_sight(
                            monster.col, monster.row,
                            party.col, party.row)):
                    # Intercept but stay within leash
                    self._guardian_move_toward_dungeon(
                        monster, party.col, party.row,
                        ax, ay, leash, occupied)
                else:
                    # Drift back toward anchor if too far
                    dist = (abs(monster.col - ax)
                            + abs(monster.row - ay))
                    if dist > leash:
                        monster.try_move_toward(
                            ax, ay,
                            self.dungeon_data.tile_map,
                            occupied)
                    # Otherwise stay put
            elif (abs(monster.col - party.col)
                      + abs(monster.row - party.row) <= 6
                  and self._has_line_of_sight(monster.col, monster.row,
                                              party.col, party.row)):
                # Monster can see the player within 6 tiles — pursue
                monster.try_move_toward(
                    party.col, party.row,
                    self.dungeon_data.tile_map,
                    occupied,
                )
            else:
                # Monster can't see the player — wander randomly
                monster.try_move_random(
                    self.dungeon_data.tile_map,
                    occupied,
                    party_col=party.col,
                    party_row=party.row,
                )
            # Add new position back
            occupied.add((monster.col, monster.row))

    def _guardian_move_toward_dungeon(self, mon, target_col, target_row,
                                      anchor_col, anchor_row, leash,
                                      occupied):
        """Move a dungeon guardian toward *target* within leash of anchor."""
        tmap = self.dungeon_data.tile_map
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        best = None
        best_dist = abs(mon.col - target_col) + abs(mon.row - target_row)
        for dc, dr in dirs:
            nc, nr = mon.col + dc, mon.row + dr
            if (abs(nc - anchor_col) + abs(nr - anchor_row)) > leash:
                continue
            if (nc, nr) in occupied:
                continue
            if not (0 <= nc < tmap.width and 0 <= nr < tmap.height):
                continue
            if not tmap.is_walkable(nc, nr):
                continue
            d = abs(nc - target_col) + abs(nr - target_row)
            if d < best_dist:
                best_dist = d
                best = (nc, nr)
        if best:
            mon.col, mon.row = best

    def _check_monster_contact(self):
        """If a monster is adjacent to (or onto) the party, show encounter screen."""
        if not self.dungeon_data:
            return
        if self.encounter_action_active:
            return
        party = self.game.party
        for monster in self.dungeon_data.monsters:
            if not monster.is_alive():
                continue
            dc = abs(monster.col - party.col)
            dr = abs(monster.row - party.row)
            if dc + dr <= 1:  # Same tile or cardinal-adjacent
                self._show_encounter_action(monster)
                return

    # ── Encounter action screen (Fight / Flee) ─────────────────

    def _show_encounter_action(self, monster):
        """Show the encounter prompt for a dungeon monster."""
        self.encounter_action_monster = monster
        self.encounter_action_cursor = 0
        self.encounter_action_result = None
        self.encounter_result_timer = 0
        self.encounter_action_active = True

    def _handle_encounter_action_input(self, event):
        """Handle input for the monster encounter action screen."""
        # While showing a flee result message, consume any key to dismiss
        if self.encounter_action_result is not None:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                if self.encounter_action_result in ("fled", "fled_far"):
                    # Successful flee — push monster away
                    flee_dist = self._encounter_flee_distance
                    mon = self.encounter_action_monster
                    if mon and self.dungeon_data:
                        party = self.game.party
                        dx = mon.col - party.col
                        dy = mon.row - party.row
                        step_x = (1 if dx > 0 else -1 if dx < 0
                                  else (1 if dy == 0 else 0))
                        step_y = (1 if dy > 0 else -1 if dy < 0
                                  else (0 if dx != 0 else 1))
                        tmap = self.dungeon_data.tile_map
                        for _ in range(flee_dist):
                            nc = mon.col + step_x
                            nr = mon.row + step_y
                            if (0 <= nc < tmap.width
                                    and 0 <= nr < tmap.height
                                    and tmap.is_walkable(nc, nr)):
                                mon.col, mon.row = nc, nr
                            else:
                                break
                    self.encounter_action_active = False
                else:
                    # Failed flee — enter combat
                    self._encounter_engage()
            return

        n_options = 2  # Engage, Flee
        if event.key in (pygame.K_UP, pygame.K_w):
            self.encounter_action_cursor = (
                self.encounter_action_cursor - 1) % n_options
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.encounter_action_cursor = (
                self.encounter_action_cursor + 1) % n_options
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.encounter_action_cursor == 0:
                self._encounter_engage()
            elif self.encounter_action_cursor == 1:
                self._encounter_flee()
        elif event.key == pygame.K_ESCAPE:
            self._encounter_flee()

    def _encounter_engage(self):
        """Confirm engagement — start combat with the contacted monster."""
        mon = self.encounter_action_monster
        self.encounter_action_active = False
        if mon:
            self._start_combat(mon)

    def _encounter_flee(self):
        """Attempt to flee using a DEX saving throw.

        Party average DEX modifier vs. monster effective DEX.
        Roll d20 + party_avg_dex_mod >= 10 + monster_dex_mod to escape.
        """
        import random as _rng
        party = self.game.party
        mon = self.encounter_action_monster

        alive = [m for m in party.members if m.is_alive()]
        if alive:
            avg_dex_mod = sum(m.dex_mod for m in alive) / len(alive)
        else:
            avg_dex_mod = 0

        monster_dex_mod = max(0, (getattr(mon, 'ac', 10) - 10) // 2)
        roll = _rng.randint(1, 20)
        dc = 10 + monster_dex_mod
        total = roll + int(avg_dex_mod)

        if total >= dc:
            dist_roll = _rng.randint(1, 20) + int(avg_dex_mod)
            if dist_roll >= dc:
                flee_dist = 4
                self.encounter_action_result = "fled_far"
            else:
                flee_dist = 2
                self.encounter_action_result = "fled"
            self._encounter_flee_distance = flee_dist
            self.encounter_result_timer = 1500
            self.game.sfx.play("chirp")
        else:
            self.encounter_action_result = "failed"
            self._encounter_flee_distance = 0
            self.encounter_result_timer = 1500
            self.game.sfx.play("hit")

    def _get_monster_at(self, col, row):
        """Return the monster at (col, row) if any, else None."""
        if not self.dungeon_data:
            return None
        for monster in self.dungeon_data.monsters:
            if monster.col == col and monster.row == row and monster.is_alive():
                return monster
        return None

    def _start_combat(self, monster):
        """Transition to combat state using an encounter template."""
        # Use the first alive party member as the fighter
        fighter = None
        for member in self.game.party.members:
            if member.is_alive():
                fighter = member
                break
        if not fighter:
            return  # No alive party members (shouldn't happen)

        # Use the pre-assigned encounter template stored on the map monster
        # (set by dungeon_generator). Fall back to a random encounter if
        # the monster doesn't have one (e.g. legacy save data).
        from src.monster import create_encounter, create_monster
        tmpl = getattr(monster, "encounter_template", None)
        if tmpl is None:
            enc = create_encounter("dungeon")
            monsters = enc["monsters"]
            enc_name = enc["name"]
            battle_screen = None
        else:
            monsters = [create_monster(n) for n in tmpl["monster_names"]]
            enc_name = tmpl["name"]
            battle_screen = tmpl.get("battle_screen")
        for m in monsters:
            m.col = monster.col
            m.row = monster.row

        combat_state = self.game.states.get("combat")
        if combat_state:
            self.game.sfx.play("encounter")
            dname = getattr(self.dungeon_data, "name", "")
            combat_state.start_combat(fighter, monsters,
                                      source_state="dungeon",
                                      encounter_name=enc_name,
                                      map_monster_refs=[monster],
                                      battle_screen=battle_screen,
                                      combat_location=f"dungeon:{dname}")
            self.game.change_state("combat")

    # ── Locked door interaction ─────────────────────────────────────
    #
    # The dialog + dice-rolling + MP consumption + SFX + animation now
    # live on ``LockInteractionMixin`` (src/states/lock_mixin.py) so
    # town and overworld interiors get the exact same UX from the same
    # code path. DungeonState only needs to pass its own tile_map to
    # the mixin via ``_try_open_locked`` in ``_try_move``.

    def _attempt_trap_detection(self):
        """If Detect Traps effect is active, the thief rolls to spot traps in view.

        For each visible TILE_TRAP not already detected or triggered, the thief
        makes a saving throw: d20 + DEX modifier >= 10.  Each trap is rolled
        once per step while it remains in line of sight.
        """
        party = self.game.party
        if not party.has_effect("Detect Traps"):
            return

        # Find an alive Thief in the party
        thief = None
        for m in party.members:
            if m.is_alive() and m.char_class == "Thief":
                thief = m
                break
        if thief is None:
            return

        visible = self._compute_visible_tiles()
        tile_map = self.dungeon_data.tile_map
        detected = self.dungeon_data.detected_traps
        triggered = self.dungeon_data.triggered_traps

        for (wc, wr) in visible:
            if tile_map.get_tile(wc, wr) != TILE_TRAP:
                continue
            pos = (wc, wr)
            if pos in detected or pos in triggered:
                continue
            # Saving throw: d20 + DEX modifier vs DC 10
            roll = random.randint(1, 20) + thief.get_modifier(thief.dexterity)
            if roll >= 10:
                detected.add(pos)
                self.show_message(
                    f"{thief.name} spotted a trap!", 1500)

    def _check_tile_events(self):
        """Check for special tiles the party stepped on."""
        col = self.game.party.col
        row = self.game.party.row
        tile_id = self.dungeon_data.tile_map.get_tile(col, row)

        # Pick up placed ground items (items editor → tile_properties)
        from src.states.overworld import _try_pickup_ground_item
        _try_pickup_ground_item(
            self.game,
            self.dungeon_data.tile_map,
            col, row,
            log_sink=self.game.game_log.append,
            msg_sink=self.show_message,
        )

        if tile_id == TILE_STAIRS:
            self.show_message("Stairs up! Press ESC to leave.", 2000)

        if tile_id == TILE_CHEST:
            pos = (col, row)
            if pos not in self.dungeon_data.opened_chests:
                self.dungeon_data.opened_chests.add(pos)
                self._open_chest()
                # Replace chest with floor now that it's opened
                self.dungeon_data.tile_map.set_tile(col, row, TILE_DFLOOR)

        elif tile_id == TILE_TRAP:
            pos = (col, row)
            if pos not in self.dungeon_data.triggered_traps:
                self.dungeon_data.triggered_traps.add(pos)
                self.game.sfx.play("trap")
                # Damage a random party member
                alive = [m for m in self.game.party.members if m.is_alive()]
                if alive:
                    victim = random.choice(alive)
                    damage = random.randint(3, 8)
                    victim.hp = max(0, victim.hp - damage)
                    self.show_message(
                        f"Trap! {victim.name} takes {damage} damage!", 2000
                    )
                # Disarm the trap (replace with floor)
                self.dungeon_data.tile_map.set_tile(col, row, TILE_DFLOOR)

        elif tile_id == TILE_STAIRS_DOWN:
            if self.quest_levels and self.current_level < len(self.quest_levels) - 1:
                # Descend to next level
                self.current_level += 1
                self.dungeon_data = self.quest_levels[self.current_level]
                self._invalidate_torch_cache()
                self.game.party.col = self.dungeon_data.entry_col
                self.game.party.row = self.dungeon_data.entry_row
                self.game.camera.map_width = self.dungeon_data.tile_map.width
                self.game.camera.map_height = self.dungeon_data.tile_map.height
                self.game.camera.update(self.game.party.col, self.game.party.row)
                # Recompute visibility for the new level
                self._visible_tiles = set()
                if self.torch_active:
                    self._visible_tiles = self._compute_visible_tiles()
                depth = self.current_level + 1
                total = len(self.quest_levels)
                self.show_message(
                    f"You descend deeper... (Floor {depth}/{total})", 2000)
                # Inject quest monsters and collect items on the lowest floor
                self._inject_quest_dungeon_monsters()
                self._inject_quest_dungeon_collect_items()
                active_q = self._get_active_quest()
                if active_q:
                    active_q["current_level"] = self.current_level
            else:
                self.show_message("Stairs leading down...", 1500)

        elif tile_id == TILE_ARTIFACT:
            # Pick up whatever quest artifact belongs to this dungeon
            active_q = self._get_active_quest()
            artifact = active_q.get("artifact_name", "Shadow Crystal") if active_q else "Shadow Crystal"
            self.game.party.inv_add(artifact)
            self.dungeon_data.tile_map.set_tile(col, row, TILE_DFLOOR)
            if active_q:
                active_q["status"] = "artifact_found"
            # Only spawn a portal if exit_portal is enabled
            spawn_portal = active_q.get("exit_portal", True) if active_q else True
            if spawn_portal:
                self._place_portal(col, row)
            # Play pickup animation
            self.artifact_pickup_anim = {
                "col": col,
                "row": row,
                "timer": 2000,
                "duration": 2000,
                "name": artifact,
            }
            self.game.sfx.play("critical")
            if spawn_portal:
                self.show_message(f"Found the {artifact}! A portal appears!", 3000)
            else:
                self.show_message(f"Found the {artifact}!", 3000)

        elif tile_id == TILE_PORTAL:
            # Portal whisks the party back to the overworld
            # Quest stays "artifact_found" — the party must return the
            # artifact to the quest-giver in town for the completion
            # ceremony and reward.  The overworld tile is cleared so
            # the dungeon entrance vanishes.
            # Swap the dungeon tile on the overworld to show it's cleared
            self.game.tile_map.set_tile(
                self.overworld_col, self.overworld_row,
                TILE_DUNGEON_CLEARED)

            self._entered = False
            self.pending_combat_message = None
            self.quest_levels = None
            self.current_level = 0
            ow_col, ow_row = self.overworld_col, self.overworld_row

            def _do_portal_exit():
                self.game.party.col = ow_col
                self.game.party.row = ow_row
                self.game.camera.map_width = self.game.tile_map.width
                self.game.camera.map_height = self.game.tile_map.height
                self.game.camera.update(self.game.party.col,
                                        self.game.party.row)
                self.show_message(
                    "The portal returns you to the surface!", 3000)
                self.game.change_state("overworld")

            dungeon_name = getattr(self.dungeon_data, "name",
                                   None) or "Dungeon"
            self.game.start_loading_screen(
                f"Leaving {dungeon_name}", _do_portal_exit)

    # ── Chest loot ─────────────────────────────────────────────

    def _open_chest(self):
        """Roll random loot from a chest: gold, an item, or both."""
        from src import data_registry as DR
        self.game.sfx.play("treasure")
        # Always give some gold
        gold = random.randint(5, 30)
        self.game.party.gold += gold

        # Roll on the loot table
        loot_table = DR.chest_loot()
        total_weight = sum(w for _, w in loot_table)
        roll = random.randint(1, total_weight)
        cumulative = 0
        chosen_item = None
        for item, weight in loot_table:
            cumulative += weight
            if roll <= cumulative:
                chosen_item = item
                break

        if chosen_item:
            self.game.party.inv_add(chosen_item)
            self.show_message(
                f"The party opened a treasure chest and found {gold} gold and {chosen_item}.", 2500)
        else:
            self.show_message(
                f"The party opened a treasure chest and found {gold} gold.", 2000)

    def _place_portal(self, col, row):
        """Place a TILE_PORTAL on an adjacent walkable floor tile."""
        tmap = self.dungeon_data.tile_map
        # Try cardinal directions first, then diagonals
        for dc, dr in [(0, -1), (1, 0), (0, 1), (-1, 0),
                       (1, -1), (1, 1), (-1, 1), (-1, -1)]:
            nc, nr = col + dc, row + dr
            if 0 <= nc < tmap.width and 0 <= nr < tmap.height:
                if tmap.get_tile(nc, nr) in (TILE_DFLOOR, TILE_PUDDLE, TILE_MOSS):
                    tmap.set_tile(nc, nr, TILE_PORTAL)
                    return
        # Fallback: place it right where the artifact was (already floor)
        tmap.set_tile(col, row, TILE_PORTAL)

    def _ascend_level(self):
        """Ascend one level up in a multi-level quest dungeon."""
        if self.current_level <= 0:
            return  # Already at top
        self.current_level -= 1
        self.dungeon_data = self.quest_levels[self.current_level]
        self._invalidate_torch_cache()
        # Find the stairs-down tile on the level above to place the party
        tmap = self.dungeon_data.tile_map
        placed = False
        for r in range(tmap.height):
            for c in range(tmap.width):
                if tmap.get_tile(c, r) == TILE_STAIRS_DOWN:
                    self.game.party.col = c
                    self.game.party.row = r
                    placed = True
                    break
            if placed:
                break
        if not placed:
            # Fallback to entry point
            self.game.party.col = self.dungeon_data.entry_col
            self.game.party.row = self.dungeon_data.entry_row
        self.game.camera.map_width = tmap.width
        self.game.camera.map_height = tmap.height
        self.game.camera.update(self.game.party.col, self.game.party.row)
        self._visible_tiles = set()
        if self.torch_active:
            self._visible_tiles = self._compute_visible_tiles()
        active_q = self._get_active_quest()
        if active_q:
            active_q["current_level"] = self.current_level
        depth = self.current_level + 1
        self.show_message(f"You ascend to floor {depth}.", 2000)

    def _exit_dungeon(self):
        """Leave the dungeon and return to the overworld."""
        # Reset entered flag so next dungeon visit starts fresh
        self._entered = False
        self.pending_combat_message = None

        ow_col, ow_row = self.overworld_col, self.overworld_row
        dungeon_name = getattr(self.dungeon_data, "name", None) or "Dungeon"

        def _do_exit():
            # Restore party position on the overworld
            self.game.party.col = ow_col
            self.game.party.row = ow_row
            # Restore camera for overworld map
            self.game.camera.map_width = self.game.tile_map.width
            self.game.camera.map_height = self.game.tile_map.height
            self.game.camera.update(self.game.party.col, self.game.party.row)
            self.game.change_state("overworld")

        self.game.start_loading_screen(f"Leaving {dungeon_name}", _do_exit)


    def update(self, dt):
        dt_ms = dt * 1000
        if self.message_timer > 0:
            self.message_timer -= dt_ms
            if self.message_timer <= 0:
                self.message = ""
                self.message_timer = 0

        if self.move_cooldown > 0:
            self.move_cooldown -= dt_ms
            if self.move_cooldown < 0:
                self.move_cooldown = 0

        # Tick use-item animation
        if self.use_item_anim and self.use_item_anim["timer"] > 0:
            self.use_item_anim["timer"] -= dt_ms
            if self.use_item_anim["timer"] <= 0:
                self.use_item_anim = None

        # Tick level-up animations
        self._update_level_up_queue(dt_ms)

        # Tick door unlock animation — the mixin drives the timer and
        # the per-tile follow-up (legacy TILE_LOCKED_DOOR converts to
        # TILE_DDOOR; designer-placed locked tiles just have their
        # 'locked' tile_property removed).
        self._tick_lock_animation(dt_ms)

        # Tick artifact pickup animation
        if self.artifact_pickup_anim:
            self.artifact_pickup_anim["timer"] -= dt_ms
            if self.artifact_pickup_anim["timer"] <= 0:
                self.artifact_pickup_anim = None

        # Tick encounter result timer
        if self.encounter_result_timer > 0:
            self.encounter_result_timer -= dt_ms

    def draw(self, renderer):
        """Draw the dungeon in Ultima III style."""
        if self.showing_party_inv:
            action_opts = self._get_party_inv_action_options() if self.party_inv_action_menu else None
            renderer.draw_party_inventory_u3(
                self.game.party, self.party_inv_cursor,
                self.party_inv_choosing, self.party_inv_member,
                self.party_inv_action_menu, self.party_inv_action_cursor,
                action_options=action_opts,
                choosing_effect=self.choosing_effect,
                effect_list=self.effect_list,
                effect_cursor=self.effect_cursor,
                showing_spell_list=self.showing_spell_list,
                spell_list_items=self.spell_list_items,
                spell_list_cursor=self.spell_list_cursor,
                choosing_heal_target=self.choosing_heal_target,
                heal_target_cursor=self.heal_target_cursor,
                showing_brew_list=self.showing_brew_list,
                brew_list_items=self.brew_list_items,
                brew_list_cursor=self.brew_list_cursor,
                brew_result_msg=self.brew_result_msg,
                tinker_available=self._can_tinker(),
                applying_poison_step=self.applying_poison_step,
                applying_poison_cursor=self.applying_poison_cursor,
                applying_poison_item=self.applying_poison_item,
                applying_poison_member=getattr(self, '_applying_poison_member', None))
            if self.use_item_anim:
                renderer.draw_use_item_animation(self.game.party, self.use_item_anim)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item, getattr(self, 'examining_durability', None))
            return
        if self.showing_char_detail is not None:
            idx = self.showing_char_detail
            member = self.game.party.members[idx]
            action_opts = self._get_action_options(member) if self.char_action_menu else None
            renderer.draw_character_sheet_u3(
                member, idx, self.char_sheet_cursor,
                self.char_action_menu, self.char_action_cursor,
                action_options=action_opts)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item, getattr(self, 'examining_durability', None))
            return
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        visible = self._compute_visible_tiles()
        # Persist every tile the party has ever seen for fog of war
        self.dungeon_data.explored_tiles.update(visible)

        level_label = None
        if self.quest_levels:
            level_label = f"Level {self.current_level + 1}"
        # Determine if infravision or Galadriel's Light provides the light
        has_torch_light = self.torch_active or self._has_torch_equipped()
        party = self.game.party
        infravision_active = (not has_torch_light
                              and party.has_effect("Infravision"))
        galadriels_active = (not has_torch_light and not infravision_active
                             and party.has_effect("Galadriel's Light")
                             and party.galadriels_light_steps > 0)

        renderer.draw_dungeon_u3(
            party,
            self.dungeon_data,
            message=self.message,
            visible_tiles=visible,
            explored_tiles=self.dungeon_data.explored_tiles,
            torch_steps=self.torch_steps if has_torch_light else -1,
            level_label=level_label,
            detected_traps=self.dungeon_data.detected_traps,
            door_unlock_anim=self.door_unlock_anim,
            door_interact=self._get_door_interact_state(),
            infravision=infravision_active,
            artifact_pickup_anim=self.artifact_pickup_anim,
            galadriels_light=galadriels_active,
            dungeon_level=self.current_level,
        )
        if self.level_up_queue:
            renderer.draw_level_up_animation(self.level_up_queue[0])
        if self.encounter_action_active:
            renderer.draw_encounter_action_screen(
                self.encounter_action_monster,
                self.encounter_action_cursor,
                self.encounter_action_result)
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
        if self.showing_help:
            renderer.draw_dungeon_help_overlay()
