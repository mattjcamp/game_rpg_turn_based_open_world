/**
 * Turn-based tactical combat controller.
 *
 * Pure logic — no Phaser, no DOM. The Phaser scene constructs a Combat,
 * reads its public state to draw the arena, and calls `tryMove()`,
 * `attack()` and `decideMonsterIntent()` to advance.
 *
 * Turn flow:
 *   1. Constructor lays out party (right side) and enemies (left side)
 *      on the arena grid, then rolls initiative.
 *   2. `current` returns whose turn it is. `movePoints` reflects how
 *      many tiles the current actor has left to spend this turn.
 *   3. Active side calls `tryMove(dir)`. Three outcomes:
 *        - moved: position updated, movePoints decremented
 *        - bumped: walking into an adjacent enemy attacks them; this
 *          uses ALL remaining move points (turn ends)
 *        - blocked: wall / ally / out-of-bounds; nothing happens
 *   4. `endTurn()` advances the cursor to the next alive combatant
 *      and refills their movePoints.
 *   5. `isOver` / `winner` end the encounter when one side is wiped.
 *
 * For monster turns the scene calls `decideMonsterIntent()` repeatedly
 * until it returns 'wait' or the turn ends. The intent describes ONE
 * step (move or attack) so the scene can animate between steps.
 */

import { defaultRng, type RNG } from "../rng";
import {
  ARENA_COLS,
  ARENA_ROWS,
  ALL_DIRECTIONS,
  DIR_DELTAS,
  chebyshev,
  inBounds,
  isWall,
  type Direction,
  type GridPos,
} from "./Arena";
import { rollAttack, rollDamage, rollInitiative } from "./engine";
import type {
  AttackResult,
  Combatant,
  InitiativeRoll,
  Side,
} from "../types";

export type MoveResult =
  | { kind: "moved"; from: GridPos; to: GridPos; pointsLeft: number }
  | { kind: "attacked"; result: AttackResult }
  | { kind: "blocked"; reason: "wall" | "ally" | "no-points" | "out-of-turn" };

/** What a monster's AI wants to do this step. */
export type MonsterIntent =
  | { kind: "attack"; targetId: string }
  | { kind: "move"; dir: Direction }
  | { kind: "wait" };

export class Combat {
  readonly combatants: Combatant[];
  readonly initiativeOrder: InitiativeRoll[];
  private cursor = 0;
  /** Tiles the current actor has left to spend this turn. */
  movePoints = 0;
  readonly log: string[] = [];

  private rng: RNG;

  constructor(party: Combatant[], enemies: Combatant[], rng: RNG = defaultRng) {
    this.rng = rng;
    this.combatants = [...party, ...enemies];
    this.layoutFormations(party, enemies);

    const rolls: InitiativeRoll[] = this.combatants.map((c) => {
      const { total, raw } = rollInitiative(c.dexMod, this.rng);
      return { combatantId: c.id, total, raw };
    });
    rolls.sort((a, b) => {
      if (b.total !== a.total) return b.total - a.total;
      const ca = this.byId(a.combatantId);
      const cb = this.byId(b.combatantId);
      if (cb.dexMod !== ca.dexMod) return cb.dexMod - ca.dexMod;
      return this.combatants.indexOf(ca) - this.combatants.indexOf(cb);
    });
    this.initiativeOrder = rolls;
    this.advanceToAlive();
    this.refillMovePoints();
  }

  /**
   * Place party on the right edge of the arena, enemies on the left.
   * Stacked vertically around the arena's middle row. The exact layout
   * doesn't matter much — just keeps them apart so the player has
   * tactical decisions to make.
   */
  private layoutFormations(party: Combatant[], enemies: Combatant[]): void {
    const partyCol = ARENA_COLS - 3; // col 15
    const enemyCol = 2;
    const midRow = Math.floor(ARENA_ROWS / 2); // row 10
    party.forEach((c, i) => {
      c.position = { col: partyCol, row: midRow - Math.floor(party.length / 2) + i };
    });
    enemies.forEach((c, i) => {
      c.position = { col: enemyCol, row: midRow - Math.floor(enemies.length / 2) + i };
    });
  }

  // ── Queries ──────────────────────────────────────────────────────

  byId(id: string): Combatant {
    const c = this.combatants.find((x) => x.id === id);
    if (!c) throw new Error(`Unknown combatant id: ${id}`);
    return c;
  }

  get current(): Combatant {
    return this.byId(this.initiativeOrder[this.cursor].combatantId);
  }

  alive(side: Side): Combatant[] {
    return this.combatants.filter((c) => c.side === side && c.hp > 0);
  }

  combatantAt(col: number, row: number): Combatant | null {
    for (const c of this.combatants) {
      if (c.hp <= 0) continue;
      if (c.position.col === col && c.position.row === row) return c;
    }
    return null;
  }

  get isOver(): boolean {
    return this.alive("party").length === 0 || this.alive("enemies").length === 0;
  }

  get winner(): Side | null {
    if (!this.isOver) return null;
    return this.alive("party").length > 0 ? "party" : "enemies";
  }

  // ── Movement & bump-attack ───────────────────────────────────────

  /**
   * Attempt to move the current actor one step in `dir`. Returns a
   * structured outcome the UI can react to. Mutates state on success.
   *
   * Bump-attack rule (from src/states/combat.py): walking into an
   * adjacent enemy resolves a melee attack and consumes ALL remaining
   * move points — i.e. ends the turn after the attack resolves.
   */
  tryMove(dir: Direction): MoveResult {
    if (this.isOver) return { kind: "blocked", reason: "out-of-turn" };
    if (this.movePoints <= 0) {
      return { kind: "blocked", reason: "no-points" };
    }
    const actor = this.current;
    const [dc, dr] = DIR_DELTAS[dir];
    const nc = actor.position.col + dc;
    const nr = actor.position.row + dr;

    if (!inBounds(nc, nr) || isWall(nc, nr)) {
      return { kind: "blocked", reason: "wall" };
    }

    const occupant = this.combatantAt(nc, nr);
    if (occupant) {
      if (occupant.side === actor.side) {
        return { kind: "blocked", reason: "ally" };
      }
      // Enemy in the way → bump attack. Consumes all remaining moves.
      const result = this.attack(occupant.id);
      this.movePoints = 0;
      return { kind: "attacked", result };
    }

    const from = { ...actor.position };
    actor.position = { col: nc, row: nr };
    this.movePoints -= 1;
    return { kind: "moved", from, to: { col: nc, row: nr }, pointsLeft: this.movePoints };
  }

  /**
   * Resolve an attack from the current actor against `targetId`.
   * Used by the bump-attack path and by monster AI directly.
   */
  attack(targetId: string): AttackResult {
    const attacker = this.current;
    const target = this.byId(targetId);

    if (attacker.hp <= 0) throw new Error(`Attacker ${attacker.name} is down`);
    if (target.hp <= 0) throw new Error(`Target ${target.name} is already down`);
    if (target.side === attacker.side) {
      throw new Error(`Cannot attack ally ${target.name}`);
    }

    const roll = rollAttack(attacker.attackBonus, target.ac, this.rng);
    let damage = 0;
    if (roll.hit) {
      damage = rollDamage(
        attacker.damage.dice,
        attacker.damage.sides,
        attacker.damage.bonus,
        roll.critical,
        this.rng
      );
      target.hp = Math.max(0, target.hp - damage);
    }
    const killed = target.hp === 0 && roll.hit;
    this.log.push(
      roll.hit
        ? `${attacker.name} ${roll.critical ? "crits" : "hits"} ${target.name} for ${damage}${killed ? " — defeated!" : "."}`
        : `${attacker.name} swings at ${target.name} and misses.`
    );
    return {
      attackerId: attacker.id,
      targetId: target.id,
      hit: roll.hit,
      roll: roll.roll,
      total: roll.total,
      critical: roll.critical,
      damage,
      killed,
    };
  }

  /**
   * Decide what the active monster wants to do this STEP. Called by
   * the scene one-at-a-time so movement can be animated between tiles.
   *
   * Heuristic:
   *   - If adjacent (Chebyshev = 1) to any alive party member, attack
   *     the lowest-HP one (focus fire).
   *   - Otherwise step toward the nearest party member, picking the
   *     cardinal direction that reduces Manhattan distance most. Ties
   *     are broken by RNG so monsters don't all funnel identically.
   *   - If no useful move exists, return 'wait' so the scene ends the
   *     turn.
   */
  decideMonsterIntent(): MonsterIntent {
    const actor = this.current;
    if (actor.side !== "enemies") return { kind: "wait" };
    if (this.movePoints <= 0) return { kind: "wait" };

    const targets = this.alive("party");
    if (targets.length === 0) return { kind: "wait" };

    // Adjacent? Attack the weakest.
    const adjacent = targets.filter(
      (t) => chebyshev(actor.position, t.position) === 1
    );
    if (adjacent.length > 0) {
      adjacent.sort((a, b) => a.hp - b.hp);
      return { kind: "attack", targetId: adjacent[0].id };
    }

    // Otherwise pursue the nearest target.
    const nearest = [...targets].sort(
      (a, b) =>
        chebyshev(actor.position, a.position) -
        chebyshev(actor.position, b.position)
    )[0];

    let bestDelta = Infinity;
    const candidates: Direction[] = [];
    for (const dir of ALL_DIRECTIONS) {
      const [dc, dr] = DIR_DELTAS[dir];
      const nc = actor.position.col + dc;
      const nr = actor.position.row + dr;
      if (!inBounds(nc, nr) || isWall(nc, nr)) continue;
      const occupant = this.combatantAt(nc, nr);
      // Allow stepping into a tile occupied by the target's party so
      // the bump-attack path can resolve — but only if it's an enemy
      // of the monster. Allies of the monster (other monsters) block.
      if (occupant && occupant.side === actor.side) continue;
      const candidatePos = { col: nc, row: nr };
      const delta =
        chebyshev(candidatePos, nearest.position) -
        chebyshev(actor.position, nearest.position);
      if (delta < bestDelta) {
        bestDelta = delta;
        candidates.length = 0;
        candidates.push(dir);
      } else if (delta === bestDelta) {
        candidates.push(dir);
      }
    }

    if (candidates.length === 0 || bestDelta >= 0) {
      // No direction makes us closer. Sit still rather than wander.
      return { kind: "wait" };
    }
    const idx = Math.floor(this.rng() * candidates.length);
    return { kind: "move", dir: candidates[idx] };
  }

  // ── Turn control ─────────────────────────────────────────────────

  /** Move the turn cursor to the next alive combatant and refill points. */
  endTurn(): void {
    if (this.isOver) return;
    for (let i = 0; i < this.combatants.length; i++) {
      this.cursor = (this.cursor + 1) % this.initiativeOrder.length;
      if (this.byId(this.initiativeOrder[this.cursor].combatantId).hp > 0) {
        this.refillMovePoints();
        return;
      }
    }
  }

  private advanceToAlive(): void {
    if (this.byId(this.initiativeOrder[this.cursor].combatantId).hp > 0) return;
    this.endTurn();
  }

  private refillMovePoints(): void {
    this.movePoints = this.current.baseMoveRange;
  }
}
