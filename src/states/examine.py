"""
Examine state — zoomed-in local area view of the current overworld tile.

Pressing E on the overworld opens this state, which shows a 12×14 tile grid
themed to match the terrain.  The player walks a single character around and
can pick up randomly-spawned items.  Press ESC to return to the overworld.
"""

import random
import pygame

from src.states.base_state import BaseState
from src.settings import (
    TILE_GRASS, TILE_FOREST, TILE_SAND, TILE_PATH,
    TILE_DEFS,
)

# ── Grid dimensions ──────────────────────────────────────────────
EXAMINE_COLS = 12
EXAMINE_ROWS = 14

# ── Terrain obstacle density ─────────────────────────────────────
# Maps tile type → (obstacle_kind, min_count, max_count).
# obstacle_kind is passed to the renderer to choose the right sprite.
TERRAIN_OBSTACLES = {
    TILE_GRASS:  ("bush",  0, 2),    # mostly open, occasional bush
    TILE_FOREST: ("tree",  6, 10),   # dense trees
    TILE_SAND:   ("rock",  1, 3),    # scattered rocks
    TILE_PATH:   ("bush",  0, 1),    # mostly clear, rare bush
}
_DEFAULT_OBSTACLES = ("bush", 0, 1)

# ── Terrain-themed loot tables ───────────────────────────────────
# Low-value scraps only — nothing you'd be excited to find.
# Each entry is (item_name, weight).
EXAMINE_LOOT = {
    TILE_GRASS: [
        ("Stones", 5),
        ("Torch", 3),
    ],
    TILE_FOREST: [
        ("Stones", 4),
        ("Torch", 4),
    ],
    TILE_SAND: [
        ("Stones", 7),
        ("Torch", 3),
    ],
    TILE_PATH: [
        ("Stones", 6),
        ("Torch", 4),
    ],
}
_DEFAULT_LOOT = EXAMINE_LOOT[TILE_GRASS]

# ── Player start position (centre of interior) ──────────────────
_START_COL = 5
_START_ROW = 6


class ExamineState(BaseState):
    """Zoomed-in local area exploration."""

    def __init__(self, game):
        super().__init__(game)
        self.player_col = _START_COL
        self.player_row = _START_ROW
        self.examined_tile_type = TILE_GRASS
        self.obstacles = {}               # {(col, row): obstacle_kind}
        self.ground_items = {}            # {(col, row): {"item": str, "gold": int}}
        self.pickup_message = ""
        self.pickup_msg_timer = 0         # ms remaining
        self.tile_name = ""
        self.party_member_name = ""

    # ── Lifecycle ─────────────────────────────────────────────────

    def enter(self):
        party = self.game.party
        self.examined_tile_type = self.game.tile_map.get_tile(
            party.col, party.row)
        self.tile_name = TILE_DEFS.get(
            self.examined_tile_type, {}).get("name", "Area")

        alive = [m for m in party.members if m.is_alive()]
        self.party_member_name = alive[0].name if alive else "Party"

        # Reset position and messages
        self.player_col = _START_COL
        self.player_row = _START_ROW
        self.pickup_message = ""
        self.pickup_msg_timer = 0

        self._spawn_obstacles()
        self._spawn_examine_items()

    def exit(self):
        self.ground_items.clear()
        self.obstacles.clear()

    # ── Input ─────────────────────────────────────────────────────

    def handle_input(self, events, keys_pressed):
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                self.game.change_state("overworld")
                return
            if event.key in (pygame.K_UP, pygame.K_w):
                self._try_move(0, -1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._try_move(0, 1)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._try_move(-1, 0)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._try_move(1, 0)

    # ── Update ────────────────────────────────────────────────────

    def update(self, dt):
        if self.pickup_msg_timer > 0:
            self.pickup_msg_timer -= dt * 1000
            if self.pickup_msg_timer <= 0:
                self.pickup_message = ""
                self.pickup_msg_timer = 0

    # ── Draw ──────────────────────────────────────────────────────

    def draw(self, renderer):
        renderer.draw_examine_area(
            player_col=self.player_col,
            player_row=self.player_row,
            tile_type=self.examined_tile_type,
            obstacles=self.obstacles,
            ground_items=self.ground_items,
            tile_name=self.tile_name,
            party_member_name=self.party_member_name,
            pickup_message=self.pickup_message,
        )

    # ── Movement ──────────────────────────────────────────────────

    def _try_move(self, dcol, drow):
        """Move player if the destination is within the walkable interior."""
        new_col = self.player_col + dcol
        new_row = self.player_row + drow
        # Interior bounds: exclude the outer edge ring
        if not (1 <= new_col <= EXAMINE_COLS - 2
                and 1 <= new_row <= EXAMINE_ROWS - 2):
            return
        if (new_col, new_row) in self.obstacles:
            return
        self.player_col = new_col
        self.player_row = new_row
        self._attempt_pickup()

    # ── Obstacle generation ─────────────────────────────────────

    def _spawn_obstacles(self):
        """Scatter terrain-appropriate obstacles across the interior."""
        self.obstacles.clear()
        kind, lo, hi = TERRAIN_OBSTACLES.get(
            self.examined_tile_type, _DEFAULT_OBSTACLES)
        count = random.randint(lo, hi)
        for _ in range(count):
            for _attempt in range(40):
                col = random.randint(1, EXAMINE_COLS - 2)
                row = random.randint(1, EXAMINE_ROWS - 2)
                if (col, row) == (_START_COL, _START_ROW):
                    continue
                if (col, row) in self.obstacles:
                    continue
                self.obstacles[(col, row)] = kind
                break

    # ── Item spawning ─────────────────────────────────────────────

    def _spawn_examine_items(self):
        """Occasionally spawn 0–1 low-value items on random interior tiles."""
        self.ground_items.clear()
        loot_table = EXAMINE_LOOT.get(self.examined_tile_type, _DEFAULT_LOOT)
        weights = [w for _, w in loot_table]
        # Most of the time nothing spawns (60% chance of zero items).
        num_items = random.choices([0, 0, 0, 1, 1], k=1)[0]

        for _ in range(num_items):
            for _attempt in range(30):
                col = random.randint(1, EXAMINE_COLS - 2)
                row = random.randint(1, EXAMINE_ROWS - 2)
                if (col, row) == (_START_COL, _START_ROW):
                    continue
                if (col, row) in self.ground_items:
                    continue
                if (col, row) in self.obstacles:
                    continue
                choice = random.choices(loot_table, weights=weights, k=1)[0]
                item_name = choice[0]
                self.ground_items[(col, row)] = {"item": item_name, "gold": 0}
                break

    # ── Pickup ────────────────────────────────────────────────────

    def _attempt_pickup(self):
        """Pick up any item at the player's current position."""
        pos = (self.player_col, self.player_row)
        if pos not in self.ground_items:
            return
        loot = self.ground_items.pop(pos)
        item_name = loot.get("item")
        gold = loot.get("gold", 0)
        parts = []
        if item_name:
            self.game.party.inv_add(item_name)
            parts.append(item_name)
        if gold > 0:
            self.game.party.gold += gold
            parts.append(f"{gold} gold")
        if parts:
            self.pickup_message = f"Picked up {', '.join(parts)}!"
            self.pickup_msg_timer = 2000
            self.game.sfx.play("chirp")
