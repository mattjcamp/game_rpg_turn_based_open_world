import { describe, it, expect } from "vitest";
import { makeMonsterByName, specFromRaw, loadMonsters, _clearMonstersCache } from "./monsters";
import { readFileSync } from "node:fs";
import { join } from "node:path";

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

  it("parses Man Eater's on_hit_effects (drain + consume) into the spec", () => {
    const s = specFromRaw("Man Eater", {
      hp: 50, ac: 16, attack_bonus: 3,
      damage_dice: 3, damage_sides: 4,
      battle_scale: 2,
      on_hit_effects: [
        { type: "drain",   chance: 25, amount: 3 },
        { type: "consume", chance: 75, damage_per_turn: 1, save_dc: 14 },
      ],
      passives: [{ type: "poison_immunity" }],
    });
    expect(s.battleScale).toBe(2);
    expect(s.onHitEffects).toHaveLength(2);
    expect(s.onHitEffects?.[0]).toEqual({ type: "drain", chance: 25, amount: 3 });
    expect(s.onHitEffects?.[1]).toEqual({
      type: "consume", chance: 75, damagePerTurn: 1, saveDc: 14,
    });
    expect(s.passives?.[0]).toEqual({ type: "poison_immunity" });
  });

  it("hydrates the live catalog via loadMonsters and exposes Man Eater's effects on the Combatant", async () => {
    // Stub global.fetch so loadMonsters reads the on-disk JSON the
    // shipped game ships rather than going over HTTP. Mirrors what
    // the browser would deliver from /data/monsters.json. Vitest
    // runs from the `web/` directory; the JSON is mirrored there
    // by `npm run sync-modules` (which `pretest` already invoked).
    const json = readFileSync(join(process.cwd(), "public", "data", "monsters.json"), "utf8");
    const fakeFetch = async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => JSON.parse(json),
    });
    const originalFetch = (globalThis as { fetch?: unknown }).fetch;
    (globalThis as { fetch: unknown }).fetch = fakeFetch;
    try {
      _clearMonstersCache();
      await loadMonsters();
      const m = makeMonsterByName("Man Eater");
      expect(m.battleScale).toBe(2);
      expect(m.onHitEffects).toBeDefined();
      const consume = m.onHitEffects!.find((e) => e.type === "consume");
      expect(consume).toBeDefined();
      expect(consume).toMatchObject({
        type: "consume", damagePerTurn: 1, saveDc: 14,
      });
    } finally {
      (globalThis as { fetch: unknown }).fetch = originalFetch;
      _clearMonstersCache();
    }
  });

  it("parses Dragon's spells and regen passive", () => {
    const s = specFromRaw("Dragon", {
      hp: 125,
      battle_scale: 2,
      spells: [{
        type: "breath_fire", name: "Fire Breath",
        cast_chance: 50, range: 6,
        damage_dice: 6, damage_sides: 6, damage_bonus: 0,
        save_dc: 13,
      }],
      passives: [
        { type: "regen", amount: 10 },
        { type: "fire_resistance" },
      ],
    });
    expect(s.monsterSpells).toHaveLength(1);
    expect(s.monsterSpells?.[0].name).toBe("Fire Breath");
    expect(s.monsterSpells?.[0].castChance).toBe(50);
    expect(s.monsterSpells?.[0].damageDice).toBe(6);
    expect(s.passives?.[0]).toEqual({ type: "regen", amount: 10 });
    expect(s.passives?.[1]).toEqual({ type: "fire_resistance" });
  });

});
