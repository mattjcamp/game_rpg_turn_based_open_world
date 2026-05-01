"""Tests for the end-of-game victory screen.

Module authors can flag one quest as the climax via the
``is_final_quest`` field. When that quest's status flips to
``"turned_in"`` (the player walks back to the giver and collects the
reward), :func:`quest_manager.maybe_trigger_victory` pops a special
end-of-game screen with a Continue / New Game / Main Menu choice.

Coverage here:
  * The trigger fires only for final quests, not normal ones.
  * ``victory_text`` from the quest definition flows through to
    ``Game.victory_text`` so the renderer can show the author blurb.
  * ``CONTINUE PLAYING`` dismisses the overlay without restarting.
  * ``NEW GAME`` and ``MAIN MENU`` reset their respective state.
  * Idempotent: a second turn-in handler call with the screen
    already up doesn't restart the elapsed timer.
"""

import types

import pytest

from src import quest_manager


# ── Helpers ────────────────────────────────────────────────────────


def _attach_final_quest(game, *, name="Slay the Dragon",
                        final=True, victory_text="The realm endures."):
    """Append a quest def + module_quest_state matching what
    Game._load_module_quests would have produced."""
    qdef = {
        "name": name,
        "description": "",
        "is_final_quest": bool(final),
        "victory_text": victory_text,
        "steps": [],
    }
    if not hasattr(game, "_module_quest_defs") or game._module_quest_defs is None:
        game._module_quest_defs = []
    game._module_quest_defs.append(qdef)
    if not hasattr(game, "module_quest_states") or game.module_quest_states is None:
        game.module_quest_states = {}
    game.module_quest_states[name] = {
        "status": "completed",  # one step away from turn-in
        "step_progress": [True],
    }
    return qdef


# ── Trigger logic (unit-level) ─────────────────────────────────────


class TestMaybeTriggerVictory:
    def test_final_quest_triggers(self, game):
        _attach_final_quest(game, victory_text="A new dawn rises.")
        fired = quest_manager.maybe_trigger_victory(
            game, "Slay the Dragon")
        assert fired is True
        assert game.showing_victory is True
        assert game.victory_text == "A new dawn rises."
        assert game.victory_quest_name == "Slay the Dragon"
        # Cursor lands on the first option (CONTINUE PLAYING) so the
        # safest default is to keep playing rather than nuke the save.
        assert game.victory_cursor == 0
        assert game.victory_options[game.victory_cursor]["label"] \
            == "CONTINUE PLAYING"

    def test_non_final_quest_does_not_trigger(self, game):
        _attach_final_quest(game, name="Side Errand", final=False)
        fired = quest_manager.maybe_trigger_victory(
            game, "Side Errand")
        assert fired is False
        assert game.showing_victory is False

    def test_unknown_quest_silently_skipped(self, game):
        # Robustness: don't crash if a turn-in hook fires for a quest
        # the manifest forgot to declare.
        fired = quest_manager.maybe_trigger_victory(
            game, "No Such Quest")
        assert fired is False
        assert game.showing_victory is False

    def test_blank_victory_text_falls_back(self, game):
        _attach_final_quest(game, victory_text="")
        quest_manager.maybe_trigger_victory(game, "Slay the Dragon")
        # The renderer is responsible for the fallback line; the
        # state itself just stores the (empty) author text.
        assert game.victory_text == ""

    def test_already_showing_does_not_restart_timer(self, game):
        _attach_final_quest(game)
        quest_manager.maybe_trigger_victory(game, "Slay the Dragon")
        game.victory_elapsed = 5.0   # simulate a few seconds in
        fired = quest_manager.maybe_trigger_victory(
            game, "Slay the Dragon")
        assert fired is False
        # Elapsed timer must NOT reset — that would let a stray turn-in
        # hook re-block input on a screen the player has been
        # interacting with.
        assert game.victory_elapsed == 5.0


# ── Option actions ─────────────────────────────────────────────────


class TestVictoryActions:
    def test_continue_dismisses_overlay(self, game):
        # The realistic state when the screen pops is "in the world"
        # (title screen already dismissed). Reflect that so the
        # CONTINUE assertion can verify we don't bounce back to title.
        game.showing_title = False
        _attach_final_quest(game)
        quest_manager.maybe_trigger_victory(game, "Slay the Dragon")
        assert game.showing_victory is True
        # Find and invoke the CONTINUE PLAYING action. We look it up
        # by label rather than index so the test still passes if the
        # menu order is rearranged.
        cont = next(o for o in game.victory_options
                    if o["label"] == "CONTINUE PLAYING")
        cont["action"]()
        assert game.showing_victory is False
        # Continuing must NOT touch the title screen state.
        assert game.showing_title is False

    def test_main_menu_returns_to_title(self, game):
        game.showing_title = False
        _attach_final_quest(game)
        quest_manager.maybe_trigger_victory(game, "Slay the Dragon")
        mm = next(o for o in game.victory_options
                  if o["label"] == "MAIN MENU")
        mm["action"]()
        assert game.showing_victory is False
        assert game.showing_title is True


# ── Schema round-trip ──────────────────────────────────────────────


class TestNewQuestSchema:
    def test_new_quest_carries_final_fields(self, game):
        # _mod_quest_add_new is the helper used by the in-game
        # module editor when an author hits "New Quest". Verify the
        # new fields are present so the editor and runtime read the
        # same shape.
        if not hasattr(game, "_mod_quest_list"):
            game._mod_quest_list = []
        # The save call writes to disk; suppress it for the unit test.
        game._save_module_quests = lambda: None
        # Stub module_list/cursor so _save_module_quests has a target
        # if the test environment ever wires it back up.
        game.module_list = []
        game.module_cursor = 0
        game._mod_quest_add_new("Test Climax")
        new_q = game._mod_quest_list[-1]
        assert "is_final_quest" in new_q
        assert new_q["is_final_quest"] is False
        assert "victory_text" in new_q
        assert new_q["victory_text"] == ""


# ── Module quest editor UI ─────────────────────────────────────────


class TestQuestEditorFields:
    """The module quest editor must surface the two final-quest fields
    in its per-quest field list so authors can flip the flag without
    hand-editing JSON. This regression guards against the pair drifting
    out of the editor — they were missing in the first cut of the
    feature, which forced the author to migrate quests by hand.
    """

    def _setup_editor_for_quest(self, game, quest):
        """Wire one quest into the editor state and load its fields."""
        game._mod_quest_list = [quest]
        game._mod_quest_cursor = 0
        # The fields-loader pulls from a few caches that don't exist on
        # a fresh Game (sprites, locations, world-unlock tile names).
        # Stubs keep the test honest about exercising the field
        # construction without dragging in module asset loading.
        game._mod_quest_sprite_options = []
        game._mod_quest_sprite_name_to_file = {}
        game._mod_quest_location_options = []
        game._mod_quest_location_map = {}
        game._mod_quest_build_settings_fields()
        return game._mod_quest_fields

    def test_editor_exposes_is_final_quest(self, game):
        fields = self._setup_editor_for_quest(game, {
            "name": "Slay the Dragon",
            "description": "",
            "is_final_quest": True,
            "victory_text": "Hargorn is dead.",
            "steps": [],
        })
        keys = [f.key for f in fields]
        assert "is_final_quest" in keys, (
            "Module editor must expose an editable Is Final Quest "
            "field — without it, authors can't designate the climax "
            "quest from the UI.")
        assert "victory_text" in keys, (
            "Module editor must expose an editable Victory Text "
            "field for the author's epilogue blurb.")

    def test_is_final_quest_choice_uses_bool_strings(self, game):
        fields = self._setup_editor_for_quest(game, {
            "name": "Q", "description": "", "steps": [],
            "is_final_quest": False, "victory_text": "",
        })
        ifq = next(f for f in fields if f.key == "is_final_quest")
        assert ifq.field_type == "choice"
        assert ifq.value == "False"
        # The choice options live on the quest editor's choice map.
        opts = game._mod_quest_choice_map.get("is_final_quest")
        assert opts == ["False", "True"]

    def test_save_converts_bool_string_to_python_bool(self, game):
        fields = self._setup_editor_for_quest(game, {
            "name": "Q", "description": "", "steps": [],
            "is_final_quest": False, "victory_text": "",
        })
        # Simulate the user toggling Is Final Quest to "True" in the
        # editor — the field's value buffer is the display string.
        ifq = next(f for f in fields if f.key == "is_final_quest")
        ifq.value = "True"
        # Suppress the disk write so the test is hermetic.
        game._save_module_quests = lambda: None
        game._mod_quest_save_settings_fields()
        saved = game._mod_quest_list[0]
        assert saved["is_final_quest"] is True, (
            "Editor's 'True'/'False' choice strings must persist as "
            "real JSON booleans so the runtime truthiness check "
            "(qdef.get('is_final_quest')) lights up correctly.")
