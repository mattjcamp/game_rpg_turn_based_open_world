# monsters.json

## Purpose

Defines every monster the game can spawn — its combat stats, visual identity, movement rules, and any spell-like abilities, on-hit triggers, or passive traits.

## Location

`data/monsters.json`

## Scope of this document

The "Used?" column in this file reflects the TypeScript + Phaser implementation under `web/` only. The Python implementation under `src/` is legacy and is not consulted.

## File shape

The file is a single JSON object with two top-level keys:

```
{
  "monsters":      { <name>: <monster_record>, ... },
  "spawn_tables":  { <table_name>: [<monster_name>, ...], ... }
}
```

`monsters` is an object keyed by display name (e.g. `"Giant Rat"`, `"Goblin"`). The key doubles as the monster's identity — it's what the encounter system references.

`spawn_tables` is an object keyed by environment name. **Currently dormant** in the TS implementation; see the note at the bottom of this doc.

## Monster record fields

Every record under `monsters.<name>` may include the following fields. "Expected" = the loader (`web/src/game/data/monsters.ts:specFromRaw`) reads it; missing fields fall back to defaults where noted.

| Field | Type | Expected | Description | Valid values | Used? |
|---|---|---|---|---|---|
| `description` | string | no | Flavor text for the monster | free text | **No** — parsed onto the spec but never read |
| `undead` | bool | yes | Marks creature as undead | true / false | Yes — forwarded to `Combatant.undead`; consumed by Turn Undead |
| `humanoid` | bool | yes | Marks creature as humanoid | true / false | Partial — forwarded to `Combatant.humanoid` but no current code branches on it (Charm gating is future work) |
| `hp` | int | yes | Max hit points at spawn | positive int | Yes |
| `ac` | int | yes | Armor class (attack roll target) | typical 10–18 | Yes |
| `attack_bonus` | int | yes | Bonus added to melee attack rolls | typical 0–7 | Yes |
| `damage_dice` | int | yes | Number of dice for melee damage roll | positive int | Yes |
| `damage_sides` | int | yes | Sides per damage die (d4, d6, d8…) | positive int | Yes |
| `damage_bonus` | int | yes | Flat bonus added to melee damage | int | Yes |
| `xp_reward` | int | yes | XP granted to the party on kill | positive int | Yes |
| `gold_min` | int | yes | Minimum gold drop on kill (inclusive) | non-negative int | Yes — rolled at spawn time |
| `gold_max` | int | yes | Maximum gold drop on kill (inclusive) | non-negative int | Yes |
| `color` | [int, int, int] | yes | RGB fallback color when no sprite renders | each 0–255 | Yes |
| `spawn_weight` | int | no | Relative weight inside a spawn pool | positive int | **No** — TS encounter selection uses `encounters.json` weights, not this field |
| `tile` | string | yes | Sprite identifier or relative path | e.g. `"game/monsters/goblin.png"` or `"monsters/lich"` | Yes — paths are normalized at load time |
| `terrain` | string | yes | Terrain the monster spawns in | `"land"`, `"sea"` | Yes — gates whether creatures engage a boat-bound party |
| `move_range` | int | yes | Tiles the monster can move per turn in combat | non-negative int | Yes |
| `post_attack_move` | int | yes | Extra tiles allowed after a successful melee hit (hit-and-run) | non-negative int | Yes |
| `spells` | array \| null | yes | Spell-like abilities; see *Spell entry* below | null or array of spell objects | Yes |
| `on_hit_effects` | array \| null | yes | Effects that may trigger on a successful melee hit | null or array of on-hit objects | Yes |
| `passives` | array \| null | yes | Always-on traits like regen or resistances | null or array of passive objects | Yes |
| `battle_scale` | int | yes | Sprite size multiplier in combat (1 = standard, 2 = oversized boss) | 1 or 2 | Yes |
| `difficulty` | string | yes | Difficulty tier; used by encounter filtering | see *Difficulty values* below | Yes |
| `ranged` | object | no | Optional ranged attack profile | object or omitted | **No** — the entire `ranged` sub-object is not parsed in TS today |

## Ranged sub-object — currently unused

The `ranged` block appears on several records (Goblin, Orc, Dark Mage, Skeleton Archer, etc.) and described a secondary ranged-attack mode in the legacy Python combat. **The TypeScript loader does not parse this object**, so none of its fields affect gameplay today. The fields below are documented for reference and to preserve authoring intent until the feature is reintroduced.

| Field | Type | Description |
|---|---|---|
| `range` | int | Maximum range in tiles |
| `attack_bonus` | int | Bonus added to the ranged attack roll |
| `damage_dice` | int | Number of dice for ranged damage |
| `damage_sides` | int | Sides per ranged damage die |
| `damage_bonus` | int | Flat bonus to ranged damage |
| `projectile_color` | [int, int, int] | RGB color of the projectile |
| `projectile_symbol` | string | Glyph used for the projectile |
| `label` | string | Human-readable name for the attack (e.g. `"thrown rock"`) |

## Spell entry (inside `spells[]`)

Each spell entry is a polymorphic object discriminated by `type`. Unknown types are silently dropped at load (see `KNOWN_SPELL_TYPES` in `web/src/game/data/monsters.ts`).

**Common fields:**

| Field | Type | Description |
|---|---|---|
| `type` | string | Variant selector — see table below |
| `name` | string | Display name shown in combat log |
| `cast_chance` | int | Percent chance to cast on a given turn when conditions are met (0–100) |
| `range` | int | Casting range in tiles (omitted on `heal_self`) |

**Variants and their type-specific fields:**

| `type` | Extra fields | Handler in `web/`? |
|---|---|---|
| `sleep` | `save_dc`, `duration`, `max_target_hp` (refuses targets above this HP) | Yes — picks nearest enemy in range under the HP cap |
| `curse` | `duration`, `ac_penalty`, `attack_penalty` | Yes |
| `poison` | `save_dc`, `damage_per_turn`, `duration` | **No** — recognized as a known type but no cast handler exists |
| `magic_dart` | `damage_dice`, `damage_sides`, `damage_bonus` | Yes |
| `magic_arrow` | `damage_dice`, `damage_sides`, `damage_bonus` | Yes |
| `lightning_bolt` | `damage_dice`, `damage_sides`, `damage_bonus` | Yes |
| `fireball` | `damage_dice`, `damage_sides`, `damage_bonus`, `save_dc` | Yes — damage is halved against targets with the `fire_resistance` passive |
| `breath_fire` | `damage_dice`, `damage_sides`, `damage_bonus`, `save_dc` | Yes — same fire-resistance interaction as `fireball` |
| `heal_self` | `heal_dice`, `heal_sides`, `heal_bonus` (no `range`) | Yes — caster heals self when wounded |
| `heal_ally` | `heal_dice`, `heal_sides`, `heal_bonus` | Yes — targets the lowest-HP ally in range |

## On-hit effect entry (inside `on_hit_effects[]`)

Triggered when the monster lands a successful melee hit on a party member.

**Common fields:** `type` (string), `chance` (int 0–100, probability the effect fires on hit).

| `type` | Extra fields | Handler in `web/`? |
|---|---|---|
| `drain` | `amount` (int — HP transferred from target to attacker) | Yes |
| `consume` | `damage_per_turn`, `save_dc` | Yes — failed STR save swallows the target whole and applies a damage-over-time debuff |

The TypeScript `MonsterOnHit` union recognizes only `drain` and `consume`. Other types (e.g. `poison`, `slow`) would be silently dropped at load if added today.

## Passive entry (inside `passives[]`)

Always-on traits applied at spawn.

| `type` | Extra fields | Handler in `web/`? |
|---|---|---|
| `regen` | `amount` (int — HP restored each round, capped at max HP) | Yes — applied in `Combat.tickPassives` |
| `fire_resistance` | none | Yes — halves damage from `fireball` and `breath_fire` (see `Combat.rollMonsterSpellDamage`) |
| `poison_immunity` | none | **No** — parsed and stored on the combatant but no code currently reads it (placeholder for the poison status system) |

## spawn_tables — currently unused

The top-level `spawn_tables` object maps environment name → array of monster names. **The TypeScript implementation does not consume this key.** Encounter selection lives in `data/encounters.json`, which defines its own rosters and area mappings. The two tables below are preserved for legacy reasons and as a reference list.

| Table | Intent | Used? |
|---|---|---|
| `overworld` | World-map random encounters | No |
| `dungeon` | Dungeon random encounters | No |

## Difficulty values

The TypeScript `Difficulty` type recognizes `"easy" | "normal" | "hard" | "deadly"`. Callers supply a set of allowed difficulties when sampling encounters and the lookup is a plain string compare, so the JSON technically accepts any string — but only the four enum values participate in filtering today.

The JSON currently contains records tagged `"boss"` (e.g. Dragon). Because `"boss"` is not in the enum, those monsters are excluded from any difficulty-filtered pool, which is the intended effect: bosses are placed deliberately rather than rolled randomly. Still, the mismatch between data and enum is worth being aware of.

## Cross-references to other JSON files

None. Monster records are self-contained. The `spells` field defines spell behavior inline rather than referencing entries in `spells.json` (which is the player-facing spell list).

## Example record

Pulled from `monsters.json` (array values compacted onto single lines for readability; values are unchanged):

```json
"Goblin": {
  "description": "A small, sneaky goblin. Attacks in groups.",
  "undead": false,
  "humanoid": true,
  "hp": 6,
  "ac": 11,
  "attack_bonus": 2,
  "damage_dice": 1,
  "damage_sides": 4,
  "damage_bonus": 0,
  "xp_reward": 10,
  "gold_min": 1,
  "gold_max": 6,
  "color": [100, 160, 60],
  "spawn_weight": 40,
  "tile": "game/monsters/goblin.png",
  "ranged": {
    "range": 4,
    "attack_bonus": 2,
    "damage_dice": 1,
    "damage_sides": 3,
    "damage_bonus": 0,
    "projectile_color": [160, 140, 120],
    "projectile_symbol": ".",
    "label": "thrown rock"
  },
  "terrain": "land",
  "move_range": 6,
  "post_attack_move": 0,
  "spells": null,
  "on_hit_effects": null,
  "passives": null,
  "battle_scale": 1,
  "difficulty": "easy"
}
```

For records exercising `spells`, `on_hit_effects`, and `passives`, see `Dragon`, `Lich`, and `Vampire Lord` in the same file.

## Notes and open questions

Items worth revisiting for the next data pass:

- **`description`** is set on every record but no TS code reads it. Useful as authoring context, and a future bestiary screen would consume it — but if no such feature is planned, it's removable.
- **The `ranged` sub-object** is fully unread by the TS implementation. Goblin, Orc, Dark Mage, Skeleton Archer, and others carry rich ranged-attack definitions that do nothing in the current build. Decide whether to port the ranged-attack feature or strip the field from the data.
- **`spawn_weight`** is unused under the TS encounter system. If `encounters.json` is the sole source of truth for spawn selection, this field can be removed from `monsters.json`.
- **`spawn_tables`** at the top level is similarly unused. Removing it would simplify the schema; keep it only if there's an intent to revive it.
- **`humanoid`** is parsed onto the combatant but no current code branches on it. The Python implementation used it to gate the Charm spell on player-side casting; if Charm comes to the TS port, this is the hook.
- **`poison_immunity`** passive is parsed but has no consumer. It only matters once the poison status engine ships.
- **Spell type `poison`** is in the known-types set but lacks a cast handler. The Mind Flayer's `Cerebral Toxin` spell uses this type — it'll currently be loaded as a known spell but never actually cast.
- **`"boss"` as a difficulty value** is not in the TS `Difficulty` enum. This works (bosses are excluded from rolled encounter pools, which is desirable) but is implicit. Either add `"boss"` to the enum or document the convention in code.
- **`tile` path inconsistency** — some records use `"game/monsters/<name>.png"` (path + extension), others use `"monsters/<name>"` (no prefix, no extension). The loader normalizes both but standardizing would reduce surprise.
- **Difficulty tier `"moderate"`** appears in some legacy text but the JSON uses `"normal"`. The TS enum is `"normal"`. No JSON change needed; just flagging.
