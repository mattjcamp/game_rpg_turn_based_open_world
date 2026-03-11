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
                   gnome_machine=False, keys_needed=0):
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

    The playable interior is 18×19 tiles of floor surrounded by a brick wall
    border.  The total map is padded with extra wall tiles on every side so
    the camera (25×17 viewport) never sees out-of-bounds areas.
    """
    if seed is None:
        seed = hash(name) & 0xFFFFFFFF
    rng = random.Random(seed)

    # Playable interior dimensions (floor area inside the walls)
    # Expanded when gnome_machine is True to make room for a town square.
    if gnome_machine:
        INTERIOR_W = 24
        INTERIOR_H = 26
    else:
        INTERIOR_W = 18
        INTERIOR_H = 19

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

    # Shop
    sx, sy, sw, sh, sdoor, scounters = layout["shop"]
    _place_building(tmap, ox + sx, oy + sy, sw, sh, door_side=sdoor)
    for cx, cy in scounters:
        tmap.set_tile(ox + cx, oy + cy, TILE_COUNTER)

    # Inn
    ix, iy, iw, ih, idoor, icounters = layout["inn"]
    _place_building(tmap, ox + ix, oy + iy, iw, ih, door_side=idoor)
    for cx, cy in icounters:
        tmap.set_tile(ox + cx, oy + cy, TILE_COUNTER)

    # Temple
    temple_data = layout["temple"]
    tx, ty, tw, th, tdoor = temple_data[:5]
    _tcounters = temple_data[5] if len(temple_data) > 5 else []
    altar_pos = temple_data[6] if len(temple_data) > 6 else None
    _place_building(tmap, ox + tx, oy + ty, tw, th, door_side=tdoor)
    if altar_pos:
        tmap.set_tile(ox + altar_pos[0], oy + altar_pos[1], TILE_ALTAR)

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
    # The innkeeper only offers a quest when the module has no key
    # dungeons — if the Elder already gives dungeon quests, the
    # innkeeper just runs the inn.
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
