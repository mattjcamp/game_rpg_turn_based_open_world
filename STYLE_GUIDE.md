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

## Tile Sprite Reference (U3TilesE.gif)

Source file: `example_graphics/U3TilesE.gif` — a 256×80 pixel sprite sheet containing a 16×5 grid of 16×16 pixel tiles (80 tiles total). These are authentic Ultima III Amiga-style tiles for use as replacements for our procedurally drawn tiles.

### Row 0: Terrain & Overworld Tiles

| Pos | Name | Description |
|-----|------|-------------|
| R0 C0 | Water (Deep Ocean) | Blue horizontal wave lines on dark background. Used for seas and oceans on the overworld map. |
| R0 C1 | Grass / Plains | Sparse green dots on black. The basic open terrain tile for fields and meadows. |
| R0 C2 | Brush / Scrubland | Green cross-shaped vegetation on black. Transitional terrain between grass and forest. |
| R0 C3 | Forest | Dense green foliage clusters. Heavier tree cover, may slow movement. |
| R0 C4 | Mountains | Orange/brown chevron pattern representing peaks. Impassable or difficult terrain. |
| R0 C5 | Dungeon Entrance | Gray stone archway/doorway set against mountain terrain. Entry point to dungeon levels. |
| R0 C6 | Town / Village | White buildings with green surroundings and a red flag. Settlement that can be entered. |
| R0 C7 | Castle | White castle structure with blue base and flags. Major location such as Lord British's castle. |
| R0 C8 | Brick Wall | Red brick pattern. Interior wall tile used in towns and dungeons. |
| R0 C9 | Treasure Chest | Yellow/gold chest on black background. Lootable container found in dungeons and towns. |
| R0 C10 | Horse | Orange horse sprite. Mountable creature that increases overworld travel speed. |
| R0 C11 | Ship / Frigate | Sailing vessel with white sails and orange hull. Used for ocean travel. |
| R0 C12 | Whirlpool | Blue spiral pattern. Dangerous water hazard that can transport or damage the party. |
| R0 C13 | Island / Jungle | Green land mass with palm tree on blue water. Tropical terrain or small island. |
| R0 C14 | Moongate / Portal | Cyan vertical beams with white sparkle. Magical teleportation gate tied to moon phases. |
| R0 C15 | Pirate Ship / Ship Variant | Orange hull with white upper structure. Enemy vessel or alternate ship sprite. |

### Row 1: Characters & Monsters (Animation Frame 1)

| Pos | Name | Description |
|-----|------|-------------|
| R1 C0 | Fighter (Frame 1) | Character with orange hair, green pants. Standard melee warrior class. |
| R1 C1 | Thief (Frame 1) | Running pose with red legs. Agile rogue class specializing in traps and ranged attacks. |
| R1 C2 | Paladin (Frame 1) | White/orange armored figure. Holy warrior with both combat and priest magic. |
| R1 C3 | Wizard (Frame 1) | Blue-robed figure holding a staff. Primary spellcaster with sorcerer magic. |
| R1 C4 | Barbarian (Frame 1) | Green-clad figure with blue headgear. Strong melee fighter, no magic ability. |
| R1 C5 | Cleric (Frame 1) | Green figure carrying a cross/staff. Healer class with priest spells. |
| R1 C6 | Lark (Frame 1) | Figure with blue weapon and red pants. Hybrid class with some magical ability. |
| R1 C7 | Illusionist (Frame 1) | Magenta/purple-robed figure. Spellcaster class with both priest and sorcerer magic. |
| R1 C8 | Orc | Green-skinned humanoid creature with red eyes. Common enemy monster. |
| R1 C9 | Skeleton | Gray bone structure on black. Undead enemy found in dungeons. |
| R1 C10 | Pirate / Brigand | Red/orange figure with blue weapon. Human enemy encountered on land or sea. |
| R1 C11 | Balron / Demon | Red-winged creature with yellow flames. Powerful late-game enemy. |
| R1 C12 | Man-Thing / Treant | Yellow and green plant-like creature. Nature-based monster. |
| R1 C13 | Dragon | Green serpentine dragon shape. Powerful monster with breath attacks. |
| R1 C14 | Daemon | Red bat-winged creature. High-level demonic enemy. |
| R1 C15 | Town Gate / Portcullis | Gray grid with blue accents. Iron gate structure used at town and castle entrances. |

### Row 2: Effects, Terrain Variants & Font (Part 1)

| Pos | Name | Description |
|-----|------|-------------|
| R2 C0 | Lava / Fire Field | Yellow and red vertical stripes. Damaging terrain found in dungeons and volcanic areas. |
| R2 C1 | Poison / Flames | Red chaotic pattern. Hazardous terrain that poisons or damages the party. |
| R2 C2 | Night Sky / Stars | White diamond sparkles on blue. Starfield or magical effect background. |
| R2 C3 | Void / Empty (Black) | Solid black tile. Used for unexplored areas, void, or empty space. |
| R2 C4–C13 | Font: Letters A–I, U | Gray serif letters on black background. Part of the in-game text font. |
| R2 C14–C15 | Blank / Unused | Mostly black. Possibly unused tile slots or spacers. |

### Row 3: Font (Part 2) & Special Tiles

| Pos | Name | Description |
|-----|------|-------------|
| R3 C0–C9 | Font: Letters Y, L, D, M, O, P, U, R, S, T | Gray serif letters on black background. Continuation of the in-game text font. |
| R3 C10 | Font: Letter S (variant) | Gray stylized S, possibly a lightning or path symbol. |
| R3 C11 | Lightning / Z | Zigzag shape. Could be letter Z or a lightning bolt effect symbol. |
| R3 C12 | Moongate (Active) | Bright cyan circle with white star center. Active moongate or magical portal. |
| R3 C13 | Cursor / Sparkle | Small white four-point star on black. Selection cursor or magic effect particle. |
| R3 C14 | Shrine / Church | Gray stone building with orange cross on top. Healing or prayer location. |
| R3 C15 | NPC / Townsfolk | Person holding a weapon/tool. Generic NPC or town character sprite. |

### Row 4: Characters & Monsters (Animation Frame 2)

| Pos | Name | Description |
|-----|------|-------------|
| R4 C0–C7 | Class Sprites (Frame 2) | Alternate animation frames for Fighter, Thief, Paladin, Wizard, Barbarian, Cleric, Lark, Illusionist. Arms/legs in different positions for walk cycle. |
| R4 C8–C14 | Monster Sprites (Frame 2) | Alternate animation frames for Orc, Skeleton, Pirate, Balron, Man-Thing, Dragon, Daemon. |
| R4 C15 | Whirlpool (Frame 2) | Blue spiral variant. Alternate animation frame or secondary portal graphic. |

### Tile-to-Game Mapping

When integrating these sprites, the following mapping applies to our current tile system:

| Game Tile Constant | Sprite Sheet Position | Notes |
|--------------------|----------------------|-------|
| `TILE_WATER` | R0 C0 | Direct replacement for procedural water |
| `TILE_GRASS` | R0 C1 | Direct replacement for procedural grass |
| `TILE_FOREST` | R0 C3 | Direct replacement; R0 C2 (brush) available for light forest variant |
| `TILE_MOUNTAIN` | R0 C4 | Direct replacement for procedural mountains |
| `TILE_TOWN` | R0 C6 | Direct replacement for procedural town marker |
| `TILE_DUNGEON` | R0 C5 | Direct replacement for procedural dungeon entrance |
| `TILE_PATH` | — | No exact match; could use R0 C2 (brush) or keep procedural |
| `TILE_SAND` | — | No exact match; keep procedural |
| `TILE_BRIDGE` | — | No exact match; keep procedural |
| `TILE_WALL` / `TILE_DWALL` | R0 C8 | Red brick wall for interior/dungeon walls |
| `TILE_FLOOR` / `TILE_DFLOOR` | R2 C3 (void) or R0 C1 | Black void or grass depending on context |
| `TILE_CHEST` | R0 C9 | Direct replacement for treasure chest |
| `TILE_STAIRS` | — | No exact match; keep procedural |
| `TILE_TRAP` | — | No exact match; keep procedural (intentionally hidden) |
| `TILE_DOOR` | — | No exact match; keep procedural |

### Character Sprite Mapping

These sprites from `example_graphics/` are already loaded at runtime by the renderer:

| Class | Standalone Sprite File | Sheet Position (Frame 1 / Frame 2) |
|-------|----------------------|-------------------------------------|
| Fighter | `Ultima3_AMI_sprite_fighter.png` | R1 C0 / R4 C0 |
| Thief | `Ultima3_AMI_sprite_thief.png` | R1 C1 / R4 C1 |
| Cleric | `Ultima3_AMI_sprite_cleric.png` | R1 C5 / R4 C5 |
| Wizard | `Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png` | R1 C3 / R4 C3 |
| Barbarian | `Ultima3_AMI_sprite_barbarian.png` | R1 C4 / R4 C4 |
| Paladin | — | R1 C2 / R4 C2 |
| Lark | — | R1 C6 / R4 C6 |
| Illusionist | — (shares wizard sprite) | R1 C7 / R4 C7 |

### Monster Sprite Mapping

Monsters available in the tile sheet that could replace procedural monster sprites:

| Monster | Sheet Position (Frame 1 / Frame 2) |
|---------|-------------------------------------|
| Orc | R1 C8 / R4 C8 |
| Skeleton | R1 C9 / R4 C9 |
| Pirate / Brigand | R1 C10 / R4 C10 |
| Balron / Demon | R1 C11 / R4 C11 |
| Man-Thing / Treant | R1 C12 / R4 C12 |
| Dragon | R1 C13 / R4 C13 |
| Daemon | R1 C14 / R4 C14 |

### Additional Tiles Available for Future Use

| Sheet Position | Name | Potential Use |
|---------------|------|---------------|
| R0 C7 | Castle | Lord British's castle or major quest location |
| R0 C10 | Horse | Mount system for faster overworld travel |
| R0 C11 | Ship | Sea travel vehicle |
| R0 C12 | Whirlpool | Ocean hazard or dungeon teleporter |
| R0 C13 | Island / Jungle | New terrain type for tropical areas |
| R0 C14 | Moongate | Fast-travel portal system |
| R0 C15 | Pirate Ship | Enemy ship encounters at sea |
| R1 C15 | Town Gate | Town entrance tile |
| R2 C0 | Lava | Dungeon hazard terrain |
| R2 C1 | Poison Field | Dungeon hazard terrain |
| R2 C2 | Night Sky | Cutscene or special area background |
| R3 C12 | Moongate (Active) | Animated portal effect |
| R3 C13 | Cursor / Sparkle | Selection indicator or spell effect |
| R3 C14 | Shrine / Church | Healing location on the overworld |

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
