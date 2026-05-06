# Realm of Shadow — Web (TypeScript / Next.js / Phaser)

Experimental web port of the Pygame Realm of Shadow RPG. Lives alongside the
original Python implementation in this monorepo. Original code is unchanged
and continues to live at the repo root.

## Goals of this port

- Run in any modern browser, desktop or mobile, with no install.
- Keep deterministic game logic (combat, data, save/load) **separate** from
  rendering so it can be unit-tested independently.
- Reuse existing JSON game data (monsters, items, encounters) wherever possible.

## Current slice — overworld + town + combat round-trip

A 40×30 hand-built overworld map (the Dragon of Dagorn module, the
freshest authored content in the Python project) plus a working
exploration → town visit → encounter → combat → return loop:

- Tiles render as 32×32 sprites (the same PNGs the Pygame build uses,
  copied into `public/assets/terrain/`). Trigger tiles without a
  dedicated sprite — campfires, graveyards, generic encounter
  markers — fall back to a coloured rectangle plus a ✦ glyph.
- Combatant art is also wired up: party members render as their class
  sprite (fighter, barbarian, ranger, wizard) and monsters as their
  named sprite (giant rat, goblin, skeleton, orc). The active actor
  gets an ember-coloured halo behind their sprite; downed combatants
  fade and tint blue-grey.
- Stepping on a town tile fades to a `TownScene` that loads the named
  town from `data/towns.json` (Plainstown, Shanty Town, Seat of the
  Realm). NPCs render with their class sprite; tapping one opens a
  multi-line dialog box. Walking onto an "overworld"-linked tile fades
  back to the world at the saved return position. Town tiles still
  render as coloured rectangles (sourced from `tile_defs.json`) — town
  interior sprite art is a future slice.
- Player avatar steps tile-by-tile with WASD / arrow keys or by tapping
  an adjacent tile. The camera follows with a soft lerp and is clamped
  to the map bounds.
- Walkability comes from the same per-tile rules as the Python version
  (water and mountain block; grass / forest / sand / path / town /
  dungeon walk; etc.).
- Stepping on a ✦ trigger tile (campfire, graveyard, monster spawn, or
  explicit encounter) hands off to `CombatScene` with the tile's
  coordinates. On victory the trigger is consumed (no infinite loops);
  on defeat the overworld renders a game-over overlay.

Combat itself remains the tactical 18×21 grid from the previous slice
(positions, move points, bump-to-attack, simple monster AI).

State that survives scene transitions — the party (HP carries across
encounters), the player's overworld position, and the set of consumed
triggers — lives in a small `gameState` module singleton. Both scenes
read and write it; neither owns it.

Three pages now:
- `/` — landing with two entry points
- `/world` — overworld scene (the main demo)
- `/combat` — standalone combat-only demo (fixed encounter, fresh party)

The combat controller and tile map are pure-TypeScript modules; Phaser
only enters at the scene layer. 52 tests at last count — combat engine
math, tactical controller rules, and tile-map / parser cases.

## Run locally

```bash
cd web
npm install
npm run dev          # http://localhost:3000
npm test             # run vitest suite once
npm run test:watch   # watch mode
```

## Project layout

```
web/
├── app/                   # Next.js App Router
│   ├── layout.tsx
│   ├── page.tsx           # landing
│   ├── world/page.tsx     # overworld demo
│   └── combat/page.tsx    # standalone combat demo
├── public/
│   └── data/
│       └── overworld.json # bundled asoloth overworld map
├── src/
│   ├── components/
│   │   └── GameCanvas.tsx # client component that mounts Phaser
│   └── game/
│       ├── rng.ts                  # seedable RNG (mulberry32) for tests
│       ├── types.ts                # Combatant / AttackResult types
│       ├── state.ts                # cross-scene party + position state
│       ├── combat/
│       │   ├── Arena.ts            # grid constants, walls, distances
│       │   ├── engine.ts           # port of src/combat_engine.py
│       │   ├── engine.test.ts      # port of tests/test_combat_engine.py
│       │   ├── Combat.ts           # tactical turn controller
│       │   └── Combat.test.ts      # engine + tactical tests
│       ├── world/
│       │   ├── Tiles.ts            # tile id constants + sprite paths
│       │   ├── TileMap.ts          # map data + tile_properties + links
│       │   ├── TileMap.test.ts     # walkability + override + link tests
│       │   ├── Towns.ts            # town parser + sprite-path normaliser
│       │   └── Towns.test.ts       # parser + normaliser tests
│       ├── data/
│       │   ├── monsters.ts         # small inline sample
│       │   └── fighters.ts         # 4 sample party members
│       ├── scenes/
│       │   ├── OverworldScene.ts   # tilemap + player + camera + links
│       │   ├── TownScene.ts        # town interior + NPCs + dialog
│       │   └── CombatScene.ts      # tactical combat
│       └── PhaserGame.ts           # Phaser config / boot
├── package.json
├── tsconfig.json
├── next.config.mjs
├── tailwind.config.ts
├── postcss.config.mjs
└── vitest.config.ts
```

## Why this shape

The Python source has a clean split between deterministic logic
(`combat_engine.py`, `data_registry.py`, `save_load.py`) and Pygame-coupled
rendering (`renderer.py`, `states/combat.py`). We mirror that here:

- `src/game/combat/engine.ts` is the direct counterpart of `combat_engine.py`.
- `src/game/combat/Combat.ts` is the controller that scene code talks to.
- `src/game/scenes/*.ts` is the only place Phaser is allowed to be imported.

This keeps the engine portable (could be reused on a server, or in a
React-only renderer later) and makes the test suite fast — Vitest never has
to touch the browser.

## Deployment options

This app is fully client-side; the only server work is Next's build. Options:

1. **Subdomain** (`game.yourblog.com`) — easiest for the experiment phase.
   Deploy as a separate Vercel project, point a custom subdomain at it.
2. **Subpath via rewrites** (`yourblog.com/game`) — Vercel rewrites from the
   blog project proxy `/game/*` to this project.
3. **Static export embedded in the blog** — `next build && next export`
   produces an `out/` directory you can drop into the blog's
   `public/game/` folder. Loses some Next features, gains simplicity.
4. **Merge into the blog Next.js app** — eventual end-state. Add this as a
   route group inside the blog repo once it's stable.

Recommended: start with (1) during experimentation; revisit later.
