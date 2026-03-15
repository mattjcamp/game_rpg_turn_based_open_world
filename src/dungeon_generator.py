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
    """Place doors flush against walls where corridors enter rooms.

    Scans the one-tile-thick wall ring just *outside* each room.  A
    wall-ring tile becomes a door if:

    1. A corridor has carved it to floor.
    2. It has a cardinal neighbour inside the room (connects to interior).
    3. It has wall on both perpendicular sides (1-wide opening), giving
       the door a flush-against-the-wall appearance matching town doors.
    """
    PASSABLE = {TILE_DFLOOR, TILE_STAIRS, TILE_CHEST, TILE_TRAP,
                TILE_STAIRS_DOWN, TILE_ARTIFACT, TILE_PUDDLE, TILE_MOSS}

    # Pre-compute room interior tile sets
    all_room_tiles = set()
    room_tile_sets = []
    for room in rooms:
        tiles = set()
        for r in range(room.y, room.y2):
            for c in range(room.x, room.x2):
                tiles.add((c, r))
                all_room_tiles.add((c, r))
        room_tile_sets.append(tiles)

    for ri, room in enumerate(rooms):
        room_tiles = room_tile_sets[ri]

        # Build the wall ring: tiles just outside the room bounds
        wall_ring = []
        for c in range(room.x, room.x2):
            wall_ring.append((c, room.y - 1))   # north
            wall_ring.append((c, room.y2))       # south
        for r in range(room.y, room.y2):
            wall_ring.append((room.x - 1, r))   # west
            wall_ring.append((room.x2, r))       # east

        for wc, wr in wall_ring:
            tile = tmap.get_tile(wc, wr)
            if tile not in PASSABLE:
                continue  # still solid wall — no corridor here
            if (wc, wr) in all_room_tiles:
                continue  # inside another room, not a doorway

            # Must connect to this room's interior
            connects = False
            for dc, dr in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                if (wc + dc, wr + dr) in room_tiles:
                    connects = True
                    break
            if not connects:
                continue

            # Must have wall on both perpendicular sides (1-wide opening)
            h_walls = (tmap.get_tile(wc - 1, wr) == TILE_DWALL and
                       tmap.get_tile(wc + 1, wr) == TILE_DWALL)
            v_walls = (tmap.get_tile(wc, wr - 1) == TILE_DWALL and
                       tmap.get_tile(wc, wr + 1) == TILE_DWALL)

            if h_walls or v_walls:
                tmap.set_tile(wc, wr, TILE_DDOOR)


def _place_locked_doors(tmap, rooms):
    """Replace the single door of single-entrance rooms with a locked door.

    Must be called *after* ``_place_doors`` so that regular doors already
    sit on the wall ring.  For each room (except the entrance room),
    scan the wall ring for ``TILE_DDOOR`` tiles.  If there is exactly one,
    upgrade it to ``TILE_LOCKED_DOOR``.
    """
    for ri, room in enumerate(rooms):
        if ri == 0:
            continue  # don't lock the entrance room

        # Scan the wall ring for doors placed by _place_doors
        wall_ring = []
        for c in range(room.x, room.x2):
            wall_ring.append((c, room.y - 1))
            wall_ring.append((c, room.y2))
        for r in range(room.y, room.y2):
            wall_ring.append((room.x - 1, r))
            wall_ring.append((room.x2, r))

        doors = [(wc, wr) for wc, wr in wall_ring
                 if tmap.get_tile(wc, wr) == TILE_DDOOR]

        if len(doors) == 1:
            dc, dr = doors[0]
            tmap.set_tile(dc, dr, TILE_LOCKED_DOOR)


def _place_decorations(tmap, rooms, width, height, torch_density="medium"):
    """Sprinkle cosmetic decorations: puddles, moss, and wall torches.

    Parameters
    ----------
    torch_density : str
        ``"high"`` — well-lit; torches on most walls, party rarely
        needs light spells.  ``"medium"`` — moderate lighting (default).
        ``"low"`` — a few torches here and there, mostly dark.
    """

    # --- Torch density parameters ---
    # min_spacing: minimum Manhattan distance between torches
    # max_torches: cap as a multiplier of room count
    if torch_density == "high":
        min_spacing = 2
        max_multiplier = 5  # up to 5 per room
    elif torch_density == "low":
        min_spacing = 8
        max_multiplier = 0.5  # roughly 1 per 2 rooms
    else:  # medium (default)
        min_spacing = 4
        max_multiplier = 2  # up to 2 per room

    max_torches = max(1, int(len(rooms) * max_multiplier))

    # --- Wall torches: place on wall tiles that border a floor tile ---
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

    # Also add corridor wall candidates for high density
    if torch_density == "high":
        for y in range(height):
            for x in range(width):
                if tmap.get_tile(x, y) == TILE_DWALL and (x, y) not in torch_candidates:
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            if tmap.get_tile(nx, ny) == TILE_DFLOOR:
                                torch_candidates.append((x, y))
                                break

    # Deduplicate and space them out
    seen = set()
    unique_candidates = []
    for pos in torch_candidates:
        if pos not in seen:
            seen.add(pos)
            unique_candidates.append(pos)
    random.shuffle(unique_candidates)

    placed_torches = []
    for tc, tr in unique_candidates:
        too_close = False
        for ptc, ptr in placed_torches:
            if abs(tc - ptc) + abs(tr - ptr) < min_spacing:
                too_close = True
                break
        if too_close:
            continue
        # Don't place a torch adjacent to a door — it would break the
        # visual "flush against wall" appearance of the door.
        adjacent_door = False
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nt = tmap.get_tile(tc + dx, tr + dy)
            if nt in (TILE_DDOOR, TILE_LOCKED_DOOR):
                adjacent_door = True
                break
        if adjacent_door:
            continue
        tmap.set_tile(tc, tr, TILE_WALL_TORCH)
        placed_torches.append((tc, tr))
        if len(placed_torches) >= max_torches:
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
                     encounter_max_level=None,
                     custom_encounters=None,
                     include_random_encounters=True,
                     torch_density="medium"):
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
        custom_encounters: Optional list of encounter dicts.  New format:
            ``{"monsters": ["Orc", "Skeleton", ...]}``.  Legacy format
            ``{"monster": str, "count": int}`` is also supported.
            When provided, these specific encounters are placed in the
            dungeon instead of randomly-rolled encounters.
        include_random_encounters: If True (default), random encounters
            are generated for rooms not already occupied by custom
            encounters.  When custom_encounters is provided and this is
            False, only the custom encounters appear.

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
    # Track which rooms already have a custom encounter placed
    used_rooms = set()

    if custom_encounters:
        # ── Module-defined encounters: place specific monsters ──
        available_rooms = list(rooms[1:])  # skip entrance
        random.shuffle(available_rooms)
        for ei, enc_spec in enumerate(custom_encounters):
            if ei >= len(available_rooms):
                break  # more encounters than rooms — stop
            room = available_rooms[ei]
            used_rooms.add(id(room))
            mx, my = room.center
            mx += random.randint(-1, 1)
            my += random.randint(-1, 1)
            if tmap.get_tile(mx, my) != TILE_DFLOOR:
                mx, my = room.center  # fallback to exact center
            # Support both new {"monsters": [...]} and legacy {"monster", "count"}
            if "monsters" in enc_spec:
                mon_names = list(enc_spec["monsters"])
            else:
                mn = enc_spec.get("monster", "Giant Rat")
                mc = max(1, int(enc_spec.get("count", 1)))
                mon_names = [mn] * mc
            lead_name = mon_names[0] if mon_names else "Giant Rat"
            monster = create_monster(lead_name)
            monster.col = mx
            monster.row = my
            monster.encounter_template = {
                "name": f"Custom ({len(mon_names)})",
                "monster_names": mon_names,
                "monster_party_tile": lead_name,
            }
            monsters.append(monster)

    if include_random_encounters:
        # ── Random encounters from encounters.json ──
        # Skip entrance room and any rooms already used by custom encounters
        for room in rooms[1:]:
            if id(room) in used_rooms:
                continue
            if random.random() < 0.5:  # 50% chance per room
                mx, my = room.center
                mx += random.randint(-1, 1)
                my += random.randint(-1, 1)
                if tmap.get_tile(mx, my) == TILE_DFLOOR:
                    enc = create_encounter(encounter_area,
                                           min_level=encounter_min_level,
                                           max_level=encounter_max_level)
                    monster = create_monster(enc["monster_party_tile"])
                    monster.col = mx
                    monster.row = my
                    monster.encounter_template = {
                        "name": enc["name"],
                        "monster_names": [
                            m.name for m in enc["monsters"]],
                        "monster_party_tile": enc[
                            "monster_party_tile"],
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

    # --- Place doors flush against walls where corridors enter rooms ---
    _place_doors(tmap, rooms)

    # --- Upgrade single-entrance rooms to locked doors ---
    _place_locked_doors(tmap, rooms)

    # --- Place cosmetic decorations (puddles, moss, wall torches) ---
    _place_decorations(tmap, rooms, width, total_height,
                       torch_density=torch_density)

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


def generate_innkeeper_quest_dungeon(name="Shadow Dungeon", num_floors=None,
                                     place_artifact=True,
                                     kill_target=None, kill_count=0,
                                     torch_density="medium",
                                     dungeon_size="medium"):
    """Generate a random multi-level dungeon for an innkeeper quest.

    Parameters
    ----------
    name : str
        Display name for the dungeon.
    num_floors : int or None
        Number of floors (1–4).  If None, chosen randomly.
    place_artifact : bool
        Whether to place a quest artifact on the deepest floor.
    kill_target : str or None
        For kill quests, the monster name the player must defeat.
        When given, enough of this creature are placed across the
        dungeon floors to satisfy *kill_count*.
    kill_count : int
        Minimum number of *kill_target* creatures required across
        all floors.

    Returns
    -------
    list of DungeonData
    """
    if num_floors is None:
        num_floors = random.randint(1, 4)
    num_floors = max(1, min(4, num_floors))

    # For kill quests, distribute guaranteed encounters across floors
    # so the player can always reach the required kill count.
    floor_kill_encounters = [[] for _ in range(num_floors)]
    if kill_target and kill_count > 0:
        # Spread targets evenly across floors, at least 1 per floor
        remaining = kill_count
        for f in range(num_floors):
            # Give each floor a fair share, heavier on later floors
            floors_left = num_floors - f
            share = max(1, (remaining + floors_left - 1) // floors_left)
            share = min(share, remaining)
            if share > 0:
                floor_kill_encounters[f].append({
                    "monsters": [kill_target] * share,
                })
                remaining -= share
            if remaining <= 0:
                break

    base_w, base_h = _DUNGEON_SIZE_SCALES.get(dungeon_size, (28, 22))
    cap_w, cap_h = _DUNGEON_SIZE_CAPS.get(dungeon_size, (40, 30))

    levels = []
    for floor in range(num_floors):
        is_last = (floor == num_floors - 1)
        enc_level = floor + 1
        w = min(cap_w, base_w + floor * 2)
        h = min(cap_h, base_h + floor * 2)
        custom_enc = floor_kill_encounters[floor] or None
        # Scale room counts with dungeon size
        room_offset = {"small": -1, "medium": 0, "large": 2}.get(
            dungeon_size, 0)
        level = generate_dungeon(
            name=f"{name} - Level {floor + 1}",
            width=w, height=h,
            min_rooms=max(3, 4 + floor + room_offset),
            max_rooms=max(4, 6 + floor + room_offset),
            place_stairs_down=not is_last,
            place_artifact=(is_last and place_artifact),
            place_doors=False,
            encounter_area="dungeon",
            encounter_min_level=enc_level,
            encounter_max_level=enc_level,
            custom_encounters=custom_enc,
            torch_density=torch_density,
        )
        levels.append(level)
    return levels


_DUNGEON_SIZE_SCALES = {
    "small":  (20, 16),   # base width, base height
    "medium": (28, 22),
    "large":  (36, 28),
}
_DUNGEON_SIZE_CAPS = {
    "small":  (28, 22),   # max width, max height
    "medium": (40, 30),
    "large":  (52, 38),
}


def generate_keys_dungeon(dungeon_number, name=None, place_artifact=True,
                          module_levels=None,
                          kill_target=None, kill_count=0,
                          torch_density="medium",
                          dungeon_size="medium"):
    """Generate a progressive dungeon for a module.

    When *module_levels* is provided (from the module editor), the floor
    count and encounter placement follow those specifications.  Otherwise
    the dungeon is generated procedurally: dungeon N has N floors, with
    floor K having encounters at difficulty level K+1.

    Parameters
    ----------
    dungeon_number : int
        Which dungeon (1-8). Determines default floor count and scaling.
    name : str or None
        Display name. Defaults to "Dungeon of Key N".
    place_artifact : bool
        Whether to place a quest artifact on the deepest floor (default True).
    module_levels : list or None
        Optional list of level dicts from the module manifest, each with
        ``"name"`` and ``"encounters"`` (list of ``{"monsters": [...]}``,
        or legacy ``{"monster", "count"}``).  When provided, overrides
        the default floor count and encounter generation.
    dungeon_size : str
        "small", "medium", or "large". Controls the base floor area.

    Returns
    -------
    list of DungeonData
        One entry per floor, [floor_0, floor_1, ..., floor_(N-1)].
    """
    if name is None:
        name = f"Dungeon of Key {dungeon_number}"

    # Use module-defined floors if available, otherwise default to
    # dungeon_number floors with procedural encounters.
    if module_levels:
        num_floors = max(1, len(module_levels))
    else:
        num_floors = dungeon_number

    # For kill quests, distribute guaranteed encounters across floors
    floor_kill_encounters = [[] for _ in range(num_floors)]
    if kill_target and kill_count > 0:
        remaining = kill_count
        for f in range(num_floors):
            floors_left = num_floors - f
            share = max(1, (remaining + floors_left - 1) // floors_left)
            share = min(share, remaining)
            if share > 0:
                floor_kill_encounters[f].append({
                    "monsters": [kill_target] * share,
                })
                remaining -= share
            if remaining <= 0:
                break

    base_w, base_h = _DUNGEON_SIZE_SCALES.get(dungeon_size, (28, 22))
    cap_w, cap_h = _DUNGEON_SIZE_CAPS.get(dungeon_size, (40, 30))
    room_offset = {"small": -1, "medium": 0, "large": 2}.get(
        dungeon_size, 0)

    # Default for random_encounters at the dungeon level (True unless
    # explicitly set to False in module data).
    dung_random = True

    levels = []

    for floor in range(num_floors):
        is_last = (floor == num_floors - 1)
        enc_level = floor + 1

        # Per-floor defaults (may be overridden by module_levels)
        floor_torch = torch_density
        floor_size = dungeon_size
        floor_random = dung_random

        if module_levels and floor < len(module_levels):
            ml = module_levels[floor]
            floor_name = ml.get("name", f"Floor {floor + 1}")
            custom_enc = ml.get("encounters")
            if not custom_enc or not isinstance(custom_enc, list):
                custom_enc = None

            # Resolve inheritable settings — "inherit" or missing
            # falls back to the dungeon-level default.
            ft = ml.get("torch_density", "inherit")
            floor_torch = torch_density if ft == "inherit" else ft

            fs = ml.get("size", "inherit")
            floor_size = dungeon_size if fs == "inherit" else fs

            fr = ml.get("random_encounters", "inherit")
            if fr == "inherit":
                floor_random = dung_random
            else:
                floor_random = bool(fr)

            include_random = floor_random
        else:
            floor_name = f"Floor {floor + 1}"
            custom_enc = None
            include_random = True

        # Compute dimensions from resolved floor size
        f_base_w, f_base_h = _DUNGEON_SIZE_SCALES.get(
            floor_size, (28, 22))
        f_cap_w, f_cap_h = _DUNGEON_SIZE_CAPS.get(
            floor_size, (40, 30))
        f_room_offset = {"small": -1, "medium": 0, "large": 2}.get(
            floor_size, 0)

        w = min(f_cap_w, f_base_w + floor * 2)
        h = min(f_cap_h, f_base_h + floor * 2)
        min_r = max(3, 4 + floor + f_room_offset)
        max_r = max(4, 6 + floor + f_room_offset)

        # Merge kill-quest guaranteed encounters with any custom ones
        kill_enc = floor_kill_encounters[floor]
        if kill_enc:
            custom_enc = list(custom_enc or []) + kill_enc

        level_data = generate_dungeon(
            name=f"{name} - {floor_name}",
            width=w, height=h,
            min_rooms=min_r, max_rooms=max_r,
            place_stairs_down=not is_last,
            place_artifact=(is_last and place_artifact),
            place_doors=False,
            encounter_area="dungeon",
            encounter_min_level=enc_level,
            encounter_max_level=enc_level,
            custom_encounters=custom_enc,
            include_random_encounters=include_random,
            torch_density=floor_torch,
        )
        levels.append(level_data)

    return levels
