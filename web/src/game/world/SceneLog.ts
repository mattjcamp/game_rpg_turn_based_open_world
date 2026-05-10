/**
 * Shared bottom-of-viewport log strip used by every map scene
 * (Overworld, Town, Dungeon). Today it carries just the in-game
 * date/time and lunar phase; future iterations will surface
 * step-driven log lines (combat one-liners, "you spotted a trap",
 * etc.) into the same strip so the player has a single, predictable
 * place to look across all maps.
 *
 * Lifecycle:
 *
 *   - `installSceneLog(scene)` creates the strip (background bar,
 *     moon Graphics, time Text) and returns a handle.
 *   - `refreshSceneLog(handle, clock)` repaints the time + moon.
 *     Cheap — call once per scene boot and once per move tick.
 *
 * Camera contract:
 *
 *   The strip is pinned to the bottom of the viewport via
 *   `setScrollFactor(0)`. Each scene's `setBounds` must extend the
 *   world height by `LOG_HEIGHT` so the camera can scroll the bottom
 *   row of tiles above the strip — without that, when the party
 *   stands at the bottom row of a tall map the player marker hides
 *   behind the log strip. See `OverworldScene.installCamera` for
 *   the canonical setup.
 */

import type Phaser from "phaser";
import {
  dateStr,
  lunarPhaseIndex,
  lunarPhaseName,
  timeStr,
  type GameClock,
} from "./GameTime";
import { paintMoonPhase, MOON_HUD_SIZE } from "./MoonIcon";

/** Pixel height of the log strip. Pinned to viewport bottom. */
export const LOG_HEIGHT = 32;

/** Width the strip is drawn at — matches the fixed Phaser canvas in
 *  `PhaserGame.ts`. Centralised here so a future canvas-size change
 *  only needs to touch one constant. */
const VIEW_WIDTH = 960;

/** Total viewport height — the strip sits with its TOP at
 *  `VIEW_HEIGHT - LOG_HEIGHT` so it lines up with the bottom edge. */
const VIEW_HEIGHT = 720;

/** Background bar fill — same dark navy the old top HUD used so the
 *  log reads as scene chrome rather than an in-world overlay. */
const BAR_FILL = 0x161629;
const BAR_BORDER = 0x2a2a3a;
const TEXT_COLOR = "#dcdcc8";

export interface SceneLogHandle {
  bar: Phaser.GameObjects.Rectangle;
  clockText: Phaser.GameObjects.Text;
  moonIcon: Phaser.GameObjects.Graphics;
  /** Last phase index painted into `moonIcon` — letting
   *  `refreshSceneLog` skip the expensive shape repaint when the
   *  phase hasn't rolled over (one of eight per 28-day cycle). */
  lastPhase: number;
}

/**
 * Install the bottom log strip on `scene`. Adds three GameObjects
 * pinned to the viewport: a background rectangle, a Graphics for the
 * moon, and a Text for the date/time + phase name. Returns a handle
 * the caller passes to `refreshSceneLog` on each tick.
 *
 * Depth is set high (50) so the strip layers over world sprites,
 * darkness overlays, and the player marker without extra bookkeeping
 * at the scene level.
 */
export function installSceneLog(scene: Phaser.Scene): SceneLogHandle {
  const top = VIEW_HEIGHT - LOG_HEIGHT;
  const bar = scene.add
    .rectangle(0, top, VIEW_WIDTH, LOG_HEIGHT, BAR_FILL, 0.92)
    .setOrigin(0)
    .setScrollFactor(0)
    .setStrokeStyle(1, BAR_BORDER)
    .setDepth(50);

  // Moon icon sits in the strip's left padding. Centred vertically
  // inside the strip so it lines up with the text baseline.
  const moonIcon = scene.add
    .graphics()
    .setScrollFactor(0)
    .setDepth(51);

  // Time + phase string sits to the right of the moon. Left-aligned
  // so future log lines (combat messages, etc.) can extend rightward
  // into the same strip without fighting the time stamp's anchor.
  const clockText = scene.add
    .text(0, 0, "", {
      fontFamily: "monospace",
      fontSize: "12px",
      color: TEXT_COLOR,
    })
    .setOrigin(0, 0.5)
    .setScrollFactor(0)
    .setDepth(51);

  return { bar, clockText, moonIcon, lastPhase: -1 };
}

/**
 * Repaint the date/time + moon to match `clock`. Idempotent — safe to
 * call every move tick. The Graphics shape is only redrawn when the
 * lunar phase index changes; the text is updated unconditionally
 * since the time string ticks every step.
 */
export function refreshSceneLog(
  handle: SceneLogHandle,
  clock: GameClock,
): void {
  const text = `${dateStr(clock)} ${timeStr(clock)} · ${lunarPhaseName(clock)}`;
  handle.clockText.setText(text);

  const r = MOON_HUD_SIZE / 2;
  // Moon centre lives `padX + r` from the strip's left edge; text
  // sits a small gap to the right of the moon's right edge.
  const padX = 12;
  const moonCx = padX + r;
  const moonCy = VIEW_HEIGHT - LOG_HEIGHT / 2;
  // Vertical text anchor is `originY = 0.5` from `installSceneLog`,
  // so `y` is the centre line.
  handle.clockText.setPosition(moonCx + r + 6, moonCy);

  const phase = lunarPhaseIndex(clock);
  if (phase !== handle.lastPhase) {
    paintMoonPhase(handle.moonIcon, moonCx, moonCy, r, phase);
    handle.lastPhase = phase;
  } else {
    // Reposition without repainting — paintMoonPhase doesn't move the
    // Graphics, it draws shapes at absolute coords, so the Graphics
    // object always stays at world (0, 0). Nothing to do.
  }
}

/**
 * Tear down the log strip — destroys all three GameObjects. Useful
 * when a scene needs to rebuild its UI mid-life (rare in this
 * codebase since Phaser fires `init()` on every restart, which
 * already destroys per-scene GameObjects, but exported for symmetry).
 */
export function destroySceneLog(handle: SceneLogHandle | undefined): void {
  if (!handle) return;
  handle.bar.destroy();
  handle.clockText.destroy();
  handle.moonIcon.destroy();
}
