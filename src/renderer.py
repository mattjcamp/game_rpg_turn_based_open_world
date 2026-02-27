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

    _U3_TN_COLS = 25       # tiles visible horizontally (full width)
    _U3_TN_ROWS = 17       # tiles visible vertically
    _U3_TN_TS   = 32       # tile size
    _U3_TN_MAP_W = _U3_TN_COLS * _U3_TN_TS   # 800
    _U3_TN_MAP_H = _U3_TN_ROWS * _U3_TN_TS   # 544

    def draw_town_u3(self, party, town_data, message=""):
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

        # ── 3. party sprite ──
        psc = party.col - off_c
        psr = party.row - off_r
        if 0 <= psc < cols and 0 <= psr < rows:
            cx = psc * ts + ts // 2
            cy = psr * ts + ts // 2
            self._u3_draw_overworld_party(cx, cy)

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
        self._u3_text(town_data.name.upper(), 200, bar_y + 6, (255, 170, 85))
        light_name = party.get_equipped_name("light")
        if light_name:
            charges = party.get_equipped_charges("light")
            lbl = f"LIGHT:{light_name.upper()}"
            if charges is not None:
                lbl += f":{charges:02d}"
            self._u3_text(lbl, 420, bar_y + 6, (255, 170, 85))
        self._u3_text(f"POS:({party.col},{party.row})", 620, bar_y + 6, (136, 136, 136))
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
    _U3_OW_COLS = 25       # tiles visible horizontally (full width)
    _U3_OW_ROWS = 17       # tiles visible vertically
    _U3_OW_TS   = 32       # tile size (same as global TILE_SIZE)
    _U3_OW_MAP_W = _U3_OW_COLS * _U3_OW_TS   # 800
    _U3_OW_MAP_H = _U3_OW_ROWS * _U3_OW_TS   # 544

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
            orc_sprite = self._tile_sprites.get((1, 8))  # Orc sprite
            for mon in overworld_monsters:
                if not mon.is_alive():
                    continue
                msc = mon.col - off_c
                msr = mon.row - off_r
                if 0 <= msc < cols and 0 <= msr < rows:
                    mx = msc * ts + ts // 2
                    my = msr * ts + ts // 2
                    if orc_sprite:
                        sx = mx - orc_sprite.get_width() // 2
                        sy = my - orc_sprite.get_height() // 2
                        self.screen.blit(orc_sprite, (sx, sy))

        # ── 3. party sprite ──
        psc = party.col - off_c
        psr = party.row - off_r
        if 0 <= psc < cols and 0 <= psr < rows:
            cx = psc * ts + ts // 2
            cy = psr * ts + ts // 2
            self._u3_draw_overworld_party(cx, cy)

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
        self._u3_text(f"TERRAIN:{tile_name}", 220, bar_y + 6, (200, 200, 255), font=f)
        light_name = party.get_equipped_name("light")
        if light_name:
            charges = party.get_equipped_charges("light")
            lbl = f"LIGHT:{light_name.upper()}"
            if charges is not None:
                lbl += f":{charges:02d}"
            self._u3_text(lbl, 420, bar_y + 6, (255, 170, 85), font=f)
        self._u3_text(f"POS:({party.col},{party.row})", 600, bar_y + 6, (220, 220, 220), font=f)
        # Bottom line: controls
        self._u3_text("[ARROWS/WASD] MOVE    [P] PARTY    [ESC] QUIT",
                      8, bar_y + 28, (200, 200, 255), font=f)

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

    def _u3_draw_overworld_party(self, cx, cy):
        """White warrior party sprite with visible sword and shield."""
        W = (255, 255, 255)
        DK = (180, 180, 180)   # slight shade for depth
        # Head
        pygame.draw.circle(self.screen, W, (cx, cy - 9), 5)
        pygame.draw.circle(self.screen, DK, (cx, cy - 9), 5, 1)
        # Body
        pygame.draw.line(self.screen, W, (cx, cy - 4), (cx, cy + 4), 3)
        # Arms — angled: left arm holds shield up, right arm holds sword
        pygame.draw.line(self.screen, W, (cx, cy - 2), (cx - 8, cy - 6), 2)
        pygame.draw.line(self.screen, W, (cx, cy - 2), (cx + 8, cy - 6), 2)
        # Legs
        pygame.draw.line(self.screen, W, (cx, cy + 4), (cx - 5, cy + 13), 2)
        pygame.draw.line(self.screen, W, (cx, cy + 4), (cx + 5, cy + 13), 2)

        # ── Sword (right hand) — blade + crossguard + pommel ──
        # Blade
        pygame.draw.line(self.screen, W, (cx + 8, cy - 6), (cx + 12, cy - 14), 3)
        # Crossguard
        pygame.draw.line(self.screen, W, (cx + 6, cy - 7), (cx + 10, cy - 5), 2)
        # Pommel dot
        pygame.draw.circle(self.screen, DK, (cx + 8, cy - 5), 1)

        # ── Shield (left hand) — rounded rectangle shape ──
        shx = cx - 14
        shy = cy - 10
        shw = 7
        shh = 10
        # Shield body
        pygame.draw.rect(self.screen, W, pygame.Rect(shx, shy, shw, shh))
        # Shield border for definition
        pygame.draw.rect(self.screen, DK, pygame.Rect(shx, shy, shw, shh), 1)
        # Shield cross/boss detail
        pygame.draw.line(self.screen, DK, (shx + shw // 2, shy + 1),
                         (shx + shw // 2, shy + shh - 2), 1)
        pygame.draw.line(self.screen, DK, (shx + 1, shy + shh // 2),
                         (shx + shw - 2, shy + shh // 2), 1)

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
    _U3_DG_COLS = 25
    _U3_DG_ROWS = 17
    _U3_DG_TS   = 32
    _U3_DG_MAP_W = _U3_DG_COLS * _U3_DG_TS   # 800
    _U3_DG_MAP_H = _U3_DG_ROWS * _U3_DG_TS   # 544

    def draw_dungeon_u3(self, party, dungeon_data, message="",
                         visible_tiles=None, torch_steps=-1):
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
            self._u3_draw_overworld_party(cx, cy)

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
        self._u3_text(dungeon_data.name.upper(), 200, bar_y + 6, (200, 60, 60))
        # Light status
        light_name = party.get_equipped_name("light")
        light_charges = party.get_equipped_charges("light")
        if torch_steps >= 0:
            torch_color = (255, 170, 85) if torch_steps > 3 else (200, 60, 60)
            lbl = f"LIGHT:{light_name.upper() if light_name else 'TORCH'}:{torch_steps:02d}"
            self._u3_text(lbl, 420, bar_y + 6, torch_color)
        elif light_name:
            lbl = f"LIGHT:{light_name.upper()}"
            if light_charges is not None:
                lbl += f":{light_charges:02d}"
            self._u3_text(lbl, 420, bar_y + 6, (255, 170, 85))
        else:
            self._u3_text("NO LIGHT", 420, bar_y + 6, (136, 136, 136))
        self._u3_text(f"POS:({party.col},{party.row})", 600, bar_y + 6, (136, 136, 136))
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

        else:
            # Fallback: black
            pygame.draw.rect(self.screen, BLACK, rect)

    # ── dungeon monster sprite ─────────────────────────────

    def _u3_draw_dungeon_monster(self, monster, cx, cy):
        """Draw a monster in the dungeon using the tile sheet skeleton sprite."""
        # Use skeleton sprite from tile sheet (R1 C9)
        sprite = self._tile_sprites.get((1, 9))
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: blocky monster
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
    _ARENA_COLS = 15
    _ARENA_ROWS = 17
    _MAP_X  = 4                                     # left edge of map panel
    _MAP_Y  = 4
    _MAP_W  = _ARENA_COLS * _ARENA_TILE              # 480
    _MAP_H  = _ARENA_ROWS * _ARENA_TILE              # 544
    _RPANEL_X = _MAP_X + _MAP_W + 8                  # 492
    _RPANEL_W = SCREEN_WIDTH - _RPANEL_X - 4          # 304

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
                          is_warband=False, source_state="dungeon",
                          directing_action=None,
                          menu_actions=None):
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

        # ── 2. sprites ──
        if monster.is_alive():
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

        # ── 3. arena blue border ──
        pygame.draw.rect(self.screen, self._U3_BLUE,
                         pygame.Rect(mx - 2, my - 2,
                                     self._MAP_W + 4, self._MAP_H + 4), 2)

        # ── 4. right-hand panels ──
        rx = self._RPANEL_X
        rw = self._RPANEL_W

        # Party roster panel (shows all 4 members with sprites and bars)
        party_h = 260
        if fighters:
            self._u3_party_combat_panel(fighters, active_fighter,
                                        defending_map or {},
                                        rx, 4, rw, party_h)
        else:
            self._u3_fighter_panel(fighter, defending, rx, 4, rw, 138)
            party_h = 138

        monster_y = 4 + party_h + 4
        self._u3_monster_panel(monster, rx, monster_y, rw, 90,
                               source_state=is_outdoor and "overworld" or "dungeon")
        action_y = monster_y + 94
        arena_bottom = my + self._MAP_H
        action_h = arena_bottom - action_y
        self._u3_action_panel(phase, selected_action, is_adjacent,
                              rx, action_y, rw, action_h,
                              active_fighter=active_fighter,
                              directing_action=directing_action,
                              menu_actions=menu_actions)

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
        """Draw orc using tile sheet orc sprite for overworld combat."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2

        # Use orc sprite from tile sheet (R1 C8)
        sprite = self._tile_sprites.get((1, 8))
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: green blocky orc
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
        """Draw monster using tile sheet skeleton sprite, with fallback."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2

        # Use skeleton sprite from tile sheet (R1 C9)
        sprite = self._tile_sprites.get((1, 9))
        if sprite:
            sx = cx - sprite.get_width() // 2
            sy = cy - sprite.get_height() // 2
            self.screen.blit(sprite, (sx, sy))
        else:
            # Fallback: blocky monster
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
                                defending_map, x, y, w, h):
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
            name_wpn = f"{member.name} [{wpn_label}]"
            self._u3_text(name_wpn, info_x, row_top, name_color, f)

            # ── HP bar ──
            bar_y = row_top + 18
            hp_color = self._U3_GREEN if member.hp > member.max_hp * 0.3 else self._U3_RED
            self._u3_draw_stat_bar(info_x, bar_y, bar_w, bar_h,
                                   member.hp, member.max_hp, hp_color)
            self._u3_text(f"HP", info_x - 26, bar_y - 2, (200, 200, 200), self.font_small)

            # ── MP bar ──
            mp_y = bar_y + bar_h + 3
            mp_val = member.current_mp
            mp_max = member.max_mp
            if mp_max > 0:
                self._u3_draw_stat_bar(info_x, mp_y, bar_w, bar_h,
                                       mp_val, mp_max, (100, 100, 255))
                self._u3_text(f"MP", info_x - 26, mp_y - 2, (200, 200, 200), self.font_small)

            # ── DEF indicator ──
            if is_def:
                self._u3_text("DEF", x + w - 40, row_top + 18, self._U3_ORANGE, self.font_small)

            # ── Ammo indicator for throwable weapons ──
            if member.is_throwable_weapon():
                ammo_count = member.get_ammo()
                ammo_color = self._U3_WHITE if ammo_count > 0 else self._U3_RED
                ammo_y = mp_y if mp_max > 0 else bar_y + bar_h + 3
                self._u3_text(f"x{ammo_count}", x + w - 32, ammo_y - 2, ammo_color, self.font_small)

            ty += 58  # row height per character

    def _u3_fighter_panel(self, fighter, defending, x, y, w, h):
        """Player stats in Ultima III format."""
        self._u3_panel(x, y, w, h)
        f = self.font
        tx = x + 8
        ty = y + 6

        self._u3_text(fighter.name, tx, ty, self._U3_ORANGE, f)
        self._u3_text(fighter.char_class, tx + 160, ty, self._U3_LTBLUE, f)

        ty += 22
        ac = fighter.get_ac() + (2 if defending else 0)
        self._u3_text(f"HP:{fighter.hp:04d}/{fighter.max_hp:04d}  AC:{ac:02d}",
                      tx, ty, self._U3_WHITE, f)
        if defending:
            self._u3_text("DEF", tx + 220, ty, self._U3_ORANGE, f)

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
        if source_state == "overworld":
            sprite = self._tile_sprites.get((1, 8))  # orc
        else:
            sprite = self._tile_sprites.get((1, 9))  # skeleton
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

    def _u3_action_panel(self, phase, selected_action, is_adjacent,
                         x, y, w, h, active_fighter=None,
                         directing_action=None, menu_actions=None):
        """Action menu in retro style."""
        from src.states.combat import (
            ACTION_RANGED, ACTION_CAST, ACTION_HEAL,
            PHASE_PLAYER, PHASE_PLAYER_DIR, PHASE_VICTORY, PHASE_DEFEAT,
            PHASE_PROJECTILE, PHASE_MELEE_ANIM, PHASE_FIREBALL, PHASE_HEAL,
        )

        _DIR_LABELS = {
            ACTION_RANGED: "RANGE ATTACK",
            ACTION_CAST:   "CAST",
            ACTION_HEAL:   "HEAL",
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

            # Controls hint at bottom
            self._u3_text("[WASD] MOVE/ATTACK", tx, y + h - 48, self._U3_LTBLUE, f)
            self._u3_text("[SPACE] SKIP TURN", tx, y + h - 32, self._U3_LTBLUE, f)
            self._u3_text("[ENTER] CONFIRM", tx, y + h - 16, self._U3_ORANGE, f)

        elif phase == PHASE_PLAYER_DIR:
            # Direction selection mode
            action_label = _DIR_LABELS.get(directing_action, "???")
            self._u3_text(f"-- {action_label} --", tx, ty, self._U3_ORANGE, f)
            self._u3_text("CHOOSE DIRECTION", tx, ty + 28, self._U3_WHITE, f)

            # Draw directional arrows hint
            cx = x + w // 2
            cy = ty + 80
            self._u3_text("^", cx - 4, cy - 20, self._U3_WHITE, f)
            self._u3_text("<   >", cx - 24, cy, self._U3_WHITE, f)
            self._u3_text("v", cx - 4, cy + 20, self._U3_WHITE, f)

            self._u3_text("[ARROWS] DIRECTION", tx, y + h - 32, self._U3_LTBLUE, f)
            self._u3_text("[ESC] CANCEL", tx, y + h - 16, self._U3_ORANGE, f)

        elif phase == PHASE_VICTORY:
            self._u3_text("** VICTORY! **", tx, ty, self._U3_GREEN, f)
            self._u3_text("RETURNING...", tx, ty + 20, self._U3_GREEN, f)

        elif phase == PHASE_DEFEAT:
            self._u3_text("** DEFEATED **", tx, ty, self._U3_RED, f)
            self._u3_text("RETREATING...", tx, ty + 20, self._U3_RED, f)

        else:
            self._u3_text("-- ENEMY TURN --", tx, ty, self._U3_RED, f)
            self._u3_text("[SPACE] SPEED UP", tx, y + h - 16, self._U3_LTBLUE, f)

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

        # Build the unified list: 3 equipped slots + inventory items
        # Each entry: (label, item_name, is_equipped, slot_key_or_None)
        body_name = eq.get("body") or member.armor
        melee_name = eq.get("melee") or member.weapon
        ranged_name = eq.get("ranged")

        unified = [
            ("BODY",   body_name,   True,  "body"),
            ("MELEE",  melee_name,  True,  "melee"),
            ("RANGED", ranged_name, True,  "ranged"),
        ]
        for item_name in inv:
            # Determine if equippable and what kind
            equippable = item_name in ARMORS or item_name in WEAPONS
            unified.append((None, item_name, False, None))

        # ── EQUIPPED section header ──
        self._u3_text("EQUIPPED", rx, ry, self._U3_ORANGE, fm)
        ry += 22

        list_row = 0
        for i, (slot_label, item_name, is_eq, slot_key) in enumerate(unified):
            # Insert ITEMS header before inventory section
            if i == 3:
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
                # Item name
                if item_name:
                    self._u3_text(f"{display_name}", rx + 90, ry, self._U3_WHITE if selected else (220, 220, 230), fm)
                    # Stat hint
                    hint = ""
                    if slot_key == "body":
                        arm = ARMORS.get(item_name, {"evasion": 50})
                        hint = f"EVD:{arm['evasion']}%"
                    elif slot_key == "melee":
                        wp = WEAPONS.get(item_name, {"power": 0})
                        hint = f"PWR:{wp['power']:02d}"
                    elif slot_key == "ranged":
                        wp = WEAPONS.get(item_name, {"power": 0})
                        hint = f"PWR:{wp['power']:02d}"
                        if WEAPONS.get(item_name, {}).get("throwable", False):
                            ammo_count = member.ammo.get(item_name, 0)
                            hint += f" x{ammo_count}"
                    if hint:
                        self._u3_text(hint, rx + right_w - 90, ry, (180, 180, 180), fm)
                else:
                    self._u3_text("-- NONE --", rx + 90, ry, (120, 120, 120), fm)

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
                    wp = WEAPONS[item_name]
                    equip_hint = "(RANGED)" if wp.get("ranged", False) else "(MELEE)"
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

    def draw_shop_u3(self, party, mode="buy", cursor_index=0, message=""):
        """
        Full-screen shop for buying and selling items.

        *mode*: "buy" or "sell"
        *cursor_index*: position in the active list
        *message*: transient feedback text (e.g. "Bought Sword!")
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
                    item_name = items[item_idx]
                    selected = (item_idx == cursor_index)
                    prefix = "> " if selected else "  "
                    name_color = self._U3_WHITE if selected else (220, 220, 230)
                    price = get_sell_price(item_name)

                    self._u3_text(f"{prefix}{item_name}", tx, ty,
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
            sel_item = sell_items[cursor_index]

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
                slot = "RANGED" if wp.get("ranged", False) else "MELEE"
                self._u3_text(f"SLOT: {slot}", rx, ry, (180, 180, 180), fm)
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
                                 action_options=None):
        """
        Full-screen shared party inventory with party equipment slots.

        The list is unified: first 4 rows are party equipment slots,
        followed by shared inventory items.

        Modes:
        - Normal: browse items with cursor, Enter to open action menu.
        - action_menu: choose from context-sensitive options.
        - choosing_member: pick which party member receives the item.
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
            selected = (si == cursor_index) and not choosing_member
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

        # ── Divider between equipment and stash ──
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
            inv_cursor = cursor_index - NUM_SLOTS  # cursor relative to inventory
            if len(inv) > max_visible:
                scroll_top = max(0, min(inv_cursor - max_visible // 2,
                                        len(inv) - max_visible))

            for vi, item_idx in enumerate(range(scroll_top, min(scroll_top + max_visible, len(inv)))):
                item_name = inv[item_idx]
                global_idx = item_idx + NUM_SLOTS
                selected = (global_idx == cursor_index) and not choosing_member
                prefix = "> " if selected else "  "
                name_color = self._U3_WHITE if selected else (220, 220, 230)

                self._u3_text(f"{prefix}{item_name}", tx, ty, name_color, fm)

                # Type hint on the right
                hint = ""
                if item_name in ARMORS:
                    hint = "ARMOR"
                elif item_name in WEAPONS:
                    wp = WEAPONS[item_name]
                    hint = "RANGED WPN" if wp.get("ranged", False) else "MELEE WPN"
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
        # RIGHT PANEL — Item detail + character selection
        # ═══════════════════════════════════════
        rx = right_x + 10
        ry = panel_y + 10

        # Determine which item is selected
        sel_item = None
        sel_charges = None
        is_equip_slot = cursor_index < NUM_SLOTS
        if is_equip_slot:
            slot_key = party.PARTY_SLOTS[cursor_index]
            sel_item = party.get_equipped_name(slot_key)
            sel_charges = party.get_equipped_charges(slot_key)
        elif cursor_index - NUM_SLOTS < len(inv):
            sel_item = inv[cursor_index - NUM_SLOTS]

        # Show details of the selected item
        if sel_item:
            if is_equip_slot:
                slot_label = party.PARTY_SLOT_LABELS.get(slot_key, slot_key.upper())
                self._u3_text(f"EQUIPPED ({slot_label})", rx, ry, self._U3_ORANGE, fm)
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
                slot = "RANGED" if wp.get("ranged", False) else "MELEE"
                self._u3_text(f"SLOT: {slot}", rx, ry, (180, 180, 180), fm)
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
        else:
            self._u3_text("NO ITEMS", rx, ry, (120, 120, 120), fm)

        # ── Character selection mode ──
        if choosing_member:
            ry += 32
            pygame.draw.line(self.screen, (60, 60, 80),
                             (rx, ry), (rx + right_w - 20, ry), 1)
            ry += 10
            self._u3_text("GIVE TO:", rx, ry, self._U3_ORANGE, fm)
            ry += 22

            for mi, member in enumerate(party.members):
                selected = (mi == member_cursor)
                prefix = "> " if selected else "  "
                name_color = self._U3_WHITE if selected else self._U3_LTBLUE
                cls_short = member.char_class[:3].upper()
                label = f"{prefix}{member.name} ({cls_short})"
                self._u3_text(label, rx, ry, name_color, fm)

                if selected:
                    sel_rect = pygame.Rect(rx - 4, ry - 1, right_w - 20, row_h)
                    sel_surf = pygame.Surface((sel_rect.w, sel_rect.h), pygame.SRCALPHA)
                    sel_surf.fill((255, 255, 255, 25))
                    self.screen.blit(sel_surf, sel_rect)

                ry += row_h

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

        # ── Bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        if action_menu:
            self._u3_text("[UP/DN] SELECT  [ENTER] CONFIRM  [ESC] CANCEL",
                          8, bar_y + 5, self._U3_BLUE)
        elif choosing_member:
            self._u3_text("[UP/DN] SELECT MEMBER  [ENTER] CONFIRM  [ESC] CANCEL",
                          8, bar_y + 5, self._U3_BLUE)
        else:
            self._u3_text("[UP/DN] SELECT  [ENTER] ACTION  [ESC] BACK  [P] CLOSE",
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
            slot = "RANGED" if wp.get("ranged", False) else "MELEE"
            self._u3_text("SLOT:", name_x, ty, self._U3_LTBLUE, fm)
            self._u3_text(slot, name_x + 55, ty, (220, 220, 230), fm)
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
