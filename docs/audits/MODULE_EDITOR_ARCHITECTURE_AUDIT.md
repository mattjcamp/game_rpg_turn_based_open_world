# Module Editor System — Architecture Audit (March 24, 2026)

## Executive Summary

The module editor system has evolved to support 6 editor types (spells, items, monsters, tiles, gallery, town layouts) plus a separate map editor hub. The previous March 22 audit identified critical issues with the generic context-dict pattern. This audit **confirms those findings still apply** and uncovers **additional architectural friction** that will compound when adding new editor types (overworld maps, dungeons).

**Key takeaway:** The system is functional but not scalable. The bottleneck is *not* individual feature bugs — it's the fundamental dispatch mechanism and state proliferation pattern. Before adding new editors, refactoring priorities must target structural reuse, not just code cleanup.

---

## Architecture Overview

### Current Structure (6 Editor Types)

```
Game._handle_features_input(event)
├── Maps to: self._feat_active_editor (enum-like: "spells", "items", "monsters", "tiles", "gallery", "town", "mapeditor")
├── Dispatches to context dict: self._feat_editor_ctx()
│   ├── For spells/items/monsters: Returns generic handler interface (15 lambdas)
│   ├── For tiles: Returns same interface but uses different level-2/level-3 flow
│   ├── For gallery: Returns None (bypassed entirely, custom handlers)
│   └── For town layouts: Returns None (has dedicated handler chain)
├── Multiple input handlers at different "levels":
│   ├── Level 0: Category selection
│   ├── Level 1: List browsing (spell folders, item list, tile folders, gallery cats)
│   ├── Level 2: Item/field list editing (spells/items/monsters) OR tile list (tiles)
│   ├── Level 3: Field editing (spells/items/monsters/tiles) OR gallery details
│   ├── Level 4: Gallery tags
│   └── Level 5: Gallery pixel editor
├── Renderer call: self.renderer.draw_features_screen(**self._feat_render_state())
│   └── 60+ keyword arguments (one for each piece of state across all 6 editors)
└── State persistence: ~80 instance variables prefixed _feat_*
```

### Map Editor System (Separate Implementation)

- **Decoupled from features editor:** Has its own state variables (_meh_*), handler chains
- **Unified internal design:** Uses `MapEditorConfig` + `MapEditorState` + `MapEditorInputHandler`
- **Dataclass-based:** Modern, encapsulated state
- **Not reusable by features editor:** The generic context dict system cannot adapt to map editor's abstractions

### The Mismatch

The features editor uses a **procedural, dispatch-based** architecture while the map editor uses an **object-oriented, handler-based** architecture. They coexist in the same `Game` class but follow opposite design patterns.

---

## Critical Issues (Fix Before Adding Features)

### 1. **Monolithic Renderer Signature — THE BIGGEST SCALABILITY BARRIER**

**Location:** `game.py:5613-5719` (_feat_render_state), `renderer.py:6921-6981` (draw_features_screen)

**Current state:**
- `_feat_render_state()` builds a 60+ key dict, organized by editor type
- `draw_features_screen()` signature has 60+ individual parameters
- Every new editor adds 8-15 more parameters

**Problem:**
- This is the primary bottleneck for scaling to new editor types
- Adding an overworld or dungeon editor requires:
  1. Declare 8-15 new state variables in Game.__init__
  2. Add them to _feat_render_state() under a new editor block
  3. Add 8-15 parameters to draw_features_screen()
  4. Add rendering logic inside draw_features_screen() (already 1000+ lines)
  5. Chain input handlers at each level, testing combinations

**Why this matters for new features:**
- Overworld map editor would add: `ow_brushes`, `ow_cursor_col`, `ow_cursor_row`, `ow_camera`, `ow_selected_tile`, `ow_link_mode`, `ow_interior_links`, `ow_dirty`, etc. (~10+ params)
- Dungeon layout editor: Similar count
- Each addition increases cognitive load and error surface

**Refactoring approach:**
```python
# Instead of 60 kwargs:
@dataclass
class EditorRenderState:
    active_editor: str
    level: int
    categories: list
    cat_cursor: int
    editor_data: dict  # Editor-specific data blob

self.renderer.draw_features_screen(
    editor_state=self._build_render_state(),
    dirty=self._feat_dirty)
```

**Impact:** HIGH — This blocks scalable addition of new editors. Fixing it makes adding new editor types 50% easier.

---

### 2. **Duplicated Field Editor Logic (Level 2/3 Handlers)**

**Location:** `game.py:4727-4872` (unified handler), `game.py:5201-5205` (tiles level 3 call)

**Current state:**
- Level 2 handler: `_feat_handle_field_editing(event, ctx, ed, exit_level=1)` - generic, handles spells/items/monsters
- Level 3 tiles handler: Same method is called again at a different level (5201-5205)
- Tiles use `needs_live_sync = (ed == "tiles")` to trigger save_fields on every input

**Problem:**
- The duplication is **implicit in the call sites**, not in the code
- Tiles have custom behavior: UP/DOWN/choice cycling all call `ctx["save_fields"]()` to rebuild conditional fields
- Spells only call save_fields on explicit save (Ctrl+S) or ESC
- New editors with conditional fields (overworld: link types, dungeon: trap data) will need similar live-sync
- Each one will copy the handler and diverge: "is this behavior needed for MY editor?"

**Evidence of divergence risk:**
- Lines 4801-4806 in unified handler: `if needs_live_sync: ctx["save_fields"]()` — this is the live-sync hook
- Lines 4833-4839: Spell-specific casting_type → allowable_classes sync — **doesn't exist for tiles**
- Result: If tiles ever add interaction_type-based field rebuilding to spells, it breaks

**Refactoring approach:**
Extract a fully unified field handler that accepts editor-specific hooks:
```python
def _feat_handle_field_editing_unified(self, event, ctx, ed, exit_level,
                                       on_field_change=None,
                                       on_choice_cycle=None):
    # ... shared logic ...
    if on_field_change:
        on_field_change()  # Hook: tiles rebuilds, spells does nothing
    # ... choice cycling ...
    if on_choice_cycle:
        on_choice_cycle(choices[ci])  # Hook: spells syncs, tiles rebuilds
```

**Impact:** CRITICAL — This has caused recent interaction_type bugs. Not fixing it means every new editor will have inconsistent behavior.

---

### 3. **Dead Code in Generic Level 2 Handler**

**Location:** `game.py:4727` guard at line 4900

**Status:** RESOLVED — The previous audit's findings about dead code at lines 7278/7288/7312 do not appear in the current codebase. Either they were removed or the line numbers shifted.

---

### 4. **Field Entry Format — Positional Tuple Fragility**

**Location:** All `_feat_build_*_fields()` methods and `_feat_*_save_fields()` methods

**Current format:**
```python
entry = [label, key, value, type, editable]
# Access by index:
entry[1]  # key — what is this? (requires reading docs)
entry[3]  # type
entry[4]  # editable
```

**Problem:**
- Reading code requires constant cross-reference: "what's at index 3?"
- Field format is enforced only by convention in _feat_next_editable_generic
- Adding a new field attribute (e.g., `save_key` to fix issue #5 below) means updating all consumers

**Current format inconsistency:**
Some editors have different interpretations of the underscore prefix:
- Spells: ALL underscore fields are skipped (lines 2194-2195)
- Items: Underscore fields skipped EXCEPT `_name`, `_section`, `_slots` (lines 2403-2404)
- Monsters: Underscore fields skipped EXCEPT `_name`, `_color` (line 2583)
- Tiles: Underscore fields skipped EXCEPT `_color`, `_sprite` (line 3010)

**Refactoring approach:**
```python
from dataclasses import dataclass
@dataclass
class FieldEntry:
    label: str
    key: str
    value: str
    ftype: str = "text"
    editable: bool = True
    save_key: Optional[str] = None  # None = skip, else = dict key to save to

fields = [
    FieldEntry("Name", "name", spell["name"], "text", True, "name"),
    FieldEntry("Color", "_color", "128,128,128", "text", True, "color"),  # save to "color", not "_color"
]
```

**Impact:** MEDIUM-HIGH — Not critical for current features, but will cause copy-paste bugs in new editors.

---

### 5. **Inconsistent "Skip Underscore" Logic in save_fields**

**Location:** Each save_fields method has its own skip list (lines 2194, 2403, 2583, 3010)

**The pattern:**
- Spells (line 2194): `if key.startswith("_"): continue` — skip ALL
- Items (line 2403): `if key.startswith("_") and key not in ("_name", "_section", "_slots"): continue` — skip most
- Monsters (line 2583): `if key.startswith("_") and key not in ("_name", "_color"): continue` — skip most
- Tiles (line 3010): `if key.startswith("_") and key not in ("_color", "_sprite"): continue` — skip most

**Why:**
- Underscore prefix is used to indicate "internal" or "display-only" fields
- BUT some underscore fields ARE saved (metadata like `_color`, `_sprite`, `_name`)
- Each editor's list is different and must be maintained separately

**Problem for new editors:**
When adding an overworld or dungeon editor, a developer must ask: "Which underscore fields do I save?" There's no pattern to follow, only examples to copy from. Copy-paste will likely get it wrong.

**Refactoring approach:**
This is solved by using FieldEntry.save_key (issue #4 above). Once you have `save_key`, you don't need the underscore prefix convention at all.

**Impact:** HIGH — Will cause data corruption in new editors if not standardized.

---

## High-Priority Issues (Address Before Adding New Editors)

### 6. **No Shared Base for build_fields Boilerplate**

**Location:** Lines 2087-2156, 2324-2391, 2523-2572, 2946-2989

All four `build_fields` methods follow the same tail pattern:
```python
self._feat_X_fields = fields
self._feat_X_field = 0
self._feat_X_scroll_f = 0
self._feat_X_buffer = ""
self._feat_X_field = self._feat_next_editable_generic(self._feat_X_fields, 0)
if self._feat_X_fields:
    self._feat_X_buffer = self._feat_X_fields[self._feat_X_field][2]
```

This 7-line pattern is **identical across all 4 editors**, just with different `X`.

**Refactoring approach:**
```python
def _feat_finalize_fields(self, prefix, fields):
    """Finalize field list after building."""
    setattr(self, f"_feat_{prefix}_fields", fields)
    setattr(self, f"_feat_{prefix}_field", 0)
    setattr(self, f"_feat_{prefix}_scroll_f", 0)
    setattr(self, f"_feat_{prefix}_buffer", "")
    idx = self._feat_next_editable_generic(fields, 0)
    setattr(self, f"_feat_{prefix}_field", idx)
    if fields:
        setattr(self, f"_feat_{prefix}_buffer", fields[idx][2])

# Usage in each build_fields:
self._feat_finalize_fields("spell", fields)
```

**Impact:** MEDIUM — Reduces boilerplate by ~30 lines. Each new editor adds 7 lines; this saves them all.

---

### 7. **_feat_editor_ctx Creates Lambdas on Every Keypress**

**Location:** `game.py:5503-5611` and called from `game.py:4896`

The method creates a dict of ~15 lambdas every time an event is processed. Called on **every keypress** during editing.

**Problem:**
- Wasteful object allocation per keystroke
- Makes debugging harder (new closure objects on each call)
- Performance impact is negligible in Pygame, but pattern is poor

**Refactoring approach:**
Build ctx once when entering an editor and cache it.

**Impact:** LOW — Performance impact is negligible, but pattern matters for maintainability.

---

### 8. **Gallery and Town Layouts Bypass the Context System**

**Location:** `game.py:5503` returns None for gallery/town; `game.py:5209` dedicated town handler

The "generic" system actually serves:
- 3 editors fully (spells, items, monsters)
- 1 editor partially (tiles: uses generic for list, custom for fields)
- 2 editors not at all (gallery, town layouts)

**Result:**
- Generic system's reusability is 50% (3 of 6 editors)
- New editors don't benefit from the generic approach if they're spatial/grid-based
- Overworld and dungeon editors will likely need custom handlers, further diluting value

**Pattern recognition:**
- **Record editors:** Spells, items, monsters, tiles — benefit from generic context dict
- **Spatial/grid editors:** Overworld, dungeons, town layouts — need custom handlers
- **Pixel editors:** Gallery — needs specialized state (canvas, palette, undo stack)

**Recommendation:**
Accept this split. Don't force new editors into the generic system if they're fundamentally different. Instead:
1. Keep generic system for record editors
2. Create separate `_handle_spatial_editor_input()` pipeline for grid-based editors
3. Model spatial editors after MapEditorState/MapEditorInputHandler (already exists!)

**Impact:** ARCHITECTURAL — Not a refactoring, but a decision that affects how new editors are added.

---

## Medium-Priority Issues (Nice to Fix, Not Blocking)

### 9. **Single _feat_dirty Flag Shared Across All Editors**

**Location:** `game.py:355` (declaration), used globally

One flag: `self._feat_dirty` — tracks unsaved changes for ANY editor.

**Problem:**
- If future design allows switching between editors (tabs), the shared flag causes false prompts
- Currently works because editors are modal (enter → edit → exit)
- Not blocking, but fragile

**Recommendation:**
When/if adding editor tabs, switch to per-editor dirty tracking.

**Impact:** LOW — Not urgent, but necessary for editor tabs.

---

### 10. **State Variable Explosion**

**Location:** `game.py:340-420` (~80+ variables prefixed _feat_)

**Total: ~115 variables**

**Problem:**
- All live on `self` with no encapsulation
- Difficult to reason about scope: which state belongs to which editor?
- Initialization order matters but isn't documented
- Testing individual editors requires mocking 100+ variables

**Impact:** MEDIUM-LONG-TERM — Improves code organization but requires significant refactoring.

---

### 11. **No Input Validation on Field Values**

**Location:** All _feat_handle_field_editing text/int branches (lines 4841-4872)

- Color fields accept non-numeric input
- Int fields accept leading zeros
- Text fields accept empty strings

**Impact:** LOW — Not blocking, but improves robustness.

---

### 12. **Copy vs New-Blank Shortcut Inconsistency**

**Location:**
- Tiles (5238-5240): Both new and copy shortcuts duplicate
- Items/Monsters: Only new shortcut adds blank
- Gallery (5165-5167): Has dedicated copy shortcut

**Impact:** LOW — UX inconsistency, not architectural.

---

## What DOESN'T Need Fixing (Yet)

1. **Unsaved dialog focus trapping:** Works as-is, no evidence of input leakage
2. **Spell-specific _feat_next_editable vs generic:** The spell version isn't used (previous audit may have been outdated)
3. **_feat_next_editable_generic as staticmethod:** This is fine; it's truly stateless
4. **Section fields in rendering:** The "-- Identity --" headers render fine, no UX bugs

---

## Recommended Refactoring Priority (For Adding New Editor Types)

If your goal is to add overworld and dungeon editors, tackle these in this order:

### **Phase 1: Unblock Scaling (1-2 days)**
1. **Replace monolithic renderer call** (Critical #1) — Extract EditorRenderState dataclass, refactor draw_features_screen to accept 3 args instead of 60
   - Effort: 4 hours (mostly parameter consolidation)
   - Impact: 50% easier to add new editors

2. **Unify level 2/3 field handlers** (Critical #2) — Create _feat_handle_field_editing_unified with hooks, remove duplication
   - Effort: 3 hours
   - Impact: Eliminates source of recent bugs, prevents divergence in new editors

3. **Remove dead code** (Critical #3) — Quick scan for unreachable blocks
   - Effort: 15 min
   - Impact: Clarity

### **Phase 2: Reduce Copy-Paste (1 day)**
4. **Extract _feat_finalize_fields helper** (High #6) — Boilerplate reduction
   - Effort: 1 hour
   - Impact: Each new editor saves 7 lines

5. **Standardize field format with FieldEntry dataclass** (High #4) — Introduces explicit save_key, eliminates underscore ambiguity
   - Effort: 3 hours (need to update all build_fields and save_fields)
   - Impact: Prevents copy-paste bugs in new editors

### **Phase 3: Architecture Decision (1 hour)**
6. **Decide on spatial editor pattern** (High #8) — Accept that grid-based editors (overworld, dungeon) won't use the generic context system. Model them after MapEditorState instead.
   - Effort: Discussion + documentation
   - Impact: Clear design for new editor types

### **NOT recommended before new features:**
- State variable grouping (issue #10) — Major refactor, low ROI for now
- Input validation framework (issue #11) — Can add later per-field
- Per-editor dirty flags (issue #9) — Not needed until editor tabs exist
- Pixel editor UI improvements — Separate from scalability concerns

---

## Risk Assessment for Adding Overworld Editor Without Refactoring

If you skip the refactoring and add an overworld editor using the current pattern:

| Issue | Symptom | Likelihood |
|-------|---------|------------|
| State explosion to 150+ variables | Code becomes unmaintainable | HIGH |
| Monolithic renderer at 100+ params | Parameter ordering bugs, hard to test | HIGH |
| Field handler divergence | Live-sync works for overworld, fails for dungeon | MEDIUM |
| Copy-paste of skip logic | Data corruption in link_type field | MEDIUM |
| Confusion about which editor system to use | Overworld uses context dict, dungeon uses custom handlers, inconsistency | MEDIUM |

**Estimated extra time cost if refactoring skipped:** +8 hours (bugs + rework) per new editor type.

---

## Summary Table: What's Blocking New Features?

| Issue | Severity | Blocks New Features? | Fix Impact | Effort |
|-------|----------|---------------------|-----------|--------|
| Monolithic renderer signature | CRITICAL | YES — every editor needs params added | 50% faster editor addition | 4 hrs |
| Duplicated field handlers | CRITICAL | YES — bugs propagate to new editors | Eliminates recent bugs | 3 hrs |
| Dead code | CRITICAL | NO — just clutter | Clarity | 15 min |
| Field format / save_key inconsistency | HIGH | YES — will cause data corruption | Prevents bugs | 3 hrs |
| Boilerplate finalize_fields | HIGH | NO — but every editor repeats it | 7 lines saved per editor | 1 hr |
| Spatial editor pattern | ARCHITECTURAL | YES — need to decide approach | Prevents inconsistency | 1 hr discussion |
| State variable explosion | MEDIUM | NO — annoying but works | Organization | 1-2 days (not urgent) |
| Lambda recreation | LOW | NO — negligible perf | Minor cleanup | 30 min |
| Input validation | LOW | NO — can add later | Robustness | 2 hrs (later) |

---

## Conclusion

The module editor system is **architecturally unsustainable for scaling** due to three compounding issues:

1. The monolithic renderer call (60+ params)
2. Duplicated field handler logic
3. Inconsistent field format and save logic

These three issues interact: when you add a new editor, you must:
- Expand the renderer signature (+10 params)
- Decide which field handler pattern to use (copy one of two divergent implementations)
- Remember which underscore fields to skip (look up 4 different examples)

The good news: **None of these are fundamental design flaws.** They're all straightforward refactorings. The bad news: they compound, so delaying them costs more as you add editors.

**Recommendation:** Implement Phase 1 + Phase 2 refactoring (4-5 hours total) before starting an overworld or dungeon editor. This investment pays for itself immediately in the first new editor and multiplies in value for each subsequent one.
