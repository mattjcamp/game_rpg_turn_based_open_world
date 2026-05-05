/**
 * Arena geometry for tactical combat.
 *
 * Mirrors the Python `src/states/combat.py` constants so the rules port
 * directly: an 18×21 grid where the outer ring is solid wall and the
 * interior is open floor. Future slices can add interior obstacles
 * (`arenaObstacles` in the Python version) without touching anything
 * else here.
 */

export const ARENA_COLS = 18;
export const ARENA_ROWS = 21;

export type Direction = "n" | "s" | "e" | "w";

export const DIR_DELTAS: Record<Direction, readonly [number, number]> = {
  n: [0, -1],
  s: [0, 1],
  e: [1, 0],
  w: [-1, 0],
} as const;

export const ALL_DIRECTIONS: readonly Direction[] = ["n", "s", "e", "w"];

export interface GridPos {
  col: number;
  row: number;
}

/** True if (col, row) is on the perimeter wall. */
export function isWall(col: number, row: number): boolean {
  return (
    col <= 0 ||
    col >= ARENA_COLS - 1 ||
    row <= 0 ||
    row >= ARENA_ROWS - 1
  );
}

/** True if (col, row) is inside the arena bounds at all. */
export function inBounds(col: number, row: number): boolean {
  return col >= 0 && col < ARENA_COLS && row >= 0 && row < ARENA_ROWS;
}

/** Chebyshev distance — used for "is adjacent" checks (king-move metric). */
export function chebyshev(a: GridPos, b: GridPos): number {
  return Math.max(Math.abs(a.col - b.col), Math.abs(a.row - b.row));
}

/** Manhattan distance — used by the simple monster pursuit heuristic. */
export function manhattan(a: GridPos, b: GridPos): number {
  return Math.abs(a.col - b.col) + Math.abs(a.row - b.row);
}
