import { describe, it, expect } from "vitest";
import { decorationFor } from "./Decorations";

describe("decorationFor", () => {
  it("returns null for empty / unknown / no-effect entries", () => {
    expect(decorationFor(null)).toBeNull();
    expect(decorationFor({})).toBeNull();
    expect(decorationFor({ effect: "(none)" })).toBeNull();
    expect(decorationFor({ effect: "totally_made_up" })).toBeNull();
  });

  it("maps known effect strings to glyph specs", () => {
    expect(decorationFor({ effect: "fire" })?.glyph).toBe("▲");
    expect(decorationFor({ effect: "fairy_light" })?.glyph).toBe("✦");
    expect(decorationFor({ effect: "rising_smoke" })?.glyph).toBe("≋");
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
