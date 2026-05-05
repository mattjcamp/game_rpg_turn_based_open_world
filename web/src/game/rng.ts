/**
 * Seedable RNG (mulberry32). Returns a function with the same contract as
 * Math.random — yields a float in [0, 1).
 *
 * Used in tests so we can reproduce specific dice sequences (the Python
 * tests do this with `random.seed(...)`); the engine accepts an optional
 * RNG argument so production code keeps using Math.random.
 */
export type RNG = () => number;

export function mulberry32(seed: number): RNG {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Default RNG used when no override is supplied. */
export const defaultRng: RNG = Math.random;
