/**
 * Pulsing-glow overlay used for quest highlights.
 *
 * Mirrors the Python renderer's `_draw_pulsing_glow` (used on quest
 * givers, quest monsters, and quest items): two stacked circles that
 * sine-pulse each frame, plus an optional status badge floating above
 * the target.
 *
 * Usage:
 *   const glow = attachPulsingGlow(scene, getX, getY, { color: 0xffd470 });
 *   // ... later
 *   glow.destroy();
 *
 * `getX`/`getY` are sampled each frame so the glow tracks a sprite
 * even if it's tweened or its underlying entity is moved by some
 * other tick (e.g. wandering interior monsters).
 */

import Phaser from "phaser";

export interface PulsingGlowOptions {
  /** RGB hex for both the halo and the inner core. */
  color: number;
  /** 0..1 — Python's `intensity` parameter. Quest monsters use ~0.5,
   *  quest items + givers use 1.0 for stronger highlight. */
  intensity?: number;
  /** Phaser depth — defaults to 7 (above tile mesh, below player). */
  depth?: number;
  /** Tile size — controls the halo radius. Default 32. */
  size?: number;
}

export interface PulsingGlowHandle {
  destroy(): void;
}

/**
 * Attach a pulsing radial glow that follows a target each frame.
 * Returns a handle whose `destroy()` removes the graphics + the
 * scene-update listener, so the glow doesn't leak past its target.
 */
export function attachPulsingGlow(
  scene: Phaser.Scene,
  getX: () => number,
  getY: () => number,
  opts: PulsingGlowOptions,
): PulsingGlowHandle {
  const intensity = Math.max(0, Math.min(1, opts.intensity ?? 1));
  const depth = opts.depth ?? 7;
  const size = opts.size ?? 32;
  const color = opts.color;

  const g = scene.add.graphics();
  g.setDepth(depth);
  g.setScrollFactor(1);

  const tick = (time: number) => {
    if (!g.scene) return;  // destroyed mid-frame
    const t = time / 1000;
    const pulse = (Math.sin(t * 3.0) + 1.0) / 2.0;  // 0..1
    const x = getX();
    const y = getY();
    g.clear();

    // Outer halo — wide and soft.
    const haloR = size * (0.95 + pulse * 0.25);
    const haloA = (0.22 + pulse * 0.22) * intensity;
    g.fillStyle(color, haloA);
    g.fillCircle(x, y, haloR);

    // Inner core — brighter, tighter.
    const coreR = size * (0.55 + pulse * 0.2);
    const coreA = (0.35 + pulse * 0.35) * intensity;
    g.fillStyle(color, coreA);
    g.fillCircle(x, y, coreR);

    // Outline ring — keeps the silhouette crisp on busy backgrounds.
    const ringR = size * (0.5 + pulse * 0.1);
    const ringA = Math.min(1, (0.55 + pulse * 0.45) * intensity);
    g.lineStyle(2, color, ringA);
    g.strokeCircle(x, y, ringR);
  };
  scene.events.on(Phaser.Scenes.Events.UPDATE, tick);

  return {
    destroy(): void {
      scene.events.off(Phaser.Scenes.Events.UPDATE, tick);
      g.destroy();
    },
  };
}

// ── Color presets — matched to the Python renderer's hues ────────

/** Warm gold — quest givers and quest monsters. */
export const QUEST_GIVER_COLOR = 0xffb428;
/** Cyan — quest collectible artifacts. */
export const QUEST_ITEM_COLOR = 0x28b4ff;
/** Soft gold for quest-monster halos (Python uses 255,180,40). */
export const QUEST_MONSTER_COLOR = 0xffb428;
