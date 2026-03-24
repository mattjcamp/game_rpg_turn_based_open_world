# Module Editor Refactoring Checklist

Before adding new editor types (overworld maps, dungeons), complete these refactorings in order.

## Phase 1: Unblock Scaling (1-2 days)

### 1.1 Replace Monolithic Renderer Call (4 hours)

**Goal:** Replace 60+ individual parameters with a single state dataclass

**Changes needed:**

1. **In `src/game.py` (~line 340-420):**
   - Create `EditorRenderState` dataclass with: active_editor, level, categories, cat_cursor, editor_data dict
   - Create `_build_render_state()` method that returns EditorRenderState instead of dict with 60 keys
   - Update renderer call (`~line 5974`) to: `self.renderer.draw_features_screen(**self._feat_render_state())`

2. **In `src/renderer.py` (~line 6921):**
   - Change `draw_features_screen()` signature from 60+ params to accept `EditorRenderState` + common state
   - Inside method, unpack `editor_state.editor_data` for active editor's state
   - Update all rendering logic to use unpacked data

**Testing:** All 6 editors should render identically after this change

**Line references:**
- game.py: _feat_render_state (5613-5719), renderer call (5974-5975)
- renderer.py: draw_features_screen (6921-6981)

---

### 1.2 Unify Field Handler Logic with Hooks (3 hours)

**Goal:** Eliminate implicit duplication of _feat_handle_field_editing at different levels

**Changes needed:**

1. **In `src/game.py`:**
   - Rename current `_feat_handle_field_editing()` to `_feat_handle_field_editing_unified()`
   - Add parameters: `on_field_change=None, on_choice_cycle=None` (callable hooks)
   - Replace `needs_live_sync = (ed == "tiles")` with conditional hook calls
   - Replace spell-specific casting_type sync (lines 4833-4839) with hook parameter
   - Call site at level 2 (line 4901): `self._feat_handle_field_editing_unified(event, ctx, ed, exit_level=1, on_field_change=tiles_rebuild if ed=='tiles' else None)`
   - Call site at level 3 (line 5204): Same, but with exit_level=2

2. **Define editor-specific hooks:**
   - `_on_tile_field_change()`: calls save_fields() to rebuild conditional fields
   - `_on_spell_choice_cycle(value)`: syncs casting_type → allowable_classes

**Testing:** Tiles with conditional fields should rebuild seamlessly; spells should maintain class sync

**Line references:**
- game.py: _feat_handle_field_editing (4727-4872), level 2 call (4901), level 3 call (5204)

---

### 1.3 Code Cleanup (15 minutes)

- [ ] Scan for unreachable `if ed == "tiles":` blocks inside level 2 handler (issue #3)
- [ ] Remove if found

---

## Phase 2: Reduce Copy-Paste (1 day)

### 2.1 Extract _feat_finalize_fields Helper (1 hour)

**Goal:** Remove 7-line boilerplate from all build_fields methods

**Changes needed:**

1. **In `src/game.py`, add method (~line 2080, before first build_fields):**

```python
def _feat_finalize_fields(self, prefix, fields):
    """Finalize and initialize field list after building.
    
    Sets: fields, field cursor, field scroll, buffer, and loads first editable.
    """
    setattr(self, f"_feat_{prefix}_fields", fields)
    setattr(self, f"_feat_{prefix}_field", 0)
    setattr(self, f"_feat_{prefix}_scroll_f", 0)
    setattr(self, f"_feat_{prefix}_buffer", "")
    idx = self._feat_next_editable_generic(fields, 0)
    setattr(self, f"_feat_{prefix}_field", idx)
    if fields:
        setattr(self, f"_feat_{prefix}_buffer", fields[idx][2])
```

2. **Replace in all 4 build_fields methods:**
   - `_feat_build_spell_fields()` (~line 2147-2156): Replace lines 2147-2156 with `self._feat_finalize_fields("spell", fields)`
   - `_feat_build_item_fields()` (~line 2383-2391): Replace lines 2383-2391 with `self._feat_finalize_fields("item", fields)`
   - `_feat_build_mon_fields()` (~line 2567-2572): Replace lines 2567-2572 with `self._feat_finalize_fields("mon", fields)`
   - `_feat_build_tile_fields()` (~line 2981-2989): Replace lines 2981-2989 with `self._feat_finalize_fields("tile", fields)`

**Testing:** build_fields for all 4 editors should work identically

**Line references:**
- game.py: spell finalize (2147-2156), item (2383-2391), mon (2567-2572), tile (2981-2989)

---

### 2.2 Standardize Field Format with FieldEntry Dataclass (3 hours)

**Goal:** Eliminate positional tuple access and standardize save_key logic

**Changes needed:**

1. **In `src/game.py`, add class definition (~line 1, after imports):**

```python
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class FieldEntry:
    """Represents a single editable field in the features editor."""
    label: str
    key: str
    value: str
    ftype: str = "text"           # "text", "int", "choice", "sprite", "section"
    editable: bool = True
    save_key: Optional[str] = None # None = skip, else = dict key to save to
    validator: Optional[Callable[[str], bool]] = None  # Optional validation
```

2. **Update all `build_fields()` methods to use FieldEntry:**
   - Replace lists `["label", "key", "value", "type", True]` with `FieldEntry("label", "key", "value", "type", True, "save_key")`
   - For underscore fields, set save_key to the actual key (e.g., `_color` → `save_key="color"`)
   - Example: `FieldEntry("Color", "_color", "128,128,128", "text", True, "color")`

3. **Update `_feat_next_editable_generic()` to work with FieldEntry:**
   - Change `entry[4]` to `entry.editable`
   - Change `entry[3]` to `entry.ftype`

4. **Update all `save_fields()` methods to use save_key:**
   - Replace all the different `if key.startswith("_") and key not in (...)` patterns with:
   ```python
   for entry in self._feat_X_fields:
       if entry.save_key is None:
           continue
       actual_key = entry.save_key
       val = entry.value
       # ... type-specific conversion ...
       obj[actual_key] = converted_value
   ```

5. **Update field access in `_feat_handle_field_editing_unified()`:**
   - Change `entry[1]` (key) to `entry.key`
   - Change `entry[2]` (value) to `entry.value`
   - Change `entry[3]` (type) to `entry.ftype`
   - Change `entry[4]` (editable) to `entry.editable`

**Testing:** All 4 editors should load/save fields identically to before

**Line references:**
- game.py: All _feat_build_*_fields methods (2087, 2324, 2523, 2946)
- game.py: All _feat_save_*_fields methods (2181, 2393, 2573, 2999)
- game.py: _feat_next_editable_generic (~line 3804)
- game.py: _feat_handle_field_editing_unified (4727 after Phase 1.2)

---

## Phase 3: Architecture Decision (1 hour)

### 3.1 Decide on Spatial Editor Pattern (1 hour discussion)

**Goal:** Define clear design pattern for grid/map-based editors (overworld, dungeons)

**Decision points:**

1. **Where do spatial editors live?**
   - Option A: Extend _feat_ system with new case in _feat_editor_ctx()
   - Option B: Create separate `_handle_spatial_editor_input()` pipeline (recommended)
   - Recommendation: **Option B** — spatial editors are fundamentally different from record editors

2. **What should spatial editors model after?**
   - **Recommended:** Copy MapEditorState/MapEditorInputHandler pattern from src/map_editor.py
   - This is already proven design in the codebase
   - Avoids forcing grid-based editors into record-editor context dict

3. **How does rendering work?**
   - Record editors: Use updated EditorRenderState.editor_data dict
   - Spatial editors: Pass their own state dataclass to draw_* method
   - Keep separate code paths; don't force everything through one renderer

4. **Documentation to create:**
   - `EDITOR_TYPES.md`: Explains which system each editor uses
   - `SPATIAL_EDITOR_TEMPLATE.py`: Template for new overworld/dungeon editors

**Outcome:** Write design doc clarifying:
- Record editors use _feat_editor_ctx + unified field handlers
- Spatial editors use MapEditorState-like pattern
- Gallery stays as-is (pixel editor specialist)
- Each editor type has clear responsibilities

---

## Post-Refactoring Validation

After completing all phases, verify:

- [ ] All 6 existing editors still work (spells, items, monsters, tiles, gallery, town)
- [ ] No regressions in field editing behavior
- [ ] Unsaved dialog still works correctly
- [ ] Tile conditional fields (interaction_type) rebuild correctly
- [ ] Spell field sync (casting_type → allowable_classes) works
- [ ] Renderer no longer has 60+ parameters
- [ ] Field format is FieldEntry throughout
- [ ] Adding a new record editor requires <2 hours of work

---

## Effort Summary

| Phase | Task | Effort | Total |
|-------|------|--------|-------|
| 1 | Monolithic renderer | 4 hrs | 4 hrs |
| 1 | Unified field handler | 3 hrs | 7 hrs |
| 1 | Code cleanup | 15 min | ~7.25 hrs |
| 2 | Finalize fields helper | 1 hr | 8.25 hrs |
| 2 | Field format dataclass | 3 hrs | 11.25 hrs |
| 3 | Architecture decision | 1 hr | 12.25 hrs |
| | Testing/debugging buffer | 2-3 hrs | **~14-15 hrs total** |

**Realistic timeline:** 3-4 days of focused development

**Return on investment:** 
- Overworld editor will take ~20 hours without refactoring
- After refactoring, ~12 hours (8 hour savings)
- Dungeon editor after overworld: ~10 hours (10 hour savings)
- Total ROI: 18+ hours saved across two new editors = major win

