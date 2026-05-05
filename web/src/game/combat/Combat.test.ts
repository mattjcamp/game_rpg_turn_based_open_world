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
import { Combat } from "./Combat";
import { mulberry32 } from "../rng";
import { ARENA_COLS, ARENA_ROWS } from "./Arena";
import type { Combatant } from "../types";

function make(
  id: string,
  side: "party" | "enemies",
  overrides: Partial<Combatant> = {}
): Combatant {
  return {
    id,
    name: id,
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
    while (c.current.id !== "p1") c.endTurn();
    const result = c.attack("e1");
    expect(result.hit).toBe(true);
    expect(c.byId("e1").hp).toBe(10 - result.damage);
    expect(c.log.length).toBe(1);
  });

  it("clamps HP at 0 and marks killed when the blow is fatal", () => {
    const c = new Combat(
      [make("p1", "party", { attackBonus: 100, damage: { dice: 10, sides: 10, bonus: 99 } })],
      [make("e1", "enemies", { ac: 1, hp: 1, maxHp: 1 })],
      mulberry32(1)
    );
    while (c.current.id !== "p1") c.endTurn();
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
  it("places party on the right side of the arena", () => {
    const c = new Combat(
      [make("p1", "party"), make("p2", "party")],
      [make("e1", "enemies")],
      mulberry32(1)
    );
    for (const p of c.alive("party")) {
      expect(p.position.col).toBeGreaterThan(ARENA_COLS / 2);
    }
  });

  it("places enemies on the left side of the arena", () => {
    const c = new Combat(
      [make("p1", "party")],
      [make("e1", "enemies"), make("e2", "enemies")],
      mulberry32(1)
    );
    for (const e of c.alive("enemies")) {
      expect(e.position.col).toBeLessThan(ARENA_COLS / 2);
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
    while (c.current.id !== "p1") c.endTurn();
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
    while (c.current.id !== "p1") c.endTurn();
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
    while (c.current.id !== "p1") c.endTurn();
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
    while (c.current.id !== "p1") c.endTurn();
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
    while (c.current.id !== "p1") c.endTurn();
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
