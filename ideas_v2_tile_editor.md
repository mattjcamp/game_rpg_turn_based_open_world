Honest answer: the framework choice is the right question, but the answer isn't "TypeScript/Phaser" — it's "TypeScript + React, with Phaser embedded for the canvas preview only." You correctly identified what you're really building: a structured JSON editor. Phaser is the wrong tool for *that* part of the project, just like pygame turned out to be the wrong tool for it in v1.

The way to think about a level/module editor is two layers:

**The chrome — forms, sidebars, file lists, property inspectors, undo stack, dialogs.** This is what dominates the surface area of any real editor and it's where the Python version spent the most code (`features_editor.py`, the module_editor_* files). HTML + React eats this for breakfast. You get contenteditable, native inputs, focus management, accessibility, copy/paste, multi-select, virtualized lists, JSON-schema-driven forms (rjsf or a hand-rolled equivalent), Monaco/CodeMirror for raw-JSON escape hatches. Phaser gives you none of that — every form field becomes a hand-painted rectangle with hand-rolled keyboard handling. You've already lived this.

**The canvas — tile grid, sprite placement, drag handles, lighting preview, walkability overlay.** Here Phaser is genuinely good. You already have `tileSpriteKey`, the tile manifest, the renderer, the lighting math. A `<PhaserCanvas>` React component that mounts a small Phaser scene and exposes imperative methods (place tile, drag start, etc.) lets you reuse 100% of the runtime rendering pipeline. The editor's map preview becomes "the same draw code the game uses, with extra interaction listeners."

Pattern-wise this is exactly what Tiled, LDtk, Phaser Editor 2D, Spline, and every other modern web-based level editor does — and your `/party/new` page is already proof-of-concept for it (React handling the form, an `<img>` for sprite preview).

The big wins of porting over staying on the Python editor:

- **Free type safety and validation.** The runtime already has `Item`, `MonsterSpec`, `RawParty`, `Effect`, etc. as TypeScript types. Your editor forms read and write through those exact types — if you add `bonusDamage` to `Item.ts` tomorrow, the editor surfaces it automatically. The Python editor has to chase that drift by hand (`features_editor.py:2002` literally has "Bonus Damage" stringly-typed against the JSON key — that's the kind of duplication that goes away).
- **Live preview parity.** Edit a tile and see it render with the same lighting/decorations the game shows. The Python editor has its own renderer (`map_editor_renderer.py`) that has to be kept in sync with the runtime renderer — a known source of drift.
- **No more Python install.** Anyone who can run `npm install` can author content.
- **Schema-driven UI.** Once the runtime types exist, you can generate property panels almost mechanically. Things like enum dropdowns (race, class, damage_type) drop out of the type definitions instead of being hand-coded.

The catches you'll want to plan for:

- **File writes.** Browsers can't write to disk freely. Three reasonable options: (1) run the editor only against the Next.js dev server with a small `/api/save` route that writes JSON to `data/`, the moral equivalent of how Tiled saves; (2) the File System Access API, which is Chrome/Edge only but lets you grant a folder once and edit it directly; (3) export-as-download + drag-back-to-import, which is portable but high friction. Option 1 is probably what you want — your dev workflow is already `npm run dev`.
- **Bundle splitting.** Don't ship editor code to players. Put it under a `/admin` or `/editor` route group and configure Next.js to exclude it from the production build (or build it as a separate sub-app under `web/editor/`).
- **Undo/redo.** Plan it in from day one as a command pattern over the in-memory document. Retrofitting undo onto direct-mutation code is painful — ask the Python version.
- **The Tiled escape hatch.** For map editing specifically, exporting/importing Tiled `.tmx` is cheap and means power users can sidestep your editor for big jobs. Worth supporting from v1.

Cost-benefit, candidly: porting the Python editor is a real chunk of work — probably bigger than the original game port if you replicate every feature, smaller if you scope to the editors you actually use weekly. The smart v2 path is to port the editors you touch most often (probably module_editor_town and features_editor based on file names), leave the rest in Python for now, and let usage tell you what's next. The two editors can coexist — both read the same JSON files.

If I were starting fresh today I'd absolutely do it in React + a Phaser canvas component. But I'd port incrementally, one editor at a time, starting with whichever one you find most painful in pygame right now.