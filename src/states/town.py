"""
Town state - exploring a town interior.

The party walks around inside a town, talks to NPCs by bumping into them,
and can leave through the exit gate to return to the overworld.
"""

import pygame

from src.states.base_state import BaseState
from src.settings import MOVE_REPEAT_DELAY, TILE_EXIT


class TownState(BaseState):
    """Handles exploration inside a town."""

    def __init__(self, game):
        super().__init__(game)
        self.town_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        self.npc_dialogue_active = False
        self.npc_speaking = None
        self.showing_party = False
        self.showing_char_detail = None
        self.char_sheet_cursor = 0

        # We'll save the overworld position so we can restore it on exit
        self.overworld_col = 0
        self.overworld_row = 0

    def enter_town(self, town_data, overworld_col, overworld_row):
        """
        Set up the town state with town-specific data.
        Called before change_state so the town knows what to load.
        """
        self.town_data = town_data
        self.overworld_col = overworld_col
        self.overworld_row = overworld_row

    def enter(self):
        """Called when this state becomes active."""
        if self.town_data:
            town_name = self.town_data.name
            self.show_message(f"Welcome to {town_name}!", 2500)
            # Move party to town entry point
            self.game.party.col = self.town_data.entry_col
            self.game.party.row = self.town_data.entry_row
            # Update camera for the town map
            self.game.camera.map_width = self.town_data.tile_map.width
            self.game.camera.map_height = self.town_data.tile_map.height
            self.game.camera.update(self.game.party.col, self.game.party.row)

    def exit(self):
        """Called when leaving this state."""
        self.npc_dialogue_active = False
        self.npc_speaking = None

    def handle_input(self, events, keys_pressed):
        """Handle movement and NPC interaction."""
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_p:
                    if self.showing_char_detail is not None:
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        self.showing_party = False
                        return
                    if not self.npc_dialogue_active:
                        self.showing_party = not self.showing_party
                        return
                if event.key == pygame.K_ESCAPE:
                    if self.showing_char_detail is not None:
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        return
                    if self.showing_party:
                        self.showing_party = False
                        return
                # Character sheet cursor navigation
                if self.showing_char_detail is not None:
                    member = self.game.party.members[self.showing_char_detail]
                    total_rows = 3 + len(member.inventory)
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
                        return
                    if self.npc_dialogue_active:
                        # Dismiss dialogue
                        self.npc_dialogue_active = False
                        self.npc_speaking = None
                        self.message = ""
                        self.message_timer = 0
                    else:
                        # Leave town
                        self._exit_town()
                        return

                # Space/Enter to advance NPC dialogue or interact
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    if self.npc_dialogue_active:
                        # Advance dialogue
                        self._advance_dialogue()
                        return

        # If showing party screen, character detail, or dialogue, block movement
        if self.showing_party or self.showing_char_detail is not None:
            return
        if self.npc_dialogue_active:
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
            self._try_move_or_interact(dcol, drow)

    def _try_move_or_interact(self, dcol, drow):
        """Move the party, or interact with an NPC if one is in the way."""
        party = self.game.party
        target_col = party.col + dcol
        target_row = party.row + drow

        # Check for NPC at target
        npc = self.town_data.get_npc_at(target_col, target_row)
        if npc:
            self._start_dialogue(npc)
            self.move_cooldown = MOVE_REPEAT_DELAY
            return

        # Check walkability on the town map
        if self.town_data.tile_map.is_walkable(target_col, target_row):
            party.col = target_col
            party.row = target_row
            self.move_cooldown = MOVE_REPEAT_DELAY
            self._check_tile_events()
        else:
            self.move_cooldown = MOVE_REPEAT_DELAY

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        tile_id = self.town_data.tile_map.get_tile(
            self.game.party.col, self.game.party.row
        )
        if tile_id == TILE_EXIT:
            self._exit_town()

    def _start_dialogue(self, npc):
        """Begin talking to an NPC."""
        self.npc_dialogue_active = True
        self.npc_speaking = npc
        line = npc.get_dialogue()
        self.message = f"{npc.name}: {line}"
        self.message_timer = 0  # dialogue stays until dismissed

    def _advance_dialogue(self):
        """Dismiss the current dialogue."""
        self.npc_dialogue_active = False
        self.npc_speaking = None
        self.message = ""
        self.message_timer = 0

    def _handle_equip_action(self, member):
        """Handle Enter key on the character sheet item list."""
        idx = self.char_sheet_cursor
        if idx < 3:
            slot_keys = ["body", "melee", "ranged"]
            member.unequip_slot(slot_keys[idx])
        else:
            inv_idx = idx - 3
            if inv_idx < len(member.inventory):
                member.equip_item(member.inventory[inv_idx])
        total = 3 + len(member.inventory)
        if self.char_sheet_cursor >= total:
            self.char_sheet_cursor = max(0, total - 1)

    def _exit_town(self):
        """Leave the town and return to the overworld."""
        # Restore party position on the overworld
        self.game.party.col = self.overworld_col
        self.game.party.row = self.overworld_row

        # Restore camera for overworld map
        self.game.camera.map_width = self.game.tile_map.width
        self.game.camera.map_height = self.game.tile_map.height
        self.game.camera.update(self.game.party.col, self.game.party.row)

        self.game.change_state("overworld")

    def show_message(self, text, duration_ms=2000):
        """Display a temporary message."""
        self.message = text
        self.message_timer = duration_ms

    def update(self, dt):
        """Update timers."""
        dt_ms = dt * 1000
        if self.message_timer > 0:
            self.message_timer -= dt_ms
            if self.message_timer <= 0:
                if not self.npc_dialogue_active:
                    self.message = ""
                self.message_timer = 0

        if self.move_cooldown > 0:
            self.move_cooldown -= dt_ms
            if self.move_cooldown < 0:
                self.move_cooldown = 0

    def draw(self, renderer):
        """Draw the town in Ultima III style."""
        if self.showing_char_detail is not None:
            idx = self.showing_char_detail
            renderer.draw_character_sheet_u3(
                self.game.party.members[idx], idx, self.char_sheet_cursor)
            return
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        # Use the new sprite-tile-based town renderer
        msg = self.message if not self.npc_dialogue_active else ""
        renderer.draw_town_u3(
            self.game.party,
            self.town_data,
            message=msg,
        )
        # Dialogue box renders on top if active
        if self.message and self.npc_dialogue_active:
            renderer.draw_dialogue_box(self.message)
