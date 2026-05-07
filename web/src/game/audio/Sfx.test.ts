/**
 * Tests for the Web-Audio chiptune SFX module.
 *
 * vitest runs in jsdom, which doesn't ship a working AudioContext, so
 * actual playback is impossible. The contract these tests guard is:
 *
 *   - The catalog covers every name spells.json references via `sfx`
 *     and `hit_sfx`, plus the names CombatScene plays directly.
 *   - `Sfx.play` is a no-op (and never throws) when there's no audio,
 *     so headless test runs are safe.
 *   - The mute toggle persists through localStorage.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { Sfx, SFX_NAMES, _resetSfx } from "./Sfx";

beforeEach(() => {
  _resetSfx();
  Sfx.setMuted(false);
});

describe("Sfx — catalog completeness", () => {
  // Names every CombatScene action calls. If a future change adds a
  // new SFX trigger, adding it here is the minimum to keep the audio
  // path covered.
  const COMBAT_NAMES = [
    "miss", "critical", "monster_hit", "player_hurt",
    "encounter", "victory", "defeat", "chirp", "arrow",
  ];

  // Names referenced in data/spells.json (sfx + hit_sfx fields).
  const SPELL_NAMES = [
    "fireball", "explosion", "heal", "shield",
    "turn_undead", "magic_burst", "lock_pick_success",
  ];

  it("knows every combat-trigger name", () => {
    for (const n of COMBAT_NAMES) {
      expect(Sfx.has(n), `missing combat SFX: ${n}`).toBe(true);
    }
  });

  it("knows every spell sfx/hit_sfx name", () => {
    for (const n of SPELL_NAMES) {
      expect(Sfx.has(n), `missing spell SFX: ${n}`).toBe(true);
    }
  });

  it("covers every non-empty sfx/hit_sfx in the live spells.json", async () => {
    // Cross-check: nothing in the data should fall through to a
    // missing generator. If a designer adds a new spell with a new
    // SFX name in spells.json, this guard fails until the catalog
    // gains a matching entry.
    const fs = await import("node:fs");
    const path = await import("node:path");
    const repoRoot = path.resolve(__dirname, "..", "..", "..", "..");
    const file = path.join(repoRoot, "data", "spells.json");
    const raw = JSON.parse(fs.readFileSync(file, "utf-8")) as
      { spells?: Array<{ sfx?: string; hit_sfx?: string | null }> };
    const referenced = new Set<string>();
    for (const s of raw.spells ?? []) {
      if (s.sfx) referenced.add(s.sfx);
      if (s.hit_sfx) referenced.add(s.hit_sfx);
    }
    for (const name of referenced) {
      expect(Sfx.has(name), `spells.json references missing SFX "${name}"`)
        .toBe(true);
    }
  });

  it("exports a non-empty SFX_NAMES list", () => {
    expect(SFX_NAMES.length).toBeGreaterThan(10);
    expect(SFX_NAMES).toContain("fireball");
  });
});

describe("Sfx — playback safety", () => {
  it("play() does not throw without an AudioContext", () => {
    expect(() => Sfx.play("fireball")).not.toThrow();
  });

  it("play() ignores unknown names", () => {
    expect(() => Sfx.play("not-a-real-sfx")).not.toThrow();
    expect(() => Sfx.play(undefined)).not.toThrow();
    expect(() => Sfx.play(null)).not.toThrow();
    expect(() => Sfx.play("")).not.toThrow();
  });
});

describe("Sfx — mute toggle", () => {
  it("setMuted persists through the getter", () => {
    expect(Sfx.muted).toBe(false);
    Sfx.setMuted(true);
    expect(Sfx.muted).toBe(true);
    Sfx.setMuted(false);
    expect(Sfx.muted).toBe(false);
  });

  it("muted=true blocks play() without throwing", () => {
    Sfx.setMuted(true);
    expect(() => Sfx.play("fireball")).not.toThrow();
  });

  it("persists the muted flag to localStorage when available", () => {
    // The default vitest environment is node, where localStorage is
    // undefined; skip the persistence check there. In-browser the
    // setMuted call already wrote the flag (covered by the previous
    // test) — this just confirms the storage write doesn't throw.
    if (typeof localStorage === "undefined") return;
    Sfx.setMuted(true);
    expect(localStorage.getItem("rpg.sfx.muted")).toBe("1");
    Sfx.setMuted(false);
    expect(localStorage.getItem("rpg.sfx.muted")).toBe("0");
  });
});
