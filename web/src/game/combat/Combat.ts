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
import {
  sumBuff,
  tickBuffs,
  describeExpire,
  type Buff,
  type BuffKind,
} from "./Buffs";
import type {
  AttackResult,
  Combatant,
  InitiativeRoll,
  Side,
} from "../types";

/** True when this combatant's turns are run by the monster-AI loop. */
export function isAiControlled(c: Combatant): boolean {
  // Honour an explicit flag first (summons set it true on the party
  // side); otherwise default to "enemies are AI, party are player".
  if (typeof c.aiControlled === "boolean") return c.aiControlled;
  return c.side === "enemies";
}

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
  /**
   * Numerical buffs / debuffs keyed by combatant id. Mirrors the
   * Python game's bless_buffs / curse_buffs / range_buffs dicts
   * unified into one structure. See `./Buffs.ts` for kinds.
   */
  private buffs = new Map<string, Buff[]>();
  /**
   * Per-combatant summon timer (in rounds). Animate Dead and similar
   * spells push an entry here; tickSummons() decrements at end of
   * round and crumbles the summon to dust when it expires.
   */
  private summons = new Map<string, number>();
  /** Counts cursor advances; we tick buffs once per full round
   *  (equal to combatants.length advances). */
  private turnsAdvanced = 0;

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

    // Opening banner — mirrors the Python game's "Party vs N enemies!"
    // intro lines so the bottom log opens with context.
    const enemyNames = enemies.map((e) => e.name).join(", ");
    this.log.push(`--- Party vs ${enemies.length} enemies! ---`);
    if (enemyNames) this.log.push(`(${enemyNames})`);
    this.log.push(`${party.length} party members engage!`);
    this.log.push(`-- ${this.current.name}'s turn --`);
  }

  /**
   * Place party on the bottom of the arena, enemies at the top —
   * matches the Python game's combat layout (the U3-style "your
   * heroes line up at the foot of the screen, the foe stands at the
   * top"). Centred horizontally so a small or large party still
   * spans the middle of the row.
   */
  private layoutFormations(party: Combatant[], enemies: Combatant[]): void {
    const partyRow = ARENA_ROWS - 3;        // 2nd from bottom
    const enemyRow = 2;                     // 2nd from top
    const midCol = Math.floor(ARENA_COLS / 2);
    const startCol = (n: number): number =>
      midCol - Math.floor(n / 2);
    party.forEach((c, i) => {
      c.position = { col: startCol(party.length) + i, row: partyRow };
    });
    enemies.forEach((c, i) => {
      c.position = { col: startCol(enemies.length) + i, row: enemyRow };
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

  // ── Mid-fight roster changes ─────────────────────────────────────
  //
  // The constructor seeds the roster from `(party, enemies)`; spells
  // like Animate Dead need to bring new actors in mid-encounter. These
  // helpers keep `combatants` and `initiativeOrder` in sync so the
  // scene's existing turn loop just picks the new entry up.

  /**
   * Add a combatant mid-fight. Rolls initiative for them, splices the
   * roll into the existing order so they get a turn this round (after
   * the current actor), and stamps their position on the grid.
   *
   * If `summonTurns` is provided, the combatant is tracked as a summon
   * — at the end of each full round its timer ticks down, and when it
   * hits zero the combatant crumbles to dust (HP = 0).
   */
  addCombatant(
    c: Combatant,
    position: { col: number; row: number },
    summonTurns?: number,
  ): void {
    c.position = { ...position };
    this.combatants.push(c);
    const { total, raw } = rollInitiative(c.dexMod, this.rng);
    // Insert the roll just after the current cursor so the new actor
    // takes their turn before the round wraps. Splicing here also
    // keeps `initiativeOrder.length === combatants.length`, which the
    // round-tick math depends on.
    this.initiativeOrder.splice(this.cursor + 1, 0, {
      combatantId: c.id, total, raw,
    });
    if (typeof summonTurns === "number" && summonTurns > 0) {
      this.summons.set(c.id, summonTurns);
    }
  }

  // ── Buffs / debuffs ──────────────────────────────────────────────

  /** Add a numerical buff or debuff to a combatant. */
  addBuff(combatantId: string, buff: Buff): void {
    const list = this.buffs.get(combatantId) ?? [];
    list.push(buff);
    this.buffs.set(combatantId, list);
  }

  /** Sum every active buff of `kind` on this combatant — handy for
   *  scenes wanting to display "+2 ATK" badges or log breakdowns. */
  sumBuff(combatantId: string, kind: BuffKind): number {
    return sumBuff(this.buffs.get(combatantId), kind);
  }

  /**
   * True if this combatant has any active buff with the given source
   * tag (case-insensitive). Used by the scene to drive source-keyed
   * visuals — e.g. holding the caster at low alpha while their
   * "Invisibility" buff is in effect.
   */
  hasBuffFromSource(combatantId: string, source: string): boolean {
    const list = this.buffs.get(combatantId);
    if (!list) return false;
    const tag = source.toLowerCase();
    return list.some((b) => b.source.toLowerCase() === tag);
  }

  /** Hit-roll bonus = base attackBonus + active attack_bonus buffs
   *  − active attack_penalty buffs. */
  effectiveAttackBonus(c: Combatant): number {
    const list = this.buffs.get(c.id);
    return c.attackBonus + sumBuff(list, "attack_bonus")
                          - sumBuff(list, "attack_penalty");
  }

  /** Defensive AC = base ac + ac_bonus − ac_penalty. */
  effectiveAc(c: Combatant): number {
    const list = this.buffs.get(c.id);
    return c.ac + sumBuff(list, "ac_bonus") - sumBuff(list, "ac_penalty");
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

    // Resolve hit + damage using *effective* values so buffs and
    // debuffs (Bless +ATK, Curse -ATK / -AC, Shield +AC) flow into
    // the math automatically.
    const effAtk = this.effectiveAttackBonus(attacker);
    const effAc = this.effectiveAc(target);
    const roll = rollAttack(effAtk, effAc, this.rng);
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
    // Detailed log line — mirrors the Python game's "(d20:N+M=T vs ACX)"
    // format so the player can see the math behind each swing. The
    // bonus shown is the effective one so a Blessed attacker visibly
    // adds the +2.
    const bonusStr = effAtk >= 0 ? `+${effAtk}` : `${effAtk}`;
    const dice = `d20:${roll.roll}${bonusStr}=${roll.total} vs AC${effAc}`;
    this.log.push(
      roll.hit
        ? `${attacker.name} ${roll.critical ? "crits" : "hits"} ${target.name} (${dice}) — ${damage} dmg${killed ? ", defeated!" : "."}`
        : `${attacker.name} swings at ${target.name} (${dice}) — miss.`
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
    // Generalised: any AI-controlled combatant runs this loop. Enemies
    // are AI-driven by default; summoned allies (Animate Dead) live on
    // the party side but flip aiControlled so they fight on their own.
    if (!isAiControlled(actor)) return { kind: "wait" };
    if (this.movePoints <= 0) return { kind: "wait" };

    // Hostile to whichever side the actor isn't on.
    const enemySide: Side = actor.side === "enemies" ? "party" : "enemies";
    const targets = this.alive(enemySide);
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
      this.turnsAdvanced += 1;
      // End of a round — every combatant has had a chance to act.
      // Tick all buff durations down once and log expirations.
      if (this.turnsAdvanced % this.combatants.length === 0) {
        this.tickAllBuffs();
        this.tickSummons();
      }
      if (this.byId(this.initiativeOrder[this.cursor].combatantId).hp > 0) {
        this.refillMovePoints();
        this.log.push(`-- ${this.current.name}'s turn --`);
        return;
      }
    }
  }

  /** Round-end tick. Decrements every active buff and logs expirations. */
  private tickAllBuffs(): void {
    for (const [id, list] of this.buffs) {
      const expired = tickBuffs(list);
      if (list.length === 0) this.buffs.delete(id);
      for (const b of expired) {
        const c = this.combatants.find((x) => x.id === id);
        if (!c || c.hp <= 0) continue;
        this.log.push(describeExpire(c.name, b.source));
      }
    }
  }

  /**
   * Round-end tick for active summons. Decrements each timer and, when
   * one hits zero, sets the summon's HP to zero with a flavour log
   * line ("X crumbles to dust!"). Mirrors the Python summon_buffs
   * expiration in `_tick_summon_buffs`.
   */
  private tickSummons(): void {
    for (const [id, turnsLeft] of this.summons) {
      const next = turnsLeft - 1;
      if (next <= 0) {
        this.summons.delete(id);
        const c = this.combatants.find((x) => x.id === id);
        if (c && c.hp > 0) {
          c.hp = 0;
          this.log.push(`${c.name} crumbles to dust!`);
        }
      } else {
        this.summons.set(id, next);
      }
    }
  }

  private advanceToAlive(): void {
    if (this.byId(this.initiativeOrder[this.cursor].combatantId).hp > 0) return;
    this.endTurn();
  }

  private refillMovePoints(): void {
    // baseMoveRange + active range_bonus buffs (Long Shanks). Mirrors
    // the Python game's range_buffs entry being added to the per-turn
    // movement allowance.
    const bonus = sumBuff(this.buffs.get(this.current.id), "range_bonus");
    this.movePoints = this.current.baseMoveRange + bonus;
  }
}
