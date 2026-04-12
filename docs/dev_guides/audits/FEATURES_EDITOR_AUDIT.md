# Features Editor System — Technical Debt Audit

**Date:** March 22, 2026
**Scope:** `src/game.py` — Game Features editor system (lines ~340–8500)

---

## Executive Summary

The Features editor is a multi-level, multi-editor system handling 6 editor types (spells, items, monsters, tiles, gallery, town layouts). It uses a context-dict pattern (`_feat_editor_ctx()`) to share generic handler logic across 4 of the 6 editors, with gallery and town layouts as special cases.

The system works but has accumulated significant technical debt. The biggest risks for future adaptation (overworld maps, dungeons) are: **code duplication between level 2 and level 3 handlers**, a **monolithic renderer call with 60+ keyword arguments**, and **inconsistent patterns across editor types**. Below are the specific findings organized by severity.

---

## CRITICAL — Fix Before Adapting

### 1. Duplicated Field Editor Logic (level 2 vs level 3)

The generic field editor (level 2, lines 7221–7350) and the tile field editor (level 3, lines 7650–7753) are **near-identical copies** with subtle differences:

- Level 2 handles spells/items/monsters; level 3 handles tiles
- Level 3 calls `save_fields()` on UP/DOWN and after choice cycling; level 2 only does this for tiles (dead code — see below)
- Level 3 re-reads `fields`/`n`/`field_idx` after save; level 2 does not
- Level 2 has the spell casting_type → allowable_classes sync; level 3 does not

**Risk:** Every future editor that needs conditional fields or live-sync will need its own copy of this handler, and behavioral divergence will multiply. The recent interaction_type bugs were caused directly by this duplication — the tile handler was missing logic that the generic handler had.

**Recommendation:** Unify into a single `_feat_handle_field_editing(ctx, ed)` method called from both level 2 and level 3 paths. Pass `ed` to control editor-specific hooks (spell class sync, tile live-sync). The level 2 guard `ed not in ("tiles", "gallery")` and the level 3 guard `ed == "tiles"` can both call this shared method.

### 2. Dead Code in Generic Level 2 Handler

Three `if ed == "tiles":` blocks inside the generic level 2 handler (lines 7278, 7288, 7312) are **unreachable dead code**. The outer condition at line 7221 explicitly excludes tiles: `ed not in ("tiles", "gallery")`.

These are remnants from when tiles used level 2 for field editing, before the level 3 tile handler was introduced. They create confusion about where tile field editing actually happens.

**Recommendation:** Remove all three dead `if ed == "tiles":` blocks from the level 2 handler.

### 3. Monolithic Renderer Call — 60+ Keyword Args

The `draw_features_screen()` call (lines 8405–8500) passes **60+ keyword arguments**, one for every piece of editor state across all 6 editors. The matching function signature in `renderer.py` (lines 7292–7345) is equally enormous. Every new editor type requires adding more parameters to both sides.

**Risk:** This is the single biggest scalability bottleneck. Adding an overworld or dungeon editor means adding another 10–15 params to an already unwieldy signature. It's also error-prone — parameter ordering/naming mismatches are hard to spot.

**Recommendation:** Replace with a state-object pattern. Create a dataclass or dict per editor type and pass only the active editor's state:

```python
# Instead of 60 kwargs:
self.renderer.draw_features_screen(
    editor_state=self._get_active_editor_state(),
    level=self._feat_level,
    categories=self._feat_categories,
    cat_cursor=self._feat_cursor,
)
```

---

## HIGH — Address Before Adding New Editors

### 4. Inconsistent "Skip Underscore" Logic in save_fields

Each `save_fields` implementation has its own rules for which `_` prefixed keys to process:

| Editor | Skips `_*` except... |
|--------|---------------------|
| Spells | (skips all `_*`) |
| Items | `_name`, `_section`, `_slots` |
| Monsters | `_name`, `_color` |
| Tiles | `_color`, `_sprite` |

This per-editor whitelist approach means every new editor needs its own exception list. A future developer copying the pattern will likely get it wrong.

**Recommendation:** Standardize the field entry format. Instead of overloading `_` prefix to mean "internal/skip" with exceptions, add an explicit `save_key` field to the entry tuple:

```python
# Current: ["Color", "_color", "128,128,128", "text", True]
# Proposed: ["Color", "_color", "128,128,128", "text", True, "color"]
#           entry[5] = actual dict key to save to (None = skip)
```

### 5. No Shared Base for build_fields

The four `build_fields` methods (`_feat_build_spell_fields`, `_feat_build_item_fields`, `_feat_build_mon_fields`, `_feat_build_tile_fields`) all follow the same pattern but are fully independent: build a list, assign to `self._feat_X_fields`, reset cursor/scroll/buffer, advance to first editable. The boilerplate at the end of each is identical.

**Recommendation:** Extract the common tail into a helper:

```python
def _feat_finalize_fields(self, prefix, fields):
    setattr(self, f"_feat_{prefix}_fields", fields)
    setattr(self, f"_feat_{prefix}_field", 0)
    setattr(self, f"_feat_{prefix}_scroll_f", 0)
    setattr(self, f"_feat_{prefix}_buffer", "")
    idx = self._feat_next_editable_generic(fields, 0)
    setattr(self, f"_feat_{prefix}_field", idx)
    if fields:
        setattr(self, f"_feat_{prefix}_buffer", fields[idx][2])
```

### 6. `_feat_editor_ctx()` Creates Lambdas on Every Call

`_feat_editor_ctx()` (lines 8042–8150) creates a new dict of ~15 lambdas every time it's called. It's called on **every keypress event** during editing. While the performance cost is negligible in a Pygame game, the pattern is wasteful and makes debugging harder (new closure objects on every call).

**Recommendation:** Build the context once when entering an editor level and cache it as `self._feat_ctx`. Invalidate on editor change.

### 7. Gallery and Town Layouts Bypass the Context System Entirely

Gallery returns `None` from `_feat_editor_ctx()` and has fully custom handlers at every level (1–5). Town layouts bypass the context system entirely via a dedicated `_feat_handle_townlayout_input()` method at line 7209.

This means the "generic" system actually only serves 4 of 6 editors (67%), and only 3 of those (spells/items/monsters) use it for field editing. Tiles use it for list browsing (level 1–2) but have their own field editor (level 3).

**Risk:** A new editor (overworld map, dungeon) will likely need its own custom handler chain, further diluting the value of the "generic" approach.

**Recommendation:** Accept that gallery and town layouts are fundamentally different (they have grid painters, pixel editors, etc.) and focus the generic system on data-record editors (spells, items, monsters, tiles). For new editors, decide upfront whether they're "record editors" (use the generic system) or "spatial editors" (custom handlers).

---

## MEDIUM — Quality and Maintainability

### 8. Single `_feat_dirty` Flag Shared Across All Editors

There's one `self._feat_dirty` flag (line 348) shared by all editors. It's set to True on any field change and checked on ESC to trigger the unsaved dialog.

**Risk:** If future code ever allows switching between editors without fully exiting (e.g., tabs), the shared dirty flag would cause false save prompts or missed saves.

**Recommendation:** This is fine for now, but when adding editor tabs or rapid switching, consider per-editor dirty tracking.

### 9. State Variable Explosion

The features editor declares ~80 instance variables on `self` (lines 340–420), all prefixed with `_feat_`. Each new editor type adds 8–15 more variables. There's no encapsulation — all editors' state lives on the Game object.

**Current state variable counts:**
- Core/shared: ~10 (`_feat_level`, `_feat_cursor`, `_feat_dirty`, etc.)
- Spells: ~15 (`_feat_spell_list`, `_feat_spell_cursor`, `_feat_spell_fields`, etc.)
- Items: ~8
- Monsters: ~8
- Tiles: ~12
- Gallery: ~15
- Town layouts: ~25
- Pixel editor: ~10

**Recommendation:** Group into per-editor state objects:

```python
self._feat_spell = SpellEditorState()
self._feat_tile = TileEditorState()
```

This would also simplify the context dict — each state object could expose the standard interface directly.

### 10. Field Entry Format Is a Positional Tuple/List

Fields are `[label, key, value, type, editable]` — a 5-element list accessed by index. This is fragile and hard to read:

```python
entry[3]  # What is index 3? (field type)
entry[4]  # What is index 4? (editable flag)
```

**Recommendation:** Use a namedtuple or small dataclass:

```python
FieldEntry = namedtuple("FieldEntry", "label key value ftype editable")
```

### 11. `_feat_next_editable_generic` Is a Staticmethod but Relies on List Convention

This function (line 4499) checks `entry[4]` for editability and `entry[3] != "section"`. It's a staticmethod, which is good, but it bakes in knowledge of the field format. If the format changes, this breaks silently.

**Recommendation:** Couple with the field entry format reform (issue 10 above).

### 12. Spell Editor Has Its Own `_feat_next_editable` in Addition to the Generic One

There's both `_feat_next_editable` (spell-specific, searches `_feat_spell_fields`) and `_feat_next_editable_generic` (takes any fields list). The spell-specific version is used in `_feat_build_spell_fields` while the generic is used everywhere else.

**Recommendation:** Remove the spell-specific version and use the generic one consistently.

---

## LOW — Nice to Have

### 13. No Input Validation on Field Values

Text and int fields accept any input with no validation. For example:
- Color fields accept non-numeric input (parsing silently fails in save)
- Int fields accept leading zeros
- Name fields accept empty strings

Not a bug currently, but could cause data corruption if the user enters unexpected values.

### 14. Unsaved Dialog Is Modal but Not Focus-Trapped

The unsaved dialog sets `_unsaved_dialog_active = True` and intercepts events, but the handler is checked early in `_handle_features_input`. If any code path bypasses this check, input could leak through.

### 15. Copy/Duplicate Shortcut Inconsistency

- Tiles: `_is_new_shortcut(event) or _is_copy_shortcut(event)` both trigger duplicate
- Items/Monsters: `_is_new_shortcut(event)` triggers add (new blank), no copy shortcut
- Gallery: Has its own `_feat_gallery_duplicate()` on copy shortcut

The copy vs new-blank distinction is inconsistent across editor types.

---

## Recommended Refactoring Priority

If you plan to adapt this pattern for overworld maps and dungeons, tackle these in order:

1. **Unify level 2 and level 3 field handlers** (Critical #1) — eliminates the source of the most recent bugs and prevents future handler divergence
2. **Remove dead code** (Critical #2) — quick win, reduces confusion
3. **Replace monolithic renderer call** (Critical #3) — the biggest barrier to adding new editors
4. **Extract `_feat_finalize_fields` helper** (High #5) — reduces boilerplate when adding new editor types
5. **Standardize save_fields skip logic** (High #4) — prevents copy-paste bugs in new editors

Items 1 and 2 are quick, targeted changes. Item 3 is the most impactful for long-term maintainability but requires coordinated changes in both `game.py` and `renderer.py`.
