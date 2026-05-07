import { describe, it, expect } from "vitest";
import { decorationFor } from "./Decorations";

describe("decorationFor", () => {
  it("returns null for empty / unknown / no-effect entries", () => {
    expect(decorationFor(null)).toBeNull();
    expect(decorationFor({})).toBeNull();
    expect(decorationFor({ effect: "(none)" })).toBeNull();
    expect(decorationFor({ effect: "totally_made_up" })).toBeNull();
  });

  it("returns null for the animated effect kinds — TileEffects.ts owns them", () => {
    // These four used to render as static Unicode glyphs here; the
    // live animations in TileEffects.ts replace them.
    expect(decorationFor({ effect: "fire" })).toBeNull();
    expect(decorationFor({ effect: "torch" })).toBeNull();
    expect(decorationFor({ effect: "fairy_light" })).toBeNull();
    expect(decorationFor({ effect: "rising_smoke" })).toBeNull();
  });

  it("renders an item star when an item is present, even without effect", () => {
    const d = decorationFor({ item: "Torch" });
    expect(d?.glyph).toBe("★");
    expect(d?.color).toBe("#ffd470");
  });

  it("prefers the item star over the effect glyph if both are present", () => {
    expect(decorationFor({ item: "Sword", effect: "fire" })?.glyph).toBe("★");
  });
});
