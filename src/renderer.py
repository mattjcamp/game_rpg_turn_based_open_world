"""
Renderer - handles all drawing to the screen.

Currently uses colored rectangles for tiles (no sprites yet).
This is intentional: it lets us iterate on gameplay without
worrying about art assets. When we're ready for sprites, we
just swap the draw_tile method.
"""

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
        self.font_small = pygame.font.SysFont("monospace", 12)

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
            # Treasure chest
            body = pygame.Rect(cx - 7, cy - 3, 14, 10)
            pygame.draw.rect(self.screen, (140, 100, 30), body)
            pygame.draw.rect(self.screen, (100, 70, 20), body, 1)
            # Lid (rounded top)
            lid = pygame.Rect(cx - 7, cy - 7, 14, 5)
            pygame.draw.rect(self.screen, (160, 115, 35), lid)
            pygame.draw.rect(self.screen, (100, 70, 20), lid, 1)
            # Lock
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
    _U3_OW_COLS = 15       # tiles visible horizontally
    _U3_OW_ROWS = 18       # tiles visible vertically
    _U3_OW_TS   = 32       # tile size (same as global TILE_SIZE)
    _U3_OW_MAP_W = _U3_OW_COLS * _U3_OW_TS   # 480
    _U3_OW_MAP_H = _U3_OW_ROWS * _U3_OW_TS   # 576

    def draw_overworld_u3(self, party, tile_map, message=""):
        """
        Full Ultima III-style overworld screen.

        ┌────────────────┬──────────────────┐
        │                │ 1 ROLAND  FIG    │
        │  15×18 tile    │ HP:0030 AC:12    │
        │  map           ├──────────────────┤
        │                │ 2 MIRA    CLE    │
        │  (black bg,    │ HP:0022 AC:10    │
        │   green dots,  ├──────────────────┤
        │   colored      │ 3 THERON  MAG    │
        │   terrain)     │ HP:0016 AC:10    │
        │                ├──────────────────┤
        │                │ 4 SABLE   THI    │
        │                │ HP:0020 AC:14    │
        │                ├──────────────────┤
        │                │ GOLD: 0100       │
        │                │ TERRAIN: GRASS   │
        ├────────────────┴──────────────────┤
        │ [ARROWS/WASD] MOVE   [ESC] QUIT  │
        └───────────────────────────────────┘
        """
        self.screen.fill((0, 0, 0))

        ts = self._U3_OW_TS
        cols = self._U3_OW_COLS
        rows = self._U3_OW_ROWS

        # ── compute camera offset for the reduced viewport ──
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

        # ── 2. party sprite ──
        psc = party.col - off_c
        psr = party.row - off_r
        if 0 <= psc < cols and 0 <= psr < rows:
            cx = psc * ts + ts // 2
            cy = psr * ts + ts // 2
            self._u3_draw_overworld_party(cx, cy)

        # ── 3. blue border around map ──
        pygame.draw.rect(self.screen, (68, 68, 255),
                         pygame.Rect(0, 0, self._U3_OW_MAP_W, self._U3_OW_MAP_H), 2)

        # ── 4. right panel ──
        rx = self._U3_OW_MAP_W + 4
        rw = SCREEN_WIDTH - rx
        self._u3_overworld_right_panel(party, tile_map, rx, 0, rw)

        # ── 5. bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        self._u3_text("[ARROWS/WASD] MOVE    [ESC] QUIT",
                      8, bar_y + 5, (68, 68, 255))

        # ── 6. floating message ──
        if message:
            surf = self.font.render(message.upper(), True, (255, 170, 85))
            rect = surf.get_rect(center=(self._U3_OW_MAP_W // 2, 16))
            bg = rect.inflate(20, 8)
            pygame.draw.rect(self.screen, (0, 0, 0), bg)
            pygame.draw.rect(self.screen, (68, 68, 255), bg, 2)
            self.screen.blit(surf, rect)

    # ── overworld tile rendering ─────────────────────────────

    def _u3_draw_overworld_tile(self, tile_id, px, py, ts, wc, wr):
        """Draw a single overworld tile in Ultima III style with good contrast."""
        from src.settings import (
            TILE_GRASS, TILE_WATER, TILE_FOREST, TILE_MOUNTAIN,
            TILE_TOWN, TILE_DUNGEON, TILE_PATH, TILE_SAND, TILE_BRIDGE,
        )

        BLACK = (0, 0, 0)
        GREEN = (0, 170, 0)
        DKGRN = (0, 102, 0)
        BLUE  = (30, 60, 170)
        LTBLU = (60, 100, 200)
        WHITE = (255, 255, 255)
        GRAY  = (136, 136, 136)
        BROWN = (140, 100, 50)
        SAND  = (180, 160, 80)
        ORANGE = (255, 170, 85)

        rect = pygame.Rect(px, py, ts, ts)
        cx = px + ts // 2
        cy = py + ts // 2
        seed = wc * 31 + wr * 17  # deterministic pseudo-random

        if tile_id == TILE_WATER:
            # Dark blue base with brighter wave lines for clear water look
            pygame.draw.rect(self.screen, (0, 0, 60), rect)
            # Multiple wave lines across the tile
            for i in range(3):
                s = seed + i * 23
                dy = 5 + (s * 7) % (ts - 10)
                dx_off = (s * 3) % 6
                wave_color = LTBLU if s % 2 else BLUE
                # Small horizontal wave dashes
                pygame.draw.line(self.screen, wave_color,
                                 (px + dx_off + 2, py + dy),
                                 (px + dx_off + 8, py + dy), 1)
            # Extra bright accent dot
            if seed % 3 < 2:
                dx = (seed * 11) % (ts - 8) + 4
                dy = (seed * 5) % (ts - 8) + 4
                pygame.draw.rect(self.screen, (80, 130, 220),
                                 pygame.Rect(px + dx, py + dy, 2, 1))

        elif tile_id == TILE_GRASS:
            # Black base with scattered green crosses and dots
            pygame.draw.rect(self.screen, BLACK, rect)
            # More crosses for denser ground coverage
            for i in range(2):
                s = seed + i * 43
                if (s + i) % 4 < 3:  # ~75% chance each
                    dx = (s * 7) % (ts - 8) + 4
                    dy = (s * 13) % (ts - 8) + 4
                    c = GREEN if s % 3 else DKGRN
                    x, y = px + dx, py + dy
                    pygame.draw.line(self.screen, c, (x - 2, y), (x + 2, y), 1)
                    pygame.draw.line(self.screen, c, (x, y - 2), (x, y + 2), 1)
            # Extra dots
            if (seed + 3) % 5 < 3:
                dx2 = ((seed + 5) * 11) % (ts - 8) + 4
                dy2 = ((seed + 5) * 3) % (ts - 8) + 4
                pygame.draw.rect(self.screen, DKGRN,
                                 pygame.Rect(px + dx2, py + dy2, 2, 2))

        elif tile_id == TILE_FOREST:
            # Dark green tinted base — clearly different from plain grass
            pygame.draw.rect(self.screen, (0, 20, 0), rect)
            # Dense green crosses in background
            for i in range(4):
                s = seed + i * 37
                dx = (s * 7) % (ts - 6) + 3
                dy = (s * 13) % (ts - 6) + 3
                c = GREEN if s % 2 else DKGRN
                x, y = px + dx, py + dy
                pygame.draw.line(self.screen, c, (x - 2, y), (x + 2, y), 1)
                pygame.draw.line(self.screen, c, (x, y - 2), (x, y + 2), 1)
            # Prominent triangle tree in center
            pts = [(cx, cy - 8), (cx - 6, cy + 4), (cx + 6, cy + 4)]
            pygame.draw.polygon(self.screen, GREEN, pts)
            # Smaller darker inner tree
            pts2 = [(cx, cy - 5), (cx - 3, cy + 2), (cx + 3, cy + 2)]
            pygame.draw.polygon(self.screen, DKGRN, pts2)
            # Trunk
            pygame.draw.line(self.screen, BROWN, (cx, cy + 4), (cx, cy + 7), 2)

        elif tile_id == TILE_MOUNTAIN:
            # Dark gray base tint to distinguish from black ground
            pygame.draw.rect(self.screen, (20, 15, 10), rect)
            # Larger, more prominent mountain with layered look
            # Base/foothills
            base_pts = [(cx - 10, cy + 8), (cx - 2, cy - 2), (cx + 6, cy + 8)]
            pygame.draw.polygon(self.screen, (100, 90, 80), base_pts)
            # Main peak
            pts = [(cx, cy - 10), (cx - 9, cy + 7), (cx + 9, cy + 7)]
            pygame.draw.polygon(self.screen, GRAY, pts)
            # Snow cap — bigger and brighter
            snow = [(cx, cy - 10), (cx - 4, cy - 4), (cx + 4, cy - 4)]
            pygame.draw.polygon(self.screen, WHITE, snow)
            # Ridge lines for depth
            pygame.draw.line(self.screen, (100, 100, 100),
                             (cx, cy - 10), (cx - 9, cy + 7), 1)
            pygame.draw.line(self.screen, (100, 100, 100),
                             (cx, cy - 10), (cx + 9, cy + 7), 1)

        elif tile_id == TILE_TOWN:
            # Grass-tinted base so towns look like they're on ground
            pygame.draw.rect(self.screen, BLACK, rect)
            if seed % 3 < 2:
                c = GREEN if seed % 2 else DKGRN
                x, y = px + 4, py + 4
                pygame.draw.line(self.screen, c, (x - 2, y), (x + 2, y), 1)
                pygame.draw.line(self.screen, c, (x, y - 2), (x, y + 2), 1)
            # White house shape
            roof = [(cx, cy - 7), (cx - 6, cy - 1), (cx + 6, cy - 1)]
            pygame.draw.polygon(self.screen, WHITE, roof)
            walls = pygame.Rect(cx - 5, cy - 1, 10, 8)
            pygame.draw.rect(self.screen, WHITE, walls, 1)
            # Door
            pygame.draw.rect(self.screen, ORANGE,
                             pygame.Rect(cx - 1, cy + 2, 3, 5))

        elif tile_id == TILE_DUNGEON:
            # Dark ground base
            pygame.draw.rect(self.screen, BLACK, rect)
            # Dark cave entrance — purple/red circle with "!" marker
            pygame.draw.circle(self.screen, (102, 51, 85), (cx, cy), 8)
            pygame.draw.circle(self.screen, (68, 34, 68), (cx, cy), 5)
            t = self.font_small.render("!", True, ORANGE)
            self.screen.blit(t, (cx - 3, cy - 5))

        elif tile_id == TILE_PATH:
            # Slightly warm-tinted base so paths are visible
            pygame.draw.rect(self.screen, (15, 10, 5), rect)
            # More tan/brown dots for denser path texture
            for i in range(3):
                s = seed + i * 29
                dx = (s * 7) % (ts - 6) + 3
                dy = (s * 13) % (ts - 6) + 3
                c = BROWN if s % 2 else (100, 80, 50)
                pygame.draw.rect(self.screen, c,
                                 pygame.Rect(px + dx, py + dy, 3, 2))

        elif tile_id == TILE_SAND:
            # Warm dark yellow base — distinct from both grass and path
            pygame.draw.rect(self.screen, (25, 20, 5), rect)
            # Dense sand speckles
            for i in range(4):
                s = seed + i * 19
                dx = (s * 7) % (ts - 6) + 3
                dy = (s * 13) % (ts - 6) + 3
                c = SAND if s % 2 else (150, 130, 60)
                pygame.draw.rect(self.screen, c,
                                 pygame.Rect(px + dx, py + dy, 2, 2))

        elif tile_id == TILE_BRIDGE:
            # Water base + brown planks
            pygame.draw.rect(self.screen, (0, 0, 60), rect)
            for i in range(3):
                plank = pygame.Rect(px + 2, py + 6 + i * 10, ts - 4, 5)
                pygame.draw.rect(self.screen, BROWN, plank)
                pygame.draw.rect(self.screen, (80, 60, 30), plank, 1)

        else:
            # Fallback: black
            pygame.draw.rect(self.screen, BLACK, rect)

    def _u3_draw_overworld_party(self, cx, cy):
        """White stick-figure party sprite on the overworld."""
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
        # Sword
        pygame.draw.line(self.screen, BLU, (cx + 6, cy - 8), (cx + 6, cy + 2), 2)
        # Shield
        pygame.draw.rect(self.screen, BLU,
                         pygame.Rect(cx - 10, cy - 5, 4, 7))

    # ── overworld right panel ────────────────────────────────

    def _u3_overworld_right_panel(self, party, tile_map, x, y, w):
        """Draw the right-hand stat panel for the overworld."""
        # Each party member gets a block
        block_h = 130
        for i, member in enumerate(party.members):
            by = y + i * block_h
            self._u3_panel(x, by, w, block_h)
            tx = x + 8
            ty = by + 6

            # Number + Name + Class (abbreviated)
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

        # Bottom info block (below party members)
        info_y = y + 4 * block_h
        info_h = SCREEN_HEIGHT - info_y - 24  # above status bar
        self._u3_panel(x, info_y, w, info_h)
        tx = x + 8
        ty = info_y + 6

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
    _U3_DG_COLS = 15
    _U3_DG_ROWS = 18
    _U3_DG_TS   = 32
    _U3_DG_MAP_W = _U3_DG_COLS * _U3_DG_TS   # 480
    _U3_DG_MAP_H = _U3_DG_ROWS * _U3_DG_TS   # 576

    def draw_dungeon_u3(self, party, dungeon_data, message=""):
        """
        Full Ultima III-style dungeon screen.

        Layout matches the overworld: map on left, stat panels on right,
        status bar at bottom. Fog of war limits visibility.
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

        # ── 2. monster sprites ──
        for monster in dungeon_data.monsters:
            if not monster.is_alive():
                continue
            msc = monster.col - off_c
            msr = monster.row - off_r
            if 0 <= msc < cols and 0 <= msr < rows:
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
        self._u3_dungeon_fog(psc, psr, cols, rows, ts, light_radius=4)

        # ── 5. blue border around map ──
        pygame.draw.rect(self.screen, (68, 68, 255),
                         pygame.Rect(0, 0, self._U3_DG_MAP_W, self._U3_DG_MAP_H), 2)

        # ── 6. right panel ──
        rx = self._U3_DG_MAP_W + 4
        rw = SCREEN_WIDTH - rx
        self._u3_dungeon_right_panel(party, dungeon_data, rx, 0, rw)

        # ── 7. bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        self._u3_text("[ARROWS/WASD] MOVE    [ESC] STAIRS",
                      8, bar_y + 5, (68, 68, 255))

        # ── 8. floating message ──
        if message:
            surf = self.font.render(message.upper(), True, (255, 170, 85))
            rect = surf.get_rect(center=(self._U3_DG_MAP_W // 2, 16))
            bg = rect.inflate(20, 8)
            pygame.draw.rect(self.screen, (0, 0, 0), bg)
            pygame.draw.rect(self.screen, (68, 68, 255), bg, 2)
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
            # Treasure chest on black floor
            pygame.draw.rect(self.screen, BLACK, rect)
            # Chest body
            body = pygame.Rect(cx - 7, cy - 2, 14, 9)
            pygame.draw.rect(self.screen, BROWN, body)
            pygame.draw.rect(self.screen, (100, 70, 30), body, 1)
            # Lid
            lid = pygame.Rect(cx - 7, cy - 6, 14, 5)
            pygame.draw.rect(self.screen, (160, 115, 40), lid)
            pygame.draw.rect(self.screen, (100, 70, 30), lid, 1)
            # Lock
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
        """Draw a monster in the dungeon using the same U3 blocky style as combat."""
        mc = monster.color
        W = (255, 255, 255)

        # Body block
        body = pygame.Rect(cx - 8, cy - 6, 16, 14)
        pygame.draw.rect(self.screen, mc, body)
        # Head block
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

    # ── dungeon fog of war ─────────────────────────────────

    def _u3_dungeon_fog(self, party_sc, party_sr, cols, rows, ts, light_radius=4):
        """Draw fog of war over the U3 dungeon map area."""
        import math

        fog = pygame.Surface((self._U3_DG_MAP_W, self._U3_DG_MAP_H), pygame.SRCALPHA)

        fade_start = light_radius
        fade_end = light_radius + 1.5

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
    _ARENA_ROWS = 10
    _MAP_X  = 4                                     # left edge of map panel
    _MAP_Y  = 4
    _MAP_W  = _ARENA_COLS * _ARENA_TILE              # 480
    _MAP_H  = _ARENA_ROWS * _ARENA_TILE              # 320
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
                          melee_effects=None, hit_effects=None):
        """
        Draw the Ultima III-style combat screen with all party members.
        """
        self.screen.fill(self._U3_BLACK)

        mx, my = self._MAP_X, self._MAP_Y
        ts = self._ARENA_TILE

        # ── 1. draw arena tiles ──
        for r in range(self._ARENA_ROWS):
            for c in range(self._ARENA_COLS):
                px = mx + c * ts
                py = my + r * ts
                wall = (c == 0 or c == self._ARENA_COLS - 1
                        or r == 0 or r == self._ARENA_ROWS - 1)
                if wall:
                    self._u3_draw_wall_tile(px, py, ts)
                else:
                    self._u3_draw_floor_tile(px, py, ts, c, r)

        # ── 2. sprites ──
        if monster.is_alive():
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

        # ── 3. arena blue border ──
        pygame.draw.rect(self.screen, self._U3_BLUE,
                         pygame.Rect(mx - 2, my - 2,
                                     self._MAP_W + 4, self._MAP_H + 4), 2)

        # ── 4. right-hand panels ──
        rx = self._RPANEL_X
        rw = self._RPANEL_W

        # Party roster panel (shows all 4 members compactly)
        if fighters:
            self._u3_party_combat_panel(fighters, active_fighter,
                                        defending_map or {},
                                        rx, 4, rw, 180)
        else:
            self._u3_fighter_panel(fighter, defending, rx, 4, rw, 138)

        self._u3_monster_panel(monster, rx, 188, rw, 100)
        self._u3_action_panel(phase, selected_action, is_adjacent,
                              rx, 292, rw, 110,
                              active_fighter=active_fighter)
        self._u3_log_panel(combat_log, rx, 406, rw, 190)

        # ── 5. left-side combat log (below arena) ──
        log_y = my + self._MAP_H + 4
        log_h = SCREEN_HEIGHT - log_y - 30
        self._u3_log_panel(combat_log, mx - 2, log_y, self._MAP_W + 4, log_h)

        # ── 6. bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        is_ranged_bar = (active_fighter and active_fighter.is_ranged())
        if is_ranged_bar:
            self._u3_text("[WASD] MOVE  [ARROWS] SHOOT  [ENTER] ACT  [SPACE] SPEED",
                          8, bar_y + 5, self._U3_BLUE)
        else:
            self._u3_text("[WASD] MOVE  [ARROWS] ATTACK  [ENTER] ACT  [SPACE] SPEED",
                          8, bar_y + 5, self._U3_BLUE)

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
        """Coloured monster figure, Ultima III style."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2
        mc = monster.color
        W = self._U3_WHITE

        # Body (larger, more menacing)
        body = pygame.Rect(cx - 8, cy - 6, 16, 14)
        pygame.draw.rect(self.screen, mc, body)
        # Head
        pygame.draw.rect(self.screen, mc,
                         pygame.Rect(cx - 5, cy - 12, 10, 7))
        # Eyes — always white with red pupils
        pygame.draw.rect(self.screen, W,
                         pygame.Rect(cx - 4, cy - 10, 3, 3))
        pygame.draw.rect(self.screen, W,
                         pygame.Rect(cx + 1, cy - 10, 3, 3))
        pygame.draw.rect(self.screen, (255, 0, 0),
                         pygame.Rect(cx - 3, cy - 9, 1, 1))
        pygame.draw.rect(self.screen, (255, 0, 0),
                         pygame.Rect(cx + 2, cy - 9, 1, 1))
        # Arms / claws
        pygame.draw.line(self.screen, mc,
                         (cx - 8, cy - 3), (cx - 13, cy + 4), 2)
        pygame.draw.line(self.screen, mc,
                         (cx + 8, cy - 3), (cx + 13, cy + 4), 2)
        # Legs
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
        """Draw a party member on the combat arena.
        Active member gets a highlight ring. Color based on class."""
        cx = ax + col * ts + ts // 2
        cy = ay + row * ts + ts // 2

        color = self._CLASS_COLORS.get(member.char_class.lower(),
                                        self._U3_WHITE)
        BLU = (120, 120, 255)

        # Active-turn highlight ring
        if is_active:
            pygame.draw.circle(self.screen, self._U3_ORANGE,
                               (cx, cy), 15, 1)

        # Head
        pygame.draw.circle(self.screen, color, (cx, cy - 9), 4)
        # Body
        pygame.draw.line(self.screen, color, (cx, cy - 5), (cx, cy + 4), 2)
        # Arms
        pygame.draw.line(self.screen, color, (cx - 6, cy - 2), (cx + 6, cy - 2), 2)
        # Legs
        pygame.draw.line(self.screen, color, (cx, cy + 4), (cx - 5, cy + 12), 2)
        pygame.draw.line(self.screen, color, (cx, cy + 4), (cx + 5, cy + 12), 2)
        # Sword (right hand)
        pygame.draw.line(self.screen, BLU, (cx + 6, cy - 8), (cx + 6, cy + 2), 2)
        # Shield (left hand)
        pygame.draw.rect(self.screen, BLU,
                         pygame.Rect(cx - 10, cy - 5, 4, 7))

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

    # ==============================================================
    #  RIGHT-HAND PANELS
    # ==============================================================

    def _u3_party_combat_panel(self, fighters, active_fighter,
                                defending_map, x, y, w, h):
        """Compact party roster for combat — all 4 members in one panel."""
        self._u3_panel(x, y, w, h)
        tx = x + 8
        ty = y + 6

        self._u3_text("PARTY", tx, ty, self._U3_ORANGE, self.font)
        ty += 20

        for i, member in enumerate(fighters):
            is_active = (member is active_fighter)
            is_def = defending_map.get(member, False)

            # Prefix: arrow for active, space otherwise
            prefix = "> " if is_active else "  "

            # Name + class
            if not member.is_alive():
                name_color = self._U3_RED
                status = "DEAD"
            elif is_active:
                name_color = self._U3_ORANGE
                status = ""
            else:
                name_color = self._U3_WHITE
                status = ""

            cls_short = member.char_class[:3].upper()
            self._u3_text(f"{prefix}{member.name}", tx, ty, name_color)
            self._u3_text(cls_short, tx + 160, ty, self._U3_BLUE)

            ty += 14
            hp_text = f"  HP:{member.hp:04d}/{member.max_hp:04d}"
            if is_def:
                hp_text += " DEF"
            if status:
                hp_text += f" {status}"
            self._u3_text(hp_text, tx, ty, self._U3_GRAY)

            ty += 18

    def _u3_fighter_panel(self, fighter, defending, x, y, w, h):
        """Player stats in Ultima III format."""
        self._u3_panel(x, y, w, h)
        tx = x + 8
        ty = y + 6

        self._u3_text(fighter.name, tx, ty, self._U3_ORANGE, self.font)
        self._u3_text(fighter.char_class, tx + 160, ty, self._U3_BLUE, self.font)

        ty += 22
        ac = fighter.get_ac() + (2 if defending else 0)
        self._u3_text(f"HP:{fighter.hp:04d}/{fighter.max_hp:04d}  AC:{ac:02d}",
                      tx, ty)
        if defending:
            self._u3_text("DEF", tx + 220, ty, self._U3_ORANGE)

        ty += 16
        self._u3_text(f"S:{fighter.strength:02d} D:{fighter.dexterity:02d} I:{fighter.intelligence:02d} W:{fighter.wisdom:02d}",
                      tx, ty)

        ty += 16
        self._u3_text(f"LVL:{fighter.level:02d}  EXP:{fighter.exp:04d}",
                      tx, ty)

        ty += 16
        self._u3_text(f"WPN: {fighter.weapon}", tx, ty, self._U3_GRAY)

        ty += 16
        dice_c, dice_s, dice_b = fighter.get_damage_dice()
        atk = f"ATK: D20{format_modifier(fighter.get_attack_bonus())}  DMG: {dice_c}D{dice_s}{format_modifier(dice_b)}"
        self._u3_text(atk, tx, ty, self._U3_GRAY)

    def _u3_monster_panel(self, monster, x, y, w, h):
        """Monster stats panel."""
        self._u3_panel(x, y, w, h)
        tx = x + 8
        ty = y + 6

        self._u3_text(monster.name, tx, ty, self._U3_RED, self.font)

        ty += 22
        self._u3_text(f"HP:{monster.hp:04d}/{monster.max_hp:04d}  AC:{monster.ac:02d}",
                      tx, ty)

        ty += 16
        atk_text = f"ATK:+{monster.attack_bonus:02d}  DMG:{monster.damage_dice}D{monster.damage_sides}+{monster.damage_bonus}"
        self._u3_text(atk_text, tx, ty, self._U3_GRAY)

        # HP bar (retro style: bracketed text bar)
        ty += 20
        bar_w = w - 20
        bar_h = 8
        bar_x = tx
        pygame.draw.rect(self.screen, self._U3_BLUE,
                         pygame.Rect(bar_x, ty, bar_w, bar_h), 1)
        if monster.max_hp > 0:
            fill = max(1, int((bar_w - 2) * monster.hp / monster.max_hp))
            bc = self._U3_RED if monster.hp <= monster.max_hp * 0.3 else (170, 0, 0)
            pygame.draw.rect(self.screen, bc,
                             pygame.Rect(bar_x + 1, ty + 1, fill, bar_h - 2))

    def _u3_action_panel(self, phase, selected_action, is_adjacent,
                         x, y, w, h, active_fighter=None):
        """Action menu in retro style."""
        from src.states.combat import (
            ACTION_NAMES, ACTION_ATTACK,
            PHASE_PLAYER, PHASE_VICTORY, PHASE_DEFEAT,
            PHASE_PROJECTILE, PHASE_MELEE_ANIM,
        )

        self._u3_panel(x, y, w, h)
        tx = x + 8
        ty = y + 6

        is_ranged = (active_fighter and active_fighter.is_ranged())

        if phase == PHASE_PROJECTILE:
            self._u3_text("-- FIRING --", tx, ty, self._U3_ORANGE)
            self._u3_text("PROJECTILE IN FLIGHT...", tx, ty + 24, self._U3_WHITE)

        elif phase == PHASE_MELEE_ANIM:
            self._u3_text("-- ATTACKING --", tx, ty, self._U3_ORANGE)
            self._u3_text("STRIKE!", tx, ty + 24, self._U3_WHITE)

        elif phase == PHASE_PLAYER:
            if is_ranged:
                self._u3_text("-- YOUR TURN (RANGED) --", tx, ty, self._U3_ORANGE)
            else:
                self._u3_text("-- YOUR TURN --", tx, ty, self._U3_ORANGE)

            for i, name in enumerate(ACTION_NAMES):
                iy = ty + 24 + i * 24
                selected = (i == selected_action)

                # For ranged fighters, Attack is never grayed out
                if is_ranged:
                    grayed = False
                else:
                    grayed = (i == ACTION_ATTACK and not is_adjacent)

                prefix = "> " if selected else "  "
                if grayed:
                    label = prefix + name.upper() + " (CLOSER!)"
                    color = self._U3_GRAY
                elif selected:
                    label = prefix + name.upper()
                    color = self._U3_WHITE
                else:
                    label = prefix + name.upper()
                    color = self._U3_BLUE

                self._u3_text(label, tx, iy, color)

            self._u3_text("[WASD] MOVE", tx, y + h - 32, self._U3_BLUE)
            if is_ranged:
                self._u3_text("[ARROWS] SHOOT  [ENTER] ACT", tx, y + h - 16, self._U3_ORANGE)
            else:
                self._u3_text("[ARROWS] STRIKE  [ENTER] ACT", tx, y + h - 16, self._U3_ORANGE)

        elif phase == PHASE_VICTORY:
            self._u3_text("** VICTORY! **", tx, ty, self._U3_GREEN)
            self._u3_text("RETURNING...", tx, ty + 20, self._U3_GREEN)

        elif phase == PHASE_DEFEAT:
            self._u3_text("** DEFEATED **", tx, ty, self._U3_RED)
            self._u3_text("RETREATING...", tx, ty + 20, self._U3_RED)

        else:
            self._u3_text("-- ENEMY TURN --", tx, ty, self._U3_RED)
            self._u3_text("[SPACE] SPEED UP", tx, y + h - 16, self._U3_BLUE)

    def _u3_log_panel(self, combat_log, x, y, w, h):
        """Combat log panel with blue border and retro text."""
        self._u3_panel(x, y, w, h)

        line_h = 15
        max_lines = (h - 10) // line_h
        visible = combat_log[-max_lines:]

        for i, line in enumerate(visible):
            if "CRITICAL" in line:
                color = self._U3_ORANGE
            elif "Hit!" in line:
                color = self._U3_WHITE
            elif "Miss" in line or "Failed" in line:
                color = self._U3_GRAY
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
                color = self._U3_BLUE

            self._u3_text(line, x + 6, y + 5 + i * line_h, color)

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
        card_h = 240
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

            # Number, name, class
            alive_color = self._U3_ORANGE if member.is_alive() else self._U3_RED
            self._u3_text(f"{i+1}", tx, ty, self._U3_BLUE, self.font)
            self._u3_text(member.name, tx + 22, ty, alive_color, self.font)
            cls_label = f"{member.char_class}"
            self._u3_text(cls_label, tx + 190, ty, self._U3_BLUE, self.font)

            # Race
            ty += 22
            self._u3_text(f"RACE: {member.race}", tx, ty, self._U3_GRAY)

            # HP / MP
            ty += 18
            self._u3_text(
                f"HP: {member.hp:04d}/{member.max_hp:04d}    "
                f"MP: {member.mp:04d}",
                tx, ty, self._U3_WHITE)

            # Stats
            ty += 18
            self._u3_text(
                f"STR:{member.strength:02d}  DEX:{member.dexterity:02d}  "
                f"INT:{member.intelligence:02d}  WIS:{member.wisdom:02d}",
                tx, ty, self._U3_WHITE)

            # Level / EXP
            ty += 18
            self._u3_text(
                f"LVL:{member.level:02d}  EXP:{member.exp:04d}  AC:{member.get_ac():02d}",
                tx, ty, self._U3_WHITE)

            # Weapon info
            ty += 22
            wp = WEAPONS.get(member.weapon, {"power": 0, "ranged": False})
            rng = "RANGED" if wp["ranged"] else "MELEE"
            self._u3_text(
                f"WPN: {member.weapon}  (PWR:{wp['power']:02d} {rng})",
                tx, ty, self._U3_GRAY)

            # Armor info
            ty += 18
            arm = ARMORS.get(member.armor, {"evasion": 50})
            self._u3_text(
                f"ARM: {member.armor}  (EVD:{arm['evasion']}%)",
                tx, ty, self._U3_GRAY)

            # Magic type
            ty += 18
            magic_types = []
            if member.can_cast_priest():
                magic_types.append("PRIEST")
            if member.can_cast_sorcerer():
                magic_types.append("SORCERER")
            if magic_types:
                self._u3_text(
                    f"MAGIC: {' + '.join(magic_types)}",
                    tx, ty, (120, 120, 255))
            else:
                self._u3_text("MAGIC: NONE", tx, ty, (80, 80, 80))

            # Damage estimate
            ty += 18
            dmg = member.get_damage()
            self._u3_text(f"EST DMG: {dmg:02d}", tx, ty, self._U3_GRAY)

            # Status
            ty += 18
            status = "ALIVE" if member.is_alive() else "DEAD"
            sc = self._U3_GREEN if member.is_alive() else self._U3_RED
            self._u3_text(f"STATUS: {status}", tx, ty, sc)

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
        self._u3_text("[P] CLOSE    [ESC] CLOSE",
                      8, bar_y + 5, self._U3_BLUE)
