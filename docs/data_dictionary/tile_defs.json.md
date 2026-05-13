# tile_defs.json

## Purpose

The canonical, runtime-loaded **tile catalog**. Every tile ID referenced in any map (overworld, town, dungeon, combat) resolves to a record here. For each tile this file specifies the display name, walkability, fallback color, sprite key, optional lighting/transparency flags, and optional interaction metadata (shop, sign, spawn).

This file is the single source of truth for tile identity in the TypeScript build. The other three tile-related files (`u4_tiles.json`, `tile_manifest.json`, `unique_tiles.json`) are unused.

## Location

`data/tile_defs.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "<tile_id>": { ...tile_record... },
  ...
}
```

A flat dictionary whose keys are **stringified integer tile IDs** (`"0"`, `"1"`, `"2"`, … up to `"78"`, sparsely populated). The integer is the tile's identity throughout the codebase. The loader is `Tiles.ts:244` (`loadTileDefs`) / `Tiles.ts:261` (`populateRuntimeDefs`).

## Tile record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Display name (e.g. `"Grass"`, `"Stone Floor"`) | Yes — `Tiles.ts:249`; `findArtifactTileId` matches on it (`Tiles.ts:358`) |
| `walkable` | bool | Whether the party can step on this tile | Yes — `Tiles.ts:250`, gates movement in scenes and `TileMap.walkable()` |
| `color` | [int, int, int] | RGB fallback rectangle color when no sprite renders | Yes — `Tiles.ts:251` |
| `context` | string | Editor-side bucket (`"overworld"`, `"town"`, `"dungeon"`, `"artifacts"`, `"spawns"`) | **Partial** — only `"artifacts"` is branched on (`Tiles.ts:357,373`); other values are stored but not queried at runtime |
| `sprite` | string | Logical sprite key (e.g. `"overworld/grass"`); resolved to `/assets/<key>.png` via `spriteUrlForKey()` at `Tiles.ts:227`. Empty string = render the fallback color instead | Yes |
| `flags` | object | Optional rendering / lighting flags; see below | Yes |
| `interaction_type` | string | Optional interaction discriminator (`"shop"`, `"sign"`, `"spawn"`) | Yes — `TileMap.ts:192,215` |
| `interaction_data` | string | Payload for the interaction (counter key, sign text, or spawn template ID) | Yes — `TileMap.ts:193,216` |

## `flags` sub-object

Present on tiles that emit light or interact with the lighting system. Consumed by `Lighting.ts:90-103`.

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `light_source` | bool | Tile emits light (torch, brazier, lava) | Yes — `Lighting.ts:90` |
| `light_radius` | number | Light source radius in tiles | Yes — `Lighting.ts:97` |
| `light_intensity` | number | Light source intensity | Yes — `Lighting.ts:97` |
| `feature_light` | bool | Tile is a "feature light" (door, altar, exit) emitting a smaller ambient light | Yes — `Lighting.ts:100` |
| `feature_radius` | number | Feature light radius | Yes — `Lighting.ts:103` |
| `feature_intensity` | number | Feature light intensity | Yes — `Lighting.ts:103` |
| `transparent` | bool | Light passes through this tile (water, windows) | Yes |

## Polymorphic discriminators

Two discriminators worth knowing about:

**`interaction_type`** drives behavior in `TileMap.shopAt()` and `TileMap.signAt()` (`TileMap.ts:192-217`):

| `interaction_type` | What `interaction_data` means | Handler |
|---|---|---|
| `"shop"` | Counter key into `counters.json` | Opens the shop UI for that counter |
| `"sign"` | Sign message string | Displays the sign text |
| `"spawn"` | Spawn template ID | Overworld trigger glyph (lair entrance) |

**`context: "artifacts"`** is the only `context` value the TS code branches on. `findArtifactTileId()` and `isArtifactTile()` (`Tiles.ts:353-374`) scan the catalog for these so dungeon quest-placement can show the correct artifact sprite per quest.

The spawn trigger IDs (66, 67, 68, 69, 71, 75) all have `context: "spawns"`, but the code identifies them via a hardcoded `TRIGGER_IDS` set in `Tiles.ts:377-382` rather than via the `context` string.

## Cross-references to other JSON files

This file is referenced from many places:

- `monsters.json`'s `tile` field is **not** a tile ID — it's a sprite path string and bypasses this file entirely.
- `spawn_points.json` keys (`"66"`, `"67"`, ...) are tile IDs that must match entries here.
- `interaction_data` for `interaction_type: "shop"` is a key into `counters.json` (e.g. `"general"`, `"weapon"`, `"healing"`).
- `tile_manifest.json` has a `tile_id` back-reference field on some entries; that file is otherwise unused.
- Hardcoded constants in `Tiles.ts:24-76` mirror these IDs as named exports (`TILE_GRASS = 0`, `TILE_TOWN_FLOOR = 10`, `TILE_BOAT = 64`, `TILE_FOREST_ARCHWAY_UP = 77`, ...).
- All map data — `map_templates.json`, `town_templates.json`, and live module town/dungeon files — uses these tile IDs as cell values.

## Example record

A light-emitting tile (Wall Torch, ID 34):

```json
"34": {
  "name": "Wall Torch",
  "walkable": false,
  "color": [160, 120, 40],
  "context": "dungeon",
  "sprite": "dungeon/wall_torch",
  "flags": {
    "light_source": true,
    "light_radius": 5.0,
    "light_intensity": 3.0
  }
}
```

## Notes and open questions

Sparse ID space — gaps at 15–19, 30–31, 40–42, etc. — suggests historical churn from the Python era. Renumbering would touch every map file, so leave it; just don't assume IDs are dense.

IDs 12, 57, 58, 59, 61 all share the `town/counter` sprite but differ by `interaction_data` (`general` / `weapon` / `armor` / `magic` / `healing`). That's how shop variety works.

Two `"Door"` entries (13 = town door, 26 = dungeon door) — duplicate display names, distinct IDs and contexts. `findArtifactTileId` matches by display name, so be careful about adding more name-duplicate tiles.

The `color` field for IDs 48–65 and 70–76 is the placeholder `[128, 128, 128]` — authors stopped filling it in once sprites became reliable. Fine in practice (the sprite is what renders) but worth noting if you ever rely on the fallback color.

`context` is mostly informational. Only the `"artifacts"` value is queried at runtime. If `context` is going to remain in the schema, consider documenting which values are "live" vs. "editor-only" so authors aren't surprised when changes don't take effect.

The TS port hardcodes specific tile IDs as named constants in `Tiles.ts:24-76`. Whenever you add or renumber a tile that needs special handling (boat, archway, spawn trigger, etc.), check whether a constant needs to move with it.
