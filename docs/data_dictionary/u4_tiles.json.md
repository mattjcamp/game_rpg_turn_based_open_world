# u4_tiles.json

## Purpose

A description of the original Ultima IV 16×16 sprite atlas (`U4TilesV.gif`) — file names, display names, and category labels for each of the 256 grid positions. **Unused by the TypeScript implementation.** The atlas has been atomised into individual PNGs that the web build serves directly from `web/public/assets/`, and tile identity in the runtime comes from `tile_defs.json`, not from this file's `"col,row"` keys.

## Location

`data/u4_tiles.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. Every field is currently `No`. The file lives on for legacy Python tooling (`src/renderer.py`, atlas exporters, manual generators).

## File shape

Top-level object with atlas-wide metadata plus a `tiles` map keyed by `"col,row"` grid coordinates (`"0,0"` through `"15,15"`).

```
{
  "_comment": "...",
  "source": "...",
  "tile_size": 16,
  "grid": "16x16",
  "total_tiles": 256,
  "tiles": { "<col,row>": { ...tile_record... }, ... }
}
```

## Top-level fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `_comment` | string | Author note | No |
| `source` | string | Path to the source GIF | No |
| `tile_size` | int | Pixel size of each tile (16) | No |
| `grid` | string | Atlas grid dimensions (`"16x16"`) | No |
| `total_tiles` | int | Number of tile slots (256) | No |
| `tiles` | object | Map of `"col,row"` → tile record | No |

## Tile record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `file` | string | Filename of the extracted PNG (e.g. `"deep_water.png"`) | No |
| `name` | string | Human-readable label (e.g. `"Deep Water"`, `"Balron (F1)"`) | No |
| `category` | string | One of `terrain`, `structure`, `vehicle`, `dungeon`, `npc`, `player`, `monster`, `celestial`, `effect`, `item`, `font`, `misc`, `hazard` | No |

## Cross-references to other JSON files

None active. The `file` values correspond to individual PNGs under `web/public/assets/`, but the TS sprite-loading path doesn't go through this index. Categories like `font` and `celestial` describe glyphs that were never ported to the TS build.

## Example record

```json
"0,0": {
  "file": "deep_water.png",
  "name": "Deep Water",
  "category": "terrain"
}
```

## Notes and open questions

This file is documentation of the upstream Ultima IV asset set, not runtime data. It's safe to leave in place for tooling purposes but nothing in the playable game depends on it. If the Python tooling that uses it is also being retired, this file can go with it.
