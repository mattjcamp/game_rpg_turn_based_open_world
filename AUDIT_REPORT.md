# Realm of Shadow — Codebase Audit Report

**Date:** March 28, 2026
**Scope:** Technical debt, redundancy, separation of concerns
**Total codebase:** 42 Python files, ~63,000 lines

---

## Executive Summary

The codebase is functional and well-structured at the module level, with clean data/engine separation and a solid state machine architecture. However, five files carry the vast majority of the complexity and technical debt. Three systemic issues stand out:

1. **~780 lines of copy-pasted quest logic** across town.py, dungeon.py, and overworld.py
2. **renderer.py is an 18,295-line god class** with 169 methods and ~50 inline imports
3. **game.py is an 8,050-line god class** mixing module editing, quest management, and game state

The good news: the architecture is sound enough that these can be addressed incrementally without rewriting from scratch.

---

## The Big 5 Files

| File | Lines | Methods | Verdict |
|------|-------|---------|---------|
| renderer.py | 18,295 | 169 | God class — needs splitting |
| game.py | 8,050 | 140+ | God class — needs extraction |
| combat.py | 5,300 | — | Acceptable for a state machine |
| features_editor.py | 4,579 | — | Complex but self-contained |
| town.py | 2,789 | ~60 | Reasonable, but shares redundant code |

---

## Issue 1: Redundant Quest Logic (~780 duplicated lines)

The same quest patterns are copy-pasted across three state files with only minor variations (which container to use, NPC vs Monster object type).

### Quest item collection (3 identical copies)

| Function | File | Lines |
|----------|------|-------|
| `_collect_quest_item()` | town.py | 1372–1408 |
| `_collect_dungeon_quest_item()` | dungeon.py | 446–480 |
| `_collect_overworld_quest_item()` | overworld.py | 557–587 |
| `_collect_building_quest_item()` | overworld.py | 1639–1665 |

All four do the same thing: remove item, update `step_progress`, check `all(progress)`, play SFX.

### Quest kill tracking (3 identical copies)

| Function | File | Lines |
|----------|------|-------|
| `_check_quest_monster_kills()` | town.py | 312–390 |
| `_check_quest_monster_kills()` | overworld.py | 772–854 |
| `_check_module_quest_kills()` | dungeon.py | 152–226 |

All three: build Counter of kills, loop quest defs, match against step targets, update progress.

### Quest monster/item spawning (3+ copies per pattern)

| Pattern | town.py | dungeon.py | overworld.py |
|---------|---------|-----------|--------------|
| Monster spawning | lines 983–1151 | lines 227–315 | lines 1536–1624 |
| Item spawning | lines 1152–1216 | lines 316–436 | lines 1481–1535 |
| Guardian movement | — | lines 1079–1103 | lines 973–1003 |

### Recommended fix

Create `src/quest_manager.py` with shared methods:

- `collect_quest_item(game, quest_name, step_idx, item_name)` — one implementation, called by all states
- `check_quest_kills(game, killed_monsters)` — one implementation
- `spawn_quest_entities(game, location_key, tile_map, entity_list)` — parameterized spawner

**Estimated savings: ~500–600 lines eliminated, single source of truth for quest logic.**

---

## Issue 2: renderer.py God Class (18,295 lines)

This is the single largest maintenance risk. Key problems:

### ~50 inline imports in draw methods

Every frame, methods re-import `math`, `time`, `random` inside their bodies. Python caches modules so it's not catastrophic, but it's messy and indicates copy-paste development.

**Fix:** Move all imports to the top of the file. One-time change, no risk.

### Mega-methods

| Method | Lines | What it does |
|--------|-------|-------------|
| `draw_party_inventory_u3` | 988 | Entire inventory screen |
| `draw_combat_arena` | 562 | Entire combat screen |
| `draw_character_sheet_u3` | 503 | Entire character sheet |
| `_u3_draw_dungeon_tile` | 422 | Single dungeon tile with all variants |
| `draw_shop_u3` | 396 | Entire shop screen |

### Tile drawing duplicated 3x

`_u3_draw_town_tile` (171 lines), `_u3_draw_overworld_tile` (175 lines), and `_u3_draw_dungeon_tile` (422 lines) all follow the same pattern: check sprite override → try manifest → procedural fallback.

### Action screens duplicated 3x

`draw_town_action_screen`, `draw_building_action_screen`, `draw_dungeon_action_screen` — all draw a rect + border + title + option list with cursor.

### Recommended phased fix

1. **Phase 1 (quick, safe):** Move inline imports to top of file
2. **Phase 2:** Extract sub-renderers — `OverworldRenderer`, `TownRenderer`, `DungeonRenderer`, `UIRenderer`, `EffectRenderer`
3. **Phase 3:** Break mega-methods into focused helpers (inventory header/items/stats/buttons)
4. **Phase 4:** Unify tile drawing into a parameterized base + palette system

---

## Issue 3: game.py God Class (8,050 lines)

`game.py` mixes three distinct responsibilities:

1. **Game orchestration** — state machine, main loop, save/load (~1,500 lines)
2. **Module editor** — town/dungeon/quest editing UI (~3,500 lines, all the `_mod_*` methods)
3. **Quest system** — spawning, NPC assignment, quest log (~2,500 lines)

### Redundancy within game.py

- **Ring-walking spawn algorithm** duplicated 4 times (lines 1319, 1379, 1643, 1713) with slightly different max-ring values
- **`hasattr()` defensive checks** for attributes already initialized in `__init__` (lines 1467, 1469, 1776, 1794, 1812)
- **Location-to-key mapping** (`f"interior:{name}"`, `f"town:{name}"`, etc.) repeated in 3+ places

### `_title_new_game()` is 251 lines

This single method resets state, loads modules, initializes towns, assigns NPCs, and spawns quests. Should be 3–4 focused methods.

### Recommended fix

1. Extract `src/quest_manager.py` — all `_spawn_quest_*`, `_register_quest_*`, `_build_quest_log`, quest state tracking
2. Extract `src/module_editor.py` — all `_mod_*` methods and fields (this alone removes ~3,500 lines)
3. Extract ring-walking algorithm into a shared `_find_spawn_position()` helper

---

## Issue 4: Test Code in Production

**overworld.py line 145:** `self._spawn_test_spellcaster()` — spawns a Dark Mage on every fresh overworld entry. The entire function (lines 208–230) is debug code.

**Fix:** Remove or gate behind a `DEBUG` flag.

---

## Issue 5: Separation of Concerns

### What's good

- State machine architecture is clean — `BaseState` provides a proper interface
- Data files (JSON) are well-separated from engine code
- `data_registry.py` provides centralized cached access to game data
- `InventoryMixin` properly shares inventory UI across states
- Rendering is mostly delegated to `renderer.py` (states don't draw directly)

### What needs work

- **Renderer inspects game domain objects** — NPC types, quest status, monster race checks all happen inside render methods. Should pass rendering hints instead.
- **Quest state mutations in render pipeline** — `draw()` method in overworld.py syncs quest status onto NPC objects before rendering. Should happen in `update()`.
- **Building interior logic sprawl** — ~400 lines of building-specific code scattered across overworld.py (entry/exit, spawning, NPC movement, collection, combat). Could be a `BuildingInteriorHandler` if it grows further.

---

## Issue 6: Hardcoded Magic Numbers

Numbers like guardian leash distance (4), intercept range (6 or 8), NPC wander range (3), message timers (2500, 3000, 4000ms), and spawn probabilities (0.08) are scattered across all state files with no constants.

**Fix:** Add to `settings.py` or a new `constants.py`:

```python
GUARDIAN_LEASH = 4
GUARDIAN_INTERCEPT_RANGE = 6
NPC_WANDER_RANGE = 3
MSG_TIMER_SHORT = 2500
MSG_TIMER_LONG = 4000
```

---

## What's Already Good

These are strengths worth preserving:

- **Clean state machine** — BaseState interface, proper enter/exit lifecycle
- **Data/code separation** — modules/ vs src/ vs data/ is well-organized
- **No circular imports** — dependency graph is acyclic (late imports in inventory_mixin are intentional)
- **Minimal debug markers** — only 1 TODO and 1 TEST marker found across 63K lines
- **Consistent patterns** — even the duplicated code follows consistent conventions
- **Module system** — clean abstraction for loading user-created content

---

## Recommended Refactoring Priority

### Do First (high impact, low risk)

1. **Remove test spellcaster** from overworld.py (5 minutes)
2. **Move renderer inline imports** to file top (~50 imports, 30 minutes)
3. **Extract `quest_manager.py`** with shared collect/kill/spawn logic (2–3 hours, eliminates ~600 lines of duplication)

### Do Next (high impact, moderate effort)

4. **Extract `module_editor.py`** from game.py (~3,500 lines moved, 2–3 hours)
5. **Centralize magic numbers** into constants (1 hour)
6. **Break up mega-methods** in renderer.py — start with `draw_party_inventory_u3` (988 lines → 4 helpers)

### Do Later (architectural, higher risk)

7. **Split renderer.py** into sub-renderers (4–6 hours)
8. **Unify tile drawing** into parameterized base (2–3 hours)
9. **Extract rendering hints** — stop renderer from inspecting game objects directly
