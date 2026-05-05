/**
 * Turn-based combat controller.
 *
 * Pure logic — no Phaser, no DOM. The Phaser scene constructs a Combat,
 * reads its public state to draw the arena, and calls `attack()` /
 * `takeMonsterTurn()` to advance. This is what makes the engine
 * testable and portable.
 *
 * Turn flow:
 *   1. Constructor rolls initiative for every combatant, sorts desc.
 *   2. `current` returns whose turn it is.
 *   3. Active side calls `attack(targetId)`. The result contains the
 *      attack details + damage; HP is mutated in place.
 *   4. Caller advances to the next alive combatant via `endTurn()`.
 *   5. `isOver` / `winner` end the encounter when one side is wiped.
 */

import { defaultRng, type RNG } from "../rng";
import {
  rollAttack,
  rollDamage,
  rollInitiative,
} from "./engine";
import type {
  AttackResult,
  Combatant,
  InitiativeRoll,
  Side,
} from "../types";

export class Combat {
  readonly combatants: Combatant[];
  readonly initiativeOrder: InitiativeRoll[];
  /** Index into `initiativeOrder`, pointing at the active combatant. */
  private cursor = 0;
  readonly log: string[] = [];

  private rng: RNG;

  constructor(party: Combatant[], enemies: Combatant[], rng: RNG = defaultRng) {
    this.rng = rng;
    this.combatants = [...party, ...enemies];

    // Roll initiative for every combatant, sort descending. Ties are
    // broken by DEX modifier, then by stable insertion order — that
    // gives the party the edge on a true tie, matching the Python rule.
    const rolls: InitiativeRoll[] = this.combatants.map((c) => {
      const { total, raw } = rollInitiative(c.dexMod, this.rng);
      return { combatantId: c.id, total, raw };
    });
    rolls.sort((a, b) => {
      if (b.total !== a.total) return b.total - a.total;
      const ca = this.byId(a.combatantId);
      const cb = this.byId(b.combatantId);
      if (cb.dexMod !== ca.dexMod) return cb.dexMod - ca.dexMod;
      // Stable: party (added first) wins tiebreakers
      return (
        this.combatants.indexOf(ca) - this.combatants.indexOf(cb)
      );
    });
    this.initiativeOrder = rolls;
    this.advanceToAlive();
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

  get isOver(): boolean {
    return this.alive("party").length === 0 || this.alive("enemies").length === 0;
  }

  get winner(): Side | null {
    if (!this.isOver) return null;
    return this.alive("party").length > 0 ? "party" : "enemies";
  }

  // ── Actions ──────────────────────────────────────────────────────

  /**
   * Resolve an attack from the active combatant against `targetId`.
   * Mutates target HP and pushes a log line. Throws if it's not the
   * attacker's turn or target is invalid.
   */
  attack(targetId: string): AttackResult {
    const attacker = this.current;
    const target = this.byId(targetId);

    if (attacker.hp <= 0) {
      throw new Error(`Attacker ${attacker.name} is down`);
    }
    if (target.hp <= 0) {
      throw new Error(`Target ${target.name} is already down`);
    }
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
    const line = roll.hit
      ? `${attacker.name} ${roll.critical ? "crits" : "hits"} ${target.name} for ${damage} damage${killed ? " — defeated!" : "."}`
      : `${attacker.name} swings at ${target.name} and misses.`;
    this.log.push(line);

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
   * Convenience for monster turns: pick a random alive party member
   * and attack. Returns the result, or null if the encounter ended.
   */
  takeMonsterTurn(): AttackResult | null {
    if (this.isOver) return null;
    const targets = this.alive("party");
    if (targets.length === 0) return null;
    const idx = Math.floor(this.rng() * targets.length);
    return this.attack(targets[idx].id);
  }

  /** Move the turn cursor to the next alive combatant. */
  endTurn(): void {
    if (this.isOver) return;
    for (let i = 0; i < this.combatants.length; i++) {
      this.cursor = (this.cursor + 1) % this.initiativeOrder.length;
      if (this.byId(this.initiativeOrder[this.cursor].combatantId).hp > 0) {
        return;
      }
    }
  }

  /** On startup, skip past anyone who's already dead (defensive). */
  private advanceToAlive(): void {
    if (this.byId(this.initiativeOrder[this.cursor].combatantId).hp > 0) return;
    this.endTurn();
  }
}
