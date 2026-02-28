# Realm of Shadow - An Ultima III Inspired RPG

A hobby RPG project built with Python and Pygame, inspired by the classic Ultima III: Exodus.

- [Detailed Ultima 3 Information](https://strategywiki.org/wiki/Ultima_III:_Exodus)
- [Visual Style Guide](STYLE_GUIDE.md) — color palette, layout rules, sprite specs, and tile patterns derived from the `example_*` reference images

## Vision

An Ultima III-inspired (not exact) top-down, turn-based RPG with a party of 4 adventurers. The core gameplay loop follows the classic overworld-town-dungeon structure with traditional character progression and loot. The key twist is that the **world content is randomly generated** — each new game produces a fresh overworld map with procedurally generated towns and dungeons, giving every playthrough a unique world to explore.

### What stays faithful to Ultima III
- Party of 4 adventurers with races, classes, and stats
- Turn-based combat
- Top-down tile-based view
- Overworld map with towns and dungeons to discover
- Character progression (leveling, equipment, spells)
- Loot as both random drops and standard items

### What's new
- Procedurally generated overworld (coastlines, biomes, terrain)
- Randomly generated towns (layouts, NPC placement, shops)
- Randomly generated dungeons (rooms, corridors, encounters)
- Themed or hybrid generation planned for later iterations

## Tech Stack

- **Python 3** — chosen for rapid iteration and readability; this project will change a lot
- **Pygame** — lightweight, good fit for tile-based rendering, simple input/audio

## Running the Game

```bash
pip install pygame
python3 main.py
```

### Controls
- Arrow keys or WASD — Move the party
- Walk into NPCs — Talk to them
- Space / Enter — Advance NPC dialogue
- ESC — Leave town (when inside) / Leave dungeon (on stairs) / Quit (on overworld)

## Project Structure

```
ultima3_clone/
├── main.py              ← Entry point
├── requirements.txt     ← Dependencies
├── assets/              ← Future sprites and sounds
├── data/                ← Future map data, item tables
└── src/
    ├── settings.py      ← Constants, tile definitions, colors
    ├── tile_map.py      ← Map grid and test map
    ├── party.py         ← Party and character management
    ├── camera.py        ← Viewport that follows the party
    ├── renderer.py      ← Tile rendering, party marker, HUD, NPC drawing
    ├── game.py          ← Game loop and state machine
    ├── town_generator.py    ← Town map + NPC generation
    ├── dungeon_generator.py ← Procedural dungeon generation
    ├── monster.py           ← Monster class and factory functions
    ├── combat_engine.py     ← D&D dice rolls, attack resolution, damage
    └── states/
        ├── base_state.py    ← Base state interface
        ├── overworld.py     ← Overworld exploration state
        ├── town.py          ← Town interior exploration state
        ├── dungeon.py       ← Dungeon exploration state
        └── combat.py        ← Turn-based combat state
```

## Development Log

### Session 1 — Initial Prototype
- Discussed game vision and design decisions
- Chose Python + Pygame as the tech stack
- Built the foundational engine:
  - Game loop with state machine architecture
  - Tile-based map system with 9 tile types (grass, water, forest, mountain, town, dungeon, path, sand, bridge)
  - Camera/viewport that follows the party
  - Renderer with colored rectangles and simple tile icons (trees, mountains, houses, cave entrances)
  - Party system with 4 starter characters (Fighter, Cleric, Mage, Thief)
  - Arrow key / WASD movement with collision detection
  - HUD showing position, terrain, and party stats
  - A 40x30 hardcoded test island with ocean border, beaches, mountains, forest, a river with bridge, a town, and a dungeon entrance

### Session 2 — Town Interiors
- Added 5 new town-interior tile types: floor, wall, counter, door, exit
- Built a town generator that creates a 20x20 walled town with:
  - Weapon shop (Gruff's Armaments) with counter
  - Armor shop (Helga's Armor Emporium) with counter
  - Inn (The Sleeping Griffin) with bar counter
  - Elder's house (Elder Morath with quest dialogue)
  - Central grass courtyard
  - 3 wandering villagers with unique dialogue
  - Exit gate at the bottom
- NPC system with dialogue cycling (bump to talk, Space/Enter to advance)
- Color-coded NPC sprites by type (gold=shopkeep, blue=innkeeper, purple=elder, green=villager)
- Name tags floating above each NPC
- TownState handles separate camera, movement, NPC interaction, and exit back to overworld
- Dialogue box UI with dismiss/continue hints
- Town-specific HUD showing town name, position, controls hint
- Renderer expanded with brick walls, counters, doors, exit arrow, and NPC drawing
- Seamless overworld ↔ town transitions (walk onto town tile to enter, walk onto exit or press ESC to leave)

### Session 3 — Procedural Dungeons
- Added 5 dungeon tile types: stone floor, stone wall, stairs up, chest, trap
- Built a procedural dungeon generator using rooms-and-corridors algorithm:
  - Carves 6–10 random rooms out of solid stone
  - Connects rooms with L-shaped corridors
  - Places entrance stairs in the first room
  - Scatters treasure chests (60% chance per room) in later rooms
  - Hides traps (35% chance) in rooms and corridors
  - Every dungeon is unique — generated fresh each time you enter
- DungeonState with full exploration:
  - Walk onto chests to loot gold (10–50 per chest, added to party total)
  - Step on traps for damage to a random party member (3–8 HP)
  - Chests and traps disappear after triggering (replaced with floor)
  - Can only exit by standing on the stairs and pressing ESC
- Dark dungeon visuals: stone block walls, cracked floors, stair steps with up-arrow, golden chests with locks, subtle red trap markers
- Dungeon-specific HUD with dark red theme, gold counter, and chests-found tracker
- Knight avatar with sword/shield updated to work across all three map types

### Session 4 — D&D Turn-Based Combat
- Built a complete D&D 5e-inspired combat engine:
  - Dice rolling: d20 attack rolls, variable damage dice per weapon
  - Ability modifiers: (stat − 10) / 2 for STR, DEX, INT
  - Attack resolution: d20 + attack bonus vs AC, natural 1 always misses, natural 20 always crits
  - Critical hits double the damage dice (not the bonus)
  - Initiative: d20 + DEX modifier determines who acts first
- Monster system with 3 monster types:
  - Giant Rat (HP 8, AC 12) — weak but fast
  - Skeleton (HP 16, AC 13) — undead warrior
  - Orc (HP 22, AC 13) — tough and hard-hitting
  - Each has unique color, damage dice, and XP/gold rewards
- Full CombatState with phase-based turn system:
  - Initiative phase → Player turn → Monster turn → repeat
  - Player actions: Attack (d20 + STR mod vs AC), Defend (+2 AC until next turn), Flee (DEX check vs DC 10)
  - Failed flee attempt gives the monster a free attack
  - Victory awards XP and gold, removes monster from dungeon
  - Defeat revives the fighter with 1 HP
- Combat screen with dedicated UI:
  - Large monster sprite at top with HP bar and AC display
  - Color-coded scrolling combat log (hits in green, misses in gray, crits in yellow, damage in red)
  - Player info panel with HP bar, AC, weapon, and stat breakdowns
  - Action menu with arrow-key selection and phase-appropriate labels
- Monsters placed in procedurally generated dungeons:
  - 50% chance per room (excluding entrance) to spawn a random monster
  - Monsters visible on the dungeon map as colored sprites with red eyes
  - Walk into a monster to initiate combat (bump-to-fight)
- Party members now have real weapons: Roland (Long Sword 1d8), Mira (Mace 1d6), Theron (Staff 1d6), Sable (Dagger 1d4+DEX)

### Session 5 — Tactical Combat Arena + Ultima III Reskin
- Converted combat from a portrait-style stat screen to a **top-down tactical arena**:
  - 15×10 tile grid with brick walls and open floor
  - Player and monster positioned on the arena as moveable sprites
  - **WASD movement** during player's turn (each move consumes the turn)
  - **Bump-to-attack**: walk into the monster's tile to melee attack
  - Attack menu option requires **adjacency** (Chebyshev distance ≤ 1) — grayed out when too far
  - Monster AI: chases the player 1 tile per turn, attacks when adjacent
- Reskinned combat screen to match **Ultima III visual style** (see `STYLE_GUIDE.md`):
  - Pure black background with bright blue `(68,68,255)` panel borders
  - Left-side map / right-side stat panels layout (matching the classic split-screen)
  - Dark purple brick-pattern wall tiles, black floor with scattered green dot/cross decorations
  - Simple white stick-figure player sprite, colored block-figure monster sprites
  - All text uppercase in monospace font with retro color coding (orange names, white stats, blue labels)
  - Zero-padded stat numbers (`HP:0030/0030 AC:12`)
  - Combat log with color-coded lines in blue-bordered scrolling panel
  - Bottom status bar with control hints

### Next Steps
- flesh out differences in characters more clearly
- implement experience and leveling system
- create quest procedure
- flesh out early spells and items for for level 1 to 2