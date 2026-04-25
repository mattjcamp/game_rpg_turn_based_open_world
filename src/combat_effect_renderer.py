"""
Combat effect rendering mixin.

Contains all visual-effect drawing methods for the combat arena:
melee slashes, fireballs, heal glows, lightning bolts, buff/debuff
indicators, etc.  Mixed into the main Renderer class.
"""

import math
import random
import pygame


class CombatEffectRendererMixin:
    """Mixin providing all combat visual-effect drawing methods.

    Expects the host class to have:
        self.screen   — the pygame display surface
        self.font     — default font
        self.font_small — small font
        self._U3_BLACK, self._U3_WHITE — colour constants
    """

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

    def _u3_draw_consume_effect(self, ax, ay, ts, fx):
        """Draw the "swallowed whole" effect — a contracting purple
        vortex with a bold "SWALLOWED!" label so the player can see
        which character just got eaten.

        Phase 1 (0–0.5):   purple/red rings shrink toward the centre
                           (the character being pulled in).
        Phase 2 (0.2–1.0): "SWALLOWED!" floats up and fades.
        """
        cx = ax + fx.col * ts + ts // 2
        cy = ay + fx.row * ts + ts // 2
        p = fx.progress  # 0 → 1

        # Phase 1: contracting concentric rings.
        if p < 0.5:
            sub_p = p / 0.5
            for i in range(3):
                base_r = 16 + i * 4
                r = max(2, int(base_r * (1.0 - sub_p)))
                alpha_f = 1.0 - sub_p
                col = (int(150 * alpha_f),
                       int(40 * alpha_f),
                       int(180 * alpha_f))
                pygame.draw.circle(self.screen, col, (cx, cy), r, 2)
            # Bright core that pulses inward.
            core = max(1, int(6 * (1.0 - sub_p)))
            pygame.draw.circle(self.screen, (220, 100, 255),
                               (cx, cy), core)

        # Phase 2: floating label.
        if p > 0.2:
            label_p = min(1.0, (p - 0.2) / 0.8)
            float_y = cy - 18 - int(label_p * 14)
            alpha_f = 1.0 - max(0.0, (label_p - 0.5) / 0.5)
            r_val = int(255 * alpha_f)
            g_val = int(180 * alpha_f)
            b_val = int(255 * alpha_f)
            if r_val > 0:
                text = "SWALLOWED!"
                surf = self.font_small.render(
                    text, True, (r_val, g_val, b_val))
                outline = self.font_small.render(
                    text, True, (0, 0, 0))
                rx = cx - surf.get_width() // 2
                for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    self.screen.blit(outline, (rx + ox, float_y + oy))
                self.screen.blit(surf, (rx, float_y))

    def _u3_draw_release_effect(self, ax, ay, ts, fx):
        """Draw the "spat out" / "released" effect — a green/yellow
        burst expanding outward at the destination tile, with an
        "ESCAPED!" label.  The reverse of ``_u3_draw_consume_effect``.

        Phase 1 (0–0.5):   bright burst rings expand outward.
        Phase 2 (0.2–1.0): "ESCAPED!" label floats up and fades.
        """
        cx = ax + fx.col * ts + ts // 2
        cy = ay + fx.row * ts + ts // 2
        p = fx.progress

        if p < 0.5:
            sub_p = p / 0.5
            # Outer expanding ring (green to yellow, fading).
            outer_r = int(4 + sub_p * 16)
            alpha_f = 1.0 - sub_p
            col_outer = (int(120 * alpha_f),
                         int(255 * alpha_f),
                         int(80 * alpha_f))
            pygame.draw.circle(self.screen, col_outer,
                               (cx, cy), outer_r, 2)
            # Inner bright core.
            inner_r = int(2 + sub_p * 6)
            col_inner = (int(255 * alpha_f),
                         int(255 * alpha_f),
                         int(120 * alpha_f))
            pygame.draw.circle(self.screen, col_inner,
                               (cx, cy), inner_r)
            # Sparkle bursts at cardinal points.
            for i in range(4):
                ang = i * 1.5708
                sx = cx + int(math.cos(ang) * outer_r)
                sy = cy + int(math.sin(ang) * outer_r)
                spark_sz = max(1, int(2 * alpha_f))
                pygame.draw.circle(self.screen, (255, 255, 200),
                                   (sx, sy), spark_sz)

        if p > 0.2:
            label_p = min(1.0, (p - 0.2) / 0.8)
            float_y = cy - 18 - int(label_p * 14)
            alpha_f = 1.0 - max(0.0, (label_p - 0.5) / 0.5)
            r_val = int(180 * alpha_f)
            g_val = int(255 * alpha_f)
            b_val = int(120 * alpha_f)
            if r_val > 0:
                text = "ESCAPED!"
                surf = self.font_small.render(
                    text, True, (r_val, g_val, b_val))
                outline = self.font_small.render(
                    text, True, (0, 0, 0))
                rx = cx - surf.get_width() // 2
                for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    self.screen.blit(outline, (rx + ox, float_y + oy))
                self.screen.blit(surf, (rx, float_y))

    def _u3_draw_backstab(self, ax, ay, ts, fx):
        """Draw the Thief backstab effect — purple expanding rings
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
        breath_fire gets a special directional fire stream from the caster.
        """
        cx = int(ax + fx.col * ts + ts // 2)
        cy = int(ay + fx.row * ts + ts // 2)
        p = fx.progress  # 0 → 1
        ticks = pygame.time.get_ticks()
        r, g, b = fx.color

        # ── Special: breath_fire draws a fire stream from monster ──
        if fx.spell_type == "breath_fire" and fx.source_col is not None:
            self._u3_draw_breath_fire_stream(ax, ay, ts, fx, cx, cy, p, ticks)
            return

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

    def _u3_draw_breath_fire_stream(self, ax, ay, ts, fx, tx, ty, p, ticks):
        """Draw a fire breath stream from the monster to the target.

        The fire cone travels from the source (monster) toward the target,
        widening as it goes, with flickering particles and a burst on impact.
        """
        # Source pixel position (monster's mouth)
        src_x = int(ax + fx.source_col * ts + ts // 2)
        src_y = int(ay + fx.source_row * ts + ts // 2)

        # Direction vector
        dx = tx - src_x
        dy = ty - src_y
        length = math.sqrt(dx * dx + dy * dy) or 1.0
        nx, ny = dx / length, dy / length  # normalized direction
        # Perpendicular for cone width
        px, py = -ny, nx

        # ── Phase 1 (0-60%): fire stream travels from monster to target ──
        if p < 0.6:
            stream_p = p / 0.6  # 0→1 over this phase
            # How far the stream head has traveled
            head_dist = stream_p * length

            # Draw the cone: wide particles from source to stream head
            n_particles = int(20 + 15 * stream_p)
            for i in range(n_particles):
                # Position along the stream (0=source, 1=head)
                t = (i / max(1, n_particles - 1))
                d = t * head_dist
                # Cone widens from 2px at source to ~ts/2 at head
                spread = 2 + t * ts * 0.5
                # Jitter for organic fire look
                jitter_x = spread * math.sin(ticks * 0.015 + i * 2.7)
                jitter_y = spread * math.cos(ticks * 0.018 + i * 3.1)

                fire_x = int(src_x + nx * d + px * jitter_x * 0.4)
                fire_y = int(src_y + ny * d + py * jitter_x * 0.4
                             + jitter_y * 0.15)

                # Color: bright yellow at source, deep orange/red at head
                cr = 255
                cg = max(30, int(255 - 200 * t))
                cb = max(0, int(80 - 80 * t))
                size = max(2, int(3 + 4 * t * (0.7 + 0.3
                           * math.sin(ticks * 0.02 + i))))
                pygame.draw.circle(self.screen, (cr, cg, cb),
                                   (fire_x, fire_y), size)

            # Bright core along the center line
            core_pts = 8
            for i in range(core_pts):
                t = i / max(1, core_pts - 1)
                d = t * head_dist
                flicker = 0.8 + 0.2 * math.sin(ticks * 0.025 + i * 1.5)
                core_x = int(src_x + nx * d)
                core_y = int(src_y + ny * d)
                cg = int(220 * flicker)
                pygame.draw.circle(self.screen, (255, cg, 50),
                                   (core_x, core_y),
                                   max(1, int(2 * (1.0 - t * 0.5))))

        # ── Phase 2 (60-100%): impact burst on target + fade ──
        else:
            fade_p = (p - 0.6) / 0.4  # 0→1 over this phase
            alpha = 1.0 - fade_p

            # Shrinking fire stream (still visible, fading)
            n_particles = max(3, int(15 * alpha))
            for i in range(n_particles):
                t = i / max(1, n_particles - 1)
                d = t * length
                spread = (2 + t * ts * 0.5) * alpha
                jitter_x = spread * math.sin(ticks * 0.015 + i * 2.7)
                fire_x = int(src_x + nx * d + px * jitter_x * 0.4)
                fire_y = int(src_y + ny * d + py * jitter_x * 0.15)
                cr = int(255 * alpha)
                cg = max(0, int((255 - 200 * t) * alpha))
                cb = 0
                size = max(1, int((3 + 3 * t) * alpha))
                if cr > 10:
                    pygame.draw.circle(self.screen, (cr, cg, cb),
                                       (fire_x, fire_y), size)

            # Explosion burst at the target
            burst_r = int(ts * 0.6 * (0.5 + 0.5 * fade_p) * alpha)
            if burst_r > 2:
                burst_surf = pygame.Surface(
                    (burst_r * 2, burst_r * 2), pygame.SRCALPHA)
                ba = int(120 * alpha)
                pygame.draw.circle(burst_surf, (255, 100, 20, ba),
                                   (burst_r, burst_r), burst_r)
                pygame.draw.circle(burst_surf, (255, 200, 50, ba),
                                   (burst_r, burst_r),
                                   max(1, burst_r // 2))
                self.screen.blit(burst_surf,
                                 (tx - burst_r, ty - burst_r))

            # Scattered embers around impact
            n_embers = max(2, int(6 * alpha))
            for i in range(n_embers):
                angle = ticks * 0.01 + i * 1.05 + fade_p * 3
                dist = int(ts * 0.3 * fade_p + ts * 0.15)
                ex = tx + int(math.cos(angle) * dist)
                ey = ty + int(math.sin(angle) * dist)
                ec = max(0, int(255 * alpha))
                eg = max(0, int(120 * alpha))
                if ec > 10:
                    pygame.draw.circle(self.screen, (ec, eg, 0),
                                       (ex, ey), max(1, int(2 * alpha)))

        # Draw spell label above the target
        if p < 0.85:
            label = fx.label
            if not fx.success:
                label += " - Resisted!"
            font = self.font_small
            txt = font.render(label, True, (255, 120, 30))
            lx = tx - txt.get_width() // 2
            ly = ty - ts // 2 - 12 - int(p * 8)
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

    # ── Shatter effect ─────────────────────────────────────────────

    def _u3_draw_shatter_effect(self, ax, ay, ts, fx):
        """Draw a dramatic item-shatter burst — red/orange shards
        radiating outward with a brief screen shake and floating text."""
        import math
        cx = ax + fx.col * ts + ts // 2
        cy = ay + fx.row * ts + ts // 2
        p = fx.progress  # 0 → 1

        # Screen shake in early phase
        if p < 0.3:
            import random
            shake = int(3 * (1.0 - p / 0.3))
            if shake > 0:
                cx += random.randint(-shake, shake)
                cy += random.randint(-shake, shake)

        # Phase 1 (0–0.25): bright orange-white flash
        if p < 0.25:
            sub_p = p / 0.25
            radius = int(6 + sub_p * 14)
            alpha_f = 1.0 - sub_p * 0.4
            c = (int(255 * alpha_f), int(180 * alpha_f), int(60 * alpha_f))
            pygame.draw.circle(self.screen, c, (cx, cy), radius)
            # White core
            pygame.draw.circle(self.screen, (255, 255, 220),
                               (cx, cy), int(4 + sub_p * 6))

        # Phase 2 (0.15–0.7): shards radiating outward
        if 0.15 < p < 0.7:
            sub_p = (p - 0.15) / 0.55
            num_shards = 8
            for i in range(num_shards):
                angle = (2 * math.pi * i) / num_shards + 0.3
                dist = int(8 + sub_p * 24)
                sx = cx + int(math.cos(angle) * dist)
                sy = cy + int(math.sin(angle) * dist)
                alpha_f = 1.0 - sub_p
                # Alternating red/orange shards
                if i % 2 == 0:
                    c = (int(255 * alpha_f), int(80 * alpha_f), int(20 * alpha_f))
                else:
                    c = (int(255 * alpha_f), int(160 * alpha_f), int(40 * alpha_f))
                shard_size = max(1, int(3 * alpha_f))
                pygame.draw.rect(self.screen, c,
                                 (sx - shard_size, sy - shard_size,
                                  shard_size * 2, shard_size * 2))

        # Phase 3 (0.3–1.0): "SHATTERED!" text floating up
        if p > 0.3:
            sub_p = (p - 0.3) / 0.7
            float_y = cy - 16 - int(sub_p * 24)
            alpha_f = max(0, 1.0 - sub_p * 1.2)
            if alpha_f > 0:
                txt = "SHATTERED!"
                r_val = int(255 * alpha_f)
                g_val = int(100 * alpha_f)
                surf = self.font_small.render(txt, True, (r_val, g_val, 0))
                outline = self.font_small.render(txt, True, self._U3_BLACK)
                rx = cx - surf.get_width() // 2
                for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    self.screen.blit(outline, (rx + ox, float_y + oy))
                self.screen.blit(surf, (rx, float_y))

