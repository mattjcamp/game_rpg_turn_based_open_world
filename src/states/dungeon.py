"""
Dungeon state - exploring a procedurally generated dungeon.

The party navigates dark corridors and rooms, finds treasure chests,
avoids traps, and can exit via the stairs back to the overworld.
"""

import random

import pygame

from src.states.base_state import BaseState
from src.states.inventory_mixin import InventoryMixin
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_STAIRS, TILE_CHEST, TILE_TRAP, TILE_DFLOOR,
    TILE_STAIRS_DOWN, TILE_ARTIFACT, TILE_PORTAL, TILE_LOCKED_DOOR, TILE_DDOOR,
)


class DungeonState(InventoryMixin, BaseState):
    """Handles exploration inside a dungeon."""

    def __init__(self, game):
        super().__init__(game)
        self.dungeon_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        self._init_inventory_state()

        # Torch lighting system
        self.torch_active = False
        self.torch_steps = 0

        # Save overworld position for when we leave
        self.overworld_col = 0
        self.overworld_row = 0

        # Quest dungeon multi-level support
        self.quest_levels = None   # list of DungeonData if this is a quest dungeon
        self.current_level = 0     # 0 or 1

        # Message queued by combat state on return
        self.pending_combat_message = None
        # Track if we've already entered (so re-entry from combat doesn't reset position)
        self._entered = False

        # ── Locked door interaction prompt ──
        self.door_interact_active = False
        self.door_interact_col = 0
        self.door_interact_row = 0
        self.door_interact_cursor = 0
        self.door_interact_options = []  # list of (label, action_key)

        # ── Door unlock animation ──
        self.door_unlock_anim = None  # {"col", "row", "timer", "duration"}

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

    def _get_active_quest(self):
        """Return the quest dict that owns this dungeon, or None."""
        oc, orow = self.overworld_col, self.overworld_row
        for q in (self.game.quest, getattr(self.game, "house_quest", None)):
            if (q and q.get("status") in ("active", "artifact_found")
                    and q.get("dungeon_col") == oc
                    and q.get("dungeon_row") == orow):
                return q
        return None

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

    def enter(self):
        """Called when this state becomes active."""
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
            # Try to light the equipped torch automatically
            if self._activate_torch():
                self.show_message(
                    f"You descend into {self.dungeon_data.name}... Torch lit!", 2500
                )
            else:
                self.show_message(
                    f"You descend into {self.dungeon_data.name}... No torch equipped!", 2500
                )
            # Move party to dungeon entry point (the stairs)
            self.game.party.col = self.dungeon_data.entry_col
            self.game.party.row = self.dungeon_data.entry_row
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
                # ── Log overlay input ──
                if self.showing_log:
                    if event.key == pygame.K_l or event.key == pygame.K_ESCAPE:
                        self.showing_log = False
                    elif event.key == pygame.K_UP:
                        self.log_scroll += 3
                    elif event.key == pygame.K_DOWN:
                        self.log_scroll = max(0, self.log_scroll - 3)
                    return

                # ── Door interaction prompt input ──
                if self.door_interact_active:
                    self._handle_door_interact_input(event)
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
                    # Only allow escape if standing on stairs
                    tile_id = self.dungeon_data.tile_map.get_tile(
                        self.game.party.col, self.game.party.row
                    )
                    if tile_id == TILE_STAIRS:
                        if self.quest_levels and self.current_level == 1:
                            # Ascend back to level 0
                            self._ascend_level()
                        else:
                            self._exit_dungeon()
                    else:
                        self.show_message(
                            "Find the stairs to escape!", 1500
                        )
                    return
                if event.key == pygame.K_l:
                    self.showing_log = True
                    self.log_scroll = 0
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

        # If showing party screen, character detail, party inventory, or door prompt, block movement
        if (self.showing_party or self.showing_char_detail is not None
                or self.showing_party_inv or self.door_interact_active
                or self.door_unlock_anim):
            return

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
        elif keys_pressed[pygame.K_DOWN] or keys_pressed[pygame.K_s]:
            drow = 1

        if dcol != 0 or drow != 0:
            self._try_move(dcol, drow)

    def _try_move(self, dcol, drow):
        """Move the party within the dungeon, then let monsters take a step."""
        party = self.game.party
        target_col = party.col + dcol
        target_row = party.row + drow

        # Check for monster at target position (bump-to-fight)
        monster = self._get_monster_at(target_col, target_row)
        if monster:
            self._start_combat(monster)
            self.move_cooldown = MOVE_REPEAT_DELAY
            return

        # Check for locked door — show interaction prompt
        tile_id = self.dungeon_data.tile_map.get_tile(target_col, target_row)
        if tile_id == TILE_LOCKED_DOOR:
            self._show_door_interact(target_col, target_row)
            self.move_cooldown = MOVE_REPEAT_DELAY
            return

        if self.dungeon_data.tile_map.is_walkable(target_col, target_row):
            party.col = target_col
            party.row = target_row
            self.move_cooldown = MOVE_REPEAT_DELAY
            self._check_tile_events()
            self._attempt_trap_detection()
            # After party moves, let every alive monster take a step
            self._move_monsters()
            # A monster may have walked adjacent — check for contact
            self._check_monster_contact()
            # Burn torch after each successful step
            self._tick_torch()
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
        """
        party = self.game.party
        pc, pr = party.col, party.row
        visible = {(pc, pr)}

        has_light = (self.torch_active or self._has_torch_equipped()
                     or party.has_effect("Infravision"))
        if not has_light:
            # Minimal visibility — just the 8 neighbours
            for dc in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    visible.add((pc + dc, pr + dr))
            return visible

        # Torch lit — use recursive shadowcasting for full line-of-sight
        tile_map = self.dungeon_data.tile_map
        max_radius = max(tile_map.width, tile_map.height)

        # Eight octants cover all 360 degrees
        # Each octant is defined by multipliers (xx, xy, yx, yy) that map
        # (row along ray, column offset) to (dx, dy) world offsets.
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
        for xx, xy, yx, yy in octants:
            self._cast_light(visible, tile_map, pc, pr,
                             1, 1.0, 0.0, max_radius,
                             xx, xy, yx, yy)
        return visible

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

                # Check if this tile blocks light
                is_wall = not tile_map.is_walkable(map_x, map_y)

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
        # Build set of occupied positions (other monsters) to prevent stacking
        occupied = {(m.col, m.row) for m in alive}
        for monster in alive:
            # Remove self from occupied so it can move
            occupied.discard((monster.col, monster.row))
            if self._has_line_of_sight(monster.col, monster.row,
                                       party.col, party.row):
                # Monster can see the player — pursue
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

    def _check_monster_contact(self):
        """If a monster moved adjacent to the party, start combat."""
        if not self.dungeon_data:
            return
        party = self.game.party
        for monster in self.dungeon_data.monsters:
            if not monster.is_alive():
                continue
            dc = abs(monster.col - party.col)
            dr = abs(monster.row - party.row)
            if dc + dr == 1:  # Cardinal-adjacent
                self._start_combat(monster)
                return

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
        else:
            monsters = [create_monster(n) for n in tmpl["monster_names"]]
            enc_name = tmpl["name"]
        for m in monsters:
            m.col = monster.col
            m.row = monster.row

        combat_state = self.game.states.get("combat")
        if combat_state:
            self.game.sfx.play("encounter")
            combat_state.start_combat(fighter, monsters,
                                      source_state="dungeon",
                                      encounter_name=enc_name,
                                      map_monster_refs=[monster])
            self.game.change_state("combat")

    # ── Locked door interaction ─────────────────────────────────────

    def _show_door_interact(self, col, row):
        """Show an interaction prompt when the party encounters a locked door."""
        party = self.game.party

        self.door_interact_col = col
        self.door_interact_row = row
        self.door_interact_cursor = 0

        # Build available options based on party state
        options = []

        # Check if there's an alive Thief with lockpicks
        thief = None
        for m in party.members:
            if m.is_alive() and m.char_class == "Thief":
                thief = m
                break

        picks = party.inv_get_charges("Lockpick")
        if thief and picks > 0:
            options.append((f"Pick Lock ({thief.name}, {picks} picks)", "pick"))
        elif thief and picks <= 0:
            options.append(("Pick Lock (no lockpicks!)", "no_picks"))
        elif thief is None:
            options.append(("Pick Lock (no thief!)", "no_thief"))

        # TODO: could add "Use Key" option if keys are implemented

        options.append(("Leave", "leave"))

        self.door_interact_options = options
        self.door_interact_active = True

    def _handle_door_interact_input(self, event):
        """Handle UP/DOWN/ENTER navigation of the door interaction prompt."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.door_interact_cursor = (
                (self.door_interact_cursor - 1)
                % len(self.door_interact_options)
            )
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.door_interact_cursor = (
                (self.door_interact_cursor + 1)
                % len(self.door_interact_options)
            )
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            _, action = self.door_interact_options[self.door_interact_cursor]
            self._resolve_door_interact(action)
        elif event.key == pygame.K_ESCAPE:
            self._close_door_interact()

    def _resolve_door_interact(self, action):
        """Execute the chosen door interaction action."""
        if action == "pick":
            self._close_door_interact()
            self._attempt_lock_pick(self.door_interact_col,
                                    self.door_interact_row)
        elif action == "no_picks":
            self._close_door_interact()
            thief = self._find_thief()
            self.show_message(
                f"{thief.name} has no lockpicks left!", 2000)
        elif action == "no_thief":
            self._close_door_interact()
            self.show_message("You need a thief to pick the lock!", 2000)
        else:
            # "leave" or unknown
            self._close_door_interact()

    def _close_door_interact(self):
        """Dismiss the door interaction prompt."""
        self.door_interact_active = False
        self.door_interact_options = []
        self.door_interact_cursor = 0

    def _get_door_interact_state(self):
        """Return the current door interaction state for the renderer, or None."""
        if not self.door_interact_active:
            return None
        return {
            "col": self.door_interact_col,
            "row": self.door_interact_row,
            "cursor": self.door_interact_cursor,
            "options": self.door_interact_options,
        }

    def _find_thief(self):
        """Return the first alive Thief in the party, or None."""
        for m in self.game.party.members:
            if m.is_alive() and m.char_class == "Thief":
                return m
        return None

    def _attempt_lock_pick(self, col, row):
        """Thief attempts to pick a locked door. DEX saving throw: d20 + DEX mod >= 12.

        Consumes one Lockpick from the party's shared inventory on each attempt
        (success or failure).  If no lockpicks remain the attempt is blocked.
        """
        party = self.game.party
        thief = self._find_thief()

        if thief is None:
            self.show_message("The door is locked. You need a thief!", 2000)
            return

        # Check for lockpicks in shared inventory
        picks_left = party.inv_get_charges("Lockpick")
        if picks_left <= 0:
            self.show_message(
                f"{thief.name} has no lockpicks left!", 2000)
            return

        # Consume one lockpick (whether the attempt succeeds or fails)
        party.inv_consume_charge("Lockpick")
        remaining = party.inv_get_charges("Lockpick")

        roll = random.randint(1, 20) + thief.get_modifier(thief.dexterity)
        if roll >= 12:
            # Success — play unlock animation, then convert to open door
            self.door_unlock_anim = {
                "col": col,
                "row": row,
                "timer": 1200,      # total animation time in ms
                "duration": 1200,
            }
            self.game.sfx.play("lock_pick_success")
            self.show_message(
                f"{thief.name} picked the lock! "
                f"({remaining} picks left)", 1800)
        else:
            # Failure
            self.game.sfx.play("lock_pick_fail")
            self.show_message(
                f"{thief.name} failed to pick the lock. "
                f"({remaining} picks left)", 1500)

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

        if tile_id == TILE_STAIRS:
            self.show_message("Stairs up! Press ESC to leave.", 2000)

        elif tile_id == TILE_CHEST:
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
            if self.quest_levels and self.current_level == 0:
                # Descend to level 2
                self.current_level = 1
                self.dungeon_data = self.quest_levels[1]
                self.game.party.col = self.dungeon_data.entry_col
                self.game.party.row = self.dungeon_data.entry_row
                self.game.camera.map_width = self.dungeon_data.tile_map.width
                self.game.camera.map_height = self.dungeon_data.tile_map.height
                self.game.camera.update(self.game.party.col, self.game.party.row)
                # Recompute visibility for the new level
                self._visible_tiles = set()
                if self.torch_active:
                    self._visible_tiles = self._compute_visible_tiles()
                self.show_message("You descend deeper...", 2000)
                active_q = self._get_active_quest()
                if active_q:
                    active_q["current_level"] = 1
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
            # Spawn a portal doorway on an adjacent floor tile
            self._place_portal(col, row)
            self.show_message(f"Found the {artifact}! A portal appears!", 3000)

        elif tile_id == TILE_PORTAL:
            # Portal whisks the party back to the overworld
            self._entered = False
            self.pending_combat_message = None
            self.quest_levels = None
            self.current_level = 0
            self.game.party.col = self.overworld_col
            self.game.party.row = self.overworld_row
            self.game.camera.map_width = self.game.tile_map.width
            self.game.camera.map_height = self.game.tile_map.height
            self.game.camera.update(self.game.party.col, self.game.party.row)
            self.show_message("The portal returns you to the surface!", 3000)
            self.game.change_state("overworld")

    # ── Chest loot ─────────────────────────────────────────────

    # Weighted loot table: (item_name, weight)
    # Higher weight = more common.  None means gold only.
    _CHEST_LOOT = [
        (None,           10),   # gold only (most common)
        ("Torch",         6),
        ("Healing Herb",  5),
        ("Antidote",      3),
        ("Dagger",        3),
        ("Club",          3),
        ("Mace",          2),
        ("Leather",       2),
        ("Sling",         2),
        ("Axe",           1),
        ("Sword",         1),
        ("Chain",         1),
        ("Bow",           1),
    ]

    def _open_chest(self):
        """Roll random loot from a chest: gold, an item, or both."""
        self.game.sfx.play("treasure")
        # Always give some gold
        gold = random.randint(5, 30)
        self.game.party.gold += gold

        # Roll on the loot table
        total_weight = sum(w for _, w in self._CHEST_LOOT)
        roll = random.randint(1, total_weight)
        cumulative = 0
        chosen_item = None
        for item, weight in self._CHEST_LOOT:
            cumulative += weight
            if roll <= cumulative:
                chosen_item = item
                break

        if chosen_item:
            self.game.party.inv_add(chosen_item)
            self.show_message(
                f"Treasure! {gold} gold and {chosen_item}!", 2500)
        else:
            self.show_message(f"Treasure! Found {gold} gold!", 2000)

    def _place_portal(self, col, row):
        """Place a TILE_PORTAL on an adjacent walkable floor tile."""
        tmap = self.dungeon_data.tile_map
        # Try cardinal directions first, then diagonals
        for dc, dr in [(0, -1), (1, 0), (0, 1), (-1, 0),
                       (1, -1), (1, 1), (-1, 1), (-1, -1)]:
            nc, nr = col + dc, row + dr
            if 0 <= nc < tmap.width and 0 <= nr < tmap.height:
                if tmap.get_tile(nc, nr) == TILE_DFLOOR:
                    tmap.set_tile(nc, nr, TILE_PORTAL)
                    return
        # Fallback: place it right where the artifact was (already floor)
        tmap.set_tile(col, row, TILE_PORTAL)

    def _ascend_level(self):
        """Ascend from level 1 back to level 0 in a quest dungeon."""
        self.current_level = 0
        self.dungeon_data = self.quest_levels[0]
        # Find the stairs-down tile on level 0 to place the party there
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
            active_q["current_level"] = 0
        self.show_message("You ascend to the upper level.", 2000)

    def _exit_dungeon(self):
        """Leave the dungeon and return to the overworld."""
        # Reset entered flag so next dungeon visit starts fresh
        self._entered = False
        self.pending_combat_message = None

        # Restore party position on the overworld
        self.game.party.col = self.overworld_col
        self.game.party.row = self.overworld_row

        # Restore camera for overworld map
        self.game.camera.map_width = self.game.tile_map.width
        self.game.camera.map_height = self.game.tile_map.height
        self.game.camera.update(self.game.party.col, self.game.party.row)

        self.game.change_state("overworld")


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

        # Tick door unlock animation
        if self.door_unlock_anim:
            self.door_unlock_anim["timer"] -= dt_ms
            if self.door_unlock_anim["timer"] <= 0:
                # Animation finished — convert the tile to an open door
                col = self.door_unlock_anim["col"]
                row = self.door_unlock_anim["row"]
                self.dungeon_data.tile_map.set_tile(col, row, TILE_DDOOR)
                self.door_unlock_anim = None

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
                tinker_available=self._can_tinker())
            if self.use_item_anim:
                renderer.draw_use_item_animation(self.game.party, self.use_item_anim)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item)
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
                renderer.draw_item_examine(self.examining_item)
            return
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        visible = self._compute_visible_tiles()
        level_label = None
        if self.quest_levels:
            level_label = f"LEVEL {self.current_level + 1}"
        # Determine if infravision is providing the light (no torch active)
        has_torch_light = self.torch_active or self._has_torch_equipped()
        infravision_active = (not has_torch_light
                              and self.game.party.has_effect("Infravision"))

        renderer.draw_dungeon_u3(
            self.game.party,
            self.dungeon_data,
            message=self.message,
            visible_tiles=visible,
            torch_steps=self.torch_steps if has_torch_light else -1,
            level_label=level_label,
            detected_traps=self.dungeon_data.detected_traps,
            door_unlock_anim=self.door_unlock_anim,
            door_interact=self._get_door_interact_state(),
            infravision=infravision_active,
        )
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
