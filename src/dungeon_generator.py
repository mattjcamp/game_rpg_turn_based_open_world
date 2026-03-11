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
    TILE_STAIRS_DOWN, TILE_DDOOR, TILE_ARTIFACT, TILE_LOCKED_DOOR,
    TILE_PUDDLE, TILE_MOSS, TILE_WALL_TORCH,
)
from src.monster import create_random_monster, create_encounter, create_monster


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
        # Track which traps have been detected by the thief
        self.detected_traps = set()
        # Monsters placed in the dungeon
        self.monsters = monsters or []
        # Fog of war: tiles the party has ever seen
        self.explored_tiles = set()

    # ── Serialization ────────────────────────────────────────────

    def to_dict(self):
        """Serialize this dungeon to a JSON-safe dict.

        Captures the full tile grid, explored tiles, chest/trap state,
        and monster positions + HP so dungeons persist across visits
        and save/load.
        """
        # Serialize tile map as a flat 2D list of tile IDs
        tiles_2d = []
        for r in range(self.tile_map.height):
            row_data = []
            for c in range(self.tile_map.width):
                row_data.append(self.tile_map.get_tile(c, r))
            tiles_2d.append(row_data)

        # Serialize monsters (position, HP, and encounter template)
        monsters_data = []
        for m in self.monsters:
            monsters_data.append({
                "col": m.col,
                "row": m.row,
                "hp": m.hp,
                "max_hp": m.max_hp,
                "name": m.name,
                "encounter_template": getattr(m, "encounter_template", None),
            })

        return {
            "name": self.name,
            "width": self.tile_map.width,
            "height": self.tile_map.height,
            "tiles": tiles_2d,
            "entry_col": self.entry_col,
            "entry_row": self.entry_row,
            "opened_chests": [list(pos) for pos in self.opened_chests],
            "triggered_traps": [list(pos) for pos in self.triggered_traps],
            "detected_traps": [list(pos) for pos in self.detected_traps],
            "explored_tiles": [list(pos) for pos in self.explored_tiles],
            "monsters": monsters_data,
        }

    @classmethod
    def from_dict(cls, data):
        """Reconstruct a DungeonData from a serialized dict."""
        from src.tile_map import TileMap
        from src.monster import create_monster

        width = data["width"]
        height = data["height"]
        tmap = TileMap(width, height, default_tile=0)
        # Restore tile grid
        for r, row_data in enumerate(data["tiles"]):
            for c, tile_id in enumerate(row_data):
                tmap.set_tile(c, r, tile_id)

        # Restore monsters
        monsters = []
        for md in data.get("monsters", []):
            try:
                m = create_monster(md["name"])
            except (ValueError, KeyError):
                continue
            m.col = md["col"]
            m.row = md["row"]
            m.hp = md["hp"]
            m.max_hp = md["max_hp"]
            if md.get("encounter_template"):
                m.encounter_template = md["encounter_template"]
            monsters.append(m)

        # We don't need to restore rooms — they're only used during
        # generation.  Pass an empty list.
        dd = cls(tmap, [], data["entry_col"], data["entry_row"],
                 name=data.get("name", "The Depths"), monsters=monsters)
        dd.opened_chests = {tuple(p) for p in data.get("opened_chests", [])}
        dd.triggered_traps = {tuple(p) for p in data.get("triggered_traps", [])}
        dd.detected_traps = {tuple(p) for p in data.get("detected_traps", [])}
        dd.explored_tiles = {tuple(p) for p in data.get("explored_tiles", [])}
        return dd


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


def _place_locked_doors(tmap, rooms):
    """Place locked doors on rooms that have exactly one tile-wide entrance.

    A room entrance is a perimeter tile that is floor/door and has a cardinal
    neighbour outside the room that is also floor/door (i.e. corridor).
    If there is exactly one such entrance tile, replace it with a locked door.
    Skip the first room (entrance room with stairs).
    """
    PASSABLE = {TILE_DFLOOR, TILE_DDOOR, TILE_STAIRS, TILE_CHEST,
                TILE_TRAP, TILE_STAIRS_DOWN, TILE_ARTIFACT,
                TILE_PUDDLE, TILE_MOSS}

    # Build set of tiles belonging to each room
    room_tile_sets = []
    for room in rooms:
        tiles = set()
        for r in range(room.y, room.y2):
            for c in range(room.x, room.x2):
                tiles.add((c, r))
        room_tile_sets.append(tiles)

    all_room_tiles = set()
    for s in room_tile_sets:
        all_room_tiles |= s

    for ri, room in enumerate(rooms):
        if ri == 0:
            continue  # don't lock the entrance room

        room_tiles = room_tile_sets[ri]

        # Find perimeter tiles
        perimeter = set()
        for c in range(room.x, room.x2):
            perimeter.add((c, room.y))
            perimeter.add((c, room.y2 - 1))
        for r in range(room.y, room.y2):
            perimeter.add((room.x, r))
            perimeter.add((room.x2 - 1, r))

        # Find entrance tiles: perimeter floor/door tiles with an outside
        # cardinal neighbour that is also passable
        entrances = []
        for (pc, pr) in perimeter:
            tid = tmap.get_tile(pc, pr)
            if tid not in PASSABLE and tid != TILE_DDOOR:
                continue
            for dc, dr in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nc, nr = pc + dc, pr + dr
                if (nc, nr) in room_tiles:
                    continue  # neighbour is inside the room
                if tmap.get_tile(nc, nr) in PASSABLE or tmap.get_tile(nc, nr) == TILE_DDOOR:
                    entrances.append((pc, pr))
                    break

        if len(entrances) == 1:
            ec, er = entrances[0]
            tmap.set_tile(ec, er, TILE_LOCKED_DOOR)


def _place_decorations(tmap, rooms, width, height):
    """Sprinkle cosmetic decorations: puddles, moss, and wall torches."""

    # --- Wall torches: place on wall tiles that border a floor tile ---
    # Torches are spaced out so they don't cluster; aim for ~1 per room.
    torch_candidates = []
    for room in rooms:
        # Check wall tiles along room edges
        for x in range(room.x - 1, room.x + room.w + 1):
            for y in [room.y - 1, room.y + room.h]:
                if 0 <= x < width and 0 <= y < height:
                    if tmap.get_tile(x, y) == TILE_DWALL:
                        # Must have a floor neighbor (so the light has
                        # somewhere to shine)
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = x + dx, y + dy
                            if tmap.get_tile(nx, ny) == TILE_DFLOOR:
                                torch_candidates.append((x, y))
                                break
        for y in range(room.y - 1, room.y + room.h + 1):
            for x in [room.x - 1, room.x + room.w]:
                if 0 <= x < width and 0 <= y < height:
                    if tmap.get_tile(x, y) == TILE_DWALL:
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = x + dx, y + dy
                            if tmap.get_tile(nx, ny) == TILE_DFLOOR:
                                torch_candidates.append((x, y))
                                break

    # Deduplicate and space them out (min 4 tiles apart)
    random.shuffle(torch_candidates)
    placed_torches = []
    for tc, tr in torch_candidates:
        too_close = False
        for ptc, ptr in placed_torches:
            if abs(tc - ptc) + abs(tr - ptr) < 4:
                too_close = True
                break
        if not too_close:
            tmap.set_tile(tc, tr, TILE_WALL_TORCH)
            placed_torches.append((tc, tr))
            # Limit to roughly 1-2 per room
            if len(placed_torches) >= len(rooms) * 2:
                break

    # --- Puddles: small water patches on floor tiles ---
    # Prefer tiles away from room centers, near corridors
    floor_tiles = []
    for y in range(height):
        for x in range(width):
            if tmap.get_tile(x, y) == TILE_DFLOOR:
                floor_tiles.append((x, y))
    num_puddles = max(2, len(rooms) // 2)
    random.shuffle(floor_tiles)
    puddles_placed = 0
    for fx, fy in floor_tiles:
        if puddles_placed >= num_puddles:
            break
        # Prefer tiles that have at least 2 wall neighbors (corners, corridors)
        wall_count = sum(
            1 for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if tmap.get_tile(fx + dx, fy + dy) == TILE_DWALL
        )
        if wall_count >= 1 and random.random() < 0.4:
            tmap.set_tile(fx, fy, TILE_PUDDLE)
            puddles_placed += 1

    # --- Moss: grows on floor tiles adjacent to walls ---
    num_moss = max(3, len(rooms))
    random.shuffle(floor_tiles)
    moss_placed = 0
    for fx, fy in floor_tiles:
        if moss_placed >= num_moss:
            break
        if tmap.get_tile(fx, fy) != TILE_DFLOOR:
            continue  # may have been turned into puddle
        wall_count = sum(
            1 for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if tmap.get_tile(fx + dx, fy + dy) in (TILE_DWALL, TILE_WALL_TORCH)
        )
        if wall_count >= 1 and random.random() < 0.35:
            tmap.set_tile(fx, fy, TILE_MOSS)
            moss_placed += 1


def generate_dungeon(name="The Depths", width=40, height=30,
                     min_rooms=6, max_rooms=10,
                     room_min_size=4, room_max_size=8,
                     seed=None,
                     place_stairs_down=False, place_artifact=False,
                     place_doors=False,
                     encounter_area="dungeon",
                     encounter_min_level=None,
                     encounter_max_level=None):
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
    # Each map monster represents an encounter group. We pre-roll the
    # encounter template and use monster_party_tile for the map sprite.
    # The full encounter data is stored on the monster so combat can
    # use it instead of rolling a new random encounter.
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
                enc = create_encounter(encounter_area,
                                       min_level=encounter_min_level,
                                       max_level=encounter_max_level)
                # Create the map-visible monster using the party tile
                monster = create_monster(enc["monster_party_tile"])
                monster.col = mx
                monster.row = my
                # Stash encounter template (names only) so combat can
                # recreate fresh monsters with full HP each fight
                monster.encounter_template = {
                    "name": enc["name"],
                    "monster_names": [m.name for m in enc["monsters"]],
                    "monster_party_tile": enc["monster_party_tile"],
                }
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

    # --- Place locked doors on rooms with single-tile entrances ---
    _place_locked_doors(tmap, rooms)

    # --- Place cosmetic decorations (puddles, moss, wall torches) ---
    _place_decorations(tmap, rooms, width, total_height)

    # Entry point is on the stairs
    entry_col = stairs_col
    entry_row = stairs_row

    return DungeonData(tmap, rooms, entry_col, entry_row, name,
                       monsters=monsters)


def generate_house_dungeon(name="Elara's House"):
    """Generate a two-level house dungeon (ground floor + basement).

    Level 0 (Ground Floor): a small house with a few rooms and stairs
        down to the basement. Easy monsters (rats, goblins).
    Level 1 (Basement): a cramped cellar with the family heirloom
        in the deepest room.

    Returns:
        A list [level_0_data, level_1_data] of DungeonData objects.
    """
    level_0 = generate_dungeon(
        name=f"{name} - Ground Floor",
        width=24, height=18,
        min_rooms=4, max_rooms=5,
        room_min_size=3, room_max_size=5,
        place_stairs_down=True,
        place_doors=False,
        encounter_area="house_basement",
    )
    level_1 = generate_dungeon(
        name=f"{name} - Basement",
        width=20, height=15,
        min_rooms=3, max_rooms=4,
        room_min_size=3, room_max_size=5,
        place_artifact=True,
        place_doors=False,
        encounter_area="house_basement",
    )
    return [level_0, level_1]


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
        place_doors=False,
    )
    level_1 = generate_dungeon(
        name=f"{name} - Level 2",
        place_artifact=True,
        place_doors=False,
    )
    return [level_0, level_1]


def generate_keys_dungeon(dungeon_number, name=None, place_artifact=True):
    """Generate a progressive dungeon for the Keys of Shadow module.

    Dungeon N has N floors. Floor K (0-indexed) has encounters at level K+1.
    The artifact (key) is on the deepest floor (unless *place_artifact* is
    False, e.g. for kill-type quests where the portal spawns on kill count).

    Parameters
    ----------
    dungeon_number : int
        Which dungeon (1-8). Determines number of floors and max difficulty.
    name : str or None
        Display name. Defaults to "Dungeon of Key N".
    place_artifact : bool
        Whether to place a quest artifact on the deepest floor (default True).

    Returns
    -------
    list of DungeonData
        One entry per floor, [floor_0, floor_1, ..., floor_(N-1)].
    """
    if name is None:
        name = f"Dungeon of Key {dungeon_number}"

    num_floors = dungeon_number
    levels = []

    for floor in range(num_floors):
        is_last = (floor == num_floors - 1)
        enc_level = floor + 1  # floor 0 → level 1, floor 1 → level 2, etc.

        # Dungeons get slightly bigger with depth
        w = min(40, 28 + floor * 2)
        h = min(30, 22 + floor * 2)
        min_r = min(8, 4 + floor)
        max_r = min(12, 6 + floor)

        level_data = generate_dungeon(
            name=f"{name} - Floor {floor + 1}",
            width=w, height=h,
            min_rooms=min_r, max_rooms=max_r,
            place_stairs_down=not is_last,
            place_artifact=(is_last and place_artifact),
            place_doors=False,
            encounter_area="dungeon",
            encounter_min_level=enc_level,
            encounter_max_level=enc_level,
        )
        levels.append(level_data)

    return levels
