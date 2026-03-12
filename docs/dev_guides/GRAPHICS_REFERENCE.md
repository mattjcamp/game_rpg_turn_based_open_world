# Graphics Reference — Realm of Shadow

All tiles are displayed at the in-game scale of 32×32 pixels. This document covers tiles in `src/assets/game/` (active in the game) and `src/assets/unassigned/` (available for future use). Archived original source art is in `src/assets/archive/` and is not listed here.

---

## 1. Overworld Terrain

These tiles render the outdoor world map. Defined in `data/tile_manifest.json` under `"overworld"`, loaded by `TileManifest` and rendered in `renderer.py :: _u3_draw_overworld_tile()`.

| Preview | Name | Tile ID | File | Used For |
|---------|------|---------|------|----------|
| <img src="src/assets/game/terrain/grass.png" width="32" height="32"> | grass | 0 | `game/terrain/grass.png` | Default overworld ground; also used as town floor (tile_id 10) |
| <img src="src/assets/game/terrain/water.png" width="32" height="32"> | water | 1 | `game/terrain/water.png` | Oceans, rivers, lakes |
| <img src="src/assets/game/terrain/forest.png" width="32" height="32"> | forest | 2 | `game/terrain/forest.png` | Forest terrain; blocks movement |
| <img src="src/assets/game/terrain/mountain.png" width="32" height="32"> | mountain | 3 | `game/terrain/mountain.png` | Mountain terrain; impassable |
| <img src="src/assets/game/terrain/town.png" width="32" height="32"> | town | 4 | `game/terrain/town.png` | Town entrance markers on overworld; also used as town exit (tile_id 14) |
| <img src="src/assets/game/terrain/dungeon.png" width="32" height="32"> | dungeon | 5 | `game/terrain/dungeon.png` | Dungeon entrance markers; shared by dungeon_cleared (tile_id 9) |
| <img src="src/assets/game/terrain/path.png" width="32" height="32"> | path | 6 | `game/terrain/path.png` | Dirt paths connecting landmarks |
| <img src="src/assets/game/terrain/sand.png" width="32" height="32"> | sand | 7 | `game/terrain/sand.png` | Sandy/beach terrain near coasts |
| <img src="src/assets/game/terrain/bridge.png" width="32" height="32"> | bridge | 8 | `game/terrain/bridge.png` | Wooden bridge over rivers |

---

## 2. Town Interior Tiles

Used inside town maps. Defined in `data/tile_manifest.json` under `"town"`, rendered in `renderer.py :: _u3_draw_town_tile()`. Tiles not matched here fall through to procedural rendering.

| Preview | Name | Tile ID | File | Used For |
|---------|------|---------|------|----------|
| <img src="src/assets/game/terrain/grass.png" width="32" height="32"> | floor | 10 | `game/terrain/grass.png` | Indoor floor (shares grass sprite) |
| <img src="src/assets/game/terrain/wall.png" width="32" height="32"> | wall | 11 | `game/terrain/wall.png` | Building walls |
| <img src="src/assets/game/terrain/counter.png" width="32" height="32"> | counter | 12 | `game/terrain/counter.png` | Shop counters |
| <img src="src/assets/game/terrain/door.png" width="32" height="32"> | door | 13 | `game/terrain/door.png` | Doorways |
| <img src="src/assets/game/terrain/town.png" width="32" height="32"> | exit | 14 | `game/terrain/town.png` | Town exit tile (shares town sprite) |
| <img src="src/assets/game/terrain/altar.png" width="32" height="32"> | altar | 35 | `game/terrain/altar.png` | Altars in temples/shrines |

---

## 3. Dungeon Tiles

Base sprites for dungeon levels. Defined in `data/tile_manifest.json` under `"dungeon"`. These are blitted first, then procedural effects (palette tinting, moss, lava overlays) are drawn on top in `renderer.py :: _u3_draw_dungeon_tile()`.

| Preview | Name | Tile ID | File | Used For |
|---------|------|---------|------|----------|
| <img src="src/assets/game/dungeon/brick_floor.png" width="32" height="32"> | dfloor | 20 | `game/dungeon/brick_floor.png` | Dungeon floor; also used as base for stairs (22), trap (24), stairs_down (25), machine (30), keyslot (31) |
| <img src="src/assets/game/dungeon/brick_wall.png" width="32" height="32"> | dwall | 21 | `game/dungeon/brick_wall.png` | Dungeon walls |
| <img src="src/assets/game/dungeon/chest_tile.png" width="32" height="32"> | chest | 23 | `game/dungeon/chest_tile.png` | Treasure chests in dungeons |
| <img src="src/assets/game/dungeon/locked_door.png" width="32" height="32"> | ddoor / locked_door | 26, 29 | `game/dungeon/locked_door.png` | Dungeon doors (locked and unlocked) |
| <img src="src/assets/game/dungeon/sparkle.png" width="32" height="32"> | artifact | 27 | `game/dungeon/sparkle.png` | Artifact pickup locations |
| <img src="src/assets/game/dungeon/portal_open.png" width="32" height="32"> | portal | 28 | `game/dungeon/portal_open.png` | Active dungeon portals |
| <img src="src/assets/game/dungeon/shallow_water.png" width="32" height="32"> | puddle | 32 | `game/dungeon/shallow_water.png` | Water puddles in dungeons |
| <img src="src/assets/game/dungeon/swamp.png" width="32" height="32"> | moss | 33 | `game/dungeon/swamp.png` | Mossy/swampy dungeon patches |
| <img src="src/assets/game/dungeon/torch_post.png" width="32" height="32"> | wall_torch | 34 | `game/dungeon/torch_post.png` | Wall-mounted torches |

---

## 4. Player Characters

Class sprites for the party. Defined in `data/tile_manifest.json` under `"characters"` and `data/character_tiles.json`. Loaded by `renderer.py :: _load_class_sprites()` and used on the overworld party display, combat, party screen, and character creation.

| Preview | Name | File | Used For |
|---------|------|------|----------|
| <img src="src/assets/game/characters/fighter.png" width="32" height="32"> | fighter | `game/characters/fighter.png` | Fighter class; default party member Roland |
| <img src="src/assets/game/characters/cleric.png" width="32" height="32"> | cleric | `game/characters/cleric.png` | Cleric class; default party member Selina |
| <img src="src/assets/game/characters/wizard.png" width="32" height="32"> | wizard | `game/characters/wizard.png` | Wizard class; default party member Elrond |
| <img src="src/assets/game/characters/thief.png" width="32" height="32"> | thief | `game/characters/thief.png` | Thief class; default party member Merry |
| <img src="src/assets/game/characters/barbarian.png" width="32" height="32"> | barbarian | `game/characters/barbarian.png` | Barbarian class |
| <img src="src/assets/game/characters/alchemist.png" width="32" height="32"> | alchemist | `game/characters/alchemist.png` | Alchemist class |
| <img src="src/assets/game/characters/illusionist.png" width="32" height="32"> | illusionist | `game/characters/illusionist.png` | Illusionist class |
| <img src="src/assets/game/characters/druid.png" width="32" height="32"> | druid | `game/characters/druid.png` | Druid class; default roster member |
| <img src="src/assets/game/characters/paladin.png" width="32" height="32"> | paladin | `game/characters/paladin.png` | Paladin class; default roster member |
| <img src="src/assets/game/characters/ranger.png" width="32" height="32"> | ranger | `game/characters/ranger.png` | Ranger class; default roster member |
| <img src="src/assets/game/characters/lark.png" width="32" height="32"> | lark | `game/characters/lark.png` | Lark class |
| <img src="src/assets/game/characters/ranger_alt.png" width="32" height="32"> | ranger_alt | `game/characters/ranger_alt.png` | Alternate ranger sprite (character creation) |

---

## 5. NPCs

Non-player character sprites for towns and character creation screens. Loaded from `data/tile_manifest.json` under `"npcs"` and `data/character_tiles.json`. Used by `renderer.py` for town NPC rendering (shopkeep, innkeeper, elder, villagers) and character creation portrait selection.

### Town NPCs (manifest-loaded)

| Preview | Name | File | Used For |
|---------|------|------|----------|
| <img src="src/assets/game/npcs/shopkeep.png" width="32" height="32"> | shopkeep | `game/npcs/shopkeep.png` | Shop merchants |
| <img src="src/assets/game/npcs/innkeeper.png" width="32" height="32"> | innkeeper | `game/npcs/innkeeper.png` | Inn proprietors |
| <img src="src/assets/game/npcs/elder.png" width="32" height="32"> | elder | `game/npcs/elder.png` | Town elders / quest givers |
| <img src="src/assets/game/npcs/villager_citizen.png" width="32" height="32"> | villager_0 | `game/npcs/villager_citizen.png` | Citizen villager |
| <img src="src/assets/game/npcs/villager_shepherd.png" width="32" height="32"> | villager_1 | `game/npcs/villager_shepherd.png` | Shepherd villager |
| <img src="src/assets/game/npcs/villager_bard.png" width="32" height="32"> | villager_2 | `game/npcs/villager_bard.png` | Bard villager |
| <img src="src/assets/game/npcs/villager_guard.png" width="32" height="32"> | villager_3 | `game/npcs/villager_guard.png` | Guard villager |
| <img src="src/assets/game/npcs/villager_beggar.png" width="32" height="32"> | villager_4 | `game/npcs/villager_beggar.png` | Beggar villager |
| <img src="src/assets/game/npcs/villager_child.png" width="32" height="32"> | villager_5 | `game/npcs/villager_child.png` | Child villager |

### Character Creation Portraits (character_tiles.json)

These additional sprites appear as portrait options during character creation. They supplement the class sprites above.

| Preview | File | Used For |
|---------|------|----------|
| <img src="src/assets/game/npcs/u4_monk.png" width="32" height="32"> | `game/npcs/u4_monk.png` | Monk portrait option |
| <img src="src/assets/game/npcs/u4_tinker.png" width="32" height="32"> | `game/npcs/u4_tinker.png` | Tinker portrait option |
| <img src="src/assets/game/npcs/u4_shepherd.png" width="32" height="32"> | `game/npcs/u4_shepherd.png` | Shepherd portrait option |
| <img src="src/assets/game/npcs/u4_avatar.png" width="32" height="32"> | `game/npcs/u4_avatar.png` | Avatar portrait option |
| <img src="src/assets/game/npcs/u4_knight.png" width="32" height="32"> | `game/npcs/u4_knight.png` | Knight portrait option |
| <img src="src/assets/game/npcs/u4_guard.png" width="32" height="32"> | `game/npcs/u4_guard.png` | Guard portrait option |
| <img src="src/assets/game/npcs/u4_healer.png" width="32" height="32"> | `game/npcs/u4_healer.png` | Healer portrait option |
| <img src="src/assets/game/npcs/u4_jester.png" width="32" height="32"> | `game/npcs/u4_jester.png` | Jester portrait option |
| <img src="src/assets/game/npcs/u4_villager_male.png" width="32" height="32"> | `game/npcs/u4_villager_male.png` | Male villager portrait |
| <img src="src/assets/game/npcs/u4_villager_female.png" width="32" height="32"> | `game/npcs/u4_villager_female.png` | Female villager portrait |
| <img src="src/assets/game/npcs/u4_child.png" width="32" height="32"> | `game/npcs/u4_child.png` | Child portrait option |
| <img src="src/assets/game/npcs/u4_beggar.png" width="32" height="32"> | `game/npcs/u4_beggar.png` | Beggar portrait option |
| <img src="src/assets/game/npcs/u4_citizen.png" width="32" height="32"> | `game/npcs/u4_citizen.png` | Citizen portrait option |
| <img src="src/assets/game/npcs/u4_guard_npc.png" width="32" height="32"> | `game/npcs/u4_guard_npc.png` | Guard NPC portrait option |
| <img src="src/assets/game/npcs/townsfolk.png" width="32" height="32"> | `game/npcs/townsfolk.png` | Townsfolk portrait option |
| <img src="src/assets/game/npcs/brigand.png" width="32" height="32"> | `game/npcs/brigand.png` | Brigand portrait option |
| <img src="src/assets/game/npcs/vga_avatar.png" width="32" height="32"> | `game/npcs/vga_avatar.png` | VGA avatar portrait |
| <img src="src/assets/game/npcs/vga_mage.png" width="32" height="32"> | `game/npcs/vga_mage.png` | VGA mage portrait |
| <img src="src/assets/game/npcs/vga_fighter.png" width="32" height="32"> | `game/npcs/vga_fighter.png` | VGA fighter portrait |
| <img src="src/assets/game/npcs/vga_druid.png" width="32" height="32"> | `game/npcs/vga_druid.png` | VGA druid portrait |
| <img src="src/assets/game/npcs/vga_paladin.png" width="32" height="32"> | `game/npcs/vga_paladin.png` | VGA paladin portrait |
| <img src="src/assets/game/npcs/vga_ranger.png" width="32" height="32"> | `game/npcs/vga_ranger.png` | VGA ranger portrait |
| <img src="src/assets/game/npcs/vga_jester.png" width="32" height="32"> | `game/npcs/vga_jester.png` | VGA jester portrait |
| <img src="src/assets/game/npcs/vga_rogue.png" width="32" height="32"> | `game/npcs/vga_rogue.png` | VGA rogue portrait |
| <img src="src/assets/game/npcs/vga_evil_mage.png" width="32" height="32"> | `game/npcs/vga_evil_mage.png` | VGA evil mage portrait |

---

## 6. Monsters

Combat enemy sprites. Defined in `data/tile_manifest.json` under `"monsters"` and `data/monsters.json`. Loaded by `TileManifest` and used by `renderer.py :: _load_tile_sheet()` for overworld encounters and combat scenes. The skeleton sprite also serves as the fallback for any missing monster graphic.

| Preview | Name | File | Used By (monsters.json) |
|---------|------|------|------------------------|
| <img src="src/assets/game/monsters/giant_rat.png" width="32" height="32"> | giant_rat | `game/monsters/giant_rat.png` | Giant Rat |
| <img src="src/assets/game/monsters/skeleton.png" width="32" height="32"> | skeleton | `game/monsters/skeleton.png` | Skeleton, Skeleton Archer; also global fallback sprite |
| <img src="src/assets/game/monsters/orc.png" width="32" height="32"> | orc | `game/monsters/orc.png` | Orc, Orc Shaman |
| <img src="src/assets/game/monsters/goblin.png" width="32" height="32"> | goblin | `game/monsters/goblin.png` | Goblin |
| <img src="src/assets/game/monsters/zombie.png" width="32" height="32"> | zombie | `game/monsters/zombie.png` | Zombie |
| <img src="src/assets/game/monsters/wolf.png" width="32" height="32"> | wolf | `game/monsters/wolf.png` | Wolf |
| <img src="src/assets/game/monsters/dark_mage.png" width="32" height="32"> | dark_mage | `game/monsters/dark_mage.png` | Dark Mage; also a character creation portrait |
| <img src="src/assets/game/monsters/troll.png" width="32" height="32"> | troll | `game/monsters/troll.png` | Troll |

---

## 7. Overworld Landmarks

Unique one-of-a-kind tiles placed on the overworld map. Defined in `data/unique_tiles.json` and `data/tile_manifest.json` under `"unique_tiles"`. Loaded by `renderer.py :: _get_unique_tile_sprite()`.

| Preview | Name | File | Used For |
|---------|------|------|----------|
| <img src="src/assets/game/landmarks/moongate_active.png" width="32" height="32"> | moongate_active | `game/landmarks/moongate_active.png` | Active moongate portal; also used for seal_of_binding |
| <img src="src/assets/game/landmarks/moongate_dormant.png" width="32" height="32"> | moongate_dormant | `game/landmarks/moongate_dormant.png` | Dormant moongate (inactive stone circle) |
| <img src="src/assets/game/landmarks/ruined_tower.png" width="32" height="32"> | ruined_tower | `game/landmarks/ruined_tower.png` | Crumbling wizard tower ruin |
| <img src="src/assets/game/landmarks/sunken_shipwreck.png" width="32" height="32"> | sunken_shipwreck | `game/landmarks/sunken_shipwreck.png` | Shipwreck near shore |
| <img src="src/assets/game/landmarks/lava_vent.png" width="32" height="32"> | lava_vent | `game/landmarks/lava_vent.png` | Volcanic steam vent |
| <img src="src/assets/game/landmarks/smuggler_tunnel.png" width="32" height="32"> | smuggler_tunnel | `game/landmarks/smuggler_tunnel.png` | Hidden tunnel entrance |
| <img src="src/assets/game/landmarks/poison_swamp.png" width="32" height="32"> | poison_swamp | `game/landmarks/poison_swamp.png` | Toxic swamp area |
| <img src="src/assets/game/landmarks/treasure_hoard.png" width="32" height="32"> | treasure_hoard | `game/landmarks/treasure_hoard.png` | Hidden treasure cache |

---

## 8. Objects

Interactive objects placed on maps. Defined in `data/tile_manifest.json` under `"objects"`.

| Preview | Name | File | Used For |
|---------|------|------|----------|
| <img src="src/assets/game/items/chest.png" width="32" height="32"> | chest | `game/items/chest.png` | Treasure chests on overworld/towns |
| <img src="src/assets/game/items/town_gate.png" width="32" height="32"> | town_gate | `game/items/town_gate.png` | Town entrance gate |

---

## 9. Unassigned Tiles

These 32×32 sprites are not currently used in the game but are available in `src/assets/unassigned/` for future updates. They include alternate animation frames, additional monsters, terrain variants, and utility sprites.

### Characters (alternate frames)

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/unassigned/barbarian_f1.png" width="32" height="32"> | `unassigned/barbarian_f1.png` | Barbarian frame 1 |
| <img src="src/assets/unassigned/barbarian_f2.png" width="32" height="32"> | `unassigned/barbarian_f2.png` | Barbarian frame 2 |
| <img src="src/assets/unassigned/cleric_f1.png" width="32" height="32"> | `unassigned/cleric_f1.png` | Cleric frame 1 |
| <img src="src/assets/unassigned/cleric_f2.png" width="32" height="32"> | `unassigned/cleric_f2.png` | Cleric frame 2 |
| <img src="src/assets/unassigned/fighter_f1.png" width="32" height="32"> | `unassigned/fighter_f1.png` | Fighter frame 1 |
| <img src="src/assets/unassigned/fighter_f2.png" width="32" height="32"> | `unassigned/fighter_f2.png` | Fighter frame 2 |
| <img src="src/assets/unassigned/illusionist_f1.png" width="32" height="32"> | `unassigned/illusionist_f1.png` | Illusionist frame 1 |
| <img src="src/assets/unassigned/illusionist_f2.png" width="32" height="32"> | `unassigned/illusionist_f2.png` | Illusionist frame 2 |
| <img src="src/assets/unassigned/lark_f1.png" width="32" height="32"> | `unassigned/lark_f1.png` | Lark frame 1 |
| <img src="src/assets/unassigned/lark_f2.png" width="32" height="32"> | `unassigned/lark_f2.png` | Lark frame 2 |
| <img src="src/assets/unassigned/paladin_f1.png" width="32" height="32"> | `unassigned/paladin_f1.png` | Paladin frame 1 |
| <img src="src/assets/unassigned/paladin_f2.png" width="32" height="32"> | `unassigned/paladin_f2.png` | Paladin frame 2 |
| <img src="src/assets/unassigned/thief_f1.png" width="32" height="32"> | `unassigned/thief_f1.png` | Thief frame 1 |
| <img src="src/assets/unassigned/thief_f2.png" width="32" height="32"> | `unassigned/thief_f2.png` | Thief frame 2 |
| <img src="src/assets/unassigned/wizard_f1.png" width="32" height="32"> | `unassigned/wizard_f1.png` | Wizard frame 1 |
| <img src="src/assets/unassigned/wizard_f2.png" width="32" height="32"> | `unassigned/wizard_f2.png` | Wizard frame 2 |

### Monsters (additional / alternate frames)

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/unassigned/balron_demon_f1.png" width="32" height="32"> | `unassigned/balron_demon_f1.png` | Balron/Demon frame 1 |
| <img src="src/assets/unassigned/balron_demon_f2.png" width="32" height="32"> | `unassigned/balron_demon_f2.png` | Balron/Demon frame 2 |
| <img src="src/assets/unassigned/daemon_f1.png" width="32" height="32"> | `unassigned/daemon_f1.png` | Daemon frame 1 |
| <img src="src/assets/unassigned/daemon_f2.png" width="32" height="32"> | `unassigned/daemon_f2.png` | Daemon frame 2 |
| <img src="src/assets/unassigned/dragon_f1.png" width="32" height="32"> | `unassigned/dragon_f1.png` | Dragon frame 1 |
| <img src="src/assets/unassigned/dragon_f2.png" width="32" height="32"> | `unassigned/dragon_f2.png` | Dragon frame 2 |
| <img src="src/assets/unassigned/man_thing_f1.png" width="32" height="32"> | `unassigned/man_thing_f1.png` | Man-Thing frame 1 |
| <img src="src/assets/unassigned/man_thing_f2.png" width="32" height="32"> | `unassigned/man_thing_f2.png` | Man-Thing frame 2 |
| <img src="src/assets/unassigned/orc_f2.png" width="32" height="32"> | `unassigned/orc_f2.png` | Orc frame 2 |
| <img src="src/assets/unassigned/pirate_brigand_f2.png" width="32" height="32"> | `unassigned/pirate_brigand_f2.png` | Pirate/Brigand frame 2 |
| <img src="src/assets/unassigned/skeleton_f2.png" width="32" height="32"> | `unassigned/skeleton_f2.png` | Skeleton frame 2 |

### Terrain Variants

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/unassigned/brush_scrubland.png" width="32" height="32"> | `unassigned/brush_scrubland.png` | Scrubland/brush terrain |
| <img src="src/assets/unassigned/forest.png" width="32" height="32"> | `unassigned/forest.png` | Alternate forest tile |
| <img src="src/assets/unassigned/grass_plains.png" width="32" height="32"> | `unassigned/grass_plains.png` | Open grass plains |
| <img src="src/assets/unassigned/island_jungle.png" width="32" height="32"> | `unassigned/island_jungle.png` | Jungle/island vegetation |
| <img src="src/assets/unassigned/mountains.png" width="32" height="32"> | `unassigned/mountains.png` | Alternate mountain tile |
| <img src="src/assets/unassigned/water_deep_ocean.png" width="32" height="32"> | `unassigned/water_deep_ocean.png` | Deep ocean water |
| <img src="src/assets/unassigned/void_empty.png" width="32" height="32"> | `unassigned/void_empty.png` | Void/empty space |
| <img src="src/assets/unassigned/night_sky_stars.png" width="32" height="32"> | `unassigned/night_sky_stars.png` | Starry night sky |
| <img src="src/assets/unassigned/brick_wall.png" width="32" height="32"> | `unassigned/brick_wall.png` | Alternate brick wall |

### Structures & Landmarks

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/unassigned/town_village.png" width="32" height="32"> | `unassigned/town_village.png` | Village/settlement |
| <img src="src/assets/unassigned/shrine_church.png" width="32" height="32"> | `unassigned/shrine_church.png` | Shrine or church building |

### Vehicles & Objects

| Preview | File | Description |
|---------|------|-------------|
| <img src="src/assets/unassigned/horse.png" width="32" height="32"> | `unassigned/horse.png` | Horse mount |
| <img src="src/assets/unassigned/ship_frigate.png" width="32" height="32"> | `unassigned/ship_frigate.png` | Sailing ship/frigate |
| <img src="src/assets/unassigned/whirlpool.png" width="32" height="32"> | `unassigned/whirlpool.png` | Whirlpool frame 1 |
| <img src="src/assets/unassigned/whirlpool_f2.png" width="32" height="32"> | `unassigned/whirlpool_f2.png` | Whirlpool frame 2 |
| <img src="src/assets/unassigned/cursor_sparkle.png" width="32" height="32"> | `unassigned/cursor_sparkle.png` | Sparkle cursor effect |
