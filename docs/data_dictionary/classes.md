# classes (data/classes/*.json)

## Purpose

Defines the eight playable character classes (alchemist, cleric, druid, fighter, paladin, ranger, thief, wizard) — their HP/MP growth per level, XP curve, movement range, casting tradition, and any class-specific abilities. One file per class, all sharing an identical schema.

## Location

`data/classes/alchemist.json`, `cleric.json`, `druid.json`, `fighter.json`, `paladin.json`, `ranger.json`, `thief.json`, `wizard.json`.

The TS loader (`web/src/game/world/Classes.ts:125-136`) fetches by lowercase filename when a character of that class is constructed.

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. The 8 files share one schema; this doc documents the shared shape and calls out per-class quirks at the bottom.

## File shape

Each file is a flat singleton object describing one class — no records collection, no nesting beyond `mp_source` and `class_abilities`.

## Fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Display name (`"Fighter"`, `"Wizard"`, …) | Yes |
| `_comment` | string | Author note | No |
| `allowed_weapons` | string[] \| `"all"` | Wieldable weapon families (`"sword"`, `"long_bow"`, etc.) | **No** — parsed onto the model but never queried |
| `allowed_armor` | string[] \| `"all"` | Wearable armor families (`"cloth"`, `"leather"`, `"chain"`, `"plate"`) | **No** — same |
| `hp_per_level` | number | HP added per level-up | Yes — `Leveling.ts:150` |
| `mp_per_level` | number | MP added per level-up | Yes — `Leveling.ts:155` |
| `range` | number | Tiles of movement per combat turn | Yes |
| `exp_per_level` | number | XP per level threshold | Yes — `Leveling.ts:82,146` |
| `allowed_races` | string[] | Races allowed to take this class (e.g. `["human", "elf"]`) | **Partial** — the JSON values are unread; the canonical race-gate table is hardcoded in `web/app/party/new/page.tsx:64-73` as `CLASS_RACES`. Editing this field has no effect on the character creator. |
| `spell_type` | `"none" \| "priest" \| "sorcerer" \| "both"` | Casting tradition discriminator | **No** — `spells.json`'s `allowable_classes` drives spell unlocks instead |
| `mp_source` | object \| null | MP scaling source; see below | Partial |
| `class_abilities` | object[] | Non-spell class features; see below | Yes |
| `mp_regen_multiplier` | number | Faster-than-default MP regen multiplier (Druid only) | **No** — parsed but no consumer |

## `mp_source` sub-object

Determines which stat drives a class's maximum MP. Set to `null` for non-casters (Fighter, Thief).

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `ability` | string (single stat) | Single-stat caster: stat name (`"intelligence"`, `"wisdom"`) | Yes — `Classes.ts:93-94`, `Leveling.ts:61` |
| `abilities` | string[] (dual stats) | Dual-stat caster: list of stat names | Yes — `Classes.ts:95-99`, `Leveling.ts:64` (used only by Druid) |
| `mode` | `"higher" \| "average"` | Combine rule when `abilities` has multiple stats | Yes — `Leveling.ts:66-69` |
| `percentage` | number | Base MP as a fraction of the source stat | **No** — parsed but no consumer |

`mp_source` is the only true discriminator in the schema. The loader branches on whether `ability` (string) or `abilities` (array) is present.

## `class_abilities` entry

Non-spell unlocks like Herbalism, Pick Locks, Detect Traps. Only Paladin, Ranger, and Alchemist define these in current data.

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Ability label | Yes |
| `description` | string | UI text | Yes |
| `min_level` | number (default 1) | Level the ability unlocks at | Yes — `Leveling.ts:119` |

## Cross-references to other JSON files

`allowed_races` values are matched (case-insensitive) against keys in `races.json`. Because the JSON values are unread, this is documentary only today.

The class `name` field is matched against `roster[].class` in `party.json` (case-insensitive) and against entries in `spells.json`'s `allowable_classes` arrays.

`allowed_weapons` and `allowed_armor` would conceptually match `item_type` values in `items.json`, but neither side enforces the relationship at runtime.

## Example record

`data/classes/ranger.json`, exercises every optional field:

```json
{
  "name": "Ranger",
  "_comment": "A woodsman who can use any bow, light armor...",
  "allowed_weapons": ["fists","dagger","club","sling","short_bow","long_bow","crossbow","sword"],
  "allowed_armor": ["cloth","leather","chain"],
  "hp_per_level": 10,
  "mp_per_level": 3,
  "range": 6,
  "exp_per_level": 1500,
  "allowed_races": ["human","dwarf","halfling","elf","gnome"],
  "spell_type": "priest",
  "mp_source": { "ability": "wisdom", "percentage": 50 },
  "class_abilities": [
    { "name": "Herbalism",    "description": "..." },
    { "name": "Pick Locks",   "min_level": 3, "description": "..." },
    { "name": "Detect Traps", "min_level": 3, "description": "..." }
  ]
}
```

## Per-class quirks

- **Fighter** uses `"allowed_weapons": "all"` and `"allowed_armor": "all"` (strings). Other classes use arrays. `mp_source: null`.
- **Paladin** uses `"allowed_weapons": "all"` (string). Defines `class_abilities`.
- **Thief** has `mp_source: null`.
- **Druid** carries `mp_regen_multiplier` (not present on other classes; not read by TS) and is the only class using a dual-stat `mp_source` (`abilities` + `mode`).
- **Ranger** is the only class whose first `class_abilities` entry (Herbalism) omits `min_level`, defaulting it to 1 via the loader.
- **Alchemist** defines `class_abilities`.

## Notes and open questions

A handful of fields appear to have once driven the legacy Python implementation and no longer do anything in TS:

- `_comment` is documentation; no TS reader.
- `allowed_weapons` and `allowed_armor` are parsed onto the class model but never queried. If equipment restrictions matter going forward, this is the wiring target; otherwise the fields can be dropped.
- `spell_type` looks like a discriminator but isn't one — spell access flows entirely through `spells.json`'s `allowable_classes`. The field can be removed without behavior change.
- `mp_source.percentage` is parsed but unread.
- `mp_regen_multiplier` is Druid-specific authoring intent without a runtime consumer.
- `allowed_races` is the bigger issue: it's the visible source of race gating, but the actual gate lives in TS source (`CLASS_RACES` constant in `app/party/new/page.tsx`). Editing this field is a foot-gun — looks like it should work, doesn't. Either wire the loader to consume it, or remove it from the JSON and treat the TS constant as the canonical source.

Schema inconsistencies between files that are worth normalizing once the cleanup pass happens:

- Some files use `"allowed_weapons": "all"` (string) and others use arrays. Pick one convention.
- `mp_source` is `null` on non-casters and an object on casters. Fine, but the field is required-or-null rather than optional, which is slightly awkward.
- `class_abilities` is omitted on classes that don't have any rather than being an empty array. Either is fine; just pick one.
