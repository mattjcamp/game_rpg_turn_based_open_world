"""
Renderer - handles all drawing to the screen.

Currently uses colored rectangles for tiles (no sprites yet).
This is intentional: it lets us iterate on gameplay without
worrying about art assets. When we're ready for sprites, we
just swap the draw_tile method.
"""

import math
import os
import random
import pygame

from src.combat_engine import format_modifier
from src.settings import (
    TILE_SIZE, TILE_DEFS, VIEWPORT_COLS, VIEWPORT_ROWS,
    COLOR_BLACK, COLOR_WHITE, COLOR_YELLOW, COLOR_HUD_BG, COLOR_HUD_TEXT,
    PARTY_COLOR, SCREEN_WIDTH, SCREEN_HEIGHT,
    TILE_FLOOR, TILE_WALL, TILE_COUNTER, TILE_DOOR, TILE_EXIT,
    TILE_DFLOOR, TILE_DWALL, TILE_STAIRS, TILE_CHEST, TILE_TRAP,
    TILE_STAIRS_DOWN, TILE_DDOOR, TILE_ARTIFACT, TILE_PORTAL, TILE_LOCKED_DOOR,
    TILE_DUNGEON_CLEARED,
    TILE_PUDDLE, TILE_MOSS, TILE_WALL_TORCH,
)


class Renderer:
    """Draws the game world and UI to a pygame surface."""

    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont("monospace", 18)
        self.font_med = pygame.font.SysFont("monospace", 16)
        self.font_small = pygame.font.SysFont("monospace", 14)
        self._load_class_sprites()
        self._load_tile_sheet()

        # Action panel expand/collapse animation (0.0 = normal, 1.0 = full)
        self._action_panel_expand = 0.0

    def _load_tile_sheet(self):
        """Load U3TilesE.gif and extract individual 16x16 tiles, scaled to 32x32."""
        import os
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        sheet_path = os.path.join(assets_dir, "U3TilesE.gif")

        self._tile_sprites = {}  # (row, col) -> 32x32 pygame surface

        # ── Always initialise tile maps & sprite caches ──
        # (These must exist even when the sprite sheet is missing.)
        self._chest_tile = None
        self._town_gate_tile = None
        self._monster_tiles = {}
        self._npc_sprites = {}
        self._villager_sprites = []
        self._unique_tile_sprites = {}
        self._assets_dir = assets_dir

        from src.settings import (
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
            TILE_TOWN, TILE_DUNGEON, TILE_PATH, TILE_SAND, TILE_BRIDGE,
            TILE_FLOOR, TILE_WALL, TILE_COUNTER, TILE_DOOR, TILE_EXIT,
            TILE_DFLOOR, TILE_DWALL, TILE_CHEST,
        )
        self._overworld_tile_map = {
            TILE_WATER:    (0, 0),
            TILE_GRASS:    (0, 1),
            TILE_FOREST:   (0, 3),
            TILE_MOUNTAIN: (0, 4),
            TILE_DUNGEON:  (0, 5),
            TILE_DUNGEON_CLEARED: (0, 5),   # same sprite, tinted by procedural overlay
            TILE_TOWN:     (0, 6),
            TILE_PATH:     (0, 2),
            TILE_CHEST:    (0, 9),
        }
        self._town_tile_map = {
            TILE_FLOOR:    (0, 1),
            TILE_WALL:     (0, 8),
            TILE_CHEST:    (0, 9),
            TILE_EXIT:     (0, 6),
        }
        self._dungeon_tile_map = {}  # populated below if sheet exists

        if not os.path.exists(sheet_path):
            return

        sheet = pygame.image.load(sheet_path).convert_alpha()
        src_ts = 16  # source tile size
        dst_ts = 32  # destination tile size (our game tile size)
        cols = sheet.get_width() // src_ts   # 16
        rows = sheet.get_height() // src_ts  # 5

        for r in range(rows):
            for c in range(cols):
                tile_surf = sheet.subsurface(
                    pygame.Rect(c * src_ts, r * src_ts, src_ts, src_ts))
                scaled = pygame.transform.scale(tile_surf, (dst_ts, dst_ts))
                self._tile_sprites[(r, c)] = scaled

        # ── Load treasure chest tile from reference doc asset ──
        assets_dir = self._assets_dir
        chest_path = os.path.join(assets_dir, "chest_tile.png")
        if os.path.exists(chest_path):
            raw = pygame.image.load(chest_path).convert_alpha()
            self._chest_tile = pygame.transform.scale(raw, (dst_ts, dst_ts))

        # ── Load town gate tile ──
        gate_path = os.path.join(assets_dir, "town_gate.png")
        if os.path.exists(gate_path):
            raw = pygame.image.load(gate_path).convert_alpha()
            self._town_gate_tile = pygame.transform.scale(raw, (dst_ts, dst_ts))

        # ── Load monster tile sprites from assets ──
        from src.monster import MONSTERS
        for name, data in MONSTERS.items():
            tile_file = data.get("tile")
            if tile_file and tile_file not in self._monster_tiles:
                tile_path = os.path.join(assets_dir, tile_file)
                if os.path.exists(tile_path):
                    raw = pygame.image.load(tile_path).convert_alpha()
                    self._monster_tiles[tile_file] = pygame.transform.scale(
                        raw, (dst_ts, dst_ts))

        # ── Load NPC type sprites from VGA / U4 tiles ──
        npc_sprite_map = {
            "shopkeep":  "steele_tiles/vga_tinker_f1.png",
            "innkeeper": "steele_tiles/vga_bard_f1.png",
            "elder":     "steele_tiles/vga_lord_f1.png",
        }
        villager_files = [
            "steele_tiles/vga_citizen_f1.png",
            "steele_tiles/vga_shepherd_f1.png",
            "steele_tiles/vga_singing_bard_f1.png",
            "steele_tiles/vga_guard_f1.png",
            "steele_tiles/vga_beggar_f1.png",
            "steele_tiles/vga_child_f1.png",
        ]
        for ntype, fname in npc_sprite_map.items():
            npc_path = os.path.join(assets_dir, fname)
            if os.path.exists(npc_path):
                raw = pygame.image.load(npc_path).convert_alpha()
                self._npc_sprites[ntype] = pygame.transform.scale(
                    raw, (dst_ts, dst_ts))
        for fname in villager_files:
            vpath = os.path.join(assets_dir, fname)
            if os.path.exists(vpath):
                raw = pygame.image.load(vpath).convert_alpha()
                self._villager_sprites.append(
                    pygame.transform.scale(raw, (dst_ts, dst_ts)))

    def _get_tile_sprite(self, tile_id):
        """Return the sprite surface for an overworld tile, or None."""
        pos = self._overworld_tile_map.get(tile_id)
        if pos:
            return self._tile_sprites.get(pos)
        return None

    def _load_class_sprites(self):
        """Load character class sprites.

        Primary source: larger Amiga-style sprites in src/assets/.
        Fallback: U4 16×16 tile sprites in src/assets/u4_tiles/ for any
        class that doesn't have an Amiga sprite.  The U4 tiles are scaled
        to 32×32 so they're comparable in size to the Amiga sprites.
        """
        import os
        sprite_dir = os.path.join(os.path.dirname(__file__), "assets")

        # Primary sprites (Amiga-style, ~28-34 px)
        sprite_files = {
            "fighter":     "Ultima3_AMI_sprite_fighter.png",
            "cleric":      "Ultima3_AMI_sprite_cleric.png",
            "wizard":      "Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png",
            "thief":       "Ultima3_AMI_sprite_thief.png",
            "barbarian":   "Ultima3_AMI_sprite_barbarian.png",
        }

        # U4 tile fallbacks for classes without Amiga sprites.
        # Maps class name -> filename in src/assets/u4_tiles/
        u4_tile_dir = os.path.join(os.path.dirname(__file__), "assets", "u4_tiles")
        u4_class_tiles = {
            "alchemist":   "healer_alt_f1.png", # alchemist tile
            "illusionist": "mage.png",           # blue-robed mage
            "druid":       "druid.png",          # red-robed druid
            "paladin":     "paladin.png",        # green-caped paladin
            "ranger":      "ranger.png",         # orange-clad ranger
            "lark":        "bard.png",           # bard (closest to lark)
        }

        self._class_sprites = {}       # class name -> original-size surface
        self._class_sprites_big = {}   # class name -> scaled up for party screen

        # Load primary Amiga sprites
        for cls_name, filename in sprite_files.items():
            path = os.path.join(sprite_dir, filename)
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                self._class_sprites[cls_name] = img
                big = pygame.transform.scale(
                    img, (img.get_width() * 3, img.get_height() * 3))
                self._class_sprites_big[cls_name] = big

        # Load U4 tile sprites for any class still missing
        for cls_name, filename in u4_class_tiles.items():
            if cls_name in self._class_sprites:
                continue  # already loaded from primary source
            path = os.path.join(u4_tile_dir, filename)
            if os.path.exists(path):
                raw = pygame.image.load(path).convert_alpha()
                # Make black pixels transparent (U4 tiles use black bg)
                raw = raw.convert_alpha()
                w, h = raw.get_size()
                for px in range(w):
                    for py in range(h):
                        r, g, b, a = raw.get_at((px, py))
                        if r == 0 and g == 0 and b == 0:
                            raw.set_at((px, py), (0, 0, 0, 0))
                # Scale 16×16 → 32×32 to match game tile size
                scaled = pygame.transform.scale(raw, (32, 32))
                self._class_sprites[cls_name] = scaled
                # 3× big version (32 → 96) for party screen
                big = pygame.transform.scale(raw, (96, 96))
                self._class_sprites_big[cls_name] = big

        # Create a white-tinted fighter sprite for the party map marker.
        # The source sprite has a solid black (0,0,0) background — make
        # those pixels transparent and turn the actual figure pixels white.
        self._party_map_sprite = None
        fighter_src = self._class_sprites.get("fighter")
        if fighter_src:
            w, h = fighter_src.get_size()
            white_sprite = pygame.Surface((w, h), pygame.SRCALPHA)
            for px in range(w):
                for py in range(h):
                    r, g, b, a = fighter_src.get_at((px, py))
                    if a == 0 or (r == 0 and g == 0 and b == 0):
                        # Background — keep transparent
                        pass
                    else:
                        # Figure pixel — make white
                        white_sprite.set_at((px, py), (255, 255, 255, 255))
            self._party_map_sprite = white_sprite

    def _get_class_sprite(self, char_class, big=False):
        """Return the sprite surface for a character class, or None."""
        key = char_class.lower()
        if big:
            return self._class_sprites_big.get(key)
        return self._class_sprites.get(key)

    def _get_member_sprite(self, member, big=False):
        """Return the sprite for a party member, using custom tile if set.

        Falls back to the class-based sprite if no custom tile exists.
        """
        if member.sprite:
            raw = self._load_cc_tile(member.sprite)
            if raw is not None:
                target = (96, 96) if big else (32, 32)
                # Cache scaled versions per (file, size) to avoid re-scaling
                cache_key = (member.sprite, target)
                if not hasattr(self, '_member_sprite_cache'):
                    self._member_sprite_cache = {}
                if cache_key not in self._member_sprite_cache:
                    self._member_sprite_cache[cache_key] = (
                        pygame.transform.scale(raw, target))
                return self._member_sprite_cache[cache_key]
        return self._get_class_sprite(member.char_class, big=big)

    def draw_map(self, tile_map, camera):
        """Draw the visible portion of the map."""
        for screen_row in range(VIEWPORT_ROWS):
            for screen_col in range(VIEWPORT_COLS):
                world_col = screen_col + camera.offset_col
                world_row = screen_row + camera.offset_row
                tile_id = tile_map.get_tile(world_col, world_row)
                tile_def = TILE_DEFS.get(tile_id, TILE_DEFS[0])
                color = tile_def["color"]

                rect = pygame.Rect(
                    screen_col * TILE_SIZE,
                    screen_row * TILE_SIZE,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                pygame.draw.rect(self.screen, color, rect)

                # Draw a subtle grid line
                pygame.draw.rect(self.screen, (0, 0, 0), rect, 1)

                # Draw a symbol on special tiles
                self._draw_tile_detail(tile_id, rect)

    def _draw_tile_detail(self, tile_id, rect):
        """Add visual detail to certain tile types."""
        cx = rect.centerx
        cy = rect.centery

        from src.settings import (
            TILE_FOREST, TILE_MOUNTAIN, TILE_TOWN, TILE_DUNGEON, TILE_BRIDGE
        )

        if tile_id == TILE_FOREST:
            # Simple tree symbol: a small triangle
            points = [(cx, cy - 8), (cx - 6, cy + 4), (cx + 6, cy + 4)]
            pygame.draw.polygon(self.screen, (0, 120, 0), points)
            pygame.draw.line(self.screen, (80, 50, 20), (cx, cy + 4), (cx, cy + 8), 2)

        elif tile_id == TILE_MOUNTAIN:
            # Mountain peak triangle
            points = [(cx, cy - 10), (cx - 8, cy + 6), (cx + 8, cy + 6)]
            pygame.draw.polygon(self.screen, (160, 160, 160), points)
            # Snow cap
            snow = [(cx, cy - 10), (cx - 3, cy - 4), (cx + 3, cy - 4)]
            pygame.draw.polygon(self.screen, COLOR_WHITE, snow)

        elif tile_id == TILE_TOWN:
            # Small house shape
            # Roof
            roof = [(cx, cy - 8), (cx - 8, cy - 1), (cx + 8, cy - 1)]
            pygame.draw.polygon(self.screen, (160, 60, 40), roof)
            # Walls
            walls = pygame.Rect(cx - 6, cy - 1, 12, 9)
            pygame.draw.rect(self.screen, (200, 180, 140), walls)
            # Door
            door = pygame.Rect(cx - 2, cy + 2, 4, 6)
            pygame.draw.rect(self.screen, (80, 50, 20), door)

        elif tile_id == TILE_DUNGEON:
            # Dark cave entrance
            pygame.draw.circle(self.screen, (40, 10, 30), (cx, cy), 10)
            pygame.draw.circle(self.screen, (20, 0, 15), (cx, cy), 6)
            # Skull-ish hint
            text = self.font_small.render("!", True, COLOR_YELLOW)
            self.screen.blit(text, (cx - 3, cy - 6))

        elif tile_id == TILE_BRIDGE:
            # Wooden planks
            for i in range(-1, 2):
                plank_rect = pygame.Rect(rect.x + 2, rect.y + 8 + i * 10, TILE_SIZE - 4, 6)
                pygame.draw.rect(self.screen, (120, 80, 30), plank_rect)

        elif tile_id == TILE_WALL:
            # Brick-like pattern
            for iy in range(0, TILE_SIZE, 8):
                offset = 6 if (iy // 8) % 2 else 0
                for ix in range(offset, TILE_SIZE, 12):
                    brick = pygame.Rect(rect.x + ix, rect.y + iy, 10, 6)
                    pygame.draw.rect(self.screen, (110, 85, 60), brick)
                    pygame.draw.rect(self.screen, (70, 55, 35), brick, 1)

        elif tile_id == TILE_COUNTER:
            # Flat surface with items
            top = pygame.Rect(rect.x + 2, rect.y + 6, TILE_SIZE - 4, TILE_SIZE - 12)
            pygame.draw.rect(self.screen, (170, 120, 70), top)
            pygame.draw.rect(self.screen, (100, 70, 40), top, 1)
            # Little item on counter
            pygame.draw.circle(self.screen, COLOR_YELLOW, (cx, cy), 4)

        elif tile_id == TILE_DOOR:
            # Wooden door
            door_rect = pygame.Rect(rect.x + 6, rect.y + 2, TILE_SIZE - 12, TILE_SIZE - 4)
            pygame.draw.rect(self.screen, (100, 65, 30), door_rect)
            pygame.draw.rect(self.screen, (60, 40, 15), door_rect, 1)
            # Handle
            pygame.draw.circle(self.screen, COLOR_YELLOW, (cx + 4, cy), 2)

        elif tile_id == TILE_EXIT:
            # Green arrow pointing down
            points = [(cx, cy + 8), (cx - 6, cy - 2), (cx + 6, cy - 2)]
            pygame.draw.polygon(self.screen, (40, 200, 40), points)
            text = self.font_small.render("EXIT", True, COLOR_WHITE)
            self.screen.blit(text, (cx - 10, cy - 12))

        elif tile_id == TILE_DWALL:
            # Dark stone blocks
            for iy in range(0, TILE_SIZE, 10):
                offset = 5 if (iy // 10) % 2 else 0
                for ix in range(offset, TILE_SIZE, 10):
                    block = pygame.Rect(rect.x + ix, rect.y + iy, 9, 9)
                    pygame.draw.rect(self.screen, (40, 38, 35), block)
                    pygame.draw.rect(self.screen, (22, 20, 18), block, 1)

        elif tile_id == TILE_DFLOOR:
            # Subtle stone floor cracks
            pygame.draw.line(self.screen, (42, 38, 34),
                             (rect.x + 4, rect.y + 8),
                             (rect.x + 14, rect.y + 12), 1)
            pygame.draw.line(self.screen, (42, 38, 34),
                             (rect.x + 20, rect.y + 22),
                             (rect.x + 28, rect.y + 18), 1)

        elif tile_id == TILE_STAIRS:
            # Stairs going up — horizontal lines like steps
            for i in range(4):
                step_y = rect.y + 4 + i * 7
                step_w = TILE_SIZE - 8 - i * 3
                step_x = rect.x + 4 + i * 1
                step_rect = pygame.Rect(step_x, step_y, step_w, 5)
                pygame.draw.rect(self.screen, (100, 95, 80), step_rect)
                pygame.draw.rect(self.screen, (70, 65, 55), step_rect, 1)
            # Up arrow hint
            arrow = [(cx, rect.y + 2), (cx - 4, rect.y + 6), (cx + 4, rect.y + 6)]
            pygame.draw.polygon(self.screen, (180, 220, 180), arrow)

        elif tile_id == TILE_CHEST:
            # Treasure chest — use reference tile image
            if self._chest_tile:
                self.screen.blit(self._chest_tile, (rect.x, rect.y))
            else:
                # Fallback procedural
                body = pygame.Rect(cx - 7, cy - 3, 14, 10)
                pygame.draw.rect(self.screen, (140, 100, 30), body)
                pygame.draw.rect(self.screen, (100, 70, 20), body, 1)
                lid = pygame.Rect(cx - 7, cy - 7, 14, 5)
                pygame.draw.rect(self.screen, (160, 115, 35), lid)
                pygame.draw.rect(self.screen, (100, 70, 20), lid, 1)
                pygame.draw.circle(self.screen, COLOR_YELLOW, (cx, cy - 1), 2)

        elif tile_id == TILE_TRAP:
            # Hidden trap — subtle red-ish marks on floor
            pygame.draw.line(self.screen, (80, 30, 30),
                             (cx - 5, cy - 5), (cx + 5, cy + 5), 1)
            pygame.draw.line(self.screen, (80, 30, 30),
                             (cx + 5, cy - 5), (cx - 5, cy + 5), 1)
            pygame.draw.circle(self.screen, (70, 25, 25), (cx, cy), 3, 1)

    def draw_party(self, party, camera):
        """Draw the party as a simple white stick-figure (Ultima III style)."""
        screen_col, screen_row = camera.world_to_screen(party.col, party.row)
        cx = screen_col * TILE_SIZE + TILE_SIZE // 2
        cy = screen_row * TILE_SIZE + TILE_SIZE // 2
        W = (255, 255, 255)
        BLU = (120, 120, 255)

        # Head
        pygame.draw.circle(self.screen, W, (cx, cy - 9), 4)
        # Body
        pygame.draw.line(self.screen, W, (cx, cy - 5), (cx, cy + 4), 2)
        # Arms
        pygame.draw.line(self.screen, W, (cx - 6, cy - 2), (cx + 6, cy - 2), 2)
        # Legs
        pygame.draw.line(self.screen, W, (cx, cy + 4), (cx - 5, cy + 12), 2)
        pygame.draw.line(self.screen, W, (cx, cy + 4), (cx + 5, cy + 12), 2)
        # Sword (right hand)
        pygame.draw.line(self.screen, BLU, (cx + 6, cy - 8), (cx + 6, cy + 2), 2)
        # Shield (left hand)
        pygame.draw.rect(self.screen, BLU,
                         pygame.Rect(cx - 10, cy - 5, 4, 7))

    def draw_hud(self, party, tile_map):
        """Draw a simple HUD at the bottom of the screen."""
        hud_height = 80
        hud_y = SCREEN_HEIGHT - hud_height
        hud_rect = pygame.Rect(0, hud_y, SCREEN_WIDTH, hud_height)
        pygame.draw.rect(self.screen, COLOR_HUD_BG, hud_rect)
        pygame.draw.line(self.screen, COLOR_WHITE, (0, hud_y), (SCREEN_WIDTH, hud_y), 1)

        # Show terrain info
        tile_name = tile_map.get_tile_name(party.col, party.row)
        pos_text = f"Position: ({party.col}, {party.row})  Terrain: {tile_name}"
        text_surface = self.font.render(pos_text, True, COLOR_HUD_TEXT)
        self.screen.blit(text_surface, (10, hud_y + 8))

        # Show party summary
        x_offset = 10
        for i, member in enumerate(party.members):
            status = f"{member.name} ({member.char_class}) HP:{member.hp}/{member.max_hp}"
            color = COLOR_HUD_TEXT if member.is_alive() else (150, 50, 50)
            text_surface = self.font_small.render(status, True, color)
            self.screen.blit(text_surface, (x_offset, hud_y + 30 + i * 14))

    def draw_npcs(self, npcs, camera):
        """Draw NPC sprites on the map using per-type VGA tile sprites."""
        for npc in npcs:
            screen_col, screen_row = camera.world_to_screen(npc.col, npc.row)
            if 0 <= screen_col < VIEWPORT_COLS and 0 <= screen_row < VIEWPORT_ROWS:
                cx = screen_col * TILE_SIZE + TILE_SIZE // 2
                cy = screen_row * TILE_SIZE + TILE_SIZE // 2
                self._u3_draw_npc_sprite(npc, cx, cy)

    # ========================================================
    # TOWN  –  Ultima III retro style (sprite tiles)
    # ========================================================

    _U3_TN_COLS = 30       # tiles visible horizontally (full width)
    _U3_TN_ROWS = 21       # tiles visible vertically
    _U3_TN_TS   = 32       # tile size
    _U3_TN_MAP_W = _U3_TN_COLS * _U3_TN_TS   # 960
    _U3_TN_MAP_H = _U3_TN_ROWS * _U3_TN_TS   # 672

    def draw_town_u3(self, party, town_data, message="",
                      quest_complete=False, darkness_active=False,
                      keys_inserted=0):
        """
        Full Ultima III-style town screen — full-width map with bottom info bar.
        Uses sprite sheet tiles where available, procedural fallback otherwise.
        """
        self.screen.fill((0, 0, 0))

        ts = self._U3_TN_TS
        cols = self._U3_TN_COLS
        rows = self._U3_TN_ROWS
        tile_map = town_data.tile_map

        # ── compute camera offset ──
        off_c = party.col - cols // 2
        off_r = party.row - rows // 2
        off_c = max(0, min(off_c, tile_map.width - cols))
        off_r = max(0, min(off_r, tile_map.height - rows))

        # ── Build keyslot lookup: (col,row) → slot_index ──
        self._keyslot_index = {}
        for idx, pos in enumerate(getattr(town_data, "keyslot_positions", [])):
            self._keyslot_index[pos] = idx

        # ── 1. draw map tiles ──
        for sr in range(rows):
            for sc in range(cols):
                wc = sc + off_c
                wr = sr + off_r
                tid = tile_map.get_tile(wc, wr)
                px = sc * ts
                py = sr * ts
                self._u3_draw_town_tile(tid, px, py, ts, wc, wr,
                                        keys_inserted=keys_inserted)

        # ── 2. NPC sprites ──
        for npc in town_data.npcs:
            nsc = npc.col - off_c
            nsr = npc.row - off_r
            if 0 <= nsc < cols and 0 <= nsr < rows:
                cx = nsc * ts + ts // 2
                cy = nsr * ts + ts // 2
                self._u3_draw_npc_sprite(npc, cx, cy)

        # ── 2b. Shadow Crystal on innkeeper's counter (quest trophy) ──
        if quest_complete:
            import math
            import time as _time
            anim_t = _time.time()
            for npc in town_data.npcs:
                if npc.npc_type == "innkeeper":
                    crystal_wc = npc.col
                    crystal_wr = npc.row - 1  # counter tile above innkeeper
                    csc = crystal_wc - off_c
                    csr = crystal_wr - off_r
                    if 0 <= csc < cols and 0 <= csr < rows:
                        gcx = csc * ts + ts // 2
                        gcy = csr * ts + ts // 2
                        bob = int(2 * math.sin(anim_t * 2.5))
                        # Small glow
                        glow_r = int(8 + 2 * math.sin(anim_t * 3))
                        glow_surf = pygame.Surface(
                            (glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                        glow_a = int(50 + 25 * math.sin(anim_t * 2))
                        pygame.draw.circle(
                            glow_surf, (120, 60, 200, glow_a),
                            (glow_r, glow_r), glow_r)
                        self.screen.blit(
                            glow_surf,
                            (gcx - glow_r, gcy + bob - glow_r))
                        # Small diamond crystal
                        sz = 5
                        pts = [
                            (gcx, gcy + bob - sz),
                            (gcx + sz, gcy + bob),
                            (gcx, gcy + bob + sz),
                            (gcx - sz, gcy + bob),
                        ]
                        pulse = 0.15 * math.sin(anim_t * 4)
                        cr = min(255, int(140 * (1 + pulse)))
                        cb = min(255, int(220 * (1 + pulse)))
                        pygame.draw.polygon(
                            self.screen, (cr, 80, cb), pts)
                        pygame.draw.polygon(
                            self.screen, (200, 160, 255), pts, 1)
                    break

        # ── 3. party sprite ──
        psc = party.col - off_c
        psr = party.row - off_r
        if 0 <= psc < cols and 0 <= psr < rows:
            cx = psc * ts + ts // 2
            cy = psr * ts + ts // 2
            self._u3_draw_overworld_party(cx, cy, party)

        # ── 3b. darkness overlay (Keys of Shadow / nighttime) ──
        clock = party.clock
        has_infravision = party.has_effect("Infravision")
        has_galadriels = (party.has_effect("Galadriel's Light")
                          and party.galadriels_light_steps > 0)
        if not clock.is_day or darkness_active:
            has_light = (party.get_equipped_name("light") is not None
                         or has_infravision or has_galadriels)
            # Build extra light sources from filled keyslots
            keyslot_lights = []
            if keys_inserted > 0 and self._keyslot_index:
                for (kc, kr), si in self._keyslot_index.items():
                    if si < keys_inserted:
                        # Convert world coords to screen-tile coords
                        ksc = kc - off_c
                        ksr = kr - off_r
                        # Each filled keyslot emits light that grows
                        # slightly with more keys inserted
                        ks_radius = 1.5 + 0.3 * keys_inserted
                        keyslot_lights.append(
                            (ksc, ksr, ks_radius, 1.5))
            self._draw_overworld_darkness(clock, psc, psr, ts, cols, rows,
                                          has_light=has_light,
                                          force_night=darkness_active,
                                          extra_lights=keyslot_lights)
            if has_infravision and party.get_equipped_name("light") is None:
                self._u3_infravision_tint(cols, rows, ts, None, 0, 0, psc, psr)
            elif (has_galadriels
                  and party.get_equipped_name("light") is None
                  and not has_infravision):
                self._u3_galadriels_tint(cols, rows, ts, None, 0, 0, psc, psr)

        # ── 4. blue border around map ──
        pygame.draw.rect(self.screen, (68, 68, 255),
                         pygame.Rect(0, 0, self._U3_TN_MAP_W, self._U3_TN_MAP_H), 2)

        # ── 5. bottom info bar ──
        bar_y = self._U3_TN_MAP_H
        bar_h = SCREEN_HEIGHT - bar_y
        self._u3_panel(0, bar_y, SCREEN_WIDTH, bar_h)

        tile_name = tile_map.get_tile_name(party.col, party.row)
        # Top line: town info
        self._u3_text(f"GOLD:{party.gold:d}", 8, bar_y + 6, (255, 255, 0))
        self._u3_text(town_data.name.upper(), 240, bar_y + 6, (255, 170, 85))
        light_name = party.get_equipped_name("light")
        if light_name:
            charges = party.get_equipped_charges("light")
            lbl = f"LIGHT:{light_name.upper()}"
            if charges is not None:
                lbl += f":{charges:d}"
            self._u3_text(lbl, 520, bar_y + 6, (255, 170, 85))
        self._u3_text(f"POS:({party.col},{party.row})", 770, bar_y + 6, (136, 136, 136))
        # Bottom line: controls
        self._u3_text("[ARROWS/WASD] MOVE  [P] PARTY  [BUMP NPC] TALK  [ESC] LEAVE",
                      8, bar_y + 28, (68, 68, 255))

        # ── 6. floating message ──
        self._draw_floating_message(message)

    def draw_pickpocket_targeting(self, party, town_data, targets, cursor_idx):
        """Draw pickpocket targeting overlay on top of the town map.

        Shows a pulsing selection cursor around the targeted NPC,
        dim highlight on all other candidate NPCs, and a prompt bar.
        """
        import math as _math

        ts = self._U3_TN_TS
        cols = self._U3_TN_COLS
        rows = self._U3_TN_ROWS
        tile_map = town_data.tile_map

        off_c = party.col - cols // 2
        off_r = party.row - rows // 2
        off_c = max(0, min(off_c, tile_map.width - cols))
        off_r = max(0, min(off_r, tile_map.height - rows))

        # Slight dim overlay over the whole map to focus attention
        dim = pygame.Surface((self._U3_TN_MAP_W, self._U3_TN_MAP_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 60))
        self.screen.blit(dim, (0, 0))

        pulse = _math.sin(pygame.time.get_ticks() * 0.006)

        for i, npc in enumerate(targets):
            nsc = npc.col - off_c
            nsr = npc.row - off_r
            if not (0 <= nsc < cols and 0 <= nsr < rows):
                continue
            px = nsc * ts
            py = nsr * ts
            is_selected = (i == cursor_idx)

            if is_selected:
                # Pulsing yellow/gold selection box
                alpha = int(140 + 80 * pulse)
                sel_color = (255, 200, 50, alpha)
                sel_surf = pygame.Surface((ts, ts), pygame.SRCALPHA)
                sel_surf.fill((255, 200, 50, 40))
                self.screen.blit(sel_surf, (px, py))
                # Animated border
                border_w = 2
                pygame.draw.rect(self.screen, (255, 220, 80),
                                 pygame.Rect(px, py, ts, ts), border_w)
                # Corner accents (pulsing)
                corner_len = int(6 + 2 * pulse)
                c = (255, 255, 150)
                # top-left
                pygame.draw.line(self.screen, c, (px, py), (px + corner_len, py), 2)
                pygame.draw.line(self.screen, c, (px, py), (px, py + corner_len), 2)
                # top-right
                pygame.draw.line(self.screen, c, (px + ts, py), (px + ts - corner_len, py), 2)
                pygame.draw.line(self.screen, c, (px + ts, py), (px + ts, py + corner_len), 2)
                # bottom-left
                pygame.draw.line(self.screen, c, (px, py + ts), (px + corner_len, py + ts), 2)
                pygame.draw.line(self.screen, c, (px, py + ts), (px, py + ts - corner_len), 2)
                # bottom-right
                pygame.draw.line(self.screen, c, (px + ts, py + ts), (px + ts - corner_len, py + ts), 2)
                pygame.draw.line(self.screen, c, (px + ts, py + ts), (px + ts, py + ts - corner_len), 2)
            else:
                # Subtle white outline on non-selected candidates
                pygame.draw.rect(self.screen, (150, 150, 150),
                                 pygame.Rect(px, py, ts, ts), 1)

        # ── Prompt bar at bottom of map ──
        bar_y = self._U3_TN_MAP_H
        target_npc = targets[cursor_idx] if cursor_idx < len(targets) else None
        name = target_npc.name if target_npc else "???"
        halfling = None
        for m in party.members:
            if m.is_alive() and m.race == "Halfling":
                halfling = m
                break
        hname = halfling.name if halfling else "Halfling"

        # Overwrite the controls line with targeting prompt
        prompt_y = bar_y + 28
        prompt_bg = pygame.Rect(0, prompt_y - 2, 960, 22)
        pygame.draw.rect(self.screen, (0, 0, 0), prompt_bg)
        self._u3_text(
            f"PICKPOCKET: {hname} -> {name.upper()}   "
            f"[ARROWS] SELECT  [ENTER] ATTEMPT  [ESC] CANCEL",
            8, prompt_y, (220, 180, 50))

    def _u3_draw_town_tile(self, tile_id, px, py, ts, wc, wr,
                            keys_inserted=0):
        """Draw a single town tile using sprite sheet art when available."""
        from src.settings import (
            TILE_FLOOR, TILE_WALL, TILE_COUNTER, TILE_DOOR, TILE_EXIT,
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
            TILE_MACHINE, TILE_KEYSLOT,
        )

        # Use extracted town gate tile for exit
        if tile_id == TILE_EXIT and self._town_gate_tile:
            self.screen.blit(self._town_gate_tile, (px, py))
            return

        # Try town tile map first, then overworld tile map
        pos = self._town_tile_map.get(tile_id)
        if pos is None:
            pos = self._overworld_tile_map.get(tile_id)
        if pos is not None:
            sprite = self._tile_sprites.get(pos)
            if sprite:
                self.screen.blit(sprite, (px, py))
                return

        # Procedural fallback for unmapped / unloaded tiles
        BLACK = (0, 0, 0)
        BROWN = (140, 100, 50)
        ORANGE = (255, 170, 85)
        YELLOW = (255, 255, 0)

        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2
        seed = wc * 31 + wr * 17

        if tile_id == TILE_FLOOR:
            # Indoor floor — dark grey stone
            base = 45 + (seed % 15)
            pygame.draw.rect(self.screen, (base, base, base), rect)
            # Subtle stone-slab lines
            pygame.draw.line(self.screen, (base - 10, base - 10, base - 10),
                             (px, py + ts // 2), (px + ts, py + ts // 2), 1)
            pygame.draw.line(self.screen, (base - 10, base - 10, base - 10),
                             (px + ts // 2, py), (px + ts // 2, py + ts), 1)

        elif tile_id == TILE_WALL:
            # Brick wall
            pygame.draw.rect(self.screen, (120, 80, 50), rect)
            for iy in range(0, ts, 8):
                offset = 6 if (iy // 8) % 2 else 0
                for ix in range(offset, ts, 12):
                    brick = pygame.Rect(px + ix, py + iy, 10, 6)
                    pygame.draw.rect(self.screen, (100, 65, 40), brick, 1)

        elif tile_id == TILE_EXIT:
            # Gate / exit — green field with archway
            pygame.draw.rect(self.screen, (20, 100, 15), rect)
            # Stone arch
            arch_w = ts - 8
            pygame.draw.rect(self.screen, (130, 130, 130),
                             pygame.Rect(px + 4, py + 6, arch_w, ts - 6))
            pygame.draw.rect(self.screen, (60, 60, 60),
                             pygame.Rect(px + 8, py + 10, arch_w - 8, ts - 10))

        elif tile_id == TILE_GRASS:
            base_g = 100 + (seed % 30)
            pygame.draw.rect(self.screen, (20, base_g, 15), rect)

        elif tile_id == TILE_WATER:
            pygame.draw.rect(self.screen, (15, 30, 120), rect)

        elif tile_id == TILE_COUNTER:
            pygame.draw.rect(self.screen, BLACK, rect)
            top = pygame.Rect(px + 3, py + 8, ts - 6, ts - 14)
            pygame.draw.rect(self.screen, BROWN, top)
            pygame.draw.rect(self.screen, (100, 70, 30), top, 1)
            pygame.draw.circle(self.screen, YELLOW, (cx, cy), 3)

        elif tile_id == TILE_DOOR:
            pygame.draw.rect(self.screen, BLACK, rect)
            door_rect = pygame.Rect(px + 7, py + 2, ts - 14, ts - 4)
            pygame.draw.rect(self.screen, (100, 65, 30), door_rect)
            pygame.draw.rect(self.screen, (60, 40, 15), door_rect, 1)
            pygame.draw.circle(self.screen, YELLOW, (cx + 3, cy), 2)

        elif tile_id == TILE_MACHINE:
            self._draw_machine_tile(px, py, ts, wc, wr)

        elif tile_id == TILE_KEYSLOT:
            self._draw_keyslot_tile(px, py, ts, wc, wr, keys_inserted)

        else:
            # Unknown tile — use TILE_DEFS color if available
            tile_def = TILE_DEFS.get(tile_id)
            if tile_def:
                pygame.draw.rect(self.screen, tile_def["color"], rect)
            else:
                pygame.draw.rect(self.screen, BLACK, rect)

    def _draw_machine_tile(self, px, py, ts, wc, wr):
        """Draw one tile of the gnomish machine (part of a 3×3 structure).

        Uses a deterministic seed from the world coordinates so each of
        the 9 tiles gets a unique mechanical part: gears, boilers,
        gauges, pipes, vents, or the central energy core.
        """
        import math as _math
        import time as _time

        t = _time.time()
        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2

        # Palette
        METAL = (55, 55, 65)
        METAL_LIGHT = (80, 80, 95)
        METAL_DARK = (35, 35, 42)
        RIVET = (120, 120, 130)
        COPPER = (180, 100, 40)
        COPPER_DARK = (130, 70, 25)
        ENERGY = (160, 80, 200)
        ENERGY_BRIGHT = (220, 140, 255)

        # Base metal plate
        pygame.draw.rect(self.screen, METAL, rect)
        pygame.draw.rect(self.screen, METAL_DARK, rect, 1)

        # Determine which part to draw via a stable seed from world pos
        seed = (wc + wr * 3) % 9

        if seed == 0:
            # ── Energy core: pulsing orb with arcs ──
            core_rect = pygame.Rect(px + 2, py + 2, ts - 4, ts - 4)
            pygame.draw.rect(self.screen, (25, 15, 35), core_rect)
            pygame.draw.rect(self.screen, COPPER, core_rect, 2)
            # Pulsing orb
            orb_r = int(7 + 2 * _math.sin(t * 2.5))
            orb_a = int(160 + 60 * _math.sin(t * 3.0))
            orb_s = pygame.Surface((orb_r * 2 + 8, orb_r * 2 + 8),
                                   pygame.SRCALPHA)
            pygame.draw.circle(orb_s,
                               (ENERGY[0], ENERGY[1], ENERGY[2], orb_a // 3),
                               (orb_r + 4, orb_r + 4), orb_r + 4)
            pygame.draw.circle(orb_s,
                               (ENERGY_BRIGHT[0], ENERGY_BRIGHT[1],
                                ENERGY_BRIGHT[2], orb_a),
                               (orb_r + 4, orb_r + 4), orb_r)
            pygame.draw.circle(orb_s,
                               (255, 220, 255, min(255, orb_a + 40)),
                               (orb_r + 4, orb_r + 4), max(1, orb_r // 2))
            self.screen.blit(orb_s, (cx - orb_r - 4, cy - orb_r - 4))
            # Energy arcs
            for i in range(4):
                angle = t * 2.0 + i * _math.pi / 2
                arc_len = 6 + int(3 * _math.sin(t * 4 + i))
                x1 = cx + int(5 * _math.cos(angle))
                y1 = cy + int(5 * _math.sin(angle))
                x2 = cx + int(arc_len * _math.cos(angle))
                y2 = cy + int(arc_len * _math.sin(angle))
                arc_c = min(255, int(220 + 35 * _math.sin(t * 5 + i)))
                pygame.draw.line(self.screen, (arc_c, 100, 255),
                                 (x1, y1), (x2, y2), 1)
            # Corner bolts
            for bx, by in ((px + 4, py + 4), (px + ts - 5, py + 4),
                           (px + 4, py + ts - 5), (px + ts - 5, py + ts - 5)):
                pygame.draw.circle(self.screen, RIVET, (bx, by), 2)
                pygame.draw.circle(self.screen, METAL_DARK, (bx, by), 1)

        elif seed in (1, 5):
            # ── Rotating gear ──
            direction = 1.0 if seed == 1 else -1.0
            gear_r = 9
            pygame.draw.circle(self.screen, COPPER, (cx, cy), gear_r, 2)
            teeth = 8
            for i in range(teeth):
                angle = direction * t * 1.2 + i * (2 * _math.pi / teeth)
                tx = cx + int((gear_r + 2) * _math.cos(angle))
                ty = cy + int((gear_r + 2) * _math.sin(angle))
                pygame.draw.circle(self.screen, COPPER_DARK, (tx, ty), 2)
            pygame.draw.circle(self.screen, METAL_LIGHT, (cx, cy), 4)
            pygame.draw.circle(self.screen, METAL_DARK, (cx, cy), 2)
            # Spokes
            for i in range(4):
                angle = direction * t * 1.2 + i * _math.pi / 2
                sx = cx + int(gear_r * _math.cos(angle))
                sy = cy + int(gear_r * _math.sin(angle))
                pygame.draw.line(self.screen, COPPER_DARK, (cx, cy), (sx, sy), 1)

        elif seed in (2, 6):
            # ── Boiler with pressure gauge ──
            boiler = pygame.Rect(px + 4, py + 4, ts - 8, ts - 8)
            pygame.draw.rect(self.screen, METAL_LIGHT, boiler)
            pygame.draw.rect(self.screen, METAL_DARK, boiler, 1)
            # Horizontal bands
            for band_y in (py + 8, py + ts // 2, py + ts - 9):
                pygame.draw.line(self.screen, COPPER_DARK,
                                 (px + 4, band_y), (px + ts - 5, band_y), 1)
            # Gauge
            g_cx = cx + (4 if seed == 2 else -4)
            g_cy = cy - 2
            pygame.draw.circle(self.screen, (20, 20, 20), (g_cx, g_cy), 5)
            pygame.draw.circle(self.screen, RIVET, (g_cx, g_cy), 5, 1)
            # Animated needle
            angle = t * 1.5 + seed * 0.7
            nx = g_cx + int(3 * _math.cos(angle))
            ny = g_cy + int(3 * _math.sin(angle))
            pygame.draw.line(self.screen, (255, 60, 60),
                             (g_cx, g_cy), (nx, ny), 1)
            # Rivets
            for rx, ry in ((px + 3, py + 3), (px + ts - 4, py + 3),
                           (px + 3, py + ts - 4), (px + ts - 4, py + ts - 4)):
                pygame.draw.circle(self.screen, RIVET, (rx, ry), 1)

        elif seed in (3, 7):
            # ── Exhaust vents with steam ──
            for vx in range(px + 4, px + ts - 3, 6):
                vent = pygame.Rect(vx, py + 3, 4, ts - 6)
                pygame.draw.rect(self.screen, METAL_DARK, vent)
                pygame.draw.rect(self.screen, METAL_LIGHT, vent, 1)
            # Animated steam puffs
            steam_a = int(70 + 40 * _math.sin(t * 3 + seed))
            steam_s = pygame.Surface((14, 10), pygame.SRCALPHA)
            pygame.draw.ellipse(steam_s, (200, 200, 220, steam_a),
                                (0, 0, 14, 10))
            sx = cx - 7 + int(3 * _math.sin(t * 2 + seed))
            sy = py - 3 + int(2 * _math.cos(t * 1.5))
            self.screen.blit(steam_s, (sx, sy))
            # Pipe across one edge
            pygame.draw.line(self.screen, COPPER,
                             (px, py + ts - 3), (px + ts, py + ts - 3), 2)

        elif seed == 4:
            # ── Key slots panel (4 glowing slots) ──
            base = pygame.Rect(px + 2, py + 2, ts - 4, ts - 4)
            pygame.draw.rect(self.screen, METAL_DARK, base)
            pygame.draw.rect(self.screen, RIVET, base, 1)
            for i in range(4):
                kx = px + 4 + i * 7
                slot = pygame.Rect(kx, cy - 3, 5, 7)
                pulse = int(60 + 50 * _math.sin(t * 2 + i * 0.8))
                pygame.draw.rect(self.screen, (pulse, 25, pulse + 30), slot)
                pygame.draw.rect(self.screen, RIVET, slot, 1)
            # Label "KEYS" in tiny text
            label = self.font_small.render("KEYS", True, ENERGY)
            lrect = label.get_rect(center=(cx, py + 6))
            self.screen.blit(label, lrect)
            # Pipe across top
            pygame.draw.line(self.screen, COPPER,
                             (px, py + 2), (px + ts, py + 2), 2)

        else:
            # ── Conduit / pipe junction ──
            # Horizontal pipe
            pygame.draw.line(self.screen, COPPER,
                             (px, cy), (px + ts, cy), 3)
            pygame.draw.line(self.screen, COPPER_DARK,
                             (px, cy - 2), (px + ts, cy - 2), 1)
            # Vertical pipe
            pygame.draw.line(self.screen, COPPER,
                             (cx, py), (cx, py + ts), 3)
            pygame.draw.line(self.screen, COPPER_DARK,
                             (cx - 2, py), (cx - 2, py + ts), 1)
            # Junction plate
            junct = pygame.Rect(cx - 5, cy - 5, 10, 10)
            pygame.draw.rect(self.screen, METAL_LIGHT, junct)
            pygame.draw.rect(self.screen, COPPER, junct, 1)
            # Animated flow indicator
            flow_x = px + int((t * 20 + seed * 10) % ts)
            pygame.draw.circle(self.screen, ENERGY, (flow_x, cy), 2)
            flow_y = py + int((t * 15 + seed * 7) % ts)
            pygame.draw.circle(self.screen, ENERGY, (cx, flow_y), 2)

    def _draw_keyslot_tile(self, px, py, ts, wc, wr, keys_inserted):
        """Draw a single keyslot pedestal around the gnome machine.

        Empty slots show a dark stone pedestal with an empty keyhole.
        Filled slots glow and pulse with golden-white light, and emit
        a small radial light bloom to push back the darkness.
        """
        import math as _math
        import time as _time

        t = _time.time()
        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2

        # Determine this slot's index (0-7)
        slot_idx = getattr(self, "_keyslot_index", {}).get((wc, wr), -1)
        filled = slot_idx >= 0 and slot_idx < keys_inserted

        # Palette
        STONE = (50, 45, 55)
        STONE_LIGHT = (70, 65, 75)
        STONE_DARK = (30, 28, 35)

        # Key colours — each slot gets a unique hue
        KEY_HUES = [
            (255, 200, 60),   # 0: gold
            (60, 200, 255),   # 1: ice blue
            (255, 80, 80),    # 2: crimson
            (80, 255, 120),   # 3: emerald
            (200, 120, 255),  # 4: violet
            (255, 160, 40),   # 5: amber
            (40, 255, 220),   # 6: teal
            (255, 255, 180),  # 7: pale sun
        ]
        hue = KEY_HUES[slot_idx % 8] if slot_idx >= 0 else (100, 100, 100)

        # ── Base: stone pedestal ──
        pygame.draw.rect(self.screen, STONE, rect)
        pygame.draw.rect(self.screen, STONE_DARK, rect, 1)
        # Inner raised platform
        plat = pygame.Rect(px + 3, py + 3, ts - 6, ts - 6)
        pygame.draw.rect(self.screen, STONE_LIGHT, plat)
        pygame.draw.rect(self.screen, STONE_DARK, plat, 1)

        if filled:
            # ── Filled slot: glowing key with pulse and light bloom ──

            # Outer glow bloom (alpha-blended circle)
            pulse = 0.5 + 0.5 * _math.sin(t * 2.5 + slot_idx * 0.9)
            bloom_r = int(ts * 0.7 + 4 * pulse)
            bloom_alpha = int(60 + 50 * pulse)
            bloom_s = pygame.Surface((bloom_r * 2, bloom_r * 2),
                                     pygame.SRCALPHA)
            br, bg, bb = hue
            pygame.draw.circle(bloom_s,
                               (br, bg, bb, bloom_alpha // 3),
                               (bloom_r, bloom_r), bloom_r)
            pygame.draw.circle(bloom_s,
                               (br, bg, bb, bloom_alpha),
                               (bloom_r, bloom_r), bloom_r // 2)
            self.screen.blit(bloom_s,
                             (cx - bloom_r, cy - bloom_r))

            # Key shape: vertical bar + crossbar (T-shape)
            key_bright = tuple(min(255, int(c * (0.8 + 0.2 * pulse)))
                               for c in hue)
            # Vertical shaft
            pygame.draw.line(self.screen, key_bright,
                             (cx, cy - 6), (cx, cy + 5), 3)
            # Key head (circle at top)
            pygame.draw.circle(self.screen, key_bright, (cx, cy - 6), 3)
            pygame.draw.circle(self.screen,
                               (255, 255, 255), (cx, cy - 6), 1)
            # Key teeth (small nubs at bottom)
            pygame.draw.line(self.screen, key_bright,
                             (cx, cy + 4), (cx + 3, cy + 4), 2)
            pygame.draw.line(self.screen, key_bright,
                             (cx, cy + 2), (cx + 2, cy + 2), 1)

            # Central sparkle
            sparkle_a = int(180 + 75 * _math.sin(t * 4.0 + slot_idx))
            sparkle_s = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(sparkle_s,
                               (255, 255, 240, sparkle_a), (4, 4), 3)
            pygame.draw.circle(sparkle_s,
                               (255, 255, 255, min(255, sparkle_a + 40)),
                               (4, 4), 1)
            self.screen.blit(sparkle_s, (cx - 4, cy - 8))

            # Corner rune marks (tiny glowing dots)
            for corner_x, corner_y in ((px + 4, py + 4),
                                        (px + ts - 5, py + 4),
                                        (px + 4, py + ts - 5),
                                        (px + ts - 5, py + ts - 5)):
                dot_a = int(120 + 80 * _math.sin(
                    t * 3.0 + corner_x * 0.1 + corner_y * 0.1))
                dot_s = pygame.Surface((4, 4), pygame.SRCALPHA)
                pygame.draw.circle(dot_s,
                                   (br, bg, bb, dot_a), (2, 2), 2)
                self.screen.blit(dot_s, (corner_x - 2, corner_y - 2))
        else:
            # ── Empty slot: dark keyhole waiting for a key ──

            # Keyhole shape: circle + triangle
            pygame.draw.circle(self.screen, STONE_DARK, (cx, cy - 2), 4)
            pygame.draw.circle(self.screen, (20, 15, 25), (cx, cy - 2), 3)
            # Keyhole slit
            pygame.draw.polygon(self.screen, (20, 15, 25), [
                (cx - 2, cy + 1),
                (cx + 2, cy + 1),
                (cx + 1, cy + 6),
                (cx - 1, cy + 6),
            ])

            # Faint pulse to indicate it's interactive
            faint = int(20 + 15 * _math.sin(t * 1.5 + slot_idx * 0.7))
            faint_s = pygame.Surface((ts, ts), pygame.SRCALPHA)
            pygame.draw.circle(faint_s,
                               (hue[0], hue[1], hue[2], faint),
                               (ts // 2, ts // 2), ts // 3)
            self.screen.blit(faint_s, (px, py))

            # Corner rivets
            for rx, ry in ((px + 4, py + 4), (px + ts - 5, py + 4),
                           (px + 4, py + ts - 5), (px + ts - 5, py + ts - 5)):
                pygame.draw.circle(self.screen, (80, 75, 85), (rx, ry), 1)

    def _u3_draw_npc_sprite(self, npc, cx, cy):
        """Draw an NPC on the town map using per-type VGA sprites."""
        import math as _math
        import time as _time

        # ── Animated gnome (Fizzwick) ──
        if npc.npc_type == "gnome":
            self._draw_gnome_sprite(npc, cx, cy)
            return

        sprite = self._npc_sprites.get(npc.npc_type)
        # Villagers rotate among several sprites based on name hash
        if sprite is None and self._villager_sprites:
            idx = hash(npc.name) % len(self._villager_sprites)
            sprite = self._villager_sprites[idx]
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: colored stick figure
            npc_colors = {
                "shopkeep": (200, 160, 60),
                "innkeeper": (60, 160, 200),
                "elder":     (180, 80, 200),
                "villager":  (100, 180, 100),
            }
            color = npc_colors.get(npc.npc_type, (100, 180, 100))
            pygame.draw.circle(self.screen, color, (cx, cy - 9), 4)
            pygame.draw.line(self.screen, color, (cx, cy - 5), (cx, cy + 4), 2)
            pygame.draw.line(self.screen, color, (cx - 6, cy - 2), (cx + 6, cy - 2), 2)
            pygame.draw.line(self.screen, color, (cx, cy + 4), (cx - 5, cy + 12), 2)
            pygame.draw.line(self.screen, color, (cx, cy + 4), (cx + 5, cy + 12), 2)

        # Name tag above
        name_surf = self.font_small.render(npc.name.upper(), True, (255, 255, 255))
        name_rect = name_surf.get_rect(center=(cx, cy - 20))
        bg = name_rect.inflate(4, 2)
        pygame.draw.rect(self.screen, (0, 0, 0), bg)
        self.screen.blit(name_surf, name_rect)

    def _draw_gnome_sprite(self, npc, cx, cy):
        """Draw an animated gnome NPC — short, pointy hat, bobbing, with glow."""
        import math as _math
        import time as _time

        t = _time.time()

        # Bobbing offset (gentle float up and down)
        bob = int(2 * _math.sin(t * 2.5))

        # Subtle pulsing glow around the gnome
        glow_r = int(14 + 3 * _math.sin(t * 1.8))
        glow_a = int(35 + 20 * _math.sin(t * 2.0))
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            glow_surf, (180, 120, 255, glow_a),
            (glow_r, glow_r), glow_r)
        self.screen.blit(glow_surf, (cx - glow_r, cy + bob - glow_r))

        # --- Body (shorter than regular NPCs) ---
        body_color = (120, 80, 40)     # brown tunic
        skin = (220, 180, 140)
        hat_color = (160, 60, 200)     # purple pointy hat

        # Head (round, slightly larger for gnome proportions)
        head_y = cy + bob - 7
        pygame.draw.circle(self.screen, skin, (cx, head_y), 5)
        # Eyes
        pygame.draw.circle(self.screen, (40, 40, 40), (cx - 2, head_y - 1), 1)
        pygame.draw.circle(self.screen, (40, 40, 40), (cx + 2, head_y - 1), 1)

        # Pointy hat
        hat_tip_y = head_y - 14
        hat_base_y = head_y - 4
        hat_pts = [
            (cx, hat_tip_y),           # tip
            (cx - 6, hat_base_y),      # left brim
            (cx + 6, hat_base_y),      # right brim
        ]
        pygame.draw.polygon(self.screen, hat_color, hat_pts)
        pygame.draw.polygon(self.screen, (200, 100, 255), hat_pts, 1)
        # Hat star/sparkle at tip (animated)
        sparkle_a = int(200 + 55 * _math.sin(t * 4))
        sparkle_col = (255, 255, min(255, sparkle_a))
        pygame.draw.circle(self.screen, sparkle_col, (cx, hat_tip_y), 2)

        # Torso (short, squat)
        torso_top = cy + bob - 2
        torso_bot = cy + bob + 5
        pygame.draw.line(self.screen, body_color, (cx, torso_top), (cx, torso_bot), 3)

        # Arms (slightly waving)
        arm_wave = int(2 * _math.sin(t * 3.0))
        pygame.draw.line(self.screen, body_color,
                         (cx - 6, torso_top + 1 - arm_wave),
                         (cx, torso_top + 2), 2)
        pygame.draw.line(self.screen, body_color,
                         (cx + 6, torso_top + 1 + arm_wave),
                         (cx, torso_top + 2), 2)

        # Legs (short, stubby)
        pygame.draw.line(self.screen, body_color,
                         (cx, torso_bot), (cx - 3, cy + bob + 11), 2)
        pygame.draw.line(self.screen, body_color,
                         (cx, torso_bot), (cx + 3, cy + bob + 11), 2)

        # Beard (white, small)
        beard_y = head_y + 3
        pygame.draw.line(self.screen, (220, 220, 220),
                         (cx - 2, beard_y), (cx, beard_y + 4), 1)
        pygame.draw.line(self.screen, (220, 220, 220),
                         (cx + 2, beard_y), (cx, beard_y + 4), 1)

        # Name tag above (yellow for quest-giver)
        name_surf = self.font_small.render(npc.name.upper(), True, (255, 255, 100))
        name_rect = name_surf.get_rect(center=(cx, cy + bob - 24))
        bg = name_rect.inflate(4, 2)
        pygame.draw.rect(self.screen, (0, 0, 0), bg)
        self.screen.blit(name_surf, name_rect)

    def draw_hud_town(self, party, town_data):
        """Draw HUD for the town view."""
        hud_height = 80
        hud_y = SCREEN_HEIGHT - hud_height
        hud_rect = pygame.Rect(0, hud_y, SCREEN_WIDTH, hud_height)
        pygame.draw.rect(self.screen, COLOR_HUD_BG, hud_rect)
        pygame.draw.line(self.screen, COLOR_WHITE, (0, hud_y), (SCREEN_WIDTH, hud_y), 1)

        # Town name and position
        tile_name = town_data.tile_map.get_tile_name(party.col, party.row)
        info_text = f"{town_data.name}  |  ({party.col}, {party.row})  {tile_name}"
        text_surface = self.font.render(info_text, True, COLOR_HUD_TEXT)
        self.screen.blit(text_surface, (10, hud_y + 8))

        # Controls hint
        hint = "Arrow keys: Move  |  Bump NPC: Talk  |  ESC: Leave town"
        hint_surface = self.font_small.render(hint, True, (140, 140, 160))
        self.screen.blit(hint_surface, (10, hud_y + 28))

        # Party summary (compact)
        x_offset = 10
        for i, member in enumerate(party.members):
            status = f"{member.name} HP:{member.hp}/{member.max_hp}"
            color = COLOR_HUD_TEXT if member.is_alive() else (150, 50, 50)
            text_surface = self.font_small.render(status, True, color)
            self.screen.blit(text_surface, (x_offset + i * 180, hud_y + 50))

    def draw_fog_of_war(self, party, camera, light_radius=4):
        """
        Draw a darkness overlay that limits visibility to a radius
        around the party. Uses Euclidean distance for a circular light
        with a smooth gradient at the edges.
        """
        import math

        # Create an alpha surface (starts fully transparent)
        fog = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)

        # Party position in screen tile coords
        party_scol, party_srow = camera.world_to_screen(party.col, party.row)

        # The gradient zone extends 1.5 tiles beyond the hard radius
        fade_start = light_radius
        fade_end = light_radius + 1.5

        for screen_row in range(VIEWPORT_ROWS + 1):
            for screen_col in range(VIEWPORT_COLS + 1):
                # Euclidean distance from party (tile centers)
                dx = screen_col - party_scol
                dy = screen_row - party_srow
                dist = math.sqrt(dx * dx + dy * dy)

                if dist <= fade_start:
                    # Fully lit — no fog
                    continue
                elif dist >= fade_end:
                    alpha = 255
                else:
                    # Smooth gradient in the fade zone
                    t = (dist - fade_start) / (fade_end - fade_start)
                    alpha = int(255 * t)

                rect = pygame.Rect(
                    screen_col * TILE_SIZE,
                    screen_row * TILE_SIZE,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                fog.fill((0, 0, 0, alpha), rect)

        self.screen.blit(fog, (0, 0))

    def draw_hud_dungeon(self, party, dungeon_data):
        """Draw HUD for the dungeon view."""
        hud_height = 80
        hud_y = SCREEN_HEIGHT - hud_height
        hud_rect = pygame.Rect(0, hud_y, SCREEN_WIDTH, hud_height)
        pygame.draw.rect(self.screen, (10, 8, 15), hud_rect)
        pygame.draw.line(self.screen, (80, 40, 40), (0, hud_y), (SCREEN_WIDTH, hud_y), 1)

        # Dungeon name and position
        tile_name = dungeon_data.tile_map.get_tile_name(party.col, party.row)
        info_text = f"{dungeon_data.name}  |  ({party.col}, {party.row})  {tile_name}"
        text_surface = self.font.render(info_text, True, (180, 140, 140))
        self.screen.blit(text_surface, (10, hud_y + 8))

        # Controls hint
        hint = "Arrow keys: Move  |  ESC on stairs: Leave dungeon"
        hint_surface = self.font_small.render(hint, True, (120, 100, 110))
        self.screen.blit(hint_surface, (10, hud_y + 28))

        # Party summary with gold
        x_offset = 10
        for i, member in enumerate(party.members):
            status = f"{member.name} HP:{member.hp}/{member.max_hp}"
            color = (180, 160, 160) if member.is_alive() else (150, 50, 50)
            text_surface = self.font_small.render(status, True, color)
            self.screen.blit(text_surface, (x_offset + i * 170, hud_y + 50))

        # Gold display
        gold_text = f"Gold: {party.gold}"
        gold_surface = self.font.render(gold_text, True, COLOR_YELLOW)
        self.screen.blit(gold_surface, (SCREEN_WIDTH - 140, hud_y + 8))

        # Chests found
        chests_text = f"Chests: {len(dungeon_data.opened_chests)}"
        chests_surface = self.font_small.render(chests_text, True, (180, 140, 80))
        self.screen.blit(chests_surface, (SCREEN_WIDTH - 140, hud_y + 30))

    def draw_dialogue_box(self, message):
        """Draw an NPC dialogue box at the top of the screen with word wrap."""
        if not message:
            return
        box_x = 30
        box_y = 10
        box_width = SCREEN_WIDTH - 60
        text_pad = 12
        max_text_w = box_width - text_pad * 2

        # Word-wrap the message into lines that fit the box
        words = message.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip() if current else word
            tw, _ = self.font.size(test)
            if tw <= max_text_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            lines = [message]

        line_h = self.font.get_linesize()
        spacing = 2
        text_block_h = len(lines) * line_h + max(0, len(lines) - 1) * spacing
        hint_h = 20  # space for the hint line
        box_height = text_pad + text_block_h + 6 + hint_h + text_pad

        # Store the dialogue box bottom for the quest choice box to use
        self._dialogue_box_bottom = box_y + box_height

        # Dark box with border
        box_rect = pygame.Rect(box_x, box_y, box_width, box_height)
        pygame.draw.rect(self.screen, (15, 15, 30), box_rect)
        pygame.draw.rect(self.screen, (120, 100, 60), box_rect, 2)

        # Draw wrapped text lines
        cur_y = box_y + text_pad
        for ln in lines:
            text_surface = self.font.render(ln, True, COLOR_WHITE)
            self.screen.blit(text_surface, (box_x + text_pad, cur_y))
            cur_y += line_h + spacing

        # Hint to dismiss
        hint = "[SPACE / ENTER] continue   [ESC] close"
        hint_surface = self.font_small.render(hint, True, (120, 120, 140))
        self.screen.blit(hint_surface, (box_x + text_pad, cur_y + 4))

    def draw_quest_complete_effect(self, effect):
        """Draw the quest completion celebration animation overlay.

        Three phases:
        1. Crystal rises and glows at center screen
        2. Crystal shatters into sparks, gold coins rain
        3. QUEST COMPLETE banner with sparkles
        """
        import math

        t = effect.timer
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2

        # Semi-transparent overlay that darkens over time
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dark = min(180, int(t * 120))
        overlay.fill((0, 0, 0, dark))
        self.screen.blit(overlay, (0, 0))

        # ── Phase 1 (0.0 - 1.5s): Crystal rises and glows ──
        if t < 1.5:
            phase = t / 1.5
            # Crystal rises from bottom to center
            crystal_y = int(SCREEN_HEIGHT - phase * (SCREEN_HEIGHT // 2 - 40))
            crystal_x = cx

            # Draw the Shadow Crystal — purple gem shape
            glow_r = int(20 + 30 * phase)
            glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            pulse = 0.5 + 0.5 * math.sin(t * 8)
            alpha = int((100 + 80 * pulse) * phase)
            pygame.draw.circle(glow, (120, 60, 200, alpha),
                               (glow_r, glow_r), glow_r)
            self.screen.blit(glow,
                             (crystal_x - glow_r, crystal_y - glow_r))

            # Diamond shape
            size = int(12 + 8 * phase)
            points = [
                (crystal_x, crystal_y - size),      # top
                (crystal_x + size, crystal_y),       # right
                (crystal_x, crystal_y + size),       # bottom
                (crystal_x - size, crystal_y),       # left
            ]
            r = int(100 + 100 * pulse)
            g = int(40 + 40 * pulse)
            b = int(180 + 60 * pulse)
            pygame.draw.polygon(self.screen, (r, g, b), points)
            pygame.draw.polygon(self.screen, (200, 160, 255), points, 2)

            # Inner highlight
            inner_size = size // 2
            inner_pts = [
                (crystal_x, crystal_y - inner_size),
                (crystal_x + inner_size, crystal_y),
                (crystal_x, crystal_y + inner_size),
                (crystal_x - inner_size, crystal_y),
            ]
            pygame.draw.polygon(self.screen, (180, 140, 255, 180), inner_pts)

            # Rising sparkle trail
            for i in range(6):
                spark_t = (t * 3 + i * 0.5) % 2.0
                sx = crystal_x + int(15 * math.sin(t * 4 + i))
                sy = crystal_y + int(spark_t * 40)
                spark_alpha = max(0, 255 - int(spark_t * 200))
                if spark_alpha > 0:
                    self.screen.set_at((sx, sy),
                                       (200, 160, 255))
                    self.screen.set_at((sx + 1, sy),
                                       (200, 160, 255))

        # ── Phase 2 (1.5 - 3.0s): Crystal shatters + gold coins rain ──
        elif t < 3.0:
            phase = (t - 1.5) / 1.5  # 0..1

            # Explosion flash at start of phase
            if phase < 0.15:
                flash_alpha = int(200 * (1.0 - phase / 0.15))
                flash = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT),
                                       pygame.SRCALPHA)
                flash.fill((200, 160, 255, flash_alpha))
                self.screen.blit(flash, (0, 0))

            # Crystal shards flying outward
            elapsed = t - 1.5
            for shard in effect.shards:
                sx = cx + int(shard["vx"] * elapsed)
                sy = cy + int(shard["vy"] * elapsed + 100 * elapsed * elapsed)
                # Fade out over time
                fade = max(0.0, 1.0 - phase)
                if fade > 0 and 0 <= sx < SCREEN_WIDTH and 0 <= sy < SCREEN_HEIGHT:
                    s = shard["size"]
                    c = shard["color"]
                    fc = (int(c[0] * fade), int(c[1] * fade), int(c[2] * fade))
                    pygame.draw.rect(self.screen, fc, (sx, sy, s, s))

            # Gold coin rain
            for coin in effect.coins:
                coin_elapsed = elapsed - coin["delay"]
                if coin_elapsed < 0:
                    continue
                coin_x = coin["x"] + int(10 * math.sin(coin_elapsed * 3))
                coin_y = int(coin["speed"] * coin_elapsed)
                if coin_y > SCREEN_HEIGHT:
                    continue

                # Spinning coin effect — alternating width
                spin = math.sin(coin_elapsed * 8)
                w = max(1, int(abs(spin) * 6))
                h = 8
                coin_color = (255, 220, 50) if spin > 0 else (200, 170, 30)
                pygame.draw.ellipse(self.screen, coin_color,
                                    (coin_x - w // 2, coin_y, w, h))
                pygame.draw.ellipse(self.screen, (255, 255, 150),
                                    (coin_x - w // 2, coin_y, w, h), 1)

            # Gold amount text rising
            gold_text = f"+{effect.reward_gold} GOLD"
            gold_y = cy + 40 - int(phase * 60)
            text_alpha = min(255, int(phase * 400))
            if text_alpha > 0:
                c = min(255, int(255 * min(1.0, phase * 2)))
                self._u3_text(gold_text,
                              cx - len(gold_text) * 5, gold_y,
                              (c, c, int(c * 0.3)), self.font)

        # ── Phase 3 (3.0 - 5.0s): QUEST COMPLETE banner + sparkles ──
        else:
            phase = (t - 3.0) / 2.0  # 0..1

            # Banner fade in
            banner_alpha = min(1.0, phase * 2)

            # Banner background
            banner_w = 500
            banner_h = 120
            bx = (SCREEN_WIDTH - banner_w) // 2
            by = (SCREEN_HEIGHT - banner_h) // 2 - 40

            banner_surf = pygame.Surface((banner_w, banner_h), pygame.SRCALPHA)
            ba = int(200 * banner_alpha)
            banner_surf.fill((20, 10, 40, ba))
            self.screen.blit(banner_surf, (bx, by))

            # Ornate border (double line)
            bc = int(200 * banner_alpha)
            border_color = (bc, int(bc * 0.7), int(bc * 0.3))
            pygame.draw.rect(self.screen, border_color,
                             (bx, by, banner_w, banner_h), 2)
            pygame.draw.rect(self.screen, border_color,
                             (bx + 4, by + 4, banner_w - 8, banner_h - 8), 1)

            # "QUEST COMPLETE!" text
            title = "QUEST COMPLETE!"
            pulse = 0.1 * math.sin(t * 3)
            tr = min(255, int((255) * banner_alpha * (1 + pulse)))
            tg = min(255, int((220) * banner_alpha * (1 + pulse)))
            tb = min(255, int((60) * banner_alpha * (1 + pulse)))
            tw = len(title) * 10
            self._u3_text(title,
                          cx - tw // 2, by + 16,
                          (tr, tg, tb), self.font)

            # Quest name
            qname = "The Shadow Crystal"
            qw = len(qname) * 8
            qc = int(180 * banner_alpha)
            self._u3_text(qname,
                          cx - qw // 2, by + 45,
                          (qc, qc, int(qc * 1.2)), self.font_med)

            # Reward summary
            reward_text = f"+{effect.reward_gold} Gold   +50 XP"
            rw = len(reward_text) * 7
            rc = int(200 * banner_alpha)
            self._u3_text(reward_text,
                          cx - rw // 2, by + 72,
                          (rc, rc, int(rc * 0.4)), self.font_med)

            # Item display hint
            item_text = "The Shadow Crystal is now on display at the inn!"
            iw = len(item_text) * 6
            ic = int(140 * banner_alpha)
            self._u3_text(item_text,
                          cx - iw // 2, by + 95,
                          (ic, int(ic * 0.8), ic), self.font_small)

            # Celebration sparkles around the banner
            for sparkle in effect.sparkles:
                sp_x = sparkle["x"]
                sp_y = sparkle["y"]
                sp_phase = sparkle["phase"] + t * sparkle["speed"]
                brightness = int((0.5 + 0.5 * math.sin(sp_phase)) * 255 * banner_alpha)
                if brightness > 30:
                    sc = (brightness, int(brightness * 0.85),
                          int(brightness * 0.3))
                    self.screen.set_at((sp_x, sp_y), sc)
                    # Cross pattern for brighter sparkles
                    if brightness > 150:
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nx, ny = sp_x + dx, sp_y + dy
                            if 0 <= nx < SCREEN_WIDTH and 0 <= ny < SCREEN_HEIGHT:
                                self.screen.set_at(
                                    (nx, ny),
                                    (brightness // 2, brightness // 2,
                                     brightness // 3))

    def draw_quest_choice_box(self, choices, cursor):
        """Draw a Y/N quest choice prompt below the dialogue box."""
        box_width = SCREEN_WIDTH - 60
        box_height = 50
        box_x = 30
        # Position just below the dialogue box (dynamic height)
        box_y = getattr(self, "_dialogue_box_bottom", 80) + 6

        box_rect = pygame.Rect(box_x, box_y, box_width, box_height)
        pygame.draw.rect(self.screen, (15, 15, 30), box_rect)
        pygame.draw.rect(self.screen, (200, 180, 50), box_rect, 2)

        # Draw each choice
        for i, choice in enumerate(choices):
            color = COLOR_YELLOW if i == cursor else COLOR_WHITE
            prefix = "> " if i == cursor else "  "
            text_surf = self.font.render(f"{prefix}{choice}", True, color)
            self.screen.blit(text_surf, (box_x + 16, box_y + 6 + i * 20))

    def draw_monsters(self, monsters, camera):
        """Draw monster sprites on the dungeon map (Ultima III style)."""
        W = (255, 255, 255)
        for monster in monsters:
            if not monster.is_alive():
                continue
            screen_col, screen_row = camera.world_to_screen(monster.col, monster.row)
            if 0 <= screen_col < VIEWPORT_COLS and 0 <= screen_row < VIEWPORT_ROWS:
                cx = screen_col * TILE_SIZE + TILE_SIZE // 2
                cy = screen_row * TILE_SIZE + TILE_SIZE // 2
                mc = monster.color

                # Same blocky monster as combat: body + head + eyes
                # Body
                body = pygame.Rect(cx - 8, cy - 6, 16, 14)
                pygame.draw.rect(self.screen, mc, body)
                # Head
                pygame.draw.rect(self.screen, mc,
                                 pygame.Rect(cx - 5, cy - 12, 10, 7))
                # Eyes — white with red pupils
                pygame.draw.rect(self.screen, W,
                                 pygame.Rect(cx - 4, cy - 10, 3, 3))
                pygame.draw.rect(self.screen, W,
                                 pygame.Rect(cx + 1, cy - 10, 3, 3))
                pygame.draw.rect(self.screen, (255, 0, 0),
                                 pygame.Rect(cx - 3, cy - 9, 1, 1))
                pygame.draw.rect(self.screen, (255, 0, 0),
                                 pygame.Rect(cx + 2, cy - 9, 1, 1))
                # Name tag (uppercase)
                name_surf = self.font_small.render(monster.name.upper(), True, (255, 100, 100))
                name_rect = name_surf.get_rect(center=(cx, cy - 16))
                bg = name_rect.inflate(4, 2)
                pygame.draw.rect(self.screen, (0, 0, 0), bg)
                self.screen.blit(name_surf, name_rect)

    def draw_message(self, message, y_offset=0):
        """Draw a temporary message on screen (e.g., 'Blocked!' or 'Entering town...')."""
        if message:
            text_surface = self.font.render(message, True, COLOR_YELLOW)
            text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, 20 + y_offset))
            # Dark background for readability
            bg_rect = text_rect.inflate(20, 8)
            pygame.draw.rect(self.screen, COLOR_HUD_BG, bg_rect)
            self.screen.blit(text_surface, text_rect)

    # ========================================================
    # OVERWORLD  –  Ultima III retro style
    # ========================================================

    # Map viewport for the U3 split-screen layout
    _U3_OW_COLS = 30       # tiles visible horizontally (full width)
    _U3_OW_ROWS = 21       # tiles visible vertically
    _U3_OW_TS   = 32       # tile size (same as global TILE_SIZE)
    _U3_OW_MAP_W = _U3_OW_COLS * _U3_OW_TS   # 960
    _U3_OW_MAP_H = _U3_OW_ROWS * _U3_OW_TS   # 672

    def draw_overworld_u3(self, party, tile_map, message="", overworld_monsters=None,
                          unique_text="", unique_flash=0.0, unique_pos=None,
                          push_anim=None, repel_effect=None,
                          darkness_active=False):
        """
        Full Ultima III-style overworld screen — full-width map with bottom info bar.

        ┌─────────────────────────────────────┐
        │                                     │
        │         25×17 tile map              │
        │         (full screen width)         │
        │                                     │
        ├─────────────────────────────────────┤
        │ GOLD:00100  TERRAIN:GRASS  (20,15)  │
        │ [ARROWS/WASD] MOVE        [ESC]QUIT│
        └─────────────────────────────────────┘
        """
        self.screen.fill((0, 0, 0))

        ts = self._U3_OW_TS
        cols = self._U3_OW_COLS
        rows = self._U3_OW_ROWS

        # ── compute camera offset ──
        off_c = party.col - cols // 2
        off_r = party.row - rows // 2
        off_c = max(0, min(off_c, tile_map.width - cols))
        off_r = max(0, min(off_r, tile_map.height - rows))

        # ── 1. draw map tiles ──
        from src.settings import (
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
            TILE_TOWN, TILE_DUNGEON, TILE_PATH, TILE_SAND, TILE_BRIDGE,
        )

        for sr in range(rows):
            for sc in range(cols):
                wc = sc + off_c
                wr = sr + off_r
                tid = tile_map.get_tile(wc, wr)
                px = sc * ts
                py = sr * ts
                self._u3_draw_overworld_tile(tid, px, py, ts, wc, wr)

        # ── 1b. draw visible unique tile sprites ──
        for (uc, ur), utile in tile_map.unique_tiles.items():
            if not utile.get("visible") or not utile.get("tile"):
                continue
            usc = uc - off_c
            usr = ur - off_r
            if 0 <= usc < cols and 0 <= usr < rows:
                sprite = self._get_unique_tile_sprite(utile["tile"], ts)
                if sprite:
                    px = usc * ts
                    py = usr * ts
                    self.screen.blit(sprite, (px, py))

        # ── 1c. seasonal snow overlay (winter months) ──
        clock = party.clock
        if clock.month_index in (0, 1, 11):  # Jan, Feb, Dec
            self._draw_snow_overlay(tile_map, ts, cols, rows, off_c, off_r, clock)

        # ── 2. overworld monster sprites ──
        if overworld_monsters:
            for mon in overworld_monsters:
                if not mon.is_alive():
                    continue
                msc = mon.col - off_c
                msr = mon.row - off_r
                if 0 <= msc < cols and 0 <= msr < rows:
                    mx = msc * ts + ts // 2
                    my = msr * ts + ts // 2
                    mon_sprite = self._get_monster_sprite(mon)
                    if mon_sprite:
                        sx = mx - mon_sprite.get_width() // 2
                        sy = my - mon_sprite.get_height() // 2
                        self.screen.blit(mon_sprite, (sx, sy))

        # ── 3. party sprite ──
        psc = party.col - off_c
        psr = party.row - off_r
        if 0 <= psc < cols and 0 <= psr < rows:
            cx = psc * ts + ts // 2
            cy = psr * ts + ts // 2
            self._u3_draw_overworld_party(cx, cy, party)

        # ── 3b. Push spell expanding-wave animation ──
        if push_anim:
            self._draw_push_spell_wave(push_anim, repel_effect,
                                       party, ts, cols, rows, off_c, off_r)

        # ── 3c. Time-of-day darkness overlay ──
        clock = party.clock
        has_infravision = party.has_effect("Infravision")
        has_galadriels = (party.has_effect("Galadriel's Light")
                          and party.galadriels_light_steps > 0)
        if not clock.is_day or darkness_active:
            has_light = (party.get_equipped_name("light") is not None
                         or has_infravision or has_galadriels)
            self._draw_overworld_darkness(clock, psc, psr, ts, cols, rows,
                                          has_light=has_light,
                                          force_night=darkness_active)
            # Apply infravision red tint when it's the active light source
            if has_infravision and party.get_equipped_name("light") is None:
                self._u3_infravision_tint(cols, rows, ts, None, 0, 0, psc, psr)
            # Apply Galadriel's Light blue tint (when no torch or infravision)
            elif (has_galadriels
                  and party.get_equipped_name("light") is None
                  and not has_infravision):
                self._u3_galadriels_tint(cols, rows, ts, None, 0, 0, psc, psr)
        # Galadriel's Light blue tint also applies during day (subtle)
        if has_galadriels and not has_infravision:
            self._u3_galadriels_tint(cols, rows, ts, None, 0, 0, psc, psr,
                                      subtle=True)

        # ── 4. blue border around map ──
        pygame.draw.rect(self.screen, (68, 68, 255),
                         pygame.Rect(0, 0, self._U3_OW_MAP_W, self._U3_OW_MAP_H), 2)

        # ── 5. bottom info bar ──
        bar_y = self._U3_OW_MAP_H
        bar_h = SCREEN_HEIGHT - bar_y
        self._u3_panel(0, bar_y, SCREEN_WIDTH, bar_h)

        tile_name = tile_map.get_tile_name(party.col, party.row)
        f = self.font  # larger 16px font for readability
        clock = party.clock
        icon_sz = 20
        row1_y = bar_y + 4
        row2_y = bar_y + 30

        # ── Row 1: [moon][sun/moon] date+time  gold  terrain ──
        x = 6
        self._draw_moon_phase(x, row1_y, icon_sz, clock.lunar_phase_index)
        x += icon_sz + 4
        self._draw_sky_icon(x, row1_y, icon_sz, clock)
        x += icon_sz + 8
        self._u3_text(clock.full_str, x, row1_y + 2,
                      (180, 200, 255), font=f)
        self._u3_text(f"GOLD:{party.gold:d}", 380, row1_y + 2,
                      (255, 255, 0), font=f)
        self._u3_text(f"TERRAIN:{tile_name}", 560, row1_y + 2,
                      (200, 200, 255), font=f)
        self._u3_text(f"POS:({party.col},{party.row})", 840, row1_y + 2,
                      (220, 220, 220), font=f)

        # ── Row 2: light info + unique tile text ──
        light_name = party.get_equipped_name("light")
        row2_x = 8
        if light_name:
            charges = party.get_equipped_charges("light")
            lbl = f"LIGHT:{light_name.upper()}"
            if charges is not None:
                lbl += f":{charges:d}"
            self._u3_text(lbl, row2_x, row2_y, (255, 170, 85),
                          font=self.font_small)
            row2_x += len(lbl) * 8 + 16

        if unique_text:
            pulse = (math.sin(unique_flash) + 1.0) * 0.5
            r = int(200 + 55 * pulse)
            g = int(170 + 60 * pulse)
            b = int(80 * (1.0 - pulse * 0.4))
            display_text = unique_text
            max_chars = (SCREEN_WIDTH - row2_x - 8) // 7
            if len(display_text) > max_chars:
                display_text = display_text[:max_chars - 3] + "..."
            self._u3_text(display_text, row2_x, row2_y,
                          (r, g, b), font=self.font_small)

        # ── 5c. sparkle effect on the map tile ──
        if unique_pos and unique_flash > 0:
            uc, ur = unique_pos
            usc = uc - off_c
            usr = ur - off_r
            if 0 <= usc < cols and 0 <= usr < rows:
                cx = usc * ts + ts // 2
                cy = usr * ts + ts // 2
                # Expanding ring
                ring_r = int(8 + 12 * ((math.sin(unique_flash * 1.5) + 1) * 0.5))
                ring_alpha = int(180 * max(0, (math.cos(unique_flash * 0.8) + 1) * 0.5))
                ring_surf = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(ring_surf, (255, 220, 100, ring_alpha),
                                   (ring_r + 2, ring_r + 2), ring_r, 2)
                self.screen.blit(ring_surf, (cx - ring_r - 2, cy - ring_r - 2))
                # Sparkle dots orbiting the tile
                for i in range(4):
                    angle = unique_flash * 2.0 + i * (math.pi / 2)
                    sx = cx + int(14 * math.cos(angle))
                    sy = cy + int(14 * math.sin(angle))
                    dot_alpha = int(200 * max(0, math.sin(unique_flash * 3.0 + i)))
                    dot_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
                    pygame.draw.circle(dot_surf, (255, 255, 200, dot_alpha), (3, 3), 3)
                    self.screen.blit(dot_surf, (sx - 3, sy - 3))

        # ── 6. floating message ──
        self._draw_floating_message(message)

    # ── overworld tile rendering ─────────────────────────────

    def _u3_draw_overworld_tile(self, tile_id, px, py, ts, wc, wr):
        """Draw a single overworld tile using sprite sheet art when available,
        falling back to procedural drawing for tiles without sprites."""
        from src.settings import (
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
            TILE_TOWN, TILE_DUNGEON, TILE_PATH, TILE_SAND, TILE_BRIDGE,
            TILE_MACHINE, TILE_KEYSLOT, TILE_DUNGEON_CLEARED,
        )

        # Try sprite sheet first
        sprite = self._get_tile_sprite(tile_id)
        if sprite:
            self.screen.blit(sprite, (px, py))
            # Cleared dungeons get a dark tint overlay + "X" mark
            if tile_id == TILE_DUNGEON_CLEARED:
                overlay = pygame.Surface((ts, ts), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 120))
                self.screen.blit(overlay, (px, py))
                cx = px + ts // 2
                cy = py + ts // 2
                pygame.draw.line(self.screen, (160, 140, 100),
                                 (cx - 5, cy - 5), (cx + 5, cy + 5), 2)
                pygame.draw.line(self.screen, (160, 140, 100),
                                 (cx + 5, cy - 5), (cx - 5, cy + 5), 2)
            return

        # Fallback: procedural drawing when sprites are unavailable
        BLACK = (0, 0, 0)
        BROWN = (140, 100, 50)
        SAND_C = (180, 160, 80)

        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2
        seed = wc * 31 + wr * 17

        if tile_id == TILE_GRASS:
            # Green field with subtle variation
            base_g = 100 + (seed % 30)
            pygame.draw.rect(self.screen, (20, base_g, 15), rect)
            # A few darker grass tufts
            for i in range(3):
                s = seed + i * 37
                gx = px + (s * 7) % (ts - 4) + 2
                gy = py + (s * 13) % (ts - 4) + 2
                pygame.draw.line(self.screen, (10, base_g + 30, 10),
                                 (gx, gy + 3), (gx, gy), 1)

        elif tile_id == TILE_WATER:
            # Blue water with wave highlights
            pygame.draw.rect(self.screen, (15, 30, 120), rect)
            t = pygame.time.get_ticks()
            for i in range(2):
                s = seed + i * 23
                wx = px + (s * 11) % (ts - 8) + 4
                wy = py + (s * 7) % (ts - 8) + 4
                phase = (t * 0.002 + s) % 6.28
                shimmer = int(30 + 20 * math.sin(phase))
                pygame.draw.line(self.screen, (40 + shimmer, 80 + shimmer, 180),
                                 (wx, wy), (wx + 6, wy), 1)

        elif tile_id == TILE_FOREST:
            # Dark green ground with tree shapes
            pygame.draw.rect(self.screen, (10, 60, 10), rect)
            # Simple tree: triangle crown + trunk
            points = [(cx, cy - 10), (cx - 7, cy + 3), (cx + 7, cy + 3)]
            pygame.draw.polygon(self.screen, (0, 100 + (seed % 30), 0), points)
            pygame.draw.line(self.screen, (80, 50, 20),
                             (cx, cy + 3), (cx, cy + 8), 2)

        elif tile_id == TILE_MOUNTAIN:
            # Grey mountain peak
            pygame.draw.rect(self.screen, (60, 50, 40), rect)
            points = [(cx, cy - 12), (cx - 10, cy + 8), (cx + 10, cy + 8)]
            pygame.draw.polygon(self.screen, (140, 140, 140), points)
            # Snow cap
            snow = [(cx, cy - 12), (cx - 4, cy - 4), (cx + 4, cy - 4)]
            pygame.draw.polygon(self.screen, (230, 230, 255), snow)

        elif tile_id == TILE_TOWN:
            # Green field with small house
            pygame.draw.rect(self.screen, (20, 100, 15), rect)
            roof = [(cx, cy - 9), (cx - 8, cy - 1), (cx + 8, cy - 1)]
            pygame.draw.polygon(self.screen, (160, 60, 40), roof)
            walls = pygame.Rect(cx - 6, cy - 1, 12, 9)
            pygame.draw.rect(self.screen, (200, 180, 140), walls)
            door = pygame.Rect(cx - 2, cy + 2, 4, 6)
            pygame.draw.rect(self.screen, (80, 50, 20), door)

        elif tile_id == TILE_DUNGEON:
            # Dark ground with cave entrance
            pygame.draw.rect(self.screen, (30, 25, 20), rect)
            pygame.draw.circle(self.screen, (40, 10, 30), (cx, cy), 10)
            pygame.draw.circle(self.screen, (20, 0, 15), (cx, cy), 6)
            text = self.font_small.render("!", True, (255, 255, 0))
            self.screen.blit(text, (cx - 3, cy - 6))

        elif tile_id == TILE_DUNGEON_CLEARED:
            # Collapsed / cleared cave entrance — muted colours, "X" mark
            pygame.draw.rect(self.screen, (40, 35, 30), rect)
            pygame.draw.circle(self.screen, (55, 45, 40), (cx, cy), 10)
            pygame.draw.circle(self.screen, (35, 30, 25), (cx, cy), 6)
            # Draw an "X" to indicate cleared
            pygame.draw.line(self.screen, (100, 90, 70),
                             (cx - 5, cy - 5), (cx + 5, cy + 5), 2)
            pygame.draw.line(self.screen, (100, 90, 70),
                             (cx + 5, cy - 5), (cx - 5, cy + 5), 2)

        elif tile_id == TILE_PATH:
            # Dirt path
            base_g = 80 + (seed % 20)
            pygame.draw.rect(self.screen, (base_g, base_g - 20, base_g - 40), rect)
            # Pebble details
            for i in range(3):
                s = seed + i * 41
                gx = px + (s * 9) % (ts - 4) + 2
                gy = py + (s * 11) % (ts - 4) + 2
                pygame.draw.circle(self.screen, (base_g + 20, base_g, base_g - 20),
                                   (gx, gy), 1)

        elif tile_id == TILE_SAND:
            pygame.draw.rect(self.screen, (25, 20, 5), rect)
            for i in range(4):
                s = seed + i * 19
                dx = (s * 7) % (ts - 6) + 3
                dy = (s * 13) % (ts - 6) + 3
                c = SAND_C if s % 2 else (150, 130, 60)
                pygame.draw.rect(self.screen, c,
                                 pygame.Rect(px + dx, py + dy, 2, 2))

        elif tile_id == TILE_BRIDGE:
            pygame.draw.rect(self.screen, (0, 0, 60), rect)
            for i in range(3):
                plank = pygame.Rect(px + 2, py + 6 + i * 10, ts - 4, 5)
                pygame.draw.rect(self.screen, BROWN, plank)
                pygame.draw.rect(self.screen, (80, 60, 30), plank, 1)

        elif tile_id == TILE_MACHINE:
            self._draw_machine_tile(px, py, ts, wc, wr)
            return

        elif tile_id == TILE_KEYSLOT:
            self._draw_keyslot_tile(px, py, ts, wc, wr, 0)
            return

        else:
            # Unknown tile — use TILE_DEFS color if available
            tile_def = TILE_DEFS.get(tile_id)
            if tile_def:
                pygame.draw.rect(self.screen, tile_def["color"], rect)
            else:
                pygame.draw.rect(self.screen, BLACK, rect)

    def _u3_draw_overworld_party(self, cx, cy, party=None):
        """Party map sprite — white-tinted fighter tile with torch effect."""
        import math

        sprite = self._party_map_sprite
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: simple white dot if sprite failed to load
            pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), 6)

        # ── Flickering light effect when LIGHT slot is occupied ──
        if party and party.get_equipped_name("light") is not None:
            t = pygame.time.get_ticks()
            # Use multiple sine waves at different speeds for organic flicker
            flicker1 = math.sin(t * 0.008)          # slow sway
            flicker2 = math.sin(t * 0.023) * 0.5    # medium pulse
            flicker3 = math.sin(t * 0.051) * 0.3    # fast shimmer
            flicker = flicker1 + flicker2 + flicker3  # range roughly -1.8..+1.8

            # Flame position: above sprite top, with horizontal sway
            sprite_top = cy - (sprite.get_height() // 2 if sprite else 16)
            fx = cx + int(flicker * 2)
            fy = sprite_top - 3

            # Outer glow (semi-transparent orange circle)
            glow_r = 7 + int(flicker2 * 2)
            glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            glow_alpha = 50 + int(flicker * 10)
            pygame.draw.circle(glow_surf, (255, 140, 40, glow_alpha),
                               (glow_r, glow_r), glow_r)
            self.screen.blit(glow_surf, (fx - glow_r, fy - glow_r))

            # Flame core — 3 layers (outer orange, middle yellow, inner white)
            h_outer = 6 + int(flicker2 * 2)
            h_mid = 4 + int(flicker3 * 1)
            h_inner = 2

            # Outer flame (orange-red)
            pts_outer = [(fx - 3, fy), (fx, fy - h_outer), (fx + 3, fy)]
            pygame.draw.polygon(self.screen, (255, 100, 20), pts_outer)

            # Mid flame (yellow)
            pts_mid = [(fx - 2, fy), (fx, fy - h_mid), (fx + 2, fy)]
            pygame.draw.polygon(self.screen, (255, 220, 60), pts_mid)

            # Inner flame (white-hot)
            pts_inner = [(fx - 1, fy), (fx, fy - h_inner), (fx + 1, fy)]
            pygame.draw.polygon(self.screen, (255, 255, 200), pts_inner)

    # ── overworld right panel ────────────────────────────────

    def _u3_overworld_right_panel(self, party, tile_map, x, y, w):
        """Draw the right-hand info panel for the overworld (no individual character stats)."""
        # Single info panel spanning the full height
        info_h = SCREEN_HEIGHT - y - 24  # above status bar
        self._u3_panel(x, y, w, info_h)
        tx = x + 8
        ty = y + 6

        self._u3_text(f"GOLD: {party.gold:d}", tx, ty, (255, 255, 0))

        ty += 18
        tile_name = tile_map.get_tile_name(party.col, party.row)
        self._u3_text(f"TERRAIN: {tile_name}", tx, ty, (68, 68, 255))

        ty += 18
        self._u3_text(f"POS: ({party.col},{party.row})", tx, ty, (136, 136, 136))

    # ========================================================
    # DUNGEON  –  Ultima III retro style
    # ========================================================

    # Dungeon viewport: same split-screen as overworld
    _U3_DG_COLS = 30
    _U3_DG_ROWS = 21
    _U3_DG_TS   = 32
    _U3_DG_MAP_W = _U3_DG_COLS * _U3_DG_TS   # 960
    _U3_DG_MAP_H = _U3_DG_ROWS * _U3_DG_TS   # 672

    # ── dungeon level palettes ──────────────────────────────
    # Each palette defines the visual theme for a dungeon depth.
    # Keys: wall_base, wall_bricks (list of 3), wall_mortar, floor_base,
    #        floor_detail, accent, env_type
    _DUNGEON_PALETTES = [
        {   # Level 1 — Standard stone dungeon (gray-blue)
            "wall_base":   (30, 28, 40),
            "wall_bricks": [(75, 70, 90), (60, 58, 78), (85, 80, 100)],
            "wall_mortar": (40, 38, 55),
            "floor_base":  (0, 0, 0),
            "floor_detail": (30, 28, 35),
            "accent":      (80, 80, 100),
            "env_type":    "stone",
        },
        {   # Level 2 — Mossy cavern (green-tinted)
            "wall_base":   (22, 35, 25),
            "wall_bricks": [(50, 75, 55), (40, 62, 45), (58, 82, 60)],
            "wall_mortar": (28, 42, 30),
            "floor_base":  (5, 8, 3),
            "floor_detail": (20, 35, 18),
            "accent":      (60, 100, 65),
            "env_type":    "moss",
        },
        {   # Level 3 — Volcanic depths (red-orange)
            "wall_base":   (40, 22, 18),
            "wall_bricks": [(90, 55, 40), (75, 45, 32), (100, 60, 42)],
            "wall_mortar": (50, 28, 20),
            "floor_base":  (10, 3, 2),
            "floor_detail": (40, 15, 10),
            "accent":      (200, 100, 40),
            "env_type":    "lava",
        },
        {   # Level 4 — Frozen crypt (ice-blue)
            "wall_base":   (28, 35, 48),
            "wall_bricks": [(70, 85, 110), (55, 70, 95), (80, 95, 120)],
            "wall_mortar": (38, 45, 62),
            "floor_base":  (4, 6, 12),
            "floor_detail": (22, 30, 45),
            "accent":      (140, 180, 220),
            "env_type":    "ice",
        },
        {   # Level 5+ — Shadow void (deep purple/black)
            "wall_base":   (35, 18, 40),
            "wall_bricks": [(72, 40, 80), (58, 32, 68), (82, 48, 92)],
            "wall_mortar": (42, 22, 48),
            "floor_base":  (6, 2, 8),
            "floor_detail": (28, 12, 32),
            "accent":      (160, 80, 200),
            "env_type":    "void",
        },
    ]

    def _get_dungeon_palette(self, level):
        """Return the palette dict for the given dungeon depth (0-based)."""
        idx = min(level, len(self._DUNGEON_PALETTES) - 1)
        return self._DUNGEON_PALETTES[idx]

    def draw_dungeon_u3(self, party, dungeon_data, message="",
                         visible_tiles=None, torch_steps=-1,
                         level_label=None, detected_traps=None,
                         door_unlock_anim=None, door_interact=None,
                         infravision=False, galadriels_light=False,
                         artifact_pickup_anim=None,
                         dungeon_level=0):
        """
        Full Ultima III-style dungeon screen — full-width map with bottom info bar.
        Fog of war limits visibility.
        """
        self.screen.fill((0, 0, 0))

        ts = self._U3_DG_TS
        cols = self._U3_DG_COLS
        rows = self._U3_DG_ROWS

        tile_map = dungeon_data.tile_map

        # ── compute camera offset ──
        off_c = party.col - cols // 2
        off_r = party.row - rows // 2
        off_c = max(0, min(off_c, tile_map.width - cols))
        off_r = max(0, min(off_r, tile_map.height - rows))

        # ── 1. draw map tiles ──
        palette = self._get_dungeon_palette(dungeon_level)
        for sr in range(rows):
            for sc in range(cols):
                wc = sc + off_c
                wr = sr + off_r
                tid = tile_map.get_tile(wc, wr)
                px = sc * ts
                py = sr * ts
                self._u3_draw_dungeon_tile(tid, px, py, ts, wc, wr, palette)

        # ── 1b. red glow on detected traps ──
        if detected_traps:
            import math
            pulse = 0.55 + 0.45 * math.sin(pygame.time.get_ticks() * 0.005)
            alpha = int(70 * pulse)
            for (tc, tr) in detected_traps:
                sc_t = tc - off_c
                sr_t = tr - off_r
                if 0 <= sc_t < cols and 0 <= sr_t < rows:
                    glow_rect = pygame.Rect(sc_t * ts, sr_t * ts, ts, ts)
                    glow_surf = pygame.Surface((ts, ts), pygame.SRCALPHA)
                    glow_surf.fill((255, 30, 30, alpha))
                    self.screen.blit(glow_surf, glow_rect)
                    # Bright red X over the trap
                    cx_t = sc_t * ts + ts // 2
                    cy_t = sr_t * ts + ts // 2
                    line_col = (255, int(50 * pulse), int(50 * pulse))
                    pygame.draw.line(self.screen, line_col,
                                     (cx_t - 6, cy_t - 6), (cx_t + 6, cy_t + 6), 2)
                    pygame.draw.line(self.screen, line_col,
                                     (cx_t + 6, cy_t - 6), (cx_t - 6, cy_t + 6), 2)

        # ── 1c. animated glow on artifact tiles ──
        import math as _math
        _art_t = pygame.time.get_ticks()
        _art_pulse = 0.5 + 0.5 * _math.sin(_art_t * 0.004)
        _art_ring = (0.5 + 0.5 * _math.sin(_art_t * 0.002)) * 6 + 8
        for sr2 in range(rows):
            for sc2 in range(cols):
                wc2 = sc2 + off_c
                wr2 = sr2 + off_r
                if tile_map.get_tile(wc2, wr2) == TILE_ARTIFACT:
                    # Skip if not visible
                    if visible_tiles and (wc2, wr2) not in visible_tiles:
                        continue
                    acx = sc2 * ts + ts // 2
                    acy = sr2 * ts + ts // 2
                    # Outer pulsing ring
                    ring_r = int(_art_ring)
                    ring_alpha = int(80 * _art_pulse)
                    ring_surf = pygame.Surface((ts, ts), pygame.SRCALPHA)
                    pygame.draw.circle(ring_surf, (200, 100, 255, ring_alpha),
                                       (ts // 2, ts // 2), ring_r, 2)
                    self.screen.blit(ring_surf, (sc2 * ts, sr2 * ts))
                    # Inner golden glow
                    glow_alpha = int(60 + 50 * _art_pulse)
                    glow_surf = pygame.Surface((ts, ts), pygame.SRCALPHA)
                    pygame.draw.circle(glow_surf,
                                       (255, 220, 100, glow_alpha),
                                       (ts // 2, ts // 2), 6)
                    self.screen.blit(glow_surf, (sc2 * ts, sr2 * ts))
                    # Rotating sparkles
                    for i in range(4):
                        angle = _art_t * 0.003 + i * 1.5708
                        sp_r = 8 + 3 * _math.sin(_art_t * 0.006 + i)
                        sx = acx + int(_math.cos(angle) * sp_r)
                        sy = acy + int(_math.sin(angle) * sp_r)
                        brightness = int(180 + 75 * _art_pulse)
                        pygame.draw.circle(self.screen,
                                           (brightness, brightness, 200), (sx, sy), 1)

        # ── 1d. animated glow on portal tiles ──
        _ptl_pulse = 0.5 + 0.5 * _math.sin(_art_t * 0.005)
        _ptl_ring  = 0.5 + 0.5 * _math.sin(_art_t * 0.0025)
        for sr2 in range(rows):
            for sc2 in range(cols):
                wc2 = sc2 + off_c
                wr2 = sr2 + off_r
                if tile_map.get_tile(wc2, wr2) == TILE_PORTAL:
                    if visible_tiles and (wc2, wr2) not in visible_tiles:
                        continue
                    pcx = sc2 * ts + ts // 2
                    pcy = sr2 * ts + ts // 2
                    # Pulsing cyan aura
                    aura_alpha = int(40 + 50 * _ptl_pulse)
                    aura_surf = pygame.Surface((ts, ts), pygame.SRCALPHA)
                    aura_surf.fill((0, 180, 255, aura_alpha))
                    self.screen.blit(aura_surf, (sc2 * ts, sr2 * ts))
                    # Outer energy ring
                    ring_r2 = int(10 + 4 * _ptl_ring)
                    ring_surf2 = pygame.Surface((ts, ts), pygame.SRCALPHA)
                    pygame.draw.circle(ring_surf2, (0, 220, 255, int(90 * _ptl_pulse)),
                                       (ts // 2, ts // 2), ring_r2, 2)
                    self.screen.blit(ring_surf2, (sc2 * ts, sr2 * ts))
                    # Orbiting energy motes (6 motes, cyan/white)
                    for i in range(6):
                        angle = _art_t * 0.004 + i * 1.0472  # 60 degrees apart
                        m_r = 7 + 3 * _math.sin(_art_t * 0.005 + i * 0.8)
                        mx = pcx + int(_math.cos(angle) * m_r)
                        my = pcy + int(_math.sin(angle) * m_r)
                        bright = int(160 + 95 * _ptl_pulse)
                        col_mote = (bright // 2, bright, 255) if i % 2 == 0 else (bright, bright, 255)
                        pygame.draw.circle(self.screen, col_mote, (mx, my), 1)

        # ── 1e. animated torch light glow ──
        # Wall torches cast a warm flickering light on nearby floor tiles
        _torch_flicker = 0.6 + 0.4 * _math.sin(_art_t * 0.008)
        _torch_flicker2 = 0.6 + 0.4 * _math.sin(_art_t * 0.011 + 1.5)
        _torch_radius = 3  # tiles of light radius
        for sr2 in range(rows):
            for sc2 in range(cols):
                wc2 = sc2 + off_c
                wr2 = sr2 + off_r
                if tile_map.get_tile(wc2, wr2) == TILE_WALL_TORCH:
                    if visible_tiles and (wc2, wr2) not in visible_tiles:
                        continue
                    # Light up surrounding tiles in a radius
                    for dr in range(-_torch_radius, _torch_radius + 1):
                        for dc in range(-_torch_radius, _torch_radius + 1):
                            dist = abs(dr) + abs(dc)
                            if dist == 0 or dist > _torch_radius:
                                continue
                            nsc = sc2 + dc
                            nsr = sr2 + dr
                            if 0 <= nsc < cols and 0 <= nsr < rows:
                                # Use alternating flicker for variety
                                flk = _torch_flicker if (dc + dr) % 2 == 0 else _torch_flicker2
                                # Intensity falls off with distance
                                intensity = (1.0 - dist / (_torch_radius + 1)) * flk
                                alpha = int(35 * intensity)
                                if alpha > 0:
                                    glow_s = pygame.Surface((ts, ts), pygame.SRCALPHA)
                                    glow_s.fill((255, 160, 50, alpha))
                                    self.screen.blit(glow_s, (nsc * ts, nsr * ts))

        # ── 2. monster sprites (only within visible tiles) ──
        for monster in dungeon_data.monsters:
            if not monster.is_alive():
                continue
            msc = monster.col - off_c
            msr = monster.row - off_r
            if 0 <= msc < cols and 0 <= msr < rows:
                _vis = visible_tiles and (monster.col, monster.row) in visible_tiles
                _fallback = not visible_tiles and abs(monster.col - party.col) <= 1 and abs(monster.row - party.row) <= 1
                if _vis or _fallback:
                    mx = msc * ts + ts // 2
                    my = msr * ts + ts // 2
                    self._u3_draw_dungeon_monster(monster, mx, my)

        # ── 3. party sprite ──
        psc = party.col - off_c
        psr = party.row - off_r
        if 0 <= psc < cols and 0 <= psr < rows:
            cx = psc * ts + ts // 2
            cy = psr * ts + ts // 2
            self._u3_draw_overworld_party(cx, cy, party)

        # ── 3b. infravision red/black tint ──
        if infravision:
            self._u3_infravision_tint(cols, rows, ts, visible_tiles,
                                       off_c, off_r, psc, psr)
        # ── 3c. Galadriel's Light blue tint ──
        elif galadriels_light:
            self._u3_galadriels_tint(cols, rows, ts, visible_tiles,
                                      off_c, off_r, psc, psr)

        # ── 4. fog of war ──
        self._u3_dungeon_fog(psc, psr, cols, rows, ts,
                              visible_tiles=visible_tiles, off_c=off_c, off_r=off_r)

        # ── 4b. door unlock animation ──
        if door_unlock_anim:
            self._u3_draw_door_unlock_anim(door_unlock_anim, off_c, off_r,
                                            cols, rows, ts)

        # ── 4c. artifact pickup animation ──
        if artifact_pickup_anim:
            self._u3_draw_artifact_pickup(artifact_pickup_anim, off_c, off_r,
                                           cols, rows, ts)

        # ── 5. blue border around map ──
        pygame.draw.rect(self.screen, (68, 68, 255),
                         pygame.Rect(0, 0, self._U3_DG_MAP_W, self._U3_DG_MAP_H), 2)

        # ── 6. bottom info bar ──
        bar_y = self._U3_DG_MAP_H
        bar_h = SCREEN_HEIGHT - bar_y
        self._u3_panel(0, bar_y, SCREEN_WIDTH, bar_h)

        tile_name = dungeon_data.tile_map.get_tile_name(party.col, party.row)
        chests = len(dungeon_data.opened_chests)
        # Top line: game info
        self._u3_text(f"GOLD:{party.gold:d}", 8, bar_y + 6, (255, 255, 0))
        dg_name = dungeon_data.name.upper()
        if level_label:
            dg_name += f"  [{level_label}]"
        self._u3_text(dg_name, 240, bar_y + 6, (200, 60, 60))
        # Light status
        light_name = party.get_equipped_name("light")
        light_charges = party.get_equipped_charges("light")
        if torch_steps >= 0:
            torch_color = (255, 170, 85) if torch_steps > 3 else (200, 60, 60)
            lbl = f"LIGHT:{light_name.upper() if light_name else 'TORCH'}:{torch_steps:d}"
            self._u3_text(lbl, 520, bar_y + 6, torch_color)
        elif infravision:
            self._u3_text("INFRAVISION", 520, bar_y + 6, (200, 40, 40))
        elif galadriels_light:
            gl_steps = party.galadriels_light_steps
            gl_color = (120, 160, 255) if gl_steps > 50 else (200, 100, 100)
            self._u3_text(f"STARLIGHT:{gl_steps:d}", 520, bar_y + 6, gl_color)
        elif light_name:
            lbl = f"LIGHT:{light_name.upper()}"
            if light_charges is not None:
                lbl += f":{light_charges:d}"
            self._u3_text(lbl, 520, bar_y + 6, (255, 170, 85))
        else:
            self._u3_text("NO LIGHT", 520, bar_y + 6, (136, 136, 136))
        self._u3_text(f"POS:({party.col},{party.row})", 750, bar_y + 6, (136, 136, 136))
        # Bottom line: controls
        self._u3_text("[ARROWS/WASD] MOVE    [P] PARTY    [ESC] STAIRS",
                      8, bar_y + 28, (68, 68, 255))

        # ── 7. floating message ──
        self._draw_floating_message(message)

        # ── 8. door interaction prompt ──
        if door_interact:
            self._u3_draw_door_interact(door_interact, off_c, off_r, ts)

    # ── dungeon tile rendering ─────────────────────────────

    # ── door unlock animation & interaction prompt ───────────

    def _u3_draw_door_unlock_anim(self, anim, off_c, off_r, cols, rows, ts):
        """Draw the door-unlock animation: iron bands snap, lock shatters, door swings open.

        Four phases:
        1. (0.0-0.2) Lock shakes and glows — thief is working the pick
        2. (0.2-0.5) Lock shatters — sparks fly outward
        3. (0.5-0.8) Iron bands crack and fall away with flash
        4. (0.8-1.0) Door swings open — planks lighten to regular door color
        """
        import math

        col, row = anim["col"], anim["row"]
        sc = col - off_c
        sr = row - off_r
        if not (0 <= sc < cols and 0 <= sr < rows):
            return

        px = sc * ts
        py = sr * ts
        cx = px + ts // 2
        cy = py + ts // 2

        duration = anim["duration"]
        elapsed = duration - anim["timer"]
        p = max(0.0, min(1.0, elapsed / duration))
        ticks = pygame.time.get_ticks()

        if p < 0.2:
            # Phase 1: Lock shakes and glows
            sub_p = p / 0.2
            shake_x = int(2 * math.sin(ticks * 0.04) * (1.0 - sub_p * 0.5))
            shake_y = int(1 * math.cos(ticks * 0.05))

            # Draw the locked door with shake offset
            door_rect = pygame.Rect(px + 5 + shake_x, py + 2 + shake_y,
                                    ts - 10, ts - 4)
            pygame.draw.rect(self.screen, (0, 0, 0),
                             pygame.Rect(px, py, ts, ts))
            pygame.draw.rect(self.screen, (60, 38, 18), door_rect)
            # Iron bands
            for dy_frac in (4, ts // 2, ts - 8):
                pygame.draw.line(self.screen, (100, 100, 110),
                                 (px + 5 + shake_x, py + dy_frac + shake_y),
                                 (px + ts - 5 + shake_x, py + dy_frac + shake_y), 2)

            # Glowing keyhole (pulsing orange/yellow)
            glow = int(180 + 75 * sub_p * math.sin(ticks * 0.02))
            glow = max(0, min(255, glow))
            pygame.draw.circle(self.screen, (glow, glow // 2, 0),
                               (cx + shake_x, cy + shake_y), 4)

        elif p < 0.5:
            # Phase 2: Lock shatters — sparks fly outward
            sub_p = (p - 0.2) / 0.3

            # Draw door (no shake now)
            pygame.draw.rect(self.screen, (0, 0, 0),
                             pygame.Rect(px, py, ts, ts))
            door_rect = pygame.Rect(px + 5, py + 2, ts - 10, ts - 4)
            pygame.draw.rect(self.screen, (60, 38, 18), door_rect)
            # Iron bands still visible but dimming
            band_bright = int(110 * (1.0 - sub_p * 0.5))
            for dy_frac in (4, ts // 2, ts - 8):
                pygame.draw.line(self.screen, (band_bright, band_bright, band_bright + 10),
                                 (px + 5, py + dy_frac),
                                 (px + ts - 5, py + dy_frac), 2)

            # Sparks flying outward from the lock position
            num_sparks = 8
            for i in range(num_sparks):
                angle = (i / num_sparks) * 6.283 + ticks * 0.003
                dist = ts * 0.3 * sub_p + ts * 0.1
                sx = cx + int(math.cos(angle) * dist)
                sy = cy + int(math.sin(angle) * dist)
                spark_alpha = max(0.0, 1.0 - sub_p)
                bright = int(255 * spark_alpha)
                if bright > 20:
                    pygame.draw.circle(self.screen,
                                       (bright, bright // 2, 0),
                                       (sx, sy), max(1, int(2 * spark_alpha)))

            # Bright flash at center
            flash = int(200 * max(0.0, 1.0 - sub_p * 2))
            if flash > 10:
                pygame.draw.circle(self.screen, (flash, flash, flash // 2),
                                   (cx, cy), max(1, int(5 * (1.0 - sub_p))))

        elif p < 0.8:
            # Phase 3: Iron bands crack and fall — door color transitions
            sub_p = (p - 0.5) / 0.3

            pygame.draw.rect(self.screen, (0, 0, 0),
                             pygame.Rect(px, py, ts, ts))

            # Door wood color transitions from dark locked to lighter open
            r_col = int(60 + 30 * sub_p)
            g_col = int(38 + 17 * sub_p)
            b_col = int(18 + 7 * sub_p)
            door_rect = pygame.Rect(px + 5, py + 2, ts - 10, ts - 4)
            pygame.draw.rect(self.screen, (r_col, g_col, b_col), door_rect)

            # Iron band fragments falling
            band_alpha = max(0.0, 1.0 - sub_p * 1.5)
            if band_alpha > 0.05:
                band_b = int(100 * band_alpha)
                fall_offset = int(sub_p * ts * 0.3)
                for dy_frac in (4, ts // 2, ts - 8):
                    # Fragments fall downward and spread apart
                    y_off = py + dy_frac + fall_offset
                    spread = int(sub_p * 4)
                    if band_b > 5:
                        pygame.draw.line(self.screen, (band_b, band_b, band_b + 10),
                                         (px + 5 - spread, y_off),
                                         (px + ts // 2 - 2, y_off), 2)
                        pygame.draw.line(self.screen, (band_b, band_b, band_b + 10),
                                         (px + ts // 2 + 2, y_off),
                                         (px + ts - 5 + spread, y_off), 2)

            # Plank lines start appearing
            plank_alpha = sub_p
            if plank_alpha > 0.1:
                plank_b = int(60 * plank_alpha)
                for dy in range(4, ts - 6, 6):
                    pygame.draw.line(self.screen, (plank_b, int(plank_b * 0.58), int(plank_b * 0.25)),
                                     (px + 7, py + dy), (px + ts - 7, py + dy), 1)

        else:
            # Phase 4: Door is now open — draw as regular door with gentle glow
            sub_p = (p - 0.8) / 0.2

            pygame.draw.rect(self.screen, (0, 0, 0),
                             pygame.Rect(px, py, ts, ts))
            door_rect = pygame.Rect(px + 6, py + 2, ts - 12, ts - 4)
            pygame.draw.rect(self.screen, (90, 55, 25), door_rect)
            # Plank lines
            for dy in range(4, ts - 6, 6):
                pygame.draw.line(self.screen, (60, 35, 15),
                                 (px + 7, py + dy), (px + ts - 7, py + dy), 1)
            # Handle
            pygame.draw.circle(self.screen, (255, 255, 0), (cx + 4, cy), 2)
            pygame.draw.rect(self.screen, (60, 35, 15), door_rect, 1)

            # Fading golden glow around the opened door
            glow_f = 1.0 - sub_p
            glow_bright = int(120 * glow_f)
            if glow_bright > 5:
                glow_surf = pygame.Surface((ts + 8, ts + 8), pygame.SRCALPHA)
                glow_surf.fill((glow_bright, int(glow_bright * 0.85), 0,
                                int(40 * glow_f)))
                self.screen.blit(glow_surf, (px - 4, py - 4))

    def _u3_draw_artifact_pickup(self, anim, off_c, off_r, cols, rows, ts):
        """Draw artifact pickup celebration: expanding rings, rising sparks,
        and a floating artifact name that rises and fades."""
        import math

        col, row = anim["col"], anim["row"]
        sc = col - off_c
        sr = row - off_r
        if not (0 <= sc < cols and 0 <= sr < rows):
            return

        progress = 1.0 - (anim["timer"] / anim["duration"])
        cx = sc * ts + ts // 2
        cy = sr * ts + ts // 2

        # Phase 1 (0.0–0.4): bright flash + expanding golden rings
        if progress < 0.4:
            p = progress / 0.4
            # Central flash — white circle that expands and fades
            flash_r = int(4 + 20 * p)
            flash_a = int(255 * (1.0 - p))
            flash_surf = pygame.Surface((ts * 3, ts * 3), pygame.SRCALPHA)
            pygame.draw.circle(flash_surf, (255, 255, 220, flash_a),
                               (ts * 3 // 2, ts * 3 // 2), flash_r)
            self.screen.blit(flash_surf,
                             (cx - ts * 3 // 2, cy - ts * 3 // 2))
            # Two expanding golden rings
            for i in range(2):
                ring_p = max(0.0, p - i * 0.15)
                ring_r = int(6 + 30 * ring_p)
                ring_a = int(200 * (1.0 - ring_p))
                if ring_a > 0:
                    ring_surf = pygame.Surface((ts * 3, ts * 3), pygame.SRCALPHA)
                    pygame.draw.circle(ring_surf, (255, 200, 50, ring_a),
                                       (ts * 3 // 2, ts * 3 // 2), ring_r, 2)
                    self.screen.blit(ring_surf,
                                     (cx - ts * 3 // 2, cy - ts * 3 // 2))

        # Phase 2 (0.2–0.8): sparkles rise upward
        if 0.2 < progress < 0.8:
            sp = (progress - 0.2) / 0.6
            num_sparks = 12
            for i in range(num_sparks):
                angle = i * (2 * math.pi / num_sparks) + sp * 2
                dist = 6 + 18 * sp
                sx = cx + int(math.cos(angle) * dist)
                sy = cy - int(8 + 30 * sp) + int(math.sin(angle * 2) * 4)
                alpha = int(255 * (1.0 - sp))
                spark_col = (255, 220, 80) if i % 2 == 0 else (200, 120, 255)
                spark_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
                # Cross sparkle
                pygame.draw.line(spark_surf, (*spark_col, alpha),
                                 (3, 0), (3, 5), 1)
                pygame.draw.line(spark_surf, (*spark_col, alpha),
                                 (0, 3), (5, 3), 1)
                self.screen.blit(spark_surf, (sx - 3, sy - 3))

        # Phase 3 (0.3–1.0): floating artifact name rises and fades
        if progress > 0.3:
            tp = (progress - 0.3) / 0.7
            text_alpha = int(255 * (1.0 - tp * tp))
            text_y = cy - 20 - int(40 * tp)
            name = anim.get("name", "ARTIFACT")
            text_surf = self.font_small.render(name.upper(), True,
                                                (255, 220, 100))
            # Create alpha surface
            alpha_surf = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
            alpha_surf.blit(text_surf, (0, 0))
            alpha_surf.set_alpha(text_alpha)
            tx = cx - text_surf.get_width() // 2
            self.screen.blit(alpha_surf, (tx, text_y))

        # Phase 2b (0.4–0.7): brief purple diamond shape expanding
        if 0.4 < progress < 0.7:
            dp = (progress - 0.4) / 0.3
            d_size = int(4 + 16 * dp)
            d_alpha = int(180 * (1.0 - dp))
            diamond = [
                (cx, cy - d_size),
                (cx + d_size, cy),
                (cx, cy + d_size),
                (cx - d_size, cy),
            ]
            d_surf = pygame.Surface((ts * 3, ts * 3), pygame.SRCALPHA)
            offset_pts = [(x - cx + ts * 3 // 2, y - cy + ts * 3 // 2)
                          for x, y in diamond]
            pygame.draw.polygon(d_surf, (200, 100, 255, d_alpha), offset_pts, 2)
            self.screen.blit(d_surf, (cx - ts * 3 // 2, cy - ts * 3 // 2))

    def _u3_draw_door_interact(self, interact, off_c, off_r, ts):
        """Draw the locked-door interaction prompt panel near the door.

        Shows a small panel with a title and selectable options.
        """
        col, row = interact["col"], interact["row"]
        cursor = interact["cursor"]
        options = interact["options"]

        # Position the panel at center of screen
        panel_w = 280
        line_h = 22
        panel_h = 30 + line_h * len(options) + 10
        panel_x = (SCREEN_WIDTH - panel_w) // 2
        panel_y = (SCREEN_HEIGHT - panel_h) // 2 - 30

        # Dark panel with border
        self._u3_panel(panel_x, panel_y, panel_w, panel_h)

        # Title
        self._u3_text("LOCKED DOOR", panel_x + 10, panel_y + 8,
                       (255, 200, 100), self.font)

        # Options
        oy = panel_y + 30
        for i, (label, action_key) in enumerate(options):
            is_selected = (i == cursor)
            if is_selected:
                # Highlight bar
                highlight = pygame.Rect(panel_x + 4, oy - 1,
                                        panel_w - 8, line_h)
                pygame.draw.rect(self.screen, (40, 40, 80), highlight)

                # Arrow indicator
                self._u3_text(">", panel_x + 10, oy,
                              (255, 220, 100), self.font_small)

            # Determine color based on action availability
            if action_key in ("no_picks", "no_thief"):
                color = (120, 100, 100)  # greyed out
            elif is_selected:
                color = (255, 255, 255)
            else:
                color = (180, 180, 200)

            self._u3_text(label.upper(), panel_x + 26, oy, color,
                          self.font_small)
            oy += line_h

        # Hint text
        self._u3_text("[ENTER] SELECT  [ESC] LEAVE",
                       panel_x + 10, oy + 2, (80, 80, 140), self.font_small)

        # Draw a pulsing indicator on the locked door tile
        sc = col - off_c
        sr = row - off_r
        ticks = pygame.time.get_ticks()
        import math
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
        alpha = int(50 + 40 * pulse)
        door_px = sc * ts
        door_py = sr * ts
        glow_surf = pygame.Surface((ts, ts), pygame.SRCALPHA)
        glow_surf.fill((255, 180, 60, alpha))
        self.screen.blit(glow_surf, (door_px, door_py))

    def _u3_draw_dungeon_tile(self, tile_id, px, py, ts, wc, wr, palette=None):
        """Draw a single dungeon tile in Ultima III style."""
        BLACK  = (0, 0, 0)
        WHITE  = (255, 255, 255)
        BLUE   = (68, 68, 255)
        GRAY   = (136, 136, 136)
        DKGRAY = (60, 55, 65)
        PURPLE = (102, 51, 85)
        DKPUR  = (68, 34, 68)
        BROWN  = (140, 100, 50)
        ORANGE = (255, 170, 85)
        YELLOW = (255, 255, 0)

        # Default palette (level 1 stone) if none provided
        if palette is None:
            palette = self._DUNGEON_PALETTES[0]

        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2
        seed = wc * 31 + wr * 17

        if tile_id == TILE_DWALL:
            # Stone blocks — colors from level palette
            pygame.draw.rect(self.screen, palette["wall_base"], rect)
            bricks = palette["wall_bricks"]
            mortar = palette["wall_mortar"]
            for iy in range(0, ts, 8):
                offset = 5 if (iy // 8) % 2 else 0
                for ix in range(offset, ts, 11):
                    s = (wc * 7 + wr * 13 + ix + iy) % 5
                    if s < 2:
                        bc = bricks[0]
                    elif s < 4:
                        bc = bricks[1]
                    else:
                        bc = bricks[2]
                    brick = pygame.Rect(px + ix, py + iy, 9, 6)
                    pygame.draw.rect(self.screen, bc, brick)
                    pygame.draw.rect(self.screen, mortar, brick, 1)

            # Environmental details on walls
            env = palette["env_type"]
            if env == "moss":
                # Moss patches on some wall tiles
                if seed % 3 == 0:
                    mx = (seed * 7) % (ts - 8) + 2
                    my = ts - 4
                    for i in range(3):
                        gx = px + mx + i * 3 - 3
                        gy = py + my - (seed + i) % 3
                        pygame.draw.rect(self.screen, (40, 90, 35),
                                         pygame.Rect(gx, gy, 2, 2))
            elif env == "lava":
                # Glowing cracks in walls
                if seed % 4 == 0:
                    lx = px + (seed * 3) % (ts - 6) + 3
                    pygame.draw.line(self.screen, (200, 80, 20),
                                     (lx, py + ts - 2), (lx + 3, py + ts - 8), 1)
            elif env == "ice":
                # Frost crystals on walls
                if seed % 3 == 0:
                    fx = px + (seed * 5) % (ts - 8) + 4
                    fy = py + (seed * 3) % (ts - 8) + 4
                    pygame.draw.line(self.screen, (160, 200, 240),
                                     (fx, fy), (fx + 4, fy - 3), 1)
                    pygame.draw.line(self.screen, (160, 200, 240),
                                     (fx, fy), (fx - 2, fy - 4), 1)
            elif env == "void":
                # Faint purple energy wisps
                if seed % 5 == 0:
                    import math as _m
                    t = pygame.time.get_ticks() * 0.003 + seed
                    vx = px + ts // 2 + int(_m.sin(t) * 4)
                    vy = py + ts // 2 + int(_m.cos(t * 0.7) * 3)
                    pygame.draw.circle(self.screen, (120, 50, 160),
                                       (vx, vy), 2)

        elif tile_id == TILE_DFLOOR:
            # Floor — colors from level palette
            pygame.draw.rect(self.screen, palette["floor_base"], rect)
            detail_col = palette["floor_detail"]
            for i in range(2):
                s = seed + i * 41
                if s % 4 < 2:
                    dx = (s * 7) % (ts - 6) + 3
                    dy = (s * 13) % (ts - 6) + 3
                    pygame.draw.rect(self.screen, detail_col,
                                     pygame.Rect(px + dx, py + dy, 2, 1))

            # Environmental floor details
            env = palette["env_type"]
            if env == "moss":
                # Small moss spots on floor
                if seed % 5 == 0:
                    mx = (seed * 11) % (ts - 4) + 2
                    my = (seed * 7) % (ts - 4) + 2
                    pygame.draw.rect(self.screen, (25, 55, 22),
                                     pygame.Rect(px + mx, py + my, 3, 2))
            elif env == "lava":
                # Lava glow seeping through floor cracks
                if seed % 6 < 2:
                    lx = (seed * 9) % (ts - 8) + 4
                    ly = (seed * 5) % (ts - 6) + 3
                    glow_c = (140 + (seed % 40), 40 + (seed % 20), 10)
                    pygame.draw.line(self.screen, glow_c,
                                     (px + lx, py + ly),
                                     (px + lx + 5, py + ly + 2), 1)
            elif env == "ice":
                # Ice sheen on floor
                if seed % 4 == 0:
                    shine = pygame.Surface((ts, ts), pygame.SRCALPHA)
                    shine.fill((100, 150, 220, 12))
                    self.screen.blit(shine, (px, py))
            elif env == "void":
                # Dark energy tendrils on floor
                if seed % 7 < 2:
                    vx = (seed * 3) % (ts - 6) + 3
                    vy = (seed * 11) % (ts - 6) + 3
                    pygame.draw.circle(self.screen, (60, 20, 70),
                                       (px + vx, py + vy), 2)

        elif tile_id == TILE_WALL:
            # Town-interior walls reused in dungeon — same stone style
            pygame.draw.rect(self.screen, (30, 28, 40), rect)
            for iy in range(0, ts, 8):
                offset = 5 if (iy // 8) % 2 else 0
                for ix in range(offset, ts, 11):
                    s = (wc * 7 + wr * 13 + ix + iy) % 5
                    bc = (75, 70, 90) if s < 2 else (60, 58, 78)
                    brick = pygame.Rect(px + ix, py + iy, 9, 6)
                    pygame.draw.rect(self.screen, bc, brick)
                    pygame.draw.rect(self.screen, (40, 38, 55), brick, 1)

        elif tile_id == TILE_FLOOR:
            # Town-interior floor — same as dungeon floor
            pygame.draw.rect(self.screen, BLACK, rect)
            if seed % 5 < 2:
                dx = (seed * 7) % (ts - 6) + 3
                dy = (seed * 13) % (ts - 6) + 3
                pygame.draw.rect(self.screen, (30, 28, 35),
                                 pygame.Rect(px + dx, py + dy, 2, 1))

        elif tile_id == TILE_STAIRS:
            # Stairs up — stone steps with blue-white highlight
            pygame.draw.rect(self.screen, BLACK, rect)
            for i in range(4):
                step_y = py + 4 + i * 7
                step_w = ts - 8 - i * 3
                step_x = px + 4 + i
                sc = 90 + i * 15  # gradually lighter
                step_rect = pygame.Rect(step_x, step_y, step_w, 5)
                pygame.draw.rect(self.screen, (sc, sc, sc + 20), step_rect)
                pygame.draw.rect(self.screen, (50, 50, 60), step_rect, 1)
            # Up arrow
            arrow = [(cx, py + 2), (cx - 4, py + 6), (cx + 4, py + 6)]
            pygame.draw.polygon(self.screen, BLUE, arrow)

        elif tile_id == TILE_CHEST:
            # Treasure chest — use reference tile image
            if self._chest_tile:
                self.screen.blit(self._chest_tile, (rect.x, rect.y))
            else:
                # Fallback procedural
                pygame.draw.rect(self.screen, BLACK, rect)
                body = pygame.Rect(cx - 7, cy - 2, 14, 9)
                pygame.draw.rect(self.screen, BROWN, body)
                pygame.draw.rect(self.screen, (100, 70, 30), body, 1)
                lid = pygame.Rect(cx - 7, cy - 6, 14, 5)
                pygame.draw.rect(self.screen, (160, 115, 40), lid)
                pygame.draw.rect(self.screen, (100, 70, 30), lid, 1)
                pygame.draw.circle(self.screen, YELLOW, (cx, cy), 2)

        elif tile_id == TILE_TRAP:
            # Trap — looks like floor but with faint red X
            pygame.draw.rect(self.screen, BLACK, rect)
            pygame.draw.line(self.screen, (60, 20, 20),
                             (cx - 5, cy - 5), (cx + 5, cy + 5), 1)
            pygame.draw.line(self.screen, (60, 20, 20),
                             (cx + 5, cy - 5), (cx - 5, cy + 5), 1)

        elif tile_id == TILE_COUNTER:
            # Counter/table
            pygame.draw.rect(self.screen, BLACK, rect)
            top = pygame.Rect(px + 3, py + 8, ts - 6, ts - 14)
            pygame.draw.rect(self.screen, BROWN, top)
            pygame.draw.rect(self.screen, (100, 70, 30), top, 1)
            pygame.draw.circle(self.screen, YELLOW, (cx, cy), 3)

        elif tile_id == TILE_DOOR:
            # Wooden door
            pygame.draw.rect(self.screen, BLACK, rect)
            door_rect = pygame.Rect(px + 7, py + 2, ts - 14, ts - 4)
            pygame.draw.rect(self.screen, (100, 65, 30), door_rect)
            pygame.draw.rect(self.screen, (60, 40, 15), door_rect, 1)
            pygame.draw.circle(self.screen, YELLOW, (cx + 3, cy), 2)

        elif tile_id == TILE_EXIT:
            # Exit marker — green arrow on black
            pygame.draw.rect(self.screen, BLACK, rect)
            arrow = [(cx, cy + 8), (cx - 6, cy - 2), (cx + 6, cy - 2)]
            pygame.draw.polygon(self.screen, (0, 170, 0), arrow)

        elif tile_id == TILE_STAIRS_DOWN:
            # Stairs down — darker steps with down arrow
            pygame.draw.rect(self.screen, BLACK, rect)
            for i in range(4):
                step_y = py + 4 + i * 7
                step_w = ts - 8 - (3 - i) * 3
                step_x = px + 4 + (3 - i)
                sc = 90 - i * 12  # gradually darker
                step_rect = pygame.Rect(step_x, step_y, step_w, 5)
                pygame.draw.rect(self.screen, (sc, sc - 10, sc - 5), step_rect)
                pygame.draw.rect(self.screen, (40, 35, 45), step_rect, 1)
            # Down arrow
            arrow = [(cx, py + ts - 3), (cx - 4, py + ts - 7), (cx + 4, py + ts - 7)]
            pygame.draw.polygon(self.screen, ORANGE, arrow)

        elif tile_id == TILE_DDOOR:
            # Dungeon door — brown planks
            pygame.draw.rect(self.screen, BLACK, rect)
            door_rect = pygame.Rect(px + 6, py + 2, ts - 12, ts - 4)
            pygame.draw.rect(self.screen, (90, 55, 25), door_rect)
            # Plank lines
            for dy in range(4, ts - 6, 6):
                pygame.draw.line(self.screen, (60, 35, 15),
                                 (px + 7, py + dy), (px + ts - 7, py + dy), 1)
            # Handle
            pygame.draw.circle(self.screen, YELLOW, (cx + 4, cy), 2)
            pygame.draw.rect(self.screen, (60, 35, 15), door_rect, 1)

        elif tile_id == TILE_LOCKED_DOOR:
            # Locked dungeon door — iron-bound dark planks with keyhole
            pygame.draw.rect(self.screen, BLACK, rect)
            door_rect = pygame.Rect(px + 5, py + 2, ts - 10, ts - 4)
            pygame.draw.rect(self.screen, (60, 38, 18), door_rect)
            # Iron bands
            for dy in (4, ts // 2, ts - 8):
                pygame.draw.line(self.screen, (100, 100, 110),
                                 (px + 5, py + dy), (px + ts - 5, py + dy), 2)
            # Keyhole
            pygame.draw.circle(self.screen, (180, 170, 50), (cx, cy), 3)
            pygame.draw.circle(self.screen, (30, 20, 10), (cx, cy), 2)
            pygame.draw.line(self.screen, (30, 20, 10),
                             (cx, cy), (cx, cy + 4), 1)
            # Border
            pygame.draw.rect(self.screen, (80, 80, 90), door_rect, 1)

        elif tile_id == TILE_ARTIFACT:
            # Glowing crystal on pedestal
            pygame.draw.rect(self.screen, BLACK, rect)
            # Pedestal
            ped = pygame.Rect(cx - 5, cy + 4, 10, 6)
            pygame.draw.rect(self.screen, GRAY, ped)
            pygame.draw.rect(self.screen, (100, 100, 110), ped, 1)
            # Crystal — diamond shape
            crystal = [
                (cx, cy - 8),       # top
                (cx + 5, cy),       # right
                (cx, cy + 4),       # bottom
                (cx - 5, cy),       # left
            ]
            pygame.draw.polygon(self.screen, (180, 60, 200), crystal)
            pygame.draw.polygon(self.screen, (220, 100, 255), crystal, 1)
            # Glow effect
            glow = pygame.Surface((16, 16), pygame.SRCALPHA)
            pygame.draw.circle(glow, (200, 100, 255, 50), (8, 8), 8)
            self.screen.blit(glow, (cx - 8, cy - 8))

        elif tile_id == TILE_PORTAL:
            # Swirling portal doorway — distinct cyan/blue energy arch
            pygame.draw.rect(self.screen, BLACK, rect)
            # Stone archway frame
            arch_color = (100, 100, 120)
            # Left pillar
            pygame.draw.rect(self.screen, arch_color,
                             pygame.Rect(px + 3, py + 6, 5, ts - 8))
            # Right pillar
            pygame.draw.rect(self.screen, arch_color,
                             pygame.Rect(px + ts - 8, py + 6, 5, ts - 8))
            # Top arch
            pygame.draw.rect(self.screen, arch_color,
                             pygame.Rect(px + 3, py + 3, ts - 6, 5))
            # Swirling energy fill inside the arch
            inner = pygame.Surface((ts - 14, ts - 12), pygame.SRCALPHA)
            inner.fill((0, 180, 255, 80))
            self.screen.blit(inner, (px + 7, py + 7))
            # Energy swirl lines
            import math as _math
            for i in range(3):
                sy = py + 10 + i * 7
                for sx_off in range(1, ts - 15, 2):
                    wave = int(_math.sin(sx_off * 0.5 + i * 2.0) * 2)
                    c_val = 150 + (sx_off * 7 + i * 30) % 105
                    pygame.draw.rect(self.screen, (0, c_val, 255),
                                     pygame.Rect(px + 8 + sx_off, sy + wave, 2, 1))
            # Bright glow around the portal
            glow = pygame.Surface((ts, ts), pygame.SRCALPHA)
            pygame.draw.rect(glow, (0, 180, 255, 40),
                             pygame.Rect(0, 0, ts, ts))
            self.screen.blit(glow, (px, py))
            # Pillar highlights
            pygame.draw.rect(self.screen, (140, 140, 160),
                             pygame.Rect(px + 3, py + 3, ts - 6, 5), 1)

        elif tile_id == TILE_PUDDLE:
            # Dark water puddle on dungeon floor
            pygame.draw.rect(self.screen, palette["floor_base"], rect)
            # Puddle shape — irregular oval
            puddle_w = ts - 8 + (seed % 5)
            puddle_h = ts - 14 + (seed % 4)
            puddle_rect = pygame.Rect(cx - puddle_w // 2, cy - puddle_h // 2,
                                      puddle_w, puddle_h)
            # Dark blue water
            pygame.draw.ellipse(self.screen, (20, 35, 60), puddle_rect)
            pygame.draw.ellipse(self.screen, (30, 50, 80), puddle_rect, 1)
            # Animated shimmer highlight
            import math as _mp
            t = pygame.time.get_ticks()
            shimmer = 0.5 + 0.5 * _mp.sin(t * 0.003 + seed)
            sh_x = cx - 3 + int(shimmer * 4)
            sh_y = cy - 2
            sh_alpha = int(40 + 40 * shimmer)
            sh_surf = pygame.Surface((6, 2), pygame.SRCALPHA)
            sh_surf.fill((120, 160, 220, sh_alpha))
            self.screen.blit(sh_surf, (sh_x, sh_y))

        elif tile_id == TILE_MOSS:
            # Mossy stone floor
            pygame.draw.rect(self.screen, palette["floor_base"], rect)
            # Floor texture underneath
            detail_col = palette["floor_detail"]
            if seed % 3 == 0:
                dx = (seed * 7) % (ts - 6) + 3
                dy = (seed * 13) % (ts - 6) + 3
                pygame.draw.rect(self.screen, detail_col,
                                 pygame.Rect(px + dx, py + dy, 2, 1))
            # Moss patches — several small green clumps
            moss_colors = [(30, 70, 25), (20, 55, 18), (40, 80, 30),
                           (25, 60, 20)]
            for i in range(4 + seed % 3):
                s = seed * 7 + i * 37
                mx = (s * 11) % (ts - 6) + 3
                my = (s * 17) % (ts - 6) + 3
                mw = 2 + s % 3
                mh = 1 + s % 2
                mc = moss_colors[i % len(moss_colors)]
                pygame.draw.rect(self.screen, mc,
                                 pygame.Rect(px + mx, py + my, mw, mh))
            # Occasional tiny tendril
            if seed % 4 == 0:
                tx = px + (seed * 3) % (ts - 4) + 2
                ty = py + (seed * 9) % (ts - 8) + 4
                pygame.draw.line(self.screen, (35, 75, 28),
                                 (tx, ty), (tx + 2, ty - 3), 1)

        elif tile_id == TILE_WALL_TORCH:
            # Wall tile with mounted torch — animated flame
            # Draw the wall base first (same as DWALL)
            pygame.draw.rect(self.screen, palette["wall_base"], rect)
            bricks = palette["wall_bricks"]
            mortar = palette["wall_mortar"]
            for iy in range(0, ts, 8):
                offset = 5 if (iy // 8) % 2 else 0
                for ix in range(offset, ts, 11):
                    s = (wc * 7 + wr * 13 + ix + iy) % 5
                    if s < 2:
                        bc = bricks[0]
                    elif s < 4:
                        bc = bricks[1]
                    else:
                        bc = bricks[2]
                    brick = pygame.Rect(px + ix, py + iy, 9, 6)
                    pygame.draw.rect(self.screen, bc, brick)
                    pygame.draw.rect(self.screen, mortar, brick, 1)
            # Torch bracket — small brown mounting
            bracket_x = cx - 2
            bracket_y = cy + 2
            pygame.draw.rect(self.screen, (100, 70, 30),
                             pygame.Rect(bracket_x, bracket_y, 4, 6))
            pygame.draw.rect(self.screen, (70, 45, 15),
                             pygame.Rect(bracket_x, bracket_y, 4, 6), 1)
            # Animated flame
            import math as _mt
            t = pygame.time.get_ticks()
            flicker = _mt.sin(t * 0.012 + wc * 3.7 + wr * 5.3)
            flicker2 = _mt.sin(t * 0.019 + wc * 2.1 + wr * 7.1)
            # Outer flame (orange-red, larger)
            flame_h = 8 + int(flicker * 2)
            flame_w = 5 + int(flicker2)
            flame_top = bracket_y - flame_h
            flame_pts = [
                (cx, flame_top),                        # tip
                (cx - flame_w // 2, bracket_y),         # bottom-left
                (cx + flame_w // 2, bracket_y),         # bottom-right
            ]
            pygame.draw.polygon(self.screen, (220, 120, 30), flame_pts)
            # Inner flame (bright yellow, smaller)
            inner_h = flame_h - 3
            inner_w = max(1, flame_w - 3)
            inner_pts = [
                (cx + int(flicker), flame_top + 2),
                (cx - inner_w // 2, bracket_y - 1),
                (cx + inner_w // 2, bracket_y - 1),
            ]
            pygame.draw.polygon(self.screen, (255, 230, 80), inner_pts)
            # Tiny bright core
            pygame.draw.circle(self.screen, (255, 255, 200),
                               (cx, bracket_y - 2), 2)

        else:
            # Fallback: black
            pygame.draw.rect(self.screen, BLACK, rect)

    # ── unique tile sprite ─────────────────────────────────

    def _get_unique_tile_sprite(self, filename, size=32):
        """Load and cache a unique tile sprite from assets."""
        key = (filename, size)
        if key not in self._unique_tile_sprites:
            path = os.path.join(self._assets_dir, filename)
            if os.path.exists(path):
                raw = pygame.image.load(path).convert_alpha()
                self._unique_tile_sprites[key] = pygame.transform.scale(
                    raw, (size, size))
            else:
                self._unique_tile_sprites[key] = None
        return self._unique_tile_sprites[key]

    # ── dungeon monster sprite ─────────────────────────────

    def _get_monster_sprite(self, monster):
        """Get the tile sprite for a monster, falling back to tile sheet."""
        # Try per-monster tile from assets
        if monster.tile:
            sprite = self._monster_tiles.get(monster.tile)
            if sprite:
                return sprite
        # Fallback to tile sheet skeleton
        return self._tile_sprites.get((1, 9))

    def _u3_draw_dungeon_monster(self, monster, cx, cy):
        """Draw a monster in the dungeon using its unique tile sprite."""
        sprite = self._get_monster_sprite(monster)
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: blocky monster with monster-specific color
            mc = monster.color
            W = (255, 255, 255)
            body = pygame.Rect(cx - 8, cy - 6, 16, 14)
            pygame.draw.rect(self.screen, mc, body)
            pygame.draw.rect(self.screen, mc,
                             pygame.Rect(cx - 5, cy - 12, 10, 7))
            pygame.draw.rect(self.screen, W,
                             pygame.Rect(cx - 4, cy - 10, 3, 3))
            pygame.draw.rect(self.screen, W,
                             pygame.Rect(cx + 1, cy - 10, 3, 3))
            pygame.draw.rect(self.screen, (255, 0, 0),
                             pygame.Rect(cx - 3, cy - 9, 1, 1))
            pygame.draw.rect(self.screen, (255, 0, 0),
                             pygame.Rect(cx + 2, cy - 9, 1, 1))

    # ── dungeon fog of war ─────────────────────────────────

    def _u3_dungeon_fog(self, party_sc, party_sr, cols, rows, ts,
                         visible_tiles=None, off_c=0, off_r=0):
        """Draw fog of war over the U3 dungeon map area.

        If *visible_tiles* is provided (a set of (col, row) world coords),
        tiles in the set are fully visible, tiles one step beyond get a soft
        fade, and everything else is blacked out.  Falls back to a simple
        radius-1 Euclidean fog when no set is supplied.
        """
        import math

        fog = pygame.Surface((self._U3_DG_MAP_W, self._U3_DG_MAP_H), pygame.SRCALPHA)

        if visible_tiles is not None:
            for sr in range(rows):
                for sc in range(cols):
                    wc = sc + off_c
                    wr = sr + off_r
                    if (wc, wr) in visible_tiles:
                        # Fully visible — no fog
                        continue
                    # Check if any visible neighbour exists (edge fade)
                    edge = False
                    for dc in (-1, 0, 1):
                        for dr in (-1, 0, 1):
                            if (wc + dc, wr + dr) in visible_tiles:
                                edge = True
                                break
                        if edge:
                            break
                    alpha = 160 if edge else 255
                    rect = pygame.Rect(sc * ts, sr * ts, ts, ts)
                    fog.fill((0, 0, 0, alpha), rect)
        else:
            # Fallback: simple radius-1 fog
            fade_start = 1
            fade_end = 2.5
            for sr in range(rows):
                for sc in range(cols):
                    dx = sc - party_sc
                    dy = sr - party_sr
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist <= fade_start:
                        continue
                    elif dist >= fade_end:
                        alpha = 255
                    else:
                        t = (dist - fade_start) / (fade_end - fade_start)
                        alpha = int(255 * t)
                    rect = pygame.Rect(sc * ts, sr * ts, ts, ts)
                    fog.fill((0, 0, 0, alpha), rect)

        self.screen.blit(fog, (0, 0))

    def _u3_infravision_tint(self, cols, rows, ts, visible_tiles,
                              off_c, off_r, party_sc, party_sr):
        """Apply a red/black infrared tint to the map area.

        Converts pixels to grayscale, then maps luminance to a red channel
        only — bright areas become bright red, dark areas stay black.
        Gives the look of infrared goggles.
        """
        map_w = cols * ts
        map_h = rows * ts

        try:
            import pygame.surfarray as surfarray
            import numpy as np

            # Grab the current screen pixels for the map area
            map_rect = pygame.Rect(0, 0, map_w, map_h)
            map_surf = self.screen.subsurface(map_rect).copy()
            arr = surfarray.pixels3d(map_surf)  # shape (w, h, 3)

            # Compute luminance (grayscale) using standard weights
            # arr is (width, height, 3) with R=0, G=1, B=2
            lum = (arr[:, :, 0].astype(np.float32) * 0.299
                   + arr[:, :, 1].astype(np.float32) * 0.587
                   + arr[:, :, 2].astype(np.float32) * 0.114)

            # Map luminance to red channel; green/blue get a tiny fraction
            # for a warm infrared feel rather than pure red monochrome
            arr[:, :, 0] = np.clip(lum * 1.1, 0, 255).astype(np.uint8)
            arr[:, :, 1] = np.clip(lum * 0.08, 0, 255).astype(np.uint8)
            arr[:, :, 2] = np.clip(lum * 0.04, 0, 255).astype(np.uint8)

            del arr  # release surfarray lock
            self.screen.blit(map_surf, (0, 0))

        except (ImportError, Exception):
            # Fallback: simple red overlay with MULTIPLY-like blend
            # Remove green/blue with a dark overlay, then tint red
            tint = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
            tint.fill((0, 0, 0, 180))
            self.screen.blit(tint, (0, 0))
            red_wash = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
            red_wash.fill((180, 0, 0, 80))
            self.screen.blit(red_wash, (0, 0))

    def _u3_galadriels_tint(self, cols, rows, ts, visible_tiles,
                              off_c, off_r, party_sc, party_sr,
                              subtle=False):
        """Apply a soft blue tint to the map area for Galadriel's Light.

        When *subtle* is True (daytime overworld), only a very light wash
        is applied.  Otherwise, the effect shifts the colour balance toward
        blue/white starlight.
        """
        map_w = cols * ts
        map_h = rows * ts

        try:
            import pygame.surfarray as surfarray
            import numpy as np

            map_rect = pygame.Rect(0, 0, map_w, map_h)
            map_surf = self.screen.subsurface(map_rect).copy()
            arr = surfarray.pixels3d(map_surf)  # shape (w, h, 3)

            if subtle:
                # Daytime: very light blue wash — barely noticeable
                arr[:, :, 0] = np.clip(arr[:, :, 0].astype(np.int16) - 8,
                                        0, 255).astype(np.uint8)
                arr[:, :, 1] = np.clip(arr[:, :, 1].astype(np.int16) - 4,
                                        0, 255).astype(np.uint8)
                arr[:, :, 2] = np.clip(arr[:, :, 2].astype(np.int16) + 18,
                                        0, 255).astype(np.uint8)
            else:
                # Full starlight: shift toward cool blue/white
                lum = (arr[:, :, 0].astype(np.float32) * 0.299
                       + arr[:, :, 1].astype(np.float32) * 0.587
                       + arr[:, :, 2].astype(np.float32) * 0.114)

                # Keep some of the original colour, blend with blue-shifted lum
                arr[:, :, 0] = np.clip(
                    arr[:, :, 0] * 0.55 + lum * 0.25, 0, 255
                ).astype(np.uint8)
                arr[:, :, 1] = np.clip(
                    arr[:, :, 1] * 0.55 + lum * 0.35, 0, 255
                ).astype(np.uint8)
                arr[:, :, 2] = np.clip(
                    arr[:, :, 2] * 0.45 + lum * 0.65, 0, 255
                ).astype(np.uint8)

            del arr
            self.screen.blit(map_surf, (0, 0))

        except (ImportError, Exception):
            # Fallback: simple blue overlay
            tint = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
            if subtle:
                tint.fill((40, 60, 140, 25))
            else:
                tint.fill((30, 50, 120, 70))
            self.screen.blit(tint, (0, 0))

    # ── dungeon right panel ────────────────────────────────

    def _u3_dungeon_right_panel(self, party, dungeon_data, x, y, w):
        """Draw the right-hand stat panel for the dungeon."""
        block_h = 130
        for i, member in enumerate(party.members):
            by = y + i * block_h
            self._u3_panel(x, by, w, block_h)
            tx = x + 8
            ty = by + 6

            cls_short = member.char_class[:3].upper()
            alive_color = (255, 170, 85) if member.is_alive() else (200, 60, 60)
            self._u3_text(f"{i+1}", tx, ty, (68, 68, 255), self.font)
            self._u3_text(member.name, tx + 20, ty, alive_color, self.font)
            self._u3_text(cls_short, tx + 180, ty, (68, 68, 255))

            ty += 20
            self._u3_text(
                f"HP:{member.hp:d}/{member.max_hp:d}  AC:{member.get_ac():d}",
                tx, ty)

            ty += 16
            self._u3_text(
                f"S:{member.strength:d} D:{member.dexterity:d} I:{member.intelligence:d} W:{member.wisdom:d}",
                tx, ty, (136, 136, 136))

            ty += 16
            self._u3_text(
                f"LVL:{member.level:d}  EXP:{member.exp:d}/{member.xp_for_next_level:d}",
                tx, ty, (136, 136, 136))

            ty += 16
            self._u3_text(f"WPN: {member.weapon}", tx, ty, (136, 136, 136))

        # Bottom info block
        info_y = y + 4 * block_h
        info_h = SCREEN_HEIGHT - info_y - 24
        self._u3_panel(x, info_y, w, info_h)
        tx = x + 8
        ty = info_y + 6

        self._u3_text(f"GOLD: {party.gold:d}", tx, ty, (255, 255, 0))

        ty += 18
        self._u3_text(f"DUNGEON: {dungeon_data.name}", tx, ty, (200, 60, 60))

        ty += 18
        tile_name = dungeon_data.tile_map.get_tile_name(party.col, party.row)
        self._u3_text(f"TILE: {tile_name}", tx, ty, (68, 68, 255))

        ty += 18
        self._u3_text(f"POS: ({party.col},{party.row})", tx, ty, (136, 136, 136))

        ty += 18
        chests = len(dungeon_data.opened_chests)
        self._u3_text(f"CHESTS: {chests:d}", tx, ty, (255, 170, 85))

    # ========================================================
    # COMBAT ARENA  –  Ultima III retro style
    # ========================================================

    # ── Retro colour palette (C64 / Apple II inspired) ──
    _U3_BLACK  = (0, 0, 0)
    _U3_BLUE   = (90, 90, 255)
    _U3_LTBLUE = (180, 180, 255)   # brighter blue for readable text
    _U3_WHITE  = (255, 255, 255)
    _U3_ORANGE = (255, 185, 100)
    _U3_GREEN  = (0, 200, 0)
    _U3_DKGRN  = (0, 130, 0)
    _U3_RED    = (220, 70, 70)
    _U3_GRAY   = (170, 170, 170)
    _U3_BRICK1 = (102, 51, 85)
    _U3_BRICK2 = (68, 34, 68)

    # ── Layout constants ──
    _ARENA_TILE = 32
    _ARENA_COLS = 18
    _ARENA_ROWS = 21
    _MAP_X  = 4                                     # left edge of map panel
    _MAP_Y  = 4
    _MAP_W  = _ARENA_COLS * _ARENA_TILE              # 576
    _MAP_H  = _ARENA_ROWS * _ARENA_TILE              # 672
    _RPANEL_X = _MAP_X + _MAP_W + 8                  # 588
    _RPANEL_W = SCREEN_WIDTH - _RPANEL_X - 4          # 368

    # ── helper: draw a blue-bordered retro panel ──
    def _u3_panel(self, x, y, w, h):
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, self._U3_BLACK, rect)
        pygame.draw.rect(self.screen, self._U3_BLUE, rect, 2)

    # ── helper: render uppercase white text ──
    def _u3_text(self, text, x, y, color=None, font=None):
        f = font or self.font_small
        c = color or self._U3_WHITE
        surf = f.render(text.upper(), True, c)
        self.screen.blit(surf, (x, y))

    def _draw_floating_message(self, message, y=16, max_width=None):
        """Draw a word-wrapped floating message box centred on screen.

        Long messages are split across multiple lines so they stay inside
        the game viewport.
        """
        if not message:
            return
        if max_width is None:
            max_width = SCREEN_WIDTH - 40  # 20px padding each side
        text = message.upper()
        color = (255, 220, 140)
        border_color = (120, 120, 255)
        font = self.font

        # Word-wrap into lines that fit within max_width
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip() if current else word
            tw, _ = font.size(test)
            if tw <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            return

        # Render each line surface
        line_surfs = [font.render(ln, True, color) for ln in lines]
        line_h = line_surfs[0].get_height()
        spacing = 2
        total_h = len(line_surfs) * line_h + (len(line_surfs) - 1) * spacing
        box_w = max(s.get_width() for s in line_surfs) + 20
        box_h = total_h + 10

        box_x = (SCREEN_WIDTH - box_w) // 2
        box_y = y - box_h // 2

        # Background and border
        bg_rect = pygame.Rect(box_x, box_y, box_w, box_h)
        pygame.draw.rect(self.screen, (0, 0, 0), bg_rect)
        pygame.draw.rect(self.screen, border_color, bg_rect, 2)

        # Blit lines centred
        cur_y = box_y + 5
        for surf in line_surfs:
            sx = (SCREEN_WIDTH - surf.get_width()) // 2
            self.screen.blit(surf, (sx, cur_y))
            cur_y += line_h + spacing

    # ── helper: scrollable list for action panels ──

    def _u3_scrollable_list(self, tx, top_y, avail_h, font, items, cursor):
        """Render a scrollable list within a fixed-height region.

        *items* is a list of (label_str, is_selected_bool).
        *cursor* is the currently selected index.
        *avail_h* is the pixel height available for the list area.
        Draws up/down scroll indicators when the list is clipped.
        """
        ROW_H = 24
        ARROW_H = 16  # space reserved for a scroll arrow

        total = len(items)
        if total == 0:
            return

        # How many rows can we actually display?
        max_visible = max(1, avail_h // ROW_H)

        if total <= max_visible:
            # Everything fits — no scrolling needed
            for i, (label, sel) in enumerate(items):
                iy = top_y + i * ROW_H
                prefix = "> " if sel else "  "
                color = self._U3_WHITE if sel else self._U3_LTBLUE
                self._u3_text(prefix + label, tx, iy, color, font)
            return

        # Need scrolling — leave room for indicators
        visible_rows = max(1, (avail_h - ARROW_H * 2) // ROW_H)

        # Compute scroll offset: keep cursor roughly centred
        scroll = cursor - visible_rows // 2
        scroll = max(0, min(scroll, total - visible_rows))

        show_up = scroll > 0
        show_down = scroll + visible_rows < total

        draw_y = top_y

        # Up arrow
        if show_up:
            self._u3_text("    " + chr(0x25B2) + " more", tx, draw_y,
                          self._U3_LTBLUE, self.font_small)
            draw_y += ARROW_H

        # Visible items
        for vi in range(visible_rows):
            idx = scroll + vi
            if idx >= total:
                break
            label, sel = items[idx]
            iy = draw_y + vi * ROW_H
            prefix = "> " if sel else "  "
            color = self._U3_WHITE if sel else self._U3_LTBLUE
            self._u3_text(prefix + label, tx, iy, color, font)

        # Down arrow
        if show_down:
            arrow_y = draw_y + visible_rows * ROW_H
            self._u3_text("    " + chr(0x25BC) + " more", tx, arrow_y,
                          self._U3_LTBLUE, self.font_small)

    # ── helper: draw a procedural lunar phase icon ──

    def _get_moon_surfaces(self, size):
        """Return cached list of 8 pre-rendered moon phase surfaces."""
        if hasattr(self, '_moon_cache') and self._moon_cache_size == size:
            return self._moon_cache

        r = size // 2
        cx, cy = r, r
        moon_color = (220, 220, 200)
        shadow_color = (20, 20, 40)

        # Build a circle mask once (True where inside circle)
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (cx, cy), r)

        phases = []
        for pi in range(8):
            surf = pygame.Surface((size, size), pygame.SRCALPHA)

            if pi == 0:
                # New moon: dark circle with faint outline
                pygame.draw.circle(surf, shadow_color, (cx, cy), r)
                pygame.draw.circle(surf, (60, 60, 80), (cx, cy), r, 1)
            elif pi == 4:
                # Full moon: bright circle
                pygame.draw.circle(surf, moon_color, (cx, cy), r)
            else:
                # Draw bright circle, then shadow ellipse, then clip
                pygame.draw.circle(surf, moon_color, (cx, cy), r)
                if pi in (1, 2, 3):
                    # Waxing: shadow on the left side
                    shadow_w = {1: r * 2, 2: r, 3: r // 2}[pi]
                    shadow_rect = pygame.Rect(cx - r, cy - r, shadow_w, size)
                else:
                    # Waning: shadow on the right side
                    shadow_w = {5: r // 2, 6: r, 7: r * 2}[pi]
                    shadow_rect = pygame.Rect(cx + r - shadow_w, cy - r,
                                              shadow_w, size)
                pygame.draw.ellipse(surf, shadow_color, shadow_rect)
                # Clip to circle: clear pixels outside the mask
                for py_ in range(size):
                    for px_ in range(size):
                        if mask.get_at((px_, py_)).a == 0:
                            surf.set_at((px_, py_), (0, 0, 0, 0))

            phases.append(surf)

        self._moon_cache = phases
        self._moon_cache_size = size
        return phases

    def _draw_moon_phase(self, x, y, size, phase_index):
        """Draw a cached moon phase icon at (x, y)."""
        surfaces = self._get_moon_surfaces(size)
        self.screen.blit(surfaces[phase_index % 8], (x, y))

    # ── helper: draw a sun or moon icon based on time of day ──

    def _draw_sky_icon(self, x, y, size, clock):
        """Draw a sun (day), crescent moon (night), or horizon icon (dawn/dusk)."""
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx, cy = size // 2, size // 2
        r = size // 2 - 1

        if clock.is_day:
            # Bright sun: yellow circle with short rays
            sun_r = r - 3
            pygame.draw.circle(surf, (255, 220, 60), (cx, cy), sun_r)
            # Rays
            for i in range(8):
                angle = i * (math.pi / 4)
                inner = sun_r + 2
                outer = r
                x1 = cx + int(inner * math.cos(angle))
                y1 = cy + int(inner * math.sin(angle))
                x2 = cx + int(outer * math.cos(angle))
                y2 = cy + int(outer * math.sin(angle))
                pygame.draw.line(surf, (255, 200, 40), (x1, y1), (x2, y2), 1)
        elif clock.is_night:
            # Night crescent moon (small, silver)
            pygame.draw.circle(surf, (180, 190, 210), (cx, cy), r - 2)
            # Shadow to make crescent
            pygame.draw.circle(surf, (0, 0, 0, 0), (cx + 4, cy - 2), r - 2)
            shadow = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(shadow, (20, 20, 40, 255),
                               (cx + 4, cy - 2), r - 2)
            surf.blit(shadow, (0, 0))
            # Tiny stars
            for sx, sy in [(3, 3), (size - 4, 5), (5, size - 5)]:
                if 0 <= sx < size and 0 <= sy < size:
                    surf.set_at((sx, sy), (200, 200, 255, 180))
        elif clock.is_dawn:
            # Dawn: horizon line with half-sun rising
            horizon_y = cy + 3
            # Orange-pink gradient glow
            for gy in range(horizon_y, size):
                alpha = int(120 * (1.0 - (gy - horizon_y) / (size - horizon_y)))
                pygame.draw.line(surf, (255, 140, 60, alpha),
                                 (0, gy), (size - 1, gy))
            # Half-sun peeking above horizon
            pygame.draw.circle(surf, (255, 200, 80), (cx, horizon_y), 5)
            # Clip below horizon
            clip = pygame.Surface((size, size - horizon_y), pygame.SRCALPHA)
            clip.fill((0, 0, 0, 0))
            surf.blit(clip, (0, horizon_y), special_flags=pygame.BLEND_RGBA_MIN)
            # Re-draw horizon line
            pygame.draw.line(surf, (255, 160, 80),
                             (1, horizon_y), (size - 2, horizon_y), 1)
        else:
            # Dusk: horizon line with half-sun setting
            horizon_y = cy + 3
            for gy in range(horizon_y, size):
                alpha = int(100 * (1.0 - (gy - horizon_y) / (size - horizon_y)))
                pygame.draw.line(surf, (200, 80, 120, alpha),
                                 (0, gy), (size - 1, gy))
            pygame.draw.circle(surf, (220, 140, 60), (cx, horizon_y), 5)
            clip = pygame.Surface((size, size - horizon_y), pygame.SRCALPHA)
            clip.fill((0, 0, 0, 0))
            surf.blit(clip, (0, horizon_y), special_flags=pygame.BLEND_RGBA_MIN)
            pygame.draw.line(surf, (200, 100, 80),
                             (1, horizon_y), (size - 2, horizon_y), 1)

        self.screen.blit(surf, (x, y))

    # ==============================================================
    #  MAIN ENTRY POINT
    # ==============================================================

    def draw_combat_arena(self, fighter, monster, combat_log, phase,
                          selected_action, defending,
                          player_col, player_row,
                          monster_col, monster_row,
                          is_adjacent, combat_message,
                          fighters=None, fighter_positions=None,
                          active_fighter=None, defending_map=None,
                          projectiles=None,
                          melee_effects=None, hit_effects=None,
                          fireballs=None, fireball_explosions=None,
                          heal_effects=None,
                          shield_effects=None,
                          shield_buffs=None,
                          range_buffs=None,
                          shield_target_col=0,
                          shield_target_row=0,
                          turn_undead_effects=None,
                          charm_effects=None,
                          sleep_effects=None,
                          sleep_buffs=None,
                          teleport_effects=None,
                          invisibility_effects=None,
                          invisibility_buffs=None,
                          animate_dead_effects=None,
                          summon_buffs=None,
                          aoe_fireball_effects=None,
                          aoe_explosions=None,
                          lightning_bolt_effects=None,
                          cure_poison_effects=None,
                          bless_effects=None,
                          bless_buffs=None,
                          curse_effects=None,
                          curse_buffs=None,
                          monster_spell_effects=None,
                          is_warband=False, source_state="dungeon",
                          directing_action=None,
                          menu_actions=None,
                          spell_list=None, spell_cursor=0,
                          selected_spell=None,
                          throw_list=None, throw_cursor=0,
                          selected_throw=None,
                          use_item_list=None, use_item_cursor=0,
                          selected_use_item=None,
                          monsters=None, monster_positions=None,
                          encounter_name=None):
        """
        Draw the Ultima III-style combat screen with all party members.
        """
        self.screen.fill(self._U3_BLACK)

        mx, my = self._MAP_X, self._MAP_Y
        ts = self._ARENA_TILE
        is_outdoor = (source_state == "overworld")

        # ── 1. draw arena tiles ──
        for r in range(self._ARENA_ROWS):
            for c in range(self._ARENA_COLS):
                px = mx + c * ts
                py = my + r * ts
                wall = (c == 0 or c == self._ARENA_COLS - 1
                        or r == 0 or r == self._ARENA_ROWS - 1)
                if is_outdoor:
                    if wall:
                        self._u3_draw_outdoor_edge_tile(px, py, ts, c, r)
                    else:
                        self._u3_draw_outdoor_floor_tile(px, py, ts, c, r)
                else:
                    if wall:
                        self._u3_draw_wall_tile(px, py, ts)
                    else:
                        self._u3_draw_floor_tile(px, py, ts, c, r)

        # ── 2. monster sprites ──
        if monsters and monster_positions:
            for mon in monsters:
                if not mon.is_alive():
                    continue
                mc, mr = monster_positions.get(mon, (0, 0))
                if is_outdoor:
                    self._u3_draw_orc_combat_sprite(mon, mx, my, ts, mc, mr)
                else:
                    self._u3_draw_monster_sprite(mon, mx, my, ts, mc, mr)
                # Draw charmed indicator (pink glow + hearts)
                if getattr(mon, "charmed", False):
                    self._u3_draw_charmed_indicator(mx, my, ts, mc, mr)
                # Draw sleep indicator (Zzz floating above)
                if sleep_buffs and mon in sleep_buffs:
                    self._u3_draw_sleep_indicator(mx, my, ts, mc, mr,
                                                  sleep_buffs[mon])
                # Draw poison indicator on poisoned monsters
                mon_poisoned = (getattr(mon, "poisoned", False)
                                or getattr(mon, "poisoned_mp", False)
                                or getattr(mon, "poisoned_debilitate", False))
                if mon_poisoned:
                    turns = max(getattr(mon, "poison_turns", 0),
                                getattr(mon, "poison_mp_turns", 0),
                                getattr(mon, "poison_debilitate_turns", 0))
                    self._u3_draw_poison_indicator(mx, my, ts, mc, mr, turns)
        elif monster and monster.is_alive():
            # Legacy single-monster fallback
            if is_outdoor:
                self._u3_draw_orc_combat_sprite(monster, mx, my, ts,
                                                monster_col, monster_row)
            else:
                self._u3_draw_monster_sprite(monster, mx, my, ts,
                                             monster_col, monster_row)

        # Draw ALL party members on the arena
        if fighters and fighter_positions:
            for member in fighters:
                if not member.is_alive():
                    continue
                col, row = fighter_positions.get(member, (3, 5))
                is_active = (member is active_fighter)
                # Invisible members are semi-transparent with pulsing alpha
                if invisibility_buffs and member in invisibility_buffs:
                    ticks = pygame.time.get_ticks()
                    invis_alpha = int(40 + 25 * math.sin(ticks * 0.004))
                    self._u3_draw_party_member_sprite(
                        mx, my, ts, col, row, member, is_active,
                        alpha=invis_alpha)
                else:
                    self._u3_draw_party_member_sprite(
                        mx, my, ts, col, row, member, is_active)

            # Draw persistent shield bubbles over buffed fighters
            if shield_buffs:
                for member, buff in shield_buffs.items():
                    if member.is_alive() and member in fighter_positions:
                        sc, sr = fighter_positions[member]
                        self._u3_draw_shield_bubble(mx, my, ts, sc, sr,
                                                    buff["turns_left"])

            # Draw range buff indicators (green speed lines) over buffed fighters
            if range_buffs:
                for member, buff in range_buffs.items():
                    if member.is_alive() and member in fighter_positions:
                        sc, sr = fighter_positions[member]
                        self._u3_draw_range_buff_indicator(
                            mx, my, ts, sc, sr, buff["turns_left"])

            # Draw sleep indicator on sleeping fighters (Zzz)
            if sleep_buffs:
                for member in fighters:
                    if member.is_alive() and member in sleep_buffs and member in fighter_positions:
                        sc, sr = fighter_positions[member]
                        self._u3_draw_sleep_indicator(mx, my, ts, sc, sr,
                                                      sleep_buffs[member])

            # Draw poison indicator on poisoned fighters (green tint)
            for member in fighters:
                if member.is_alive() and getattr(member, "poisoned", False) and member in fighter_positions:
                    sc, sr = fighter_positions[member]
                    self._u3_draw_poison_indicator(mx, my, ts, sc, sr,
                                                   getattr(member, "poison_turns", 0))

            # Draw curse indicator on cursed fighters
            if curse_buffs:
                for member in fighters:
                    if member.is_alive() and member in curse_buffs and member in fighter_positions:
                        sc, sr = fighter_positions[member]
                        self._u3_draw_curse_indicator(mx, my, ts, sc, sr,
                                                      curse_buffs[member].get("turns_left", 0))
        else:
            # Fallback: single player sprite
            self._u3_draw_player_sprite(mx, my, ts, player_col, player_row)

        # ── 2b. projectiles ──
        if projectiles:
            for proj in projectiles:
                if proj.alive:
                    pcx = mx + proj.current_col * ts + ts // 2
                    pcy = my + proj.current_row * ts + ts // 2
                    # Draw projectile symbol as colored shape
                    color = proj.color
                    sym = proj.symbol
                    # Main projectile body — bright dot with trail effect
                    pygame.draw.circle(self.screen, color, (int(pcx), int(pcy)), 4)
                    pygame.draw.circle(self.screen, self._U3_WHITE,
                                       (int(pcx), int(pcy)), 2)
                    # Direction indicator (arrow head)
                    if sym == ">":
                        pts = [(int(pcx) + 6, int(pcy)),
                               (int(pcx) + 1, int(pcy) - 4),
                               (int(pcx) + 1, int(pcy) + 4)]
                        pygame.draw.polygon(self.screen, color, pts)
                    elif sym == "<":
                        pts = [(int(pcx) - 6, int(pcy)),
                               (int(pcx) - 1, int(pcy) - 4),
                               (int(pcx) - 1, int(pcy) + 4)]
                        pygame.draw.polygon(self.screen, color, pts)
                    elif sym == "v":
                        pts = [(int(pcx), int(pcy) + 6),
                               (int(pcx) - 4, int(pcy) + 1),
                               (int(pcx) + 4, int(pcy) + 1)]
                        pygame.draw.polygon(self.screen, color, pts)
                    elif sym == "^":
                        pts = [(int(pcx), int(pcy) - 6),
                               (int(pcx) - 4, int(pcy) - 1),
                               (int(pcx) + 4, int(pcy) - 1)]
                        pygame.draw.polygon(self.screen, color, pts)
                    # Trail - small fading dot behind projectile
                    trail_x = pcx - (proj.end_col - proj.start_col) * 0.3 * ts
                    trail_y = pcy - (proj.end_row - proj.start_row) * 0.3 * ts
                    trail_col = (color[0] // 3, color[1] // 3, color[2] // 3)
                    pygame.draw.circle(self.screen, trail_col,
                                       (int(trail_x), int(trail_y)), 2)

        # ── 2c. melee slash effects ──
        if melee_effects:
            for fx in melee_effects:
                if fx.alive:
                    self._u3_draw_melee_effect(mx, my, ts, fx)

        # ── 2d. hit flash effects ──
        if hit_effects:
            from src.states.combat import _PrecisionStrikeEffect
            for fx in hit_effects:
                if fx.alive:
                    if isinstance(fx, _PrecisionStrikeEffect):
                        self._u3_draw_precision_strike(mx, my, ts, fx)
                    else:
                        self._u3_draw_hit_effect(mx, my, ts, fx)

        # ── 2e. fireball projectiles ──
        if fireballs:
            for fb in fireballs:
                if fb.alive:
                    self._u3_draw_fireball(mx, my, ts, fb)

        # ── 2f. fireball explosions ──
        if fireball_explosions:
            for fx in fireball_explosions:
                if fx.alive:
                    self._u3_draw_fireball_explosion(mx, my, ts, fx)

        # ── 2g. heal effects ──
        if heal_effects:
            for fx in heal_effects:
                if fx.alive:
                    self._u3_draw_heal_effect(mx, my, ts, fx)

        # ── 2h. shield effects ──
        if shield_effects:
            for fx in shield_effects:
                if fx.alive:
                    self._u3_draw_shield_effect(mx, my, ts, fx)

        # ── 2i. shield target selection box ──
        from src.states.combat import PHASE_SHIELD_TARGET
        if phase == PHASE_SHIELD_TARGET:
            self._u3_draw_target_cursor(mx, my, ts,
                                        shield_target_col, shield_target_row)

        # ── 2j. turn undead effects ──
        if turn_undead_effects:
            for fx in turn_undead_effects:
                if fx.alive:
                    self._u3_draw_turn_undead_effect(mx, my, ts, fx)

        # ── 2k. charm effects ──
        if charm_effects:
            for fx in charm_effects:
                if fx.alive:
                    self._u3_draw_charm_effect(mx, my, ts, fx)

        # ── 2l. sleep effects ──
        if sleep_effects:
            for fx in sleep_effects:
                if fx.alive:
                    self._u3_draw_sleep_effect(mx, my, ts, fx)

        # ── 2m. teleport effects ──
        if teleport_effects:
            for fx in teleport_effects:
                if fx.alive:
                    self._u3_draw_teleport_effect(mx, my, ts, fx)

        # ── 2n. invisibility effects ──
        if invisibility_effects:
            for fx in invisibility_effects:
                if fx.alive:
                    self._u3_draw_invisibility_effect(mx, my, ts, fx)

        # ── 2o. animate dead effects ──
        if animate_dead_effects:
            for fx in animate_dead_effects:
                if fx.alive:
                    self._u3_draw_animate_dead_effect(mx, my, ts, fx)

        # ── 2p. summoned skeleton indicators ──
        if summon_buffs and monsters and monster_positions:
            for mon, turns_left in summon_buffs.items():
                if mon.is_alive() and mon in monster_positions:
                    sc, sr = monster_positions[mon]
                    self._u3_draw_summon_indicator(mx, my, ts, sc, sr,
                                                   turns_left)

        # ── 2q. AoE fireball projectiles ──
        if aoe_fireball_effects:
            for fb in aoe_fireball_effects:
                if fb.alive:
                    self._u3_draw_aoe_fireball(mx, my, ts, fb)

        # ── 2r. AoE explosions ──
        if aoe_explosions:
            for fx in aoe_explosions:
                if fx.alive:
                    self._u3_draw_aoe_explosion(mx, my, ts, fx)

        # ── 2s. lightning bolt effects ──
        if lightning_bolt_effects:
            for fx in lightning_bolt_effects:
                if fx.alive:
                    self._u3_draw_lightning_bolt(mx, my, ts, fx)

        # ── 2t. cure poison effects ──
        if cure_poison_effects:
            for fx in cure_poison_effects:
                if fx.alive:
                    self._u3_draw_cure_poison_effect(mx, my, ts, fx)

        # ── 2u. bless effects ──
        if bless_effects:
            for fx in bless_effects:
                if fx.alive:
                    self._u3_draw_bless_effect(mx, my, ts, fx)

        # ── 2v. curse effects ──
        if curse_effects:
            for fx in curse_effects:
                if fx.alive:
                    self._u3_draw_curse_effect(mx, my, ts, fx)

        # ── 2w. monster spell effects ──
        if monster_spell_effects:
            for fx in monster_spell_effects:
                if fx.alive:
                    self._u3_draw_monster_spell_effect(mx, my, ts, fx)

        # ── 3. arena blue border ──
        pygame.draw.rect(self.screen, self._U3_BLUE,
                         pygame.Rect(mx - 2, my - 2,
                                     self._MAP_W + 4, self._MAP_H + 4), 2)

        # ── 4. right-hand panels (with animated action panel expansion) ──
        rx = self._RPANEL_X
        rw = self._RPANEL_W
        arena_bottom = my + self._MAP_H

        # Determine if we're in a player-interactive phase
        from src.states.combat import (
            PHASE_PLAYER as _PP, PHASE_PLAYER_DIR as _PPD,
            PHASE_SPELL_SELECT as _PSS, PHASE_THROW_SELECT as _PTS,
            PHASE_USE_ITEM as _PUI, PHASE_SHIELD_TARGET as _PST,
        )
        _player_phases = (_PP, _PPD, _PSS, _PTS, _PUI, _PST)
        is_player_phase = phase in _player_phases

        # Animate expand/collapse (smooth ease-out interpolation)
        expand_speed = 5.0  # rate of transition per second
        dt_anim = 1.0 / max(self.screen.get_width(), 30)  # approximate dt
        # Use pygame clock for consistent animation
        dt_anim = pygame.time.get_ticks() * 0.001  # we'll use a fixed step
        if is_player_phase:
            self._action_panel_expand = min(1.0,
                self._action_panel_expand + 0.08)
        else:
            self._action_panel_expand = max(0.0,
                self._action_panel_expand - 0.08)

        # Ease function for smooth animation
        t = self._action_panel_expand
        ease_t = t * t * (3.0 - 2.0 * t)  # smoothstep

        # Party roster panel (shows all 4 members with sprites and bars)
        party_h = 300
        if fighters:
            self._u3_party_combat_panel(fighters, active_fighter,
                                        defending_map or {},
                                        rx, 4, rw, party_h,
                                        shield_buffs=shield_buffs or {},
                                        range_buffs=range_buffs or {},
                                        invisibility_buffs=invisibility_buffs or {},
                                        bless_buffs=bless_buffs or {})
        else:
            self._u3_fighter_panel(fighter, defending, rx, 4, rw, 138,
                                   shield_buffs=shield_buffs or {})
            party_h = 138

        monster_y = 4 + party_h + 4
        alive_monsters = [m for m in (monsters or []) if m.is_alive()] if monsters else ([monster] if monster and monster.is_alive() else [])
        monster_panel_h = max(50, 28 + 68 * len(alive_monsters))
        self._u3_monster_panel_multi(alive_monsters, rx, monster_y, rw, monster_panel_h,
                                     source_state=is_outdoor and "overworld" or "dungeon",
                                     encounter_name=encounter_name,
                                     sleep_buffs=sleep_buffs,
                                     summon_buffs=summon_buffs,
                                     curse_buffs=curse_buffs)

        # Calculate normal (collapsed) and expanded action panel positions
        normal_action_y = monster_y + monster_panel_h + 4
        expanded_action_y = 4  # top of the right panel area
        action_y = int(normal_action_y + (expanded_action_y - normal_action_y) * ease_t)
        action_h = arena_bottom - action_y

        # When expanding, draw action panel OVER the other panels
        # (it will naturally cover them since it's drawn after)
        self._u3_action_panel(phase, selected_action, is_adjacent,
                              rx, action_y, rw, action_h,
                              active_fighter=active_fighter,
                              directing_action=directing_action,
                              menu_actions=menu_actions,
                              spell_list=spell_list,
                              spell_cursor=spell_cursor,
                              selected_spell=selected_spell,
                              throw_list=throw_list,
                              throw_cursor=throw_cursor,
                              selected_throw=selected_throw,
                              use_item_list=use_item_list,
                              use_item_cursor=use_item_cursor,
                              selected_use_item=selected_use_item)

        # ── 5. bottom combat log ──
        bar_y = arena_bottom + 6
        bar_h = SCREEN_HEIGHT - bar_y
        self._u3_panel(0, bar_y, SCREEN_WIDTH, bar_h)

        log_y_start = bar_y + 4
        line_h = 16
        max_lines = (bar_h - 8) // line_h
        if max_lines > 0 and combat_log:
            visible = combat_log[-max_lines:]
            for i, line in enumerate(visible):
                if "CRITICAL" in line:
                    color = (255, 200, 80)
                elif "Hit!" in line:
                    color = self._U3_WHITE
                elif "Miss" in line or "Failed" in line:
                    color = (200, 200, 210)
                elif "damage" in line and "deals" in line:
                    color = (255, 100, 100)
                elif "defeated" in line or "XP" in line or "Escaped" in line:
                    color = (80, 255, 80)
                elif "fallen" in line:
                    color = (255, 100, 100)
                elif "---" in line:
                    color = (255, 200, 80)
                elif "moves closer" in line:
                    color = (255, 200, 80)
                else:
                    color = (210, 210, 255)
                self._u3_text(line, 8, log_y_start + i * line_h, color, self.font)

        # ── 7. floating combat message ──
        if combat_message:
            surf = self.font.render(combat_message.upper(), True,
                                    self._U3_ORANGE)
            rect = surf.get_rect(center=(mx + self._MAP_W // 2,
                                         my + self._MAP_H // 2))
            bg = rect.inflate(20, 10)
            pygame.draw.rect(self.screen, self._U3_BLACK, bg)
            pygame.draw.rect(self.screen, self._U3_BLUE, bg, 2)
            self.screen.blit(surf, rect)

    # ==============================================================
    #  TILE DRAWING  (retro Ultima III look)
    # ==============================================================

    def _u3_draw_wall_tile(self, px, py, ts):
        """Brick-pattern wall like Ultima III dungeons."""
        pygame.draw.rect(self.screen, self._U3_BRICK2,
                         pygame.Rect(px, py, ts, ts))
        for by in range(0, ts, 8):
            off = 5 if (by // 8) % 2 else 0
            for bx in range(off, ts, 12):
                brick = pygame.Rect(px + bx, py + by, 10, 6)
                pygame.draw.rect(self.screen, self._U3_BRICK1, brick)
                pygame.draw.rect(self.screen, self._U3_BRICK2, brick, 1)

    def _u3_draw_floor_tile(self, px, py, ts, col, row):
        """Black floor with scattered green dots / crosses."""
        pygame.draw.rect(self.screen, self._U3_BLACK,
                         pygame.Rect(px, py, ts, ts))
        # Deterministic pseudo-random green crosses
        seed = (col * 31 + row * 17)
        if seed % 5 < 2:
            dx = (seed * 7) % (ts - 8) + 4
            dy = (seed * 13) % (ts - 8) + 4
            x, y = px + dx, py + dy
            c = self._U3_GREEN if seed % 3 else self._U3_DKGRN
            pygame.draw.line(self.screen, c, (x - 2, y), (x + 2, y), 1)
            pygame.draw.line(self.screen, c, (x, y - 2), (x, y + 2), 1)
        if (seed + 3) % 7 < 2:
            dx2 = ((seed + 5) * 11) % (ts - 8) + 4
            dy2 = ((seed + 5) * 3) % (ts - 8) + 4
            x2, y2 = px + dx2, py + dy2
            pygame.draw.rect(self.screen, self._U3_DKGRN,
                             pygame.Rect(x2, y2, 2, 2))

    def _u3_draw_outdoor_floor_tile(self, px, py, ts, col, row):
        """Grass-style floor tile for outdoor combat arenas."""
        # Use grass sprite from tile sheet if available
        sprite = self._tile_sprites.get((0, 1))  # grass tile
        if sprite:
            self.screen.blit(sprite, (px, py))
        else:
            # Fallback: procedural grass
            pygame.draw.rect(self.screen, (15, 60, 15),
                             pygame.Rect(px, py, ts, ts))
            seed = (col * 31 + row * 17)
            if seed % 4 < 2:
                dx = (seed * 7) % (ts - 8) + 4
                dy = (seed * 13) % (ts - 8) + 4
                c = (30, 100, 30) if seed % 3 else (20, 70, 20)
                pygame.draw.line(self.screen, c,
                                 (px + dx, py + dy - 2), (px + dx, py + dy + 2), 1)

    def _u3_draw_outdoor_edge_tile(self, px, py, ts, col, row):
        """Edge tiles for outdoor arena — forest/tree border."""
        # Use forest sprite from tile sheet if available
        sprite = self._tile_sprites.get((0, 3))  # forest tile
        if sprite:
            self.screen.blit(sprite, (px, py))
        else:
            # Fallback: dark green tree edge
            pygame.draw.rect(self.screen, (10, 50, 10),
                             pygame.Rect(px, py, ts, ts))
            cx, cy = px + ts // 2, py + ts // 2
            pygame.draw.circle(self.screen, (20, 80, 20), (cx, cy), 10)
            pygame.draw.circle(self.screen, (15, 60, 15), (cx, cy), 7)

    def _u3_draw_orc_combat_sprite(self, monster, ax, ay, ts, col, row):
        """Draw monster using its unique tile sprite for overworld combat."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2

        sprite = self._get_monster_sprite(monster)
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            mc = monster.color
            body = pygame.Rect(cx - 8, cy - 6, 16, 14)
            pygame.draw.rect(self.screen, mc, body)
            pygame.draw.rect(self.screen, mc,
                             pygame.Rect(cx - 5, cy - 12, 10, 7))
            pygame.draw.rect(self.screen, self._U3_WHITE,
                             pygame.Rect(cx - 4, cy - 10, 3, 3))

        # HP bar below the monster sprite
        hp_ratio = max(0.0, min(1.0, monster.hp / monster.max_hp)) if monster.max_hp > 0 else 0.0
        bar_w = max(sprite.get_width() if sprite else 20, 20)
        bar_h = 3
        bar_x = cx - bar_w // 2
        bar_y = cy + 22

        pygame.draw.rect(self.screen, (40, 40, 40),
                         pygame.Rect(bar_x, bar_y, bar_w, bar_h))
        fill_w = max(0, int(bar_w * hp_ratio))
        if fill_w > 0:
            if hp_ratio > 0.66:
                bar_color = (40, 220, 40)
            elif hp_ratio > 0.33:
                bar_color = (220, 220, 40)
            else:
                bar_color = (220, 40, 40)
            pygame.draw.rect(self.screen, bar_color,
                             pygame.Rect(bar_x, bar_y, fill_w, bar_h))

    # ==============================================================
    #  SPRITE DRAWING  (simple retro pixel-art figures)
    # ==============================================================

    def _u3_draw_player_sprite(self, ax, ay, ts, col, row):
        """White stick-figure knight, Ultima III style."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2
        W = self._U3_WHITE
        BLU = (120, 120, 255)

        # Head
        pygame.draw.circle(self.screen, W, (cx, cy - 9), 4)
        # Body
        pygame.draw.line(self.screen, W, (cx, cy - 5), (cx, cy + 4), 2)
        # Arms
        pygame.draw.line(self.screen, W, (cx - 6, cy - 2), (cx + 6, cy - 2), 2)
        # Legs
        pygame.draw.line(self.screen, W, (cx, cy + 4), (cx - 5, cy + 12), 2)
        pygame.draw.line(self.screen, W, (cx, cy + 4), (cx + 5, cy + 12), 2)
        # Sword (right hand — short line)
        pygame.draw.line(self.screen, BLU, (cx + 6, cy - 8), (cx + 6, cy + 2), 2)
        # Shield (left hand — small rect)
        pygame.draw.rect(self.screen, BLU,
                         pygame.Rect(cx - 10, cy - 5, 4, 7))

    def _u3_draw_monster_sprite(self, monster, ax, ay, ts, col, row):
        """Draw monster using its unique tile sprite for dungeon combat."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2

        sprite = self._get_monster_sprite(monster)
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: blocky monster with arms and legs
            mc = monster.color
            W = self._U3_WHITE
            body = pygame.Rect(cx - 8, cy - 6, 16, 14)
            pygame.draw.rect(self.screen, mc, body)
            pygame.draw.rect(self.screen, mc,
                             pygame.Rect(cx - 5, cy - 12, 10, 7))
            pygame.draw.rect(self.screen, W,
                             pygame.Rect(cx - 4, cy - 10, 3, 3))
            pygame.draw.rect(self.screen, W,
                             pygame.Rect(cx + 1, cy - 10, 3, 3))
            pygame.draw.rect(self.screen, (255, 0, 0),
                             pygame.Rect(cx - 3, cy - 9, 1, 1))
            pygame.draw.rect(self.screen, (255, 0, 0),
                             pygame.Rect(cx + 2, cy - 9, 1, 1))
            pygame.draw.line(self.screen, mc,
                             (cx - 8, cy - 3), (cx - 13, cy + 4), 2)
            pygame.draw.line(self.screen, mc,
                             (cx + 8, cy - 3), (cx + 13, cy + 4), 2)
            pygame.draw.line(self.screen, mc,
                             (cx - 4, cy + 8), (cx - 6, cy + 14), 2)
            pygame.draw.line(self.screen, mc,
                             (cx + 4, cy + 8), (cx + 6, cy + 14), 2)

        # HP bar below the monster sprite
        hp_ratio = max(0.0, min(1.0, monster.hp / monster.max_hp)) if monster.max_hp > 0 else 0.0
        bar_w = max(sprite.get_width() if sprite else 20, 20)
        bar_h = 3
        bar_x = cx - bar_w // 2
        bar_y = cy + 22

        pygame.draw.rect(self.screen, (40, 40, 40),
                         pygame.Rect(bar_x, bar_y, bar_w, bar_h))
        fill_w = max(0, int(bar_w * hp_ratio))
        if fill_w > 0:
            if hp_ratio > 0.66:
                bar_color = (40, 220, 40)
            elif hp_ratio > 0.33:
                bar_color = (220, 220, 40)
            else:
                bar_color = (220, 40, 40)
            pygame.draw.rect(self.screen, bar_color,
                             pygame.Rect(bar_x, bar_y, fill_w, bar_h))

    # ── Per-class colour for party member sprites ──
    _CLASS_COLORS = {
        "fighter":     (255, 255, 255),   # white
        "cleric":      (120, 200, 255),   # light blue
        "wizard":      (200, 120, 255),   # purple
        "thief":       (255, 200, 80),    # gold
        "paladin":     (255, 255, 200),   # pale gold
        "barbarian":   (255, 180, 120),   # tan
        "lark":        (180, 255, 180),   # light green
        "ranger":      (120, 255, 120),   # green
        "druid":       (180, 220, 180),   # sage
        "illusionist": (255, 180, 220),   # pink
        "alchemist":   (200, 200, 120),   # olive
    }

    def _u3_draw_party_member_sprite(self, ax, ay, ts, col, row,
                                      member, is_active, alpha=255):
        """Draw a party member on the combat arena using loaded sprite.
        Active member gets a highlight ring. Falls back to stick figure.
        alpha < 255 renders the sprite semi-transparent (for invisibility)."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2

        color = self._CLASS_COLORS.get(member.char_class.lower(),
                                        self._U3_WHITE)

        # Try to use loaded sprite (custom tile or class default)
        sprite = self._get_member_sprite(member, big=False)
        if sprite:
            # Center the sprite on the tile
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            if alpha < 255:
                ghost = sprite.copy()
                ghost.set_alpha(alpha)
                self.screen.blit(ghost, (sx, sy))
            else:
                self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: stick figure
            BLU = (120, 120, 255)
            if alpha < 255:
                # Draw to a temp surface for transparency
                sw, sh = ts + 20, ts + 30
                temp = pygame.Surface((sw, sh), pygame.SRCALPHA)
                ox, oy = sw // 2, sh // 2  # local center
                pygame.draw.circle(temp, (*color, alpha), (ox, oy - 9), 4)
                pygame.draw.line(temp, (*color, alpha), (ox, oy - 5), (ox, oy + 4), 2)
                pygame.draw.line(temp, (*color, alpha), (ox - 6, oy - 2), (ox + 6, oy - 2), 2)
                pygame.draw.line(temp, (*color, alpha), (ox, oy + 4), (ox - 5, oy + 12), 2)
                pygame.draw.line(temp, (*color, alpha), (ox, oy + 4), (ox + 5, oy + 12), 2)
                pygame.draw.line(temp, (*BLU, alpha), (ox + 6, oy - 8), (ox + 6, oy + 2), 2)
                pygame.draw.rect(temp, (*BLU, alpha),
                                 pygame.Rect(ox - 10, oy - 5, 4, 7))
                self.screen.blit(temp, (cx - sw // 2, cy - sh // 2))
            else:
                pygame.draw.circle(self.screen, color, (cx, cy - 9), 4)
                pygame.draw.line(self.screen, color, (cx, cy - 5), (cx, cy + 4), 2)
                pygame.draw.line(self.screen, color, (cx - 6, cy - 2), (cx + 6, cy - 2), 2)
                pygame.draw.line(self.screen, color, (cx, cy + 4), (cx - 5, cy + 12), 2)
                pygame.draw.line(self.screen, color, (cx, cy + 4), (cx + 5, cy + 12), 2)
                pygame.draw.line(self.screen, BLU, (cx + 6, cy - 8), (cx + 6, cy + 2), 2)
                pygame.draw.rect(self.screen, BLU,
                                 pygame.Rect(cx - 10, cy - 5, 4, 7))

        # Active-turn indicator: orange box around sprite + downward arrow above
        if is_active:
            # Highlight box around the sprite
            hw = max(sprite.get_width() if sprite else 20, 20) // 2 + 3
            hh = max(sprite.get_height() if sprite else 24, 24) // 2 + 3
            highlight_rect = pygame.Rect(cx - hw, cy - hh, hw * 2, hh * 2)
            pygame.draw.rect(self.screen, self._U3_ORANGE, highlight_rect, 2)
            # Downward-pointing arrow above the character
            arrow_y = cy - hh - 6
            arrow_pts = [(cx, arrow_y + 5), (cx - 4, arrow_y - 1), (cx + 4, arrow_y - 1)]
            pygame.draw.polygon(self.screen, self._U3_ORANGE, arrow_pts)

        # HP bar below the sprite
        hp_ratio = max(0.0, min(1.0, member.hp / member.max_hp)) if member.max_hp > 0 else 0.0
        bar_w = max(sprite.get_width() if sprite else 20, 20)
        bar_h = 3
        bar_x = cx - bar_w // 2
        bar_y = cy + 22

        # Background (dark)
        bg_rect = pygame.Rect(bar_x, bar_y, bar_w, bar_h)
        if alpha < 255:
            bg_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
            bg_surf.fill((40, 40, 40, alpha))
            self.screen.blit(bg_surf, (bar_x, bar_y))
        else:
            pygame.draw.rect(self.screen, (40, 40, 40), bg_rect)

        # Filled portion — color based on HP ratio
        fill_w = max(0, int(bar_w * hp_ratio))
        if fill_w > 0:
            if hp_ratio > 0.66:
                bar_color = (40, 220, 40)       # green — top third
            elif hp_ratio > 0.33:
                bar_color = (220, 220, 40)      # yellow — middle third
            else:
                bar_color = (220, 40, 40)        # red — bottom third

            fill_rect = pygame.Rect(bar_x, bar_y, fill_w, bar_h)
            if alpha < 255:
                fill_surf = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
                fill_surf.fill((*bar_color, alpha))
                self.screen.blit(fill_surf, (bar_x, bar_y))
            else:
                pygame.draw.rect(self.screen, bar_color, fill_rect)

    # ==============================================================
    #  COMBAT EFFECTS (slash, hit flash)
    # ==============================================================

    def _u3_draw_melee_effect(self, ax, ay, ts, fx):
        """Draw a melee slash effect — animated arc/sweep at the target tile."""
        import math

        cx = ax + fx.col * ts + ts // 2
        cy = ay + fx.row * ts + ts // 2
        p = fx.progress  # 0 → 1

        color = fx.color
        dcol, drow = fx.direction

        # Fade out alpha by drawing progressively dimmer
        brightness = max(0.0, 1.0 - p * 0.6)
        c = (int(color[0] * brightness),
             int(color[1] * brightness),
             int(color[2] * brightness))

        # Slash sweep: a rotating line that sweeps ~90 degrees
        # Base angle determined by attack direction
        if dcol > 0:
            base_angle = 0
        elif dcol < 0:
            base_angle = math.pi
        elif drow > 0:
            base_angle = math.pi / 2
        else:
            base_angle = -math.pi / 2

        # Sweep from -45 to +45 degrees around the base angle
        sweep_offset = (p - 0.5) * math.pi * 0.8
        angle = base_angle + sweep_offset

        slash_len = int(14 + p * 6)  # grows slightly as it sweeps
        x1 = cx + int(math.cos(angle) * 4)
        y1 = cy + int(math.sin(angle) * 4)
        x2 = cx + int(math.cos(angle) * slash_len)
        y2 = cy + int(math.sin(angle) * slash_len)

        # Main slash line
        pygame.draw.line(self.screen, c, (x1, y1), (x2, y2), 3)

        # Bright tip
        pygame.draw.circle(self.screen, self._U3_WHITE, (x2, y2), 2)

        # Secondary slash line (slightly offset for a wider sweep look)
        angle2 = base_angle + sweep_offset * 0.7
        x3 = cx + int(math.cos(angle2) * slash_len * 0.7)
        y3 = cy + int(math.sin(angle2) * slash_len * 0.7)
        dim_c = (c[0] // 2, c[1] // 2, c[2] // 2)
        pygame.draw.line(self.screen, dim_c, (cx, cy), (x3, y3), 2)

        # Impact sparks at early/mid animation
        if 0.2 < p < 0.7:
            for i in range(3):
                spark_angle = base_angle + (i - 1) * 0.5 + p * 2
                spark_dist = 8 + i * 4
                sx = cx + int(math.cos(spark_angle) * spark_dist)
                sy = cy + int(math.sin(spark_angle) * spark_dist)
                pygame.draw.circle(self.screen, self._U3_WHITE, (sx, sy), 1)

    def _u3_draw_hit_effect(self, ax, ay, ts, fx):
        """Draw a hit flash — white flash then red, with shake and damage number."""
        cx = ax + fx.col * ts + ts // 2
        cy = ay + fx.row * ts + ts // 2
        p = fx.progress  # 0 → 1

        # Phase 1 (0–0.4): bright white flash expanding outward
        # Phase 2 (0.4–1.0): red flash fading out + damage number floating up
        if p < 0.4:
            # White flash — expanding ring
            sub_p = p / 0.4
            radius = int(6 + sub_p * 12)
            alpha_f = 1.0 - sub_p * 0.5
            c = (int(255 * alpha_f), int(255 * alpha_f), int(255 * alpha_f))
            pygame.draw.circle(self.screen, c, (cx, cy), radius, 2)
            # Central flash
            pygame.draw.circle(self.screen, self._U3_WHITE, (cx, cy),
                               int(4 + sub_p * 4))
        else:
            # Red flash fading out
            sub_p = (p - 0.4) / 0.6
            alpha_f = 1.0 - sub_p
            r_val = int(255 * alpha_f)
            if r_val > 0:
                c = (r_val, int(60 * alpha_f), int(60 * alpha_f))
                radius = int(10 + sub_p * 4)
                pygame.draw.circle(self.screen, c, (cx, cy), radius, 2)

        # Damage number floating upward
        if fx.damage > 0 and p > 0.15:
            float_y = cy - 14 - int(p * 20)
            dmg_text = str(fx.damage)
            # White text with dark outline for readability
            surf = self.font_small.render(dmg_text, True, self._U3_WHITE)
            outline = self.font_small.render(dmg_text, True, self._U3_BLACK)
            rx = cx - surf.get_width() // 2
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                self.screen.blit(outline, (rx + ox, float_y + oy))
            self.screen.blit(surf, (rx, float_y))

    def _u3_draw_precision_strike(self, ax, ay, ts, fx):
        """Draw the Thief precision strike effect — purple expanding rings
        with bright sparkle bursts, distinct from normal hit flashes."""
        cx = ax + fx.col * ts + ts // 2
        cy = ay + fx.row * ts + ts // 2
        p = fx.progress  # 0 → 1

        # Phase 1 (0–0.3): bright purple-white flash
        # Phase 2 (0.3–0.7): expanding double rings with sparkles
        # Phase 3 (0.7–1.0): "PRECISION STRIKE!" text floats up, fades

        if p < 0.3:
            sub_p = p / 0.3
            radius = int(4 + sub_p * 10)
            alpha_f = 1.0 - sub_p * 0.3
            c = (int(200 * alpha_f), int(140 * alpha_f), int(255 * alpha_f))
            pygame.draw.circle(self.screen, c, (cx, cy), radius)
            # White core
            pygame.draw.circle(self.screen, (255, 255, 255),
                               (cx, cy), int(3 + sub_p * 4))
        elif p < 0.7:
            sub_p = (p - 0.3) / 0.4
            alpha_f = 1.0 - sub_p
            # Outer expanding ring
            r1 = int(12 + sub_p * 16)
            c1 = (int(180 * alpha_f), int(80 * alpha_f), int(255 * alpha_f))
            pygame.draw.circle(self.screen, c1, (cx, cy), r1, 2)
            # Inner ring
            r2 = int(6 + sub_p * 10)
            c2 = (int(255 * alpha_f), int(200 * alpha_f), int(255 * alpha_f))
            pygame.draw.circle(self.screen, c2, (cx, cy), r2, 1)
            # Sparkle crosses at cardinal points
            for angle_i in range(4):
                import math as _m
                a = angle_i * 1.5708 + sub_p * 2.0
                sx = cx + int(_m.cos(a) * r1)
                sy = cy + int(_m.sin(a) * r1)
                spark_sz = int(3 * alpha_f)
                if spark_sz > 0:
                    pygame.draw.line(self.screen, (255, 220, 255),
                                     (sx - spark_sz, sy), (sx + spark_sz, sy), 1)
                    pygame.draw.line(self.screen, (255, 220, 255),
                                     (sx, sy - spark_sz), (sx, sy + spark_sz), 1)

        # Floating "PRECISION STRIKE!" label
        if p > 0.2:
            label_p = min(1.0, (p - 0.2) / 0.8)
            float_y = cy - 20 - int(label_p * 16)
            alpha_f = 1.0 - max(0.0, (label_p - 0.6) / 0.4)
            r_val = int(220 * alpha_f)
            g_val = int(180 * alpha_f)
            b_val = int(255 * alpha_f)
            if r_val > 0:
                text = "PRECISION STRIKE!"
                surf = self.font_small.render(text, True, (r_val, g_val, b_val))
                outline = self.font_small.render(text, True, (0, 0, 0))
                rx = cx - surf.get_width() // 2
                for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    self.screen.blit(outline, (rx + ox, float_y + oy))
                self.screen.blit(surf, (rx, float_y))

    def _u3_draw_fireball(self, ax, ay, ts, fb):
        """Draw a fireball projectile — orange/red glowing ball with trail."""
        cx = int(ax + fb.current_col * ts + ts // 2)
        cy = int(ay + fb.current_row * ts + ts // 2)

        # Pulsating radius
        pulse = 1.0 + 0.3 * math.sin(fb.progress * 20)
        radius = int(fb.radius * pulse)

        # Core — bright yellow-white
        pygame.draw.circle(self.screen, (255, 255, 200), (cx, cy), max(2, radius // 2))
        # Inner glow — orange
        pygame.draw.circle(self.screen, (255, 160, 30), (cx, cy), radius)
        # Outer glow — red/orange, slightly transparent look via thinner ring
        pygame.draw.circle(self.screen, (255, 80, 20), (cx, cy), radius + 3, 2)

        # Trail particles — fading orange dots behind
        dx = fb.end_col - fb.start_col
        dy = fb.end_row - fb.start_row
        for i in range(3):
            t_offset = (i + 1) * 0.08
            trail_prog = max(0, fb.progress - t_offset)
            tx = int(ax + (fb.start_col + dx * trail_prog) * ts + ts // 2)
            ty = int(ay + (fb.start_row + dy * trail_prog) * ts + ts // 2)
            fade = max(0, 200 - i * 60)
            tr = max(1, radius - i * 2)
            pygame.draw.circle(self.screen, (fade, fade // 3, 0), (tx, ty), tr)

    def _u3_draw_fireball_explosion(self, ax, ay, ts, fx):
        """Draw fireball explosion — expanding ring of fire."""
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1

        # Expanding rings of fire
        max_radius = int(ts * 1.5)

        if p < 0.5:
            # Phase 1: bright expanding fireball
            sub_p = p / 0.5
            radius = int(6 + sub_p * max_radius)
            # Bright yellow-orange core
            core_r = max(1, int(radius * 0.5))
            pygame.draw.circle(self.screen, (255, 255, 100), (cx, cy), core_r)
            # Orange ring
            pygame.draw.circle(self.screen, (255, 140, 20), (cx, cy), radius, 3)
            # Red outer ring
            pygame.draw.circle(self.screen, (255, 50, 10), (cx, cy),
                               int(radius * 1.2), 2)
        else:
            # Phase 2: fading out
            sub_p = (p - 0.5) / 0.5
            alpha_f = 1.0 - sub_p
            radius = int(max_radius * (0.8 + sub_p * 0.4))
            r_val = int(255 * alpha_f)
            g_val = int(80 * alpha_f)
            if r_val > 0:
                pygame.draw.circle(self.screen, (r_val, g_val, 0), (cx, cy),
                                   radius, 2)
            # Smoke-like gray ring
            gray = int(100 * alpha_f)
            if gray > 0:
                pygame.draw.circle(self.screen, (gray, gray, gray), (cx, cy),
                                   int(radius * 1.3), 1)

    def _u3_draw_aoe_fireball(self, ax, ay, ts, fb):
        """Draw an AoE fireball projectile — larger, angrier fireball with trail."""
        cx = int(ax + fb.current_col * ts + ts // 2)
        cy = int(ay + fb.current_row * ts + ts // 2)

        # Bigger, more aggressive pulsation
        pulse = 1.0 + 0.4 * math.sin(fb.progress * 24)
        radius = int(fb.radius * pulse)

        # Core — bright white-yellow
        pygame.draw.circle(self.screen, (255, 255, 220), (cx, cy), max(3, radius // 2))
        # Inner glow — deep orange
        pygame.draw.circle(self.screen, (255, 140, 20), (cx, cy), radius)
        # Outer glow — angry red
        pygame.draw.circle(self.screen, (255, 40, 10), (cx, cy), radius + 4, 3)
        # Extra outer ring — dark red shimmer
        pygame.draw.circle(self.screen, (180, 20, 0), (cx, cy), radius + 7, 2)

        # Trail particles — more and brighter
        dx = fb.end_col - fb.start_col
        dy = fb.end_row - fb.start_row
        for i in range(5):
            t_offset = (i + 1) * 0.06
            trail_prog = max(0, fb.progress - t_offset)
            tx = int(ax + (fb.start_col + dx * trail_prog) * ts + ts // 2)
            ty = int(ay + (fb.start_row + dy * trail_prog) * ts + ts // 2)
            fade = max(0, 240 - i * 45)
            tr = max(1, radius - i * 2)
            pygame.draw.circle(self.screen, (fade, fade // 4, 0), (tx, ty), tr)

    def _u3_draw_aoe_explosion(self, ax, ay, ts, fx):
        """Draw a massive AoE explosion — expanding fire covering the blast radius.

        Three phases:
        1. (0.0-0.3) Flash and rapid expansion to full radius
        2. (0.3-0.7) Roaring inferno at full size with flickering
        3. (0.7-1.0) Fade out with smoke
        """
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1

        # Maximum visual radius = blast radius * tile size
        max_radius = int(fx.radius * ts)
        ticks = pygame.time.get_ticks()

        if p < 0.3:
            # Phase 1: Flash and rapid expansion
            sub_p = p / 0.3
            radius = int(8 + sub_p * max_radius)

            # Bright white-yellow flash at the start
            flash_alpha = max(0, 1.0 - sub_p * 2)
            if flash_alpha > 0:
                flash_r = int(radius * 0.6)
                pygame.draw.circle(self.screen,
                                   (255, 255, int(200 * flash_alpha)),
                                   (cx, cy), flash_r)

            # Expanding orange-red fireball
            core_r = max(2, int(radius * 0.7))
            pygame.draw.circle(self.screen, (255, 200, 50), (cx, cy), core_r)
            pygame.draw.circle(self.screen, (255, 120, 20), (cx, cy), radius, 4)
            pygame.draw.circle(self.screen, (220, 40, 10), (cx, cy),
                               int(radius * 1.1), 3)

        elif p < 0.7:
            # Phase 2: Roaring inferno — full size with flickering
            sub_p = (p - 0.3) / 0.4
            radius = max_radius

            # Flickering effect using sin waves at different frequencies
            flicker1 = 0.8 + 0.2 * math.sin(ticks * 0.015)
            flicker2 = 0.85 + 0.15 * math.sin(ticks * 0.023 + 1.5)

            # Inner hot zone — bright yellow-orange
            inner_r = int(radius * 0.5 * flicker1)
            pygame.draw.circle(self.screen, (255, 220, 80), (cx, cy), inner_r)

            # Main fire — orange
            mid_r = int(radius * 0.75 * flicker2)
            pygame.draw.circle(self.screen, (255, 140, 30), (cx, cy), mid_r)

            # Outer fire ring — red
            pygame.draw.circle(self.screen, (230, 60, 10), (cx, cy),
                               int(radius * flicker1), 3)

            # Scattered embers/sparks around the perimeter
            for i in range(8):
                angle = (ticks * 0.003 + i * 0.785)  # 8 evenly spaced
                spark_dist = radius * (0.7 + 0.3 * math.sin(ticks * 0.01 + i))
                sx = cx + int(math.cos(angle) * spark_dist)
                sy = cy + int(math.sin(angle) * spark_dist)
                spark_r = 2 + int(2 * math.sin(ticks * 0.02 + i * 0.5))
                pygame.draw.circle(self.screen, (255, 200, 50), (sx, sy),
                                   max(1, spark_r))

        else:
            # Phase 3: Fade out with smoke
            sub_p = (p - 0.7) / 0.3
            alpha_f = 1.0 - sub_p
            radius = int(max_radius * (1.0 + sub_p * 0.2))  # slightly expanding

            # Fading red-orange
            r_val = int(200 * alpha_f)
            g_val = int(60 * alpha_f)
            if r_val > 5:
                fade_r = int(radius * 0.6 * alpha_f)
                if fade_r > 0:
                    pygame.draw.circle(self.screen, (r_val, g_val, 0),
                                       (cx, cy), fade_r)

            # Fading outer ring
            ring_r = int(180 * alpha_f)
            if ring_r > 5:
                pygame.draw.circle(self.screen, (ring_r, ring_r // 4, 0),
                                   (cx, cy), radius, 2)

            # Smoke rings — gray, drifting outward
            smoke_gray = int(80 * alpha_f)
            if smoke_gray > 5:
                smoke_r = int(radius * (1.0 + sub_p * 0.5))
                pygame.draw.circle(self.screen, (smoke_gray, smoke_gray, smoke_gray),
                                   (cx, cy), smoke_r, 1)
                # Second smoke ring slightly offset
                smoke_r2 = int(radius * (0.8 + sub_p * 0.6))
                pygame.draw.circle(self.screen,
                                   (smoke_gray // 2, smoke_gray // 2, smoke_gray // 2),
                                   (cx, cy), smoke_r2, 1)

    def _u3_draw_lightning_bolt(self, ax, ay, ts, fx):
        """Draw a crackling lightning bolt along a line of tiles.

        Three phases:
        1. (0.0-0.2) Bolt appears tile-by-tile with a bright flash
        2. (0.2-0.7) Full bolt crackles and arcs with electrical energy
        3. (0.7-1.0) Bolt fades with residual sparks
        """
        p = fx.progress  # 0 → 1
        tiles = fx.tiles
        if not tiles:
            return

        ticks = pygame.time.get_ticks()
        num_tiles = len(tiles)

        if p < 0.2:
            # Phase 1: bolt extends tile by tile
            sub_p = p / 0.2
            visible_count = max(1, int(sub_p * num_tiles))
            visible_tiles = tiles[:visible_count]

            # Bright white flash on the newest tile
            if visible_tiles:
                last_c, last_r = visible_tiles[-1]
                flash_cx = int(ax + last_c * ts + ts // 2)
                flash_cy = int(ay + last_r * ts + ts // 2)
                pygame.draw.circle(self.screen, (255, 255, 255),
                                   (flash_cx, flash_cy), ts // 2)

            # Draw bolt segments between consecutive tiles
            for i in range(len(visible_tiles)):
                c, r = visible_tiles[i]
                cx = int(ax + c * ts + ts // 2)
                cy = int(ay + r * ts + ts // 2)

                # Bright core on each tile
                pygame.draw.circle(self.screen, (200, 200, 255),
                                   (cx, cy), 4)

                # Connect to previous tile with a jagged line
                if i > 0:
                    pc, pr = visible_tiles[i - 1]
                    px = int(ax + pc * ts + ts // 2)
                    py_ = int(ay + pr * ts + ts // 2)
                    self._draw_jagged_line(px, py_, cx, cy,
                                           (180, 180, 255), 2, ticks)

        elif p < 0.7:
            # Phase 2: full bolt crackles with arcs
            sub_p = (p - 0.2) / 0.5

            # Draw all segments with flickering brightness
            for i in range(num_tiles):
                c, r = tiles[i]
                cx = int(ax + c * ts + ts // 2)
                cy = int(ay + r * ts + ts // 2)

                # Flickering glow per tile
                flicker = 0.6 + 0.4 * math.sin(ticks * 0.02 + i * 1.3)
                glow_r = int(ts * 0.4 * flicker)
                bright = int(220 * flicker)

                # Blue-white electrical glow
                pygame.draw.circle(self.screen,
                                   (bright // 2, bright // 2, bright),
                                   (cx, cy), glow_r)
                # Bright core
                pygame.draw.circle(self.screen, (255, 255, 255),
                                   (cx, cy), max(2, glow_r // 3))

                # Connect to previous tile
                if i > 0:
                    pc, pr = tiles[i - 1]
                    px = int(ax + pc * ts + ts // 2)
                    py_ = int(ay + pr * ts + ts // 2)
                    line_bright = int(255 * flicker)
                    self._draw_jagged_line(px, py_, cx, cy,
                                           (line_bright // 2, line_bright // 2, line_bright),
                                           3, ticks)

            # Random arc sparks branching off the bolt
            for i in range(3):
                idx = (ticks // 80 + i * 7) % num_tiles
                bc, br = tiles[idx]
                bx = int(ax + bc * ts + ts // 2)
                by = int(ay + br * ts + ts // 2)
                # Random offset for the spark
                spark_dx = random.randint(-ts // 2, ts // 2)
                spark_dy = random.randint(-ts // 2, ts // 2)
                pygame.draw.line(self.screen, (150, 150, 255),
                                 (bx, by),
                                 (bx + spark_dx, by + spark_dy), 1)

        else:
            # Phase 3: fade out with residual sparks
            sub_p = (p - 0.7) / 0.3
            alpha_f = 1.0 - sub_p

            for i in range(num_tiles):
                c, r = tiles[i]
                cx = int(ax + c * ts + ts // 2)
                cy = int(ay + r * ts + ts // 2)

                # Fading glow
                bright = int(150 * alpha_f)
                if bright > 5:
                    glow_r = int(ts * 0.3 * alpha_f)
                    if glow_r > 0:
                        pygame.draw.circle(self.screen,
                                           (bright // 3, bright // 3, bright),
                                           (cx, cy), glow_r)

                # Connect to previous tile (fading)
                if i > 0 and bright > 10:
                    pc, pr = tiles[i - 1]
                    px = int(ax + pc * ts + ts // 2)
                    py_ = int(ay + pr * ts + ts // 2)
                    self._draw_jagged_line(px, py_, cx, cy,
                                           (bright // 3, bright // 3, bright),
                                           max(1, int(2 * alpha_f)), ticks)

            # Residual sparks — fewer as we fade
            spark_count = max(0, int(4 * alpha_f))
            for i in range(spark_count):
                idx = (ticks // 120 + i * 5) % num_tiles
                sc, sr = tiles[idx]
                sx = int(ax + sc * ts + ts // 2)
                sy = int(ay + sr * ts + ts // 2)
                sdx = random.randint(-ts // 3, ts // 3)
                sdy = random.randint(-ts // 3, ts // 3)
                spark_bright = int(200 * alpha_f)
                if spark_bright > 10:
                    pygame.draw.line(self.screen,
                                     (spark_bright // 2, spark_bright // 2, spark_bright),
                                     (sx, sy), (sx + sdx, sy + sdy), 1)

    def _draw_jagged_line(self, x1, y1, x2, y2, color, width, ticks):
        """Draw a jagged/zigzag line between two points to simulate electricity."""
        # Break the line into segments and offset the midpoints
        segments = 4
        points = [(x1, y1)]
        for s in range(1, segments):
            t = s / segments
            mx = int(x1 + (x2 - x1) * t)
            my = int(y1 + (y2 - y1) * t)
            # Perpendicular offset for jaggedness
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1:
                points.append((mx, my))
                continue
            # Perpendicular direction
            px = -dy / length
            py_ = dx / length
            # Offset oscillates based on time and segment index
            offset = 3 * math.sin(ticks * 0.03 + s * 2.7)
            mx += int(px * offset)
            my += int(py_ * offset)
            points.append((mx, my))
        points.append((x2, y2))

        # Draw the jagged line
        for i in range(len(points) - 1):
            pygame.draw.line(self.screen, color,
                             points[i], points[i + 1], width)

    def _u3_draw_cure_poison_effect(self, ax, ay, ts, fx):
        """Draw a cleansing cure-poison effect — green toxin rising out, replaced by white purity.

        Three phases:
        1. (0.0-0.3) Green poison bubbles rise out of the target
        2. (0.3-0.7) White/gold cleansing glow intensifies
        3. (0.7-1.0) Gentle sparkle fade-out
        """
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1
        ticks = pygame.time.get_ticks()

        if p < 0.3:
            # Phase 1: Green poison bubbles rise out
            sub_p = p / 0.3
            # Rising green particles
            for i in range(6):
                angle = i * 1.047  # ~60 degrees apart
                rise = sub_p * ts * 0.8
                bx = cx + int(math.cos(angle + ticks * 0.005) * ts * 0.3)
                by = cy - int(rise) + int(math.sin(ticks * 0.008 + i) * 3)
                bubble_r = max(1, int(3 * (1.0 - sub_p)))
                g_val = int(200 * (1.0 - sub_p))
                if g_val > 10:
                    pygame.draw.circle(self.screen, (30, g_val, 30),
                                       (bx, by), bubble_r)

            # Green glow fading away from target
            glow_r = int(ts * 0.4)
            glow_alpha = 1.0 - sub_p
            green = int(150 * glow_alpha)
            if green > 5:
                pygame.draw.circle(self.screen, (20, green, 20),
                                   (cx, cy), glow_r, 2)

        elif p < 0.7:
            # Phase 2: White/gold cleansing glow
            sub_p = (p - 0.3) / 0.4
            glow_r = int(ts * 0.5 * (0.6 + 0.4 * sub_p))
            flicker = 0.8 + 0.2 * math.sin(ticks * 0.015)

            # Inner white glow
            inner_r = max(2, int(glow_r * 0.5 * flicker))
            pygame.draw.circle(self.screen, (255, 255, 240),
                               (cx, cy), inner_r)

            # Gold ring
            gold_r = int(glow_r * flicker)
            pygame.draw.circle(self.screen, (255, 215, 80),
                               (cx, cy), gold_r, 2)

            # Outer white ring
            pygame.draw.circle(self.screen, (220, 255, 220),
                               (cx, cy), int(glow_r * 1.2), 1)

        else:
            # Phase 3: Sparkle fade-out
            sub_p = (p - 0.7) / 0.3
            alpha_f = 1.0 - sub_p

            # Fading sparkles
            for i in range(4):
                angle = ticks * 0.004 + i * 1.57
                dist = ts * 0.3 * (1.0 + sub_p * 0.5)
                sx = cx + int(math.cos(angle) * dist)
                sy = cy + int(math.sin(angle) * dist)
                bright = int(220 * alpha_f)
                if bright > 10:
                    pygame.draw.circle(self.screen,
                                       (bright, bright, bright // 2),
                                       (sx, sy), max(1, int(2 * alpha_f)))

            # Fading center glow
            center_bright = int(180 * alpha_f)
            if center_bright > 5:
                pygame.draw.circle(self.screen,
                                   (center_bright, center_bright, center_bright // 2),
                                   (cx, cy), max(1, int(ts * 0.2 * alpha_f)))

    def _u3_draw_bless_effect(self, ax, ay, ts, fx):
        """Draw a golden blessing aura — expanding rings of light with sparkles.

        Three phases:
        1. (0.0-0.3) Golden pillar of light descends from above
        2. (0.3-0.7) Expanding golden rings radiate outward
        3. (0.7-1.0) Gentle golden sparkle fade-out
        """
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1
        ticks = pygame.time.get_ticks()

        if p < 0.3:
            # Phase 1: Golden pillar of light descends
            sub_p = p / 0.3
            beam_top = cy - int(ts * 1.5 * (1.0 - sub_p))
            beam_w = max(2, int(ts * 0.15))
            bright = int(255 * sub_p)
            if bright > 10:
                pygame.draw.line(self.screen, (bright, int(bright * 0.84), 0),
                                 (cx, beam_top), (cx, cy), beam_w)
                # Inner white core
                pygame.draw.line(self.screen, (bright, bright, int(bright * 0.6)),
                                 (cx, beam_top), (cx, cy), max(1, beam_w // 2))

        elif p < 0.7:
            # Phase 2: Expanding golden rings
            sub_p = (p - 0.3) / 0.4
            for ring_i in range(3):
                ring_p = (sub_p + ring_i * 0.15) % 1.0
                ring_r = int(ts * 0.2 + ts * 0.6 * ring_p)
                alpha_f = max(0.0, 1.0 - ring_p)
                gold = int(220 * alpha_f)
                if gold > 10:
                    pygame.draw.circle(self.screen, (gold, int(gold * 0.85), 0),
                                       (cx, cy), ring_r, 2)
            # Central warm glow
            flicker = 0.8 + 0.2 * math.sin(ticks * 0.012)
            glow_r = max(2, int(ts * 0.3 * flicker))
            pygame.draw.circle(self.screen, (255, 215, 80),
                               (cx, cy), glow_r)

        else:
            # Phase 3: Golden sparkle fade-out
            sub_p = (p - 0.7) / 0.3
            alpha_f = 1.0 - sub_p
            for i in range(5):
                angle = ticks * 0.005 + i * 1.257
                dist = ts * 0.4 * (1.0 + sub_p * 0.3)
                sx = cx + int(math.cos(angle) * dist)
                sy = cy + int(math.sin(angle) * dist)
                bright = int(200 * alpha_f)
                if bright > 10:
                    pygame.draw.circle(self.screen, (bright, int(bright * 0.84), 0),
                                       (sx, sy), max(1, int(2 * alpha_f)))
            # Fading center glow
            center_b = int(160 * alpha_f)
            if center_b > 5:
                pygame.draw.circle(self.screen, (center_b, int(center_b * 0.84), 0),
                                   (cx, cy), max(1, int(ts * 0.15 * alpha_f)))

    def _u3_draw_curse_effect(self, ax, ay, ts, fx):
        """Draw a dark malediction — purple/black energy spiraling inward onto the target.

        Three phases:
        1. (0.0-0.3) Dark tendrils spiral inward from edges
        2. (0.3-0.7) Pulsing dark aura with purple flashes
        3. (0.7-1.0) Aura shrinks and brands the target
        """
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1
        ticks = pygame.time.get_ticks()

        if p < 0.3:
            # Phase 1: Dark tendrils spiral inward
            sub_p = p / 0.3
            for i in range(6):
                angle = ticks * 0.006 + i * 1.047
                dist = ts * 0.8 * (1.0 - sub_p)
                tx_pos = cx + int(math.cos(angle) * dist)
                ty_pos = cy + int(math.sin(angle) * dist)
                bright = int(120 * sub_p)
                pygame.draw.line(self.screen, (bright, 0, int(bright * 1.5)),
                                 (tx_pos, ty_pos), (cx, cy), max(1, int(2 * sub_p)))

        elif p < 0.7:
            # Phase 2: Pulsing dark aura with purple flashes
            sub_p = (p - 0.3) / 0.4
            pulse = 0.7 + 0.3 * math.sin(ticks * 0.015)
            aura_r = int(ts * 0.5 * pulse)

            # Dark core
            pygame.draw.circle(self.screen, (40, 0, 60),
                               (cx, cy), max(2, int(aura_r * 0.5)))
            # Purple ring
            pygame.draw.circle(self.screen, (140, 40, 200),
                               (cx, cy), aura_r, 2)
            # Outer dark ring
            pygame.draw.circle(self.screen, (80, 0, 120),
                               (cx, cy), int(aura_r * 1.3), 1)

            # Occasional purple spark
            if (ticks // 80) % 3 == 0:
                spark_angle = random.random() * 6.28
                spark_dist = random.randint(2, int(ts * 0.4))
                sx = cx + int(math.cos(spark_angle) * spark_dist)
                sy = cy + int(math.sin(spark_angle) * spark_dist)
                pygame.draw.circle(self.screen, (180, 60, 255),
                                   (sx, sy), 2)

        else:
            # Phase 3: Aura shrinks and brands
            sub_p = (p - 0.7) / 0.3
            alpha_f = 1.0 - sub_p
            aura_r = max(2, int(ts * 0.4 * alpha_f))

            pygame.draw.circle(self.screen, (int(100 * alpha_f), 0, int(150 * alpha_f)),
                               (cx, cy), aura_r, 2)
            # Fading purple center
            core_b = int(80 * alpha_f)
            if core_b > 5:
                pygame.draw.circle(self.screen, (core_b, 0, int(core_b * 1.5)),
                                   (cx, cy), max(1, int(aura_r * 0.4)))

    def _u3_draw_monster_spell_effect(self, ax, ay, ts, fx):
        """Draw a monster spell-like ability effect.

        Colour-coded by spell type with a pulsing glow and label text.
        Supports: sleep (purple), curse (red), heal (green), poison (sickly green).
        """
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1
        ticks = pygame.time.get_ticks()
        r, g, b = fx.color

        if p < 0.3:
            # Phase 1: expanding ring
            sub_p = p / 0.3
            radius = max(2, int(ts * 0.6 * sub_p))
            pygame.draw.circle(self.screen, (r, g, b), (cx, cy), radius, 2)
            # Inner glow
            inner_r = max(1, int(radius * 0.4))
            pygame.draw.circle(self.screen, (min(255, r + 60),
                               min(255, g + 60), min(255, b + 60)),
                               (cx, cy), inner_r)

        elif p < 0.7:
            # Phase 2: pulsing aura with sparkles
            sub_p = (p - 0.3) / 0.4
            pulse = 0.7 + 0.3 * math.sin(ticks * 0.012)
            radius = max(2, int(ts * 0.5 * pulse))
            # Outer ring
            pygame.draw.circle(self.screen, (r, g, b), (cx, cy), radius, 2)
            # Inner fill (dim)
            dim_r = max(1, int(radius * 0.5))
            pygame.draw.circle(self.screen, (r // 3, g // 3, b // 3),
                               (cx, cy), dim_r)
            # Sparkles
            for i in range(4):
                angle = ticks * 0.008 + i * 1.57
                dist = random.randint(2, max(3, int(ts * 0.35)))
                sx = cx + int(math.cos(angle) * dist)
                sy = cy + int(math.sin(angle) * dist)
                pygame.draw.circle(self.screen, (min(255, r + 80),
                                   min(255, g + 80), min(255, b + 80)),
                                   (sx, sy), 2)

        else:
            # Phase 3: fade out
            sub_p = (p - 0.7) / 0.3
            alpha_f = 1.0 - sub_p
            radius = max(2, int(ts * 0.4 * alpha_f))
            cr = int(r * alpha_f)
            cg = int(g * alpha_f)
            cb = int(b * alpha_f)
            if cr + cg + cb > 10:
                pygame.draw.circle(self.screen, (cr, cg, cb),
                                   (cx, cy), radius, 2)

        # Draw spell label above the effect
        if p < 0.85:
            label = fx.label
            if not fx.success:
                label += " - Resisted!"
            font = self.font_small
            txt = font.render(label, True, (r, g, b))
            lx = cx - txt.get_width() // 2
            ly = cy - ts // 2 - 12 - int(p * 8)
            self.screen.blit(txt, (lx, ly))

    def _u3_draw_heal_effect(self, ax, ay, ts, fx):
        """Draw a healing glow — green sparkles rising upward with heal number."""
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ax + fx.row * ts + ts // 2)
        # Fix: use ay for y-axis
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1

        # Phase 1 (0–0.4): green glow expanding
        # Phase 2 (0.4–0.7): sparkles rising
        # Phase 3 (0.7–1.0): fade out

        if p < 0.4:
            # Green glow expanding from center
            sub_p = p / 0.4
            radius = int(4 + sub_p * 14)
            # Bright green core
            g_val = int(200 + 55 * sub_p)
            pygame.draw.circle(self.screen, (80, g_val, 80), (cx, cy), radius)
            # White sparkle center
            pygame.draw.circle(self.screen, (200, 255, 200), (cx, cy),
                               max(1, radius // 3))
        elif p < 0.7:
            # Sparkles rising upward
            sub_p = (p - 0.4) / 0.3
            base_radius = int(14 - sub_p * 4)
            # Central glow fading
            alpha_f = 1.0 - sub_p * 0.5
            g_val = int(220 * alpha_f)
            if g_val > 0:
                pygame.draw.circle(self.screen, (int(60 * alpha_f), g_val,
                                                  int(60 * alpha_f)),
                                   (cx, cy), base_radius)
            # Rising sparkle particles
            for i in range(4):
                angle = (i * 90 + sub_p * 120) * 3.14159 / 180
                spark_r = int(8 + sub_p * 12)
                sx = cx + int(math.cos(angle) * spark_r)
                sy = cy - int(sub_p * 16) + int(math.sin(angle) * spark_r // 2)
                spark_size = max(1, int(3 * (1.0 - sub_p)))
                pygame.draw.circle(self.screen, (150, 255, 150),
                                   (sx, sy), spark_size)
        else:
            # Fade out — gentle green shimmer
            sub_p = (p - 0.7) / 0.3
            alpha_f = 1.0 - sub_p
            g_val = int(180 * alpha_f)
            if g_val > 0:
                for i in range(3):
                    float_y = cy - int(12 + sub_p * 20) + i * 6
                    spark_size = max(1, int(2 * alpha_f))
                    pygame.draw.circle(self.screen,
                                       (int(100 * alpha_f), g_val,
                                        int(100 * alpha_f)),
                                       (cx - 4 + i * 4, float_y), spark_size)

        # Heal number floating upward (green "+N")
        if fx.amount > 0 and p > 0.15:
            float_y = cy - 14 - int(p * 24)
            heal_text = f"+{fx.amount}"
            surf = self.font.render(heal_text, True, (100, 255, 100))
            outline = self.font.render(heal_text, True, self._U3_BLACK)
            rx = cx - surf.get_width() // 2
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                self.screen.blit(outline, (rx + ox, float_y + oy))
            self.screen.blit(surf, (rx, float_y))

    def _u3_draw_shield_bubble(self, ax, ay, ts, col, row, turns_left):
        """Draw a persistent glowing bubble around a shielded character.

        The bubble pulses gently, with orbiting sparkles. As the buff nears
        expiration (1 turn left), the bubble flickers to signal it's fading.
        """
        ticks = pygame.time.get_ticks()
        cx = int(ax + col * ts + ts // 2)
        cy = int(ay + row * ts + ts // 2)

        # Gentle pulse
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.003)

        # Flicker when about to expire
        if turns_left <= 1:
            flicker = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(ticks * 0.02))
        else:
            flicker = 1.0

        base_alpha = int((40 + 25 * pulse) * flicker)
        radius = int(ts * 0.48)

        # Translucent dome fill
        bubble_surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4),
                                     pygame.SRCALPHA)
        fill_color = (80, 160, 255, base_alpha)
        pygame.draw.circle(bubble_surf, fill_color,
                           (radius + 2, radius + 2), radius)
        self.screen.blit(bubble_surf,
                         (cx - radius - 2, cy - radius - 2))

        # Bright ring outline
        ring_alpha = int((120 + 80 * pulse) * flicker)
        ring_surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4),
                                   pygame.SRCALPHA)
        ring_color = (100, 180, 255, ring_alpha)
        pygame.draw.circle(ring_surf, ring_color,
                           (radius + 2, radius + 2), radius, 2)
        self.screen.blit(ring_surf,
                         (cx - radius - 2, cy - radius - 2))

        # Orbiting sparkles (3 small dots circling the perimeter)
        num_sparkles = 3
        orbit_r = radius - 2
        for i in range(num_sparkles):
            angle_offset = (i * 360.0 / num_sparkles)
            angle = math.radians(angle_offset + ticks * 0.08)
            sx = cx + int(math.cos(angle) * orbit_r)
            sy = cy + int(math.sin(angle) * orbit_r)
            sparkle_alpha = int((160 + 80 * pulse) * flicker)
            sparkle_surf = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(sparkle_surf,
                               (180, 220, 255, sparkle_alpha), (3, 3), 2)
            self.screen.blit(sparkle_surf, (sx - 3, sy - 3))

        # Top highlight arc (subtle shine on top of bubble)
        shine_alpha = int((60 + 40 * pulse) * flicker)
        shine_surf = pygame.Surface((radius * 2 + 4, radius + 4),
                                    pygame.SRCALPHA)
        shine_rect = pygame.Rect(4, 4, radius * 2 - 4, radius - 2)
        pygame.draw.ellipse(shine_surf,
                            (200, 230, 255, shine_alpha), shine_rect, 1)
        self.screen.blit(shine_surf,
                         (cx - radius - 2, cy - radius - 2))

    def _u3_draw_range_buff_indicator(self, ax, ay, ts, col, row, turns_left):
        """Draw a green speed-lines aura around a character with Long Shanks.

        Small green arrows/lines sweep upward around the character to
        indicate enhanced movement.  Flickers when about to expire.
        """
        ticks = pygame.time.get_ticks()
        cx = int(ax + col * ts + ts // 2)
        cy = int(ay + row * ts + ts // 2)

        # Flicker when about to expire
        if turns_left <= 1:
            flicker = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(ticks * 0.02))
        else:
            flicker = 1.0

        GREEN = (80, 255, 120)
        BRIGHT_GREEN = (140, 255, 180)

        # Pulsing green glow at feet
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
        glow_r = int(ts * 0.35)
        glow_alpha = int((30 + 20 * pulse) * flicker)
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                    pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*GREEN, glow_alpha),
                           (glow_r + 2, glow_r + 2), glow_r)
        self.screen.blit(glow_surf,
                         (cx - glow_r - 2, cy - glow_r - 2))

        # Speed lines sweeping upward on both sides
        num_lines = 4
        for i in range(num_lines):
            phase = ((ticks * 0.004 + i * 0.5) % 2.0)
            if phase > 1.0:
                continue
            side = -1 if i % 2 == 0 else 1
            lx = cx + side * int(ts * 0.3)
            ly_start = cy + int(ts * 0.3) - int(phase * ts * 0.6)
            ly_end = ly_start - int(4 + phase * 3)
            line_alpha = int(180 * (1.0 - phase) * flicker)
            if line_alpha > 10:
                line_surf = pygame.Surface((3, abs(ly_end - ly_start) + 2),
                                           pygame.SRCALPHA)
                pygame.draw.line(line_surf, (*BRIGHT_GREEN, line_alpha),
                                 (1, abs(ly_end - ly_start)), (1, 0), 2)
                self.screen.blit(line_surf, (lx - 1, min(ly_start, ly_end)))

    def _u3_draw_turn_undead_effect(self, ax, ay, ts, fx):
        """Draw the Turn Undead holy blast — a radiant wave of golden-white
        light expanding from the caster and engulfing the monster.

        Phase 1 (0–0.25): Holy glow builds around caster
        Phase 2 (0.25–0.65): Radiant wave travels toward the monster
        Phase 3 (0.65–1.0): Bright explosion on the monster + fade
        """
        p = fx.progress  # 0 → 1

        # Caster and monster pixel centers
        cast_cx = int(ax + fx.caster_col * ts + ts // 2)
        cast_cy = int(ay + fx.caster_row * ts + ts // 2)
        mon_cx = int(ax + fx.monster_col * ts + ts // 2)
        mon_cy = int(ay + fx.monster_row * ts + ts // 2)

        # Gold / holy white colors
        GOLD = (255, 220, 80)
        HOLY_WHITE = (255, 255, 220)
        HOLY_GLOW = (255, 240, 150)

        if p < 0.25:
            # Phase 1: holy glow building around caster
            sub_p = p / 0.25
            radius = int(4 + sub_p * 14)
            # Bright gold core
            glow_surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4),
                                       pygame.SRCALPHA)
            alpha = int(120 * sub_p)
            pygame.draw.circle(glow_surf, (*GOLD, alpha),
                               (radius + 2, radius + 2), radius)
            self.screen.blit(glow_surf,
                             (cast_cx - radius - 2, cast_cy - radius - 2))
            # White sparkle center
            pygame.draw.circle(self.screen, HOLY_WHITE,
                               (cast_cx, cast_cy), max(2, int(3 * sub_p)))
            # Rising holy sparkles
            ticks = pygame.time.get_ticks()
            for i in range(4):
                angle = math.radians(i * 90 + ticks * 0.15)
                sr = int(6 + sub_p * 8)
                sx = cast_cx + int(math.cos(angle) * sr)
                sy = cast_cy - int(sub_p * 8) + int(math.sin(angle) * sr // 2)
                s_size = max(1, int(2 * sub_p))
                pygame.draw.circle(self.screen, HOLY_GLOW, (sx, sy), s_size)

        elif p < 0.65:
            # Phase 2: radiant wave traveling from caster to monster
            sub_p = (p - 0.25) / 0.4
            # Interpolate position
            wave_cx = int(cast_cx + (mon_cx - cast_cx) * sub_p)
            wave_cy = int(cast_cy + (mon_cy - cast_cy) * sub_p)

            # Trailing glow at caster (fading)
            fade = max(0, 1.0 - sub_p * 1.5)
            if fade > 0:
                tr_r = int(10 * fade)
                tr_surf = pygame.Surface((tr_r * 2 + 4, tr_r * 2 + 4),
                                         pygame.SRCALPHA)
                pygame.draw.circle(tr_surf, (*GOLD, int(60 * fade)),
                                   (tr_r + 2, tr_r + 2), tr_r)
                self.screen.blit(tr_surf,
                                 (cast_cx - tr_r - 2, cast_cy - tr_r - 2))

            # Main wave orb
            orb_r = int(8 + 4 * math.sin(sub_p * 6))
            orb_surf = pygame.Surface((orb_r * 2 + 4, orb_r * 2 + 4),
                                       pygame.SRCALPHA)
            pygame.draw.circle(orb_surf, (*HOLY_WHITE, 180),
                               (orb_r + 2, orb_r + 2), orb_r)
            self.screen.blit(orb_surf,
                             (wave_cx - orb_r - 2, wave_cy - orb_r - 2))
            # Gold ring around orb
            pygame.draw.circle(self.screen, GOLD, (wave_cx, wave_cy),
                               orb_r + 2, 2)

            # Trail particles
            for i in range(3):
                t_off = sub_p - i * 0.08
                if t_off < 0:
                    continue
                tx = int(cast_cx + (mon_cx - cast_cx) * t_off)
                ty = int(cast_cy + (mon_cy - cast_cy) * t_off)
                trail_alpha = max(0, 1.0 - i * 0.35)
                tr_size = max(1, int(3 * trail_alpha))
                tr_surf2 = pygame.Surface((tr_size * 2 + 2, tr_size * 2 + 2),
                                           pygame.SRCALPHA)
                pygame.draw.circle(tr_surf2,
                                   (*HOLY_GLOW, int(100 * trail_alpha)),
                                   (tr_size + 1, tr_size + 1), tr_size)
                self.screen.blit(tr_surf2,
                                 (tx - tr_size - 1, ty - tr_size - 1))

        else:
            # Phase 3: explosion of holy light on the monster
            sub_p = (p - 0.65) / 0.35
            fade = 1.0 - sub_p

            # Expanding radiant burst
            burst_r = int(12 + sub_p * 20)
            burst_surf = pygame.Surface((burst_r * 2 + 4, burst_r * 2 + 4),
                                         pygame.SRCALPHA)
            alpha = int(160 * fade)
            pygame.draw.circle(burst_surf, (*GOLD, alpha),
                               (burst_r + 2, burst_r + 2), burst_r)
            self.screen.blit(burst_surf,
                             (mon_cx - burst_r - 2, mon_cy - burst_r - 2))

            # Inner white flash
            flash_r = int(burst_r * 0.5)
            flash_surf = pygame.Surface((flash_r * 2 + 4, flash_r * 2 + 4),
                                         pygame.SRCALPHA)
            pygame.draw.circle(flash_surf, (*HOLY_WHITE, int(200 * fade)),
                               (flash_r + 2, flash_r + 2), flash_r)
            self.screen.blit(flash_surf,
                             (mon_cx - flash_r - 2, mon_cy - flash_r - 2))

            # Holy rays radiating outward
            num_rays = 8
            for i in range(num_rays):
                angle = math.radians(i * (360 / num_rays) + sub_p * 45)
                inner_r = int(burst_r * 0.3)
                outer_r = burst_r
                x1 = mon_cx + int(math.cos(angle) * inner_r)
                y1 = mon_cy + int(math.sin(angle) * inner_r)
                x2 = mon_cx + int(math.cos(angle) * outer_r)
                y2 = mon_cy + int(math.sin(angle) * outer_r)
                ray_surf = pygame.Surface(
                    (abs(x2 - x1) + 6, abs(y2 - y1) + 6), pygame.SRCALPHA)
                # Draw ray as a line on main screen with alpha approximation
                ray_alpha = fade
                ray_color = (int(255 * ray_alpha), int(240 * ray_alpha),
                             int(150 * ray_alpha))
                if ray_color[0] > 10:
                    pygame.draw.line(self.screen, ray_color, (x1, y1),
                                     (x2, y2), max(1, int(2 * fade)))

            # Scattering sparkles
            ticks = pygame.time.get_ticks()
            for i in range(6):
                angle = math.radians(i * 60 + ticks * 0.1)
                dist = int(burst_r * 0.7 + sub_p * 10)
                sx = mon_cx + int(math.cos(angle) * dist)
                sy = mon_cy + int(math.sin(angle) * dist)
                s_size = max(1, int(2 * fade))
                s_alpha = int(180 * fade)
                if s_alpha > 10:
                    spark_surf = pygame.Surface((s_size * 2 + 2, s_size * 2 + 2),
                                                pygame.SRCALPHA)
                    pygame.draw.circle(spark_surf, (*HOLY_WHITE, s_alpha),
                                       (s_size + 1, s_size + 1), s_size)
                    self.screen.blit(spark_surf,
                                     (sx - s_size - 1, sy - s_size - 1))

    def _u3_draw_charmed_indicator(self, ax, ay, ts, col, row):
        """Draw a pulsing pink glow and floating hearts over a charmed monster."""
        ticks = pygame.time.get_ticks()
        cx = int(ax + col * ts + ts // 2)
        cy = int(ax + row * ts + ts // 2)
        # Correct y base from ax to ay
        cy = int(ay + row * ts + ts // 2)

        PINK = (255, 120, 200)
        MAGENTA = (220, 60, 180)

        # Pulsing pink glow around the monster
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.004)
        glow_r = int(ts // 2 + 2)
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                    pygame.SRCALPHA)
        alpha = int(40 + 30 * pulse)
        pygame.draw.circle(glow_surf, (*PINK, alpha),
                           (glow_r + 2, glow_r + 2), glow_r)
        self.screen.blit(glow_surf,
                         (cx - glow_r - 2, cy - glow_r - 2))

        # Small floating hearts above the monster
        for i in range(2):
            h_phase = (ticks * 0.002 + i * 1.5) % 2.0
            if h_phase < 1.0:
                hx = cx + int(math.sin(h_phase * 3.14 + i) * 5)
                hy = cy - ts // 2 - int(h_phase * 8) - i * 4
                h_size = max(1, int(2 * (1.0 - h_phase)))
                h_alpha = int(180 * (1.0 - h_phase))
                if h_alpha > 10:
                    h_surf = pygame.Surface((h_size * 2 + 2, h_size * 2 + 2),
                                             pygame.SRCALPHA)
                    pygame.draw.circle(h_surf, (*MAGENTA, h_alpha),
                                       (h_size + 1, h_size + 1), h_size)
                    self.screen.blit(h_surf,
                                     (hx - h_size - 1, hy - h_size - 1))

    def _u3_draw_charm_effect(self, ax, ay, ts, fx):
        """Draw the Charm Person enchantment — swirling pink/purple spirals.

        Phase 1 (0–0.3): Pink sparkles gather around the target
        Phase 2 (0.3–0.7): Swirling enchantment spiral tightens
        Phase 3 (0.7–1.0): Flash (pink for success, red puff for resist) + fade
        """
        p = fx.progress  # 0 → 1

        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)

        PINK = (255, 120, 200)
        PURPLE = (180, 80, 220)
        MAGENTA = (220, 60, 180)
        RESIST_RED = (255, 80, 80)

        ticks = pygame.time.get_ticks()

        if p < 0.3:
            # Phase 1: pink sparkles gathering
            sub_p = p / 0.3
            num_sparks = int(6 + sub_p * 6)
            for i in range(num_sparks):
                angle = math.radians(i * (360 / num_sparks) + ticks * 0.2)
                dist = int(20 - sub_p * 12)
                sx = cx + int(math.cos(angle) * dist)
                sy = cy + int(math.sin(angle) * dist)
                s_size = max(1, int(3 * sub_p))
                alpha = int(160 * sub_p)
                spark_surf = pygame.Surface((s_size * 2 + 2, s_size * 2 + 2),
                                            pygame.SRCALPHA)
                color = PINK if i % 2 == 0 else PURPLE
                pygame.draw.circle(spark_surf, (*color, alpha),
                                   (s_size + 1, s_size + 1), s_size)
                self.screen.blit(spark_surf,
                                 (sx - s_size - 1, sy - s_size - 1))

        elif p < 0.7:
            # Phase 2: swirling enchantment spiral
            sub_p = (p - 0.3) / 0.4
            num_orbs = 8
            for i in range(num_orbs):
                base_angle = i * (360 / num_orbs)
                spin = ticks * 0.3 + sub_p * 360
                angle = math.radians(base_angle + spin)
                dist = int(14 - sub_p * 6)
                ox = cx + int(math.cos(angle) * dist)
                oy = cy + int(math.sin(angle) * dist)
                o_size = max(1, int(2 + sub_p * 2))
                alpha = int(200 * (0.5 + 0.5 * math.sin(sub_p * 10 + i)))
                alpha = max(0, min(255, alpha))
                orb_surf = pygame.Surface((o_size * 2 + 2, o_size * 2 + 2),
                                           pygame.SRCALPHA)
                color = MAGENTA if i % 2 == 0 else PURPLE
                pygame.draw.circle(orb_surf, (*color, alpha),
                                   (o_size + 1, o_size + 1), o_size)
                self.screen.blit(orb_surf,
                                 (ox - o_size - 1, oy - o_size - 1))
            # Central glow
            glow_r = int(6 + sub_p * 4)
            glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                        pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*PINK, int(100 * sub_p)),
                               (glow_r + 2, glow_r + 2), glow_r)
            self.screen.blit(glow_surf,
                             (cx - glow_r - 2, cy - glow_r - 2))

        else:
            # Phase 3: result flash + fade
            sub_p = (p - 0.7) / 0.3
            fade = 1.0 - sub_p

            if fx.success:
                # Pink/magenta burst — charmed!
                burst_r = int(10 + sub_p * 18)
                burst_surf = pygame.Surface((burst_r * 2 + 4, burst_r * 2 + 4),
                                             pygame.SRCALPHA)
                pygame.draw.circle(burst_surf, (*PINK, int(160 * fade)),
                                   (burst_r + 2, burst_r + 2), burst_r)
                self.screen.blit(burst_surf,
                                 (cx - burst_r - 2, cy - burst_r - 2))
                # Heart-like sparkles floating up
                for i in range(4):
                    hx = cx + int(math.sin(ticks * 0.005 + i * 1.5) * 8)
                    hy = cy - int(sub_p * 20) - i * 5
                    h_size = max(1, int(3 * fade))
                    h_alpha = int(200 * fade)
                    if h_alpha > 10:
                        h_surf = pygame.Surface((h_size * 2 + 2, h_size * 2 + 2),
                                                 pygame.SRCALPHA)
                        pygame.draw.circle(h_surf, (*MAGENTA, h_alpha),
                                           (h_size + 1, h_size + 1), h_size)
                        self.screen.blit(h_surf,
                                         (hx - h_size - 1, hy - h_size - 1))
            else:
                # Red puff — resisted
                puff_r = int(8 + sub_p * 10)
                puff_surf = pygame.Surface((puff_r * 2 + 4, puff_r * 2 + 4),
                                            pygame.SRCALPHA)
                pygame.draw.circle(puff_surf, (*RESIST_RED, int(120 * fade)),
                                   (puff_r + 2, puff_r + 2), puff_r)
                self.screen.blit(puff_surf,
                                 (cx - puff_r - 2, cy - puff_r - 2))

    def _u3_draw_sleep_indicator(self, ax, ay, ts, col, row, turns_left):
        """Draw floating 'Zzz' letters above a sleeping monster with a blue glow."""
        ticks = pygame.time.get_ticks()
        cx = int(ax + col * ts + ts // 2)
        cy = int(ay + row * ts + ts // 2)

        SLEEP_BLUE = (100, 140, 255)
        DEEP_BLUE = (60, 80, 200)

        # Pulsing blue glow around the monster
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.003)
        glow_r = int(ts // 2 + 2)
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                    pygame.SRCALPHA)
        alpha = int(30 + 25 * pulse)
        pygame.draw.circle(glow_surf, (*DEEP_BLUE, alpha),
                           (glow_r + 2, glow_r + 2), glow_r)
        self.screen.blit(glow_surf,
                         (cx - glow_r - 2, cy - glow_r - 2))

        # Floating "Z" letters drifting upward
        for i in range(3):
            z_phase = (ticks * 0.0015 + i * 0.8) % 2.0
            if z_phase < 1.5:
                z_progress = z_phase / 1.5
                zx = cx + int(math.sin(z_progress * 2.5 + i * 1.2) * 6) + (i - 1) * 4
                zy = cy - ts // 2 - int(z_progress * 14) - i * 3
                z_alpha = int(200 * (1.0 - z_progress * 0.7))
                z_size = max(6, 10 - i * 2)
                if z_alpha > 20:
                    z_font = self.font_small
                    z_text = "Z"
                    z_surf = z_font.render(z_text, True, (*SLEEP_BLUE,))
                    z_overlay = pygame.Surface(z_surf.get_size(), pygame.SRCALPHA)
                    z_overlay.fill((0, 0, 0, 0))
                    z_overlay.blit(z_surf, (0, 0))
                    z_overlay.set_alpha(z_alpha)
                    self.screen.blit(z_overlay, (zx, zy))

    def _u3_draw_poison_indicator(self, ax, ay, ts, col, row, turns_left):
        """Draw a sickly green bubbling indicator above a poisoned fighter."""
        ticks = pygame.time.get_ticks()
        cx = int(ax + col * ts + ts // 2)
        cy = int(ay + row * ts + ts // 2)

        POISON_GREEN = (80, 180, 40)
        DARK_GREEN = (40, 100, 20)

        # Pulsing green tint
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
        glow_r = int(ts // 2 + 2)
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                    pygame.SRCALPHA)
        alpha = int(20 + 20 * pulse)
        pygame.draw.circle(glow_surf, (*DARK_GREEN, alpha),
                           (glow_r + 2, glow_r + 2), glow_r)
        self.screen.blit(glow_surf,
                         (cx - glow_r - 2, cy - glow_r - 2))

        # Small bubbles rising
        for i in range(3):
            b_phase = (ticks * 0.002 + i * 0.7) % 2.0
            if b_phase < 1.5:
                b_progress = b_phase / 1.5
                bx = cx + int(math.sin(b_progress * 3.0 + i * 1.5) * 5) + (i - 1) * 3
                by = cy - ts // 2 - int(b_progress * 10) - i * 2
                b_alpha = int(160 * (1.0 - b_progress * 0.7))
                b_r = max(1, 3 - i)
                if b_alpha > 20:
                    bub_surf = pygame.Surface((b_r * 2 + 2, b_r * 2 + 2),
                                              pygame.SRCALPHA)
                    pygame.draw.circle(bub_surf, (*POISON_GREEN, b_alpha),
                                       (b_r + 1, b_r + 1), b_r)
                    self.screen.blit(bub_surf, (bx - b_r - 1, by - b_r - 1))

    def _u3_draw_curse_indicator(self, ax, ay, ts, col, row, turns_left):
        """Draw a dark purple swirl indicator above a cursed fighter."""
        ticks = pygame.time.get_ticks()
        cx = int(ax + col * ts + ts // 2)
        cy = int(ay + row * ts + ts // 2)

        CURSE_PURPLE = (140, 40, 200)

        # Small rotating dark particles
        for i in range(3):
            angle = ticks * 0.004 + i * 2.09
            dist = int(ts * 0.3)
            px = cx + int(math.cos(angle) * dist)
            py = cy - ts // 4 + int(math.sin(angle) * dist * 0.5)
            pygame.draw.circle(self.screen, CURSE_PURPLE, (px, py), 2)

    def _u3_draw_sleep_effect(self, ax, ay, ts, fx):
        """Draw the Sleep spell effect — soft blue/purple mist descending.

        Phase 1 (0–0.3): Blue sparkles drift down around the target
        Phase 2 (0.3–0.7): Swirling blue mist envelops the target
        Phase 3 (0.7–1.0): Flash (blue glow for success, fizzle for resist) + fade
        """
        p = fx.progress  # 0 → 1

        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)

        LIGHT_BLUE = (140, 180, 255)
        DEEP_BLUE = (60, 80, 220)
        SOFT_PURPLE = (120, 100, 200)
        RESIST_RED = (255, 80, 80)

        ticks = pygame.time.get_ticks()

        if p < 0.3:
            # Phase 1: blue sparkles drifting down
            sub_p = p / 0.3
            num_sparkles = int(6 + sub_p * 10)
            for i in range(num_sparkles):
                angle = (ticks * 0.003 + i * 0.7) % (2 * math.pi)
                r = ts * 0.6 * (1.0 - sub_p * 0.4)
                sx = cx + int(math.cos(angle) * r)
                sy = cy - ts // 2 + int(sub_p * ts * 0.8) + int(math.sin(angle + i) * 3)
                spark_alpha = int(120 + 80 * math.sin(ticks * 0.01 + i))
                spark_r = max(1, int(2 - sub_p))
                s = pygame.Surface((spark_r * 2 + 2, spark_r * 2 + 2),
                                    pygame.SRCALPHA)
                pygame.draw.circle(s, (*LIGHT_BLUE, spark_alpha),
                                   (spark_r + 1, spark_r + 1), spark_r)
                self.screen.blit(s, (sx - spark_r - 1, sy - spark_r - 1))

        elif p < 0.7:
            # Phase 2: blue mist enveloping
            sub_p = (p - 0.3) / 0.4
            mist_r = int(ts * 0.5 + sub_p * ts * 0.2)
            mist_alpha = int(60 + 40 * sub_p)
            mist_surf = pygame.Surface((mist_r * 2 + 4, mist_r * 2 + 4),
                                        pygame.SRCALPHA)
            pygame.draw.circle(mist_surf, (*DEEP_BLUE, mist_alpha),
                               (mist_r + 2, mist_r + 2), mist_r)
            self.screen.blit(mist_surf,
                             (cx - mist_r - 2, cy - mist_r - 2))

            # Inner swirl
            for i in range(4):
                swirl_angle = ticks * 0.005 + i * 1.57 + sub_p * 3
                sr = mist_r * (0.3 + 0.3 * sub_p)
                sx = cx + int(math.cos(swirl_angle) * sr)
                sy = cy + int(math.sin(swirl_angle) * sr)
                dot_r = max(1, int(3 - sub_p * 2))
                dot_alpha = int(140 * (1.0 - sub_p * 0.3))
                dot_surf = pygame.Surface((dot_r * 2 + 2, dot_r * 2 + 2),
                                           pygame.SRCALPHA)
                pygame.draw.circle(dot_surf, (*SOFT_PURPLE, dot_alpha),
                                   (dot_r + 1, dot_r + 1), dot_r)
                self.screen.blit(dot_surf, (sx - dot_r - 1, sy - dot_r - 1))

        else:
            # Phase 3: result flash + fade
            sub_p = (p - 0.7) / 0.3
            fade = 1.0 - sub_p

            if fx.success:
                # Blue glow settling — monster falls asleep
                glow_r = int(ts * 0.6 - sub_p * ts * 0.2)
                glow_alpha = int(100 * fade)
                if glow_r > 0 and glow_alpha > 5:
                    glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                                pygame.SRCALPHA)
                    pygame.draw.circle(glow_surf, (*DEEP_BLUE, glow_alpha),
                                       (glow_r + 2, glow_r + 2), glow_r)
                    self.screen.blit(glow_surf,
                                     (cx - glow_r - 2, cy - glow_r - 2))
            else:
                # Red fizzle puff — resisted
                puff_r = int(6 + sub_p * 8)
                puff_surf = pygame.Surface((puff_r * 2 + 4, puff_r * 2 + 4),
                                            pygame.SRCALPHA)
                pygame.draw.circle(puff_surf, (*RESIST_RED, int(100 * fade)),
                                   (puff_r + 2, puff_r + 2), puff_r)
                self.screen.blit(puff_surf,
                                 (cx - puff_r - 2, cy - puff_r - 2))

    def _u3_draw_teleport_effect(self, ax, ay, ts, fx):
        """Draw Misty Step teleport — silvery mist at origin fading out, then
        coalescing at the destination.

        Phase 1 (0–0.4): Swirling silver mist at origin, caster fades out
        Phase 2 (0.4–0.7): Streaking silver particles travel from origin to dest
        Phase 3 (0.7–1.0): Silver mist coalesces at destination, caster appears
        """
        p = fx.progress  # 0 → 1

        from_cx = int(ax + fx.from_col * ts + ts // 2)
        from_cy = int(ay + fx.from_row * ts + ts // 2)
        to_cx = int(ax + fx.to_col * ts + ts // 2)
        to_cy = int(ay + fx.to_row * ts + ts // 2)

        SILVER = (200, 210, 230)
        LIGHT_SILVER = (220, 230, 245)
        MIST_BLUE = (150, 180, 220)
        WHITE = (255, 255, 255)

        ticks = pygame.time.get_ticks()

        if p < 0.4:
            # Phase 1: swirling silver mist at origin
            sub_p = p / 0.4
            num_particles = int(8 + sub_p * 12)
            expand = 1.0 + sub_p * 0.5
            for i in range(num_particles):
                angle = (ticks * 0.005 + i * 0.45) % (2 * math.pi)
                r = ts * 0.3 * expand + math.sin(ticks * 0.008 + i) * 3
                sx = from_cx + int(math.cos(angle) * r)
                sy = from_cy + int(math.sin(angle) * r)
                alpha = int(160 * (1.0 - sub_p * 0.5))
                spark_r = max(1, int(3 - sub_p))
                s = pygame.Surface((spark_r * 2 + 2, spark_r * 2 + 2),
                                    pygame.SRCALPHA)
                color = SILVER if i % 2 == 0 else MIST_BLUE
                pygame.draw.circle(s, (*color, alpha),
                                   (spark_r + 1, spark_r + 1), spark_r)
                self.screen.blit(s, (sx - spark_r - 1, sy - spark_r - 1))

            # Fading glow at origin
            glow_r = int(ts * 0.5)
            glow_alpha = int(80 * (1.0 - sub_p))
            if glow_alpha > 5:
                glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                            pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (*LIGHT_SILVER, glow_alpha),
                                   (glow_r + 2, glow_r + 2), glow_r)
                self.screen.blit(glow_surf,
                                 (from_cx - glow_r - 2, from_cy - glow_r - 2))

        elif p < 0.7:
            # Phase 2: streaking particles from origin to destination
            sub_p = (p - 0.4) / 0.3
            num_streaks = 6
            for i in range(num_streaks):
                t = (sub_p + i * 0.12) % 1.0
                # Particle position along the line
                px = from_cx + int((to_cx - from_cx) * t)
                py = from_cy + int((to_cy - from_cy) * t)
                # Add slight wobble
                wobble = math.sin(ticks * 0.01 + i * 2.0) * 4
                px += int(wobble)
                py += int(math.cos(ticks * 0.01 + i * 1.5) * 3)
                streak_alpha = int(200 * (1.0 - abs(t - 0.5) * 2))
                streak_r = max(1, 3 - int(abs(t - 0.5) * 4))
                s = pygame.Surface((streak_r * 2 + 2, streak_r * 2 + 2),
                                    pygame.SRCALPHA)
                color = WHITE if i % 3 == 0 else SILVER
                pygame.draw.circle(s, (*color, streak_alpha),
                                   (streak_r + 1, streak_r + 1), streak_r)
                self.screen.blit(s, (px - streak_r - 1, py - streak_r - 1))

        else:
            # Phase 3: silver mist coalescing at destination
            sub_p = (p - 0.7) / 0.3
            num_particles = int(12 * (1.0 - sub_p * 0.5))
            contract = 1.0 - sub_p * 0.7
            for i in range(num_particles):
                angle = (ticks * 0.006 + i * 0.5) % (2 * math.pi)
                r = ts * 0.4 * contract + math.sin(ticks * 0.007 + i) * 2
                sx = to_cx + int(math.cos(angle) * r)
                sy = to_cy + int(math.sin(angle) * r)
                alpha = int(180 * (1.0 - sub_p * 0.8))
                spark_r = max(1, int(3 * (1.0 - sub_p * 0.5)))
                s = pygame.Surface((spark_r * 2 + 2, spark_r * 2 + 2),
                                    pygame.SRCALPHA)
                color = LIGHT_SILVER if i % 2 == 0 else SILVER
                pygame.draw.circle(s, (*color, alpha),
                                   (spark_r + 1, spark_r + 1), spark_r)
                self.screen.blit(s, (sx - spark_r - 1, sy - spark_r - 1))

            # Brightening glow at destination
            glow_r = int(ts * 0.5 * (1.0 - sub_p * 0.3))
            glow_alpha = int(60 + 40 * sub_p)
            glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                        pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*WHITE, min(glow_alpha, 120)),
                               (glow_r + 2, glow_r + 2), glow_r)
            self.screen.blit(glow_surf,
                             (to_cx - glow_r - 2, to_cy - glow_r - 2))

    def _u3_draw_invisibility_effect(self, ax, ay, ts, fx):
        """Draw the Invisibility casting effect — character shimmers and fades.

        Phase 1 (0–0.4): Silvery-white sparkles swirl inward around the caster
        Phase 2 (0.4–0.7): Body shimmers with refractive light distortion
        Phase 3 (0.7–1.0): Caster fades to near-transparent with a soft glow
        """
        p = fx.progress  # 0 → 1

        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)

        SILVER_WHITE = (220, 230, 250)
        LIGHT_CYAN = (180, 220, 255)
        PALE_BLUE = (160, 190, 240)

        ticks = pygame.time.get_ticks()

        if p < 0.4:
            # Phase 1: sparkles swirl inward
            sub_p = p / 0.4
            num_sparkles = int(10 + sub_p * 8)
            contract = 1.0 - sub_p * 0.6
            for i in range(num_sparkles):
                angle = (ticks * 0.006 + i * 0.5) % (2 * math.pi)
                r = ts * 0.5 * contract
                sx = cx + int(math.cos(angle) * r)
                sy = cy + int(math.sin(angle) * r)
                alpha = int(180 * (0.5 + 0.5 * math.sin(ticks * 0.01 + i)))
                spark_r = max(1, int(2.5 - sub_p))
                s = pygame.Surface((spark_r * 2 + 2, spark_r * 2 + 2),
                                    pygame.SRCALPHA)
                color = SILVER_WHITE if i % 2 == 0 else LIGHT_CYAN
                pygame.draw.circle(s, (*color, alpha),
                                   (spark_r + 1, spark_r + 1), spark_r)
                self.screen.blit(s, (sx - spark_r - 1, sy - spark_r - 1))

        elif p < 0.7:
            # Phase 2: shimmering distortion around the caster
            sub_p = (p - 0.4) / 0.3
            for i in range(6):
                shimmer_angle = ticks * 0.008 + i * 1.05
                sr = ts * 0.25 + math.sin(ticks * 0.005 + i) * 4
                sx = cx + int(math.cos(shimmer_angle) * sr)
                sy = cy + int(math.sin(shimmer_angle) * sr)
                shimmer_alpha = int(120 * (1.0 - sub_p * 0.5))
                dot_r = max(1, 3)
                s = pygame.Surface((dot_r * 2 + 2, dot_r * 2 + 2),
                                    pygame.SRCALPHA)
                pygame.draw.circle(s, (*PALE_BLUE, shimmer_alpha),
                                   (dot_r + 1, dot_r + 1), dot_r)
                self.screen.blit(s, (sx - dot_r - 1, sy - dot_r - 1))

            # Central glow
            glow_r = int(ts * 0.4)
            glow_alpha = int(50 + 30 * sub_p)
            glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                        pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*SILVER_WHITE, glow_alpha),
                               (glow_r + 2, glow_r + 2), glow_r)
            self.screen.blit(glow_surf,
                             (cx - glow_r - 2, cy - glow_r - 2))

        else:
            # Phase 3: fade out with residual glow
            sub_p = (p - 0.7) / 0.3
            fade = 1.0 - sub_p
            glow_r = int(ts * 0.35 * fade)
            glow_alpha = int(60 * fade)
            if glow_r > 0 and glow_alpha > 5:
                glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                            pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (*LIGHT_CYAN, glow_alpha),
                                   (glow_r + 2, glow_r + 2), glow_r)
                self.screen.blit(glow_surf,
                                 (cx - glow_r - 2, cy - glow_r - 2))

    def _u3_draw_animate_dead_effect(self, ax, ay, ts, fx):
        """Draw Animate Dead — dark bones/earth rising from the ground.

        Phase 1 (0–0.3): Dark green/brown particles bubble up from below
        Phase 2 (0.3–0.7): Bone fragments swirl upward forming a shape
        Phase 3 (0.7–1.0): Dark flash as the skeleton solidifies
        """
        p = fx.progress  # 0 → 1

        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)

        DARK_GREEN = (40, 80, 30)
        BONE_WHITE = (200, 200, 180)
        EARTH_BROWN = (80, 60, 30)
        SICKLY_GREEN = (80, 160, 60)

        ticks = pygame.time.get_ticks()

        if p < 0.3:
            # Phase 1: dark particles bubbling up from below
            sub_p = p / 0.3
            num = int(6 + sub_p * 10)
            for i in range(num):
                bx = cx + int(math.sin(ticks * 0.004 + i * 1.1) * ts * 0.3)
                rise = sub_p * ts * 0.6
                by = cy + ts // 2 - int(rise * (i / max(num, 1)))
                alpha = int(140 * sub_p)
                r = max(1, int(2 + math.sin(i + ticks * 0.005)))
                s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
                color = EARTH_BROWN if i % 2 == 0 else DARK_GREEN
                pygame.draw.circle(s, (*color, alpha),
                                   (r + 1, r + 1), r)
                self.screen.blit(s, (bx - r - 1, by - r - 1))

        elif p < 0.7:
            # Phase 2: bone fragments swirl upward
            sub_p = (p - 0.3) / 0.4
            num_bones = int(8 + sub_p * 6)
            for i in range(num_bones):
                angle = (ticks * 0.005 + i * 0.7) % (2 * math.pi)
                shrink = 1.0 - sub_p * 0.6
                r = ts * 0.35 * shrink
                bx = cx + int(math.cos(angle) * r)
                by = cy - int(sub_p * ts * 0.3) + int(math.sin(angle) * r * 0.5)
                alpha = int(200 * (0.5 + 0.5 * sub_p))
                bone_r = max(1, int(2.5))
                s = pygame.Surface((bone_r * 2 + 2, bone_r * 2 + 2),
                                    pygame.SRCALPHA)
                color = BONE_WHITE if i % 3 != 0 else SICKLY_GREEN
                pygame.draw.circle(s, (*color, alpha),
                                   (bone_r + 1, bone_r + 1), bone_r)
                self.screen.blit(s, (bx - bone_r - 1, by - bone_r - 1))

            # Central glow
            glow_r = int(ts * 0.3)
            glow_alpha = int(40 + 30 * sub_p)
            glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                        pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*SICKLY_GREEN, glow_alpha),
                               (glow_r + 2, glow_r + 2), glow_r)
            self.screen.blit(glow_surf,
                             (cx - glow_r - 2, cy - glow_r - 2))

        else:
            # Phase 3: dark flash as skeleton solidifies
            sub_p = (p - 0.7) / 0.3
            fade = 1.0 - sub_p

            # Sickly green burst
            burst_r = int(ts * 0.4 + sub_p * ts * 0.2)
            burst_alpha = int(80 * fade)
            if burst_r > 0 and burst_alpha > 5:
                burst_surf = pygame.Surface((burst_r * 2 + 4, burst_r * 2 + 4),
                                             pygame.SRCALPHA)
                pygame.draw.circle(burst_surf, (*SICKLY_GREEN, burst_alpha),
                                   (burst_r + 2, burst_r + 2), burst_r)
                self.screen.blit(burst_surf,
                                 (cx - burst_r - 2, cy - burst_r - 2))

            # Bone-white flash in center
            flash_r = int(ts * 0.25 * fade)
            flash_alpha = int(120 * fade)
            if flash_r > 0 and flash_alpha > 5:
                flash_surf = pygame.Surface((flash_r * 2 + 4, flash_r * 2 + 4),
                                             pygame.SRCALPHA)
                pygame.draw.circle(flash_surf, (*BONE_WHITE, flash_alpha),
                                   (flash_r + 2, flash_r + 2), flash_r)
                self.screen.blit(flash_surf,
                                 (cx - flash_r - 2, cy - flash_r - 2))

    def _u3_draw_summon_indicator(self, ax, ay, ts, col, row, turns_left):
        """Draw a subtle green glow around a summoned skeleton ally."""
        ticks = pygame.time.get_ticks()
        cx = int(ax + col * ts + ts // 2)
        cy = int(ay + row * ts + ts // 2)

        SUMMON_GREEN = (80, 180, 80)

        # Pulsing green glow
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.004)
        glow_r = int(ts // 2 + 2)
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4),
                                    pygame.SRCALPHA)
        # Flicker when about to expire
        if turns_left <= 2:
            flicker = int(abs(math.sin(ticks * 0.015)) * 40)
            alpha = int(20 + flicker * pulse)
        else:
            alpha = int(30 + 20 * pulse)
        pygame.draw.circle(glow_surf, (*SUMMON_GREEN, alpha),
                           (glow_r + 2, glow_r + 2), glow_r)
        self.screen.blit(glow_surf,
                         (cx - glow_r - 2, cy - glow_r - 2))

    def _u3_draw_target_cursor(self, ax, ay, ts, col, row):
        """Draw a pulsing blue selection box at (col, row) on the arena."""
        ticks = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.006)

        px = ax + col * ts
        py = ay + row * ts

        # Pulsing blue box outline (2-pixel border)
        blue_val = int(140 + 115 * pulse)
        color = (80, int(160 * pulse), blue_val)
        rect = pygame.Rect(px, py, ts, ts)
        pygame.draw.rect(self.screen, color, rect, 2)

        # Corner brackets for extra visibility
        bracket_len = ts // 3
        bright = (int(120 + 135 * pulse), int(180 + 75 * pulse), 255)
        # Top-left
        pygame.draw.line(self.screen, bright, (px, py), (px + bracket_len, py), 2)
        pygame.draw.line(self.screen, bright, (px, py), (px, py + bracket_len), 2)
        # Top-right
        pygame.draw.line(self.screen, bright, (px + ts, py), (px + ts - bracket_len, py), 2)
        pygame.draw.line(self.screen, bright, (px + ts, py), (px + ts, py + bracket_len), 2)
        # Bottom-left
        pygame.draw.line(self.screen, bright, (px, py + ts), (px + bracket_len, py + ts), 2)
        pygame.draw.line(self.screen, bright, (px, py + ts), (px, py + ts - bracket_len), 2)
        # Bottom-right
        pygame.draw.line(self.screen, bright, (px + ts, py + ts), (px + ts - bracket_len, py + ts), 2)
        pygame.draw.line(self.screen, bright, (px + ts, py + ts), (px + ts, py + ts - bracket_len), 2)

        # Subtle translucent blue fill
        overlay = pygame.Surface((ts, ts), pygame.SRCALPHA)
        alpha = int(30 + 30 * pulse)
        overlay.fill((80, 160, 255, alpha))
        self.screen.blit(overlay, (px, py))

    def _u3_draw_shield_effect(self, ax, ay, ts, fx):
        """Draw a shield glow — blue energy dome coalescing around the target."""
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1

        # Phase 1 (0–0.3): blue sparks converging inward
        # Phase 2 (0.3–0.6): shield dome forming
        # Phase 3 (0.6–1.0): bright flash then fade

        if p < 0.3:
            sub_p = p / 0.3
            # Blue sparks converging from edges
            for i in range(6):
                angle = (i * 60 + sub_p * 180) * 3.14159 / 180
                dist = int(18 * (1.0 - sub_p))
                sx = cx + int(math.cos(angle) * dist)
                sy = cy + int(math.sin(angle) * dist)
                spark_size = max(1, int(2 + sub_p * 2))
                blue_val = int(180 + 75 * sub_p)
                pygame.draw.circle(self.screen, (100, 160, blue_val),
                                   (sx, sy), spark_size)
        elif p < 0.6:
            sub_p = (p - 0.3) / 0.3
            # Shield dome forming — concentric blue rings
            radius = int(6 + sub_p * 10)
            blue_val = int(200 + 55 * sub_p)
            # Outer ring
            pygame.draw.circle(self.screen, (80, 140, blue_val),
                               (cx, cy), radius, 2)
            # Inner glow
            inner_r = max(1, radius - 4)
            glow_surf = pygame.Surface((inner_r * 2, inner_r * 2), pygame.SRCALPHA)
            alpha = int(80 * sub_p)
            pygame.draw.circle(glow_surf, (100, 180, 255, alpha),
                               (inner_r, inner_r), inner_r)
            self.screen.blit(glow_surf, (cx - inner_r, cy - inner_r))
        else:
            sub_p = (p - 0.6) / 0.4
            alpha_f = 1.0 - sub_p
            # Fading shield dome
            radius = int(16 - sub_p * 4)
            blue_val = int(255 * alpha_f)
            if blue_val > 10:
                pygame.draw.circle(self.screen, (int(60 * alpha_f),
                                                  int(120 * alpha_f),
                                                  blue_val),
                                   (cx, cy), radius, 2)
                # Fading inner sparkles
                for i in range(3):
                    angle = (i * 120 + sub_p * 90) * 3.14159 / 180
                    sr = int(radius * 0.6)
                    sx = cx + int(math.cos(angle) * sr)
                    sy = cy + int(math.sin(angle) * sr)
                    s_size = max(1, int(2 * alpha_f))
                    pygame.draw.circle(self.screen,
                                       (int(100 * alpha_f), int(180 * alpha_f),
                                        int(255 * alpha_f)),
                                       (sx, sy), s_size)

        # AC bonus text floating upward (blue "+N AC")
        if fx.ac_bonus > 0 and p > 0.2:
            float_y = cy - 14 - int(p * 24)
            txt = f"+{fx.ac_bonus} AC"
            surf = self.font.render(txt, True, (100, 180, 255))
            outline = self.font.render(txt, True, self._U3_BLACK)
            rx = cx - surf.get_width() // 2
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                self.screen.blit(outline, (rx + ox, float_y + oy))
            self.screen.blit(surf, (rx, float_y))

    # ==============================================================
    #  RIGHT-HAND PANELS
    # ==============================================================

    def _u3_draw_stat_bar(self, x, y, w, h, current, maximum, color, bg=(40, 40, 40)):
        """Draw a horizontal stat bar (HP or MP style)."""
        pygame.draw.rect(self.screen, bg, pygame.Rect(x, y, w, h))
        if maximum > 0:
            fill = max(1, int((w - 2) * current / maximum))
            pygame.draw.rect(self.screen, color,
                             pygame.Rect(x + 1, y + 1, fill, h - 2))
        pygame.draw.rect(self.screen, (80, 80, 80), pygame.Rect(x, y, w, h), 1)

    def _u3_party_combat_panel(self, fighters, active_fighter,
                                defending_map, x, y, w, h,
                                shield_buffs=None, range_buffs=None,
                                invisibility_buffs=None,
                                bless_buffs=None):
        """Party roster with character sprites and HP/MP bars."""
        self._u3_panel(x, y, w, h)
        f = self.font
        tx = x + 8
        ty = y + 6

        self._u3_text("PARTY", tx, ty, self._U3_ORANGE, f)
        ty += 22

        sprite_size = 32  # sprite display area
        bar_w = w - sprite_size - 30  # bar width after sprite + padding
        bar_h = 8

        for i, member in enumerate(fighters):
            is_active = (member is active_fighter)
            is_def = defending_map.get(member, False)
            row_top = ty

            # ── Character sprite ──
            sprite = self._get_member_sprite(member)
            if sprite:
                sx = tx
                sy = row_top + 2
                if not member.is_alive():
                    # Dim the sprite for dead members
                    dim = sprite.copy()
                    dim.set_alpha(80)
                    self.screen.blit(dim, (sx, sy))
                else:
                    self.screen.blit(sprite, (sx, sy))
                    if is_active:
                        # Orange highlight box around active character
                        pygame.draw.rect(self.screen, self._U3_ORANGE,
                                         pygame.Rect(sx - 2, sy - 2,
                                                     sprite.get_width() + 4,
                                                     sprite.get_height() + 4), 2)

            # ── Name + class (to the right of sprite) ──
            info_x = tx + sprite_size + 6

            if not member.is_alive():
                name_color = self._U3_RED
            elif is_active:
                name_color = self._U3_ORANGE
            else:
                name_color = self._U3_WHITE

            wpn_label = member.weapon if member.weapon else "Fists"
            self._u3_text(member.name, info_x, row_top, name_color, f)

            # ── Stat line: AC, weapon, damage dice ──
            stat_y = row_top + 16
            ac_val = member.get_ac()
            dice_c, dice_s, dice_b = member.get_damage_dice()
            dmg_str = f"{dice_c}d{dice_s}"
            if dice_b > 0:
                dmg_str += f"+{dice_b}"
            elif dice_b < 0:
                dmg_str += f"{dice_b}"
            stat_line = f"AC:{ac_val}  {wpn_label}  DMG:{dmg_str}"
            self._u3_text(stat_line, info_x, stat_y, (180, 210, 230), self.font_small)

            # ── HP bar + numeric readout ──
            bar_y = row_top + 28
            hp_color = self._U3_GREEN if member.hp > member.max_hp * 0.3 else self._U3_RED
            hp_bar_w = bar_w - 60  # leave room for numbers
            self._u3_draw_stat_bar(info_x, bar_y, hp_bar_w, bar_h,
                                   member.hp, member.max_hp, hp_color)
            hp_txt = f"{member.hp}/{member.max_hp}"
            self._u3_text(hp_txt, info_x + hp_bar_w + 4, bar_y - 2,
                          self._U3_WHITE, self.font_small)

            # ── MP bar + numeric readout ──
            mp_y = bar_y + bar_h + 3
            mp_val = member.current_mp
            mp_max = member.max_mp
            if mp_max > 0:
                self._u3_draw_stat_bar(info_x, mp_y, hp_bar_w, bar_h,
                                       mp_val, mp_max, (100, 100, 255))
                mp_txt = f"{mp_val}/{mp_max}"
                self._u3_text(mp_txt, info_x + hp_bar_w + 4, mp_y - 2,
                              self._U3_WHITE, self.font_small)

            # ── DEF / SHLD indicators ──
            indicator_y = row_top + 28
            if is_def:
                self._u3_text("DEF", x + w - 40, indicator_y, self._U3_ORANGE, self.font_small)
                indicator_y += 12
            if shield_buffs and shield_buffs.get(member):
                self._u3_text("SHLD", x + w - 44, indicator_y, (100, 180, 255), self.font_small)
                indicator_y += 12
            if range_buffs and range_buffs.get(member):
                self._u3_text("FAST", x + w - 44, indicator_y, (80, 255, 120), self.font_small)
                indicator_y += 12
            if invisibility_buffs and invisibility_buffs.get(member):
                self._u3_text("INVIS", x + w - 48, indicator_y, (180, 200, 255), self.font_small)
                indicator_y += 12
            if bless_buffs and bless_buffs.get(member):
                self._u3_text("BLSS", x + w - 44, indicator_y, (255, 215, 80), self.font_small)

            # ── Ammo indicator for throwable weapons ──
            if member.is_throwable_weapon():
                ammo_count = member.get_ammo()
                ammo_color = self._U3_WHITE if ammo_count > 0 else self._U3_RED
                ammo_y = mp_y if mp_max > 0 else bar_y + bar_h + 3
                self._u3_text(f"x{ammo_count}", x + w - 32, ammo_y - 2, ammo_color, self.font_small)

            ty += 68  # row height per character

    def _u3_fighter_panel(self, fighter, defending, x, y, w, h,
                          shield_buffs=None):
        """Player stats in Ultima III format."""
        self._u3_panel(x, y, w, h)
        f = self.font
        tx = x + 8
        ty = y + 6

        self._u3_text(fighter.name, tx, ty, self._U3_ORANGE, f)
        self._u3_text(fighter.char_class, tx + 160, ty, self._U3_LTBLUE, f)

        ty += 22
        ac = fighter.get_ac() + (2 if defending else 0)
        shield = (shield_buffs or {}).get(fighter)
        if shield:
            ac += shield["ac_bonus"]
        self._u3_text(f"HP:{fighter.hp:d}/{fighter.max_hp:d}  AC:{ac:d}",
                      tx, ty, self._U3_WHITE, f)
        if defending:
            self._u3_text("DEF", tx + 220, ty, self._U3_ORANGE, f)
        if shield:
            label_x = tx + 220 + (32 if defending else 0)
            self._u3_text("SHLD", label_x, ty, (100, 180, 255), f)

        ty += 18
        self._u3_text(f"S:{fighter.strength:d} D:{fighter.dexterity:d} I:{fighter.intelligence:d} W:{fighter.wisdom:d}",
                      tx, ty, (200, 200, 200), f)

        ty += 18
        self._u3_text(f"LVL:{fighter.level:d}  EXP:{fighter.exp:d}/{fighter.xp_for_next_level:d}",
                      tx, ty, (200, 200, 200), f)

        ty += 18
        self._u3_text(f"WPN: {fighter.weapon}", tx, ty, (200, 200, 200), f)

        ty += 18
        dice_c, dice_s, dice_b = fighter.get_damage_dice()
        atk = f"ATK: D20{format_modifier(fighter.get_attack_bonus())}  DMG: {dice_c}D{dice_s}{format_modifier(dice_b)}"
        self._u3_text(atk, tx, ty, (200, 200, 200), f)

    def _u3_monster_panel(self, monster, x, y, w, h, source_state="dungeon"):
        """Monster stats panel — same layout as party panel entries."""
        self._u3_panel(x, y, w, h)
        f = self.font
        tx = x + 8
        ty = y + 6

        self._u3_text("ENEMY", tx, ty, self._U3_RED, f)
        ty += 22

        sprite_size = 32
        bar_w = w - sprite_size - 30
        bar_h = 8

        # ── Monster sprite ──
        sprite = self._get_monster_sprite(monster)
        if sprite:
            sx = tx
            sy = ty + 2
            self.screen.blit(sprite, (sx, sy))

        # ── Name + type (to the right of sprite) ──
        info_x = tx + sprite_size + 6
        self._u3_text(monster.name, info_x, ty, self._U3_RED, f)
        atk_short = f"AC:{monster.ac}"
        self._u3_text(atk_short, x + w - 70, ty, self._U3_LTBLUE, f)

        # ── HP bar ──
        bar_y = ty + 18
        hp_color = (200, 40, 40) if monster.hp > monster.max_hp * 0.3 else self._U3_RED
        self._u3_draw_stat_bar(info_x, bar_y, bar_w, bar_h,
                               monster.hp, monster.max_hp, hp_color)
        self._u3_text("HP", info_x - 26, bar_y - 2, (200, 200, 200), self.font_small)

        # ── ATK/DMG line ──
        stat_y = bar_y + bar_h + 3
        atk_text = f"ATK:+{monster.attack_bonus:d}  DMG:{monster.damage_dice}D{monster.damage_sides}+{monster.damage_bonus}"
        self._u3_text(atk_text, info_x, stat_y, (200, 200, 200), self.font_small)

    def _u3_monster_panel_multi(self, monsters, x, y, w, h,
                               source_state="dungeon", encounter_name=None,
                               sleep_buffs=None, summon_buffs=None,
                               curse_buffs=None):
        """Monster stats panel matching the party panel format with sprites and bars."""
        self._u3_panel(x, y, w, h)
        f = self.font
        tx = x + 8
        ty = y + 6

        label = encounter_name or ("ENEMY" if len(monsters) == 1 else "ENEMIES")
        self._u3_text(label, tx, ty, self._U3_RED, f)
        ty += 22

        sprite_size = 32  # sprite display area (matches party panel)
        bar_w = w - sprite_size - 30  # bar width after sprite + padding
        bar_h = 8

        for mon in monsters:
            row_top = ty

            # ── Monster sprite ──
            sprite = self._get_monster_sprite(mon)
            if sprite:
                sx = tx
                sy = row_top + 2
                if not mon.is_alive():
                    dim = sprite.copy()
                    dim.set_alpha(80)
                    self.screen.blit(dim, (sx, sy))
                else:
                    self.screen.blit(sprite, (sx, sy))

            # ── Name (to the right of sprite) ──
            info_x = tx + sprite_size + 6
            is_charmed = getattr(mon, "charmed", False)
            is_summoned = (summon_buffs and mon in summon_buffs) if summon_buffs else False
            is_sleeping = (sleep_buffs and mon in sleep_buffs) if sleep_buffs else False
            is_cursed = (curse_buffs and mon in curse_buffs) if curse_buffs else False
            if is_summoned:
                name_color = (120, 220, 140)  # Green for summoned
                display_name = f"{mon.name} (Summon)"
            elif is_charmed:
                name_color = (255, 120, 200)  # Pink for charmed
                display_name = f"{mon.name} (Ally)"
            elif is_sleeping:
                name_color = (120, 140, 220)  # Blue for sleeping
                display_name = f"{mon.name} (Zzz)"
            elif is_cursed and mon.is_alive():
                name_color = (180, 80, 200)  # Purple for cursed
                display_name = f"{mon.name} (Cursed)"
            elif mon.is_alive():
                name_color = self._U3_RED
                display_name = mon.name
            else:
                name_color = (120, 40, 40)
                display_name = mon.name
            self._u3_text(display_name, info_x, row_top, name_color, f)

            # ── Stat line: AC, damage dice, attack bonus ──
            stat_y = row_top + 16
            dmg_str = f"{mon.damage_dice}d{mon.damage_sides}"
            if mon.damage_bonus > 0:
                dmg_str += f"+{mon.damage_bonus}"
            elif mon.damage_bonus < 0:
                dmg_str += f"{mon.damage_bonus}"
            atk_str = f"+{mon.attack_bonus}" if mon.attack_bonus >= 0 else f"{mon.attack_bonus}"
            stat_line = f"AC:{mon.ac}  ATK:{atk_str}  DMG:{dmg_str}"
            self._u3_text(stat_line, info_x, stat_y, (210, 190, 170), self.font_small)

            # ── HP bar + numeric readout (green→red like party panel) ──
            bar_y = row_top + 28
            hp_color = self._U3_GREEN if mon.hp > mon.max_hp * 0.3 else self._U3_RED
            hp_bar_w = bar_w - 60  # leave room for numbers
            self._u3_draw_stat_bar(info_x, bar_y, hp_bar_w, bar_h,
                                   mon.hp, mon.max_hp, hp_color)
            hp_txt = f"{mon.hp}/{mon.max_hp}"
            self._u3_text(hp_txt, info_x + hp_bar_w + 4, bar_y - 2,
                          self._U3_WHITE, self.font_small)

            # ── MP bar + numeric readout (matches party panel layout) ──
            mp_y = bar_y + bar_h + 3
            mon_mp = getattr(mon, 'current_mp', 0)
            mon_mp_max = getattr(mon, 'max_mp', 0)
            if mon_mp_max > 0:
                self._u3_draw_stat_bar(info_x, mp_y, hp_bar_w, bar_h,
                                       mon_mp, mon_mp_max, (100, 100, 255))
                mp_txt = f"{mon_mp}/{mon_mp_max}"
                self._u3_text(mp_txt, info_x + hp_bar_w + 4, mp_y - 2,
                              self._U3_WHITE, self.font_small)

            ty += 68  # row height per monster (matches party panel)

    def _u3_action_panel(self, phase, selected_action, is_adjacent,
                         x, y, w, h, active_fighter=None,
                         directing_action=None, menu_actions=None,
                         spell_list=None, spell_cursor=0,
                         selected_spell=None,
                         throw_list=None, throw_cursor=0,
                         selected_throw=None,
                         use_item_list=None, use_item_cursor=0,
                         selected_use_item=None):
        """Action menu in retro style."""
        from src.states.combat import (
            ACTION_RANGED, ACTION_CAST, ACTION_THROW, ACTION_USE_ITEM,
            PHASE_PLAYER, PHASE_PLAYER_DIR, PHASE_SPELL_SELECT,
            PHASE_THROW_SELECT, PHASE_USE_ITEM,
            PHASE_VICTORY, PHASE_DEFEAT,
            PHASE_PROJECTILE, PHASE_MELEE_ANIM, PHASE_FIREBALL, PHASE_HEAL,
            PHASE_SHIELD, PHASE_SHIELD_TARGET, PHASE_TURN_UNDEAD,
        )

        _DIR_LABELS = {
            ACTION_RANGED: "RANGE ATTACK",
            ACTION_CAST:   "CAST",
            ACTION_THROW:  "THROW",
        }
        _SPELL_DIR_LABELS = {
            "fireball": "FIREBALL",
            "heal":     "HEAL",
        }

        self._u3_panel(x, y, w, h)
        f = self.font
        tx = x + 8
        ty = y + 6

        if phase == PHASE_FIREBALL:
            self._u3_text("-- CASTING --", tx, ty, (255, 140, 30), f)
            self._u3_text("FIREBALL!", tx, ty + 24, (255, 200, 60), f)

        elif phase == PHASE_HEAL:
            self._u3_text("-- HEALING --", tx, ty, (80, 255, 80), f)
            self._u3_text("RESTORE!", tx, ty + 24, (150, 255, 150), f)

        elif phase == PHASE_SHIELD:
            self._u3_text("-- SHIELDING --", tx, ty, (100, 180, 255), f)
            self._u3_text("BARRIER!", tx, ty + 24, (150, 200, 255), f)

        elif phase == PHASE_TURN_UNDEAD:
            self._u3_text("-- HOLY POWER --", tx, ty, (255, 220, 80), f)
            self._u3_text("TURN UNDEAD!", tx, ty + 24, (255, 255, 200), f)

        elif phase == PHASE_SHIELD_TARGET:
            # Free-cursor target selection mode
            spell_name = "SHIELD"
            if selected_spell:
                from src.states.combat import SPELLS_DATA
                sd = SPELLS_DATA.get(selected_spell, {})
                spell_name = sd.get("name", "SHIELD").upper()

            self._u3_text(f"-- {spell_name} --", tx, ty, (100, 180, 255), f)
            self._u3_text("SELECT TARGET", tx, ty + 28, self._U3_WHITE, f)

            # Show visual hint
            cx = x + w // 2
            cy = ty + 76
            self._u3_text("^", cx - 4, cy - 20, self._U3_WHITE, f)
            self._u3_text("<   >", cx - 24, cy, self._U3_WHITE, f)
            self._u3_text("v", cx - 4, cy + 20, self._U3_WHITE, f)


        elif phase == PHASE_PROJECTILE:
            self._u3_text("-- FIRING --", tx, ty, self._U3_ORANGE, f)
            self._u3_text("PROJECTILE IN FLIGHT...", tx, ty + 24, self._U3_WHITE, f)

        elif phase == PHASE_MELEE_ANIM:
            self._u3_text("-- ATTACKING --", tx, ty, self._U3_ORANGE, f)
            self._u3_text("STRIKE!", tx, ty + 24, self._U3_WHITE, f)

        elif phase == PHASE_PLAYER:
            # Menu selection mode
            name = active_fighter.name if active_fighter else "???"
            self._u3_text(f"-- {name.upper()}'S TURN --", tx, ty, self._U3_ORANGE, f)

            if menu_actions:
                self._u3_scrollable_list(
                    tx, ty + 28, h - 34, f,
                    items=[(label.upper(), i == selected_action)
                           for i, (_aid, label) in enumerate(menu_actions)],
                    cursor=selected_action)


        elif phase == PHASE_SPELL_SELECT:
            # Spell selection sub-menu
            name = active_fighter.name if active_fighter else "???"
            self._u3_text(f"-- {name.upper()}'S SPELLS --", tx, ty, self._U3_ORANGE, f)

            if spell_list:
                self._u3_scrollable_list(
                    tx, ty + 28, h - 34, f,
                    items=[(label.upper(), i == spell_cursor)
                           for i, (_sid, label, _mp) in enumerate(spell_list)],
                    cursor=spell_cursor)
            else:
                self._u3_text("  NO SPELLS AVAILABLE", tx, ty + 28, (160, 160, 160), f)


        elif phase == PHASE_THROW_SELECT:
            # Throw item selection sub-menu
            name = active_fighter.name if active_fighter else "???"
            self._u3_text(f"-- THROW ITEM --", tx, ty, self._U3_ORANGE, f)

            if throw_list:
                self._u3_scrollable_list(
                    tx, ty + 28, h - 34, f,
                    items=[(f"{iname.upper()} x{cnt}", i == throw_cursor)
                           for i, (iname, cnt) in enumerate(throw_list)],
                    cursor=throw_cursor)
            else:
                self._u3_text("  NO THROWABLE ITEMS", tx, ty + 28, (160, 160, 160), f)


        elif phase == PHASE_USE_ITEM:
            # Use item selection sub-menu
            name = active_fighter.name if active_fighter else "???"
            self._u3_text(f"-- USE ITEM --", tx, ty, self._U3_ORANGE, f)

            if use_item_list:
                self._u3_scrollable_list(
                    tx, ty + 28, h - 34, f,
                    items=[(f"{iname.upper()} x{cnt}", i == use_item_cursor)
                           for i, (iname, cnt, _eff, _pow) in enumerate(use_item_list)],
                    cursor=use_item_cursor)
            else:
                self._u3_text("  NO USABLE ITEMS", tx, ty + 28, (160, 160, 160), f)


        elif phase == PHASE_PLAYER_DIR:
            # Direction selection mode — show spell/throw name if applicable
            if directing_action == ACTION_RANGED and active_fighter:
                rw = active_fighter.get_ranged_weapon()
                action_label = f"SHOOT {rw.upper()}" if rw else "RANGE ATTACK"
            elif directing_action == ACTION_CAST and selected_spell:
                action_label = _SPELL_DIR_LABELS.get(selected_spell, "CAST")
            elif directing_action == ACTION_THROW and selected_throw:
                action_label = f"THROW {selected_throw.upper()}"
            else:
                action_label = _DIR_LABELS.get(directing_action, "???")
            self._u3_text(f"-- {action_label} --", tx, ty, self._U3_ORANGE, f)
            self._u3_text("CHOOSE DIRECTION", tx, ty + 28, self._U3_WHITE, f)

            # Draw directional arrows hint
            cx = x + w // 2
            cy = ty + 80
            self._u3_text("^", cx - 4, cy - 20, self._U3_WHITE, f)
            self._u3_text("<   >", cx - 24, cy, self._U3_WHITE, f)
            self._u3_text("v", cx - 4, cy + 20, self._U3_WHITE, f)


        elif phase == PHASE_VICTORY:
            self._u3_text("** VICTORY! **", tx, ty, self._U3_GREEN, f)
            self._u3_text("RETURNING...", tx, ty + 20, self._U3_GREEN, f)

        elif phase == PHASE_DEFEAT:
            self._u3_text("** DEFEATED **", tx, ty, self._U3_RED, f)
            self._u3_text("RETREATING...", tx, ty + 20, self._U3_RED, f)

        else:
            self._u3_text("-- ENEMY TURN --", tx, ty, self._U3_RED, f)

    def _u3_log_panel(self, combat_log, x, y, w, h):
        """Combat log panel with blue border and retro text."""
        self._u3_panel(x, y, w, h)
        f = self.font

        line_h = 18
        max_lines = (h - 10) // line_h
        visible = combat_log[-max_lines:]

        for i, line in enumerate(visible):
            if "CRITICAL" in line:
                color = self._U3_ORANGE
            elif "Hit!" in line:
                color = self._U3_WHITE
            elif "Miss" in line or "Failed" in line:
                color = (180, 180, 180)
            elif "damage" in line and "deals" in line:
                color = self._U3_RED
            elif "defeated" in line or "XP" in line or "Escaped" in line:
                color = self._U3_GREEN
            elif "fallen" in line:
                color = self._U3_RED
            elif "---" in line:
                color = self._U3_ORANGE
            elif "moves closer" in line:
                color = self._U3_ORANGE
            else:
                color = self._U3_LTBLUE

            self._u3_text(line, x + 6, y + 5 + i * line_h, color, f)

    # ========================================================
    # PARTY SCREEN  –  Ultima III retro style (P key overlay)
    # ========================================================

    def draw_title_screen(self, options, cursor, elapsed, module_info=None):
        """Draw the title screen with ASCII art, menu options, and animation.

        Parameters
        ----------
        options     : list of dicts with 'label' keys
        cursor      : which option is highlighted
        elapsed     : total seconds since title screen appeared (for animations)
        module_info : optional string like "Module: Realm of Shadow v1.0.0"
        """
        import math
        self.screen.fill((0, 0, 0))

        # ── Starfield background ──
        # Twinkling dots to set atmosphere
        rng = [17, 53, 97, 131, 173, 211, 263, 307, 359, 401,
               449, 491, 541, 587, 631, 677, 719, 761, 809, 853]
        for i, seed in enumerate(rng):
            sx = (seed * 7 + i * 41) % SCREEN_WIDTH
            sy = (seed * 13 + i * 67) % (SCREEN_HEIGHT - 200)
            # Twinkle: brightness oscillates per star
            phase = elapsed * (0.5 + i * 0.15) + seed
            brightness = int(60 + 60 * math.sin(phase))
            brightness = max(20, min(140, brightness))
            c = (brightness, brightness, brightness + 30)
            self.screen.set_at((sx, sy), c)
            if i % 3 == 0:
                self.screen.set_at((sx + 1, sy), (c[0] // 2, c[1] // 2, c[2] // 2))

        # ── ASCII Art Title ──
        art = [
            r"     ____  _____    _    _     __  __",
            r"    |  _ \| ____|  / \  | |   |  \/  |",
            r"    | |_) |  _|   / _ \ | |   | |\/| |",
            r"    |  _ <| |___ / ___ \| |___| |  | |",
            r"    |_| \_\_____/_/   \_\_____|_|  |_|",
            r"",
            r"              ___  _____",
            r"             / _ \|  ___|",
            r"            | | | | |_",
            r"            | |_| |  _|",
            r"             \___/|_|",
            r"",
            r"   ____ _   _    _    ____   _____        __",
            r"  / ___| | | |  / \  |  _ \ / _ \ \      / /",
            r"  \___ \ |_| | / _ \ | | | | | | \ \ /\ / / ",
            r"   ___) |  _|/ ___ \| |_| | |_| |\ V  V /  ",
            r"  |____/|_| /_/   \_\____/ \___/  \_/\_/   ",
        ]

        # Fade in effect for the title text
        fade = min(1.0, elapsed / 2.0)

        art_y = 30
        for i, line in enumerate(art):
            # Stagger each line's fade slightly
            line_fade = min(1.0, max(0.0, fade - i * 0.03))
            r = int(200 * line_fade)
            g = int(120 * line_fade)
            b = int(50 * line_fade)
            # Glow effect: the title pulses gently
            pulse = 0.15 * math.sin(elapsed * 1.5 + i * 0.2)
            r = min(255, int(r * (1.0 + pulse)))
            g = min(255, int(g * (1.0 + pulse)))
            b = min(255, int(b * (1.0 + pulse)))
            self._u3_text(line, 180, art_y + i * 16, (r, g, b), self.font_small)

        # ── Subtitle ──
        sub_fade = min(1.0, max(0.0, (elapsed - 1.5) / 1.0))
        if sub_fade > 0:
            sub_r = int(140 * sub_fade)
            sub_g = int(140 * sub_fade)
            sub_b = int(180 * sub_fade)
            subtitle = "A Classic RPG Adventure"
            sw = len(subtitle) * 8  # approximate monospace width
            self._u3_text(subtitle,
                          SCREEN_WIDTH // 2 - sw // 2, art_y + len(art) * 16 + 12,
                          (sub_r, sub_g, sub_b), self.font_med)

        # ── Decorative separator ──
        sep_y = art_y + len(art) * 16 + 40
        sep_fade = min(1.0, max(0.0, (elapsed - 2.0) / 0.5))
        if sep_fade > 0:
            sep_color = (int(80 * sep_fade), int(60 * sep_fade), int(40 * sep_fade))
            sep_text = "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~"
            sw = len(sep_text) * 5
            self._u3_text(sep_text,
                          SCREEN_WIDTH // 2 - sw // 2, sep_y,
                          sep_color, self.font_small)

        # ── Menu options ──
        menu_y = sep_y + 35
        menu_fade = min(1.0, max(0.0, (elapsed - 2.5) / 1.0))
        if menu_fade > 0:
            # Panel behind menu (extra height for module info + hint text)
            panel_w = 320
            panel_h = 30 + len(options) * 40 + 55
            panel_x = (SCREEN_WIDTH - panel_w) // 2
            panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel_surf.fill((20, 15, 30, int(180 * menu_fade)))
            self.screen.blit(panel_surf, (panel_x, menu_y - 10))

            # Border
            border_alpha = int(120 * menu_fade)
            pygame.draw.rect(self.screen,
                             (100, 70, 40, border_alpha),
                             (panel_x, menu_y - 10, panel_w, panel_h), 1)

            for i, opt in enumerate(options):
                y = menu_y + 10 + i * 40
                selected = (i == cursor)

                if selected:
                    # Animated cursor arrow
                    arrow_offset = int(3 * math.sin(elapsed * 4.0))
                    arrow_x = panel_x + 16 + arrow_offset
                    ar = int(255 * menu_fade)
                    ag = int(200 * menu_fade)
                    ab = int(60 * menu_fade)
                    self._u3_text(">", arrow_x, y, (ar, ag, ab), self.font)

                    # Highlighted label
                    lr = int(255 * menu_fade)
                    lg = int(255 * menu_fade)
                    lb = int(100 * menu_fade)
                    self._u3_text(opt["label"], panel_x + 40, y,
                                  (lr, lg, lb), self.font)

                    # Selection highlight bar
                    bar = pygame.Surface((panel_w - 12, 24), pygame.SRCALPHA)
                    bar.fill((255, 200, 60, int(25 * menu_fade)))
                    self.screen.blit(bar, (panel_x + 6, y - 2))
                else:
                    cr = int(160 * menu_fade)
                    cg = int(160 * menu_fade)
                    cb = int(160 * menu_fade)
                    self._u3_text(opt["label"], panel_x + 40, y,
                                  (cr, cg, cb), self.font)

        # ── Bottom info inside the menu panel ──
        hint_fade = min(1.0, max(0.0, (elapsed - 3.0) / 1.0))
        if hint_fade > 0 and menu_fade > 0:
            # Position inside the panel, below the last menu option
            info_y = menu_y + 10 + len(options) * 40 + 4

            # Active module indicator — bright gold
            if module_info:
                mod_color = (int(200 * hint_fade), int(170 * hint_fade),
                             int(80 * hint_fade))
                mw, _ = self.font_med.size(module_info.upper())
                self._u3_text(module_info,
                              panel_x + (panel_w - mw) // 2,
                              info_y,
                              mod_color, self.font_med)
                info_y += 22

            # Hint text — bright blue
            hint_color = (int(100 * hint_fade), int(100 * hint_fade),
                          int(255 * hint_fade))
            hint = "[UP/DOWN] Select  [ENTER] Choose"
            hint_w, _ = self.font_med.size(hint.upper())
            self._u3_text(hint,
                          panel_x + (panel_w - hint_w) // 2,
                          info_y,
                          hint_color, self.font_med)

        # ── Copyright / credits (below the panel) ──
        if hint_fade > 0:
            cr_color = (int(60 * hint_fade), int(60 * hint_fade),
                        int(80 * hint_fade))
            credit = "Realm of Shadow  (c) 2026"
            cw = len(credit) * 5
            self._u3_text(credit,
                          SCREEN_WIDTH // 2 - cw // 2,
                          SCREEN_HEIGHT - 28,
                          cr_color, self.font_small)

    def draw_module_screen(self, modules, cursor, active_path):
        """Draw the module selection / browser screen.

        Parameters
        ----------
        modules     : list of module info dicts (id, name, author, description, version, path)
        cursor      : which module is highlighted
        active_path : path of the currently active module (for checkmark indicator)
        """
        import math
        self.screen.fill((0, 0, 0))

        fm = self.font_med
        f = self.font
        fs = self.font_small

        # ── Header ──
        self._u3_text("MODULES", SCREEN_WIDTH // 2 - 40, 20, self._U3_ORANGE, f)
        pygame.draw.line(self.screen, (80, 60, 40),
                         (80, 50), (SCREEN_WIDTH - 80, 50), 1)

        if not modules:
            self._u3_text("No modules found in modules/ directory.",
                          SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2,
                          (180, 100, 100), fm)
            self._u3_text("[ESC] Back",
                          SCREEN_WIDTH // 2 - 40, SCREEN_HEIGHT - 50,
                          (100, 100, 200), fs)
            return

        # ── Layout: left panel (module list) + right panel (detail) ──
        left_x = 40
        left_w = 320
        right_x = left_x + left_w + 30
        right_w = SCREEN_WIDTH - right_x - 40
        panel_y = 65
        panel_h = SCREEN_HEIGHT - 130

        # Left panel background
        left_surf = pygame.Surface((left_w, panel_h), pygame.SRCALPHA)
        left_surf.fill((20, 15, 30, 180))
        self.screen.blit(left_surf, (left_x, panel_y))
        pygame.draw.rect(self.screen, (80, 60, 40),
                         (left_x, panel_y, left_w, panel_h), 1)

        # Right panel background
        right_surf = pygame.Surface((right_w, panel_h), pygame.SRCALPHA)
        right_surf.fill((20, 15, 30, 180))
        self.screen.blit(right_surf, (right_x, panel_y))
        pygame.draw.rect(self.screen, (80, 60, 40),
                         (right_x, panel_y, right_w, panel_h), 1)

        # ── Module list (left panel) ──
        self._u3_text("AVAILABLE", left_x + 12, panel_y + 8,
                      self._U3_ORANGE, fs)
        row_h = 36
        list_y = panel_y + 30

        # Scrolling
        max_visible = (panel_h - 40) // row_h
        scroll_top = 0
        if len(modules) > max_visible:
            scroll_top = max(0, min(cursor - max_visible // 2,
                                    len(modules) - max_visible))

        for vi, mi in enumerate(range(scroll_top,
                                      min(scroll_top + max_visible,
                                          len(modules)))):
            mod = modules[mi]
            y = list_y + vi * row_h
            selected = (mi == cursor)
            is_active = (mod["path"] == active_path)

            # Selection highlight bar
            if selected:
                bar = pygame.Surface((left_w - 4, row_h - 4), pygame.SRCALPHA)
                bar.fill((255, 200, 60, 30))
                self.screen.blit(bar, (left_x + 2, y - 2))

            # Cursor arrow
            prefix = "> " if selected else "  "
            name_color = self._U3_WHITE if selected else (180, 180, 180)

            # Active module gets a green checkmark
            marker = ""
            if is_active:
                marker = " *"

            self._u3_text(f"{prefix}{mod['name']}{marker}",
                          left_x + 10, y, name_color, fm)

            # Version in small text
            ver_color = (100, 100, 120) if not selected else (140, 140, 160)
            self._u3_text(f"v{mod['version']}", left_x + 10, y + 18,
                          ver_color, fs)

        # Scroll indicators
        if scroll_top > 0:
            self._u3_text("^", left_x + left_w // 2 - 4, list_y - 8,
                          (120, 120, 140), fs)
        if scroll_top + max_visible < len(modules):
            self._u3_text("v", left_x + left_w // 2 - 4,
                          list_y + max_visible * row_h - 4,
                          (120, 120, 140), fs)

        # ── Detail panel (right) ──
        if 0 <= cursor < len(modules):
            mod = modules[cursor]
            dy = panel_y + 12

            # Module name
            self._u3_text(mod["name"], right_x + 16, dy, self._U3_WHITE, f)
            dy += 28

            # Author
            self._u3_text(f"by {mod['author']}", right_x + 16, dy,
                          (160, 160, 180), fm)
            dy += 22

            # Version
            self._u3_text(f"Version {mod['version']}", right_x + 16, dy,
                          (120, 120, 140), fs)
            dy += 22

            # Active status
            if mod["path"] == active_path:
                self._u3_text("ACTIVE", right_x + 16, dy,
                              self._U3_GREEN, fm)
            else:
                self._u3_text("NOT SELECTED", right_x + 16, dy,
                              (120, 100, 80), fm)
            dy += 28

            # Separator
            pygame.draw.line(self.screen, (60, 50, 40),
                             (right_x + 16, dy),
                             (right_x + right_w - 16, dy), 1)
            dy += 14

            # Description — pixel-accurate word wrap within panel
            desc = mod.get("description", "")
            max_pixel_w = right_w - 36  # 16px padding each side + margin
            desc_bottom = panel_y + panel_h - 40  # leave room for ID
            if desc:
                words = desc.split()
                line = ""
                for word in words:
                    test = f"{line} {word}".strip()
                    tw, _ = fm.size(test.upper())
                    if tw > max_pixel_w and line:
                        if dy < desc_bottom:
                            self._u3_text(line, right_x + 16, dy,
                                          (180, 180, 200), fm)
                        dy += 18
                        line = word
                    else:
                        line = test
                if line and dy < desc_bottom:
                    self._u3_text(line, right_x + 16, dy,
                                  (180, 180, 200), fm)
                    dy += 18

            # Module ID (for debugging / reference)
            id_y = max(dy + 16, panel_y + panel_h - 28)
            self._u3_text(f"ID: {mod['id']}", right_x + 16, id_y,
                          (80, 80, 100), fs)

        # ── Footer hints ──
        hint_y = SCREEN_HEIGHT - 45
        hint_color = (68, 68, 200)
        self._u3_text("[UP/DOWN] Browse   [ENTER] Select   [ESC] Back",
                      SCREEN_WIDTH // 2 - 180, hint_y, hint_color, fs)

    def draw_game_over_screen(self, options, cursor, elapsed):
        """Draw a grim game-over screen with skull art and menu options.

        Parameters
        ----------
        options : list of dicts with 'label' keys
        cursor  : which option is highlighted
        elapsed : total seconds since game over screen appeared
        """
        import math
        self.screen.fill((0, 0, 0))

        # ── Blood-red fog particles ──
        rng = [23, 59, 101, 149, 191, 233, 277, 311, 367, 409,
               457, 499, 547, 593, 641, 683, 727, 769, 811, 859]
        for i, seed in enumerate(rng):
            px = (seed * 11 + i * 37) % SCREEN_WIDTH
            py = (seed * 7 + i * 53) % SCREEN_HEIGHT
            # Slow drift
            drift = math.sin(elapsed * 0.3 + seed * 0.1) * 20
            px = int(px + drift) % SCREEN_WIDTH
            phase = elapsed * (0.2 + i * 0.08) + seed
            brightness = int(20 + 15 * math.sin(phase))
            brightness = max(5, min(40, brightness))
            self.screen.set_at((px, py), (brightness, 0, 0))
            if i % 2 == 0:
                self.screen.set_at(
                    ((px + 1) % SCREEN_WIDTH, py),
                    (brightness // 2, 0, 0))

        # ── Skull ASCII Art ──
        skull = [
            "            ______",
            "         .-'      '-.",
            "        /            \\",
            "       |              |",
            "       |,  .-.  .-.  ,|",
            "       | )(_o/  \\o_)( |",
            "       |/     /\\     \\|",
            "       (_     ^^     _)",
            "        \\__|IIIIII|__/",
            "         | \\IIIIII/ |",
            "         \\          /",
            "          '--------'",
        ]

        # Fade in the skull over 1.5 seconds
        skull_fade = min(1.0, elapsed / 1.5)
        skull_y = 60
        for i, line in enumerate(skull):
            line_fade = min(1.0, max(0.0, skull_fade - i * 0.04))
            r = int(140 * line_fade)
            g = int(20 * line_fade)
            b = int(20 * line_fade)
            # Subtle red pulse
            pulse = 0.12 * math.sin(elapsed * 1.2 + i * 0.3)
            r = min(255, int(r * (1.0 + pulse)))
            sw = len(line) * 7
            self._u3_text(line,
                          SCREEN_WIDTH // 2 - sw // 2, skull_y + i * 16,
                          (r, g, b), self.font)

        # ── "GAME OVER" text ──
        go_fade = min(1.0, max(0.0, (elapsed - 1.0) / 1.0))
        if go_fade > 0:
            go_text = "G A M E   O V E R"
            pulse = 0.2 * math.sin(elapsed * 2.0)
            gr = min(255, int((200 + 55 * pulse) * go_fade))
            gg = int(30 * go_fade)
            gb = int(30 * go_fade)
            gw = len(go_text) * 9
            self._u3_text(go_text,
                          SCREEN_WIDTH // 2 - gw // 2,
                          skull_y + len(skull) * 16 + 25,
                          (gr, gg, gb), self.font)

        # ── Epitaph text ──
        ep_fade = min(1.0, max(0.0, (elapsed - 1.8) / 1.0))
        if ep_fade > 0:
            epitaph = "Your journey ends here... but perhaps not forever."
            ec = int(100 * ep_fade)
            ew = len(epitaph) * 6
            self._u3_text(epitaph,
                          SCREEN_WIDTH // 2 - ew // 2,
                          skull_y + len(skull) * 16 + 55,
                          (ec, max(0, ec - 20), max(0, ec - 10)),
                          self.font_med)

        # ── Separator ──
        sep_fade = min(1.0, max(0.0, (elapsed - 2.0) / 0.5))
        sep_y = skull_y + len(skull) * 16 + 85
        if sep_fade > 0:
            sep_color = (int(60 * sep_fade), int(15 * sep_fade),
                         int(15 * sep_fade))
            sep_text = "~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~"
            sw = len(sep_text) * 5
            self._u3_text(sep_text,
                          SCREEN_WIDTH // 2 - sw // 2, sep_y,
                          sep_color, self.font_small)

        # ── Menu options ──
        menu_y = sep_y + 30
        menu_fade = min(1.0, max(0.0, (elapsed - 2.0) / 1.0))
        if menu_fade > 0:
            # Dark panel behind menu
            panel_w = 320
            panel_h = 30 + len(options) * 40 + 20
            panel_x = (SCREEN_WIDTH - panel_w) // 2
            panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel_surf.fill((30, 5, 5, int(180 * menu_fade)))
            self.screen.blit(panel_surf, (panel_x, menu_y - 10))

            # Blood-red border
            border_alpha = int(120 * menu_fade)
            pygame.draw.rect(self.screen,
                             (120, 20, 20, border_alpha),
                             (panel_x, menu_y - 10, panel_w, panel_h), 1)

            for i, opt in enumerate(options):
                y = menu_y + 10 + i * 40
                selected = (i == cursor)

                if selected:
                    # Animated cursor
                    arrow_offset = int(3 * math.sin(elapsed * 4.0))
                    arrow_x = panel_x + 16 + arrow_offset
                    ar = int(255 * menu_fade)
                    ag = int(80 * menu_fade)
                    ab = int(60 * menu_fade)
                    self._u3_text(">", arrow_x, y, (ar, ag, ab), self.font)

                    # Highlighted label
                    self._u3_text(opt["label"], panel_x + 40, y,
                                  (int(255 * menu_fade), int(200 * menu_fade),
                                   int(100 * menu_fade)), self.font)

                    # Red selection bar
                    bar = pygame.Surface((panel_w - 12, 24), pygame.SRCALPHA)
                    bar.fill((200, 40, 40, int(25 * menu_fade)))
                    self.screen.blit(bar, (panel_x + 6, y - 2))
                else:
                    c = int(140 * menu_fade)
                    self._u3_text(opt["label"], panel_x + 40, y,
                                  (c, max(0, c - 20), max(0, c - 20)),
                                  self.font)

        # ── Bottom hint ──
        hint_fade = min(1.0, max(0.0, (elapsed - 2.5) / 1.0))
        if hint_fade > 0:
            hint_color = (int(60 * hint_fade), int(30 * hint_fade),
                          int(30 * hint_fade))
            hint = "[UP/DOWN] SELECT   [ENTER] CHOOSE"
            hw = len(hint) * 5
            self._u3_text(hint,
                          SCREEN_WIDTH // 2 - hw // 2,
                          SCREEN_HEIGHT - 50,
                          hint_color, self.font_small)

    def draw_settings_screen(self, settings, cursor):
        """Draw a full-screen settings overlay in Ultima III style.

        settings: list of dicts with keys 'label', 'value', 'type'
                  type is 'toggle' (on/off)
        cursor:   which row is selected
        """
        self.screen.fill((0, 0, 0))

        # Title bar
        self._u3_panel(0, 0, SCREEN_WIDTH, 30)
        self._u3_text("SETTINGS", SCREEN_WIDTH // 2 - 40, 8,
                       (255, 170, 85), self.font)

        # Settings panel
        panel_w = 400
        panel_h = 40 + len(settings) * 40 + 50
        panel_x = (SCREEN_WIDTH - panel_w) // 2
        panel_y = 60

        self._u3_panel(panel_x, panel_y, panel_w, panel_h)

        for i, setting in enumerate(settings):
            y = panel_y + 20 + i * 40
            selected = (i == cursor)
            label_color = (255, 255, 0) if selected else (200, 200, 200)
            prefix = "> " if selected else "  "

            # Label
            self._u3_text(f"{prefix}{setting['label']}",
                          panel_x + 16, y, label_color, self.font)

            # Value
            if setting['type'] == 'toggle':
                val_text = "ON" if setting['value'] else "OFF"
                val_color = (0, 200, 0) if setting['value'] else (200, 60, 60)
                # Draw a toggle indicator
                tx = panel_x + panel_w - 80
                self._u3_text(f"[ {val_text} ]", tx, y, val_color, self.font)

            # Value for action type
            if setting['type'] == 'action':
                # Draw a right arrow to indicate sub-screen
                tx = panel_x + panel_w - 80
                self._u3_text(">>>", tx, y,
                              (255, 255, 0) if selected else (100, 100, 100),
                              self.font)

        # Controls hint
        hint_y = panel_y + panel_h - 30
        self._u3_text("[UP/DOWN] SELECT   [ENTER] CHOOSE   [M/ESC] CLOSE",
                      panel_x + 16, hint_y, (68, 68, 255), self.font_small)

    def draw_save_load_screen(self, mode, slot_infos, cursor, message=None):
        """Draw the save/load slot picker screen.

        Parameters
        ----------
        mode : str
            "save" or "load"
        slot_infos : list
            List of save-info dicts (or None for empty slots).
        cursor : int
            Which slot is currently selected (0-based).
        message : str or None
            Feedback message to display (e.g. "Game saved!").
        """
        import time as _time
        self.screen.fill((0, 0, 0))

        title = "SAVE GAME" if mode == "save" else "LOAD GAME"

        # Title bar
        self._u3_panel(0, 0, SCREEN_WIDTH, 30)
        self._u3_text(title, SCREEN_WIDTH // 2 - len(title) * 5, 8,
                       (255, 170, 85), self.font)

        # Slot panel
        panel_w = 500
        slot_h = 70
        panel_h = 40 + len(slot_infos) * (slot_h + 8) + 60
        panel_x = (SCREEN_WIDTH - panel_w) // 2
        panel_y = 60

        self._u3_panel(panel_x, panel_y, panel_w, panel_h)

        for i, info in enumerate(slot_infos):
            y = panel_y + 20 + i * (slot_h + 8)
            selected = (i == cursor)

            # Slot background highlight
            if selected:
                highlight = pygame.Surface((panel_w - 20, slot_h), pygame.SRCALPHA)
                highlight.fill((60, 60, 120, 80))
                self.screen.blit(highlight, (panel_x + 10, y))

            # Slot border
            border_color = (255, 255, 0) if selected else (80, 80, 100)
            pygame.draw.rect(self.screen, border_color,
                             (panel_x + 10, y, panel_w - 20, slot_h), 1)

            prefix = "> " if selected else "  "
            slot_num = i + 1

            if info is None:
                # Empty slot
                self._u3_text(f"{prefix}SLOT {slot_num}  -  EMPTY",
                              panel_x + 20, y + 10,
                              (120, 120, 120), self.font)
                if mode == "save":
                    self._u3_text("(New save)",
                                  panel_x + 20, y + 35,
                                  (80, 80, 80), self.font_small)
            else:
                # Filled slot
                names = ", ".join(info.get("party_names", []))
                gold = info.get("gold", 0)
                avg_lv = info.get("level_avg", 1)
                ts = info.get("timestamp", 0)

                # Format timestamp
                try:
                    dt_str = _time.strftime("%b %d %Y  %H:%M",
                                           _time.localtime(ts))
                except Exception:
                    dt_str = "Unknown date"

                label_color = (255, 255, 0) if selected else (200, 200, 200)
                self._u3_text(f"{prefix}SLOT {slot_num}",
                              panel_x + 20, y + 6, label_color, self.font)

                # Date on the right
                self._u3_text(dt_str, panel_x + panel_w - 200, y + 6,
                              (150, 150, 200), self.font_small)

                # Party names
                self._u3_text(names, panel_x + 30, y + 28,
                              (180, 200, 255), self.font_med)

                # Gold and level
                self._u3_text(f"Gold: {gold}   Avg Lv: {avg_lv:.0f}",
                              panel_x + 30, y + 48,
                              (200, 180, 100), self.font_small)

        # Feedback message
        if message:
            msg_y = panel_y + panel_h - 55
            self._u3_text(message,
                          SCREEN_WIDTH // 2 - len(message) * 5, msg_y,
                          (100, 255, 100), self.font)

        # Controls hint
        hint_y = panel_y + panel_h - 30
        action_word = "SAVE" if mode == "save" else "LOAD"
        self._u3_text(
            f"[UP/DOWN] SELECT   [ENTER] {action_word}   [ESC] BACK",
            panel_x + 16, hint_y, (68, 68, 255), self.font_small)

    def draw_party_screen_u3(self, party):
        """
        Full-screen party status overlay in Ultima III style.

        Shows detailed stats for all 4 members plus party-wide info.
        """
        from src.party import WEAPONS, ARMORS

        self.screen.fill(self._U3_BLACK)

        # Title bar
        self._u3_panel(0, 0, SCREEN_WIDTH, 30)
        self._u3_text("PARTY STATUS", SCREEN_WIDTH // 2 - 60, 8,
                       self._U3_ORANGE, self.font)

        # Four character cards, 2x2 grid
        card_w = SCREEN_WIDTH // 2 - 8
        card_h = 274
        positions = [
            (4, 36),
            (SCREEN_WIDTH // 2 + 4, 36),
            (4, 36 + card_h + 4),
            (SCREEN_WIDTH // 2 + 4, 36 + card_h + 4),
        ]

        for i, member in enumerate(party.members):
            cx, cy = positions[i]
            self._u3_panel(cx, cy, card_w, card_h)
            tx = cx + 10
            ty = cy + 8

            # Character sprite on the right side of the card
            sprite = self._get_member_sprite(member, big=True)
            if sprite:
                sx = cx + card_w - sprite.get_width() - 10
                sy = cy + (card_h - sprite.get_height()) // 2
                if not member.is_alive():
                    # Dim the sprite for dead members
                    dark = sprite.copy()
                    dark.fill((80, 80, 80), special_flags=pygame.BLEND_RGB_MULT)
                    self.screen.blit(dark, (sx, sy))
                else:
                    self.screen.blit(sprite, (sx, sy))

            # Number, name, class
            alive_color = self._U3_ORANGE if member.is_alive() else self._U3_RED
            self._u3_text(f"{i+1}", tx, ty, self._U3_BLUE, self.font)
            self._u3_text(member.name, tx + 22, ty, alive_color, self.font)
            cls_label = f"{member.char_class}"
            self._u3_text(cls_label, tx + 190, ty, self._U3_BLUE, self.font)

            # Race
            fm = self.font_med
            ty += 22
            self._u3_text("RACE:", tx, ty, self._U3_LTBLUE, fm)
            self._u3_text(f"{member.race}", tx + 58, ty, self._U3_WHITE, fm)

            # HP bar + text
            ty += 20
            hp_color = self._U3_GREEN if member.hp > member.max_hp * 0.3 else self._U3_RED
            self._u3_text("HP:", tx, ty, (220, 220, 230), fm)
            bar_x = tx + 30
            bar_w = 120
            bar_h = 12
            self._u3_draw_stat_bar(bar_x, ty + 1, bar_w, bar_h,
                                   member.hp, member.max_hp, hp_color)
            self._u3_text(
                f"{member.hp:d}/{member.max_hp:d}",
                bar_x + bar_w + 6, ty, self._U3_WHITE, fm)

            # MP bar + text
            ty += 18
            mp_color = (100, 100, 255)
            self._u3_text("MP:", tx, ty, (220, 220, 230), fm)
            if member.max_mp > 0:
                self._u3_draw_stat_bar(bar_x, ty + 1, bar_w, bar_h,
                                       member.current_mp, member.max_mp, mp_color)
                self._u3_text(
                    f"{member.current_mp:d}/{member.max_mp:d}",
                    bar_x + bar_w + 6, ty, self._U3_WHITE, fm)
            else:
                self._u3_text("----/----", bar_x + bar_w + 6, ty, (120, 120, 120), fm)

            # Stats
            ty += 20
            self._u3_text(
                f"STR:{member.strength:d}  DEX:{member.dexterity:d}  "
                f"INT:{member.intelligence:d}  WIS:{member.wisdom:d}",
                tx, ty, self._U3_LTBLUE, fm)

            # Level / EXP
            ty += 20
            self._u3_text(
                f"LVL:{member.level:d}  EXP:{member.exp:d}/{member.xp_for_next_level:d}  AC:{member.get_ac():d}",
                tx, ty, self._U3_WHITE, fm)

            # Weapon info
            ty += 22
            wp = WEAPONS.get(member.weapon, {"power": 0, "ranged": False})
            rng = "RANGED" if wp["ranged"] else "MELEE"
            ammo_str = f"  x{member.get_ammo()}" if member.is_throwable_weapon() else ""
            self._u3_text("WPN:", tx, ty, self._U3_LTBLUE, fm)
            self._u3_text(
                f"{member.weapon}  (PWR:{wp['power']:d} {rng}){ammo_str}",
                tx + 50, ty, (230, 230, 240), fm)

            # Armor info
            ty += 20
            arm = ARMORS.get(member.armor, {"evasion": 50})
            self._u3_text("ARM:", tx, ty, self._U3_LTBLUE, fm)
            self._u3_text(
                f"{member.armor}  (EVD:{arm['evasion']}%)",
                tx + 50, ty, (230, 230, 240), fm)

            # Magic type
            ty += 20
            magic_types = []
            if member.can_cast_priest():
                magic_types.append("PRIEST")
            if member.can_cast_sorcerer():
                magic_types.append("SORCERER")
            if magic_types:
                self._u3_text("MAGIC:", tx, ty, self._U3_LTBLUE, fm)
                self._u3_text(
                    f"{' + '.join(magic_types)}",
                    tx + 68, ty, (180, 180, 255), fm)
            else:
                self._u3_text("MAGIC:", tx, ty, self._U3_LTBLUE, fm)
                self._u3_text("NONE", tx + 68, ty, (150, 150, 150), fm)

            # Damage estimate
            ty += 20
            dmg = member.get_damage()
            self._u3_text("EST DMG:", tx, ty, self._U3_LTBLUE, fm)
            self._u3_text(f"{dmg:d}", tx + 88, ty, self._U3_WHITE, fm)

            # Status
            ty += 20
            status = "ALIVE" if member.is_alive() else "DEAD"
            sc = self._U3_GREEN if member.is_alive() else self._U3_RED
            self._u3_text(f"STATUS: {status}", tx, ty, sc, fm)

        # Bottom info bar
        info_y = 36 + card_h * 2 + 12
        info_h = SCREEN_HEIGHT - info_y - 28
        if info_h > 10:
            self._u3_panel(4, info_y, SCREEN_WIDTH - 8, info_h)
            self._u3_text(f"GOLD: {party.gold:d}", 14, info_y + 6,
                          (255, 255, 0))
            alive = len(party.alive_members())
            self._u3_text(f"ALIVE: {alive}/4", 200, info_y + 6,
                          self._U3_WHITE)

        # Bottom status bar
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        self._u3_text("[1-4] DETAIL    [5] STASH    [P] CLOSE    [ESC] CLOSE",
                      8, bar_y + 5, self._U3_BLUE)

    def draw_character_sheet_u3(self, member, index, cursor_index=0,
                                action_menu=False, action_cursor=0,
                                action_options=None):
        """
        Full-screen detailed character sheet for a single party member.

        Shows large sprite, all stats with modifiers, interactive equipment
        and inventory list with cursor navigation.

        cursor_index: selected row in the unified equip+inventory list (0-based).
        action_menu: if True, show an action popup over the selected item.
        action_cursor: which option is highlighted in the action popup.
        """
        from src.party import WEAPONS, ARMORS
        from src.combat_engine import format_modifier

        fm = self.font_med
        f = self.font
        self.screen.fill(self._U3_BLACK)

        # ── Title bar ──
        self._u3_panel(0, 0, SCREEN_WIDTH, 30)
        title = f"CHARACTER {index + 1}: {member.name.upper()}"
        self._u3_text(title, SCREEN_WIDTH // 2 - len(title) * 5, 8,
                       self._U3_ORANGE, f)

        # ── Main content area: left panel + right panel ──
        left_x = 4
        left_w = SCREEN_WIDTH // 2 - 6
        right_x = SCREEN_WIDTH // 2 + 2
        right_w = SCREEN_WIDTH // 2 - 6
        panel_y = 36
        panel_h = SCREEN_HEIGHT - 36 - 28

        self._u3_panel(left_x, panel_y, left_w, panel_h)
        self._u3_panel(right_x, panel_y, right_w, panel_h)

        # ═══════════════════════════════════════════════
        # LEFT PANEL — Identity, sprite, core stats
        # ═══════════════════════════════════════════════
        tx = left_x + 12
        ty = panel_y + 10

        # Large sprite
        sprite = self._get_member_sprite(member, big=True)
        if sprite:
            sx = left_x + left_w - sprite.get_width() - 14
            sy = ty
            if not member.is_alive():
                dark = sprite.copy()
                dark.fill((80, 80, 80), special_flags=pygame.BLEND_RGB_MULT)
                self.screen.blit(dark, (sx, sy))
            else:
                self.screen.blit(sprite, (sx, sy))

        # Name and class
        self._u3_text(member.name, tx, ty, self._U3_ORANGE, f)
        ty += 22
        self._u3_text(f"{member.char_class}", tx, ty, self._U3_WHITE, f)
        ty += 22
        self._u3_text("RACE:", tx, ty, self._U3_LTBLUE, fm)
        self._u3_text(f"{member.race}", tx + 58, ty, self._U3_WHITE, fm)
        gender_str = getattr(member, 'gender', 'Unknown')
        self._u3_text(f"  {gender_str}", tx + 58 + fm.size(member.race.upper())[0], ty,
                      (180, 180, 200), fm)
        ty += 20
        self._u3_text(f"LEVEL: {member.level:d}", tx, ty, self._U3_WHITE, fm)
        self._u3_text(f"EXP: {member.exp:d}/{member.xp_for_next_level:d}",
                      tx + 120, ty, (220, 220, 230), fm)

        # ── HP bar ──
        ty += 28
        hp_color = self._U3_GREEN if member.hp > member.max_hp * 0.3 else self._U3_RED
        self._u3_text("HIT POINTS", tx, ty, self._U3_LTBLUE, fm)
        ty += 18
        bar_w = left_w - 28
        bar_h = 14
        self._u3_draw_stat_bar(tx, ty, bar_w, bar_h,
                               member.hp, member.max_hp, hp_color)
        ty += bar_h + 2
        self._u3_text(
            f"{member.hp:d} / {member.max_hp:d}",
            tx, ty, self._U3_WHITE, fm)

        # ── MP bar ──
        ty += 22
        self._u3_text("MAGIC POINTS", tx, ty, self._U3_LTBLUE, fm)
        ty += 18
        if member.max_mp > 0:
            self._u3_draw_stat_bar(tx, ty, bar_w, bar_h,
                                   member.current_mp, member.max_mp, (100, 100, 255))
            ty += bar_h + 2
            self._u3_text(
                f"{member.current_mp:d} / {member.max_mp:d}",
                tx, ty, self._U3_WHITE, fm)
        else:
            self._u3_draw_stat_bar(tx, ty, bar_w, bar_h, 0, 1, (60, 60, 60))
            ty += bar_h + 2
            self._u3_text("---- / ----", tx, ty, (120, 120, 120), fm)

        # ── Attributes with modifiers ──
        ty += 24
        self._u3_text("ATTRIBUTES", tx, ty, self._U3_ORANGE, fm)
        ty += 20
        attrs = [
            ("STR", member.strength, member.str_mod),
            ("DEX", member.dexterity, member.dex_mod),
            ("INT", member.intelligence, member.int_mod),
            ("WIS", member.wisdom, member.wis_mod),
        ]
        for label, val, mod in attrs:
            mod_str = format_modifier(mod)
            self._u3_text(f"{label}:", tx, ty, self._U3_LTBLUE, fm)
            self._u3_text(f"{val:d}", tx + 42, ty, self._U3_WHITE, fm)
            mod_color = self._U3_GREEN if mod > 0 else self._U3_RED if mod < 0 else (180, 180, 180)
            self._u3_text(f"({mod_str})", tx + 68, ty, mod_color, fm)
            ty += 18

        # ── Status ──
        ty += 8
        status = "ALIVE" if member.is_alive() else "DEAD"
        sc = self._U3_GREEN if member.is_alive() else self._U3_RED
        self._u3_text("STATUS:", tx, ty, self._U3_LTBLUE, fm)
        self._u3_text(status, tx + 78, ty, sc, fm)

        # ── Racial Traits / Effects ──
        ty += 26
        # Collect racial effects from races.json and match against
        # effects.json for descriptions; also show innate racial traits
        # that aren't in the party-effect system.
        from src.party import EFFECTS_DATA
        racial_fx = member.racial_effects  # list of effect id strings
        panel_bottom = panel_y + panel_h - 8
        desc_max_w = left_w - 28  # max pixel width for description text
        if racial_fx:
            self._u3_text("TRAITS", tx, ty, self._U3_ORANGE, fm)
            ty += 20
            # Build lookup from effects.json for descriptions
            eff_lookup = {e["id"]: e for e in EFFECTS_DATA}
            # Fallback descriptions for racial traits not in effects.json
            _trait_desc = {
                "infravision": "Dwarven eyes pierce the darkness.",
                "pickpocket": "Nimble fingers can pilfer from NPCs.",
                "tinker": "Knack for tinkering with mechanisms.",
                "galadriel_light": "Elven starlight illuminates the dark.",
                "detect_traps": "Keen senses reveal hidden traps.",
            }
            fs = self.font_small
            for fx_id in racial_fx:
                if ty + 15 > panel_bottom:
                    break
                eff = eff_lookup.get(fx_id)
                if eff:
                    fx_name = eff["name"]
                    fx_desc = eff.get("description", "")
                else:
                    fx_name = fx_id.replace("_", " ").title()
                    fx_desc = _trait_desc.get(fx_id, "")
                self._u3_text(fx_name, tx, ty, (220, 200, 140), fm)
                ty += 15
                if fx_desc:
                    # Word-wrap description to fit within the panel
                    words = fx_desc.upper().split()
                    line = ""
                    for word in words:
                        test = (line + " " + word).strip()
                        tw, _ = fs.size(test)
                        if tw > desc_max_w and line:
                            if ty + 14 > panel_bottom:
                                break
                            self._u3_text(line, tx + 8, ty, (140, 140, 160), fs)
                            ty += 14
                            line = word
                        else:
                            line = test
                    if line and ty + 14 <= panel_bottom:
                        self._u3_text(line, tx + 8, ty, (140, 140, 160), fs)
                        ty += 16

        # ── Available Spells ──
        ty += 6
        from src.party import SPELLS_DATA
        char_class = member.char_class
        char_level = member.level
        available = [s for s in SPELLS_DATA.values()
                     if char_class in s.get("allowable_classes", [])
                     and char_level >= s.get("min_level", 1)]
        if available:
            self._u3_text("SPELLS", tx, ty, self._U3_ORANGE, fm)
            ty += 20
            # Sort by mp_cost then name
            available.sort(key=lambda s: (s.get("mp_cost", 0), s["name"]))
            spell_bottom = panel_y + panel_h - 8
            for spell in available:
                if ty + 16 > spell_bottom:
                    self._u3_text("...", tx, ty, (120, 120, 140), fm)
                    break
                sname = spell["name"]
                mp_cost = spell.get("mp_cost", 0)
                castable = member.current_mp >= mp_cost
                name_col = (180, 180, 255) if castable else (100, 100, 120)
                cost_col = (140, 200, 140) if castable else (100, 100, 120)
                self._u3_text(sname, tx, ty, name_col, fm)
                cost_str = f"{mp_cost} MP"
                self._u3_text(cost_str, tx + left_w - 80, ty, cost_col, fm)
                ty += 16
        else:
            self._u3_text("SPELLS", tx, ty, self._U3_ORANGE, fm)
            ty += 20
            self._u3_text("-- NONE --", tx, ty, (120, 120, 120), fm)

        # ═══════════════════════════════════════════════
        # RIGHT PANEL — Interactive equip/inventory list
        # ═══════════════════════════════════════════════
        rx = right_x + 12
        ry = panel_y + 10
        row_h = 20   # height per selectable row

        eq = getattr(member, 'equipped', {})
        inv = getattr(member, 'inventory', [])

        # Build the unified list: 4 equipped slots + inventory items
        # Each entry: (label, item_name, is_equipped, slot_key_or_None)
        from src.party import PartyMember
        _slots = PartyMember._EQUIP_SLOTS
        _labels = PartyMember._SLOT_LABELS

        unified = []
        for sk in _slots:
            item = eq.get(sk)
            unified.append((_labels[sk], item, True, sk))
        for item_name in inv:
            # Determine if equippable and what kind
            equippable = item_name in ARMORS or item_name in WEAPONS
            unified.append((None, item_name, False, None))

        # ── EQUIPPED section header ──
        self._u3_text("EQUIPPED", rx, ry, self._U3_ORANGE, fm)
        ry += 22

        list_row = 0
        num_equip_slots = len(_slots)
        for i, (slot_label, item_name, is_eq, slot_key) in enumerate(unified):
            # Insert ITEMS header before inventory section
            if i == num_equip_slots:
                ry += 10
                self._u3_text("ITEMS", rx, ry, self._U3_ORANGE, fm)
                ry += 22

            selected = (list_row == cursor_index)
            prefix = "> " if selected else "  "

            if is_eq:
                # Equipped slot row: label on first line, item indented below
                eq_row_h = 34  # total height for a two-line equipped row
                display_name = item_name if item_name else "-- NONE --"
                name_color = self._U3_WHITE if selected else self._U3_LTBLUE

                # Highlight bar behind both lines of selected row
                if selected:
                    sel_rect = pygame.Rect(rx - 4, ry - 1, right_w - 16, eq_row_h)
                    sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                    sel_surf.fill((255, 255, 255, 25))
                    self.screen.blit(sel_surf, sel_rect)

                # Slot label line
                self._u3_text(f"{prefix}{slot_label}:", rx, ry, name_color, fm)

                # Stat hint on label line (right-aligned)
                hint = ""
                if item_name:
                    if slot_key == "body":
                        arm = ARMORS.get(item_name, {"evasion": 50})
                        hint = f"EVD:{arm['evasion']}%"
                    elif slot_key in ("right_hand", "left_hand"):
                        wp = WEAPONS.get(item_name, {"power": 0})
                        hint = f"PWR:{wp['power']:d}"
                if hint:
                    self._u3_text(hint, rx + right_w - 90, ry, (180, 180, 180), fm)

                # Item name on second line, indented
                ry += 16
                item_indent = rx + 20
                if item_name:
                    # Check for weapon poison on this slot
                    wp_poison = None
                    if slot_key in ("right_hand", "left_hand"):
                        wp_poison = getattr(member, "weapon_poison", {}).get(slot_key)
                    if wp_poison:
                        hits = wp_poison.get("hits_remaining", 0)
                        poison_label = f"{display_name} (P:{hits})"
                        self._u3_text(poison_label, item_indent, ry,
                                      (80, 220, 80) if selected else (60, 180, 60), fm)
                    else:
                        self._u3_text(display_name, item_indent, ry,
                                      self._U3_WHITE if selected else (220, 220, 230), fm)
                else:
                    self._u3_text("-- NONE --", item_indent, ry, (120, 120, 120), fm)

                # Advance past the item line to next row
                ry += 20

            else:
                # Inventory item row
                name_color = self._U3_WHITE if selected else (220, 220, 230)
                self._u3_text(f"{prefix}{item_name}", rx, ry, name_color, fm)

                # Show what slot it would equip to
                equip_hint = ""
                if item_name in ARMORS:
                    equip_hint = "(BODY)"
                elif item_name in WEAPONS:
                    equip_hint = "(WEAPON)"
                if equip_hint:
                    self._u3_text(equip_hint, rx + right_w - 90, ry,
                                  (160, 160, 255) if selected else (100, 100, 160), fm)

                # Highlight bar behind selected row
                if selected:
                    sel_rect = pygame.Rect(rx - 4, ry - 1, right_w - 16, row_h)
                    sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                    sel_surf.fill((255, 255, 255, 25))
                    self.screen.blit(sel_surf, sel_rect)

                ry += row_h
            list_row += 1

        # If inventory is empty, show placeholder
        if len(inv) == 0 and list_row == num_equip_slots:
            ry += 10
            self._u3_text("ITEMS", rx, ry, self._U3_ORANGE, fm)
            ry += 22
            self._u3_text("  (EMPTY)", rx, ry, (120, 120, 120), fm)

        # ── Combat stats (detailed breakdown) ──
        ry += 16
        pygame.draw.line(self.screen, (60, 60, 80),
                         (rx, ry), (rx + right_w - 24, ry), 1)
        ry += 8
        self._u3_text("COMBAT STATS", rx, ry, self._U3_ORANGE, fm)
        ry += 20
        rpb = right_w - 24  # right panel usable width
        fs = self.font_small
        dim = (120, 120, 140)   # dim color for breakdown text
        val_c = self._U3_WHITE  # value color
        lbl_c = self._U3_LTBLUE  # label color
        buf_c = (180, 255, 140)  # buff bonus color

        # — Armor Class —
        ac = member.get_ac()
        armor_name = member.armor or "Cloth"
        armor_data = ARMORS.get(armor_name, {"evasion": 50})
        armor_bonus = (armor_data["evasion"] - 50) // 5
        dex_mod = member.dex_mod
        potion_ac = getattr(member, "potion_buffs", {}).get("ac", 0)

        self._u3_text("AC", rx, ry, lbl_c, fm)
        self._u3_text(f"{ac:d}", rx + 38, ry, val_c, fm)
        ry += 16
        # Breakdown line
        parts = [f"BASE 10"]
        if armor_bonus:
            parts.append(f"{armor_name.upper()} {armor_bonus:+d}")
        if dex_mod:
            parts.append(f"DEX {dex_mod:+d}")
        if potion_ac:
            parts.append(f"POTION {potion_ac:+d}")
        breakdown = "  ".join(parts)
        self._u3_text(breakdown, rx + 4, ry, dim, fs)
        ry += 18

        # — Gather weapons from both hands —
        eq = getattr(member, 'equipped', {})
        rh_name = eq.get("right_hand") or "Fists"
        lh_name = eq.get("left_hand")
        # Build list of (weapon_name, hand_label) for each occupied hand
        weapon_entries = []
        rh_data = WEAPONS.get(rh_name, {})
        if rh_data or rh_name == "Fists":
            weapon_entries.append((rh_name, "R"))
        if lh_name and WEAPONS.get(lh_name):
            weapon_entries.append((lh_name, "L"))
        has_two = len(weapon_entries) > 1
        potions = getattr(member, "potion_buffs", {})

        for wp_name, hand_tag in weapon_entries:
            wdata = WEAPONS.get(wp_name, {"power": 0})
            wp_power = wdata["power"] if isinstance(wdata, dict) else 0
            wp_ranged = wdata.get("ranged", False) if isinstance(wdata, dict) else False

            # — Header for this weapon —
            if has_two:
                hand_label = "RIGHT HAND" if hand_tag == "R" else "LEFT HAND"
                self._u3_text(hand_label, rx, ry, self._U3_ORANGE, fs)
                ry += 14

            # — Attack —
            stat_label = "DEX" if wp_ranged else "STR"
            stat_mod = member.dex_mod if wp_ranged else member.str_mod
            potion_key = "dexterity" if wp_ranged else "strength"
            potion_atk = potions.get(potion_key, 0)
            atk_total = stat_mod + potion_atk

            self._u3_text("ATK", rx, ry, lbl_c, fm)
            self._u3_text(f"D20{format_modifier(atk_total)}", rx + 38, ry, val_c, fm)
            ry += 16
            parts = []
            if wp_ranged:
                parts.append("RANGED")
            parts.append(f"{stat_label} {stat_mod:+d}")
            if potion_atk:
                parts.append(f"POTION {potion_atk:+d}")
            self._u3_text("  ".join(parts), rx + 4, ry, dim, fs)
            ry += 16

            # — Damage —
            dice_count, dice_sides, dmg_bonus = member.get_damage_dice(wp_name)
            potion_dmg = potions.get(potion_key, 0)
            total_bonus = dmg_bonus + potion_dmg
            dmg_min = max(1, dice_count + total_bonus)
            dmg_max = max(1, dice_count * dice_sides + total_bonus)
            dice_str = f"{dice_count}D{dice_sides}"
            if total_bonus > 0:
                dice_str += f"+{total_bonus}"
            elif total_bonus < 0:
                dice_str += f"{total_bonus}"

            self._u3_text("DAMAGE", rx, ry, lbl_c, fm)
            self._u3_text(dice_str, rx + 68, ry, val_c, fm)
            ry += 16
            self._u3_text(f"RANGE {dmg_min} - {dmg_max}", rx + 4, ry, dim, fs)
            ry += 14
            parts = [f"{wp_name.upper()} {dice_count}D{dice_sides}"]
            parts.append(f"{stat_label} {dmg_bonus:+d}")
            if potion_dmg:
                parts.append(f"POTION {potion_dmg:+d}")
            self._u3_text("  ".join(parts), rx + 4, ry, dim, fs)
            ry += 16

        # — Magic type —
        magic_types = []
        if member.can_cast_priest():
            magic_types.append("PRIEST")
        if member.can_cast_sorcerer():
            magic_types.append("SORCERER")
        magic_str = " + ".join(magic_types) if magic_types else "NONE"
        self._u3_text("MAGIC", rx, ry, lbl_c, fm)
        self._u3_text(magic_str, rx + 60, ry,
                      (180, 180, 255) if magic_types else (150, 150, 150), fm)

        # ── Action menu popup ──
        if action_menu and action_options:
            # Use the options list passed from the state (single source of truth)
            options = action_options
            item_name = None
            if cursor_index < len(unified):
                _, item_name, _, _ = unified[cursor_index]

            if options:
                # Size popup to fit longest option text
                max_label = max((len(o) for o in options), default=0)
                popup_w = max(240, max_label * 10 + 40)
                popup_h = 22 + len(options) * 22 + 8
                popup_x = SCREEN_WIDTH // 2 - popup_w // 2
                popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

                # Background
                pygame.draw.rect(self.screen, (20, 20, 40),
                                 (popup_x, popup_y, popup_w, popup_h))
                pygame.draw.rect(self.screen, self._U3_LTBLUE,
                                 (popup_x, popup_y, popup_w, popup_h), 2)

                # Title
                disp = item_name if item_name else "NONE"
                self._u3_text(disp, popup_x + 10, popup_y + 6, self._U3_ORANGE, fm)
                oy = popup_y + 26
                for oi, opt_text in enumerate(options):
                    sel = (oi == action_cursor)
                    prefix = "> " if sel else "  "
                    col = self._U3_WHITE if sel else self._U3_LTBLUE
                    self._u3_text(f"{prefix}{opt_text}", popup_x + 10, oy, col, fm)
                    if sel:
                        hl = pygame.Rect(popup_x + 4, oy - 1, popup_w - 8, 20)
                        hl_s = pygame.Surface((hl.w, hl.h), pygame.SRCALPHA)
                        hl_s.fill((255, 255, 255, 25))
                        self.screen.blit(hl_s, hl)
                    oy += 22

        # ── Bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        if action_menu:
            self._u3_text("[UP/DN] SELECT  [ENTER] CONFIRM  [ESC] CANCEL",
                          8, bar_y + 5, self._U3_BLUE)
        else:
            self._u3_text("[UP/DN] SELECT  [ENTER] ACTION  [ESC] BACK  [P] CLOSE",
                          8, bar_y + 5, self._U3_BLUE)

    # ========================================================
    # SHOP SCREEN
    # ========================================================

    def draw_shop_u3(self, party, mode="buy", cursor_index=0, message="",
                      quest_complete=False):
        """
        Full-screen shop for buying and selling items.

        *mode*: "buy" or "sell"
        *cursor_index*: position in the active list
        *message*: transient feedback text (e.g. "Bought Sword!")
        *quest_complete*: if True, show Shadow Crystal display case
        """
        from src.party import (SHOP_INVENTORY, WEAPONS, ARMORS, ITEM_INFO,
                                get_sell_price, group_items_by_category,
                                group_inventory_by_category)

        fm = self.font_med
        f = self.font
        self.screen.fill(self._U3_BLACK)

        buy_items = list(SHOP_INVENTORY.keys())
        sell_items = party.shared_inventory

        # Pre-compute grouped buy list: [(item_name_or_None, cat_label_or_None), ...]
        grouped_buy = group_items_by_category(buy_items)
        # Pre-compute grouped sell list with headers
        grouped_sell = group_inventory_by_category(sell_items, party.item_name)

        # ── Title bar with BUY / SELL tabs ──
        self._u3_panel(0, 0, SCREEN_WIDTH, 30)
        self._u3_text("SHOP", 10, 8, self._U3_ORANGE, f)

        # Tab indicators
        buy_col = self._U3_WHITE if mode == "buy" else self._U3_GRAY
        sell_col = self._U3_WHITE if mode == "sell" else self._U3_GRAY
        buy_bg = self._U3_BLUE if mode == "buy" else (40, 40, 60)
        sell_bg = self._U3_BLUE if mode == "sell" else (40, 40, 60)

        buy_tab = pygame.Rect(200, 4, 80, 22)
        sell_tab = pygame.Rect(286, 4, 80, 22)
        pygame.draw.rect(self.screen, buy_bg, buy_tab)
        pygame.draw.rect(self.screen, sell_bg, sell_tab)
        pygame.draw.rect(self.screen, self._U3_LTBLUE, buy_tab, 1)
        pygame.draw.rect(self.screen, self._U3_LTBLUE, sell_tab, 1)
        self._u3_text("BUY", 224, 8, buy_col, fm)
        self._u3_text("SELL", 308, 8, sell_col, fm)

        # ── Layout ──
        left_x = 4
        left_w = SCREEN_WIDTH // 2 + 60
        right_x = left_x + left_w + 4
        right_w = SCREEN_WIDTH - right_x - 4
        panel_y = 36
        panel_h = SCREEN_HEIGHT - 36 - 28

        self._u3_panel(left_x, panel_y, left_w, panel_h)
        self._u3_panel(right_x, panel_y, right_w, panel_h)

        row_h = 20

        # ═══════════════════════════════════════
        # LEFT PANEL — Item list
        # ═══════════════════════════════════════
        tx = left_x + 12
        ty = panel_y + 10

        if mode == "buy":
            self._u3_text("FOR SALE", tx, ty, self._U3_ORANGE, fm)
            self._u3_text(f"({len(buy_items)} ITEMS)", tx + 110, ty,
                          self._U3_GRAY, fm)
            ty += 24

            # grouped_buy: [(item_name_or_None, cat_label_or_None), ...]
            rows = grouped_buy
            max_visible = (panel_h - 60) // row_h
            # Find the visual row that corresponds to cursor_index-th item
            item_counter = -1
            cursor_visual = 0
            for ri, (iname, cat) in enumerate(rows):
                if iname is not None:
                    item_counter += 1
                    if item_counter == cursor_index:
                        cursor_visual = ri
                        break

            scroll_top = 0
            if len(rows) > max_visible:
                scroll_top = max(0, min(cursor_visual - max_visible // 2,
                                        len(rows) - max_visible))

            item_counter = -1
            for ri in range(scroll_top, min(scroll_top + max_visible, len(rows))):
                iname, cat = rows[ri]
                if iname is None:
                    # Category header
                    self._u3_text(f"-- {cat} --", tx + 4, ty,
                                  self._U3_ORANGE, self.font_small)
                    ty += row_h
                    continue

                item_counter_temp = sum(1 for r in rows[:ri + 1] if r[0] is not None) - 1
                selected = (item_counter_temp == cursor_index)
                prefix = "> " if selected else "  "
                name_color = self._U3_WHITE if selected else (220, 220, 230)
                cost = SHOP_INVENTORY[iname]["buy"]

                self._u3_text(f"{prefix}{iname}", tx, ty, name_color, fm)
                price_col = (255, 255, 0) if selected else (200, 200, 100)
                self._u3_text(f"{cost}g", tx + left_w - 80, ty, price_col, fm)

                if selected:
                    sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
                    sel_surf = pygame.Surface(
                        (sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                    sel_surf.fill((255, 255, 255, 25))
                    self.screen.blit(sel_surf, sel_rect)
                ty += row_h

            if scroll_top > 0:
                self._u3_text("^ MORE ^", tx + left_w // 2 - 50,
                              panel_y + 32, self._U3_GRAY, self.font_small)
            if scroll_top + max_visible < len(rows):
                self._u3_text("v MORE v", tx + left_w // 2 - 50,
                              panel_y + panel_h - 18, self._U3_GRAY,
                              self.font_small)

        else:  # sell
            self._u3_text("YOUR ITEMS", tx, ty, self._U3_ORANGE, fm)
            self._u3_text(f"({len(sell_items)} ITEMS)", tx + 120, ty,
                          self._U3_GRAY, fm)
            ty += 24

            if not sell_items:
                self._u3_text("  (NOTHING TO SELL)", tx, ty,
                              (120, 120, 120), fm)
            else:
                rows = grouped_sell  # mixed list: header strings + inventory entries
                max_visible = (panel_h - 60) // row_h
                # Find visual row for cursor_index-th item
                item_counter = -1
                cursor_visual = 0
                for ri, entry in enumerate(rows):
                    is_header = isinstance(entry, str) and entry.startswith("__header__:")
                    if not is_header:
                        item_counter += 1
                        if item_counter == cursor_index:
                            cursor_visual = ri
                            break

                scroll_top = 0
                if len(rows) > max_visible:
                    scroll_top = max(0, min(cursor_visual - max_visible // 2,
                                            len(rows) - max_visible))

                for ri in range(scroll_top, min(scroll_top + max_visible, len(rows))):
                    entry = rows[ri]
                    is_header = isinstance(entry, str) and entry.startswith("__header__:")
                    if is_header:
                        cat_label = entry.split(":", 1)[1]
                        self._u3_text(f"-- {cat_label} --", tx + 4, ty,
                                      self._U3_ORANGE, self.font_small)
                        ty += row_h
                        continue

                    item_name = party.item_name(entry)
                    item_ch = party.item_charges(entry)
                    # Compute this entry's item index
                    idx_temp = sum(1 for r in rows[:ri + 1]
                                   if not (isinstance(r, str) and r.startswith("__header__:"))) - 1
                    selected = (idx_temp == cursor_index)
                    prefix = "> " if selected else "  "
                    name_color = self._U3_WHITE if selected else (220, 220, 230)
                    price = get_sell_price(item_name)

                    display = item_name
                    if item_ch is not None:
                        display = f"{item_name} ({item_ch})"
                    self._u3_text(f"{prefix}{display}", tx, ty,
                                  name_color, fm)
                    price_col = (255, 255, 0) if selected else (200, 200, 100)
                    self._u3_text(f"{price}g", tx + left_w - 80, ty,
                                  price_col, fm)

                    if selected:
                        sel_rect = pygame.Rect(tx - 4, ty - 1,
                                               left_w - 24, row_h)
                        sel_surf = pygame.Surface(
                            (sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                        sel_surf.fill((255, 255, 255, 25))
                        self.screen.blit(sel_surf, sel_rect)
                    ty += row_h

                if scroll_top > 0:
                    self._u3_text("^ MORE ^", tx + left_w // 2 - 50,
                                  panel_y + 32, self._U3_GRAY,
                                  self.font_small)
                if scroll_top + max_visible < len(rows):
                    self._u3_text("v MORE v", tx + left_w // 2 - 50,
                                  panel_y + panel_h - 18, self._U3_GRAY,
                                  self.font_small)

        # ═══════════════════════════════════════
        # RIGHT PANEL — Item details + gold
        # ═══════════════════════════════════════
        rx = right_x + 10
        ry = panel_y + 10

        # Determine selected item from grouped lists
        sel_item = None
        if mode == "buy" and grouped_buy:
            item_count = -1
            for iname, cat in grouped_buy:
                if iname is not None:
                    item_count += 1
                    if item_count == cursor_index:
                        sel_item = iname
                        break
        elif mode == "sell" and grouped_sell:
            item_count = -1
            for entry in grouped_sell:
                is_hdr = isinstance(entry, str) and entry.startswith("__header__:")
                if not is_hdr:
                    item_count += 1
                    if item_count == cursor_index:
                        sel_item = party.item_name(entry)
                        break

        if sel_item:
            self._u3_text("DETAILS", rx, ry, self._U3_ORANGE, fm)
            ry += 22
            self._u3_text(sel_item, rx, ry, self._U3_WHITE, f)
            ry += 24

            # Item stats
            if sel_item in ARMORS:
                arm = ARMORS[sel_item]
                self._u3_text("TYPE: ARMOR", rx, ry, self._U3_LTBLUE, fm)
                ry += 18
                self._u3_text(f"EVASION: {arm['evasion']}%", rx, ry,
                              (220, 220, 230), fm)
                ry += 18
                self._u3_text("SLOT: BODY", rx, ry, (180, 180, 180), fm)
            elif sel_item in WEAPONS:
                wp = WEAPONS[sel_item]
                wtype = "RANGED" if wp.get("ranged", False) else "MELEE"
                self._u3_text(f"TYPE: {wtype} WEAPON", rx, ry,
                              self._U3_LTBLUE, fm)
                ry += 18
                self._u3_text(f"POWER: {wp['power']:d}", rx, ry,
                              (220, 220, 230), fm)
                ry += 18
                self._u3_text("SLOT: RIGHT HAND", rx, ry, (180, 180, 180), fm)
            else:
                self._u3_text("TYPE: GENERAL ITEM", rx, ry,
                              self._U3_LTBLUE, fm)
                ry += 18
                self._u3_text("NOT EQUIPPABLE", rx, ry,
                              (180, 180, 180), fm)

            ry += 28
            # Price line
            if mode == "buy":
                cost = SHOP_INVENTORY[sel_item]["buy"]
                affordable = party.gold >= cost
                price_color = (255, 255, 0) if affordable else self._U3_RED
                self._u3_text(f"COST: {cost} GOLD", rx, ry, price_color, fm)
                if not affordable:
                    ry += 18
                    self._u3_text("(NOT ENOUGH GOLD)", rx, ry,
                                  self._U3_RED, self.font_small)
            else:
                price = get_sell_price(sel_item)
                self._u3_text(f"VALUE: {price} GOLD", rx, ry,
                              (255, 255, 0), fm)

            # Description from ITEM_INFO
            ry += 28
            info = ITEM_INFO.get(sel_item)
            if info:
                desc = info.get("desc", "")
                # Word-wrap description
                words = desc.split()
                line = ""
                for word in words:
                    test = f"{line} {word}".strip()
                    if fm.size(test)[0] > right_w - 24:
                        self._u3_text(line, rx, ry, self._U3_GRAY, fm)
                        ry += 16
                        line = word
                    else:
                        line = test
                if line:
                    self._u3_text(line, rx, ry, self._U3_GRAY, fm)
        else:
            self._u3_text("NO ITEMS", rx, ry, (120, 120, 120), fm)

        # ── Shadow Crystal display case (quest trophy) ──
        if quest_complete:
            import math
            import time as _time
            anim_t = _time.time()

            case_y = panel_y + panel_h - 120
            case_w = right_w - 20
            case_h = 80
            case_x = right_x + 10

            # Display case background
            case_surf = pygame.Surface((case_w, case_h), pygame.SRCALPHA)
            case_surf.fill((15, 8, 30, 200))
            self.screen.blit(case_surf, (case_x, case_y))

            # Ornate border
            pygame.draw.rect(self.screen, (140, 80, 200),
                             (case_x, case_y, case_w, case_h), 2)
            pygame.draw.rect(self.screen, (80, 40, 120),
                             (case_x + 2, case_y + 2,
                              case_w - 4, case_h - 4), 1)

            # Label
            self._u3_text("ON DISPLAY", case_x + 8, case_y + 4,
                          (180, 140, 220), self.font_small)

            # Animated crystal gem in the display case
            gem_cx = case_x + case_w // 2
            gem_cy = case_y + case_h // 2 + 4
            bob = int(3 * math.sin(anim_t * 2))

            # Glow behind crystal
            glow_r = int(18 + 4 * math.sin(anim_t * 3))
            glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            glow_alpha = int(60 + 30 * math.sin(anim_t * 2.5))
            pygame.draw.circle(glow, (120, 60, 200, glow_alpha),
                               (glow_r, glow_r), glow_r)
            self.screen.blit(glow,
                             (gem_cx - glow_r, gem_cy + bob - glow_r))

            # Diamond-shaped crystal
            size = 10
            pulse = 0.15 * math.sin(anim_t * 4)
            cr = min(255, int(140 * (1 + pulse)))
            cg = min(255, int(80 * (1 + pulse)))
            cb = min(255, int(220 * (1 + pulse)))
            pts = [
                (gem_cx, gem_cy + bob - size),
                (gem_cx + size, gem_cy + bob),
                (gem_cx, gem_cy + bob + size),
                (gem_cx - size, gem_cy + bob),
            ]
            pygame.draw.polygon(self.screen, (cr, cg, cb), pts)
            pygame.draw.polygon(self.screen, (200, 160, 255), pts, 1)

            # Inner sparkle
            inner = size // 2
            ipts = [
                (gem_cx, gem_cy + bob - inner),
                (gem_cx + inner, gem_cy + bob),
                (gem_cx, gem_cy + bob + inner),
                (gem_cx - inner, gem_cy + bob),
            ]
            pygame.draw.polygon(self.screen, (220, 200, 255), ipts)

            # Item name
            self._u3_text("Shadow Crystal",
                          gem_cx - 55, gem_cy + bob + size + 6,
                          (180, 140, 255), self.font_small)

        # ── Gold display ──
        gold_y = panel_y + panel_h - 30
        self._draw_item_icon(rx + 12, gold_y + 8, "chest", 28)
        self._u3_text(f"GOLD: {party.gold:d}", rx + 30, gold_y + 2,
                      (255, 255, 0), fm)

        # ── Floating shop message ──
        if message:
            surf = fm.render(message.upper(), True, (255, 220, 140))
            rect = surf.get_rect(center=(SCREEN_WIDTH // 2,
                                         SCREEN_HEIGHT // 2))
            bg = rect.inflate(24, 12)
            pygame.draw.rect(self.screen, (0, 0, 0), bg)
            pygame.draw.rect(self.screen, self._U3_LTBLUE, bg, 2)
            self.screen.blit(surf, rect)

        # ── Bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        action = "BUY" if mode == "buy" else "SELL"
        self._u3_text(
            f"[UP/DN] SELECT  [ENTER] {action}  [TAB] BUY/SELL  [ESC] LEAVE",
            8, bar_y + 5, self._U3_BLUE)

    def draw_party_inventory_u3(self, party, cursor_index=0,
                                 choosing_member=False, member_cursor=0,
                                 action_menu=False, action_cursor=0,
                                 action_options=None,
                                 choosing_effect=False, effect_list=None,
                                 effect_cursor=0,
                                 showing_spell_list=False,
                                 spell_list_items=None,
                                 spell_list_cursor=0,
                                 choosing_heal_target=False,
                                 heal_target_cursor=0,
                                 showing_brew_list=False,
                                 brew_list_items=None,
                                 brew_list_cursor=0,
                                 brew_result_msg=None,
                                 pickpocket_available=False,
                                 tinker_available=False,
                                 applying_poison_step=None,
                                 applying_poison_cursor=0,
                                 applying_poison_item=None,
                                 applying_poison_member=None):
        """
        Full-screen shared party inventory with party equipment slots.

        The list is unified: first 4 rows are party equipment slots,
        followed by shared inventory items.

        Modes:
        - Normal: browse items with cursor, Enter to open action menu.
        - action_menu: choose from context-sensitive options.
        """
        from src.party import (WEAPONS, ARMORS, ITEM_INFO, EFFECTS_DATA,
                                group_inventory_by_category)

        fm = self.font_med
        f = self.font
        self.screen.fill(self._U3_BLACK)
        self._last_party = party

        # ── Title bar ──
        self._u3_panel(0, 0, SCREEN_WIDTH, 30)
        self._u3_text("PARTY INVENTORY", SCREEN_WIDTH // 2 - 75, 8,
                       self._U3_ORANGE, f)

        # ── Layout: left = item list, right = item details + member select ──
        left_x = 4
        left_w = SCREEN_WIDTH // 2 + 60
        right_x = left_x + left_w + 4
        right_w = SCREEN_WIDTH - right_x - 4
        panel_y = 36
        panel_h = SCREEN_HEIGHT - 36 - 28

        self._u3_panel(left_x, panel_y, left_w, panel_h)
        self._u3_panel(right_x, panel_y, right_w, panel_h)

        inv = party.shared_inventory
        row_h = 20

        # ═══════════════════════════════════════
        # LEFT PANEL — Effects + Item list
        # ═══════════════════════════════════════
        tx = left_x + 12
        ty = panel_y + 10

        # ── Effects section (active + available effects) ──
        self._u3_text("EFFECTS", tx, ty, self._U3_ORANGE, fm)
        ty += 24

        # Build combined list: active effects first, then available
        active_effects = [(s, party.get_effect(s)) for s in party.EFFECT_SLOTS
                          if party.get_effect(s) is not None]
        available_effects = party.get_available_effects()
        all_effect_rows = []
        for slot_key, eff_name in active_effects:
            all_effect_rows.append(('active', slot_key, eff_name))
        for eff in available_effects:
            all_effect_rows.append(('available', eff))
        NUM_EFFECTS = len(all_effect_rows)

        if not all_effect_rows:
            self._u3_text("  (NONE)", tx, ty, (120, 120, 120), fm)
            ty += row_h
        else:
            for ei, row in enumerate(all_effect_rows):
                selected = (ei == cursor_index)
                prefix = "> " if selected else "  "

                if row[0] == 'active':
                    _slot_key, effect = row[1], row[2]
                    eff_color = self._U3_WHITE if selected else (220, 220, 230)
                    display_eff = effect
                    if effect == "Torch":
                        torch_charges = party.get_equipped_charges("light")
                        if torch_charges is not None:
                            display_eff = f"Torch ({torch_charges})"
                    # Active marker
                    self._u3_text(f"{prefix}{display_eff}", tx, ty, eff_color, fm)
                    # Small green dot to indicate active
                    pygame.draw.circle(self.screen, self._U3_GREEN,
                                       (tx + left_w - 30, ty + row_h // 2), 4)
                else:
                    eff_dict = row[1]
                    eff_color = (150, 150, 170) if not selected else (200, 200, 220)
                    self._u3_text(f"{prefix}{eff_dict['name']}", tx, ty, eff_color, fm)

                if selected:
                    sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
                    sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                    sel_surf.fill((255, 255, 255, 25))
                    self.screen.blit(sel_surf, sel_rect)

                ty += row_h

        # ── Divider ──
        ty += 6
        pygame.draw.line(self.screen, (60, 60, 80),
                         (tx, ty), (tx + left_w - 32, ty), 1)
        ty += 8

        # ── CAST row ──
        CAST_INDEX = NUM_EFFECTS
        cast_selected = (cursor_index == CAST_INDEX)
        cast_prefix = "> " if cast_selected else "  "
        cast_color = self._U3_WHITE if cast_selected else self._U3_GREEN
        self._u3_text(f"{cast_prefix}CAST SPELL", tx, ty, cast_color, fm)
        # Show a small hint on the right when selected
        if cast_selected:
            self._u3_text("ENTER", tx + left_w - 100, ty,
                          self._U3_GREEN, self.font_small)
            sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
            sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
            sel_surf.fill((255, 255, 255, 25))
            self.screen.blit(sel_surf, sel_rect)
        ty += row_h

        # ── BREW row ──
        BREW_INDEX = NUM_EFFECTS + 1
        brew_selected = (cursor_index == BREW_INDEX)
        brew_prefix = "> " if brew_selected else "  "
        brew_color = self._U3_WHITE if brew_selected else (180, 120, 255)
        self._u3_text(f"{brew_prefix}BREW POTIONS", tx, ty, brew_color, fm)
        if brew_selected:
            self._u3_text("ENTER", tx + left_w - 100, ty,
                          (180, 120, 255), self.font_small)
            sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
            sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
            sel_surf.fill((255, 255, 255, 25))
            self.screen.blit(sel_surf, sel_rect)
        ty += row_h

        # ── PICKPOCKET row (only when available) ──
        PICK_INDEX = -1
        next_header = BREW_INDEX + 1
        if pickpocket_available:
            PICK_INDEX = next_header
            next_header += 1
            pick_selected = (cursor_index == PICK_INDEX)
            pick_prefix = "> " if pick_selected else "  "
            pick_color = self._U3_WHITE if pick_selected else (220, 180, 80)
            self._u3_text(f"{pick_prefix}PICKPOCKET", tx, ty, pick_color, fm)
            if pick_selected:
                self._u3_text("ENTER", tx + left_w - 100, ty,
                              (220, 180, 80), self.font_small)
                sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
                sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                sel_surf.fill((255, 255, 255, 25))
                self.screen.blit(sel_surf, sel_rect)
            ty += row_h

        # ── TINKER row (only when available) ──
        TINK_INDEX = -1
        if tinker_available:
            TINK_INDEX = next_header
            next_header += 1
            tink_selected = (cursor_index == TINK_INDEX)
            tink_prefix = "> " if tink_selected else "  "
            tink_color = self._U3_WHITE if tink_selected else (140, 200, 140)
            self._u3_text(f"{tink_prefix}TINKER", tx, ty, tink_color, fm)
            if tink_selected:
                self._u3_text("ENTER", tx + left_w - 100, ty,
                              (140, 200, 140), self.font_small)
                sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
                sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                sel_surf.fill((255, 255, 255, 25))
                self.screen.blit(sel_surf, sel_rect)
            ty += row_h

        # ── Divider ──
        ty += 6
        pygame.draw.line(self.screen, (60, 60, 80),
                         (tx, ty), (tx + left_w - 32, ty), 1)
        ty += 8

        # ── Shared stash section ──
        self._u3_text("SHARED STASH", tx, ty, self._U3_ORANGE, fm)
        self._u3_text(f"({len(inv)} ITEMS)", tx + 140, ty, self._U3_GRAY, fm)
        ty += 24

        if not inv:
            self._u3_text("  (EMPTY)", tx, ty, (120, 120, 120), fm)
        else:
            # Build grouped display list (header strings + original entries)
            grouped_stash = group_inventory_by_category(inv, party.item_name)

            # Map: for each row in grouped_stash, what flat inventory index?
            # Headers get -1, items get their index counting only non-headers.
            row_inv_indices = []
            item_counter = 0
            for entry in grouped_stash:
                is_hdr = isinstance(entry, str) and entry.startswith("__header__:")
                if is_hdr:
                    row_inv_indices.append(-1)
                else:
                    row_inv_indices.append(item_counter)
                    item_counter += 1

            header_count = next_header  # effects + CAST + BREW (+ PICKPOCKET/TINKER)
            inv_cursor = cursor_index - header_count  # cursor relative to inventory

            # Find the visual row that corresponds to inv_cursor
            cursor_visual = 0
            for ri, flat_idx in enumerate(row_inv_indices):
                if flat_idx == inv_cursor:
                    cursor_visual = ri
                    break

            stash_area_top = ty
            stash_area_h = panel_y + panel_h - ty - 10
            max_visible = stash_area_h // row_h

            scroll_top = 0
            if len(grouped_stash) > max_visible:
                scroll_top = max(0, min(cursor_visual - max_visible // 2,
                                        len(grouped_stash) - max_visible))

            for ri in range(scroll_top, min(scroll_top + max_visible, len(grouped_stash))):
                entry = grouped_stash[ri]
                is_hdr = isinstance(entry, str) and entry.startswith("__header__:")

                if is_hdr:
                    cat_label = entry.split(":", 1)[1]
                    self._u3_text(f"-- {cat_label} --", tx + 4, ty,
                                  self._U3_ORANGE, self.font_small)
                    ty += row_h
                    continue

                flat_idx = row_inv_indices[ri]
                item_name = party.item_name(entry)
                item_ch = party.item_charges(entry)
                selected = (flat_idx == inv_cursor)
                prefix = "> " if selected else "  "
                name_color = self._U3_WHITE if selected else (220, 220, 230)

                display = item_name
                if item_ch is not None:
                    display = f"{item_name} ({item_ch})"
                self._u3_text(f"{prefix}{display}", tx, ty, name_color, fm)

                # Type hint on the right
                hint = ""
                if item_name in ARMORS:
                    hint = "ARMOR"
                elif item_name in WEAPONS:
                    hint = "WEAPON"
                else:
                    hint = "ITEM"
                hint_color = self._U3_LTBLUE if selected else (120, 120, 160)
                self._u3_text(hint, tx + left_w - 120, ty, hint_color, fm)

                # Highlight bar
                if selected:
                    sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
                    sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                    sel_surf.fill((255, 255, 255, 25))
                    self.screen.blit(sel_surf, sel_rect)

                ty += row_h

            # Scroll indicators
            if scroll_top > 0:
                self._u3_text("^ MORE ^", tx + left_w // 2 - 50, stash_area_top - 2,
                               self._U3_GRAY, self.font_small)
            if scroll_top + max_visible < len(grouped_stash):
                self._u3_text("v MORE v", tx + left_w // 2 - 50,
                               panel_y + panel_h - 18, self._U3_GRAY, self.font_small)

        # ═══════════════════════════════════════
        # RIGHT PANEL — Characters + Item detail
        # ═══════════════════════════════════════
        rx = right_x + 10
        ry = panel_y + 10

        # ── Character mini-cards (press 1-4 to open detail) ──
        self._u3_text("PARTY  [1-4]", rx, ry, self._U3_ORANGE, fm)
        ry += 20

        char_card_h = 76
        sprite_w = 36  # space reserved for avatar
        fs = self.font_small
        for mi, member in enumerate(party.members):
            cy = ry
            alive = member.is_alive()
            name_color = self._U3_WHITE if alive else self._U3_RED

            # Avatar sprite
            sprite = self._get_member_sprite(member, big=False)
            if sprite:
                sx = rx
                sy = cy + 2
                if not alive:
                    dark = sprite.copy()
                    dark.fill((80, 80, 80), special_flags=pygame.BLEND_RGB_MULT)
                    self.screen.blit(dark, (sx, sy))
                else:
                    self.screen.blit(sprite, (sx, sy))

            # Text starts after avatar
            tx2 = rx + sprite_w
            bar_full_w = right_w - sprite_w - 16

            # Number + name
            self._u3_text(f"{mi+1}", tx2, cy - 2, self._U3_WHITE, f)
            self._u3_text(member.name, tx2 + 18, cy, name_color, fm)

            # Class, Race, Gender — compact line
            cy += 16
            info_str = f"{member.char_class}  {member.race}  {member.gender}"
            self._u3_text(info_str, tx2, cy, (150, 150, 170), fs)

            # Level + HP/MP numbers
            cy += 13
            lvl_str = f"LVL {member.level}"
            hp_str = f"HP {member.hp}/{member.max_hp}"
            mp_cur = member.current_mp
            mp_max = member.max_mp
            mp_str = f"MP {mp_cur}/{mp_max}" if mp_max > 0 else "MP ---"
            stats_str = f"{lvl_str}   {hp_str}   {mp_str}"
            self._u3_text(stats_str, tx2, cy, (180, 180, 200), fs)

            # HP bar
            cy += 14
            hp_frac = member.hp / member.max_hp if member.max_hp > 0 else 0
            hp_color = self._U3_GREEN if hp_frac > 0.3 else self._U3_RED
            self._u3_draw_stat_bar(tx2, cy + 1, bar_full_w, 7,
                                   member.hp, member.max_hp, hp_color)

            # MP bar
            cy += 11
            if mp_max > 0:
                mp_frac = mp_cur / mp_max
                mp_color = self._U3_LTBLUE if mp_frac > 0.3 else (180, 80, 80)
                self._u3_draw_stat_bar(tx2, cy + 1, bar_full_w, 7,
                                       mp_cur, mp_max, mp_color)

            ry += char_card_h

        # ── Divider ──
        ry += 2
        pygame.draw.line(self.screen, (60, 60, 80),
                         (rx, ry), (rx + right_w - 20, ry), 1)
        ry += 8

        # ── Item detail section ──
        sel_item = None
        sel_charges = None
        is_effect_row = (cursor_index < NUM_EFFECTS)
        is_active_effect = False
        is_available_effect = False
        effect_row_data = None
        if is_effect_row and cursor_index < len(all_effect_rows):
            effect_row_data = all_effect_rows[cursor_index]
            if effect_row_data[0] == 'active':
                is_active_effect = True
                sel_item = effect_row_data[2]
                if sel_item == "Torch":
                    sel_charges = party.get_equipped_charges("light")
            else:
                is_available_effect = True
        is_cast_row = (cursor_index == CAST_INDEX)
        is_brew_row = (cursor_index == BREW_INDEX)
        is_pick_row = (PICK_INDEX >= 0 and cursor_index == PICK_INDEX)
        is_tink_row = (TINK_INDEX >= 0 and cursor_index == TINK_INDEX)
        header_count = next_header  # effects + CAST + BREW (+ PICKPOCKET/TINKER if shown)
        if is_active_effect:
            pass  # sel_item already set above
        elif is_available_effect:
            pass  # handled separately below with effect detail display
        elif is_cast_row or is_brew_row or is_pick_row or is_tink_row:
            pass  # no item detail for the CAST/BREW/PICK/TINK rows
        elif cursor_index >= header_count:
            from src.party import grouped_index_to_original
            grouped_idx = cursor_index - header_count
            orig_idx = grouped_index_to_original(inv, party.item_name, grouped_idx)
            if 0 <= orig_idx < len(inv):
                entry = inv[orig_idx]
                sel_item = party.item_name(entry)
                sel_charges = party.item_charges(entry)

        # Show details of the selected item
        if sel_item:
            if is_active_effect:
                self._u3_text("ACTIVE EFFECT", rx, ry, self._U3_ORANGE, fm)
            else:
                self._u3_text("SELECTED", rx, ry, self._U3_ORANGE, fm)
            ry += 22

            # Draw item icon
            icon_size = 48
            icon_info = ITEM_INFO.get(sel_item, {})
            icon_type = icon_info.get("icon", "tool")
            # Draw icon centered at the left of the detail area
            icon_cx = rx + icon_size // 2 + 4
            icon_cy = ry + icon_size // 2
            # Background circle behind the icon
            pygame.draw.circle(self.screen, (30, 30, 55),
                               (icon_cx, icon_cy), icon_size // 2 + 6)
            pygame.draw.circle(self.screen, (60, 60, 90),
                               (icon_cx, icon_cy), icon_size // 2 + 6, 2)
            self._draw_item_icon(icon_cx, icon_cy, icon_type, icon_size)

            # Item name to the right of the icon
            name_x = rx + icon_size + 18
            self._u3_text(sel_item, name_x, ry + 4, self._U3_WHITE, f)
            # Charges under the name if applicable
            if sel_charges is not None:
                self._u3_text(f"x{sel_charges}", name_x, ry + 24,
                              (255, 170, 85), fm)
            ry += icon_size + 12

            # Item stats
            if sel_item in ARMORS:
                arm = ARMORS[sel_item]
                self._u3_text(f"TYPE: ARMOR", rx, ry, self._U3_LTBLUE, fm)
                ry += 18
                self._u3_text(f"EVASION: {arm['evasion']}%", rx, ry, (220, 220, 230), fm)
                ry += 18
                self._u3_text("SLOT: BODY", rx, ry, (180, 180, 180), fm)
            elif sel_item in WEAPONS:
                wp = WEAPONS[sel_item]
                wtype = "RANGED" if wp.get("ranged", False) else "MELEE"
                self._u3_text(f"TYPE: {wtype} WEAPON", rx, ry, self._U3_LTBLUE, fm)
                ry += 18
                self._u3_text(f"POWER: {wp['power']:d}", rx, ry, (220, 220, 230), fm)
                ry += 18
                self._u3_text("SLOT: RIGHT HAND", rx, ry, (180, 180, 180), fm)
            else:
                self._u3_text("TYPE: GENERAL ITEM", rx, ry, self._U3_LTBLUE, fm)

            # Description — check item info first, then effect definitions
            info = ITEM_INFO.get(sel_item)
            desc = None
            if info and info.get("desc"):
                desc = info["desc"]
            elif is_active_effect:
                # Look up in EFFECTS_DATA for non-item effects
                for edef in EFFECTS_DATA:
                    if edef["name"] == sel_item:
                        desc = edef.get("description", "")
                        break
            if desc:
                ry += 24
                words = desc.split()
                line = ""
                for word in words:
                    test = f"{line} {word}".strip()
                    if len(test) > 28:
                        self._u3_text(line, rx, ry, (180, 180, 200), fm)
                        ry += 16
                        line = word
                    else:
                        line = test
                if line:
                    self._u3_text(line, rx, ry, (180, 180, 200), fm)
            if is_active_effect:
                ry += 20
                self._u3_text("ENTER to remove", rx, ry, (200, 100, 100), fm)
        elif is_cast_row:
            self._u3_text("CAST SPELL", rx, ry, self._U3_GREEN, fm)
            ry += 22
            self._u3_text("Press ENTER to view", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("available spells for", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("the current location.", rx, ry, (180, 180, 200), fm)
        elif is_brew_row:
            self._u3_text("BREW POTIONS", rx, ry, (180, 120, 255), fm)
            ry += 22
            # Draw a potion icon
            icon_size = 48
            icon_cx = rx + icon_size // 2 + 4
            icon_cy = ry + icon_size // 2
            pygame.draw.circle(self.screen, (30, 30, 55),
                               (icon_cx, icon_cy), icon_size // 2 + 6)
            pygame.draw.circle(self.screen, (80, 50, 120),
                               (icon_cx, icon_cy), icon_size // 2 + 6, 2)
            self._draw_item_icon(icon_cx, icon_cy, "potion", icon_size)
            # Text to the right of the icon
            name_x = rx + icon_size + 18
            self._u3_text("Alchemy", name_x, ry + 4, self._U3_WHITE, f)
            ry += icon_size + 12
            # Check if an alchemist is available
            has_alchemist = False
            for m in party.members:
                if m.is_alive() and m.char_class == "Alchemist":
                    has_alchemist = True
                    break
            if has_alchemist:
                self._u3_text("Press ENTER to browse", rx, ry, (180, 180, 200), fm)
                ry += 16
                self._u3_text("potion recipes. Your", rx, ry, (180, 180, 200), fm)
                ry += 16
                self._u3_text("Alchemist can brew", rx, ry, (180, 180, 200), fm)
                ry += 16
                self._u3_text("potions from reagents", rx, ry, (180, 180, 200), fm)
                ry += 16
                self._u3_text("in the party stash.", rx, ry, (180, 180, 200), fm)
                ry += 24
                self._u3_text("Requires INT check", rx, ry, (200, 200, 140), fm)
            else:
                self._u3_text("No Alchemist in the", rx, ry, (180, 120, 120), fm)
                ry += 16
                self._u3_text("party. You need an", rx, ry, (180, 120, 120), fm)
                ry += 16
                self._u3_text("Alchemist to brew", rx, ry, (180, 120, 120), fm)
                ry += 16
                self._u3_text("potions.", rx, ry, (180, 120, 120), fm)
        elif is_pick_row:
            self._u3_text("PICKPOCKET", rx, ry, (220, 180, 80), fm)
            ry += 22
            self._u3_text("Your Halfling's nimble", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("fingers can pilfer", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("items from a nearby", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("townsperson.", rx, ry, (180, 180, 200), fm)
            ry += 24
            self._u3_text("DEX saving throw", rx, ry, (200, 200, 140), fm)
            ry += 16
            self._u3_text("determines success.", rx, ry, (200, 200, 140), fm)
            ry += 24
            self._u3_text("Failure = gold fine!", rx, ry, (200, 100, 100), fm)
        elif is_tink_row:
            self._u3_text("TINKER", rx, ry, (140, 200, 140), fm)
            ry += 22
            self._u3_text("Your Gnome's clever", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("hands can craft items", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("from scraps and bits", rx, ry, (180, 180, 200), fm)
            ry += 16
            self._u3_text("found along the way.", rx, ry, (180, 180, 200), fm)
            ry += 24
            self._u3_text("INT saving throw", rx, ry, (200, 200, 140), fm)
            ry += 16
            self._u3_text("determines success.", rx, ry, (200, 200, 140), fm)
            ry += 24
            self._u3_text("Higher level = better", rx, ry, (140, 200, 140), fm)
            ry += 16
            self._u3_text("items!", rx, ry, (140, 200, 140), fm)
        elif is_available_effect and effect_row_data:
            eff_dict = effect_row_data[1]
            self._u3_text("AVAILABLE EFFECT", rx, ry, self._U3_LTBLUE, fm)
            ry += 22
            self._u3_text(eff_dict["name"], rx, ry, self._U3_WHITE, f)
            ry += 24
            # Show description
            desc = eff_dict.get("description", "")
            if desc:
                words = desc.split()
                line = ""
                for word in words:
                    test = f"{line} {word}".strip()
                    if len(test) > 28:
                        self._u3_text(line, rx, ry, (180, 180, 200), fm)
                        ry += 16
                        line = word
                    else:
                        line = test
                if line:
                    self._u3_text(line, rx, ry, (180, 180, 200), fm)
                ry += 20
            # Show requirements
            reqs = eff_dict.get("requirements", {})
            if reqs:
                for rk, rv in reqs.items():
                    self._u3_text(f"{rk.upper()}: {rv}", rx, ry, (160, 160, 180), fm)
                    ry += 16
            ry += 8
            self._u3_text("ENTER to assign", rx, ry, self._U3_GREEN, fm)
        else:
            self._u3_text("NO ITEMS", rx, ry, (120, 120, 120), fm)


        # ── Gold display with chest icon ──
        gold_y = panel_y + panel_h - 30
        self._draw_item_icon(rx + 12, gold_y + 8, "chest", 28)
        self._u3_text(f"GOLD: {party.gold:d}", rx + 30, gold_y + 2, (255, 255, 0), fm)

        # ── Action menu popup ──
        if action_menu and action_options:
            options = action_options
            popup_item = sel_item or "EMPTY SLOT"

            max_label = max((len(o) for o in options), default=0)
            popup_w = max(220, max_label * 10 + 40)
            popup_h = 22 + len(options) * 22 + 8
            popup_x = SCREEN_WIDTH // 2 - popup_w // 2
            popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

            pygame.draw.rect(self.screen, (20, 20, 40),
                             (popup_x, popup_y, popup_w, popup_h))
            pygame.draw.rect(self.screen, self._U3_LTBLUE,
                             (popup_x, popup_y, popup_w, popup_h), 2)

            self._u3_text(popup_item, popup_x + 10, popup_y + 6, self._U3_ORANGE, fm)
            oy = popup_y + 26
            for oi, opt_text in enumerate(options):
                sel = (oi == action_cursor)
                prefix = "> " if sel else "  "
                col = self._U3_WHITE if sel else self._U3_LTBLUE
                self._u3_text(f"{prefix}{opt_text}", popup_x + 10, oy, col, fm)
                if sel:
                    hl = pygame.Rect(popup_x + 4, oy - 1, popup_w - 8, 20)
                    hl_s = pygame.Surface((hl.w, hl.h), pygame.SRCALPHA)
                    hl_s.fill((255, 255, 255, 25))
                    self.screen.blit(hl_s, hl)
                oy += 22

        # ── Spell list popup ──
        if showing_spell_list:
            spells = spell_list_items or []
            if not spells:
                popup_w = 280
                popup_h = 60
                popup_x = SCREEN_WIDTH // 2 - popup_w // 2
                popup_y = SCREEN_HEIGHT // 2 - popup_h // 2
                pygame.draw.rect(self.screen, (20, 20, 40),
                                 (popup_x, popup_y, popup_w, popup_h))
                pygame.draw.rect(self.screen, self._U3_LTBLUE,
                                 (popup_x, popup_y, popup_w, popup_h), 2)
                self._u3_text("CAST SPELL", popup_x + 10, popup_y + 6,
                              self._U3_ORANGE, fm)
                self._u3_text("NO SPELLS AVAILABLE",
                              popup_x + 10, popup_y + 30,
                              self._U3_GRAY, fm)
            else:
                max_label = max((len(s[1]) for s in spells), default=0)
                popup_w = max(320, max_label * 9 + 40)
                popup_h = 28 + len(spells) * 22 + 8
                popup_x = SCREEN_WIDTH // 2 - popup_w // 2
                popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

                pygame.draw.rect(self.screen, (20, 20, 40),
                                 (popup_x, popup_y, popup_w, popup_h))
                pygame.draw.rect(self.screen, self._U3_GREEN,
                                 (popup_x, popup_y, popup_w, popup_h), 2)

                self._u3_text("CAST SPELL", popup_x + 10, popup_y + 6,
                              self._U3_ORANGE, fm)
                oy = popup_y + 28
                for si, (spell_id, label, cost, mi) in enumerate(spells):
                    sel = (si == spell_list_cursor)
                    prefix = "> " if sel else "  "
                    col = self._U3_WHITE if sel else self._U3_LTBLUE
                    self._u3_text(f"{prefix}{label}",
                                  popup_x + 10, oy, col, fm)
                    if sel:
                        hl = pygame.Rect(popup_x + 4, oy - 1,
                                         popup_w - 8, 20)
                        hl_s = pygame.Surface((hl.w, hl.h),
                                              pygame.SRCALPHA)
                        hl_s.fill((255, 255, 255, 25))
                        self.screen.blit(hl_s, hl)
                    oy += 22

        # ── Brew list popup ──
        if showing_brew_list:
            recipes = brew_list_items or []
            if not recipes:
                popup_w = 280
                popup_h = 60
                popup_x = SCREEN_WIDTH // 2 - popup_w // 2
                popup_y = SCREEN_HEIGHT // 2 - popup_h // 2
                pygame.draw.rect(self.screen, (20, 20, 40),
                                 (popup_x, popup_y, popup_w, popup_h))
                pygame.draw.rect(self.screen, (180, 120, 255),
                                 (popup_x, popup_y, popup_w, popup_h), 2)
                self._u3_text("BREW POTIONS", popup_x + 10, popup_y + 6,
                              self._U3_ORANGE, fm)
                self._u3_text("NO RECIPES AVAILABLE",
                              popup_x + 10, popup_y + 30,
                              self._U3_GRAY, fm)
            else:
                # Left side: recipe list, Right side: recipe detail
                popup_w = 520
                popup_h = max(200, 32 + len(recipes) * 22 + 80)
                popup_x = SCREEN_WIDTH // 2 - popup_w // 2
                popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

                pygame.draw.rect(self.screen, (20, 20, 40),
                                 (popup_x, popup_y, popup_w, popup_h))
                pygame.draw.rect(self.screen, (180, 120, 255),
                                 (popup_x, popup_y, popup_w, popup_h), 2)

                self._u3_text("BREW POTIONS", popup_x + 10, popup_y + 6,
                              self._U3_ORANGE, fm)

                # Recipe list on the left
                oy = popup_y + 30
                list_w = 220
                for ri, (recipe_id, recipe_data, can_brew) in enumerate(recipes):
                    sel = (ri == brew_list_cursor)
                    prefix = "> " if sel else "  "
                    if can_brew:
                        col = self._U3_WHITE if sel else self._U3_GREEN
                    else:
                        col = (120, 120, 120) if not sel else (160, 160, 160)
                    self._u3_text(f"{prefix}{recipe_id}",
                                  popup_x + 10, oy, col, fm)
                    if sel:
                        hl = pygame.Rect(popup_x + 4, oy - 1,
                                         list_w - 8, 20)
                        hl_s = pygame.Surface((hl.w, hl.h),
                                              pygame.SRCALPHA)
                        hl_s.fill((255, 255, 255, 25))
                        self.screen.blit(hl_s, hl)
                    oy += 22

                # Vertical divider
                div_x = popup_x + list_w
                pygame.draw.line(self.screen, (60, 60, 80),
                                 (div_x, popup_y + 28),
                                 (div_x, popup_y + popup_h - 8), 1)

                # Detail panel on the right
                if recipes:
                    _rid, sel_recipe, sel_can = recipes[brew_list_cursor]
                    dx = div_x + 12
                    dy = popup_y + 32

                    self._u3_text(sel_recipe.get("name", _rid), dx, dy,
                                  self._U3_WHITE, fm)
                    dy += 20

                    # Description (word-wrapped)
                    desc = sel_recipe.get("description", "")
                    max_desc_w = popup_w - list_w - 28
                    line = ""
                    for word in desc.split():
                        test = f"{line} {word}".strip()
                        tw = fm.size(test)[0]
                        if tw > max_desc_w and line:
                            self._u3_text(line, dx, dy, (180, 180, 200), fm)
                            dy += 16
                            line = word
                        else:
                            line = test
                    if line:
                        self._u3_text(line, dx, dy, (180, 180, 200), fm)
                        dy += 20

                    # DC requirement
                    dc = sel_recipe.get("dc", 10)
                    self._u3_text(f"DC: {dc}", dx, dy, (200, 200, 140), fm)
                    dy += 20

                    # Reagents needed
                    self._u3_text("REAGENTS:", dx, dy, self._U3_ORANGE, fm)
                    dy += 18
                    reagents = sel_recipe.get("reagents", {})
                    party = self._last_party  # set below
                    for rname, rqty in reagents.items():
                        # Count how many the party has
                        have = 0
                        if party:
                            for entry in party.shared_inventory:
                                if party.item_name(entry) == rname:
                                    ch = party.item_charges(entry)
                                    have += ch if ch is not None else 1
                        have_color = self._U3_GREEN if have >= rqty else self._U3_RED
                        self._u3_text(f"  {rname}: {have}/{rqty}",
                                      dx, dy, have_color, fm)
                        dy += 16

                    # Can brew indicator
                    dy += 8
                    if sel_can:
                        self._u3_text("[ENTER] BREW", dx, dy,
                                      self._U3_GREEN, fm)
                    else:
                        self._u3_text("MISSING REAGENTS", dx, dy,
                                      self._U3_RED, fm)

        # ── Brew result message ──
        if brew_result_msg:
            msg_w = max(280, fm.size(brew_result_msg)[0] + 40)
            msg_h = 50
            msg_x = SCREEN_WIDTH // 2 - msg_w // 2
            msg_y = SCREEN_HEIGHT // 2 - msg_h // 2
            pygame.draw.rect(self.screen, (20, 20, 40),
                             (msg_x, msg_y, msg_w, msg_h))
            # Color border based on success/failure
            border_col = self._U3_GREEN if "Success" in brew_result_msg else self._U3_RED
            pygame.draw.rect(self.screen, border_col,
                             (msg_x, msg_y, msg_w, msg_h), 2)
            self._u3_text(brew_result_msg, msg_x + 10, msg_y + 16,
                          self._U3_WHITE, fm)

        # ── Heal target selection popup ──
        if choosing_heal_target:
            members = party.members
            popup_w = 320
            popup_h = 28 + len(members) * 22 + 8
            popup_x = SCREEN_WIDTH // 2 - popup_w // 2
            popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

            pygame.draw.rect(self.screen, (20, 20, 40),
                             (popup_x, popup_y, popup_w, popup_h))
            pygame.draw.rect(self.screen, self._U3_GREEN,
                             (popup_x, popup_y, popup_w, popup_h), 2)

            self._u3_text("HEAL WHO?", popup_x + 10, popup_y + 6,
                          self._U3_ORANGE, fm)
            oy = popup_y + 28
            for mi, m in enumerate(members):
                sel = (mi == heal_target_cursor)
                prefix = "> " if sel else "  "
                hp_str = f"{m.hp}/{m.max_hp}HP"
                if not m.is_alive():
                    hp_str = "DEAD"
                label = f"{prefix}{m.name}  {hp_str}"
                col = self._U3_WHITE if sel else self._U3_LTBLUE
                if not m.is_alive():
                    col = self._U3_RED if sel else (140, 60, 60)
                self._u3_text(label, popup_x + 10, oy, col, fm)
                if sel:
                    hl = pygame.Rect(popup_x + 4, oy - 1,
                                     popup_w - 8, 20)
                    hl_s = pygame.Surface((hl.w, hl.h),
                                          pygame.SRCALPHA)
                    hl_s.fill((255, 255, 255, 25))
                    self.screen.blit(hl_s, hl)
                oy += 22

        # ── Poison application overlay ──
        if applying_poison_step == "member":
            from src.party import WEAPONS
            alive = [m for m in party.members if m.is_alive()]
            popup_w = 320
            popup_h = 28 + len(alive) * 22 + 8
            popup_x = SCREEN_WIDTH // 2 - popup_w // 2
            popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

            pygame.draw.rect(self.screen, (20, 30, 20),
                             (popup_x, popup_y, popup_w, popup_h))
            pygame.draw.rect(self.screen, (80, 200, 80),
                             (popup_x, popup_y, popup_w, popup_h), 2)

            title = f"APPLY {applying_poison_item or 'POISON'}"
            self._u3_text(title, popup_x + 10, popup_y + 6,
                          (80, 220, 80), fm)
            oy = popup_y + 28
            for mi, m in enumerate(alive):
                sel = (mi == applying_poison_cursor)
                prefix = "> " if sel else "  "
                cls_ok = m.char_class in ("Thief", "Ranger", "Alchemist")
                label = f"{prefix}{m.name} ({m.char_class})"
                if cls_ok:
                    col = self._U3_WHITE if sel else self._U3_LTBLUE
                else:
                    col = (140, 100, 100) if sel else (100, 70, 70)
                self._u3_text(label, popup_x + 10, oy, col, fm)
                if sel:
                    hl = pygame.Rect(popup_x + 4, oy - 1,
                                     popup_w - 8, 20)
                    hl_s = pygame.Surface((hl.w, hl.h),
                                          pygame.SRCALPHA)
                    hl_s.fill((255, 255, 255, 25))
                    self.screen.blit(hl_s, hl)
                oy += 22

        elif applying_poison_step == "slot":
            from src.party import WEAPONS
            member = applying_poison_member
            slots = []
            for slot in ("right_hand", "left_hand"):
                wp_name = member.equipped.get(slot) if member else None
                if wp_name and wp_name != "Fists":
                    slot_label = "RIGHT HAND" if slot == "right_hand" else "LEFT HAND"
                    slots.append((slot_label, wp_name))
            popup_w = 320
            popup_h = 28 + max(len(slots), 1) * 22 + 8
            popup_x = SCREEN_WIDTH // 2 - popup_w // 2
            popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

            pygame.draw.rect(self.screen, (20, 30, 20),
                             (popup_x, popup_y, popup_w, popup_h))
            pygame.draw.rect(self.screen, (80, 200, 80),
                             (popup_x, popup_y, popup_w, popup_h), 2)

            title = f"WHICH WEAPON?"
            self._u3_text(title, popup_x + 10, popup_y + 6,
                          (80, 220, 80), fm)
            oy = popup_y + 28
            for si, (slot_label, wp_name) in enumerate(slots):
                sel = (si == applying_poison_cursor)
                prefix = "> " if sel else "  "
                label = f"{prefix}{slot_label}: {wp_name}"
                col = self._U3_WHITE if sel else self._U3_LTBLUE
                self._u3_text(label, popup_x + 10, oy, col, fm)
                if sel:
                    hl = pygame.Rect(popup_x + 4, oy - 1,
                                     popup_w - 8, 20)
                    hl_s = pygame.Surface((hl.w, hl.h),
                                          pygame.SRCALPHA)
                    hl_s.fill((255, 255, 255, 25))
                    self.screen.blit(hl_s, hl)
                oy += 22

        # ── Bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        if applying_poison_step:
            self._u3_text(
                "[UP/DN] SELECT  [ENTER] CONFIRM  [ESC] CANCEL",
                8, bar_y + 5, self._U3_BLUE)
        elif choosing_heal_target:
            self._u3_text(
                "[UP/DN] SELECT  [ENTER] HEAL  [ESC] CANCEL",
                8, bar_y + 5, self._U3_BLUE)
        elif showing_brew_list:
            if brew_list_items:
                self._u3_text(
                    "[UP/DN] SELECT  [ENTER] BREW  [ESC] CANCEL",
                    8, bar_y + 5, self._U3_BLUE)
            else:
                self._u3_text(
                    "[ESC] BACK",
                    8, bar_y + 5, self._U3_BLUE)
        elif showing_spell_list:
            if spell_list_items:
                self._u3_text(
                    "[UP/DN] SELECT  [ENTER] CAST  [ESC] CANCEL",
                    8, bar_y + 5, self._U3_BLUE)
            else:
                self._u3_text(
                    "[ESC] BACK",
                    8, bar_y + 5, self._U3_BLUE)
        elif action_menu:
            self._u3_text("[UP/DN] SELECT  [ENTER] CONFIRM  [ESC] CANCEL",
                          8, bar_y + 5, self._U3_BLUE)
        else:
            self._u3_text(
                "[UP/DN] SELECT  [ENTER] ACTION  [1-4] CHARACTER  [ESC] BACK",
                8, bar_y + 5, self._U3_BLUE)

    # ═══════════════════════════════════════════════════════════════
    # TIME-OF-DAY DARKNESS OVERLAY  (drawn on overworld map)
    # ═══════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════
    # SEASONAL WEATHER OVERLAYS
    # ═══════════════════════════════════════════════════════════════

    # Tile types that receive snow coverage
    _SNOW_TILES = None  # lazily populated from settings on first call

    def _draw_snow_overlay(self, tile_map, ts, cols, rows, off_c, off_r, clock):
        """Scatter subtle white pixel flecks over eligible overworld tiles.

        Called during winter months (December, January, February).
        Draws only individual 1px white dots — no washes or tints —
        so the underlying tile art stays clearly visible.

        Parameters
        ----------
        tile_map : TileMap
        ts       : int — tile size in pixels
        cols, rows : int — visible grid dimensions
        off_c, off_r : int — camera offset in world-tile coords
        clock    : GameClock
        """
        # Lazy-init the set of tile IDs that receive snow
        if self._SNOW_TILES is None:
            from src.settings import (
                TILE_GRASS, TILE_FOREST, TILE_MOUNTAIN,
                TILE_PATH, TILE_SAND, TILE_BRIDGE,
            )
            Renderer._SNOW_TILES = frozenset([
                TILE_GRASS, TILE_FOREST, TILE_MOUNTAIN,
                TILE_PATH, TILE_SAND, TILE_BRIDGE,
            ])

        month = clock.month_index  # 0=Jan, 11=Dec
        # More flecks in deep winter, fewer at the edges
        if month == 0:     # January
            flecks_per_tile = 6
        elif month == 1:   # February
            flecks_per_tile = 4
        elif month == 11:  # December
            flecks_per_tile = 3
        else:
            return  # not winter

        snow = pygame.Surface((cols * ts, rows * ts), pygame.SRCALPHA)

        for sr in range(rows):
            for sc in range(cols):
                wc = sc + off_c
                wr = sr + off_r
                tid = tile_map.get_tile(wc, wr)
                if tid not in self._SNOW_TILES:
                    continue

                px = sc * ts
                py = sr * ts
                seed = wc * 374761 + wr * 668265

                for i in range(flecks_per_tile):
                    s = seed + i * 7919
                    h = ((s ^ (s >> 13)) * 1274126177) & 0x7FFFFFFF
                    sz = 1 + (h >> 4) % 3  # 1px, 2px, or 3px flecks
                    dx = h % (ts - sz - 1) + 1
                    dy = (h >> 10) % (ts - sz - 1) + 1
                    a = 220 + (h >> 20) % 36  # alpha 220-255
                    snow.fill((255, 255, 255, a), (px + dx, py + dy, sz, sz))

        self.screen.blit(snow, (0, 0))

    def _draw_overworld_darkness(self, clock, party_sc, party_sr, ts, cols, rows,
                                 has_light=False, force_night=False,
                                 extra_lights=None):
        """Overlay darkness on the overworld map based on the time of day.

        During dusk/dawn the map is lightly dimmed with a warm/cool tint
        and a generous visibility radius around the party.  At night a
        deeper darkness closes in, leaving only a small lit circle around
        the party.  Having an equipped light source (torch) expands the
        visible radius at night.

        Parameters
        ----------
        clock : GameClock
        party_sc, party_sr : int
            Party position in *screen-tile* coordinates.
        ts : int
            Tile size in pixels.
        cols, rows : int
            Visible tile grid dimensions.
        has_light : bool
            Whether the party has an active light source equipped.
        """
        # Determine darkness parameters based on time phase.
        # light_radius = how many tiles around party stay fully lit.
        # fade_tiles   = gradient band width in tiles.
        # max_alpha    = darkness level for tiles beyond the lit area.
        # tint         = (R, G, B) colour tint blended into the darkness.
        if force_night:
            # Forced darkness (e.g. Keys of Shadow) — always full night
            # regardless of the clock phase.  This keeps the town dark
            # through dusk/dawn/day until the quest is complete.
            light_bonus = 3.0 if has_light else 0.0
            light_radius = 1.0 + light_bonus
            fade_tiles = 1.5
            max_alpha = 255
            tint = (0, 0, 0)
        elif clock.is_dusk:
            light_radius = 10.0
            fade_tiles = 4.0
            max_alpha = 100
            tint = (20, 10, 40)       # warm purple dusk
        elif clock.is_dawn:
            light_radius = 10.0
            fade_tiles = 4.0
            max_alpha = 80
            tint = (40, 20, 10)       # warm orange dawn
        elif clock.is_night:
            # Night is pitch black except for one tile around the party.
            # A torch expands visibility to a few more tiles.
            light_bonus = 3.0 if has_light else 0.0
            light_radius = 1.0 + light_bonus
            fade_tiles = 1.5
            max_alpha = 255                        # completely dark
            tint = (0, 0, 0)                       # pure black
        else:
            return  # daytime — nothing to draw

        fog = pygame.Surface((cols * ts, rows * ts), pygame.SRCALPHA)

        fade_end = light_radius + fade_tiles

        # Build list of all light sources: (screen_col, screen_row, radius, fade)
        all_lights = [(party_sc, party_sr, light_radius, fade_tiles)]
        if extra_lights:
            for el in extra_lights:
                all_lights.append(el)

        for sr in range(rows):
            for sc in range(cols):
                # Find the closest effective distance across all light sources
                best_t = 999.0  # normalised distance (0 = fully lit, >=1 = full dark)
                for lsc, lsr, lr, lf in all_lights:
                    dx = sc - lsc
                    dy = sr - lsr
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist <= lr:
                        best_t = 0.0
                        break
                    elif lf > 0:
                        t_val = (dist - lr) / lf
                        if t_val < best_t:
                            best_t = t_val

                if best_t <= 0.0:
                    continue  # fully lit
                elif best_t >= 1.0:
                    alpha = max_alpha
                else:
                    alpha = int(max_alpha * best_t)

                alpha = max(0, min(255, alpha))
                r = tint[0]
                g = tint[1]
                b = tint[2]
                rect = pygame.Rect(sc * ts, sr * ts, ts, ts)
                fog.fill((r, g, b, alpha), rect)

        self.screen.blit(fog, (0, 0))

    # ═══════════════════════════════════════════════════════════════
    # PUSH SPELL EXPANDING-WAVE ANIMATION  (drawn on overworld map)
    # ═══════════════════════════════════════════════════════════════

    def _draw_push_spell_wave(self, anim, repel_effect,
                              party, ts, cols, rows, off_c, off_r):
        """Draw the Push spell visual effect on the overworld map.

        Two phases:
        1. **Burst** – concentric rings expand outward from the party
           (plays during the first ~1.2 s after casting).
        2. **Aura** – a pulsing ring at the repel radius that persists for
           the full spell duration, gradually fading as steps run out.
        """
        max_radius_tiles = anim["max_radius"]
        elapsed = anim.get("elapsed_ms", 0.0)
        burst_timer = anim.get("burst_timer", 0)
        burst_dur = anim.get("burst_duration", 1200)

        # Party screen position (centre of tile)
        psc = party.col - off_c
        psr = party.row - off_r
        cx = psc * ts + ts // 2
        cy = psr * ts + ts // 2

        map_w = cols * ts
        map_h = rows * ts
        surf = pygame.Surface((map_w, map_h), pygame.SRCALPHA)

        max_px = max_radius_tiles * ts

        # ── Phase 1: initial expanding burst ──
        if burst_timer > 0:
            progress = 1.0 - (burst_timer / burst_dur)  # 0 → 1

            # Concentric expanding rings
            num_rings = 4
            for i in range(num_rings):
                ring_delay = i * 0.15
                if progress <= ring_delay:
                    continue
                ring_progress = (progress - ring_delay) / (1.0 - ring_delay)
                ring_progress = max(0.0, min(1.0, ring_progress))

                ring_r = int(ring_progress * max_px)
                if ring_r < 2:
                    continue

                alpha_base = int(200 * (1.0 - ring_progress * 0.7))
                if progress > 0.7:
                    alpha_base = int(
                        alpha_base * (1.0 - (progress - 0.7) / 0.3))
                alpha_base = max(0, min(255, alpha_base))
                if alpha_base <= 0:
                    continue

                brightness = 1.0 - (i * 0.15)
                color = (int(255 * brightness),
                         int(220 * brightness),
                         int(80 * brightness),
                         alpha_base)
                thickness = max(2, 4 - i)
                pygame.draw.circle(surf, color, (cx, cy), ring_r, thickness)

            # Radial rays
            num_rays = 8
            for j in range(num_rays):
                angle = (j / num_rays) * math.pi * 2
                ray_progress = max(0.0, min(1.0, progress * 1.2))
                ray_len = int(ray_progress * max_px)
                if ray_len < 4:
                    continue
                ray_alpha = int(120 * (1.0 - progress))
                if ray_alpha <= 0:
                    continue
                ex = cx + int(math.cos(angle) * ray_len)
                ey = cy + int(math.sin(angle) * ray_len)
                steps = max(1, ray_len // 6)
                for s in range(steps):
                    t = s / steps
                    px = int(cx + (ex - cx) * t)
                    py = int(cy + (ey - cy) * t)
                    dot_alpha = int(ray_alpha * (1.0 - t * 0.6))
                    dot_r = max(1, int(3 * (1.0 - t * 0.5)))
                    pygame.draw.circle(
                        surf, (255, 230, 120, dot_alpha),
                        (px, py), dot_r)

        # ── Phase 2: persistent pulsing aura (while repel effect active) ──
        if repel_effect:
            remaining = repel_effect["steps_remaining"]
            total = repel_effect.get("total_steps", remaining)
            life_frac = remaining / max(1, total)  # 1 → 0 over lifetime

            # Pulsing phase driven by wall-clock elapsed time
            pulse = (math.sin(elapsed * 0.005) + 1.0) * 0.5  # 0-1 oscillation

            # Outer boundary ring — pulsing alpha, fading with remaining steps
            base_alpha = int(100 * life_frac)
            ring_alpha = int(base_alpha * (0.5 + 0.5 * pulse))
            ring_alpha = max(0, min(255, ring_alpha))
            if ring_alpha > 0:
                color = (255, 220, 80, ring_alpha)
                pygame.draw.circle(surf, color, (cx, cy), max_px, 2)

            # Inner pulsing filled glow
            glow_alpha = int(30 * life_frac * (0.4 + 0.6 * pulse))
            glow_alpha = max(0, min(255, glow_alpha))
            if glow_alpha > 0:
                glow_color = (255, 230, 120, glow_alpha)
                pygame.draw.circle(surf, glow_color, (cx, cy), max_px)

            # Orbiting sparkle dots along the radius
            num_dots = 6
            orbit_speed = elapsed * 0.002
            for k in range(num_dots):
                angle = orbit_speed + (k / num_dots) * math.pi * 2
                dx = int(math.cos(angle) * max_px)
                dy = int(math.sin(angle) * max_px)
                dot_alpha = int(160 * life_frac * (0.5 + 0.5 * pulse))
                dot_alpha = max(0, min(255, dot_alpha))
                if dot_alpha > 0:
                    pygame.draw.circle(
                        surf, (255, 255, 200, dot_alpha),
                        (cx + dx, cy + dy), 3)

            # Steps remaining indicator text
            steps_text = f"PUSH: {remaining}"
            txt_surf = self.font_small.render(steps_text, True,
                                              (255, 220, 80))
            txt_alpha = int(200 * life_frac)
            txt_surf.set_alpha(txt_alpha)
            surf.blit(txt_surf, (cx - txt_surf.get_width() // 2,
                                 cy - max_px - 18))

        self.screen.blit(surf, (0, 0))

    # ═══════════════════════════════════════════════════════════════
    # USE-ITEM ANIMATION OVERLAY  (drawn on top of party inventory)
    # ═══════════════════════════════════════════════════════════════

    def draw_use_item_animation(self, party, anim):
        """Draw a healing / rest animation overlay on the party inventory screen.

        *anim* is a dict with keys:
            effect   – "rest", "heal_hp", "heal_mp", "cure_poison", etc.
            timer    – remaining ms  (starts at duration, ticks down)
            duration – total ms
            text     – short feedback string like "+12 HP"
        """
        if not anim or anim["timer"] <= 0:
            return

        t = anim["timer"]
        dur = anim["duration"]
        progress = 1.0 - (t / dur)          # 0 → 1 over lifetime
        effect = anim.get("effect", "rest")

        # ── Layout constants matching draw_party_inventory_u3 ──
        from src.settings import SCREEN_WIDTH, SCREEN_HEIGHT
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT
        left_w = int(sw * 0.56)
        right_w = sw - left_w - 4
        right_x = left_w + 2
        title_h = 30
        panel_y = title_h + 2
        rx = right_x + 10
        ry = panel_y + 10 + 20       # skip "PARTY [1-4]" header

        char_card_h = 50

        # ── Pick colours per effect type ──
        if effect == "rest":
            glow_color = (60, 220, 120)       # green glow
            particle_color = (120, 255, 180)
            text_color = (100, 255, 160)
        elif effect == "heal_hp":
            glow_color = (60, 220, 120)
            particle_color = (120, 255, 180)
            text_color = (100, 255, 160)
        elif effect == "heal_mp":
            glow_color = (80, 140, 255)       # blue glow
            particle_color = (140, 200, 255)
            text_color = (120, 180, 255)
        elif effect == "cure_poison":
            glow_color = (255, 255, 100)      # yellow glow
            particle_color = (255, 255, 200)
            text_color = (255, 255, 140)
        elif effect == "tinker":
            glow_color = (140, 200, 140)      # crafting green
            particle_color = (180, 240, 140)
            text_color = (140, 220, 140)
        elif effect == "tinker_fail":
            glow_color = (200, 100, 60)       # dull orange-red
            particle_color = (180, 120, 80)
            text_color = (200, 120, 100)
        else:
            glow_color = (200, 200, 200)
            particle_color = (255, 255, 255)
            text_color = (220, 220, 220)

        # ── Phase timing ──
        # Phase 1 (0-40%): glow sweeps across character cards
        # Phase 2 (20-80%): rising particles + HP numbers
        # Phase 3 (60-100%): fade out

        fade_alpha = 1.0
        if progress > 0.75:
            fade_alpha = max(0.0, 1.0 - (progress - 0.75) / 0.25)

        # ── Glow sweep over character cards ──
        if progress < 0.6:
            sweep = min(1.0, progress / 0.4)   # 0→1 over first 40%
            glow_a = int(60 * fade_alpha * (0.5 + 0.5 * math.sin(progress * 12)))
            glow_s = pygame.Surface((right_w - 20, int(char_card_h * len(party.members) * sweep)),
                                    pygame.SRCALPHA)
            glow_s.fill((*glow_color, max(0, min(255, glow_a))))
            self.screen.blit(glow_s, (rx, ry))

        # ── Rising sparkle particles ──
        if 0.1 < progress < 0.9:
            sparkle_phase = (progress - 0.1) / 0.8    # 0→1
            n_particles = 12
            for i in range(n_particles):
                seed = i * 137.508  # golden angle spread
                px_base = rx + 10 + ((i * 23) % (right_w - 40))
                py_base = ry + char_card_h * len(party.members)
                # Rise upward
                rise = sparkle_phase * (40 + (i % 5) * 20)
                px = px_base + int(8 * math.sin(seed + progress * 8))
                py = int(py_base - rise)
                # Fade in/out
                p_alpha = int(180 * fade_alpha * (0.5 + 0.5 * math.sin(seed + progress * 10)))
                p_alpha = max(0, min(255, p_alpha))
                sz = 2 + int(2 * ((i % 3) / 2))
                spark_s = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
                pygame.draw.circle(spark_s, (*particle_color, p_alpha), (sz, sz), sz)
                self.screen.blit(spark_s, (px - sz, py - sz))

        # ── Per-character "+" indicators rising from each card ──
        if 0.15 < progress < 0.85:
            ind_alpha = int(220 * fade_alpha)
            fm = self.font_med
            for mi, member in enumerate(party.members):
                if member.hp <= 0 and effect != "cure_poison":
                    continue
                cy = ry + mi * char_card_h + char_card_h // 2
                # Float upward
                float_y = int((progress - 0.15) * 40)
                txt_y = cy - float_y
                if effect == "rest":
                    indicator = "+HP +MP"
                elif effect == "heal_hp":
                    indicator = "+HP"
                elif effect == "heal_mp":
                    indicator = "+MP"
                elif effect == "cure_poison":
                    indicator = "CURED"
                else:
                    indicator = "+"
                ind_surf = fm.render(indicator, True, text_color)
                ind_surf.set_alpha(max(0, min(255, ind_alpha)))
                self.screen.blit(ind_surf,
                                 (rx + right_w - 80, txt_y))

        # ── Central feedback text (fades in then out) ──
        text = anim.get("text", "")
        if text and 0.2 < progress < 0.95:
            text_alpha = int(255 * fade_alpha)
            f = self.font
            ts = f.render(text, True, text_color)
            ts.set_alpha(max(0, min(255, text_alpha)))
            tx = sw // 2 - ts.get_width() // 2
            ty = sh // 2 - ts.get_height() // 2
            # Dark backdrop
            pad = 12
            bg = pygame.Surface((ts.get_width() + pad * 2, ts.get_height() + pad * 2),
                                pygame.SRCALPHA)
            bg.fill((0, 0, 0, min(255, int(180 * fade_alpha))))
            self.screen.blit(bg, (tx - pad, ty - pad))
            # Border
            pygame.draw.rect(self.screen,
                             (*glow_color, min(255, int(160 * fade_alpha))),
                             (tx - pad, ty - pad,
                              ts.get_width() + pad * 2, ts.get_height() + pad * 2), 2)
            self.screen.blit(ts, (tx, ty))

    # ═══════════════════════════════════════════════════════════════
    # LEVEL-UP ANIMATION OVERLAY
    # ═══════════════════════════════════════════════════════════════

    def draw_level_up_animation(self, entry):
        """Draw a celebratory level-up banner on the exploration screen.

        *entry* is a dict with keys:
            name     – character name
            level    – new level reached
            msg      – full message like "Kira reached Level 4! HP+15 MP+3"
            timer    – remaining ms
            duration – total ms
        """
        import math as _math

        if not entry or entry["timer"] <= 0:
            return

        from src.settings import SCREEN_WIDTH, SCREEN_HEIGHT
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT

        t = entry["timer"]
        dur = entry["duration"]
        progress = 1.0 - (t / dur)  # 0→1

        # Fade in during first 15%, hold, fade out during last 15%
        if progress < 0.15:
            alpha = progress / 0.15
        elif progress > 0.85:
            alpha = (1.0 - progress) / 0.15
        else:
            alpha = 1.0
        alpha = max(0.0, min(1.0, alpha))

        # ── Banner background ──
        banner_w = min(sw - 40, 380)
        banner_h = 72
        bx = (sw - banner_w) // 2
        # Slide in from top
        target_y = sh // 3 - banner_h // 2
        if progress < 0.1:
            by = int(-banner_h + (target_y + banner_h) * (progress / 0.1))
        else:
            by = target_y

        bg = pygame.Surface((banner_w, banner_h), pygame.SRCALPHA)
        bg_alpha = int(210 * alpha)
        bg.fill((10, 5, 30, bg_alpha))
        self.screen.blit(bg, (bx, by))

        # ── Golden border with pulse ──
        pulse = 0.7 + 0.3 * _math.sin(progress * _math.pi * 8)
        border_c = (
            int(255 * pulse * alpha),
            int(200 * pulse * alpha),
            int(50 * pulse * alpha),
            int(255 * alpha)
        )
        border_s = pygame.Surface((banner_w, banner_h), pygame.SRCALPHA)
        pygame.draw.rect(border_s, border_c,
                         (0, 0, banner_w, banner_h), 3)
        self.screen.blit(border_s, (bx, by))

        # ── "LEVEL UP!" title ──
        title_text = "LEVEL UP!"
        title_pulse = 0.8 + 0.2 * _math.sin(progress * _math.pi * 6)
        title_r = int(255 * title_pulse)
        title_g = int(220 * title_pulse)
        title_b = 50
        title_surf = self.font.render(title_text, True,
                                       (title_r, title_g, title_b))
        title_surf.set_alpha(int(255 * alpha))
        tx = bx + (banner_w - title_surf.get_width()) // 2
        ty = by + 8
        self.screen.blit(title_surf, (tx, ty))

        # ── Character info line ──
        msg = entry.get("msg", "")
        info_surf = self.font_small.render(msg, True, (220, 220, 255))
        info_surf.set_alpha(int(255 * alpha))
        ix = bx + (banner_w - info_surf.get_width()) // 2
        iy = by + 36
        self.screen.blit(info_surf, (ix, iy))

        # ── Sparkle particles rising from banner ──
        import time as _time
        now = _time.time()
        num_sparkles = 12
        for i in range(num_sparkles):
            phase = now * 2.5 + i * (2 * _math.pi / num_sparkles)
            sx = bx + int((i / num_sparkles) * banner_w)
            sy = by + banner_h - int(
                (now * 30 + i * 17) % (banner_h + 20))
            spark_alpha = int(180 * alpha * (
                0.5 + 0.5 * _math.sin(phase)))
            if spark_alpha > 10:
                spark_s = pygame.Surface((4, 4), pygame.SRCALPHA)
                sc = (255, 230, 100, spark_alpha)
                pygame.draw.circle(spark_s, sc, (2, 2), 2)
                self.screen.blit(spark_s, (sx, sy))

        # ── Star bursts at corners ──
        for corner_x, corner_y in ((bx + 6, by + 6),
                                    (bx + banner_w - 7, by + 6),
                                    (bx + 6, by + banner_h - 7),
                                    (bx + banner_w - 7, by + banner_h - 7)):
            star_a = int(200 * alpha * (
                0.5 + 0.5 * _math.sin(now * 4 + corner_x * 0.1)))
            if star_a > 20:
                star_s = pygame.Surface((8, 8), pygame.SRCALPHA)
                pygame.draw.circle(star_s, (255, 255, 200, star_a),
                                   (4, 4), 3)
                pygame.draw.circle(star_s, (255, 255, 255, min(255, star_a + 40)),
                                   (4, 4), 1)
                self.screen.blit(star_s, (corner_x - 4, corner_y - 4))

    # ═══════════════════════════════════════════════════════════════
    # ITEM EXAMINATION OVERLAY
    # ═══════════════════════════════════════════════════════════════

    # ── Character tile helpers ─────────────────────────────────

    def _load_cc_tile(self, file_path):
        """Load a character tile image by project-relative path.

        Returns a pygame Surface or None. Results are cached in
        ``self._cc_tile_cache``.
        """
        if not hasattr(self, '_cc_tile_cache'):
            self._cc_tile_cache = {}
        if file_path in self._cc_tile_cache:
            return self._cc_tile_cache[file_path]
        if not file_path:
            self._cc_tile_cache[file_path] = None
            return None
        import os
        project_root = os.path.dirname(os.path.dirname(__file__))
        abs_path = os.path.join(project_root, file_path)
        if not os.path.isfile(abs_path):
            self._cc_tile_cache[file_path] = None
            return None
        try:
            raw = pygame.image.load(abs_path).convert_alpha()
            # Make black pixels transparent (common for U4 tiles)
            w, h = raw.get_size()
            for px in range(w):
                for py in range(h):
                    r, g, b, a = raw.get_at((px, py))
                    if r == 0 and g == 0 and b == 0 and a > 0:
                        raw.set_at((px, py), (0, 0, 0, 0))
            self._cc_tile_cache[file_path] = raw
        except Exception:
            self._cc_tile_cache[file_path] = None
        return self._cc_tile_cache.get(file_path)

    def _draw_cc_tile(self, file_path, cx, cy, size):
        """Draw a character tile centered at (cx, cy) scaled to size."""
        raw = self._load_cc_tile(file_path)
        if raw is None:
            # Fallback: draw a placeholder
            pygame.draw.rect(self.screen, (60, 60, 80),
                             (cx - size // 2, cy - size // 2, size, size))
            self._u3_text("?", cx - 4, cy - 6, (120, 120, 140))
            return
        scaled = pygame.transform.scale(raw, (size, size))
        self.screen.blit(scaled, (cx - size // 2, cy - size // 2))

    def _draw_item_icon(self, cx, cy, icon_type, size=64):
        """Draw a pixel-art icon for an item type, centered at (cx, cy)."""
        s = size
        hs = s // 2
        x0 = cx - hs
        y0 = cy - hs

        # Colors
        STEEL = (180, 190, 200)
        DARK_STEEL = (120, 130, 140)
        BROWN = (140, 90, 40)
        DARK_BROWN = (100, 60, 25)
        GOLD = (220, 180, 60)
        RED = (200, 60, 60)
        GREEN = (60, 180, 60)
        BLUE = (80, 120, 220)
        LIGHT_BLUE = (140, 180, 255)
        WHITE = (240, 240, 240)
        ORANGE = (255, 170, 85)
        PURPLE = (160, 80, 200)
        YELLOW = (255, 220, 80)

        if icon_type == "sword":
            # Blade
            pygame.draw.line(self.screen, STEEL, (cx - 2, cy + hs - 8), (cx + 2, cy - hs + 6), 4)
            pygame.draw.line(self.screen, WHITE, (cx - 1, cy + hs - 12), (cx + 1, cy - hs + 8), 2)
            # Crossguard
            pygame.draw.line(self.screen, GOLD, (cx - 10, cy + 4), (cx + 10, cy + 4), 4)
            # Grip
            pygame.draw.line(self.screen, BROWN, (cx, cy + 6), (cx, cy + hs - 6), 4)
            # Pommel
            pygame.draw.circle(self.screen, GOLD, (cx, cy + hs - 4), 4)

        elif icon_type == "axe":
            # Handle
            pygame.draw.line(self.screen, BROWN, (cx, cy + hs - 6), (cx, cy - hs + 10), 4)
            # Axe head
            pts = [(cx - 2, cy - hs + 10), (cx - 14, cy - hs + 20),
                   (cx - 14, cy - 4), (cx - 2, cy + 4)]
            pygame.draw.polygon(self.screen, STEEL, pts)
            pygame.draw.polygon(self.screen, DARK_STEEL, pts, 2)
            # Edge highlight
            pygame.draw.line(self.screen, WHITE, (cx - 14, cy - hs + 20), (cx - 14, cy - 4), 2)

        elif icon_type == "bow":
            # Bow arc
            pygame.draw.arc(self.screen, BROWN,
                           (cx - 16, cy - hs + 4, 24, s - 8),
                           -1.2, 1.2, 3)
            # String
            pygame.draw.line(self.screen, (200, 200, 200),
                           (cx + 4, cy - hs + 10), (cx + 4, cy + hs - 10), 1)
            # Arrow
            pygame.draw.line(self.screen, STEEL, (cx + 4, cy - hs + 14), (cx + 4, cy + hs - 14), 2)
            # Arrowhead
            pygame.draw.polygon(self.screen, STEEL,
                               [(cx + 4, cy - hs + 10), (cx + 1, cy - hs + 18), (cx + 7, cy - hs + 18)])

        elif icon_type == "dagger":
            # Blade
            pygame.draw.line(self.screen, STEEL, (cx, cy - hs + 8), (cx, cy + 6), 3)
            pygame.draw.line(self.screen, WHITE, (cx, cy - hs + 10), (cx, cy + 2), 1)
            # Guard
            pygame.draw.line(self.screen, GOLD, (cx - 7, cy + 8), (cx + 7, cy + 8), 3)
            # Handle
            pygame.draw.line(self.screen, DARK_BROWN, (cx, cy + 10), (cx, cy + hs - 6), 4)

        elif icon_type == "mace":
            # Handle
            pygame.draw.line(self.screen, BROWN, (cx, cy + hs - 6), (cx, cy - 6), 4)
            # Head
            pygame.draw.circle(self.screen, STEEL, (cx, cy - 14), 12)
            pygame.draw.circle(self.screen, DARK_STEEL, (cx, cy - 14), 12, 2)
            # Flanges
            for angle_off in [-8, 0, 8]:
                pygame.draw.circle(self.screen, WHITE, (cx + angle_off, cy - 20), 3)

        elif icon_type == "spear":
            # Shaft
            pygame.draw.line(self.screen, BROWN, (cx, cy + hs - 4), (cx, cy - hs + 14), 3)
            # Spearhead
            pts = [(cx, cy - hs + 6), (cx - 6, cy - hs + 18), (cx + 6, cy - hs + 18)]
            pygame.draw.polygon(self.screen, STEEL, pts)
            pygame.draw.polygon(self.screen, WHITE, pts, 1)

        elif icon_type == "halberd":
            # Shaft
            pygame.draw.line(self.screen, BROWN, (cx, cy + hs - 4), (cx, cy - hs + 8), 3)
            # Axe blade on side
            pts = [(cx, cy - hs + 12), (cx - 14, cy - hs + 20),
                   (cx - 12, cy - 2), (cx, cy + 2)]
            pygame.draw.polygon(self.screen, STEEL, pts)
            pygame.draw.polygon(self.screen, DARK_STEEL, pts, 1)
            # Spear tip
            pts2 = [(cx, cy - hs + 6), (cx - 4, cy - hs + 14), (cx + 4, cy - hs + 14)]
            pygame.draw.polygon(self.screen, STEEL, pts2)

        elif icon_type == "gloves":
            # Left glove
            pygame.draw.rect(self.screen, STEEL, (cx - 16, cy - 10, 14, 20), border_radius=3)
            pygame.draw.rect(self.screen, DARK_STEEL, (cx - 16, cy - 10, 14, 20), 2, border_radius=3)
            # Right glove
            pygame.draw.rect(self.screen, STEEL, (cx + 2, cy - 10, 14, 20), border_radius=3)
            pygame.draw.rect(self.screen, DARK_STEEL, (cx + 2, cy - 10, 14, 20), 2, border_radius=3)
            # Fingers
            for gx in [cx - 12, cx - 8, cx + 6, cx + 10]:
                pygame.draw.rect(self.screen, STEEL, (gx, cy - 16, 4, 8), border_radius=2)
            # Glow
            pygame.draw.circle(self.screen, (100, 150, 255, 128), (cx, cy), 18, 1)

        elif icon_type == "armor_light":
            # Torso shape
            pts = [(cx - 12, cy - 16), (cx + 12, cy - 16),
                   (cx + 16, cy + 6), (cx + 10, cy + 20),
                   (cx - 10, cy + 20), (cx - 16, cy + 6)]
            pygame.draw.polygon(self.screen, BROWN, pts)
            pygame.draw.polygon(self.screen, DARK_BROWN, pts, 2)
            # Neck opening
            pygame.draw.arc(self.screen, DARK_BROWN,
                           (cx - 6, cy - 20, 12, 12), 0, 3.14, 2)
            # Stitching detail
            pygame.draw.line(self.screen, DARK_BROWN, (cx, cy - 14), (cx, cy + 16), 1)

        elif icon_type == "armor_heavy":
            # Torso plates
            pts = [(cx - 14, cy - 18), (cx + 14, cy - 18),
                   (cx + 18, cy + 4), (cx + 12, cy + 22),
                   (cx - 12, cy + 22), (cx - 18, cy + 4)]
            pygame.draw.polygon(self.screen, STEEL, pts)
            pygame.draw.polygon(self.screen, DARK_STEEL, pts, 2)
            # Plate lines
            pygame.draw.line(self.screen, DARK_STEEL, (cx - 12, cy - 6), (cx + 12, cy - 6), 1)
            pygame.draw.line(self.screen, DARK_STEEL, (cx - 14, cy + 6), (cx + 14, cy + 6), 1)
            # Neck guard
            pygame.draw.arc(self.screen, DARK_STEEL,
                           (cx - 8, cy - 24, 16, 14), 0, 3.14, 2)
            # Highlight
            pygame.draw.line(self.screen, WHITE, (cx - 4, cy - 14), (cx - 4, cy + 2), 1)

        elif icon_type == "potion":
            # Bottle body
            pygame.draw.ellipse(self.screen, BLUE, (cx - 10, cy - 4, 20, 24))
            pygame.draw.ellipse(self.screen, LIGHT_BLUE, (cx - 10, cy - 4, 20, 24), 2)
            # Neck
            pygame.draw.rect(self.screen, BLUE, (cx - 4, cy - 14, 8, 12))
            pygame.draw.rect(self.screen, LIGHT_BLUE, (cx - 4, cy - 14, 8, 12), 1)
            # Cork
            pygame.draw.rect(self.screen, BROWN, (cx - 5, cy - 18, 10, 6), border_radius=2)
            # Highlight
            pygame.draw.ellipse(self.screen, WHITE, (cx - 4, cy + 2, 6, 8), 1)

        elif icon_type == "herb":
            # Stem
            pygame.draw.line(self.screen, GREEN, (cx, cy + 16), (cx, cy - 4), 2)
            # Leaves
            pygame.draw.ellipse(self.screen, GREEN, (cx - 14, cy - 10, 14, 8))
            pygame.draw.ellipse(self.screen, GREEN, (cx, cy - 14, 14, 8))
            pygame.draw.ellipse(self.screen, GREEN, (cx - 8, cy - 20, 12, 8))
            # Highlight
            pygame.draw.ellipse(self.screen, (100, 220, 100), (cx - 12, cy - 9, 8, 4))
            pygame.draw.ellipse(self.screen, (100, 220, 100), (cx + 2, cy - 13, 8, 4))

        elif icon_type == "scroll":
            # Main body
            pygame.draw.rect(self.screen, (230, 210, 170), (cx - 12, cy - 16, 24, 32))
            # Top roll
            pygame.draw.ellipse(self.screen, (210, 190, 150), (cx - 14, cy - 20, 28, 10))
            # Bottom roll
            pygame.draw.ellipse(self.screen, (210, 190, 150), (cx - 14, cy + 12, 28, 10))
            # Text lines
            for ly in range(cy - 10, cy + 10, 5):
                pygame.draw.line(self.screen, (160, 140, 100),
                               (cx - 8, ly), (cx + 8, ly), 1)
            # Magic glow
            pygame.draw.rect(self.screen, PURPLE, (cx - 14, cy - 20, 28, 42), 1)

        elif icon_type == "torch":
            # Handle
            pygame.draw.rect(self.screen, BROWN, (cx - 3, cy, 6, 22))
            pygame.draw.rect(self.screen, DARK_BROWN, (cx - 3, cy, 6, 22), 1)
            # Flame base
            pygame.draw.ellipse(self.screen, ORANGE, (cx - 8, cy - 14, 16, 18))
            # Flame tip
            pygame.draw.polygon(self.screen, YELLOW,
                               [(cx, cy - 22), (cx - 5, cy - 10), (cx + 5, cy - 10)])
            # Flame core
            pygame.draw.ellipse(self.screen, YELLOW, (cx - 4, cy - 10, 8, 10))

        elif icon_type == "rope":
            # Coiled rope
            for i in range(4):
                oy = cy - 12 + i * 8
                pygame.draw.ellipse(self.screen, BROWN, (cx - 14, oy, 28, 10), 2)
            # End
            pygame.draw.line(self.screen, BROWN, (cx + 12, cy + 14), (cx + 16, cy + 22), 2)

        elif icon_type == "tool":
            # Pick body
            pygame.draw.line(self.screen, STEEL, (cx - 12, cy - 8), (cx + 12, cy - 8), 2)
            # Handle
            pygame.draw.line(self.screen, BROWN, (cx, cy - 6), (cx, cy + 18), 3)
            # Second pick
            pygame.draw.line(self.screen, STEEL, (cx - 8, cy - 4), (cx + 8, cy + 4), 2)
            # Ring
            pygame.draw.circle(self.screen, GOLD, (cx, cy - 10), 4, 1)

        elif icon_type == "bomb":
            # Body
            pygame.draw.circle(self.screen, (60, 60, 60), (cx, cy + 4), 14)
            pygame.draw.circle(self.screen, (80, 80, 80), (cx, cy + 4), 14, 2)
            # Fuse
            pygame.draw.line(self.screen, BROWN, (cx + 6, cy - 8), (cx + 12, cy - 18), 2)
            # Spark
            pygame.draw.circle(self.screen, YELLOW, (cx + 12, cy - 20), 4)
            pygame.draw.circle(self.screen, ORANGE, (cx + 12, cy - 20), 2)
            # Highlight
            pygame.draw.circle(self.screen, (100, 100, 100), (cx - 4, cy), 3)

        elif icon_type == "holy":
            # Vial
            pygame.draw.ellipse(self.screen, LIGHT_BLUE, (cx - 8, cy - 2, 16, 20))
            pygame.draw.ellipse(self.screen, WHITE, (cx - 8, cy - 2, 16, 20), 1)
            # Neck
            pygame.draw.rect(self.screen, LIGHT_BLUE, (cx - 3, cy - 12, 6, 12))
            # Cork
            pygame.draw.rect(self.screen, BROWN, (cx - 4, cy - 16, 8, 6), border_radius=2)
            # Cross symbol
            pygame.draw.line(self.screen, YELLOW, (cx, cy + 2), (cx, cy + 12), 2)
            pygame.draw.line(self.screen, YELLOW, (cx - 4, cy + 6), (cx + 4, cy + 6), 2)
            # Glow
            pygame.draw.circle(self.screen, (255, 255, 200), (cx, cy + 6), 10, 1)

        elif icon_type == "chest":
            # Treasure chest — based on the in-game chest tile art
            # Body
            body_w, body_h = 28, 18
            body_rect = pygame.Rect(cx - body_w // 2, cy - 2, body_w, body_h)
            pygame.draw.rect(self.screen, (140, 100, 30), body_rect)
            pygame.draw.rect(self.screen, (100, 70, 20), body_rect, 2)
            # Horizontal plank lines
            pygame.draw.line(self.screen, (120, 85, 25),
                           (cx - body_w // 2 + 2, cy + 5),
                           (cx + body_w // 2 - 2, cy + 5), 1)
            pygame.draw.line(self.screen, (120, 85, 25),
                           (cx - body_w // 2 + 2, cy + 11),
                           (cx + body_w // 2 - 2, cy + 11), 1)
            # Lid (arched top)
            lid_rect = pygame.Rect(cx - body_w // 2, cy - 14, body_w, 14)
            pygame.draw.rect(self.screen, (160, 115, 35), lid_rect)
            pygame.draw.rect(self.screen, (100, 70, 20), lid_rect, 2)
            # Lid arch highlight
            pygame.draw.line(self.screen, (180, 135, 50),
                           (cx - body_w // 2 + 3, cy - 12),
                           (cx + body_w // 2 - 3, cy - 12), 1)
            # Metal clasp/band across front
            pygame.draw.rect(self.screen, DARK_STEEL,
                            (cx - 2, cy - 14, 4, body_h + 14))
            pygame.draw.rect(self.screen, STEEL,
                            (cx - 2, cy - 14, 4, body_h + 14), 1)
            # Lock
            pygame.draw.circle(self.screen, GOLD, (cx, cy - 1), 4)
            pygame.draw.circle(self.screen, (180, 140, 40), (cx, cy - 1), 4, 1)
            pygame.draw.rect(self.screen, GOLD, (cx - 1, cy, 2, 3))
            # Corner rivets
            for rx_off, ry_off in [(-11, -10), (11, -10), (-11, 12), (11, 12)]:
                pygame.draw.circle(self.screen, GOLD, (cx + rx_off, cy + ry_off), 2)

        elif icon_type == "gem":
            # Diamond shape
            pts = [(cx, cy - 16), (cx + 14, cy), (cx, cy + 16), (cx - 14, cy)]
            pygame.draw.polygon(self.screen, LIGHT_BLUE, pts)
            pygame.draw.polygon(self.screen, WHITE, pts, 2)
            # Facet lines
            pygame.draw.line(self.screen, WHITE, (cx, cy - 16), (cx, cy + 16), 1)
            pygame.draw.line(self.screen, WHITE, (cx - 14, cy), (cx + 14, cy), 1)

        elif icon_type == "rock":
            # Rough stone shape
            pts = [(cx - 10, cy + 8), (cx - 14, cy - 2), (cx - 6, cy - 12),
                   (cx + 4, cy - 14), (cx + 14, cy - 4), (cx + 10, cy + 10)]
            pygame.draw.polygon(self.screen, (140, 130, 120), pts)
            pygame.draw.polygon(self.screen, (100, 95, 85), pts, 2)
            # Crack detail
            pygame.draw.line(self.screen, (100, 95, 85), (cx - 4, cy - 8), (cx + 2, cy + 4), 1)

        elif icon_type == "ammo":
            # Arrow / quiver
            for i in range(3):
                ox = -6 + i * 6
                # Shaft
                pygame.draw.line(self.screen, BROWN, (cx + ox, cy + hs - 8), (cx + ox, cy - hs + 8), 2)
                # Arrowhead
                pts = [(cx + ox, cy - hs + 4), (cx + ox - 3, cy - hs + 10), (cx + ox + 3, cy - hs + 10)]
                pygame.draw.polygon(self.screen, STEEL, pts)
                # Fletching
                pygame.draw.line(self.screen, RED, (cx + ox - 2, cy + hs - 10), (cx + ox, cy + hs - 6), 1)
                pygame.draw.line(self.screen, RED, (cx + ox + 2, cy + hs - 10), (cx + ox, cy + hs - 6), 1)

        elif icon_type == "artifact":
            # Glowing orb on a pedestal
            # Pedestal
            pygame.draw.rect(self.screen, DARK_STEEL, (cx - 6, cy + 4, 12, 10))
            pygame.draw.rect(self.screen, STEEL, (cx - 10, cy + 12, 20, 4))
            # Orb
            pygame.draw.circle(self.screen, PURPLE, (cx, cy - 4), 10)
            pygame.draw.circle(self.screen, (200, 140, 255), (cx - 3, cy - 7), 3)
            pygame.draw.circle(self.screen, (220, 200, 255), (cx, cy - 4), 10, 2)

        else:
            # Unknown — draw a question mark box
            pygame.draw.rect(self.screen, (60, 60, 80), (cx - 14, cy - 14, 28, 28), border_radius=4)
            pygame.draw.rect(self.screen, STEEL, (cx - 14, cy - 14, 28, 28), 2, border_radius=4)
            self._u3_text("?", cx - 4, cy - 6, WHITE, self.font)

    def draw_item_examine(self, item_name):
        """Draw a centered item examination popup overlay.

        Shows a pixel-art icon, item name, type, stats, and description.
        """
        from src.party import WEAPONS, ARMORS, ITEM_INFO

        fm = self.font_med
        f = self.font

        # Popup dimensions
        pw, ph = 340, 280
        px = (SCREEN_WIDTH - pw) // 2
        py = (SCREEN_HEIGHT - ph) // 2

        # Dim background
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        self.screen.blit(dim, (0, 0))

        # Popup box
        pygame.draw.rect(self.screen, (16, 16, 32), (px, py, pw, ph))
        pygame.draw.rect(self.screen, self._U3_LTBLUE, (px, py, pw, ph), 2)

        # ── Icon area (left side) ──
        icon_cx = px + 56
        icon_cy = py + 70
        # Icon background circle
        pygame.draw.circle(self.screen, (30, 30, 50), (icon_cx, icon_cy), 36)
        pygame.draw.circle(self.screen, (60, 60, 100), (icon_cx, icon_cy), 36, 1)

        info = ITEM_INFO.get(item_name, {})
        icon_type = info.get("icon", "gem")
        self._draw_item_icon(icon_cx, icon_cy, icon_type, 60)

        # ── Item name ──
        name_x = px + 110
        name_y = py + 14
        self._u3_text(item_name.upper(), name_x, name_y, self._U3_ORANGE, f)

        # ── Type and stats ──
        ty = name_y + 26
        if item_name in ARMORS:
            arm = ARMORS[item_name]
            self._u3_text("TYPE:", name_x, ty, self._U3_LTBLUE, fm)
            self._u3_text("ARMOR", name_x + 55, ty, self._U3_WHITE, fm)
            ty += 20
            self._u3_text("SLOT:", name_x, ty, self._U3_LTBLUE, fm)
            self._u3_text("BODY", name_x + 55, ty, (220, 220, 230), fm)
            ty += 20
            self._u3_text("EVASION:", name_x, ty, self._U3_LTBLUE, fm)
            self._u3_text(f"{arm['evasion']}%", name_x + 80, ty, self._U3_GREEN, fm)
        elif item_name in WEAPONS:
            wp = WEAPONS[item_name]
            wtype = "RANGED" if wp.get("ranged", False) else "MELEE"
            self._u3_text("TYPE:", name_x, ty, self._U3_LTBLUE, fm)
            self._u3_text(f"{wtype} WEAPON", name_x + 55, ty, self._U3_WHITE, fm)
            ty += 20
            self._u3_text("SLOT:", name_x, ty, self._U3_LTBLUE, fm)
            self._u3_text("RIGHT HAND", name_x + 55, ty, (220, 220, 230), fm)
            ty += 20
            self._u3_text("POWER:", name_x, ty, self._U3_LTBLUE, fm)
            pwr = wp["power"]
            pwr_color = self._U3_GREEN if pwr >= 7 else self._U3_ORANGE if pwr >= 4 else (220, 220, 230)
            self._u3_text(f"{pwr:d}", name_x + 65, ty, pwr_color, fm)
            if wp.get("throwable", False):
                ty += 20
                self._u3_text("NOTE:", name_x, ty, self._U3_LTBLUE, fm)
                self._u3_text("CONSUMABLE", name_x + 55, ty, self._U3_RED, fm)
        else:
            self._u3_text("TYPE:", name_x, ty, self._U3_LTBLUE, fm)
            self._u3_text("GENERAL ITEM", name_x + 55, ty, self._U3_WHITE, fm)
            ty += 20
            self._u3_text("NOT EQUIPPABLE", name_x, ty, (150, 150, 150), fm)

        # ── Description ──
        desc = info.get("desc", "A mysterious object of unknown origin.")
        desc_y = py + 140
        pygame.draw.line(self.screen, (60, 60, 100),
                        (px + 14, desc_y - 6), (px + pw - 14, desc_y - 6), 1)

        # Word wrap the description
        words = desc.split()
        lines = []
        current_line = ""
        max_chars = 38  # chars per line at font_med
        for word in words:
            test = current_line + (" " if current_line else "") + word
            if len(test) <= max_chars:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        for line in lines:
            self._u3_text(line, px + 18, desc_y, (200, 200, 210), fm)
            desc_y += 18

        # ── Rarity bar (based on power/evasion) ──
        bar_y = py + ph - 40
        pygame.draw.line(self.screen, (60, 60, 100),
                        (px + 14, bar_y - 6), (px + pw - 14, bar_y - 6), 1)
        # Determine rarity
        PURPLE = (160, 80, 200)
        rarity = "COMMON"
        rarity_color = self._U3_GRAY
        if item_name in WEAPONS:
            pwr = WEAPONS[item_name]["power"]
            if pwr >= 9:
                rarity, rarity_color = "LEGENDARY", PURPLE
            elif pwr >= 7:
                rarity, rarity_color = "RARE", self._U3_LTBLUE
            elif pwr >= 4:
                rarity, rarity_color = "UNCOMMON", self._U3_GREEN
        elif item_name in ARMORS:
            ev = ARMORS[item_name]["evasion"]
            if ev >= 65:
                rarity, rarity_color = "LEGENDARY", PURPLE
            elif ev >= 60:
                rarity, rarity_color = "RARE", self._U3_LTBLUE
            elif ev >= 56:
                rarity, rarity_color = "UNCOMMON", self._U3_GREEN
        self._u3_text("RARITY:", px + 18, bar_y, self._U3_LTBLUE, fm)
        self._u3_text(rarity, px + 80, bar_y, rarity_color, fm)

        # ── Dismiss hint ──
        self._u3_text("[ESC] CLOSE", px + pw - 100, py + ph - 20,
                      self._U3_BLUE, self.font_small)

    def draw_overworld_help_overlay(self):
        """Draw a full-screen overlay showing all overworld controls."""
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 200))
        self.screen.blit(dim, (0, 0))

        margin = 60
        px, py = margin, margin
        pw = SCREEN_WIDTH - margin * 2
        ph = SCREEN_HEIGHT - margin * 2

        pygame.draw.rect(self.screen, (12, 12, 24), (px, py, pw, ph))
        pygame.draw.rect(self.screen, self._U3_LTBLUE, (px, py, pw, ph), 2)

        self._u3_text("OVERWORLD CONTROLS", px + pw // 2 - 80, py + 10,
                       self._U3_ORANGE, self.font)

        f = self.font_small
        lh = 18
        col1_x = px + 20
        col2_x = px + pw // 2 + 10
        y = py + 40

        # ── Left column ──
        self._u3_text("MOVEMENT", col1_x, y, self._U3_LTBLUE, f)
        y += lh + 4
        lines_left = [
            ("[W/A/S/D]", "Move on the map"),
            ("[ARROWS]", "Move on the map"),
        ]
        for key, desc in lines_left:
            self._u3_text(key, col1_x, y, self._U3_WHITE, f)
            self._u3_text(desc, col1_x + 100, y, self._U3_GRAY, f)
            y += lh

        y += 8
        self._u3_text("MENUS & SCREENS", col1_x, y, self._U3_LTBLUE, f)
        y += lh + 4
        lines_menus = [
            ("[P]", "Open party / inventory"),
            ("[L]", "Open game log"),
            ("[H]", "Toggle this help screen"),
            ("[ESC]", "Quit game"),
        ]
        for key, desc in lines_menus:
            self._u3_text(key, col1_x, y, self._U3_WHITE, f)
            self._u3_text(desc, col1_x + 100, y, self._U3_GRAY, f)
            y += lh

        # ── Right column ──
        ry = py + 40
        self._u3_text("INTERACTIONS", col2_x, ry, self._U3_LTBLUE, f)
        ry += lh + 4
        lines_interact = [
            ("Walk into", "Enter towns and dungeons"),
            ("Enemies", "Touch to start combat"),
        ]
        for key, desc in lines_interact:
            self._u3_text(key, col2_x, ry, (200, 180, 120), f)
            self._u3_text(desc, col2_x + 100, ry, self._U3_GRAY, f)
            ry += lh

        ry += 8
        self._u3_text("PARTY SCREEN", col2_x, ry, self._U3_LTBLUE, f)
        ry += lh + 4
        lines_party = [
            ("[UP/DOWN]", "Select party member"),
            ("[ENTER]", "View character details"),
            ("[ESC]", "Close screen"),
        ]
        for key, desc in lines_party:
            self._u3_text(key, col2_x, ry, self._U3_WHITE, f)
            self._u3_text(desc, col2_x + 100, ry, self._U3_GRAY, f)
            ry += lh

        ry += 8
        self._u3_text("INFO BAR", col2_x, ry, self._U3_LTBLUE, f)
        ry += lh + 4
        lines_info = [
            ("GOLD", "Your current gold amount"),
            ("TERRAIN", "Tile type you're standing on"),
            ("POS", "Your map coordinates"),
        ]
        for key, desc in lines_info:
            self._u3_text(key, col2_x, ry, (200, 180, 120), f)
            self._u3_text(desc, col2_x + 100, ry, self._U3_GRAY, f)
            ry += lh

        # Footer
        self._u3_text("[H / ESC] CLOSE",
                      px + pw // 2 - 50, py + ph - 22,
                      self._U3_BLUE, self.font_small)

    def draw_combat_help_overlay(self):
        """Draw a full-screen overlay showing all combat controls."""
        # Dim background
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 200))
        self.screen.blit(dim, (0, 0))

        margin = 60
        px, py = margin, margin
        pw = SCREEN_WIDTH - margin * 2
        ph = SCREEN_HEIGHT - margin * 2

        pygame.draw.rect(self.screen, (12, 12, 24), (px, py, pw, ph))
        pygame.draw.rect(self.screen, self._U3_LTBLUE, (px, py, pw, ph), 2)

        # Title
        self._u3_text("COMBAT CONTROLS", px + pw // 2 - 70, py + 10,
                       self._U3_ORANGE, self.font)

        f = self.font_small
        lh = 18  # line height
        col1_x = px + 20
        col2_x = px + pw // 2 + 10
        y = py + 40

        # ── Left column ──
        self._u3_text("MOVEMENT & ACTIONS", col1_x, y, self._U3_LTBLUE, f)
        y += lh + 4
        lines_left = [
            ("[W/A/S/D]", "Move / Melee attack"),
            ("[ARROWS]", "Navigate menus / Choose direction"),
            ("[ENTER]", "Confirm selection"),
            ("[SPACE]", "Skip turn / Speed up animations"),
            ("[ESC]", "Cancel current action"),
        ]
        for key, desc in lines_left:
            self._u3_text(key, col1_x, y, self._U3_WHITE, f)
            self._u3_text(desc, col1_x + 100, y, self._U3_GRAY, f)
            y += lh

        y += 8
        self._u3_text("MENU COMMANDS", col1_x, y, self._U3_LTBLUE, f)
        y += lh + 4
        lines_menu = [
            ("[ENTER]", "Select highlighted action"),
            ("[UP/DOWN]", "Scroll action menu"),
        ]
        for key, desc in lines_menu:
            self._u3_text(key, col1_x, y, self._U3_WHITE, f)
            self._u3_text(desc, col1_x + 100, y, self._U3_GRAY, f)
            y += lh

        y += 8
        self._u3_text("ACTIONS", col1_x, y, self._U3_LTBLUE, f)
        y += lh + 4
        lines_actions = [
            ("Attack", "Move into an adjacent enemy"),
            ("Ranged", "Fire weapon in a direction"),
            ("Spell", "Cast a spell from your list"),
            ("Throw", "Throw an item at enemies"),
            ("Use Item", "Use a consumable item"),
            ("Defend", "Reduce damage taken this round"),
            ("Flee", "Attempt to escape combat"),
        ]
        for action, desc in lines_actions:
            self._u3_text(action, col1_x, y, (200, 180, 120), f)
            self._u3_text(desc, col1_x + 100, y, self._U3_GRAY, f)
            y += lh

        # ── Right column ──
        ry = py + 40
        self._u3_text("SPELLS", col2_x, ry, self._U3_LTBLUE, f)
        ry += lh + 4
        lines_spells = [
            ("Fireball", "Ranged fire damage (directional)"),
            ("Heal", "Restore HP to a party member"),
            ("Shield", "Boost AC of a party member"),
            ("Turn Undead", "Damage all undead enemies"),
        ]
        for spell, desc in lines_spells:
            self._u3_text(spell, col2_x, ry, (200, 180, 120), f)
            self._u3_text(desc, col2_x + 100, ry, self._U3_GRAY, f)
            ry += lh

        ry += 8
        self._u3_text("TARGETING", col2_x, ry, self._U3_LTBLUE, f)
        ry += lh + 4
        lines_target = [
            ("[ARROWS]", "Choose direction for ranged/spells"),
            ("[ARROWS]", "Move cursor for shield target"),
            ("[ENTER]", "Confirm target"),
            ("[ESC]", "Cancel and return to menu"),
        ]
        for key, desc in lines_target:
            self._u3_text(key, col2_x, ry, self._U3_WHITE, f)
            self._u3_text(desc, col2_x + 100, ry, self._U3_GRAY, f)
            ry += lh

        ry += 8
        self._u3_text("OTHER", col2_x, ry, self._U3_LTBLUE, f)
        ry += lh + 4
        lines_other = [
            ("[L]", "Open game log"),
            ("[H]", "Toggle this help screen"),
            ("[E]", "Open equipment screen"),
        ]
        for key, desc in lines_other:
            self._u3_text(key, col2_x, ry, self._U3_WHITE, f)
            self._u3_text(desc, col2_x + 100, ry, self._U3_GRAY, f)
            ry += lh

        # Footer hint
        self._u3_text("[H / ESC] CLOSE",
                      px + pw // 2 - 50, py + ph - 22,
                      self._U3_BLUE, self.font_small)

    def draw_log_overlay(self, log_entries, scroll_offset=0):
        """Draw a full-screen scrollable game log overlay.

        Long lines are word-wrapped so nothing bleeds past the panel
        edges, and a clipping rect prevents vertical overflow.

        log_entries : list[str]  – all accumulated log messages
        scroll_offset : int      – how many lines scrolled up from the bottom
        """
        # Lazily create the larger log font once
        if not hasattr(self, "_log_font"):
            self._log_font = pygame.font.SysFont("monospace", 18, bold=True)
        if not hasattr(self, "_log_title_font"):
            self._log_title_font = pygame.font.SysFont("monospace", 24, bold=True)

        log_font = self._log_font
        title_font = self._log_title_font

        # Dim background (darker for better contrast)
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 210))
        self.screen.blit(dim, (0, 0))

        # Log panel
        margin = 30
        px = margin
        py = margin
        pw = SCREEN_WIDTH - margin * 2
        ph = SCREEN_HEIGHT - margin * 2

        text_pad = 16            # horizontal padding inside the panel
        max_text_w = pw - text_pad * 2   # max pixel width for a line of text

        # Solid dark background for readability
        pygame.draw.rect(self.screen, (8, 8, 18), (px, py, pw, ph))
        pygame.draw.rect(self.screen, self._U3_ORANGE, (px, py, pw, ph), 2)

        # Title — large and bright
        title_surf = title_font.render("GAME LOG", True, self._U3_ORANGE)
        self.screen.blit(title_surf,
                         (px + pw // 2 - title_surf.get_width() // 2, py + 8))

        # Hints
        hint_surf = self.font.render("[UP/DOWN] SCROLL    [L/ESC] CLOSE",
                                     True, (120, 160, 255))
        self.screen.blit(hint_surf,
                         (px + pw // 2 - hint_surf.get_width() // 2,
                          py + ph - 24))

        # Content area
        content_y = py + 42
        content_h = ph - 72  # room for title + hint
        line_h = 22

        # ── Helper: word-wrap a single log entry into display lines ──
        def _wrap_line(text, font, max_w):
            """Return a list of strings that each fit within *max_w* px."""
            words = text.split(" ")
            lines = []
            current = ""
            for word in words:
                test = (current + " " + word).strip()
                tw, _ = font.size(test.upper())
                if tw <= max_w:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    # If a single word is wider than max_w, truncate it
                    tw2, _ = font.size(word.upper())
                    if tw2 > max_w:
                        while word:
                            for end in range(len(word), 0, -1):
                                cw, _ = font.size(word[:end].upper())
                                if cw <= max_w:
                                    lines.append(word[:end])
                                    word = word[end:]
                                    break
                            else:
                                # Safety: at least one char per line
                                lines.append(word[0])
                                word = word[1:]
                        current = ""
                    else:
                        current = word
            if current:
                lines.append(current)
            return lines if lines else [""]

        # ── Pre-wrap all log entries into (display_line, original_entry) ──
        wrapped = []  # list of (display_text, original_entry_text)
        for entry in log_entries:
            sub_lines = _wrap_line(entry, log_font, max_text_w)
            for sl in sub_lines:
                wrapped.append((sl, entry))

        max_visible = content_h // line_h

        if not wrapped:
            no_log = log_font.render("NO LOG ENTRIES YET.", True,
                                     self._U3_GRAY)
            self.screen.blit(no_log, (px + text_pad, content_y + 8))
            return

        total = len(wrapped)

        # scroll_offset 0 = bottom (most recent visible)
        max_scroll = max(0, total - max_visible)
        scroll_offset = max(0, min(scroll_offset, max_scroll))

        end_idx = total - scroll_offset
        start_idx = max(0, end_idx - max_visible)
        visible = wrapped[start_idx:end_idx]

        # Set a clipping rect so nothing draws outside the content area
        clip_rect = pygame.Rect(px + 2, content_y, pw - 4, content_h)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(clip_rect)

        for i, (display_text, original) in enumerate(visible):
            ly = content_y + i * line_h
            # Color code based on original entry content
            lo = original.lower()
            if "critical" in lo or "defeated" in lo:
                color = (255, 220, 60)
            elif "hit!" in lo or "damage" in lo:
                color = (255, 255, 255)
            elif "miss" in lo or "failed" in lo or "resisted" in lo:
                color = (140, 140, 160)
            elif original.startswith("--"):
                color = (255, 180, 50)
            elif "gold" in lo or "treasure" in lo:
                color = (255, 255, 60)
            elif "heals" in lo or "wakes up" in lo:
                color = (80, 255, 120)
            elif "poison" in lo:
                color = (120, 220, 60)
            elif "sleep" in lo or "zzz" in lo:
                color = (160, 140, 255)
            elif "curse" in lo or "hex" in lo:
                color = (255, 100, 100)
            elif "fallen" in lo:
                color = (255, 80, 80)
            else:
                color = (210, 210, 230)

            surf = log_font.render(display_text.upper(), True, color)
            self.screen.blit(surf, (px + text_pad, ly))

        # Restore original clip
        self.screen.set_clip(old_clip)

        # Scroll indicators — brighter, drawn outside the clip
        if scroll_offset > 0:
            more_down = log_font.render("v MORE v", True, (100, 180, 255))
            self.screen.blit(more_down,
                             (px + pw // 2 - more_down.get_width() // 2,
                              content_y + content_h - 18))
        if scroll_offset < max_scroll:
            more_up = log_font.render("^ MORE ^", True, (100, 180, 255))
            self.screen.blit(more_up,
                             (px + pw // 2 - more_up.get_width() // 2,
                              content_y))

    # ── Character Creation Screen ─────────────────────────────────

    def draw_char_create_screen(self, game):
        """Draw the character creation wizard screen.

        Reads creation state from game._cc_* attributes.
        """
        from src.party import VALID_RACES, RACE_INFO
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT
        step = game._cc_step
        elapsed = game._cc_elapsed

        # Background: dark with subtle starfield
        self.screen.fill((5, 5, 15))
        import random
        rng = random.Random(42)
        for _ in range(30):
            sx = rng.randint(0, sw)
            sy = rng.randint(0, sh)
            bright = 40 + int(20 * math.sin(elapsed * 0.8 + sx * 0.01))
            bright = max(0, min(255, bright))
            self.screen.set_at((sx, sy), (bright, bright, bright + 20))

        # Title bar
        title_text = "~ CHARACTER CREATION ~"
        t_surf = self.font.render(title_text, True, (200, 150, 60))
        self.screen.blit(t_surf, (sw // 2 - t_surf.get_width() // 2, 16))

        # Step indicator
        steps = ["NAME", "RACE", "GENDER", "CLASS", "TILE", "STATS", "CONFIRM"]
        step_map = {"name": 0, "race": 1, "gender": 2, "class": 3,
                    "tile": 4, "stats": 5, "confirm": 6, "done": 6}
        current_step_idx = step_map.get(step, 0)
        step_y = 44
        step_spacing = 80
        step_total_w = len(steps) * step_spacing
        step_x0 = sw // 2 - step_total_w // 2
        for i, s in enumerate(steps):
            x = step_x0 + i * step_spacing
            if i < current_step_idx:
                color = (60, 140, 60)   # completed
            elif i == current_step_idx:
                color = (255, 200, 60)  # current
            else:
                color = (60, 60, 80)    # future
            self._u3_text(s, x, step_y, color, self.font_small)
            if i < len(steps) - 1:
                self._u3_text(">", x + step_spacing - 10, step_y,
                              (60, 60, 80), self.font_small)

        # Main content panel
        px, py, pw, ph = 80, 72, sw - 160, sh - 130
        self._u3_panel(px, py, pw, ph)

        cx = px + 20   # content left margin
        cy = py + 16   # content top margin

        # ── NAME ENTRY ──
        if step == "name":
            self._u3_text("ENTER THY NAME:", cx, cy, (140, 140, 180))
            # Name field with blinking cursor
            name_display = game._cc_name
            blink = int(elapsed * 2) % 2 == 0
            if blink:
                name_display += "_"
            name_surf = self.font.render(name_display, True, (255, 255, 255))
            # Draw name in a bordered box
            name_box = pygame.Rect(cx, cy + 30, pw - 40, 28)
            pygame.draw.rect(self.screen, (20, 20, 40), name_box)
            pygame.draw.rect(self.screen, (100, 100, 160), name_box, 1)
            self.screen.blit(name_surf, (cx + 8, cy + 34))
            self._u3_text("(MAX 12 CHARACTERS)", cx, cy + 70,
                          (80, 80, 100), self.font_small)
            self._u3_text("[ENTER] NEXT   [ESC] BACK", cx, cy + ph - 60,
                          (68, 68, 200), self.font_small)

        # ── RACE SELECTION ──
        elif step == "race":
            self._u3_text("CHOOSE THY RACE:", cx, cy, (140, 140, 180))
            for i, race in enumerate(VALID_RACES):
                ry = cy + 30 + i * 36
                if i == game._cc_race_cursor:
                    # Selection bar
                    bar = pygame.Rect(cx, ry - 2, pw - 40, 30)
                    pygame.draw.rect(self.screen, (30, 30, 60), bar)
                    pygame.draw.rect(self.screen, (100, 100, 200), bar, 1)
                    arrow_x = cx + 4
                    bob = int(math.sin(elapsed * 4) * 3)
                    self._u3_text(">", arrow_x + bob, ry,
                                  (255, 200, 60))
                    self._u3_text(race, cx + 20, ry, (255, 255, 100))
                    # Show race info on the right
                    info = RACE_INFO.get(race, {})
                    desc = info.get("description", "")
                    effects = info.get("effects", [])
                    mods = info.get("stat_modifiers", {})
                    info_x = cx + pw // 2
                    self._u3_text("DESCRIPTION:", info_x, cy + 30,
                                  (120, 120, 160), self.font_small)
                    # Word-wrap description
                    words = desc.split()
                    lines, line = [], ""
                    for w in words:
                        if len(line) + len(w) + 1 > 36:
                            lines.append(line)
                            line = w
                        else:
                            line = (line + " " + w).strip()
                    if line:
                        lines.append(line)
                    for li, l in enumerate(lines[:4]):
                        self._u3_text(l, info_x, cy + 46 + li * 14,
                                      (160, 160, 180), self.font_small)
                    # Stat mods
                    mod_y = cy + 110
                    self._u3_text("STAT MODIFIERS:", info_x, mod_y,
                                  (120, 120, 160), self.font_small)
                    for j, (stat, val) in enumerate(mods.items()):
                        sign = "+" if val >= 0 else ""
                        col = ((100, 200, 100) if val > 0
                               else (200, 100, 100) if val < 0
                               else (120, 120, 120))
                        self._u3_text(
                            f"{stat[:3].upper()}: {sign}{val}",
                            info_x + (j % 2) * 100,
                            mod_y + 16 + (j // 2) * 16,
                            col, self.font_small)
                    # Effects
                    if effects:
                        eff_y = mod_y + 56
                        self._u3_text("INNATE EFFECTS:", info_x, eff_y,
                                      (120, 120, 160), self.font_small)
                        for ei, e in enumerate(effects):
                            self._u3_text(
                                e.replace("_", " "),
                                info_x, eff_y + 16 + ei * 14,
                                (180, 160, 100), self.font_small)
                else:
                    self._u3_text(race, cx + 20, ry, (120, 120, 140))
            self._u3_text("[UP/DOWN] SELECT   [ENTER] NEXT   [ESC] BACK",
                          cx, cy + ph - 60, (68, 68, 200), self.font_small)

        # ── GENDER SELECTION ──
        elif step == "gender":
            from src.party import PartyMember
            self._u3_text("CHOOSE THY GENDER:", cx, cy, (140, 140, 180))
            for i, gender in enumerate(PartyMember.VALID_GENDERS):
                gy = cy + 30 + i * 36
                if i == game._cc_gender_cursor:
                    bar = pygame.Rect(cx, gy - 2, pw // 2, 30)
                    pygame.draw.rect(self.screen, (30, 30, 60), bar)
                    pygame.draw.rect(self.screen, (100, 100, 200), bar, 1)
                    bob = int(math.sin(elapsed * 4) * 3)
                    self._u3_text(">", cx + 4 + bob, gy, (255, 200, 60))
                    self._u3_text(gender, cx + 20, gy, (255, 255, 100))
                else:
                    self._u3_text(gender, cx + 20, gy, (120, 120, 140))
            # Show summary so far
            sum_x = cx + pw // 2
            self._u3_text("SUMMARY:", sum_x, cy + 30,
                          (120, 120, 160), self.font_small)
            self._u3_text(f"NAME:  {game._cc_name}", sum_x, cy + 50,
                          (180, 180, 200), self.font_small)
            self._u3_text(f"RACE:  {game._cc_selected_race()}", sum_x,
                          cy + 66, (180, 180, 200), self.font_small)
            self._u3_text("[UP/DOWN] SELECT   [ENTER] NEXT   [ESC] BACK",
                          cx, cy + ph - 60, (68, 68, 200), self.font_small)

        # ── CLASS SELECTION ──
        elif step == "class":
            from src.party import PartyMember as _PM
            valid = game._cc_valid_classes_for_race()
            self._u3_text("CHOOSE THY CLASS:", cx, cy, (140, 140, 180))
            # List classes (scrollable if needed)
            visible = min(len(valid), 11)
            scroll = max(0, game._cc_class_cursor - visible + 1)
            for i in range(scroll, min(scroll + visible, len(valid))):
                draw_i = i - scroll
                cly = cy + 30 + draw_i * 28
                cls_name = valid[i]
                if i == game._cc_class_cursor:
                    bar = pygame.Rect(cx, cly - 2, pw // 2 - 20, 24)
                    pygame.draw.rect(self.screen, (30, 30, 60), bar)
                    pygame.draw.rect(self.screen, (100, 100, 200), bar, 1)
                    bob = int(math.sin(elapsed * 4) * 3)
                    self._u3_text(">", cx + 4 + bob, cly, (255, 200, 60))
                    self._u3_text(cls_name, cx + 20, cly, (255, 255, 100))
                    # Show class info on the right
                    tmpl = _PM._load_class_template(cls_name)
                    info_x = cx + pw // 2
                    self._u3_text("CLASS INFO:", info_x, cy + 30,
                                  (120, 120, 160), self.font_small)
                    spell = tmpl.get("spell_type", "none")
                    hp_lv = tmpl.get("hp_per_level", 0)
                    mp_lv = tmpl.get("mp_per_level", 0)
                    rng = tmpl.get("range", 1)
                    self._u3_text(f"HP/LVL:     {hp_lv}", info_x,
                                  cy + 50, (160, 200, 160), self.font_small)
                    self._u3_text(f"MP/LVL:     {mp_lv}", info_x,
                                  cy + 66, (160, 160, 200), self.font_small)
                    self._u3_text(f"SPELL TYPE: {spell.upper()}", info_x,
                                  cy + 82, (180, 160, 100), self.font_small)
                    self._u3_text(f"RANGE:      {rng}", info_x,
                                  cy + 98, (160, 160, 160), self.font_small)
                    # Weapon/armor access
                    wpn = tmpl.get("allowed_weapons")
                    arm = tmpl.get("allowed_armor")
                    wpn_str = "ALL" if wpn is None else ", ".join(
                        sorted(wpn))
                    arm_str = "ALL" if arm is None else ", ".join(
                        sorted(arm))
                    self._u3_text("WEAPONS:", info_x, cy + 122,
                                  (120, 120, 160), self.font_small)
                    # Word-wrap
                    for wi, chunk in enumerate(
                            [wpn_str[j:j+30]
                             for j in range(0, len(wpn_str), 30)]):
                        self._u3_text(chunk, info_x, cy + 136 + wi * 14,
                                      (160, 160, 180), self.font_small)
                    arm_y = cy + 136 + (len(wpn_str) // 30 + 1) * 14 + 4
                    self._u3_text("ARMOR:", info_x, arm_y,
                                  (120, 120, 160), self.font_small)
                    for ai, chunk in enumerate(
                            [arm_str[j:j+30]
                             for j in range(0, len(arm_str), 30)]):
                        self._u3_text(chunk, info_x,
                                      arm_y + 14 + ai * 14,
                                      (160, 160, 180), self.font_small)
                else:
                    self._u3_text(cls_name, cx + 20, cly, (120, 120, 140))
            self._u3_text("[UP/DOWN] SELECT   [ENTER] NEXT   [ESC] BACK",
                          cx, cy + ph - 60, (68, 68, 200), self.font_small)

        # ── TILE SELECTION ──
        elif step == "tile":
            self._u3_text("CHOOSE THY APPEARANCE:", cx, cy, (140, 140, 180))
            tiles = game._cc_tiles
            tile_cursor = game._cc_tile_cursor
            # Grid layout: 6 tiles per row, 80px cells
            cols = 6
            cell_w = 80
            cell_h = 90
            grid_x = cx + 10
            grid_y = cy + 28
            # Calculate visible rows
            max_rows = (ph - 120) // cell_h
            total_rows = (len(tiles) + cols - 1) // cols
            cursor_row = tile_cursor // cols
            scroll_row = max(0, min(cursor_row - max_rows // 2,
                                    total_rows - max_rows))
            if scroll_row < 0:
                scroll_row = 0

            for ti, tile in enumerate(tiles):
                row = ti // cols
                col = ti % cols
                vis_row = row - scroll_row
                if vis_row < 0 or vis_row >= max_rows:
                    continue
                tx = grid_x + col * cell_w
                ty = grid_y + vis_row * cell_h
                is_selected = (ti == tile_cursor)

                # Cell background
                if is_selected:
                    sel_rect = pygame.Rect(tx - 2, ty - 2,
                                           cell_w - 8, cell_h - 8)
                    pygame.draw.rect(self.screen, (40, 30, 60), sel_rect)
                    pygame.draw.rect(self.screen, (200, 160, 60),
                                     sel_rect, 2)
                # Load and draw the tile sprite
                self._draw_cc_tile(tile["file"], tx + (cell_w - 8) // 2,
                                   ty + 28, 56)
                # Tile name below
                name_col = ((255, 255, 100) if is_selected
                            else (120, 120, 140))
                name = tile["name"]
                # Truncate long names
                if len(name) > 10:
                    name = name[:9] + "."
                nw, _ = self.font_small.size(name.upper())
                self._u3_text(name,
                              tx + (cell_w - 8 - nw) // 2,
                              ty + 58, name_col, self.font_small)

            # Scroll indicators
            if scroll_row > 0:
                self._u3_text("^ MORE ^",
                              grid_x + (cols * cell_w) // 2 - 30,
                              grid_y - 10, (68, 68, 200), self.font_small)
            if scroll_row + max_rows < total_rows:
                self._u3_text("v MORE v",
                              grid_x + (cols * cell_w) // 2 - 30,
                              grid_y + max_rows * cell_h - 4,
                              (68, 68, 200), self.font_small)

            # Preview of selected tile on the right
            if 0 <= tile_cursor < len(tiles):
                sel_tile = tiles[tile_cursor]
                preview_x = cx + pw - 160
                preview_y = cy + 28
                # Large preview with circle bg
                circle_r = 52
                pcx = preview_x + circle_r
                pcy = preview_y + circle_r
                pygame.draw.circle(self.screen, (30, 25, 50),
                                   (pcx, pcy), circle_r)
                pygame.draw.circle(self.screen, (80, 60, 120),
                                   (pcx, pcy), circle_r, 1)
                self._draw_cc_tile(sel_tile["file"], pcx, pcy, 80)
                # Name below preview
                pn = sel_tile["name"]
                pnw, _ = self.font.size(pn.upper())
                self._u3_text(pn, pcx - pnw // 2,
                              preview_y + circle_r * 2 + 10,
                              (255, 255, 255), self.font)

            self._u3_text(
                "[ARROWS] BROWSE   [ENTER] NEXT   [ESC] BACK",
                cx, cy + ph - 60, (68, 68, 200), self.font_small)

        # ── STAT ALLOCATION ──
        elif step == "stats":
            remaining = game._cc_points_remaining
            self._u3_text("DISTRIBUTE THY ATTRIBUTES:", cx, cy,
                          (140, 140, 180))
            pts_col = ((100, 200, 100) if remaining > 0
                       else (200, 200, 60))
            self._u3_text(f"POINTS REMAINING: {remaining}", cx,
                          cy + 18, pts_col, self.font_small)
            for i, stat_key in enumerate(game._cc_stat_names):
                sy = cy + 48 + i * 40
                val = game._cc_stats[stat_key]
                label = stat_key[:3].upper()
                if i == game._cc_stat_cursor:
                    bar = pygame.Rect(cx, sy - 4, pw - 40, 34)
                    pygame.draw.rect(self.screen, (30, 30, 60), bar)
                    pygame.draw.rect(self.screen, (100, 100, 200), bar, 1)
                    bob = int(math.sin(elapsed * 4) * 3)
                    self._u3_text(">", cx + 4 + bob, sy,
                                  (255, 200, 60))
                    self._u3_text(f"{label}:", cx + 20, sy,
                                  (255, 255, 100))
                else:
                    self._u3_text(f"{label}:", cx + 20, sy,
                                  (120, 120, 140))
                # Value with bar
                self._u3_text(f"{val:2d}", cx + 70, sy, (255, 255, 255))
                # Visual bar
                bar_x = cx + 110
                bar_w = int((val - 5) / 20 * 200)
                bar_bg = pygame.Rect(bar_x, sy + 2, 200, 12)
                bar_fill = pygame.Rect(bar_x, sy + 2, bar_w, 12)
                pygame.draw.rect(self.screen, (20, 20, 40), bar_bg)
                bar_color = ((80, 160, 80) if val >= 15
                             else (160, 160, 80) if val >= 10
                             else (160, 80, 80))
                if bar_w > 0:
                    pygame.draw.rect(self.screen, bar_color, bar_fill)
                pygame.draw.rect(self.screen, (60, 60, 100), bar_bg, 1)
                # Min/max labels
                self._u3_text("5", bar_x - 2, sy + 16,
                              (60, 60, 80), self.font_small)
                self._u3_text("25", bar_x + 194, sy + 16,
                              (60, 60, 80), self.font_small)
            # Summary on the right
            sum_x = cx + pw // 2 + 40
            self._u3_text("SUMMARY:", sum_x, cy + 48,
                          (120, 120, 160), self.font_small)
            self._u3_text(f"NAME:   {game._cc_name}", sum_x, cy + 68,
                          (180, 180, 200), self.font_small)
            self._u3_text(f"RACE:   {game._cc_selected_race()}", sum_x,
                          cy + 84, (180, 180, 200), self.font_small)
            self._u3_text(f"GENDER: {game._cc_selected_gender()}", sum_x,
                          cy + 100, (180, 180, 200), self.font_small)
            self._u3_text(f"CLASS:  {game._cc_selected_class()}", sum_x,
                          cy + 116, (180, 180, 200), self.font_small)
            # Hints
            hint = "[LEFT/RIGHT] ADJUST   [UP/DOWN] SELECT STAT"
            self._u3_text(hint, cx, cy + ph - 76,
                          (68, 68, 200), self.font_small)
            if remaining == 0:
                self._u3_text("[ENTER] NEXT   [ESC] BACK", cx,
                              cy + ph - 60, (68, 68, 200), self.font_small)
            else:
                self._u3_text(
                    "SPEND ALL POINTS TO CONTINUE   [ESC] BACK",
                    cx, cy + ph - 60, (140, 100, 60), self.font_small)

        # ── CONFIRM ──
        elif step == "confirm":
            self._u3_text("CONFIRM THY CHARACTER:", cx, cy,
                          (140, 140, 180))

            # Selected tile preview on the right
            tile_file = game._cc_selected_tile()
            if tile_file:
                preview_cx = cx + pw - 80
                preview_cy = cy + 80
                circle_r = 48
                pygame.draw.circle(self.screen, (30, 25, 50),
                                   (preview_cx, preview_cy), circle_r)
                pygame.draw.circle(self.screen, (80, 60, 120),
                                   (preview_cx, preview_cy), circle_r, 1)
                self._draw_cc_tile(tile_file, preview_cx, preview_cy, 72)

            # Full summary
            dy = cy + 30
            self._u3_text(f"NAME:   {game._cc_name}", cx, dy,
                          (255, 255, 255))
            self._u3_text(f"RACE:   {game._cc_selected_race()}",
                          cx, dy + 20, (255, 255, 255))
            self._u3_text(f"GENDER: {game._cc_selected_gender()}",
                          cx, dy + 40, (255, 255, 255))
            self._u3_text(f"CLASS:  {game._cc_selected_class()}",
                          cx, dy + 60, (255, 255, 255))
            dy += 90
            for stat_key in game._cc_stat_names:
                val = game._cc_stats[stat_key]
                self._u3_text(
                    f"{stat_key[:3].upper()}: {val:2d}",
                    cx, dy, (200, 200, 220))
                dy += 18
            # Confirm/cancel buttons
            btn_y = dy + 30
            for i, label in enumerate(["CREATE", "CANCEL"]):
                by = btn_y + i * 36
                if i == game._cc_confirm_cursor:
                    bar = pygame.Rect(cx, by - 2, 200, 30)
                    pygame.draw.rect(self.screen, (30, 30, 60), bar)
                    pygame.draw.rect(self.screen, (100, 100, 200), bar, 1)
                    bob = int(math.sin(elapsed * 4) * 3)
                    self._u3_text(">", cx + 4 + bob, by, (255, 200, 60))
                    self._u3_text(label, cx + 20, by, (255, 255, 100))
                else:
                    self._u3_text(label, cx + 20, by, (120, 120, 140))
            self._u3_text("[UP/DOWN] SELECT   [ENTER] CHOOSE   [ESC] BACK",
                          cx, cy + ph - 60, (68, 68, 200), self.font_small)

        # ── DONE ──
        elif step == "done":
            self._u3_text("CHARACTER CREATED!", cx, cy + 40,
                          (100, 200, 100))
            self._u3_text(
                f"{game._cc_name} THE {game._cc_selected_race().upper()}"
                f" {game._cc_selected_class().upper()}"
                f" HAS JOINED THE ROSTER.",
                cx, cy + 70, (180, 180, 200), self.font_small)
            self._u3_text(
                f"ROSTER: {len(game.party.roster)}/{game.party.MAX_ROSTER}",
                cx, cy + 100, (140, 140, 160), self.font_small)
            self._u3_text("[ANY KEY] RETURN TO TITLE",
                          cx, cy + ph - 60, (68, 68, 200), self.font_small)

        # ── Feedback message overlay ──
        if game._cc_message and game._cc_msg_timer > 0:
            msg_surf = self.font.render(game._cc_message, True,
                                        (255, 220, 100))
            mx = sw // 2 - msg_surf.get_width() // 2
            self.screen.blit(msg_surf, (mx, sh - 40))

    # ── Party Formation Screen ────────────────────────────────────

    def draw_form_party_screen(self, game):
        """Draw the party formation screen.

        Shows the roster on the left with checkboxes, and a detail
        panel for the highlighted character on the right.
        """
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT
        elapsed = game._fp_elapsed
        roster = game.party.roster

        # Background
        self.screen.fill((5, 5, 15))
        import random
        rng = random.Random(42)
        for _ in range(30):
            sx = rng.randint(0, sw)
            sy = rng.randint(0, sh)
            bright = 40 + int(20 * math.sin(elapsed * 0.8 + sx * 0.01))
            bright = max(0, min(255, bright))
            self.screen.set_at((sx, sy), (bright, bright, bright + 20))

        # Title
        title = "~ FORM THY PARTY ~"
        t_surf = self.font.render(title, True, (200, 150, 60))
        self.screen.blit(t_surf, (sw // 2 - t_surf.get_width() // 2, 16))

        # Selection count
        count = len(game._fp_selected)
        count_col = ((100, 200, 100) if 1 <= count <= 4
                     else (200, 100, 100))
        self._u3_text(f"SELECTED: {count}/4", sw // 2 - 40, 40,
                      count_col, self.font_small)

        # Main panel
        px, py, pw, ph = 40, 60, sw - 80, sh - 110
        self._u3_panel(px, py, pw, ph)

        # Empty roster message
        if not roster:
            self._u3_text("NO CHARACTERS IN ROSTER!", px + 20, py + 40,
                          (200, 100, 100))
            self._u3_text("PRESS [C] TO CREATE A CHARACTER.",
                          px + 20, py + 66, (140, 140, 160))
            self._u3_text("[C] CREATE CHARACTER   [ESC] RETURN TO TITLE",
                          px + 20, py + ph - 40, (68, 68, 200),
                          self.font_small)
            return

        # ── Roster list (left side) ──
        roster_x = px + 12
        roster_y = py + 12
        roster_w = pw // 2 - 20
        visible = 12
        scroll = game._fp_scroll
        cursor = game._fp_cursor

        self._u3_text("ROSTER", roster_x + 4, roster_y,
                      (140, 140, 180), self.font_small)
        roster_y += 18

        row_h = 42  # taller rows to fit sprite
        for vi in range(visible):
            idx = scroll + vi
            if idx >= len(roster):
                break
            m = roster[idx]
            ry = roster_y + vi * row_h
            selected = idx in game._fp_selected
            is_cursor = idx == cursor

            # Row background
            if is_cursor:
                row_rect = pygame.Rect(roster_x, ry - 2, roster_w, row_h - 4)
                pygame.draw.rect(self.screen, (25, 25, 50), row_rect)
                pygame.draw.rect(self.screen, (80, 80, 180), row_rect, 1)

            # Checkbox
            cb_x = roster_x + 4
            cb_rect = pygame.Rect(cb_x, ry + 8, 14, 14)
            pygame.draw.rect(self.screen, (40, 40, 60), cb_rect)
            pygame.draw.rect(self.screen, (100, 100, 140), cb_rect, 1)
            if selected:
                pygame.draw.line(self.screen, (100, 220, 100),
                                 (cb_x + 2, ry + 15),
                                 (cb_x + 5, ry + 19), 2)
                pygame.draw.line(self.screen, (100, 220, 100),
                                 (cb_x + 5, ry + 19),
                                 (cb_x + 12, ry + 10), 2)

            # Character sprite (small, 32x32)
            sprite = self._get_member_sprite(m, big=False)
            sprite_w = 0
            if sprite:
                sx = roster_x + 22
                sy = ry + (row_h - 4 - sprite.get_height()) // 2
                self.screen.blit(sprite, (sx, sy))
                sprite_w = sprite.get_width() + 4

            # Name and class
            name_x = roster_x + 22 + sprite_w
            if is_cursor:
                bob = int(math.sin(elapsed * 4) * 3)
                self._u3_text(">", roster_x + 16 + bob, ry + 4,
                              (255, 200, 60), self.font_small)
                name_col = (255, 255, 100)
                class_col = (200, 200, 140)
            elif selected:
                name_col = (180, 220, 180)
                class_col = (140, 180, 140)
            else:
                name_col = (140, 140, 160)
                class_col = (100, 100, 120)

            self._u3_text(m.name, name_x + 6, ry + 4, name_col,
                          self.font_small)
            info_str = f"LV{m.level} {m.race} {m.char_class}"
            self._u3_text(info_str, name_x + 6, ry + 19, class_col,
                          self.font_small)

            # Party slot number if selected
            if selected:
                slot_list = sorted(game._fp_selected)
                slot_num = slot_list.index(idx) + 1
                self._u3_text(str(slot_num),
                              roster_x + roster_w - 18, ry + 10,
                              (100, 200, 100))

        # Scroll indicators
        if scroll > 0:
            self._u3_text("^ MORE ^", roster_x + roster_w // 2 - 30,
                          roster_y - 4, (68, 68, 200), self.font_small)
        if scroll + visible < len(roster):
            self._u3_text("v MORE v",
                          roster_x + roster_w // 2 - 30,
                          roster_y + visible * row_h - 4,
                          (68, 68, 200), self.font_small)

        # ── Detail panel (right side) ──
        detail_x = px + pw // 2 + 4
        detail_y = py + 12
        detail_w = pw // 2 - 16

        if 0 <= cursor < len(roster):
            m = roster[cursor]

            # ── Large character sprite at top of detail panel ──
            sprite_big = self._get_member_sprite(m, big=True)
            if sprite_big:
                sprite_cx = detail_x + detail_w // 2
                sprite_cy = detail_y + 4
                sx = sprite_cx - sprite_big.get_width() // 2
                # Background circle behind sprite
                circle_r = sprite_big.get_width() // 2 + 8
                pygame.draw.circle(self.screen, (30, 25, 50),
                                   (sprite_cx, sprite_cy + sprite_big.get_height() // 2),
                                   circle_r)
                pygame.draw.circle(self.screen, (80, 60, 120),
                                   (sprite_cx, sprite_cy + sprite_big.get_height() // 2),
                                   circle_r, 1)
                self.screen.blit(sprite_big, (sx, sprite_cy))
                dy = sprite_cy + sprite_big.get_height() + 10
            else:
                self._u3_text("CHARACTER DETAIL", detail_x, detail_y,
                              (140, 140, 180), self.font_small)
                dy = detail_y + 22

            # Character name centered
            name_surf = self.font.render(m.name.upper(), True, (255, 255, 255))
            self.screen.blit(name_surf,
                             (detail_x + (detail_w - name_surf.get_width()) // 2, dy))
            dy += 24

            self._u3_text(f"RACE:   {m.race}", detail_x, dy,
                          (200, 200, 220), self.font_small)
            dy += 18
            self._u3_text(f"GENDER: {m.gender}", detail_x, dy,
                          (200, 200, 220), self.font_small)
            dy += 18
            self._u3_text(f"CLASS:  {m.char_class}", detail_x, dy,
                          (200, 200, 220), self.font_small)
            dy += 18
            self._u3_text(f"LEVEL:  {m.level}", detail_x, dy,
                          (200, 200, 220), self.font_small)
            dy += 24

            # Stats with bars
            stats = [("STR", m.strength), ("DEX", m.dexterity),
                     ("INT", m.intelligence), ("WIS", m.wisdom)]
            for label, val in stats:
                self._u3_text(f"{label}: {val:2d}", detail_x, dy,
                              (180, 180, 200), self.font_small)
                bar_x = detail_x + 80
                bar_w = int(val / 25 * 140)
                bar_bg = pygame.Rect(bar_x, dy + 2, 140, 10)
                bar_fill = pygame.Rect(bar_x, dy + 2,
                                       min(bar_w, 140), 10)
                pygame.draw.rect(self.screen, (20, 20, 40), bar_bg)
                bar_color = ((80, 160, 80) if val >= 15
                             else (160, 160, 80) if val >= 10
                             else (160, 80, 80))
                if bar_w > 0:
                    pygame.draw.rect(self.screen, bar_color, bar_fill)
                pygame.draw.rect(self.screen, (60, 60, 100), bar_bg, 1)
                dy += 20

            dy += 8
            self._u3_text(f"HP: {m.hp}/{m.max_hp}", detail_x, dy,
                          (200, 120, 120), self.font_small)
            dy += 16
            # Spell type
            spell = m.spell_type
            if spell != "none":
                self._u3_text(f"MAGIC:  {spell.upper()}", detail_x, dy,
                              (160, 140, 200), self.font_small)
                dy += 16
            # Equipment
            dy += 8
            self._u3_text("EQUIPMENT:", detail_x, dy,
                          (120, 120, 160), self.font_small)
            dy += 16
            for slot_key in ("right_hand", "left_hand", "body", "head"):
                item = m.equipped.get(slot_key)
                if item:
                    slot_label = slot_key.replace("_", " ").upper()
                    self._u3_text(f"  {slot_label}: {item}",
                                  detail_x, dy,
                                  (160, 160, 180), self.font_small)
                    dy += 14

            # Racial effects
            effects = m.racial_effects
            if effects:
                dy += 8
                self._u3_text("RACIAL EFFECTS:", detail_x, dy,
                              (120, 120, 160), self.font_small)
                dy += 16
                for e in effects:
                    self._u3_text(f"  {e.replace('_', ' ').upper()}",
                                  detail_x, dy,
                                  (180, 160, 100), self.font_small)
                    dy += 14

        # ── Delete confirmation overlay ──
        if getattr(game, '_fp_confirm_delete', False):
            overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            self.screen.blit(overlay, (0, 0))
            box_w, box_h = 360, 100
            box_x = (sw - box_w) // 2
            box_y = (sh - box_h) // 2
            pygame.draw.rect(self.screen, (40, 20, 20),
                             (box_x, box_y, box_w, box_h))
            pygame.draw.rect(self.screen, (200, 80, 80),
                             (box_x, box_y, box_w, box_h), 2)
            del_name = roster[cursor].name if 0 <= cursor < len(roster) else "?"
            self._u3_text(f"DELETE {del_name}?",
                          box_x + 20, box_y + 16,
                          (255, 120, 120), self.font)
            self._u3_text("[Y] YES, DELETE   [N] CANCEL",
                          box_x + 20, box_y + 56,
                          (200, 200, 220), self.font_med)

        # ── Controls hint ──
        hint_y = py + ph + 6
        self._u3_text(
            "[UP/DN] BROWSE  [SPACE] TOGGLE  "
            "[ENTER] CONFIRM  [C] CREATE  [D] DELETE  [ESC] BACK",
            px + 4, hint_y, (68, 68, 200), self.font_small)

        # ── Feedback message ──
        if game._fp_message and game._fp_msg_timer > 0:
            msg_surf = self.font.render(game._fp_message, True,
                                        (255, 220, 100))
            mx = sw // 2 - msg_surf.get_width() // 2
            self.screen.blit(msg_surf, (mx, sh - 30))
