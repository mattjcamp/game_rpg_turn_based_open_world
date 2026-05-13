# spawn_points.json

## Purpose

Defines monster lair behavior keyed by tile ID — when the party steps on or near a "spawn point" tile (e.g. tile 66 = Monster Spawn, 69 = Dragon, 75 = Man Eater), this file determines which monsters roam nearby, how often, and what fight is triggered when the party finally steps on the tile itself.

## Location

`data/spawn_points.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "_comment": "...",
  "spawn_points": {
    "<tile_id>": { ...spawn_record... },
    ...
  }
}
```

`spawn_points` is keyed by **stringified tile ID** (e.g. `"66"`, `"67"`, `"68"`, `"69"`, `"71"`, `"75"`). The loader (`SpawnPoints.ts:75-84`) parses these strings back to integers at load time.

## Top-level fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `_comment` | string | Author note | No |
| `spawn_points` | object | Tile-ID-keyed map of spawn records | Yes |

## Spawn record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Display name for the "Approach Lair?" prompt | Yes — `SpawnPoints.ts:99` |
| `description` | string | Flavor text shown when approaching | Yes — `SpawnPoints.ts:100` |
| `spawn_monsters` | string[] | Roster the per-step roller picks from (uniform random) — cross-refs `monsters.json` | Yes — `SpawnPoints.ts:101,198` |
| `spawn_chance` | int (1–100, default 20) | Per-step percent chance to spawn a roamer | Yes — `SpawnPoints.ts:102,173` |
| `spawn_radius` | int (default 3) | Chebyshev tile radius for the saturation check | Yes — `SpawnPoints.ts:103,176-183` |
| `max_spawned` | int (default 2) | Cap on simultaneous roamers around the tile | Yes — `SpawnPoints.ts:104,184` |
| `boss_monsters` | string[] | Monsters composing the boss fight triggered when stepping on the tile itself — cross-refs `monsters.json` | Yes — `SpawnPoints.ts:105` |
| `boss_monster` | string | Legacy singular form of `boss_monsters`; used as a fallback when `boss_monsters` is empty or missing | Partial — `SpawnPoints.ts:95-97` |
| `xp_reward` | int (default 50) | XP awarded for clearing the lair | Yes — `SpawnPoints.ts:106` |
| `gold_reward` | int (default 25) | Gold awarded for clearing the lair | Yes — `SpawnPoints.ts:107` |
| `loot` | string[] | Item names dropped on clear — cross-refs `items.json` | Yes — `SpawnPoints.ts:108` |
| `background_tile` | int | Tile ID revealed when the lair is cleared | **No** — `RawSpawnPoint` doesn't include this and the parser ignores it |

## Cross-references to other JSON files

Object keys (`"66"`, `"67"`, ...) → tile IDs defined in `tile_defs.json`.

`spawn_monsters[]`, `boss_monster`, and `boss_monsters[]` → monster names defined in `monsters.json`.

`loot[]` → item names defined in `items.json` (e.g. `"+2 Chain"`, `"Arrows"`, `"Bones"`, `"Ancient Shield"`).

## Example record

Tile ID 66 (Monster Spawn):

```json
"66": {
  "name": "Monster Spawn",
  "description": "A monster lair.",
  "spawn_monsters": ["Giant Rat", "Wolf", "Goblin", "Orc", "Lich"],
  "spawn_chance": 5,
  "spawn_radius": 5,
  "max_spawned": 2,
  "boss_monster": "Goblin",
  "boss_monsters": ["Goblin"],
  "xp_reward": 50,
  "gold_reward": 25,
  "loot": ["+2 Chain", "Arrows"],
  "background_tile": 0
}
```

## Notes and open questions

A few things worth knowing:

`background_tile` is set on every record in current data but the TS parser doesn't include it on `RawSpawnPoint`. Either wire it through so cleared lairs reveal an appropriate ground tile (currently they probably just disappear or stay), or remove the field.

`boss_monster` (singular) is the legacy form of `boss_monsters` (plural). Tile 69 (Dragon) sets `boss_monster: ""` and relies entirely on `boss_monsters`. The fallback exists for backward compatibility; new entries should populate the plural form.

The numeric keys are stored as JSON strings because JSON objects can't have integer keys. The loader re-parses them via `parseInt` at `SpawnPoints.ts:91`. This is fine but it's the kind of thing that bites if you ever change the indexing scheme.

The spawn-tile IDs in this file (66, 67, 68, 69, 71, 75) correspond to entries in `tile_defs.json` with `context: "spawns"`. The relationship is implicit (the IDs match by hand), not enforced by either side.

`_comment` is documentation; no TS reader.
