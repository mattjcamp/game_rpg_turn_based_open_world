"""
Base class for game states.

The game uses a simple state machine: at any moment the game is in
exactly one state (overworld, town, dungeon, combat, menu, etc.).
Each state handles its own input, update, and draw logic.
"""


class BaseState:
    """Abstract base class for game states."""

    def __init__(self, game):
        self.game = game

    def enter(self):
        """Called when this state becomes active."""
        pass

    def exit(self):
        """Called when leaving this state."""
        pass

    def handle_input(self, events, keys_pressed):
        """Process input events and key states."""
        pass

    def update(self, dt):
        """Update game logic. dt is delta time in seconds."""
        pass

    def draw(self, renderer):
        """Draw the state to the screen."""
        pass
