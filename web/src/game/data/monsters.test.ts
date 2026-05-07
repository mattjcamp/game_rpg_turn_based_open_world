import { describe, it, expect } from "vitest";
import { makeMonsterByName, specFromRaw } from "./monsters";

describe("monsters — makeMonsterByName", () => {
  it("returns a Combatant for built-in names without the catalog loaded", () => {
    const c = makeMonsterByName("Goblin");
    expect(c.name).toBe("Goblin");
    expect(c.side).toBe("enemies");
    expect(c.maxHp).toBeGreaterThan(0);
  });

  it("flags Skeleton as undead from the BUILTIN seed", () => {
    const c = makeMonsterByName("Skeleton", "-1");
    expect(c.undead).toBe(true);
    expect(c.id).toContain("skeleton");
  });

  it("falls back to a generic stat block for unknown names", () => {
    const c = makeMonsterByName("Xorbathian");
    expect(c.name).toBe("Xorbathian");
    expect(c.maxHp).toBeGreaterThan(0);
    expect(c.ac).toBeGreaterThan(0);
  });
});

describe("monsters — specFromRaw", () => {
  it("converts a monsters.json entry into the typed spec", () => {
    const s = specFromRaw("Wolf", {
      hp: 12, ac: 12, attack_bonus: 3,
      damage_dice: 1, damage_sides: 6, damage_bonus: 1,
      color: [120, 90, 60], tile: "game/monsters/wolf.png",
      move_range: 5, undead: false,
    });
    expect(s.name).toBe("Wolf");
    expect(s.hp).toBe(12);
    expect(s.damage).toEqual({ dice: 1, sides: 6, bonus: 1 });
    expect(s.sprite).toBe("/assets/monsters/wolf.png");
    expect(s.baseMoveRange).toBe(5);
    expect(s.undead).toBe(false);
  });

  it("rewrites bare 'monsters/<name>' tile paths into /assets/", () => {
    const s = specFromRaw("Lich", { tile: "monsters/lich" });
    expect(s.sprite).toBe("/assets/monsters/lich.png");
  });

  it("uses safe defaults when fields are missing", () => {
    const s = specFromRaw("?", {});
    expect(Number.isNaN(s.hp)).toBe(false);
    expect(s.hp).toBeGreaterThan(0);
    expect(s.color).toHaveLength(3);
  });
});
