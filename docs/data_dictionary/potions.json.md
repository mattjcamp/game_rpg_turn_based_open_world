# potions.json

## Purpose

Defines alchemy crafting recipes — each recipe lists the reagents (and quantities) required, a difficulty class for the alchemy check, and the resulting item. The file also carries a top-level reagent master-list, but the master-list is currently unused by the TS implementation.

## Location

`data/potions.json`

## Scope of this document

The "Used?" column reflects the TypeScript implementation under `web/` only.

## File shape

```
{
  "_comment": "...",
  "recipes": {
    "<RecipeName>": { ...recipe_record... },
    ...
  },
  "reagents": [ "<item_name>", ... ]
}
```

`recipes` is keyed by recipe name (e.g. `"Healing Potion"`, `"Fire Oil"`). The outer key serves as the recipe ID. `reagents` is a flat array of item names declared as valid reagents.

## Top-level fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `_comment` | string | Author note | No |
| `recipes` | object | Recipe collection keyed by name | Yes — `Potions.ts:85` |
| `reagents` | string[] | Master list of valid reagent item names | **No** — `Potions.ts:84` parses only `raw.recipes` |

## Recipe record fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `name` | string | Display name (always matches the outer key in current data) | Yes — `Potions.ts:62` |
| `description` | string | Tooltip text in the recipe picker | Yes |
| `reagents` | object<string, int> | Required materials map: `{ "<item_name>": <quantity> }` | Yes — `Potions.ts:64,154,238` |
| `dc` | int | INT-check difficulty class for the alchemy attempt | Yes — `Potions.ts:65,244` |
| `result_item` | string | Name of the item produced on success | Yes — `Potions.ts:66,254` |
| `result_count` | int (default 1) | Number of copies produced on success | Yes — `Potions.ts:67,252` |
| `category` | string | Recipe category for future UI filters | **Partial** — preserved on the recipe model but no UI consumes it yet (per code comment at `Potions.ts:37-39`); observed values: `"restoration"`, `"offensive"`, `"enhancement"` |

## Cross-references to other JSON files

`recipes.<X>.reagents` keys (e.g. `"Moonpetal"`, `"Spring Water"`, `"Glowcap Mushroom"`, `"Serpent Root"`, `"Brimite Ore"`) are item names from `items.json`'s `general` bucket (typically with `item_type: "reagent"`). The reagent count lookup walks `party.inventory` by item name (`Potions.ts:115`).

`result_item` → item name in `items.json`. In current data the result name always equals the recipe key.

The root-level `reagents` array is conceptually a cross-reference to `items.json` (the canonical list of valid reagents) but the TS code doesn't enforce this. It's authoring documentation today.

## Example record

```json
"Fire Oil": {
  "name": "Fire Oil",
  "description": "A volatile oil that can be thrown to create a burst of flame.",
  "reagents": { "Brimite Ore": 1, "Glowcap Mushroom": 1 },
  "dc": 12,
  "result_item": "Fire Oil",
  "result_count": 1,
  "category": "offensive"
}
```

## Notes and open questions

The recipe schema is clean — no polymorphism, no surprises. A couple of small issues worth flagging:

The root-level `reagents` array is dead data in TS. It looks like it should be a validation contract (no recipe should reference an unknown reagent), but no code enforces it. Either wire it as a validation step or remove it from the schema; until then it's misleading.

The outer recipe key and the inner `name` field are always identical in current data. The loader uses the outer key as the recipe ID. The redundancy isn't harmful but it's a small foot-gun if an author renames one without the other.

`category` accepts only three observed values today but the type is open string. Typo risk; no enum enforcement.

All current recipes produce `result_count: 1`. The field is generic but the multi-output case isn't exercised in production data — if you add a recipe with `result_count > 1`, double-check it actually drops the expected count into the stash via `addToStash` at `Potions.ts:254`.

`_comment` is documentation; no TS reader.
