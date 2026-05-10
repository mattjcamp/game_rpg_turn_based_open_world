/**
 * Encounters module tests — focused on the sampler. The async
 * `loadEncounters` is exercised live in the build; these tests pin
 * down the in-memory filter / weighting behaviour so the dungeon
 * generator can rely on it.
 */

import { describe, it, expect } from "vitest";
import { sampleEncounter, type EncounterTemplate } from "./Encounters";
import { mulberry32 } from "../rng";

function enc(over: Partial<EncounterTemplate>): EncounterTemplate {
  return {
    name: over.name ?? "E",
    level: over.level ?? 1,
    weight: over.weight ?? 1,
    terrain: over.terrain ?? "land",
    monsterPartyTile: over.monsterPartyTile ?? "Rat",
    monsters: over.monsters ?? ["Rat"],
  };
}

describe("sampleEncounter — level band", () => {
  it("returns null when the area key is missing", () => {
    const t = { dungeon: [enc({})] };
    expect(sampleEncounter(t, "ocean")).toBeNull();
  });

  it("returns null when no encounters fall inside the level band", () => {
    const t = { dungeon: [enc({ level: 5 })] };
    expect(sampleEncounter(t, "dungeon", { minLevel: 1, maxLevel: 2 })).toBeNull();
  });

  it("samples by weight inside the level band", () => {
    const t = {
      dungeon: [
        enc({ name: "Rats", level: 1, weight: 3, monsters: ["Rat"] }),
        enc({ name: "Goblins", level: 1, weight: 1, monsters: ["Goblin"] }),
      ],
    };
    // mulberry32(42) lands in the early portion of the weight cdf —
    // first roll selects the heavier-weighted "Rats" entry.
    const r = sampleEncounter(t, "dungeon", { rng: mulberry32(42) });
    expect(r?.name).toBe("Rats");
  });
});

describe("sampleEncounter — monster-difficulty filter", () => {
  // A "normal" dungeon should never pick up hard monsters even if
  // the matching encounter lives in a higher level band — that's
  // the user-reported regression where a normal forest dungeon
  // included Banshees + Man Eaters via a level-6 encounter.
  const HAUNTED_TRAIL: EncounterTemplate = enc({
    name: "Haunted Trail",
    level: 6,
    monsterPartyTile: "Banshee",
    monsters: ["Banshee", "Man Eater"],
  });
  const RAT_PACK: EncounterTemplate = enc({
    name: "Rat Pack",
    level: 1,
    monsterPartyTile: "Giant Rat",
    monsters: ["Giant Rat", "Giant Rat"],
  });
  const MIXED: EncounterTemplate = enc({
    name: "Mixed Party",
    level: 4,
    monsterPartyTile: "Banshee",   // hard
    monsters: ["Banshee", "Goblin", "Wolf"],
  });

  const difficulty = (name: string): string | undefined => {
    if (name === "Banshee" || name === "Man Eater") return "hard";
    if (name === "Goblin"  || name === "Wolf")      return "normal";
    if (name === "Giant Rat")                       return "easy";
    return undefined;
  };

  it("excludes encounters whose monsters all fall outside the allowed tiers", () => {
    const t = { dungeon: [HAUNTED_TRAIL] };
    const r = sampleEncounter(t, "dungeon", {
      minLevel: 1, maxLevel: 8,
      allowedDifficulties: new Set(["normal"]),
      monsterDifficulty: difficulty,
    });
    // Only encounter has hard-only monsters; pruning empties the
    // roster, the encounter drops out, sampler returns null.
    expect(r).toBeNull();
  });

  it("prunes the surviving encounter's monster list to allowed tiers", () => {
    const t = { dungeon: [MIXED] };
    const r = sampleEncounter(t, "dungeon", {
      minLevel: 1, maxLevel: 8,
      allowedDifficulties: new Set(["normal"]),
      monsterDifficulty: difficulty,
      rng: mulberry32(1),
    });
    expect(r).not.toBeNull();
    // Banshee gets pruned out, Goblin + Wolf survive.
    expect(r!.monsters.sort()).toEqual(["Goblin", "Wolf"]);
  });

  it("swaps the lead when the original lead got pruned", () => {
    const t = { dungeon: [MIXED] };
    const r = sampleEncounter(t, "dungeon", {
      minLevel: 1, maxLevel: 8,
      allowedDifficulties: new Set(["normal"]),
      monsterDifficulty: difficulty,
      rng: mulberry32(1),
    });
    // Banshee was the original lead; after pruning, the first
    // surviving monster (Goblin) takes over so the on-map sprite
    // matches a monster that's actually in the fight.
    expect(r!.monsterPartyTile).toBe("Goblin");
  });

  it("keeps the original lead when it survives the prune", () => {
    const enc1 = enc({
      name: "Wolf Pack",
      level: 4,
      monsterPartyTile: "Wolf",        // normal — survives
      monsters: ["Wolf", "Banshee"],   // banshee gets pruned
    });
    const t = { dungeon: [enc1] };
    const r = sampleEncounter(t, "dungeon", {
      minLevel: 1, maxLevel: 8,
      allowedDifficulties: new Set(["normal"]),
      monsterDifficulty: difficulty,
      rng: mulberry32(1),
    });
    expect(r!.monsterPartyTile).toBe("Wolf");
    expect(r!.monsters).toEqual(["Wolf"]);
  });

  it("allows multi-tier sets — strict match isn't the only legal use", () => {
    // A "hard" dungeon could plausibly include normal + hard tiers;
    // the helper supports that by accepting multiple difficulties
    // in the set. Strict match is the dungeon-side default, but the
    // sampler doesn't enforce it.
    const t = { dungeon: [MIXED] };
    const r = sampleEncounter(t, "dungeon", {
      minLevel: 1, maxLevel: 8,
      allowedDifficulties: new Set(["normal", "hard"]),
      monsterDifficulty: difficulty,
      rng: mulberry32(1),
    });
    expect(r!.monsters.sort()).toEqual(["Banshee", "Goblin", "Wolf"]);
  });

  it("excludes monsters with no difficulty tag", () => {
    // A bare "monster name → undefined" lookup result reads as "not
    // in the allow list" so unknown / mistagged monsters can't
    // sneak into a tier-restricted dungeon. Defensive against
    // monsters.json data drift.
    const enc1 = enc({
      name: "Mystery Mob",
      level: 4,
      monsterPartyTile: "Rat",
      monsters: ["Rat", "MysteryFoe"],
    });
    const t = { dungeon: [enc1] };
    const r = sampleEncounter(t, "dungeon", {
      minLevel: 1, maxLevel: 8,
      allowedDifficulties: new Set(["easy"]),
      monsterDifficulty: (n) => n === "Rat" ? "easy" : undefined,
      rng: mulberry32(1),
    });
    expect(r!.monsters).toEqual(["Rat"]);
  });

  it("no-ops without a difficulty lookup (filter requires both options)", () => {
    // If only allowedDifficulties is set without a lookup, the
    // sampler can't tell which monsters belong to which tier, so it
    // skips the prune step rather than silently dropping every
    // encounter. The original level-band filter still applies.
    const t = { dungeon: [HAUNTED_TRAIL, RAT_PACK] };
    const r = sampleEncounter(t, "dungeon", {
      minLevel: 1, maxLevel: 8,
      allowedDifficulties: new Set(["normal"]),
      // monsterDifficulty intentionally omitted
      rng: mulberry32(1),
    });
    // No filtering happened — both encounters are still in the pool.
    expect(r).not.toBeNull();
  });
});
