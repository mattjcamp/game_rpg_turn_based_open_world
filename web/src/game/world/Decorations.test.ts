import { describe, it, expect } from "vitest";
import { decorationFor } from "./Decorations";
import type { Item } from "./Items";

/** Stand-in items catalog covering the icon types the tests touch. */
function items(): Map<string, Item> {
  const m = new Map<string, Item>();
  m.set("Torch",        { name: "Torch",        category: "general", icon: "torch" } as Item);
  m.set("Sword",        { name: "Sword",        category: "weapons", icon: "sword" } as Item);
  m.set("Healing Potion", { name: "Healing Potion", category: "general", icon: "potion" } as Item);
  m.set("Healing Herb", { name: "Healing Herb", category: "general", icon: "herb" } as Item);
  m.set("Arrows",       { name: "Arrows",       category: "general", icon: "ammo" } as Item);
  // Item without an icon field — should fall back to the generic star.
  m.set("Mystery Trinket", { name: "Mystery Trinket", category: "general" } as Item);
  return m;
}

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

  it("renders the generic gold star when no items catalog is supplied", () => {
    // Backwards-compat path — the helper still works without the
    // catalog (tests, scenes that haven't loaded items yet).
    const d = decorationFor({ item: "Torch" });
    expect(d?.glyph).toBe("★");
    expect(d?.color).toBe("#ffd470");
  });

  it("renders the per-icon glyph + colour when the items catalog is supplied", () => {
    const cat = items();
    const torch = decorationFor({ item: "Torch" }, cat);
    expect(torch?.glyph).toBe("♦");
    expect(torch?.color).toBe("#ffb84a");

    const sword = decorationFor({ item: "Sword" }, cat);
    expect(sword?.glyph).toBe("†");

    const potion = decorationFor({ item: "Healing Potion" }, cat);
    expect(potion?.glyph).toBe("♥");

    const herb = decorationFor({ item: "Healing Herb" }, cat);
    expect(herb?.glyph).toBe("✿");

    const arrows = decorationFor({ item: "Arrows" }, cat);
    expect(arrows?.glyph).toBe("▶");
  });

  it("falls back to the gold star for items the catalog doesn't know", () => {
    const d = decorationFor({ item: "Phantom Glaive" }, items());
    expect(d?.glyph).toBe("★");
    expect(d?.color).toBe("#ffd470");
  });

  it("falls back to the gold star when the item entry has no icon field", () => {
    // The catalog has the item but no icon hint — same fallback path.
    const d = decorationFor({ item: "Mystery Trinket" }, items());
    expect(d?.glyph).toBe("★");
  });

  it("prefers the item glyph over the effect glyph if both are present", () => {
    const d = decorationFor({ item: "Sword", effect: "fire" }, items());
    expect(d?.glyph).toBe("†");
  });

  it("attaches a stroke to every item decoration so it reads on any tile", () => {
    expect(decorationFor({ item: "Torch" })?.stroke).toBe("#1a1a2e");
    expect(decorationFor({ item: "Sword" }, items())?.stroke).toBe("#1a1a2e");
  });
});
