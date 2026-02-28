"""
Dungeon state - exploring a procedurally generated dungeon.

The party navigates dark corridors and rooms, finds treasure chests,
avoids traps, and can exit via the stairs back to the overworld.
"""

import random

import pygame

from src.states.base_state import BaseState
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_STAIRS, TILE_CHEST, TILE_TRAP, TILE_DFLOOR,
    TILE_STAIRS_DOWN, TILE_ARTIFACT, TILE_PORTAL,
)


class DungeonState(BaseState):
    """Handles exploration inside a dungeon."""

    def __init__(self, game):
        super().__init__(game)
        self.dungeon_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        self.showing_party = False
        self.showing_char_detail = None
        self.char_sheet_cursor = 0
        self.char_sheet_origin = None
        self.char_action_menu = False
        self.char_action_cursor = 0
        self.examining_item = None
        self.showing_party_inv = False
        self.party_inv_cursor = 0
        self.party_inv_choosing = False
        self.party_inv_member = 0
        self.party_inv_action_menu = False
        self.party_inv_action_cursor = 0
        self.choosing_effect = False
        self.effect_list = []
        self.effect_cursor = 0

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

        # If showing party screen, character detail, or party inventory, block movement
        if self.showing_party or self.showing_char_detail is not None or self.showing_party_inv:
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

        if self.dungeon_data.tile_map.is_walkable(target_col, target_row):
            party.col = target_col
            party.row = target_row
            self.move_cooldown = MOVE_REPEAT_DELAY
            self._check_tile_events()
            # After party moves, let every alive monster take a step
            self._move_monsters()
            # A monster may have walked adjacent — check for contact
            self._check_monster_contact()
            # Burn torch after each successful step
            self._tick_torch()
        else:
            self.move_cooldown = MOVE_REPEAT_DELAY

    def _handle_party_inv_input(self, event):
        """Handle input for the shared party inventory screen.

        The unified cursor covers 4 party equipment slots (indices 0-3)
        followed by shared inventory items (indices 4+).
        """
        party = self.game.party
        inv = party.shared_inventory
        members = party.members
        NUM_SLOTS = len(party.PARTY_SLOTS)
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        total_items = NUM_SLOTS + NUM_EFFECTS + len(inv)

        # Examining an item — close on ESC/Enter/Space
        if self.examining_item is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.examining_item = None
            return

        # Effect chooser is open
        if self.choosing_effect:
            if event.key == pygame.K_ESCAPE:
                self.choosing_effect = False
            elif event.key == pygame.K_UP and self.effect_list:
                self.effect_cursor = (self.effect_cursor - 1) % len(self.effect_list)
            elif event.key == pygame.K_DOWN and self.effect_list:
                self.effect_cursor = (self.effect_cursor + 1) % len(self.effect_list)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.effect_list:
                chosen_eff = self.effect_list[self.effect_cursor]
                eff_idx = self.party_inv_cursor - NUM_SLOTS
                slot_key = party.EFFECT_SLOTS[eff_idx]
                party.set_effect(slot_key, chosen_eff["name"])
                self.choosing_effect = False
            return

        # Action menu is open
        if self.party_inv_action_menu:
            options = self._get_party_inv_action_options()
            if not options:
                self.party_inv_action_menu = False
                return
            if event.key == pygame.K_UP:
                self.party_inv_action_cursor = (self.party_inv_action_cursor - 1) % len(options)
            elif event.key == pygame.K_DOWN:
                self.party_inv_action_cursor = (self.party_inv_action_cursor + 1) % len(options)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                chosen = options[self.party_inv_action_cursor]
                self._handle_party_inv_action(chosen)
            elif event.key == pygame.K_ESCAPE:
                self.party_inv_action_menu = False
            return

        # Browsing unified list (equip slots + effect slots + inventory)
        if True:
            if event.key == pygame.K_UP and total_items > 0:
                self.party_inv_cursor = (self.party_inv_cursor - 1) % total_items
            elif event.key == pygame.K_DOWN and total_items > 0:
                self.party_inv_cursor = (self.party_inv_cursor + 1) % total_items
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and total_items > 0:
                options = self._get_party_inv_action_options()
                if options:
                    self.party_inv_action_menu = True
                    self.party_inv_action_cursor = 0
            elif event.key == pygame.K_ESCAPE:
                self.showing_party_inv = False
            elif event.key == pygame.K_p:
                self.showing_party_inv = False
                self.showing_party = False
            else:
                # Number keys 1-4: open character detail sheet
                num = {pygame.K_1: 0, pygame.K_2: 1,
                       pygame.K_3: 2, pygame.K_4: 3}.get(event.key)
                if num is not None and num < len(self.game.party.members):
                    self.showing_party_inv = False
                    self.showing_char_detail = num
                    self.char_sheet_cursor = 0
                    self.char_sheet_origin = "inventory"

    def _handle_party_inv_action(self, chosen):
        """Execute the chosen action on the selected party inventory entry."""
        party = self.game.party
        NUM_SLOTS = len(party.PARTY_SLOTS)
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        idx = self.party_inv_cursor

        if idx < NUM_SLOTS:
            slot = party.PARTY_SLOTS[idx]
            if chosen == "UNEQUIP":
                party.party_unequip(slot)
                self.party_inv_action_menu = False
                # If the light slot was cleared, deactivate torch
                if slot == "light":
                    self.torch_active = False
                    self.torch_steps = 0
            elif chosen == "EXAMINE":
                item = party.get_equipped_name(slot)
                if item:
                    self.examining_item = item
        elif idx < NUM_SLOTS + NUM_EFFECTS:
            # Acting on an effect slot
            eff_idx = idx - NUM_SLOTS
            slot_key = party.EFFECT_SLOTS[eff_idx]
            if chosen == "ASSIGN EFFECT":
                self.effect_list = party.get_available_effects()
                self.effect_cursor = 0
                self.choosing_effect = True
                self.party_inv_action_menu = False
            elif chosen == "REMOVE":
                party.set_effect(slot_key, None)
                self.party_inv_action_menu = False
        else:
            inv_idx = idx - NUM_SLOTS - NUM_EFFECTS
            inv = party.shared_inventory
            if inv_idx < len(inv):
                item_name = party.item_name(inv[inv_idx])
                if chosen == "EXAMINE":
                    self.examining_item = item_name
                elif chosen.startswith("GIVE TO "):
                    give_name = chosen[8:].strip()
                    for mi, member in enumerate(party.members):
                        if member.name.upper() == give_name:
                            party.give_item_to_member(inv_idx, mi)
                            break
                    self.party_inv_action_menu = False
                    new_total = NUM_SLOTS + NUM_EFFECTS + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)
                elif chosen.startswith("EQUIP → "):
                    slot = chosen.split("→ ", 1)[1].strip().lower()
                    party.party_equip(item_name, slot)
                    self.party_inv_action_menu = False
                    new_total = NUM_SLOTS + NUM_EFFECTS + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)
                    # If a torch was equipped to the light slot, activate it
                    if slot == "light" and party.get_equipped_name("light") == "Torch":
                        self._activate_torch()

    def _get_party_inv_action_options(self):
        """Build action options for the selected party inventory entry."""
        party = self.game.party
        NUM_SLOTS = len(party.PARTY_SLOTS)
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        idx = self.party_inv_cursor

        if idx < NUM_SLOTS:
            slot = party.PARTY_SLOTS[idx]
            item = party.get_equipped_name(slot)
            if item is None:
                return []
            return ["UNEQUIP", "EXAMINE"]
        elif idx < NUM_SLOTS + NUM_EFFECTS:
            eff_idx = idx - NUM_SLOTS
            slot_key = party.EFFECT_SLOTS[eff_idx]
            current = party.get_effect(slot_key)
            options = []
            if party.get_available_effects():
                options.append("ASSIGN EFFECT")
            if current is not None:
                options.append("REMOVE")
            return options
        else:
            inv_idx = idx - NUM_SLOTS - NUM_EFFECTS
            inv = party.shared_inventory
            if inv_idx >= len(inv):
                return []
            options = []
            for s in party.PARTY_SLOTS:
                if party.get_equipped_name(s) is None:
                    label = party.PARTY_SLOT_LABELS[s]
                    options.append(f"EQUIP → {label}")
            for mi, member in enumerate(self.game.party.members):
                options.append(f"GIVE TO {member.name.upper()}")
            options.append("EXAMINE")
            return options

    def _handle_equip_action(self, member):
        """Open the action menu for the selected item/slot."""
        options = self._get_action_options(member)
        if not options:
            self.message = "Empty slot — equip items from inventory"
            self.message_timer = 2000
            return
        self.char_action_menu = True
        self.char_action_cursor = 0

    def _get_item_at_cursor(self, member):
        """Return the item name at the current char_sheet_cursor position."""
        idx = self.char_sheet_cursor
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            return member.equipped.get(slot_keys[idx])
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                return member.inventory[inv_idx]
        return None

    def _get_action_options(self, member):
        """Build the list of action option keys for the current cursor position."""
        from src.party import PartyMember
        idx = self.char_sheet_cursor
        options = []
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            slot = slot_keys[idx]
            current = member.equipped.get(slot)
            if current:
                options.append("UNEQUIP")
                options.append("RETURN TO PARTY STASH")
                options.append("EXAMINE")
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                item_name = member.inventory[inv_idx]
                if member.can_use_item(item_name):
                    valid_slots = member.get_valid_slots(item_name)
                    for s in valid_slots:
                        label = PartyMember._SLOT_LABELS[s]
                        options.append(f"EQUIP \u2192 {label}")
                options.append("RETURN TO PARTY STASH")
                options.append("EXAMINE")
        return options

    def _handle_char_action_input(self, event):
        """Handle input while the action menu popup is open."""
        if self.examining_item is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.examining_item = None
            return

        member = self.game.party.members[self.showing_char_detail]
        options = self._get_action_options(member)

        if not options:
            self.char_action_menu = False
            return

        if event.key == pygame.K_UP:
            self.char_action_cursor = (self.char_action_cursor - 1) % len(options)
        elif event.key == pygame.K_DOWN:
            self.char_action_cursor = (self.char_action_cursor + 1) % len(options)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            chosen = options[self.char_action_cursor]
            idx = self.char_sheet_cursor
            if chosen == "EXAMINE":
                self.examining_item = self._get_item_at_cursor(member)
                return
            elif chosen == "UNEQUIP":
                if idx < 4:
                    slot_keys = ["right_hand", "left_hand", "body", "head"]
                    if not member.unequip_slot(slot_keys[idx]):
                        self.message = f"Cannot remove basic {member.equipped.get(slot_keys[idx], 'gear')}!"
                        self.message_timer = 2000
            elif chosen.startswith("EQUIP"):
                inv_idx = idx - 4
                if inv_idx < len(member.inventory):
                    from src.party import PartyMember
                    _label_to_key = {v: k for k, v in PartyMember._SLOT_LABELS.items()}
                    slot_label = chosen.split("\u2192 ", 1)[1].strip()
                    slot_key = _label_to_key.get(slot_label)
                    member.equip_item(member.inventory[inv_idx], slot_key)
            elif chosen == "RETURN TO PARTY STASH":
                if idx < 4:
                    slot_keys = ["right_hand", "left_hand", "body", "head"]
                    member.return_equipped_to_party(slot_keys[idx], self.game.party)
                else:
                    inv_idx = idx - 4
                    if inv_idx < len(member.inventory):
                        member.return_item_to_party(
                            member.inventory[inv_idx], self.game.party)
            self.char_action_menu = False
            total = 4 + len(member.inventory)
            if self.char_sheet_cursor >= total:
                self.char_sheet_cursor = max(0, total - 1)
        elif event.key == pygame.K_ESCAPE:
            self.char_action_menu = False

    # ── Torch system ─────────────────────────────────────────────

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
        """Remove the burned-out torch from the party LIGHT slot."""
        party = self.game.party
        if party.get_equipped_name("light") == "Torch":
            party.equipped["light"] = None

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

        has_light = self.torch_active or self._has_torch_equipped()
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
        """Transition to combat state against the given monster."""
        # Use the first alive party member as the fighter
        fighter = None
        for member in self.game.party.members:
            if member.is_alive():
                fighter = member
                break
        if not fighter:
            return  # No alive party members (shouldn't happen)

        combat_state = self.game.states.get("combat")
        if combat_state:
            self.game.sfx.play("encounter")
            combat_state.start_combat(fighter, monster, source_state="dungeon")
            self.game.change_state("combat")

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
                if self.game.quest:
                    self.game.quest["current_level"] = 1
            else:
                self.show_message("Stairs leading down...", 1500)

        elif tile_id == TILE_ARTIFACT:
            # Pick up the quest artifact
            self.game.party.inv_add("Shadow Crystal")
            self.dungeon_data.tile_map.set_tile(col, row, TILE_DFLOOR)
            if self.game.quest:
                self.game.quest["status"] = "artifact_found"
            # Spawn a portal doorway on an adjacent floor tile
            self._place_portal(col, row)
            self.show_message("Found the Shadow Crystal! A portal appears!", 3000)

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
        if self.game.quest:
            self.game.quest["current_level"] = 0
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

    def show_message(self, text, duration_ms=2000):
        self.message = text
        self.message_timer = duration_ms

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
                effect_cursor=self.effect_cursor)
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
        renderer.draw_dungeon_u3(
            self.game.party,
            self.dungeon_data,
            message=self.message,
            visible_tiles=visible,
            torch_steps=self.torch_steps if (self.torch_active or self._has_torch_equipped()) else -1,
            level_label=level_label,
        )
