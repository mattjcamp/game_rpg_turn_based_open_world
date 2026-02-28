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
    TILE_STAIRS_DOWN, TILE_DDOOR, TILE_ARTIFACT,
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


def _place_doors(tmap, rooms):
    """Place doors where corridors meet room edges.

    Scans the perimeter of each room.  A perimeter tile gets a door if it
    is a floor tile and at least one of its cardinal neighbours is also a
    floor tile that lies *outside* every room (i.e. in a corridor).
    """
    # Build a set of all tiles that belong to a room interior
    room_tiles = set()
    for room in rooms:
        for r in range(room.y, room.y2):
            for c in range(room.x, room.x2):
                room_tiles.add((c, r))

    for room in rooms:
        # Walk the perimeter (the outermost ring of the room)
        perimeter = set()
        for c in range(room.x, room.x2):
            perimeter.add((c, room.y))
            perimeter.add((c, room.y2 - 1))
        for r in range(room.y, room.y2):
            perimeter.add((room.x, r))
            perimeter.add((room.x2 - 1, r))

        for (pc, pr) in perimeter:
            if tmap.get_tile(pc, pr) != TILE_DFLOOR:
                continue
            # Check cardinal neighbours outside the room
            for dc, dr in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nc, nr = pc + dc, pr + dr
                if (nc, nr) in room_tiles:
                    continue
                if tmap.get_tile(nc, nr) == TILE_DFLOOR:
                    tmap.set_tile(pc, pr, TILE_DDOOR)
                    break  # one door per perimeter tile


def generate_dungeon(name="The Depths", width=40, height=30,
                     min_rooms=6, max_rooms=10,
                     room_min_size=4, room_max_size=8,
                     seed=None,
                     place_stairs_down=False, place_artifact=False,
                     place_doors=False):
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
        place_stairs_down: If True, place stairs-down in the last room
        place_artifact: If True, place the quest artifact in the last room
        place_doors: If True, place doors at room/corridor junctions

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

    # --- Optional: place stairs down in the last (deepest) room ---
    if place_stairs_down and len(rooms) >= 2:
        last_room = rooms[-1]
        sc, sr = last_room.center
        tmap.set_tile(sc, sr, TILE_STAIRS_DOWN)

    # --- Optional: place quest artifact in the last room ---
    if place_artifact and len(rooms) >= 2:
        last_room = rooms[-1]
        ac, ar = last_room.center
        tmap.set_tile(ac, ar, TILE_ARTIFACT)

    # --- Optional: place doors at corridor/room junctions ---
    if place_doors:
        _place_doors(tmap, rooms)

    # Entry point is on the stairs
    entry_col = stairs_col
    entry_row = stairs_row

    return DungeonData(tmap, rooms, entry_col, entry_row, name,
                       monsters=monsters)


def generate_quest_dungeon(name="Shadow Dungeon"):
    """Generate a two-level quest dungeon with doors and an artifact.

    Level 0: standard dungeon with stairs down in the deepest room.
    Level 1: deeper dungeon with the quest artifact in the deepest room.
    Both levels have doors at room/corridor junctions.

    Returns:
        A list [level_0_data, level_1_data] of DungeonData objects.
    """
    level_0 = generate_dungeon(
        name=f"{name} - Level 1",
        place_stairs_down=True,
        place_doors=True,
    )
    level_1 = generate_dungeon(
        name=f"{name} - Level 2",
        place_artifact=True,
        place_doors=True,
    )
    return [level_0, level_1]
