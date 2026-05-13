# town_templates.json

## Purpose

A palette of town-related authoring templates: full town layouts, individual town features, and named interiors. Currently only the `interiors` bucket is populated (4 entries: "Interior 2", "Shop", "Shop", "Town Hall"). **Unused by the TypeScript implementation.** Like `map_templates.json` and `reusable_features.json`, this is a Python town-editor palette; the web build never fetches it.

## Location

`data/town_templates.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. Every field is currently `No`.

## File shape

```
{
  "layouts":   [ ],           // empty
  "features":  [ ],           // empty
  "interiors": [ <interior>, ... ]
}
```

Three top-level array buckets. Only `interiors` is populated in current data. No `_comment` key.

## Top-level keys

| Key | Description | Used in web/? |
|---|---|---|
| `layouts` | Full town layout templates (reserved — empty in current data) | No |
| `features` | Town feature templates (reserved — empty in current data) | No |
| `interiors` | Named interior templates with parent-town authoring metadata | No |

## Interior record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Interior label (often duplicated — two `"Shop"` entries exist) | No |
| `width` | int | Grid width in cells (14 in current data) | No |
| `height` | int | Grid height in cells (15 in current data) | No |
| `tiles` | object | Sparse map of `"col,row"` → tile entry | No |
| `tiles["<c>,<r>"].tile_id` | int | Tile ID from `tile_defs.json` | No |
| `tiles["<c>,<r>"].path` | string | Asset path | No |
| `tiles["<c>,<r>"].name` | string | Human label | No |
| `parent_town` | string | Town name the interior was authored under | No |

## Cross-references to other JSON files

`tile_id` values point at rows in `tile_defs.json` (commonly 10 = town floor, 30 = machine, etc.).

`parent_town` values would conceptually key into a town definition's `name` (the runtime loads town definitions from `web/public/data/towns.json` via `Towns.ts:loadTowns`). The current parent-town values (`"Town Different"`, `"Yardley"`, `"Basic Town"`, `"Philly"`, `"Newtown"`) look like editor scratch towns — they don't correspond to any town in the active module.

## Example record

The smallest interior (`"Interior 2"`), abbreviated:

```json
{
  "name": "Interior 2",
  "width": 14,
  "height": 15,
  "tiles": {
    "0,0": { "tile_id": 10, "path": "game/terrain/town_floor.png", "name": "Floor" },
    "2,2": { "tile_id": 30, "path": "game/dungeon/machine.png",    "name": "Machine" }
    /* ... mostly floor (tile_id 10), a few machine tiles ... */
  },
  "parent_town": "Town Different"
}
```

## Notes and open questions

A few things worth noting:

The `layouts` and `features` arrays exist in the schema but are empty across the entire file. Either populate them (if these template types are still part of the authoring workflow) or remove them from the schema.

Two entries are both named `"Shop"` but with different `parent_town` values. Because the file isn't consumed by any runtime, this duplicate naming is harmless today, but it would matter if a loader started keying on `name`.

The `parent_town` values point at towns that don't exist in the active module — they're leftover authoring scratch data.

Net: same disposition as `map_templates.json` and `reusable_features.json` — kept for legacy Python tooling, not consulted by the playable game. If the active module's town-interior data is what the runtime actually uses (and it is, via `towns.json`), then this file is redundant and removable once the Python editors are retired.
