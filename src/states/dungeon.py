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
)


class DungeonState(BaseState):
    """Handles exploration inside a dungeon."""

    def __init__(self, game):
        super().__init__(game)
        self.dungeon_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0

        # Save overworld position for when we leave
        self.overworld_col = 0
        self.overworld_row = 0

    def enter_dungeon(self, dungeon_data, overworld_col, overworld_row):
        """
        Set up the dungeon state with dungeon-specific data.
        Called before change_state.
        """
        self.dungeon_data = dungeon_data
        self.overworld_col = overworld_col
        self.overworld_row = overworld_row

    def enter(self):
        """Called when this state becomes active."""
        if self.dungeon_data:
            self.show_message(
                f"You descend into {self.dungeon_data.name}...", 2500
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
                if event.key == pygame.K_ESCAPE:
                    # Only allow escape if standing on stairs
                    tile_id = self.dungeon_data.tile_map.get_tile(
                        self.game.party.col, self.game.party.row
                    )
                    if tile_id == TILE_STAIRS:
                        self._exit_dungeon()
                    else:
                        self.show_message(
                            "Find the stairs to escape!", 1500
                        )
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
        """Move the party within the dungeon."""
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
        else:
            self.move_cooldown = MOVE_REPEAT_DELAY

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
                # Random treasure
                gold = random.randint(10, 50)
                self.game.party.gold += gold
                self.show_message(f"Treasure! Found {gold} gold!", 2000)
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

    def _exit_dungeon(self):
        """Leave the dungeon and return to the overworld."""
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
        """Draw the dungeon with limited visibility."""
        renderer.draw_map(self.dungeon_data.tile_map, self.game.camera)
        # Draw monsters (only alive ones will be visible)
        renderer.draw_monsters(self.dungeon_data.monsters, self.game.camera)
        renderer.draw_party(self.game.party, self.game.camera)
        # Fog of war — can only see 4 tiles in each direction
        renderer.draw_fog_of_war(self.game.party, self.game.camera, light_radius=4)
        renderer.draw_hud_dungeon(self.game.party, self.dungeon_data)
        if self.message:
            renderer.draw_message(self.message)
