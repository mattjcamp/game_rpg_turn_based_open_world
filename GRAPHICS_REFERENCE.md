# Graphics Reference — Realm of Shadow

This document catalogs every graphic used in the game, displayed at the in-game scale of 32×32 pixels, grouped by how they are used. Use this as a reference when reskinning or adding new assets.

Source art is 16×16 pixels. The renderer scales everything to 32×32 at runtime (`TILE_SIZE = 32` in `src/settings.py`).

---

## Table of Contents

1. [Tile Sheet (Overworld & Town)](#1-tile-sheet-overworld--town)
2. [Character Sprites — Amiga](#2-character-sprites--amiga)
3. [Character Sprites — U4 Style](#3-character-sprites--u4-style)
4. [Character Sprites — VGA (Steele)](#4-character-sprites--vga-steele)
5. [Monster Sprites](#5-monster-sprites)
6. [NPC Sprites](#6-npc-sprites)
7. [Overworld Special Tiles](#7-overworld-special-tiles)
8. [Item & Object Sprites](#8-item--object-sprites)
9. [Environment & Terrain Sprites](#9-environment--terrain-sprites)
10. [Unassigned Graphics](#10-unassigned-graphics)

---

## 1. Tile Sheet (Overworld & Town)

The master tile sheet `src/assets/U3TilesE.gif` contains 80 tiles (16 columns × 5 rows). Source tiles are 16×16, scaled to 32×32 at runtime. The renderer indexes tiles by `(row, col)` position. Individual tiles have been extracted to `src/assets/tile_sheet_extracted/` for reference.

**Overworld tile assignments** (from `_overworld_tile_map` in `renderer.py`):

| Preview | Tile | Sheet Position | Constant | Usage |
|---------|------|---------------|----------|-------|
| <img src="src/assets/tile_sheet_extracted/water_0_0.png" width="32" height="32"> | Water | (0, 0) | `TILE_WATER` | Ocean, lakes — non-walkable |
| <img src="src/assets/tile_sheet_extracted/grass_0_1.png" width="32" height="32"> | Grass | (0, 1) | `TILE_GRASS` | Open plains — walkable |
| <img src="src/assets/tile_sheet_extracted/path_0_2.png" width="32" height="32"> | Path | (0, 2) | `TILE_PATH` | Roads between towns — walkable |
| <img src="src/assets/tile_sheet_extracted/forest_0_3.png" width="32" height="32"> | Forest | (0, 3) | `TILE_FOREST` | Wooded areas — walkable |
| <img src="src/assets/tile_sheet_extracted/mountain_0_4.png" width="32" height="32"> | Mountain | (0, 4) | `TILE_MOUNTAIN` | Rocky peaks — non-walkable |
| <img src="src/assets/tile_sheet_extracted/dungeon_0_5.png" width="32" height="32"> | Dungeon | (0, 5) | `TILE_DUNGEON` | Dungeon entrance — walkable |
| <img src="src/assets/tile_sheet_extracted/town_0_6.png" width="32" height="32"> | Town | (0, 6) | `TILE_TOWN` | Town entrance — walkable |
| <img src="src/assets/tile_sheet_extracted/chest_0_9.png" width="32" height="32"> | Chest | (0, 9) | `TILE_CHEST` | Treasure chest — walkable |

**Town interior tile assignments** (from `_town_tile_map` in `renderer.py`):

| Preview | Tile | Sheet Position | Constant | Usage |
|---------|------|---------------|----------|-------|
| <img src="src/assets/tile_sheet_extracted/grass_0_1.png" width="32" height="32"> | Floor | (0, 1) | `TILE_FLOOR` | Interior floor — walkable |
| <img src="src/assets/tile_sheet_extracted/wall_0_8.png" width="32" height="32"> | Wall | (0, 8) | `TILE_WALL` | Interior wall — non-walkable |
| <img src="src/assets/tile_sheet_extracted/chest_0_9.png" width="32" height="32"> | Chest | (0, 9) | `TILE_CHEST` | Shop chest — walkable |
| <img src="src/assets/tile_sheet_extracted/town_0_6.png" width="32" height="32"> | Exit | (0, 6) | `TILE_EXIT` | Town exit point — walkable |

**Dungeon tiles** are rendered procedurally with colored rectangles rather than sprite sheet tiles. The tile types (`TILE_DFLOOR`, `TILE_DWALL`, `TILE_STAIRS`, etc.) use fallback colors defined in `settings.py`.

---

## 2. Character Sprites — Amiga

Larger sprites (~28–34px) from the original Amiga version of Ultima III. Used as the primary sprites for these five classes. Located in `example_graphics/` (referenced by `character_tiles.json`).

| Preview | File | Class |
|---------|------|-------|
| <img src="research/example_graphics/Ultima3_AMI_sprite_fighter.png" width="32" height="32"> | `Ultima3_AMI_sprite_fighter.png` | Fighter |
| <img src="research/example_graphics/Ultima3_AMI_sprite_cleric.png" width="32" height="32"> | `Ultima3_AMI_sprite_cleric.png` | Cleric |
| <img src="research/example_graphics/Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png" width="32" height="32"> | `Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png` | Wizard |
| <img src="research/example_graphics/Ultima3_AMI_sprite_thief.png" width="32" height="32"> | `Ultima3_AMI_sprite_thief.png` | Thief |
| <img src="research/example_graphics/Ultima3_AMI_sprite_barbarian.png" width="32" height="32"> | `Ultima3_AMI_sprite_barbarian.png` | Barbarian |

These same files are also available in `src/assets/` for the renderer:

| Preview | File | Class |
|---------|------|-------|
| <img src="src/assets/Ultima3_AMI_sprite_fighter.png" width="32" height="32"> | `Ultima3_AMI_sprite_fighter.png` | Fighter |
| <img src="src/assets/Ultima3_AMI_sprite_cleric.png" width="32" height="32"> | `Ultima3_AMI_sprite_cleric.png` | Cleric |
| <img src="src/assets/Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png" width="32" height="32"> | `Ultima3_AMI_sprite_wizard-alcmt-ilsnt.png` | Wizard / Alchemist / Illusionist |
| <img src="src/assets/Ultima3_AMI_sprite_thief.png" width="32" height="32"> | `Ultima3_AMI_sprite_thief.png` | Thief |
| <img src="src/assets/Ultima3_AMI_sprite_barbarian.png" width="32" height="32"> | `Ultima3_AMI_sprite_barbarian.png` | Barbarian |

---

## 3. Character Sprites — U4 Style

16×16 pixel tiles from the Ultima IV tileset, used as fallback class sprites and for character creation. Located in `src/assets/u4_tiles/`. Black pixels are made transparent at load time.

**Class sprites** (mapped in `renderer.py`):

| Preview | File | Class |
|---------|------|-------|
| <img src="src/assets/u4_tiles/healer_alt_f1.png" width="32" height="32"> | `healer_alt_f1.png` | Alchemist |
| <img src="src/assets/u4_tiles/mage.png" width="32" height="32"> | `mage.png` | Illusionist / Mage |
| <img src="src/assets/u4_tiles/druid.png" width="32" height="32"> | `druid.png` | Druid |
| <img src="src/assets/u4_tiles/paladin.png" width="32" height="32"> | `paladin.png` | Paladin |
| <img src="src/assets/u4_tiles/ranger.png" width="32" height="32"> | `ranger.png` | Ranger |
| <img src="src/assets/u4_tiles/bard.png" width="32" height="32"> | `bard.png` | Lark / Bard |

**Additional character creation tiles** (from `character_tiles.json`):

| Preview | File | Name |
|---------|------|------|
| <img src="src/assets/u4_tiles/ranger_alt.png" width="32" height="32"> | `ranger_alt.png` | Ranger Alt |
| <img src="src/assets/u4_tiles/monk.png" width="32" height="32"> | `monk.png` | Monk |
| <img src="src/assets/u4_tiles/tinker.png" width="32" height="32"> | `tinker.png` | Tinker |
| <img src="src/assets/u4_tiles/shepherd.png" width="32" height="32"> | `shepherd.png` | Shepherd |
| <img src="src/assets/u4_tiles/avatar_f1.png" width="32" height="32"> | `avatar_f1.png` | Avatar |
| <img src="src/assets/u4_tiles/knight_f1.png" width="32" height="32"> | `knight_f1.png` | Knight |
| <img src="src/assets/u4_tiles/guard_f1.png" width="32" height="32"> | `guard_f1.png` | Guard |
| <img src="src/assets/u4_tiles/healer_f1.png" width="32" height="32"> | `healer_f1.png` | Healer |
| <img src="src/assets/u4_tiles/jester_f1.png" width="32" height="32"> | `jester_f1.png` | Jester |
| <img src="src/assets/u4_tiles/villager_male.png" width="32" height="32"> | `villager_male.png` | Villager |
| <img src="src/assets/u4_tiles/villager_female.png" width="32" height="32"> | `villager_female.png` | Villager F |
| <img src="src/assets/u4_tiles/child_f1.png" width="32" height="32"> | `child_f1.png` | Child |
| <img src="src/assets/u4_tiles/beggar_f1.png" width="32" height="32"> | `beggar_f1.png` | Beggar |
| <img src="src/assets/u4_tiles/citizen_f1.png" width="32" height="32"> | `citizen_f1.png` | Citizen |
| <img src="src/assets/u4_tiles/guard_npc.png" width="32" height="32"> | `guard_npc.png` | Guard Alt |

---

## 4. Character Sprites — VGA (Steele)

Higher-detail VGA sprites by Joshua Steele. Used for NPCs, character creation, and villager assignments. Located in `src/assets/steele_tiles/`.

| Preview | File | Name | Usage |
|---------|------|------|-------|
| <img src="src/assets/steele_tiles/vga_avatar_f1.png" width="32" height="32"> | `vga_avatar_f1.png` | VGA Avatar | Character creation |
| <img src="src/assets/steele_tiles/vga_mage_f1.png" width="32" height="32"> | `vga_mage_f1.png` | VGA Mage | Character creation |
| <img src="src/assets/steele_tiles/vga_bard_f1.png" width="32" height="32"> | `vga_bard_f1.png` | VGA Bard | Innkeeper NPC, character creation |
| <img src="src/assets/steele_tiles/vga_fighter_f1.png" width="32" height="32"> | `vga_fighter_f1.png` | VGA Fighter | Character creation |
| <img src="src/assets/steele_tiles/vga_druid_f1.png" width="32" height="32"> | `vga_druid_f1.png` | VGA Druid | Character creation |
| <img src="src/assets/steele_tiles/vga_tinker_f1.png" width="32" height="32"> | `vga_tinker_f1.png` | VGA Tinker | Shopkeeper NPC, character creation |
| <img src="src/assets/steele_tiles/vga_paladin_f1.png" width="32" height="32"> | `vga_paladin_f1.png` | VGA Paladin | Character creation |
| <img src="src/assets/steele_tiles/vga_ranger_f1.png" width="32" height="32"> | `vga_ranger_f1.png` | VGA Ranger | Character creation |
| <img src="src/assets/steele_tiles/vga_shepherd_f1.png" width="32" height="32"> | `vga_shepherd_f1.png` | VGA Shepherd | Villager pool, character creation |
| <img src="src/assets/steele_tiles/vga_guard_f1.png" width="32" height="32"> | `vga_guard_f1.png` | VGA Guard | Villager pool, character creation |
| <img src="src/assets/steele_tiles/vga_citizen_f1.png" width="32" height="32"> | `vga_citizen_f1.png` | VGA Citizen | Villager pool, character creation |
| <img src="src/assets/steele_tiles/vga_singing_bard_f1.png" width="32" height="32"> | `vga_singing_bard_f1.png` | VGA Singing Bard | Villager pool, character creation |
| <img src="src/assets/steele_tiles/vga_jester_f1.png" width="32" height="32"> | `vga_jester_f1.png` | VGA Jester | Character creation |
| <img src="src/assets/steele_tiles/vga_beggar_f1.png" width="32" height="32"> | `vga_beggar_f1.png` | VGA Beggar | Villager pool, character creation |
| <img src="src/assets/steele_tiles/vga_child_f1.png" width="32" height="32"> | `vga_child_f1.png` | VGA Child | Villager pool, character creation |
| <img src="src/assets/steele_tiles/vga_lord_f1.png" width="32" height="32"> | `vga_lord_f1.png` | VGA Lord | Elder NPC, character creation |
| <img src="src/assets/steele_tiles/vga_rogue_f1.png" width="32" height="32"> | `vga_rogue_f1.png` | VGA Rogue | Character creation |
| <img src="src/assets/steele_tiles/vga_evil_mage_f1.png" width="32" height="32"> | `vga_evil_mage_f1.png` | VGA Evil Mage | Character creation |

---

## 5. Monster Sprites

Monster tiles loaded from `data/monsters.json`. Each monster has a `"tile"` field pointing to a file in `src/assets/`. Displayed in combat arenas at 32×32.

| Preview | File | Monster(s) |
|---------|------|-----------|
| <img src="src/assets/giant_rat_f1.png" width="32" height="32"> | `giant_rat_f1.png` | Giant Rat |
| <img src="src/assets/skeleton_f1.png" width="32" height="32"> | `skeleton_f1.png` | Skeleton, Skeleton Archer |
| <img src="src/assets/orc_f1.png" width="32" height="32"> | `orc_f1.png` | Orc, Orc Shaman |
| <img src="src/assets/goblin_f1.png" width="32" height="32"> | `goblin_f1.png` | Goblin |
| <img src="src/assets/zombie_f1.png" width="32" height="32"> | `zombie_f1.png` | Zombie |
| <img src="src/assets/wolf_f1.png" width="32" height="32"> | `wolf_f1.png` | Wolf |
| <img src="src/assets/dark_mage_f1.png" width="32" height="32"> | `dark_mage_f1.png` | Dark Mage |
| <img src="src/assets/troll_f1.png" width="32" height="32"> | `troll_f1.png` | Troll |

---

## 6. NPC Sprites

NPCs in towns use VGA Steele sprites assigned by role. The renderer maps NPC types to specific sprites.

| Preview | File | NPC Role | Color Code |
|---------|------|----------|------------|
| <img src="src/assets/steele_tiles/vga_tinker_f1.png" width="32" height="32"> | `vga_tinker_f1.png` | Shopkeeper | Gold (200, 160, 60) |
| <img src="src/assets/steele_tiles/vga_bard_f1.png" width="32" height="32"> | `vga_bard_f1.png` | Innkeeper | Blue (60, 160, 200) |
| <img src="src/assets/steele_tiles/vga_lord_f1.png" width="32" height="32"> | `vga_lord_f1.png` | Elder | Purple (180, 80, 200) |

**Villager pool** — randomly assigned via `hash(npc.name) % 6`:

| Preview | File |
|---------|------|
| <img src="src/assets/steele_tiles/vga_citizen_f1.png" width="32" height="32"> | `vga_citizen_f1.png` |
| <img src="src/assets/steele_tiles/vga_shepherd_f1.png" width="32" height="32"> | `vga_shepherd_f1.png` |
| <img src="src/assets/steele_tiles/vga_singing_bard_f1.png" width="32" height="32"> | `vga_singing_bard_f1.png` |
| <img src="src/assets/steele_tiles/vga_guard_f1.png" width="32" height="32"> | `vga_guard_f1.png` |
| <img src="src/assets/steele_tiles/vga_beggar_f1.png" width="32" height="32"> | `vga_beggar_f1.png` |
| <img src="src/assets/steele_tiles/vga_child_f1.png" width="32" height="32"> | `vga_child_f1.png` |

**Additional NPC sprites** (from `character_tiles.json`):

| Preview | File | Name |
|---------|------|------|
| <img src="src/assets/npc_townsfolk.png" width="32" height="32"> | `npc_townsfolk.png` | Townsfolk |
| <img src="src/assets/lark_f1.png" width="32" height="32"> | `lark_f1.png` | Lark Alt |
| <img src="src/assets/pirate_brigand_f1.png" width="32" height="32"> | `pirate_brigand_f1.png` | Brigand |

---

## 7. Overworld Special Tiles

Unique overworld locations defined in `data/unique_tiles.json`. These sprites overlay the base terrain tile when a special location is present. Loaded via `_get_unique_tile_sprite()` in the renderer.

| Preview | File | Unique Tile | Description |
|---------|------|-------------|-------------|
| <img src="src/assets/moongate_active.png" width="32" height="32"> | `moongate_active.png` | Moongate, Seal of Binding | Active teleportation portal |
| <img src="src/assets/moongate_portal.png" width="32" height="32"> | `moongate_portal.png` | Dormant Moongate | Inactive portal stones |
| <img src="src/assets/castle.png" width="32" height="32"> | `castle.png` | Ruined Tower | Landmark structure |
| <img src="src/assets/pirate_ship.png" width="32" height="32"> | `pirate_ship.png` | Sunken Shipwreck | Coastal point of interest |
| <img src="src/assets/lava_fire_field.png" width="32" height="32"> | `lava_fire_field.png` | Lava Vent | Hazardous terrain |
| <img src="src/assets/dungeon_entrance.png" width="32" height="32"> | `dungeon_entrance.png` | Smuggler's Tunnel | Hidden passage |
| <img src="src/assets/poison_flames.png" width="32" height="32"> | `poison_flames.png` | Poison Swamp | Toxic hazard |
| <img src="src/assets/treasure_chest.png" width="32" height="32"> | `treasure_chest.png` | Hidden Treasure Hoard | Discoverable loot |

---

## 8. Item & Object Sprites

Special object tiles used for interactive elements in towns and dungeons.

| Preview | File | Usage |
|---------|------|-------|
| <img src="src/assets/chest_tile.png" width="32" height="32"> | `chest_tile.png` | Treasure chest (towns & dungeons) |
| <img src="src/assets/town_gate.png" width="32" height="32"> | `town_gate.png` | Town entrance gate |

---

## 9. Environment & Terrain Sprites

These tiles from the U3TilesE.gif tile sheet serve as the base terrain for overworld and town rendering. The full sheet provides 80 tiles; rows 1–4 contain additional terrain variants, decorative tiles, and structures available for future use. See [Section 1](#1-tile-sheet-overworld--town) for the currently assigned positions.

---

## 10. Unassigned Graphics

The following 308 image files exist in the assets directories but are **not currently referenced** by any code or JSON configuration. They are available for use in new monsters, characters, animations, terrain, or reskins.

### Custom Sprites (`src/assets/`)

| Preview | File | Likely Purpose |
|---------|------|----------------|
| <img src="src/assets/balron_demon_f1.png" width="32" height="32"> | `balron_demon_f1.png` | Monster — demon (frame 1) |
| <img src="src/assets/balron_demon_f2.png" width="32" height="32"> | `balron_demon_f2.png` | Monster — demon (frame 2) |
| <img src="src/assets/barbarian_f1.png" width="32" height="32"> | `barbarian_f1.png` | Character — barbarian alt (frame 1) |
| <img src="src/assets/barbarian_f2.png" width="32" height="32"> | `barbarian_f2.png` | Character — barbarian alt (frame 2) |
| <img src="src/assets/brick_wall.png" width="32" height="32"> | `brick_wall.png` | Environment — brick wall |
| <img src="src/assets/brush_scrubland.png" width="32" height="32"> | `brush_scrubland.png` | Environment — scrubland terrain |
| <img src="src/assets/cleric_f1.png" width="32" height="32"> | `cleric_f1.png` | Character — cleric alt (frame 1) |
| <img src="src/assets/cleric_f2.png" width="32" height="32"> | `cleric_f2.png` | Character — cleric alt (frame 2) |
| <img src="src/assets/cursor_sparkle.png" width="32" height="32"> | `cursor_sparkle.png` | UI — cursor effect |
| <img src="src/assets/daemon_f1.png" width="32" height="32"> | `daemon_f1.png` | Monster — daemon (frame 1) |
| <img src="src/assets/daemon_f2.png" width="32" height="32"> | `daemon_f2.png` | Monster — daemon (frame 2) |
| <img src="src/assets/dragon_f1.png" width="32" height="32"> | `dragon_f1.png` | Monster — dragon (frame 1) |
| <img src="src/assets/dragon_f2.png" width="32" height="32"> | `dragon_f2.png` | Monster — dragon (frame 2) |
| <img src="src/assets/fighter_f1.png" width="32" height="32"> | `fighter_f1.png` | Character — fighter alt (frame 1) |
| <img src="src/assets/fighter_f2.png" width="32" height="32"> | `fighter_f2.png` | Character — fighter alt (frame 2) |
| <img src="src/assets/forest.png" width="32" height="32"> | `forest.png` | Environment — forest terrain |
| <img src="src/assets/grass_plains.png" width="32" height="32"> | `grass_plains.png` | Environment — grass terrain |
| <img src="src/assets/horse.png" width="32" height="32"> | `horse.png` | Mount / vehicle |
| <img src="src/assets/illusionist_f1.png" width="32" height="32"> | `illusionist_f1.png` | Character — illusionist (frame 1) |
| <img src="src/assets/illusionist_f2.png" width="32" height="32"> | `illusionist_f2.png` | Character — illusionist (frame 2) |
| <img src="src/assets/island_jungle.png" width="32" height="32"> | `island_jungle.png` | Environment — jungle terrain |
| <img src="src/assets/lark_f2.png" width="32" height="32"> | `lark_f2.png` | Character — lark (frame 2) |
| <img src="src/assets/man_thing_f1.png" width="32" height="32"> | `man_thing_f1.png` | Monster — man-thing (frame 1) |
| <img src="src/assets/man_thing_f2.png" width="32" height="32"> | `man_thing_f2.png` | Monster — man-thing (frame 2) |
| <img src="src/assets/mountains.png" width="32" height="32"> | `mountains.png` | Environment — mountain terrain |
| <img src="src/assets/night_sky_stars.png" width="32" height="32"> | `night_sky_stars.png` | Environment — night sky background |
| <img src="src/assets/orc_f2.png" width="32" height="32"> | `orc_f2.png` | Monster — orc (frame 2) |
| <img src="src/assets/paladin_f1.png" width="32" height="32"> | `paladin_f1.png` | Character — paladin alt (frame 1) |
| <img src="src/assets/paladin_f2.png" width="32" height="32"> | `paladin_f2.png` | Character — paladin alt (frame 2) |
| <img src="src/assets/pirate_brigand_f2.png" width="32" height="32"> | `pirate_brigand_f2.png` | Character — brigand (frame 2) |
| <img src="src/assets/ship_frigate.png" width="32" height="32"> | `ship_frigate.png` | Vehicle — frigate ship |
| <img src="src/assets/shrine_church.png" width="32" height="32"> | `shrine_church.png` | Environment — church/shrine |
| <img src="src/assets/skeleton_f2.png" width="32" height="32"> | `skeleton_f2.png` | Monster — skeleton (frame 2) |
| <img src="src/assets/spritesheet.png" width="32" height="32"> | `spritesheet.png` | Sprite sheet — misc |
| <img src="src/assets/thief_f1.png" width="32" height="32"> | `thief_f1.png` | Character — thief alt (frame 1) |
| <img src="src/assets/thief_f2.png" width="32" height="32"> | `thief_f2.png` | Character — thief alt (frame 2) |
| <img src="src/assets/town_village.png" width="32" height="32"> | `town_village.png` | Environment — town/village |
| <img src="src/assets/void_empty.png" width="32" height="32"> | `void_empty.png` | Environment — void/empty space |
| <img src="src/assets/water_deep_ocean.png" width="32" height="32"> | `water_deep_ocean.png` | Environment — deep water |
| <img src="src/assets/whirlpool.png" width="32" height="32"> | `whirlpool.png` | Environment — whirlpool (frame 1) |
| <img src="src/assets/whirlpool_f2.png" width="32" height="32"> | `whirlpool_f2.png` | Environment — whirlpool (frame 2) |
| <img src="src/assets/wizard_f1.png" width="32" height="32"> | `wizard_f1.png` | Character — wizard alt (frame 1) |
| <img src="src/assets/wizard_f2.png" width="32" height="32"> | `wizard_f2.png` | Character — wizard alt (frame 2) |

### VGA Steele Alt Frames (`src/assets/steele_tiles/`)

Animation frames and alternate sprites not currently assigned to any NPC or character.

| Preview | File | Likely Purpose |
|---------|------|----------------|
| <img src="src/assets/steele_tiles/vga_bard_f2.png" width="32" height="32"> | `vga_bard_f2.png` | Bard animation frame 2 |
| <img src="src/assets/steele_tiles/vga_beggar_f2.png" width="32" height="32"> | `vga_beggar_f2.png` | Beggar animation frame 2 |
| <img src="src/assets/steele_tiles/vga_bull_f1.png" width="32" height="32"> | `vga_bull_f1.png` | Bull monster frame 1 |
| <img src="src/assets/steele_tiles/vga_bull_f2.png" width="32" height="32"> | `vga_bull_f2.png` | Bull monster frame 2 |
| <img src="src/assets/steele_tiles/vga_child_f2.png" width="32" height="32"> | `vga_child_f2.png` | Child animation frame 2 |
| <img src="src/assets/steele_tiles/vga_citizen_f2.png" width="32" height="32"> | `vga_citizen_f2.png` | Citizen animation frame 2 |
| <img src="src/assets/steele_tiles/vga_druid_f2.png" width="32" height="32"> | `vga_druid_f2.png` | Druid animation frame 2 |
| <img src="src/assets/steele_tiles/vga_evil_mage_f2.png" width="32" height="32"> | `vga_evil_mage_f2.png` | Evil Mage frame 2 |
| <img src="src/assets/steele_tiles/vga_evil_mage_f3.png" width="32" height="32"> | `vga_evil_mage_f3.png` | Evil Mage frame 3 |
| <img src="src/assets/steele_tiles/vga_evil_mage_f4.png" width="32" height="32"> | `vga_evil_mage_f4.png` | Evil Mage frame 4 |
| <img src="src/assets/steele_tiles/vga_fighter_f2.png" width="32" height="32"> | `vga_fighter_f2.png` | Fighter animation frame 2 |
| <img src="src/assets/steele_tiles/vga_guard_f2.png" width="32" height="32"> | `vga_guard_f2.png` | Guard animation frame 2 |
| <img src="src/assets/steele_tiles/vga_jester_f2.png" width="32" height="32"> | `vga_jester_f2.png` | Jester animation frame 2 |
| <img src="src/assets/steele_tiles/vga_lich_f1.png" width="32" height="32"> | `vga_lich_f1.png` | Lich monster frame 1 |
| <img src="src/assets/steele_tiles/vga_lich_f2.png" width="32" height="32"> | `vga_lich_f2.png` | Lich monster frame 2 |
| <img src="src/assets/steele_tiles/vga_lich_f3.png" width="32" height="32"> | `vga_lich_f3.png` | Lich monster frame 3 |
| <img src="src/assets/steele_tiles/vga_lich_f4.png" width="32" height="32"> | `vga_lich_f4.png` | Lich monster frame 4 |
| <img src="src/assets/steele_tiles/vga_lord_f2.png" width="32" height="32"> | `vga_lord_f2.png` | Lord animation frame 2 |
| <img src="src/assets/steele_tiles/vga_mage_f2.png" width="32" height="32"> | `vga_mage_f2.png` | Mage animation frame 2 |
| <img src="src/assets/steele_tiles/vga_paladin_f2.png" width="32" height="32"> | `vga_paladin_f2.png` | Paladin animation frame 2 |
| <img src="src/assets/steele_tiles/vga_ranger_f2.png" width="32" height="32"> | `vga_ranger_f2.png` | Ranger animation frame 2 |
| <img src="src/assets/steele_tiles/vga_rogue_f2.png" width="32" height="32"> | `vga_rogue_f2.png` | Rogue frame 2 |
| <img src="src/assets/steele_tiles/vga_rogue_f3.png" width="32" height="32"> | `vga_rogue_f3.png` | Rogue frame 3 |
| <img src="src/assets/steele_tiles/vga_rogue_f4.png" width="32" height="32"> | `vga_rogue_f4.png` | Rogue frame 4 |
| <img src="src/assets/steele_tiles/vga_singing_bard_f2.png" width="32" height="32"> | `vga_singing_bard_f2.png` | Singing Bard frame 2 |
| <img src="src/assets/steele_tiles/vga_skeleton_f1.png" width="32" height="32"> | `vga_skeleton_f1.png` | Skeleton frame 1 |
| <img src="src/assets/steele_tiles/vga_skeleton_f2.png" width="32" height="32"> | `vga_skeleton_f2.png` | Skeleton frame 2 |
| <img src="src/assets/steele_tiles/vga_skeleton_f3.png" width="32" height="32"> | `vga_skeleton_f3.png` | Skeleton frame 3 |
| <img src="src/assets/steele_tiles/vga_skeleton_f4.png" width="32" height="32"> | `vga_skeleton_f4.png` | Skeleton frame 4 |
| <img src="src/assets/steele_tiles/vga_tinker_f2.png" width="32" height="32"> | `vga_tinker_f2.png` | Tinker animation frame 2 |

### U4 Tile Library (`src/assets/u4_tiles/`)

Large library of Ultima IV–style tiles available for terrain, monsters, structures, and effects.

#### Monsters & Creatures

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/u4_tiles/balron_f1.png" width="32" height="32"> | `balron_f1.png` | Balron frame 1 |
| <img src="src/assets/u4_tiles/balron_f2.png" width="32" height="32"> | `balron_f2.png` | Balron frame 2 |
| <img src="src/assets/u4_tiles/balron_f3.png" width="32" height="32"> | `balron_f3.png` | Balron frame 3 |
| <img src="src/assets/u4_tiles/balron_f4.png" width="32" height="32"> | `balron_f4.png` | Balron frame 4 |
| <img src="src/assets/u4_tiles/bat_f1.png" width="32" height="32"> | `bat_f1.png` | Bat frame 1 |
| <img src="src/assets/u4_tiles/bat_f2.png" width="32" height="32"> | `bat_f2.png` | Bat frame 2 |
| <img src="src/assets/u4_tiles/bear_f1.png" width="32" height="32"> | `bear_f1.png` | Bear frame 1 |
| <img src="src/assets/u4_tiles/bear_f2.png" width="32" height="32"> | `bear_f2.png` | Bear frame 2 |
| <img src="src/assets/u4_tiles/cyclops_f1.png" width="32" height="32"> | `cyclops_f1.png` | Cyclops frame 1 |
| <img src="src/assets/u4_tiles/cyclops_f2.png" width="32" height="32"> | `cyclops_f2.png` | Cyclops frame 2 |
| <img src="src/assets/u4_tiles/cyclops_f3.png" width="32" height="32"> | `cyclops_f3.png` | Cyclops frame 3 |
| <img src="src/assets/u4_tiles/cyclops_f4.png" width="32" height="32"> | `cyclops_f4.png` | Cyclops frame 4 |
| <img src="src/assets/u4_tiles/daemon_f1.png" width="32" height="32"> | `daemon_f1.png` | Daemon frame 1 |
| <img src="src/assets/u4_tiles/daemon_f2.png" width="32" height="32"> | `daemon_f2.png` | Daemon frame 2 |
| <img src="src/assets/u4_tiles/daemon_f3.png" width="32" height="32"> | `daemon_f3.png` | Daemon frame 3 |
| <img src="src/assets/u4_tiles/daemon_f4.png" width="32" height="32"> | `daemon_f4.png` | Daemon frame 4 |
| <img src="src/assets/u4_tiles/dark_swarm_f1.png" width="32" height="32"> | `dark_swarm_f1.png` | Dark Swarm frame 1 |
| <img src="src/assets/u4_tiles/dark_swarm_f2.png" width="32" height="32"> | `dark_swarm_f2.png` | Dark Swarm frame 2 |
| <img src="src/assets/u4_tiles/dark_swarm_f3.png" width="32" height="32"> | `dark_swarm_f3.png` | Dark Swarm frame 3 |
| <img src="src/assets/u4_tiles/dark_swarm_f4.png" width="32" height="32"> | `dark_swarm_f4.png` | Dark Swarm frame 4 |
| <img src="src/assets/u4_tiles/dragon_red_f1.png" width="32" height="32"> | `dragon_red_f1.png` | Red Dragon frame 1 |
| <img src="src/assets/u4_tiles/dragon_red_f2.png" width="32" height="32"> | `dragon_red_f2.png` | Red Dragon frame 2 |
| <img src="src/assets/u4_tiles/dragon_red_f3.png" width="32" height="32"> | `dragon_red_f3.png` | Red Dragon frame 3 |
| <img src="src/assets/u4_tiles/dragon_red_f4.png" width="32" height="32"> | `dragon_red_f4.png` | Red Dragon frame 4 |
| <img src="src/assets/u4_tiles/drake_f1.png" width="32" height="32"> | `drake_f1.png` | Drake frame 1 |
| <img src="src/assets/u4_tiles/drake_f2.png" width="32" height="32"> | `drake_f2.png` | Drake frame 2 |
| <img src="src/assets/u4_tiles/drake_f3.png" width="32" height="32"> | `drake_f3.png` | Drake frame 3 |
| <img src="src/assets/u4_tiles/drake_f4.png" width="32" height="32"> | `drake_f4.png` | Drake frame 4 |
| <img src="src/assets/u4_tiles/ettin_f1.png" width="32" height="32"> | `ettin_f1.png` | Ettin frame 1 |
| <img src="src/assets/u4_tiles/ettin_f2.png" width="32" height="32"> | `ettin_f2.png` | Ettin frame 2 |
| <img src="src/assets/u4_tiles/ettin_f3.png" width="32" height="32"> | `ettin_f3.png` | Ettin frame 3 |
| <img src="src/assets/u4_tiles/ettin_f4.png" width="32" height="32"> | `ettin_f4.png` | Ettin frame 4 |
| <img src="src/assets/u4_tiles/gazer_f1.png" width="32" height="32"> | `gazer_f1.png` | Gazer frame 1 |
| <img src="src/assets/u4_tiles/gazer_f2.png" width="32" height="32"> | `gazer_f2.png` | Gazer frame 2 |
| <img src="src/assets/u4_tiles/gazer_f3.png" width="32" height="32"> | `gazer_f3.png` | Gazer frame 3 |
| <img src="src/assets/u4_tiles/gazer_f4.png" width="32" height="32"> | `gazer_f4.png` | Gazer frame 4 |
| <img src="src/assets/u4_tiles/ghost_f1.png" width="32" height="32"> | `ghost_f1.png` | Ghost frame 1 |
| <img src="src/assets/u4_tiles/ghost_f2.png" width="32" height="32"> | `ghost_f2.png` | Ghost frame 2 |
| <img src="src/assets/u4_tiles/ghost_f3.png" width="32" height="32"> | `ghost_f3.png` | Ghost frame 3 |
| <img src="src/assets/u4_tiles/ghost_f4.png" width="32" height="32"> | `ghost_f4.png` | Ghost frame 4 |
| <img src="src/assets/u4_tiles/ghost_f5.png" width="32" height="32"> | `ghost_f5.png` | Ghost frame 5 |
| <img src="src/assets/u4_tiles/ghost_f6.png" width="32" height="32"> | `ghost_f6.png` | Ghost frame 6 |
| <img src="src/assets/u4_tiles/gremlin_f1.png" width="32" height="32"> | `gremlin_f1.png` | Gremlin frame 1 |
| <img src="src/assets/u4_tiles/gremlin_f2.png" width="32" height="32"> | `gremlin_f2.png` | Gremlin frame 2 |
| <img src="src/assets/u4_tiles/gremlin_f3.png" width="32" height="32"> | `gremlin_f3.png` | Gremlin frame 3 |
| <img src="src/assets/u4_tiles/gremlin_f4.png" width="32" height="32"> | `gremlin_f4.png` | Gremlin frame 4 |
| <img src="src/assets/u4_tiles/hydra_f1.png" width="32" height="32"> | `hydra_f1.png` | Hydra frame 1 |
| <img src="src/assets/u4_tiles/hydra_f2.png" width="32" height="32"> | `hydra_f2.png` | Hydra frame 2 |
| <img src="src/assets/u4_tiles/hydra_f3.png" width="32" height="32"> | `hydra_f3.png` | Hydra frame 3 |
| <img src="src/assets/u4_tiles/hydra_f4.png" width="32" height="32"> | `hydra_f4.png` | Hydra frame 4 |
| <img src="src/assets/u4_tiles/insectoid_f1.png" width="32" height="32"> | `insectoid_f1.png` | Insectoid frame 1 |
| <img src="src/assets/u4_tiles/insectoid_f2.png" width="32" height="32"> | `insectoid_f2.png` | Insectoid frame 2 |
| <img src="src/assets/u4_tiles/insectoid_f3.png" width="32" height="32"> | `insectoid_f3.png` | Insectoid frame 3 |
| <img src="src/assets/u4_tiles/insectoid_f4.png" width="32" height="32"> | `insectoid_f4.png` | Insectoid frame 4 |
| <img src="src/assets/u4_tiles/lich_f1.png" width="32" height="32"> | `lich_f1.png` | Lich frame 1 |
| <img src="src/assets/u4_tiles/lich_f2.png" width="32" height="32"> | `lich_f2.png` | Lich frame 2 |
| <img src="src/assets/u4_tiles/lich_f3.png" width="32" height="32"> | `lich_f3.png` | Lich frame 3 |
| <img src="src/assets/u4_tiles/lich_f4.png" width="32" height="32"> | `lich_f4.png` | Lich frame 4 |
| <img src="src/assets/u4_tiles/lizardman_f1.png" width="32" height="32"> | `lizardman_f1.png` | Lizardman frame 1 |
| <img src="src/assets/u4_tiles/lizardman_f2.png" width="32" height="32"> | `lizardman_f2.png` | Lizardman frame 2 |
| <img src="src/assets/u4_tiles/lizardman_f3.png" width="32" height="32"> | `lizardman_f3.png` | Lizardman frame 3 |
| <img src="src/assets/u4_tiles/lizardman_f4.png" width="32" height="32"> | `lizardman_f4.png` | Lizardman frame 4 |
| <img src="src/assets/u4_tiles/nixie_f1.png" width="32" height="32"> | `nixie_f1.png` | Nixie frame 1 |
| <img src="src/assets/u4_tiles/nixie_f2.png" width="32" height="32"> | `nixie_f2.png` | Nixie frame 2 |
| <img src="src/assets/u4_tiles/orc_dark.png" width="32" height="32"> | `orc_dark.png` | Dark Orc |
| <img src="src/assets/u4_tiles/orc_f1.png" width="32" height="32"> | `orc_f1.png` | Orc frame 1 |
| <img src="src/assets/u4_tiles/orc_f2.png" width="32" height="32"> | `orc_f2.png` | Orc frame 2 |
| <img src="src/assets/u4_tiles/orc_f3.png" width="32" height="32"> | `orc_f3.png` | Orc frame 3 |
| <img src="src/assets/u4_tiles/orc_f4.png" width="32" height="32"> | `orc_f4.png` | Orc frame 4 |
| <img src="src/assets/u4_tiles/orc_green.png" width="32" height="32"> | `orc_green.png` | Green Orc |
| <img src="src/assets/u4_tiles/phantom_f1.png" width="32" height="32"> | `phantom_f1.png` | Phantom frame 1 |
| <img src="src/assets/u4_tiles/phantom_f2.png" width="32" height="32"> | `phantom_f2.png` | Phantom frame 2 |
| <img src="src/assets/u4_tiles/phantom_f3.png" width="32" height="32"> | `phantom_f3.png` | Phantom frame 3 |
| <img src="src/assets/u4_tiles/phantom_f4.png" width="32" height="32"> | `phantom_f4.png` | Phantom frame 4 |
| <img src="src/assets/u4_tiles/rat_f1.png" width="32" height="32"> | `rat_f1.png` | Rat frame 1 |
| <img src="src/assets/u4_tiles/rat_f2.png" width="32" height="32"> | `rat_f2.png` | Rat frame 2 |
| <img src="src/assets/u4_tiles/rat_f3.png" width="32" height="32"> | `rat_f3.png` | Rat frame 3 |
| <img src="src/assets/u4_tiles/rat_f4.png" width="32" height="32"> | `rat_f4.png` | Rat frame 4 |
| <img src="src/assets/u4_tiles/reaper_f1.png" width="32" height="32"> | `reaper_f1.png` | Reaper frame 1 |
| <img src="src/assets/u4_tiles/reaper_f2.png" width="32" height="32"> | `reaper_f2.png` | Reaper frame 2 |
| <img src="src/assets/u4_tiles/reaper_f3.png" width="32" height="32"> | `reaper_f3.png` | Reaper frame 3 |
| <img src="src/assets/u4_tiles/reaper_f4.png" width="32" height="32"> | `reaper_f4.png` | Reaper frame 4 |
| <img src="src/assets/u4_tiles/sea_horse_f1.png" width="32" height="32"> | `sea_horse_f1.png` | Sea Horse frame 1 |
| <img src="src/assets/u4_tiles/sea_horse_f2.png" width="32" height="32"> | `sea_horse_f2.png` | Sea Horse frame 2 |
| <img src="src/assets/u4_tiles/sea_horse_f3.png" width="32" height="32"> | `sea_horse_f3.png` | Sea Horse frame 3 |
| <img src="src/assets/u4_tiles/sea_horse_f4.png" width="32" height="32"> | `sea_horse_f4.png` | Sea Horse frame 4 |
| <img src="src/assets/u4_tiles/sea_serpent_f1.png" width="32" height="32"> | `sea_serpent_f1.png` | Sea Serpent frame 1 |
| <img src="src/assets/u4_tiles/sea_serpent_f2.png" width="32" height="32"> | `sea_serpent_f2.png` | Sea Serpent frame 2 |
| <img src="src/assets/u4_tiles/sea_serpent_f3.png" width="32" height="32"> | `sea_serpent_f3.png` | Sea Serpent frame 3 |
| <img src="src/assets/u4_tiles/skeleton_f1.png" width="32" height="32"> | `skeleton_f1.png` | Skeleton frame 1 |
| <img src="src/assets/u4_tiles/skeleton_f2.png" width="32" height="32"> | `skeleton_f2.png` | Skeleton frame 2 |
| <img src="src/assets/u4_tiles/skeleton_f3.png" width="32" height="32"> | `skeleton_f3.png` | Skeleton frame 3 |
| <img src="src/assets/u4_tiles/skeleton_f4.png" width="32" height="32"> | `skeleton_f4.png` | Skeleton frame 4 |
| <img src="src/assets/u4_tiles/slime_f1.png" width="32" height="32"> | `slime_f1.png` | Slime frame 1 |
| <img src="src/assets/u4_tiles/slime_f2.png" width="32" height="32"> | `slime_f2.png` | Slime frame 2 |
| <img src="src/assets/u4_tiles/slime_f3.png" width="32" height="32"> | `slime_f3.png` | Slime frame 3 |
| <img src="src/assets/u4_tiles/slime_f4.png" width="32" height="32"> | `slime_f4.png` | Slime frame 4 |
| <img src="src/assets/u4_tiles/snake_f1.png" width="32" height="32"> | `snake_f1.png` | Snake frame 1 |
| <img src="src/assets/u4_tiles/snake_f2.png" width="32" height="32"> | `snake_f2.png` | Snake frame 2 |
| <img src="src/assets/u4_tiles/snake_f3.png" width="32" height="32"> | `snake_f3.png` | Snake frame 3 |
| <img src="src/assets/u4_tiles/snake_f4.png" width="32" height="32"> | `snake_f4.png` | Snake frame 4 |
| <img src="src/assets/u4_tiles/spider_f1.png" width="32" height="32"> | `spider_f1.png` | Spider frame 1 |
| <img src="src/assets/u4_tiles/spider_f2.png" width="32" height="32"> | `spider_f2.png` | Spider frame 2 |
| <img src="src/assets/u4_tiles/spider_f3.png" width="32" height="32"> | `spider_f3.png` | Spider frame 3 |
| <img src="src/assets/u4_tiles/spider_f4.png" width="32" height="32"> | `spider_f4.png` | Spider frame 4 |
| <img src="src/assets/u4_tiles/troll_brute_f1.png" width="32" height="32"> | `troll_brute_f1.png` | Troll Brute frame 1 |
| <img src="src/assets/u4_tiles/troll_brute_f2.png" width="32" height="32"> | `troll_brute_f2.png` | Troll Brute frame 2 |
| <img src="src/assets/u4_tiles/troll_brute_f3.png" width="32" height="32"> | `troll_brute_f3.png` | Troll Brute frame 3 |
| <img src="src/assets/u4_tiles/troll_brute_f4.png" width="32" height="32"> | `troll_brute_f4.png` | Troll Brute frame 4 |
| <img src="src/assets/u4_tiles/troll_f1.png" width="32" height="32"> | `troll_f1.png` | Troll frame 1 |
| <img src="src/assets/u4_tiles/troll_f2.png" width="32" height="32"> | `troll_f2.png` | Troll frame 2 |
| <img src="src/assets/u4_tiles/troll_f3.png" width="32" height="32"> | `troll_f3.png` | Troll frame 3 |
| <img src="src/assets/u4_tiles/troll_f4.png" width="32" height="32"> | `troll_f4.png` | Troll frame 4 |
| <img src="src/assets/u4_tiles/wisp_f1.png" width="32" height="32"> | `wisp_f1.png` | Wisp frame 1 |
| <img src="src/assets/u4_tiles/wisp_f2.png" width="32" height="32"> | `wisp_f2.png` | Wisp frame 2 |
| <img src="src/assets/u4_tiles/zorn_f1.png" width="32" height="32"> | `zorn_f1.png` | Zorn frame 1 |
| <img src="src/assets/u4_tiles/zorn_f2.png" width="32" height="32"> | `zorn_f2.png` | Zorn frame 2 |
| <img src="src/assets/u4_tiles/zorn_f3.png" width="32" height="32"> | `zorn_f3.png` | Zorn frame 3 |
| <img src="src/assets/u4_tiles/zorn_f4.png" width="32" height="32"> | `zorn_f4.png` | Zorn frame 4 |

#### Characters & NPCs (Alt Frames)

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/u4_tiles/avatar_f2.png" width="32" height="32"> | `avatar_f2.png` | Avatar frame 2 |
| <img src="src/assets/u4_tiles/beggar_f2.png" width="32" height="32"> | `beggar_f2.png` | Beggar frame 2 |
| <img src="src/assets/u4_tiles/child_f2.png" width="32" height="32"> | `child_f2.png` | Child frame 2 |
| <img src="src/assets/u4_tiles/citizen_f2.png" width="32" height="32"> | `citizen_f2.png` | Citizen frame 2 |
| <img src="src/assets/u4_tiles/fighter.png" width="32" height="32"> | `fighter.png` | Fighter static |
| <img src="src/assets/u4_tiles/guard_f2.png" width="32" height="32"> | `guard_f2.png` | Guard frame 2 |
| <img src="src/assets/u4_tiles/healer_alt_f2.png" width="32" height="32"> | `healer_alt_f2.png` | Healer alt frame 2 |
| <img src="src/assets/u4_tiles/healer_f2.png" width="32" height="32"> | `healer_f2.png` | Healer frame 2 |
| <img src="src/assets/u4_tiles/jester_f2.png" width="32" height="32"> | `jester_f2.png` | Jester frame 2 |
| <img src="src/assets/u4_tiles/knight_f2.png" width="32" height="32"> | `knight_f2.png` | Knight frame 2 |

#### Terrain & Environment

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/u4_tiles/bridge.png" width="32" height="32"> | `bridge.png` | Bridge |
| <img src="src/assets/u4_tiles/brush.png" width="32" height="32"> | `brush.png` | Brush / scrubland |
| <img src="src/assets/u4_tiles/campfire.png" width="32" height="32"> | `campfire.png` | Campfire |
| <img src="src/assets/u4_tiles/castle.png" width="32" height="32"> | `castle.png` | Castle structure |
| <img src="src/assets/u4_tiles/castle_wall_left.png" width="32" height="32"> | `castle_wall_left.png` | Castle wall (left) |
| <img src="src/assets/u4_tiles/castle_wall_mid.png" width="32" height="32"> | `castle_wall_mid.png` | Castle wall (middle) |
| <img src="src/assets/u4_tiles/castle_wall_right.png" width="32" height="32"> | `castle_wall_right.png` | Castle wall (right) |
| <img src="src/assets/u4_tiles/deep_water.png" width="32" height="32"> | `deep_water.png` | Deep water |
| <img src="src/assets/u4_tiles/darkness.png" width="32" height="32"> | `darkness.png` | Darkness / fog of war |
| <img src="src/assets/u4_tiles/dungeon_dark.png" width="32" height="32"> | `dungeon_dark.png` | Dungeon darkness |
| <img src="src/assets/u4_tiles/dungeon_entrance.png" width="32" height="32"> | `dungeon_entrance.png` | Dungeon entrance |
| <img src="src/assets/u4_tiles/forest.png" width="32" height="32"> | `forest.png` | Forest |
| <img src="src/assets/u4_tiles/grassland.png" width="32" height="32"> | `grassland.png` | Grassland |
| <img src="src/assets/u4_tiles/hills.png" width="32" height="32"> | `hills.png` | Hills |
| <img src="src/assets/u4_tiles/lava_red.png" width="32" height="32"> | `lava_red.png` | Lava |
| <img src="src/assets/u4_tiles/medium_water.png" width="32" height="32"> | `medium_water.png` | Medium water |
| <img src="src/assets/u4_tiles/mountains.png" width="32" height="32"> | `mountains.png` | Mountains |
| <img src="src/assets/u4_tiles/shallow_water.png" width="32" height="32"> | `shallow_water.png` | Shallow water |
| <img src="src/assets/u4_tiles/swamp.png" width="32" height="32"> | `swamp.png` | Swamp |
| <img src="src/assets/u4_tiles/town_small.png" width="32" height="32"> | `town_small.png` | Small town |
| <img src="src/assets/u4_tiles/village.png" width="32" height="32"> | `village.png` | Village |
| <img src="src/assets/u4_tiles/water_anim_1.png" width="32" height="32"> | `water_anim_1.png` | Water animation frame 1 |
| <img src="src/assets/u4_tiles/water_anim_2.png" width="32" height="32"> | `water_anim_2.png` | Water animation frame 2 |

#### Structures & Objects

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/u4_tiles/altar_left.png" width="32" height="32"> | `altar_left.png` | Altar (left half) |
| <img src="src/assets/u4_tiles/altar_right.png" width="32" height="32"> | `altar_right.png` | Altar (right half) |
| <img src="src/assets/u4_tiles/ankh.png" width="32" height="32"> | `ankh.png` | Ankh symbol |
| <img src="src/assets/u4_tiles/ankh_blue_f1.png" width="32" height="32"> | `ankh_blue_f1.png` | Blue ankh frame 1 |
| <img src="src/assets/u4_tiles/ankh_blue_f2.png" width="32" height="32"> | `ankh_blue_f2.png` | Blue ankh frame 2 |
| <img src="src/assets/u4_tiles/ankh_blue_f3.png" width="32" height="32"> | `ankh_blue_f3.png` | Blue ankh frame 3 |
| <img src="src/assets/u4_tiles/ankh_blue_f4.png" width="32" height="32"> | `ankh_blue_f4.png` | Blue ankh frame 4 |
| <img src="src/assets/u4_tiles/balloon.png" width="32" height="32"> | `balloon.png` | Hot air balloon |
| <img src="src/assets/u4_tiles/brick_blank_1.png" width="32" height="32"> | `brick_blank_1.png` | Blank brick tile 1 |
| <img src="src/assets/u4_tiles/brick_blank_2.png" width="32" height="32"> | `brick_blank_2.png` | Blank brick tile 2 |
| <img src="src/assets/u4_tiles/brick_blank_3.png" width="32" height="32"> | `brick_blank_3.png` | Blank brick tile 3 |
| <img src="src/assets/u4_tiles/brick_blank_4.png" width="32" height="32"> | `brick_blank_4.png` | Blank brick tile 4 |
| <img src="src/assets/u4_tiles/brick_floor.png" width="32" height="32"> | `brick_floor.png` | Brick floor |
| <img src="src/assets/u4_tiles/brick_wall.png" width="32" height="32"> | `brick_wall.png` | Brick wall |
| <img src="src/assets/u4_tiles/brick_wall_alt.png" width="32" height="32"> | `brick_wall_alt.png` | Brick wall (alternate) |
| <img src="src/assets/u4_tiles/black_blank_1.png" width="32" height="32"> | `black_blank_1.png` | Black blank tile 1 |
| <img src="src/assets/u4_tiles/black_blank_2.png" width="32" height="32"> | `black_blank_2.png` | Black blank tile 2 |
| <img src="src/assets/u4_tiles/black_blank_3.png" width="32" height="32"> | `black_blank_3.png` | Black blank tile 3 |
| <img src="src/assets/u4_tiles/chest.png" width="32" height="32"> | `chest.png` | Chest |
| <img src="src/assets/u4_tiles/covered_wagon.png" width="32" height="32"> | `covered_wagon.png` | Covered wagon |
| <img src="src/assets/u4_tiles/fireplace.png" width="32" height="32"> | `fireplace.png` | Fireplace |
| <img src="src/assets/u4_tiles/horse_east.png" width="32" height="32"> | `horse_east.png` | Horse (facing east) |
| <img src="src/assets/u4_tiles/horse_west.png" width="32" height="32"> | `horse_west.png` | Horse (facing west) |
| <img src="src/assets/u4_tiles/locked_door.png" width="32" height="32"> | `locked_door.png` | Locked door |
| <img src="src/assets/u4_tiles/moon_full.png" width="32" height="32"> | `moon_full.png` | Full moon |
| <img src="src/assets/u4_tiles/pirate_ship_f1.png" width="32" height="32"> | `pirate_ship_f1.png` | Pirate ship frame 1 |
| <img src="src/assets/u4_tiles/pirate_ship_f2.png" width="32" height="32"> | `pirate_ship_f2.png` | Pirate ship frame 2 |
| <img src="src/assets/u4_tiles/pirate_ship_f3.png" width="32" height="32"> | `pirate_ship_f3.png` | Pirate ship frame 3 |
| <img src="src/assets/u4_tiles/pirate_ship_f4.png" width="32" height="32"> | `pirate_ship_f4.png` | Pirate ship frame 4 |
| <img src="src/assets/u4_tiles/portcullis.png" width="32" height="32"> | `portcullis.png` | Portcullis gate |
| <img src="src/assets/u4_tiles/rock_pile.png" width="32" height="32"> | `rock_pile.png` | Rock pile |
| <img src="src/assets/u4_tiles/ship_east.png" width="32" height="32"> | `ship_east.png` | Ship facing east |
| <img src="src/assets/u4_tiles/ship_north.png" width="32" height="32"> | `ship_north.png` | Ship facing north |
| <img src="src/assets/u4_tiles/ship_south.png" width="32" height="32"> | `ship_south.png` | Ship facing south |
| <img src="src/assets/u4_tiles/ship_west.png" width="32" height="32"> | `ship_west.png` | Ship facing west |
| <img src="src/assets/u4_tiles/skeleton_decor.png" width="32" height="32"> | `skeleton_decor.png` | Decorative skeleton |
| <img src="src/assets/u4_tiles/stone_wall.png" width="32" height="32"> | `stone_wall.png` | Stone wall |
| <img src="src/assets/u4_tiles/torch_post.png" width="32" height="32"> | `torch_post.png` | Torch post |
| <img src="src/assets/u4_tiles/whirlpool_f1.png" width="32" height="32"> | `whirlpool_f1.png` | Whirlpool frame 1 |
| <img src="src/assets/u4_tiles/whirlpool_f2.png" width="32" height="32"> | `whirlpool_f2.png` | Whirlpool frame 2 |

#### Magic & Effects

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/u4_tiles/energy_field_p1.png" width="32" height="32"> | `energy_field_p1.png` | Energy field phase 1 |
| <img src="src/assets/u4_tiles/energy_field_p2.png" width="32" height="32"> | `energy_field_p2.png` | Energy field phase 2 |
| <img src="src/assets/u4_tiles/explosion_alt.png" width="32" height="32"> | `explosion_alt.png` | Explosion (alternate) |
| <img src="src/assets/u4_tiles/explosion_red.png" width="32" height="32"> | `explosion_red.png` | Explosion (red) |
| <img src="src/assets/u4_tiles/fire_field_mag.png" width="32" height="32"> | `fire_field_mag.png` | Magic fire field |
| <img src="src/assets/u4_tiles/fire_field_red.png" width="32" height="32"> | `fire_field_red.png` | Red fire field |
| <img src="src/assets/u4_tiles/magic_orb_blue.png" width="32" height="32"> | `magic_orb_blue.png` | Blue magic orb |
| <img src="src/assets/u4_tiles/magic_orb_red.png" width="32" height="32"> | `magic_orb_red.png` | Red magic orb |
| <img src="src/assets/u4_tiles/magical_barrier.png" width="32" height="32"> | `magical_barrier.png` | Magical barrier |
| <img src="src/assets/u4_tiles/poison_field.png" width="32" height="32"> | `poison_field.png` | Poison field |
| <img src="src/assets/u4_tiles/portal_closed.png" width="32" height="32"> | `portal_closed.png` | Portal (closed) |
| <img src="src/assets/u4_tiles/portal_open.png" width="32" height="32"> | `portal_open.png` | Portal (open) |
| <img src="src/assets/u4_tiles/sparkle.png" width="32" height="32"> | `sparkle.png` | Sparkle effect |
| <img src="src/assets/u4_tiles/tornado.png" width="32" height="32"> | `tornado.png` | Tornado |

#### Text Tiles

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/u4_tiles/letter_a.png" width="32" height="32"> | `letter_a.png` | Letter A |
| <img src="src/assets/u4_tiles/letter_b.png" width="32" height="32"> | `letter_b.png` | Letter B |
| <img src="src/assets/u4_tiles/letter_c.png" width="32" height="32"> | `letter_c.png` | Letter C |
| <img src="src/assets/u4_tiles/letter_d.png" width="32" height="32"> | `letter_d.png` | Letter D |
| <img src="src/assets/u4_tiles/letter_e.png" width="32" height="32"> | `letter_e.png` | Letter E |
| <img src="src/assets/u4_tiles/letter_f.png" width="32" height="32"> | `letter_f.png` | Letter F |
| <img src="src/assets/u4_tiles/letter_g.png" width="32" height="32"> | `letter_g.png` | Letter G |
| <img src="src/assets/u4_tiles/letter_h.png" width="32" height="32"> | `letter_h.png` | Letter H |
| <img src="src/assets/u4_tiles/letter_i.png" width="32" height="32"> | `letter_i.png` | Letter I |
| <img src="src/assets/u4_tiles/letter_j.png" width="32" height="32"> | `letter_j.png` | Letter J |
| <img src="src/assets/u4_tiles/letter_k.png" width="32" height="32"> | `letter_k.png` | Letter K |
| <img src="src/assets/u4_tiles/letter_l.png" width="32" height="32"> | `letter_l.png` | Letter L |
| <img src="src/assets/u4_tiles/letter_m.png" width="32" height="32"> | `letter_m.png` | Letter M |
| <img src="src/assets/u4_tiles/letter_n.png" width="32" height="32"> | `letter_n.png` | Letter N |
| <img src="src/assets/u4_tiles/letter_o.png" width="32" height="32"> | `letter_o.png` | Letter O |
| <img src="src/assets/u4_tiles/letter_p.png" width="32" height="32"> | `letter_p.png` | Letter P |
| <img src="src/assets/u4_tiles/letter_q.png" width="32" height="32"> | `letter_q.png` | Letter Q |
| <img src="src/assets/u4_tiles/letter_r.png" width="32" height="32"> | `letter_r.png` | Letter R |
| <img src="src/assets/u4_tiles/letter_s.png" width="32" height="32"> | `letter_s.png` | Letter S |
| <img src="src/assets/u4_tiles/letter_t.png" width="32" height="32"> | `letter_t.png` | Letter T |
| <img src="src/assets/u4_tiles/letter_u.png" width="32" height="32"> | `letter_u.png` | Letter U |
| <img src="src/assets/u4_tiles/letter_v.png" width="32" height="32"> | `letter_v.png` | Letter V |
| <img src="src/assets/u4_tiles/letter_w.png" width="32" height="32"> | `letter_w.png` | Letter W |
| <img src="src/assets/u4_tiles/letter_x.png" width="32" height="32"> | `letter_x.png` | Letter X |
| <img src="src/assets/u4_tiles/letter_y.png" width="32" height="32"> | `letter_y.png` | Letter Y |
| <img src="src/assets/u4_tiles/letter_z.png" width="32" height="32"> | `letter_z.png` | Letter Z |
| <img src="src/assets/u4_tiles/scroll_text_1.png" width="32" height="32"> | `scroll_text_1.png` | Scroll text 1 |
| <img src="src/assets/u4_tiles/scroll_text_2.png" width="32" height="32"> | `scroll_text_2.png` | Scroll text 2 |
| <img src="src/assets/u4_tiles/scroll_text_3.png" width="32" height="32"> | `scroll_text_3.png` | Scroll text 3 |

---

## Summary

| Category | In Use | Available (Unassigned) |
|----------|--------|----------------------|
| Tile sheet (U3TilesE.gif) | 8 overworld + 4 town positions | ~68 remaining sheet positions |
| Amiga character sprites | 5 | 0 |
| U4 character/class sprites | 21 | 10 alt frames |
| VGA Steele sprites | 18 | 30 alt frames + creatures |
| Monster sprites | 8 unique (10 assignments) | 100+ creature tiles in U4 library |
| Unique overworld tiles | 8 | — |
| Special objects | 2 | — |
| Custom root sprites | 6 | 43 |
| **Total** | **66 files** | **308 files** |
