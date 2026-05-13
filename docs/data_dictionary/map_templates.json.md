# map_templates.json

## Purpose

A palette of 13 reusable map templates (General Shop Interior, Tunnel Short, Shrine, Shop Exterior, Rustic Town, Tunnel Long, Abandoned Building, Capital City, Inside House, Citadels 1–4). Each template is a sparse grid of rich tile entries plus metadata describing dimensions and authoring context. **Unused by the TypeScript implementation** — the file is a Python module-editor palette.

## Location

`data/map_templates.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. Every field is currently `No`.

The file is large (~15K lines) but the schema is small; the size comes from the per-tile sparse maps for each template.

## File shape

```
{
  "me_enclosure": [
    { ...template_record... },
    ...
  ]
}
```

One top-level key (`me_enclosure`) holding an array of template records. No `_comment` key.

## Template record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `label` | string | Display name (e.g. `"General Shop Interior"`) | No |
| `subtitle` | string | `"<width>x<height>"` mirroring `map_config` dims | No |
| `description` | string | Free-form text (often empty) | No |
| `canvas_type` | string | Always `"blank"` in current data | No |
| `map_config.storage` | string | Always `"sparse"` | No |
| `map_config.grid_type` | string | Always `"fixed"` | No |
| `map_config.tile_context` | string | `"dungeon"` or `"town"` — palette filter for the editor | No |
| `map_config.width` | int | Grid width in cells (16, 20, or 25) | No |
| `map_config.height` | int | Grid height in cells (14, 20, or 25) | No |
| `tiles` | object | Sparse map of `"col,row"` → tile entry | No |
| `tiles["<c>,<r>"].tile_id` | int | Tile ID from `tile_defs.json` | No |
| `tiles["<c>,<r>"].name` | string | Human label of the tile | No |
| `tiles["<c>,<r>"].path` | string | Asset path under `unassigned/` or `game/...` | No |
| `tiles["<c>,<r>"].to_overworld` | bool | Marks a door that exits to the overworld | No — appears only once (Capital City) and is not honored |

## Cross-references to other JSON files

`tile_id` values point at rows in `tile_defs.json` (commonly 49 = brown brick wall, 13 = town door, 25 = stairs down, 26 = dungeon door, 46 = path, 48 = brown floor, 51 = lighter bricks). No references to monsters, items, or spawn data.

The per-tile shape (`{tile_id, path, name}` keyed by `"col,row"`) is structurally identical to the dict form `web/src/game/world/Towns.ts:normalizeTownTiles` accepts. If a loader is ever added, only `tile_id` would actually flow through to the runtime.

## Example record

The smallest template (General Shop Interior), abbreviated:

```json
{
  "label": "General Shop Interior",
  "subtitle": "16x14",
  "description": "",
  "canvas_type": "blank",
  "map_config": {
    "storage": "sparse",
    "grid_type": "fixed",
    "tile_context": "dungeon",
    "width": 16,
    "height": 14
  },
  "tiles": {
    "0,0": { "tile_id": 49, "name": "Brown Brick Wall", "path": "unassigned/brick_wall_brown.png" },
    "7,4": { "tile_id": 13, "name": "Door",            "path": "game/terrain/town_door.png" },
    "8,1": { "tile_id": 25, "name": "Stairs Down",     "path": "game/dungeon/stairs_down.png" }
    /* ... sparse fill of walls, floors, counters ... */
  }
}
```

## Notes and open questions

Several things to flag:

The top-level key `me_enclosure` is opaque — it appears to be a leftover identifier from the Python editor's "module editor: enclosure" concept rather than a meaningful category.

`"Capital CIty"` (sic) is a misspelling in the data. Easy fix once a loader cares about it.

The `to_overworld: true` flag on Capital City's door (around line 7090) is the only behavioral per-tile field in the file, and it isn't honored by any TS code.

`canvas_type` and `map_config` carry only one value each across all 13 templates (`"blank"` and `"sparse"`/`"fixed"`). They're effectively schema placeholders that could be dropped if this file is ever consolidated.

Net: same disposition as `reusable_features.json` and `town_templates.json` — kept for legacy Python tooling, not consulted by the playable game. If module authoring stays Python-based for now, leave it alone; if module authoring moves to the web build, decide whether to consume this file or rebuild the equivalent in module manifests.
