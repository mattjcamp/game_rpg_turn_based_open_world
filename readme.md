# Realm of Shadow

An Ultima III–inspired top-down, turn-based RPG built with Python and Pygame. Lead a party of four adventurers through a procedurally generated world of overworld exploration, town visits, dungeon delving, and tactical grid combat.

This is a hobby project. The programming was done with the help of AI (primarily Anthropic's Claude), and the codebase is designed to be approachable for anyone who wants to tinker, extend, or learn from it. See the [Developer Guide](docs/dev_guides/DEVELOPER_GUIDE.md) for tips on how to make changes yourself — even if you're not a programmer.

---

**[Check out the key features of the game here](docs/blog/screenshots_v0.2.0.md)** — here is a visual tour of the game showing the title screen, party creation, overworld, combat, dungeons, towns, and more.

---

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

- **[Developer Guide](docs/dev_guides/DEVELOPER_GUIDE.md)** — project structure, architecture, testing, making changes, working with AI, and game design philosophy. Start here if you want to contribute or modify the game.
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

All 177 tests should pass. Run this before and after making changes to catch regressions.

---

## Contributing

For project structure, architecture, testing details, making changes (including with AI), and game design notes, see the **[Developer Guide](docs/dev_guides/DEVELOPER_GUIDE.md)**.
