"""
Renderer - handles all drawing to the screen.

Currently uses colored rectangles for tiles (no sprites yet).
This is intentional: it lets us iterate on gameplay without
worrying about art assets. When we're ready for sprites, we
just swap the draw_tile method.
"""

import math
import pygame

from src.combat_engine import format_modifier
from src.settings import (
    TILE_SIZE, TILE_DEFS, VIEWPORT_COLS, VIEWPORT_ROWS,
    COLOR_BLACK, COLOR_WHITE, COLOR_YELLOW, COLOR_HUD_BG, COLOR_HUD_TEXT,
    PARTY_COLOR, SCREEN_WIDTH, SCREEN_HEIGHT,
    TILE_FLOOR, TILE_WALL, TILE_COUNTER, TILE_DOOR, TILE_EXIT,
    TILE_DFLOOR, TILE_DWALL, TILE_STAIRS, TILE_CHEST, TILE_TRAP,
    TILE_STAIRS_DOWN, TILE_DDOOR, TILE_ARTIFACT, TILE_PORTAL, TILE_LOCKED_DOOR,
)


class Renderer:
    """Draws the game world and UI to a pygame surface."""

    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont("monospace", 16)
        self.font_med = pygame.font.SysFont("monospace", 14)
        self.font_small = pygame.font.SysFont("monospace", 12)
        self._load_class_sprites()
        self._load_tile_sheet()

    def _load_tile_sheet(self):
        """Load U3TilesE.gif and extract individual 16x16 tiles, scaled to 32x32."""
        import os
        sheet_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "example_graphics", "U3TilesE.gif")

        self._tile_sprites = {}  # (row, col) -> 32x32 pygame surface

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
        chest_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "src", "assets", "chest_tile.png")
        self._chest_tile = None
        if os.path.exists(chest_path):
            raw = pygame.image.load(chest_path).convert_alpha()
            self._chest_tile = pygame.transform.scale(raw, (dst_ts, dst_ts))

        # ── Load town gate tile ──
        gate_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "src", "assets", "town_gate.png")
        self._town_gate_tile = None
        if os.path.exists(gate_path):
            raw = pygame.image.load(gate_path).convert_alpha()
            self._town_gate_tile = pygame.transform.scale(raw, (dst_ts, dst_ts))

        # ── Load monster tile sprites from assets ──
        self._monster_tiles = {}  # tile filename -> scaled pygame surface
        from src.monster import MONSTERS
        assets_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "src", "assets")
        for name, data in MONSTERS.items():
            tile_file = data.get("tile")
            if tile_file and tile_file not in self._monster_tiles:
                tile_path = os.path.join(assets_dir, tile_file)
                if os.path.exists(tile_path):
                    raw = pygame.image.load(tile_path).convert_alpha()
                    self._monster_tiles[tile_file] = pygame.transform.scale(
                        raw, (dst_ts, dst_ts))

        # Map game tile IDs to sheet positions (row, col)
        # Based on the style guide tile-to-game mapping
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
            TILE_TOWN:     (0, 6),
            # PATH uses brush/scrubland tile (R0 C2)
            TILE_PATH:     (0, 2),
            # Treasure chest (same sprite as town chest)
            TILE_CHEST:    (0, 9),
            # No exact match for sand or bridge — will fall back to procedural
        }
        # Town interior tile mapping
        self._town_tile_map = {
            TILE_FLOOR:    (0, 1),   # Grass for outdoor floor areas
            TILE_WALL:     (0, 8),   # Red brick wall
            TILE_CHEST:    (0, 9),   # Treasure chest
            TILE_EXIT:     (0, 6),   # Town tile as exit marker
            # TILE_COUNTER and TILE_DOOR have no exact match — procedural fallback
        }

    def _get_tile_sprite(self, tile_id):
        """Return the sprite surface for an overworld tile, or None."""
        pos = self._overworld_tile_map.get(tile_id)
        if pos:
            return self._tile_sprites.get(pos)
        return None

    def _load_class_sprites(self):
        """Load character class sprites from example_graphics/ folder."""
        import os
        sprite_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "example_graphics")

        # Map class names to sprite filenames
        sprite_files = {
            "fighter":  "Ultima3_AMI_sprite_fighter.png",
            "cleric":   "Ultima3_AMI_sprite_cleric.png",
            "wizard":   "Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png",
            "alchemist":"Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png",
            "illusionist":"Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png",
            "thief":    "Ultima3_AMI_sprite_thief.png",
            "barbarian":"Ultima3_AMI_sprite_barbarian.png",
        }

        self._class_sprites = {}       # class name -> original-size surface
        self._class_sprites_big = {}   # class name -> scaled up for party screen
        for cls_name, filename in sprite_files.items():
            path = os.path.join(sprite_dir, filename)
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                self._class_sprites[cls_name] = img
                # Scale up 3x for the party screen (~ 84-102 x 96px)
                big = pygame.transform.scale(
                    img, (img.get_width() * 3, img.get_height() * 3))
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
        """Draw NPC sprites on the map (Ultima III stick-figure style)."""
        for npc in npcs:
            screen_col, screen_row = camera.world_to_screen(npc.col, npc.row)
            if 0 <= screen_col < VIEWPORT_COLS and 0 <= screen_row < VIEWPORT_ROWS:
                cx = screen_col * TILE_SIZE + TILE_SIZE // 2
                cy = screen_row * TILE_SIZE + TILE_SIZE // 2

                # Body color based on NPC type
                npc_colors = {
                    "shopkeep": (200, 160, 60),
                    "innkeeper": (60, 160, 200),
                    "elder":     (180, 80, 200),
                    "villager":  (100, 180, 100),
                }
                color = npc_colors.get(npc.npc_type, (100, 180, 100))

                # Simple stick-figure, same proportions as the player
                # Head
                pygame.draw.circle(self.screen, color, (cx, cy - 9), 4)
                # Body
                pygame.draw.line(self.screen, color, (cx, cy - 5), (cx, cy + 4), 2)
                # Arms
                pygame.draw.line(self.screen, color, (cx - 6, cy - 2), (cx + 6, cy - 2), 2)
                # Legs
                pygame.draw.line(self.screen, color, (cx, cy + 4), (cx - 5, cy + 12), 2)
                pygame.draw.line(self.screen, color, (cx, cy + 4), (cx + 5, cy + 12), 2)
                # Name tag (small, uppercase)
                name_surf = self.font_small.render(npc.name.upper(), True, COLOR_WHITE)
                name_rect = name_surf.get_rect(center=(cx, cy - 16))
                bg = name_rect.inflate(4, 2)
                pygame.draw.rect(self.screen, (0, 0, 0), bg)
                self.screen.blit(name_surf, name_rect)

    # ========================================================
    # TOWN  –  Ultima III retro style (sprite tiles)
    # ========================================================

    _U3_TN_COLS = 30       # tiles visible horizontally (full width)
    _U3_TN_ROWS = 21       # tiles visible vertically
    _U3_TN_TS   = 32       # tile size
    _U3_TN_MAP_W = _U3_TN_COLS * _U3_TN_TS   # 960
    _U3_TN_MAP_H = _U3_TN_ROWS * _U3_TN_TS   # 672

    def draw_town_u3(self, party, town_data, message="",
                      quest_complete=False):
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

        # ── 1. draw map tiles ──
        for sr in range(rows):
            for sc in range(cols):
                wc = sc + off_c
                wr = sr + off_r
                tid = tile_map.get_tile(wc, wr)
                px = sc * ts
                py = sr * ts
                self._u3_draw_town_tile(tid, px, py, ts, wc, wr)

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

        # ── 4. blue border around map ──
        pygame.draw.rect(self.screen, (68, 68, 255),
                         pygame.Rect(0, 0, self._U3_TN_MAP_W, self._U3_TN_MAP_H), 2)

        # ── 5. bottom info bar ──
        bar_y = self._U3_TN_MAP_H
        bar_h = SCREEN_HEIGHT - bar_y
        self._u3_panel(0, bar_y, SCREEN_WIDTH, bar_h)

        tile_name = tile_map.get_tile_name(party.col, party.row)
        # Top line: town info
        self._u3_text(f"GOLD:{party.gold:05d}", 8, bar_y + 6, (255, 255, 0))
        self._u3_text(town_data.name.upper(), 240, bar_y + 6, (255, 170, 85))
        light_name = party.get_equipped_name("light")
        if light_name:
            charges = party.get_equipped_charges("light")
            lbl = f"LIGHT:{light_name.upper()}"
            if charges is not None:
                lbl += f":{charges:02d}"
            self._u3_text(lbl, 520, bar_y + 6, (255, 170, 85))
        self._u3_text(f"POS:({party.col},{party.row})", 770, bar_y + 6, (136, 136, 136))
        # Bottom line: controls
        self._u3_text("[ARROWS/WASD] MOVE  [P] PARTY  [BUMP NPC] TALK  [ESC] LEAVE",
                      8, bar_y + 28, (68, 68, 255))

        # ── 6. floating message ──
        if message:
            surf = self.font.render(message.upper(), True, (255, 220, 140))
            rect = surf.get_rect(center=(SCREEN_WIDTH // 2, 16))
            bg = rect.inflate(20, 8)
            pygame.draw.rect(self.screen, (0, 0, 0), bg)
            pygame.draw.rect(self.screen, (120, 120, 255), bg, 2)
            self.screen.blit(surf, rect)

    def _u3_draw_town_tile(self, tile_id, px, py, ts, wc, wr):
        """Draw a single town tile using sprite sheet art when available."""
        from src.settings import (
            TILE_FLOOR, TILE_WALL, TILE_COUNTER, TILE_DOOR, TILE_EXIT,
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
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

        # Procedural fallback for unmapped tiles
        BLACK = (0, 0, 0)
        BROWN = (140, 100, 50)
        ORANGE = (255, 170, 85)
        YELLOW = (255, 255, 0)

        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2

        if tile_id == TILE_COUNTER:
            # Counter/table on black floor
            pygame.draw.rect(self.screen, BLACK, rect)
            top = pygame.Rect(px + 3, py + 8, ts - 6, ts - 14)
            pygame.draw.rect(self.screen, BROWN, top)
            pygame.draw.rect(self.screen, (100, 70, 30), top, 1)
            pygame.draw.circle(self.screen, YELLOW, (cx, cy), 3)

        elif tile_id == TILE_DOOR:
            # Wooden door on black floor
            pygame.draw.rect(self.screen, BLACK, rect)
            door_rect = pygame.Rect(px + 7, py + 2, ts - 14, ts - 4)
            pygame.draw.rect(self.screen, (100, 65, 30), door_rect)
            pygame.draw.rect(self.screen, (60, 40, 15), door_rect, 1)
            pygame.draw.circle(self.screen, YELLOW, (cx + 3, cy), 2)

        else:
            # Fallback: black
            pygame.draw.rect(self.screen, BLACK, rect)

    def _u3_draw_npc_sprite(self, npc, cx, cy):
        """Draw an NPC on the town map using the tile sheet NPC sprite or stick figure."""
        # Try to use the NPC sprite from the tile sheet (R3 C15)
        npc_sprite = self._tile_sprites.get((3, 15))
        if npc_sprite:
            sx = cx - npc_sprite.get_width() // 2
            sy = cy - npc_sprite.get_height() // 2
            self.screen.blit(npc_sprite, (sx, sy))
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
        """Draw an NPC dialogue box at the top of the screen."""
        if not message:
            return
        box_width = SCREEN_WIDTH - 60
        box_height = 60
        box_x = 30
        box_y = 10

        # Dark box with border
        box_rect = pygame.Rect(box_x, box_y, box_width, box_height)
        pygame.draw.rect(self.screen, (15, 15, 30), box_rect)
        pygame.draw.rect(self.screen, (120, 100, 60), box_rect, 2)

        # Text
        text_surface = self.font.render(message, True, COLOR_WHITE)
        self.screen.blit(text_surface, (box_x + 12, box_y + 10))

        # Hint to dismiss
        hint = "[SPACE / ENTER] continue   [ESC] close"
        hint_surface = self.font_small.render(hint, True, (120, 120, 140))
        self.screen.blit(hint_surface, (box_x + 12, box_y + 36))

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
        """Draw a Y/N quest choice prompt at the bottom of the dialogue area."""
        box_width = SCREEN_WIDTH - 60
        box_height = 50
        box_x = 30
        box_y = 80  # below the dialogue box

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

    def draw_overworld_u3(self, party, tile_map, message="", overworld_monsters=None):
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

        # ── 4. blue border around map ──
        pygame.draw.rect(self.screen, (68, 68, 255),
                         pygame.Rect(0, 0, self._U3_OW_MAP_W, self._U3_OW_MAP_H), 2)

        # ── 5. bottom info bar ──
        bar_y = self._U3_OW_MAP_H
        bar_h = SCREEN_HEIGHT - bar_y
        self._u3_panel(0, bar_y, SCREEN_WIDTH, bar_h)

        tile_name = tile_map.get_tile_name(party.col, party.row)
        f = self.font  # larger 16px font for readability
        # Top line: game info
        self._u3_text(f"GOLD:{party.gold:05d}", 8, bar_y + 6, (255, 255, 0), font=f)
        self._u3_text(f"TERRAIN:{tile_name}", 260, bar_y + 6, (200, 200, 255), font=f)
        light_name = party.get_equipped_name("light")
        if light_name:
            charges = party.get_equipped_charges("light")
            lbl = f"LIGHT:{light_name.upper()}"
            if charges is not None:
                lbl += f":{charges:02d}"
            self._u3_text(lbl, 520, bar_y + 6, (255, 170, 85), font=f)
        self._u3_text(f"POS:({party.col},{party.row})", 750, bar_y + 6, (220, 220, 220), font=f)

        # ── 6. floating message ──
        if message:
            surf = self.font.render(message.upper(), True, (255, 220, 140))
            rect = surf.get_rect(center=(SCREEN_WIDTH // 2, 16))
            bg = rect.inflate(20, 8)
            pygame.draw.rect(self.screen, (0, 0, 0), bg)
            pygame.draw.rect(self.screen, (120, 120, 255), bg, 2)
            self.screen.blit(surf, rect)

    # ── overworld tile rendering ─────────────────────────────

    def _u3_draw_overworld_tile(self, tile_id, px, py, ts, wc, wr):
        """Draw a single overworld tile using sprite sheet art when available,
        falling back to procedural drawing for tiles without sprites."""
        from src.settings import (
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
            TILE_TOWN, TILE_DUNGEON, TILE_PATH, TILE_SAND, TILE_BRIDGE,
        )

        # Try sprite sheet first
        sprite = self._get_tile_sprite(tile_id)
        if sprite:
            self.screen.blit(sprite, (px, py))
            return

        # Fallback: procedural drawing for tiles not in the sheet
        BLACK = (0, 0, 0)
        BROWN = (140, 100, 50)
        SAND  = (180, 160, 80)

        rect = pygame.Rect(px, py, ts, ts)
        seed = wc * 31 + wr * 17

        if tile_id == TILE_SAND:
            pygame.draw.rect(self.screen, (25, 20, 5), rect)
            for i in range(4):
                s = seed + i * 19
                dx = (s * 7) % (ts - 6) + 3
                dy = (s * 13) % (ts - 6) + 3
                c = SAND if s % 2 else (150, 130, 60)
                pygame.draw.rect(self.screen, c,
                                 pygame.Rect(px + dx, py + dy, 2, 2))

        elif tile_id == TILE_BRIDGE:
            pygame.draw.rect(self.screen, (0, 0, 60), rect)
            for i in range(3):
                plank = pygame.Rect(px + 2, py + 6 + i * 10, ts - 4, 5)
                pygame.draw.rect(self.screen, BROWN, plank)
                pygame.draw.rect(self.screen, (80, 60, 30), plank, 1)

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

        self._u3_text(f"GOLD: {party.gold:05d}", tx, ty, (255, 255, 0))

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

    def draw_dungeon_u3(self, party, dungeon_data, message="",
                         visible_tiles=None, torch_steps=-1,
                         level_label=None, detected_traps=None):
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
        for sr in range(rows):
            for sc in range(cols):
                wc = sc + off_c
                wr = sr + off_r
                tid = tile_map.get_tile(wc, wr)
                px = sc * ts
                py = sr * ts
                self._u3_draw_dungeon_tile(tid, px, py, ts, wc, wr)

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

        # ── 4. fog of war ──
        self._u3_dungeon_fog(psc, psr, cols, rows, ts,
                              visible_tiles=visible_tiles, off_c=off_c, off_r=off_r)

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
        self._u3_text(f"GOLD:{party.gold:05d}", 8, bar_y + 6, (255, 255, 0))
        dg_name = dungeon_data.name.upper()
        if level_label:
            dg_name += f"  [{level_label}]"
        self._u3_text(dg_name, 240, bar_y + 6, (200, 60, 60))
        # Light status
        light_name = party.get_equipped_name("light")
        light_charges = party.get_equipped_charges("light")
        if torch_steps >= 0:
            torch_color = (255, 170, 85) if torch_steps > 3 else (200, 60, 60)
            lbl = f"LIGHT:{light_name.upper() if light_name else 'TORCH'}:{torch_steps:02d}"
            self._u3_text(lbl, 520, bar_y + 6, torch_color)
        elif light_name:
            lbl = f"LIGHT:{light_name.upper()}"
            if light_charges is not None:
                lbl += f":{light_charges:02d}"
            self._u3_text(lbl, 520, bar_y + 6, (255, 170, 85))
        else:
            self._u3_text("NO LIGHT", 520, bar_y + 6, (136, 136, 136))
        self._u3_text(f"POS:({party.col},{party.row})", 750, bar_y + 6, (136, 136, 136))
        # Bottom line: controls
        self._u3_text("[ARROWS/WASD] MOVE    [P] PARTY    [ESC] STAIRS",
                      8, bar_y + 28, (68, 68, 255))

        # ── 7. floating message ──
        if message:
            surf = self.font.render(message.upper(), True, (255, 220, 140))
            rect = surf.get_rect(center=(SCREEN_WIDTH // 2, 16))
            bg = rect.inflate(20, 8)
            pygame.draw.rect(self.screen, (0, 0, 0), bg)
            pygame.draw.rect(self.screen, (120, 120, 255), bg, 2)
            self.screen.blit(surf, rect)

    # ── dungeon tile rendering ─────────────────────────────

    def _u3_draw_dungeon_tile(self, tile_id, px, py, ts, wc, wr):
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

        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2
        seed = wc * 31 + wr * 17

        if tile_id == TILE_DWALL:
            # Ornate gray-blue stone blocks (matches example_dungeon)
            pygame.draw.rect(self.screen, (30, 28, 40), rect)
            # Brick pattern with slight color variation
            for iy in range(0, ts, 8):
                offset = 5 if (iy // 8) % 2 else 0
                for ix in range(offset, ts, 11):
                    s = (wc * 7 + wr * 13 + ix + iy) % 5
                    # Vary brick colors for stone texture
                    if s < 2:
                        bc = (75, 70, 90)
                    elif s < 4:
                        bc = (60, 58, 78)
                    else:
                        bc = (85, 80, 100)
                    brick = pygame.Rect(px + ix, py + iy, 9, 6)
                    pygame.draw.rect(self.screen, bc, brick)
                    pygame.draw.rect(self.screen, (40, 38, 55), brick, 1)

        elif tile_id == TILE_DFLOOR:
            # Black floor with subtle stone-crack dots
            pygame.draw.rect(self.screen, BLACK, rect)
            # Sparse gray dots for stone floor texture
            for i in range(2):
                s = seed + i * 41
                if s % 4 < 2:
                    dx = (s * 7) % (ts - 6) + 3
                    dy = (s * 13) % (ts - 6) + 3
                    pygame.draw.rect(self.screen, (30, 28, 35),
                                     pygame.Rect(px + dx, py + dy, 2, 1))

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

        else:
            # Fallback: black
            pygame.draw.rect(self.screen, BLACK, rect)

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
                f"HP:{member.hp:04d}/{member.max_hp:04d}  AC:{member.get_ac():02d}",
                tx, ty)

            ty += 16
            self._u3_text(
                f"S:{member.strength:02d} D:{member.dexterity:02d} I:{member.intelligence:02d} W:{member.wisdom:02d}",
                tx, ty, (136, 136, 136))

            ty += 16
            self._u3_text(
                f"LVL:{member.level:02d}  EXP:{member.exp:04d}",
                tx, ty, (136, 136, 136))

            ty += 16
            self._u3_text(f"WPN: {member.weapon}", tx, ty, (136, 136, 136))

        # Bottom info block
        info_y = y + 4 * block_h
        info_h = SCREEN_HEIGHT - info_y - 24
        self._u3_panel(x, info_y, w, info_h)
        tx = x + 8
        ty = info_y + 6

        self._u3_text(f"GOLD: {party.gold:05d}", tx, ty, (255, 255, 0))

        ty += 18
        self._u3_text(f"DUNGEON: {dungeon_data.name}", tx, ty, (200, 60, 60))

        ty += 18
        tile_name = dungeon_data.tile_map.get_tile_name(party.col, party.row)
        self._u3_text(f"TILE: {tile_name}", tx, ty, (68, 68, 255))

        ty += 18
        self._u3_text(f"POS: ({party.col},{party.row})", tx, ty, (136, 136, 136))

        ty += 18
        chests = len(dungeon_data.opened_chests)
        self._u3_text(f"CHESTS: {chests:02d}", tx, ty, (255, 170, 85))

    # ========================================================
    # COMBAT ARENA  –  Ultima III retro style
    # ========================================================

    # ── Retro colour palette (C64 / Apple II inspired) ──
    _U3_BLACK  = (0, 0, 0)
    _U3_BLUE   = (68, 68, 255)
    _U3_LTBLUE = (160, 160, 255)   # brighter blue for readable text
    _U3_WHITE  = (255, 255, 255)
    _U3_ORANGE = (255, 170, 85)
    _U3_GREEN  = (0, 170, 0)
    _U3_DKGRN  = (0, 102, 0)
    _U3_RED    = (200, 60, 60)
    _U3_GRAY   = (136, 136, 136)
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
                          shield_target_col=0,
                          shield_target_row=0,
                          turn_undead_effects=None,
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
                self._u3_draw_party_member_sprite(
                    mx, my, ts, col, row, member, is_active)

            # Draw persistent shield bubbles over buffed fighters
            if shield_buffs:
                for member, buff in shield_buffs.items():
                    if member.is_alive() and member in fighter_positions:
                        sc, sr = fighter_positions[member]
                        self._u3_draw_shield_bubble(mx, my, ts, sc, sr,
                                                    buff["turns_left"])
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
            for fx in hit_effects:
                if fx.alive:
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

        # ── 3. arena blue border ──
        pygame.draw.rect(self.screen, self._U3_BLUE,
                         pygame.Rect(mx - 2, my - 2,
                                     self._MAP_W + 4, self._MAP_H + 4), 2)

        # ── 4. right-hand panels ──
        rx = self._RPANEL_X
        rw = self._RPANEL_W

        # Party roster panel (shows all 4 members with sprites and bars)
        party_h = 300
        if fighters:
            self._u3_party_combat_panel(fighters, active_fighter,
                                        defending_map or {},
                                        rx, 4, rw, party_h,
                                        shield_buffs=shield_buffs or {})
        else:
            self._u3_fighter_panel(fighter, defending, rx, 4, rw, 138,
                                   shield_buffs=shield_buffs or {})
            party_h = 138

        monster_y = 4 + party_h + 4
        alive_monsters = [m for m in (monsters or []) if m.is_alive()] if monsters else ([monster] if monster and monster.is_alive() else [])
        monster_panel_h = max(50, 28 + 68 * len(alive_monsters))
        self._u3_monster_panel_multi(alive_monsters, rx, monster_y, rw, monster_panel_h,
                                     source_state=is_outdoor and "overworld" or "dungeon",
                                     encounter_name=encounter_name)
        action_y = monster_y + monster_panel_h + 4
        arena_bottom = my + self._MAP_H
        action_h = arena_bottom - action_y
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
                                      member, is_active):
        """Draw a party member on the combat arena using loaded sprite.
        Active member gets a highlight ring. Falls back to stick figure."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2

        color = self._CLASS_COLORS.get(member.char_class.lower(),
                                        self._U3_WHITE)

        # Try to use loaded sprite
        sprite = self._get_class_sprite(member.char_class, big=False)
        if sprite:
            # Center the sprite on the tile
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: stick figure
            BLU = (120, 120, 255)
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

        # Name label below
        name_surf = self.font_small.render(member.name[0].upper(), True, color)
        self.screen.blit(name_surf, (cx - 3, cy + 14))

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
                                shield_buffs=None):
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
            sprite = self._get_class_sprite(member.char_class)
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
        self._u3_text(f"HP:{fighter.hp:04d}/{fighter.max_hp:04d}  AC:{ac:02d}",
                      tx, ty, self._U3_WHITE, f)
        if defending:
            self._u3_text("DEF", tx + 220, ty, self._U3_ORANGE, f)
        if shield:
            label_x = tx + 220 + (32 if defending else 0)
            self._u3_text("SHLD", label_x, ty, (100, 180, 255), f)

        ty += 18
        self._u3_text(f"S:{fighter.strength:02d} D:{fighter.dexterity:02d} I:{fighter.intelligence:02d} W:{fighter.wisdom:02d}",
                      tx, ty, (200, 200, 200), f)

        ty += 18
        self._u3_text(f"LVL:{fighter.level:02d}  EXP:{fighter.exp:04d}",
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
        atk_text = f"ATK:+{monster.attack_bonus:02d}  DMG:{monster.damage_dice}D{monster.damage_sides}+{monster.damage_bonus}"
        self._u3_text(atk_text, info_x, stat_y, (200, 200, 200), self.font_small)

    def _u3_monster_panel_multi(self, monsters, x, y, w, h,
                               source_state="dungeon", encounter_name=None):
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
            name_color = self._U3_RED if mon.is_alive() else (120, 40, 40)
            self._u3_text(mon.name, info_x, row_top, name_color, f)

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
                for i, (action_id, label) in enumerate(menu_actions):
                    iy = ty + 28 + i * 24
                    selected = (i == selected_action)
                    prefix = "> " if selected else "  "
                    color = self._U3_WHITE if selected else self._U3_LTBLUE
                    self._u3_text(prefix + label.upper(), tx, iy, color, f)


        elif phase == PHASE_SPELL_SELECT:
            # Spell selection sub-menu
            name = active_fighter.name if active_fighter else "???"
            self._u3_text(f"-- {name.upper()}'S SPELLS --", tx, ty, self._U3_ORANGE, f)

            if spell_list:
                for i, (spell_id, label, mp_cost) in enumerate(spell_list):
                    iy = ty + 28 + i * 24
                    sel = (i == spell_cursor)
                    prefix = "> " if sel else "  "
                    color = self._U3_WHITE if sel else self._U3_LTBLUE
                    self._u3_text(prefix + label.upper(), tx, iy, color, f)
            else:
                self._u3_text("  NO SPELLS AVAILABLE", tx, ty + 28, (160, 160, 160), f)


        elif phase == PHASE_THROW_SELECT:
            # Throw item selection sub-menu
            name = active_fighter.name if active_fighter else "???"
            self._u3_text(f"-- THROW ITEM --", tx, ty, self._U3_ORANGE, f)

            if throw_list:
                for i, (item_name, count) in enumerate(throw_list):
                    iy = ty + 28 + i * 24
                    sel = (i == throw_cursor)
                    prefix = "> " if sel else "  "
                    color = self._U3_WHITE if sel else self._U3_LTBLUE
                    label = f"{item_name.upper()} x{count}"
                    self._u3_text(prefix + label, tx, iy, color, f)
            else:
                self._u3_text("  NO THROWABLE ITEMS", tx, ty + 28, (160, 160, 160), f)


        elif phase == PHASE_USE_ITEM:
            # Use item selection sub-menu
            name = active_fighter.name if active_fighter else "???"
            self._u3_text(f"-- USE ITEM --", tx, ty, self._U3_ORANGE, f)

            if use_item_list:
                for i, (item_name, count, effect, power) in enumerate(use_item_list):
                    iy = ty + 28 + i * 24
                    sel = (i == use_item_cursor)
                    prefix = "> " if sel else "  "
                    color = self._U3_WHITE if sel else self._U3_LTBLUE
                    label = f"{item_name.upper()} x{count}"
                    self._u3_text(prefix + label, tx, iy, color, f)
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

    def draw_title_screen(self, options, cursor, elapsed):
        """Draw the title screen with ASCII art, menu options, and animation.

        Parameters
        ----------
        options : list of dicts with 'label' keys
        cursor  : which option is highlighted
        elapsed : total seconds since title screen appeared (for animations)
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
            subtitle = "An Ultima III Tribute"
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
            # Panel behind menu
            panel_w = 320
            panel_h = 30 + len(options) * 40 + 20
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

        # ── Bottom hints ──
        hint_fade = min(1.0, max(0.0, (elapsed - 3.0) / 1.0))
        if hint_fade > 0:
            hint_color = (int(68 * hint_fade), int(68 * hint_fade),
                          int(200 * hint_fade))
            hint = "[UP/DOWN] SELECT   [ENTER] CHOOSE"
            hw = len(hint) * 5
            self._u3_text(hint,
                          SCREEN_WIDTH // 2 - hw // 2,
                          SCREEN_HEIGHT - 50,
                          hint_color, self.font_small)

            # Copyright / credits
            cr_color = (int(60 * hint_fade), int(60 * hint_fade),
                        int(80 * hint_fade))
            credit = "Inspired by Ultima III: Exodus  (c) 1983 Origin Systems"
            cw = len(credit) * 5
            self._u3_text(credit,
                          SCREEN_WIDTH // 2 - cw // 2,
                          SCREEN_HEIGHT - 28,
                          cr_color, self.font_small)

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
            sprite = self._get_class_sprite(member.char_class, big=True)
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
                f"{member.hp:04d}/{member.max_hp:04d}",
                bar_x + bar_w + 6, ty, self._U3_WHITE, fm)

            # MP bar + text
            ty += 18
            mp_color = (100, 100, 255)
            self._u3_text("MP:", tx, ty, (220, 220, 230), fm)
            if member.max_mp > 0:
                self._u3_draw_stat_bar(bar_x, ty + 1, bar_w, bar_h,
                                       member.current_mp, member.max_mp, mp_color)
                self._u3_text(
                    f"{member.current_mp:04d}/{member.max_mp:04d}",
                    bar_x + bar_w + 6, ty, self._U3_WHITE, fm)
            else:
                self._u3_text("----/----", bar_x + bar_w + 6, ty, (120, 120, 120), fm)

            # Stats
            ty += 20
            self._u3_text(
                f"STR:{member.strength:02d}  DEX:{member.dexterity:02d}  "
                f"INT:{member.intelligence:02d}  WIS:{member.wisdom:02d}",
                tx, ty, self._U3_LTBLUE, fm)

            # Level / EXP
            ty += 20
            self._u3_text(
                f"LVL:{member.level:02d}  EXP:{member.exp:04d}  AC:{member.get_ac():02d}",
                tx, ty, self._U3_WHITE, fm)

            # Weapon info
            ty += 22
            wp = WEAPONS.get(member.weapon, {"power": 0, "ranged": False})
            rng = "RANGED" if wp["ranged"] else "MELEE"
            ammo_str = f"  x{member.get_ammo()}" if member.is_throwable_weapon() else ""
            self._u3_text("WPN:", tx, ty, self._U3_LTBLUE, fm)
            self._u3_text(
                f"{member.weapon}  (PWR:{wp['power']:02d} {rng}){ammo_str}",
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
            self._u3_text(f"{dmg:02d}", tx + 88, ty, self._U3_WHITE, fm)

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
            self._u3_text(f"GOLD: {party.gold:05d}", 14, info_y + 6,
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
        sprite = self._get_class_sprite(member.char_class, big=True)
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
        ty += 20
        self._u3_text(f"LEVEL: {member.level:02d}", tx, ty, self._U3_WHITE, fm)
        self._u3_text(f"EXP: {member.exp:04d}", tx + 120, ty, (220, 220, 230), fm)

        # ── HP bar ──
        ty += 28
        hp_color = self._U3_GREEN if member.hp > member.max_hp * 0.3 else self._U3_RED
        self._u3_text("HIT POINTS", tx, ty, self._U3_LTBLUE, fm)
        ty += 18
        bar_w = left_w - 100
        bar_h = 14
        self._u3_draw_stat_bar(tx, ty, bar_w, bar_h,
                               member.hp, member.max_hp, hp_color)
        self._u3_text(
            f"{member.hp:04d} / {member.max_hp:04d}",
            tx + bar_w + 8, ty, self._U3_WHITE, fm)

        # ── MP bar ──
        ty += 24
        self._u3_text("MAGIC POINTS", tx, ty, self._U3_LTBLUE, fm)
        ty += 18
        if member.max_mp > 0:
            self._u3_draw_stat_bar(tx, ty, bar_w, bar_h,
                                   member.current_mp, member.max_mp, (100, 100, 255))
            self._u3_text(
                f"{member.current_mp:04d} / {member.max_mp:04d}",
                tx + bar_w + 8, ty, self._U3_WHITE, fm)
        else:
            self._u3_draw_stat_bar(tx, ty, bar_w, bar_h, 0, 1, (60, 60, 60))
            self._u3_text("---- / ----", tx + bar_w + 8, ty, (120, 120, 120), fm)

        # ── Attributes with modifiers ──
        ty += 30
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
            self._u3_text(f"{val:02d}", tx + 42, ty, self._U3_WHITE, fm)
            mod_color = self._U3_GREEN if mod > 0 else self._U3_RED if mod < 0 else (180, 180, 180)
            self._u3_text(f"({mod_str})", tx + 68, ty, mod_color, fm)
            ty += 18

        # ── Status ──
        ty += 8
        status = "ALIVE" if member.is_alive() else "DEAD"
        sc = self._U3_GREEN if member.is_alive() else self._U3_RED
        self._u3_text("STATUS:", tx, ty, self._U3_LTBLUE, fm)
        self._u3_text(status, tx + 78, ty, sc, fm)

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
                # Equipped slot row
                display_name = item_name if item_name else "-- NONE --"
                name_color = self._U3_WHITE if selected else self._U3_LTBLUE

                # Slot label
                self._u3_text(f"{prefix}{slot_label}:", rx, ry, name_color, fm)
                # Item name (offset enough to clear longest label "RIGHT HAND:")
                item_x = rx + 120
                if item_name:
                    self._u3_text(f"{display_name}", item_x, ry, self._U3_WHITE if selected else (220, 220, 230), fm)
                    # Stat hint
                    hint = ""
                    if slot_key == "body":
                        arm = ARMORS.get(item_name, {"evasion": 50})
                        hint = f"EVD:{arm['evasion']}%"
                    elif slot_key == "head":
                        hint = ""  # head slot — no stat preview yet
                    elif slot_key in ("right_hand", "left_hand"):
                        wp = WEAPONS.get(item_name, {"power": 0})
                        hint = f"PWR:{wp['power']:02d}"
                    if hint:
                        self._u3_text(hint, rx + right_w - 90, ry, (180, 180, 180), fm)
                else:
                    self._u3_text("-- NONE --", item_x, ry, (120, 120, 120), fm)

                # Highlight bar behind selected row
                if selected:
                    sel_rect = pygame.Rect(rx - 4, ry - 1, right_w - 16, row_h)
                    sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                    sel_surf.fill((255, 255, 255, 25))
                    self.screen.blit(sel_surf, sel_rect)

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
        if len(inv) == 0 and list_row == 3:
            ry += 10
            self._u3_text("ITEMS", rx, ry, self._U3_ORANGE, fm)
            ry += 22
            self._u3_text("  (EMPTY)", rx, ry, (120, 120, 120), fm)

        # ── Combat summary (compact) ──
        ry += 16
        pygame.draw.line(self.screen, (60, 60, 80),
                         (rx, ry), (rx + right_w - 24, ry), 1)
        ry += 8
        ac = member.get_ac()
        est_dmg = member.get_damage()
        self._u3_text(f"AC:{ac:02d}  ATK:D20{format_modifier(member.get_attack_bonus())}  DMG:{est_dmg:02d}",
                      rx, ry, self._U3_LTBLUE, fm)

        # ── Magic summary (compact) ──
        ry += 20
        magic_types = []
        if member.can_cast_priest():
            magic_types.append("PRIEST")
        if member.can_cast_sorcerer():
            magic_types.append("SORCERER")
        magic_str = " + ".join(magic_types) if magic_types else "NONE"
        self._u3_text(f"MAGIC: {magic_str}", rx, ry, (180, 180, 255) if magic_types else (150, 150, 150), fm)

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
        from src.party import SHOP_INVENTORY, WEAPONS, ARMORS, ITEM_INFO, get_sell_price

        fm = self.font_med
        f = self.font
        self.screen.fill(self._U3_BLACK)

        buy_items = list(SHOP_INVENTORY.keys())
        sell_items = party.shared_inventory

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

            items = buy_items
            max_visible = (panel_h - 60) // row_h
            scroll_top = 0
            if len(items) > max_visible:
                scroll_top = max(0, min(cursor_index - max_visible // 2,
                                        len(items) - max_visible))

            for vi, item_idx in enumerate(
                    range(scroll_top, min(scroll_top + max_visible, len(items)))):
                item_name = items[item_idx]
                selected = (item_idx == cursor_index)
                prefix = "> " if selected else "  "
                name_color = self._U3_WHITE if selected else (220, 220, 230)
                cost = SHOP_INVENTORY[item_name]["buy"]

                self._u3_text(f"{prefix}{item_name}", tx, ty, name_color, fm)
                # Price on the right
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
            if scroll_top + max_visible < len(items):
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
                items = sell_items
                max_visible = (panel_h - 60) // row_h
                scroll_top = 0
                if len(items) > max_visible:
                    scroll_top = max(0, min(cursor_index - max_visible // 2,
                                            len(items) - max_visible))

                for vi, item_idx in enumerate(
                        range(scroll_top,
                              min(scroll_top + max_visible, len(items)))):
                    entry = items[item_idx]
                    item_name = party.item_name(entry)
                    item_ch = party.item_charges(entry)
                    selected = (item_idx == cursor_index)
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
                if scroll_top + max_visible < len(items):
                    self._u3_text("v MORE v", tx + left_w // 2 - 50,
                                  panel_y + panel_h - 18, self._U3_GRAY,
                                  self.font_small)

        # ═══════════════════════════════════════
        # RIGHT PANEL — Item details + gold
        # ═══════════════════════════════════════
        rx = right_x + 10
        ry = panel_y + 10

        # Determine selected item
        sel_item = None
        if mode == "buy" and buy_items and 0 <= cursor_index < len(buy_items):
            sel_item = buy_items[cursor_index]
        elif mode == "sell" and sell_items and 0 <= cursor_index < len(sell_items):
            sel_item = party.item_name(sell_items[cursor_index])

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
                self._u3_text(f"POWER: {wp['power']:02d}", rx, ry,
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
        self._u3_text(f"GOLD: {party.gold:05d}", rx + 30, gold_y + 2,
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
                                 effect_cursor=0):
        """
        Full-screen shared party inventory with party equipment slots.

        The list is unified: first 4 rows are party equipment slots,
        followed by shared inventory items.

        Modes:
        - Normal: browse items with cursor, Enter to open action menu.
        - action_menu: choose from context-sensitive options.
        """
        from src.party import WEAPONS, ARMORS, ITEM_INFO

        NUM_SLOTS = len(party.PARTY_SLOTS)
        fm = self.font_med
        f = self.font
        self.screen.fill(self._U3_BLACK)

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
        # LEFT PANEL — Equipped slots + Item list
        # ═══════════════════════════════════════
        tx = left_x + 12
        ty = panel_y + 10

        # ── Party equipment section ──
        self._u3_text("PARTY EQUIPMENT", tx, ty, self._U3_ORANGE, fm)
        ty += 24

        for si, slot_key in enumerate(party.PARTY_SLOTS):
            slot_label = party.PARTY_SLOT_LABELS.get(slot_key, slot_key.upper())
            item_name = party.get_equipped_name(slot_key)
            charges = party.get_equipped_charges(slot_key)
            selected = (si == cursor_index)
            prefix = "> " if selected else "  "

            name_color = self._U3_WHITE if selected else self._U3_LTBLUE
            self._u3_text(f"{prefix}{slot_label}:", tx, ty, name_color, fm)

            if item_name:
                display = item_name
                if charges is not None:
                    display = f"{item_name} ({charges})"
                item_color = self._U3_WHITE if selected else (220, 220, 230)
                self._u3_text(display, tx + 120, ty, item_color, fm)
            else:
                self._u3_text("-- EMPTY --", tx + 120, ty, (120, 120, 120), fm)

            if selected:
                sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
                sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                sel_surf.fill((255, 255, 255, 25))
                self.screen.blit(sel_surf, sel_rect)

            ty += row_h

        # ── Divider between equipment and effects ──
        ty += 6
        pygame.draw.line(self.screen, (60, 60, 80),
                         (tx, ty), (tx + left_w - 32, ty), 1)
        ty += 8

        # ── Effects section ──
        self._u3_text("EFFECTS", tx, ty, self._U3_ORANGE, fm)
        ty += 24

        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        for ei, slot_key in enumerate(party.EFFECT_SLOTS):
            effect = party.get_effect(slot_key)
            global_ei = ei + NUM_SLOTS
            selected = (global_ei == cursor_index)
            prefix = "> " if selected else "  "

            slot_num = f"{ei + 1}."
            name_color = self._U3_WHITE if selected else self._U3_LTBLUE
            self._u3_text(f"{prefix}{slot_num}", tx, ty, name_color, fm)

            if effect:
                eff_color = self._U3_WHITE if selected else (220, 220, 230)
                self._u3_text(effect, tx + 40, ty, eff_color, fm)
            else:
                self._u3_text("-- EMPTY --", tx + 40, ty, (120, 120, 120), fm)

            if selected:
                sel_rect = pygame.Rect(tx - 4, ty - 1, left_w - 24, row_h)
                sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                sel_surf.fill((255, 255, 255, 25))
                self.screen.blit(sel_surf, sel_rect)

            ty += row_h

        # ── Divider between effects and stash ──
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
            # Compute visible window (scroll if list is long)
            stash_area_top = ty
            stash_area_h = panel_y + panel_h - ty - 10
            max_visible = stash_area_h // row_h

            scroll_top = 0
            header_count = NUM_SLOTS + NUM_EFFECTS
            inv_cursor = cursor_index - header_count  # cursor relative to inventory
            if len(inv) > max_visible:
                scroll_top = max(0, min(inv_cursor - max_visible // 2,
                                        len(inv) - max_visible))

            for vi, item_idx in enumerate(range(scroll_top, min(scroll_top + max_visible, len(inv)))):
                entry = inv[item_idx]
                item_name = party.item_name(entry)
                item_ch = party.item_charges(entry)
                global_idx = item_idx + header_count
                selected = (global_idx == cursor_index)
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
                    wp = WEAPONS[item_name]
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
            if scroll_top + max_visible < len(inv):
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

        char_card_h = 50
        sprite_w = 36  # space reserved for avatar
        for mi, member in enumerate(party.members):
            cy = ry
            alive = member.is_alive()
            name_color = self._U3_WHITE if alive else self._U3_RED

            # Avatar sprite
            sprite = self._get_class_sprite(member.char_class, big=False)
            if sprite:
                sx = rx
                sy = cy + (char_card_h - sprite.get_height()) // 2
                if not alive:
                    dark = sprite.copy()
                    dark.fill((80, 80, 80), special_flags=pygame.BLEND_RGB_MULT)
                    self.screen.blit(dark, (sx, sy))
                else:
                    self.screen.blit(sprite, (sx, sy))

            # Text starts after avatar
            tx2 = rx + sprite_w

            # Number + name + class
            self._u3_text(f"{mi+1}", tx2, cy, self._U3_BLUE, fm)
            self._u3_text(member.name, tx2 + 16, cy, name_color, fm)
            cls_short = member.char_class[:3].upper()
            self._u3_text(cls_short, rx + right_w - 60, cy, self._U3_LTBLUE, fm)

            # HP bar
            cy += 16
            hp_frac = member.hp / member.max_hp if member.max_hp > 0 else 0
            hp_color = self._U3_GREEN if hp_frac > 0.3 else self._U3_RED
            bar_w_px = right_w - sprite_w - 80
            self._u3_text("HP", tx2, cy, (180, 180, 200), self.font_small)
            self._u3_draw_stat_bar(tx2 + 22, cy + 1, bar_w_px, 10,
                                   member.hp, member.max_hp, hp_color)
            self._u3_text(f"{member.hp}/{member.max_hp}",
                          tx2 + 22 + bar_w_px + 4, cy, (200, 200, 210), self.font_small)

            # Weapon summary
            cy += 14
            rw_name = member.equipped.get("right_hand") or "---"
            lw_name = member.equipped.get("left_hand") or "---"
            equip_str = f"R:{rw_name}  L:{lw_name}"
            self._u3_text(equip_str, tx2 + 4, cy, (160, 160, 180), self.font_small)

            ry += char_card_h

        # ── Divider ──
        ry += 2
        pygame.draw.line(self.screen, (60, 60, 80),
                         (rx, ry), (rx + right_w - 20, ry), 1)
        ry += 8

        # ── Item detail section ──
        sel_item = None
        sel_charges = None
        is_equip_slot = cursor_index < NUM_SLOTS
        is_effect_slot = (NUM_SLOTS <= cursor_index < NUM_SLOTS + NUM_EFFECTS)
        header_count = NUM_SLOTS + NUM_EFFECTS
        if is_equip_slot:
            slot_key = party.PARTY_SLOTS[cursor_index]
            sel_item = party.get_equipped_name(slot_key)
            sel_charges = party.get_equipped_charges(slot_key)
        elif is_effect_slot:
            eff_idx = cursor_index - NUM_SLOTS
            eff_slot_key = party.EFFECT_SLOTS[eff_idx]
            sel_item = party.get_effect(eff_slot_key)
        elif cursor_index - header_count < len(inv):
            entry = inv[cursor_index - header_count]
            sel_item = party.item_name(entry)
            sel_charges = party.item_charges(entry)

        # Show details of the selected item
        if sel_item:
            if is_equip_slot:
                slot_label = party.PARTY_SLOT_LABELS.get(slot_key, slot_key.upper())
                self._u3_text(f"EQUIPPED ({slot_label})", rx, ry, self._U3_ORANGE, fm)
            elif is_effect_slot:
                self._u3_text("ACTIVE EFFECT", rx, ry, self._U3_ORANGE, fm)
            else:
                self._u3_text("SELECTED", rx, ry, self._U3_ORANGE, fm)
            ry += 22
            self._u3_text(sel_item, rx, ry, self._U3_WHITE, f)
            ry += 24

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
                self._u3_text(f"POWER: {wp['power']:02d}", rx, ry, (220, 220, 230), fm)
                ry += 18
                self._u3_text("SLOT: RIGHT HAND", rx, ry, (180, 180, 180), fm)
            else:
                self._u3_text("TYPE: GENERAL ITEM", rx, ry, self._U3_LTBLUE, fm)

            # Charges (for equipped items with charges)
            if sel_charges is not None:
                ry += 18
                self._u3_text(f"CHARGES: {sel_charges}", rx, ry, (255, 170, 85), fm)

            # Description
            info = ITEM_INFO.get(sel_item)
            if info and info.get("desc"):
                ry += 24
                desc = info["desc"]
                # Word-wrap description
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
        elif is_equip_slot:
            slot_label = party.PARTY_SLOT_LABELS.get(slot_key, slot_key.upper())
            self._u3_text(f"{slot_label} SLOT", rx, ry, self._U3_ORANGE, fm)
            ry += 22
            self._u3_text("(EMPTY)", rx, ry, (120, 120, 120), fm)
        elif is_effect_slot:
            self._u3_text("EFFECT SLOT", rx, ry, self._U3_ORANGE, fm)
            ry += 22
            self._u3_text("(EMPTY)", rx, ry, (120, 120, 120), fm)
        else:
            self._u3_text("NO ITEMS", rx, ry, (120, 120, 120), fm)


        # ── Gold display with chest icon ──
        gold_y = panel_y + panel_h - 30
        self._draw_item_icon(rx + 12, gold_y + 8, "chest", 28)
        self._u3_text(f"GOLD: {party.gold:05d}", rx + 30, gold_y + 2, (255, 255, 0), fm)

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

        # ── Effect chooser popup ──
        if choosing_effect and effect_list:
            efl = effect_list
            popup_w = 340
            popup_h = 28 + len(efl) * 22 + 8
            popup_x = SCREEN_WIDTH // 2 - popup_w // 2
            popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

            pygame.draw.rect(self.screen, (20, 20, 40),
                             (popup_x, popup_y, popup_w, popup_h))
            pygame.draw.rect(self.screen, self._U3_ORANGE,
                             (popup_x, popup_y, popup_w, popup_h), 2)

            self._u3_text("ASSIGN EFFECT", popup_x + 10, popup_y + 6,
                          self._U3_ORANGE, fm)
            oy = popup_y + 28
            for ei, eff in enumerate(efl):
                sel = (ei == effect_cursor)
                prefix = "> " if sel else "  "
                col = self._U3_WHITE if sel else self._U3_LTBLUE
                dur = eff["duration"]
                dur_str = "PERM" if dur == "permanent" else f"{dur} steps"
                self._u3_text(f"{prefix}{eff['name']}", popup_x + 10, oy,
                              col, fm)
                self._u3_text(dur_str, popup_x + popup_w - 100, oy,
                              (160, 160, 180), self.font_small)
                if sel:
                    hl = pygame.Rect(popup_x + 4, oy - 1, popup_w - 8, 20)
                    hl_s = pygame.Surface((hl.w, hl.h), pygame.SRCALPHA)
                    hl_s.fill((255, 255, 255, 25))
                    self.screen.blit(hl_s, hl)
                oy += 22

        # ── Bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        if choosing_effect:
            self._u3_text("[UP/DN] SELECT  [ENTER] ASSIGN  [ESC] CANCEL",
                          8, bar_y + 5, self._U3_BLUE)
        elif action_menu:
            self._u3_text("[UP/DN] SELECT  [ENTER] CONFIRM  [ESC] CANCEL",
                          8, bar_y + 5, self._U3_BLUE)
        else:
            self._u3_text("[UP/DN] SELECT  [ENTER] ACTION  [1-4] CHARACTER  [ESC] BACK",
                          8, bar_y + 5, self._U3_BLUE)

    # ═══════════════════════════════════════════════════════════════
    # ITEM EXAMINATION OVERLAY
    # ═══════════════════════════════════════════════════════════════

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
            self._u3_text(f"{pwr:02d}", name_x + 65, ty, pwr_color, fm)
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

        log_entries : list[str]  – all accumulated log messages
        scroll_offset : int      – how many lines scrolled up from the bottom
        """
        # Dim background
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        self.screen.blit(dim, (0, 0))

        # Log panel
        margin = 40
        px = margin
        py = margin
        pw = SCREEN_WIDTH - margin * 2
        ph = SCREEN_HEIGHT - margin * 2

        pygame.draw.rect(self.screen, (12, 12, 24), (px, py, pw, ph))
        pygame.draw.rect(self.screen, self._U3_LTBLUE, (px, py, pw, ph), 2)

        # Title
        self._u3_text("GAME LOG", px + pw // 2 - 40, py + 8,
                       self._U3_ORANGE, self.font)

        # Hints
        self._u3_text("[UP/DOWN] SCROLL    [L/ESC] CLOSE",
                      px + pw // 2 - 130, py + ph - 20,
                      self._U3_BLUE, self.font_small)

        # Content area
        content_y = py + 32
        content_h = ph - 56  # room for title + hint
        line_h = 16
        max_visible = content_h // line_h

        if not log_entries:
            self._u3_text("No log entries yet.",
                          px + 16, content_y + 8, self._U3_GRAY, self.font)
            return

        total = len(log_entries)

        # scroll_offset 0 = bottom (most recent visible)
        # Clamp scroll
        max_scroll = max(0, total - max_visible)
        scroll_offset = max(0, min(scroll_offset, max_scroll))

        # Which entries to show
        end_idx = total - scroll_offset
        start_idx = max(0, end_idx - max_visible)
        visible = log_entries[start_idx:end_idx]

        for i, line in enumerate(visible):
            ly = content_y + i * line_h
            # Color code based on content
            if "CRITICAL" in line or "defeated" in line.lower():
                color = (255, 200, 80)
            elif "Hit!" in line or "damage" in line:
                color = self._U3_WHITE
            elif "Miss" in line or "Failed" in line:
                color = (160, 160, 170)
            elif line.startswith("--"):
                color = self._U3_ORANGE
            elif "gold" in line.lower() or "treasure" in line.lower():
                color = (255, 255, 0)
            else:
                color = (180, 180, 200)
            self._u3_text(line, px + 16, ly, color, self.font_small)

        # Scroll indicator
        if scroll_offset > 0:
            self._u3_text("v MORE v", px + pw // 2 - 30,
                          content_y + content_h - 14,
                          self._U3_LTBLUE, self.font_small)
        if end_idx < total or start_idx > 0:
            if scroll_offset < max_scroll:
                self._u3_text("^ MORE ^", px + pw // 2 - 30,
                              content_y, self._U3_LTBLUE, self.font_small)
