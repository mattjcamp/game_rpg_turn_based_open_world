"""
Overworld state - the main exploration mode.

This is where the party walks around the overworld map, encounters
towns, dungeons, and random encounters. It's the "hub" state of
the game.
"""

import pygame

from src.states.base_state import BaseState
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_TOWN, TILE_DUNGEON,
)
from src.dungeon_generator import generate_dungeon


class OverworldState(BaseState):
    """Handles overworld exploration."""

    def __init__(self, game):
        super().__init__(game)
        self.message = ""
        self.message_timer = 0  # ms remaining to show message
        self.move_cooldown = 0  # ms until next move allowed
        self.showing_party = False

    def enter(self):
        self.message = "Welcome, adventurers! Use arrow keys to explore."
        self.message_timer = 3000

    def handle_input(self, events, keys_pressed):
        """Handle arrow key movement with repeat delay."""
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.showing_party:
                        self.showing_party = False
                        return
                    self.game.running = False
                    return
                if event.key == pygame.K_p:
                    self.showing_party = not self.showing_party
                    return

        # If showing party screen, block all other input
        if self.showing_party:
            return

        # Movement only if cooldown has elapsed
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
            party = self.game.party
            moved = party.try_move(dcol, drow, self.game.tile_map)

            if moved:
                self.move_cooldown = MOVE_REPEAT_DELAY
                self._check_tile_events()
            else:
                self.move_cooldown = MOVE_REPEAT_DELAY
                self.show_message("Blocked!", 800)

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        tile_id = self.game.tile_map.get_tile(
            self.game.party.col, self.game.party.row
        )

        if tile_id == TILE_TOWN:
            # Enter the town!
            town_state = self.game.states["town"]
            town_state.enter_town(
                self.game.town_data,
                self.game.party.col,
                self.game.party.row
            )
            self.game.change_state("town")
            return

        elif tile_id == TILE_DUNGEON:
            # Generate a fresh dungeon each time!
            dungeon_data = generate_dungeon("The Depths")
            dungeon_state = self.game.states["dungeon"]
            dungeon_state.enter_dungeon(
                dungeon_data,
                self.game.party.col,
                self.game.party.row
            )
            self.game.change_state("dungeon")
            return

    def show_message(self, text, duration_ms=2000):
        """Display a temporary message."""
        self.message = text
        self.message_timer = duration_ms

    def update(self, dt):
        """Update timers."""
        dt_ms = dt * 1000  # convert seconds to ms
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
        """Draw the overworld in Ultima III style."""
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        renderer.draw_overworld_u3(
            self.game.party,
            self.game.tile_map,
            message=self.message,
        )
