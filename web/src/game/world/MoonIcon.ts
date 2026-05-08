/**
 * Procedural lunar-phase icon renderer.
 *
 * Mirrors `Renderer._get_moon_surfaces` in `src/renderer.py` —
 * 8 phases drawn as a small bright disc with a shadow ellipse
 * occluding the dim side. Phase 0 is a dark disc; phase 4 is a
 * full bright disc.
 *
 * The shadow ellipse extends slightly past the moon's circle on
 * the dark side; that overflow blends into the dark HUD bar
 * (#161629), which is close enough to the shadow tint that it
 * reads as part of the icon.
 */

import type Phaser from "phaser";

const MOON_LIT = 0xdcdcc8;     // (220, 220, 200)
const MOON_SHADOW = 0x141428;  // (20, 20, 40)
const MOON_OUTLINE = 0x3c3c50; // (60, 60, 80) — only used for the new moon

/**
 * Paint a moon-phase icon into a fresh Graphics object centred on
 * (cx, cy) with radius `r`. Caller owns the Graphics object — typical
 * use is to clear+repaint when the phase changes.
 */
export function paintMoonPhase(
  g: Phaser.GameObjects.Graphics,
  cx: number,
  cy: number,
  r: number,
  phaseIndex: number,
): void {
  g.clear();
  const pi = ((phaseIndex % 8) + 8) % 8;

  if (pi === 0) {
    // New moon: dark disc with a faint outline so it doesn't
    // disappear against the HUD.
    g.fillStyle(MOON_SHADOW, 1);
    g.fillCircle(cx, cy, r);
    g.lineStyle(1, MOON_OUTLINE, 1);
    g.strokeCircle(cx, cy, r);
    return;
  }
  if (pi === 4) {
    // Full moon: bright disc.
    g.fillStyle(MOON_LIT, 1);
    g.fillCircle(cx, cy, r);
    return;
  }

  // All other phases: bright disc + shadow ellipse on the dim side.
  g.fillStyle(MOON_LIT, 1);
  g.fillCircle(cx, cy, r);

  // Shadow ellipse width per phase (Python widths, scaled to r):
  //   pi=1 (waxing crescent):    width = 2r  (almost full shadow)
  //   pi=2 (first quarter):      width = r
  //   pi=3 (waxing gibbous):     width = r/2
  //   pi=5 (waning gibbous):     width = r/2
  //   pi=6 (last quarter):       width = r
  //   pi=7 (waning crescent):    width = 2r
  const widths: Record<number, number> = {
    1: 2 * r, 2: r, 3: r / 2, 5: r / 2, 6: r, 7: 2 * r,
  };
  const shadowW = widths[pi];
  // Phase 1-3 → waxing → shadow on the LEFT
  // Phase 5-7 → waning → shadow on the RIGHT
  let leftEdge: number;
  if (pi >= 1 && pi <= 3) {
    leftEdge = cx - r;
  } else {
    leftEdge = cx + r - shadowW;
  }
  // Phaser's fillEllipse takes (centerX, centerY, width, height).
  const ex = leftEdge + shadowW / 2;
  g.fillStyle(MOON_SHADOW, 1);
  g.fillEllipse(ex, cy, shadowW, r * 2);
}

/** Diameter (px) used for the HUD moon icon. */
export const MOON_HUD_SIZE = 14;
