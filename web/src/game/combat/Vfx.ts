/**
 * Combat visual effects, painted on top of the existing CombatScene.
 *
 * Each helper takes a Phaser scene plus screen-space coordinates and
 * spawns short-lived game objects that the engine cleans up via
 * `onComplete: destroy`. Nothing in here mutates combat state — the
 * scene owns dice rolls and HP; we only draw the eye candy.
 *
 * Conventions:
 *   - Coordinates are arena-relative *screen* pixels (the scene already
 *     converts grid (col, row) → centre x/y via tileX / tileY).
 *   - Colours are 0xRRGGBB integers so they pass straight to Phaser.
 *   - Every effect resolves on its own; awaiting them is optional.
 */

import Phaser from "phaser";

const TILE = 32;

const COLOURS: Record<string, number> = {
  fire:      0xff7a3a,
  ember:     0xffce5c,
  lightning: 0xa9d4ff,
  arcane:    0xc28bff,
  heal:      0x88ff9c,
  buff:      0xffe48a,
  curse:     0x9d4cff,
  shield:    0x9bcfff,
  miss:      0xbdb38a,
  blood:     0xff4f4f,
  white:     0xffffff,
};

type Pt = { x: number; y: number };

/** Single bright flash on a target body — colour-coded by intent. */
export function flashTarget(
  scene: Phaser.Scene,
  target: Phaser.GameObjects.GameObject & { x: number; y: number },
  color = COLOURS.blood,
): void {
  const halo = scene.add.circle(
    (target as unknown as { x: number }).x,
    (target as unknown as { y: number }).y,
    18, color, 0.6,
  ).setDepth(50);
  scene.tweens.add({
    targets: halo,
    radius: 26, alpha: 0,
    duration: 220,
    onComplete: () => halo.destroy(),
  });
}

/** Brief tint flicker on the caster — telegraphs that they're casting. */
export function castGlow(
  scene: Phaser.Scene,
  caster: Phaser.GameObjects.GameObject & { x: number; y: number },
  color = COLOURS.arcane,
): void {
  const aura = scene.add.circle(
    (caster as unknown as { x: number }).x,
    (caster as unknown as { y: number }).y,
    20, color, 0.45,
  ).setDepth(40);
  scene.tweens.add({
    targets: aura,
    radius: 8, alpha: 0,
    duration: 320,
    onComplete: () => aura.destroy(),
  });
}

/**
 * Aimed projectile travelling from `from` → `to` on a slight arc. Used
 * by Throw, Range, and single-target damage spells. Rotates the dot to
 * face direction of travel for visual punch.
 */
export function projectileLine(
  scene: Phaser.Scene,
  from: Pt, to: Pt,
  color = COLOURS.arcane,
  durationMs = 220,
): Promise<void> {
  return new Promise((resolve) => {
    const dot = scene.add.rectangle(from.x, from.y, 8, 4, color, 1)
      .setDepth(60);
    const angle = Math.atan2(to.y - from.y, to.x - from.x);
    dot.rotation = angle;
    // Arc midpoint: slight upward bow.
    const dist = Phaser.Math.Distance.Between(from.x, from.y, to.x, to.y);
    const apex = Math.min(28, dist * 0.18);
    const midX = (from.x + to.x) / 2;
    const midY = (from.y + to.y) / 2 - apex;
    // Two-step tween: from → mid → to. Phaser doesn't ship a native
    // quadratic-bezier tween, so we just chain two.
    scene.tweens.add({
      targets: dot, x: midX, y: midY,
      duration: durationMs / 2,
      onComplete: () => {
        scene.tweens.add({
          targets: dot, x: to.x, y: to.y,
          duration: durationMs / 2,
          onComplete: () => { dot.destroy(); resolve(); },
        });
      },
    });
  });
}

/**
 * Lightning bolt: a jagged poly-line drawn instantly, then faded out.
 * `segments` randomises the kink count for non-determinism between
 * casts.
 */
export function lightningZigzag(
  scene: Phaser.Scene,
  from: Pt, to: Pt,
  segments = 6,
): Promise<void> {
  return new Promise((resolve) => {
    const g = scene.add.graphics().setDepth(70);
    g.lineStyle(3, COLOURS.lightning, 1);
    g.beginPath();
    g.moveTo(from.x, from.y);
    for (let i = 1; i < segments; i++) {
      const t = i / segments;
      const x = Phaser.Math.Linear(from.x, to.x, t);
      const y = Phaser.Math.Linear(from.y, to.y, t);
      const jx = (Math.random() - 0.5) * 14;
      const jy = (Math.random() - 0.5) * 14;
      g.lineTo(x + jx, y + jy);
    }
    g.lineTo(to.x, to.y);
    g.strokePath();
    scene.tweens.add({
      targets: g, alpha: 0,
      duration: 280,
      onComplete: () => { g.destroy(); resolve(); },
    });
  });
}

/**
 * Radial burst — used for Fireball / Turn Undead. Paints an expanding
 * filled circle plus a ring of dots that scatter outward.
 */
export function radialBurst(
  scene: Phaser.Scene,
  at: Pt,
  color = COLOURS.fire,
  emberColor = COLOURS.ember,
  radius = 56,
): Promise<void> {
  return new Promise((resolve) => {
    const orb = scene.add.circle(at.x, at.y, 8, color, 0.85).setDepth(55);
    scene.tweens.add({
      targets: orb,
      radius, alpha: 0,
      duration: 380,
      onComplete: () => orb.destroy(),
    });
    const ring = scene.add.circle(at.x, at.y, 4, emberColor, 0).setDepth(56);
    ring.setStrokeStyle(2, emberColor, 1);
    scene.tweens.add({
      targets: ring,
      radius: radius + 8, alpha: 0,
      duration: 480,
      onComplete: () => ring.destroy(),
    });
    // Embers — small dots flying outward.
    const sparks = 10;
    for (let i = 0; i < sparks; i++) {
      const a = (i / sparks) * Math.PI * 2;
      const sx = at.x, sy = at.y;
      const tx = sx + Math.cos(a) * (radius + 6);
      const ty = sy + Math.sin(a) * (radius + 6);
      const dot = scene.add.rectangle(sx, sy, 4, 4, emberColor, 1).setDepth(57);
      scene.tweens.add({
        targets: dot, x: tx, y: ty, alpha: 0,
        duration: 460,
        onComplete: () => dot.destroy(),
      });
    }
    scene.time.delayedCall(480, () => resolve());
  });
}

/**
 * Rising green sparkles for heal-type spells. Spawns a handful of dots
 * just below the target sprite that float up while fading.
 */
export function healingSparkles(
  scene: Phaser.Scene,
  at: Pt,
  count = 8,
): Promise<void> {
  return new Promise((resolve) => {
    const colors = [COLOURS.heal, 0xb4f5be, 0xeaffe0];
    for (let i = 0; i < count; i++) {
      const ox = (Math.random() - 0.5) * TILE;
      const sx = at.x + ox;
      const sy = at.y + TILE / 2;
      const dot = scene.add.circle(
        sx, sy, 2.5, colors[i % colors.length], 1,
      ).setDepth(55);
      scene.tweens.add({
        targets: dot,
        y: sy - TILE - 8 - Math.random() * 8,
        alpha: 0,
        duration: 700 + Math.random() * 300,
        delay: Math.random() * 120,
        onComplete: () => dot.destroy(),
      });
    }
    scene.time.delayedCall(900, () => resolve());
  });
}

/**
 * Buff aura — slow expanding ring around an ally. Used for Bless,
 * Shield, Long Shanks, Invisibility (slightly different colours per
 * source; caller picks).
 */
export function glowAura(
  scene: Phaser.Scene,
  at: Pt,
  color = COLOURS.buff,
): Promise<void> {
  return new Promise((resolve) => {
    const ring = scene.add.circle(at.x, at.y, 10, color, 0).setDepth(45);
    ring.setStrokeStyle(2, color, 0.9);
    scene.tweens.add({
      targets: ring,
      radius: 28, alpha: 0,
      duration: 520,
      onComplete: () => { ring.destroy(); resolve(); },
    });
  });
}

/** Quick screen shake — used for crits, explosions, big damage. */
export function screenShake(
  scene: Phaser.Scene,
  intensity = 0.005,
  durationMs = 180,
): void {
  if (!scene.cameras?.main) return;
  scene.cameras.main.shake(durationMs, intensity);
}

/** Floating "miss" or "X" marker over a target. Doesn't block. */
export function floatingX(
  scene: Phaser.Scene,
  at: Pt,
): void {
  const t = scene.add.text(at.x, at.y - 4, "✕", {
    fontFamily: "Georgia, serif",
    fontSize: "20px",
    color: "#bdb38a",
    stroke: "#1a1a2e",
    strokeThickness: 3,
  }).setOrigin(0.5).setDepth(80);
  scene.tweens.add({
    targets: t, y: t.y - 16, alpha: 0,
    duration: 480,
    onComplete: () => t.destroy(),
  });
}

export const VFX_COLOURS = COLOURS;
