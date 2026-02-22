# Ultima III Visual Style Guide

Reference images analyzed: `example_combat.webp`, `example_combat_2.png`, `example_dungeon.jpg`, `example_overview_map.png`

This document captures the visual rules derived from those screenshots so they don't need to be re-examined. Use this when reskinning any screen (overworld, town, dungeon, menus, etc.) to match the Ultima III aesthetic.

---

## Screen Layout

Every screen in Ultima III follows the same split-panel structure:

```
┌──────────────────────┬──────────────────┐
│                      │  Character 1     │
│                      │  stats block     │
│                      ├──────────────────┤
│   TILE MAP           │  Character 2     │
│   (~60% width)       │  stats block     │
│                      ├──────────────────┤
│                      │  Character 3     │
│                      │  stats block     │
│                      ├──────────────────┤
│                      │  Character 4     │
│                      │  stats block     │
├──────────────────────┼──────────────────┤
│  STATUS BAR          │  MESSAGE LOG     │
│  (wind, location)    │  (scrolling)     │
└──────────────────────┴──────────────────┘
```

- The **tile map** occupies the left ~60% of the screen, full height minus a thin status bar at the bottom.
- The **right panel** (~40% width) is divided into stacked sections, each with its own blue border.
- A **status bar** runs along the bottom of the map area (shows wind direction, location info, or control hints).
- All sections are separated by bright blue border lines (2px thick).

For our 800x600 screen, the approximate pixel layout is:
- Map panel: x=4, y=4, width=480, height=320 (15 tiles x 10 tiles at 32px)
- Right panel: x=492, width=304
- Status bar: full width, height=24, at the bottom

---

## Color Palette

These are the core colors used throughout every Ultima III screen. They approximate the C64/Apple II palette.

| Name       | RGB             | Hex       | Usage                                        |
|------------|-----------------|-----------|----------------------------------------------|
| Black      | (0, 0, 0)      | `#000000` | Background everywhere — screen, panels, tiles |
| Blue       | (68, 68, 255)   | `#4444FF` | Borders, frames, unselected menu text, hints  |
| White      | (255, 255, 255) | `#FFFFFF` | Primary text, player sprites, selected items  |
| Orange     | (255, 170, 85)  | `#FFAA55` | Character names, highlights, critical hits    |
| Green      | (0, 170, 0)     | `#00AA00` | Grass/floor dots, victory text, rewards       |
| Dark Green | (0, 102, 0)     | `#006600` | Secondary grass dots, darker vegetation       |
| Red        | (200, 60, 60)   | `#C83C3C` | Monster names, damage text, defeat, HP bars   |
| Gray       | (136, 136, 136) | `#888888` | Dimmed/disabled text, miss messages, stats     |
| Brick 1    | (102, 51, 85)   | `#663355` | Wall brick face color (lighter)               |
| Brick 2    | (68, 34, 68)    | `#442244` | Wall brick outline/mortar color (darker)      |

**Rule**: The background is ALWAYS pure black `(0,0,0)`. Never use dark gray or dark blue as a background — it must be true black to match the CRT look.

---

## Borders and Panels

- Every discrete UI section (stat block, log, menu, map frame) gets a **2px bright blue border** drawn as a rectangle outline.
- The interior of each panel is filled with **pure black** before drawing content.
- There is no padding gradient, drop shadow, or rounded corners — just hard rectangular blue lines on black.
- Adjacent panels can share a border edge (no gap needed between them).

```python
# Standard panel drawing pattern:
def draw_panel(screen, x, y, w, h):
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(screen, (0, 0, 0), rect)          # black fill
    pygame.draw.rect(screen, (68, 68, 255), rect, 2)    # blue border
```

---

## Text Style

- **All text is UPPERCASE.** Every string rendered on screen should be `.upper()`'d before drawing.
- Use a **monospace font** (we use `pygame.font.SysFont("monospace", ...)`).
- Two sizes: 16px for headers/names, 12px for stats/log lines.
- No anti-aliasing trickery — just sharp monospace on black.

### Text color rules:
| Context                     | Color  |
|-----------------------------|--------|
| Character/player names      | Orange |
| Monster names               | Red    |
| Class names, hints, labels  | Blue   |
| Stats, HP, AC numbers       | White  |
| Weapon/damage details       | Gray   |
| Selected menu item          | White  |
| Unselected menu item        | Blue   |
| Disabled/grayed menu item   | Gray   |
| Combat hit messages         | White  |
| Combat miss messages        | Gray   |
| Critical hit messages       | Orange |
| Damage dealt messages       | Red    |
| Victory/reward messages     | Green  |
| Defeat messages             | Red    |
| General info/initiative     | Blue   |

---

## Stat Display Format

Character stats are shown in a compact, retro numeric format with zero-padded numbers:

```
ROLAND          FIGHTER
HP:0030/0030  AC:12
STR:16  DEX:12  INT:08
LVL:01  EXP:0000
WPN: LONG SWORD
ATK: D20+3  DMG: 1D8+3
```

Monster stats follow the same pattern:

```
GIANT RAT
HP:0008/0008  AC:12
ATK:+02  DMG:1D4+0
[========     ]   ← HP bar
```

HP bars use a blue border outline with a red fill. The fill is darker red `(170,0,0)` normally and switches to brighter red `(200,60,60)` when HP drops below 30%.

---

## Tile Rendering

### Floor Tiles (arena, overworld grass, dungeon floor)
- Base: pure **black** rectangle.
- Decoration: scattered small green **crosses** (+ shape, 5px wide) and **dots** (2x2px squares) placed at deterministic pseudo-random positions.
- Use the tile's grid coordinates as a seed: `seed = col * 31 + row * 17`. This ensures the pattern is consistent frame-to-frame without storing a map.
- Roughly 30-40% of floor tiles get a green cross; ~20% get an additional green dot.
- Alternate between bright green `(0,170,0)` and dark green `(0,102,0)` for variety.

### Wall Tiles (arena perimeter, dungeon walls, town walls)
- Base: dark purple `(68, 34, 68)` fill.
- Brick pattern: rows of small rectangles (10x6px) in lighter purple `(102, 51, 85)` with 1px darker outlines.
- Alternate rows are offset by 5px to create a staggered brick look.
- Row spacing: 8px vertical. Brick spacing: 12px horizontal.

### Water (overworld)
- Dark blue base, could add subtle wave dots in lighter blue.

### Special Tiles (chests, traps, stairs, doors, exits)
- Keep existing detail drawings but ensure they sit on a black background tile, not a colored one.

---

## Sprite Style

Sprites are **simple stick figures** made from basic shapes — circles, lines, and small rectangles. They should look like they could exist on an 8-bit system. No smooth gradients or anti-aliased edges.

### Player Sprite (white)
- **Head**: solid white circle, radius 4px
- **Body**: vertical white line, 2px thick, ~9px long
- **Arms**: horizontal white line, 2px thick, ~12px wide
- **Legs**: two diagonal white lines splaying outward, 2px thick
- **Sword**: blue-tinted `(120,120,255)` vertical line in right hand
- **Shield**: blue-tinted `(120,120,255)` small 4x7px rectangle on left

Total size: fits within a 32x32 tile with a few pixels of padding.

### Monster Sprite (colored)
- **Body**: solid colored rectangle, 16x14px, using the monster's `color` attribute
- **Head**: solid colored rectangle above body, 10x7px
- **Eyes**: two 3x3 white squares with 1x1 red pupils (always white+red regardless of body color)
- **Arms/claws**: two diagonal colored lines extending outward from the body
- **Legs**: two diagonal colored lines extending downward

The monster's body color comes from the `Monster.color` attribute:
- Giant Rat: `(140, 100, 80)` — brown
- Skeleton: `(220, 220, 200)` — bone white
- Orc: `(80, 140, 60)` — green

### NPC Sprites
- Similar stick-figure style to the player but in the NPC's type color.
- Name tags above in white on a black background rectangle.

---

## Menu / Action Selection

- The selected item has a `> ` prefix (the `>` character in white or orange).
- Selected items are rendered in **white**.
- Unselected items are rendered in **blue**.
- Disabled items are rendered in **gray** with a parenthetical explanation like `(CLOSER!)`.
- No highlight bars or background rectangles behind selected items — just the `>` prefix and color change.

---

## Combat Log

- Shown in a blue-bordered panel.
- Each line is rendered in the appropriate color from the text color rules above.
- Lines scroll upward as new entries are added (show the last N lines that fit).
- Line height: 15px. Font: small monospace (12px).
- All text is uppercase.

---

## Status Bar

- A thin (24px tall) blue-bordered panel spanning the full screen width at the bottom.
- Contains control hints or status info in **blue** text.
- Examples: `[WASD] MOVE   [UP/DN] MENU   [ENTER] ACT   [SPACE] SPEED`
- In the overworld, could show wind direction (like "NORTH WIND" in the originals).

---

## Summary of Key Rules

1. **Black background everywhere** — never dark gray, never dark blue.
2. **Blue borders on everything** — every panel, every section, 2px thick, `(68,68,255)`.
3. **All text uppercase** — `.upper()` every string before rendering.
4. **Monospace font only** — no proportional fonts.
5. **Simple stick-figure sprites** — white for player, colored for monsters/NPCs.
6. **Green dots on black for floors** — the signature Ultima III ground texture.
7. **Purple brick pattern for walls** — staggered rows of small colored rectangles.
8. **Left map / right stats layout** — the map always takes the left ~60%, stats panels on the right.
9. **Zero-padded numbers** — `HP:0030/0030` not `HP:30/30`.
10. **Orange for names, white for data, blue for labels, gray for disabled.**
