"""
Examine state — zoomed-in local area view of the current overworld tile.

Pressing E on the overworld opens this state, which shows a 12×14 tile grid
themed to match the terrain.  The player walks a single character around and
can pick up randomly-spawned items.  Press E or ESC to return to the overworld.

Tile layouts (obstacles and ground items) are persisted so revisiting a tile
shows the same layout.  The player can drop inventory items with L.
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
# Forageable items: rocks are common, reagents less so, healing herbs rare.
# Each entry is (item_name, weight).
# The "reagent" entries are placeholders — the actual reagent chosen at
# spawn time is picked randomly from FORAGE_REAGENTS.
EXAMINE_LOOT = {
    TILE_GRASS: [
        ("Rock", 10),
        ("_reagent_", 4),
        ("Healing Herb", 2),
    ],
    TILE_FOREST: [
        ("Rock", 8),
        ("_reagent_", 6),
        ("Healing Herb", 3),
    ],
    TILE_SAND: [
        ("Rock", 12),
        ("_reagent_", 3),
        ("Healing Herb", 1),
    ],
    TILE_PATH: [
        ("Rock", 10),
        ("_reagent_", 3),
        ("Healing Herb", 2),
    ],
}
_DEFAULT_LOOT = EXAMINE_LOOT[TILE_GRASS]

# Reagent items that can appear when "_reagent_" is rolled.
FORAGE_REAGENTS = [
    "Moonpetal",
    "Glowcap Mushroom",
    "Serpent Root",
    "Brimite Ore",
    "Spring Water",
]

# Classes whose presence in the party boosts reagent find rates.
_HERBALIST_CLASSES = {"ranger", "alchemist"}

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
        # Drop mode state
        self.drop_mode = False
        self.drop_cursor = 0
        self.drop_items = []              # list of item names available to drop
        self.drop_message = ""
        self.drop_msg_timer = 0

    # ── Lifecycle ─────────────────────────────────────────────────

    def enter(self):
        party = self.game.party
        self.examined_tile_type = self.game.tile_map.get_tile(
            party.col, party.row)
        self.tile_name = TILE_DEFS.get(
            self.examined_tile_type, {}).get("name", "Area")

        self.party_member_name = ""

        # Reset position and messages
        self.player_col = _START_COL
        self.player_row = _START_ROW
        self.pickup_message = ""
        self.pickup_msg_timer = 0
        self.drop_mode = False
        self.drop_cursor = 0
        self.drop_items = []
        self.drop_message = ""
        self.drop_msg_timer = 0

        # Check for a saved layout for this overworld tile
        saved = self.game.get_examined_tile(party.col, party.row)
        if saved is not None:
            self._restore_layout(saved)
        else:
            self._spawn_obstacles()
            self._spawn_examine_items()

    def exit(self):
        # Save the current layout before leaving
        party = self.game.party
        self._save_layout(party.col, party.row)
        self.ground_items.clear()
        self.obstacles.clear()

    # ── Persistence ──────────────────────────────────────────────

    def _save_layout(self, col, row):
        """Persist current obstacles and ground items for this tile."""
        data = {
            "obstacles": dict(self.obstacles),
            "ground_items": {
                f"{c},{r}": v
                for (c, r), v in self.ground_items.items()
            },
        }
        self.game.save_examined_tile(col, row, data)

    def _restore_layout(self, saved):
        """Restore obstacles and ground items from saved data."""
        self.obstacles.clear()
        self.ground_items.clear()
        for pos, kind in saved.get("obstacles", {}).items():
            if isinstance(pos, tuple):
                self.obstacles[pos] = kind
            else:
                # Saved keys may be "col,row" strings
                c, r = pos.split(",")
                self.obstacles[(int(c), int(r))] = kind
        for pos_str, item_data in saved.get("ground_items", {}).items():
            c, r = pos_str.split(",")
            self.ground_items[(int(c), int(r))] = dict(item_data)

    # ── Input ─────────────────────────────────────────────────────

    def handle_input(self, events, keys_pressed):
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if self.drop_mode:
                self._handle_drop_input(event)
                return
            if event.key in (pygame.K_ESCAPE, pygame.K_e):
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
            elif event.key == pygame.K_l:
                self._enter_drop_mode()

    def _handle_drop_input(self, event):
        """Handle input while in drop-item selection mode."""
        if event.key == pygame.K_ESCAPE:
            self.drop_mode = False
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            if self.drop_cursor > 0:
                self.drop_cursor -= 1
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            if self.drop_cursor < len(self.drop_items) - 1:
                self.drop_cursor += 1
        elif event.key == pygame.K_RETURN:
            self._confirm_drop()

    # ── Update ────────────────────────────────────────────────────

    def update(self, dt):
        if self.pickup_msg_timer > 0:
            self.pickup_msg_timer -= dt * 1000
            if self.pickup_msg_timer <= 0:
                self.pickup_message = ""
                self.pickup_msg_timer = 0
        if self.drop_msg_timer > 0:
            self.drop_msg_timer -= dt * 1000
            if self.drop_msg_timer <= 0:
                self.drop_message = ""
                self.drop_msg_timer = 0

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
            drop_mode=self.drop_mode,
            drop_items=self.drop_items,
            drop_cursor=self.drop_cursor,
            drop_message=self.drop_message,
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

    def _has_herbalist(self):
        """Return True if any alive party member is a Ranger or Alchemist."""
        for m in self.game.party.members:
            if m.is_alive() and m.char_class.lower() in _HERBALIST_CLASSES:
                return True
        return False

    def _build_loot_table(self):
        """Return (loot_table, weights) adjusted for party composition.

        If a Ranger or Alchemist is present, reagent weights are doubled.
        """
        base = EXAMINE_LOOT.get(self.examined_tile_type, _DEFAULT_LOOT)
        herbalist = self._has_herbalist()
        table = []
        weights = []
        for item_name, weight in base:
            table.append(item_name)
            if herbalist and item_name == "_reagent_":
                weights.append(weight * 2)
            else:
                weights.append(weight)
        return table, weights

    def _resolve_item_name(self, raw_name):
        """Turn a loot-table entry into a real item name.

        The placeholder ``_reagent_`` is replaced with a random reagent.
        """
        if raw_name == "_reagent_":
            return random.choice(FORAGE_REAGENTS)
        return raw_name

    def _spawn_examine_items(self):
        """Occasionally spawn 0–1 forageable items on random interior tiles."""
        self.ground_items.clear()
        table, weights = self._build_loot_table()
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
                raw = random.choices(table, weights=weights, k=1)[0]
                item_name = self._resolve_item_name(raw)
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

    # ── Drop items ───────────────────────────────────────────────

    def _enter_drop_mode(self):
        """Open the drop-item selector from current inventory."""
        names = self.game.party.inv_names()
        if not names:
            self.pickup_message = "Stash is empty — nothing to drop."
            self.pickup_msg_timer = 2500
            return
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for n in names:
            if n not in seen:
                seen.add(n)
                unique.append(n)
        self.drop_items = unique
        self.drop_cursor = 0
        self.drop_mode = True

    def _confirm_drop(self):
        """Drop the selected item at the player's feet."""
        if not self.drop_items:
            self.drop_mode = False
            return
        item_name = self.drop_items[self.drop_cursor]
        pos = (self.player_col, self.player_row)

        # Can't drop on a tile that already has an item or an obstacle
        if pos in self.ground_items:
            self.drop_message = "Something is already here."
            self.drop_msg_timer = 1500
            self.drop_mode = False
            return
        if pos in self.obstacles:
            self.drop_message = "Can't drop here."
            self.drop_msg_timer = 1500
            self.drop_mode = False
            return

        removed = self.game.party.inv_remove(item_name)
        if removed is None:
            self.drop_mode = False
            return

        self.ground_items[pos] = {"item": item_name, "gold": 0}
        self.drop_message = f"Dropped {item_name}."
        self.drop_msg_timer = 2000
        self.drop_mode = False
        self.game.sfx.play("chirp")
