# races.json

## Purpose

Defines the five playable races (Human, Dwarf, Halfling, Elf, Gnome) — their stat modifiers, innate effects, and per-race XP overrides. **Mostly dead in the TypeScript implementation**: only Human's `exp_per_level` override is actually read. Stat modifiers and effects are duplicated as hardcoded TS constants and the JSON values are ignored.

## Location

`data/races.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

Singleton object keyed by capitalized race name (`Human`, `Dwarf`, `Halfling`, `Elf`, `Gnome`), with a sibling `_comment` field. The loader (`Classes.ts:139-154`, `loadRaces()`) skips keys starting with `_`.

```
{
  "_comment": "...",
  "Human":  { ...race_record... },
  "Dwarf":  { ... },
  ...
}
```

## Fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `_comment` | string | Author note | No |
| `<Race>.description` | string | Flavor text | **No** — `loadRaces()` ignores it |
| `<Race>.stat_modifiers` | object | `{strength,dexterity,constitution,intelligence,wisdom}` deltas applied at character creation | **Partial** — the JSON is unread; the canonical race-mod table is hardcoded at `web/app/party/new/page.tsx:46-52` as `RACE_MODS` |
| `<Race>.exp_per_level` | number | Race-level XP curve override | **Yes** — `Classes.ts:149`, `Leveling.ts:82,146`; only Human supplies this in current data |
| `<Race>.effects` | string[] | Innate effect IDs (e.g. `["infravision"]`) | **Partial** — the JSON values are unread; the equivalent table is hardcoded at `Classes.ts:172-190` as `RACE_ABILITIES`, and the effect handlers in `Effects.ts` / `PartyActions.ts` look up effects by string literal rather than by going through this file |

## Cross-references to other JSON files

`effects` strings (`infravision`, `pickpocket`, `galadriel_light`, `tinker`) conceptually map to effect IDs in `effects.json`, but the runtime doesn't perform that lookup — the effects are hand-wired in TS by name.

Race keys are referenced (case-insensitively) by `allowed_races` in the class files and by `roster[].race` in `party.json`. The class files use lowercase race names (`"human"`); this file uses capitalized names (`"Human"`). `raceAbilities()` at `Classes.ts:200` normalizes case at lookup.

## Example record

```json
"Dwarf": {
  "description": "Stout and hardy, dwarves are natural miners...",
  "stat_modifiers": {
    "strength": 2,
    "dexterity": -1,
    "intelligence": 0,
    "wisdom": 1,
    "constitution": 2
  },
  "effects": ["infravision"]
}
```

## Notes and open questions

The big issue is the same as `classes/*.json`'s `allowed_races`: the JSON looks authoritative but isn't. Three of the four interesting fields (`description`, `stat_modifiers`, `effects`) are duplicated in TS source. Editing them has no effect on gameplay.

Editing `Human.exp_per_level` is the only operation on this file that actually changes behavior — every other race relies on the class default.

`Human.effects` is `[]` (the trade-off being that humans get the XP bonus instead of an innate effect). That's intentional, not a bug.

Net: same recommendation as the `allowed_races` field — either wire the loader to consume `stat_modifiers` and `effects`, or remove them from the JSON and accept the TS constants as canonical. Today this file is the more confusing of the two because it's only 7% useful and 93% misleading.
