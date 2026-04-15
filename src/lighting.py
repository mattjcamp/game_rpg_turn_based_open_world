"""
Unified lighting system for all map rendering contexts.

Replaces three separate lighting implementations (overworld darkness,
town interior darkness, dungeon fog-of-war) with a single composable
pipeline driven by a LightingContext dataclass.

Usage
-----
Each map state (overworld, town, dungeon) builds a LightingContext
describing the desired lighting conditions, then calls
``render_lighting(screen, ctx)`` after tiles and entities are drawn
but before the UI border/HUD.

Example configurations:

    # Dungeon — shadowcast fog-of-war with torch glow
    ctx = LightingContext(
        mode=LightingMode.FOG_OF_WAR,
        visible_tiles=visible, explored_tiles=explored,
        party_screen_pos=(psc, psr), tile_size=ts,
        viewport_cols=cols, viewport_rows=rows,
        camera_offset=(off_c, off_r),
        torch_tiles=torch_positions,
    )

    # Overworld night — clock-driven darkness
    ctx = LightingContext(
        mode=LightingMode.CLOCK_DARKNESS,
        clock=game_clock, party_screen_pos=(psc, psr),
        tile_size=ts, viewport_cols=cols, viewport_rows=rows,
        has_party_light=True, force_night=darkness_active,
        extra_lights=torch_lights + feature_lights,
    )

    # Town interior — forced darkness with torch glow
    ctx = LightingContext(
        mode=LightingMode.INTERIOR_DARKNESS,
        party_screen_pos=(psc, psr), tile_size=ts,
        viewport_cols=cols, viewport_rows=rows,
        has_party_light=True,
        extra_lights=torch_lights + feature_lights,
        torch_tiles=torch_positions,
    )
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Sequence, Set, Tuple

import pygame

try:
    import numpy as np
    import pygame.surfarray as surfarray
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ─── Lighting mode enum ───────────────────────────────────────────

class LightingMode(Enum):
    """Which darkness/fog algorithm to use."""
    NONE = auto()              # Full daylight — no overlay
    CLOCK_DARKNESS = auto()    # Overworld: time-of-day driven
    INTERIOR_DARKNESS = auto() # Town/overworld interiors: always dark
    FOG_OF_WAR = auto()        # Dungeon: shadowcast visibility sets


# ─── Post-processing tint enum ────────────────────────────────────

class TintEffect(Enum):
    """Post-processing colour tint applied after darkness."""
    NONE = auto()
    INFRAVISION = auto()       # Red/black infrared
    GALADRIELS_LIGHT = auto()  # Blue/white starlight
    GALADRIELS_SUBTLE = auto() # Faint daytime blue wash


# ─── Light source tuple ───────────────────────────────────────────
# (screen_col, screen_row, radius, fade_tiles)
LightSource = Tuple[float, float, float, float]

# Torch tile position (screen_col, screen_row)
TorchTile = Tuple[int, int]


# ─── LightingContext dataclass ────────────────────────────────────

@dataclass
class LightingContext:
    """All parameters needed to render lighting for one frame.

    Built by each map state and passed to ``render_lighting()``.
    Only the fields relevant to the chosen ``mode`` need to be set.
    """

    # ── Core ──
    mode: LightingMode = LightingMode.NONE
    tile_size: int = 32
    viewport_cols: int = 25
    viewport_rows: int = 17
    party_screen_pos: Tuple[int, int] = (0, 0)

    # ── Clock-based darkness (CLOCK_DARKNESS mode) ──
    clock: object = None            # GameClock instance
    force_night: bool = False       # Quest-forced permanent night

    # ── Party light source ──
    has_party_light: bool = False   # Torch / infravision / galadriel equipped
    party_light_radius: float = 1.0 # Base radius without bonuses
    party_light_bonus: float = 3.0  # Extra radius when has_party_light

    # ── Extra light sources (distance-based modes) ──
    extra_lights: Sequence[LightSource] = field(default_factory=list)

    # ── Torch glow (warm orange flicker on nearby tiles) ──
    torch_tiles: Sequence[TorchTile] = field(default_factory=list)
    torch_glow_radius: int = 3
    torch_glow_color: Tuple[int, int, int] = (255, 160, 50)
    torch_glow_base_alpha: int = 35

    # ── Fog of war (FOG_OF_WAR mode) ──
    visible_tiles: Optional[Set[Tuple[int, int]]] = None
    explored_tiles: Optional[Set[Tuple[int, int]]] = None
    camera_offset: Tuple[int, int] = (0, 0)

    # ── Post-processing tint ──
    tint: TintEffect = TintEffect.NONE

    # ── Rendering surface info (for fog-of-war blit target) ──
    fog_surface_size: Optional[Tuple[int, int]] = None  # (w, h) override


# ─── Main render entry point ──────────────────────────────────────

def render_lighting(screen: pygame.Surface, ctx: LightingContext) -> None:
    """Apply the full lighting pipeline to *screen* for one frame.

    Call order within each draw function should be:
        1. Draw tiles
        2. Draw torch glow (before darkness so it shows through)
        3. Draw entities / sprites
        4. Draw darkness / fog overlay
        5. Apply post-processing tint
    This function handles steps 2, 4, and 5.
    """
    ts = ctx.tile_size
    cols = ctx.viewport_cols
    rows = ctx.viewport_rows
    psc, psr = ctx.party_screen_pos

    # ── Step 2: Torch glow (warm orange flicker) ──
    if ctx.torch_tiles:
        _render_torch_glow(screen, ctx)

    # ── Steps 4+5: Darkness/fog + post-processing tint ──
    # For FOG_OF_WAR the tint must come *before* the fog overlay so that
    # unexplored areas stay pure black (fog covers tinted pixels).
    # For distance-based modes the order doesn't matter visually, so we
    # apply tint *after* darkness for consistency with the legacy code.

    if ctx.mode == LightingMode.FOG_OF_WAR:
        # Tint first, then fog on top
        _apply_tint(screen, ctx)
        _render_fog_of_war(screen, ctx)
    else:
        # Darkness first, then tint
        if ctx.mode == LightingMode.CLOCK_DARKNESS:
            _render_clock_darkness(screen, ctx)
        elif ctx.mode == LightingMode.INTERIOR_DARKNESS:
            _render_interior_darkness(screen, ctx)
        # LightingMode.NONE — skip darkness
        _apply_tint(screen, ctx)


def _apply_tint(screen: pygame.Surface, ctx: LightingContext) -> None:
    """Apply the post-processing tint from the context, if any."""
    if ctx.tint == TintEffect.INFRAVISION:
        _render_infravision_tint(screen, ctx)
    elif ctx.tint == TintEffect.GALADRIELS_LIGHT:
        _render_galadriels_tint(screen, ctx, subtle=False)
    elif ctx.tint == TintEffect.GALADRIELS_SUBTLE:
        _render_galadriels_tint(screen, ctx, subtle=True)


# ─── Torch glow ───────────────────────────────────────────────────

def _render_torch_glow(screen: pygame.Surface, ctx: LightingContext) -> None:
    """Draw warm orange flickering glow around wall-torch tiles."""
    ts = ctx.tile_size
    cols = ctx.viewport_cols
    rows = ctx.viewport_rows
    radius = ctx.torch_glow_radius
    base_alpha = ctx.torch_glow_base_alpha
    gr, gg, gb = ctx.torch_glow_color

    now = pygame.time.get_ticks()
    flicker1 = 0.6 + 0.4 * math.sin(now * 0.008)
    flicker2 = 0.6 + 0.4 * math.sin(now * 0.011 + 1.5)

    glow_s = pygame.Surface((ts, ts), pygame.SRCALPHA)

    for tsc, tsr in ctx.torch_tiles:
        tsc_i = int(round(tsc))
        tsr_i = int(round(tsr))
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                dist = abs(dr) + abs(dc)
                if dist == 0 or dist > radius:
                    continue
                nsc = tsc_i + dc
                nsr = tsr_i + dr
                if 0 <= nsc < cols and 0 <= nsr < rows:
                    flk = flicker1 if (dc + dr) % 2 == 0 else flicker2
                    intensity = (1.0 - dist / (radius + 1)) * flk
                    alpha = int(base_alpha * intensity)
                    if alpha > 0:
                        glow_s.fill((gr, gg, gb, alpha))
                        screen.blit(glow_s, (nsc * ts, nsr * ts))


# ─── Clock-based darkness (overworld) ─────────────────────────────

def _resolve_clock_params(ctx: LightingContext):
    """Determine darkness parameters from the GameClock phase.

    Returns (light_radius, fade_tiles, max_alpha, tint_rgb) or None
    if it's daytime and no darkness should be drawn.
    """
    clock = ctx.clock
    has_light = ctx.has_party_light
    light_bonus = ctx.party_light_bonus if has_light else 0.0

    if ctx.force_night:
        return (ctx.party_light_radius + light_bonus, 1.5, 255, (0, 0, 0))
    elif clock.is_dusk:
        return (10.0, 4.0, 100, (20, 10, 40))
    elif clock.is_dawn:
        return (10.0, 4.0, 80, (40, 20, 10))
    elif clock.is_night:
        return (ctx.party_light_radius + light_bonus, 1.5, 255, (0, 0, 0))
    else:
        return None  # daytime


def _render_clock_darkness(screen: pygame.Surface, ctx: LightingContext) -> None:
    """Overlay darkness based on time-of-day (overworld / town outdoor)."""
    params = _resolve_clock_params(ctx)
    if params is None:
        return  # daytime — nothing to draw

    light_radius, fade_tiles, max_alpha, tint = params
    _blit_distance_darkness(
        screen, ctx,
        party_radius=light_radius, party_fade=fade_tiles,
        max_alpha=max_alpha, tint_rgb=tint,
    )


# ─── Interior darkness (town/overworld interiors) ─────────────────

def _render_interior_darkness(screen: pygame.Surface, ctx: LightingContext) -> None:
    """Overlay always-dark interior lighting (forced night, no clock)."""
    has_light = ctx.has_party_light
    light_bonus = ctx.party_light_bonus if has_light else 0.0
    radius = ctx.party_light_radius + light_bonus

    _blit_distance_darkness(
        screen, ctx,
        party_radius=radius, party_fade=1.5,
        max_alpha=255, tint_rgb=(0, 0, 0),
    )


# ─── Shared distance-based darkness blit ──────────────────────────

def _blit_distance_darkness(
    screen: pygame.Surface,
    ctx: LightingContext,
    party_radius: float,
    party_fade: float,
    max_alpha: int,
    tint_rgb: Tuple[int, int, int],
) -> None:
    """Per-tile SRCALPHA darkness overlay with multiple light sources.

    Used by both clock-darkness and interior-darkness modes.
    """
    ts = ctx.tile_size
    cols = ctx.viewport_cols
    rows = ctx.viewport_rows
    psc, psr = ctx.party_screen_pos

    # Assemble all light sources: party + extras
    all_lights = [(psc, psr, party_radius, party_fade)]
    for el in ctx.extra_lights:
        all_lights.append(el)

    r, g, b = tint_rgb
    fog_tile = pygame.Surface((ts, ts), pygame.SRCALPHA)

    for sr in range(rows):
        for sc in range(cols):
            best_t = 999.0
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
            fog_tile.fill((r, g, b, alpha))
            screen.blit(fog_tile, (sc * ts, sr * ts))


# ─── Fog of war (dungeon) ─────────────────────────────────────────

def _render_fog_of_war(screen: pygame.Surface, ctx: LightingContext) -> None:
    """Draw fog of war using visibility / explored tile sets.

    Visible tiles are clear, edge tiles get soft fade, explored tiles
    show dim outlines, and unexplored tiles are pitch black.
    Falls back to simple radius-1 fog if no visible_tiles set is given.
    """
    ts = ctx.tile_size
    cols = ctx.viewport_cols
    rows = ctx.viewport_rows
    psc, psr = ctx.party_screen_pos
    off_c, off_r = ctx.camera_offset

    # Determine fog surface size (may differ from viewport for dungeon panel layout)
    if ctx.fog_surface_size:
        fog_w, fog_h = ctx.fog_surface_size
    else:
        fog_w = cols * ts
        fog_h = rows * ts

    fog = pygame.Surface((fog_w, fog_h), pygame.SRCALPHA)

    if ctx.visible_tiles is not None:
        _explored = ctx.explored_tiles or set()
        for sr in range(rows):
            for sc in range(cols):
                wc = sc + off_c
                wr = sr + off_r
                if (wc, wr) in ctx.visible_tiles:
                    continue  # fully visible
                # Check if any visible neighbour exists (edge fade)
                edge = False
                for dc in (-1, 0, 1):
                    for dr in (-1, 0, 1):
                        if (wc + dc, wr + dr) in ctx.visible_tiles:
                            edge = True
                            break
                    if edge:
                        break
                rect = pygame.Rect(sc * ts, sr * ts, ts, ts)
                if edge:
                    fog.fill((0, 0, 0, 160), rect)
                elif (wc, wr) in _explored:
                    fog.fill((15, 15, 30, 175), rect)
                else:
                    fog.fill((0, 0, 0, 255), rect)
    else:
        # Fallback: simple radius-1 fog
        fade_start = 1
        fade_end = 2.5
        for sr in range(rows):
            for sc in range(cols):
                dx = sc - psc
                dy = sr - psr
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

    screen.blit(fog, (0, 0))


# ─── Infravision tint ─────────────────────────────────────────────

def _render_infravision_tint(screen: pygame.Surface, ctx: LightingContext) -> None:
    """Apply red/black infrared tint to the map area.

    Converts pixels to grayscale then maps luminance to the red channel.
    """
    map_w = ctx.viewport_cols * ctx.tile_size
    map_h = ctx.viewport_rows * ctx.tile_size

    if _HAS_NUMPY:
        try:
            map_rect = pygame.Rect(0, 0, map_w, map_h)
            map_surf = screen.subsurface(map_rect).copy()
            arr = surfarray.pixels3d(map_surf)

            lum = (arr[:, :, 0].astype(np.float32) * 0.299
                   + arr[:, :, 1].astype(np.float32) * 0.587
                   + arr[:, :, 2].astype(np.float32) * 0.114)

            arr[:, :, 0] = np.clip(lum * 1.1, 0, 255).astype(np.uint8)
            arr[:, :, 1] = np.clip(lum * 0.08, 0, 255).astype(np.uint8)
            arr[:, :, 2] = np.clip(lum * 0.04, 0, 255).astype(np.uint8)

            del arr
            screen.blit(map_surf, (0, 0))
            return
        except Exception:
            pass

    # Fallback: simple red overlay
    tint = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
    tint.fill((0, 0, 0, 180))
    screen.blit(tint, (0, 0))
    red_wash = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
    red_wash.fill((180, 0, 0, 80))
    screen.blit(red_wash, (0, 0))


# ─── Galadriel's Light tint ──────────────────────────────────────

def _render_galadriels_tint(
    screen: pygame.Surface,
    ctx: LightingContext,
    subtle: bool = False,
) -> None:
    """Apply blue/white starlight tint to the map area.

    When *subtle* is True (daytime), only a very light wash is applied.
    """
    map_w = ctx.viewport_cols * ctx.tile_size
    map_h = ctx.viewport_rows * ctx.tile_size

    if _HAS_NUMPY:
        try:
            map_rect = pygame.Rect(0, 0, map_w, map_h)
            map_surf = screen.subsurface(map_rect).copy()
            arr = surfarray.pixels3d(map_surf)

            if subtle:
                arr[:, :, 0] = np.clip(
                    arr[:, :, 0].astype(np.int16) - 8, 0, 255
                ).astype(np.uint8)
                arr[:, :, 1] = np.clip(
                    arr[:, :, 1].astype(np.int16) - 4, 0, 255
                ).astype(np.uint8)
                arr[:, :, 2] = np.clip(
                    arr[:, :, 2].astype(np.int16) + 18, 0, 255
                ).astype(np.uint8)
            else:
                lum = (arr[:, :, 0].astype(np.float32) * 0.299
                       + arr[:, :, 1].astype(np.float32) * 0.587
                       + arr[:, :, 2].astype(np.float32) * 0.114)
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
            screen.blit(map_surf, (0, 0))
            return
        except Exception:
            pass

    # Fallback: simple blue overlay
    tint_surf = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
    if subtle:
        tint_surf.fill((40, 60, 140, 25))
    else:
        tint_surf.fill((30, 50, 120, 70))
    screen.blit(tint_surf, (0, 0))


# ─── Utility: scan tiles for light sources ────────────────────────

def scan_light_sources(tile_map, off_c: int, off_r: int,
                       cols: int, rows: int,
                       pad_sc: float = 0.0, pad_sr: float = 0.0):
    """Scan visible viewport tiles for light-emitting features.

    Returns (torch_lights, feature_lights, torch_positions) where:
    - torch_lights: list of LightSource for distance-darkness extra_lights
    - feature_lights: list of LightSource for doors/altars/exits
    - torch_positions: list of TorchTile screen coords for glow rendering
    """
    from src.settings import (
        TILE_WALL_TORCH, TILE_CAVE_TORCH, TILE_DOOR, TILE_ALTAR, TILE_EXIT,
    )

    torch_lights: list = []
    feature_lights: list = []
    torch_positions: list = []

    for sr in range(rows):
        for sc in range(cols):
            wc = sc + off_c
            wr = sr + off_r
            tid = tile_map.get_tile(wc, wr)
            ssc = sc + pad_sc
            ssr = sr + pad_sr
            if tid in (TILE_WALL_TORCH, TILE_CAVE_TORCH):
                torch_lights.append((ssc, ssr, 5.0, 3.0))
                torch_positions.append((sc, sr))
            elif tid == TILE_DOOR:
                feature_lights.append((ssc, ssr, 2.5, 2.0))
            elif tid == TILE_ALTAR:
                feature_lights.append((ssc, ssr, 3.0, 2.5))
            elif tid == TILE_EXIT:
                feature_lights.append((ssc, ssr, 2.0, 1.5))

    return torch_lights, feature_lights, torch_positions
