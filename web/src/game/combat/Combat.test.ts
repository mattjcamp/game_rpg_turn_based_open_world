/**
 * Combat controller tests.
 *
 * Two layers:
 *   - "JRPG layer" — initiative ordering, attack flow, end conditions,
 *     turn advancement (from the original first slice).
 *   - "Tactical layer" — grid placement, movement, blocking rules,
 *     bump-attacks, monster AI (added with the tactical port).
 *
 * Loosely modelled on tests/test_combat.py from the Python project.
 */

import { describe, it, expect } from "vitest";
import { Combat, isAiControlled } from "./Combat";
import { mulberry32 } from "../rng";
import { ARENA_COLS, ARENA_ROWS } from "./Arena";
import type { Combatant } from "../types";

function make(
  id: string,
  side: "party" | "enemies",
  overrides: Partial<Combatant> = {}
): Combatant {
  // Cast away the literal-type narrowing from the `id` argument so
  // tests comparing `c.current.id !== "..."` against another literal
  // don't trip TS's "no overlap" diagnostic. At runtime the id is
  // just a string.
  const wideId: string = id;
  return {
    id: wideId,
    name: wideId,
    side,
    maxHp: 20,
    hp: 20,
    ac: 12,
    attackBonus: 4,
    damage: { dice: 1, sides: 6, bonus: 2 },
    dexMod: 0,
    color: [200, 200, 200],
    baseMoveRange: 4,
    position: { col: 0, row: 0 }, // overwritten by Combat
    ...overrides,
  };
}

describe("Combat — setup", () => {
  it("builds a turn order with one entry per combatant", () => {
    const c = new Combat(
      [make("p1", "party"), make("p2", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    expect(c.initiativeOrder).toHaveLength(3);
    const ids = c.initiativeOrder.map((r) => r.combatantId).sort();
    expect(ids).toEqual(["e1", "p1", "p2"]);
  });

  it("sorts the turn order descending by total roll", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    const totals = c.initiativeOrder.map((r) => r.total);
    expect(totals).toEqual([...totals].sort((a, b) => b - a));
  });

  it("starts with isOver=false and a living `current`", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    expect(c.isOver).toBe(false);
    expect(c.current.hp).toBeGreaterThan(0);
  });
});

describe("Combat — attack flow", () => {
  it("reduces target HP on a hit and pushes a log line", () => {
    const c = new Combat(
      // Massively favourable attacker (huge bonus, no AC) so we get hits
      [make("p1", "party", { attackBonus: 100 })],
      [make("e1", "enemies", { ac: 1, hp: 10, maxHp: 10 })],
      mulberry32(1)
    );
    // Force the active to be the party member by spinning the cursor.
    while ((c.current.id as string) !== "p1") c.endTurn();
    const baseLines = c.log.length;       // opening banner + initial turn line
    const result = c.attack("e1");
    expect(result.hit).toBe(true);
    expect(c.byId("e1").hp).toBe(10 - result.damage);
    // attack adds exactly one new line (the dice/result detail)
    expect(c.log.length).toBe(baseLines + 1);
    expect(c.log[c.log.length - 1]).toMatch(/d20:\d+/);
  });

  it("clamps HP at 0 and marks killed when the blow is fatal", () => {
    const c = new Combat(
      [make("p1", "party", { attackBonus: 100, damage: { dice: 10, sides: 10, bonus: 99 } })],
      [make("e1", "enemies", { ac: 1, hp: 1, maxHp: 1 })],
      mulberry32(1)
    );
    while ((c.current.id as string) !== "p1") c.endTurn();
    const result = c.attack("e1");
    expect(result.killed).toBe(true);
    expect(c.byId("e1").hp).toBe(0);
  });

  it("rejects attacks against allies", () => {
    const c = new Combat(
      [make("p1", "party"), make("p2", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    while (c.current.side !== "party") c.endTurn();
    const ally = c.alive("party").find((x) => x.id !== c.current.id)!;
    expect(() => c.attack(ally.id)).toThrow();
  });
});

describe("Combat — end conditions", () => {
  it("ends with party victory when all enemies are at 0 HP", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies", { hp: 0, maxHp: 5 })],
      mulberry32(1)
    );
    expect(c.isOver).toBe(true);
    expect(c.winner).toBe("party");
  });

  it("ends with enemy victory when the party is wiped", () => {
    const c = new Combat(
      [make("p1", "party", { hp: 0 })],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    expect(c.isOver).toBe(true);
    expect(c.winner).toBe("enemies");
  });
});

describe("Combat — turn advancement", () => {
  it("endTurn skips over dead combatants", () => {
    const c = new Combat(
      [make("p1", "party"), make("p2", "party", { hp: 0 })],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    // Spin a full cycle and confirm we never land on p2.
    const visited: string[] = [];
    for (let i = 0; i < 6; i++) {
      visited.push(c.current.id);
      c.endTurn();
    }
    expect(visited).not.toContain("p2");
  });
});

// ── Tactical layer ───────────────────────────────────────────────────

describe("Combat — initial grid layout", () => {
  it("places the party near the bottom of the arena", () => {
    const c = new Combat(
      [make("p1", "party"), make("p2", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    // Party should sit on a row in the lower half of the arena and
    // strictly above the bottom wall.
    for (const p of c.alive("party")) {
      expect(p.position.row).toBeGreaterThan(ARENA_ROWS / 2);
      expect(p.position.row).toBeLessThan(ARENA_ROWS - 1);
    }
  });

  it("places enemies near the top of the arena", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies"), make("e2", "enemies")],
      mulberry32(1)
    );
    for (const e of c.alive("enemies")) {
      expect(e.position.row).toBeLessThan(ARENA_ROWS / 2);
      expect(e.position.row).toBeGreaterThan(0);
    }
  });

  it("keeps every starting position inside the wall ring", () => {
    const c = new Combat(
      [make("p1", "party"), make("p2", "party")],
      [make("e1", "enemies"), make("e2", "enemies")],
      mulberry32(1)
    );
    for (const x of c.combatants) {
      expect(x.position.col).toBeGreaterThan(0);
      expect(x.position.col).toBeLessThan(ARENA_COLS - 1);
      expect(x.position.row).toBeGreaterThan(0);
      expect(x.position.row).toBeLessThan(ARENA_ROWS - 1);
    }
  });
});

describe("Combat — move points", () => {
  it("starts the active actor with their baseMoveRange", () => {
    const c = new Combat(
      [make("p1", "party", { baseMoveRange: 5 })],
      [make("e1", "enemies", { baseMoveRange: 2 })],
      mulberry32(1)
    );
    expect(c.movePoints).toBe(c.current.baseMoveRange);
  });

  it("refills move points on endTurn for the next actor", () => {
    const c = new Combat(
      [make("p1", "party", { baseMoveRange: 5 })],
      [make("e1", "enemies", { baseMoveRange: 2 })],
      mulberry32(1)
    );
    const startId = c.current.id;
    c.movePoints = 0;
    c.endTurn();
    expect(c.current.id).not.toBe(startId);
    expect(c.movePoints).toBe(c.current.baseMoveRange);
  });
});

describe("Combat — movement", () => {
  it("decrements move points on a successful step", () => {
    const c = new Combat(
      [make("p1", "party", { baseMoveRange: 4 })],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    while ((c.current.id as string) !== "p1") c.endTurn();
    const before = c.current.position.col;
    const result = c.tryMove("w");
    expect(result.kind).toBe("moved");
    expect(c.movePoints).toBe(3);
    expect(c.current.position.col).toBe(before - 1);
  });

  it("blocks against the perimeter wall", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    while ((c.current.id as string) !== "p1") c.endTurn();
    // Force the actor next to the east wall: col = ARENA_COLS - 2.
    c.current.position = { col: ARENA_COLS - 2, row: 5 };
    const result = c.tryMove("e");
    expect(result.kind).toBe("blocked");
    if (result.kind === "blocked") expect(result.reason).toBe("wall");
    expect(c.current.position.col).toBe(ARENA_COLS - 2); // unchanged
  });

  it("blocks against an ally and does not consume points", () => {
    const c = new Combat(
      [make("p1", "party"), make("p2", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    while ((c.current.id as string) !== "p1") c.endTurn();
    const p1 = c.current;
    const p2 = c.combatants.find((x) => x.id === "p2")!;
    p1.position = { col: 5, row: 5 };
    p2.position = { col: 6, row: 5 };
    const before = c.movePoints;
    const result = c.tryMove("e");
    expect(result.kind).toBe("blocked");
    expect(c.movePoints).toBe(before);
    expect(p1.position.col).toBe(5); // unchanged
  });

  it("returns blocked with reason 'no-points' once exhausted", () => {
    const c = new Combat(
      [make("p1", "party", { baseMoveRange: 1 })],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    while ((c.current.id as string) !== "p1") c.endTurn();
    c.current.position = { col: 8, row: 8 };
    expect(c.tryMove("w").kind).toBe("moved");
    const second = c.tryMove("w");
    expect(second.kind).toBe("blocked");
    if (second.kind === "blocked") expect(second.reason).toBe("no-points");
  });
});

describe("Combat — bump-to-attack", () => {
  it("triggers an attack when stepping into an adjacent enemy", () => {
    const c = new Combat(
      // Force a hit: massive attack bonus, target AC 1.
      [make("p1", "party", { attackBonus: 100, baseMoveRange: 3 })],
      [make("e1", "enemies", { ac: 1, hp: 50, maxHp: 50 })],
      mulberry32(1)
    );
    while ((c.current.id as string) !== "p1") c.endTurn();
    const p1 = c.current;
    const e1 = c.byId("e1");
    p1.position = { col: 8, row: 8 };
    e1.position = { col: 9, row: 8 };
    const result = c.tryMove("e");
    expect(result.kind).toBe("attacked");
    if (result.kind === "attacked") {
      expect(result.result.attackerId).toBe("p1");
      expect(result.result.targetId).toBe("e1");
      expect(result.result.hit).toBe(true);
    }
    // Bump uses ALL remaining movement.
    expect(c.movePoints).toBe(0);
    // Attacker did not displace into the target's tile.
    expect(p1.position).toEqual({ col: 8, row: 8 });
  });
});

describe("Combat — monster AI", () => {
  it("attacks an adjacent party member", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies", { attackBonus: 100 })],
      mulberry32(1)
    );
    while (c.current.id !== "e1") c.endTurn();
    c.byId("p1").position = { col: 5, row: 5 };
    c.current.position = { col: 6, row: 5 };
    const intent = c.decideMonsterIntent();
    expect(intent.kind).toBe("attack");
    if (intent.kind === "attack") expect(intent.targetId).toBe("p1");
  });

  it("steps in a direction that reduces distance to the nearest party member", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    while (c.current.id !== "e1") c.endTurn();
    // Place party west of the monster.
    c.byId("p1").position = { col: 3, row: 5 };
    c.current.position = { col: 10, row: 5 };
    const intent = c.decideMonsterIntent();
    expect(intent.kind).toBe("move");
    if (intent.kind === "move") expect(intent.dir).toBe("w");
  });

  it("returns 'wait' when no direction reduces distance (already adjacent target ignored, no path)", () => {
    // Construct a scenario where every cardinal step would either hit
    // the wall or stay equidistant. A monster cornered at (1, 1) with
    // the target at (1, 1) itself can't happen, so we use a target on
    // a diagonal so cardinal moves don't strictly close Chebyshev
    // distance — those cases return 'wait' under the simple heuristic.
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    while (c.current.id !== "e1") c.endTurn();
    // Diagonal target — no cardinal step strictly closes Chebyshev
    // distance (it stays the same). The heuristic returns 'wait'.
    c.byId("p1").position = { col: 5, row: 5 };
    c.current.position = { col: 7, row: 7 };
    const intent = c.decideMonsterIntent();
    // Either 'wait' or a move; if it does move, distance must drop.
    if (intent.kind === "move") {
      const beforeDist = Math.max(
        Math.abs(7 - 5),
        Math.abs(7 - 5)
      );
      // Re-compute the simulated next distance:
      const dirDelta: Record<string, [number, number]> = {
        n: [0, -1], s: [0, 1], e: [1, 0], w: [-1, 0],
      };
      const [dc, dr] = dirDelta[intent.dir];
      const afterDist = Math.max(
        Math.abs(7 + dc - 5),
        Math.abs(7 + dr - 5)
      );
      expect(afterDist).toBeLessThan(beforeDist);
    } else {
      expect(intent.kind).toBe("wait");
    }
  });
});

describe("Combat — buff registry", () => {
  it("hasBuffFromSource matches case-insensitively and only on that source", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1),
    );
    c.addBuff("p1", { kind: "ac_bonus", value: 6, turnsLeft: 3, source: "Invisibility" });
    expect(c.hasBuffFromSource("p1", "Invisibility")).toBe(true);
    expect(c.hasBuffFromSource("p1", "invisibility")).toBe(true);  // case-insensitive
    expect(c.hasBuffFromSource("p1", "Bless")).toBe(false);
    expect(c.hasBuffFromSource("e1", "Invisibility")).toBe(false);
  });

  it("hasBuffFromSource flips to false the round the source expires", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(2),
    );
    c.addBuff("p1", { kind: "ac_bonus", value: 6, turnsLeft: 1, source: "Invisibility" });
    expect(c.hasBuffFromSource("p1", "Invisibility")).toBe(true);
    // Cycle one full round so tickAllBuffs decrements + expires it.
    for (let i = 0; i < c.combatants.length; i++) c.endTurn();
    expect(c.hasBuffFromSource("p1", "Invisibility")).toBe(false);
  });

  it("addBuff stores a buff on the right combatant and sumBuff sums it", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1),
    );
    c.addBuff("p1", { kind: "attack_bonus", value: 2, turnsLeft: 4, source: "Bless" });
    c.addBuff("p1", { kind: "attack_bonus", value: 1, turnsLeft: 4, source: "Other" });
    expect(c.sumBuff("p1", "attack_bonus")).toBe(3);
    expect(c.sumBuff("p1", "ac_bonus")).toBe(0);
    expect(c.sumBuff("e1", "attack_bonus")).toBe(0);
  });

  it("effectiveAttackBonus and effectiveAc fold buffs and penalties into the base stat", () => {
    const c = new Combat(
      [make("p1", "party", { attackBonus: 4, ac: 12 })],
      [make("e1", "enemies", { attackBonus: 3, ac: 11 })],
      mulberry32(1),
    );
    c.addBuff("p1", { kind: "attack_bonus", value: 2, turnsLeft: 4, source: "Bless" });
    c.addBuff("e1", { kind: "ac_penalty",  value: 2, turnsLeft: 4, source: "Curse" });
    c.addBuff("e1", { kind: "attack_penalty", value: 2, turnsLeft: 4, source: "Curse" });

    expect(c.effectiveAttackBonus(c.byId("p1"))).toBe(6);  // 4 + 2
    expect(c.effectiveAc(c.byId("e1"))).toBe(9);            // 11 - 2
    expect(c.effectiveAttackBonus(c.byId("e1"))).toBe(1);   // 3 - 2
  });

  it("ticks every buff once per round and logs an expire line", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(7),
    );
    // 1-turn buff so it expires on the very next round-tick.
    c.addBuff("p1", { kind: "attack_bonus", value: 2, turnsLeft: 1, source: "Bless" });
    expect(c.sumBuff("p1", "attack_bonus")).toBe(2);

    // Step through one full round: combatants.length end-turns trigger
    // exactly one tick.
    const rounds = c.combatants.length;
    for (let i = 0; i < rounds; i++) c.endTurn();

    expect(c.sumBuff("p1", "attack_bonus")).toBe(0);
    // Some expire-line was logged for p1.
    expect(c.log.some((l) => /blessing fades/i.test(l))).toBe(true);
  });

  it("isAiControlled defaults: enemies = AI, party = player", () => {
    const p1 = make("p1", "party");
    const e1 = make("e1", "enemies");
    expect(isAiControlled(p1)).toBe(false);
    expect(isAiControlled(e1)).toBe(true);
  });

  it("isAiControlled honours an explicit aiControlled override", () => {
    // A summon: party-side but AI-driven.
    const summon = make("s1", "party", { aiControlled: true });
    expect(isAiControlled(summon)).toBe(true);
    // An NPC ally: enemies-side but the player drives them. Hypothetical
    // — the override must respect both directions.
    const charmed = make("c1", "enemies", { aiControlled: false });
    expect(isAiControlled(charmed)).toBe(false);
  });

  it("addCombatant inserts into combatants and initiative order", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(1),
    );
    expect(c.combatants).toHaveLength(2);
    expect(c.initiativeOrder).toHaveLength(2);

    const summon = make("sum", "party", { aiControlled: true });
    c.addCombatant(summon, { col: 4, row: 4 }, 5);

    expect(c.combatants).toHaveLength(3);
    expect(c.initiativeOrder).toHaveLength(3);
    // The new combatant exists in the order.
    expect(c.initiativeOrder.map((r) => r.combatantId)).toContain("sum");
    // Position was stamped on by addCombatant.
    expect(summon.position).toEqual({ col: 4, row: 4 });
  });

  it("summon timer ticks each round and crumbles to dust on expiry", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies")],
      mulberry32(2),
    );
    const summon = make("sum", "party", {
      aiControlled: true, hp: 30, maxHp: 30,
    });
    c.addCombatant(summon, { col: 5, row: 5 }, /*summonTurns*/ 1);
    expect(summon.hp).toBe(30);

    // Cycle one full round (combatants.length = 3 with the summon).
    const rounds = c.combatants.length;
    for (let i = 0; i < rounds; i++) c.endTurn();

    // Timer was 1 → ticks to 0 → crumbles.
    expect(summon.hp).toBe(0);
    expect(c.log.some((l) => /crumbles to dust/i.test(l))).toBe(true);
  });

  it("non-summon entries are unaffected by tickSummons", () => {
    const c = new Combat(
      [make("p1", "party", { hp: 20, maxHp: 20 })],
      [make("e1", "enemies", { hp: 20, maxHp: 20 })],
      mulberry32(3),
    );
    const before = c.byId("p1").hp;
    // Step a few rounds — neither side has a summon timer.
    for (let i = 0; i < c.combatants.length * 3; i++) c.endTurn();
    expect(c.byId("p1").hp).toBe(before);
  });

  it("AI-controlled party-side actor's intent targets enemies", () => {
    // Summon with high dexMod so it gets first turn; place it next to
    // an enemy so it picks an attack instead of moving.
    const c = new Combat(
      [make("p1", "party"),
       make("sum", "party", { aiControlled: true, dexMod: 10 })],
      [make("e1", "enemies", { dexMod: -10 })],
      mulberry32(11),
    );
    // Force position adjacency by placing the enemy and the summon
    // diagonally next to each other.
    c.byId("sum").position = { col: 5, row: 5 };
    c.byId("e1").position  = { col: 6, row: 5 };
    // Wind the cursor to the summon.
    while (c.current.id !== "sum") c.endTurn();
    const intent = c.decideMonsterIntent();
    expect(intent.kind).toBe("attack");
    if (intent.kind === "attack") expect(intent.targetId).toBe("e1");
  });

  it("range_bonus buffs extend the next refilled movePoints", () => {
    // Force initiative so p1 acts first by giving them a high dexMod.
    const c = new Combat(
      [make("p1", "party", { baseMoveRange: 4, dexMod: 10 })],
      [make("e1", "enemies", { dexMod: -10 })],
      mulberry32(2),
    );
    // Walk the turn cursor until p1 is current.
    while ((c.current.id as string) !== "p1") c.endTurn();
    expect(c.movePoints).toBe(4);

    // Now buff and roll forward a full loop to refill on p1's next turn.
    c.addBuff("p1", { kind: "range_bonus", value: 3, turnsLeft: 5, source: "Long Shanks" });
    const loopSize = c.combatants.length;
    for (let i = 0; i < loopSize; i++) c.endTurn();
    expect(c.current.id).toBe("p1");
    expect(c.movePoints).toBe(7);  // 4 + 3
  });
});

describe("Combat — monster passives + on-hit + spell AI", () => {
  function endRound(c: Combat): void {
    const n = c.combatants.length;
    for (let i = 0; i < n; i++) c.endTurn();
  }

  it("regen passive heals the monster at the end of each round", () => {
    const dragon = make("drag", "enemies", {
      maxHp: 100, hp: 60,
      passives: [{ type: "regen", amount: 10 }],
    });
    const c = new Combat([make("p1", "party")], [dragon], mulberry32(1));
    endRound(c);
    const after = c.combatants.find((x) => x.id === "drag")!;
    expect(after.hp).toBe(70);
    // Caps at maxHp — repeat enough times to overshoot.
    for (let i = 0; i < 10; i++) endRound(c);
    expect(c.combatants.find((x) => x.id === "drag")!.hp).toBe(100);
  });

  it("regen never wakes a downed monster", () => {
    const downed = make("down", "enemies", {
      maxHp: 50, hp: 0,
      passives: [{ type: "regen", amount: 5 }],
    });
    const c = new Combat([make("p1", "party")], [downed], mulberry32(1));
    endRound(c);
    expect(c.combatants.find((x) => x.id === "down")!.hp).toBe(0);
  });

  it("fire_resistance halves breath_fire damage", () => {
    // attacker with breath_fire 50/50 cast chance + fixed 10 damage dice.
    // To make damage deterministic for the assertion, use a custom rng
    // and a small dice spec.
    const fireDragon = make("drag", "enemies", {
      maxHp: 100, hp: 100,
      monsterSpells: [{
        // Deterministic 20 damage = 1d1 + 19. (Pure-bonus spells with
        // no dice are treated as status-only by the engine.)
        type: "breath_fire", name: "Fire Breath",
        castChance: 100, range: 5,
        damageDice: 1, damageSides: 1, damageBonus: 19,
      }],
    });
    const tough = make("p1", "party", {
      maxHp: 100, hp: 100,
      passives: [{ type: "fire_resistance" }],
    });
    const wimp = make("p2", "party", { maxHp: 100, hp: 100 });
    const c = new Combat([tough, wimp], [fireDragon], mulberry32(7));
    // Walk to the dragon's turn.
    while (c.current.id !== "drag") c.endTurn();
    // Cast at the resistant target — flat 20 damage halved to 10.
    c.castMonsterSpell(0, "p1");
    expect(c.combatants.find((x) => x.id === "p1")!.hp).toBe(90);
    // Cast at the unresistant target — full 20.
    c.castMonsterSpell(0, "p2");
    expect(c.combatants.find((x) => x.id === "p2")!.hp).toBe(80);
  });

  it("on-hit drain heals the attacker by `amount` on a successful hit", () => {
    const leech = make("leech", "enemies", {
      attackBonus: 100, // always hits the dummy AC 12 below
      maxHp: 50, hp: 30,
      damage: { dice: 0, sides: 0, bonus: 5 }, // flat 5 dmg
      onHitEffects: [{ type: "drain", chance: 100, amount: 4 }],
    });
    const target = make("p1", "party", { ac: 12 });
    const c = new Combat([target], [leech], mulberry32(11));
    while (c.current.id !== "leech") c.endTurn();
    // Force the attack against the party member (via the public API).
    c.attack("p1");
    expect(c.combatants.find((x) => x.id === "leech")!.hp).toBe(34); // 30 + 4
  });

  it("on-hit consume rolls a STR save — pass means the bite never lands the swallow", () => {
    const eater = make("ate", "enemies", {
      attackBonus: 100,
      damage: { dice: 0, sides: 0, bonus: 1 },
      onHitEffects: [{
        type: "consume", chance: 100,
        damagePerTurn: 6, saveDc: 5, // trivially-low DC so any save passes
      }],
    });
    const burly = make("p1", "party", {
      ac: 12, maxHp: 50, hp: 50, strength: 18, // STR mod +4
    });
    const c = new Combat([burly], [eater], mulberry32(11));
    while (c.current.id !== "ate") c.endTurn();
    c.attack("p1");
    // STR mod +4 + any d20 ≥ 1 = at least 5 ≥ DC 5 → twists free.
    expect(c.combatants.find((x) => x.id === "p1")!.consumed).toBeUndefined();
  });

  it("on-hit consume swallows when the STR save fails: hides the victim, ticks each of their turns, releases on a passing save", () => {
    const eater = make("ate", "enemies", {
      attackBonus: 100,
      damage: { dice: 0, sides: 0, bonus: 1 },
      onHitEffects: [{
        type: "consume", chance: 100,
        damagePerTurn: 6, saveDc: 30, // unreachable; failed save guaranteed
      }],
    });
    const victim = make("p1", "party", {
      ac: 12, maxHp: 50, hp: 50, strength: 10,
    });
    const c = new Combat([victim], [eater], mulberry32(11));
    while (c.current.id !== "ate") c.endTurn();
    c.attack("p1");
    const swallowed = c.combatants.find((x) => x.id === "p1")!;
    // Off the board: position sentinel + consumed payload + original
    // position remembered for spit-out.
    expect(swallowed.consumed).toBeDefined();
    expect(swallowed.position).toEqual({ col: -1, row: -1 });
    expect(swallowed.consumed!.originalPosition).toBeDefined();
    // Walk to the victim's turn — auto-resolve should fire and tick
    // their HP (with this RNG / DC 30, save will fail).
    while ((c.current.id as string) !== "p1") c.endTurn();
    expect(c.isCurrentConsumed()).toBe(true);
    const beforeHp = swallowed.hp;
    const events = c.runConsumedAutoTurn();
    expect(events.find((e) => e.kind === "tick")).toBeDefined();
    expect(swallowed.hp).toBe(beforeHp - 6);
    // Lower the DC and walk to the victim's next turn — they should
    // escape and reappear on the board.
    swallowed.consumed!.saveDc = 1;
    c.endTurn();
    while ((c.current.id as string) !== "p1") c.endTurn();
    const events2 = c.runConsumedAutoTurn();
    expect(events2.find((e) => e.kind === "saved")).toBeDefined();
    expect(swallowed.consumed).toBeUndefined();
    // Position is back on a valid arena cell (not the {-1,-1} sentinel).
    expect(swallowed.position.col).toBeGreaterThanOrEqual(0);
    expect(swallowed.position.row).toBeGreaterThanOrEqual(0);
  });

  it("releases the victim immediately when the consumer is killed", () => {
    // A second eater so the encounter doesn't auto-end when the
    // first one dies — that lets us verify the release fires before
    // initiative concludes.
    const eaterA = make("ateA", "enemies", {
      attackBonus: 100, damage: { dice: 0, sides: 0, bonus: 1 },
      onHitEffects: [{
        type: "consume", chance: 100,
        damagePerTurn: 6, saveDc: 30,
      }],
      hp: 1, maxHp: 1, // one-shot kill
    });
    const eaterB = make("ateB", "enemies");
    const victim = make("p1", "party", {
      ac: 12, maxHp: 50, hp: 50, strength: 10,
      attackBonus: 100, damage: { dice: 0, sides: 0, bonus: 100 },
    });
    const c = new Combat([victim], [eaterA, eaterB], mulberry32(11));
    while (c.current.id !== "ateA") c.endTurn();
    c.attack("p1");
    const swallowed = c.combatants.find((x) => x.id === "p1")!;
    expect(swallowed.consumed).toBeDefined();
    expect(swallowed.position).toEqual({ col: -1, row: -1 });
    // Walk to a turn we can act on (skip ateB, p1's auto-resolve).
    // The eaterA is killed via attack from p1 — but p1 is consumed
    // and can't act. So have eaterB attack ateA via direct hp bash.
    // Simpler: have ateB hit ateA (we can't; same side). Cleanest:
    // walk to p1's turn where the auto-resolver gets the consumer
    // dead path on its own. But ateA is alive! We need to kill it.
    //
    // Use the public `attack` API by making ateA-the-attacker hit
    // a friendly... that's blocked. Simplest path: skip the test of
    // the kill-via-attack flow and just call releaseAllConsumedBy by
    // proxy — kill ateA's HP and walk to p1's turn so the auto
    // resolver's "consumer dead" branch runs.
    eaterA.hp = 0;
    while ((c.current.id as string) !== "p1") c.endTurn();
    const events = c.runConsumedAutoTurn();
    expect(events.find((e) => e.kind === "saved")).toBeDefined();
    expect(swallowed.consumed).toBeUndefined();
  });

  it("releases consumed victims the moment the consumer dies via attack", () => {
    const eater = make("ate", "enemies", {
      attackBonus: 100, damage: { dice: 0, sides: 0, bonus: 1 },
      onHitEffects: [{
        type: "consume", chance: 100,
        damagePerTurn: 6, saveDc: 30,
      }],
      hp: 1, maxHp: 1,
    });
    // Two party members so one can kill the eater while the other
    // is being digested.
    const v = make("v", "party", { strength: 10, ac: 12, hp: 50, maxHp: 50 });
    const k = make("k", "party", {
      attackBonus: 100, damage: { dice: 0, sides: 0, bonus: 100 },
    });
    const c = new Combat([v, k], [eater], mulberry32(11));
    while (c.current.id !== "ate") c.endTurn();
    c.attack("v");
    expect(c.combatants.find((x) => x.id === "v")!.consumed).toBeDefined();
    while ((c.current.id as string) !== "k") c.endTurn();
    c.attack("ate"); // one-shots
    // Killing the consumer immediately spits out the victim.
    expect(c.combatants.find((x) => x.id === "v")!.consumed).toBeUndefined();
    expect(c.combatants.find((x) => x.id === "v")!.position.col).toBeGreaterThanOrEqual(0);
  });

  it("spell AI returns a `spell` intent when cast_chance hits", () => {
    const lich = make("lich", "enemies", {
      monsterSpells: [{
        type: "magic_dart", name: "Magic Dart",
        castChance: 100, range: 30,  // arena is 18×18 — anyone is in range
        damageDice: 1, damageSides: 1, damageBonus: 3,
      }],
    });
    const c = new Combat([make("p1", "party")], [lich], mulberry32(3));
    while (c.current.id !== "lich") c.endTurn();
    const intent = c.decideMonsterIntent();
    expect(intent.kind).toBe("spell");
    if (intent.kind === "spell") {
      expect(intent.targetId).toBe("p1");
    }
  });

  it("heal_self only fires when the caster is wounded", () => {
    const troll = make("troll", "enemies", {
      maxHp: 50, hp: 50,
      monsterSpells: [{
        type: "heal_self", name: "Mend Wounds",
        castChance: 100,
        healDice: 0, healSides: 0, healBonus: 8,
      }],
    });
    const c = new Combat([make("p1", "party")], [troll], mulberry32(5));
    while (c.current.id !== "troll") c.endTurn();
    // Full HP — engine should refuse the heal even though chance is 100.
    expect(c.decideMonsterIntent().kind).not.toBe("spell");
    // Wound the troll, then re-roll.
    c.combatants.find((x) => x.id === "troll")!.hp = 30;
    const intent = c.decideMonsterIntent();
    expect(intent.kind).toBe("spell");
  });
});

