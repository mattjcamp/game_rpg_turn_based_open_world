# spells.json

## Purpose

The player-facing spell list. Each record defines who can cast the spell, when it's available, what it costs, how it resolves in combat, and which targeting picker the UI should use. This file is the source of truth for player spellcasting; monster spell-likes are defined inline in `monsters.json` and do not reference this file.

## Location

`data/spells.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "spells": [ <spell_record>, ... ]
}
```

A single top-level key `spells` holding a flat array. Spells are identified by their `id` field. Loader: `Spells.ts:82` (`loadSpells`).

## Spell record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `id` | string | Stable identifier (e.g. `"magic_dart"`, `"fireball_aoe"`, `"heal"`) | Yes — `Spells.ts:98`; `PartyScene.ts:974` |
| `name` | string | Display name | Yes |
| `description` | string | Tooltip text | Yes |
| `allowable_classes` | string[] | Classes that may learn this spell — names matched against `data/classes/*.json` `name` | Yes — `Spells.ts:132`, `CombatActions.ts:214` |
| `casting_type` | string | `"sorcerer"` / `"priest"` — flavor categorization | Partial — preserved on the model, no code branches on it |
| `min_level` | number | Minimum caster level required | Yes — `Spells.ts:119` |
| `class_min_levels` | object | Per-class level override, e.g. `{ "Paladin": 5 }` for Turn Undead | Yes — `Spells.ts:120` |
| `mp_cost` | number | MP deducted on cast | Yes — `Spells.ts:134` |
| `duration` | `"instant"` \| number | Step / round count for ongoing spells | Partial — buffs use it for ticks; some records use the string `"10"` instead of a number |
| `effect_type` | string | Resolution discriminator — drives the combat handler; see below | Yes |
| `effect_value` | object | Per-effect numeric payload — fields read depend on `effect_type` | Yes |
| `range` | number | Maximum range in tiles | Yes |
| `targeting` | string | Picker UI discriminator; see below | Yes |
| `usable_in` | string[] | Contexts the spell can be cast in: `"battle"`, `"overworld"`, `"town"`, `"dungeon"` | Yes — `Spells.ts:148`, `CombatActions.ts:213` |
| `sfx` | string \| null | Sound effect cue at cast-time | Yes |
| `hit_sfx` | string \| null | Sound effect cue at hit/resolve | Yes |
| `icon` | string | UI icon hint | Partial — declared, mostly empty in current data |

## `effect_value` sub-object

`effect_value` is a property bag whose populated fields depend on the spell's `effect_type`. The fields below are the union of everything actually consumed somewhere in TS — any single spell uses only a subset.

| Field | Used by |
|---|---|
| `dice` | Legacy dice spec (e.g. `"1d6"`); `rollSpellHeal` (`CombatActions.ts:183`) falls back to this when `dice_count`/`dice_sides` are absent |
| `dice_count` | Damage / heal — number of dice |
| `dice_sides` | Damage / heal — sides per die |
| `stat_bonus` | Damage / heal — stat name (`"intelligence"`, `"wisdom"`) added to roll |
| `min_damage` | Floor for damage rolls (declared; `rollSpellHeal` enforces `Math.max(1, …)` instead — see Notes) |
| `min_heal` | Floor for heal rolls (declared; not read — see Notes) |
| `hp_amount` | Direct HP for heal spells |
| `hp_percent` | Percentage HP for major/mass heals |
| `mp_percent` | Percentage MP for restore spells |
| `heal_percent` | Percentage heal for some restore variants |
| `cure_poison` | Boolean flag for poison removal |
| `ac_bonus` | AC buff amount |
| `range_bonus` | Range buff amount |
| `attack_bonus` | To-hit buff amount |
| `ac_penalty` | AC debuff amount (curse) |
| `attack_penalty` | To-hit debuff amount (curse) |
| `max_target_hp` | Sleep ceiling — refuses targets above this HP |
| `save_dc_base` | Base save DC |
| `save_dc_stat` | Stat used to scale save DC |
| `save_stat` | Stat the target rolls against |
| `radius` | AoE radius for `aoe_fireball` |
| `push_distance` | Knockback distance for `knock` / push |
| `steps` | Step duration for overworld spells (e.g. magic light) |
| `skeleton_hp`, `skeleton_ac`, `skeleton_attack`, `skeleton_dmg_dice`, `skeleton_dmg_sides`, `skeleton_dmg_bonus` | Animate Dead skeleton stats (`CombatActions.ts:445`) |

## Polymorphic discriminators

Two discriminators, combined in `CombatActions.ts:238` (`classifyCombatCast`).

**`effect_type`** drives spell resolution. The branches consumed by TS:

| `effect_type` | Where it fires | Notes |
|---|---|---|
| `damage` | `CombatActions.ts:270-279`, `CombatScene.ts:1786+` | Single-target damage spells |
| `lightning_bolt` | `CombatScene.ts` | Line damage |
| `aoe_fireball` | `CombatScene.ts` | AoE damage (Fireball; `id: "fireball_aoe"`) |
| `heal` | combat + out-of-combat | Single-target heal |
| `major_heal` | same | Larger heal |
| `mass_heal` | same | Party-wide heal |
| `restore` | same | MP restore |
| `cure_poison` | same | Status cleanse |
| `ac_buff` | combat | AC buff |
| `range_buff` | combat | Range buff |
| `bless` | combat | Generic buff |
| `curse` | combat | Generic debuff |
| `sleep` | combat | Status: targets only ≤ `max_target_hp` |
| `charm` | combat | Status |
| `invisibility` | combat | Status |
| `magic_light` | dungeon | `PartyActions.ts:1236`; dungeon-only |
| `repel_monsters` | overworld | Repel encounters |
| `summon_skeleton` | combat | Spawns a skeleton from `effect_value.skeleton_*` (`CombatActions.ts:445`) |
| `teleport` | various | Move the party |
| `undead_damage` | combat | Turn Undead-style damage |
| `knock` | dungeon | `Lock.ts:188`; dungeon-only door/lock opening |

Unrecognized `effect_type` values would be silently ignored by the resolver — there's no fallback handler.

**`targeting`** drives the picker UI:

| `targeting` | Picker behavior |
|---|---|
| `self` | Auto-targets the caster |
| `select_ally` | Lets the player click an ally |
| `select_ally_or_self` | Same, plus self is selectable |
| `select_enemy` | Lets the player click an enemy |
| `select_tile` | Lets the player click an empty tile |
| `directional_projectile` | Lets the player choose a direction |
| `auto_monster` | Auto-picks the nearest enemy |

## Cross-references to other JSON files

`allowable_classes` and `class_min_levels` keys → class names defined in `data/classes/*.json` (`name` field).

`sfx` and `hit_sfx` → entries in the SFX catalog at `web/src/game/audio/Sfx.ts` (not a data file).

The spell `id` `"cure_poison"` intentionally collides with the `items.json` `effect: "cure_poison"` tag — they're the same conceptual capability, but the item-use handler does not delegate to the spell.

`id: "fireball"` is referenced by `items.json` Sun Sword's `on_hit.spell_id: "fireball"`. See Notes — the reference is currently broken.

## Example record

Magic Dart, exercises directional projectile + damage:

```json
{
  "id": "fireball",
  "name": "Magic Dart",
  "description": "Hurls an energy-charged dart in a straight line, stinging on impact.",
  "allowable_classes": ["Wizard","Alchemist","Druid"],
  "casting_type": "sorcerer",
  "min_level": 1,
  "mp_cost": 6,
  "duration": "instant",
  "effect_type": "damage",
  "effect_value": {
    "dice": "1d6",
    "stat_bonus": "intelligence",
    "min_damage": 1,
    "dice_count": 1,
    "dice_sides": 6
  },
  "range": 10,
  "targeting": "directional_projectile",
  "usable_in": ["battle"],
  "sfx": "fireball",
  "hit_sfx": "explosion",
  "icon": "unique_tiles/sunken_shipwreck"
}
```

## Notes and open questions

A handful of things to flag:

**The `id: "fireball"` collision is a bug magnet.** The spell with `id: "fireball"` is named "Magic Dart"; the spell named "Fireball" has `id: "fireball_aoe"`. The Sun Sword in `items.json` declares `on_hit.spell_id: "fireball"`, almost certainly intending the AOE — but the hook isn't wired anyway. When the hook gets wired, rename or repoint.

**`dice` AND `dice_count`/`dice_sides` are redundant.** Both are present on damage/heal records. `rollSpellHeal` (`CombatActions.ts:183`) prefers the new dice_count/dice_sides pair and falls back to parsing the legacy `dice` string. Cleanup target: drop the legacy `dice` field once every record carries the new pair.

**`min_damage` and `min_heal` are declared but unread.** TS uses `Math.max(1, ...)` instead. Either wire the field or remove it.

**`duration: "10"` on the Push spell (around line 522) is a string.** Every other numeric duration is a number. Normalize to int.

**`hit_sfx` is inconsistent** — sometimes `""`, sometimes `null`. Pick one.

**`icon` is mostly empty.** Magic Dart sets `icon: "unique_tiles/sunken_shipwreck"`, which is almost certainly a placeholder copy-paste. Either fill in real icon keys or drop the field.

`casting_type` is currently informational only. If you want the future bookkeeping (sorcerer vs. priest spell lists for UI grouping), it's there ready to consume. If not, it's a removable field.
