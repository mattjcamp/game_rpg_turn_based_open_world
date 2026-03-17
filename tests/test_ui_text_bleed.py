"""Tests that UI text elements fit within their designated containers.

Verifies that rendered text via pygame fonts does not bleed out of
the panel boundaries used in the features spell list and other UI
elements.
"""
import json
import os
import sys

import pytest

# Ensure we can import from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# We need pygame initialised for font metrics but not a display.
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
pygame.init()

from src.settings import SCREEN_WIDTH, SCREEN_HEIGHT


# ---------- helpers --------------------------------------------------

def _load_spells():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "spells.json")
    with open(path) as f:
        return json.load(f).get("spells", [])


def _make_fonts():
    """Return (font_18, font_med_16, font_small_14) matching renderer."""
    return (
        pygame.font.SysFont("liberationsans", 18),
        pygame.font.SysFont("liberationsans", 16),
        pygame.font.SysFont("liberationsans", 14),
    )


# ---------- feature spell list panel constants -----------------------
# These match draw_features_screen() in renderer.py
FEAT_LEFT_X = 40
FEAT_LEFT_W = 280
FEAT_RIGHT_X = FEAT_LEFT_X + FEAT_LEFT_W + 20
FEAT_RIGHT_W = SCREEN_WIDTH - FEAT_RIGHT_X - 40


# ---------- tests ----------------------------------------------------

class TestSpellListTextBleed:
    """Verify no text overflows the left or right panels in the spell
    list view of the features editor."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.spells = _load_spells()
        self.font, self.fm, self.fs = _make_fonts()

    def test_spell_name_fits_left_panel(self):
        """Each spell name (with "> " prefix) must fit in left_w - 24."""
        max_pw = FEAT_LEFT_W - 24
        for spell in self.spells:
            name = spell.get("name", "???")
            text = f"> {name}"
            w, _ = self.fm.size(text)
            assert w <= max_pw, (
                f"Spell name '{name}' is {w}px wide, exceeds "
                f"left panel max {max_pw}px"
            )

    def test_level_mp_subtitle_fits_left_panel(self):
        """The 'L#' and 'MP cost' subtitle must not exceed left panel."""
        # L# drawn at left_x + 26, MP drawn at left_x + 70
        # Both must end before left_x + left_w
        max_level_w = 70 - 26  # space available for L# text
        max_mp_w = FEAT_LEFT_W - 70  # space from mp_x to right edge
        for spell in self.spells:
            lvl = spell.get("min_level", 1)
            mp = spell.get("mp_cost", 0)
            lw, _ = self.fs.size(f"L{lvl}")
            mw, _ = self.fs.size(f"{mp} MP")
            assert lw <= max_level_w, (
                f"Level text 'L{lvl}' ({lw}px) exceeds column "
                f"width {max_level_w}px"
            )
            assert mw <= max_mp_w, (
                f"MP text '{mp} MP' ({mw}px) exceeds available "
                f"width {max_mp_w}px"
            )

    def test_level_and_mp_do_not_overlap(self):
        """L# text ending must not reach the MP text start position.

        L# is drawn at x-offset 26, MP at x-offset 70.
        So L# text width + 26 must be < 70.
        """
        for spell in self.spells:
            lvl = spell.get("min_level", 1)
            lw, _ = self.fs.size(f"L{lvl}")
            end_x = 26 + lw
            assert end_x <= 70, (
                f"Level 'L{lvl}' ends at {end_x}px, bleeds into MP "
                f"column starting at 70px"
            )

    def test_right_panel_detail_text_fits(self):
        """Spell detail info on the right panel must fit."""
        max_pw = FEAT_RIGHT_W - 36  # description wrap width
        for spell in self.spells:
            # Title
            name = spell.get("name", "???")
            tw, _ = self.font.size(name)
            assert tw <= FEAT_RIGHT_W - 32, (
                f"Spell title '{name}' ({tw}px) exceeds right panel"
            )
            # Casting type line
            ctype = spell.get("casting_type", "sorcerer").title()
            line = f"{ctype} spell"
            cw, _ = self.fm.size(line)
            assert cw <= FEAT_RIGHT_W - 32, (
                f"Casting type line '{line}' ({cw}px) exceeds right panel"
            )
            # Classes line
            classes = ", ".join(spell.get("allowable_classes", []))
            cline = f"Classes: {classes}"
            clw, _ = self.fm.size(cline)
            assert clw <= FEAT_RIGHT_W - 32, (
                f"Classes line '{cline}' ({clw}px) exceeds right panel "
                f"max {FEAT_RIGHT_W - 32}px"
            )
            # Summary line
            summary = (
                f"Level {spell.get('min_level', 1)}  |  "
                f"{spell.get('mp_cost', 0)} MP  |  "
                f"{spell.get('effect_type', '?')}"
            )
            sw, _ = self.fm.size(summary)
            assert sw <= FEAT_RIGHT_W - 32, (
                f"Summary line '{summary}' ({sw}px) exceeds right panel "
                f"max {FEAT_RIGHT_W - 32}px"
            )
            # Description words (each individual word must fit max_pw
            # or wrapping is impossible)
            desc = spell.get("description", "")
            for word in desc.split():
                ww, _ = self.fm.size(word)
                assert ww <= max_pw, (
                    f"Word '{word}' ({ww}px) in '{name}' description "
                    f"exceeds wrap width {max_pw}px — cannot wrap"
                )

    def test_section_header_fits_left_panel(self):
        """Section headers 'Sorcerer Spells' / 'Cleric Spells' must
        fit within the left panel."""
        max_w = FEAT_LEFT_W - 24
        for label in ("Sorcerer Spells", "Cleric Spells"):
            w, _ = self.fs.size(label)
            assert w <= max_w, (
                f"Section header '{label}' ({w}px) exceeds left panel "
                f"max {max_w}px"
            )
