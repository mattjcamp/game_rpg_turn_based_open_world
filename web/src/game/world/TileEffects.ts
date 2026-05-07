/**
 * Per-tile animated effects driven by `tile_properties[col,row].effect`.
 *
 * Mirrors the Python renderer's procedural overlay drawing
 * (`Renderer._draw_effect_*` in `src/renderer.py`): each frame a
 * single Graphics object is cleared and repainted using
 * time + per-tile-seed parametric math, so torches flicker, fires
 * dance, smoke rises, and fairy lights twinkle without animation
 * frames or sprite sheets.
 *
 *   - "torch"        — small mounted-flame, gentle flicker
 *   - "fire"         — campfire flame with a spark drift
 *   - "fairy_light"  — three pastel sparkles orbiting the tile
 *   - "rising_smoke" — six staggered grey puffs drifting up
 *
 * Each tile gets a deterministic seed from its (col,row) so neighbours
 * never animate in lockstep — same trick the Python version uses.
 */

import type Phaser from "phaser";
import type { TileMap } from "./TileMap";

// Phaser scene event names. Hardcoding the strings (rather than
// reaching into `Phaser.Scenes.Events.*` at runtime) keeps this
// module loadable in the Vitest Node environment without pulling
// the full Phaser bundle into tests.
const PHASER_UPDATE = "update";
const PHASER_SHUTDOWN = "shutdown";

export type TileEffectKind = "torch" | "fire" | "fairy_light" | "rising_smoke";

const KNOWN: ReadonlySet<string> = new Set([
  "torch", "fire", "fairy_light", "rising_smoke",
]);

/** Parse a tile_properties.effect string into a known kind, or null. */
export function parseTileEffect(value: unknown): TileEffectKind | null {
  if (typeof value !== "string") return null;
  return KNOWN.has(value) ? (value as TileEffectKind) : null;
}

export interface AnimatedTile {
  col: number;
  row: number;
  effect: TileEffectKind;
}

/**
 * Scan a tile map's `tileProperties` for entries whose `effect` is one
 * of the four animated kinds. Out-of-bounds keys are skipped silently.
 */
export function collectAnimatedTiles(tileMap: TileMap): AnimatedTile[] {
  const out: AnimatedTile[] = [];
  for (const [key, entry] of Object.entries(tileMap.tileProperties)) {
    if (!entry || typeof entry !== "object") continue;
    const eff = parseTileEffect((entry as { effect?: unknown }).effect);
    if (!eff) continue;
    const [c, r] = key.split(",").map((s) => parseInt(s, 10));
    if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
    if (!tileMap.inBounds(c, r)) continue;
    out.push({ col: c, row: r, effect: eff });
  }
  return out;
}

/** Per-tile deterministic seed — same as Python's (col*31 + row*17). */
function seedFor(col: number, row: number): number {
  return ((col * 31 + row * 17) & 0xffff);
}

// ── Per-effect painters ────────────────────────────────────────────
//
// Each painter draws into the shared Graphics object. Coordinates are
// in scene/world space. `t` is seconds since scene start. `ts` is the
// tile size in pixels (32 in our maps).

function drawFire(
  g: Phaser.GameObjects.Graphics,
  px: number, py: number, ts: number,
  col: number, row: number, t: number,
): void {
  const seed = seedFor(col, row);
  const cx = px + ts / 2;
  const baseY = py + ts - 4;
  const flicker = 0.7 + 0.3 * Math.sin(t * 7.0 + seed);

  // Soft glow under the flame.
  const glowR = Math.max(4, Math.floor(ts * 0.35 * flicker));
  g.fillStyle(0xff8228, 70 / 255);
  g.fillCircle(cx, baseY + 2, glowR);

  // Outer flame (red-orange) — slight tip jitter so it dances.
  const outerH = Math.floor(ts * 0.55 * flicker) + 2;
  const tipDx = Math.floor(Math.sin(t * 9 + seed));
  g.fillStyle(0xf05a1e, 1);
  g.fillPoints([
    { x: cx + tipDx, y: baseY - outerH },
    { x: cx - 5,     y: baseY - outerH / 2 },
    { x: cx - 6,     y: baseY - 2 },
    { x: cx + 6,     y: baseY - 2 },
    { x: cx + 5,     y: baseY - outerH / 2 },
  ], true);

  // Inner yellow flame, slightly smaller.
  const innerFlicker = 0.7 + 0.3 * Math.sin(t * 11.0 + seed * 1.7);
  const innerH = Math.floor(outerH * 0.65 * innerFlicker) + 1;
  g.fillStyle(0xffdc5a, 1);
  g.fillPoints([
    { x: cx,     y: baseY - innerH },
    { x: cx - 3, y: baseY - innerH / 2 },
    { x: cx - 4, y: baseY - 2 },
    { x: cx + 4, y: baseY - 2 },
    { x: cx + 3, y: baseY - innerH / 2 },
  ], true);

  // White-hot core dot.
  g.fillStyle(0xffffdc, 1);
  g.fillCircle(cx, baseY - 3, 1);

  // Occasional spark drifting up.
  const sparkPhase = ((t * 1.3 + seed * 0.07) % 1.0 + 1.0) % 1.0;
  if (sparkPhase < 0.6) {
    const sx = cx + Math.floor(Math.sin(t * 5 + seed) * 5);
    const sy = baseY - 6 - Math.floor(sparkPhase * 14);
    const sa = 1.0 - sparkPhase / 0.6;
    g.fillStyle(0xffc850, sa);
    g.fillCircle(sx, sy, 1);
  }
}

function drawTorch(
  g: Phaser.GameObjects.Graphics,
  px: number, py: number, ts: number,
  col: number, row: number, t: number,
): void {
  const seed = seedFor(col, row);
  const cx = px + ts / 2;
  // A torch is mounted on a wall — sit higher than a campfire.
  const baseY = py + ts / 2 + ts / 6;
  const flicker = 0.85 + 0.15 * Math.sin(t * 5.0 + seed);

  // Subdued halo.
  const glowR = Math.max(3, Math.floor(ts * 0.22 * flicker));
  g.fillStyle(0xff9632, 55 / 255);
  g.fillCircle(cx, baseY + 1, glowR);

  // Outer flame — narrower, ~60% the height of `fire`.
  const outerH = Math.floor(ts * 0.32 * flicker) + 2;
  const tipDx = Math.floor(Math.sin(t * 6 + seed));
  g.fillStyle(0xeb6e28, 1);
  g.fillPoints([
    { x: cx + tipDx, y: baseY - outerH },
    { x: cx - 3,     y: baseY - outerH / 2 },
    { x: cx - 3,     y: baseY - 1 },
    { x: cx + 3,     y: baseY - 1 },
    { x: cx + 3,     y: baseY - outerH / 2 },
  ], true);

  // Inner yellow flame.
  const innerFlicker = 0.85 + 0.15 * Math.sin(t * 8.0 + seed * 1.7);
  const innerH = Math.floor(outerH * 0.6 * innerFlicker) + 1;
  g.fillStyle(0xffdc64, 1);
  g.fillPoints([
    { x: cx,     y: baseY - innerH },
    { x: cx - 2, y: baseY - innerH / 2 },
    { x: cx - 2, y: baseY - 1 },
    { x: cx + 2, y: baseY - 1 },
    { x: cx + 2, y: baseY - innerH / 2 },
  ], true);

  // White-hot core.
  g.fillStyle(0xffffe6, 1);
  g.fillCircle(cx, baseY - 2, 1);
}

function drawFairyLight(
  g: Phaser.GameObjects.Graphics,
  px: number, py: number, ts: number,
  col: number, row: number, t: number,
): void {
  const seed = seedFor(col, row);
  const cx = px + ts / 2;
  const cy = py + ts / 2;
  const radius = ts / 3;
  const colors = [0xffebb4, 0xc8dcff, 0xffc8f0]; // cream, icy blue, rose
  for (let i = 0; i < 3; i++) {
    const phase = t * 1.4 + i * 2.094 + seed * 0.01;
    const x = cx + Math.cos(phase) * radius;
    const y = cy + Math.sin(phase) * (radius * 0.7);
    const twinkle = 0.5 + 0.5 * Math.sin(t * 5 + i * 1.7 + seed);
    const a = twinkle;
    if (a < 0.12) continue;
    const c = colors[i];
    // Soft halo.
    g.fillStyle(c, a * 0.25);
    g.fillCircle(x, y, 4);
    // Four-point glint cross.
    g.lineStyle(1, c, Math.min(1.0, a + 0.16));
    g.lineBetween(x - 2, y, x + 2, y);
    g.lineBetween(x, y - 2, x, y + 2);
    // Bright core.
    g.fillStyle(0xffffff, Math.min(1.0, a + 0.16));
    g.fillCircle(x, y, 1);
  }
}

function drawRisingSmoke(
  g: Phaser.GameObjects.Graphics,
  px: number, py: number, ts: number,
  col: number, row: number, t: number,
): void {
  const seed = seedFor(col, row);
  const cx = px + ts / 2;

  // Faint dark base smudge anchoring the column.
  const baseY = py + ts - 3;
  const baseR = Math.max(3, Math.floor(ts / 5));
  const basePulse = 0.85 + 0.15 * Math.sin(t * 2.0 + seed);
  g.fillStyle(0x3c3c41, (110 * basePulse) / 255);
  g.fillCircle(cx, baseY, baseR);

  // Six staggered puffs drifting up.
  const nPuffs = 6;
  for (let i = 0; i < nPuffs; i++) {
    let phase = (t * 0.7 + i / nPuffs + seed * 0.013) % 1.0;
    if (phase < 0) phase += 1.0;
    const y = py + ts - 2 - phase * ts * 1.25;
    const sway = Math.sin(phase * Math.PI * 2 + seed + i * 0.7) * 5;
    const x = cx + sway;
    const r = 4 + 5 * Math.sin(phase * Math.PI);
    if (r < 1) continue;
    const a = (1.0 - phase) * Math.min(1.0, phase * 5);
    if (a <= 0) continue;
    let shade = 150 - 50 * phase + (phase > 0.55 ? 80 : 0);
    shade = Math.max(60, Math.min(220, Math.round(shade)));
    const color = (shade << 16) | (shade << 8) | shade;
    g.fillStyle(color, (230 * a) / 255);
    g.fillCircle(x, y, r);
    // Inner darker core gives the puff dimension.
    const innerR = Math.max(1, r - 2);
    const inner = Math.max(40, shade - 50);
    const innerColor = (inner << 16) | (inner << 8) | (inner + 5);
    g.fillStyle(innerColor, Math.min(1.0, (230 * a + 20) / 255));
    g.fillCircle(x, y, innerR);
  }
}

function drawTileEffect(
  g: Phaser.GameObjects.Graphics,
  kind: TileEffectKind,
  px: number, py: number, ts: number,
  col: number, row: number, t: number,
): void {
  switch (kind) {
    case "fire":         return drawFire(g, px, py, ts, col, row, t);
    case "torch":        return drawTorch(g, px, py, ts, col, row, t);
    case "fairy_light":  return drawFairyLight(g, px, py, ts, col, row, t);
    case "rising_smoke": return drawRisingSmoke(g, px, py, ts, col, row, t);
  }
}

/**
 * Install animated overlays for every tile in `tileMap` whose
 * `tile_properties.effect` is one of the supported kinds. Creates one
 * Graphics object covering the whole map and clears+redraws it on
 * every scene UPDATE event. Returns a teardown function; the helper
 * also auto-cleans on the scene's SHUTDOWN event so callers usually
 * don't need to keep the handle.
 */
export function installTileEffects(
  scene: Phaser.Scene,
  tileMap: TileMap,
  tileSize: number,
  depth: number,
): () => void {
  const tiles = collectAnimatedTiles(tileMap);
  if (tiles.length === 0) return () => {};
  const g = scene.add.graphics().setDepth(depth);
  const handler = (time: number) => {
    g.clear();
    const t = time * 0.001;
    for (const a of tiles) {
      drawTileEffect(
        g, a.effect,
        a.col * tileSize, a.row * tileSize, tileSize,
        a.col, a.row, t,
      );
    }
  };
  scene.events.on(PHASER_UPDATE, handler);
  const teardown = () => {
    scene.events.off(PHASER_UPDATE, handler);
    g.destroy();
  };
  scene.events.once(PHASER_SHUTDOWN, teardown);
  return teardown;
}
