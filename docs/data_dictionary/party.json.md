# party.json

## Purpose

The starting party save-game seed: where the party spawns, how much gold they have, who's in the roster, who's currently active, what gear they're carrying, and a few step-counter resources (torch, magic light, Galadriel's Light). At runtime, `loadParty()` (`Party.ts:430-454`) prefers the in-memory cache, then `localStorage`, then this JSON — so the file is consulted only on a fresh start.

## Location

`data/party.json`. Note: `web/public/data/party.json` is auto-regenerated from this file by `web/scripts/sync-modules.mjs` during `predev` / `prebuild`. Edit the source, not the copy.

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

A flat singleton object with section keys (`start_position`, `gold`, `roster`, `active_party`, `party_effects`, `inventory`, step counters). No record collection — the whole file is one save record.

## Top-level fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `_comment` | string | Author note (also warns about the auto-regenerated copy) | No |
| `start_position` | `{ col: int, row: int }` | Initial party position on the world map | Yes — `Party.ts:321-325` |
| `gold` | int | Shared party gold pool | Yes |
| `roster` | object[] | All available members; see below | Yes |
| `active_party` | int[] | Indices into `roster` for the four currently active members | Yes — `Party.ts:329`, `activeMembers` at `Party.ts:458` |
| `party_effects` | object | Up to four named active-effect slots | Yes — `Party.ts:330-332` |
| `inventory` | object[] | Shared party stash | Yes |
| `torch_steps` | int | Remaining lit-torch steps | Yes |
| `magic_light_steps` | int | Light-spell orb remaining steps | Yes — `Party.ts:335` (raw key supported; not present in the seed) |
| `galadriels_light_steps` | int | Elven Light remaining steps | Yes — `Party.ts:336` |
| `last_tinker_day` | int | Gnome Tinker cooldown (in-game days) | Yes — `Party.ts:337` (raw key supported; not present in the seed) |

## `roster[]` entry

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Character name | Yes |
| `class` | string | Class name in PascalCase (matched against `data/classes/<lowercase>.json`) | Yes — `Party.ts:216` |
| `race` | string | Race name (matched against `races.json`) | Yes — `Party.ts:222` |
| `gender` | string | `"Male"` / `"Female"` | Partial — stored and persisted but no gameplay branches on it |
| `hp` | int | Current HP (also seeds `maxHp`) | Yes — `Party.ts:218,224-225` |
| `mp` | int | Current MP (also seeds `maxMp`) | Yes — `Party.ts:226-227` |
| `strength` | int | Post-race STR | Yes |
| `dexterity` | int | Post-race DEX | Yes |
| `constitution` | int | Post-race CON | Yes |
| `intelligence` | int | Post-race INT | Yes |
| `wisdom` | int | Post-race WIS | Yes |
| `level` | int | Character level | Yes |
| `exp` | int | Cumulative XP | Yes |
| `equipped` | object | Equipment slot map; see below | Yes |
| `inventory` | object[] | Per-member bag (separate from the shared stash); items carry optional `charges` or `durability` | Yes — `Party.ts:251` |
| `sprite` | string | PNG path (normalized by `spriteForMember` at `Party.ts:206` — invalid paths fall back to the class default) | Yes |

## `equipped` sub-object

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `right_hand` | string \| null | Weapon (or two-hander) | Yes — `Party.ts:236` |
| `body` | string \| null | Armor | Yes — `Party.ts:238` |
| `left_hand` | string \| null | Legacy off-hand slot | **No** — `migrateUnsupportedSlots` (`Party.ts:273-289`) silently moves any occupant back to inventory on load |
| `head` | string \| null | Legacy head slot | **No** — same migration |

## `party_effects` sub-object

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `effect_1` | string \| null | First active effect ID | Yes |
| `effect_2` | string \| null | Second active effect ID | Yes |
| `effect_3` | string \| null | Third active effect ID | Yes |
| `effect_4` | string \| null | Fourth active effect ID | Yes |

Effect IDs are looked up in `effects.json`.

## `inventory[]` entry (shared stash and per-member bag both use this shape)

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `item` | string | Item name from `items.json` | Yes |
| `charges` | int (optional) | For consumables and ammo | Yes |
| `durability` | int (optional) | For gear with wear | Yes |

## Cross-references to other JSON files

`roster[].class` → `data/classes/<lowercase>.json` (e.g. `"Fighter"` → `classes/fighter.json`), fetched on demand by `loadClass`.

`roster[].race` → keys in `data/races.json` (case-insensitive).

`roster[].equipped.*` and all `item` strings (member inventory and shared stash) → entries in `data/items.json`, looked up via `loadItems()` (`Party.ts:447`).

`party_effects.effect_1..4` → effect IDs in `data/effects.json`.

`roster[].sprite` → an asset path under `web/public/assets/...` (not a data file).

## Example record

The first roster entry (Aldric the fighter):

```json
{
  "name": "Aldric",
  "class": "Fighter",
  "race": "Human",
  "gender": "Male",
  "hp": 16,
  "mp": 0,
  "strength": 16,
  "dexterity": 11,
  "constitution": 12,
  "intelligence": 8,
  "wisdom": 8,
  "level": 1,
  "exp": 0,
  "equipped": {
    "right_hand": "Club",
    "left_hand": null,
    "body": "Cloth",
    "head": null
  },
  "inventory": [],
  "sprite": "src/assets/game/characters/fighter.png"
}
```

## Notes and open questions

`gender` is stored and persisted to localStorage but no gameplay code reads it — purely cosmetic on the character sheet. Fine, but explicit so it isn't mistaken for a stat gate.

`equipped.left_hand` and `equipped.head` are legacy slots from the Python build. The TS port's PartyScene UI only surfaces `right_hand` and `body`, and the load-time migration silently relocates anything in the legacy slots back to inventory. Either remove these fields from the seed (and stop emitting them on save) or revive the slots in the UI.

`magic_light_steps` and `last_tinker_day` are supported by the loader but absent from the shipped seed file. They appear only after gameplay populates them. Authoring them as 0 in the seed would make the schema explicit.

The seed inventory uses singular item names with `charges` (e.g. `{"item": "Rock", "charges": 20}`) where elsewhere the codebase tends to refer to "Rocks" (plural). Double-check against `items.json` to avoid load-time mismatches.

Every seed roster member has a `sprite` path under `src/assets/game/...` which fails the `humanoid` prefix check in `spriteForMember` (`Party.ts:206`) and falls through to the class default at `/assets/characters/<class>.png`. So the seed sprite paths are effectively dead — replaced at load time regardless. Worth either fixing the paths or accepting them as dead-by-design.

`_comment` is documentation; it includes the auto-regeneration warning, which is worth keeping.
