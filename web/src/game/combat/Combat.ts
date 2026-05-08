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
import type { MonsterSpell, MonsterPassive } from "../data/monsters";

/** Subset of MonsterSpell the dice helpers actually use. Keeping this
 *  narrow lets the helpers stay easy to test in isolation. */
type MonsterSpellLike = Pick<
  MonsterSpell,
  "type" | "damageDice" | "damageSides" | "damageBonus"
       | "healDice"   | "healSides"   | "healBonus"
>;

/** Pick the nearest enemy within `range` tiles (Chebyshev). Returns
 *  null when nobody qualifies — caller falls through to melee. */
function nearestInRange(
  actor: Combatant,
  candidates: Combatant[],
  range: number | undefined,
): Combatant | null {
  const r = range ?? Infinity;
  let best: Combatant | null = null;
  let bestDist = Infinity;
  for (const c of candidates) {
    const d = chebyshev(actor.position, c.position);
    if (d > r) continue;
    if (d < bestDist) { best = c; bestDist = d; }
  }
  return best;
}

/** True iff the combatant carries a passive of the given kind. */
function hasPassive(c: Combatant, kind: MonsterPassive["type"]): boolean {
  if (!c.passives) return false;
  return c.passives.some((p) => p.type === kind);
}

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

/** Events the round-end consume tick produces. The scene drains
 *  these via `popConsumeEvents()` after each `endTurn()` so it can
 *  float damage numbers / show an escape flash on the affected
 *  sprite. Without these the HP drain is invisible to the player. */
export type ConsumeEvent =
  | { targetId: string; kind: "applied"; consumerId: string }
  | { targetId: string; kind: "tick"; damage: number }
  | { targetId: string; kind: "saved" }
  | { targetId: string; kind: "released" };

/** What a monster's AI wants to do this step. */
export type MonsterIntent =
  | { kind: "attack"; targetId: string }
  | { kind: "move"; dir: Direction }
  | { kind: "spell"; spellIndex: number; targetId?: string }
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
  /** Consume-tick events accumulated since the last `popConsumeEvents`
   *  call. Drained by the scene each `endTurn()` so floating damage
   *  / escape labels animate in sync with HP changes. */
  private pendingConsumeEvents: ConsumeEvent[] = [];

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
   * Scatter party across the bottom band of the arena and enemies
   * across the top band. Each side gets a 4-row band (rows 11..14 for
   * party, rows 1..4 for enemies) with a one-column gutter against
   * the perimeter walls. Cells are shuffled with the seeded RNG and
   * the first N taken, so positions are random per-encounter but
   * reproducible in tests.
   *
   * Replaces an earlier "everyone in one row, centred" layout that
   * left party and enemies looking like two opposing chorus lines.
   */
  private layoutFormations(party: Combatant[], enemies: Combatant[]): void {
    const colMin = 2;
    const colMax = ARENA_COLS - 3;          // inclusive, leaves a wall gutter
    const partyRows = [ARENA_ROWS - 5, ARENA_ROWS - 4, ARENA_ROWS - 3, ARENA_ROWS - 2];
    const enemyRows = [1, 2, 3, 4];
    this.placeOnBand(party, colMin, colMax, partyRows);
    this.placeOnBand(enemies, colMin, colMax, enemyRows);
  }

  /** Shuffle the (col, row) cells in the given band and assign the
   *  first `combatants.length` to each combatant. Falls back to row 0
   *  / centred col stacking if (somehow) the band is smaller than the
   *  group — should never happen with the bands above. */
  private placeOnBand(
    combatants: Combatant[],
    colMin: number,
    colMax: number,
    rows: number[],
  ): void {
    const cells: GridPos[] = [];
    for (const r of rows) {
      for (let c = colMin; c <= colMax; c++) cells.push({ col: c, row: r });
    }
    // Fisher-Yates with Math.random — deliberately NOT this.rng so
    // the seeded combat RNG sequence (d20s, damage rolls, init) stays
    // independent of formation shuffling. Tests pin combat RNG with
    // mulberry32 and check positions only as bands, not exact cells,
    // so non-deterministic placement is fine.
    for (let i = cells.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [cells[i], cells[j]] = [cells[j], cells[i]];
    }
    combatants.forEach((c, i) => {
      c.position = cells[i] ?? { col: colMin, row: rows[0] };
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
      this.applyOnHitEffects(attacker, target);
    }
    const killed = target.hp === 0 && roll.hit;
    // Release anyone in the dead actor's stomach so the encounter
    // doesn't end with a Cleric forever inside a corpse. Mirrors the
    // Python game's `_release_consumed_fighter` triggered from
    // `_on_monster_killed`.
    if (killed) {
      this.releaseAllConsumedBy(target.id);
    }
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

    // Hostile to whichever side the actor isn't on. Consumed party
    // members are off the board — exclude them from the AI target
    // list so a Man Eater doesn't "attack" someone in its own belly.
    const enemySide: Side = actor.side === "enemies" ? "party" : "enemies";
    const targets = this.alive(enemySide).filter((c) => !c.consumed);
    if (targets.length === 0) return { kind: "wait" };

    // Spell-casting AI — Dragons breathe fire, Liches throw bolts,
    // Trolls heal themselves. Roll each spell's `cast_chance`; the
    // first one that passes AND has a valid target wins. Mirrors the
    // Python game's `_monster_try_spell` at `combat.py:5120+`.
    const spellIntent = this.maybePickSpell(actor, targets);
    if (spellIntent) return spellIntent;

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
        this.tickPassives();
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

  /**
   * End-of-round pass for monster `passives` array.
   *
   *   - `regen`            — heal `amount` HP, capped at maxHp.
   *   - `fire_resistance`  — passive flag; consumed by spell damage.
   *   - `poison_immunity`  — passive flag; consumed by future poison.
   *
   * Only the regen branch mutates state here; the other two are
   * declarative flags read at damage-resolution time.
   */
  private tickPassives(): void {
    for (const c of this.combatants) {
      if (c.hp <= 0) continue;
      if (!c.passives) continue;
      for (const p of c.passives) {
        if (p.type === "regen" && c.hp < c.maxHp) {
          const before = c.hp;
          c.hp = Math.min(c.maxHp, c.hp + p.amount);
          const healed = c.hp - before;
          if (healed > 0) {
            this.log.push(`${c.name} regenerates ${healed} HP.`);
          }
        }
      }
    }
  }

  /** True when the active combatant has been swallowed and their
   *  turn should auto-resolve via `runConsumedAutoTurn` rather than
   *  prompting the player or running the AI loop. */
  isCurrentConsumed(): boolean {
    return !!this.current.consumed;
  }

  /**
   * Auto-resolve the active combatant's turn while they're consumed.
   * Mirrors `_tick_consumed_fighter` at `src/states/combat.py:4771`:
   *
   *   - Roll d20 + STR mod vs the saved `saveDc`.
   *   - Pass → spit them out at a free tile near the consumer
   *     (or near their original position if the consumer's gone),
   *     clear the debuff, queue a "saved" event.
   *   - Fail → take `damagePerTurn` HP, queue a "tick" event. If
   *     they hit 0 HP they died inside; the body is "released" at
   *     the consumer's tile so it can be revived later.
   *
   * Returns the queued events so the scene can animate. Caller is
   * responsible for calling `endTurn()` afterwards — the auto-resolve
   * always consumes the whole turn regardless of outcome.
   */
  runConsumedAutoTurn(): ConsumeEvent[] {
    const actor = this.current;
    if (!actor.consumed) return [];
    const data = actor.consumed;
    const consumer = this.combatants.find((x) => x.id === data.consumerId);

    // Consumer dead? Auto-release without rolling — the body just
    // tumbles out as the beast falls.
    if (!consumer || consumer.hp <= 0) {
      this.releaseConsumed(actor, consumer ?? null);
      this.log.push(`${actor.name} tumbles free as the beast falls!`);
      return this.popConsumeEvents();
    }

    const strMod = Math.floor(((actor.strength ?? 10) - 10) / 2);
    const roll = 1 + Math.floor(this.rng() * 20);
    const total = roll + strMod;
    if (total >= data.saveDc) {
      this.releaseConsumed(actor, consumer);
      this.log.push(
        `${actor.name} fights free of ${consumer.name}! ` +
        `(STR ${roll}+${strMod}=${total} vs DC ${data.saveDc})`
      );
      return this.popConsumeEvents();
    }

    // Save failed — take a per-turn HP tick.
    const dmg = data.damagePerTurn;
    actor.hp = Math.max(0, actor.hp - dmg);
    this.log.push(
      `${actor.name} is crushed inside ${consumer.name}! (-${dmg} HP) ` +
      `(STR ${roll}+${strMod}=${total} vs DC ${data.saveDc} — Failed!)`
    );
    this.pendingConsumeEvents.push({ targetId: actor.id, kind: "tick", damage: dmg });
    if (actor.hp === 0) {
      // Died inside — clear the debuff and drop the body out so it
      // can be revived later. The "released" event tells the scene
      // to make the corpse visible again.
      this.releaseConsumed(actor, consumer);
      this.log.push(`${actor.name}'s body tumbles out, lifeless.`);
    }
    return this.popConsumeEvents();
  }

  /**
   * Place a previously-consumed combatant back on the arena at a
   * free tile near `consumer` (or their original position if the
   * consumer is gone), clear their `consumed` marker, and queue a
   * `saved` event for the scene to animate.
   */
  private releaseConsumed(actor: Combatant, consumer: Combatant | null): void {
    const data = actor.consumed!;
    const anchor = consumer && consumer.hp > 0
      ? consumer.position
      : data.originalPosition;
    const newPos = this.findFreeTileNear(anchor) ?? anchor;
    actor.position = { ...newPos };
    actor.consumed = undefined;
    this.pendingConsumeEvents.push({ targetId: actor.id, kind: "saved" });
  }

  /** Pop every consumed actor whose consumer just died back onto the
   *  arena. Called from `attack()` and `castMonsterSpell` whenever
   *  damage drops a target to 0 HP. */
  private releaseAllConsumedBy(consumerId: string): void {
    for (const c of this.combatants) {
      if (!c.consumed || c.consumed.consumerId !== consumerId) continue;
      const consumer = this.combatants.find((x) => x.id === consumerId) ?? null;
      this.releaseConsumed(c, consumer);
      this.log.push(`${c.name} tumbles free as the beast falls!`);
    }
  }

  /** Spiral search for the first walkable, unoccupied tile within 5
   *  rings of `origin`. Returns null when the arena is jam-packed —
   *  the caller falls back to dropping at the origin tile. */
  private findFreeTileNear(origin: GridPos): GridPos | null {
    for (let r = 0; r <= 5; r++) {
      for (let dc = -r; dc <= r; dc++) {
        for (let dr = -r; dr <= r; dr++) {
          if (Math.max(Math.abs(dc), Math.abs(dr)) !== r) continue;
          const c = origin.col + dc;
          const ro = origin.row + dr;
          if (!inBounds(c, ro) || isWall(c, ro)) continue;
          if (this.combatantAt(c, ro)) continue;
          return { col: c, row: ro };
        }
      }
    }
    return null;
  }

  /** Drain the queued consume-tick events so the scene can animate
   *  them. Each call empties the buffer. */
  popConsumeEvents(): ConsumeEvent[] {
    const out = this.pendingConsumeEvents;
    this.pendingConsumeEvents = [];
    return out;
  }

  /**
   * Walk the actor's `monsterSpells` table and return the first spell
   * intent whose dice roll passes `cast_chance` AND has a valid
   * target. Damage spells need an enemy in range; heal_self needs the
   * caster to be wounded; heal_ally needs a wounded same-side ally.
   * Returns null when nothing is castable this turn.
   */
  private maybePickSpell(actor: Combatant, enemies: Combatant[]): MonsterIntent | null {
    if (!actor.monsterSpells || actor.monsterSpells.length === 0) return null;
    for (let i = 0; i < actor.monsterSpells.length; i++) {
      const spell = actor.monsterSpells[i];
      const chance = spell.castChance | 0;
      if (chance <= 0) continue;
      const roll = Math.floor(this.rng() * 100) + 1;
      if (roll > chance) continue;

      // heal_self — only when wounded.
      if (spell.type === "heal_self") {
        if (actor.hp >= actor.maxHp) continue;
        return { kind: "spell", spellIndex: i };
      }
      // heal_ally — pick the lowest-HP wounded same-side ally.
      if (spell.type === "heal_ally") {
        const allies = this.alive(actor.side).filter((c) => c.id !== actor.id && c.hp < c.maxHp);
        if (allies.length === 0) continue;
        allies.sort((a, b) => a.hp - b.hp);
        const ally = allies[0];
        if (spell.range != null && chebyshev(actor.position, ally.position) > spell.range) continue;
        return { kind: "spell", spellIndex: i, targetId: ally.id };
      }
      // sleep — refuses targets above max_target_hp; closest enemy in range.
      if (spell.type === "sleep") {
        const max = spell.maxTargetHp ?? Infinity;
        const candidates = enemies.filter((e) => e.maxHp <= max);
        const target = nearestInRange(actor, candidates, spell.range);
        if (!target) continue;
        return { kind: "spell", spellIndex: i, targetId: target.id };
      }
      // Everything else (breath_fire, magic_dart, magic_arrow, fireball,
      // lightning_bolt, poison, curse) targets the nearest enemy in range.
      const target = nearestInRange(actor, enemies, spell.range);
      if (!target) continue;
      return { kind: "spell", spellIndex: i, targetId: target.id };
    }
    return null;
  }

  /**
   * Resolve a spell from the active actor's `monsterSpells` table.
   * Mutates HP / status, appends a log line, and returns a brief
   * outcome the scene can animate. Used by the scene's monster-turn
   * loop after `decideMonsterIntent` returns a `kind: "spell"` intent.
   */
  castMonsterSpell(spellIndex: number, targetId?: string): {
    spellName: string;
    targetId: string;
    damage: number;
    heal: number;
    killed: boolean;
  } {
    const actor = this.current;
    const spell = actor.monsterSpells?.[spellIndex];
    if (!spell) {
      throw new Error(`No monster spell at index ${spellIndex} for ${actor.name}`);
    }
    let damage = 0;
    let heal = 0;
    let target: Combatant | null = null;

    if (spell.type === "heal_self") {
      heal = this.rollHealAmount(spell, actor);
      const before = actor.hp;
      actor.hp = Math.min(actor.maxHp, actor.hp + heal);
      heal = actor.hp - before;
      this.log.push(`${actor.name} casts ${spell.name} and recovers ${heal} HP.`);
      target = actor;
    } else if (spell.type === "heal_ally") {
      target = (targetId && this.byIdMaybe(targetId)) || null;
      if (!target) {
        this.log.push(`${actor.name} fizzles ${spell.name} — no target.`);
      } else {
        const amt = this.rollHealAmount(spell, target);
        const before = target.hp;
        target.hp = Math.min(target.maxHp, target.hp + amt);
        heal = target.hp - before;
        this.log.push(
          `${actor.name} casts ${spell.name} on ${target.name} (+${heal} HP).`
        );
      }
    } else {
      // Damage / debuff spells.
      target = (targetId && this.byIdMaybe(targetId)) || null;
      if (!target) {
        this.log.push(`${actor.name} fizzles ${spell.name} — no target.`);
      } else {
        damage = this.rollMonsterSpellDamage(spell, target);
        if (damage > 0) target.hp = Math.max(0, target.hp - damage);
        const dealtMsg = damage > 0
          ? `${target.name} takes ${damage} damage`
          : `${target.name} resists`;
        this.log.push(`${actor.name} casts ${spell.name}! ${dealtMsg}.`);
        if (target.hp === 0) {
          this.releaseAllConsumedBy(target.id);
        }
        // Sleep / curse currently log only — the duration ticker for
        // monster-cast statuses is a follow-up.
      }
    }
    const tid = target?.id ?? actor.id;
    return {
      spellName: spell.name,
      targetId: tid,
      damage,
      heal,
      killed: target ? target.hp === 0 : false,
    };
  }

  /** Sum dice + bonus for a damage spell, halving fire-typed damage
   *  when the target has a `fire_resistance` passive. */
  private rollMonsterSpellDamage(spell: MonsterSpellLike, target: Combatant): number {
    const dice = spell.damageDice ?? 0;
    const sides = spell.damageSides ?? 0;
    const bonus = spell.damageBonus ?? 0;
    if (dice <= 0 || sides <= 0) {
      // Pure-status spell (sleep / curse) with no damage payload.
      return 0;
    }
    let total = bonus;
    for (let i = 0; i < dice; i++) {
      total += Math.floor(this.rng() * sides) + 1;
    }
    if (spell.type === "breath_fire" || spell.type === "fireball") {
      if (hasPassive(target, "fire_resistance")) {
        const halved = Math.max(1, Math.floor(total / 2));
        this.log.push(`${target.name}'s fire resistance halves ${total} → ${halved}.`);
        return halved;
      }
    }
    return Math.max(1, total);
  }

  private rollHealAmount(spell: MonsterSpellLike, _target: Combatant): number {
    const dice = spell.healDice ?? 1;
    const sides = spell.healSides ?? 6;
    const bonus = spell.healBonus ?? 0;
    let total = bonus;
    for (let i = 0; i < dice; i++) {
      total += Math.floor(this.rng() * sides) + 1;
    }
    return Math.max(1, total);
  }

  private byIdMaybe(id: string): Combatant | null {
    return this.combatants.find((c) => c.id === id) ?? null;
  }

  /**
   * Roll each `onHitEffects` entry attached to the attacker against
   * the target after a successful melee hit. Currently handles:
   *
   *   - `drain`    — heal the attacker by `amount` (life-leech)
   *   - `consume`  — apply the per-turn damage debuff that ticks
   *                  in `tickConsumeDebuffs` until the victim saves
   *
   * Each effect rolls independently against its `chance` (0-100).
   */
  private applyOnHitEffects(attacker: Combatant, target: Combatant): void {
    if (!attacker.onHitEffects) return;
    for (const eff of attacker.onHitEffects) {
      const roll = Math.floor(this.rng() * 100) + 1;
      if (roll > eff.chance) continue;
      if (eff.type === "drain") {
        const before = attacker.hp;
        attacker.hp = Math.min(attacker.maxHp, attacker.hp + eff.amount);
        const healed = attacker.hp - before;
        if (healed > 0) {
          this.log.push(`${attacker.name} drains ${healed} HP from ${target.name}.`);
        }
      } else if (eff.type === "consume") {
        // STR save vs the consume DC — pass twists free, fail is
        // swallowed whole. Mirrors `_apply_consume_effect` in
        // `src/states/combat.py:4714`.
        if (target.consumed) continue; // already inside something
        const strMod = Math.floor(((target.strength ?? 10) - 10) / 2);
        const roll = 1 + Math.floor(this.rng() * 20);
        const total = roll + strMod;
        if (total >= eff.saveDc) {
          this.log.push(
            `${target.name} twists free of ${attacker.name}'s jaws! ` +
            `(STR ${roll}+${strMod}=${total} vs DC ${eff.saveDc})`
          );
          continue;
        }
        // Save failed — swallow whole. Stash the original position so
        // we can release them near it later, then move off-board so
        // collision / targeting helpers don't see them.
        target.consumed = {
          damagePerTurn: eff.damagePerTurn,
          saveDc: eff.saveDc,
          consumerId: attacker.id,
          originalPosition: { ...target.position },
        };
        target.position = { col: -1, row: -1 };
        this.log.push(
          `${attacker.name} swallows ${target.name} whole! ` +
          `(STR ${roll}+${strMod}=${total} vs DC ${eff.saveDc} — Failed!)`
        );
        this.pendingConsumeEvents.push({
          targetId: target.id, kind: "applied", consumerId: attacker.id,
        });
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
