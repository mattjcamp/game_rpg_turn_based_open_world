# loot.json

## Purpose

A weighted random-draw table intended to drive chest contents — each entry is an `(item, weight)` pair, plus a `null` "empty chest" outcome. **Unused by the TypeScript implementation.** Chests in the TS port award gold only (no item drops), and post-combat item drops are computed from `counters.json` instead.

## Location

`data/loot.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only. Every field is currently `No`.

## File shape

Single top-level key `chest_loot` holding an array of weighted draw entries.

```
{
  "chest_loot": [
    { "item": <name> | null, "weight": <int> },
    ...
  ]
}
```

## Fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `chest_loot[]` | array | The complete weighted draw table | No |
| `chest_loot[].item` | string \| null | Item name from `items.json`, or `null` for "no drop" | No |
| `chest_loot[].weight` | int | Relative weight in a weighted random pick | No |

## Cross-references to other JSON files

Item name strings (`"Torch"`, `"Healing Herb"`, `"Broad Axe"`, etc.) would resolve against entries in `items.json` if the table were consumed. No TS code performs this lookup today.

## Example record

```json
{ "item": "Healing Herb", "weight": 5 }
```

## Notes and open questions

Two things to flag:

The TS chest-opening handler (`DungeonScene.ts:openChest`, around line 1127) currently awards `5 + rand(0..25)` gold and nothing else. If chests should drop items, this is the wiring target.

The post-combat loot pool (`web/src/game/world/Loot.ts`) is unrelated to this file — it draws from the `general`, `weapon`, and `armor` counter inventories in `counters.json`, with a flat 25% drop chance. So `counters.json` is the de facto loot table for combat drops.

If chests are meant to give items going forward, this file is the natural source. If they're not, this file is a deletion candidate.
