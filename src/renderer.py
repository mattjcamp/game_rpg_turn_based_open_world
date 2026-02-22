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
        """Draw the party as a knight with a sword."""
        screen_col, screen_row = camera.world_to_screen(party.col, party.row)
        cx = screen_col * TILE_SIZE + TILE_SIZE // 2
        cy = screen_row * TILE_SIZE + TILE_SIZE // 2

        # --- Sword (behind knight, on the right side) ---
        # Blade
        pygame.draw.line(self.screen, (200, 210, 220),
                         (cx + 6, cy - 12), (cx + 6, cy + 4), 2)
        # Crossguard
        pygame.draw.line(self.screen, (180, 160, 50),
                         (cx + 2, cy - 4), (cx + 10, cy - 4), 2)
        # Grip
        pygame.draw.line(self.screen, (100, 70, 40),
                         (cx + 6, cy - 4), (cx + 6, cy + 2), 2)
        # Pommel
        pygame.draw.circle(self.screen, (180, 160, 50), (cx + 6, cy + 3), 2)

        # --- Shield (left side) ---
        shield_points = [
            (cx - 9, cy - 4),
            (cx - 4, cy - 5),
            (cx - 4, cy + 3),
            (cx - 7, cy + 5),
            (cx - 10, cy + 3),
        ]
        pygame.draw.polygon(self.screen, (60, 80, 160), shield_points)
        pygame.draw.polygon(self.screen, (80, 100, 200), shield_points, 1)
        # Shield emblem (small cross)
        pygame.draw.line(self.screen, COLOR_YELLOW, (cx - 7, cy - 2), (cx - 7, cy + 2), 1)
        pygame.draw.line(self.screen, COLOR_YELLOW, (cx - 9, cy), (cx - 5, cy), 1)

        # --- Helmet ---
        # Main helm (slightly taller than a circle for that bucket-helm look)
        pygame.draw.rect(self.screen, (160, 165, 170),
                         pygame.Rect(cx - 5, cy - 13, 10, 10))
        # Rounded top
        pygame.draw.circle(self.screen, (160, 165, 170), (cx, cy - 13), 5)
        # Visor slit
        pygame.draw.line(self.screen, (40, 40, 50),
                         (cx - 3, cy - 8), (cx + 3, cy - 8), 1)
        # Helm outline
        pygame.draw.rect(self.screen, (100, 105, 110),
                         pygame.Rect(cx - 5, cy - 13, 10, 10), 1)
        # Plume on top
        pygame.draw.line(self.screen, (200, 40, 40),
                         (cx, cy - 18), (cx + 4, cy - 15), 2)
        pygame.draw.line(self.screen, (200, 40, 40),
                         (cx, cy - 18), (cx - 2, cy - 15), 2)

        # --- Body / armor ---
        body_rect = pygame.Rect(cx - 5, cy - 3, 10, 10)
        pygame.draw.rect(self.screen, (140, 145, 150), body_rect)
        pygame.draw.rect(self.screen, (100, 105, 110), body_rect, 1)
        # Belt
        pygame.draw.line(self.screen, (100, 70, 40),
                         (cx - 5, cy + 2), (cx + 5, cy + 2), 2)
        # Belt buckle
        pygame.draw.rect(self.screen, COLOR_YELLOW,
                         pygame.Rect(cx - 1, cy + 1, 3, 3))

        # --- Legs / boots ---
        # Left leg
        pygame.draw.rect(self.screen, (120, 125, 130),
                         pygame.Rect(cx - 4, cy + 7, 3, 6))
        # Right leg
        pygame.draw.rect(self.screen, (120, 125, 130),
                         pygame.Rect(cx + 1, cy + 7, 3, 6))
        # Boots
        pygame.draw.rect(self.screen, (80, 55, 30),
                         pygame.Rect(cx - 5, cy + 11, 4, 3))
        pygame.draw.rect(self.screen, (80, 55, 30),
                         pygame.Rect(cx + 1, cy + 11, 4, 3))

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
        """Draw NPC sprites on the map."""
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

                # Head
                pygame.draw.circle(self.screen, (220, 185, 155), (cx, cy - 6), 5)
                # Body
                body_rect = pygame.Rect(cx - 5, cy - 1, 10, 10)
                pygame.draw.rect(self.screen, color, body_rect)
                # Name tag (small)
                name_surf = self.font_small.render(npc.name, True, COLOR_WHITE)
                name_rect = name_surf.get_rect(center=(cx, cy - 14))
                bg = name_rect.inflate(4, 2)
                pygame.draw.rect(self.screen, (0, 0, 0, 180), bg)
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
        """Draw monster sprites on the dungeon map."""
        for monster in monsters:
            if not monster.is_alive():
                continue
            screen_col, screen_row = camera.world_to_screen(monster.col, monster.row)
            if 0 <= screen_col < VIEWPORT_COLS and 0 <= screen_row < VIEWPORT_ROWS:
                cx = screen_col * TILE_SIZE + TILE_SIZE // 2
                cy = screen_row * TILE_SIZE + TILE_SIZE // 2
                color = monster.color

                # Body (larger than NPC)
                body = pygame.Rect(cx - 7, cy - 4, 14, 12)
                pygame.draw.rect(self.screen, color, body)
                pygame.draw.rect(self.screen, (min(255, color[0]+40),
                                               min(255, color[1]+40),
                                               min(255, color[2]+40)), body, 1)
                # Eyes (menacing red dots)
                pygame.draw.circle(self.screen, (255, 40, 40), (cx - 3, cy - 1), 2)
                pygame.draw.circle(self.screen, (255, 40, 40), (cx + 3, cy - 1), 2)
                # Name tag
                name_surf = self.font_small.render(monster.name, True, (255, 100, 100))
                name_rect = name_surf.get_rect(center=(cx, cy - 12))
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
                          is_adjacent, combat_message):
        """
        Draw the Ultima III-style combat screen.

        Layout:
        ┌────────────────────┬──────────────┐
        │                    │ FIGHTER      │
        │   15×10 arena      │ MONSTER      │
        │   (dark + green    ├──────────────┤
        │    dots, brick     │ > ATTACK     │
        │    walls)          │   DEFEND     │
        ├────────────────────│   FLEE       │
        │   COMBAT LOG       ├──────────────┤
        │   (scrolling)      │  LOG (cont)  │
        ├────────────────────┴──────────────┤
        │  [WASD] MOVE        ENTER: ACT    │
        └───────────────────────────────────┘
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
        self._u3_draw_player_sprite(mx, my, ts, player_col, player_row)

        # ── 3. arena blue border ──
        pygame.draw.rect(self.screen, self._U3_BLUE,
                         pygame.Rect(mx - 2, my - 2,
                                     self._MAP_W + 4, self._MAP_H + 4), 2)

        # ── 4. right-hand panels ──
        rx = self._RPANEL_X
        rw = self._RPANEL_W

        self._u3_fighter_panel(fighter, defending, rx, 4, rw, 138)
        self._u3_monster_panel(monster, rx, 146, rw, 100)
        self._u3_action_panel(phase, selected_action, is_adjacent,
                              rx, 250, rw, 148)
        self._u3_log_panel(combat_log, rx, 402, rw, 194)

        # ── 5. left-side combat log (below arena) ──
        log_y = my + self._MAP_H + 4
        log_h = SCREEN_HEIGHT - log_y - 30
        self._u3_log_panel(combat_log, mx - 2, log_y, self._MAP_W + 4, log_h)

        # ── 6. bottom status bar ──
        bar_y = SCREEN_HEIGHT - 24
        self._u3_panel(0, bar_y, SCREEN_WIDTH, 24)
        self._u3_text("[WASD] MOVE   [UP/DN] MENU   [ENTER] ACT   [SPACE] SPEED",
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

    # ==============================================================
    #  RIGHT-HAND PANELS
    # ==============================================================

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
        self._u3_text(f"STR:{fighter.strength:02d}  DEX:{fighter.dexterity:02d}  INT:{fighter.intelligence:02d}",
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
                         x, y, w, h):
        """Action menu in retro style."""
        from src.states.combat import (
            ACTION_NAMES, ACTION_ATTACK,
            PHASE_PLAYER, PHASE_VICTORY, PHASE_DEFEAT,
        )

        self._u3_panel(x, y, w, h)
        tx = x + 8
        ty = y + 6

        if phase == PHASE_PLAYER:
            self._u3_text("-- YOUR TURN --", tx, ty, self._U3_ORANGE)

            for i, name in enumerate(ACTION_NAMES):
                iy = ty + 24 + i * 24
                selected = (i == selected_action)
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
            self._u3_text("[ENTER] CONFIRM", tx, y + h - 16, self._U3_BLUE)

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
