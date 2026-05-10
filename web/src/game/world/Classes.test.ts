/**
 * Classes module tests — focused on the small surface area the UI
 * leans on directly. The async loaders (`loadClass`, `loadRaces`)
 * are exercised via fetch in the live build; here we cover the
 * pure helpers exposed alongside.
 */

import { describe, it, expect } from "vitest";
import { raceAbilities } from "./Classes";

describe("raceAbilities", () => {
  it("returns Infravision for Dwarves", () => {
    const out = raceAbilities("Dwarf");
    expect(out.map((a) => a.name)).toEqual(["Infravision"]);
    expect(out[0].description.length).toBeGreaterThan(0);
  });

  it("returns Pickpocket for Halflings", () => {
    expect(raceAbilities("Halfling").map((a) => a.name))
      .toEqual(["Pickpocket"]);
  });

  it("returns Galadriel's Light for Elves", () => {
    expect(raceAbilities("Elf").map((a) => a.name))
      .toEqual(["Galadriel's Light"]);
  });

  it("returns Tinker for Gnomes", () => {
    expect(raceAbilities("Gnome").map((a) => a.name))
      .toEqual(["Tinker"]);
  });

  it("returns [] for Humans (their edge is faster XP, surfaced elsewhere)", () => {
    expect(raceAbilities("Human")).toEqual([]);
  });

  it("returns [] for unknown races rather than throwing", () => {
    expect(raceAbilities("Mythical")).toEqual([]);
    expect(raceAbilities("")).toEqual([]);
  });

  it("matches case-insensitively on the race name", () => {
    expect(raceAbilities("dwarf").map((a) => a.name)).toEqual(["Infravision"]);
    expect(raceAbilities("HALFLING").map((a) => a.name)).toEqual(["Pickpocket"]);
    expect(raceAbilities("eLf").map((a) => a.name)).toEqual(["Galadriel's Light"]);
  });
});
