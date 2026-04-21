"""Regenerate docs/manuals/players_guide.pdf from players_guide.md.

This is a hand-tailored Markdown → PDF renderer that reproduces the
1980's-style fantasy-manual aesthetic used in the existing PDF:

  * Cream/parchment page background (#F4ECD6)
  * Burgundy ink (#6B2A1A) for accents, headings and the page frame
  * Ornate double-line border with L-shaped corner brackets and diamond
    accents at the midpoints of each edge
  * Running header "REALM OF SHADOW" in small caps, italic page number
  * Section headers: centred, all-caps, with a decorative line-diamond-
    line divider beneath them
  * Title page with hero artwork recovered from the previous PDF
  * Two-column portrait + text layout for each of the eight class pages

Assets (cover art, class portraits) live in docs/manuals/assets/ and are
reused from the previous PDF build so future regenerations have access
to them without re-extracting.

Run:  python3 docs/manuals/build_manual.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor, Color
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as canvaslib
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Frame,
)


# ── Paths ────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
MD_PATH = HERE / "players_guide.md"
OUT_PATH = HERE / "players_guide.pdf"
ASSETS = HERE / "assets"


# ── Palette ──────────────────────────────────────────────────────────

CREAM = HexColor("#F4ECD6")
INK = HexColor("#3A1F10")          # body text — warm black-brown
ACCENT = HexColor("#6B2A1A")       # burgundy — headings, borders
ACCENT_SOFT = HexColor("#8A4530")  # softer burgundy — meta / running head
RULE = HexColor("#8A4530")


# ── Page geometry ────────────────────────────────────────────────────

PAGE_W, PAGE_H = letter
MARGIN = 0.75 * inch
INNER_MARGIN = 0.30 * inch   # gap between outer frame and text frame

TEXT_LEFT = MARGIN + INNER_MARGIN
TEXT_RIGHT = PAGE_W - MARGIN - INNER_MARGIN
TEXT_TOP = PAGE_H - MARGIN - INNER_MARGIN - 0.30 * inch
TEXT_BOTTOM = MARGIN + INNER_MARGIN + 0.25 * inch
TEXT_WIDTH = TEXT_RIGHT - TEXT_LEFT
TEXT_HEIGHT = TEXT_TOP - TEXT_BOTTOM


# ── Styles ───────────────────────────────────────────────────────────

BASE_FONT = "Times-Roman"
BOLD_FONT = "Times-Bold"
ITAL_FONT = "Times-Italic"
BOLD_ITAL_FONT = "Times-BoldItalic"


def _para_style(name, **kw):
    defaults = dict(
        name=name,
        fontName=BASE_FONT,
        fontSize=11,
        leading=14,
        textColor=INK,
        alignment=4,  # justify
        spaceAfter=6,
        firstLineIndent=0,
    )
    defaults.update(kw)
    return ParagraphStyle(**defaults)


BODY = _para_style("Body", firstLineIndent=18)
BODY_NOINDENT = _para_style("BodyNI", alignment=0)
FLAVOR = _para_style(
    "Flavor", fontName=ITAL_FONT, textColor=ACCENT_SOFT,
    alignment=1, spaceAfter=10, fontSize=10.5, leading=13.5,
)
H1 = _para_style(
    "H1", fontName=BOLD_FONT, fontSize=22, leading=26,
    textColor=ACCENT, alignment=1, spaceAfter=0, spaceBefore=6,
)
H2 = _para_style(
    "H2", fontName=BOLD_FONT, fontSize=17, leading=22,
    textColor=ACCENT, alignment=1, spaceAfter=0, spaceBefore=8,
)
H3 = _para_style(
    "H3", fontName=BOLD_FONT, fontSize=13.5, leading=17,
    textColor=ACCENT, alignment=0, spaceAfter=6, spaceBefore=14,
)
CLASS_NAME = _para_style(
    "ClassName", fontName=BOLD_FONT, fontSize=24, leading=28,
    textColor=ACCENT, alignment=0, spaceAfter=4, spaceBefore=0,
)
CLASS_FLAVOR = _para_style(
    "ClassFlavor", fontName=ITAL_FONT, textColor=ACCENT_SOFT,
    fontSize=10.5, leading=13, alignment=1, spaceAfter=6,
)
BULLET = _para_style("Bullet", leftIndent=18, bulletIndent=4, firstLineIndent=0)
CODE = _para_style(
    "Code", fontName="Courier-Bold", fontSize=10.5, leading=13,
    leftIndent=18, spaceAfter=6, textColor=INK, alignment=0,
)
TABLE_HEAD = _para_style(
    "TableHead", fontName=BOLD_FONT, alignment=1,
    textColor=ACCENT, fontSize=10.5, leading=13, spaceAfter=0,
)
TABLE_CELL = _para_style(
    "TableCell", alignment=1, fontSize=10, leading=12, spaceAfter=0,
)
TABLE_CAPTION = _para_style(
    "TableCaption", fontName=ITAL_FONT, textColor=ACCENT_SOFT,
    alignment=1, fontSize=10.5, leading=13, spaceAfter=6,
)
TABLE_TITLE = _para_style(
    "TableTitle", fontName=BOLD_FONT, textColor=ACCENT,
    alignment=1, fontSize=13, leading=16, spaceAfter=2,
)
SECTION_TOC_ITEM = _para_style(
    "TOC", fontSize=11, leading=15, alignment=0, spaceAfter=2,
)


# ── Page frame drawn behind every page ──────────────────────────────

def _diamond(c, cx, cy, r, color):
    c.saveState()
    c.setFillColor(color)
    c.setStrokeColor(color)
    p = c.beginPath()
    p.moveTo(cx, cy + r)
    p.lineTo(cx + r, cy)
    p.lineTo(cx, cy - r)
    p.lineTo(cx - r, cy)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def _draw_page_frame(c, doc, show_header=True, page_num=None):
    # Fill page with cream
    c.saveState()
    c.setFillColor(CREAM)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    c.restoreState()

    # Outer ornate frame
    c.saveState()
    c.setStrokeColor(ACCENT)
    # Double-line border
    c.setLineWidth(1.6)
    c.rect(MARGIN, MARGIN, PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN, stroke=1, fill=0)
    c.setLineWidth(0.6)
    ins = 5
    c.rect(MARGIN + ins, MARGIN + ins,
           PAGE_W - 2 * (MARGIN + ins),
           PAGE_H - 2 * (MARGIN + ins),
           stroke=1, fill=0)

    # L-shaped corner brackets — filled "staple" pieces over the corners
    # that give the frame an illuminated-manuscript feel.
    bracket = 26
    arm = 14
    for (cx, cy, xdir, ydir) in [
        (MARGIN,                   PAGE_H - MARGIN,  1, -1),   # top-left
        (PAGE_W - MARGIN,          PAGE_H - MARGIN, -1, -1),   # top-right
        (MARGIN,                   MARGIN,           1,  1),   # bottom-left
        (PAGE_W - MARGIN,          MARGIN,          -1,  1),   # bottom-right
    ]:
        offx = xdir * bracket
        offy = ydir * bracket
        ax = cx + offx
        ay = cy + offy
        c.setLineWidth(1.4)
        # horizontal arm (from corner inward)
        c.line(ax, ay, ax - xdir * arm, ay)
        # vertical arm
        c.line(ax, ay, ax, ay - ydir * arm)
        # small nib on each arm tip
        c.circle(ax - xdir * arm, ay, 1.8, stroke=1, fill=1)
        c.circle(ax, ay - ydir * arm, 1.8, stroke=1, fill=1)

    # Diamond accents at midpoints of each edge (just outside inner rect)
    midx = PAGE_W / 2
    midy = PAGE_H / 2
    _diamond(c, midx, MARGIN + ins, 3.0, ACCENT)
    _diamond(c, midx, PAGE_H - MARGIN - ins, 3.0, ACCENT)
    _diamond(c, MARGIN + ins, midy, 3.0, ACCENT)
    _diamond(c, PAGE_W - MARGIN - ins, midy, 3.0, ACCENT)
    c.restoreState()

    # Running header
    if show_header:
        c.saveState()
        c.setFont(BASE_FONT, 8.5)
        c.setFillColor(ACCENT_SOFT)
        c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN + 6,
                            "R E A L M   O F   S H A D O W")
        c.restoreState()

    # Page number
    if page_num is not None:
        c.saveState()
        c.setFont(ITAL_FONT, 9)
        c.setFillColor(ACCENT_SOFT)
        c.drawCentredString(PAGE_W / 2, MARGIN - 14, str(page_num))
        c.restoreState()


def _on_page(c, doc):
    # Skip running header + page number on the title page (page 1)
    pn = doc.page
    if pn == 1:
        _draw_page_frame(c, doc, show_header=False, page_num=None)
    else:
        _draw_page_frame(c, doc, show_header=True, page_num=pn)


# ── Custom flowables ────────────────────────────────────────────────

class OrnateRule(Flowable):
    """Horizontal rule with a diamond ornament in the middle."""
    def __init__(self, width, color=RULE, size=3, gap=4, thickness=0.8):
        super().__init__()
        self.width = width
        self.color = color
        self.size = size
        self.gap = gap
        self.thickness = thickness

    def wrap(self, availWidth, availHeight):
        return (self.width, max(self.size * 2 + 2, 8))

    def draw(self):
        c = self.canv
        h = self.wrap(self.width, 0)[1]
        y = h / 2
        c.saveState()
        c.setStrokeColor(self.color)
        c.setLineWidth(self.thickness)
        dw = self.size + self.gap
        c.line(0, y, self.width / 2 - dw, y)
        c.line(self.width / 2 + dw, y, self.width, y)
        # Diamond
        c.setFillColor(self.color)
        cx = self.width / 2
        s = self.size
        p = c.beginPath()
        p.moveTo(cx, y + s)
        p.lineTo(cx + s, y)
        p.lineTo(cx, y - s)
        p.lineTo(cx - s, y)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.restoreState()


class SectionHeader(Flowable):
    """Centered all-caps heading with an ornate rule below."""
    def __init__(self, text, width, top_pad=16, bottom_pad=8):
        super().__init__()
        self.text = text.upper()
        self.width = width
        self.top_pad = top_pad
        self.bottom_pad = bottom_pad

    def wrap(self, availWidth, availHeight):
        return (self.width, 52 + self.top_pad + self.bottom_pad)

    def draw(self):
        c = self.canv
        c.saveState()
        # Heading
        c.setFont(BOLD_FONT, 20)
        c.setFillColor(ACCENT)
        text_y = self.bottom_pad + 22
        c.drawCentredString(self.width / 2, text_y, self.text)
        # Rule
        c.setStrokeColor(RULE)
        c.setLineWidth(1.0)
        ry = self.bottom_pad + 8
        gap = 8
        c.line(0, ry, self.width / 2 - gap, ry)
        c.line(self.width / 2 + gap, ry, self.width, ry)
        # Diamond
        c.setFillColor(RULE)
        cx = self.width / 2
        s = 4
        p = c.beginPath()
        p.moveTo(cx, ry + s); p.lineTo(cx + s, ry)
        p.lineTo(cx, ry - s); p.lineTo(cx - s, ry); p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.restoreState()


# ── Markdown parser (purpose-built) ─────────────────────────────────

INLINE_RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_RE_ITAL = re.compile(r"\*([^*]+?)\*")
INLINE_RE_CODE = re.compile(r"`([^`]+?)`")
INLINE_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _html_escape(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def _inline(text):
    """Convert markdown inline markup to reportlab paragraph mini-HTML."""
    s = _html_escape(text)
    s = INLINE_RE_LINK.sub(r'<link href="\2" color="#6B2A1A">\1</link>', s)
    s = INLINE_RE_BOLD.sub(r"<b>\1</b>", s)
    s = INLINE_RE_ITAL.sub(r"<i>\1</i>", s)
    s = INLINE_RE_CODE.sub(r'<font face="Courier-Bold">\1</font>', s)
    # Retain raw em-dashes / en-dashes as-is
    return s


def _parse_table_block(lines, i):
    """Parse a GFM-style pipe table starting at lines[i].
    Returns (rows, next_i).  Header row is rows[0].
    """
    def cells(line):
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        return parts
    header = cells(lines[i])
    # The next line is the separator like |---|:---:|
    sep = lines[i + 1]
    if not re.match(r"^\s*\|?[\s:|\-]+\|?\s*$", sep):
        return None, i
    rows = [header]
    j = i + 2
    while j < len(lines) and lines[j].lstrip().startswith("|"):
        rows.append(cells(lines[j]))
        j += 1
    return rows, j


def _tokenize(md):
    """Return a stream of blocks: ('h1', text) / ('h2', text) / ('h3', text) /
    ('p', text) / ('ul', [items]) / ('ol', [items]) / ('hr',) /
    ('table', rows) / ('code', text) / ('blank',).
    """
    lines = md.splitlines()
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            blocks.append(("blank",))
            i += 1
            continue
        if stripped == "---":
            blocks.append(("hr",))
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            blocks.append((f"h{level}", text))
            i += 1
            continue
        # Pipe table?
        if stripped.startswith("|") and (i + 1 < n) and re.match(
                r"^\s*\|?[\s:|\-]+\|?\s*$", lines[i + 1]):
            rows, j = _parse_table_block(lines, i)
            if rows:
                blocks.append(("table", rows))
                i = j
                continue
        # Code block
        if stripped.startswith("```"):
            j = i + 1
            buf = []
            while j < n and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            blocks.append(("code", "\n".join(buf)))
            i = j + 1
            continue
        # Unordered list
        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]).rstrip())
                i += 1
            blocks.append(("ul", items))
            continue
        # Ordered list
        if re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]).rstrip())
                i += 1
            blocks.append(("ol", items))
            continue
        # Paragraph — collect until blank / heading / list / table
        buf = [line.rstrip()]
        j = i + 1
        while j < n:
            nxt = lines[j]
            if not nxt.strip():
                break
            if nxt.lstrip().startswith(("#", "|", "-", "*", "```")) \
                    or re.match(r"^\s*\d+\.\s+", nxt):
                break
            buf.append(nxt.rstrip())
            j += 1
        blocks.append(("p", " ".join(buf).strip()))
        i = j
    return blocks


# ── Class-page special handling ─────────────────────────────────────

CLASS_ORDER = ["Fighter", "Wizard", "Cleric", "Thief",
               "Paladin", "Ranger", "Druid", "Alchemist"]


def _slice_class_block(blocks, name):
    """Find the contiguous block list for a ### <class name> section."""
    start = None
    for idx, b in enumerate(blocks):
        if b[0] == "h3" and b[1].strip().lower() == name.lower():
            start = idx
            break
    if start is None:
        return None, None
    end = len(blocks)
    for idx in range(start + 1, len(blocks)):
        if blocks[idx][0] == "h3" or blocks[idx][0] == "h2":
            end = idx
            break
    return start, end


def _mini_stat_table(rows):
    tbl = Table(rows, colWidths=[inch * 0.95, inch * 0.95, inch * 0.95, inch * 0.95],
                hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONT",         (0, 0), (-1, 0),  BOLD_FONT, 10.5),
        ("FONT",         (0, 1), (-1, 1),  BASE_FONT, 10),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  ACCENT),
        ("TEXTCOLOR",    (0, 1), (-1, 1),  INK),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("LINEABOVE",    (0, 0), (-1, 0),  0.6, ACCENT_SOFT),
        ("LINEBELOW",    (0, 0), (-1, 0),  0.6, ACCENT_SOFT),
        ("LINEBELOW",    (0, 1), (-1, 1),  0.6, ACCENT_SOFT),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _class_page(blocks, name, portrait_path):
    """Render a single class section as a two-column layout."""
    start, end = _slice_class_block(blocks, name)
    if start is None:
        return []
    # The section heading itself is blocks[start]; following blocks:
    # [p(flavor)], [table], [p(weapons)], [p(armor)], [p(body)], [p(abilities)], ...
    sub = blocks[start + 1:end]

    flavor_text = ""
    stats_rows = None
    weapons_text = ""
    armor_text = ""
    body_paras = []
    ability_paras = []

    # Scan
    saw_table = False
    for typ, *payload in sub:
        if typ == "blank" or typ == "hr":
            continue
        if typ == "p":
            text = payload[0]
            # Flavor is the first italic *…*
            if not flavor_text and text.startswith("*") and text.endswith("*"):
                flavor_text = text[1:-1]
                continue
            # Weapons / Armor / Abilities lines
            if text.startswith("**Weapons:**"):
                weapons_text = text
                continue
            if text.startswith("**Armor:**"):
                armor_text = text
                continue
            if saw_table and not body_paras:
                body_paras.append(text)
                continue
            if body_paras and not ability_paras and "**" in text and \
                    not text.startswith("**"):
                body_paras.append(text)
                continue
            # Ability line begins with **Name** — …
            if text.startswith("**"):
                ability_paras.append(text)
                continue
            # Otherwise more body
            body_paras.append(text)
        elif typ == "table":
            saw_table = True
            stats_rows = payload[0]

    # Build right-column content
    right = []
    right.append(Paragraph(name, CLASS_NAME))
    if flavor_text:
        right.append(Paragraph(_inline(flavor_text), CLASS_FLAVOR))
    if stats_rows:
        rr = [[Paragraph(_inline(c), TABLE_HEAD) for c in stats_rows[0]],
              [Paragraph(_inline(c), TABLE_CELL) for c in stats_rows[1]]]
        right.append(_mini_stat_table(rr))
        right.append(Spacer(0, 6))
    if weapons_text:
        right.append(Paragraph(_inline(weapons_text), BODY_NOINDENT))
    if armor_text:
        right.append(Paragraph(_inline(armor_text), BODY_NOINDENT))
    for p in body_paras:
        right.append(Paragraph(_inline(p), BODY))
    for a in ability_paras:
        right.append(Paragraph(_inline(a), BODY_NOINDENT))

    # Left column: portrait
    left = []
    if portrait_path and portrait_path.exists():
        img = Image(str(portrait_path), width=2.3 * inch, height=2.5 * inch,
                    kind="proportional")
        left.append(img)

    # Two-column layout using a table
    layout = Table([[left, right]],
                   colWidths=[2.5 * inch, TEXT_WIDTH - 2.5 * inch - 0.15 * inch])
    layout.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return [KeepTogether(layout),
            Spacer(0, 8),
            OrnateRule(TEXT_WIDTH, color=RULE, size=3, gap=6, thickness=0.7),
            Spacer(0, 10)]


# ── Main render loop ────────────────────────────────────────────────

def _data_table(rows, caption=None, title=None, col_widths=None):
    header = [Paragraph(_inline(c), TABLE_HEAD) for c in rows[0]]
    body_cells = []
    for row in rows[1:]:
        body_cells.append([Paragraph(_inline(c), TABLE_CELL) for c in row])
    data = [header] + body_cells
    if col_widths is None:
        n = len(rows[0])
        col_widths = [TEXT_WIDTH / n] * n
    tbl = Table(data, colWidths=col_widths, hAlign="CENTER", repeatRows=1)
    style = [
        ("FONT",      (0, 0), (-1, 0),  BOLD_FONT, 10.5),
        ("TEXTCOLOR", (0, 0), (-1, 0),  ACCENT),
        ("LINEBELOW", (0, 0), (-1, 0),  0.8, ACCENT_SOFT),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, ACCENT_SOFT),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    for r in range(1, len(data)):
        style.append(("LINEBELOW", (0, r), (-1, r), 0.3, HexColor("#C9B98E")))
    tbl.setStyle(TableStyle(style))
    out = []
    if title:
        out.append(Paragraph(title, TABLE_TITLE))
    if caption:
        out.append(Paragraph(caption, TABLE_CAPTION))
    out.append(tbl)
    out.append(Spacer(0, 6))
    return out


def _render_blocks(story, blocks):
    """Turn the block stream into reportlab flowables, skipping class
    sections (those are rendered separately via _class_page)."""

    in_professions = False
    skip_until_next_h3_or_h2 = False

    # ── Skip the document's front matter (H1 title + H2 "PLAYER'S
    # HANDBOOK" + two italic subtitle paragraphs).  The title page
    # renders these via _title_page() with custom layout, so echoing
    # them in the body would duplicate content.
    i = 0
    while i < len(blocks):
        t, *p = blocks[i]
        if t == "h2" and p[0].strip() != "PLAYER'S HANDBOOK":
            break
        i += 1

    # Also skip any leading HR / blank blocks that came just before
    # the first real section header so we don't double-rule.
    while i < len(blocks) and blocks[i][0] in ("hr", "blank"):
        i += 1

    while i < len(blocks):
        typ, *payload = blocks[i]

        # Skip the class H3 blocks — those are rendered by _class_page.
        if typ == "h3" and payload[0].strip() in CLASS_ORDER and in_professions:
            skip_until_next_h3_or_h2 = True
            i += 1
            continue
        if skip_until_next_h3_or_h2:
            if typ in ("h2",):
                skip_until_next_h3_or_h2 = False
            elif typ == "h3" and payload[0].strip() not in CLASS_ORDER:
                skip_until_next_h3_or_h2 = False
            else:
                i += 1
                continue

        if typ == "h1":
            # Skip the top-level title — handled by title page
            i += 1
            continue
        if typ == "h2":
            title = payload[0].strip()
            if title == "PLAYER'S HANDBOOK":
                i += 1
                continue
            story.append(PageBreak())
            story.append(Spacer(0, 6))
            story.append(SectionHeader(title, TEXT_WIDTH))
            in_professions = (title == "THE PROFESSIONS")
            i += 1

            # Insert profession table + class pages right after THE PROFESSIONS
            if in_professions:
                # Continue normally — the Table 1 sub-heading + table will
                # be rendered as usual; after that we'll inject class pages.
                pass
            continue
        if typ == "h3":
            text = payload[0].strip()
            # Special-case the in-content "Table 1" header to mimic the
            # centered "TABLE 1 / Characteristics of each Profession" layout
            if text.lower().startswith("table 1"):
                story.append(Paragraph("TABLE 1", TABLE_TITLE))
                story.append(Paragraph(
                    "<i>Characteristics of each Profession</i>",
                    TABLE_CAPTION))
                i += 1
                continue
            story.append(Paragraph(text, H3))
            i += 1
            continue
        if typ == "p":
            text = payload[0]
            # Standalone emphasis-only paragraphs → italic flavor text
            if text.startswith("*") and text.endswith("*") and "**" not in text:
                story.append(Paragraph(_inline(text), FLAVOR))
            else:
                # Paragraphs that contain an unbreakable URL, a Markdown
                # link, or start with a bold list-marker like "**N.**"
                # wrap poorly under full justification (the URL can't
                # hyphenate, so the remaining words get stretched).  Use
                # the non-justified variant for those so word spacing
                # stays natural.
                has_link = "http://" in text or "https://" in text or \
                           "](" in text
                looks_like_numbered = bool(re.match(r"^\*\*\d+\.\*\*\s", text))
                style = BODY_NOINDENT if (has_link or looks_like_numbered) \
                    else BODY
                story.append(Paragraph(_inline(text), style))
            i += 1
            continue
        if typ == "ul":
            items = payload[0]
            for it in items:
                story.append(Paragraph("• " + _inline(it),
                                       _para_style("UL", leftIndent=18,
                                                   firstLineIndent=-8,
                                                   spaceAfter=2,
                                                   alignment=0)))
            story.append(Spacer(0, 4))
            i += 1
            continue
        if typ == "ol":
            items = payload[0]
            for idx, it in enumerate(items, 1):
                story.append(Paragraph(f"<b>{idx}.</b> " + _inline(it),
                                       _para_style("OL", leftIndent=18,
                                                   firstLineIndent=-12,
                                                   spaceAfter=3,
                                                   alignment=0)))
            story.append(Spacer(0, 4))
            i += 1
            continue
        if typ == "hr":
            # Collapse HRs that sit directly next to a section header —
            # SectionHeader already has its own decorative divider.
            prev_nonblank = None
            for k in range(i - 1, -1, -1):
                if blocks[k][0] != "blank":
                    prev_nonblank = blocks[k][0]
                    break
            next_nonblank = None
            for k in range(i + 1, len(blocks)):
                if blocks[k][0] != "blank":
                    next_nonblank = blocks[k][0]
                    break
            if prev_nonblank == "h2" or next_nonblank == "h2":
                i += 1
                continue
            story.append(Spacer(0, 4))
            story.append(OrnateRule(TEXT_WIDTH, color=RULE,
                                    size=3, gap=6, thickness=0.7))
            story.append(Spacer(0, 4))
            i += 1
            continue
        if typ == "table":
            rows = payload[0]
            # Are we inside Professions and is this the main Table 1?
            if rows and rows[0][0].lower() == "class":
                story.extend(_data_table(rows))
                # After Table 1, insert class pages
                if in_professions:
                    story.append(Spacer(0, 12))
                    for class_name in CLASS_ORDER:
                        story.append(PageBreak())
                        story.append(Spacer(0, 4))
                        pose = ASSETS / f"portrait_{class_name.lower()}.png"
                        story.extend(_class_page(blocks, class_name, pose))
            else:
                story.extend(_data_table(rows))
            i += 1
            continue
        if typ == "code":
            story.append(Paragraph(
                "<font face='Courier-Bold'>" +
                _html_escape(payload[0]).replace("\n", "<br/>") +
                "</font>", CODE))
            i += 1
            continue
        if typ == "blank":
            i += 1
            continue
        # Unknown — ignore
        i += 1


# ── Title page ──────────────────────────────────────────────────────

def _title_page(story):
    story.append(Spacer(0, 50))
    story.append(Paragraph("REALM OF SHADOW", H1))
    story.append(Spacer(0, 2))
    story.append(OrnateRule(TEXT_WIDTH * 0.7, color=ACCENT, size=3, gap=6,
                            thickness=1.0))
    story.append(Spacer(0, 18))

    cover = ASSETS / "cover_art.png"
    if cover.exists():
        # Scale: original 1668×640 aspect ratio ~2.6
        img_w = 5.5 * inch
        img_h = img_w * (640 / 1668)
        img = Image(str(cover), width=img_w, height=img_h)
        img.hAlign = "CENTER"
        story.append(img)

    story.append(Spacer(0, 18))
    story.append(OrnateRule(TEXT_WIDTH * 0.7, color=ACCENT, size=3, gap=6,
                            thickness=1.0))
    story.append(Spacer(0, 16))
    story.append(Paragraph("PLAYER'S HANDBOOK",
                           _para_style("TitleSub", fontName=BOLD_FONT,
                                       fontSize=28, leading=32,
                                       textColor=ACCENT, alignment=1,
                                       spaceAfter=10)))
    story.append(Spacer(0, 4))
    story.append(Paragraph("<i>A Player's Guide to the Lands of Shadow</i>",
                           _para_style("TitleMeta", fontName=ITAL_FONT,
                                       fontSize=12, leading=16,
                                       textColor=ACCENT_SOFT, alignment=1,
                                       spaceAfter=2)))
    story.append(Paragraph("<i>An Ultima III-Inspired Tactical Fantasy RPG</i>",
                           _para_style("TitleMeta2", fontName=ITAL_FONT,
                                       fontSize=12, leading=16,
                                       textColor=ACCENT_SOFT, alignment=1)))


# ── Build ────────────────────────────────────────────────────────────

def build():
    md = MD_PATH.read_text(encoding="utf-8")
    blocks = _tokenize(md)

    doc = BaseDocTemplate(
        str(OUT_PATH),
        pagesize=letter,
        leftMargin=TEXT_LEFT, rightMargin=PAGE_W - TEXT_RIGHT,
        topMargin=PAGE_H - TEXT_TOP, bottomMargin=TEXT_BOTTOM,
        title="Realm of Shadow — Player's Handbook",
        author="Matt Campbell",
        subject="Player's Handbook",
        creator="docs/manuals/build_manual.py",
    )
    frame = Frame(TEXT_LEFT, TEXT_BOTTOM,
                  TEXT_WIDTH, TEXT_HEIGHT,
                  leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0,
                  id="normal", showBoundary=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=_on_page)])

    story = []
    _title_page(story)
    _render_blocks(story, blocks)

    doc.build(story)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB, "
          f"{len(blocks)} blocks)")


if __name__ == "__main__":
    build()
