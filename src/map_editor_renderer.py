"""
Unified map editor renderer.

Provides ``draw_map_editor()`` — a single entry point that reads a
:class:`MapEditorState` (via ``to_data_dict()``) and draws the
appropriate editor UI.  The function delegates to the host
:class:`Renderer` for sprite helpers (``_u3_draw_overworld_tile``,
``_get_unique_tile_sprite``, font references, etc.).

This module does **not** subclass Renderer — it takes a renderer
reference so it can reuse its sprite cache and font objects.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import pygame

from src.settings import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    TILE_SIZE,
    TILE_DEFS,
)
from src.map_editor import STORAGE_DENSE, STORAGE_SPARSE, _object_origin

if TYPE_CHECKING:
    from src.map_editor import Brush


# ─── Layout constants (shared across all editor surfaces) ─────────────

HEADER_H = 36
FOOTER_H = 28
LEFT_W = 180
PANEL_Y = HEADER_H + 2
LEFT_X = 4
RIGHT_X = LEFT_W + 4
RIGHT_W = SCREEN_WIDTH - RIGHT_X - 4
PANEL_H = SCREEN_HEIGHT - HEADER_H - FOOTER_H - 4
GRID_X = RIGHT_X + 4
GRID_Y = PANEL_Y + 4
GRID_W = RIGHT_W - 8
GRID_H = PANEL_H - 8


# ─── Colours ──────────────────────────────────────────────────────────

_COL_BG = (10, 8, 20)
_COL_HEADER = (20, 16, 30)
_COL_HEADER_LINE = (80, 60, 40)
_COL_PANEL_BG = (18, 14, 28)
_COL_PANEL_BORDER = (60, 50, 40)
_COL_GRID_BG = (8, 6, 16)
_COL_SEL_BAR = (255, 200, 60, 40)
_COL_SEL_BORDER = (200, 160, 60)
_COL_ORANGE = (200, 160, 60)
_COL_HINT = (140, 140, 160)
_COL_LABEL = (120, 120, 160)
_COL_LABEL_SEL = (255, 255, 100)
_COL_LABEL_NORMAL = (180, 180, 200)
_COL_COORD = (140, 140, 160)
_COL_LINK_INT = (80, 220, 255)
_COL_LINK_INT_BG = (0, 140, 200)
_COL_LINK_OW = (255, 180, 60)
_COL_LINK_OW_BG = (200, 120, 0)


# ─── Main entry point ────────────────────────────────────────────────

def draw_map_editor(renderer, data: Dict[str, Any]):
    """Draw the unified map editor UI.

    *renderer* is the host :class:`Renderer` instance (provides fonts,
    sprites, screen surface).  *data* comes from
    ``MapEditorState.to_data_dict()``.
    """
    screen = renderer.screen
    fm = renderer.font_med
    fs = renderer.font_small
    f = renderer.font

    screen.fill(_COL_BG)

    # ── Header ──
    pygame.draw.rect(screen, _COL_HEADER, (0, 0, SCREEN_WIDTH, HEADER_H))
    pygame.draw.line(screen, _COL_HEADER_LINE,
                     (0, HEADER_H - 1), (SCREEN_WIDTH, HEADER_H - 1), 1)

    title = data["title"]
    if data["dirty"]:
        title += " *"
    renderer._u3_text(title, 16, 6, _COL_ORANGE, fm)

    # Painting mode indicator
    if data.get("painting"):
        tw_title = fm.size(title)[0]
        renderer._u3_text("PAINTING", tw_title + 30, 6, (120, 255, 120), fm)

    # Coordinates + tile info
    cc, cr = data["cursor_col"], data["cursor_row"]
    tile_name = _get_cursor_tile_name(data, cc, cr)
    coord_text = f"({cc},{cr}) {tile_name}  [{data['width']}x{data['height']}]"
    tw = fm.size(coord_text)[0]
    renderer._u3_text(coord_text, SCREEN_WIDTH - tw - 16, 6, _COL_COORD, fm)

    # ── Left panel: brush palette ──
    _draw_brush_palette(renderer, data)

    # ── Right panel: tile grid ──
    _draw_tile_grid(renderer, data)

    # ── Overlays ──
    if data.get("int_picking"):
        _draw_int_picker_overlay(renderer, data)
    if data.get("int_link_picking"):
        _draw_int_link_picker_overlay(renderer, data)
    if data.get("replacing"):
        _draw_replace_overlay(renderer, data)

    # ── Save flash ──
    save_flash = data.get("save_flash", 0)
    if save_flash > 0:
        alpha = min(255, int(save_flash * 255))
        msg = "Saved!"
        tw = fm.size(msg)[0]
        sx = SCREEN_WIDTH // 2 - tw // 2
        sy = HEADER_H + 10
        surf = pygame.Surface((tw + 20, 28), pygame.SRCALPHA)
        surf.fill((40, 120, 40, alpha))
        screen.blit(surf, (sx - 10, sy - 4))
        c = (180, 255, 180) if alpha > 128 else (180, 255, 180, alpha)
        renderer._u3_text(msg, sx, sy, (180, 255, 180), fm)

    # ── Footer ──
    _draw_footer(renderer, data)


# ─── Brush palette (left panel) ──────────────────────────────────────

_COL_FOLDER_HEADER = (200, 160, 60)
_COL_FOLDER_ARROW = (200, 160, 60)
_COL_OBJECT_ICON = (120, 180, 220)


def _visible_brush_indices(brushes, brush_folders):
    """Return list of brush indices that should be displayed (respecting
    collapsed folder state)."""
    visible = []
    cur_group = None
    collapsed = False
    for i, b in enumerate(brushes):
        if getattr(b, 'is_folder_header', False):
            cur_group = b.name
            collapsed = not brush_folders.get(b.name, True)
            visible.append(i)
        elif collapsed and getattr(b, 'group', None) == cur_group:
            continue
        else:
            visible.append(i)
    return visible


def _draw_brush_palette(renderer, data: Dict):
    screen = renderer.screen
    fs = renderer.font_small

    panel_h = PANEL_H
    pygame.draw.rect(screen, _COL_PANEL_BG,
                     (LEFT_X, PANEL_Y, LEFT_W, panel_h))
    pygame.draw.rect(screen, _COL_PANEL_BORDER,
                     (LEFT_X, PANEL_Y, LEFT_W, panel_h), 1)

    renderer._u3_text("BRUSH PALETTE", LEFT_X + 10, PANEL_Y + 6,
                      _COL_LABEL, fs)

    brushes: list = data["brushes"]
    brush_idx: int = data["brush_idx"]
    storage = data["storage"]
    brush_folders = data.get("brush_folders", {})

    # Build visible index list (respects collapsed folders)
    vis = _visible_brush_indices(brushes, brush_folders)

    brush_row_h = 36 if storage == STORAGE_DENSE else 32
    brush_y0 = PANEL_Y + 26
    max_vis = (panel_h - 60) // brush_row_h

    # Scroll to keep selected brush in view
    try:
        sel_pos = vis.index(brush_idx)
    except ValueError:
        sel_pos = 0
    b_scroll = max(0, sel_pos - max_vis + 1)

    for vi in range(b_scroll,
                    min(b_scroll + max_vis, len(vis))):
        bi = vis[vi]
        by = brush_y0 + (vi - b_scroll) * brush_row_h
        is_sel = (bi == brush_idx)
        brush = brushes[bi]

        # Selection highlight
        if is_sel:
            bar = pygame.Surface((LEFT_W - 8, brush_row_h - 2),
                                 pygame.SRCALPHA)
            bar.fill(_COL_SEL_BAR)
            screen.blit(bar, (LEFT_X + 4, by))
            pygame.draw.rect(screen, _COL_SEL_BORDER,
                             (LEFT_X + 4, by,
                              LEFT_W - 8, brush_row_h - 2), 1)

        # ── Folder header ──
        if getattr(brush, 'is_folder_header', False):
            is_open = brush_folders.get(brush.name, True)
            arrow = "\u25BC" if is_open else "\u25B6"  # ▼ or ▶
            renderer._u3_text(
                arrow, LEFT_X + 10,
                by + (8 if storage == STORAGE_DENSE else 6),
                _COL_FOLDER_ARROW, fs)
            nc = _COL_FOLDER_HEADER if not is_sel else (255, 220, 80)
            renderer._u3_text(
                brush.name, LEFT_X + 24,
                by + (8 if storage == STORAGE_DENSE else 6),
                nc, fs)
            continue

        # ── Object brush ──
        if getattr(brush, 'is_object', False):
            icon_x = LEFT_X + 18
            icon_sz = 18
            # Draw a mini grid icon to represent multi-tile stamp
            pygame.draw.rect(screen, (35, 40, 55),
                             (icon_x, by + 4, icon_sz, icon_sz))
            for gr in range(3):
                for gc in range(3):
                    cell = icon_sz // 3
                    cx = icon_x + gc * cell
                    cy = by + 4 + gr * cell
                    if (gr + gc) % 2 == 0:
                        pygame.draw.rect(screen, _COL_OBJECT_ICON,
                                         (cx + 1, cy + 1,
                                          cell - 2, cell - 2))
            pygame.draw.rect(screen, _COL_PANEL_BORDER,
                             (icon_x, by + 4, icon_sz, icon_sz), 1)
            nc = _COL_LABEL_SEL if is_sel else _COL_LABEL_NORMAL
            renderer._u3_text(
                brush.name, icon_x + icon_sz + 6,
                by + (8 if storage == STORAGE_DENSE else 6),
                nc, fs)
            continue

        # ── Regular tile brush ──
        icon_x = LEFT_X + 18 if storage == STORAGE_DENSE else LEFT_X + 18
        icon_sz = 26 if storage == STORAGE_DENSE else 22
        text_x = icon_x + icon_sz + 6

        if storage == STORAGE_DENSE:
            _draw_dense_brush_icon(renderer, brush, icon_x, by, icon_sz)
        else:
            text_x = _draw_sparse_brush_icon(
                renderer, brush, icon_x, by, icon_sz)

        # Label
        nc = _COL_LABEL_SEL if is_sel else _COL_LABEL_NORMAL
        renderer._u3_text(brush.name, text_x, by + (8 if storage == STORAGE_DENSE else 6), nc, fs)

    # Hints at bottom
    renderer._u3_text("[Tab] Next Brush",
                      LEFT_X + 10, PANEL_Y + panel_h - 36,
                      _COL_HINT, fs)
    renderer._u3_text("[Shift+Tab] Prev",
                      LEFT_X + 10, PANEL_Y + panel_h - 20,
                      _COL_HINT, fs)


def _draw_dense_brush_icon(renderer, brush, icon_x, by, icon_sz):
    """Draw brush icon for dense (overworld) editors."""
    screen = renderer.screen
    if brush.is_eraser:
        # Eraser X icon
        pygame.draw.rect(screen, (40, 35, 50),
                         (icon_x, by + 4, icon_sz, icon_sz))
        pygame.draw.line(screen, (200, 80, 80),
                         (icon_x + 3, by + 7),
                         (icon_x + icon_sz - 4, by + 4 + icon_sz - 4), 2)
        pygame.draw.line(screen, (200, 80, 80),
                         (icon_x + icon_sz - 4, by + 7),
                         (icon_x + 3, by + 4 + icon_sz - 4), 2)
        pygame.draw.rect(screen, (80, 60, 60),
                         (icon_x, by + 4, icon_sz, icon_sz), 1)
    else:
        # Mini overworld tile sprite
        tmp = pygame.Surface((TILE_SIZE, TILE_SIZE))
        tmp.fill(_COL_BG)
        saved = renderer.screen
        renderer.screen = tmp
        renderer._u3_draw_overworld_tile(brush.tile_id, 0, 0, TILE_SIZE, 0, 0)
        renderer.screen = saved
        scaled = pygame.transform.scale(tmp, (icon_sz, icon_sz))
        screen.blit(scaled, (icon_x, by + 4))
        pygame.draw.rect(screen, _COL_PANEL_BORDER,
                         (icon_x, by + 4, icon_sz, icon_sz), 1)


def _draw_sparse_brush_icon(renderer, brush, icon_x, by, icon_sz) -> int:
    """Draw brush icon for sparse (interior) editors. Returns text_x."""
    screen = renderer.screen
    text_x = icon_x + 4

    if brush.path:
        spr = renderer._get_unique_tile_sprite(brush.path, icon_sz)
        if spr:
            screen.blit(spr, (icon_x, by + 4))
            text_x = icon_x + icon_sz + 6
    elif brush.tile_id is not None:
        # Try unified sprite cache first (works for all tile types)
        drawn = False
        base_spr = renderer._get_tile_sprite(brush.tile_id)
        if base_spr:
            scaled = pygame.transform.scale(base_spr, (icon_sz, icon_sz))
            screen.blit(scaled, (icon_x, by + 4))
            drawn = True
        if not drawn:
            tdef = TILE_DEFS.get(brush.tile_id, {})
            tc = tdef.get("color", (80, 80, 80))
            pygame.draw.rect(screen, tc,
                             pygame.Rect(icon_x, by + 4, icon_sz, icon_sz))
        pygame.draw.rect(screen, _COL_PANEL_BORDER,
                         pygame.Rect(icon_x, by + 4, icon_sz, icon_sz), 1)
        text_x = icon_x + icon_sz + 6

    return text_x


# ─── Tile grid (right panel) ─────────────────────────────────────────

def _draw_tile_grid(renderer, data: Dict):
    screen = renderer.screen

    pygame.draw.rect(screen, _COL_GRID_BG, (GRID_X, GRID_Y, GRID_W, GRID_H))

    if data["storage"] == STORAGE_DENSE:
        _draw_dense_grid(renderer, data)
    else:
        _draw_sparse_grid(renderer, data)

    # Grid border
    pygame.draw.rect(screen, _COL_PANEL_BORDER,
                     (GRID_X, GRID_Y, GRID_W, GRID_H), 1)


def _draw_dense_grid(renderer, data: Dict):
    """Draw scrollable dense 2D tile grid (overview map style)."""
    screen = renderer.screen
    tiles = data["tiles"]
    map_w, map_h = data["width"], data["height"]
    cam_c = data.get("cam_col", 0)
    cam_r = data.get("cam_row", 0)
    ts = data.get("tile_size", TILE_SIZE)

    vis_cols = GRID_W // ts
    vis_rows = GRID_H // ts
    cam_c = max(0, min(cam_c, map_w - vis_cols))
    cam_r = max(0, min(cam_r, map_h - vis_rows))

    total_draw_w = min(map_w, vis_cols) * ts
    total_draw_h = min(map_h, vis_rows) * ts
    ox = GRID_X + (GRID_W - total_draw_w) // 2
    oy = GRID_Y + (GRID_H - total_draw_h) // 2

    end_c = min(cam_c + vis_cols, map_w)
    end_r = min(cam_r + vis_rows, map_h)

    for mr in range(cam_r, end_r):
        for mc in range(cam_c, end_c):
            tile_id = tiles[mr][mc]
            px = ox + (mc - cam_c) * ts
            py = oy + (mr - cam_r) * ts
            renderer._u3_draw_overworld_tile(tile_id, px, py, ts, mc, mr)

    # Object stamp preview (ghost overlay on dense grid)
    brushes = data.get("brushes", [])
    bidx = data.get("brush_idx", 0)
    cur_brush = brushes[bidx] if bidx < len(brushes) else None
    cur_c, cur_r = data["cursor_col"], data["cursor_row"]
    if (cur_brush and getattr(cur_brush, 'is_object', False)
            and cur_brush.object_data):
        elapsed = pygame.time.get_ticks() / 1000.0
        pulse_a = int(40 + 20 * math.sin(elapsed * 3))
        min_c, min_r = _object_origin(cur_brush.object_data)
        for pos_key in cur_brush.object_data:
            parts = pos_key.split(",")
            if len(parts) != 2:
                continue
            oc, orow = int(parts[0]), int(parts[1])
            tc = cur_c + (oc - min_c)
            tr = cur_r + (orow - min_r)
            if cam_c <= tc < end_c and cam_r <= tr < end_r:
                gpx = ox + (tc - cam_c) * ts
                gpy = oy + (tr - cam_r) * ts
                ghost_s = pygame.Surface((ts, ts), pygame.SRCALPHA)
                ghost_s.fill((120, 180, 220, pulse_a))
                screen.blit(ghost_s, (gpx, gpy))

    # Cursor
    if cam_c <= cur_c < end_c and cam_r <= cur_r < end_r:
        elapsed = pygame.time.get_ticks() / 1000.0
        pulse = int(80 + 40 * math.sin(elapsed * 4))
        cx = ox + (cur_c - cam_c) * ts
        cy = oy + (cur_r - cam_r) * ts
        pygame.draw.rect(screen, (255, 200, pulse), (cx, cy, ts, ts), 2)

    # Tile link badges
    tile_links = data.get("tile_links", {})
    for link_key, link_val in tile_links.items():
        parts = link_key.split(",")
        if len(parts) != 2:
            continue
        lc, lr = int(parts[0]), int(parts[1])
        if cam_c <= lc < end_c and cam_r <= lr < end_r:
            bx = ox + (lc - cam_c) * ts
            by_ = oy + (lr - cam_r) * ts
            pygame.draw.rect(screen, _COL_LINK_INT, (bx, by_, ts, ts), 2)
            badge_sz = max(ts // 3, 8)
            ibx = bx + ts - badge_sz - 1
            iby = by_ + 1
            pygame.draw.rect(screen, _COL_LINK_INT_BG,
                             (ibx, iby, badge_sz, badge_sz))
            if badge_sz >= 8:
                tiny = (renderer.font_tiny
                        if hasattr(renderer, 'font_tiny')
                        else renderer.font_small)
                isf = tiny.render("I", True, (255, 255, 255))
                screen.blit(isf, (ibx + 1, iby))


def _draw_sparse_grid(renderer, data: Dict):
    """Draw fixed-size sparse tile grid (interior style)."""
    screen = renderer.screen
    tiles = data["tiles"]
    tw, th = data["width"], data["height"]
    ts = data.get("tile_size", 24)

    total_w = tw * ts
    total_h = th * ts
    gx = GRID_X + (GRID_W - total_w) // 2
    gy = GRID_Y + (GRID_H - total_h) // 2

    for r in range(th):
        for c in range(tw):
            px = gx + c * ts
            py = gy + r * ts
            pos_key = f"{c},{r}"

            if pos_key in tiles:
                td = tiles[pos_key]
                tid = td.get("tile_id") if isinstance(td, dict) else td
                # Try sprite first
                drawn = False
                if isinstance(td, dict):
                    path = td.get("path")
                    if path:
                        sprite = renderer._get_unique_tile_sprite(path, ts)
                        if sprite:
                            screen.blit(sprite, (px, py))
                            drawn = True
                if not drawn:
                    # Try unified sprite cache (works for all tile types)
                    base_spr = renderer._get_tile_sprite(tid)
                    if base_spr:
                        scaled = pygame.transform.scale(
                            base_spr, (ts, ts))
                        screen.blit(scaled, (px, py))
                        drawn = True
                if not drawn:
                    col = TILE_DEFS.get(tid, {}).get("color", (80, 80, 80))
                    pygame.draw.rect(screen, col,
                                     pygame.Rect(px, py, ts, ts))

                # Link badges
                if isinstance(td, dict):
                    _draw_sparse_link_badge(screen, renderer, td,
                                            px, py, ts)
            else:
                # Checkerboard for empty
                half = max(ts // 2, 1)
                for qr in range(2):
                    for qc in range(2):
                        qx = px + qc * half
                        qy = py + qr * half
                        qcol = ((45, 45, 45) if (qr + qc) % 2 == 0
                                else (30, 30, 30))
                        pygame.draw.rect(screen, qcol,
                                         pygame.Rect(qx, qy, half, half))

            # Grid lines
            pygame.draw.rect(screen, (40, 35, 30),
                             pygame.Rect(px, py, ts, ts), 1)

    # Object stamp preview (ghost outline)
    brushes = data.get("brushes", [])
    bidx = data.get("brush_idx", 0)
    cur_brush = brushes[bidx] if bidx < len(brushes) else None
    cx, cy = data["cursor_col"], data["cursor_row"]
    if (cur_brush and getattr(cur_brush, 'is_object', False)
            and cur_brush.object_data):
        elapsed = pygame.time.get_ticks() / 1000.0
        pulse_a = int(40 + 20 * math.sin(elapsed * 3))
        min_c, min_r = _object_origin(cur_brush.object_data)
        ghost = pygame.Surface((tw * ts, th * ts), pygame.SRCALPHA)
        for pos_key in cur_brush.object_data:
            parts = pos_key.split(",")
            if len(parts) != 2:
                continue
            oc, orow = int(parts[0]), int(parts[1])
            tc = cx + (oc - min_c)
            tr = cy + (orow - min_r)
            if 0 <= tc < tw and 0 <= tr < th:
                ghost.fill((120, 180, 220, pulse_a),
                           pygame.Rect(tc * ts, tr * ts, ts, ts))
        screen.blit(ghost, (gx, gy))

    # Cursor
    if cx >= 0 and cy >= 0:
        elapsed = pygame.time.get_ticks() / 1000.0
        pulse = int(80 + 40 * math.sin(elapsed * 4))
        cursor_rect = pygame.Rect(gx + cx * ts, gy + cy * ts, ts, ts)
        pygame.draw.rect(screen, (255, 200, pulse), cursor_rect, 2)


def _draw_sparse_link_badge(screen, renderer, td: Dict,
                            px: int, py: int, ts: int):
    """Draw an interior/overworld link badge on a sparse tile."""
    badge_char = None
    badge_border = None
    badge_bg = None
    if td.get("to_overworld") or td.get("to_town"):
        badge_border = _COL_LINK_OW
        badge_bg = _COL_LINK_OW_BG
        badge_char = "T" if td.get("to_town") else "O"
    elif td.get("interior"):
        badge_border = _COL_LINK_INT
        badge_bg = _COL_LINK_INT_BG
        badge_char = "I"
    if badge_char:
        pygame.draw.rect(screen, badge_border,
                         pygame.Rect(px, py, ts, ts), 2)
        badge_sz = max(ts // 3, 6)
        bxb = px + ts - badge_sz - 1
        byb = py + 1
        pygame.draw.rect(screen, badge_bg,
                         pygame.Rect(bxb, byb, badge_sz, badge_sz))
        if badge_sz >= 8:
            tiny = (renderer.font_tiny
                    if hasattr(renderer, 'font_tiny')
                    else renderer.font_small)
            isf = tiny.render(badge_char, True, (255, 255, 255))
            screen.blit(isf, (bxb + 1, byb))


# ─── Overlays ─────────────────────────────────────────────────────────

def _draw_int_picker_overlay(renderer, data: Dict):
    """Draw the interior link picker for the overview map editor."""
    screen = renderer.screen
    fs = renderer.font_small
    f = renderer.font

    interiors = data.get("int_pick_list", [])
    cursor = data.get("int_pick_cursor", 0)

    ow = min(GRID_W - 40, 300)
    oh = min(GRID_H - 40, 40 + (1 + len(interiors)) * 28)
    ox = GRID_X + (GRID_W - ow) // 2
    oy = GRID_Y + (GRID_H - oh) // 2

    overlay = pygame.Surface((ow, oh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 220))
    screen.blit(overlay, (ox, oy))
    pygame.draw.rect(screen, _COL_LINK_INT, (ox, oy, ow, oh), 1)

    renderer._u3_text("LINK INTERIOR", ox + 10, oy + 6, _COL_ORANGE, f)

    row_h = 28
    ly = oy + 32
    def _fmt_interior(entry):
        name = entry.get("name", "?")
        itype = entry.get("type", "")
        if itype:
            return f"[{itype.capitalize()}] {name}"
        return name
    options = ["(none)"] + [_fmt_interior(i) for i in interiors]
    for i, label in enumerate(options):
        y = ly + i * row_h
        if y + row_h > oy + oh:
            break
        is_sel = (i == cursor)
        if is_sel:
            bar = pygame.Surface((ow - 8, row_h - 2), pygame.SRCALPHA)
            bar.fill((_COL_LINK_INT[0], _COL_LINK_INT[1],
                      _COL_LINK_INT[2], 40))
            screen.blit(bar, (ox + 4, y))
        nc = ((255, 100, 100) if i == 0
              else (_COL_LABEL_SEL if is_sel else _COL_LABEL_NORMAL))
        prefix = "> " if is_sel else "  "
        renderer._u3_text(f"{prefix}{label}", ox + 10, y + 4, nc, fs)


def _draw_int_link_picker_overlay(renderer, data: Dict):
    """Draw the interior link picker for the interior painter."""
    screen = renderer.screen
    fs = renderer.font_small
    f = renderer.font

    pick_list = data.get("int_link_pick_list", [])
    exit_opts = data.get("int_link_exit_options", [])
    cursor = data.get("int_link_pick_cursor", 0)

    n_exits = len(exit_opts)
    ow = min(GRID_W - 40, 320)
    n_opts = 1 + n_exits + len(pick_list)
    oh = min(GRID_H - 40, 40 + n_opts * 28)
    ox = GRID_X + (GRID_W - ow) // 2
    oy = GRID_Y + (GRID_H - oh) // 2

    overlay = pygame.Surface((ow, oh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 220))
    screen.blit(overlay, (ox, oy))
    pygame.draw.rect(screen, _COL_LINK_INT, (ox, oy, ow, oh), 1)

    renderer._u3_text("LINK TO", ox + 10, oy + 6, _COL_ORANGE, f)

    row_h = 28
    ly = oy + 32
    # Build display options: (none), then exit options, then siblings
    options = [u"(none)"]
    for eo in exit_opts:
        options.append(eo.get("label", "?"))
    for intr in pick_list:
        options.append(intr.get("name", "?"))

    for i, label in enumerate(options):
        y = ly + i * row_h
        if y + row_h > oy + oh:
            break
        is_sel = (i == cursor)
        if is_sel:
            bar = pygame.Surface((ow - 8, row_h - 2), pygame.SRCALPHA)
            bar.fill((_COL_LINK_INT[0], _COL_LINK_INT[1],
                      _COL_LINK_INT[2], 40))
            screen.blit(bar, (ox + 4, y))
        if i == 0:
            nc = (255, 100, 100)       # (none) in red
        elif i <= n_exits:
            nc = (100, 255, 100)       # exit options in green
        else:
            nc = _COL_LABEL_SEL if is_sel else _COL_LABEL_NORMAL
        prefix = "> " if is_sel else "  "
        renderer._u3_text(f"{prefix}{label}", ox + 10, y + 4, nc, fs)


def _draw_replace_overlay(renderer, data: Dict):
    """Draw the replace-tile overlay for interior editors."""
    screen = renderer.screen
    fs = renderer.font_small
    f = renderer.font

    brushes = data["brushes"]
    src_tile = data.get("replace_src_tile")
    src_name = data.get("replace_src_name", "")
    src_empty = data.get("replace_src_empty", False)
    dst_idx = data.get("replace_dst_idx", 0)

    ow = min(GRID_W - 20, 280)
    oh = GRID_H - 20
    ox = GRID_X + (GRID_W - ow) // 2
    oy = GRID_Y + 10

    overlay = pygame.Surface((ow, oh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 220))
    screen.blit(overlay, (ox, oy))
    pygame.draw.rect(screen, _COL_SEL_BORDER, (ox, oy, ow, oh), 1)

    renderer._u3_text("REPLACE TILE", ox + 10, oy + 6, _COL_ORANGE, f)

    # Source info
    src_y = oy + 30
    renderer._u3_text("Source:", ox + 10, src_y, _COL_HINT, fs)
    if src_empty:
        sw = 18
        for qr in range(2):
            for qc in range(2):
                qcol = ((50, 50, 50) if (qr + qc) % 2 == 0
                        else (35, 35, 35))
                pygame.draw.rect(screen, qcol,
                                 pygame.Rect(ox + 70 + qc * (sw // 2),
                                             src_y + qr * (sw // 2),
                                             sw // 2, sw // 2))
    else:
        src_drawn = False
        src_spr = renderer._get_tile_sprite(src_tile)
        if src_spr:
            scaled = pygame.transform.scale(src_spr, (18, 18))
            screen.blit(scaled, (ox + 70, src_y))
            src_drawn = True
        if not src_drawn:
            tdef = TILE_DEFS.get(src_tile, {})
            tc = tdef.get("color", (80, 80, 80))
            pygame.draw.rect(screen, tc, pygame.Rect(ox + 70, src_y, 18, 18))
    renderer._u3_text(src_name, ox + 95, src_y + 2, (255, 255, 200), fs)

    # Destination list
    dst_y0 = src_y + 28
    renderer._u3_text("Destination:", ox + 10, dst_y0, _COL_HINT, fs)
    row_h = 26
    list_y0 = dst_y0 + 20
    max_vis = (oy + oh - list_y0 - 10) // row_h
    scroll = max(0, dst_idx - max_vis + 1)

    for i in range(scroll, min(scroll + max_vis, len(brushes))):
        ly = list_y0 + (i - scroll) * row_h
        is_sel = (i == dst_idx)
        if is_sel:
            bar = pygame.Surface((ow - 16, row_h - 2), pygame.SRCALPHA)
            bar.fill(_COL_SEL_BAR)
            screen.blit(bar, (ox + 8, ly))

        b = brushes[i]
        if b.tile_id is not None:
            dst_drawn = False
            dst_spr = renderer._get_tile_sprite(b.tile_id)
            if dst_spr:
                scaled = pygame.transform.scale(dst_spr, (16, 16))
                screen.blit(scaled, (ox + 14, ly + 2))
                dst_drawn = True
            if not dst_drawn:
                tdef = TILE_DEFS.get(b.tile_id, {})
                tc = tdef.get("color", (80, 80, 80))
                pygame.draw.rect(screen, tc,
                                 pygame.Rect(ox + 14, ly + 2, 16, 16))
        else:
            pygame.draw.rect(screen, (40, 35, 50),
                             pygame.Rect(ox + 14, ly + 2, 16, 16))
            pygame.draw.line(screen, (200, 80, 80),
                             (ox + 16, ly + 4), (ox + 28, ly + 16), 1)

        nc = _COL_LABEL_SEL if is_sel else _COL_LABEL_NORMAL
        prefix = "> " if is_sel else "  "
        renderer._u3_text(f"{prefix}{b.name}", ox + 36, ly + 2, nc, fs)


# ─── Footer hints ────────────────────────────────────────────────────

def _draw_footer(renderer, data: Dict):
    fs = renderer.font_small

    if data.get("replacing"):
        hint = ("[Up/Dn] Select Destination  "
                "[Enter] Replace All  [Esc] Cancel")
    elif data.get("int_link_picking"):
        hint = "[Up/Dn] Select  [Enter] Confirm  [Esc] Cancel"
    elif data.get("int_picking"):
        hint = "[Up/Dn] Select  [Enter] Confirm  [Esc] Cancel"
    elif data["storage"] == STORAGE_DENSE:
        hint = ("[Arrows] Move  [Enter/Space] Paint  "
                "[Tab] Brush  [I] Link  [X] Unlink  "
                "[Ctrl+S] Save  [Esc] Save & Exit")
    else:
        hint = ("[Arrows/WASD] Move  [Enter] Paint  "
                "[I] Link  [R] Replace  [X] Unlink  "
                "[Tab] Brush  [Ctrl+S] Save  [Esc] Save & Exit")

    hw = fs.size(hint)[0]
    renderer._u3_text(hint,
                      SCREEN_WIDTH // 2 - hw // 2,
                      SCREEN_HEIGHT - FOOTER_H + 4,
                      _COL_HINT, fs)


# ─── Helpers ──────────────────────────────────────────────────────────

def _get_cursor_tile_name(data: Dict, col: int, row: int) -> str:
    """Get the display name of the tile under the cursor."""
    if data["storage"] == STORAGE_DENSE:
        tiles = data["tiles"]
        if 0 <= row < data["height"] and 0 <= col < data["width"]:
            tid = tiles[row][col]
            td = TILE_DEFS.get(tid)
            if td:
                return td["name"]
    else:
        td = data["tiles"].get(f"{col},{row}")
        if isinstance(td, dict):
            return td.get("name", "")
        elif td is None:
            return "(empty)"
    return ""
