# counters.json

## Purpose

Defines the shops and temples encountered behind town counters — armor shop, general store, mage guild, healing temple, inn, magic shop, reagent shop, weapon shop. Each "counter" has a display name and either a stock list (regular shops) or a service menu (temple). This file is also the de facto source of the **post-combat item drop pool** — `web/src/game/world/Loot.ts` builds drops from the `general`, `weapon`, and `armor` counters' inventories.

## Location

`data/counters.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "armor":   { ...counter_record... },
  "general": { ... },
  "guild":   { ... },
  "healing": { ... },
  "inn":     { ... },
  "magic":   { ... },
  "reagent": { ... },
  "weapon":  { ... }
}
```

Object keyed by shop type. The key is the counter's identity — NPCs and counter tiles reference it.

## Counter record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Display label shown as the shop UI title | Yes — `Counters.ts:71` |
| `description` | string | Flavor text shown under the title | Yes — `Counters.ts:72` |
| `items` | string[] | Stock list — each entry is an item name from `items.json`. Duplicates are intentional (control weighting / scarcity). Empty for service-only counters. | Yes — `Counters.ts:73`; seeded into per-counter live inventory via `getOrSeedShopStock` (`TownActions.ts:200-214`); also feeds `buildLootPool` in `Loot.ts:38-52` |
| `kind` | string \| omitted | Discriminator — `"service"` for temple-style counters, omitted for regular shops | Yes — `TownScene.ts:2268,2298,2586` |
| `services` | object[] \| omitted | Service menu entries (only present when `kind === "service"`) | Yes — `Counters.ts:75-80`; consumed by `performTempleService` (`TownActions.ts:225+`) |

## `services[]` entry (service counters only)

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `id` | string | Service identifier — must match a handler in `performTempleService` | Yes |
| `name` | string | Display name in the menu | Yes |
| `description` | string | Tooltip / description text | Yes |
| `cost` | int | Gold cost for the service | Yes |

Recognized service IDs (handlers in `TownActions.ts:225+`): `heal_all_hp`, `restore_all_mp`, `cure_all_poisons`, `raise_dead`. Unknown IDs fall through politely.

## Cross-references to other JSON files

`items[]` strings are looked up in `items.json`. `buildLootPool` (`Loot.ts:47`) guards with `items.has(name)`, so unknown names are silently dropped from the loot pool — useful to know if a drop "disappears."

Counter keys (`general`, `weapon`, etc.) are referenced from:
- NPC `shopType` fields in `web/public/data/towns.json` (modules' towns file, `Towns.ts:40`)
- Counter tile resolution via `interaction_data` in `tile_defs.json` (`TileMap.ts:170`, `Tiles.ts:125`)

The post-combat loot pool reads exactly three counters: `general`, `weapon`, `armor` (the `LOOT_SHOP_TYPES` constant at `Loot.ts:22`). The other four (`magic`, `reagent`, `guild`, `inn`, `healing`) are excluded from drops.

## Example record

The healing temple (service counter, showcases `kind` + `services`):

```json
"healing": {
  "name": "Healing Counter",
  "description": "A temple healer who mends flesh, restores the arcane, purges poison, and — for a price — returns the dead to life.",
  "items": [],
  "kind": "service",
  "services": [
    { "id": "heal_all_hp",      "name": "Heal All HP",      "description": "Restore every living member to full hit points.",      "cost": 100 },
    { "id": "restore_all_mp",   "name": "Restore All MP",   "description": "Refill every living member's magic points.",            "cost": 75 },
    { "id": "cure_all_poisons", "name": "Cure All Poisons", "description": "Cleanse poison from every party member.",               "cost": 50 },
    { "id": "raise_dead",       "name": "Raise Dead",       "description": "Return a fallen ally to full health. Costly miracle.",  "cost": 1000 }
  ]
}
```

## Notes and open questions

This file is doing double duty as both the shop system and the loot system, which is a useful efficiency but worth being aware of when editing. If you remove an item from `general.items`, you remove it from both the store stock and the post-combat drop pool.

`cure_all_poisons` and `raise_dead` are wired in TS but partially stubbed (per the comment at `TownActions.ts:258-259`): poison status isn't modeled on `PartyMember` in the web port yet, so the service refuses cleanly rather than mutating state.

The `inn` counter has a stock list (`Healing Herb`, `Camping Supplies`) but no special `kind`, so it's treated as a regular shop. There is no "sleep at the inn" handler driven by this file in TS — that flow lives elsewhere if it exists.

Item-name duplicates in `items[]` are the stocking mechanism: buying removes one entry from the live stock array (which is a mutable reference returned by `getOrSeedShopStock` at `TownActions.ts:200-214`). So `["Sword", "Sword", "Mace"]` means two Swords and one Mace in stock.

`healing.items` is `[]` (empty array) rather than omitted, which is the right convention for service counters with no purchasable goods. Stay consistent if you add new service counters.
