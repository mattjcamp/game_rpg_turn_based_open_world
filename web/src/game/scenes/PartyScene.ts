/**
 * Party Inventory screen — opened with the 'P' key from any map.
 *
 * Layout follows the Python game's `draw_party_inventory_u3`:
 *
 *   ┌────────────────── PARTY ──────────────────┐
 *   │ EFFECTS                │ PARTY [1-4]      │
 *   │ > Detect Traps         │ ┌───┐ 1 Gimli    │
 *   │   Infravision          │ │spr│ Fighter…   │
 *   │   Galadriel's Light    │ └───┘ HP ▓▓▓▓ MP │
 *   │ ──────                 │ … (×4)            │
 *   │ CAST SPELL             │ ──────            │
 *   │ ──────                 │ DETAIL OF         │
 *   │ SHARED STASH (n)       │ SELECTED ROW      │
 *   │   Healing Herb   ITEM  │                  │
 *   │   …                    │ GOLD: 25         │
 *   ├────────────────────────┴──────────────────┤
 *   │ [↑↓] select [↩] action [1-4] char [esc]   │
 *   └───────────────────────────────────────────┘
 *
 * Styling follows the rest of the web app — dark navy panels, warm
 * gold headers, parchment body text, monospace for stats. No Ultima 3
 * pixel fonts.
 *
 * Interaction:
 *   ↑ / ↓ : move the cursor through the left list
 *   Enter : trigger the selected row's action (placeholder for now —
 *           the action handlers come in a follow-up slice)
 *   1-4   : open the matching active member's detail sheet
 *   ESC   : back from detail to inventory; from inventory, close
 *   P     : close the screen unconditionally
 */

import Phaser from "phaser";
import { gameState } from "../state";
import {
  loadParty,
  activeMembers,
  type Party,
  type PartyMember,
} from "../world/Party";
import {
  loadClass,
  loadRaces,
  raceAbilities,
  type ClassTemplate,
  type RaceInfo,
} from "../world/Classes";
import { xpForNextLevel } from "../world/Leveling";
import { combatStatsFor } from "../combat/CombatBridge";
import {
  loadEffects,
  canEquip,
  type Effect,
} from "../world/Effects";
import {
  loadSpells,
  spellsCastableFromMenu,
  castersFor,
  minLevelFor,
  type Spell,
} from "../world/Spells";
import {
  assignEffectToParty,
  removeEffectFromParty,
  giveStashItemTo,
  returnItemToStash,
  castHealOnTarget,
  castMassHeal,
  castMagicLight,
  classifyMenuCast,
  equipItemFromInventory,
  equipItemIntoSlot,
  equippableSlots,
  unequipSlot,
  hasClass,
  hasRace,
  pickpocket,
  tinker,
  canTinker,
  getItemMaxDurability,
  getSlotDurability,
  consumeCampingSupplies,
  consumeTorch,
} from "../world/PartyActions";
import {
  loadItems,
  type Item,
  type EquipSlot,
} from "../world/Items";
import { loadCounters } from "../world/Counters";
import {
  loadPotions,
  recipeAvailability,
  attemptBrew,
  type Recipe,
} from "../world/Potions";
import { dayIndex } from "../world/GameTime";
import { assetUrl } from "../world/Module";
import { preloadPartyMemberSprites } from "../data/fighters";
import { Sfx } from "../audio/Sfx";

// Canvas
const W = 960;
const H = 720;

// Web-app theme palette (matches TownScene dialog + HUD bar).
const C = {
  bgFull:    0x0c0c14,   // overall overlay backdrop
  panel:     0x161629,   // panel fill
  panelEdge: 0x2a2a3a,   // subtle slate border
  accent:    0xc8553d,   // warm rust accent (selected / divider)
  gold:      0xffd470,   // header / title text
  body:      0xf6efd6,   // primary text
  dim:       0xbdb38a,   // secondary text
  faint:     0x6f6960,   // disabled text
  hpFull:    0x6acf6a,
  hpLow:     0xd14a4a,
  mp:        0x7aa6ff,
  divider:   0x2a2a3a,
  selectBg:  0x2a1f24,   // selected row background tint
} as const;

const hex = (n: number) => "#" + n.toString(16).padStart(6, "0");
const FONT_TITLE = (color: number = C.gold) => ({ fontFamily: "Georgia, serif", fontSize: "22px", color: hex(color) });
const FONT_HEAD  = (color: number = C.gold) => ({ fontFamily: "Georgia, serif", fontSize: "16px", color: hex(color) });
const FONT_BODY  = (color: number = C.body) => ({ fontFamily: "Georgia, serif", fontSize: "14px", color: hex(color) });
const FONT_MONO  = (color: number = C.dim)  => ({ fontFamily: "monospace",     fontSize: "12px", color: hex(color) });
const FONT_HINT  = (color: number = C.dim)  => ({ fontFamily: "monospace",     fontSize: "12px", color: hex(color) });

/**
 * Format the bonus on a damage roll for display: "+4", "-1", or ""
 * for zero. Used by the character sheet's Damage row to render
 * "1d6 +4" rather than "1d6 + 4" or "1d6 +0". Skipping the zero
 * bonus keeps unarmed / fists ("just 1") clean instead of "0d0 +1".
 */
function formatDamageBonus(bonus: number): string {
  if (bonus === 0) return "";
  return bonus > 0 ? ` +${bonus}` : ` ${bonus}`;
}

interface PartySceneData {
  /** Scene key to resume on close. */
  from?: string;
  /**
   * Stable per-NPC keys (`npcKey()` from state.ts) for every NPC in
   * the 8 cells around the party in the launching scene. Used by
   * the PICKPOCKET action to (a) confirm a target is in reach and
   * (b) refuse when every nearby NPC is already in
   * `gameState.pickpocketedNpcs`. The launching scene computes the
   * list before launching the overlay; OverworldScene passes [].
   */
  nearbyNpcKeys?: readonly string[];
}

/**
 * Sub-modes the screen can be in:
 *   - inventory:    default — left list, right party panel
 *   - spell-list:   CAST SPELL was activated; left panel shows spells
 *   - spell-target: a single-target spell is picked, waiting for 1-4
 *   - give-item:    a stash item is picked, waiting for 1-4 recipient
 *   - detail:       per-character drill-down (1-4 from any other mode)
 *   - equip-slot:   detail → Enter on a multi-slot item; waiting for
 *                   1-N to choose the destination slot
 */
type Mode =
  | "inventory" | "spell-list" | "spell-target" | "give-item"
  | "detail" | "equip-slot"
  /** Modal popup over detail/inventory: shows description + durability
   *  bar for the row the cursor was on. ESC/E/Enter dismisses. */
  | "examine"
  /** Gnome racial ability: shows a list of every general-store item
   *  and lets the player pick one to tinker into the stash. Open via
   *  the TINKER row; closes on Enter (commit) or ESC (cancel). */
  | "tinker-picker"
  /** Alchemist crafting: shows every loaded potion recipe with its
   *  reagent costs and DC; affordable recipes are highlighted, the
   *  rest are dimmed. Enter commits a brew (consuming reagents +
   *  rolling INT vs DC); ESC cancels. */
  | "brew-picker";

/**
 * One entry in the left-side list. Effects, the CAST SPELL row, and
 * stash items are unified so the cursor can travel through them all.
 */
type ListRow =
  | { kind: "effect"; effect: Effect; equipped: boolean; available: boolean }
  | { kind: "cast" }
  | { kind: "brew" }
  | { kind: "pickpocket" }
  | { kind: "tinker" }
  | { kind: "header"; label: string }
  | { kind: "item"; index: number; name: string; charges?: number };

/** Spell-list row form. Castable spells are highlighted; the rest
 *  are dimmed with a hint about why (no caster, level too low, etc.). */
type SpellRow = { spell: Spell; castable: boolean };

export class PartyScene extends Phaser.Scene {
  private from = "OverworldScene";
  /** NPCs within 1 tile (8-direction) of the party in the launching scene. */
  /**
   * Stable keys for every NPC the party can pickpocket from this
   * party-screen open. Empty when no NPCs are adjacent (or the
   * launching scene was the overworld). Drives both the
   * PICKPOCKET row's "ready / no targets" hint and the actual
   * `pickpocket()` call.
   */
  private nearbyNpcKeys: readonly string[] = [];
  private party: Party | null = null;
  private effects: Effect[] = [];
  private spells: Spell[] = [];
  private items: Map<string, Item> = new Map();
  /**
   * Deduped list of item names from counters.json's "general" entry.
   * Loaded once in create() so the Tinker picker (Gnome ability)
   * has a static menu to render. Kept as the array form for stable
   * cursor ordering, and a Set for fast `tinker()` validation.
   */
  private generalStockList: string[] = [];
  private generalStockSet: ReadonlySet<string> = new Set();
  /**
   * Tinker picker UI state. Active when `mode === "tinker-picker"`;
   * stores the cursor row and the list of items the player can pick
   * (same as `generalStockList`, just snapshotted at picker open so
   * it stays stable if counters somehow reload mid-pick).
   */
  private tinkerPickerCursor = 0;
  /**
   * Alchemist brew picker state. Loaded once on scene create() and
   * reused across picker opens — the JSON is static for the
   * session. `brewRecipeCursor` tracks the highlighted row.
   */
  private potionRecipes: Recipe[] = [];
  private brewRecipeCursor = 0;
  /** Class templates keyed by lowercase class name. Loaded once in
   *  create() so the XP-to-next-level lookup stays synchronous. */
  private classTemplates = new Map<string, ClassTemplate>();
  private races = new Map<string, RaceInfo>();

  /** Pre-compute "current XP / threshold" for a member if we have the
   *  class template loaded. Returns null when the template is missing
   *  so the renderer can fall back to a bare "EXP <n>" display. */
  private xpRowFor(m: PartyMember): { exp: number; need: number } | null {
    const tpl = this.classTemplates.get(m.class.toLowerCase());
    if (!tpl) return null;
    const race = this.races.get(m.race) ?? null;
    return { exp: m.exp, need: xpForNextLevel(m, tpl, race) };
  }
  private rows: ListRow[] = [];
  private selectable: number[] = []; // indices into rows[] that the cursor visits
  private cursor = 0;                 // index into selectable[]
  private mode: Mode = "inventory";
  private detailIndex = 0;
  /**
   * Detail-mode cursor position. Rows are: 0..3 = the four equipment
   * slots (right_hand, left_hand, body, head), then 4..(4+N-1) =
   * personal inventory entries.
   */
  private detailCursor = 0;
  /** Pixels the abilities region (Race / Class / Spells) is scrolled
   *  by. Wheel + PgUp/PgDn move it; switching the displayed character
   *  resets to 0 so each new sheet opens at the top. */
  private detailScroll = 0;
  /** Most recent maxScroll computed during render — used by the
   *  wheel/key handlers to clamp scroll attempts without recomputing
   *  the section heights. Stays in sync because every scroll change
   *  triggers a re-render which rewrites this value. */
  private detailScrollMax = 0;

  // Spell-list state
  private spellRows: SpellRow[] = [];
  private spellCursor = 0;
  /** Spell waiting on a target select (mode === "spell-target"). */
  private pendingSpell: Spell | null = null;

  // Give-item state — stash index of the item awaiting a recipient.
  private pendingGiveStashIndex: number | null = null;

  /**
   * Examine-popup state. `examineRow` describes what the player asked
   * to inspect — either an equipped slot on the current detail member
   * or an entry in their personal inventory. `examineFromMode` is the
   * mode to restore when the popup is dismissed.
   */
  private examineRow:
    | { kind: "slot"; slot: EquipSlot; itemName: string }
    | { kind: "personal"; index: number; entry: { item: string; durability?: number } }
    | { kind: "stash"; index: number; entry: { item: string; durability?: number } }
    | null = null;
  private examineFromMode: Mode | null = null;

  // Equip-slot state — when an item with 2+ candidate slots is picked,
  // we hold the personal-inventory index here while the player chooses
  // which slot to equip into.
  private pendingEquipIndex: number | null = null;
  private pendingEquipSlots: EquipSlot[] = [];

  /** Last action's feedback line. Cleared on next render trigger. */
  private feedback = "";

  private objects: Phaser.GameObjects.GameObject[] = [];

  constructor() { super({ key: "PartyScene" }); }

  init(data?: PartySceneData): void {
    this.from = data?.from ?? "OverworldScene";
    this.nearbyNpcKeys = data?.nearbyNpcKeys ?? [];
    this.mode = "inventory";
    this.cursor = 0;
    this.detailIndex = 0;
    this.detailCursor = 0;
    this.detailScroll = 0;
    this.detailScrollMax = 0;
    this.spellRows = [];
    this.spellCursor = 0;
    this.pendingSpell = null;
    this.pendingGiveStashIndex = null;
    this.pendingEquipIndex = null;
    this.pendingEquipSlots = [];
    this.feedback = "";
    this.objects = [];
  }

  preload(): void {
    for (const f of [
      "alchemist", "barbarian", "cleric", "fighter",
      "illusionist", "paladin", "ranger", "thief", "wizard",
    ]) {
      const path = assetUrl(`/assets/characters/${f}.png`);
      this.load.image(path, path);
    }
  }

  async create(): Promise<void> {
    try {
      if (!gameState.partyData) gameState.partyData = await loadParty();
      this.party = gameState.partyData;
      // The static class-sprite preload only covers the 9 shipped
      // class portraits. Players who picked an NPC / monster avatar
      // for their character would otherwise render as a grey
      // "missing texture" rectangle in the formation grid and the
      // detail panel.
      await preloadPartyMemberSprites(this, this.party);
      this.effects = await loadEffects();
      this.spells = await loadSpells();
      this.items = await loadItems();
      // Potion recipes back the Alchemist's BREW row. Loaded once
      // per scene boot; the recipe picker re-queries availability
      // against the live stash on each open. A missing/empty file
      // collapses the picker to "No recipes known" feedback.
      try { this.potionRecipes = await loadPotions(); } catch { /* keep empty */ }
      // Counters back the Tinker picker — a Gnome can produce any
      // item that normally appears in the General Store. We load
      // and dedupe the stock once so the picker UI has a stable
      // alphabetised list to render. A failure here just leaves
      // the list empty; the picker will show "no items available"
      // rather than crashing.
      try {
        const counters = await loadCounters();
        const general = counters.get("general");
        if (general) {
          const seen = new Set<string>(general.items);
          this.generalStockList = [...seen].sort();
          this.generalStockSet = seen;
        }
      } catch { /* counters absent — picker stays empty */ }
      // Class & race templates back the XP-to-next-level display.
      // Per-class fetches in parallel; a missing file is non-fatal —
      // the row falls back to "EXP <n>" without the threshold.
      try { this.races = await loadRaces(); } catch { /* keep empty */ }
      const klasses = new Set(activeMembers(this.party).map((m) => m.class));
      await Promise.all(
        [...klasses].map(async (k) => {
          try { this.classTemplates.set(k.toLowerCase(), await loadClass(k)); }
          catch { /* leave missing — display falls back gracefully */ }
        }),
      );
    } catch (err) {
      this.track(this.add.text(20, 20, `Failed to load party: ${(err as Error).message}`, FONT_BODY(C.hpLow)));
      return;
    }
    this.buildRows();
    this.installInput();
    this.render();
  }

  // ── Row construction ─────────────────────────────────────────────

  private buildRows(): void {
    if (!this.party) return;
    const members = activeMembers(this.party);
    const equippedIds = new Set(
      Object.values(this.party.partyEffects).filter((v): v is string => typeof v === "string")
    );

    const rows: ListRow[] = [];
    rows.push({ kind: "header", label: "EFFECTS" });
    for (const e of this.effects) {
      const equipped = equippedIds.has(e.id);
      const available = canEquip(e, members);
      rows.push({ kind: "effect", effect: e, equipped, available });
    }
    rows.push({ kind: "header", label: "" });
    rows.push({ kind: "cast" });

    // Conditional ability rows — show only when the appropriate
    // class / race is alive in the active party. Mirrors the Python
    // game's gating in inventory_mixin._can_pickpocket / _can_tinker
    // / _has_alchemist.
    if (hasClass(members, "Alchemist"))  rows.push({ kind: "brew" });
    if (hasRace(members,  "Halfling"))   rows.push({ kind: "pickpocket" });
    if (hasRace(members,  "Gnome"))      rows.push({ kind: "tinker" });

    rows.push({ kind: "header", label: "" });
    rows.push({ kind: "header", label: `SHARED STASH  (${this.party.inventory.length} items)` });
    this.party.inventory.forEach((it, i) => {
      rows.push({ kind: "item", index: i, name: it.item, charges: it.charges });
    });

    this.rows = rows;
    this.selectable = rows
      .map((r, i) => (r.kind === "header" ? -1 : i))
      .filter((i) => i >= 0);
    if (this.cursor >= this.selectable.length) this.cursor = 0;
  }

  // ── Input ────────────────────────────────────────────────────────

  private installInput(): void {
    const k = this.input.keyboard;
    if (!k) return;
    k.on("keydown-UP",    () => this.move(-1));
    k.on("keydown-DOWN",  () => this.move(1));
    k.on("keydown-W",     () => this.move(-1));
    k.on("keydown-S",     () => this.move(1));
    k.on("keydown-ONE",   () => this.pickMember(0));
    k.on("keydown-TWO",   () => this.pickMember(1));
    k.on("keydown-THREE", () => this.pickMember(2));
    k.on("keydown-FOUR",  () => this.pickMember(3));
    k.on("keydown-ENTER", () => this.activate());
    k.on("keydown-SPACE", () => this.activate());
    k.on("keydown-R",     () => this.returnSelected());
    k.on("keydown-E",     () => this.examineSelected());
    k.on("keydown-ESC",   () => this.escape());
    k.on("keydown-P",     () => this.close());
    // Page Up / Down scroll the abilities region in detail mode.
    // Up/Down arrows are already taken by the cursor walker, so
    // dedicated keys keep the two scopes from fighting.
    k.on("keydown-PAGE_UP",   () => this.scrollDetail(-90));
    k.on("keydown-PAGE_DOWN", () => this.scrollDetail(90));

    // Mouse wheel — only takes effect on the detail sheet so wheel
    // input on the inventory list keeps doing nothing surprising.
    this.input.on("wheel", (
      _pointer: Phaser.Input.Pointer,
      _objects: Phaser.GameObjects.GameObject[],
      _dx: number,
      dy: number,
    ) => {
      if (this.mode !== "detail") return;
      this.scrollDetail(dy);
    });
  }

  /**
   * Adjust `detailScroll` by `delta` pixels (positive = down) and
   * re-render so the band repositions. Clamps to [0, detailScrollMax],
   * bails out when there's nothing to scroll. Re-renders only when
   * the offset actually changed to keep the GameObject churn down.
   */
  private scrollDetail(delta: number): void {
    if (this.mode !== "detail") return;
    const before = this.detailScroll;
    const next = Math.max(
      0,
      Math.min(this.detailScrollMax, this.detailScroll + delta),
    );
    if (next === before) return;
    this.detailScroll = next;
    this.render();
  }

  private move(delta: number): void {
    if (this.mode === "inventory") {
      if (this.selectable.length === 0) return;
      this.cursor = (this.cursor + delta + this.selectable.length) % this.selectable.length;
      this.render();
      return;
    }
    if (this.mode === "spell-list") {
      if (this.spellRows.length === 0) return;
      this.spellCursor = (this.spellCursor + delta + this.spellRows.length) % this.spellRows.length;
      this.render();
      return;
    }
    if (this.mode === "detail") {
      const m = this.currentDetailMember();
      if (!m) return;
      const total = 4 + m.inventory.length;
      if (total === 0) return;
      this.detailCursor = (this.detailCursor + delta + total) % total;
      this.render();
      return;
    }
    if (this.mode === "tinker-picker") {
      const total = this.generalStockList.length;
      if (total === 0) return;
      this.tinkerPickerCursor = (this.tinkerPickerCursor + delta + total) % total;
      this.render();
      return;
    }
    if (this.mode === "brew-picker") {
      const total = this.potionRecipes.length;
      if (total === 0) return;
      this.brewRecipeCursor = (this.brewRecipeCursor + delta + total) % total;
      this.render();
      return;
    }
    // Other modes (target / give) have no list to scroll.
  }

  /** The member currently being viewed in detail mode, if any. */
  private currentDetailMember(): PartyMember | undefined {
    if (!this.party) return undefined;
    const members = activeMembers(this.party);
    return members[this.detailIndex];
  }

  /**
   * 0 → Hands (right_hand)
   * 1 → Body
   * 2..  → personal inventory index (cursor - 2)
   *
   * Offhand and head live in the EquipSlot type for forward compat
   * but don't show up here: the offhand slot didn't actually move
   * the dice in the current rules, so an empty "Offhand" row read
   * as broken rather than "coming soon". When the matching gameplay
   * lands, the rows + this index range grow back together.
   */
  private detailCursorKind(m: PartyMember): { kind: "slot"; slot: EquipSlot } | { kind: "item"; index: number } {
    void m;
    if (this.detailCursor < 2) {
      const slot: EquipSlot = (["right_hand", "body"] as const)[this.detailCursor];
      return { kind: "slot", slot };
    }
    return { kind: "item", index: this.detailCursor - 2 };
  }

  /**
   * Enter / Space — context-sensitive action based on the current
   * mode and the selected row.
   */
  private activate(): void {
    if (!this.party) return;
    if (this.mode === "examine") {
      // Enter dismisses the popup, just like ESC and E.
      this.mode = this.examineFromMode ?? "inventory";
      this.examineFromMode = null;
      this.examineRow = null;
      this.render();
      return;
    }
    if (this.mode === "inventory") return this.activateInventoryRow();
    if (this.mode === "spell-list") return this.activateSpellRow();
    if (this.mode === "detail") return this.activateDetailRow();
    if (this.mode === "tinker-picker") return this.activateTinkerPick();
    if (this.mode === "brew-picker") return this.activateBrewPick();
    // Target prompts and give-item prompts are answered with 1-4,
    // not Enter — Enter is a no-op there.
  }

  /**
   * Commit the current tinker picker selection: hand off to the
   * `tinker()` action, surface its message, and close the picker.
   * Refusal cases (already tinkered, no Gnome) are caught by
   * `canTinker` upstream — but tinker() defends against them too,
   * so a stale UI state still shows a friendly message instead of
   * silently dropping an extra item.
   */
  private activateTinkerPick(): void {
    if (!this.party) return;
    const itemName = this.generalStockList[this.tinkerPickerCursor];
    if (!itemName) {
      this.mode = "inventory";
      this.render();
      return;
    }
    const members = activeMembers(this.party);
    const today = dayIndex(gameState.clock);
    const r = tinker(this.party, members, itemName, today, this.generalStockSet, this.items);
    if (r.ok) Sfx.play("chirp");
    this.feedback = r.message;
    this.mode = "inventory";
    this.buildRows();
    this.render();
  }

  /**
   * Commit the current brew picker selection: hand off to
   * `attemptBrew`, surface its message, and close the picker.
   * Refuses (with a feedback line, not a crash) when the recipe is
   * unaffordable — the picker dims those rows but a player who
   * mashes Enter on a dim row deserves a clear "missing X, Y" hint
   * rather than silent consumption of reagents that don't exist.
   */
  private activateBrewPick(): void {
    if (!this.party) return;
    const recipe = this.potionRecipes[this.brewRecipeCursor];
    if (!recipe) {
      this.mode = "inventory";
      this.render();
      return;
    }
    const members = activeMembers(this.party);
    const avail = recipeAvailability(this.party, recipe);
    if (!avail.affordable) {
      this.feedback = `Missing reagents: ${avail.missing.join(", ")}.`;
      this.render();
      return;
    }
    const r = attemptBrew(this.party, members, recipe);
    if (r.success) Sfx.play("heal");
    else if (r.success === false) Sfx.play("miss");
    this.feedback = r.message;
    this.mode = "inventory";
    this.buildRows();
    this.render();
  }

  /**
   * Detail-mode Enter:
   *   - On an equipped slot: unequip it (item drops into inventory).
   *   - On a personal inventory item:
   *       * If the item has only one accepting slot, equip it there.
   *       * If the item accepts two or more slots (a dagger in either
   *         hand, a versatile weapon), enter "equip-slot" mode and
   *         let the player pick.
   */
  private activateDetailRow(): void {
    const m = this.currentDetailMember();
    if (!m) return;
    const sel = this.detailCursorKind(m);
    if (sel.kind === "slot") {
      const r = unequipSlot(m, sel.slot, this.items);
      this.feedback = r.message;
      this.clampDetailCursor(m);
      this.render();
      return;
    }

    // Personal-inventory row.
    const inv = m.inventory[sel.index];
    if (!inv) return;
    const def = this.items.get(inv.item);
    // Filter to UI-supported slots so a head-only item routes through
    // the auto path (where equipItemFromInventory refuses politely)
    // instead of opening a slot prompt for a slot the UI doesn't show.
    const slots: EquipSlot[] = def ? equippableSlots(def) : [];

    if (slots.length >= 2) {
      // Multi-slot item — prompt for the destination.
      this.pendingEquipIndex = sel.index;
      this.pendingEquipSlots = slots;
      this.mode = "equip-slot";
      this.feedback = "";
      this.render();
      return;
    }

    // Single-slot or non-equippable — fall through to the auto path
    // (refuses politely with feedback when not equippable).
    const r = equipItemFromInventory(m, sel.index, this.items);
    this.feedback = r.message;
    this.clampDetailCursor(m);
    this.render();
  }

  /**
   * Slot picker — the player has chosen the n-th slot from
   * `pendingEquipSlots`. Equip into that slot, then back to detail.
   */
  private pickEquipSlot(slotIdx: number): void {
    const m = this.currentDetailMember();
    if (!m) return;
    if (this.pendingEquipIndex == null) return;
    const slot = this.pendingEquipSlots[slotIdx];
    if (slot === undefined) return; // out of range — ignore
    const r = equipItemIntoSlot(m, this.pendingEquipIndex, slot, this.items);
    this.feedback = r.message;
    this.pendingEquipIndex = null;
    this.pendingEquipSlots = [];
    this.mode = "detail";
    this.clampDetailCursor(m);
    this.render();
  }

  /**
   * 'R' — return-to-stash secondary action. Works on either an
   * equipped slot (unequips first) or a personal inventory item
   * (just moves it).
   */
  private returnSelected(): void {
    if (!this.party || this.mode !== "detail") return;
    const m = this.currentDetailMember();
    if (!m) return;
    const sel = this.detailCursorKind(m);
    if (sel.kind === "slot") {
      // Unequip into inventory then move that fresh inventory entry
      // (last index) into the shared stash.
      const u = unequipSlot(m, sel.slot, this.items);
      if (!u.ok || m.inventory.length === 0) {
        this.feedback = u.message;
        this.render();
        return;
      }
      const r = returnItemToStash(this.party, this.detailIndex, m.inventory.length - 1);
      this.feedback = r.ok
        ? `${u.message.replace(/\.$/, "")}, then returned to stash.`
        : r.message;
    } else {
      const r = returnItemToStash(this.party, this.detailIndex, sel.index);
      this.feedback = r.message;
    }
    this.clampDetailCursor(m);
    this.render();
  }

  /**
   * E key — open the inspect popup for whatever the cursor is on.
   *
   * Works in three contexts:
   *   - examine mode itself: dismiss (toggle off).
   *   - detail mode: inspect the equipped slot or personal-inventory
   *     entry the detailCursor points at.
   *   - inventory mode: inspect a stash item the main cursor is on
   *     (skips effects / spell rows / ability rows — those don't have
   *     durability state to show).
   */
  private examineSelected(): void {
    if (this.mode === "examine") {
      // Toggle dismiss.
      this.mode = this.examineFromMode ?? "inventory";
      this.examineFromMode = null;
      this.examineRow = null;
      this.render();
      return;
    }
    if (this.mode === "detail" && this.party) {
      const m = this.currentDetailMember();
      if (!m) return;
      const sel = this.detailCursorKind(m);
      if (sel.kind === "slot") {
        const itemName = (() => {
          const SLOT_TO_FIELD = {
            right_hand: "rightHand",
            left_hand:  "leftHand",
            body:       "body",
            head:       "head",
          } as const;
          return m.equipped[SLOT_TO_FIELD[sel.slot]];
        })();
        if (!itemName) {
          this.feedback = "Slot is empty.";
          this.render();
          return;
        }
        this.examineFromMode = this.mode;
        this.examineRow = { kind: "slot", slot: sel.slot, itemName };
        this.mode = "examine";
        this.render();
        return;
      }
      const entry = m.inventory[sel.index];
      if (!entry) return;
      this.examineFromMode = this.mode;
      this.examineRow = { kind: "personal", index: sel.index, entry };
      this.mode = "examine";
      this.render();
      return;
    }
    if (this.mode === "inventory" && this.party) {
      const row = this.rows[this.selectable[this.cursor] ?? -1];
      if (!row || row.kind !== "item") {
        this.feedback = "Press E on an item to inspect it.";
        this.render();
        return;
      }
      const entry = this.party.inventory[row.index];
      if (!entry) return;
      this.examineFromMode = this.mode;
      this.examineRow = { kind: "stash", index: row.index, entry };
      this.mode = "examine";
      this.render();
      return;
    }
  }

  private clampDetailCursor(m: PartyMember): void {
    const total = 4 + m.inventory.length;
    if (total === 0) { this.detailCursor = 0; return; }
    if (this.detailCursor >= total) this.detailCursor = total - 1;
    if (this.detailCursor < 0) this.detailCursor = 0;
  }

  private activateInventoryRow(): void {
    if (!this.party) return;
    const row = this.rows[this.selectable[this.cursor] ?? -1];
    if (!row) return;
    const members = activeMembers(this.party);

    if (row.kind === "effect") {
      const result = row.equipped
        ? removeEffectFromParty(this.party, row.effect)
        : assignEffectToParty(this.party, row.effect, members);
      this.feedback = result.message;
      this.buildRows(); // equipped flag changes
      this.render();
      return;
    }

    if (row.kind === "cast") {
      this.openSpellList();
      return;
    }

    if (row.kind === "brew") {
      // Alchemist's BREW POTIONS row → recipe picker. Refuses early
      // when no Alchemist is in the party or no recipes loaded so
      // the player isn't dropped into an empty modal.
      if (!hasClass(members, "Alchemist")) {
        this.feedback = "No Alchemist in the party.";
        this.render();
        return;
      }
      if (this.potionRecipes.length === 0) {
        this.feedback = "No recipes known.";
        this.render();
        return;
      }
      this.brewRecipeCursor = 0;
      this.mode = "brew-picker";
      this.feedback = "";
      this.render();
      return;
    }
    if (row.kind === "pickpocket") {
      // Pickpocket is gated three ways:
      //   1. There must be at least one NPC adjacent.
      //   2. That NPC must not already be in
      //      `gameState.pickpocketedNpcs` (once-per-NPC rule).
      //   3. There must be a Halfling in the active party (the
      //      action helper enforces this last one).
      // The action helper handles 1 + 2 internally and returns
      // `pickedKey` when it commits — we stamp it into the gate
      // Set on success so future opens see this NPC as spent.
      const r = pickpocket(
        this.party,
        members,
        this.nearbyNpcKeys,
        gameState.pickpocketedNpcs,
      );
      if (r.ok && r.pickedKey) {
        gameState.pickpocketedNpcs.add(r.pickedKey);
      }
      this.feedback = r.message;
      this.buildRows();
      this.render();
      return;
    }
    if (row.kind === "tinker") {
      // Daily-gate the ability up front: if the party already
      // tinkered today, surface the refusal here rather than
      // making the player browse the picker for nothing.
      const today = dayIndex(gameState.clock);
      if (!canTinker(this.party, members, today)) {
        const gnome = members.find((m) => m.race === "Gnome");
        this.feedback = gnome
          ? `${gnome.name} has already tinkered today — try again tomorrow.`
          : "No Gnome in the party.";
        this.render();
        return;
      }
      if (this.generalStockList.length === 0) {
        this.feedback = "Tinkering needs a general-store catalog (counters.json missing or empty).";
        this.render();
        return;
      }
      this.tinkerPickerCursor = 0;
      this.mode = "tinker-picker";
      this.render();
      return;
    }

    if (row.kind === "item") {
      // Party-wide consumables short-circuit the give-item flow:
      // pressing Enter on Camping Supplies / Torch uses them on the
      // whole party rather than handing them to a single character.
      // Sfx and a one-line feedback string keep things lightweight —
      // a fancier "USED!" toast is a future polish step.
      if (row.name === "Camping Supplies") {
        const r = consumeCampingSupplies(this.party);
        if (r.ok) Sfx.play("heal");
        this.feedback = r.message;
        this.buildRows();
        this.render();
        return;
      }
      if (row.name === "Torch") {
        const r = consumeTorch(this.party);
        if (r.ok) Sfx.play("chirp");
        this.feedback = r.message;
        this.buildRows();
        this.render();
        return;
      }
      this.pendingGiveStashIndex = row.index;
      this.mode = "give-item";
      this.render();
      return;
    }
  }

  private activateSpellRow(): void {
    if (!this.party) return;
    const sr = this.spellRows[this.spellCursor];
    if (!sr || !sr.castable) {
      this.feedback = sr ? `${sr.spell.name} cannot be cast right now.` : "";
      this.render();
      return;
    }
    const kind = classifyMenuCast(sr.spell);
    const members = activeMembers(this.party);
    if (kind === "single-ally") {
      this.pendingSpell = sr.spell;
      this.mode = "spell-target";
      this.render();
      return;
    }
    if (kind === "mass") {
      const result = castMassHeal(this.party, members, sr.spell);
      this.feedback = result.message;
      this.mode = "inventory";
      this.buildRows();
      this.render();
      return;
    }
    if (kind === "self") {
      // Self-cast utility spells — currently Light, which feeds the
      // party's torch-step counter so the lighting overlay treats it
      // like a magic torch. No target prompt, just MP + state mutation
      // and a feedback line. Other self-cast spells will route through
      // the same dispatch as they're added.
      if (sr.spell.effect_type === "magic_light") {
        const result = castMagicLight(this.party, members, sr.spell);
        this.feedback = result.message;
        this.mode = "inventory";
        this.buildRows();
        this.render();
        return;
      }
      // Self-cast spells we recognise but haven't wired yet — keep the
      // unsupported fallback rather than silently consuming MP.
      this.feedback = `${sr.spell.name} has no effect outside combat (yet).`;
      this.render();
      return;
    }
    // Unsupported in the menu (knock, reveal_map…) — give a polite
    // line so the player knows the spell is real but not wired up
    // out of combat yet.
    this.feedback = `${sr.spell.name} has no effect outside combat (yet).`;
    this.render();
  }

  private openSpellList(): void {
    if (!this.party) return;
    const members = activeMembers(this.party);
    const castable = spellsCastableFromMenu(this.spells, members);
    const castableIds = new Set(castable.map((s) => s.id));
    // Filter to spells the active party has at least *learned* — i.e.
    // some member's class allows the spell AND that member meets its
    // min_level. Higher-level spells nobody has unlocked yet are
    // hidden entirely, not greyed out, so a level-1 wizard doesn't see
    // Fireball staring back at them. MP-shortfall and similar runtime
    // gates still flow through the `castable` flag below.
    const learned = this.spells.filter((s) =>
      s.usable_in.some((c) => c !== "battle") &&
      members.some(
        (m) =>
          s.allowable_classes.includes(m.class) &&
          m.level >= minLevelFor(s, m.class),
      ),
    );
    this.spellRows = learned.map((s) => ({
      spell: s, castable: castableIds.has(s.id),
    }));
    // Sort: castable first, then by name.
    this.spellRows.sort((a, b) =>
      Number(b.castable) - Number(a.castable) || a.spell.name.localeCompare(b.spell.name)
    );
    this.spellCursor = 0;
    this.mode = "spell-list";
    this.feedback = "";
    this.render();
  }

  /**
   * 1-4 dispatch — the meaning depends on the current mode:
   *   - spell-target: pick the heal target
   *   - give-item:    pick the recipient
   *   - any other:    open the per-character detail sheet
   */
  private pickMember(idx: number): void {
    if (!this.party) return;

    // In equip-slot mode the 1-N keys pick a destination slot, not
    // a party member. Resolve and bail out before the default path.
    if (this.mode === "equip-slot") {
      this.pickEquipSlot(idx);
      return;
    }

    const members = activeMembers(this.party);
    if (idx < 0 || idx >= members.length) return;

    if (this.mode === "spell-target" && this.pendingSpell) {
      const result = castHealOnTarget(this.party, members, this.pendingSpell, idx);
      this.feedback = result.message;
      this.pendingSpell = null;
      this.mode = "inventory";
      this.buildRows();
      this.render();
      return;
    }

    if (this.mode === "give-item" && this.pendingGiveStashIndex != null) {
      const result = giveStashItemTo(this.party, this.pendingGiveStashIndex, idx);
      this.feedback = result.message;
      this.pendingGiveStashIndex = null;
      this.mode = "inventory";
      this.buildRows();
      this.render();
      return;
    }

    // Default: open detail sheet (works from inventory, spell-list, detail).
    this.detailIndex = idx;
    this.detailCursor = 0;
    // Reset the abilities-region scroll so each character opens at
    // the top — surprising otherwise when the previous character had
    // a long Spells list and we landed mid-scroll on the new one.
    this.detailScroll = 0;
    this.mode = "detail";
    this.render();
  }

  private escape(): void {
    if (this.mode === "examine") {
      // Dismiss the popup; restore whatever mode we came from. We
      // stash the prior mode on `examineFromMode` when opening.
      this.mode = this.examineFromMode ?? "inventory";
      this.examineFromMode = null;
      this.examineRow = null;
      this.feedback = "";
      this.render();
      return;
    }
    if (this.mode === "spell-target") {
      this.pendingSpell = null;
      this.mode = "spell-list";
      this.feedback = "";
      this.render();
      return;
    }
    if (this.mode === "give-item") {
      this.pendingGiveStashIndex = null;
      this.mode = "inventory";
      this.feedback = "";
      this.render();
      return;
    }
    if (this.mode === "spell-list") {
      this.mode = "inventory";
      this.feedback = "";
      this.render();
      return;
    }
    if (this.mode === "equip-slot") {
      this.pendingEquipIndex = null;
      this.pendingEquipSlots = [];
      this.mode = "detail";
      this.feedback = "";
      this.render();
      return;
    }
    if (this.mode === "detail") {
      this.mode = "inventory";
      this.render();
      return;
    }
    if (this.mode === "tinker-picker") {
      this.mode = "inventory";
      this.feedback = "";
      this.render();
      return;
    }
    if (this.mode === "brew-picker") {
      this.mode = "inventory";
      this.feedback = "";
      this.render();
      return;
    }
    this.close();
  }

  private close(): void {
    this.scene.stop();
    this.scene.resume(this.from);
  }

  // ── Render helpers ───────────────────────────────────────────────

  private track<T extends Phaser.GameObjects.GameObject>(o: T): T {
    this.objects.push(o);
    return o;
  }

  private panel(x: number, y: number, w: number, h: number): void {
    this.track(
      this.add.rectangle(x, y, w, h, C.panel, 0.96)
        .setOrigin(0)
        .setStrokeStyle(2, C.panelEdge)
    );
  }

  private bar(
    x: number, y: number, w: number, h: number,
    cur: number, max: number, color: number,
  ): void {
    this.track(this.add.rectangle(x, y, w, h, 0x1c1c2a, 1).setOrigin(0));
    const fillW = max > 0 ? Math.max(1, Math.floor((w - 2) * cur / max)) : 0;
    if (fillW > 0) {
      this.track(this.add.rectangle(x + 1, y + 1, fillW, h - 2, color, 1).setOrigin(0));
    }
  }

  private text(
    x: number, y: number, content: string,
    style: Phaser.Types.GameObjects.Text.TextStyle,
    origin: [number, number] = [0, 0],
    wrapWidth?: number,
  ): Phaser.GameObjects.Text {
    const finalStyle = wrapWidth
      ? { ...style, wordWrap: { width: wrapWidth, useAdvancedWrap: true } }
      : style;
    return this.track(this.add.text(x, y, content, finalStyle).setOrigin(origin[0], origin[1]));
  }

  private divider(x: number, y: number, w: number): void {
    this.track(this.add.rectangle(x, y, w, 1, C.divider, 1).setOrigin(0));
  }

  private titleBar(label: string): void {
    this.panel(8, 8, W - 16, 36);
    this.text(W / 2, 16, label, FONT_TITLE(), [0.5, 0]);
  }

  private hintBar(label: string): void {
    const y = H - 32;
    this.panel(8, y, W - 16, 24);
    this.text(20, y + 6, label, FONT_HINT());
  }

  private render(): void {
    for (const o of this.objects) o.destroy();
    this.objects = [];
    if (!this.party) return;
    // Full-screen dim backdrop.
    this.track(this.add.rectangle(0, 0, W, H, C.bgFull, 0.94).setOrigin(0));
    // Detail and equip-slot share the per-character sheet layout —
    // equip-slot is an overlay prompt that lives inside the detail
    // panels (rust-outlined slot rows + slot prompt in the action
    // hint footer). Anything else uses the inventory layout (which
    // covers spell-list, spell-target, and give-item — all of which
    // are overlays inside the inventory panels).
    if (this.mode === "detail" || this.mode === "equip-slot") {
      this.renderDetail();
      return;
    }
    if (this.mode === "examine") {
      // Draw the underlying screen first so the popup floats over it.
      if (this.examineFromMode === "detail") this.renderDetail();
      else this.renderInventory();
      this.renderExamine();
      return;
    }
    if (this.mode === "tinker-picker") {
      // Render the inventory layout underneath so the picker reads
      // as a modal — same pattern give-item / spell-target use.
      this.renderInventory();
      this.renderTinkerPicker();
      return;
    }
    if (this.mode === "brew-picker") {
      this.renderInventory();
      this.renderBrewPicker();
      return;
    }
    this.renderInventory();
  }

  /**
   * Modal picker for the Gnome's daily tinker. Shows every general-
   * store item the player can pick from, vertically-scrollable with
   * a window-shifting cursor (matches the throw / spell pickers in
   * CombatScene). Enter commits, ESC cancels.
   */
  private renderTinkerPicker(): void {
    const W_BOX = 320;
    const H_BOX = 360;
    const X = (W - W_BOX) / 2;
    const Y = (H - H_BOX) / 2;
    // Backdrop + frame.
    this.track(
      this.add.rectangle(X, Y, W_BOX, H_BOX, 0x161629, 0.97).setOrigin(0)
        .setStrokeStyle(2, C.gold),
    );
    this.track(this.add.text(X + 16, Y + 12, "TINKER", FONT_HEAD(C.gold)));
    this.track(this.add.text(
      X + 16, Y + 36,
      "Pick one item from the general-store catalog.",
      FONT_BODY(C.dim),
    ));
    // Scroll window — show ~12 rows at a time, keep cursor in view.
    const ROW_H = 20;
    const VISIBLE = 12;
    const list = this.generalStockList;
    const cursor = this.tinkerPickerCursor;
    let scroll = Math.max(0, cursor - Math.floor(VISIBLE / 2));
    scroll = Math.min(scroll, Math.max(0, list.length - VISIBLE));
    const top = Y + 64;
    for (let i = 0; i < Math.min(VISIBLE, list.length); i++) {
      const idx = scroll + i;
      const name = list[idx];
      if (!name) break;
      const isCursor = idx === cursor;
      const rowY = top + i * ROW_H;
      if (isCursor) {
        this.track(
          this.add.rectangle(X + 8, rowY - 2, W_BOX - 16, ROW_H, C.selectBg, 1).setOrigin(0),
        );
      }
      const prefix = isCursor ? "> " : "  ";
      this.track(this.add.text(
        X + 16, rowY,
        `${prefix}${name}`,
        FONT_BODY(isCursor ? C.body : C.dim),
      ));
    }
    // Scroll arrows when there's more above / below the window.
    if (scroll > 0) {
      this.track(this.add.text(X + W_BOX - 24, top - 18, "▲", FONT_MONO(C.gold)));
    }
    if (scroll + VISIBLE < list.length) {
      this.track(
        this.add.text(X + W_BOX - 24, top + VISIBLE * ROW_H + 4, "▼", FONT_MONO(C.gold)),
      );
    }
    // Footer hint.
    this.track(this.add.text(
      X + 16, Y + H_BOX - 24,
      "[↑↓] select   [Enter] tinker   [ESC] cancel",
      FONT_HINT(),
    ));
  }

  /**
   * Modal picker for the Alchemist's BREW POTIONS row. Each row
   * shows the recipe name, DC, and reagent costs. Affordable
   * recipes render in body colour; the rest are dimmed with a
   * "missing X" hint so the player can see what to forage next.
   * Enter commits a brew (consuming reagents + rolling INT vs DC);
   * ESC cancels.
   */
  private renderBrewPicker(): void {
    if (!this.party) return;
    const W_BOX = 480;
    const H_BOX = 380;
    const X = (W - W_BOX) / 2;
    const Y = (H - H_BOX) / 2;
    this.track(
      this.add.rectangle(X, Y, W_BOX, H_BOX, 0x161629, 0.97).setOrigin(0)
        .setStrokeStyle(2, C.gold),
    );
    this.text(X + 16, Y + 12, "BREW POTIONS", FONT_HEAD(C.gold));
    this.text(
      X + 16, Y + 36,
      "Pick a recipe to brew. Reagents are consumed; an INT check decides success.",
      FONT_BODY(C.dim),
    );

    const recipes = this.potionRecipes;
    const ROW_H = 36;
    const VISIBLE = 7;
    const cursor = this.brewRecipeCursor;
    let scroll = Math.max(0, cursor - Math.floor(VISIBLE / 2));
    scroll = Math.min(scroll, Math.max(0, recipes.length - VISIBLE));
    const top = Y + 70;

    for (let i = 0; i < Math.min(VISIBLE, recipes.length); i++) {
      const idx = scroll + i;
      const recipe = recipes[idx];
      if (!recipe) break;
      const avail = recipeAvailability(this.party, recipe);
      const isCursor = idx === cursor;
      const rowY = top + i * ROW_H;
      if (isCursor) {
        this.track(
          this.add.rectangle(X + 8, rowY - 2, W_BOX - 16, ROW_H, C.selectBg, 1)
            .setOrigin(0),
        );
      }
      const prefix = isCursor ? "> " : "  ";
      // Recipe name on the left, DC right-aligned. Body colour when
      // affordable, faint when missing reagents.
      this.text(
        X + 16, rowY,
        `${prefix}${recipe.name}`,
        FONT_BODY(avail.affordable ? C.body : C.faint),
      );
      this.text(
        X + W_BOX - 16, rowY,
        `DC ${recipe.dc}`,
        FONT_MONO(avail.affordable ? C.gold : C.faint),
        [1, 0],
      );
      // Reagent breakdown — "Moonpetal x1 · Spring Water x1" or
      // "missing: Moonpetal" when short.
      const reagentText = Object.entries(recipe.reagents)
        .map(([name, qty]) => `${name} x${qty}`)
        .join("  ·  ");
      this.text(
        X + 32, rowY + 16,
        avail.affordable
          ? reagentText
          : `missing: ${avail.missing.join(", ")}`,
        FONT_MONO(avail.affordable ? C.dim : C.faint),
      );
    }

    if (scroll > 0) {
      this.text(X + W_BOX - 24, top - 18, "▲", FONT_MONO(C.gold));
    }
    if (scroll + VISIBLE < recipes.length) {
      this.text(X + W_BOX - 24, top + VISIBLE * ROW_H + 4, "▼", FONT_MONO(C.gold));
    }
    // Footer hint.
    this.text(
      X + 16, Y + H_BOX - 24,
      "[↑↓] select   [Enter] brew   [ESC] cancel",
      FONT_HINT(),
    );
  }

  /**
   * Floating popup with item description + durability bar. Reads
   * durability live from the equippedDurability tracker (slot rows)
   * or InventoryItem.durability (stash / personal entries).
   */
  private renderExamine(): void {
    if (!this.party || !this.examineRow) return;
    const itemName = this.examineRow.kind === "slot"
      ? this.examineRow.itemName
      : this.examineRow.entry.item;
    const def = this.items.get(itemName);

    // Resolve current/max durability.
    let cur: number | null = null;
    let max: number | null = null;
    if (this.examineRow.kind === "slot") {
      const m = this.currentDetailMember();
      if (m) {
        const d = getSlotDurability(m, this.examineRow.slot, this.items);
        if (d) { cur = d.current; max = d.max; }
      }
    } else {
      max = getItemMaxDurability(itemName, this.items);
      if (max != null) {
        cur = this.examineRow.entry.durability ?? max;
        if (cur > max) cur = max;
      }
    }

    const w = 420, h = 240;
    const x = (W - w) / 2;
    const y = (H - h) / 2;
    this.track(this.add.rectangle(x, y, w, h, 0x10101a, 0.98)
      .setOrigin(0)
      .setStrokeStyle(2, C.accent));
    this.track(this.add.text(x + 14, y + 10, "INSPECT", FONT_HEAD(C.accent)));

    // Item name.
    this.track(this.add.text(x + 14, y + 40, itemName, FONT_HEAD(C.gold)));

    // Slot list.
    const slots = def?.slots ?? [];
    const slotsLine = slots.length
      ? `Slots: ${slots.map((s) => s.replace("_", " ")).join(", ")}`
      : "Slots: —";
    this.track(this.add.text(x + 14, y + 64, slotsLine, FONT_MONO(C.dim)));

    // Description (wrap by hand — the existing scene's text helpers
    // don't expose wordWrap).
    const desc = def?.description ?? "(No description.)";
    this.track(this.add.text(x + 14, y + 88, desc, {
      ...FONT_BODY(),
      wordWrap: { width: w - 28 },
    }));

    // Durability bar.
    const barX = x + 14;
    const barY = y + h - 56;
    const barW = w - 28;
    const barH = 14;
    this.track(this.add.text(barX, barY - 18, "Durability", FONT_MONO(C.dim)));
    if (max == null) {
      this.track(this.add.text(barX, barY, "Indestructible", FONT_MONO(C.gold)));
    } else if (cur == null) {
      this.track(this.add.text(barX, barY, `${max} / ${max}`, FONT_MONO()));
    } else {
      // Background frame.
      this.track(this.add.rectangle(barX, barY, barW, barH, 0x1c1c2a, 1)
        .setOrigin(0)
        .setStrokeStyle(1, C.panelEdge));
      // Filled portion, colour by remaining %.
      const pct = Math.max(0, Math.min(1, cur / max));
      const col = pct > 0.66 ? 0x6dbf60 : pct > 0.33 ? 0xddc05c : 0xd86a4a;
      this.track(this.add.rectangle(barX + 1, barY + 1,
                                    Math.max(0, (barW - 2) * pct), barH - 2,
                                    col, 1).setOrigin(0));
      this.track(this.add.text(barX + barW, barY + barH + 2,
                               `${cur} / ${max}`,
                               FONT_MONO(C.dim)).setOrigin(1, 0));
    }

    // Footer hint.
    this.track(this.add.text(x + 14, y + h - 22,
                             "[E] / [ESC] / [Enter] close",
                             FONT_MONO(C.dim)));
  }

  // ── Inventory mode ───────────────────────────────────────────────

  private renderInventory(): void {
    if (!this.party) return;
    this.titleBar(this.titleForMode());

    const top = 52;
    const bottom = H - 40;
    const leftX = 8;
    const leftW = (W * 0.55) | 0;            // 528
    const rightX = leftX + leftW + 8;
    const rightW = W - rightX - 8;            // ≈ 408
    const panelH = bottom - top;

    this.panel(leftX, top, leftW, panelH);
    this.panel(rightX, top, rightW, panelH);

    if (this.mode === "spell-list") {
      this.renderSpellListColumn(leftX, top, leftW, panelH);
    } else {
      this.renderListColumn(leftX, top, leftW, panelH);
    }
    this.renderPartyColumn(rightX, top, rightW, panelH);

    // Mode-aware hint bar.
    this.hintBar(this.hintForMode());
  }

  private titleForMode(): string {
    switch (this.mode) {
      case "spell-list":    return "PARTY  ·  CAST SPELL";
      case "spell-target":  return `PARTY  ·  ${this.pendingSpell?.name ?? "Cast"}  —  pick a target`;
      case "give-item":     return "PARTY  ·  Give item — pick a recipient";
      case "tinker-picker": return "PARTY  ·  TINKER";
      case "brew-picker":   return "PARTY  ·  BREW POTIONS";
      default:              return "PARTY";
    }
  }

  private hintForMode(): string {
    switch (this.mode) {
      case "spell-list":
        return "[↑↓] select   [Enter] cast   [ESC] back";
      case "spell-target":
        return `[1-4] choose target   [ESC] cancel`;
      case "give-item":
        return "[1-4] choose recipient   [ESC] cancel";
      default:
        return "[↑↓] select   [Enter] action   [1-4] character   [ESC] close";
    }
  }

  private renderListColumn(x: number, y: number, w: number, h: number): void {
    const padX = 16;
    const startY = y + 16;
    const rowH = 22;
    const visibleRows = Math.floor((h - 32) / rowH);

    // Scrolling: keep cursor's row in view.
    const cursorRow = this.selectable[this.cursor] ?? 0;
    let topRow = 0;
    if (cursorRow > visibleRows - 4) {
      topRow = Math.min(this.rows.length - visibleRows, cursorRow - Math.floor(visibleRows / 2));
    }
    topRow = Math.max(0, topRow);
    const endRow = Math.min(this.rows.length, topRow + visibleRows);

    for (let i = topRow; i < endRow; i++) {
      const r = this.rows[i];
      const ry = startY + (i - topRow) * rowH;
      const isCursor = i === cursorRow;

      if (r.kind === "header") {
        if (r.label === "") {
          // Spacer row — render a thin divider for visual rhythm.
          this.divider(x + padX, ry + rowH / 2, w - padX * 2);
        } else {
          this.text(x + padX, ry + 2, r.label, FONT_HEAD());
        }
        continue;
      }

      if (isCursor) {
        this.track(
          this.add.rectangle(x + 4, ry, w - 8, rowH, C.selectBg, 1).setOrigin(0)
        );
        this.track(
          this.add.rectangle(x + 4, ry, 3, rowH, C.accent, 1).setOrigin(0)
        );
      }

      if (r.kind === "effect") {
        const color = r.equipped ? C.gold : r.available ? C.body : C.faint;
        const prefix = r.equipped ? "● " : r.available ? "  " : "× ";
        this.text(x + padX, ry + 2, `${prefix}${r.effect.name}`, FONT_BODY(color));
        if (r.equipped) {
          this.text(x + w - padX, ry + 2, "EQUIPPED", FONT_MONO(C.gold), [1, 0]);
        } else if (!r.available) {
          this.text(x + w - padX, ry + 2, "REQ NOT MET", FONT_MONO(C.faint), [1, 0]);
        }
      } else if (r.kind === "cast") {
        this.text(x + padX, ry + 2, "CAST SPELL", FONT_BODY(C.body));
        this.text(x + w - padX, ry + 2, "ENTER", FONT_MONO(C.gold), [1, 0]);
      } else if (r.kind === "brew") {
        // Class-coloured row hints (mirror the Python palette: a
        // soft purple for brew, gold for pickpocket, leafy green
        // for tinker).
        this.text(x + padX, ry + 2, "BREW POTIONS", FONT_BODY(0xc8a0ff));
        this.text(x + w - padX, ry + 2, "ALCHEMIST", FONT_MONO(C.dim), [1, 0]);
      } else if (r.kind === "pickpocket") {
        this.text(x + padX, ry + 2, "PICKPOCKET", FONT_BODY(0xe6c878));
        this.text(x + w - padX, ry + 2, "HALFLING", FONT_MONO(C.dim), [1, 0]);
      } else if (r.kind === "tinker") {
        const usedToday = !!this.party
          && typeof this.party.lastTinkerDay === "number"
          && this.party.lastTinkerDay === dayIndex(gameState.clock);
        const titleColor = usedToday ? C.faint : 0x9cd49c;
        const suffixColor = usedToday ? C.faint : C.dim;
        const tag = usedToday ? "USED TODAY" : "GNOME";
        this.text(x + padX, ry + 2, "TINKER", FONT_BODY(titleColor));
        this.text(x + w - padX, ry + 2, tag, FONT_MONO(suffixColor), [1, 0]);
      } else if (r.kind === "item") {
        const charges = r.charges != null ? `  (${r.charges})` : "";
        this.text(x + padX, ry + 2, r.name + charges, FONT_BODY(C.body));
      }
    }
  }

  private renderPartyColumn(x: number, y: number, w: number, h: number): void {
    if (!this.party) return;
    const padX = 16;
    const members = activeMembers(this.party);

    let cy = y + 14;
    // Header changes per mode so the player always knows what 1-4 will do.
    const headerLabel =
      this.mode === "spell-target" ? "PARTY  [1-4 = TARGET]"
      : this.mode === "give-item"  ? "PARTY  [1-4 = RECIPIENT]"
      : "PARTY  [1-4]";
    this.text(x + padX, cy, headerLabel,
              FONT_HEAD(this.mode === "inventory" || this.mode === "spell-list"
                        ? C.gold : C.accent));
    cy += 22;

    const cardH = 78;
    for (let i = 0; i < 4; i++) {
      this.renderMiniCard(members[i], i, x + padX, cy, w - padX * 2, cardH);
      cy += cardH + 4;
    }

    cy += 8;
    this.divider(x + padX, cy, w - padX * 2);
    cy += 12;

    // Detail block — driven by the current mode.
    const detailH = h - (cy - y) - 70;
    if (this.mode === "spell-list") {
      const sel = this.spellRows[this.spellCursor];
      this.renderSpellDetail(sel, x + padX, cy, w - padX * 2, detailH);
    } else if (this.mode === "spell-target" && this.pendingSpell) {
      this.renderTargetPrompt(this.pendingSpell, x + padX, cy, w - padX * 2);
    } else if (this.mode === "give-item" && this.pendingGiveStashIndex != null) {
      const it = this.party.inventory[this.pendingGiveStashIndex];
      this.renderGivePrompt(it?.item ?? "Item", x + padX, cy, w - padX * 2);
    } else {
      const row = this.rows[this.selectable[this.cursor] ?? -1];
      this.renderRowDetail(row, x + padX, cy, w - padX * 2, detailH);
    }

    // Feedback line — sits just above the gold footer.
    if (this.feedback) {
      this.text(x + padX, y + h - 56, this.feedback,
                FONT_BODY(C.gold), [0, 0], w - padX * 2);
    }

    // Gold footer
    const goldY = y + h - 36;
    this.text(x + padX, goldY, `GOLD: ${this.party.gold}`, FONT_HEAD(C.gold));
    this.text(x + w - padX, goldY, `STASH: ${this.party.inventory.length}`, FONT_MONO(C.dim), [1, 0]);
  }

  /**
   * Replacement for the left-side list when CAST SPELL is active.
   * Renders one row per spell that's usable outside combat, with
   * castable spells highlighted in body colour and the rest dimmed
   * with the reason they're unavailable.
   */
  private renderSpellListColumn(x: number, y: number, w: number, h: number): void {
    if (!this.party) return;
    const padX = 16;
    const startY = y + 16;
    const rowH = 22;
    const visibleRows = Math.floor((h - 32) / rowH);
    let topRow = 0;
    if (this.spellCursor > visibleRows - 4) {
      topRow = Math.min(this.spellRows.length - visibleRows, this.spellCursor - Math.floor(visibleRows / 2));
    }
    topRow = Math.max(0, topRow);
    const endRow = Math.min(this.spellRows.length, topRow + visibleRows);

    this.text(x + padX, y + 6, "AVAILABLE SPELLS", FONT_HEAD());

    for (let i = topRow; i < endRow; i++) {
      const sr = this.spellRows[i];
      const ry = startY + (i - topRow) * rowH + 16;
      const isCursor = i === this.spellCursor;
      if (isCursor) {
        this.track(this.add.rectangle(x + 4, ry, w - 8, rowH, C.selectBg, 1).setOrigin(0));
        this.track(this.add.rectangle(x + 4, ry, 3, rowH, C.accent, 1).setOrigin(0));
      }
      const color = sr.castable ? C.body : C.faint;
      this.text(x + padX, ry + 2, sr.spell.name, FONT_BODY(color));
      this.text(x + w - padX - 60, ry + 2, `${sr.spell.mp_cost} MP`,
                FONT_MONO(sr.castable ? C.gold : C.faint), [1, 0]);
      // Right-edge tag — kind of cast or "?" if unsupported.
      const kind = classifyMenuCast(sr.spell);
      const tag = kind === "single-ally" ? "TARGET"
                : kind === "mass" ? "PARTY"
                : kind === "self" ? "SELF"
                : "—";
      this.text(x + w - padX, ry + 2, tag, FONT_MONO(C.dim), [1, 0]);
    }

    if (this.spellRows.length === 0) {
      this.text(x + padX, startY + 16, "No spells available — no caster meets requirements.",
                FONT_BODY(C.faint), [0, 0], w - padX * 2);
    }
  }

  private renderSpellDetail(
    sr: SpellRow | undefined,
    x: number, y: number, w: number, h: number,
  ): void {
    if (!sr) return;
    const s = sr.spell;
    const members = activeMembers(this.party!);
    this.text(x, y, sr.castable ? "SPELL" : "UNAVAILABLE SPELL", FONT_HEAD(sr.castable ? C.gold : C.faint));
    this.text(x, y + 22, s.name, FONT_BODY(C.body));
    this.text(x, y + 42, s.description, FONT_BODY(C.dim), [0, 0], w);

    const eligible = castersFor(s, members);
    const casters = eligible.length > 0
      ? eligible.map((m) => m.name).join(", ")
      : "—";
    this.text(x, y + h - 76, `Cost: ${s.mp_cost} MP`, FONT_MONO(C.dim));
    this.text(x, y + h - 60, `Classes: ${s.allowable_classes.join(", ")}`, FONT_MONO(C.dim), [0, 0], w);
    this.text(x, y + h - 38, `Castable by: ${casters}`, FONT_MONO(C.dim), [0, 0], w);

    const kind = classifyMenuCast(s);
    const hint = kind === "single-ally" ? "Enter to cast, then 1-4 for target"
               : kind === "mass" ? "Enter to cast on the whole party"
               : kind === "self" ? "Enter to cast on the caster"
               : "Has no effect outside combat (yet)";
    this.text(x, y + h - 18, hint,
              FONT_MONO(sr.castable && kind !== "unsupported" ? C.gold : C.faint));
  }

  private renderTargetPrompt(spell: Spell, x: number, y: number, w: number): void {
    this.text(x, y, "CHOOSE TARGET", FONT_HEAD(C.accent));
    this.text(x, y + 24, `Casting ${spell.name}.`, FONT_BODY(C.body));
    this.text(x, y + 46, "Press 1, 2, 3 or 4 to pick a party member.",
              FONT_BODY(C.dim), [0, 0], w);
    this.text(x, y + 70, "ESC to cancel.", FONT_MONO(C.dim));
  }

  private renderGivePrompt(itemName: string, x: number, y: number, w: number): void {
    this.text(x, y, "GIVE ITEM", FONT_HEAD(C.accent));
    this.text(x, y + 24, itemName, FONT_BODY(C.body));
    this.text(x, y + 46, "Press 1, 2, 3 or 4 to choose a recipient.",
              FONT_BODY(C.dim), [0, 0], w);
    this.text(x, y + 70, "ESC to cancel.", FONT_MONO(C.dim));
  }

  private renderMiniCard(
    m: PartyMember | undefined,
    idx: number,
    x: number, y: number, w: number, h: number,
  ): void {
    this.track(
      this.add.rectangle(x, y, w, h, 0x1c1c2a, 1)
        .setOrigin(0)
        .setStrokeStyle(1, C.panelEdge)
    );
    if (!m) {
      this.text(x + w / 2, y + h / 2, "(empty)", FONT_MONO(C.faint), [0.5, 0.5]);
      return;
    }
    const dead = m.hp <= 0;

    // Avatar
    const avatarSize = 56;
    const ax = x + 8, ay = y + (h - avatarSize) / 2;
    if (this.textures.exists(m.sprite)) {
      const img = this.add.image(ax, ay, m.sprite).setOrigin(0);
      img.setDisplaySize(avatarSize, avatarSize);
      if (dead) img.setTintFill(0x505050);
      this.track(img);
    } else {
      this.track(this.add.rectangle(ax, ay, avatarSize, avatarSize, 0x4a3322).setOrigin(0));
    }

    const tx = ax + avatarSize + 10;
    this.text(tx, y + 6, `${idx + 1}  ${m.name}`, FONT_BODY(dead ? C.hpLow : C.body));
    this.text(tx, y + 22, `${m.class}  ${m.race}  ${m.gender}`, FONT_MONO(C.dim));
    const mpStr = m.maxMp != null ? `MP ${m.mp}/${m.maxMp}` : "MP —";
    const xpRow = this.xpRowFor(m);
    const xpStr = xpRow ? `XP ${xpRow.exp}/${xpRow.need}` : `XP ${m.exp}`;
    this.text(tx, y + 38, `LVL ${m.level}   HP ${m.hp}/${m.maxHp}   ${mpStr}   ${xpStr}`, FONT_MONO(C.dim));

    // HP / MP bars
    const barW = w - (tx - x) - 12;
    const hpPct = m.maxHp > 0 ? m.hp / m.maxHp : 0;
    this.bar(tx, y + 54, barW, 6, m.hp, m.maxHp, hpPct <= 0.3 ? C.hpLow : C.hpFull);
    if (m.maxMp != null) {
      this.bar(tx, y + 64, barW, 6, m.mp ?? 0, m.maxMp, C.mp);
    }

    // Click handler — pickMember dispatches based on current mode
    // (target select, give recipient, or detail-drill).
    const hit = this.add.rectangle(x, y, w, h, 0xffffff, 0)
      .setOrigin(0)
      .setInteractive({ useHandCursor: true });
    hit.on("pointerdown", () => this.pickMember(idx));
    this.track(hit);

    // Highlight ring when this card is the active target / recipient
    // candidate. Helps the player see which slot the next 1-4 will hit.
    if (this.mode === "spell-target" || this.mode === "give-item") {
      this.track(
        this.add.rectangle(x, y, w, h, 0xffffff, 0)
          .setOrigin(0)
          .setStrokeStyle(2, C.accent)
      );
    }
  }

  private renderRowDetail(
    row: ListRow | undefined,
    x: number, y: number, w: number, h: number,
  ): void {
    if (!row) return;
    if (row.kind === "header") return;

    if (row.kind === "effect") {
      const e = row.effect;
      this.text(x, y, row.equipped ? "ACTIVE EFFECT"
                : row.available ? "AVAILABLE EFFECT" : "UNAVAILABLE EFFECT",
                FONT_HEAD(row.available || row.equipped ? C.gold : C.faint));
      this.text(x, y + 22, e.name, FONT_BODY(C.body));
      this.text(x, y + 42, e.description, FONT_BODY(C.dim), [0, 0], w);
      // Requirements / duration footer
      const dur = typeof e.duration === "number" ? `${e.duration} steps` : "permanent";
      this.text(x, y + h - 56, `Duration: ${dur}`, FONT_MONO(C.dim));
      const reqText = describeRequirement(e);
      if (reqText) this.text(x, y + h - 38, `Requires: ${reqText}`, FONT_MONO(C.dim), [0, 0], w);
      const hint = row.equipped ? "Enter to remove"
                 : row.available ? "Enter to assign"
                 : "Cannot assign — requirements not met";
      this.text(x, y + h - 18, hint, FONT_MONO(row.available || row.equipped ? C.gold : C.faint));
      return;
    }
    if (row.kind === "cast") {
      this.text(x, y, "CAST SPELL", FONT_HEAD());
      this.text(x, y + 24,
                "Open the spell list — pick any spell a caster in the party can use right now.",
                FONT_BODY(C.dim), [0, 0], w);
      this.text(x, y + h - 18, "Enter to open the spell list", FONT_MONO(C.gold));
      return;
    }
    if (row.kind === "brew") {
      this.text(x, y, "BREW POTIONS", FONT_HEAD());
      this.text(x, y + 24,
                "Your Alchemist mixes a random potion (Healing, Mana, Antidote, "
                + "or one of the Elixirs) into the shared stash.",
                FONT_BODY(C.dim), [0, 0], w);
      this.text(x, y + h - 18, "Enter to brew", FONT_MONO(C.gold));
      return;
    }
    if (row.kind === "pickpocket") {
      // Three states the player can be in:
      //   - "ready": at least one nearby NPC hasn't been lifted from yet
      //   - "spent": NPCs are in reach but every one's been hit already
      //   - "no-targets": nothing nearby to even try
      const total = this.nearbyNpcKeys.length;
      const fresh = this.nearbyNpcKeys.filter(
        (k) => !gameState.pickpocketedNpcs.has(k),
      ).length;
      const state: "ready" | "spent" | "no-targets" =
        total === 0 ? "no-targets" : fresh === 0 ? "spent" : "ready";
      const titleColor = state === "ready" ? C.gold : C.faint;
      this.text(x, y, "PICKPOCKET", FONT_HEAD(titleColor));
      this.text(x, y + 24,
                "Your Halfling lifts something useful from a nearby NPC. "
                + "Each person can only be pickpocketed once per run.",
                FONT_BODY(C.dim), [0, 0], w);
      const status =
        state === "ready"
          ? `${fresh} fresh target${fresh === 1 ? "" : "s"} within reach`
            + (fresh < total ? ` (${total - fresh} already lifted)` : ".")
          : state === "spent"
            ? "Already pickpocketed everyone in reach. Try a different NPC."
            : "Stand next to an NPC in a town, then re-open this menu.";
      const statusColor = state === "ready" ? C.gold : C.faint;
      this.text(x, y + h - 38, status, FONT_MONO(statusColor), [0, 0], w);
      const hint =
        state === "ready" ? "Enter to attempt a pickpocket"
        : state === "spent" ? "No fresh targets — Enter has no effect"
        : "No target — Enter has no effect";
      this.text(x, y + h - 18, hint, FONT_MONO(statusColor));
      return;
    }
    if (row.kind === "tinker") {
      // Show whether the daily ability is available right now so the
      // player knows whether Enter will open the picker or just
      // bounce off with a "tomorrow" message.
      const today = this.party
        ? dayIndex(gameState.clock)
        : 0;
      const usedToday = !!this.party
        && typeof this.party.lastTinkerDay === "number"
        && this.party.lastTinkerDay === today;
      const titleColor = usedToday ? C.faint : C.gold;
      this.text(x, y, "TINKER", FONT_HEAD(titleColor));
      this.text(x, y + 24,
                "Your Gnome cobbles together any item from the general "
                + "store catalog — once per day.",
                FONT_BODY(C.dim), [0, 0], w);
      const hint = usedToday
        ? "Already used today — try again tomorrow"
        : "Enter to pick an item";
      this.text(x, y + h - 18, hint, FONT_MONO(usedToday ? C.faint : C.gold));
      return;
    }
    if (row.kind === "item") {
      this.text(x, y, "ITEM", FONT_HEAD());
      const charges = row.charges != null ? `  (${row.charges})` : "";
      this.text(x, y + 24, row.name + charges, FONT_BODY(C.body));
      this.text(x, y + 48, "Give this item to one of the active party members.",
                FONT_BODY(C.dim), [0, 0], w);
      this.text(x, y + h - 18, "Enter, then 1-4 to choose a recipient", FONT_MONO(C.gold));
      return;
    }
  }

  // ── Detail mode ──────────────────────────────────────────────────

  private renderDetail(): void {
    if (!this.party) return;
    const members = activeMembers(this.party);
    const m = members[this.detailIndex];
    if (!m) { this.mode = "inventory"; this.render(); return; }

    const titleSuffix =
      this.mode === "equip-slot"
        ? "  ·  EQUIP — pick a slot"
        : "";
    this.titleBar(
      `${m.name.toUpperCase()}  —  ${m.class} • ${m.race} • Lvl ${m.level}${titleSuffix}`
    );

    const top = 52;
    const bottom = H - 40;
    const leftX = 8;
    const leftW = (W * 0.5) | 0;
    const rightX = leftX + leftW + 8;
    const rightW = W - rightX - 8;
    const panelH = bottom - top;

    this.panel(leftX, top, leftW, panelH);
    this.panel(rightX, top, rightW, panelH);

    this.renderDetailLeft(m, leftX, top, leftW, panelH);
    this.renderDetailRight(m, rightX, top, rightW, panelH);

    const hint = this.mode === "equip-slot"
      ? "[1-N] choose slot   [ESC] cancel"
      : "[↑↓] select   [Enter] equip / unequip   [R] return to stash   "
        + "[1-4] switch character   [ESC] back   [P] close";
    this.hintBar(hint);
  }

  private renderDetailLeft(
    m: PartyMember, x: number, y: number, w: number, h: number,
  ): void {
    const padX = 20;
    let cy = y + 16;

    // Big portrait + identity
    const sz = 96;
    if (this.textures.exists(m.sprite)) {
      const img = this.add.image(x + padX, cy, m.sprite).setOrigin(0);
      img.setDisplaySize(sz, sz);
      if (m.hp <= 0) img.setTintFill(0x505050);
      this.track(img);
    }
    const tx = x + padX + sz + 16;
    this.text(tx, cy, m.name, FONT_TITLE());
    this.text(tx, cy + 30, `${m.class}  •  ${m.race}  •  ${m.gender}`, FONT_BODY(C.dim));
    const xpRow = this.xpRowFor(m);
    const levelLine = xpRow
      ? `Level ${m.level}   •   EXP ${xpRow.exp} / ${xpRow.need}`
      : `Level ${m.level}   •   EXP ${m.exp}`;
    this.text(tx, cy + 52, levelLine, FONT_BODY(C.body));

    cy += sz + 12;

    // HP / MP bars
    const barW = w - padX * 2;
    this.text(x + padX, cy, "HP", FONT_HEAD());
    this.text(x + w - padX, cy, `${m.hp} / ${m.maxHp}`, FONT_BODY(C.body), [1, 0]);
    cy += 22;
    const hpPct = m.maxHp > 0 ? m.hp / m.maxHp : 0;
    this.bar(x + padX, cy, barW, 10, m.hp, m.maxHp, hpPct <= 0.3 ? C.hpLow : C.hpFull);
    cy += 20;

    this.text(x + padX, cy, "MP", FONT_HEAD());
    if (m.maxMp != null) {
      this.text(x + w - padX, cy, `${m.mp} / ${m.maxMp}`, FONT_BODY(C.body), [1, 0]);
      cy += 22;
      this.bar(x + padX, cy, barW, 10, m.mp ?? 0, m.maxMp, C.mp);
    } else {
      this.text(x + w - padX, cy, "—", FONT_BODY(C.faint), [1, 0]);
      cy += 22;
      this.bar(x + padX, cy, barW, 10, 0, 1, C.divider);
    }
    cy += 26;

    this.divider(x + padX, cy, w - padX * 2); cy += 14;

    // ── COMBAT — derived numbers from gear + attributes ─────────────
    //
    // Placed first (right under MP) because it's the answer to the
    // most common question the player is asking when they open the
    // sheet: "how hard does this character hit?"
    this.text(x + padX, cy, "COMBAT", FONT_HEAD()); cy += 22;
    const cs = combatStatsFor(m, this.items);
    const dice = cs.damage.dice > 0
      ? `${cs.damage.dice}d${cs.damage.sides}${formatDamageBonus(cs.damage.bonus)}`
      : `${cs.damage.bonus}`;
    this.text(x + padX,         cy, "AC",                  FONT_BODY(C.dim));
    this.text(x + padX + 130,   cy, String(cs.ac),         FONT_BODY(C.body));
    cy += 20;
    this.text(x + padX,         cy, "Damage",              FONT_BODY(C.dim));
    this.text(x + padX + 130,   cy, dice,                  FONT_BODY(C.body));
    if (cs.weaponName) {
      this.text(x + padX + 180, cy, `(${cs.weaponName})`,  FONT_BODY(C.dim));
    }
    cy += 26;

    // ── ATTRIBUTES — raw ability scores + their D&D mods ────────────
    this.text(x + padX, cy, "ATTRIBUTES", FONT_HEAD()); cy += 22;
    // Constitution drives HP at level-up via its modifier, so the
    // detail panel needs to surface it alongside the other four
    // attributes — otherwise CON 17 looks identical to CON 8 from
    // this screen and the player can't see why their toughness
    // changed when they swap members in/out.
    const stats: [string, number][] = [
      ["Strength",     m.strength],
      ["Dexterity",    m.dexterity],
      ["Constitution", m.constitution],
      ["Intelligence", m.intelligence],
      ["Wisdom",       m.wisdom],
    ];
    for (const [label, v] of stats) {
      const mod = Math.floor((v - 10) / 2);
      const modStr = mod > 0 ? `+${mod}` : `${mod}`;
      const modColor = mod > 0 ? C.hpFull : mod < 0 ? C.hpLow : C.dim;
      this.text(x + padX,         cy, label,                  FONT_BODY(C.dim));
      this.text(x + padX + 130,   cy, String(v),              FONT_BODY(C.body));
      this.text(x + padX + 180,   cy, `(${modStr})`,          FONT_BODY(modColor));
      cy += 20;
    }

    // ── Race / Class / Spells abilities (scrollable region) ─────────
    //
    // Three stacked sections so the player can see at a glance what
    // their character can DO. Conventions across all three:
    //
    //   - currently usable  → body color
    //   - level-locked     → faint with `(L<n>)` hint
    //
    // SPELLS is hidden entirely for non-casters; RACE for Humans;
    // CLASS for plain classes that ship no level-gated abilities.
    //
    // The region scrolls when content exceeds the panel — wheel +
    // PgUp/PgDn shift `detailScroll` and we re-render. Rows whose
    // virtual y falls outside the visible band [scrollTop, bottomY]
    // are skipped entirely, which is enough to clip cleanly without
    // leaning on a Phaser mask. ▲/▼ indicators on the right edge
    // hint that more content is in either direction.
    cy += 10;
    const scrollTop = cy;
    const bottomY = y + h - 12;
    let virtualCy = scrollTop - this.detailScroll;
    virtualCy = this.renderRaceAbilitiesSection(m, x, virtualCy, w, scrollTop, bottomY);
    virtualCy = this.renderClassAbilitiesSection(m, x, virtualCy, w, scrollTop, bottomY);
    virtualCy = this.renderSpellsSection(m, x, virtualCy, w, scrollTop, bottomY);

    // Now that the full virtual height is known, clamp scroll to
    // [0, maxScroll] in case the user shrank a list (e.g. equipped a
    // new item that no longer matters) and the saved offset is too
    // deep. A second render isn't necessary — we already drew at the
    // current offset; the clamp prevents future scroll commands from
    // landing past the bottom.
    const totalVirtualHeight = (virtualCy - (scrollTop - this.detailScroll));
    const visibleHeight = bottomY - scrollTop;
    const maxScroll = Math.max(0, totalVirtualHeight - visibleHeight);
    if (this.detailScroll > maxScroll) {
      this.detailScroll = maxScroll;
    }
    this.detailScrollMax = maxScroll;

    // Scroll indicators — small ▲ at the top-right of the region when
    // there's content above; ▼ at the bottom when there's content below.
    if (this.detailScroll > 0) {
      this.text(x + w - padX, scrollTop, "▲", FONT_MONO(C.dim), [1, 0]);
    }
    if (this.detailScroll < maxScroll) {
      this.text(x + w - padX, bottomY - 14, "▼", FONT_MONO(C.dim), [1, 0]);
    }
  }

  /**
   * Helper for the three scrollable sections — render a single row's
   * label/right-side pair only when the virtual y falls inside the
   * scrollable band. Everything outside [scrollTop, bottomY] is
   * skipped, which is what gives the scrolling its visual clip.
   */
  private drawScrollRow(
    cy: number, scrollTop: number, bottomY: number,
    drawFn: () => void,
  ): void {
    if (cy + 14 < scrollTop) return;     // row's bottom edge above visible band
    if (cy > bottomY) return;            // row's top edge below visible band
    drawFn();
  }

  /**
   * Render the SPELLS heading and one row per spell whose
   * `allowable_classes` includes the member's class. Castable rows
   * are body-color; locked rows fall back to faint with a `(L<n>)`
   * hint. Returns the next virtual `cy` so the caller can stack the
   * next section. Rows outside [scrollTop, bottomY] are clipped.
   */
  private renderSpellsSection(
    m: PartyMember, x: number, cy: number, w: number,
    scrollTop: number, bottomY: number,
  ): number {
    const padX = 20;
    const klassLower = m.class.toLowerCase();
    // Filter the catalog once. Sort by required level (asc) so the
    // castable spells cluster at the top.
    const mySpells = this.spells
      .filter((s) =>
        s.allowable_classes.some((c) => c.toLowerCase() === klassLower)
      )
      .map((s) => ({ spell: s, gate: minLevelFor(s, m.class) }))
      .sort((a, b) => a.gate - b.gate || a.spell.name.localeCompare(b.spell.name));
    if (mySpells.length === 0) return cy;

    const headerY = cy;
    this.drawScrollRow(headerY, scrollTop, bottomY, () => {
      this.text(x + padX, headerY, "SPELLS", FONT_HEAD());
    });
    cy += 22;
    for (const { spell, gate } of mySpells) {
      const usable = m.level >= gate;
      const color = usable ? C.body : C.faint;
      const rowY = cy;
      this.drawScrollRow(rowY, scrollTop, bottomY, () => {
        this.text(x + padX, rowY, spell.name, FONT_BODY(color));
        const right = usable ? `${spell.mp_cost} MP` : `(L${gate})`;
        this.text(x + w - padX, rowY, right, FONT_MONO(usable ? C.dim : C.faint), [1, 0]);
      });
      cy += 18;
    }
    cy += 6;
    return cy;
  }

  /**
   * Render the RACE ABILITIES heading. Race-gated abilities are
   * always available (no level gate today), so every row is
   * body-color. Hides the section when the race has no innate
   * abilities (Humans). Rows outside the visible band are clipped.
   */
  private renderRaceAbilitiesSection(
    m: PartyMember, x: number, cy: number, w: number,
    scrollTop: number, bottomY: number,
  ): number {
    const padX = 20;
    void w;
    const abilities = raceAbilities(m.race);
    if (abilities.length === 0) return cy;

    const headerY = cy;
    this.drawScrollRow(headerY, scrollTop, bottomY, () => {
      this.text(x + padX, headerY, "RACE ABILITIES", FONT_HEAD());
    });
    cy += 22;
    for (const a of abilities) {
      const rowY = cy;
      this.drawScrollRow(rowY, scrollTop, bottomY, () => {
        this.text(x + padX, rowY, a.name, FONT_BODY(C.body));
      });
      cy += 18;
    }
    cy += 6;
    return cy;
  }

  /**
   * Render the CLASS ABILITIES heading. Class abilities load from
   * the per-class JSON via ClassTemplate.classAbilities; each row is
   * body-color when `member.level >= minLevel` and faint with a
   * `(L<n>)` hint otherwise. Hides the section when the class has
   * no abilities at all (Fighter, Thief, Wizard, Cleric ship empty).
   */
  private renderClassAbilitiesSection(
    m: PartyMember, x: number, cy: number, w: number,
    scrollTop: number, bottomY: number,
  ): number {
    const padX = 20;
    const tpl = this.classTemplates.get(m.class.toLowerCase());
    const list = tpl?.classAbilities ?? [];
    if (list.length === 0) return cy;

    const headerY = cy;
    this.drawScrollRow(headerY, scrollTop, bottomY, () => {
      this.text(x + padX, headerY, "CLASS ABILITIES", FONT_HEAD());
    });
    cy += 22;
    // Sort by required level so unlocked abilities lead.
    const sorted = [...list].sort(
      (a, b) => a.minLevel - b.minLevel || a.name.localeCompare(b.name)
    );
    for (const a of sorted) {
      const usable = m.level >= a.minLevel;
      const color = usable ? C.body : C.faint;
      const rowY = cy;
      this.drawScrollRow(rowY, scrollTop, bottomY, () => {
        this.text(x + padX, rowY, a.name, FONT_BODY(color));
        const right = usable ? "" : `(L${a.minLevel})`;
        if (right) {
          this.text(x + w - padX, rowY, right, FONT_MONO(C.faint), [1, 0]);
        }
      });
      cy += 18;
    }
    cy += 6;
    return cy;
  }

  private renderDetailRight(
    m: PartyMember, x: number, y: number, w: number, h: number,
  ): void {
    const padX = 20;
    const innerW = w - padX * 2;
    let cy = y + 16;

    this.text(x + padX, cy, "EQUIPPED", FONT_HEAD()); cy += 22;

    // Two rows: Hands (the player's weapon, drives attack/damage)
    // and Body. Offhand + head will return when the matching
    // gameplay + UI lands; surfacing them today promises a buff
    // they can't deliver and an "Offhand" row that didn't actually
    // move the dice.
    const slots: [string, EquipSlot, string | null][] = [
      ["Hands",  "right_hand", m.equipped.rightHand],
      ["Body",   "body",       m.equipped.body],
    ];
    const rowH = 22;
    // In equip-slot mode, each candidate slot in `pendingEquipSlots`
    // gets a [N] number badge so the player knows which key picks
    // which slot. Index is into the pendingEquipSlots array.
    const slotKeyForRow = (slot: EquipSlot): number =>
      this.pendingEquipSlots.indexOf(slot);
    for (let i = 0; i < slots.length; i++) {
      const [label, slotName, val] = slots[i];
      const isCursor = this.mode === "detail" && this.detailCursor === i;
      const isCandidate =
        this.mode === "equip-slot" && this.pendingEquipSlots.includes(slotName);
      if (isCursor) {
        this.track(this.add.rectangle(x + 4, cy - 2, w - 8, rowH, C.selectBg, 1).setOrigin(0));
        this.track(this.add.rectangle(x + 4, cy - 2, 3, rowH, C.accent, 1).setOrigin(0));
      }
      if (isCandidate) {
        // Rust outline marks "press 1/2/… to land here".
        this.track(
          this.add.rectangle(x + 4, cy - 2, w - 8, rowH, 0xffffff, 0)
            .setOrigin(0)
            .setStrokeStyle(2, C.accent)
        );
      }
      this.text(x + padX,       cy, label,        FONT_BODY(C.dim));
      this.text(x + padX + 100, cy, val ?? "—",   FONT_BODY(val ? C.body : C.faint));
      if (isCandidate) {
        const n = slotKeyForRow(slotName) + 1;
        this.text(x + w - padX, cy, `[${n}]`, FONT_MONO(C.gold), [1, 0]);
      }
      cy += rowH;
    }

    cy += 8;
    this.divider(x + padX, cy, innerW); cy += 12;

    this.text(x + padX, cy, "PERSONAL ITEMS", FONT_HEAD()); cy += 22;
    if (m.inventory.length === 0) {
      this.text(x + padX, cy, "(none)", FONT_BODY(C.faint));
      cy += 22;
    } else {
      for (let i = 0; i < m.inventory.length; i++) {
        const it = m.inventory[i];
        const isCursor = this.detailCursor === 2 + i;
        if (isCursor) {
          this.track(this.add.rectangle(x + 4, cy - 2, w - 8, rowH, C.selectBg, 1).setOrigin(0));
          this.track(this.add.rectangle(x + 4, cy - 2, 3, rowH, C.accent, 1).setOrigin(0));
        }
        const charges = it.charges != null ? `  (${it.charges})` : "";
        const def = this.items.get(it.item);
        // Filter to the slots the UI currently supports so a head-
        // only item reads as not-equippable rather than promising a
        // row the player can't see.
        const fits = def ? equippableSlots(def) : [];
        const equippable = fits.length > 0;
        this.text(x + padX, cy, `· ${it.item}${charges}`, FONT_BODY(C.body));
        if (equippable) {
          const slot = fits[0];
          this.text(x + w - padX, cy,
                    `equip → ${SLOT_LABELS_DISPLAY[slot]}`,
                    FONT_MONO(C.gold), [1, 0]);
        } else if (def) {
          this.text(x + w - padX, cy, def.usable ? "USE" : "—", FONT_MONO(C.dim), [1, 0]);
        }
        cy += rowH;
      }
    }

    // Footer: feedback line, then the action hint.
    if (this.feedback) {
      this.text(x + padX, y + h - 56, this.feedback,
                FONT_BODY(C.gold), [0, 0], innerW);
    }
    // Action hint — in equip-slot mode the right panel doubles as the
    // slot prompt; otherwise it summarises what Enter / R do.
    if (this.mode === "equip-slot" && this.pendingEquipIndex != null) {
      const it = m.inventory[this.pendingEquipIndex];
      const choices = this.pendingEquipSlots
        .map((s, i) => `[${i + 1}] ${SLOT_LABELS_DISPLAY[s]}`)
        .join("    ");
      this.text(x + padX, y + h - 50,
                `Equip ${it?.item ?? "item"} where?`,
                FONT_BODY(C.accent));
      this.text(x + padX, y + h - 30, `${choices}    [ESC] cancel`,
                FONT_MONO(C.gold));
    } else {
      const hint = this.detailRowActionHint(m);
      this.text(x + padX, y + h - 32, hint, FONT_MONO(C.dim));
    }
  }

  /**
   * Compose a context hint for the current detail-cursor row — tells
   * the player what Enter / R will do without them having to guess.
   */
  private detailRowActionHint(m: PartyMember): string {
    const sel = this.detailCursorKind(m);
    if (sel.kind === "slot") {
      // detailCursorKind only returns currently-supported slots
      // (right_hand → Hands, body), so the fallback chain stays
      // narrow.
      const cur = sel.slot === "right_hand" ? m.equipped.rightHand : m.equipped.body;
      if (cur == null) return "Empty slot — equip an item from below to fill it.";
      return `Enter unequips ${cur}.   R drops it back into the stash.`;
    }
    const it = m.inventory[sel.index];
    if (!it) return "";
    const def = this.items.get(it.item);
    const fits = def ? equippableSlots(def) : [];
    if (fits.length > 0) {
      return fits.length >= 2
        ? `Enter prompts where to equip ${it.item}.   R returns to stash.`
        : `Enter equips ${it.item}.   R returns it to the stash.`;
    }
    return `${it.item} cannot be equipped.   R returns it to the stash.`;
  }
}

const SLOT_LABELS_DISPLAY: Record<EquipSlot, string> = {
  // Player-facing labels for slot pickers. The collapsed model uses
  // "hands" for the right-hand (primary weapon) slot. Offhand /
  // helmet labels stay defined for forward compat — they just don't
  // get shown today since their slots aren't surfaced.
  right_hand: "hands",
  left_hand:  "offhand",
  body:       "body",
  head:       "helmet",
};

function describeRequirement(e: Effect): string | null {
  if (e.item_granted) return "an item the party doesn't yet carry";
  const r = e.requirements;
  if (!r) return null;
  return formatReq(r);
}

function formatReq(r: import("../world/Effects").Requirement): string {
  if (r.any_of && r.any_of.length > 0) return r.any_of.map(formatReq).join("  or  ");
  if (r.class) return `${r.class}` + (r.min_level ? ` (Lv ${r.min_level}+)` : "");
  if (r.race) return r.race;
  return "?";
}
