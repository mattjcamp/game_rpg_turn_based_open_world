/**
 * Headless tests for the Music manager.
 *
 * `Music.playArea()` is hard to exercise without a DOM (it constructs
 * `new Audio(...)` and reads `requestAnimationFrame`); these tests
 * focus on the pure parts: catalog shape, mute / volume getters and
 * setters, and localStorage persistence. The actual audio playback
 * is best verified manually in the browser.
 */

import { afterEach, beforeEach, describe, it, expect } from "vitest";
import {
  Music,
  MUSIC_TRACKS,
  setMuted,
  setVolume,
  _resetMusic,
} from "./Music";

const MUTED_KEY  = "rpg.music.muted";
const VOLUME_KEY = "rpg.music.volume";

beforeEach(() => {
  _resetMusic();
  // Reset the persisted state so each test starts from defaults.
  // localStorage is undefined under the node test env; guard the
  // cleanup so non-browser runs don't throw.
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(MUTED_KEY);
    localStorage.removeItem(VOLUME_KEY);
  }
  // Reset the in-memory state too (vitest doesn't reset module-scope
  // mutable state between cases; setMuted/setVolume call sites in
  // earlier tests would otherwise leak through).
  setMuted(false);
  setVolume(0.5);
});

afterEach(() => {
  _resetMusic();
});

describe("MUSIC_TRACKS catalog", () => {
  it("has an entry for each of the four game areas", () => {
    expect(Object.keys(MUSIC_TRACKS).sort()).toEqual([
      "combat", "dungeon", "overworld", "town",
    ]);
  });

  it("ships the two requested overworld tracks (Scepter + Aurelian)", () => {
    expect(MUSIC_TRACKS.overworld).toContain(
      "/audio/overworld/scepter_of_the_celestial_guardian.mp3",
    );
    expect(MUSIC_TRACKS.overworld).toContain(
      "/audio/overworld/aurelian_overture.mp3",
    );
  });

  it("ships exactly one track for each non-overworld area", () => {
    expect(MUSIC_TRACKS.combat).toHaveLength(1);
    expect(MUSIC_TRACKS.town).toHaveLength(1);
    expect(MUSIC_TRACKS.dungeon).toHaveLength(1);
  });

  it("every catalog URL is a /audio/<area>/<file>.mp3 path", () => {
    for (const [area, urls] of Object.entries(MUSIC_TRACKS)) {
      for (const u of urls) {
        expect(u).toMatch(new RegExp(`^/audio/${area}/[a-z0-9_]+\\.mp3$`));
      }
    }
  });
});

describe("Music.setMuted / Music.muted", () => {
  it("toggling mute updates the public getter", () => {
    setMuted(true);
    expect(Music.muted).toBe(true);
    setMuted(false);
    expect(Music.muted).toBe(false);
  });

  it("persists the preference to localStorage", () => {
    // Skip the persistence assertion under the node test env where
    // localStorage is undefined; the in-memory contract is exercised
    // by the previous test.
    if (typeof localStorage === "undefined") return;
    setMuted(true);
    expect(localStorage.getItem(MUTED_KEY)).toBe("1");
    setMuted(false);
    expect(localStorage.getItem(MUTED_KEY)).toBe("0");
  });

  it("coerces truthy / falsy values to booleans", () => {
    setMuted(1 as unknown as boolean);
    expect(Music.muted).toBe(true);
    setMuted(0 as unknown as boolean);
    expect(Music.muted).toBe(false);
  });
});

describe("Music.setVolume / Music.volume", () => {
  it("clamps values to [0, 1]", () => {
    setVolume(2);
    expect(Music.volume).toBe(1);
    setVolume(-0.5);
    expect(Music.volume).toBe(0);
    setVolume(0.42);
    expect(Music.volume).toBeCloseTo(0.42);
  });

  it("ignores non-finite inputs without changing state", () => {
    setVolume(0.7);
    setVolume(Number.NaN);
    expect(Music.volume).toBeCloseTo(0.7);
    setVolume(Number.POSITIVE_INFINITY);
    // Infinity is non-finite, so the setter rejects it and the
    // previous value persists.
    expect(Music.volume).toBeCloseTo(0.7);
  });

  it("persists the volume to localStorage", () => {
    if (typeof localStorage === "undefined") return;
    setVolume(0.33);
    expect(localStorage.getItem(VOLUME_KEY)).toBe("0.33");
  });
});

describe("Music.currentArea", () => {
  it("starts as null before any playArea call", () => {
    // _resetMusic() in beforeEach guarantees a clean slate.
    expect(Music.currentArea).toBeNull();
  });
});
