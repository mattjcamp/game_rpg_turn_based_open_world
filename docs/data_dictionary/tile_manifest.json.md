# tile_manifest.json

## Purpose

A "graphics single source of truth" (per its own `_comment`) — a denormalized catalog of every sprite available to the editor, grouped by category (overworld, town, dungeon, people, monsters, unique_tiles, objects, items, unassigned). For each sprite it records the asset path, which editor buckets the sprite is offered in (`usable_in`), and an optional back-reference to a tile ID in `tile_defs.json`. **Unused by the TypeScript implementation.** The runtime gets all of this information from `tile_defs.json` directly.

## Location

`data/tile_manifest.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. Every field is currently `No`. The file was the spine of the Python feature/town editors; the web port reaches sprites by way of `tile_defs.json[id].sprite` and bypasses this index entirely.

## File shape

```
{
  "_comment": "...",
  "_version": 2,
  "overworld":     { "<key>": { "path": ..., "usable_in": [...], "tile_id"?: <int> }, ... },
  "town":          { ... },
  "dungeon":       { ... },
  "people":        { ... },
  "monsters":      { ... },
  "unique_tiles":  { ... },
  "objects":       { ... },
  "unassigned":    { ... },
  "items":         { ... }
}
```

Each bucket is an object keyed by sprite slug. The top-level bucket name is the editor category.

## Top-level keys

| Key | Description |
|---|---|
| `_comment` | Manifest preamble |
| `_version` | Schema version (currently `2`) |
| `overworld` | World-map sprite catalog |
| `town` | Town interior/exterior sprite catalog |
| `dungeon` | Dungeon sprite catalog |
| `people` | NPC and character sprite catalog (~70 entries) |
| `monsters` | Monster sprite catalog (~50 entries) |
| `unique_tiles` | Landmark sprites (moongate, ruined tower, seal of binding, etc.) |
| `objects` | Object sprite catalog (decorations, containers) |
| `unassigned` | Sprite slugs awaiting categorization or stale duplicates (`_copy.png`, animation frames `_f1/_f2` never wired) |
| `items` | Item sprite catalog |

## Sprite record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `path` | string | Repo-relative PNG path (e.g. `"src/assets/game/terrain/grass.png"`) | No |
| `usable_in` | string[] | Which editor buckets the sprite is offered in | No |
| `tile_id` | int (optional) | Back-reference to a tile ID in `tile_defs.json`; present on ~30 of ~250 entries | No |

## Cross-references to other JSON files

The `tile_id` field, where present, points at a row in `tile_defs.json`. Example: `tile_manifest.unique_tiles.seal_of_binding` declares `tile_id: 65`, which corresponds to `tile_defs["65"]` (name `"Seal of Binding"`, sprite key `"unique_tiles/seal_of_binding"`, context `"artifacts"`).

The `path` values still follow the legacy Python layout (`src/assets/...`) — they have not been re-pointed at the web build's `web/public/assets/...` directory.

## Example record

```json
"overworld": {
  "grass": {
    "path": "src/assets/game/terrain/grass.png",
    "usable_in": ["overworld", "town"],
    "tile_id": 0
  }
}
```

## Notes and open questions

This file overlaps heavily with `tile_defs.json` (which is the live source of truth) and with the on-disk `web/public/assets/` tree (which is the live sprite store). Three issues to flag:

The `path` values point at `src/assets/...`, not `web/public/assets/...`. If anything ever does start consuming this file, those paths will need to be rewritten or normalized at load.

Many entries in the `unassigned` bucket are stale — `_copy` duplicates and `_f1` / `_f2` frame variants for animations that were never implemented. A cleanup pass would shrink this file substantially.

The `tile_id` back-reference is partial (~30 of ~250 entries). If this file is going to be revived, the back-references should be filled in completely so it's actually authoritative; if it isn't, the field is misleading.

Net: same disposition as `u4_tiles.json` and `unique_tiles.json` — kept for legacy tooling, not consulted by the playable game. Delete it together with the Python editors, or rebuild it as a proper bidirectional index against `tile_defs.json`.
