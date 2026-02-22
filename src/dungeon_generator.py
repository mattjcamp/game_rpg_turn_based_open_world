"""
Procedural dungeon generator.

Uses a rooms-and-corridors algorithm:
1. Start with a grid of solid stone wall
2. Carve out rectangular rooms at random positions
3. Connect each room to the next with L-shaped corridors
4. Place the entrance stairs in the first room
5. Scatter treasure chests and traps in later rooms

Each call to generate_dungeon() produces a fresh layout.
"""

import random

from src.tile_map import TileMap
from src.settings import (
    TILE_DFLOOR, TILE_DWALL, TILE_STAIRS, TILE_CHEST, TILE_TRAP,
)
from src.monster import create_random_monster


class Room:
    """A rectangular room in the dungeon."""

    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    @property
    def center(self):
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def x2(self):
        return self.x + self.w

    @property
    def y2(self):
        return self.y + self.h

    def intersects(self, other, padding=1):
        """Check if this room overlaps another (with padding)."""
        return (
            self.x - padding < other.x2 + padding and
            self.x2 + padding > other.x - padding and
            self.y - padding < other.y2 + padding and
            self.y2 + padding > other.y - padding
        )


class DungeonData:
    """Holds everything about a generated dungeon."""

    def __init__(self, tile_map, rooms, entry_col, entry_row, name="The Depths",
                 monsters=None):
        self.tile_map = tile_map
        self.rooms = rooms
        self.entry_col = entry_col
        self.entry_row = entry_row
        self.name = name
        # Track which chests have been opened (keyed by (col, row))
        self.opened_chests = set()
        # Track which traps have been triggered
        self.triggered_traps = set()
        # Monsters placed in the dungeon
        self.monsters = monsters or []


def _carve_room(tmap, room):
    """Carve a room out of solid wall, filling it with floor."""
    for row in range(room.y, room.y2):
        for col in range(room.x, room.x2):
            tmap.set_tile(col, row, TILE_DFLOOR)


def _carve_h_tunnel(tmap, x1, x2, y):
    """Carve a horizontal tunnel."""
    for col in range(min(x1, x2), max(x1, x2) + 1):
        tmap.set_tile(col, y, TILE_DFLOOR)


def _carve_v_tunnel(tmap, y1, y2, x):
    """Carve a vertical tunnel."""
    for row in range(min(y1, y2), max(y1, y2) + 1):
        tmap.set_tile(x, row, TILE_DFLOOR)


def _connect_rooms(tmap, room_a, room_b):
    """Connect two rooms with an L-shaped corridor."""
    ax, ay = room_a.center
    bx, by = room_b.center

    # Randomly choose horizontal-first or vertical-first
    if random.random() < 0.5:
        _carve_h_tunnel(tmap, ax, bx, ay)
        _carve_v_tunnel(tmap, ay, by, bx)
    else:
        _carve_v_tunnel(tmap, ay, by, ax)
        _carve_h_tunnel(tmap, ax, bx, by)


def generate_dungeon(name="The Depths", width=40, height=30,
                     min_rooms=6, max_rooms=10,
                     room_min_size=4, room_max_size=8,
                     seed=None):
    """
    Generate a procedural dungeon.

    Args:
        name: Display name for the dungeon
        width: Map width in tiles
        height: Map height in tiles
        min_rooms: Minimum number of rooms to place
        max_rooms: Maximum number of rooms to attempt
        room_min_size: Minimum room dimension (width or height)
        room_max_size: Maximum room dimension
        seed: Optional random seed for reproducibility

    Returns:
        DungeonData with the generated map and metadata.
    """
    if seed is not None:
        random.seed(seed)

    # Pad the map with extra rows for HUD visibility (same trick as town)
    BUFFER = 3
    total_height = height + BUFFER

    tmap = TileMap(width, total_height, default_tile=TILE_DWALL)

    rooms = []
    num_rooms = random.randint(min_rooms, max_rooms)
    attempts = 0
    max_attempts = num_rooms * 20

    while len(rooms) < num_rooms and attempts < max_attempts:
        attempts += 1

        # Random room dimensions and position (keep 1-tile border)
        w = random.randint(room_min_size, room_max_size)
        h = random.randint(room_min_size, room_max_size)
        x = random.randint(1, width - w - 1)
        y = random.randint(1, height - h - 1)

        new_room = Room(x, y, w, h)

        # Check for overlap with existing rooms
        overlap = False
        for other in rooms:
            if new_room.intersects(other, padding=1):
                overlap = True
                break

        if not overlap:
            _carve_room(tmap, new_room)

            # Connect to previous room
            if rooms:
                _connect_rooms(tmap, rooms[-1], new_room)

            rooms.append(new_room)

    # --- Place stairs (entrance) in the first room ---
    stairs_col, stairs_row = rooms[0].center
    tmap.set_tile(stairs_col, stairs_row, TILE_STAIRS)

    # --- Place chests in some of the later rooms ---
    for room in rooms[2:]:  # Skip first two rooms (too close to entrance)
        if random.random() < 0.6:  # 60% chance of a chest
            # Place chest in a corner of the room
            cx = room.x + random.choice([1, room.w - 2])
            cy = room.y + random.choice([1, room.h - 2])
            # Make sure it's on floor
            if tmap.get_tile(cx, cy) == TILE_DFLOOR:
                tmap.set_tile(cx, cy, TILE_CHEST)

    # --- Place traps in corridors and some rooms ---
    for room in rooms[1:]:
        if random.random() < 0.35:  # 35% chance of a trap
            # Place near the entrance of the room
            tx, ty = room.center
            # Offset slightly from center
            tx += random.randint(-1, 1)
            ty += random.randint(-1, 1)
            if tmap.get_tile(tx, ty) == TILE_DFLOOR:
                tmap.set_tile(tx, ty, TILE_TRAP)

    # --- Place monsters in rooms (not the entrance room) ---
    monsters = []
    for room in rooms[1:]:
        if random.random() < 0.5:  # 50% chance of a monster per room
            # Place near center of the room
            mx, my = room.center
            # Offset slightly so monsters aren't all dead-center
            mx += random.randint(-1, 1)
            my += random.randint(-1, 1)
            # Make sure we're on a floor tile (not a chest/trap/stairs)
            if tmap.get_tile(mx, my) == TILE_DFLOOR:
                monster = create_random_monster()
                monster.col = mx
                monster.row = my
                monsters.append(monster)

    # Entry point is on the stairs
    entry_col = stairs_col
    entry_row = stairs_row

    return DungeonData(tmap, rooms, entry_col, entry_row, name,
                       monsters=monsters)
