# UI Controls Audit

**Realm of Shadow — An Ultima III Inspired RPG**

Baseline audit of every screen, function, and key binding in the game UI. This document serves as the starting-point reference for unifying controls into a single consistent standard and as the template for all future UI features.

**Screens documented:** 24 | **Controls catalogued:** 200+ | **Date:** March 21, 2026

---

## 1. Title / Main Menu

**Source:** `game.py` — `_handle_title_input()` ~line 5972
**Renderer:** `renderer.draw_title_screen()`

Menu options (dynamic): RETURN TO GAME (conditional), START NEW GAME, FORM PARTY, SAVE GAME, LOAD GAME, EDIT GAME FEATURES, SETTINGS, QUIT GAME.

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Select option | Enter / Space |

---

## 2. Character Creation

**Source:** `game.py` — `_handle_char_create_input()` ~line 1434
**Renderer:** `renderer.draw_char_create_screen()`

Seven-step wizard: Name Entry → Race → Gender → Class → Tile/Sprite → Stat Allocation → Confirmation.

### Step 1 — Name Entry

| Function | Key(s) |
|----------|--------|
| Type character | Any printable key |
| Delete character | Backspace |
| Confirm name | Enter |
| Go back | Escape |

### Step 2 — Race Selection

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Confirm selection | Enter / Space |
| Go back | Escape |

### Step 3 — Gender Selection

| Function | Key(s) |
|----------|--------|
| Toggle selection | Up / Down Arrow |
| Confirm selection | Enter / Space |
| Go back | Escape |

### Step 4 — Class Selection

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Confirm selection | Enter / Space |
| Go back | Escape |

### Step 5 — Tile/Sprite Selection

| Function | Key(s) |
|----------|--------|
| Move left | Left Arrow |
| Move right | Right Arrow |
| Move up (jump 6) | Up Arrow |
| Move down (jump 6) | Down Arrow |
| Confirm selection | Enter / Space |
| Go back | Escape |

### Step 6 — Stat Allocation

| Function | Key(s) |
|----------|--------|
| Previous stat | Up Arrow |
| Next stat | Down Arrow |
| Decrease stat | Left Arrow |
| Increase stat | Right Arrow |
| Confirm | Enter / Space |
| Go back | Escape |

### Step 7 — Confirmation

| Function | Key(s) |
|----------|--------|
| Toggle CREATE / CANCEL | Up / Down Arrow |
| Execute selection | Enter / Space |
| Go back | Escape |

---

## 3. Form Party

**Source:** `game.py` — `_handle_form_party_input()` ~line 1629
**Renderer:** `renderer.draw_form_party_screen()`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Toggle character active | Space |
| Confirm party / start game | Enter |
| Delete character | D |
| Create new character | C |
| Go back | Escape |

### Delete Confirmation Sub-dialog

| Function | Key(s) |
|----------|--------|
| Confirm deletion | Y |
| Cancel | N / Escape |

---

## 4. Overworld

**Source:** `game.py` / `src/states/overworld.py`
**Renderer:** `renderer.draw_overworld()`
**Hint:** `Arrow keys: Move | Bump NPC: Talk | ESC: Leave town`

### Global Shortcuts (available in all game-world screens)

| Function | Key(s) |
|----------|--------|
| Character 1 sheet | 1 |
| Character 2 sheet | 2 |
| Character 3 sheet | 3 |
| Character 4 sheet | 4 |
| Quest log | Q |
| Main menu | M |

### Movement & Interaction

| Function | Key(s) |
|----------|--------|
| Move | Arrow Keys / WASD |
| Examine tile | E |
| Interact / confirm | Enter |
| Cancel / close | Escape |

---

## 5. Town

**Source:** `src/states/town.py`
**Renderer:** `renderer.draw_town()`
**Hint:** `Arrow keys: Move | Bump NPC: Talk | ESC: Leave town`

| Function | Key(s) |
|----------|--------|
| Move | Arrow Keys |
| Talk to NPC | Move into NPC |
| Interact with object | Enter |
| Open inventory | I |
| Leave town | Escape |

---

## 6. Dungeon

**Source:** `src/states/dungeon.py`
**Renderer:** `renderer.draw_dungeon()`
**Hint:** `Arrow keys: Move | ESC on stairs: Leave dungeon`

| Function | Key(s) |
|----------|--------|
| Move | Arrow Keys |
| Fight monster | Move into monster |
| Use stairs / exit | Escape (at stairs) |
| Open inventory | I |

---

## 7. Combat

**Source:** `src/states/combat.py`
**Renderer:** `renderer.draw_combat()`

| Function | Key(s) |
|----------|--------|
| Navigate menu | Up / Down or W / S |
| Navigate targets | Left / Right or A / D |
| Confirm action | Enter |
| Open inventory | I |
| Character status | O |
| Toggle action tabs | Tab / B |
| Open equipment | E |
| Cancel / go back | Escape / Backspace |

---

## 8. Inventory / Equipment

**Source:** Called from overworld / town / combat
**Renderer:** `renderer.draw_character_detail()`

| Function | Key(s) |
|----------|--------|
| Navigate items | Up / Down Arrow |
| Switch character | Left / Right Arrow |
| View / examine item | Enter |
| Drop / remove item | L |
| Toggle tabs | Tab |
| Close inventory | P / Escape |

---

## 9. Shopping / Merchant

**Source:** `src/states/town.py`
**Renderer:** `renderer.draw_shop()`

| Function | Key(s) |
|----------|--------|
| Navigate items | Up / Down Arrow |
| Select / confirm | Enter |
| Toggle buy / sell | Tab / B |
| Leave shop | Escape |

---

## 10. NPC Dialog

**Source:** Dialog system in `src/states/`

| Function | Key(s) |
|----------|--------|
| Advance dialog | Space / Enter |
| Select option | Up / Down then Enter |
| Exit dialog | Escape |

---

## 11. Quest Log

**Source:** `game.py` ~line 6789

| Function | Key(s) |
|----------|--------|
| Scroll up | Up Arrow |
| Scroll down | Down Arrow |
| Close | Q / Escape |

---

## 12. Game Over

**Source:** `game.py` — `_handle_game_over_input()` ~line 5945
**Renderer:** `renderer.draw_game_over()`

Options: LOAD GAME, NEW GAME.

| Function | Key(s) |
|----------|--------|
| Navigate | Up / Down Arrow |
| Select | Enter / Space |

---

## 13. Settings

**Source:** `game.py` — `_handle_settings_input()` ~line 6639
**Renderer:** `renderer.draw_settings()`
**Hint:** `[UP/DN] SELECT  [ENTER/L/R] CHANGE  [M/ESC] CLOSE`

Options: MUSIC (toggle), SOUNDTRACK (cycle), SMITE/DEBUG (toggle), START WITH EQUIPMENT (toggle), START LEVEL (cycle 1–10).

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Toggle option | Enter / Space |
| Cycle left | Left Arrow |
| Cycle right | Right Arrow |
| Close | M / Escape |

---

## 14. Save / Load

**Source:** `game.py` — `_handle_save_load_input()` ~line 6681
**Renderer:** `renderer.draw_save_load_screen()`
**Hint (save):** `[UP/DN] SELECT  [ENTER] SAVE  [ESC] BACK`
**Hint (load):** `[UP/DN] SELECT  [ENTER] LOAD  [D] DELETE  [ESC] BACK`

| Function | Key(s) |
|----------|--------|
| Navigate slots | Up / Down Arrow |
| Save / Load | Enter / Space |
| Delete slot (load only) | D |
| Go back | Escape |

### Delete Confirmation

| Function | Key(s) |
|----------|--------|
| Confirm | Y |
| Cancel | N / Escape |

---

## 15. Edit Game Features — Main Menu

**Source:** `game.py` — `_handle_features_input()` ~line 5985
**Renderer:** `renderer.draw_features_screen()`
**Hint:** `[UP/DN] Browse  [ENTER] Open  [ESC] Back`

Categories: Modules, Spells, Items, Monsters, Tile Types, Tile Gallery, Town Layouts.

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Open category | Enter / Space |
| Go back | Escape |

---

## 16. Spells Editor

**Source:** `game.py` — Features input handler, levels 1–2

### Level 1 — Spell List

**Hint:** `[UP/DN] Browse  [ENTER] Open  [A] Add  [D] Remove  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Open spell | Enter / Right Arrow |
| Add new spell | A |
| Delete spell | D / Delete |
| Go back | Escape |

### Level 2 — Spell Field Editor

**Hint:** `[UP/DN] Field  [TYPE] Edit  [LT/RT] Adjust  [CTRL+S] Create  [ESC] Cancel`

| Function | Key(s) |
|----------|--------|
| Previous field | Up Arrow |
| Next field | Down Arrow |
| Cycle choice left | Left Arrow |
| Cycle choice right | Right Arrow |
| Type text | Printable characters |
| Delete character | Backspace |
| Save | Ctrl+S |
| Cancel | Escape |

---

## 17. Items Editor

Same pattern as Spells Editor (Section 16). Level 1 list browser + Level 2 field editor with identical controls.

### Level 1 — Item List

**Hint:** `[UP/DN] Browse  [ENTER] Open  [A] Add  [D] Remove  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Open item | Enter / Right Arrow |
| Add new item | A |
| Delete item | D / Delete |
| Go back | Escape |

### Level 2 — Item Field Editor

Identical to Spells Field Editor (see Section 16, Level 2).

---

## 18. Monsters Editor

Same pattern as Spells/Items Editor. Level 1 list browser + Level 2 field editor with identical controls.

### Level 1 — Monster List

**Hint:** `[UP/DN] Browse  [ENTER] Open  [A] Add  [D] Remove  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Open monster | Enter / Right Arrow |
| Add new monster | A |
| Delete monster | D / Delete |
| Go back | Escape |

### Level 2 — Monster Field Editor

Identical to Spells Field Editor (see Section 16, Level 2).

---

## 19. Tile Types Editor

Three-level editor: Folder list → Tile list → Tile field editor.

### Level 1 — Folder List

Folders: Overworld, Town, Dungeon, Battle Screen, Examine Screen.

**Hint:** `[UP/DN] Browse  [ENTER] Open  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Enter folder | Enter / Right Arrow |
| Go back | Escape |

### Level 2 — Tile List

**Hint:** `[UP/DN] Browse  [ENTER] Open  [A] Add  [D] Remove  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Open tile | Enter / Right Arrow |
| Add tile | A |
| Delete tile | D / Delete |
| Go back | Escape |

### Level 3 — Tile Field Editor

Identical to Spells Field Editor (see Section 16, Level 2).

---

## 20. Tile Gallery

Four-level system: Category folders → Sprite list → Tag editor → Pixel editor.

### Level 1 — Category Folders

Categories: overworld, town, dungeon, people, monsters, objects, unique_tiles, items, spells, unassigned.

**Hint:** `[UP/DN] Browse  [ENTER] Open  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Enter category | Enter / Right Arrow |
| Go back | Escape |

### Level 2 — Sprite List

**Hint:** `[Up/Dn] Browse  [Enter] Tags  [E] Edit Pixels  [Ctrl+D] Duplicate  [N] Rename  [X] Delete  [Esc] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Open tag editor | Enter / Right Arrow |
| Open pixel editor | E |
| Duplicate sprite | Ctrl+D |
| Rename sprite | N |
| Delete sprite | X / Delete |
| Go back | Escape |

### Naming Mode (rename / duplicate)

| Function | Key(s) |
|----------|--------|
| Type character | Printable characters |
| Delete character | Backspace |
| Confirm name | Enter |
| Cancel | Escape |

### Level 3 — Tag Editor

**Hint:** `[UP/DN] Browse  [ENTER/SPACE/L/R] Toggle  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Previous tag | Up Arrow |
| Next tag | Down Arrow |
| Toggle tag | Enter / Space / Left / Right |
| Save and back | Escape |

---

## 21. Pixel Editor

Accessible from Tile Gallery Level 2. Full sprite editing with canvas, palette, color replace, and undo.

**Hint:** `[Arrows] Move  [Space] Paint  [Tab] Palette  [Q/E] Color  [P] Pick  [R] Replace  [Ctrl+Z] Undo  [Esc] Save`

### Canvas Mode

| Function | Key(s) |
|----------|--------|
| Move cursor | Arrow Keys |
| Paint pixel | Enter / Space |
| Previous color | Q |
| Next color | E |
| Eyedropper (pick) | P |
| Color replace mode | R |
| Undo | U / Ctrl+Z |
| Switch to palette | Tab |
| Save and exit | Escape |

### Palette Mode

| Function | Key(s) |
|----------|--------|
| Move selection | Arrow Keys |
| Confirm color | Enter / Space |
| Switch to canvas | Tab |

### Color Replace Mode

| Function | Key(s) |
|----------|--------|
| Navigate dest color | Arrow Keys |
| Execute replacement | Enter / Space |
| Cancel | Escape |

---

## 22. Town Layouts Editor

Three sub-editors: Town Layouts, Town Features, Town Interiors.

**Source:** `game.py` — `_feat_handle_townlayout_input()` ~line 2947

### Level 0 — Sub-Editor Selection

**Hint:** `[UP/DN] Browse  [ENTER] Open  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Enter sub-editor | Enter / Space |
| Go back | Escape |

### Level 1 — Layout / Feature / Interior List

**Hint:** `[UP/DN] Browse  [ENTER] Open  [A] Add  [D] Remove  [N] Rename  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Open layout | Enter / Space |
| Add new | A |
| Delete | D |
| Rename | N |
| Go back | Escape |

### Naming Mode

| Function | Key(s) |
|----------|--------|
| Type character | Printable characters (max 40) |
| Delete character | Backspace |
| Confirm name | Enter |
| Cancel | Escape |

### Level 2 — Grid Painter

**Hint:** `[ARROWS] Move  [ENTER] Paint  [TAB/B] Cycle Brush  [S] Save  [ESC] Exit`

| Function | Key(s) |
|----------|--------|
| Move cursor | Arrow Keys |
| Paint tile | Enter |
| Next brush | Tab / B |
| Previous brush | Shift+Tab / Shift+B |
| Save layout | S |
| Exit painter | Escape |

---

## 23. Modules Editor

**Source:** `game.py` — `_handle_module_input()` ~line 3513

### Module Selection

**Hint:** `[UP/DN] Browse  [S] Select  [N] New  [E] Edit  [D] Delete  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate up | Up Arrow |
| Navigate down | Down Arrow |
| Select / activate | S |
| Create new | N |
| Edit | E |
| Delete | D |
| Go back | Escape |

### Delete Confirmation

| Function | Key(s) |
|----------|--------|
| Confirm | Y |
| Cancel | N / Escape |

### Module Edit — Section Browser (Level 0)

Sections: Module Details, Settings, Towns, Dungeons, Quests, Unique Tiles, Battle Screen, Examine Screen.

**Hint:** `[UP/DN] Browse  [ENTER] Open  [A] Add  [D] Delete  [CTRL+S] Save  [ESC] Back`

| Function | Key(s) |
|----------|--------|
| Navigate | Up / Down Arrow |
| Enter section | Enter / Right Arrow |
| Add item | A |
| Delete item | D / Delete |
| Save | Ctrl+S |
| Go back | Escape / Left Arrow |

### Module Edit — Field Editor (Level 1)

**Hint:** `[UP/DN] Field  [TYPE] Edit  [LT/RT] Adjust  [CTRL+S] Save  [ESC] Back`

Identical to Spells Field Editor (see Section 16, Level 2).

### Module Create Form

**Hint:** `[UP/DN] Field  [TYPE] Edit  [LT/RT] Adjust  [CTRL+S] Create  [ESC] Cancel`

Identical control scheme to field editor; Ctrl+S creates instead of saves.

---

## 24. Battle Screen / Examine Screen Editor

**Source:** `game.py` — `_handle_battle_screen_input()` ~line 4678
**Hint:** `[ARROWS] Move  [ENTER] Paint  [TAB/B] Cycle  [I] Mode  [O] Settings  [ESC] Done`

Modes: obstacle, tile.

### Grid Painter

| Function | Key(s) |
|----------|--------|
| Move cursor | Arrow Keys / WASD |
| Paint at cursor | Enter |
| Next brush | Tab / B |
| Previous brush | Shift+Tab / Shift+B |
| Toggle obstacle/tile mode | I |
| Open settings | O |
| Exit editor | Escape / Backspace |

### Settings Sub-Menu

| Function | Key(s) |
|----------|--------|
| Navigate | Up / Down Arrow |
| Cycle left | Left Arrow |
| Cycle right | Right Arrow |
| Close settings | Escape / Backspace / O |

---

## 25. Consistency Analysis

This section documents the recurring UI patterns and the inconsistencies between them. It is the baseline for unification work.

### Pattern A — Vertical List Navigation

Used by: Title Menu, Form Party, Character Creation (race/class/gender), Settings, Save/Load, Features Main, all list browsers (Spells, Items, Monsters, Tile Types, Tile Gallery, Town Layouts, Modules).

| Action | Current binding | Status |
|--------|----------------|--------|
| Navigate up | Up Arrow | **Consistent** |
| Navigate down | Down Arrow | **Consistent** |
| Select / open | Enter (some also accept Space) | **Inconsistent** |
| Go back | Escape | **Consistent** |

### Pattern B — Field Editor

Used by: Spells, Items, Monsters, Tile Types, Modules field editors.

| Action | Current binding | Status |
|--------|----------------|--------|
| Previous field | Up Arrow | **Consistent** |
| Next field | Down Arrow | **Consistent** |
| Cycle choice | Left / Right Arrow | **Consistent** |
| Type text | Printable characters | **Consistent** |
| Delete text | Backspace | **Consistent** |
| Save | Ctrl+S | **Consistent** |
| Cancel | Escape | **Consistent** |

### Pattern C — Grid Painter

Used by: Town Layout Grid, Battle Screen, Examine Screen editors.

| Action | Current binding | Status |
|--------|----------------|--------|
| Move cursor | Arrow Keys (Battle/Examine also WASD) | **Inconsistent** — Town layout missing WASD |
| Paint | Enter | **Consistent** |
| Cycle brush | Tab / B | **Consistent** |
| Reverse cycle | Shift+Tab / Shift+B | **Consistent** |
| Save | S (Town) vs implicit on Escape (Battle/Examine) | **Inconsistent** |
| Exit | Escape (Town) vs Escape/Backspace (Battle/Examine) | **Inconsistent** |

### Pattern D — Text Input / Naming

Used by: Character name entry, Gallery rename/duplicate, Town layout naming.

| Action | Current binding | Status |
|--------|----------------|--------|
| Type | Printable characters | **Consistent** |
| Delete | Backspace | **Consistent** |
| Confirm | Enter | **Consistent** |
| Cancel | Escape | **Consistent** |

### Pattern E — Confirmation Dialog

Used by: Form Party delete, Save/Load delete, Modules delete.

| Action | Current binding | Status |
|--------|----------------|--------|
| Confirm | Y | **Consistent** |
| Cancel | N / Escape | **Consistent** |

---

### Inconsistency Register

Each row is a specific inconsistency found across the codebase, with the screens affected and a description of the variance.

| # | Action | Current bindings | Screens affected | Variance |
|---|--------|-----------------|------------------|----------|
| 1 | **Select / Confirm** | Enter+Space vs Enter only | Title, Char Create, Game Over, Features Main use Enter+Space; Combat uses Enter only | Some screens accept Space as confirm, others don't |
| 2 | **Delete item** | D vs X vs Delete vs D/Delete | Form Party: D; Gallery sprite list: X/Delete; Editors: D/Delete; Town layouts: D | No consistent delete key across screens |
| 3 | **Save work** | S vs Ctrl+S vs Escape (implicit) | Town painter: S; Field editors: Ctrl+S; Pixel editor: Escape (saves on exit) | Three different save paradigms |
| 4 | **Go back / cancel** | Escape vs Escape+Backspace vs Escape+Left | Most screens: Escape; Battle/Examine: Escape+Backspace; Modules browser: Escape+Left Arrow | Inconsistent alternate back keys |
| 5 | **Close screen** | Escape vs M/Escape vs P/Escape vs Q/Escape | Settings: M+Esc; Inventory: P+Esc; Quest log: Q+Esc | Contextual toggle keys double as close |
| 6 | **Grid movement** | Arrows only vs Arrows+WASD | Town layout painter: Arrows only; Battle/Examine/Overworld: Arrows+WASD | WASD support missing from town grid painter |
| 7 | **Tag toggle** | Enter / Space / Left / Right (4 keys) | Gallery tag editor only | Overly permissive — 4 keys for one action |
| 8 | **Open item for edit** | Enter vs Enter+Right Arrow | Features Main: Enter/Space; List browsers: Enter/Right Arrow | Right Arrow as "drill in" is inconsistent with Space |
| 9 | **Create new item** | A vs C vs N | Editors: A (Add); Form Party: C (Create); Modules: N (New) | Three different "create" keys |
| 10 | **Brush cycling** | Tab/B (painters) vs Q/E (pixel editor) | Grid painters: Tab/B; Pixel editor: Q/E for color cycle | Different cycle keys between related editors |

---

### Summary Statistics

- **Total screens:** 24
- **Total unique controls:** 200+
- **Recurring patterns identified:** 5 (A–E)
- **Inconsistencies logged:** 10
- **Most consistent pattern:** Field Editor (Pattern B) — fully uniform across 5 editors
- **Least consistent area:** Delete/Save/Create keys — different across nearly every screen family
