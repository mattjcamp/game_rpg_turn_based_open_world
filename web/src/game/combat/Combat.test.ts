/**
 * Combat controller tests — covers initiative ordering, attack flow,
 * end-of-combat conditions, and turn advancement past downed actors.
 *
 * Loosely modelled on tests/test_combat.py from the Python project,
 * but scoped to the simpler JRPG-style controller (no tactical grid yet).
 */

import { describe, it, expect } from "vitest";
import { Combat } from "./Combat";
import { mulberry32 } from "../rng";
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
