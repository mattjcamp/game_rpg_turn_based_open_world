"""
Tests for the animated tile-effect overlay system.

The map editor lets authors attach a procedural animation to any tile
via the inspector. The available effects are declared in
``src.map_editor.EFFECT_CYCLE`` (which drives the Enter/Space picker)
and rendered at runtime by ``Renderer._draw_tile_effect_overlay``,
which dispatches to a per-effect ``_draw_effect_<name>`` method.

Coverage here:
  * The cycle exposes the expected effects in a stable order, including
    the new ``torch`` option introduced alongside ``fire``.
  * Every cycle entry has a human-readable label.
  * The runtime dispatcher routes each effect string to the right
    drawer — including ``torch`` — and silently ignores unknown ones.
"""

import types
import unittest.mock as mock

import pytest

from src.map_editor import (
    EFFECT_CYCLE, EFFECT_NONE, EFFECT_RISING_SMOKE, EFFECT_FIRE,
    EFFECT_TORCH, EFFECT_FAIRY_LIGHT, _EFFECT_LABELS,
)


# ── Effect catalogue ────────────────────────────────────────────────


class TestEffectCycle:

    def test_cycle_contains_all_known_effects(self):
        # Order matters here only in that EFFECT_NONE must come first
        # (so the picker starts on "no effect"); the remaining order
        # is the authoring convention, exercised below.
        assert EFFECT_CYCLE[0] == EFFECT_NONE
        for name in (EFFECT_RISING_SMOKE, EFFECT_FIRE,
                     EFFECT_TORCH, EFFECT_FAIRY_LIGHT):
            assert name in EFFECT_CYCLE, (
                f"{name!r} missing from EFFECT_CYCLE — the inspector "
                f"picker won't be able to land on it.")

    def test_torch_immediately_follows_fire(self):
        """Authoring nicety: pressing Enter on a fire tile should
        advance to torch so the two flame sizes can be compared with
        a single keypress."""
        i_fire = EFFECT_CYCLE.index(EFFECT_FIRE)
        assert EFFECT_CYCLE[i_fire + 1] == EFFECT_TORCH

    def test_every_cycle_entry_has_a_label(self):
        for effect in EFFECT_CYCLE:
            assert effect in _EFFECT_LABELS, (
                f"{effect!r} is in the cycle but has no label entry — "
                f"the inspector would render an empty value.")

    def test_torch_label_reads_naturally(self):
        assert _EFFECT_LABELS[EFFECT_TORCH] == "torch"


# ── Runtime dispatcher (Renderer._draw_tile_effect_overlay) ─────────


def _make_renderer_proxy():
    """Build a stand-in renderer carrying just the dispatcher and the
    per-effect drawers as mocks.

    Pulling the unbound dispatcher off the real ``Renderer`` class
    avoids the heavy ``__init__`` (which loads sprites and opens a
    pygame display).  We bind it to a ``SimpleNamespace`` whose
    ``_draw_effect_*`` attributes are mocks, so we can assert which
    one was called for a given effect string.
    """
    from src.renderer import Renderer
    proxy = types.SimpleNamespace(
        _draw_effect_rising_smoke=mock.Mock(),
        _draw_effect_fire=mock.Mock(),
        _draw_effect_torch=mock.Mock(),
        _draw_effect_fairy_light=mock.Mock(),
    )
    proxy._draw_tile_effect_overlay = (
        Renderer._draw_tile_effect_overlay.__get__(proxy, type(proxy)))
    return proxy


class TestEffectDispatcher:

    @pytest.mark.parametrize("effect_name, drawer_attr", [
        ("rising_smoke", "_draw_effect_rising_smoke"),
        ("fire",         "_draw_effect_fire"),
        ("torch",        "_draw_effect_torch"),
        ("fairy_light",  "_draw_effect_fairy_light"),
    ])
    def test_dispatch_routes_to_correct_drawer(
            self, effect_name, drawer_attr):
        proxy = _make_renderer_proxy()
        tile_props = {(3, 4): {"effect": effect_name}}
        proxy._draw_tile_effect_overlay(
            px=10, py=20, ts=24, wc=3, wr=4,
            tile_properties=tile_props)
        getattr(proxy, drawer_attr).assert_called_once()
        # Sanity: no other drawer fired.
        for other in ("_draw_effect_rising_smoke",
                       "_draw_effect_fire",
                       "_draw_effect_torch",
                       "_draw_effect_fairy_light"):
            if other != drawer_attr:
                assert not getattr(proxy, other).called, (
                    f"{other} fired for effect {effect_name!r}")

    def test_unknown_effect_is_silently_ignored(self):
        """Forward-compat: a save authored against a future editor
        version with new effects must still load on the current
        renderer without crashing."""
        proxy = _make_renderer_proxy()
        tile_props = {(0, 0): {"effect": "definitely_not_a_real_effect"}}
        # No drawer should fire and nothing should raise.
        proxy._draw_tile_effect_overlay(
            px=0, py=0, ts=24, wc=0, wr=0,
            tile_properties=tile_props)
        for drawer in ("_draw_effect_rising_smoke",
                       "_draw_effect_fire",
                       "_draw_effect_torch",
                       "_draw_effect_fairy_light"):
            assert not getattr(proxy, drawer).called

    def test_string_keyed_props_also_dispatch(self):
        """Editor-authored maps store tile_properties with string
        keys (``"col,row"``); procedural maps use tuple keys. The
        dispatcher must accept both — without this the torch effect
        wouldn't render on hand-edited maps."""
        proxy = _make_renderer_proxy()
        tile_props = {"7,2": {"effect": "torch"}}
        proxy._draw_tile_effect_overlay(
            px=0, py=0, ts=24, wc=7, wr=2,
            tile_properties=tile_props)
        proxy._draw_effect_torch.assert_called_once()

    def test_no_props_at_position_is_a_noop(self):
        proxy = _make_renderer_proxy()
        proxy._draw_tile_effect_overlay(
            px=0, py=0, ts=24, wc=99, wr=99,
            tile_properties={(0, 0): {"effect": "torch"}})
        for drawer in ("_draw_effect_rising_smoke",
                       "_draw_effect_fire",
                       "_draw_effect_torch",
                       "_draw_effect_fairy_light"):
            assert not getattr(proxy, drawer).called
