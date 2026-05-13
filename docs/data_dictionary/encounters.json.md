# encounters.json

## Purpose

Defines named encounter rosters used by the world / dungeon / interior random-encounter system and by quests. Each encounter ties a difficulty level, a weight (for weighted sampling), and a list of monster names. The encounter is the unit of selection — the combat scene loads its full monster roster from this file.

This is the file that supersedes `monsters.json`'s `spawn_tables` top-level key, which the TS implementation does not read.

## Location

`data/encounters.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "_comment": "...",
  "encounters": {
    "dungeon":        [ <encounter_record>, ... ],
    "house_basement": [ <encounter_record>, ... ],
    "overworld":      [ <encounter_record>, ... ]
  }
}
```

The `encounters` object is keyed by **area bucket**. Each value is an array of encounter records — flat objects, no grids. Loader: `Encounters.ts:65-81` (`loadEncounters`).

## Top-level fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `_comment` | string | Author note | No |
| `encounters` | object | Area-keyed map of encounter arrays | Yes |
| `encounters.dungeon` | array | Dungeon rosters (~most populated) | Yes |
| `encounters.house_basement` | array | Sub-area rosters (levels 1–2 only) | Yes |
| `encounters.overworld` | array | World-map rosters | Yes |

## Encounter record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Display / lookup name; referenced by towns (NPC encounter triggers) and quest kill-step rows | Yes — `Encounters.ts:56` |
| `level` | int (1–8) | Difficulty band; the sampler filters by `[minLevel..maxLevel]` | Yes — `Encounters.ts:57,140` |
| `weight` | int (> 0) | Weighted-sample probability inside an eligible band | Yes — `Encounters.ts:58,167-172` |
| `terrain` | `"land"` \| `"sea"` | Land/sea filter | **Partial** — parsed (loader narrows anything non-`"sea"` to `"land"` at `Encounters.ts:59`); no downstream consumer queries the field today |
| `monster_party_tile` | string | Lead monster shown on the overworld map sprite; falls back to `monsters[0]` when empty | Yes — `Encounters.ts:52-54,160` |
| `monsters` | string[] | Roster handed to the combat scene; cross-refs `monsters.json` names | Yes — `Encounters.ts:48-51` |

## Polymorphic discriminator

The area bucket key (`"dungeon"` / `"house_basement"` / `"overworld"`) is the discriminator and is selected by the caller — `sampleEncounter(table, area, ...)` at `Encounters.ts:130-135`. Encounter records themselves have no `type` field.

## Cross-references to other JSON files

`monsters[]` and `monster_party_tile` → monster names defined in `monsters.json` (resolved via `makeMonsterByName`).

`name` is referenced from:
- `data/towns.json`'s `encounters[].name` (`AuthoredEncounter` type in `Towns.ts:62-71`)
- Quest kill-step rows in `quests.json`, resolved via `rosterFor(encounters, encounterName)` at `InteriorSpawn.ts:153,359`

## Example record

A small dungeon encounter (level 1):

```json
{
  "name": "Cellar Rats",
  "level": 1,
  "weight": 30,
  "terrain": "land",
  "monster_party_tile": "Giant Rat",
  "monsters": ["Giant Rat"]
}
```

## Notes and open questions

`terrain` is the dead field of the bunch. Every record sets it (88 of 91 are `"land"`), but no downstream code branches on it. Either wire it into the world-map encounter picker (so sea encounters only fire on water tiles) or drop it.

Two overworld records — `Lich with Minions` and `Mind Flayer` (around lines 1008-1028) — have empty `monster_party_tile: ""`. The loader silently substitutes `monsters[0]` for these, so the encounter still works, but it's worth either filling these in deliberately or removing the field when omitted.

Levels span 1–8 across all three buckets except `house_basement`, which is capped at levels 1–2. That's intentional given the area's narrative scope.

`_comment` is documentation; no TS reader.
