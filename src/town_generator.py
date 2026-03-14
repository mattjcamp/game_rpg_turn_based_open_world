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
    TILE_MACHINE, TILE_KEYSLOT, TILE_ALTAR, TILE_GRASS,
)


class NPC:
    """A non-player character inside a town."""

    # NPC types that stay in place (inside buildings or at fixed posts)
    STATIONARY_TYPES = {"shopkeep", "innkeeper", "priest", "gnome"}

    def __init__(self, col, row, name, dialogue, npc_type="villager",
                 quest_dialogue=None, quest_choices=None, god_name=None,
                 quest_name=None, artifact_name=None,
                 hint_active=None, text_complete=None,
                 innkeeper_quests=False):
        self.col = col
        self.row = row
        self.name = name
        self.dialogue = dialogue  # list of strings, cycles through on each talk
        self.npc_type = npc_type  # villager, shopkeep, innkeeper, elder, priest
        self._talk_index = 0
        # Quest support — only used for quest-giving NPCs
        self.quest_dialogue = quest_dialogue  # list of strings for quest offer
        self.quest_choices = quest_choices    # e.g. ["Yes, I'll do it!", "Not right now."]
        # Innkeeper quest metadata (from quest pool)
        self.quest_name = quest_name or "The Shadow Crystal"
        self.artifact_name = artifact_name or "Shadow Crystal"
        self.hint_active = hint_active
        self.text_complete = text_complete
        # Innkeeper repeatable quests flag
        self.innkeeper_quests = innkeeper_quests
        # Priest support
        self.god_name = god_name or "The Divine"
        # Quest highlight — set True by the town state when this NPC
        # is offering a quest or waiting for quest resolution.
        self.quest_highlight = False

        # Wandering support — NPCs not in STATIONARY_TYPES will roam
        self.home_col = col
        self.home_row = row
        self.wander_timer = random.uniform(1.0, 3.0)  # seconds until next move
        self.wander_range = 4  # max tiles from home position

    def get_dialogue(self):
        """Return the next line of dialogue and advance the index."""
        line = self.dialogue[self._talk_index]
        self._talk_index = (self._talk_index + 1) % len(self.dialogue)
        return line


class TownData:
    """Holds everything about a town: map, NPCs, name, entry point."""

    def __init__(self, tile_map, npcs, name, entry_col, entry_row,
                 keyslot_positions=None, town_style="medieval",
                 building_signs=None):
        self.tile_map = tile_map
        self.npcs = npcs
        self.name = name
        self.entry_col = entry_col
        self.entry_row = entry_row
        # Ordered list of (col, row) for the 8 key slots (index = slot number)
        self.keyslot_positions = keyslot_positions or []
        # Visual style key — used by the renderer to pick a colour palette
        self.town_style = town_style
        # Building name signs — list of dicts with keys:
        #   text (str), row (int), col (int), width (int in tiles)
        # Used by the renderer to overlay text on building walls.
        self.building_signs = building_signs or []

    def get_npc_at(self, col, row):
        """Return the NPC at the given position, or None."""
        for npc in self.npcs:
            if npc.col == col and npc.row == row:
                return npc
        return None


def _clamp_building(bx, by, bw, bh, iw, ih, counters, altar_pos=None):
    """Clamp a building's position so it fits within the interior.

    Returns (clamped_bx, clamped_by, adjusted_counters, adjusted_altar).
    Leaves a 1-tile margin on all sides so doors always have a walkable
    approach tile inside the town interior.
    """
    # Maximum position that keeps the building + 1-tile approach inside
    max_x = iw - bw - 1   # 1-tile margin on the right
    max_y = ih - bh - 1   # 1-tile margin on the bottom
    min_x = 1             # 1-tile margin on the left
    min_y = 1             # 1-tile margin on the top

    cx = max(min_x, min(bx, max_x))
    cy = max(min_y, min(by, max_y))
    dx = cx - bx
    dy = cy - by

    adj_counters = [(c + dx, r + dy) for c, r in counters]
    adj_altar = (altar_pos[0] + dx, altar_pos[1] + dy) if altar_pos else None
    return cx, cy, adj_counters, adj_altar


def _ensure_all_doors_accessible(tmap, entry_col, entry_row):
    """Post-placement pass: guarantee every door is reachable from the entry.

    Uses flood-fill from the town entry point to find the reachable area.
    For each door that is NOT reachable, carves a shortest path through
    walls to connect it to the reachable walkable area.
    """
    from collections import deque

    _WALKABLE = {TILE_FLOOR, TILE_DOOR, TILE_EXIT}

    def _flood():
        """Return set of all (col, row) reachable from entry."""
        visited = set()
        q = deque([(entry_col, entry_row)])
        visited.add((entry_col, entry_row))
        while q:
            c, r = q.popleft()
            for dc, dr in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nc, nr = c + dc, r + dr
                if ((nc, nr) not in visited
                        and 0 <= nc < tmap.width
                        and 0 <= nr < tmap.height
                        and tmap.get_tile(nc, nr) in _WALKABLE):
                    visited.add((nc, nr))
                    q.append((nc, nr))
        return visited

    def _carve_path(door_c, door_r, reachable):
        """BFS from *door* through walls until a reachable tile is found.

        Converts every wall tile along the shortest path to TILE_FLOOR
        so the door connects to the walkable area.
        """
        parent = {}
        q = deque()
        # Seed BFS with the door's non-reachable wall neighbours
        for dc, dr in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nc, nr = door_c + dc, door_r + dr
            if 0 <= nc < tmap.width and 0 <= nr < tmap.height:
                if (nc, nr) in reachable:
                    return  # already connected
                if tmap.get_tile(nc, nr) == TILE_WALL:
                    q.append((nc, nr))
                    parent[(nc, nr)] = None
        while q:
            c, r = q.popleft()
            for dc, dr in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nc, nr = c + dc, r + dr
                if (nc, nr) in reachable:
                    # Trace back and carve every wall tile to floor
                    cur = (c, r)
                    while cur is not None:
                        tmap.set_tile(cur[0], cur[1], TILE_FLOOR)
                        cur = parent[cur]
                    return
                if ((nc, nr) not in parent
                        and 0 <= nc < tmap.width
                        and 0 <= nr < tmap.height
                        and tmap.get_tile(nc, nr) == TILE_WALL):
                    parent[(nc, nr)] = (c, r)
                    q.append((nc, nr))

    # Iterate — each carve may unlock additional doors behind it
    for _ in range(8):
        reachable = _flood()
        fixed_any = False
        for r in range(tmap.height):
            for c in range(tmap.width):
                if tmap.get_tile(c, r) == TILE_DOOR and (c, r) not in reachable:
                    _carve_path(c, r, reachable)
                    fixed_any = True
        if not fixed_any:
            break


def _place_building(tmap, x, y, w, h, door_side="south"):
    """
    Place a rectangular building on the town map.

    Walls on the perimeter, floor inside, one door opening.
    The tile just outside the door is guaranteed to be walkable floor.
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

    # Ensure the approach tile outside the door is walkable floor
    approach = {
        "south": (door_col, door_row + 1),
        "north": (door_col, door_row - 1),
        "east":  (door_col + 1, door_row),
        "west":  (door_col - 1, door_row),
    }
    ac, ar = approach[door_side]
    if 0 <= ac < tmap.width and 0 <= ar < tmap.height:
        tile = tmap.get_tile(ac, ar)
        if tile not in (TILE_FLOOR, TILE_EXIT, TILE_DOOR):
            tmap.set_tile(ac, ar, TILE_FLOOR)


# ── Town variety pools ──────────────────────────────────────────────
# Each pool is indexed deterministically by a seed so that every town
# in a module is unique yet reproducible across saves.

_PRIEST_POOL = [
    {"name": "Brother Cedric",  "god": "Solarius",  "title": "Temple of Solarius"},
    {"name": "Sister Miriel",   "god": "Lunara",    "title": "Shrine of Lunara"},
    {"name": "Father Aldous",   "god": "Terran",    "title": "Chapel of Terran"},
    {"name": "Mother Ysara",    "god": "Aethis",    "title": "Sanctuary of Aethis"},
    {"name": "Brother Thane",   "god": "Pyralis",   "title": "Temple of Pyralis"},
    {"name": "Sister Vesper",   "god": "Noxara",    "title": "Shrine of Noxara"},
    {"name": "Father Corwin",   "god": "Aquilis",   "title": "Chapel of Aquilis"},
    {"name": "Mother Elara",    "god": "Verdantis", "title": "Sanctuary of Verdantis"},
]

_PRIEST_DIALOGUE_POOL = [
    [
        "Welcome to the {title}, child.",
        "The light of {god} heals all wounds.",
        "We offer healing and resurrection for those in need.",
        "May {god}'s radiance guide your path.",
    ],
    [
        "Enter freely, traveler. {god} welcomes all.",
        "The faithful of {god} know no fear.",
        "Healing and blessings are offered here.",
        "Go with {god}'s grace.",
    ],
    [
        "Peace be upon you, wanderer.",
        "In {god}'s name, we mend body and soul.",
        "Even the gravest wounds yield to {god}'s power.",
        "Walk always in the light.",
    ],
]

_SHOPKEEP_POOL = [
    {"name": "Gruff",    "shop": "Gruff's Armaments"},
    {"name": "Mara",     "shop": "Mara's Provisions"},
    {"name": "Holt",     "shop": "Holt's Outfitters"},
    {"name": "Venna",    "shop": "Venna's Curiosities"},
    {"name": "Bram",     "shop": "Bram's Forge"},
    {"name": "Sigrid",   "shop": "Sigrid's Sundries"},
    {"name": "Torvin",   "shop": "Torvin's Wares"},
    {"name": "Lira",     "shop": "Lira's Trading Post"},
]

_SHOPKEEP_DIALOGUE_POOL = [
    [
        "Welcome to {shop}!",
        "I've got the finest steel this side of the mountains.",
        "Swords, axes, bows -- you name it, I forge it.",
        "Come back when you've got more gold!",
    ],
    [
        "Step right in! {shop} has everything you need.",
        "Potions, scrolls, provisions -- take your pick.",
        "Fair prices for honest folk.",
        "Safe travels, adventurer!",
    ],
    [
        "Ah, customers! Welcome to {shop}.",
        "You won't find better quality anywhere else.",
        "Every item here has been tested in the field.",
        "Gold well spent is gold well earned!",
    ],
]

_INNKEEPER_POOL = [
    {"name": "Bertram",  "inn": "The Sleeping Griffin"},
    {"name": "Aldric",   "inn": "The Brass Lantern"},
    {"name": "Roslyn",   "inn": "The Copper Kettle"},
    {"name": "Gareth",   "inn": "The Wanderer's Rest"},
    {"name": "Nessa",    "inn": "The Silver Stag"},
    {"name": "Doric",    "inn": "The Hearthstone"},
    {"name": "Pella",    "inn": "The Rusty Anchor"},
    {"name": "Orin",     "inn": "The Howling Wind"},
]

_INNKEEPER_DIALOGUE_POOL = [
    [
        "Welcome to {inn} Inn!",
        "Rest your weary bones. A room is 10 gold per night.",
        "I hear strange things stir in the wilds...",
        "Can I get you an ale?",
    ],
    [
        "Come in, come in! {inn} is the warmest spot in town.",
        "Hot stew and a soft bed -- what more could you want?",
        "Travelers bring all sorts of stories through here.",
        "Stay as long as you like!",
    ],
    [
        "Ah, adventurers! {inn} welcomes you.",
        "You look like you could use a good meal.",
        "The roads have been dangerous lately, I hear.",
        "Rest well -- you'll need your strength.",
    ],
]

_INNKEEPER_QUEST_POOL = [
    {
        "dialogue": [
            "Psst... adventurer! I've heard rumors of a strange crystal hidden in a nearby dungeon.",
            "It radiates dark energy and threatens our town. Will you seek it out and bring it back?",
        ],
        "choices": ["Yes, I'll find it!", "Not right now."],
        "quest_name": "The Shadow Crystal",
        "artifact_name": "Shadow Crystal",
        "hint_active": "Have you found the Shadow Crystal yet? It's out there somewhere...",
        "text_complete": "The Shadow Crystal sits safely behind my counter. You've earned a hero's welcome here!",
    },
    {
        "dialogue": [
            "Listen... a merchant's amulet was stolen and hidden deep in a dungeon nearby.",
            "It's a powerful relic and dangerous in the wrong hands. Could you retrieve it?",
        ],
        "choices": ["I'll look into it.", "Maybe later."],
        "quest_name": "The Merchant's Amulet",
        "artifact_name": "Merchant's Amulet",
        "hint_active": "Any sign of the Merchant's Amulet? I heard the dungeon is treacherous...",
        "text_complete": "The Merchant's Amulet is back where it belongs. You have my deepest thanks!",
    },
    {
        "dialogue": [
            "I shouldn't say this, but... something's been poisoning our well water.",
            "A cursed relic in the ruins nearby is the source. Can you recover it before it's too late?",
        ],
        "choices": ["I'll check it out.", "Not my problem."],
        "quest_name": "The Cursed Relic",
        "artifact_name": "Cursed Relic",
        "hint_active": "Our well water grows darker by the day. Please hurry and find that relic!",
        "text_complete": "The Cursed Relic is safely contained. The well water is already clearing up!",
    },
]

_ELDER_POOL = [
    "Elder Morath", "Elder Gwynn", "Elder Fenn", "Elder Bera",
    "Elder Cato", "Elder Sybil", "Elder Rowan", "Elder Petra",
]

_ELDER_DIALOGUE_POOL = [
    [
        "Ah, brave adventurers! Our town faces dark times.",
        "Ancient evils stir in the dungeons beneath the land.",
        "Seek out the hidden dangers before they find us.",
        "I sense great potential in you. Do not lose hope.",
    ],
    [
        "Welcome, travelers. I am the keeper of this town's history.",
        "These lands were peaceful once, before the darkness came.",
        "Be wary of the wilds -- not all creatures are friendly.",
        "May fortune smile upon your journey.",
    ],
    [
        "You carry the look of adventurers. Good -- we need heroes.",
        "Our scouts report growing dangers in every direction.",
        "The ancient wards are failing. Something must be done.",
        "I pray you have the courage to see this through.",
    ],
]

_QUEST_GIVER_POOL = [
    "Alaric the Wanderer", "Seraphina", "Old Bartholomew", "Mirabel",
    "Captain Drake", "Sage Elara", "Brother Aldric", "Dame Isolde",
    "Wanderer Kael", "Mystic Theron", "Lady Revenna", "Fen the Bold",
]

_VILLAGER_NAME_POOL = [
    "Tomas", "Elena", "Joric", "Bess", "Finn", "Lysa", "Karl",
    "Maren", "Pieter", "Wren", "Dorin", "Hanna", "Sven", "Ida",
    "Calla", "Rodric", "Thea", "Birk", "Ona", "Leif",
]

_VILLAGER_DIALOGUE_POOL = [
    ["Beautiful day, isn't it?", "Watch out for wolves in the forest."],
    ["I lost my cat somewhere near the mountains...", "Have you seen a tabby?"],
    ["The elder seems worried lately.", "Something about the dungeons."],
    ["I used to be an adventurer, you know.", "Then I took an arrow to the knee."],
    ["The harvest was good this year.", "But strange lights appear at night..."],
    ["My grandmother tells tales of ancient heroes.", "Maybe you'll be one someday!"],
    ["The road north has been dangerous lately.", "Stick to the main paths."],
    ["I heard a merchant selling rare herbs.", "Worth checking the shop."],
    ["The inn serves the best stew in the region!", "You should try it."],
    ["Don't wander too far from town after dark.", "Things lurk in the shadows."],
    ["The blacksmith makes fine blades.", "But they don't come cheap."],
    ["Have you heard about the old ruins?", "They say treasure lies within."],
]

# ── NPC pools for optional buildings ─────────────────────────────
_OPTIONAL_BUILDING_NPCS = {
    "reagent_shop": {
        "names": ["Sage Willa", "Herbalist Fen", "Alchemist Rowe",
                   "Apothecary Nell"],
        "dialogues": [
            [
                "Welcome to the Reagent Shop!",
                "I have rare herbs and spell components.",
                "Wizards and clerics swear by my stock.",
                "Need bat wings? Moonstone dust? I've got it all.",
            ],
            [
                "Come in! Fresh reagents, just gathered.",
                "These components enhance any spell.",
                "Handle the nightshade carefully, if you please.",
                "Good luck on your adventures!",
            ],
        ],
        "npc_type": "shopkeep",
    },
    "potion_shop": {
        "names": ["Elixia", "Master Dram", "Brewer Cask", "Vial"],
        "dialogues": [
            [
                "Potions for every ailment!",
                "Health potions, mana tonics, antidotes...",
                "My brews are the finest in the land.",
                "Drink responsibly!",
            ],
            [
                "Step into the Potion Emporium!",
                "Every potion is brewed fresh daily.",
                "Need something for the road? I've got you covered.",
                "Come back anytime!",
            ],
        ],
        "npc_type": "shopkeep",
    },
    "weapons_shop": {
        "names": ["Ironhand", "Steelforge Gorm", "Blademaiden Yara",
                   "Whetstone Dirk"],
        "dialogues": [
            [
                "Welcome to the Weapon Forge!",
                "Swords, axes, maces -- forged with care.",
                "Every blade is tested before it leaves my shop.",
                "Arm yourself well, adventurer!",
            ],
            [
                "Looking for steel? You've come to the right place.",
                "I forge weapons that can cut through shadow itself.",
                "Quality steel isn't cheap, but it'll save your life.",
                "Choose wisely!",
            ],
        ],
        "npc_type": "shopkeep",
    },
    "armor_shop": {
        "names": ["Platewright", "Tanner Husk", "Shieldmaiden Bryn",
                   "Armorer Keld"],
        "dialogues": [
            [
                "Welcome to the Armor Shop!",
                "Leather, chain, plate -- I've got it all.",
                "A good shield is worth its weight in gold.",
                "Don't go into a dungeon unprotected!",
            ],
            [
                "Step in! Let me fit you for some proper armor.",
                "My chainmail has saved many a life.",
                "The monsters out there don't pull their punches.",
                "Invest in defense -- it pays off.",
            ],
        ],
        "npc_type": "shopkeep",
    },
    "book_shop": {
        "names": ["Scribe Lorewick", "Inkwell", "Sage Pagelore",
                   "Librarian Quill"],
        "dialogues": [
            [
                "Welcome to the Book Shop!",
                "Spell tomes, histories, bestiaries...",
                "Knowledge is the greatest weapon of all.",
                "Browse to your heart's content!",
            ],
            [
                "Ah, a fellow seeker of knowledge!",
                "I have rare texts from across the realms.",
                "Some of these books contain powerful secrets.",
                "Handle the ancient ones with care!",
            ],
        ],
        "npc_type": "shopkeep",
    },
    "map_shop": {
        "names": ["Cartographer Finn", "Explorer Maris", "Mapmaker Gale",
                   "Navigator Thorn"],
        "dialogues": [
            [
                "Welcome! Need a map of the region?",
                "I've charted every trail and dungeon entrance.",
                "A good map can be the difference between life and death.",
                "The wilds hold many secrets -- my maps reveal them.",
            ],
            [
                "Maps! Charts! Surveys of the land!",
                "I've explored every corner of this region.",
                "Want to know where the dungeons are? Ask me.",
                "Safe travels, adventurer!",
            ],
        ],
        "npc_type": "shopkeep",
    },
    "town_hall": {
        "names": ["Mayor Aldwyn", "Reeve Selene", "Magistrate Horace",
                   "Councilor Petra"],
        "dialogues": [
            [
                "Welcome to the Town Hall.",
                "I oversee the affairs of this settlement.",
                "If you seek quests, speak to the townsfolk.",
                "We're grateful for any help against the darkness.",
            ],
            [
                "Greetings, adventurer. This is the seat of government.",
                "Our records show increasing monster activity nearby.",
                "The town's coffers are thin, but we offer what we can.",
                "Speak with me if you need information about the area.",
            ],
        ],
        "npc_type": "elder",
    },
    "tavern": {
        "names": ["Barkeep Rudo", "Tavernmaster Ivy", "Brewmaster Ogg",
                   "Bard Celeste"],
        "dialogues": [
            [
                "Welcome to the tavern! Pull up a chair!",
                "We've got ale, wine, and stories aplenty.",
                "The bard plays every evening -- don't miss it!",
                "Drink up and enjoy the music!",
            ],
            [
                "Come in from the cold! Drinks are on tap.",
                "Travelers share the best tales in here.",
                "I've heard rumors of treasure in the old ruins...",
                "Enjoy yourself -- you've earned a rest!",
            ],
        ],
        "npc_type": "villager",
    },
}


def _find_open_floor_spot(tmap, npcs, ox, oy, iw, ih, rng,
                          min_x=2, min_y=2, size_w=4, size_h=4):
    """Find a position for a small building that fits on open floor.

    Returns (col, row) of the top-left corner, or None if no spot found.
    The building footprint is size_w × size_h.
    """
    occupied_npc = {(n.col, n.row) for n in npcs}
    candidates = []
    # Scan the interior for positions where the full building fits on floor
    for by in range(oy + min_y, oy + ih - size_h - 1):
        for bx in range(ox + min_x, ox + iw - size_w - 1):
            fits = True
            for dr in range(size_h):
                for dc in range(size_w):
                    tc, tr = bx + dc, by + dr
                    tile = tmap.get_tile(tc, tr)
                    if tile != TILE_FLOOR:
                        fits = False
                        break
                    if (tc, tr) in occupied_npc:
                        fits = False
                        break
                if not fits:
                    break
            if fits:
                candidates.append((bx, by))
    if not candidates:
        return None
    return rng.choice(candidates)


# Display names for optional building types
_OPTIONAL_BUILDING_LABELS = {
    "reagent_shop":  "Reagents",
    "potion_shop":   "Potions",
    "weapons_shop":  "Weapons",
    "armor_shop":    "Armor",
    "book_shop":     "Books",
    "map_shop":      "Maps",
    "town_hall":     "Town Hall",
    "tavern":        "Tavern",
}

# Layout variants for optional buildings — each is (width, height,
# counter_offsets, npc_offset, door_side).  Cycled through so
# adjacent buildings look different.
_OPT_BUILDING_LAYOUTS = [
    # wide counter at top
    (6, 5, [(1, 1), (2, 1), (3, 1)], (2, 3), "south"),
    # L-shaped counter
    (6, 5, [(1, 1), (2, 1), (1, 2)], (3, 3), "south"),
    # counter on the right
    (6, 5, [(4, 1), (4, 2), (4, 3)], (2, 2), "south"),
    # compact counter in middle
    (6, 5, [(2, 2), (3, 2)], (3, 3), "south"),
]


def _place_optional_buildings(tmap, npcs, ox, oy, iw, ih,
                              building_keys, rng, building_signs=None):
    """Place optional buildings and their NPCs in the town.

    Each optional building is a 6×5 structure placed on open floor.
    A shopkeeper or thematic NPC is placed inside.  Different buildings
    get varied interior layouts.
    """
    layout_idx = 0
    for bkey in building_keys:
        if bkey == "shrine":
            # Shrine is the same as the existing temple — already placed
            # by the base layout, so skip it.
            continue

        npc_pool = _OPTIONAL_BUILDING_NPCS.get(bkey)
        if not npc_pool:
            continue

        # Pick a layout variant for this building
        blayout = _OPT_BUILDING_LAYOUTS[layout_idx % len(_OPT_BUILDING_LAYOUTS)]
        bw, bh = blayout[0], blayout[1]
        layout_idx += 1

        # Find a spot for the building
        spot = _find_open_floor_spot(tmap, npcs, ox, oy, iw, ih, rng,
                                     min_x=1, min_y=1,
                                     size_w=bw, size_h=bh)
        if spot is None:
            continue  # not enough room — skip this building

        bx, by = spot
        _place_building(tmap, bx, by, bw, bh, door_side=blayout[4])
        # Place counters from the layout
        for dc, dr in blayout[2]:
            tmap.set_tile(bx + dc, by + dr, TILE_COUNTER)

        # Create the NPC inside the building
        npc_name = rng.choice(npc_pool["names"])
        npc_dlg = list(rng.choice(npc_pool["dialogues"]))
        npc_type = npc_pool["npc_type"]
        npc_col = bx + blayout[3][0]
        npc_row = by + blayout[3][1]
        npcs.append(NPC(npc_col, npc_row, npc_name, npc_dlg,
                        npc_type=npc_type))

        # Record building sign
        if building_signs is not None:
            label = _OPTIONAL_BUILDING_LABELS.get(bkey, bkey.replace("_", " ").title())
            building_signs.append({
                "text": label,
                "row": by,       # top wall
                "col": bx,
                "width": bw,
            })


# Building layout variants — each defines building positions and door sides
# relative to the interior origin (ox, oy).  Format per building:
#   (x, y, w, h, door_side, counter_tiles, altar_pos_or_None)
# 8 variants give <2% chance of identical layout with 2 towns.
_LAYOUT_POOL = [
    {   # 0 — classic: shop top-left, inn top-right, temple bottom-left
        "name": "classic",
        "shop":   (1,  1,  6, 5, "south",  [(3, 2), (4, 2), (5, 2)]),
        "inn":    (11, 1,  6, 5, "south",  [(13, 2), (14, 2)]),
        "temple": (1,  12, 6, 5, "east",   [], (3, 14)),
    },
    {   # 1 — mirrored: shop top-right, inn top-left, temple bottom-right
        "name": "mirrored",
        "shop":   (11, 1,  6, 5, "south",  [(13, 2), (14, 2), (15, 2)]),
        "inn":    (1,  1,  6, 5, "south",  [(3, 2), (4, 2)]),
        "temple": (11, 12, 6, 5, "west",   [], (14, 14)),
    },
    {   # 2 — central temple at bottom-centre
        "name": "central_temple",
        "shop":   (1,  1,  6, 5, "south",  [(3, 2), (4, 2), (5, 2)]),
        "inn":    (11, 1,  6, 5, "south",  [(13, 2), (14, 2)]),
        "temple": (6,  12, 6, 5, "south",  [], (9, 14)),
    },
    {   # 3 — L-shape: shop top-left, inn mid-left, temple bottom-right
        "name": "L_shape",
        "shop":   (1,  1,  6, 5, "south",  [(3, 2), (4, 2), (5, 2)]),
        "inn":    (1,  8,  6, 5, "east",   [(3, 9), (4, 9)]),
        "temple": (11, 12, 6, 5, "west",   [], (14, 14)),
    },
    {   # 4 — temple north: temple top-centre, shops below on sides
        "name": "temple_north",
        "shop":   (1,  8,  6, 5, "south",  [(3, 9), (4, 9), (5, 9)]),
        "inn":    (11, 8,  6, 5, "south",  [(13, 9), (14, 9)]),
        "temple": (6,  1,  6, 5, "south",  [], (9, 3)),
    },
    {   # 5 — corridor: all three buildings along the left wall
        "name": "corridor",
        "shop":   (1,  1,  6, 5, "east",   [(3, 2), (4, 2), (5, 2)]),
        "inn":    (1,  7,  6, 5, "east",   [(3, 8), (4, 8)]),
        "temple": (1,  13, 6, 5, "east",   [], (3, 15)),
    },
    {   # 6 — courtyard: buildings form a U around the open centre
        "name": "courtyard",
        "shop":   (1,  1,  7, 5, "south",  [(3, 2), (4, 2), (5, 2), (6, 2)]),
        "inn":    (10, 1,  7, 5, "south",  [(12, 2), (13, 2), (14, 2)]),
        "temple": (5,  13, 8, 5, "north",  [], (9, 15)),
    },
    {   # 7 — diagonal: buildings staggered diagonally
        "name": "diagonal",
        "shop":   (1,  1,  6, 5, "south",  [(3, 2), (4, 2), (5, 2)]),
        "inn":    (6,  7,  6, 5, "south",  [(8, 8), (9, 8)]),
        "temple": (11, 13, 6, 5, "west",   [], (14, 15)),
    },
]


def generate_town(name="Thornwall", seed=None, layout_index=None,
                   has_key_dungeons=False, innkeeper_quests=False,
                   gnome_machine=False, keys_needed=0,
                   town_config=None):
    """
    Generate a town map with NPCs and an exit.

    Each town is procedurally varied based on *seed*: different building
    layout, NPC names, dialogue, shop themes, and god names.  Two towns
    with different seeds will look and feel distinct.

    *layout_index* — if provided, selects a specific layout from
    ``_LAYOUT_POOL`` (modulo pool size).  When the caller passes the
    town's ordinal index (0, 1, 2, …), every town in a module is
    guaranteed a different base layout (up to 8 towns before wrapping).
    If *None*, the layout is chosen randomly from the seed.

    *town_config* — optional dict with keys ``size`` (small/medium/large),
    ``style`` (medieval/desert/coastal/forest/mountain), and ``buildings``
    (list of optional building keys like ``"tavern"``, ``"weapons_shop"``).
    When *None*, defaults are used.

    The playable interior is surrounded by a brick wall border.  The total
    map is padded with extra wall tiles on every side so the camera
    (25×17 viewport) never sees out-of-bounds areas.
    """
    if seed is None:
        seed = hash(name) & 0xFFFFFFFF
    rng = random.Random(seed)

    # Parse town config
    if town_config is None:
        town_config = {}
    town_size = town_config.get("size", "medium")
    town_style = town_config.get("style", "medieval")
    optional_buildings = town_config.get("buildings", [])

    # Playable interior dimensions based on size setting
    # Gnome machine towns get extra space regardless
    _SIZE_DIMS = {
        "small":  (14, 15),
        "medium": (18, 19),
        "large":  (24, 26),
    }
    base_w, base_h = _SIZE_DIMS.get(town_size, (18, 19))
    if gnome_machine:
        # Ensure enough room for the machine square
        INTERIOR_W = max(base_w, 24)
        INTERIOR_H = max(base_h, 26)
    else:
        INTERIOR_W = base_w
        INTERIOR_H = base_h

    PAD_X = 13
    PAD_Y = 9

    W = INTERIOR_W + 2 + PAD_X * 2
    H = INTERIOR_H + 2 + PAD_Y * 2

    BORDER_X = PAD_X
    BORDER_Y = PAD_Y
    BORDER_W = INTERIOR_W + 2
    BORDER_H = INTERIOR_H + 2

    tmap = TileMap(W, H, default_tile=TILE_GRASS)

    # --- Single-row brick wall border around the town ---
    for col in range(BORDER_X, BORDER_X + BORDER_W):
        tmap.set_tile(col, BORDER_Y, TILE_WALL)                # top
        tmap.set_tile(col, BORDER_Y + BORDER_H - 1, TILE_WALL) # bottom
    for row in range(BORDER_Y, BORDER_Y + BORDER_H):
        tmap.set_tile(BORDER_X, row, TILE_WALL)                # left
        tmap.set_tile(BORDER_X + BORDER_W - 1, row, TILE_WALL) # right

    # --- Floor inside the brick border ---
    for row in range(BORDER_Y + 1, BORDER_Y + BORDER_H - 1):
        for col in range(BORDER_X + 1, BORDER_X + BORDER_W - 1):
            tmap.set_tile(col, row, TILE_FLOOR)

    # --- Exit gate (bottom centre of the brick border) ---
    exit_col = BORDER_X + BORDER_W // 2
    exit_row = BORDER_Y + BORDER_H - 1
    tmap.set_tile(exit_col, exit_row, TILE_EXIT)

    ox = BORDER_X + 1
    oy = BORDER_Y + 1

    # --- Pick a building layout ---
    # If a layout_index is given, use it (guarantees unique layouts per
    # town ordinal).  Otherwise fall back to seed-based random choice.
    if layout_index is not None:
        layout = _LAYOUT_POOL[layout_index % len(_LAYOUT_POOL)]
    else:
        layout = rng.choice(_LAYOUT_POOL)

    # ── Building signs — collect as we place buildings ──
    building_signs = []

    # Shop — clamp position to fit interior
    sx, sy, sw, sh, sdoor, scounters = layout["shop"]
    sx, sy, scounters, _ = _clamp_building(
        sx, sy, sw, sh, INTERIOR_W, INTERIOR_H, scounters)
    _place_building(tmap, ox + sx, oy + sy, sw, sh, door_side=sdoor)
    for cx, cy in scounters:
        tmap.set_tile(ox + cx, oy + cy, TILE_COUNTER)
    building_signs.append({
        "text": "General Store",
        "row": oy + sy,
        "col": ox + sx,
        "width": sw,
    })

    # Inn — clamp position to fit interior
    ix, iy, iw, ih, idoor, icounters = layout["inn"]
    ix, iy, icounters, _ = _clamp_building(
        ix, iy, iw, ih, INTERIOR_W, INTERIOR_H, icounters)
    _place_building(tmap, ox + ix, oy + iy, iw, ih, door_side=idoor)
    for cx, cy in icounters:
        tmap.set_tile(ox + cx, oy + cy, TILE_COUNTER)
    building_signs.append({
        "text": "Inn",
        "row": oy + iy,
        "col": ox + ix,
        "width": iw,
    })

    # Temple — clamp position to fit interior
    temple_data = layout["temple"]
    tx, ty, tw, th, tdoor = temple_data[:5]
    _tcounters = temple_data[5] if len(temple_data) > 5 else []
    altar_pos = temple_data[6] if len(temple_data) > 6 else None
    tx, ty, _tcounters, altar_pos = _clamp_building(
        tx, ty, tw, th, INTERIOR_W, INTERIOR_H, _tcounters, altar_pos)
    _place_building(tmap, ox + tx, oy + ty, tw, th, door_side=tdoor)
    if altar_pos:
        tmap.set_tile(ox + altar_pos[0], oy + altar_pos[1], TILE_ALTAR)
    building_signs.append({
        "text": "Temple",
        "row": oy + ty,
        "col": ox + tx,
        "width": tw,
    })

    # --- Pick unique NPCs from pools ---
    npcs = []

    # Priest
    priest = rng.choice(_PRIEST_POOL)
    priest_dlg_template = rng.choice(_PRIEST_DIALOGUE_POOL)
    priest_dlg = [line.format(title=priest["title"], god=priest["god"])
                  for line in priest_dlg_template]
    # Place priest near altar (or inside temple)
    if altar_pos:
        priest_col, priest_row = ox + altar_pos[0] + 1, oy + altar_pos[1]
    else:
        priest_col, priest_row = ox + tx + tw // 2, oy + ty + th // 2
    npcs.append(NPC(priest_col, priest_row, priest["name"],
                    priest_dlg, npc_type="priest", god_name=priest["god"]))

    # Shopkeeper (inside the shop, behind the counter)
    shopkeep = rng.choice(_SHOPKEEP_POOL)
    shop_dlg_template = rng.choice(_SHOPKEEP_DIALOGUE_POOL)
    shop_dlg = [line.format(shop=shopkeep["shop"])
                for line in shop_dlg_template]
    shopkeep_col = ox + sx + sw // 2
    shopkeep_row = oy + sy + sh - 2
    npcs.append(NPC(shopkeep_col, shopkeep_row, shopkeep["name"],
                    shop_dlg, npc_type="shopkeep"))

    # Innkeeper (inside the inn, behind the bar)
    # When innkeeper_quests is True, the innkeeper offers an endless
    # supply of randomly generated quests.  When False AND the module
    # has key dungeons, the innkeeper just runs the inn.
    innkeeper = rng.choice(_INNKEEPER_POOL)
    inn_dlg_template = rng.choice(_INNKEEPER_DIALOGUE_POOL)
    inn_dlg = [line.format(inn=innkeeper["inn"])
               for line in inn_dlg_template]
    innkeeper_col = ox + ix + iw // 2
    innkeeper_row = oy + iy + ih - 2
    if has_key_dungeons and not innkeeper_quests:
        npcs.append(NPC(innkeeper_col, innkeeper_row, innkeeper["name"],
                        inn_dlg, npc_type="innkeeper"))
    else:
        quest = rng.choice(_INNKEEPER_QUEST_POOL)
        npcs.append(NPC(innkeeper_col, innkeeper_row, innkeeper["name"],
                        inn_dlg, npc_type="innkeeper",
                        quest_dialogue=quest["dialogue"],
                        quest_choices=quest["choices"],
                        quest_name=quest.get("quest_name"),
                        artifact_name=quest.get("artifact_name"),
                        hint_active=quest.get("hint_active"),
                        text_complete=quest.get("text_complete"),
                        innkeeper_quests=innkeeper_quests))

    # Town elder (in the open area, middle of the map)
    elder_name = rng.choice(_ELDER_POOL)
    elder_dlg = list(rng.choice(_ELDER_DIALOGUE_POOL))
    # Insert the town name into the first line
    elder_dlg[0] = elder_dlg[0].replace("Our town", f"{name}")
    # Position scales with interior — stays in the open area
    elder_x = ox + INTERIOR_W // 2
    elder_y = oy + min(10, INTERIOR_H // 2)
    npcs.append(NPC(elder_x, elder_y, elder_name,
                    elder_dlg, npc_type="elder"))

    # Wandering villagers (3, each with unique name and dialogue)
    available_names = list(_VILLAGER_NAME_POOL)
    rng.shuffle(available_names)
    available_dlgs = list(_VILLAGER_DIALOGUE_POOL)
    rng.shuffle(available_dlgs)

    # Villager positions vary by seed — jitter within safe floor area
    # Scale with interior size so they don't bunch up in larger towns
    v_mid_y = min(15, INTERIOR_H - 4)
    v_top_y = min(8, INTERIOR_H // 3)
    _base_spots = [(5, v_mid_y),
                   (INTERIOR_W - 5, v_mid_y),
                   (INTERIOR_W // 2, v_top_y)]
    villager_spots = [
        (ox + bx + rng.randint(-1, 1), oy + by + rng.randint(-1, 1))
        for bx, by in _base_spots
    ]
    for i, (vc, vr) in enumerate(villager_spots):
        vname = available_names[i % len(available_names)]
        vdlg = available_dlgs[i % len(available_dlgs)]
        npcs.append(NPC(vc, vr, vname, vdlg, npc_type="villager"))

    # ── Optional buildings from town_config ──
    # Place additional buildings and their NPCs on open floor space.
    _place_optional_buildings(tmap, npcs, ox, oy, INTERIOR_W, INTERIOR_H,
                              optional_buildings, rng,
                              building_signs=building_signs)

    # ── Ensure every door is reachable ──
    # Buildings may overlap or optional buildings may seal off a core
    # building's door.  This pass uses flood-fill from the entry point
    # and carves short paths through walls to connect any isolated doors.
    _ensure_all_doors_accessible(tmap, exit_col, exit_row - 1)

    # ── Optional gnome machine (for "Gnome Machine" quest style) ──
    # The expanded town (24×26) has a dedicated open town square in the
    # lower-centre area (below the buildings) where the machine sits.
    # The gnome NPC stands to the right of the machine with guaranteed
    # clear floor tiles so the player can always reach him.
    if gnome_machine:
        # Town square centre — well below the building zone
        sq_cx = ox + INTERIOR_W // 2     # horizontal centre
        sq_cy = oy + INTERIOR_H - 5      # 5 tiles from the bottom wall

        # Clear a 7×5 floor area around the square centre to guarantee
        # no stray wall/counter tiles from building layouts overlap
        for dr in range(-2, 3):
            for dc in range(-3, 4):
                tmap.set_tile(sq_cx + dc, sq_cy + dr, TILE_FLOOR)

        # Machine at the square centre
        mc, mr = sq_cx, sq_cy
        tmap.set_tile(mc, mr, TILE_MACHINE)

        # Key slot ring around the machine (decorative)
        key_total = max(1, min(8, keys_needed))
        slot_offsets = [(-1, 0), (1, 0), (0, -1), (0, 1),
                        (-1, -1), (1, -1), (-1, 1), (1, 1)]
        for si in range(min(key_total, len(slot_offsets))):
            sc = mc + slot_offsets[si][0]
            sr = mr + slot_offsets[si][1]
            tmap.set_tile(sc, sr, TILE_KEYSLOT)

        # Gnome NPC — quest-giver, stands 3 tiles right of the machine
        # with guaranteed open floor around him
        gnome_col = mc + 3
        gnome_row = mr
        gnome_name = rng.choice(["Fizzwick", "Tinkleton", "Cogsworth",
                                 "Sprocket", "Wizzle", "Ratchet"])
        gnome_dlg = [
            f"I built this machine to channel the ancient energy...",
            f"But it needs {key_total} keys to function!",
            f"The keys are scattered across the dungeons of the land.",
            f"Please, bring me the keys!",
        ]
        gnome_quest_dlg = [
            f"Adventurers! I am {gnome_name}, and I need your help.",
            f"My machine requires {key_total} keys hidden in "
            f"dungeons across the land.",
            f"Each one is guarded by fearsome creatures.",
            f"Will you help me recover them?",
        ]
        npcs.append(NPC(gnome_col, gnome_row, gnome_name, gnome_dlg,
                        npc_type="gnome",
                        quest_dialogue=gnome_quest_dlg,
                        quest_choices=["We'll find the keys!",
                                       "Not right now."]))

    # Entry point: just inside the exit gate
    entry_col = exit_col
    entry_row = exit_row - 1

    return TownData(tmap, npcs, name, entry_col, entry_row,
                    town_style=town_style,
                    building_signs=building_signs)


def add_quest_giver_npc(town_data, quest_giver_name, dungeon_key_str,
                        dungeon_name, quest_hint, quest_objective,
                        quest_type, seed=0):
    """Inject a quest-giver NPC into an existing town.

    The NPC is placed on an open floor tile near the town centre.  It
    holds exactly one quest (identified by *dungeon_key_str*, a string
    like ``"5,10"``).  When the player accepts the quest, only that
    single key dungeon is revealed.

    Parameters
    ----------
    town_data : TownData
    quest_giver_name : str   – NPC display name
    dungeon_key_str : str    – ``"col,row"`` key into ``game.key_dungeons``
    dungeon_name : str       – display name of the dungeon
    quest_hint : str         – hint shown in quest dialogue
    quest_objective : str    – objective text (for kill quests)
    quest_type : str         – ``"retrieve"`` or ``"kill"``
    seed : int               – for deterministic position jitter
    """
    rng = random.Random(seed)
    tmap = town_data.tile_map
    occupied = {(n.col, n.row) for n in town_data.npcs}
    occupied.add((town_data.entry_col, town_data.entry_row))

    # Try to find an open floor tile near the centre of town
    cx = tmap.width // 2
    cy = tmap.height // 2
    placed = None
    for ring in range(0, 10):
        candidates = []
        for dc in range(-ring, ring + 1):
            for dr in range(-ring, ring + 1):
                if ring > 0 and max(abs(dc), abs(dr)) != ring:
                    continue
                c, r = cx + dc, cy + dr
                if (0 <= c < tmap.width and 0 <= r < tmap.height
                        and tmap.get_tile(c, r) == TILE_FLOOR
                        and (c, r) not in occupied):
                    candidates.append((c, r))
        if candidates:
            placed = rng.choice(candidates)
            break
    if placed is None:
        # Absolute fallback — just put them at town centre
        placed = (cx, cy)

    col, row = placed

    # Build quest-offer dialogue
    if quest_type == "kill" and quest_objective:
        q_dialogue = [
            f"I've been searching for someone brave enough to help.",
            f"In the {dungeon_name}, you must {quest_objective}. {quest_hint}",
            f"Will you take on this challenge?",
        ]
    else:
        q_dialogue = [
            f"I've been searching for someone brave enough to help.",
            f"The {dungeon_name} holds a powerful artifact. {quest_hint}",
            f"Will you seek it out and bring it back?",
        ]

    ambient = [
        "The world needs heroes like you.",
        "I sense great potential in your party.",
        "Be wary of the dangers that lurk in the dungeons.",
    ]

    npc = NPC(col, row, quest_giver_name, ambient,
              npc_type="quest_giver",
              quest_dialogue=q_dialogue,
              quest_choices=["Yes, we'll do it!", "Not right now."])
    # Store which dungeon this quest-giver reveals
    npc.dungeon_key_str = dungeon_key_str
    npc.dungeon_name = dungeon_name
    town_data.npcs.append(npc)
    return npc


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

    tmap = TileMap(W, H, default_tile=TILE_GRASS)

    # --- Single-row brick wall border around the town ---
    for col in range(BORDER_X, BORDER_X + BORDER_W):
        tmap.set_tile(col, BORDER_Y, TILE_WALL)                # top
        tmap.set_tile(col, BORDER_Y + BORDER_H - 1, TILE_WALL) # bottom
    for row in range(BORDER_Y, BORDER_Y + BORDER_H):
        tmap.set_tile(BORDER_X, row, TILE_WALL)                # left
        tmap.set_tile(BORDER_X + BORDER_W - 1, row, TILE_WALL) # right

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

    # ── Temple of Lunara (lower-centre, 6×5, door north) ──
    _place_building(tmap, ox + 11, oy + 18, 6, 5, door_side="north")
    # Altar inside the temple
    tmap.set_tile(ox + 13, oy + 20, TILE_ALTAR)

    # ── Small cottage A (lower-mid-left, 4×4, door south) ──
    _place_building(tmap, ox + 8, oy + 18, 4, 4, door_side="south")

    # ── Small cottage B (lower-mid-right, 4×4, door south) ──
    _place_building(tmap, ox + 18, oy + 18, 4, 4, door_side="south")

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

    # ── Temple Priestess ──
    npcs.append(NPC(ox + 14, oy + 20, "Sister Vesper", [
        "Welcome to the Temple of Lunara, traveler.",
        "Even in this endless night, the moon watches over us.",
        "We offer healing and resurrection to those in need.",
        "May Lunara's silver light guide you through the dark.",
    ], npc_type="priest", god_name="Lunara"))

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
