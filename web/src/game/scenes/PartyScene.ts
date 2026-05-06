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
  loadEffects,
  canEquip,
  type Effect,
} from "../world/Effects";
import {
  loadSpells,
  spellsCastableFromMenu,
  castersFor,
  type Spell,
} from "../world/Spells";
import {
  assignEffectToParty,
  removeEffectFromParty,
  giveStashItemTo,
  returnItemToStash,
  castHealOnTarget,
  castMassHeal,
  classifyMenuCast,
  equipItemFromInventory,
  equipItemIntoSlot,
  unequipSlot,
  hasClass,
  hasRace,
  brewPotion,
  pickpocket,
  tinker,
} from "../world/PartyActions";
import {
  loadItems,
  type Item,
  type EquipSlot,
} from "../world/Items";

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

interface PartySceneData {
  /** Scene key to resume on close. */
  from?: string;
  /**
   * Number of NPCs adjacent to the party in the launching scene. Used
   * to gate the PICKPOCKET action — the Python game requires at least
   * one adjacent NPC. The launching scene computes this in 8 directions
   * around the player before launching the overlay; OverworldScene
   * passes 0.
   */
  nearbyNpcCount?: number;
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
type Mode = "inventory" | "spell-list" | "spell-target" | "give-item" | "detail" | "equip-slot";

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
  private nearbyNpcCount = 0;
  private party: Party | null = null;
  private effects: Effect[] = [];
  private spells: Spell[] = [];
  private items: Map<string, Item> = new Map();
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

  // Spell-list state
  private spellRows: SpellRow[] = [];
  private spellCursor = 0;
  /** Spell waiting on a target select (mode === "spell-target"). */
  private pendingSpell: Spell | null = null;

  // Give-item state — stash index of the item awaiting a recipient.
  private pendingGiveStashIndex: number | null = null;

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
    this.nearbyNpcCount = data?.nearbyNpcCount ?? 0;
    this.mode = "inventory";
    this.cursor = 0;
    this.detailIndex = 0;
    this.detailCursor = 0;
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
      "illusionist", "paladin", "ranger", "wizard",
    ]) {
      const path = `/assets/characters/${f}.png`;
      this.load.image(path, path);
    }
  }

  async create(): Promise<void> {
    try {
      if (!gameState.partyData) gameState.partyData = await loadParty();
      this.party = gameState.partyData;
      this.effects = await loadEffects();
      this.spells = await loadSpells();
      this.items = await loadItems();
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
    k.on("keydown-ESC",   () => this.escape());
    k.on("keydown-P",     () => this.close());
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
    // Other modes (target / give) have no list to scroll.
  }

  /** The member currently being viewed in detail mode, if any. */
  private currentDetailMember(): PartyMember | undefined {
    if (!this.party) return undefined;
    const members = activeMembers(this.party);
    return members[this.detailIndex];
  }

  /**
   * 0..3 → equip slot (right_hand, left_hand, body, head)
   * 4..  → personal inventory index (cursor - 4)
   */
  private detailCursorKind(m: PartyMember): { kind: "slot"; slot: EquipSlot } | { kind: "item"; index: number } {
    if (this.detailCursor < 4) {
      const slot: EquipSlot = (["right_hand", "left_hand", "body", "head"] as const)[this.detailCursor];
      return { kind: "slot", slot };
    }
    return { kind: "item", index: this.detailCursor - 4 };
  }

  /**
   * Enter / Space — context-sensitive action based on the current
   * mode and the selected row.
   */
  private activate(): void {
    if (!this.party) return;
    if (this.mode === "inventory") return this.activateInventoryRow();
    if (this.mode === "spell-list") return this.activateSpellRow();
    if (this.mode === "detail") return this.activateDetailRow();
    // Target prompts and give-item prompts are answered with 1-4,
    // not Enter — Enter is a no-op there.
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
      const r = unequipSlot(m, sel.slot);
      this.feedback = r.message;
      this.clampDetailCursor(m);
      this.render();
      return;
    }

    // Personal-inventory row.
    const inv = m.inventory[sel.index];
    if (!inv) return;
    const def = this.items.get(inv.item);
    const slots: EquipSlot[] = def?.characterCanEquip ? def.slots : [];

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
      const u = unequipSlot(m, sel.slot);
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
      const r = brewPotion(this.party, members);
      this.feedback = r.message;
      this.buildRows();
      this.render();
      return;
    }
    if (row.kind === "pickpocket") {
      // The Python game requires at least one NPC adjacent (8-dir) to
      // the party in town. If we were launched from a scene with no
      // adjacent NPCs (overworld, or an empty patch of town), refuse
      // here — the underlying loot roll only fires once a target is
      // in reach.
      if (this.nearbyNpcCount === 0) {
        this.feedback = "No one nearby to pickpocket.";
        this.render();
        return;
      }
      const r = pickpocket(this.party, members);
      this.feedback = r.message;
      this.buildRows();
      this.render();
      return;
    }
    if (row.kind === "tinker") {
      const r = tinker(this.party, members);
      this.feedback = r.message;
      this.buildRows();
      this.render();
      return;
    }

    if (row.kind === "item") {
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
    // Unsupported in the menu (knock, magic_light…) — give a polite
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
    // Keep all spells that COULD be cast outside combat (so the
    // player sees what they're missing) but mark only currently-
    // castable ones as activatable.
    const outsideCombat = this.spells.filter((s) =>
      s.usable_in.some((c) => c !== "battle")
    );
    this.spellRows = outsideCombat.map((s) => ({
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
    this.mode = "detail";
    this.render();
  }

  private escape(): void {
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
    this.renderInventory();
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
      case "spell-list":   return "PARTY  ·  CAST SPELL";
      case "spell-target": return `PARTY  ·  ${this.pendingSpell?.name ?? "Cast"}  —  pick a target`;
      case "give-item":    return "PARTY  ·  Give item — pick a recipient";
      default:             return "PARTY";
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
        this.text(x + padX, ry + 2, "TINKER", FONT_BODY(0x9cd49c));
        this.text(x + w - padX, ry + 2, "GNOME", FONT_MONO(C.dim), [1, 0]);
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
    this.text(tx, y + 38, `LVL ${m.level}   HP ${m.hp}/${m.maxHp}   ${mpStr}`, FONT_MONO(C.dim));

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
      const ready = this.nearbyNpcCount > 0;
      this.text(x, y, "PICKPOCKET", FONT_HEAD(ready ? C.gold : C.faint));
      this.text(x, y + 24,
                "Your Halfling lifts something useful from a nearby NPC. "
                + "Could be coins, herbs, arrows, even a Dagger.",
                FONT_BODY(C.dim), [0, 0], w);
      // Status line — "Ready" when the launching scene reported at least
      // one adjacent NPC, otherwise an instruction.
      this.text(x, y + h - 38,
                ready
                  ? `${this.nearbyNpcCount} target${this.nearbyNpcCount === 1 ? "" : "s"} within reach.`
                  : "Stand next to an NPC in a town, then re-open this menu.",
                FONT_MONO(ready ? C.gold : C.faint), [0, 0], w);
      this.text(x, y + h - 18,
                ready ? "Enter to attempt a pickpocket"
                      : "No target — Enter has no effect",
                FONT_MONO(ready ? C.gold : C.faint));
      return;
    }
    if (row.kind === "tinker") {
      this.text(x, y, "TINKER", FONT_HEAD());
      this.text(x, y + 24,
                "Your Gnome cobbles together a utility item — a lockpick, "
                + "torch, arrows, bolts, or camping supplies.",
                FONT_BODY(C.dim), [0, 0], w);
      this.text(x, y + h - 18, "Enter to tinker", FONT_MONO(C.gold));
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
    this.text(tx, cy + 52, `Level ${m.level}`, FONT_BODY(C.body));

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

    // Stats
    this.text(x + padX, cy, "ATTRIBUTES", FONT_HEAD()); cy += 22;
    const stats: [string, number][] = [
      ["Strength",     m.strength],
      ["Dexterity",    m.dexterity],
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
  }

  private renderDetailRight(
    m: PartyMember, x: number, y: number, w: number, h: number,
  ): void {
    const padX = 20;
    const innerW = w - padX * 2;
    let cy = y + 16;

    this.text(x + padX, cy, "EQUIPPED", FONT_HEAD()); cy += 22;

    // The four equipment slots map 1:1 to detail-cursor rows 0..3.
    const slots: [string, EquipSlot, string | null][] = [
      ["Weapon",  "right_hand", m.equipped.rightHand],
      ["Offhand", "left_hand",  m.equipped.leftHand],
      ["Body",    "body",       m.equipped.body],
      ["Helmet",  "head",       m.equipped.head],
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
        const isCursor = this.detailCursor === 4 + i;
        if (isCursor) {
          this.track(this.add.rectangle(x + 4, cy - 2, w - 8, rowH, C.selectBg, 1).setOrigin(0));
          this.track(this.add.rectangle(x + 4, cy - 2, 3, rowH, C.accent, 1).setOrigin(0));
        }
        const charges = it.charges != null ? `  (${it.charges})` : "";
        const def = this.items.get(it.item);
        const equippable = !!(def?.characterCanEquip && def.slots.length > 0);
        this.text(x + padX, cy, `· ${it.item}${charges}`, FONT_BODY(C.body));
        if (equippable) {
          const slot = def!.slots[0];
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
      const cur = (
        sel.slot === "right_hand" ? m.equipped.rightHand
        : sel.slot === "left_hand"  ? m.equipped.leftHand
        : sel.slot === "body"       ? m.equipped.body
        : m.equipped.head
      );
      if (cur == null) return "Empty slot — equip an item from below to fill it.";
      return `Enter unequips ${cur}.   R drops it back into the stash.`;
    }
    const it = m.inventory[sel.index];
    if (!it) return "";
    const def = this.items.get(it.item);
    if (def?.characterCanEquip && def.slots.length > 0) {
      return def.slots.length >= 2
        ? `Enter prompts where to equip ${it.item}.   R returns to stash.`
        : `Enter equips ${it.item}.   R returns it to the stash.`;
    }
    return `${it.item} cannot be equipped.   R returns it to the stash.`;
  }
}

const SLOT_LABELS_DISPLAY: Record<EquipSlot, string> = {
  right_hand: "weapon",
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
