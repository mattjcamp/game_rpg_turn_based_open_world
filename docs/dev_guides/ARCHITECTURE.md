# Architecture

Turn-based open-world RPG built with Pygame. This document captures the
key design decisions so that any contributor (human or AI) can work on
the codebase consistently.

## Guiding Principles

1. **Separate concerns.** Data models, editor/business logic, and
   rendering live in distinct layers. A UI reorganization should never
   require touching data-loading code, and vice versa.

2. **Typed contracts between layers.** Dataclasses in `editor_types.py`
   define the shape of data flowing from logic → renderer. The renderer
   never reaches back into the editor to read state directly.

3. **Dependency injection over globals.** Editor classes receive the
   resources they need (module paths, renderer hooks) through their
   constructor, not by importing or reaching into the Game singleton.

4. **Incremental migration.** Legacy patterns (positional lists, raw
   dicts) may still exist in some editors. New code should use the typed
   patterns (`FieldEntry`, render-state dataclasses). Convert legacy
   code when you touch it.

## Directory Layout

```
src/
  game.py               # Game loop, state machine, screen routing
  features_editor.py    # Features editor: all state, input, data I/O
  editor_types.py       # Shared dataclasses (FieldEntry, render states)
  renderer.py           # All drawing / UI rendering
  map_editor.py         # Standalone map editor (launched from features)
  map_editor_renderer.py
  settings.py           # Constants (screen size, FPS, colours)
  data_loader.py        # Load game data from JSON
  data_registry.py      # Centralised data cache
  party.py              # Party / character model
  monster.py            # Monster model
  tile_map.py           # Tile map utilities
  tile_manifest.py      # Sprite manifest loader
  module_loader.py      # Module (mod) packaging
  save_load.py          # Save / load game state
  music.py              # Audio
  camera.py             # Viewport camera
  states/               # State-machine states (overworld, town, etc.)
data/
  *.json                # Default game data files
```

## Layer Responsibilities

### Data Layer (`data_loader.py`, `data_registry.py`, `data/*.json`)
- Reads/writes JSON on disk.
- Provides typed accessors (e.g. `load_items()`, `load_spells()`).
- No awareness of UI, editors, or Pygame.

### Editor Layer (`features_editor.py`, `editor_types.py`)
- `FeaturesEditor` owns **all** editor state and logic.
- Handles keyboard input, manages navigation (levels, cursors, scrolls).
- Loads/saves data via `data_loader` or direct JSON I/O.
- Exposes a single `get_render_state() → FeaturesRenderState` for the
  renderer. Never draws anything itself.
- Communicates with Game through a thin callback interface
  (`on_close`, `on_show_unsaved_dialog`, etc.), not by mutating Game
  attributes directly.

### Render Layer (`renderer.py`, `map_editor_renderer.py`)
- Pure output: takes a state object, draws pixels.
- `draw_features_screen(state: FeaturesRenderState)` is the single
  entry point for features-editor rendering.
- No editor logic, no data loading, no input handling.

### Game Shell (`game.py`)
- Owns the Pygame loop, clock, screen, state machine.
- Routes input to the active subsystem (state, editor, title screen).
- Instantiates `FeaturesEditor` and delegates to it when the features
  screen is active.
- Should stay lean — avoid adding editor-specific logic here.

## Features Editor Categories

The features editor has 5 top-level categories:

| Category  | Editor key | Notes |
|-----------|-----------|-------|
| Modules   | (special) | Opens module browser, not a field editor |
| Spells    | `spells`  | 3-level nav: casting type → level → spell |
| Items     | `items`   | Flat list with sections (weapons, armor, etc.) |
| Monsters  | `monsters`| Flat list |
| Maps      | `maps`    | Hub with template folders + Tiles sub-folder |

The **Maps** hub contains:
- Overview Templates, Dungeon Templates, Examine Templates,
  Enclosure Templates, Battle Templates
- Tiles folder → Tile Types, Tile Gallery (via `_editor_redirect`)

## Data Flow (Features Editor)

```
User presses key
  → Game.update() dispatches event to FeaturesEditor.handle_input()
    → FeaturesEditor mutates its own state
    → (optionally loads/saves JSON)

Game.draw()
  → state = FeaturesEditor.get_render_state()
  → Renderer.draw_features_screen(state)
```

## Patterns

### FieldEntry
All editor field lists use `FieldEntry(label, key, value, field_type,
editable)` from `editor_types.py`. Legacy `[label, key, value, type,
editable]` lists may still exist in the module editor — convert when
touching that code.

### Editor Context (`_editor_ctx()`)
Each editor type provides a context dict with lambdas for generic
operations (get list, get cursor, save fields, get choices, etc.).
This allows the field-editing handler to work identically across all
editor types without `if editor == "spells"` branches.

### Render State Dataclasses
Each editor has a sub-dataclass (`SpellEditorRS`, `ItemEditorRS`, etc.)
nested inside `FeaturesRenderState`. The renderer destructures these
to draw the appropriate UI. Adding a new editor means adding a new
sub-dataclass — no signature changes needed.

### Navigation Levels
- Level 0: Category selector
- Level 1: List browser (spells, items, tiles, etc.)
- Level 2: Field editor
- Level 3+: Deeper (tile folders, gallery categories, pixel editor)
