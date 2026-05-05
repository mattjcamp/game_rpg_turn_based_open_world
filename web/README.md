# Realm of Shadow — Web (TypeScript / Next.js / Phaser)

Experimental web port of the Pygame Realm of Shadow RPG. Lives alongside the
original Python implementation in this monorepo. Original code is unchanged
and continues to live at the repo root.

## Goals of this port

- Run in any modern browser, desktop or mobile, with no install.
- Keep deterministic game logic (combat, data, save/load) **separate** from
  rendering so it can be unit-tested independently.
- Reuse existing JSON game data (monsters, items, encounters) wherever possible.

## Current slice — tactical grid combat

A single turn-based encounter on the same 18×21 arena the Pygame version
uses, with positions, movement points, and bump-to-attack:

- Initiative, attack, and damage all flow through the ported
  `combat_engine` (nat-1 / nat-20 rules; crit doubles dice, not bonus).
- Each turn refills the active actor's `movePoints` from their
  `baseMoveRange`. Each cardinal step costs one point.
- Walking into an adjacent enemy is a melee attack; the bump consumes
  ALL remaining movement (turn ends after the attack resolves).
- Monster AI: attack adjacent party members (focus-fire the lowest HP),
  otherwise step toward the nearest with a Chebyshev-distance heuristic.

Input: WASD or arrow keys to move, tap an adjacent tile to move there
(works on touch devices), space or the End-Turn button to skip remaining
moves. Movement, bump, miss/hit/crit, victory/defeat are all animated.

The Phaser combat scene reads from a pure-TypeScript `Combat` controller;
the controller has no Phaser dependency and is fully tested under Vitest
(41 tests at last count — engine math + tactical rules).

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
│   └── combat/page.tsx    # loads <GameCanvas /> dynamically
├── src/
│   ├── components/
│   │   └── GameCanvas.tsx # client component that mounts Phaser
│   └── game/
│       ├── rng.ts                  # seedable RNG (mulberry32) for tests
│       ├── types.ts                # Combatant / AttackResult types
│       ├── combat/
│       │   ├── Arena.ts            # grid constants, walls, distances
│       │   ├── engine.ts           # port of src/combat_engine.py
│       │   ├── engine.test.ts      # port of tests/test_combat_engine.py
│       │   ├── Combat.ts           # tactical turn controller
│       │   └── Combat.test.ts      # engine + tactical tests
│       ├── data/
│       │   ├── monsters.ts         # small inline sample
│       │   └── fighters.ts         # 4 sample party members
│       ├── scenes/
│       │   └── CombatScene.ts      # Phaser scene
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
