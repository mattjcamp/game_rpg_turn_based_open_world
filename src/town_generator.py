"""
Town map generator.

Creates a small town interior map with buildings, shops, NPCs, and an exit.
Each town is a self-contained TileMap with its own NPC data. For now towns
are hand-templated with some randomization; later this can be made fully
procedural.
"""

import random

from src.tile_map import TileMap
from src.settings import (
    TILE_FLOOR, TILE_WALL, TILE_COUNTER, TILE_DOOR, TILE_EXIT,
    TILE_MACHINE, TILE_KEYSLOT,
)


class NPC:
    """A non-player character inside a town."""

    def __init__(self, col, row, name, dialogue, npc_type="villager",
                 quest_dialogue=None, quest_choices=None):
        self.col = col
        self.row = row
        self.name = name
        self.dialogue = dialogue  # list of strings, cycles through on each talk
        self.npc_type = npc_type  # villager, shopkeep, innkeeper, elder
        self._talk_index = 0
        # Quest support — only used for quest-giving NPCs
        self.quest_dialogue = quest_dialogue  # list of strings for quest offer
        self.quest_choices = quest_choices    # e.g. ["Yes, I'll do it!", "Not right now."]

    def get_dialogue(self):
        """Return the next line of dialogue and advance the index."""
        line = self.dialogue[self._talk_index]
        self._talk_index = (self._talk_index + 1) % len(self.dialogue)
        return line


class TownData:
    """Holds everything about a town: map, NPCs, name, entry point."""

    def __init__(self, tile_map, npcs, name, entry_col, entry_row,
                 keyslot_positions=None):
        self.tile_map = tile_map
        self.npcs = npcs
        self.name = name
        self.entry_col = entry_col
        self.entry_row = entry_row
        # Ordered list of (col, row) for the 8 key slots (index = slot number)
        self.keyslot_positions = keyslot_positions or []

    def get_npc_at(self, col, row):
        """Return the NPC at the given position, or None."""
        for npc in self.npcs:
            if npc.col == col and npc.row == row:
                return npc
        return None


def _place_building(tmap, x, y, w, h, door_side="south"):
    """
    Place a rectangular building on the town map.

    Walls on the perimeter, floor inside, one door opening.
    """
    for row in range(y, y + h):
        for col in range(x, x + w):
            if row == y or row == y + h - 1 or col == x or col == x + w - 1:
                tmap.set_tile(col, row, TILE_WALL)
            else:
                tmap.set_tile(col, row, TILE_FLOOR)

    # Place door
    if door_side == "south":
        door_col = x + w // 2
        door_row = y + h - 1
    elif door_side == "north":
        door_col = x + w // 2
        door_row = y
    elif door_side == "east":
        door_col = x + w - 1
        door_row = y + h // 2
    else:  # west
        door_col = x
        door_row = y + h // 2

    tmap.set_tile(door_col, door_row, TILE_DOOR)


def generate_town(name="Thornwall"):
    """
    Generate a town map with NPCs and an exit.

    The playable interior is 18×19 tiles of floor surrounded by a brick wall
    border.  The total map is padded with extra wall tiles on every side so
    the camera (25×17 viewport) never sees out-of-bounds areas.
    """
    # Playable interior dimensions (floor area inside the walls)
    INTERIOR_W = 18
    INTERIOR_H = 19

    # Padding: enough extra wall tiles around the playable area so the
    # camera can never scroll past the map boundary.
    # Viewport is 25 cols × 17 rows; half-viewport is the most the camera
    # can offset from the party position near the edges.
    PAD_X = 13   # extra wall columns on each side
    PAD_Y = 9    # extra wall rows on top and bottom

    # Total map size
    W = INTERIOR_W + 2 + PAD_X * 2   # +2 for the brick border itself
    H = INTERIOR_H + 2 + PAD_Y * 2

    # The playable brick border starts at (PAD_X, PAD_Y)
    BORDER_X = PAD_X
    BORDER_Y = PAD_Y
    BORDER_W = INTERIOR_W + 2
    BORDER_H = INTERIOR_H + 2

    tmap = TileMap(W, H, default_tile=TILE_WALL)

    # --- Floor inside the brick border ---
    for row in range(BORDER_Y + 1, BORDER_Y + BORDER_H - 1):
        for col in range(BORDER_X + 1, BORDER_X + BORDER_W - 1):
            tmap.set_tile(col, row, TILE_FLOOR)

    # --- Exit gate (bottom centre of the brick border) ---
    exit_col = BORDER_X + BORDER_W // 2
    exit_row = BORDER_Y + BORDER_H - 1
    tmap.set_tile(exit_col, exit_row, TILE_EXIT)

    # --- Helper: convert interior-relative coords to world coords ---
    # Interior (0,0) is the top-left floor tile inside the wall.
    ox = BORDER_X + 1   # world col of interior col 0
    oy = BORDER_Y + 1   # world row of interior row 0

    # --- Buildings ---

    # Shop (upper-left, 6 wide × 5 tall, door faces south)
    _place_building(tmap, ox + 1, oy + 1, 6, 5, door_side="south")
    # Counter inside the shop
    tmap.set_tile(ox + 3, oy + 2, TILE_COUNTER)
    tmap.set_tile(ox + 4, oy + 2, TILE_COUNTER)
    tmap.set_tile(ox + 5, oy + 2, TILE_COUNTER)

    # Inn (upper-right, 6 wide × 5 tall, door faces south)
    _place_building(tmap, ox + 11, oy + 1, 6, 5, door_side="south")
    # Bar counter inside the inn
    tmap.set_tile(ox + 13, oy + 2, TILE_COUNTER)
    tmap.set_tile(ox + 14, oy + 2, TILE_COUNTER)

    # --- NPCs ---
    npcs = []

    # Shopkeeper inside the shop (behind the counter)
    npcs.append(NPC(ox + 4, oy + 3, "Gruff", [
        "Welcome to Gruff's Armaments!",
        "I've got the finest steel this side of the mountains.",
        "Swords, axes, bows -- you name it, I forge it.",
        "Come back when you've got more gold!",
    ], npc_type="shopkeep"))

    # Innkeeper inside the inn (behind the bar)
    npcs.append(NPC(ox + 14, oy + 3, "Bertram", [
        "Welcome to the Sleeping Griffin Inn!",
        "Rest your weary bones. A room is 10 gold per night.",
        "I hear dark things stir in the dungeons to the east...",
        "Can I get you an ale?",
    ], npc_type="innkeeper",
       quest_dialogue=[
           "Psst... adventurer! I've heard rumors of a Shadow Crystal hidden in a dungeon that appeared near our lands.",
           "It radiates dark energy and threatens our town. Will you seek it out and bring it back to me?",
       ],
       quest_choices=["Yes, I'll find it!", "Not right now."],
    ))

    # Town elder (wandering in the open area)
    npcs.append(NPC(ox + 9, oy + 10, "Elder Morath", [
        "Ah, brave adventurers! Our town is in grave danger.",
        "A great evil festers in the dungeon to the east.",
        "You must find the four shrines hidden across the land.",
        "Only then can the shadow be banished forever.",
        "I sense great potential in you. Do not lose hope.",
    ], npc_type="elder"))

    # Wandering villagers
    villager_dialogues = [
        ["Beautiful day, isn't it?", "Watch out for wolves in the forest."],
        ["I lost my cat somewhere near the mountains...", "Have you seen a tabby?"],
        ["The elder seems worried lately.", "Something about the dungeons."],
        ["I used to be an adventurer, you know.", "Then I took an arrow to the knee."],
    ]

    villager_spots = [(ox + 5, oy + 15), (ox + 13, oy + 15), (ox + 9, oy + 8)]
    for i, (vc, vr) in enumerate(villager_spots):
        name_pool = ["Tomas", "Elena", "Joric", "Bess", "Finn"]
        npcs.append(NPC(vc, vr, name_pool[i % len(name_pool)],
                        villager_dialogues[i % len(villager_dialogues)],
                        npc_type="villager"))

    # Entry point: just inside the exit gate
    entry_col = exit_col
    entry_row = exit_row - 1

    return TownData(tmap, npcs, name, entry_col, entry_row)


def generate_duskhollow():
    """
    Generate the town of Duskhollow for the Keys of Shadow module.

    A larger town (28×25 interior) with shrines, houses, a shop, an inn,
    and the Gnome Machine at its centre.  The town is perpetually dark
    (handled by the rendering layer via ``darkness_active``).
    """
    INTERIOR_W = 28
    INTERIOR_H = 25

    # Padding so the camera (30×21 viewport) never sees out-of-bounds.
    PAD_X = 16
    PAD_Y = 11

    W = INTERIOR_W + 2 + PAD_X * 2
    H = INTERIOR_H + 2 + PAD_Y * 2

    BORDER_X = PAD_X
    BORDER_Y = PAD_Y
    BORDER_W = INTERIOR_W + 2
    BORDER_H = INTERIOR_H + 2

    tmap = TileMap(W, H, default_tile=TILE_WALL)

    # --- Floor inside the brick border ---
    for row in range(BORDER_Y + 1, BORDER_Y + BORDER_H - 1):
        for col in range(BORDER_X + 1, BORDER_X + BORDER_W - 1):
            tmap.set_tile(col, row, TILE_FLOOR)

    # --- Exit gate (bottom centre) ---
    exit_col = BORDER_X + BORDER_W // 2
    exit_row = BORDER_Y + BORDER_H - 1
    tmap.set_tile(exit_col, exit_row, TILE_EXIT)

    # Interior origin — (0,0) of the interior coordinate space.
    ox = BORDER_X + 1
    oy = BORDER_Y + 1

    # ── Gnome Machine — dead centre, 3×3 footprint ──
    machine_col = ox + INTERIOR_W // 2
    machine_row = oy + INTERIOR_H // 2
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            tmap.set_tile(machine_col + dc, machine_row + dr, TILE_MACHINE)

    # ── 8 Key Slots surrounding the machine ──
    # Placed in a ring just outside the 3×3 machine body.
    # Order: N, NE, E, SE, S, SW, W, NW (matches key indices 0-7)
    keyslot_offsets = [
        ( 0, -2),   # N  — top centre
        ( 2, -2),   # NE — top-right
        ( 2,  0),   # E  — right centre
        ( 2,  2),   # SE — bottom-right
        ( 0,  2),   # S  — bottom centre
        (-2,  2),   # SW — bottom-left
        (-2,  0),   # W  — left centre
        (-2, -2),   # NW — top-left
    ]
    keyslot_positions = []  # ordered list of (col, row) for slots 0-7
    for dc, dr in keyslot_offsets:
        sc, sr = machine_col + dc, machine_row + dr
        tmap.set_tile(sc, sr, TILE_KEYSLOT)
        keyslot_positions.append((sc, sr))

    # ================================================================
    # BUILDINGS
    # ================================================================

    # ── Shop (upper-left, 7×5, door south) ──
    _place_building(tmap, ox + 1, oy + 1, 7, 5, door_side="south")
    # Counter inside
    for c in range(ox + 3, ox + 6):
        tmap.set_tile(c, oy + 2, TILE_COUNTER)

    # ── Inn (upper-right, 7×5, door south) ──
    _place_building(tmap, ox + 20, oy + 1, 7, 5, door_side="south")
    # Bar counter
    tmap.set_tile(ox + 23, oy + 2, TILE_COUNTER)
    tmap.set_tile(ox + 24, oy + 2, TILE_COUNTER)
    tmap.set_tile(ox + 25, oy + 2, TILE_COUNTER)

    # ── Shrine of Light (mid-left, 5×5, door east) ──
    _place_building(tmap, ox + 1, oy + 8, 5, 5, door_side="east")

    # ── Shrine of Stars (mid-right, 5×5, door west) ──
    _place_building(tmap, ox + 22, oy + 8, 5, 5, door_side="west")

    # ── Elder's House (lower-left, 6×5, door east) ──
    _place_building(tmap, ox + 1, oy + 15, 6, 5, door_side="east")

    # ── Guard House (lower-right, 6×5, door west) ──
    _place_building(tmap, ox + 21, oy + 15, 6, 5, door_side="west")

    # ── Small cottage A (lower-mid-left, 4×4, door south) ──
    _place_building(tmap, ox + 9, oy + 18, 4, 4, door_side="south")

    # ── Small cottage B (lower-mid-right, 4×4, door south) ──
    _place_building(tmap, ox + 16, oy + 18, 4, 4, door_side="south")

    # ================================================================
    # NPCs
    # ================================================================
    npcs = []

    # ── Shopkeeper ──
    npcs.append(NPC(ox + 4, oy + 3, "Mara", [
        "Welcome to Mara's Provisions!",
        "Stock up before heading into the dark.",
        "Torches are half-price for adventurers.",
        "Be careful out there — the monsters grow fiercer to the north.",
    ], npc_type="shopkeep"))

    # ── Innkeeper ──
    npcs.append(NPC(ox + 24, oy + 3, "Aldric", [
        "Welcome to the Dim Lantern Inn.",
        "Rest here to recover your strength.",
        "The darkness has been hard on business...",
        "Talk to the gnome by the machine if you want to help.",
    ], npc_type="innkeeper"))

    # ── Fizzwick the Gnome — quest-giver, stands next to the machine ──
    npcs.append(NPC(machine_col + 3, machine_row, "Fizzwick", [
        "Oh! Oh dear! You've come to help, haven't you?",
        "I built this machine to harness the sun's energy...",
        "But something went terribly wrong! It's devouring the light!",
        "I've tried everything — only the 8 Keys of Shadow can shut it down.",
        "The keys are scattered across 8 dungeons in these lands.",
        "Each dungeon is deeper and more dangerous than the last.",
        "Please, bring me the keys! I'll insert them into the machine myself.",
        "Hurry... Duskhollow cannot survive in darkness forever.",
    ], npc_type="gnome",
       quest_dialogue=[
           "You there! Adventurers! I am Fizzwick, and I've made a terrible mistake.",
           "My machine was meant to bring endless daylight to Duskhollow...",
           "Instead it's consumed the sun entirely! The town is trapped in darkness!",
           "Only the 8 Keys of Shadow can reverse it. They're hidden in dungeons "
           "across the land — each one guarded by fiercer monsters than the last.",
           "Will you help me recover them and save Duskhollow?",
       ],
       quest_choices=["We'll find the keys!", "Not right now."],
    ))

    # ── Shrine Keeper of Light ──
    npcs.append(NPC(ox + 3, oy + 10, "Sister Luma", [
        "This is the Shrine of Light. May its glow guide you.",
        "The first key lies in a small warren just outside town.",
        "Bring torches — the darkness is absolute without them.",
        "Each key you recover weakens the machine's grip.",
        "Return here if your spirits falter. Light endures.",
    ], npc_type="elder"))

    # ── Shrine Keeper of Stars ──
    npcs.append(NPC(ox + 24, oy + 10, "Brother Astrin", [
        "Welcome to the Shrine of Stars, traveler.",
        "The dungeons grow deeper and more dangerous as you venture further.",
        "The easiest lies south-west. The hardest is far to the south-east.",
        "Study the stars... even in darkness, they remember the sun.",
        "Prepare well. The eighth dungeon has eight floors of peril.",
    ], npc_type="elder"))

    # ── Elder Gwynn ──
    npcs.append(NPC(ox + 4, oy + 17, "Elder Gwynn", [
        "Ah, you've come at last. I am Gwynn, elder of Duskhollow.",
        "The gnome Fizzwick was once a friend to this town.",
        "But his obsession with shadow-energy consumed him.",
        "He built the machine to harness the sun's power...",
        "Instead it devoured the light entirely.",
        "Fizzwick vanished, but the machine remains. Only the 8 keys can stop it.",
    ], npc_type="elder"))

    # ── Captain Hale ──
    npcs.append(NPC(ox + 24, oy + 17, "Captain Hale", [
        "I'm Captain Hale of the Duskhollow Guard.",
        "My soldiers can hold the town, but those dungeons are beyond us.",
        "The nearer dungeons have weaker creatures — rats, goblins.",
        "But the distant ones? Dragons. Liches. Worse.",
        "Match your strength to the dungeon's depth, or you'll never return.",
    ], npc_type="villager"))

    # ── Villagers ──
    npcs.append(NPC(ox + 10, oy + 7, "Tilda", [
        "I haven't seen the sun in so long...",
        "My children are frightened of the dark.",
        "Please, find those keys and end this nightmare.",
    ], npc_type="villager"))

    npcs.append(NPC(ox + 18, oy + 7, "Ren", [
        "The darkness brings foul creatures closer to town.",
        "I've boarded up my windows, for what good it does.",
        "Some say the keys glow when you're near them.",
    ], npc_type="villager"))

    npcs.append(NPC(ox + 14, oy + 16, "Old Finch", [
        "I remember when the sun shone on Duskhollow.",
        "The flowers in the square were beautiful then.",
        "Now there's only that cursed machine.",
        "Fizzwick... what have you done?",
    ], npc_type="villager"))

    # Entry point: just inside the exit gate
    entry_col = exit_col
    entry_row = exit_row - 1

    return TownData(tmap, npcs, "Duskhollow", entry_col, entry_row,
                    keyslot_positions=keyslot_positions)
