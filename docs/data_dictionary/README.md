# Data dictionary

This folder documents the JSON configuration files under `data/` — what each file is for, what the fields mean, and whether they're actually consumed by the canonical TypeScript + Phaser implementation under `web/`. The legacy Python codebase under `src/` is out of scope; "Used?" columns reflect the TS build only.

## How to read these docs

Each entity (one JSON file, or in the case of classes one folder) gets a markdown doc with a consistent structure: purpose, file shape, field tables (with a "Used?" column), polymorphic discriminators where relevant, cross-references to other JSON files, an example record, and a notes section that captures dead fields, schema inconsistencies, and cleanup candidates.

When you're looking up "what does field X in file Y mean," go straight to the field table. When you're trying to clean things up, scan the "Notes and open questions" sections — that's where the deletion candidates and wiring gaps live.

## Live entities (consumed by the TS build)

These files actively drive gameplay in `web/`.

| File | Doc | Purpose |
|---|---|---|
| `data/monsters.json` | [monsters.md](monsters.md) | Monster catalog and inline spell/passive/on-hit definitions |
| `data/items.json` | [items.json.md](items.json.md) | Weapons, armor, consumables, reagents, quest items |
| `data/spells.json` | [spells.json.md](spells.json.md) | Player-facing spell list |
| `data/effects.json` | [effects.json.md](effects.json.md) | Party-wide status effects (Detect Traps, Infravision, …) |
| `data/potions.json` | [potions.json.md](potions.json.md) | Alchemy recipes |
| `data/encounters.json` | [encounters.json.md](encounters.json.md) | Encounter rosters by area (overworld / dungeon / house_basement) |
| `data/spawn_points.json` | [spawn_points.json.md](spawn_points.json.md) | Monster lair behavior keyed by tile ID |
| `data/counters.json` | [counters.json.md](counters.json.md) | Shop and temple counters; also the source of post-combat loot drops |
| `data/tile_defs.json` | [tile_defs.json.md](tile_defs.json.md) | Canonical tile catalog — source of truth for tile IDs |
| `data/party.json` | [party.json.md](party.json.md) | Starting party save-game seed |
| `data/classes/*.json` | [classes.md](classes.md) | The eight playable classes (shared schema) |

## Partial / mostly-dead entities

These files have a few fields wired but most of the schema is documentation-only.

| File | Doc | What's actually live |
|---|---|---|
| `data/races.json` | [races.json.md](races.json.md) | Only Human's `exp_per_level` is consumed; `stat_modifiers` and `effects` are duplicated as TS constants |

## Dead entities (not consumed by the TS build)

These files survive from the legacy Python codebase or its editors. The TS build doesn't fetch them; the schemas are documented for reference and to support future re-wiring decisions.

| File | Doc | Why it's dead |
|---|---|---|
| `data/config.json` | [config.json.md](config.json.md) | Every flag is hardcoded in TS source |
| `data/loot.json` | [loot.json.md](loot.json.md) | Chest loot — TS chests give gold only; combat drops come from `counters.json` |
| `data/u4_tiles.json` | [u4_tiles.json.md](u4_tiles.json.md) | Legacy Ultima IV atlas index; TS serves PNGs directly |
| `data/tile_manifest.json` | [tile_manifest.json.md](tile_manifest.json.md) | Legacy editor sprite catalog; superseded by `tile_defs.json` |
| `data/unique_tiles.json` | [unique_tiles.json.md](unique_tiles.json.md) | No unique-tile loader in TS |
| `data/reusable_features.json` | [reusable_features.json.md](reusable_features.json.md) | Python feature-editor palette |
| `data/map_templates.json` | [map_templates.json.md](map_templates.json.md) | Python map-editor palette |
| `data/town_templates.json` | [town_templates.json.md](town_templates.json.md) | Python town-editor palette |

## Cross-file relationships at a glance

The live data graph in the TS build looks roughly like this:

- `monsters.json` is the catalog. It's referenced by:
  - `encounters.json` (monster names in rosters)
  - `spawn_points.json` (`spawn_monsters`, `boss_monsters`)
- `items.json` is the catalog. It's referenced by:
  - `counters.json` (shop stock + loot pool)
  - `potions.json` (recipe reagents and results)
  - `party.json` (equipped gear, inventory)
  - `spawn_points.json` (`loot[]`)
  - `effects.json` is referenced from `items.json` via `grants_effect` (currently only Sun Sword)
- `spells.json` references class names from `data/classes/*.json`.
- `tile_defs.json` is the tile-ID source of truth — referenced by every map data file (module town and dungeon files), `spawn_points.json` (numeric keys), and `counters.json` (via tile `interaction_data`).
- `party.json` ties most of the catalogs together — its roster references classes and races, its inventory and equipment reference items, and its effect slots reference effects.

`monsters.json`'s `tile` field is a sprite-path string, **not** a tile ID — it bypasses `tile_defs.json` entirely.

## Common cleanup candidates flagged across files

This is a digest of the deletion / wiring candidates surfaced in the individual docs. None of these are recommendations to act now — they're a punch list for a future cleanup pass.

Fields parsed onto runtime models but never read:

- `monsters.json` — `description`, the entire `ranged` sub-object, `spawn_weight`, the top-level `spawn_tables` block
- `items.json` — `indestructible`, `stat_bonuses` (Sun Sword), `on_hit` (Sun Sword), `icon_color` (keys), the throwable-poison subfields
- `spells.json` — `min_damage`, `min_heal`, the legacy `dice` string (now redundant with `dice_count`/`dice_sides`), most `icon` values
- `effects.json` — `aura_color`, `aura_pulse_hz`, `aura_radius` (Sun Sword aura)
- `classes/*.json` — `_comment`, `allowed_weapons`, `allowed_armor`, `spell_type`, `mp_source.percentage`, `mp_regen_multiplier`
- `races.json` — `description`, `stat_modifiers`, `effects` (all duplicated as TS constants)
- `potions.json` — root-level `reagents` master list (dead validation contract)
- `party.json` — `gender`, `equipped.left_hand`, `equipped.head` (legacy slots silently migrated out)
- `spawn_points.json` — `background_tile`

Polymorphic types referenced but lacking handlers in TS:

- `monsters.json` `on_hit_effects` types `poison` and `slow`
- `monsters.json` `passives.poison_immunity` (parsed but no consumer)
- `monsters.json` spell type `poison` (in known set but no cast handler)
- `items.json` `effect` values without handlers (Scroll of Fire, Smoke Bomb, Rope, Holy Water)

Entire files that are candidates for deletion if the legacy Python editors are retired:

- `config.json`, `loot.json`, `u4_tiles.json`, `tile_manifest.json`, `unique_tiles.json`, `reusable_features.json`, `map_templates.json`, `town_templates.json`

Schema inconsistencies worth normalizing:

- `monsters.json` — `tile` paths inconsistent (some `"game/monsters/<name>.png"`, some `"monsters/<name>"`)
- `monsters.json` — `"boss"` difficulty exists in JSON but isn't in the TS `Difficulty` enum
- `classes/*.json` — `allowed_weapons` / `allowed_armor` sometimes `"all"` (string), sometimes an array
- `spells.json` — `duration: "10"` (string) on Push while every other numeric duration is a number
- `spells.json` — `hit_sfx` sometimes `""`, sometimes `null`
- `spells.json` — `id: "fireball"` is actually Magic Dart; the real Fireball has `id: "fireball_aoe"`
- `map_templates.json` — `"Capital CIty"` (sic) misspelling
