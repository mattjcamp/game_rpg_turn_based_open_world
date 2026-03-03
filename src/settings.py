"""
Game settings and constants.

All tunable values live here so they're easy to find and change.
"""

# ----- Display -----
SCREEN_WIDTH = 960
SCREEN_HEIGHT = 736
TILE_SIZE = 32          # Each tile is 32x32 pixels
FPS = 60
GAME_TITLE = "Realm of Shadow - An Ultima III Inspired RPG"

# ----- Viewport -----
# How many tiles visible on screen at once
VIEWPORT_COLS = SCREEN_WIDTH // TILE_SIZE   # 30
VIEWPORT_ROWS = SCREEN_HEIGHT // TILE_SIZE  # 26

# ----- Movement -----
# Delay (in ms) between repeated moves when holding a key
MOVE_REPEAT_DELAY = 150

# ----- Tile IDs -----
# These map to entries in TILE_DEFS below
TILE_GRASS    = 0
TILE_WATER    = 1
TILE_FOREST   = 2
TILE_MOUNTAIN = 3
TILE_TOWN     = 4
TILE_DUNGEON  = 5
TILE_PATH     = 6
TILE_SAND     = 7
TILE_BRIDGE   = 8

# ----- Town-interior tile IDs -----
TILE_FLOOR    = 10
TILE_WALL     = 11
TILE_COUNTER  = 12
TILE_DOOR     = 13
TILE_EXIT     = 14

# ----- Dungeon tile IDs -----
TILE_DFLOOR   = 20
TILE_DWALL    = 21
TILE_STAIRS   = 22
TILE_CHEST    = 23
TILE_TRAP     = 24
TILE_STAIRS_DOWN = 25
TILE_DDOOR    = 26
TILE_ARTIFACT = 27
TILE_PORTAL   = 28
TILE_LOCKED_DOOR = 29

# ----- Tile Definitions -----
# Each tile has: color (RGB), walkable (bool), name (str)
TILE_DEFS = {
    TILE_GRASS:    {"color": (34, 139, 34),   "walkable": True,  "name": "Grass"},
    TILE_WATER:    {"color": (30, 90, 180),   "walkable": False, "name": "Water"},
    TILE_FOREST:   {"color": (0, 80, 0),      "walkable": True,  "name": "Forest"},
    TILE_MOUNTAIN: {"color": (130, 130, 130), "walkable": False, "name": "Mountain"},
    TILE_TOWN:     {"color": (180, 140, 80),  "walkable": True,  "name": "Town"},
    TILE_DUNGEON:  {"color": (120, 40, 80),   "walkable": True,  "name": "Dungeon"},
    TILE_PATH:     {"color": (160, 140, 100), "walkable": True,  "name": "Path"},
    TILE_SAND:     {"color": (210, 190, 130), "walkable": True,  "name": "Sand"},
    TILE_BRIDGE:   {"color": (140, 100, 50),  "walkable": True,  "name": "Bridge"},
    # Town-interior tiles
    TILE_FLOOR:    {"color": (160, 130, 100), "walkable": True,  "name": "Floor"},
    TILE_WALL:     {"color": (90, 70, 50),    "walkable": False, "name": "Wall"},
    TILE_COUNTER:  {"color": (140, 100, 60),  "walkable": False, "name": "Counter"},
    TILE_DOOR:     {"color": (120, 80, 40),   "walkable": True,  "name": "Door"},
    TILE_EXIT:     {"color": (60, 180, 60),   "walkable": True,  "name": "Exit"},
    # Dungeon tiles
    TILE_DFLOOR:   {"color": (50, 45, 40),    "walkable": True,  "name": "Stone Floor"},
    TILE_DWALL:    {"color": (30, 28, 25),    "walkable": False, "name": "Stone Wall"},
    TILE_STAIRS:   {"color": (80, 75, 60),    "walkable": True,  "name": "Stairs Up"},
    TILE_CHEST:    {"color": (50, 45, 40),    "walkable": True,  "name": "Chest"},
    TILE_TRAP:     {"color": (50, 45, 40),    "walkable": True,  "name": "Trap"},
    TILE_STAIRS_DOWN: {"color": (60, 50, 45), "walkable": True, "name": "Stairs Down"},
    TILE_DDOOR:    {"color": (120, 80, 40),  "walkable": True,  "name": "Door"},
    TILE_ARTIFACT: {"color": (200, 180, 50), "walkable": True,  "name": "Artifact"},
    TILE_PORTAL:   {"color": (100, 200, 255), "walkable": True, "name": "Portal"},
    TILE_LOCKED_DOOR: {"color": (100, 60, 30), "walkable": False, "name": "Locked Door"},
}

# ----- Colors (UI) -----
COLOR_BLACK   = (0, 0, 0)
COLOR_WHITE   = (255, 255, 255)
COLOR_YELLOW  = (255, 255, 0)
COLOR_HUD_BG  = (20, 20, 30)
COLOR_HUD_TEXT = (220, 220, 220)

# ----- Party marker -----
PARTY_COLOR = (255, 255, 255)
