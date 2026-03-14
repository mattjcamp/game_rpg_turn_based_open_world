# Developer Guide

This guide covers everything you need to know to work on the Realm of Shadow codebase — the project layout, architecture, testing, data-driven design, the module system, and tips for making changes with or without AI assistance. For setup instructions (cloning, installing, running), see the [main README](../../README.md).

---

## Project Structure

```
game_rpg_turn_based_open_world/
├── main.py                  ← Entry point — run this to play
├── requirements.txt         ← Python dependencies (pygame, numpy)
│
├── data/                    ← Game data (all JSON, easy to edit)
│   ├── items.json           ← Weapons, armor, consumables, shop inventories
│   ├── monsters.json        ← Monster stats, drops, and behavior
│   ├── spells.json          ← Spell definitions and effects
│   ├── effects.json         ← Buff/debuff effect definitions
│   ├── encounters.json      ← Encounter tables by terrain
│   ├── races.json           ← Playable race stats and bonuses
│   ├── party.json           ← Default starting party configuration
│   ├── potions.json         ← Potion effects
│   ├── config.json          ← Player settings (music, etc.)
│   ├── character_tiles.json ← Character sprite assignments
│   ├── unique_tiles.json    ← Special overworld tile definitions
│   ├── u4_tiles.json        ← Tile mapping for Ultima IV–style sprites
│   ├── classes/             ← One JSON file per character class
│   │   ├── fighter.json
│   │   ├── cleric.json
│   │   ├── wizard.json
│   │   ├── thief.json
│   │   ├── paladin.json
│   │   ├── ranger.json
│   │   ├── druid.json
│   │   └── alchemist.json
│   └── saves/               ← Save game slots
│
├── docs/                    ← All documentation
│   ├── dev_guides/          ← Developer reference
│   │   ├── DEVELOPER_GUIDE.md   ← This file
│   │   ├── COMBAT_MECHANICS.md  ← Combat math reference
│   │   ├── GRAPHICS_REFERENCE.md ← Tile IDs, sprites, asset paths
│   │   └── STYLE_GUIDE.md      ← Visual design rules
│   ├── manuals/             ← Player-facing documentation
│   │   ├── players_manual.md
│   │   └── images/          ← Manual illustrations
│   ├── blog/                ← Screenshots and visual tours
│   └── research/            ← Design reference material
│       ├── ULTIMA3_CHARACTERS.md
│       ├── dnd_5e_cleric_spells_reference.md
│       ├── example_combat.webp
│       ├── example_overview_map.png
│       ├── example_dungeon.jpg
│       └── example_graphics/ ← Sprite reference images
│
├── src/                     ← Game source code
│   ├── game.py              ← Main game loop, state machine, menus
│   ├── settings.py          ← Constants, tile definitions, colors
│   ├── tile_map.py          ← Overworld map grid and generation
│   ├── camera.py            ← Viewport that follows the party
│   ├── renderer.py          ← All drawing: tiles, sprites, HUD, UI panels
│   ├── party.py             ← Party, characters, inventory, equipment
│   ├── monster.py           ← Monster definitions and factory functions
│   ├── combat_engine.py     ← D&D-style dice rolls, attack resolution
│   ├── combat_effect_renderer.py ← Visual effects for combat (sparks, etc.)
│   ├── music.py             ← Procedural chiptune music (numpy waveforms)
│   ├── save_load.py         ← Save/load game state to JSON
│   ├── data_loader.py       ← Reads JSON data files with module fallback
│   ├── module_loader.py     ← Discovers and loads game modules
│   ├── game_time.py         ← In-game clock and day/night cycle
│   ├── town_generator.py    ← Procedural town layouts and NPCs
│   ├── dungeon_generator.py ← Procedural dungeon rooms and corridors
│   ├── assets/              ← Sprite sheets, tile images (~375 files)
│   └── states/              ← Game state implementations
│       ├── base_state.py    ← Base state interface (enter/exit/update/draw)
│       ├── overworld.py     ← Overworld exploration
│       ├── town.py          ← Town interior exploration
│       ├── dungeon.py       ← Dungeon crawling
│       ├── combat.py        ← Tactical grid combat
│       ├── combat_effects.py ← Combat buff/debuff system
│       ├── examine.py       ← Zoomed-in tile examination
│       └── inventory_mixin.py ← Shared inventory UI behavior
│
├── modules/                 ← Game content modules
│   └── keys_of_shadow/      ← Default adventure module
│       ├── module.json      ← Module manifest and progression config
│       └── overworld.json   ← Custom overworld map data
│
├── tests/                   ← Test suite (177 tests)
│   ├── conftest.py          ← Headless pygame mock and shared fixtures
│   ├── test_combat.py
│   ├── test_examine.py
│   ├── test_party.py
│   ├── test_refactored.py
│   └── test_states.py
│
└── archive/                 ← Deprecated data files
```

---

## Architecture

### State Machine

The game runs on a **state machine**. `game.py` owns the main loop and switches between states registered in `self.states`: overworld, town, dungeon, combat, and examine. Each state is a class that implements `enter()`, `exit()`, `handle_input()`, `update()`, and `draw()`. Transitions happen via `game.change_state("state_name")`.

The base interface is defined in `src/states/base_state.py`. When adding a new game screen or mode, create a new state class that inherits from `BaseState`, register it in the `self.states` dictionary in `game.py`, and transition to it from another state.

### Rendering

All drawing is centralized in `renderer.py` — it's the largest file in the project. Each state calls a specific renderer method in its `draw()` call (e.g., `renderer.draw_overworld()`, `renderer.draw_combat_arena()`, `renderer.draw_examine_area()`). The renderer owns no game state; it just receives data and draws it.

### JSON-Driven Data

Game data is JSON-driven. Items, monsters, spells, classes, encounters, and effects are all defined in `data/*.json`. You can tweak stats, add new monsters, or rebalance weapons just by editing JSON — no code changes needed. The `data_loader.py` module reads these files and provides fallback resolution when modules override specific data.

### Module System

Modules are self-contained content packs in `modules/`. The default module, Keys of Shadow, provides its own overworld map, progression system, towns, dungeons, and unique tiles. Each module has a `module.json` manifest that defines metadata, world configuration, towns, dungeons, quests, and unique tiles.

The module loader (`module_loader.py`) discovers modules on disk and falls back to `data/` for anything a module doesn't override. The in-game module editor allows players to create and modify modules without touching JSON files directly.

#### Unique Tiles

Unique tiles are special one-of-a-kind map features defined per module. Each unique tile has a name, description, base terrain type (for theming), an optional overworld graphic, and optionally a custom examine-screen layout. The examine layout includes both painted tile graphics and placed items, both defined through the in-game editor.

Unique tile data lives in the module's `module.json` under the `unique_tiles` key. When a new game starts, `load_unique_tiles()` in `tile_map.py` resolves tile definitions by checking the module manifest first, then a standalone `unique_tiles.json`, then the global fallback in `data/`.

### Procedural Music

Music is procedurally generated at runtime using numpy waveforms — square waves, triangle waves, and noise — so there are no audio files to manage. The `music.py` module handles all audio generation and playback.

---

## Running the Tests

The test suite runs entirely headless (no display needed) using a mock pygame layer defined in `tests/conftest.py`.

```
pip3 install pytest
python3 -m pytest tests/ -v
```

All 177 tests should pass. Run this before and after making changes to catch regressions. The tests cover combat mechanics, party management, state transitions, examine-area logic, and more.

---

## Making Changes

### Data Changes (Easiest)

Adding items, monsters, spells, or tweaking stats usually means editing a JSON file in `data/`. These changes take effect immediately the next time you start a new game. Examples of common data changes:

- Add a weapon: edit `data/items.json`, add an entry under `"weapons"` with power, icon, price, and description fields.
- Add a monster: edit `data/monsters.json`, add an entry with HP, AC, attacks, drops, and XP.
- Add a spell: edit `data/spells.json`, add an entry with cost, effect, and targeting info.
- Tweak class stats: edit the relevant file in `data/classes/`.

### Code Changes

For anything beyond data tweaks, the key files to know are:

- **`src/game.py`** — the central hub. Owns the main loop, menu screens, module editor, and state transitions. This is a large file; search for method names rather than scrolling.
- **`src/renderer.py`** — all drawing code. Also large. Find the right section by searching for the method called by the state you're working on.
- **`src/states/*.py`** — game logic for each mode. These are smaller and more focused. Each state handles its own input, update, and draw.
- **`src/tile_map.py`** — overworld generation and tile placement.
- **`src/combat_engine.py`** — dice rolls, attack resolution, damage calculation.

### Adding a New State

1. Create a new file in `src/states/` that subclasses `BaseState`.
2. Implement `enter()`, `exit()`, `handle_input()`, `update()`, and `draw()`.
3. Add a renderer method for the state's visuals in `renderer.py`.
4. Register the state in `game.py`'s `self.states` dictionary.
5. Transition to it from another state using `self.game.change_state("your_state")`.

---

## Working with AI

Most of the code in this project was written with the help of AI, primarily using **Claude** (Anthropic's AI assistant). This is a practical and effective way to build and modify a game like this, even if you're not deeply experienced with Python or Pygame.

### How to make changes using Claude

1. **Start a conversation** in the Claude app (claude.ai) or Claude Code (command-line tool).

2. **Give Claude context.** Share the relevant file(s) you want to change. For example, if you want to add a new monster, you might paste in `data/monsters.json` and a snippet from `src/monster.py` and ask Claude to add one. If you want to change how combat works, share `src/states/combat.py` and `docs/dev_guides/COMBAT_MECHANICS.md`.

3. **Describe what you want in plain language.** You don't need to specify exact code. Examples of good prompts:
   - "Add a new monster called Shadow Wolf with 30 HP, 14 AC, that does 2d6 damage and drops 50 XP"
   - "Make forest tiles spawn more items when examined"
   - "Change the combat music to be slower and more ominous"
   - "Add a new spell called Fireball that hits all enemies for 3d6 damage"

4. **Ask Claude to explain what it changed** if you want to understand the code better.

5. **Run the tests** after making changes: `python3 -m pytest tests/ -v`

### Tips for working with AI on this codebase

- **Data changes are the easiest.** Adding items, monsters, spells, or tweaking stats usually means editing a JSON file in `data/`. Claude can do this reliably and you can verify the changes by just reading the JSON.

- **The state machine is the key concept.** If you tell Claude you want to add a new game screen or mode, mention that the game uses a state machine and point it to `src/states/base_state.py` as a template.

- **`renderer.py` is large.** If you want visual changes, tell Claude which state's drawing you want to modify (e.g., "the overworld HUD" or "the combat arena floor tiles") so it can find the right section.

- **Ask for tests.** When Claude adds new features, ask it to write tests too. The existing test suite in `tests/` provides good examples of the testing patterns used.

- **Share the style guide.** If you want UI or visual changes that match the game's aesthetic, share `docs/dev_guides/STYLE_GUIDE.md` with Claude so it follows the established color palette and layout conventions.

---

## Game Design

### What stays faithful to Ultima III

- Party of 4 adventurers with races, classes, and stats
- Turn-based tactical combat on a grid
- Top-down tile-based world view
- Overworld with towns and dungeons to discover
- Character progression through leveling and equipment
- Procedural chiptune music

### What's different

- Procedurally generated overworld (coastlines, biomes, terrain)
- Randomly generated town layouts and NPC placement
- Randomly generated dungeon rooms, corridors, and encounters
- Modular content system (adventures are self-contained modules)
- In-game module editor for creating and customizing content
- Examine mode for zoomed-in tile exploration with persistent layouts
- Custom examine-screen painting and item placement per unique tile
- Item dropping and ground item persistence
