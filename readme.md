# Realm of Shadow

An Ultima III–inspired top-down, turn-based RPG built with Python and Pygame. Lead a party of four adventurers through a procedurally generated world of overworld exploration, town visits, dungeon delving, and tactical grid combat.

This is a hobby project. The programming was done with the help of AI (primarily Anthropic's Claude), and the codebase is designed to be approachable for anyone who wants to tinker, extend, or learn from it. See the section on [working with AI](#working-with-ai) below for tips on how to make changes yourself — even if you're not a programmer.

## Downloading & Playing

A pre-built macOS version is available on the [Releases](../../releases) page. To get started:

1. Download the `.zip` file from the latest release.
2. Unzip it — you'll get a folder called `RealmOfShadow`.
3. **Before opening the game**, you must clear the macOS quarantine flag. Open Terminal and run:
   ```
   xattr -cr ~/Downloads/RealmOfShadow/
   ```
   If you unzipped it somewhere other than Downloads, adjust the path — or drag the folder onto the Terminal window to fill it in automatically. You need to do this each time you download a new release.
4. Open the `RealmOfShadow` folder and double-click the file called **`RealmOfShadow`** (the one with no file extension) to launch the game.

> **First launch:** The game may take 10–20 seconds to appear the first time you run it while your system unpacks and caches the bundled libraries. Subsequent launches will be faster.

> **"Damaged and can't be opened" error:** If you skipped step 3 and macOS says the app is damaged, don't worry — the file isn't actually damaged. macOS shows this message for any downloaded app that isn't notarized with Apple. Run the `xattr -cr` command from step 3 and try again.

---

## Documentation & Reference

Before diving into the code, these documents give useful context on the game's design and mechanics:

- **[Player's Manual](docs/manuals/players_manual.md)** — races, classes, combat, spells, quests, items, and controls from the player's perspective. Illustrations are in `docs/manuals/images/`.
- **[Visual Style Guide](docs/dev_guides/STYLE_GUIDE.md)** — color palette, layout rules, sprite specs, and tile patterns. Derived from the Ultima III reference screenshots in `docs/research/`.
- **[Graphics Reference](docs/dev_guides/GRAPHICS_REFERENCE.md)** — tile IDs, sprite assignments, and asset file locations for every visual element.
- **[Combat Mechanics](docs/dev_guides/COMBAT_MECHANICS.md)** — the single source of truth for how attacks, damage, defense, and spells work under the hood.
- **[Ultima III Character Reference](docs/research/ULTIMA3_CHARACTERS.md)** — original game's race/class/attribute system, used as a design template.
- **[Ultima III StrategyWiki](https://strategywiki.org/wiki/Ultima_III:_Exodus)** — external reference for the original game.

The `docs/research/` folder also contains reference screenshots (`example_combat.webp`, `example_overview_map.png`, etc.) and sprite reference material in `docs/research/example_graphics/` that were used to guide the visual style.

---

## Getting Started

### What You Need

- **Python 3.9 or newer.** Check with `python3 --version` in a terminal. If you don't have it:
  - **Mac:** `brew install python3` (if you have Homebrew) or download from [python.org](https://www.python.org/downloads/macos/)
  - **Windows:** Download from [python.org](https://www.python.org/downloads/windows/) — check "Add Python to PATH" during install
  - **Linux:** `sudo apt install python3 python3-pip` (Ubuntu/Debian) or your distro's equivalent

- **Git** (to clone the repo). Most Macs and Linux systems have it already. Windows users can get it from [git-scm.com](https://git-scm.com/).

### Setup

1. **Clone the repository:**
   ```
   git clone https://github.com/mattjcamp/game_rpg_turn_based_open_world
   cd game_rpg_turn_based_open_world
   ```

2. **Install dependencies:**
   ```
   pip3 install -r requirements.txt
   ```
   This installs Pygame (graphics/audio) and NumPy (used for procedural music generation).

3. **Run the game:**
   ```
   python3 main.py
   ```

That's it. A window should open with the title screen.

### Controls

**Overworld:**

- Arrow keys or WASD — Move the party
- E — Examine the local area (zoomed-in view of the current tile)
- L — Load game
- P — Pause / open settings
- H — Help
- Walk into a town tile to enter it; walk into a dungeon tile to enter it
- ESC — Quit

**Towns:**

- Arrow keys or WASD — Move
- Walk into NPCs to talk; Space/Enter to advance dialogue
- ESC — Leave town

**Dungeons:**

- Arrow keys or WASD — Move
- Walk into monsters to fight; walk into chests to loot
- ESC on stairs — Leave dungeon

**Combat (tactical grid):**

- WASD — Move on the arena grid (each move takes a turn)
- Walk into a monster to melee attack
- Arrow keys — Navigate action menu
- Enter — Confirm action
- ESC — Flee attempt

**Examine mode:**

- Arrow keys or WASD — Walk around the zoomed-in area
- Q — Drop an item from inventory
- ESC — Return to overworld

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
│   │   ├── COMBAT_MECHANICS.md  ← Combat math reference
│   │   ├── GRAPHICS_REFERENCE.md ← Tile IDs, sprites, asset paths
│   │   └── STYLE_GUIDE.md      ← Visual design rules
│   ├── manuals/             ← Player-facing documentation
│   │   ├── players_manual.md
│   │   └── images/          ← Manual illustrations
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
├── tests/                   ← Test suite (166 tests)
│   ├── conftest.py          ← Headless pygame mock and shared fixtures
│   ├── test_combat.py
│   ├── test_examine.py
│   ├── test_party.py
│   ├── test_refactored.py
│   └── test_states.py
│
└── archive/                 ← Deprecated data files
```

### Architecture at a Glance

The game runs on a **state machine**. `game.py` owns the main loop and switches between states registered in `self.states`: overworld, town, dungeon, combat, and examine. Each state is a class that implements `enter()`, `exit()`, `handle_input()`, `update()`, and `draw()`. Transitions happen via `game.change_state("state_name")`.

**Rendering** is centralized in `renderer.py` — it's the largest file and handles all drawing for every state. Each state calls a specific renderer method in its `draw()` (e.g., `renderer.draw_overworld()`, `renderer.draw_combat_arena()`).

**Game data is JSON-driven.** Items, monsters, spells, classes, encounters, and effects are all defined in `data/*.json`. You can tweak stats, add new monsters, or rebalance weapons just by editing JSON — no code changes needed.

**Modules** are self-contained content packs in `modules/`. The default module, Keys of Shadow, provides its own overworld map and progression system. The module loader falls back to `data/` for anything a module doesn't override.

**Music** is procedurally generated at runtime using numpy waveforms — square waves, triangle waves, and noise — so there are no audio files to manage.

---

## Building a Standalone Executable

If you want to build the game yourself (or build for a platform not listed in Releases), you can package it into a standalone app using PyInstaller.

### Prerequisites

```
pip3 install pyinstaller
```

### Build

```
python3 build_game.py
```

This runs PyInstaller using the included `realm_of_shadow.spec` and produces a ready-to-distribute folder at `dist/RealmOfShadow/`. The build takes a minute or two. On macOS, the script automatically applies an ad-hoc code signature to reduce Gatekeeper warnings.

> **Note:** You need to build on each platform you want to support — a Mac produces a Mac build, Windows produces a Windows build, etc.

### Distribute

Zip the output folder and share it:

```
cd dist && zip -r RealmOfShadow-mac.zip RealmOfShadow/
```

Upload the zip to [itch.io](https://itch.io), attach it to a GitHub Release, or send it directly.

### Platform Notes for Recipients

**Windows** — Unzip the folder and double-click `RealmOfShadow.exe`. If Windows Defender SmartScreen shows a warning, click "More info" and then "Run anyway."

**Linux** — Unzip the folder, then in a terminal:
```
chmod +x RealmOfShadow/RealmOfShadow
./RealmOfShadow/RealmOfShadow
```

---

## Running the Tests

The test suite runs entirely headless (no display needed) using a mock pygame layer defined in `tests/conftest.py`.

```
pip3 install pytest
python3 -m pytest tests/ -v
```

All 166 tests should pass. Run this before and after making changes to catch regressions.

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
- Examine mode for zoomed-in tile exploration with persistent layouts
- Item dropping and ground item persistence
