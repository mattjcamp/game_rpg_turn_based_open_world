"""
Shared pick-lock / Knock-spell dialog for any tile marked ``locked``.

The dungeon state has always supported locked-door doorways that were
placed procedurally.  This mixin exposes the same UX — bump a tile,
see a dialog listing Pick Lock (by a Thief with a Lockpick) and Cast
Knock (by a caster with the spell + enough MP), pick one, see the
animation, result message, and SFX — for **any** tile that has
``tile_properties[f"{col},{row}"]["locked"] == True`` on its current
map.  That includes tiles the designer paints in the map editor (via
the Attributes panel's new Locked toggle) and legacy dungeon
``TILE_LOCKED_DOOR`` tiles alike.

States adopt the mixin by:
  1. Inheriting ``LockInteractionMixin``.
  2. Calling ``self._init_lock_interaction()`` from ``__init__``.
  3. In the move/bump path, calling
     ``self._try_open_locked(tile_map, target_col, target_row)`` and
     returning early if it returns ``True``.
  4. In the input dispatch, routing events to
     ``self._handle_lock_interact_input(event)`` while
     ``self.door_interact_active`` is True.
  5. (Optional) overriding ``_on_lock_opened`` to perform a
     state-specific tile change (e.g. the dungeon converts
     ``TILE_LOCKED_DOOR`` to ``TILE_DDOOR``).  The default simply
     removes the ``locked`` tile_property so the tile reverts to
     its base walkability.

The dialog input/render layer reuses the existing dungeon renderer
(``Renderer._u3_draw_door_interact``) via the ``_get_door_interact_state``
accessor — town and overworld states hand the same dict to the
renderer so every editor gets the same panel without new UI code.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Optional

import pygame

from src.settings import TILE_LOCKED_DOOR, TILE_DDOOR


class LockInteractionMixin:
    """Mix-in that provides pick-lock and Knock dialog handling."""

    # ── State init ─────────────────────────────────────────────────

    def _init_lock_interaction(self) -> None:
        """Seed the fields the dialog reads and writes.

        Safe to call from a state's ``__init__`` or a
        ``reset_for_new_game`` hook.
        """
        self.door_interact_active = False
        self.door_interact_col = 0
        self.door_interact_row = 0
        self.door_interact_cursor = 0
        self.door_interact_options = []
        self.door_unlock_anim = None
        # Remember which tile_map the dialog is acting on so the
        # animation completion can update the right map even if the
        # active state has since changed tile_map (e.g. after a town
        # transition). Also remember a per-lock callback so the host
        # state can customise what "opened" means for this tile.
        self._lock_interact_tile_map = None
        self._lock_interact_on_open = None

    # ── Public entry point from movement code ──────────────────────

    def _try_open_locked(self, tile_map: Any, col: int, row: int,
                         on_open: Optional[Callable] = None) -> bool:
        """If the tile at (col, row) on *tile_map* is locked, open the
        pick-lock dialog and return True.  Otherwise return False.

        Detects both legacy ``TILE_LOCKED_DOOR`` tiles and any tile
        whose ``tile_properties`` dict has ``"locked": True`` set via
        the map editor's Attributes panel.

        *on_open* is an optional callback invoked after a successful
        pick/knock animation completes; it receives ``(tile_map, col,
        row)`` and is responsible for applying any state-specific
        change (for example the dungeon converts the tile to
        ``TILE_DDOOR``).  If omitted, the default behaviour is to
        remove the ``locked`` tile_property so the tile reverts to
        its base walkable state.
        """
        if tile_map is None:
            return False
        tile_id = tile_map.get_tile(col, row)
        tprops = (getattr(tile_map, "tile_properties", None) or {}).get(
            f"{col},{row}", {})
        is_locked = bool(tprops.get("locked")) or tile_id == TILE_LOCKED_DOOR
        if not is_locked:
            return False
        self._show_lock_interact(col, row, tile_map, on_open=on_open)
        return True

    # ── Dialog building ────────────────────────────────────────────

    def _show_lock_interact(self, col: int, row: int, tile_map: Any,
                            on_open: Optional[Callable] = None) -> None:
        """Open the Pick Lock / Cast Knock / Leave dialog."""
        party = self.game.party

        self.door_interact_col = col
        self.door_interact_row = row
        self.door_interact_cursor = 0
        self._lock_interact_tile_map = tile_map
        self._lock_interact_on_open = on_open

        options = []

        # Thief with lockpicks?
        thief = self._find_lock_thief()
        picks = party.inv_get_charges("Lockpick")
        if thief and picks > 0:
            options.append(
                (f"Pick Lock ({thief.name}, {picks} picks)", "pick"))
        elif thief and picks <= 0:
            options.append(("Pick Lock (no lockpicks!)", "no_picks"))
        elif thief is None:
            options.append(("Pick Lock (no thief!)", "no_thief"))

        # Caster with Knock + MP?
        knock_caster = self._find_knock_caster()
        if knock_caster:
            from src.party import SPELLS_DATA
            knock = SPELLS_DATA.get("knock", {})
            mp_cost = knock.get("mp_cost", 7)
            if knock_caster.current_mp >= mp_cost:
                options.append(
                    (f"Cast Knock ({knock_caster.name}, {mp_cost} MP)",
                     "knock"))
            else:
                options.append(
                    ("Cast Knock (insufficient MP)", "no_knock_mp"))

        options.append(("Leave", "leave"))
        self.door_interact_options = options
        self.door_interact_active = True

    # ── Input handling (call from the state's KEYDOWN dispatch) ────

    def _handle_lock_interact_input(self, event) -> None:
        if not self.door_interact_active:
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.door_interact_cursor = (
                (self.door_interact_cursor - 1)
                % max(1, len(self.door_interact_options)))
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.door_interact_cursor = (
                (self.door_interact_cursor + 1)
                % max(1, len(self.door_interact_options)))
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            _, action = self.door_interact_options[
                self.door_interact_cursor]
            self._resolve_lock_interact(action)
        elif event.key == pygame.K_ESCAPE:
            self._close_lock_interact()

    def _resolve_lock_interact(self, action: str) -> None:
        col, row = self.door_interact_col, self.door_interact_row
        if action == "pick":
            self._close_lock_interact()
            self._attempt_lock_pick(col, row)
        elif action == "no_picks":
            self._close_lock_interact()
            thief = self._find_lock_thief()
            name = thief.name if thief else "Thief"
            self._lock_message(f"{name} has no lockpicks left!", 2000)
        elif action == "no_thief":
            self._close_lock_interact()
            self._lock_message(
                "You need a thief to pick the lock!", 2000)
        elif action == "knock":
            self._close_lock_interact()
            self._attempt_knock_spell(col, row)
        elif action == "no_knock_mp":
            self._close_lock_interact()
            caster = self._find_knock_caster()
            name = caster.name if caster else "Caster"
            self._lock_message(
                f"{name} doesn't have enough MP to cast Knock!", 2000)
        else:
            self._close_lock_interact()

    def _close_lock_interact(self) -> None:
        self.door_interact_active = False
        self.door_interact_options = []
        self.door_interact_cursor = 0

    # ── Attempts ───────────────────────────────────────────────────

    def _attempt_lock_pick(self, col: int, row: int) -> None:
        party = self.game.party
        thief = self._find_lock_thief()
        if thief is None:
            self._lock_message(
                "The door is locked. You need a thief!", 2000)
            return
        picks_left = party.inv_get_charges("Lockpick")
        if picks_left <= 0:
            self._lock_message(
                f"{thief.name} has no lockpicks left!", 2000)
            return
        party.inv_consume_charge("Lockpick")
        remaining = party.inv_get_charges("Lockpick")

        roll = (random.randint(1, 20)
                + thief.get_modifier(thief.dexterity))
        if roll >= 12:
            self._start_unlock_animation(col, row)
            self._safe_sfx("lock_pick_success")
            self._lock_message(
                f"{thief.name} picked the lock! "
                f"({remaining} picks left)", 1800)
        else:
            self._safe_sfx("lock_pick_fail")
            self._lock_message(
                f"{thief.name} failed to pick the lock. "
                f"({remaining} picks left)", 1500)

    def _attempt_knock_spell(self, col: int, row: int) -> None:
        from src.party import SPELLS_DATA
        caster = self._find_knock_caster()
        if caster is None:
            self._lock_message("No one can cast Knock!", 2000)
            return
        knock = SPELLS_DATA.get("knock", {})
        mp_cost = knock.get("mp_cost", 7)
        ev = knock.get("effect_value", {})
        save_dc = ev.get("save_dc_base", 12)
        save_stat = ev.get("save_stat", "intelligence")
        if caster.current_mp < mp_cost:
            self._lock_message(
                f"{caster.name} doesn't have enough MP! "
                f"({caster.current_mp}/{mp_cost} MP)", 2000)
            return
        caster.current_mp -= mp_cost
        stat_val = getattr(caster, save_stat, 10)
        modifier = caster.get_modifier(stat_val)
        roll = random.randint(1, 20)
        total = roll + modifier
        if total >= save_dc:
            self._start_unlock_animation(col, row)
            self._safe_sfx("lock_pick_success")
            self._lock_message(
                f"{caster.name} casts Knock — the lock clicks open! "
                f"(roll {roll}+{modifier}={total} vs DC {save_dc}, "
                f"{caster.current_mp} MP left)", 2000)
            try:
                self.game.game_log.append(
                    f"{caster.name} cast Knock and unlocked a door "
                    f"(d20={roll}+{modifier}={total} vs DC {save_dc}).")
            except Exception:
                pass
        else:
            self._safe_sfx("lock_pick_fail")
            self._lock_message(
                f"{caster.name}'s Knock fizzles... "
                f"(roll {roll}+{modifier}={total} vs DC {save_dc}, "
                f"{caster.current_mp} MP left)", 2000)

    # ── Animation ──────────────────────────────────────────────────

    def _start_unlock_animation(self, col: int, row: int) -> None:
        """Queue the brief unlock glow animation at (col, row)."""
        self.door_unlock_anim = {
            "col": col,
            "row": row,
            "timer": 1200,
            "duration": 1200,
        }

    def _tick_lock_animation(self, dt_ms: int) -> None:
        """Call from the state's update() to progress the animation.

        When the timer hits zero the mixin invokes the configured
        ``on_open`` callback (or ``_on_lock_opened`` default) so the
        tile change happens at the end of the visual glow rather
        than instantly.
        """
        if not self.door_unlock_anim:
            return
        self.door_unlock_anim["timer"] -= dt_ms
        if self.door_unlock_anim["timer"] <= 0:
            col = self.door_unlock_anim["col"]
            row = self.door_unlock_anim["row"]
            tmap = self._lock_interact_tile_map
            callback = self._lock_interact_on_open
            self.door_unlock_anim = None
            if callable(callback):
                try:
                    callback(tmap, col, row)
                except Exception:
                    self._on_lock_opened_default(tmap, col, row)
            else:
                self._on_lock_opened_default(tmap, col, row)
            self._lock_interact_tile_map = None
            self._lock_interact_on_open = None

    # ── Helpers ────────────────────────────────────────────────────

    def _get_door_interact_state(self):
        """Return the dict the renderer consumes, or None."""
        if not self.door_interact_active:
            return None
        return {
            "col": self.door_interact_col,
            "row": self.door_interact_row,
            "cursor": self.door_interact_cursor,
            "options": self.door_interact_options,
        }

    def _find_lock_thief(self):
        for m in self.game.party.members:
            if m.is_alive() and m.char_class == "Thief":
                return m
        return None

    def _find_knock_caster(self):
        from src.party import SPELLS_DATA
        knock = SPELLS_DATA.get("knock")
        if knock is None:
            return None
        allowed = [c.lower() for c in knock.get("allowable_classes", [])]
        min_lvl = knock.get("min_level", 1)
        for m in self.game.party.members:
            if (m.is_alive()
                    and m.char_class.lower() in allowed
                    and m.level >= min_lvl):
                return m
        return None

    # ── Virtual hooks (override in host state if needed) ───────────

    def _on_lock_opened_default(self, tile_map, col, row) -> None:
        """Default behaviour when a locked tile is picked open.

        Legacy dungeon ``TILE_LOCKED_DOOR`` tiles are converted to
        ``TILE_DDOOR`` (open door).  Any other tile just has its
        ``locked`` tile_property removed so it reverts to its base
        walkability.
        """
        if tile_map is None:
            return
        tile_id = tile_map.get_tile(col, row)
        if tile_id == TILE_LOCKED_DOOR:
            tile_map.set_tile(col, row, TILE_DDOOR)
            return
        props = getattr(tile_map, "tile_properties", None)
        if props is not None:
            pos_key = f"{col},{row}"
            entry = props.get(pos_key)
            if isinstance(entry, dict) and "locked" in entry:
                del entry["locked"]
                if not entry:
                    del props[pos_key]

    def _lock_message(self, msg: str, duration_ms: int) -> None:
        """Show *msg* in whatever way the host state does."""
        if hasattr(self, "show_message"):
            try:
                self.show_message(msg, duration_ms)
                return
            except Exception:
                pass
        # Fallback — at least keep a log entry
        try:
            self.game.game_log.append(msg)
        except Exception:
            pass

    def _safe_sfx(self, name: str) -> None:
        try:
            self.game.sfx.play(name)
        except Exception:
            pass
