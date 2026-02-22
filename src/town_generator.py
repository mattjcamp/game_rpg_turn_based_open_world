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
    TILE_FLOOR, TILE_WALL, TILE_COUNTER, TILE_DOOR, TILE_EXIT, TILE_GRASS,
)


class NPC:
    """A non-player character inside a town."""

    def __init__(self, col, row, name, dialogue, npc_type="villager"):
        self.col = col
        self.row = row
        self.name = name
        self.dialogue = dialogue  # list of strings, cycles through on each talk
        self.npc_type = npc_type  # villager, shopkeep, innkeeper, elder
        self._talk_index = 0

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
    Returns the interior floor coordinates for placing counters/NPCs.
    """
    interior = []

    for row in range(y, y + h):
        for col in range(x, x + w):
            if row == y or row == y + h - 1 or col == x or col == x + w - 1:
                tmap.set_tile(col, row, TILE_WALL)
            else:
                tmap.set_tile(col, row, TILE_FLOOR)
                interior.append((col, row))

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

    return interior


def generate_town(name="Thornwall"):
    """
    Generate a town map with buildings, NPCs, and an exit.

    The town is 20x20 tiles:
    - Outer wall border
    - Floor everywhere inside
    - Several buildings (weapon shop, armor shop, inn, elder's house)
    - NPCs inside and outside
    - Exit gate at the bottom center
    """
    W = 20
    TOWN_H = 21        # Playable town area (row 0..20)
    BUFFER = 3          # Extra wall rows below so exit isn't hidden by HUD
    H = TOWN_H + BUFFER # Total map height
    tmap = TileMap(W, H, default_tile=TILE_FLOOR)

    # --- Outer wall (the playable town boundary) ---
    for row in range(TOWN_H):
        for col in range(W):
            if row == 0 or row == TOWN_H - 1 or col == 0 or col == W - 1:
                tmap.set_tile(col, row, TILE_WALL)

    # --- Buffer rows below the wall (solid wall so camera can scroll past exit) ---
    for row in range(TOWN_H, H):
        for col in range(W):
            tmap.set_tile(col, row, TILE_WALL)

    # --- Exit gate (bottom of the playable wall) ---
    exit_col = W // 2
    exit_row = TOWN_H - 1
    tmap.set_tile(exit_col, exit_row, TILE_EXIT)

    # --- Buildings ---

    # Weapon Shop (top-left area)
    _place_building(tmap, 2, 2, 6, 5, door_side="south")
    # Counter inside
    tmap.set_tile(4, 3, TILE_COUNTER)
    tmap.set_tile(5, 3, TILE_COUNTER)
    tmap.set_tile(6, 3, TILE_COUNTER)

    # Armor Shop (top-right area)
    _place_building(tmap, 12, 2, 6, 5, door_side="south")
    # Counter inside
    tmap.set_tile(14, 3, TILE_COUNTER)
    tmap.set_tile(15, 3, TILE_COUNTER)
    tmap.set_tile(16, 3, TILE_COUNTER)

    # Inn (middle-left area)
    _place_building(tmap, 2, 10, 7, 5, door_side="east")
    # Counter (bar)
    tmap.set_tile(3, 11, TILE_COUNTER)
    tmap.set_tile(4, 11, TILE_COUNTER)

    # Elder's House (middle-right area)
    _place_building(tmap, 13, 10, 6, 5, door_side="west")

    # --- Some decoration: grass patches in the town square ---
    for col in range(8, 12):
        for row in range(8, 11):
            tmap.set_tile(col, row, TILE_GRASS)

    # --- NPCs ---
    npcs = []

    # Weapon shopkeeper
    npcs.append(NPC(5, 4, "Gruff", [
        "Welcome to Gruff's Armaments!",
        "I've got the finest steel this side of the mountains.",
        "Swords, axes, bows -- you name it, I forge it.",
        "Come back when you've got more gold!",
    ], npc_type="shopkeep"))

    # Armor shopkeeper
    npcs.append(NPC(15, 4, "Helga", [
        "Helga's Armor Emporium! Best protection in the realm.",
        "Chain mail, plate armor, enchanted shields...",
        "A good suit of armor is worth more than any sword.",
        "Stay safe out there, adventurer.",
    ], npc_type="shopkeep"))

    # Innkeeper
    npcs.append(NPC(3, 12, "Bertram", [
        "Welcome to the Sleeping Griffin Inn!",
        "Rest your weary bones. A room is 10 gold per night.",
        "I hear dark things stir in the dungeons to the east...",
        "Can I get you an ale?",
    ], npc_type="innkeeper"))

    # Town elder
    npcs.append(NPC(15, 12, "Elder Morath", [
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

    # Place villagers in open floor spaces
    villager_spots = [(6, 16), (14, 16), (10, 9)]
    for i, (vc, vr) in enumerate(villager_spots):
        name_pool = ["Tomas", "Elena", "Joric", "Bess", "Finn"]
        npcs.append(NPC(vc, vr, name_pool[i % len(name_pool)],
                        villager_dialogues[i % len(villager_dialogues)],
                        npc_type="villager"))

    # Entry point: just inside the exit gate
    entry_col = exit_col
    entry_row = exit_row - 1

    return TownData(tmap, npcs, name, entry_col, entry_row)
