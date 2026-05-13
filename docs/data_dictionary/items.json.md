# items.json

## Purpose

The master item catalog — every weapon, armor piece, consumable, reagent, key, quest artifact, scroll, and miscellaneous object the game knows about. Each record carries the gameplay-relevant properties (damage, AC, slots, durability, ammo, price) plus rendering hints (icon, icon color).

## Location

`data/items.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "weapons": { "<name>": { ...item_record... }, ... },
  "armors":  { "<name>": { ... }, ... },
  "general": { "<name>": { ... }, ... }
}
```

Three category buckets, each keyed by display name. The TS loader (`Items.ts:232`, `loadItems`) flattens all three buckets into one `Map<string, Item>` and stamps a `category` discriminator (`"weapons"` / `"armors"` / `"general"`) onto each item.

## Top-level keys

| Key | Description |
|---|---|
| `weapons` | Melee and ranged weapons |
| `armors` | Body armor pieces |
| `general` | Everything else — consumables, ammo, reagents, scrolls, keys, quest items, tools |

## Item record fields

The shape is uniform across buckets; field presence varies by what the item does. The loader is permissive (missing fields take defaults) so most fields below are optional in any given record.

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `power` | number | Weapon damage; consumable potency (e.g. healing dice scalar) | Yes — `CombatBridge.ts:191`, `CombatActions.ts:624` |
| `ranged` | bool | Weapon is a ranged attack | Yes — `CombatActions.ts:325` (`isRanged`) |
| `melee` | bool | Weapon is a melee attack | Yes — defaults; `CombatBridge.ts:78` |
| `throwable` | bool | Eligible for the Throw action | Yes — `CombatActions.ts:315` |
| `slots` | string[] | Equip slots (`"right_hand"`, `"left_hand"`, `"body"`, `"head"`) | Yes — `Items.ts:152,258` |
| `description` | string | UI text | Yes |
| `icon` | string | Render glyph hint (e.g. `"sword"`, `"potion"`) | Yes — `Items.ts:63` |
| `item_type` | string | Gameplay subtype tag — drives bow ranges and some special-case checks | Yes — range lookup at `CombatActions.ts:338` |
| `party_can_equip` | bool | Eligible for a party-wide slot (banners and the like) | Yes |
| `character_can_equip` | bool | Eligible for a per-character equip slot | Yes — `Items.ts:261` |
| `buy` | number | Shop purchase price | Yes |
| `sell` | number | Shop sell-back price | Yes |
| `durability` | number | Max uses; 0 = indestructible | Yes — `PartyActions.ts:533` |
| `indestructible` | bool | Redundant with `durability: 0` | **No** — TS reads only `durability` |
| `ammo` | string | Item name of the ammo this weapon consumes | Yes — `Items.ts:89` |
| `evasion` | number | Armor AC base (replaces unarmored AC) | Yes — `CombatBridge.ts:87` |
| `ac_bonus` | number | Flat AC bonus added on top of any base | Yes — `CombatBridge.ts:49` |
| `bonus_damage` | string \| number | Extra dice on hit (e.g. `"1d6"`) | Yes — `CombatBridge.ts:191` |
| `damage_type` | string | Damage school (e.g. `"fire"`) | Yes — `CombatBridge.ts:192` |
| `grants_effect` | string | Effect ID conferred while equipped (see `effects.json`) | Yes — `PartyActions.ts:211` |
| `stat_bonuses` | object | Per-stat bonuses while equipped | **No** — present only on Sun Sword (`{}`); no TS reader |
| `on_hit` | `{ spell_id, chance }` | Proc spell on hit | **No** — present only on Sun Sword; no TS reader |
| `usable` | bool | Consumable | Yes — `Items.ts:228` |
| `combat_usable` | bool | Usable mid-combat (default true) | Yes — `Items.ts:227` |
| `effect` | string | Effect tag for `usable` items — drives the consume handler | Yes — `CombatActions.ts:623` |
| `stackable` | bool | Stack copies in inventory | Yes — `Items.ts:210` |
| `charges` | number | Stack size or use count | Yes — `Items.ts:200` |
| `quest_item` | bool | Marks the item as a quest objective | Partial — referenced indirectly in `Towns.ts` NPC type list; the bool itself isn't read |
| `icon_color` | [int, int, int] | RGB tint for key/artifact icons | **No** — present on keys and Dragonheart; no TS reader |

Throwable-poison fields (present on `Lingering Venom`, `Paralytic Poison`, `Poison Vial`, `Weakening Poison`) — all dormant in TS today; the `combat_only` use-branch deals `power + 1d6` splash damage and ignores these:

| Field | Type | Used in web/? |
|---|---|---|
| `poison_type` | string | **No** |
| `poison_damage` | mixed | **No** |
| `poison_duration` | number | **No** |
| `poison_mp_drain` | number | **No** |
| `poison_debilitate` | bool | **No** |
| `save_dc` | number | **No** (for these throwables only) |

## Polymorphic discriminators

Two discriminators worth knowing about.

**Category** (`weapons` / `armors` / `general`) is set by which top-level bucket the entry sits in. It's stamped onto `Item.category` at `Items.ts:159`. No code switches on this explicitly; per-category shape is communicated through which fields are populated (e.g. `evasion` on armors, `power` on weapons/consumables).

**`item_type`** is a narrow discriminator inside the `general` bucket. `CombatActions.ts:337-346` (`maxRangeFor`) branches on `long_bow`, `crossbow`, `short_bow`, `sling`, and `rock` to set ranged-attack range. Other observed values (`antidote`, `potion`, `herb`, `reagent`, `quest_item`, `ammo`, `holy_water`, `bomb`, `scroll`, `torch`, `camping_supplies`, `lockpick`, `poison_potion`, `throwable`, `rope`) are mostly informational tags — only `quest_item` is referenced indirectly (through Towns NPC types).

**`effect`** is a discriminator for `usable` consumables. The switch in `CombatActions.ts:626-808` branches on: `heal_hp`, `heal_mp`, `cure_poison`, `buff_strength`, `buff_ac`, `combat_only`, plus a generic default. `rest` (Camping Supplies) is handled out-of-combat via `PartyActions.ts:1271`.

## Cross-references to other JSON files

`ammo: "Arrows"` / `"Bolts"` / `"Stones"` → other item names within this same file (general bucket).

`grants_effect: "sun_sword_aura"` → effect ID in `effects.json`.

Item names are referenced from many other data files:
- `counters.json` `items[]` stock lists (shop inventories)
- `potions.json` recipe `result_item` and `reagents` keys
- `party.json` `equipped.*` and `inventory[]` `item` strings
- `spawn_points.json` `loot[]`
- `monsters.json` does **not** reference items today (no monster-specific loot table in v1).

Spell ID references: Sun Sword's `on_hit.spell_id: "fireball"` would target a spell in `spells.json`. The hook is not wired in TS; see Notes.

## Example record

The Sun Sword — exercises every optional weapon field:

```json
"Sun Sword": {
  "power": 20,
  "ranged": false,
  "slots": ["right_hand","left_hand"],
  "description": "A radiant blade infused with solar energy...",
  "icon": "sword",
  "item_type": "sword",
  "party_can_equip": false,
  "character_can_equip": true,
  "durability": 0,
  "indestructible": true,
  "melee": false,
  "throwable": false,
  "buy": 0,
  "sell": 0,
  "damage_type": "fire",
  "bonus_damage": "1d6",
  "ac_bonus": 0,
  "stat_bonuses": {},
  "grants_effect": "sun_sword_aura",
  "on_hit": { "spell_id": "fireball", "chance": 0.25 }
}
```

## Notes and open questions

A reasonable cleanup pass would land here, since the catalog is large and several fields are dormant. The most material observations:

`indestructible: true/false` is redundant with `durability: 0`. The TS code reads only `durability`. The redundant field can be removed.

`stat_bonuses: {}` and `on_hit: { spell_id, chance }` exist only on the Sun Sword and have no TS reader. They look like placeholder hooks for future passive stat bonuses and proc effects. If those features aren't on the near-term roadmap, the fields are removable.

`melee: false` is set on weapons that are clearly melee (Sword, Iron Sword, Mace, Sun Sword, Halberd, Spear). The TS default in `CombatBridge.ts` treats anything not `ranged` as melee for stat-modifier selection, so the `melee` flag is purely descriptive. The values are inconsistent across records; if you want to keep the field, normalize them.

The throwable-poison subfields (`poison_type`, `poison_damage`, `poison_duration`, `poison_mp_drain`, `poison_debilitate`, `save_dc`) on the four poison-throwable items are all dead — the `combat_only` use-branch deals only `power + 1d6` splash. The DOT, MP drain, and debilitate variants aren't modeled. Either wire them or strip them.

`icon_color` (3-int RGB) on Keys of Shadow and Dragonheart has no TS reader.

`Scroll of Fire`, `Smoke Bomb`, `Rope`, and `Holy Water` exist as items but no `effect` handler implements their behaviors. They're inventory placeholders.

Sun Sword's `on_hit.spell_id: "fireball"` is doubly broken: not only is the hook unwired, but `spells.json`'s `id: "fireball"` is actually Magic Dart in current data (the AOE Fireball uses `id: "fireball_aoe"`). If/when this is wired up, point at `fireball_aoe`.
