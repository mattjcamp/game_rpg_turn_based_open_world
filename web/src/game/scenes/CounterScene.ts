/**
 * Counter screen — opens when the party interacts with a counter tile
 * (or a shopkeep / priest NPC; that wiring is a follow-up). Two modes:
 *
 *   - Shop counter: buy/sell. TAB swaps modes. Buy lists items the
 *     counter sells (from counters.json) at the price in items.json;
 *     sell lists the party stash at half-price (or items.json `sell`).
 *   - Service counter: pick a priced service (heal HP, restore MP,
 *     cure poison, raise dead). Mirrors the Python game's healing
 *     counter — same service ids, same costs.
 *
 * Layout follows PartyScene's two-column overlay so the screen looks
 * familiar: left panel for the list, right panel for context (counter
 * description + party gold).
 */

import Phaser from "phaser";
import { gameState } from "../state";
import { loadParty, type Party } from "../world/Party";
import { loadItems, type Item } from "../world/Items";
import {
  loadCounters,
  type Counter,
  type ShopService,
} from "../world/Counters";
import {
  buildShopRows,
  buildSellRows,
  buyFromShop,
  sellToShop,
  applyService,
  type ShopRow,
  type SellRow,
} from "../world/CounterActions";

// Canvas
const W = 960;
const H = 720;

// Palette — same source as PartyScene so the overlay reads as a
// sibling screen rather than a one-off.
const C = {
  bgFull:    0x0c0c14,
  panel:     0x161629,
  panelEdge: 0x2a2a3a,
  accent:    0xc8553d,
  gold:      0xffd470,
  body:      0xf6efd6,
  dim:       0xbdb38a,
  faint:     0x6f6960,
  divider:   0x2a2a3a,
  selectBg:  0x2a1f24,
} as const;

const hex = (n: number) => "#" + n.toString(16).padStart(6, "0");
const FONT_TITLE = (color: number = C.gold) => ({ fontFamily: "Georgia, serif", fontSize: "22px", color: hex(color) });
const FONT_HEAD  = (color: number = C.gold) => ({ fontFamily: "Georgia, serif", fontSize: "16px", color: hex(color) });
const FONT_BODY  = (color: number = C.body) => ({ fontFamily: "Georgia, serif", fontSize: "14px", color: hex(color) });
const FONT_MONO  = (color: number = C.dim)  => ({ fontFamily: "monospace",     fontSize: "12px", color: hex(color) });
const FONT_HINT  = (color: number = C.dim)  => ({ fontFamily: "monospace",     fontSize: "12px", color: hex(color) });

interface CounterSceneData {
  /** Counter key from counters.json (e.g. "general", "weapon", "healing"). */
  counterKey: string;
  /** Scene to resume on close. Defaults to TownScene. */
  from?: string;
}

type Mode = "shop-buy" | "shop-sell" | "service";

export class CounterScene extends Phaser.Scene {
  private from = "TownScene";
  private counterKey = "";

  private party: Party | null = null;
  private items: Map<string, Item> = new Map();
  private counter: Counter | null = null;

  private mode: Mode = "shop-buy";
  private cursor = 0;
  private feedback = "";

  private buyRows: ShopRow[] = [];
  private sellRows: SellRow[] = [];

  private objects: Phaser.GameObjects.GameObject[] = [];

  constructor() {
    super({ key: "CounterScene" });
  }

  init(data?: CounterSceneData): void {
    this.counterKey = data?.counterKey ?? "";
    this.from = data?.from ?? "TownScene";
    this.mode = "shop-buy";
    this.cursor = 0;
    this.feedback = "";
    this.objects = [];
    this.buyRows = [];
    this.sellRows = [];
  }

  async create(): Promise<void> {
    try {
      if (!gameState.partyData) gameState.partyData = await loadParty();
      this.party = gameState.partyData;
      this.items = await loadItems();
      const counters = await loadCounters();
      this.counter = counters.get(this.counterKey) ?? null;
    } catch (err) {
      this.track(
        this.add.text(20, 20,
          `Failed to load counter: ${(err as Error).message}`,
          FONT_BODY()),
      );
      return;
    }
    if (!this.counter) {
      this.track(
        this.add.text(20, 20,
          `Counter '${this.counterKey}' not found in counters.json.`,
          FONT_BODY()),
      );
      return;
    }
    this.mode = this.counter.kind === "service" ? "service" : "shop-buy";
    this.refreshRows();
    this.installInput();
    this.render();
  }

  // ── Input ────────────────────────────────────────────────────────

  private installInput(): void {
    const k = this.input.keyboard;
    if (!k) return;
    k.on("keydown-UP",    () => this.move(-1));
    k.on("keydown-DOWN",  () => this.move(1));
    k.on("keydown-W",     () => this.move(-1));
    k.on("keydown-S",     () => this.move(1));
    k.on("keydown-TAB",   () => this.toggleBuySell());
    k.on("keydown-ENTER", () => this.activate());
    k.on("keydown-SPACE", () => this.activate());
    k.on("keydown-ESC",   () => this.close());
    k.on("keydown-P",     () => this.close());
  }

  private currentList(): { length: number } {
    if (this.mode === "shop-buy") return this.buyRows;
    if (this.mode === "shop-sell") return this.sellRows;
    return this.counter?.services ?? [];
  }

  private move(delta: number): void {
    const len = this.currentList().length;
    if (len === 0) return;
    this.cursor = (this.cursor + delta + len) % len;
    this.feedback = "";
    this.render();
  }

  private toggleBuySell(): void {
    if (!this.counter || this.counter.kind !== "shop") return;
    this.mode = this.mode === "shop-buy" ? "shop-sell" : "shop-buy";
    this.cursor = 0;
    this.feedback = "";
    this.render();
  }

  private activate(): void {
    if (!this.party || !this.counter) return;
    if (this.mode === "shop-buy") {
      const row = this.buyRows[this.cursor];
      if (!row) return;
      const r = buyFromShop(this.party, row);
      this.feedback = r.message;
      this.refreshRows();
      this.render();
      return;
    }
    if (this.mode === "shop-sell") {
      const row = this.sellRows[this.cursor];
      if (!row) return;
      const r = sellToShop(this.party, row);
      this.feedback = r.message;
      // Selling shifts indices — rebuild and clamp the cursor.
      this.refreshRows();
      if (this.cursor >= this.sellRows.length) {
        this.cursor = Math.max(0, this.sellRows.length - 1);
      }
      this.render();
      return;
    }
    if (this.mode === "service") {
      const svc = this.counter.services[this.cursor];
      if (!svc) return;
      const r = applyService(this.party, svc);
      this.feedback = r.message;
      this.render();
    }
  }

  private refreshRows(): void {
    if (!this.party || !this.counter) return;
    if (this.counter.kind === "shop") {
      this.buyRows = buildShopRows(this.counter, this.items);
      this.sellRows = buildSellRows(this.party, this.items);
    }
  }

  private close(): void {
    this.scene.stop();
    this.scene.resume(this.from);
  }

  // ── Render ───────────────────────────────────────────────────────

  private track<T extends Phaser.GameObjects.GameObject>(o: T): T {
    this.objects.push(o);
    return o;
  }

  private panel(x: number, y: number, w: number, h: number): void {
    this.track(
      this.add.rectangle(x, y, w, h, C.panel, 0.96)
        .setOrigin(0)
        .setStrokeStyle(2, C.panelEdge),
    );
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
    if (!this.party || !this.counter) return;
    // Backdrop dim so the underlying TownScene shows through faintly.
    this.track(this.add.rectangle(0, 0, W, H, C.bgFull, 0.94).setOrigin(0));

    this.titleBar(this.titleForMode());

    const top = 52;
    const bottom = H - 40;
    const leftX = 8;
    const leftW = (W * 0.55) | 0;
    const rightX = leftX + leftW + 8;
    const rightW = W - rightX - 8;
    const panelH = bottom - top;

    this.panel(leftX, top, leftW, panelH);
    this.panel(rightX, top, rightW, panelH);

    if (this.counter.kind === "service") {
      this.renderServiceList(leftX, top, leftW, panelH);
    } else if (this.mode === "shop-buy") {
      this.renderBuyList(leftX, top, leftW, panelH);
    } else {
      this.renderSellList(leftX, top, leftW, panelH);
    }
    this.renderRightColumn(rightX, top, rightW, panelH);

    this.hintBar(this.hintForMode());
  }

  private titleForMode(): string {
    const name = this.counter?.name ?? "Counter";
    if (this.counter?.kind === "service") return name;
    return this.mode === "shop-buy"
      ? `${name}  ·  BUY`
      : `${name}  ·  SELL`;
  }

  private hintForMode(): string {
    if (this.counter?.kind === "service") {
      return "[↑↓] select   [Enter] purchase   [ESC] leave";
    }
    return "[↑↓] select   [Enter] confirm   [TAB] swap buy/sell   [ESC] leave";
  }

  // ── List columns ─────────────────────────────────────────────────

  private renderBuyList(x: number, y: number, w: number, h: number): void {
    const padX = 16;
    const startY = y + 16;
    const rowH = 22;
    const visibleRows = Math.floor((h - 32) / rowH);

    this.text(x + padX, y + 6, "FOR SALE", FONT_HEAD());

    if (this.buyRows.length === 0) {
      this.text(x + padX, startY + 16,
                "Nothing for sale at this counter.",
                FONT_BODY(C.faint), [0, 0], w - padX * 2);
      return;
    }

    let topRow = 0;
    if (this.cursor > visibleRows - 4) {
      topRow = Math.min(
        Math.max(0, this.buyRows.length - visibleRows),
        this.cursor - Math.floor(visibleRows / 2),
      );
    }
    const endRow = Math.min(this.buyRows.length, topRow + visibleRows);

    for (let i = topRow; i < endRow; i++) {
      const row = this.buyRows[i];
      const ry = startY + (i - topRow) * rowH + 16;
      const isCursor = i === this.cursor;
      if (isCursor) {
        this.track(this.add.rectangle(x + 4, ry, w - 8, rowH, C.selectBg, 1).setOrigin(0));
        this.track(this.add.rectangle(x + 4, ry, 3, rowH, C.accent, 1).setOrigin(0));
      }
      const canAfford = (this.party?.gold ?? 0) >= row.price;
      const color = canAfford ? C.body : C.faint;
      this.text(x + padX, ry + 2, row.itemName, FONT_BODY(color));
      this.text(x + w - padX, ry + 2, `${row.price} g`,
                FONT_MONO(canAfford ? C.gold : C.faint), [1, 0]);
    }
  }

  private renderSellList(x: number, y: number, w: number, h: number): void {
    const padX = 16;
    const startY = y + 16;
    const rowH = 22;
    const visibleRows = Math.floor((h - 32) / rowH);

    this.text(x + padX, y + 6,
              `STASH  (${this.party?.inventory.length ?? 0} items)`,
              FONT_HEAD());

    if (this.sellRows.length === 0) {
      this.text(x + padX, startY + 16,
                "The party stash is empty.",
                FONT_BODY(C.faint), [0, 0], w - padX * 2);
      return;
    }

    let topRow = 0;
    if (this.cursor > visibleRows - 4) {
      topRow = Math.min(
        Math.max(0, this.sellRows.length - visibleRows),
        this.cursor - Math.floor(visibleRows / 2),
      );
    }
    const endRow = Math.min(this.sellRows.length, topRow + visibleRows);

    for (let i = topRow; i < endRow; i++) {
      const row = this.sellRows[i];
      const ry = startY + (i - topRow) * rowH + 16;
      const isCursor = i === this.cursor;
      if (isCursor) {
        this.track(this.add.rectangle(x + 4, ry, w - 8, rowH, C.selectBg, 1).setOrigin(0));
        this.track(this.add.rectangle(x + 4, ry, 3, rowH, C.accent, 1).setOrigin(0));
      }
      const sellable = row.price > 0;
      const color = sellable ? C.body : C.faint;
      this.text(x + padX, ry + 2, row.itemName, FONT_BODY(color));
      this.text(x + w - padX, ry + 2,
                sellable ? `${row.price} g` : "—",
                FONT_MONO(sellable ? C.gold : C.faint), [1, 0]);
    }
  }

  private renderServiceList(x: number, y: number, w: number, h: number): void {
    const padX = 16;
    const startY = y + 16;
    const rowH = 30;

    this.text(x + padX, y + 6, "SERVICES", FONT_HEAD());

    const services = this.counter?.services ?? [];
    if (services.length === 0) {
      this.text(x + padX, startY + 16,
                "This counter offers no services.",
                FONT_BODY(C.faint), [0, 0], w - padX * 2);
      return;
    }

    for (let i = 0; i < services.length; i++) {
      const svc = services[i];
      const ry = startY + i * rowH + 16;
      const isCursor = i === this.cursor;
      const canAfford = (this.party?.gold ?? 0) >= svc.cost;
      const color = canAfford ? C.body : C.faint;
      if (isCursor) {
        this.track(this.add.rectangle(x + 4, ry, w - 8, rowH, C.selectBg, 1).setOrigin(0));
        this.track(this.add.rectangle(x + 4, ry, 3, rowH, C.accent, 1).setOrigin(0));
      }
      this.text(x + padX, ry + 2, svc.name, FONT_BODY(color));
      this.text(x + w - padX, ry + 2, `${svc.cost} g`,
                FONT_MONO(canAfford ? C.gold : C.faint), [1, 0]);
    }
  }

  // ── Right column (description + gold + feedback) ────────────────

  private renderRightColumn(x: number, y: number, w: number, h: number): void {
    if (!this.counter || !this.party) return;
    const padX = 16;
    let cy = y + 16;

    this.text(x + padX, cy, this.counter.name, FONT_HEAD()); cy += 24;
    this.text(x + padX, cy, this.counter.description,
              FONT_BODY(C.dim), [0, 0], w - padX * 2);
    cy += 96;

    this.divider(x + padX, cy, w - padX * 2); cy += 12;

    // Selected-row detail (item description / service description).
    const detailH = h - (cy - y) - 96;
    this.renderSelectionDetail(x + padX, cy, w - padX * 2, detailH);

    // Feedback line — sits just above the gold footer.
    if (this.feedback) {
      this.text(x + padX, y + h - 56, this.feedback,
                FONT_BODY(C.gold), [0, 0], w - padX * 2);
    }

    // Gold footer.
    const goldY = y + h - 36;
    this.text(x + padX, goldY, `GOLD: ${this.party.gold}`, FONT_HEAD(C.gold));
    this.text(x + w - padX, goldY,
              `STASH: ${this.party.inventory.length}`,
              FONT_MONO(C.dim), [1, 0]);
  }

  private renderSelectionDetail(
    x: number, y: number, w: number, h: number,
  ): void {
    if (!this.counter) return;
    if (this.counter.kind === "service") {
      const svc = this.counter.services[this.cursor];
      this.renderServiceDetail(svc, x, y, w, h);
      return;
    }
    if (this.mode === "shop-buy") {
      const row = this.buyRows[this.cursor];
      this.renderItemDetail(row?.itemName ?? null, row?.item ?? null,
                            row?.price ?? 0, "Buy", x, y, w, h);
      return;
    }
    const row = this.sellRows[this.cursor];
    this.renderItemDetail(row?.itemName ?? null, row?.item ?? null,
                          row?.price ?? 0, "Sell", x, y, w, h);
  }

  private renderItemDetail(
    itemName: string | null,
    item: Item | null,
    price: number,
    verb: "Buy" | "Sell",
    x: number, y: number, w: number, _h: number,
  ): void {
    if (!itemName) {
      this.text(x, y, "(nothing selected)", FONT_BODY(C.faint));
      return;
    }
    this.text(x, y, "ITEM", FONT_HEAD());
    this.text(x, y + 22, itemName, FONT_BODY(C.body));
    if (item?.description) {
      this.text(x, y + 44, item.description, FONT_BODY(C.dim), [0, 0], w);
    }
    this.text(x, y + 100, `${verb} price: ${price} gold`, FONT_MONO(C.gold));
  }

  private renderServiceDetail(
    svc: ShopService | undefined,
    x: number, y: number, w: number, _h: number,
  ): void {
    if (!svc) {
      this.text(x, y, "(no service selected)", FONT_BODY(C.faint));
      return;
    }
    this.text(x, y, "SERVICE", FONT_HEAD());
    this.text(x, y + 22, svc.name, FONT_BODY(C.body));
    if (svc.description) {
      this.text(x, y + 44, svc.description, FONT_BODY(C.dim), [0, 0], w);
    }
    this.text(x, y + 100, `Cost: ${svc.cost} gold`, FONT_MONO(C.gold));
  }
}
