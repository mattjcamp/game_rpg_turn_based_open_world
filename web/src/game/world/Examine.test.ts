import { describe, it, expect } from "vitest";
import {
  hasHerbalist,
  generateExamineLayout,
  attemptHerbalistDiscovery,
  attemptOverworldHerbalism,
  isForageableTile,
  freezeLayout,
  thawLayout,
  themeTileFor,
  EXAMINE_COLS,
  EXAMINE_ROWS,
  EXAMINE_START_COL,
  EXAMINE_START_ROW,
  FORAGE_REAGENTS,
} from "./Examine";
import { TILE_FOREST, TILE_GRASS, TILE_PATH, TILE_SAND, TILE_WATER } from "./Tiles";
import { partyFromRaw, activeMembers } from "./Party";

function makeParty() {
  return partyFromRaw({
    start_position: { col: 0, row: 0 },
    gold: 0,
    roster: [
      { name: "Gimli",   class: "Fighter",  race: "Dwarf",   level: 1, hp: 20, intelligence: 10 },
      { name: "Merry",   class: "Thief",    race: "Halfling",level: 1, hp: 18, intelligence: 12 },
      { name: "Brom",    class: "Ranger",   race: "Human",   level: 1, hp: 16, intelligence: 14 },
      { name: "Selina",  class: "Alchemist",race: "Gnome",   level: 1, hp: 18, intelligence: 16 },
    ],
    active_party: [0, 1, 2, 3],
    inventory: [],
  });
}

// Stubbable rng: returns the values in order, looping back to the start.
function seqRng(values: number[]): () => number {
  let i = 0;
  return () => {
    const v = values[i % values.length];
    i++;
    return v;
  };
}

describe("themeTileFor", () => {
  it("collapses unknown overworld tiles to grass", () => {
    expect(themeTileFor(TILE_GRASS)).toBe(TILE_GRASS);
    expect(themeTileFor(TILE_FOREST)).toBe(TILE_FOREST);
    expect(themeTileFor(TILE_SAND)).toBe(TILE_SAND);
    expect(themeTileFor(TILE_PATH)).toBe(TILE_PATH);
    expect(themeTileFor(TILE_WATER)).toBe(TILE_GRASS);
  });
});

describe("hasHerbalist", () => {
  it("detects an alive Ranger", () => {
    const p = makeParty();
    expect(hasHerbalist(activeMembers(p))).toBe(true);
  });

  it("detects an alive Alchemist", () => {
    const p = makeParty();
    p.roster[2].hp = 0; // kill the Ranger; the Alchemist still qualifies
    expect(hasHerbalist(activeMembers(p))).toBe(true);
  });

  it("returns false when the only herbalist is unconscious", () => {
    const p = makeParty();
    p.roster[2].hp = 0; // Ranger down
    p.roster[3].hp = 0; // Alchemist down
    expect(hasHerbalist(activeMembers(p))).toBe(false);
  });

  it("returns false for parties without a Ranger or Alchemist", () => {
    const p = partyFromRaw({
      gold: 0,
      roster: [{ name: "Solo", class: "Fighter", race: "Human", level: 1, hp: 12 }],
      active_party: [0],
    });
    expect(hasHerbalist(activeMembers(p))).toBe(false);
  });
});

describe("generateExamineLayout", () => {
  it("produces a layout themed to the requested terrain", () => {
    const p = makeParty();
    // Use a real (varied) rng so the placement loop actually finds
    // distinct cells rather than collapsing to a single key.
    const layout = generateExamineLayout(
      TILE_FOREST, "Forest", activeMembers(p), Math.random,
    );
    expect(layout.tileType).toBe(TILE_FOREST);
    expect(layout.tileName).toBe("Forest");
    // Forest range is 6–10 obstacles. The placement loop can come up
    // short under unlucky rolls, but at minimum we expect a few trees.
    expect(layout.obstacles.size).toBeGreaterThan(0);
    expect(layout.obstacles.size).toBeLessThanOrEqual(10);
    for (const kind of layout.obstacles.values()) {
      expect(kind).toBe("tree");
    }
    expect(layout.reagentsSearched).toBe(false);
  });

  it("places obstacles only on interior cells (avoids the edge ring + start)", () => {
    const p = makeParty();
    const layout = generateExamineLayout(
      TILE_FOREST, "Forest", activeMembers(p), Math.random,
    );
    for (const key of layout.obstacles.keys()) {
      const [c, r] = key.split(",").map(Number);
      expect(c).toBeGreaterThanOrEqual(1);
      expect(c).toBeLessThanOrEqual(EXAMINE_COLS - 2);
      expect(r).toBeGreaterThanOrEqual(1);
      expect(r).toBeLessThanOrEqual(EXAMINE_ROWS - 2);
      expect(c === EXAMINE_START_COL && r === EXAMINE_START_ROW).toBe(false);
    }
  });
});

describe("attemptHerbalistDiscovery", () => {
  it("only rolls for alive Rangers and Alchemists", () => {
    const p = makeParty();
    // rng sequence:
    //   member loop is roster order [Fighter, Thief, Ranger, Alchemist].
    //   Fighter / Thief are skipped before any rng call.
    //   Ranger:    randInt(1,20) → floor(0.95 * 20) + 1 = 20  → success
    //              then floor(0.0 * 5) → 0 → "Moonpetal"
    //   Alchemist: randInt(1,20) → floor(0.95 * 20) + 1 = 20  → success
    //              then floor(0.5 * 5) → 2 → "Serpent Root"
    const rng = seqRng([0.95, 0.0, 0.95, 0.5]);
    const members = activeMembers(p);
    const out = attemptHerbalistDiscovery(p, members, rng);
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({ member: "Brom",   reagent: "Moonpetal" });
    expect(out[1]).toEqual({ member: "Selina", reagent: "Serpent Root" });
    // Both reagents land in the shared stash.
    expect(p.inventory.map((i) => i.item)).toEqual(["Moonpetal", "Serpent Root"]);
  });

  it("skips a herbalist whose roll falls under DC 13", () => {
    const p = makeParty();
    // randInt picks 1 → roll = 1 + INT mod (Ranger has INT 14 → +2) = 3 < 13.
    // Same for Alchemist (INT 16 → +3, roll = 4) → still < 13.
    const rng = seqRng([0.0]);
    const out = attemptHerbalistDiscovery(p, activeMembers(p), rng);
    expect(out).toEqual([]);
    expect(p.inventory).toEqual([]);
  });

  it("doesn't roll for downed herbalists", () => {
    const p = makeParty();
    p.roster[2].hp = 0;
    p.roster[3].hp = 0;
    const out = attemptHerbalistDiscovery(p, activeMembers(p), () => 0.99);
    expect(out).toEqual([]);
  });
});

describe("isForageableTile", () => {
  it("accepts grass / forest / sand / path", () => {
    expect(isForageableTile(TILE_GRASS)).toBe(true);
    expect(isForageableTile(TILE_FOREST)).toBe(true);
    expect(isForageableTile(TILE_SAND)).toBe(true);
    expect(isForageableTile(TILE_PATH)).toBe(true);
  });

  it("rejects water and other non-walkable wilds", () => {
    expect(isForageableTile(TILE_WATER)).toBe(false);
    // Any tile id outside the foraging set is rejected.
    expect(isForageableTile(9999)).toBe(false);
  });
});

describe("attemptOverworldHerbalism (passive per-step roll)", () => {
  it("returns no finds without a Ranger or Alchemist", () => {
    const p = partyFromRaw({
      gold: 0,
      roster: [
        { name: "Solo", class: "Fighter", race: "Human", level: 1, hp: 12, intelligence: 18 },
      ],
      active_party: [0],
    });
    const out = attemptOverworldHerbalism(p, activeMembers(p), () => 0.99);
    expect(out).toEqual([]);
    expect(p.inventory).toEqual([]);
  });

  it("requires d20 + INT mod ≥ 20 — Ranger at INT 14 needs a nat 18+", () => {
    // INT 14 → +2 mod. DC 20 means raw d20 must be ≥ 18 (rolls 18, 19, 20
    // succeed). randInt uses `floor(rng() * 20) + 1`, so rng = 0.85 →
    // d20 = 18, the lowest passing roll.
    const p = makeParty();
    p.roster[3].hp = 0; // remove Alchemist so only the Ranger rolls
    const rng = seqRng([0.85, 0.0]); // nat 18 + Moonpetal pick
    const out = attemptOverworldHerbalism(p, activeMembers(p), rng);
    expect(out).toEqual([{ member: "Brom", reagent: "Moonpetal" }]);
    expect(p.inventory.map((i) => i.item)).toEqual(["Moonpetal"]);
  });

  it("skips a roll that falls just short — nat 17 + INT mod 2 = 19 < DC 20", () => {
    const p = makeParty();
    p.roster[3].hp = 0;
    const rng = seqRng([0.80]); // floor(0.80 * 20) + 1 = 17 → 17 + 2 = 19
    const out = attemptOverworldHerbalism(p, activeMembers(p), rng);
    expect(out).toEqual([]);
    expect(p.inventory).toEqual([]);
  });

  it("rolls independently for each herbalist on the same step", () => {
    const p = makeParty();
    // Ranger (INT 14, +2 mod): nat 18 succeeds; pick Moonpetal (rng 0.0).
    // Alchemist (INT 16, +3 mod): nat 17 succeeds (17 + 3 = 20); pick
    //   Glowcap Mushroom (rng 0.20 → idx 1).
    const rng = seqRng([0.85, 0.0, 0.80, 0.20]);
    const out = attemptOverworldHerbalism(p, activeMembers(p), rng);
    expect(out).toEqual([
      { member: "Brom",   reagent: "Moonpetal" },
      { member: "Selina", reagent: "Glowcap Mushroom" },
    ]);
    expect(p.inventory.map((i) => i.item)).toEqual(["Moonpetal", "Glowcap Mushroom"]);
  });

  it("ignores downed herbalists", () => {
    const p = makeParty();
    p.roster[2].hp = 0; // Ranger down
    p.roster[3].hp = 0; // Alchemist down
    // Even a nat 20 wouldn't matter — they shouldn't roll at all.
    const out = attemptOverworldHerbalism(p, activeMembers(p), () => 0.99);
    expect(out).toEqual([]);
  });

  it("uses an INT 10 baseline that only crits — exactly 5% find rate", () => {
    const p = partyFromRaw({
      gold: 0,
      roster: [
        { name: "Idris", class: "Ranger", race: "Human", level: 1, hp: 14, intelligence: 10 },
      ],
      active_party: [0],
    });
    // INT 10 → +0 mod, DC 20 → only a natural 20 hits. Anything below
    // 0.95 in rng → d20 ≤ 19 → miss.
    const miss = attemptOverworldHerbalism(p, activeMembers(p), seqRng([0.94]));
    expect(miss).toEqual([]);
    const hit = attemptOverworldHerbalism(p, activeMembers(p), seqRng([0.95, 0.0]));
    expect(hit).toEqual([{ member: "Idris", reagent: "Moonpetal" }]);
  });
});

describe("freezeLayout / thawLayout round-trip", () => {
  it("preserves obstacles, ground items, and the searched flag", () => {
    const layout = {
      tileType: TILE_GRASS,
      tileName: "Grass",
      obstacles: new Map([["3,4", "bush" as const], ["7,2", "rock" as const]]),
      groundItems: new Map([["5,5", { item: "Healing Herb" }]]),
      reagentsSearched: true,
    };
    const back = thawLayout(freezeLayout(layout));
    expect(back.tileType).toBe(TILE_GRASS);
    expect(back.tileName).toBe("Grass");
    expect(back.reagentsSearched).toBe(true);
    expect(Array.from(back.obstacles.entries())).toEqual([
      ["3,4", "bush"], ["7,2", "rock"],
    ]);
    expect(Array.from(back.groundItems.entries())).toEqual([
      ["5,5", { item: "Healing Herb" }],
    ]);
  });
});

describe("FORAGE_REAGENTS catalog", () => {
  it("matches the Python reagent list verbatim", () => {
    expect(FORAGE_REAGENTS).toEqual([
      "Moonpetal",
      "Glowcap Mushroom",
      "Serpent Root",
      "Brimite Ore",
      "Spring Water",
    ]);
  });
});

// floorTileFor / edgeTileFor are pure helpers — same module.
import { floorTileFor, edgeTileFor } from "./Examine";
import { TILE_MOUNTAIN } from "./Tiles";

describe("floorTileFor (per-cell theme variety)", () => {
  it("paints a 2-tile path strip down the middle for the path theme", () => {
    for (let r = 1; r < EXAMINE_ROWS - 1; r++) {
      expect(floorTileFor(TILE_PATH, 5, r)).toBe(TILE_PATH);
      expect(floorTileFor(TILE_PATH, 6, r)).toBe(TILE_PATH);
      // Outside that strip, expect grass.
      expect(floorTileFor(TILE_PATH, 1, r)).toBe(TILE_GRASS);
      expect(floorTileFor(TILE_PATH, 10, r)).toBe(TILE_GRASS);
    }
  });

  it("paints sand themes uniformly (no accent variety)", () => {
    for (let r = 0; r < EXAMINE_ROWS; r++) {
      for (let c = 0; c < EXAMINE_COLS; c++) {
        expect(floorTileFor(TILE_SAND, c, r)).toBe(TILE_SAND);
      }
    }
  });

  it("sprinkles forest accents into a grass theme", () => {
    let grass = 0;
    let forest = 0;
    for (let r = 0; r < EXAMINE_ROWS; r++) {
      for (let c = 0; c < EXAMINE_COLS; c++) {
        const id = floorTileFor(TILE_GRASS, c, r);
        if (id === TILE_GRASS) grass += 1;
        else if (id === TILE_FOREST) forest += 1;
        else throw new Error(`unexpected tile id ${id}`);
      }
    }
    expect(grass).toBeGreaterThan(forest * 3); // grass dominates
    expect(forest).toBeGreaterThan(0);          // but a few trees show through
  });

  it("makes forest themes mostly forest with grass clearings", () => {
    let forest = 0;
    let grass = 0;
    for (let r = 0; r < EXAMINE_ROWS; r++) {
      for (let c = 0; c < EXAMINE_COLS; c++) {
        const id = floorTileFor(TILE_FOREST, c, r);
        if (id === TILE_FOREST) forest += 1;
        else if (id === TILE_GRASS) grass += 1;
        else throw new Error(`unexpected tile id ${id}`);
      }
    }
    expect(forest).toBeGreaterThan(grass);
  });

  it("is deterministic — same (theme, col, row) always yields the same tile", () => {
    expect(floorTileFor(TILE_GRASS, 3, 4)).toBe(floorTileFor(TILE_GRASS, 3, 4));
    expect(floorTileFor(TILE_FOREST, 5, 6)).toBe(floorTileFor(TILE_FOREST, 5, 6));
  });
});

describe("edgeTileFor", () => {
  it("rings sand themes with mountain (rocky cliffs)", () => {
    expect(edgeTileFor(TILE_SAND)).toBe(TILE_MOUNTAIN);
  });
  it("rings grass / forest / path themes with forest", () => {
    expect(edgeTileFor(TILE_GRASS)).toBe(TILE_FOREST);
    expect(edgeTileFor(TILE_FOREST)).toBe(TILE_FOREST);
    expect(edgeTileFor(TILE_PATH)).toBe(TILE_FOREST);
  });
});
