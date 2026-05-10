/**
 * Procedural lunar-phase icon renderer.
 *
 * Mirrors `Renderer._get_moon_surfaces` in `src/renderer.py` —
 * 8 phases drawn as a bright disc with a shadow ellipse occluding
 * the dim side. Phase 0 is a dark outlined disc; phase 4 is a full
 * bright disc.
 *
 * Colour choices vs the Python pygame version:
 *   - `MOON_SHADOW` is intentionally lifted off the log-strip fill
 *     (#161629) so the dim side of a crescent/gibbous moon doesn't
 *     visually merge with the bar and lose its shape. The Python
 *     game had the same hazard but used a different bar tint that
 *     read more like night sky; on the web port the dark navy bar
 *     ate the moon's shadow at the previous tint, hiding phases.
 *   - Every phase is rimmed with a faint outline (not just the new
 *     moon) so the moon's circumference is always crisp against the
 *     bar — a partial moon used to look like just a sliver of light
 *     floating in the strip.
 */

import type Phaser from "phaser";

const MOON_LIT = 0xf2ecc8;     // warm parchment (slightly lifted from the strip text colour)
const MOON_SHADOW = 0x4a4560;  // muted purple-grey — reads as "shadow" against the dark bar
const MOON_OUTLINE = 0x5c5c70; // soft grey-violet rim for crispness

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
    // Full moon: bright disc with the same crisp outline so it lines
    // up with the rim used in partial phases (no visual "growing"
    // effect when the moon rolls from waxing gibbous to full).
    g.fillStyle(MOON_LIT, 1);
    g.fillCircle(cx, cy, r);
    g.lineStyle(1, MOON_OUTLINE, 1);
    g.strokeCircle(cx, cy, r);
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

  // Final crisp rim — drawn last so it sits over both the lit disc
  // and the shadow ellipse. Without this the shadow ellipse spills
  // past the lit circle's edge on partial phases (the ellipse width
  // exceeds the radius for crescents) and the moon looks lopsided.
  g.lineStyle(1, MOON_OUTLINE, 1);
  g.strokeCircle(cx, cy, r);
}

/** Diameter (px) used for the HUD moon icon. Sized to fit comfortably
 *  inside the 32px log strip with room above and below — large enough
 *  that the player can read the phase at a glance without needing to
 *  rely on the "New Moon" / "Waxing Gibbous" text label. */
export const MOON_HUD_SIZE = 22;
