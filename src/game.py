"""
Main Game class - the heart of the application.

Manages the game loop, state machine, and top-level resources.
"""

import pygame

from src.settings import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, GAME_TITLE, COLOR_BLACK
from src.tile_map import create_test_map
from src.party import create_default_party
from src.camera import Camera
from src.renderer import Renderer
from src.states.overworld import OverworldState
from src.states.town import TownState
from src.states.dungeon import DungeonState
from src.states.combat import CombatState
from src.town_generator import generate_town
from src.music import MusicManager


class Game:
    """
    Top-level game object.

    Owns the pygame display, clock, and manages the game state machine.
    """

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(GAME_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        # --- Create game world ---
        self.tile_map = create_test_map()

        # Party start position is defined in data/party.json
        self.party = create_default_party()

        # Camera follows the party
        self.camera = Camera(self.tile_map.width, self.tile_map.height)
        self.camera.update(self.party.col, self.party.row)

        # Renderer
        self.renderer = Renderer(self.screen)

        # --- Town data ---
        # Pre-generate the town so it persists across visits
        self.town_data = generate_town("Thornwall")

        # --- Quest state ---
        # None when no quest active; dict when quest is in progress
        self.quest = None

        # --- Music ---
        self.music = MusicManager()

        # --- State machine ---
        self.states = {
            "overworld": OverworldState(self),
            "town": TownState(self),
            "dungeon": DungeonState(self),
            "combat": CombatState(self),
        }
        self.current_state = None
        self.change_state("overworld")

    def change_state(self, state_name):
        """Switch to a different game state."""
        if self.current_state:
            self.current_state.exit()
        self.current_state = self.states[state_name]
        self.current_state.enter()
        # Switch music to match the new state
        self.music.play(state_name)

    def run(self):
        """Main game loop."""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # delta time in seconds

            # --- Events ---
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                    self.music.toggle_mute()

            # --- Input ---
            keys_pressed = pygame.key.get_pressed()
            self.current_state.handle_input(events, keys_pressed)

            # --- Update ---
            self.current_state.update(dt)
            self.camera.update(self.party.col, self.party.row)

            # --- Draw ---
            self.screen.fill(COLOR_BLACK)
            self.current_state.draw(self.renderer)
            pygame.display.flip()

        pygame.quit()
