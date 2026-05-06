/**
 * Tests for the Party loader + sprite fallback logic.
 */

import { describe, it, expect } from "vitest";
import {
  partyFromRaw,
  memberFromRaw,
  spriteForMember,
  activeMembers,
} from "./Party";

describe("spriteForMember", () => {
  it("keeps a normalised /assets/characters/<known>.png path as-is", () => {
    expect(
      spriteForMember("src/assets/game/characters/cleric.png", "Cleric")
    ).toBe("/assets/characters/cleric.png");
    expect(
      spriteForMember("/assets/characters/wizard.png", "Wizard")
    ).toBe("/assets/characters/wizard.png");
  });

  it("falls back to a class-based sprite when the source path isn't shipped", () => {
    // The default party.json hands Gimli (a Fighter) a placeholder
    // shopkeep sprite — we don't ship that NPC PNG, so fall back to
    // the fighter class sprite.
    expect(
      spriteForMember("src/assets/game/npcs/shopkeep.png", "Fighter")
    ).toBe("/assets/characters/fighter.png");
    expect(
      spriteForMember("src/assets/game/npcs/vga_evil_mage.png", "Wizard")
    ).toBe("/assets/characters/wizard.png");
  });

  it("normalises class casing for the fallback path", () => {
    expect(spriteForMember("nope.png", "Wizard")).toBe(
      "/assets/characters/wizard.png"
    );
    expect(spriteForMember(undefined, "Cleric")).toBe(
      "/assets/characters/cleric.png"
    );
  });
});

describe("memberFromRaw", () => {
  it("populates maxHp from hp at load time", () => {
    const m = memberFromRaw({
      name: "Gimli", class: "Fighter", race: "Dwarf", gender: "Male",
      hp: 24, strength: 18, dexterity: 14, intelligence: 9, wisdom: 9,
      level: 2,
      equipped: { right_hand: "Sword", left_hand: null, body: "Cloth", head: null },
      inventory: [{ item: "Healing Herb" }],
    });
    expect(m.hp).toBe(24);
    expect(m.maxHp).toBe(24);
    expect(m.equipped.rightHand).toBe("Sword");
    expect(m.equipped.body).toBe("Cloth");
    expect(m.inventory).toEqual([{ item: "Healing Herb" }]);
  });

  it("defaults missing fields sensibly", () => {
    const m = memberFromRaw({});
    expect(m.name).toBe("?");
    expect(m.class).toBe("Fighter");
    expect(m.maxHp).toBe(0);
    expect(m.equipped).toEqual({
      rightHand: null, leftHand: null, body: null, head: null,
    });
    expect(m.sprite).toBe("/assets/characters/fighter.png");
  });
});

describe("partyFromRaw", () => {
  const raw = {
    start_position: { col: 14, row: 16 },
    gold: 25,
    roster: [
      { name: "Gimli", class: "Fighter", race: "Dwarf", hp: 20 },
      { name: "Merry", class: "Thief",   race: "Halfling", hp: 18 },
      { name: "Gandolf", class: "Wizard", race: "Elf", hp: 16 },
      { name: "Selina", class: "Cleric", race: "Human", hp: 18 },
    ],
    active_party: [0, 1, 2, 3],
    party_effects: { effect_1: null, effect_2: null, effect_3: null, effect_4: null },
    inventory: [{ item: "Torch" }, { item: "Rock" }],
  };

  it("parses every top-level field", () => {
    const p = partyFromRaw(raw);
    expect(p.startPosition).toEqual({ col: 14, row: 16 });
    expect(p.gold).toBe(25);
    expect(p.roster).toHaveLength(4);
    expect(p.activeParty).toEqual([0, 1, 2, 3]);
    expect(p.inventory).toHaveLength(2);
  });

  it("activeMembers returns the four active roster entries in order", () => {
    const p = partyFromRaw({
      ...raw,
      active_party: [3, 1, 0, 2], // out of natural order
    });
    const members = activeMembers(p);
    expect(members.map((m) => m.name)).toEqual([
      "Selina", "Merry", "Gimli", "Gandolf",
    ]);
  });

  it("activeMembers skips out-of-bounds indices", () => {
    const p = partyFromRaw({ ...raw, active_party: [0, 99, 1] });
    expect(activeMembers(p).map((m) => m.name)).toEqual(["Gimli", "Merry"]);
  });

  it("defaults active_party / party_effects / inventory when missing", () => {
    const p = partyFromRaw({ roster: [{ name: "Solo", class: "Fighter" }] });
    expect(p.activeParty).toEqual([0, 1, 2, 3]);
    expect(p.partyEffects.effect_1).toBeNull();
    expect(p.inventory).toEqual([]);
  });
});
