# effects.json

## Purpose

Defines party-wide "slottable" status effects — currently `detect_traps`, `infravision`, `galadriels_light`, and `sun_sword_aura`. Each effect carries a requirements predicate (class or race gates) and either a duration in steps or a `"permanent"` lifetime. The party UI surfaces up to four active effect slots.

## Location

`data/effects.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "_comment": "...",
  "effects": [ <effect_record>, ... ]
}
```

`effects` is a flat array. Each record is identified by its `id` string.

## Effect record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `id` | string | Stable identifier referenced from `party.party_effects`, `items.grants_effect`, and TS switch statements | Yes — `Effects.ts:54` |
| `name` | string | Display label | Yes |
| `description` | string | Tooltip text | Yes |
| `duration` | `"permanent"` \| number | Step count before expiry, or the literal string `"permanent"` | Yes — `PartyActions.ts:412` for Galadriel's Light tick |
| `requirements` | object | Eligibility predicate; see below | Yes — `Effects.ts:68 meetsClause` |
| `item_granted` | bool | If true, this effect is conferred by an equipped item rather than slotted manually | Yes — `Effects.ts:90`, `PartyScene.ts:2379` |
| `aura_color` | [int, int, int] | RGB aura tint while active | **No** — appears only on `sun_sword_aura`; no TS reader |
| `aura_pulse_hz` | number | Aura pulse frequency | **No** |
| `aura_radius` | number | Aura tile radius | **No** |

## `requirements` predicate

A small predicate language with three variants. The loader at `Effects.ts:68-82` evaluates the predicate against a candidate character.

| Variant | Shape | Behavior |
|---|---|---|
| Class gate | `{ "class": "<ClassName>", "min_level"?: <int> }` | Character must be of that class and at or above `min_level` (defaults to 1) |
| Race gate | `{ "race": "<RaceName>" }` | Character must be of that race |
| Any-of | `{ "any_of": [ <predicate>, ... ] }` | At least one inner predicate must match (recursive) |

If `requirements` is omitted entirely the effect is always available (`Effects.ts:91`).

## Per-effect handler matrix

Effects are NOT generic — the TS combat / step / lighting code hardcodes behavior per `id`. Adding a new effect requires adding both a new entry here AND a new switch arm in TS, plus an entry in `PartyActions.ts:226-229` `EFFECT_DISPLAY_NAMES`.

| `id` | Handler |
|---|---|
| `detect_traps` | `PartyActions.ts:286` |
| `infravision` | `PartyActions.ts:365,368` |
| `galadriels_light` | `PartyActions.ts:412` (step tick) |
| `sun_sword_aura` | `PartyActions.ts:432,451-456`; granted by Sun Sword weapon |

## Cross-references to other JSON files

`requirements.class` → class names defined in `data/classes/*.json` (`name` field).

`requirements.race` → race names defined in `data/races.json` (top-level keys, case-insensitive).

`id: "sun_sword_aura"` → referenced by `items.json` Sun Sword's `grants_effect` field.

Effect IDs are written into `party.json`'s `party_effects.effect_1..4` save slots.

## Example record

```json
{
  "id": "detect_traps",
  "name": "Detect Traps",
  "description": "Traps are revealed before the party steps on them.",
  "duration": "permanent",
  "requirements": {
    "any_of": [
      { "class": "Thief",  "min_level": 1 },
      { "class": "Ranger", "min_level": 3 }
    ]
  }
}
```

## Notes and open questions

The schema is open but the implementation is fully hardcoded. Adding a new effect to this file alone has no runtime effect — it would silently appear in eligibility lists but never do anything. The hand-wired switch in `PartyActions.ts` is the constraint.

The `aura_color`, `aura_pulse_hz`, and `aura_radius` fields on `sun_sword_aura` came from the legacy Python renderer (`src/renderer.py:6269`), which actually drew the aura. The TS port hasn't implemented the aura visual yet, so these are dormant authoring intent.

`item_granted: true` effects (currently only `sun_sword_aura`) flow through a separate code path — they're applied automatically when the item is equipped (`PartyActions.ts:181`) and refused from manual slot selection (`Effects.ts:90`). This is implicit; if you add another item-granted effect, both behaviors need to be remembered.

`_comment` is documentation; no TS reader.

The file is small (4 entries) so cleanup pressure is low, but the schema is the right shape for future expansion. The main thing to keep in mind is that adding a new effect is a multi-file change, not just a JSON edit.
