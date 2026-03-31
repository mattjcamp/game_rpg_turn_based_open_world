# Linking & Lighting Systems Audit

## Part 1: The Linking System

### Current State — Three Separate Linking Mechanisms

The codebase has evolved three different ways to link tiles between maps, each with its own data format, key type, and lookup logic.

**1. Overworld `tile_links` (TileMap class, tile_map.py line 38)**

```python
self.tile_links = {}   # "col,row" -> {"interior": name, "type": "town"|"dungeon"|"building"}
```

- Keys are **strings** like `"10,14"`
- Values are dicts with `interior` (name), `type`, and optional `sub_interior`
- Looked up in `overworld.py _check_tile_event()` — the handler branches on `type` to decide what action screen to show
- Source: `overview_map.json` tile_links section

**2. Town `interior_links` (TownData class, town_generator.py)**

```python
self.interior_links = {}   # (col, row) -> interior_name_string
```

- Keys are **tuples** like `(5, 8)`
- Values are **bare strings** — just the interior name, no type or metadata
- Looked up in `town.py _check_tile_event()` — any match triggers `_enter_interior()`
- Source: tiles in `towns.json` that have an `"interior"` field

**3. Building interior tiles (buildings.json spaces)**

- Links are embedded directly in tile definitions: `{"tile_id": 26, "interior": "General Shop", "to_town": true, "to_overworld": true}`
- No separate dict — discovered by scanning the tile grid at load time
- Exit behavior is controlled by boolean flags (`to_town`, `to_overworld`) rather than typed links

### Why This Causes Problems

**Inconsistent key formats.** String `"col,row"` vs tuple `(col, row)` means every piece of code that touches links needs to know which format it's dealing with. Conversion bugs are silent — a missed string-to-tuple conversion just means the link isn't found.

**No common link schema.** Overworld links carry `type` and `sub_interior` but town links are bare name strings. This means town-to-interior transitions can't distinguish between a shop, a quest room, and a dungeon entrance without looking up the target definition separately.

**No back-link information.** When you enter an interior, the code has to *search* for a return tile by scanning for `to_town` flags or name matches:

```python
if source_name and td["interior"] == source_name:
    back_link_pos = (c, r)
```

If no match is found, the player can get stuck. There's no validation that bidirectional links exist.

**No map location metadata on the link.** When transitioning, the code has to separately track where the player came from using stashed state (`_stashed_overworld_tile_map`, `_interior_stack`). The link itself doesn't say "you came from overworld tile (10,14)" — that context lives in the stack frames.

**Interior stack complexity.** Both `overworld.py` and `town.py` maintain their own interior stacks with slightly different shapes, and the stack-unwinding logic (to prevent circular nesting) adds defensive code that wouldn't be needed if links were self-describing.

### Proposed Unified Link Structure

Your instinct is right — every linked tile should carry enough information to be self-describing. Here's a suggested universal format:

```python
# Every tile link, regardless of context, uses this shape:
{
    "target_map": "Aseroth",              # name of destination map/interior
    "target_type": "town",                # town | dungeon | building | interior | overworld
    "target_pos": [5, 8],                 # where to place party in destination (or null for auto)
    "source_map": "Overworld",            # name of THIS map (for return navigation)
    "source_pos": [10, 14],              # position of THIS link tile in source map
    "connecting_tile": [10, 15],          # adjacent tile the player walks onto to trigger
    "sub_interior": null                  # optional: specific room within building
}
```

**Key changes from current system:**

- **`source_map` + `source_pos`**: The link knows where it lives. When you arrive at a destination, you don't need a stack to remember where you came from — the link on the exit tile tells you.
- **`target_pos`**: No more BFS-searching for a walkable tile near an exit. The link says exactly where to spawn.
- **`connecting_tile`**: Your suggestion. This is the tile the player stands on to trigger the transition. This solves the problem where the trigger tile and the visual "door" tile are different, and gives the renderer a clear tile to highlight or animate.
- **Uniform `target_type`**: One field, same vocabulary everywhere. No more branching on string type in one place and boolean flags in another.
- **Stored as tuples (or 2-element arrays in JSON)**: Consistent key format everywhere.

**Storage would be a single dict on every TileMap:**

```python
class TileMap:
    def __init__(self, ...):
        # ... existing fields ...
        self.links = {}   # (col, row) -> LinkDef dict (as above)
```

All three current mechanisms (`tile_links`, `interior_links`, `to_town`/`to_overworld` flags) collapse into this one dict.

### Migration Path

1. Add a `links` dict to `TileMap` alongside the existing fields
2. Write a converter that reads the three current formats and produces unified links
3. Update `_check_tile_event()` in all three states to read from `self.tile_map.links`
4. Once stable, remove `tile_links`, `interior_links`, and the flag-scanning code
5. Update module loader and editors to write the new format

---

## Part 2: The Lighting System

### Current State — Three Independent Implementations

The lighting system has three contexts that each handle things differently:

**1. Dungeon Lighting (dungeon.py + renderer.py)**

- **Fog of war**: Full recursive shadowcasting from party position
- **Torch system**: Equipped torches burn down per step; affect LOS radius
- **Wall torches**: Pre-computed illumination map (`_get_torch_lit_map()`), shadowcast at radius 4, only activate when within party's LOS
- **Rendering**: Warm orange glow overlay (255,160,50) with sin-based flicker, then fog-of-war SRCALPHA overlay on top
- **Explored tiles**: Persistent set tracks what's been seen; unseen = black, seen-but-not-visible = dim blue-gray

**2. Overworld Lighting (renderer.py `_draw_overworld_darkness`)**

- **No fog of war** — all tiles always visible
- **Time-based phases**: night (alpha 255, black), dusk (alpha 100, purple tint), dawn (alpha 80, orange tint)
- **Light sources**: Party (radius 1.0, +3.0 with torch), wall torches (5.0), doors (2.5), altars (3.0), exits (2.0)
- **Rendering**: Per-tile distance-to-nearest-light calculation → alpha gradient

**3. Town Lighting (renderer.py `draw_town_u3` + town.py)**

- **No fog of war** — all tiles always visible
- **Darkness triggers**: Nighttime, Keys of Shadow curse, Gnome Machine quest, or interior detection
- **Interior auto-detection**: If any `TILE_WALL_TORCH` is found in viewport, `interior_darkness = True`
- **Rendering**: Calls the same `_draw_overworld_darkness()` with `force_night=True` for interiors
- **No warm glow**: Unlike dungeons, town torches don't get the orange flickering glow overlay

### Inconsistencies Found

| Issue | Dungeon | Overworld | Town |
|-------|---------|-----------|------|
| **Fog of war** | Full shadowcasting + explored set | None | None |
| **Torch radius** | 4 tiles (shadowcast) | 5.0 tiles (distance) | 5.0 tiles (distance) |
| **Torch activation** | Requires LOS to party | Always active | Always active |
| **Warm glow visual** | Yes (orange flicker) | No | No |
| **Interior detection** | Explicit (always dark) | Flag from state | Auto-detect via torch presence |
| **Light source scan** | Pre-computed per level | Per-frame viewport scan | Per-frame viewport scan |

**The biggest inconsistency**: Dungeons have a rich, atmospheric lighting model (shadowcasting + torch glow + explored map), but when you enter a dark building interior in a town, you just get the flat distance-based overlay with no glow effects. This makes town interiors feel less polished than dungeons even though they're conceptually similar spaces.

**The auto-detection hack**: Town interiors are detected by checking whether wall torches exist in the viewport (line 661-665 of renderer.py). This is fragile — a town building without wall torches won't get darkness, and a building whose torches are just off-screen might flicker between lit and dark as the camera moves.

**Duplicate darkness algorithms**: The overworld and town share `_draw_overworld_darkness()`, but dungeons have their own separate fog system (`_u3_dungeon_fog`). The distance calculations, alpha curves, and tint colors are all defined independently in each path.

### Proposed Unified Lighting Architecture

A single lighting pipeline that every map context feeds into:

```
┌─────────────────────────────────────────────────────┐
│                  LightingContext                      │
│                                                       │
│  visibility_mode:  "full" | "fog_of_war"             │
│  ambient_level:    0.0 (pitch black) → 1.0 (full)   │
│  ambient_tint:     (r, g, b)                         │
│  light_sources:    [(col, row, radius, fade, color)] │
│  party_light:      radius (0 = no torch)             │
│  explored_tiles:   set | None                        │
│  use_shadowcast:   bool                              │
│  use_glow_fx:      bool                              │
└─────────────────────────────────────────────────────┘
```

Each map state creates a `LightingContext` and passes it to a single `render_lighting()` function:

- **Dungeon**: `visibility_mode="fog_of_war"`, `ambient_level=0.0`, `use_shadowcast=True`, `use_glow_fx=True`, `explored_tiles=dungeon_data.explored_tiles`
- **Overworld night**: `visibility_mode="full"`, `ambient_level=0.0`, `ambient_tint=(0,0,0)`, `use_shadowcast=False`, `use_glow_fx=False`
- **Overworld dusk**: `visibility_mode="full"`, `ambient_level=0.6`, `ambient_tint=(20,10,40)`
- **Town interior**: `visibility_mode="full"`, `ambient_level=0.0`, `use_shadowcast=False`, `use_glow_fx=True` — now interiors get the warm torch glow too
- **Town night outdoors**: `visibility_mode="full"`, `ambient_level=0.0`, `ambient_tint=(0,0,0)`, `use_glow_fx=False`

The renderer calls one function: `render_lighting(screen, tile_map, party_pos, lighting_ctx)`. That function handles fog of war, darkness overlay, glow effects, and infravision/Galadriel tints in a single pass.

### What This Fixes

- **Consistent torch behavior**: Same radius and glow style everywhere
- **No auto-detection hack**: The map state explicitly sets `ambient_level=0.0` for interiors rather than inferring it from torch presence
- **Glow effects in town interiors**: They'd get the same warm orange flicker as dungeons
- **Single code path**: One distance calculation, one alpha curve, one rendering pipeline — fewer places for bugs to hide
- **Easy to extend**: Adding a new lighting scenario (cave, underwater, magical darkness) is just a new `LightingContext` configuration, not a new rendering branch

---

## Part 3: Quick Wins vs. Larger Refactors

### Quick Wins (low risk, high clarity)

1. **Standardize link key format** — Convert all `"col,row"` string keys to `(col, row)` tuples at load time. This is a find-and-replace in the loader with a small adapter function.

2. **Add `source_pos` to links** — When building link dicts, include the source position. This eliminates the stack-search for back-links.

3. **Add warm glow to town interiors** — Port the dungeon torch glow rendering (renderer.py lines 3257-3286) into the town interior path. Immediate visual improvement.

4. **Replace torch auto-detection** — Add an `interior_darkness` flag to interior definitions in `buildings.json` / `towns.json` rather than inferring it from torch tile presence.

### Larger Refactors (higher payoff, more testing needed)

5. **Unified link schema** — Implement the universal link dict described above. Requires updating module loader, all three state files, editors, and save/load.

6. **LightingContext abstraction** — Extract lighting into its own module with the context-based API. Requires touching renderer.py heavily but makes the code significantly more testable.

7. **Bidirectional link validation** — Add a validation pass in the module loader that checks every link has a corresponding return link, warning at load time rather than trapping the player at runtime.

8. **Connecting tile support** — Your idea of a connecting tile on each link. This would need editor support to designate the "approach tile" and a small rendering hook to highlight it.
