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

    def __init__(self, tile_map, npcs, name, entry_col, entry_row):
        self.tile_map = tile_map
        self.npcs = npcs
        self.name = name
        self.entry_col = entry_col
        self.entry_row = entry_row

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
