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
    TILE_MOUNTAIN, TILE_PATH,
    TILE_FOREST, TILE_WATER, TILE_GRASS, TILE_SAND,
    TILE_FOREST_ARCHWAY_UP, TILE_FOREST_ARCHWAY_DOWN,
)
from src.monster import create_encounter, create_monster

# All tile IDs that count as "wall" for dungeon generation purposes
# (door placement, torch placement, decoration adjacency checks).
# Forest dungeons use trees/water as walls in addition to mountains —
# the door & decoration helpers treat any of these as solid blocking
# terrain regardless of dungeon style.
_WALL_TILES = frozenset({TILE_DWALL, TILE_MOUNTAIN,
                         TILE_FOREST, TILE_WATER})


# ── Debug switch: suppress random encounters in newly generated dungeons ──
# Quest-registered monsters (injected at runtime by
# states.dungeon._inject_quest_dungeon_monsters) and module-defined
# ``custom_encounters`` are unaffected — only the per-room random
# encounters in ``generate_dungeon`` are skipped when this is True.
# Toggled by the DM-mode-only "QUEST MONSTERS ONLY" Settings entry via
# ``Game._toggle_quest_monsters_only``; also re-applied at Game init
# from the persisted config.
_DEBUG_QUEST_MONSTERS_ONLY = False


def set_quest_monsters_only_debug(enabled):
    """Enable/disable the debug flag that suppresses random dungeon encounters.

    When enabled, calls to :func:`generate_dungeon` behave as if
    ``include_random_encounters=False`` was passed, regardless of the
    caller's argument. Custom/module encounters and quest monsters are
    unaffected.
    """
    global _DEBUG_QUEST_MONSTERS_ONLY
    _DEBUG_QUEST_MONSTERS_ONLY = bool(enabled)


def is_quest_monsters_only_debug():
    """Return whether the quest-monsters-only debug flag is active."""
    return _DEBUG_QUEST_MONSTERS_ONLY


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
                 monsters=None, style=None):
        self.tile_map = tile_map
        self.rooms = rooms
        self.entry_col = entry_col
        self.entry_row = entry_row
        self.name = name
        self.style = style  # "cave", "crypt", etc. — drives rendering palette
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
        # (col, row) positions of TILE_STAIRS tiles that, when ESC'd
        # from, exit the dungeon back to the overworld instead of
        # ascending one level. Used on the bottom level of procedural
        # multi-level dungeons so the party doesn't have to walk all
        # the way back to the top floor to leave.
        self.overworld_exits = set()

    @property
    def floor_tile(self):
        """Return the tile_id used for walkable floor in this dungeon.

        Per-style mapping:
        - ``"cave"``   → ``TILE_PATH``   (overworld cave look)
        - ``"forest"`` → ``TILE_GRASS``  (clearings between the trees)
        - everything else → ``TILE_DFLOOR`` (stone-block dungeon floor)

        Pickup code (chest, trap, artifact) reads this when restoring
        a tile after the feature is consumed, so the cell blends back
        into the surrounding floor regardless of dungeon style.  The
        renderer also uses it to disguise undetected traps.
        """
        if self.style == "cave":
            return TILE_PATH
        if self.style == "forest":
            return TILE_GRASS
        return TILE_DFLOOR

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

        # Serialize the cosmetic decoration overlay (puddles, moss,
        # torches).  Stored as a list of [col, row, tile_id] triples so
        # the JSON is human-readable and stable across versions.
        decorations_data = [
            [c, r, tid]
            for (c, r), tid in self.tile_map.decorations.items()
        ]

        # Serialize per-cell property overrides (walkability flips for
        # forest dungeons, etc.) so a saved-and-reloaded dungeon
        # still treats trees as walls.
        tile_props = getattr(self.tile_map, "tile_properties", None) or {}

        return {
            "name": self.name,
            "width": self.tile_map.width,
            "height": self.tile_map.height,
            "tiles": tiles_2d,
            "decorations": decorations_data,
            "tile_properties": dict(tile_props),
            "entry_col": self.entry_col,
            "entry_row": self.entry_row,
            "opened_chests": [list(pos) for pos in self.opened_chests],
            "triggered_traps": [list(pos) for pos in self.triggered_traps],
            "detected_traps": [list(pos) for pos in self.detected_traps],
            "explored_tiles": [list(pos) for pos in self.explored_tiles],
            "monsters": monsters_data,
            "style": self.style,
            "overworld_exits": [list(pos) for pos in self.overworld_exits],
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
        # Restore the decoration overlay (puddles, moss, torches).
        # Older saves predate this layer; fall back to an empty overlay.
        for entry in data.get("decorations", []):
            try:
                c, r, tid = entry
            except (TypeError, ValueError):
                continue
            tmap.set_decoration(c, r, tid)

        # Restore per-cell property overrides (walkability flips
        # for forest tree-walls, etc.).  Older saves don't have
        # this key — leaving tile_properties unset is fine.
        saved_props = data.get("tile_properties")
        if isinstance(saved_props, dict) and saved_props:
            tmap.tile_properties = dict(saved_props)

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
                 name=data.get("name", "The Depths"), monsters=monsters,
                 style=data.get("style"))
        dd.opened_chests = {tuple(p) for p in data.get("opened_chests", [])}
        dd.triggered_traps = {tuple(p) for p in data.get("triggered_traps", [])}
        dd.detected_traps = {tuple(p) for p in data.get("detected_traps", [])}
        dd.explored_tiles = {tuple(p) for p in data.get("explored_tiles", [])}
        dd.overworld_exits = {tuple(p) for p in data.get("overworld_exits", [])}
        return dd


def _carve_room(tmap, room, floor_tile=TILE_DFLOOR):
    """Carve a room out of solid wall, filling it with floor."""
    for row in range(room.y, room.y2):
        for col in range(room.x, room.x2):
            tmap.set_tile(col, row, floor_tile)


def _carve_h_tunnel(tmap, x1, x2, y, width=1, floor_tile=TILE_DFLOOR):
    """Carve a horizontal tunnel of the given *width* (centred on *y*)."""
    half = width // 2
    for col in range(min(x1, x2), max(x1, x2) + 1):
        for dy in range(-half, -half + width):
            r = y + dy
            if 1 <= r < tmap.height - 1:
                tmap.set_tile(col, r, floor_tile)


def _carve_v_tunnel(tmap, y1, y2, x, width=1, floor_tile=TILE_DFLOOR):
    """Carve a vertical tunnel of the given *width* (centred on *x*)."""
    half = width // 2
    for row in range(min(y1, y2), max(y1, y2) + 1):
        for dx in range(-half, -half + width):
            c = x + dx
            if 1 <= c < tmap.width - 1:
                tmap.set_tile(c, row, floor_tile)


def _connect_rooms(tmap, room_a, room_b, floor_tile=TILE_DFLOOR):
    """Connect two rooms with an L-shaped corridor.

    Tunnel width varies randomly: most corridors are 1 tile wide,
    some are 2, and occasionally 3 — giving the dungeon a more
    organic feel with narrow passages opening into wider stretches.
    """
    ax, ay = room_a.center
    bx, by = room_b.center

    # Pick a random width for each segment — weighted toward narrow
    w1 = random.choices([1, 2, 3], weights=[5, 3, 1])[0]
    w2 = random.choices([1, 2, 3], weights=[5, 3, 1])[0]

    # Randomly choose horizontal-first or vertical-first
    if random.random() < 0.5:
        _carve_h_tunnel(tmap, ax, bx, ay, width=w1, floor_tile=floor_tile)
        _carve_v_tunnel(tmap, ay, by, bx, width=w2, floor_tile=floor_tile)
    else:
        _carve_v_tunnel(tmap, ay, by, ax, width=w1, floor_tile=floor_tile)
        _carve_h_tunnel(tmap, ax, bx, by, width=w2, floor_tile=floor_tile)


def _place_doors(tmap, rooms, floor_tile=TILE_DFLOOR):
    """Place doors flush against walls where corridors enter rooms.

    Scans the one-tile-thick wall ring just *outside* each room.  A
    wall-ring tile becomes a door if:

    1. A corridor has carved it to floor.
    2. It has a cardinal neighbour inside the room (connects to interior).
    3. It has wall on both perpendicular sides (1-wide opening), giving
       the door a flush-against-the-wall appearance matching town doors.
    """
    # Note: puddles and moss live on the decoration overlay layer now,
    # so the underlying tile here is the floor tile — no need to list
    # them explicitly.
    PASSABLE = {floor_tile, TILE_STAIRS, TILE_CHEST, TILE_TRAP,
                TILE_STAIRS_DOWN, TILE_ARTIFACT,
                TILE_FOREST_ARCHWAY_UP, TILE_FOREST_ARCHWAY_DOWN}

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
            h_walls = (tmap.get_tile(wc - 1, wr) in _WALL_TILES and
                       tmap.get_tile(wc + 1, wr) in _WALL_TILES)
            v_walls = (tmap.get_tile(wc, wr - 1) in _WALL_TILES and
                       tmap.get_tile(wc, wr + 1) in _WALL_TILES)

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


def _fix_disconnected_locked_doors(tmap, rooms, stairs_col, stairs_row,
                                   floor_tile=TILE_DFLOOR):
    """Revert locked doors that disconnect rooms from the entrance.

    After doors and locked doors are placed, BFS from the stairs to find
    all reachable tiles (treating regular doors as walkable but locked
    doors as impassable).  Any room whose center is unreachable is
    blocked by a locked door.  For each such room, downgrade its locked
    door(s) back to regular (walkable) doors, then re-check until all
    rooms are reachable.
    """
    width = tmap.width
    height = tmap.height

    # Decorations (puddles/moss) sit on the overlay layer — the base
    # tile under them is the floor tile, which is already in this set.
    WALKABLE_FOR_CHECK = {floor_tile, TILE_STAIRS, TILE_CHEST, TILE_TRAP,
                          TILE_STAIRS_DOWN, TILE_ARTIFACT, TILE_DDOOR,
                          TILE_FOREST_ARCHWAY_UP, TILE_FOREST_ARCHWAY_DOWN}

    def bfs_reachable(start_c, start_r):
        visited = set()
        queue = [(start_c, start_r)]
        while queue:
            c, r = queue.pop(0)
            if (c, r) in visited:
                continue
            if c < 0 or c >= width or r < 0 or r >= height:
                continue
            if tmap.get_tile(c, r) not in WALKABLE_FOR_CHECK:
                continue
            visited.add((c, r))
            for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                queue.append((c + dc, r + dr))
        return visited

    # Iterate until stable — each pass may unlock one more room,
    # exposing further blocked rooms behind it.
    for _ in range(len(rooms)):
        reachable = bfs_reachable(stairs_col, stairs_row)
        all_ok = True
        for room in rooms:
            cx, cy = room.center
            if (cx, cy) in reachable:
                continue
            # Room unreachable — find locked doors on its wall ring
            all_ok = False
            for c in range(room.x, room.x2):
                for wr in (room.y - 1, room.y2):
                    if tmap.get_tile(c, wr) == TILE_LOCKED_DOOR:
                        tmap.set_tile(c, wr, TILE_DDOOR)
            for r in range(room.y, room.y2):
                for wc in (room.x - 1, room.x2):
                    if tmap.get_tile(wc, r) == TILE_LOCKED_DOOR:
                        tmap.set_tile(wc, r, TILE_DDOOR)
        if all_ok:
            break


def _place_decorations(tmap, rooms, width, height, torch_density="medium",
                       floor_tile=TILE_DFLOOR):
    """Sprinkle cosmetic decorations: puddles, moss, and wall torches.

    Decorations are stored on ``tmap.decorations`` (the overlay layer)
    rather than overwriting tiles in the main grid.  Their sprites have
    transparent backgrounds and are rendered on top of whatever floor
    or wall tile sits underneath, so a single torch / puddle / moss
    sprite looks correct in any dungeon style (stone, cave, crypt,
    lava, ice, void, …).  This is also why we no longer need a
    style-specific ``torch_tile`` argument.

    Parameters
    ----------
    torch_density : str
        ``"none"`` — no torches; dungeon is completely dark.
        ``"high"`` — well-lit; torches on most walls, party rarely
        needs light spells.  ``"medium"`` — moderate lighting (default).
        ``"low"`` — a few torches here and there, mostly dark.
    """

    # --- Torch density parameters ---
    # min_spacing: minimum Manhattan distance between torches
    # max_torches: cap as a multiplier of room count
    if torch_density == "none":
        # No torches at all — dungeon stays dark
        min_spacing = 999
        max_multiplier = 0
    elif torch_density == "high":
        min_spacing = 2
        max_multiplier = 5  # up to 5 per room
    elif torch_density == "low":
        min_spacing = 8
        max_multiplier = 0.5  # roughly 1 per 2 rooms
    else:  # medium (default)
        min_spacing = 4
        max_multiplier = 2  # up to 2 per room

    max_torches = int(len(rooms) * max_multiplier)

    # --- Wall torches: place on wall tiles that border a floor tile ---
    torch_candidates = []
    for room in rooms:
        # Check wall tiles along room edges
        for x in range(room.x - 1, room.x + room.w + 1):
            for y in [room.y - 1, room.y + room.h]:
                if 0 <= x < width and 0 <= y < height:
                    if tmap.get_tile(x, y) in _WALL_TILES:
                        # Must have a floor neighbor (so the light has
                        # somewhere to shine)
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = x + dx, y + dy
                            if tmap.get_tile(nx, ny) == floor_tile:
                                torch_candidates.append((x, y))
                                break
        for y in range(room.y - 1, room.y + room.h + 1):
            for x in [room.x - 1, room.x + room.w]:
                if 0 <= x < width and 0 <= y < height:
                    if tmap.get_tile(x, y) in _WALL_TILES:
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = x + dx, y + dy
                            if tmap.get_tile(nx, ny) == floor_tile:
                                torch_candidates.append((x, y))
                                break

    # Also add corridor wall candidates for high density
    if torch_density == "high":
        for y in range(height):
            for x in range(width):
                if tmap.get_tile(x, y) in _WALL_TILES and (x, y) not in torch_candidates:
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            if tmap.get_tile(nx, ny) == floor_tile:
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
        # Torches go on the decoration overlay layer.  The base wall
        # tile (stone, mountain, etc.) stays in the main grid and is
        # what scan/lighting/walkability code sees; the torch sprite
        # is drawn over it with a transparent background so the same
        # sprite works on any wall style.
        tmap.set_decoration(tc, tr, TILE_WALL_TORCH)
        placed_torches.append((tc, tr))
        if len(placed_torches) >= max_torches:
            break

    # --- Puddles: small water patches on floor tiles ---
    # Prefer tiles away from room centers, near corridors
    floor_tiles = []
    for y in range(height):
        for x in range(width):
            if tmap.get_tile(x, y) == floor_tile:
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
            if tmap.get_tile(fx + dx, fy + dy) in _WALL_TILES
        )
        if wall_count >= 1 and random.random() < 0.4:
            tmap.set_decoration(fx, fy, TILE_PUDDLE)
            puddles_placed += 1

    # --- Moss: grows on floor tiles adjacent to walls ---
    # We avoid stacking moss on top of an existing puddle decoration so
    # the two effects don't fight for the same cell.  A torch sitting
    # on an adjacent wall counts as "wall neighbour" for the wall_count
    # heuristic — torches anchor the wall and moss often grows beside
    # them.
    num_moss = max(3, len(rooms))
    random.shuffle(floor_tiles)
    moss_placed = 0
    for fx, fy in floor_tiles:
        if moss_placed >= num_moss:
            break
        if tmap.get_decoration(fx, fy) is not None:
            continue  # already decorated (e.g. with a puddle)
        wall_count = 0
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = fx + dx, fy + dy
            if tmap.get_tile(nx, ny) in _WALL_TILES:
                wall_count += 1
            elif tmap.get_decoration(nx, ny) == TILE_WALL_TORCH:
                wall_count += 1
        if wall_count >= 1 and random.random() < 0.35:
            tmap.set_decoration(fx, fy, TILE_MOSS)
            moss_placed += 1


# ── Difficulty profiles for procedural module dungeons ──────────
#
# Each tier defines five dials that actually affect how dangerous a
# procedurally-generated dungeon feels:
#
#   min_rooms / max_rooms   — floor area proxy (more rooms = bigger map)
#   enc_min / enc_max       — encounters.json "level" filter, offset
#                             by floor index so deeper floors always
#                             push toward harder encounters
#   enc_chance              — per-room probability of rolling a random
#                             encounter; the main "density" dial
#
# Floor index (0-based) is added to both enc_min and enc_max so a
# 4-floor "normal" dungeon ramps: F1 → 2..4, F2 → 3..5, F3 → 4..6,
# F4 → 5..7.  Each tier starts and ends in a band that is clearly
# distinguishable from the neighboring tier so the difficulty setting
# has visible in-game consequences.
DIFFICULTY_PROFILES = {
    "easy":   {"min_rooms": 4,  "max_rooms": 6,
               "enc_min": 1, "enc_max": 2, "enc_chance": 0.35},
    "normal": {"min_rooms": 6,  "max_rooms": 10,
               "enc_min": 2, "enc_max": 4, "enc_chance": 0.50},
    "hard":   {"min_rooms": 8,  "max_rooms": 14,
               "enc_min": 3, "enc_max": 6, "enc_chance": 0.65},
    "deadly": {"min_rooms": 10, "max_rooms": 18,
               "enc_min": 5, "enc_max": 8, "enc_chance": 0.80},
}

# Per-monster difficulty tiers exposed in the monster editor.
#
# The first four mirror DIFFICULTY_PROFILES — a monster tagged with one
# of those is restricted to dungeons of the matching difficulty.
#
# "boss" is a separate, reserved designation for unique creatures
# (e.g. the dragon at the climax of the main quest). A boss-tagged
# monster is filtered out of EVERY random spawn pool — random
# encounters in dungeons, overworld random encounters, and weighted
# spawn tables — so it can only enter combat via explicit quest
# placement (see DungeonState._inject_quest_dungeon_monsters and the
# overworld / town quest spawners). Without this, modules whose final
# quest target was also in the random pool would have the boss show
# up multiple times before the climactic fight, deflating the moment.
#
# "boss" is intentionally NOT a key in DIFFICULTY_PROFILES — it's a
# per-monster designation, not a whole-dungeon difficulty option.
# Adding a new whole-dungeon tier (e.g. "insane") still means
# extending DIFFICULTY_PROFILES; the boss exception is the only tier
# that lives only in this list.
DIFFICULTY_BOSS = "boss"
DIFFICULTY_TIERS = (*DIFFICULTY_PROFILES.keys(), DIFFICULTY_BOSS)

# Sentinel used in the monster editor's Difficulty field to mean "no
# tier set on this creature".  Untagged monsters bypass the dungeon
# difficulty filter — they're allowed to spawn in any tier.  Storing
# this as the literal string "any" (rather than absent / null) lets the
# editor cycle through it like any other choice.
DIFFICULTY_ANY = "any"

_ENCOUNTER_LEVEL_MAX = 8  # clamp so we don't demand levels that don't exist


def get_difficulty_profile(difficulty, floor_idx=0):
    """Resolve (min_rooms, max_rooms, enc_min, enc_max, enc_chance)
    for a difficulty + floor combination.

    Parameters
    ----------
    difficulty : str
        One of "easy", "normal", "hard", "deadly".  Unknown values
        fall back to "normal" so a stale/renamed module field never
        crashes generation.
    floor_idx : int
        Zero-based floor depth.  Deeper floors push the encounter
        level band upward so a 4-floor dungeon ramps in threat even
        on a single difficulty setting.
    """
    profile = DIFFICULTY_PROFILES.get(difficulty) \
        or DIFFICULTY_PROFILES["normal"]
    enc_min = max(1, profile["enc_min"] + floor_idx)
    enc_max = min(_ENCOUNTER_LEVEL_MAX,
                  profile["enc_max"] + floor_idx)
    if enc_min > enc_max:
        enc_min = enc_max  # floor pushed past top — clamp both to max
    return {
        "min_rooms": profile["min_rooms"],
        "max_rooms": profile["max_rooms"],
        "enc_min": enc_min,
        "enc_max": enc_max,
        "enc_chance": profile["enc_chance"],
    }


def generate_dungeon(name="The Depths", width=40, height=30,
                     min_rooms=6, max_rooms=10,
                     room_min_size=4, room_max_size=8,
                     seed=None,
                     place_stairs_down=False, place_artifact=False,
                     place_doors=False,
                     place_overworld_exit=False,
                     encounter_area="dungeon",
                     encounter_min_level=None,
                     encounter_max_level=None,
                     random_encounter_chance=0.5,
                     custom_encounters=None,
                     include_random_encounters=True,
                     torch_density="medium",
                     style=None,
                     dungeon_difficulty=None):
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
        place_overworld_exit: If True, place an additional stairs-up
            tile somewhere in the dungeon that exits directly back to
            the overworld (instead of ascending one level).  Used on
            the bottom level of procedural multi-level dungeons so
            the party can leave without walking all the way back up.
            The (col, row) of the exit is recorded on
            ``DungeonData.overworld_exits``.
        custom_encounters: Optional list of encounter dicts.  New format:
            ``{"monsters": ["Orc", "Skeleton", ...]}``.  Legacy format
            ``{"monster": str, "count": int}`` is also supported.
            When provided, these specific encounters are placed in the
            dungeon instead of randomly-rolled encounters.
        include_random_encounters: If True (default), random encounters
            are generated for rooms not already occupied by custom
            encounters.  When custom_encounters is provided and this is
            False, only the custom encounters appear.
        dungeon_difficulty: Optional tier name (``"easy"``,
            ``"normal"``, ``"hard"``, ``"deadly"``).  When set, random
            encounters are filtered so only encounters whose monsters
            all match this tier (or are tagged ``"any"``/untagged) can
            spawn — letting the author keep dragons out of easy
            dungeons by tagging the dragon "deadly" in the monster
            editor.  Custom (module-defined) encounters bypass this
            filter; author intent always wins.

    Returns:
        DungeonData with the generated map and metadata.
    """
    if seed is not None:
        random.seed(seed)

    # Pad the map with extra rows for HUD visibility (same trick as town)
    BUFFER = 3
    total_height = height + BUFFER

    # Per-style wall/floor selection.  Decorations (torches, puddles,
    # moss) live on the overlay layer with transparent sprite
    # backgrounds, so a single sprite per object renders correctly
    # over any wall/floor style — no per-style variants required.
    #
    # - "cave":   mountain walls, overworld "path" floor.
    # - "forest": tree walls (post-process sprinkles a few water
    #             ponds and mountain boulders), grass floor in rooms,
    #             with corridors converted to TILE_PATH and a few
    #             sand patches scattered in clearings during the
    #             post-process pass.
    # - else:     standard stone-block dungeon (TILE_DWALL / TILE_DFLOOR).
    if style == "cave":
        wall_tile = TILE_MOUNTAIN
        floor_tile = TILE_PATH
    elif style == "forest":
        wall_tile = TILE_FOREST
        floor_tile = TILE_GRASS
    else:
        wall_tile = TILE_DWALL
        floor_tile = TILE_DFLOOR
    tmap = TileMap(width, total_height, default_tile=wall_tile)

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
            _carve_room(tmap, new_room, floor_tile=floor_tile)

            # Connect to previous room
            if rooms:
                _connect_rooms(tmap, rooms[-1], new_room,
                               floor_tile=floor_tile)

            rooms.append(new_room)

    # --- Place stairs (entrance) ---
    # Forest dungeons put the entrance on the south edge of the map
    # (with a short trail carved inward) so the stairs read as a
    # trail leading back the way you came rather than a stairwell in
    # a room.  Other styles keep the original "first-room center"
    # behaviour.  If the edge placement can't reach the carved area
    # for any reason, we fall back to the room-center stairs.
    stairs_col, stairs_row = (None, None)
    entrance_edge = None  # Tracked so the descent can avoid the same edge.
    if style == "forest":
        # Forest dungeons use a wooded archway as the visible "way back"
        # marker — readable as a gateway tile rather than the invisible
        # stairs-painted-as-path the renderer used to emit.  The edge
        # is randomised per level for variety; if a randomly-chosen
        # edge can't carve a connecting trail (e.g. no carved cell on
        # that side of the map) we try the others before falling back
        # to a room-center stair.
        edges_to_try = ["north", "east", "south", "west"]
        random.shuffle(edges_to_try)
        for e in edges_to_try:
            sc, sr = _place_forest_edge_stairs(
                tmap, edge=e, tile_id=TILE_FOREST_ARCHWAY_UP,
                floor_tile=floor_tile, wall_tile=wall_tile)
            if sc is not None:
                stairs_col, stairs_row = sc, sr
                entrance_edge = e
                break
    if stairs_col is None:
        stairs_col, stairs_row = rooms[0].center
        tmap.set_tile(stairs_col, stairs_row, TILE_STAIRS)

    # --- Place chests in some of the later rooms ---
    for room in rooms[2:]:  # Skip first two rooms (too close to entrance)
        if random.random() < 0.6:  # 60% chance of a chest
            # Place chest in a corner of the room
            cx = room.x + random.choice([1, room.w - 2])
            cy = room.y + random.choice([1, room.h - 2])
            # Make sure it's on floor
            if tmap.get_tile(cx, cy) == floor_tile:
                tmap.set_tile(cx, cy, TILE_CHEST)

    # --- Place traps in corridors and some rooms ---
    for room in rooms[1:]:
        if random.random() < 0.35:  # 35% chance of a trap
            # Place near the entrance of the room
            tx, ty = room.center
            # Offset slightly from center
            tx += random.randint(-1, 1)
            ty += random.randint(-1, 1)
            if tmap.get_tile(tx, ty) == floor_tile:
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
            if tmap.get_tile(mx, my) != floor_tile:
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
            tmpl = {
                "name": f"Custom ({len(mon_names)})",
                "monster_names": mon_names,
                "monster_party_tile": lead_name,
            }
            # Carry custom battle screen if defined
            bs = enc_spec.get("battle_screen")
            if bs:
                tmpl["battle_screen"] = bs
            monster.encounter_template = tmpl
            monsters.append(monster)

    # Debug: suppress random encounters entirely when the debug flag is on.
    # Custom/module encounters above and quest monsters injected by the
    # dungeon state at entry time are unaffected.
    if include_random_encounters and not _DEBUG_QUEST_MONSTERS_ONLY:
        # ── Random encounters from encounters.json ──
        # Skip entrance room and any rooms already used by custom encounters
        for room in rooms[1:]:
            if id(room) in used_rooms:
                continue
            # Per-room probability of rolling a random encounter; the
            # difficulty setting feeds this dial so "deadly" dungeons
            # are noticeably more packed than "easy" ones.
            if random.random() < random_encounter_chance:
                mx, my = room.center
                mx += random.randint(-1, 1)
                my += random.randint(-1, 1)
                if tmap.get_tile(mx, my) == floor_tile:
                    enc = create_encounter(
                        encounter_area,
                        min_level=encounter_min_level,
                        max_level=encounter_max_level,
                        dungeon_difficulty=dungeon_difficulty)
                    if enc is None:
                        # No encounter in this difficulty/level/terrain
                        # combination — leave the room empty rather
                        # than spawning something off-tier.
                        continue
                    # Belt-and-braces: create_encounter already falls
                    # back to the first listed monster when
                    # ``monster_party_tile`` is blank, but if the
                    # encounter has no monsters at all (genuinely
                    # malformed data) we'd rather skip the room than
                    # crash the dungeon roll.
                    party_tile_name = enc.get("monster_party_tile") or (
                        enc["monsters"][0].name if enc.get("monsters") else None)
                    if not party_tile_name:
                        continue
                    monster = create_monster(party_tile_name)
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
    # Forest dungeons mirror the entrance: descent stairs sit on the
    # north edge with a short trail carved inward, reading as "the
    # trail continues deeper into the woods".  Falls back to the
    # last-room center if the edge placement can't connect.
    if place_stairs_down and len(rooms) >= 2:
        sc, sr = (None, None)
        if style == "forest":
            # Pick a different edge than the entrance so the player
            # actually has to traverse the level instead of stepping
            # onto the descent archway from the entrance trail.  Try
            # each remaining edge in random order until one carves a
            # valid trail; only fall back to a room-center stair if
            # all three remaining edges fail.
            remaining = [e for e in ("north", "east", "south", "west")
                         if e != entrance_edge]
            random.shuffle(remaining)
            for e in remaining:
                sc, sr = _place_forest_edge_stairs(
                    tmap, edge=e, tile_id=TILE_FOREST_ARCHWAY_DOWN,
                    floor_tile=floor_tile, wall_tile=wall_tile)
                if sc is not None:
                    break
        if sc is None:
            last_room = rooms[-1]
            sc, sr = last_room.center
            tmap.set_tile(sc, sr, TILE_STAIRS_DOWN)

    # --- Optional: place quest artifact in the last room ---
    if place_artifact and len(rooms) >= 2:
        last_room = rooms[-1]
        ac, ar = last_room.center
        tmap.set_tile(ac, ar, TILE_ARTIFACT)

    # --- Place doors flush against walls where corridors enter rooms ---
    if place_doors:
        _place_doors(tmap, rooms, floor_tile=floor_tile)

        # --- Upgrade single-entrance rooms to locked doors ---
        _place_locked_doors(tmap, rooms)

    # --- Connectivity check: revert locked doors that break access -----
    _fix_disconnected_locked_doors(tmap, rooms, stairs_col, stairs_row,
                                   floor_tile=floor_tile)

    # --- Place cosmetic decorations (puddles, moss, wall torches) ---
    _place_decorations(tmap, rooms, width, total_height,
                       torch_density=torch_density, floor_tile=floor_tile)

    # Entry point is on the stairs
    entry_col = stairs_col
    entry_row = stairs_row

    dd = DungeonData(tmap, rooms, entry_col, entry_row, name,
                     monsters=monsters, style=style)

    # --- Optional: place an "exit to overworld" staircase ---
    # Uses the same tile (TILE_STAIRS) as the entrance stairs so the
    # graphic matches; the dungeon state consults
    # ``dungeon_data.overworld_exits`` to decide whether an ESC-on-
    # stairs should ascend or leave the dungeon entirely.
    if place_overworld_exit and len(rooms) >= 2:
        if style == "forest":
            # Forest dungeons deliberately do NOT register an
            # overworld-exit cell.  The user-facing flow is "each
            # floor is another forest area" — the south-edge trail
            # ascends one area at a time, and the ESC handler in
            # states/dungeon.py already falls through to
            # _exit_dungeon() when ascending from floor 0.  Adding
            # an overworld_exit here would short-circuit the trail
            # walk: pressing ESC at the bottom floor's south stairs
            # would jump straight to the world map instead of
            # taking the player back one area at a time.
            pass
        else:
            exit_col, exit_row = _place_overworld_exit_stairs(
                tmap, rooms, floor_tile=floor_tile)
            if exit_col is not None:
                dd.overworld_exits.add((exit_col, exit_row))

    # --- Forest-style terrain pass ---
    # Runs LAST so it sees decorations (skips torch-bearing walls
    # when sprinkling water/mountain variants) and converts the
    # carved corridors + edge-stair trails to TILE_PATH in one go.
    if style == "forest":
        _apply_forest_terrain(tmap, rooms)

    return dd


def _place_forest_edge_stairs(tmap, edge, tile_id,
                              floor_tile, wall_tile):
    """Place an archway tile on the *edge* of a forest dungeon and
    carve a short trail from the edge inward to the nearest carved
    (room/corridor) cell.

    Forest dungeons read as "going from one area of the woods to
    another", so entrances and exits sit on the map perimeter rather
    than inside a room.

    Parameters
    ----------
    edge : str
        Any cardinal direction — ``"north"``, ``"east"``, ``"south"``
        or ``"west"``.  North/south fix the row near the top/bottom
        and sweep columns; east/west fix the column near the right/
        left and sweep rows.
    tile_id : int
        For forest dungeons this is ``TILE_FOREST_ARCHWAY_UP`` (the
        "way back" archway) or ``TILE_FOREST_ARCHWAY_DOWN`` (the
        "deeper into the woods" archway).  Older callers may still
        pass ``TILE_STAIRS``/``TILE_STAIRS_DOWN``, which the renderer
        disguises as the path sprite (legacy behaviour).
    floor_tile, wall_tile : int
        The room-floor tile (``TILE_GRASS``) and default wall tile
        (``TILE_FOREST``) for this dungeon.  Trail cells are carved
        as ``floor_tile`` so they get caught by the post-processing
        pass that converts non-room floors to ``TILE_PATH``.

    Returns ``(col, row)`` of the placed archway, or
    ``(None, None)`` if no carved cell could be reached from any
    candidate position along the chosen edge.
    """
    width = tmap.width
    height = tmap.height

    # Resolve the chosen edge to a "fixed axis position" + "sweep axis"
    # description.  For north/south the fixed axis is a row and we
    # sweep columns; for east/west it's a column and we sweep rows.
    horizontal = edge in ("north", "south")
    if edge == "south":
        fixed_idx = height - 2          # one inside the bottom border
        step      = -1                  # walk inward → row decreasing
    elif edge == "north":
        fixed_idx = 1                   # one inside the top border
        step      = 1                   # row increasing
    elif edge == "east":
        fixed_idx = width - 2           # one inside the right border
        step      = -1                  # col decreasing
    elif edge == "west":
        fixed_idx = 1                   # one inside the left border
        step      = 1                   # col increasing
    else:
        raise ValueError(
            f"_place_forest_edge_stairs: unknown edge {edge!r}")

    # Pick the sweep axis (columns for horizontal edges, rows for
    # vertical edges).  Try the central third first so the trail
    # connects into the bulk of the carved area, then fall back to
    # the outer thirds if those don't reach.
    sweep_size = width if horizontal else height
    sweep_start = max(1, sweep_size // 3)
    sweep_end   = min(sweep_size - 1, (2 * sweep_size) // 3)
    centered = list(range(sweep_start, sweep_end))
    outer = (list(range(1, sweep_start))
             + list(range(sweep_end, sweep_size - 1)))
    random.shuffle(centered)
    random.shuffle(outer)
    candidates = centered + outer

    if horizontal:
        # Fixed row, sweep across columns.  Walk inward (row direction)
        # from the edge row until we hit a non-wall cell.
        for c in candidates:
            r = fixed_idx
            while 0 < r < height - 1:
                if tmap.get_tile(c, r) != wall_tile:
                    # Carve floor between the edge and the carved
                    # interior, then plant the archway on the edge.
                    tr = fixed_idx
                    while tr != r:
                        tmap.set_tile(c, tr, floor_tile)
                        tr += step
                    tmap.set_tile(c, fixed_idx, tile_id)
                    return c, fixed_idx
                r += step
    else:
        # Fixed column, sweep across rows.  Walk inward (col direction)
        # from the edge column until we hit a non-wall cell.
        for r in candidates:
            c = fixed_idx
            while 0 < c < width - 1:
                if tmap.get_tile(c, r) != wall_tile:
                    tc = fixed_idx
                    while tc != c:
                        tmap.set_tile(tc, r, floor_tile)
                        tc += step
                    tmap.set_tile(fixed_idx, r, tile_id)
                    return fixed_idx, r
                c += step

    return None, None


def _apply_forest_terrain(tmap, rooms):
    """Post-process a forest dungeon for visual variety.

    Three passes, in order:

    1. **Corridors → trails.**  Any ``TILE_GRASS`` cell that lives
       outside every room rectangle is a corridor (or an edge-stair
       trail).  Those become ``TILE_PATH`` so the player can read
       "clearing" vs "trail" at a glance.
    2. **Wall variants.**  A small fraction of ``TILE_FOREST``
       walls are flipped to ``TILE_WATER`` (small ponds) or
       ``TILE_MOUNTAIN`` (boulders) — keeps the wall silhouette
       interesting without diluting the forest theme.  Cells that
       carry a decoration overlay (torches) are skipped so the
       overlay still reads against trees.
    3. **Sand patches.**  Roughly a third of the rooms get one or
       two sand cells, evoking dirt patches in a clearing.

    Wall cells (TILE_FOREST in particular — which is walkable on
    the overworld) are flagged non-walkable per cell via
    ``tile_properties`` so the player can't step into a tree the
    way they'd walk through forest on the world map.  Water and
    mountain are already non-walkable per ``TILE_DEFS``, so they
    don't need an override.
    """
    width = tmap.width
    height = tmap.height

    # Lazily initialise the per-cell property dict the existing
    # walkability override system reads.
    if not getattr(tmap, "tile_properties", None):
        tmap.tile_properties = {}
    props = tmap.tile_properties

    # 1. Identify cells inside any room rectangle.
    room_cells = set()
    for room in rooms:
        for r in range(room.y, room.y2):
            for c in range(room.x, room.x2):
                room_cells.add((c, r))

    # Corridor grass → path.
    for r in range(height):
        for c in range(width):
            if (tmap.get_tile(c, r) == TILE_GRASS
                    and (c, r) not in room_cells):
                tmap.set_tile(c, r, TILE_PATH)

    # 2. Wall variants — sparse so the forest still reads as forest.
    decorations = getattr(tmap, "decorations", {}) or {}
    for r in range(height):
        for c in range(width):
            if tmap.get_tile(c, r) != TILE_FOREST:
                continue
            if (c, r) in decorations:
                continue  # don't pull the rug out from under a torch
            roll = random.random()
            if roll < 0.05:
                tmap.set_tile(c, r, TILE_WATER)
            elif roll < 0.08:
                tmap.set_tile(c, r, TILE_MOUNTAIN)

    # 3. Sand patches in a subset of the rooms.
    for room in rooms:
        if room.w < 3 or room.h < 3:
            continue
        if random.random() >= 0.3:
            continue
        for _ in range(random.randint(1, 3)):
            cx = random.randint(room.x + 1, room.x + room.w - 2)
            cy = random.randint(room.y + 1, room.y + room.h - 2)
            if tmap.get_tile(cx, cy) == TILE_GRASS:
                tmap.set_tile(cx, cy, TILE_SAND)

    # 4. Override TILE_FOREST cells to be non-walkable.  The
    # overworld treats forest as walkable terrain (you can step
    # into the woods), but inside a forest dungeon trees are the
    # walls and must block movement.  Water and mountain are
    # already non-walkable per TILE_DEFS, so we only need overrides
    # for the surviving forest cells (after the variant pass above).
    for r in range(height):
        for c in range(width):
            if tmap.get_tile(c, r) == TILE_FOREST:
                key = f"{c},{r}"
                entry = props.get(key)
                if not isinstance(entry, dict):
                    entry = {}
                    props[key] = entry
                entry["walkable"] = False


def _place_overworld_exit_stairs(tmap, rooms, floor_tile=TILE_DFLOOR):
    """Place a TILE_STAIRS somewhere that leads back to the overworld.

    Picks a room in the middle of the run (avoids the first room which
    already holds the ascend-stairs, and the last room which may hold
    the quest artifact or other special tiles).  Within the chosen
    room, tries random floor tiles first so the exit doesn't always
    land on the exact center.  Returns ``(col, row)`` of the placed
    stair, or ``(None, None)`` if no suitable spot was found.
    """
    if len(rooms) < 2:
        return None, None

    # Candidate rooms: everything except the first (ascend stairs live
    # there) and the last (may hold artifact / stairs-down).
    if len(rooms) >= 3:
        candidates = list(rooms[1:-1])
    else:
        # Only 2 rooms — fall back to the second one but avoid its center
        candidates = [rooms[1]]
    random.shuffle(candidates)

    for room in candidates:
        # Try random interior floor tiles (up to 20 attempts per room)
        for _ in range(20):
            cx = random.randint(room.x + 1, room.x + room.w - 2)
            cy = random.randint(room.y + 1, room.y + room.h - 2)
            if tmap.get_tile(cx, cy) == floor_tile:
                tmap.set_tile(cx, cy, TILE_STAIRS)
                return cx, cy
        # Fallback: room center if it's a floor tile
        cc, cr = room.center
        if tmap.get_tile(cc, cr) == floor_tile:
            tmap.set_tile(cc, cr, TILE_STAIRS)
            return cc, cr
    return None, None


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
        place_overworld_exit=True,
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
        place_overworld_exit=True,
    )
    return [level_0, level_1]


def generate_innkeeper_quest_dungeon(name="Shadow Dungeon", num_floors=None,
                                     place_artifact=True,
                                     kill_target=None, kill_count=0,
                                     torch_density="medium",
                                     dungeon_size="medium",
                                     place_doors=False):
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
            place_doors=place_doors,
            place_overworld_exit=(is_last and num_floors > 1),
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
                          dungeon_size="medium",
                          place_doors=False):
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
            place_doors=place_doors,
            place_overworld_exit=(is_last and num_floors > 1),
            encounter_area="dungeon",
            encounter_min_level=enc_level,
            encounter_max_level=enc_level,
            custom_encounters=custom_enc,
            include_random_encounters=include_random,
            torch_density=floor_torch,
        )
        levels.append(level_data)

    return levels
