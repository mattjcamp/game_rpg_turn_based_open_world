# unique_tiles.json

## Purpose

A small catalog of "unique" landmark tiles (Moongate, Whispering Stones) that overlay a base terrain tile. Intended as a global fallback consulted when an individual module doesn't supply its own list. **Unused by the TypeScript implementation** — the TS port has no `loadUniqueTiles()` function and unique-tile placement on the overworld is not wired up. Modules carry their own embedded `unique_tiles` blocks (see `web/public/modules/*/module.json`), but those are also legacy-Python contracts and aren't consumed by `web/src/`.

## Location

`data/unique_tiles.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. Every field is currently `No`.

## File shape

```
{
  "_comment": "...",
  "unique_tiles": {
    "<slug>": { "name": ..., "description": ..., "base_tile": ... },
    ...
  }
}
```

`unique_tiles` is keyed by a slug (`moongate`, `whispering_stones`). The slug is the tile's identity.

## Fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `_comment` | string | Author note | No |
| `unique_tiles.<slug>.name` | string | Display label | No |
| `unique_tiles.<slug>.description` | string | Flavor text shown on examine | No |
| `unique_tiles.<slug>.base_tile` | string | Terrain key the unique tile is overlaid on (e.g. `"grass"`) | No |

## Cross-references to other JSON files

`base_tile` values are conceptually keys into `tile_defs.json` (matched by `sprite` name), but the TS code never performs this lookup. The richer list of unique-tile sprites (moongate, ruined tower, sunken shipwreck, lava vent, seal of binding, etc.) lives in `tile_manifest.json` under the `unique_tiles` bucket — only `seal_of_binding` has been promoted into `tile_defs.json` (ID 65) so it can actually appear on a map.

## Example record

```json
"moongate": {
  "name": "Moongate",
  "description": "A shimmering ring of blue light hovers above the ground...",
  "base_tile": "grass"
}
```

## Notes and open questions

Tiny and inert. If unique-tile placement is part of the next-version feature list, this file (or its module-embedded equivalents) is the obvious data source — but a real loader and renderer would need to be built first. If unique tiles are out of scope, this file can be deleted along with the matching `unique_tiles` blocks in module manifests.
