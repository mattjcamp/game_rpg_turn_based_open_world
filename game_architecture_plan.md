# Wilderstep: Infinite Abyss

# ASSETS
- Sprites (filenames)
- Soundtracks (filenames)

# DATA MODEL OVERVIEW
- Effect
- Spell
- Recipe
- - Defines how a craftable Item (potions, and other crafting outputs to come) is made: ingredients, any required tools or stations, and the resulting Item. Crafting is its own gameplay subsystem; Recipes are the data that drives it.
- Item
- - Specialized item types like Potions are variants of Item, not separate models
- Counter
- Monster
- Race
- Character Class
- Character
- Party
- NPC
- Encounter
- Spawn
- Map Tile
- Map
- - A single unified model for authored maps. Overview, Towns, Buildings, Detail Screens, and Battle Screens are all just Maps — the distinction between them is conceptual, not structural. Every map shares the same shape and the same (map, x, y) tile-link system, and the game treats them all identically. Groups of related maps (e.g., the five maps that together make up "Town1") can be associated through tags for editor-side organization, but tags are an authoring/UX concern, not a runtime one — the game itself relies entirely on the tile-link graph.
- Dungeon Config
- - Distinct from Map because dungeons are not authored — they're procedurally generated to give the game a rogue-like dimension. A Dungeon Config holds the generator's input parameters (number of levels, torch density, difficulty curve, monster and loot pools, etc.) rather than tile data. The generated dungeon itself becomes a set of Map instances at runtime, stored in the Game (not in the Module), so each playthrough produces a different dungeon.
- Quest Step
- Quest Config
- Module
- - The canonical definition of an adventure. Contains all the custom schema that define the game world using the data models above. Think of a Module as a template — static content authored once and shipped.
- Game
- - A runtime instance of a Module. Carries the Module's current state as it changes over the game lifecycle: the Characters in the current Party, the party's position on a Map, quest progress, counter values, flags, any procedurally generated dungeon Maps, and anything else that diverges from the Module's starting state. A save file is a serialized Game.

NOTE data models can reference other data models. For instance, both Monsters and Characters may have access to Spells and use Items.

NOTES
- Tags are a future concern, primarily for editor-side organization of related items (maps, sprites, map tiles). The game itself does not depend on tags — runtime behavior is driven by explicit links and ids. The exact tag schema will be worked out alongside the editor.
- Reuse across modules is handled through **library modules** rather than a separate Template data model. A library is just a regular Module flagged as non-playable; its contents (maps, monsters, items, recipes, etc.) can be imported into other modules via the editor. Imports are always copy-on-import — the imported entity becomes a fresh, independent instance in the destination module that the author can customize freely. This copy semantics is not optional: the tile-link system uses (map, x, y) ids that are module-scoped, so every imported map needs its own identity in the destination module before links into and out of it can be wired up. See "Library modules" in the deployment plan for the mechanics.

# PROJECT ORGANIZATION

Project
- sprites
- data_model (collection of canonical data models)
- - modules (collection of module specific data models)
- docs
- - data_dictionary
- - manual
- - dev_guides
- app
- - game
- - - module index
- - - save game
- - editor
- - - module index

# DEPLOYMENT PLAN (Detailed LLM Recommendations Below)

# v2 architecture: deployment, modules, and saves

This document describes the architecture for version 2 of the game. The scope is the smaller of the two paths discussed: a single team (Matt plus a small set of collaborators) authors modules; players consume them. No public authoring, no per-user accounts, no cloud backend.

## TL;DR

A single Next.js application is deployed as a static site by the existing GitHub Actions pipeline to GitHub Pages. Inside that one app there are two routes — `/play` for the game and `/editor` for the module editor — sharing the same build. Modules are folders of JSON files committed to the repo, discovered at runtime through an index file, and selected by the player from a module picker on the title screen. Save games live in the player's browser via localStorage and are made portable by an export/import button that produces a save file (or a copy-pasteable save code). Local testing happens either by running the dev server against the working tree or by saving in-progress modules as browser-local drafts and loading them from the game's module picker.

The code is structured so that the two things most likely to change later — where modules come from and where saves live — sit behind small interfaces (`ModuleSource`, `SaveProvider`). The current implementations are static files and localStorage; future implementations could be a remote catalog or a cloud sync service without touching the rest of the game.

## Deployment topology

The current deployment is a static site built by `npm run build` and pushed to GitHub Pages by Actions on merge to `main`. v2 keeps this exactly as-is. The only structural change is that the same build now serves two routes:

```
/                  → landing page (optional)
/play              → the game
/editor            → the module editor
/editor/<moduleId> → editing a specific module
```

Both routes share the same Next.js bundle. The editor is not a separate app; it's pages and components inside the same project under `web/app/editor/`. This is important because (1) it halves the build/deploy surface area, (2) the editor and game share the same TypeScript types for module data, and (3) you can link from one to the other (e.g., "Play this module" → `/play?module=<id>`).

No backend, no serverless functions, no auth. GitHub Actions remains the only piece of infrastructure.

## Module structure

A Module is the canonical definition of an adventure — the template a Game is instantiated from. Physically, it's a folder under `modules/` containing JSON files that define its content. The exact list of files is documented in the data dictionary at `docs/data_dictionary/`; in practice a module includes monsters, items (with potions as an item subtype), spells, effects, recipes (crafting), encounters, spawn points, counters, NPCs, quests, maps (the unified model covering overview, towns, buildings, detail screens, and battle screens), dungeon configs (inputs to procedural dungeon generation), and a starting party. Some files are global (the tile catalog `tile_defs.json`, foundational systems like classes and races) and live in `data/` rather than per-module — those are platform-level and shared across every module.

```
modules/
  the_dragon_of_dagorn/
    module.json         ← module metadata (id, title, version, description, author)
    monsters.json
    items.json          ← includes potions and other Item subtypes
    spells.json
    effects.json
    recipes.json        ← crafting recipes (potions, etc.)
    encounters.json
    spawn_points.json
    counters.json
    npcs.json
    quests.json
    maps.json           ← every authored map: overview, towns, buildings, detail, battle
    dungeon_configs.json ← parameters for procedurally generated dungeons
    party.json          ← starting party for this module
    ...
data/                   ← global, shared across modules
  tile_defs.json        ← may move per-module later if modules need custom tiles
  classes/*.json
  races.json
  modules/
    index.json          ← list of available modules (see below)
```

NOTE some of the above data model files may be simplified, split, or adjusted as the schema firms up.

Each module has its own `module.json` at its root with metadata. The `id` field is the canonical handle and must match the folder name. The `version` field is a free-form string used for save-game compatibility checks (see "Saves and module versioning" below).

## Library modules

A library is a Module that exists for reuse rather than for play. It uses the same folder structure, the same `module.json`, the same per-module JSON files, and ships through the same pipeline as a playable module. The only difference is a metadata flag that tells the play-side module picker to skip it:

```json
{
  "id": "templates",
  "title": "Reusable Maps and Content",
  "role": "library",
  "version": "1.0.0",
  "author": "Matt"
}
```

Library modules are visible to the editor like any other module, but the player never sees them in the module picker. This means the same `ModuleSource` infrastructure that loads playable modules also surfaces library content for authoring — no parallel pipeline, no new data model.

**Copy-on-import, always.** When the author selects an entity (most commonly a Map) from a library and imports it into the current module, the editor produces a fresh, independent copy that lives entirely in the destination module's JSON files. After import, edits to the copy don't affect the library, and edits to the library don't affect the copy. The author is free to customize the imported map to fit the new adventure.

This copy semantics isn't just a preference; it's a requirement of the tile-link system. Every Map needs a module-scoped identity so that (map, x, y) links into and out of it can be wired up concretely in the destination module. A by-reference template would leave the library's ids stranded in the destination, which would either bleed edits across modules or force the engine to maintain a translation layer. Copy semantics avoid the problem entirely — and they're the only model that lets the author make the imported map "their own" within the new module.

**Provenance metadata.** The editor stamps imported entities with provenance information for authoring convenience:

```json
{
  "id": "riverside_town_north",
  "name": "Riverside (North)",
  "importedFrom": {
    "module": "templates",
    "entityId": "riverside_town_north",
    "version": "1.2.0"
  },
  ...
}
```

The game never reads this metadata; it's purely so the editor can show "imported from templates@1.2.0" and offer a "re-import latest" action if the source has since changed. The author chooses whether to take the update — re-import is itself just another copy operation.

**Why this metadata is worth stamping from day one.** The `importedFrom` field is essentially free at import time — a few extra keys on the entity record — but it keeps a lot of future editor capability cheap. With provenance in place, the editor can later support diffing an imported copy against its source ("the library map has gained two new shops; want to merge them in?"), batch re-imports across many entities, library-wide "where is this used?" search, and warnings when an author edits a copy in ways that diverge meaningfully from the library version. None of that is v1 work, but if the metadata isn't stamped from the start, retrofitting it later means either re-importing everything by hand or accepting that the first wave of imported content will never have provenance. Cheap to do now, expensive to add back.

**Generalizes beyond Maps.** Although the immediate driver is reusing town maps, the same library + copy-on-import pattern works for Monsters, Items, Recipes, NPCs, Spells, and anything else worth reusing. The editor doesn't need new code per model type — it just needs to know how to copy a JSON record from one module's files into another's.

## The module index

The game discovers modules through `data/modules/index.json`. This file is the directory of every module that ships with the deployed build.

```json
{
  "modules": [
    {
      "id": "the_dragon_of_dagorn",
      "title": "The Dragon of Dagorn",
      "description": "The original adventure. Travel the realm in search of the dragon's hoard.",
      "author": "Matt",
      "version": "1.0.0",
      "path": "modules/the_dragon_of_dagorn"
    },
    {
      "id": "island",
      "title": "Island",
      "description": "A short test module.",
      "author": "Matt",
      "version": "0.3.0",
      "path": "modules/island"
    }
  ]
}
```

On startup, the game fetches `data/modules/index.json`, populates a module picker on the title screen, and on selection loads the chosen module's files from its `path`. The play-side picker filters out any module whose `role` is `"library"` so library content doesn't appear as a playable option; the editor picker shows everything. The current hardcoded `ACTIVE_MODULE = "the_dragon_of_dagorn"` constant goes away — the active module becomes a runtime selection persisted in localStorage so the player returns to the same module next session.

The index is generated, not hand-edited. A build script (`web/scripts/build-module-index.mjs`) walks `modules/`, reads each `module.json`, and writes `data/modules/index.json`. The script runs as a `prebuild` step. This avoids the "I added a new module but forgot to update the index" foot-gun.

## Authoring workflow

The authoring flow has three modes, in increasing order of permanence.

**Edit in the browser editor.** Open `/editor` in the deployed site or in the local dev server. Pick a module from the dropdown (or click "New module"). Edit its content. Changes accumulate in the editor's working state.

**Local draft.** Click "Save Draft." The current working state of the module is written to localStorage under a `drafts/<moduleId>` key. Drafts show up in the game's module picker with a "(draft)" suffix so you can click straight to `/play` and test them without leaving the browser. Drafts live only in your browser — they don't sync, they don't deploy, they don't reach other collaborators.

**Export and commit.** When the module is ready to ship, click "Export." The editor produces a zip (or the individual JSON files) that you drop into `modules/<id>/` in your local checkout. Commit, push, GitHub Actions deploys, players see the new module. This is the same git-driven workflow you have today, just with a usable editor in front of it instead of the Python editor.

These three modes compose well. You can author entirely in drafts for fast iteration, then export once a milestone is hit. Or you can `git checkout` a module, edit it in the editor against your local dev server, and commit when satisfied. The editor can detect whether it's running against the dev server (the working tree is writable) or the deployed site (read-only), and surface or hide options accordingly.

## Local testing

Two paths cover the common cases.

**Dev server against the working tree.** `npm run dev` starts the Next.js dev server. The game and editor run at `localhost:3000` and read directly from `modules/` and `data/` on disk. Any file you change in those folders shows up on next page reload — this is the natural workflow for "test this module before I commit." The module picker shows whatever's in `modules/` plus any drafts in localStorage.

**Browser drafts.** Even when running against the deployed site, you can save and test drafts entirely in your browser via the localStorage `drafts/<moduleId>` mechanism above. This is useful for collaborators who don't have the repo checked out, or for testing changes on a different machine without going through git.

For collaborators specifically: the minimum tooling required is a browser. If they don't want to clone the repo, they can author entirely via the deployed editor + drafts, then send the exported JSON files to you (or anyone with commit access) to commit. This keeps the canonical-modules-in-repo discipline while letting people who don't use git contribute content.

## Save games

A save is a serialized Game — a Module instance plus all the runtime state that has accumulated on top of it (party composition, map position, quest progress, counters, flags, any procedurally generated dungeon maps, and so on). Saves are per-player, per-module, and live in the player's browser. Storage is localStorage, keyed by module id and save slot:

```
saves/<moduleId>/<slotId> → serialized Game {
  partyState, mapPosition, counters, quests, flags,
  generatedDungeons: { ... },   ← rogue-like dungeon layouts produced this playthrough
  ...
}
```

The presence of generated dungeon maps inside the save is worth flagging early: it means save size grows with how much of the rogue-like content the player has explored, and the serialization format needs to handle Map instances (the same shape as authored maps) as a payload, not just scalar state. localStorage has roughly 5–10 MB per origin, which is plenty for a hand-authored campaign but a real constraint for a player who has descended into many dungeon levels. Worth measuring on real content before it becomes a problem.

A save records its module's id and version when it's written. On load, the game checks compatibility — if the active module's version has changed in an incompatible way since the save was written, the game warns the player. The compatibility rules can be lenient (warn but load) or strict (refuse to load) depending on how breaking the version bump is; for now, warn-and-load is the right default.

Portability between devices is provided by an Export Save / Import Save flow on the title screen. Export produces a JSON file the player can email to themselves, drop in Dropbox, or carry on a USB stick. Import reads that JSON back in and creates a save slot from it. As a more retro-feeling option, the same JSON can be base64-encoded into a short save code the player can copy and paste — same data, different envelope.

No accounts, no cloud, no servers. The player owns their saves.

## Forward-compatibility seams

Two abstractions are worth introducing on day one even though the v2 implementation doesn't need them. They cost a small amount of indirection now and save a refactor later if the architecture needs to evolve.

### `ModuleSource`

A contract for "where do modules come from?" The day-one implementation reads from the static deployed files (`StaticModuleSource`). A future implementation could read from a remote catalog (`RemoteModuleSource`) without the rest of the game changing.

```ts
interface ModuleSummary {
  id: string;
  title: string;
  description: string;
  author: string;
  version: string;
}

interface ModuleSource {
  list(): Promise<ModuleSummary[]>;
  load(moduleId: string): Promise<Module>;
}

class StaticModuleSource implements ModuleSource {
  // Reads from /data/modules/index.json and /modules/<id>/*
}
```

All game and editor code talks to a `ModuleSource` instance. The instance is wired up once at app startup.

### `SaveProvider`

A contract for "where do saves live?" The day-one implementation is localStorage. A future implementation could be cloud sync, a file-system-backed provider for desktop builds, or a server-backed one if you ever change your mind about accounts.

```ts
interface SaveSummary {
  id: string;
  moduleId: string;
  moduleVersion: string;
  createdAt: string;
  updatedAt: string;
  partyLevel: number;
  // ... other metadata for save-slot UI
}

interface SaveProvider {
  list(moduleId?: string): Promise<SaveSummary[]>;
  load(saveId: string): Promise<SaveData>;
  save(saveId: string, data: SaveData): Promise<void>;
  delete(saveId: string): Promise<void>;
  export(saveId: string): Promise<string>;  // returns JSON string or save code
  import(payload: string): Promise<string>; // returns new saveId
}

class LocalStorageSaveProvider implements SaveProvider {
  // Day-one implementation
}
```

The export/import methods are part of the interface from the start because they're features of the simple architecture, not future additions.

### What this buys you

If you later decide you do want a remote module catalog (workshop-style), the change is to write a `RemoteModuleSource` and toggle which implementation gets wired up at startup — possibly even allowing both at once (`CompositeModuleSource` that merges static + remote results). If you later decide you want cloud saves, you write a `CloudSaveProvider` against the same interface. Neither change touches game logic, editor logic, or UI components.

## What this architecture explicitly defers

To keep the scope honest, here are the things this design intentionally does not address. Each can be added later without a rewrite, but none of them is built into v2 from the start.

User accounts and auth. No login. The game is single-player and stateless from the server's perspective.

Public module authoring. Only people with repo commit access can ship modules to the deployed game. Drafts in localStorage are a private workspace, not a publication mechanism.

Cloud save sync. Saves stay in the browser they were created in. Cross-device portability is manual via export/import.

Module ratings, comments, discovery beyond the static index. The module picker shows what's in the index; that's the whole UX.

Multiplayer of any kind.

If any of these become important, the abstractions described above are the wiring points. The "harder path" architecture from the previous conversation (with Vercel/Cloudflare, R2, serverless functions, OAuth) is the natural extension if and when it's needed.

## Open questions to resolve before implementation

A handful of decisions need to be made before this can be built out concretely. None blocks the broad direction; they're all "decide before writing code" items.

**Per-module vs global split.** The current decision: per-module → monsters, items (potions included), spells, effects, recipes, encounters, spawn points, counters, NPCs, quests, maps (unified), dungeon configs, party. Global (in `data/`) → tile_defs, classes, races. Tile defs may want to move per-module later if modules need custom tiles. Classes and races are global by default but a module could plausibly want to override them — leave this as a soft decision and revisit when a module actually needs it.

**`module.json` schema.** What fields exactly? At minimum: `id`, `title`, `description`, `author`, `version`, `gameVersion` (min compatible engine version). Possibly: `tags`, `previewImage`, `startingNotes`, license info. The tag schema specifically is deferred until the editor design firms up (see top-level NOTES on tags).

**Versioning policy.** Semver? Date-based? The version string is consumed by save compatibility checks and by the editor when offering "upgrade this save to the new module version." The simplest viable rule is semver with the understanding that a major bump invalidates saves.

**Editor scope for v1 of v2.** The Python editor does a lot. The web editor will not start at parity. Pick a minimum viable feature set — likely: edit monsters, items, spells, effects, recipes, encounters, spawn points, NPCs, quests, party, dungeon configs (which are forms, not maps — they don't need a spatial editor), and a basic import-from-library flow for at least Maps (so the existing library can pay off immediately even before the in-editor map editor exists). Map editing (the big one, especially under the unified Map model that now covers overworld + town + interior + battle screens) needs its own design pass and likely isn't in the first cut. Note that authored maps and procedurally generated dungeons split the editor's responsibility cleanly: maps are authored in the editor (or imported from a library), dungeons are configured in the editor and generated by the engine.

**Where do drafts go on commit?** When the author exports a draft and commits, the draft in localStorage is now redundant. Should the editor offer to delete the draft after successful export? Keep it as a backup? Best practice is probably "keep it but mark it as exported and offer to delete from a manage-drafts screen."

**Asset story.** Modules will eventually want their own sprites — custom monsters, custom NPCs. Currently sprites are global under `web/public/assets/`. Per-module assets would need to live under `modules/<id>/assets/` and be served by Next.js (or copied to public at build time). Worth a short follow-up doc.

## Concrete next steps

In a rough order of dependency:

1. Document the per-module vs. global file split (now decided above) and the Module/Game data-model contract in `docs/data_dictionary/`. This unblocks the directory layout and the TypeScript types.
2. Write the `module.json` schema doc as part of the same data-dictionary update.
3. Build the module index generator script (`web/scripts/build-module-index.mjs`) and wire it as `prebuild`.
4. Refactor the existing `the_dragon_of_dagorn` module into the new layout — collapsing towns and dungeons into the unified `maps.json`, folding potions into `items.json`. This validates the design against real content and produces the first reference module.
5. Implement `ModuleSource` and replace the hardcoded `ACTIVE_MODULE` constant with module-picker UI on the title screen.
6. Implement `SaveProvider` (a save is a serialized Game) and rework the existing save/load paths through it. Add export/import buttons.
7. Build the editor. Start with the smallest reasonable scope (monsters, items) to validate the editor → draft → game-test loop end-to-end, then expand to the rest of the per-module files. Map editing is its own design pass.
8. Address asset story when the first module starts needing custom sprites.

The first six steps are pure engineering with clear boundaries and could be done before any editor work happens. The editor work is the larger and more open-ended chunk.
