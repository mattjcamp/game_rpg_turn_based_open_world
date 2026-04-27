"""
Unified map editor renderer.

Provides ``draw_map_editor()`` — a single entry point that reads a
:class:`MapEditorState` (via ``to_data_dict()``) and draws the
appropriate editor UI.  The function delegates to the host
:class:`Renderer` for sprite helpers (``_draw_tile``,
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

    # Mode indicators
    tw_title = fm.size(title)[0]
    if data.get("painting"):
        renderer._u3_text("PAINTING", tw_title + 30, 6, (120, 255, 120), fm)

    # Coordinates + tile info
    cc, cr = data["cursor_col"], data["cursor_row"]
    tile_name = _get_cursor_tile_name(data, cc, cr)
    coord_text = f"({cc},{cr}) {tile_name}  [{data['width']}x{data['height']}]"
    tw = fm.size(coord_text)[0]
    renderer._u3_text(coord_text, SCREEN_WIDTH - tw - 16, 6, _COL_COORD, fm)

    # ── Left panel: brush palette ──
    _draw_brush_palette(renderer, data)

    # ── Left panel bottom: tile inspector ──
    _draw_tile_inspector(renderer, data)

    # ── Right panel: tile grid ──
    _draw_tile_grid(renderer, data)

    # ── Minimap (any scrollable grid on a large map) ──
    # Shows for both dense and sparse maps once they exceed ~20 tiles
    # per side, matching the Overview Map Editor's preview behaviour.
    if (data.get("grid_type") == "scrollable"
            and (data["width"] > 20 or data["height"] > 20)):
        _draw_minimap(renderer, data)

    # ── Overlays ──
    if data.get("replacing"):
        _draw_replace_overlay(renderer, data)
    if data.get("item_picker_active"):
        _draw_item_picker_overlay(renderer, data)

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

    # ── Map picker overlay (must be last — drawn on top of everything) ──
    if data.get("map_picker_active"):
        _draw_map_picker_overlay(renderer, data)


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


_INSPECTOR_H = 260  # height reserved for the tile inspector at bottom
_BRUSH_PANEL_H = PANEL_H - _INSPECTOR_H - 4  # brush palette gets the rest


def _draw_brush_palette(renderer, data: Dict):
    screen = renderer.screen
    fs = renderer.font_small

    panel_h = _BRUSH_PANEL_H
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


def _draw_encounter_brush_icon(renderer, brush, icon_x, by, icon_sz):
    """Draw the monster-party-tile sprite as this brush's palette icon.

    Looks up the encounter's ``monster_party_tile`` (a monster name)
    and blits that sprite, falling back to a small purple diamond if
    the monster isn't registered. Shared by both the dense and sparse
    brush-icon paths so overworld / town / dungeon / building
    palettes all look consistent.
    """
    screen = renderer.screen
    # Frame the swatch with the standard panel border first so the
    # sprite reads as a clickable tile.
    pygame.draw.rect(screen, (20, 18, 30),
                     (icon_x, by + 4, icon_sz, icon_sz))
    party_tile = _get_encounter_party_tile(brush.encounter_name or "")
    sprite = None
    if party_tile:
        try:
            sprite = renderer._get_monster_sprite_by_name(party_tile)
        except Exception:
            sprite = None
        if sprite is not None and sprite.get_size() != (icon_sz, icon_sz):
            try:
                sprite = pygame.transform.smoothscale(
                    sprite, (icon_sz, icon_sz))
            except Exception:
                sprite = pygame.transform.scale(
                    sprite, (icon_sz, icon_sz))
        if sprite is None:
            try:
                sprite = renderer._get_unique_tile_sprite(
                    party_tile, icon_sz)
            except Exception:
                sprite = None
    if sprite is not None:
        screen.blit(sprite, (icon_x, by + 4))
    else:
        diamond = pygame.Surface((icon_sz, icon_sz), pygame.SRCALPHA)
        cx, cy = icon_sz // 2, icon_sz // 2
        pts = [(cx, 2), (icon_sz - 2, cy),
               (cx, icon_sz - 2), (2, cy)]
        pygame.draw.polygon(diamond, (180, 60, 140, 220), pts)
        pygame.draw.polygon(diamond, (230, 180, 230), pts, 2)
        screen.blit(diamond, (icon_x, by + 4))
    pygame.draw.rect(screen, _COL_PANEL_BORDER,
                     (icon_x, by + 4, icon_sz, icon_sz), 1)


def _draw_dense_brush_icon(renderer, brush, icon_x, by, icon_sz):
    """Draw brush icon for dense (overworld) editors."""
    screen = renderer.screen
    # Encounter brushes have tile_id=None but an encounter_name set —
    # resolve to the monster sprite so the palette shows an Orc / Rat /
    # Goblin instead of a black square.
    if getattr(brush, 'is_encounter', False):
        _draw_encounter_brush_icon(renderer, brush, icon_x, by, icon_sz)
        return
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
        renderer._draw_tile(brush.tile_id, 0, 0, TILE_SIZE, 0, 0)
        renderer.screen = saved
        scaled = pygame.transform.scale(tmp, (icon_sz, icon_sz))
        screen.blit(scaled, (icon_x, by + 4))
        pygame.draw.rect(screen, _COL_PANEL_BORDER,
                         (icon_x, by + 4, icon_sz, icon_sz), 1)


def _draw_sparse_brush_icon(renderer, brush, icon_x, by, icon_sz) -> int:
    """Draw brush icon for sparse (interior) editors. Returns text_x."""
    screen = renderer.screen
    text_x = icon_x + 4

    # Encounter brushes: draw the monster party-tile sprite.
    if getattr(brush, 'is_encounter', False):
        _draw_encounter_brush_icon(renderer, brush, icon_x, by, icon_sz)
        return icon_x + icon_sz + 6

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

def _draw_tile_inspector(renderer, data: Dict):
    """Draw the tile properties inspector panel below the brush palette."""
    screen = renderer.screen
    fs = renderer.font_small

    ix = LEFT_X
    iy = PANEL_Y + _BRUSH_PANEL_H + 4
    iw = LEFT_W
    ih = _INSPECTOR_H
    pad = 8

    pygame.draw.rect(screen, _COL_PANEL_BG, (ix, iy, iw, ih))
    pygame.draw.rect(screen, _COL_PANEL_BORDER, (ix, iy, iw, ih), 1)

    info = data.get("tile_inspector", {})
    fields = info.get("fields", [])
    tile_id = info.get("tile_id")
    editing = data.get("inspector_editing", False)
    edit_idx = data.get("inspector_field_idx", -1)
    edit_buf = data.get("inspector_buffer", "")

    renderer._u3_text("TILE PROPERTIES", ix + pad, iy + 4, _COL_LABEL, fs)

    ty = iy + 20

    if tile_id is None:
        renderer._u3_text("(empty)", ix + pad, ty, (100, 100, 120), fs)
        return

    bottom = iy + ih - 16  # reserve space for hint

    for fi, (label, key, value, field_type) in enumerate(fields):
        if ty + 14 > bottom:
            break

        is_active = editing and fi == edit_idx

        # Highlight bar
        if is_active:
            bar_h = 14 if field_type is False else 28
            bar = pygame.Surface((iw - 4, bar_h), pygame.SRCALPHA)
            bar.fill((255, 200, 60, 30))
            screen.blit(bar, (ix + 2, ty - 1))

        # ── Read-only ──
        if field_type is False:
            text = f"{label}: {value}" if value else label
            renderer._u3_text(text, ix + pad, ty, (220, 220, 230), fs)
            ty += 16
            continue

        # ── Toggle (checkbox) ──
        if field_type == "toggle":
            checked = value == "yes"
            box = "[x]" if checked else "[ ]"
            col = _COL_ORANGE if is_active else (
                (120, 255, 120) if checked else (140, 140, 160))
            renderer._u3_text(f"{box} {label}", ix + pad, ty, col, fs)
            ty += 16
            continue

        # ── Effect (animated overlay picker) ──
        # Glyph + colour signals what's currently attached: a faint dot
        # for "none", smoky grey for rising smoke, hot orange for fire,
        # bright pink for fairy light.  Press Enter/Space to cycle.
        if field_type == "effect":
            val = str(value)
            if val == "(none)" or not val:
                box, col = "[ ]", (140, 140, 160)
            elif "smoke" in val:
                box, col = "[~]", (180, 180, 195)
            elif "fire" in val:
                box, col = "[*]", (255, 150, 60)
            elif "fairy" in val or "light" in val:
                box, col = "[+]", (240, 160, 230)
            else:
                box, col = "[?]", (200, 200, 210)
            if is_active:
                col = _COL_ORANGE
            renderer._u3_text(f"{box} {label}: {val}",
                              ix + pad, ty, col, fs)
            ty += 16
            continue

        # ── Tristate (inherit / yes / no override) ──
        # Glyph: [~] = inherit (taking the tile type's default), [x] =
        # forced walkable, [ ] = forced blocked. Colour coded so the
        # override states stand out from the inherited default.
        if field_type == "tristate":
            val = str(value)
            if val.startswith("inherit"):
                box, col = "[~]", (140, 140, 160)
            elif val.startswith("yes"):
                box, col = "[x]", (120, 255, 120)
            else:
                box, col = "[ ]", (255, 120, 120)
            if is_active:
                col = _COL_ORANGE
            renderer._u3_text(f"{box} {label}: {val}",
                              ix + pad, ty, col, fs)
            ty += 16
            continue

        # ── Map picker ──
        if field_type == "map_picker":
            lbl_col = _COL_ORANGE if is_active else (140, 140, 160)
            renderer._u3_text(label, ix + pad, ty, lbl_col, fs)
            ty += 13
            if ty + 14 > bottom:
                break
            display = value if value else "(none)"
            if len(display) > 20:
                display = "..." + display[-17:]
            val_col = (255, 255, 200) if is_active else (
                (200, 200, 210) if value else (80, 80, 100))
            if is_active:
                display += " >"
            renderer._u3_text(f" {display}", ix + pad, ty, val_col, fs)
            ty += 18
            continue

        # ── Text / number ──
        lbl_col = _COL_ORANGE if is_active else (140, 140, 160)
        renderer._u3_text(label, ix + pad, ty, lbl_col, fs)
        ty += 13
        if ty + 14 > bottom:
            break
        if is_active:
            ticks = pygame.time.get_ticks()
            cursor_ch = "_" if (ticks // 400) % 2 == 0 else " "
            display = edit_buf + cursor_ch
            val_col = (255, 255, 200)
        else:
            display = value if value else "--"
            val_col = (200, 200, 210) if value else (80, 80, 100)
        renderer._u3_text(f" {display}", ix + pad, ty, val_col, fs)
        ty += 18

    # Footer hint
    if editing:
        hint = "[Up/Dn] [Enter] Done [Esc] Cancel"
    else:
        hint = "[E] Edit tile"
    renderer._u3_text(hint, ix + pad, bottom, (80, 80, 100), fs)


def _draw_map_picker_overlay(renderer, data: Dict):
    """Draw the map hierarchy picker as a centered overlay."""
    screen = renderer.screen
    fs = renderer.font_small
    fm = renderer.font_med

    hierarchy = data.get("map_hierarchy", [])
    cursor = data.get("map_picker_cursor", 0)
    if not hierarchy:
        return

    pw = min(SCREEN_WIDTH - 40, 600)
    ph = min(SCREEN_HEIGHT - 60, 500)
    px = (SCREEN_WIDTH - pw) // 2
    py = (SCREEN_HEIGHT - ph) // 2

    pygame.draw.rect(screen, (20, 20, 30), (px, py, pw, ph))
    pygame.draw.rect(screen, _COL_ORANGE, (px, py, pw, ph), 2)

    renderer._u3_text("SELECT TARGET MAP", px + 16, py + 10,
                      _COL_ORANGE, fm)
    renderer._u3_text(f"{len(hierarchy)} maps available",
                      px + 16, py + 28, (100, 100, 120), fs)

    row_h = 22
    list_y = py + 46
    list_h = ph - 80
    max_vis = list_h // row_h

    scroll = max(0, min(cursor - max_vis // 2,
                        len(hierarchy) - max_vis))

    for vi in range(scroll, min(scroll + max_vis, len(hierarchy))):
        map_id, label, indent = hierarchy[vi]
        is_sel = (vi == cursor)
        ly = list_y + (vi - scroll) * row_h

        if is_sel:
            bar = pygame.Surface((pw - 20, row_h), pygame.SRCALPHA)
            bar.fill((255, 200, 60, 40))
            screen.blit(bar, (px + 10, ly))

        indent_str = "    " * indent
        prefix = "> " if is_sel else "  "
        col = (255, 255, 230) if is_sel else (180, 180, 200)
        # Indent children; show category icon for top-level items
        if indent == 0:
            renderer._u3_text(f"{prefix}{label}",
                              px + 14, ly + 3, col, fs)
        else:
            renderer._u3_text(f"{prefix}  {indent_str}{label}",
                              px + 14, ly + 3,
                              (200, 200, 220) if is_sel else (150, 150, 170),
                              fs)

    # Show selected map ID at the bottom
    if 0 <= cursor < len(hierarchy):
        sel_id = hierarchy[cursor][0]
        renderer._u3_text(f"ID: {sel_id}", px + 16, py + ph - 34,
                          (120, 120, 140), fs)

    renderer._u3_text("[Up/Dn] Navigate  [Enter] Select  [Esc] Cancel",
                      px + 16, py + ph - 18, (100, 100, 120), fs)


def _draw_item_picker_overlay(renderer, data: Dict):
    """Modal item picker — a scrollable grid of item icons + names.

    Users see each item's real icon (the same one that shows in the
    shop / examine / inventory) so there's no guesswork about what
    they'll place on the map.
    """
    screen = renderer.screen
    fs = renderer.font_small
    fm = renderer.font_med

    names = data.get("item_list", []) or []
    if not names:
        return
    cursor = data.get("item_picker_cursor", 0)
    cursor = max(0, min(cursor, len(names) - 1))

    # Import item data once for icon + tint lookup.
    try:
        from src.party import ITEM_INFO
    except Exception:
        ITEM_INFO = {}

    pw = min(SCREEN_WIDTH - 40, 720)
    ph = min(SCREEN_HEIGHT - 60, 520)
    px = (SCREEN_WIDTH - pw) // 2
    py = (SCREEN_HEIGHT - ph) // 2

    # Dim everything behind the modal.
    dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 160))
    screen.blit(dim, (0, 0))

    pygame.draw.rect(screen, (16, 14, 28), (px, py, pw, ph))
    pygame.draw.rect(screen, _COL_ORANGE, (px, py, pw, ph), 2)

    renderer._u3_text("PLACE ITEM", px + 16, py + 10, _COL_ORANGE, fm)
    renderer._u3_text(
        f"{len(names)} items",
        px + 16, py + 32, (130, 130, 150), fs)

    # Grid layout
    pad_in = 14
    list_top = py + 56
    list_bottom = py + ph - 60
    cell_w = 64
    cell_h = 72
    cols = max(1, (pw - 2 * pad_in) // cell_w)
    rows_vis = max(1, (list_bottom - list_top) // cell_h)

    row_of_cursor = cursor // cols
    # Scroll so cursor stays visible, with a small lead.
    scroll = data.get("item_picker_scroll", 0)
    if row_of_cursor < scroll:
        scroll = row_of_cursor
    elif row_of_cursor >= scroll + rows_vis:
        scroll = row_of_cursor - rows_vis + 1
    data["item_picker_scroll"] = scroll  # cache for next frame

    # Draw visible cells
    for i, name in enumerate(names):
        r = i // cols
        c = i % cols
        if r < scroll or r >= scroll + rows_vis:
            continue
        x = px + pad_in + c * cell_w
        y = list_top + (r - scroll) * cell_h

        is_sel = (i == cursor)
        if is_sel:
            bar = pygame.Surface((cell_w - 2, cell_h - 2),
                                 pygame.SRCALPHA)
            bar.fill((255, 200, 60, 40))
            screen.blit(bar, (x + 1, y + 1))
            pygame.draw.rect(screen, _COL_ORANGE,
                             (x + 1, y + 1, cell_w - 2, cell_h - 2), 1)

        # Icon
        info = ITEM_INFO.get(name, {})
        icon_type = info.get("icon", "tool")
        tint = renderer._potion_tint(info) if info else None
        icx = x + cell_w // 2
        icy = y + 26
        icon_sz = 40
        bg = pygame.Surface((icon_sz, icon_sz), pygame.SRCALPHA)
        pygame.draw.rect(bg, (20, 20, 28, 200),
                         pygame.Rect(0, 0, icon_sz, icon_sz),
                         border_radius=4)
        screen.blit(bg, (icx - icon_sz // 2, icy - icon_sz // 2))
        renderer._draw_item_icon(icx, icy, icon_type, icon_sz, tint=tint)

        # Name (truncated if too long for the cell)
        lbl = name
        max_w = cell_w - 4
        while fs.size(lbl)[0] > max_w and len(lbl) > 2:
            lbl = lbl[:-1]
        if lbl != name:
            lbl = lbl[:-1] + "…"
        name_col = (255, 255, 230) if is_sel else (200, 200, 215)
        tw = fs.size(lbl)[0]
        renderer._u3_text(lbl, x + (cell_w - tw) // 2,
                          y + cell_h - 14, name_col, fs)

    # Selection readout and controls hint at the bottom
    sel_name = names[cursor] if names else ""
    sel_info = ITEM_INFO.get(sel_name, {})
    sel_desc = sel_info.get("desc", "") if sel_info else ""
    footer_y = py + ph - 44
    renderer._u3_text(f"Selected: {sel_name}", px + 16, footer_y,
                      (255, 220, 120), fs)
    if sel_desc:
        # Truncate the description to fit
        maxw = pw - 32
        desc = sel_desc
        while fs.size(desc)[0] > maxw and len(desc) > 3:
            desc = desc[:-1]
        if desc != sel_desc:
            desc = desc[:-1] + "…"
        renderer._u3_text(desc, px + 16, footer_y + 14,
                          (160, 160, 180), fs)

    renderer._u3_text(
        "[Arrows/PgUp/PgDn/Home/End] Browse  "
        "[Enter] Place  [Backspace] Clear  [Esc] Cancel",
        px + 16, py + ph - 18, (110, 110, 135), fs)


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

    tprops_for_fx = data.get("tile_properties") or {}
    for mr in range(cam_r, end_r):
        for mc in range(cam_c, end_c):
            tile_id = tiles[mr][mc]
            px = ox + (mc - cam_c) * ts
            py = oy + (mr - cam_r) * ts
            renderer._draw_tile(tile_id, px, py, ts, mc, mr)
            # Editor preview of animated tile effects: _draw_tile got
            # called without a tile_map, so its built-in finally hook
            # has nothing to look up.  Run the overlay explicitly,
            # passing the editor's tile_properties dict directly.
            if tprops_for_fx:
                renderer._draw_tile_effect_overlay(
                    px, py, ts, mc, mr,
                    tile_properties=tprops_for_fx)

    # Ground-item overlay (tiles with tile_properties[...]["item"] set)
    _draw_ground_items(renderer, data, ox, oy, ts,
                       cam_c, cam_r, end_c, end_r)

    # Encounter overlays (party-tile sprite per placed encounter)
    _draw_encounter_overlays(renderer, data, ox, oy, ts,
                             cam_c, cam_r, end_c, end_r)

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


    # Party start marker
    _draw_party_start_marker(renderer, data, screen, ox, oy, ts,
                             cam_c, cam_r, end_c, end_r)


def _draw_party_start_marker(renderer, data, screen, ox, oy, ts,
                              cam_c, cam_r, end_c, end_r):
    """Draw the party start position marker on the grid."""
    ps = data.get("party_start")
    if not ps:
        return
    pc, pr = ps.get("col", -1), ps.get("row", -1)
    if not (cam_c <= pc < end_c and cam_r <= pr < end_r):
        return
    px = ox + (pc - cam_c) * ts
    py = oy + (pr - cam_r) * ts

    # Draw the party map sprite if available, otherwise a white stick figure
    party_spr = getattr(renderer, '_party_map_sprite', None)
    if party_spr:
        scaled = pygame.transform.scale(party_spr, (ts, ts))
        screen.blit(scaled, (px, py))
    else:
        # Fallback: draw a simple white stick figure
        cx, cy = px + ts // 2, py + ts // 2
        r = max(ts // 6, 2)
        pygame.draw.circle(screen, (255, 255, 255), (cx, cy - r * 2), r)
        pygame.draw.line(screen, (255, 255, 255),
                         (cx, cy - r), (cx, cy + r), 1)
        pygame.draw.line(screen, (255, 255, 255),
                         (cx - r, cy), (cx + r, cy), 1)
        pygame.draw.line(screen, (255, 255, 255),
                         (cx, cy + r), (cx - r, cy + r * 2), 1)
        pygame.draw.line(screen, (255, 255, 255),
                         (cx, cy + r), (cx + r, cy + r * 2), 1)

    # Green border + "P" badge
    pygame.draw.rect(screen, (80, 255, 80), (px, py, ts, ts), 2)
    badge_sz = max(ts // 3, 8)
    bx = px + ts - badge_sz - 1
    by = py + 1
    pygame.draw.rect(screen, (20, 120, 20), (bx, by, badge_sz, badge_sz))
    if badge_sz >= 8:
        tiny = (renderer.font_tiny
                if hasattr(renderer, 'font_tiny')
                else renderer.font_small)
        psf = tiny.render("P", True, (255, 255, 255))
        screen.blit(psf, (bx + 1, by))


def _draw_minimap(renderer, data: Dict):
    """Draw a minimap in the bottom-right corner showing the full map
    with a viewport rectangle and cursor dot."""
    screen = renderer.screen
    tiles = data["tiles"]
    map_w, map_h = data["width"], data["height"]
    ts = data.get("tile_size", TILE_SIZE)

    # Minimap sizing: fit into a box in the bottom-right of the grid area
    max_mini_w = min(160, GRID_W // 3)
    max_mini_h = min(120, GRID_H // 3)
    scale = min(max_mini_w / max(map_w, 1), max_mini_h / max(map_h, 1))
    mini_w = max(int(map_w * scale), 20)
    mini_h = max(int(map_h * scale), 15)

    margin = 6
    mx = GRID_X + GRID_W - mini_w - margin
    my = GRID_Y + GRID_H - mini_h - margin

    # Semi-transparent background
    bg = pygame.Surface((mini_w + 4, mini_h + 4), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 180))
    screen.blit(bg, (mx - 2, my - 2))

    # Draw tile colours at 1-pixel-per-cell resolution, then scale up
    from src.settings import TILE_DEFS
    _MINI_COLOURS = {
        "grass": (60, 140, 40),
        "water": (40, 80, 180),
        "forest": (30, 90, 30),
        "mountain": (140, 120, 100),
        "sand": (200, 180, 120),
        "path": (160, 140, 100),
        "town": (200, 200, 60),
        "dungeon": (180, 60, 60),
        "bridge": (140, 100, 60),
    }
    mini_surf = pygame.Surface((map_w, map_h))
    mini_surf.fill((20, 20, 30))
    storage = data.get("storage")
    if storage == STORAGE_DENSE and isinstance(tiles, list):
        # Dense: tiles is a 2D array [row][col] = tile_id
        for r in range(map_h):
            row = tiles[r]
            for c in range(map_w):
                tid = row[c]
                tdef = TILE_DEFS.get(tid, {})
                tname = tdef.get("name", "").lower()
                colour = None
                for key, col in _MINI_COLOURS.items():
                    if key in tname:
                        colour = col
                        break
                if colour is None:
                    # Fallback: walkable = dark grey, unwalkable darker
                    colour = ((50, 50, 60) if tdef.get("walkable")
                              else (25, 25, 35))
                mini_surf.set_at((c, r), colour)
    elif isinstance(tiles, dict):
        # Sparse: tiles is {"c,r": {tile_id, ...}} — empty cells stay
        # at the background colour, painted cells take their tile's hue.
        for pos_key, td in tiles.items():
            parts = pos_key.split(",")
            if len(parts) != 2:
                continue
            try:
                c, r = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if not (0 <= c < map_w and 0 <= r < map_h):
                continue
            tid = td.get("tile_id") if isinstance(td, dict) else td
            tdef = TILE_DEFS.get(tid, {})
            tname = tdef.get("name", "").lower()
            colour = None
            for key, col in _MINI_COLOURS.items():
                if key in tname:
                    colour = col
                    break
            if colour is None:
                colour = ((50, 50, 60) if tdef.get("walkable")
                          else (25, 25, 35))
            mini_surf.set_at((c, r), colour)

    scaled = pygame.transform.scale(mini_surf, (mini_w, mini_h))
    screen.blit(scaled, (mx, my))

    # Draw viewport rectangle
    vis_cols = GRID_W // ts
    vis_rows = GRID_H // ts
    cam_c = data.get("cam_col", 0)
    cam_r = data.get("cam_row", 0)
    vx = mx + int(cam_c * scale)
    vy = my + int(cam_r * scale)
    vw = max(int(min(vis_cols, map_w) * scale), 2)
    vh = max(int(min(vis_rows, map_h) * scale), 2)
    pygame.draw.rect(screen, (255, 255, 255), (vx, vy, vw, vh), 1)

    # Cursor dot
    cur_c, cur_r = data["cursor_col"], data["cursor_row"]
    cx = mx + int((cur_c + 0.5) * scale)
    cy = my + int((cur_r + 0.5) * scale)
    pygame.draw.circle(screen, (255, 200, 60), (cx, cy), max(int(scale), 2))

    # Border
    pygame.draw.rect(screen, (100, 100, 120), (mx - 2, my - 2,
                                                 mini_w + 4, mini_h + 4), 1)


def _draw_sparse_grid(renderer, data: Dict):
    """Draw a sparse tile grid.

    When *grid_type* is ``"fixed"`` the whole map is shown centered in
    the grid area (interior / small-room style). When it is
    ``"scrollable"`` the grid is panned with ``cam_col``/``cam_row`` and
    only the tiles in the visible window are drawn — so large sparse
    maps (40×50 dungeons, 30×30 town interiors, etc.) can be edited at
    a comfortable tile size instead of being squished to fit.
    """
    screen = renderer.screen
    tiles = data["tiles"]
    tw, th = data["width"], data["height"]
    ts = data.get("tile_size", 24)
    scrollable = data.get("grid_type") == "scrollable"

    if scrollable:
        cam_c = data.get("cam_col", 0)
        cam_r = data.get("cam_row", 0)
        vis_cols = GRID_W // ts
        vis_rows = GRID_H // ts
        cam_c = max(0, min(cam_c, max(0, tw - vis_cols)))
        cam_r = max(0, min(cam_r, max(0, th - vis_rows)))
        total_w = min(tw, vis_cols) * ts
        total_h = min(th, vis_rows) * ts
        gx = GRID_X + (GRID_W - total_w) // 2
        gy = GRID_Y + (GRID_H - total_h) // 2
        start_c, start_r = cam_c, cam_r
        end_c = min(cam_c + vis_cols, tw)
        end_r = min(cam_r + vis_rows, th)
    else:
        cam_c = cam_r = 0
        total_w = tw * ts
        total_h = th * ts
        gx = GRID_X + (GRID_W - total_w) // 2
        gy = GRID_Y + (GRID_H - total_h) // 2
        start_c, start_r = 0, 0
        end_c, end_r = tw, th

    tprops_for_fx = data.get("tile_properties") or {}
    for r in range(start_r, end_r):
        for c in range(start_c, end_c):
            px = gx + (c - cam_c) * ts
            py = gy + (r - cam_r) * ts
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
                # Editor preview of animated tile effects.  The sparse
                # grid blits sprites directly (not via _draw_tile), so
                # we paint the overlay explicitly from the editor's
                # tile_properties dict.
                if tprops_for_fx:
                    renderer._draw_tile_effect_overlay(
                        px, py, ts, c, r,
                        tile_properties=tprops_for_fx)

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

    # Ground-item overlay for sparse grids (camera-aware)
    _draw_ground_items(renderer, data, gx, gy, ts,
                       cam_c, cam_r, end_c, end_r)

    # Encounter overlays (party-tile sprite per placed encounter)
    _draw_encounter_overlays(renderer, data, gx, gy, ts,
                             cam_c, cam_r, end_c, end_r)

    # Object stamp preview (ghost outline) — clipped to visible window
    brushes = data.get("brushes", [])
    bidx = data.get("brush_idx", 0)
    cur_brush = brushes[bidx] if bidx < len(brushes) else None
    cx, cy = data["cursor_col"], data["cursor_row"]
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
            tc = cx + (oc - min_c)
            tr = cy + (orow - min_r)
            if start_c <= tc < end_c and start_r <= tr < end_r:
                gpx = gx + (tc - cam_c) * ts
                gpy = gy + (tr - cam_r) * ts
                ghost_s = pygame.Surface((ts, ts), pygame.SRCALPHA)
                ghost_s.fill((120, 180, 220, pulse_a))
                screen.blit(ghost_s, (gpx, gpy))

    # Cursor — camera-aware
    if start_c <= cx < end_c and start_r <= cy < end_r:
        elapsed = pygame.time.get_ticks() / 1000.0
        pulse = int(80 + 40 * math.sin(elapsed * 4))
        cursor_rect = pygame.Rect(
            gx + (cx - cam_c) * ts,
            gy + (cy - cam_r) * ts,
            ts, ts)
        pygame.draw.rect(screen, (255, 200, pulse), cursor_rect, 2)


# ─── Overlays ─────────────────────────────────────────────────────────


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
    elif data.get("item_picker_active"):
        hint = ("[Arrows/PgUp/PgDn] Browse  [Enter] Place  "
                "[Backspace] Clear Item  [Esc] Cancel")
    elif data.get("inspector_editing"):
        hint = ("[Up/Dn] Field  [Type] Edit  "
                "[Enter] Save  [Esc] Cancel")
    elif data["storage"] == STORAGE_DENSE:
        hint = ("[Arrows] Move  [Shift+Arrows] Fast  "
                "[Wheel] Scroll  [Click] Paint  "
                "[Tab] Brush  [E] Edit Tile  [P] Party  "
                "[R] Replace  [Ctrl+S] Save  [Esc] Exit")
    else:
        hint = ("[Arrows/WASD] Move  [Enter] Paint  "
                "[R] Replace  [E] Edit Tile  "
                "[Tab] Brush  [Ctrl+S] Save  [Esc] Save & Exit")

    hw = fs.size(hint)[0]
    renderer._u3_text(hint,
                      SCREEN_WIDTH // 2 - hw // 2,
                      SCREEN_HEIGHT - FOOTER_H + 4,
                      _COL_HINT, fs)


def _get_encounter_party_tile(encounter_name: str):
    """Return the ``monster_party_tile`` sprite name for an encounter.

    Consults the runtime ``src.monster.ENCOUNTERS`` registry first (it
    is up-to-date because ``save_encounters`` calls ``reload_module_data``
    after every edit). Falls back to loading encounters.json on miss.
    Returns an empty string if the encounter isn't found anywhere —
    callers should fall back to the generic TILE_ENCOUNTER marker.
    """
    # Fast path: the live registry
    try:
        from src.monster import ENCOUNTERS as _ENC
        if isinstance(_ENC, dict):
            for bucket in _ENC.values():
                if not isinstance(bucket, list):
                    continue
                for entry in bucket:
                    if (isinstance(entry, dict)
                            and entry.get("name") == encounter_name):
                        return entry.get("monster_party_tile", "") or ""
    except Exception:
        pass
    # Fallback: read encounters.json directly (covers sessions where
    # the runtime registry wasn't loaded).
    try:
        import json as _json
        import os as _os
        path = _os.path.join(
            _os.path.dirname(_os.path.dirname(__file__)),
            "data", "encounters.json")
        with open(path, "r") as f:
            data = _json.load(f)
        buckets = data.get("encounters", {})
        if isinstance(buckets, dict):
            for bucket in buckets.values():
                if not isinstance(bucket, list):
                    continue
                for entry in bucket:
                    if (isinstance(entry, dict)
                            and entry.get("name") == encounter_name):
                        return entry.get("monster_party_tile", "") or ""
    except Exception:
        pass
    return ""


def _draw_encounter_overlays(renderer, data: Dict,
                              ox: int, oy: int, ts: int,
                              cam_c: int, cam_r: int,
                              end_c: int, end_r: int):
    """Overlay the party-tile sprite on every TILE_ENCOUNTER cell.

    The tile grid draws a generic encounter marker for TILE_ENCOUNTER.
    This pass walks ``tile_properties``, looks up each cell's encounter
    template name, resolves its ``monster_party_tile`` from the global
    ENCOUNTERS registry, and blits the correct monster sprite on top —
    so an Orc Band placement shows an Orc, Cellar Rats show a Giant
    Rat, etc.
    """
    tprops = data.get("tile_properties") or {}
    if not tprops:
        return
    for pos_key, props in tprops.items():
        if not isinstance(props, dict):
            continue
        enc_name = props.get("encounter")
        if not enc_name:
            continue
        parts = pos_key.split(",")
        if len(parts) != 2:
            continue
        try:
            c, r = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if not (cam_c <= c < end_c and cam_r <= r < end_r):
            continue
        px = ox + (c - cam_c) * ts
        py = oy + (r - cam_r) * ts
        party_tile = _get_encounter_party_tile(enc_name)
        # ``monster_party_tile`` in encounters.json is a monster NAME
        # (e.g. "Goblin", "Giant Rat"). Resolve it against the monster
        # registry first — that's the same cache the combat/overworld
        # renderers use for monster sprites. Fall back to the unique-
        # tile cache (covers hand-authored party graphics that aren't
        # a regular monster), then finally a purple-diamond marker.
        import pygame as _pg
        sprite = None
        if party_tile:
            try:
                sprite = renderer._get_monster_sprite_by_name(party_tile)
            except Exception:
                sprite = None
            if sprite is not None and sprite.get_size() != (ts, ts):
                # Monster sprites are cached at 32px; rescale to the
                # editor's current tile size.
                try:
                    sprite = _pg.transform.smoothscale(sprite, (ts, ts))
                except Exception:
                    sprite = _pg.transform.scale(sprite, (ts, ts))
            if sprite is None:
                try:
                    sprite = renderer._get_unique_tile_sprite(
                        party_tile, ts)
                except Exception:
                    sprite = None
        if sprite is not None:
            renderer.screen.blit(sprite, (px, py))
        else:
            # Soft fallback: a purple diamond so the placement is
            # still visually distinct from plain grass.
            diamond = _pg.Surface((ts, ts), _pg.SRCALPHA)
            cx, cy = ts // 2, ts // 2
            pts = [(cx, 2), (ts - 2, cy),
                   (cx, ts - 2), (2, cy)]
            _pg.draw.polygon(diamond, (180, 60, 140, 220), pts)
            _pg.draw.polygon(diamond, (230, 180, 230), pts, 2)
            renderer.screen.blit(diamond, (px, py))


def _draw_ground_items(renderer, data: Dict,
                        ox: int, oy: int, ts: int,
                        cam_c: int, cam_r: int,
                        end_c: int, end_r: int):
    """Overlay item icons on any tile with tile_properties[pos]["item"].

    Works for both dense and sparse grids by clamping to (cam_c..end_c,
    cam_r..end_r). Also flashes the item being painted under the cursor
    when the editor is in items mode.
    """
    tprops = data.get("tile_properties") or {}
    if not tprops:
        return
    # Scale icons to mostly fill the tile.
    icon_sz = max(8, int(ts * 0.9))

    for pos_key, props in tprops.items():
        if not isinstance(props, dict):
            continue
        item_name = props.get("item")
        if not item_name:
            continue
        parts = pos_key.split(",")
        if len(parts) != 2:
            continue
        try:
            c, r = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if not (cam_c <= c < end_c and cam_r <= r < end_r):
            continue
        px = ox + (c - cam_c) * ts
        py = oy + (r - cam_r) * ts
        _draw_item_on_tile(renderer, item_name, px, py, ts, icon_sz)


def _draw_item_on_tile(renderer, item_name: str,
                        px: int, py: int, tile_size: int,
                        icon_size: int):
    """Render a single item icon centered in the (px, py, ts, ts) tile.

    Uses the item's ``icon`` field from ITEM_INFO (the source of truth
    for display icons across every category — weapons, armors, general)
    with the per-item ``icon_color`` tint honored by _potion_tint. Falls
    back to a plain marker if the item is unknown.
    """
    try:
        from src.party import ITEM_INFO
    except Exception:
        ITEM_INFO = {}

    info = ITEM_INFO.get(item_name, {})
    icon_type = info.get("icon", "tool") if info else "tool"
    tint = None
    if hasattr(renderer, "_potion_tint"):
        try:
            tint = renderer._potion_tint(info)
        except Exception:
            tint = None
    cx = px + tile_size // 2
    cy = py + tile_size // 2
    # Soft dark rounded square behind the icon for legibility.
    bg = pygame.Surface((tile_size, tile_size), pygame.SRCALPHA)
    pygame.draw.rect(bg, (0, 0, 0, 90),
                     pygame.Rect(2, 2, tile_size - 4, tile_size - 4),
                     border_radius=4)
    renderer.screen.blit(bg, (px, py))
    try:
        renderer._draw_item_icon(cx, cy, icon_type, icon_size, tint=tint)
    except Exception:
        # Graceful fallback — draw a small "?" so the tile isn't empty.
        if hasattr(renderer, "_u3_text"):
            renderer._u3_text("?", cx - 4, cy - 6,
                              (240, 240, 240),
                              getattr(renderer, "font", None)
                              or getattr(renderer, "font_small", None))


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
