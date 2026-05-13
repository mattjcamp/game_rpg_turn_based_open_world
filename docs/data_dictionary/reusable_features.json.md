# reusable_features.json

## Purpose

A palette of reusable map features (currently a single "Shop Facade" template) bucketed by terrain context — town, dungeon, overworld. Each feature is a sparse `"col,row"` map of tile entries describing a small reusable layout. **Unused by the TypeScript implementation.** The file is a Python feature-editor palette; the web build never fetches it.

## Location

`data/reusable_features.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. Every field is currently `No`.

## File shape

```
{
  "town":      [ <feature>, ... ],
  "dungeon":   [ ],
  "overworld": [ ]
}
```

Three bucket arrays keyed by terrain context. Only `town` is populated (one entry, "Shop Facade"). No `_comment` key.

## Feature record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Template label (e.g. `"Shop Facade"`) | No |
| `width` | int | Template width in cells | No |
| `height` | int | Template height in cells | No |
| `tiles` | object | Sparse map of `"col,row"` → tile entry | No |
| `tiles["<c>,<r>"].tile_id` | int | Tile ID from `tile_defs.json` | No |
| `tiles["<c>,<r>"].path` | string | Asset path under `unassigned/` or `game/...` | No |
| `tiles["<c>,<r>"].name` | string | Human label of the tile | No |

## Cross-references to other JSON files

`tile_id` values point at rows in `tile_defs.json` (e.g. 37 = brick wall, 13 = town door). `path` values mirror the legacy Python asset layout (`unassigned/...`, `game/terrain/...`). Neither is consulted by the web build.

## Example record

```json
{
  "name": "Shop Facade",
  "width": 8,
  "height": 8,
  "tiles": {
    "0,0": { "tile_id": 37, "path": "unassigned/brick_wall_red.png", "name": "Brick" },
    "1,1": { "tile_id": 13, "path": "game/terrain/town_door.png", "name": "Door" }
  }
}
```

## Notes and open questions

Tiny file. Its tile-entry shape is structurally compatible with what `Towns.ts:normalizeTownTiles` accepts, so a future loader could promote these templates into runtime data — but doing so would require deciding what "instantiate a feature at this location" even means in the web build (paste at offset? overlay? stamp?). Until that design exists, this is a deletion candidate alongside the Python editors that populate it.
