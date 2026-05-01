"""Tests for quest-kill credit logic in ``quest_manager.check_quest_kills``.

Regression coverage for a player-reported bug: a 10-floor dungeon kill
quest whose target was a Dragon on the deepest floor was completing on
the first floor when a *random* (non-quest-tagged) Dragon appeared in
a regular encounter. The fix requires localized kill steps (steps
pinned to a dungeon, town, building, interior, or space) to credit
only kills of the quest-spawned, tagged monster — not any monster
that happens to share the encounter roster's name.

Overview/overworld kill steps keep the legacy roster-name behaviour so
older quests like "kill 5 goblins anywhere" still credit random
encounters.
"""

import types

import pytest

from src import quest_manager


# ── Helpers ────────────────────────────────────────────────────────


class _Sfx:
    """Stub so ``check_quest_kills`` can call ``game.sfx.play(...)``
    without touching pygame.mixer."""

    def __init__(self):
        self.calls = []

    def play(self, name):
        self.calls.append(name)


def _make_game(quest_defs, quest_states,
               killed_names, killed_quest_tags=None,
               combat_location=""):
    """Build a SimpleNamespace mimicking the few attributes
    ``check_quest_kills`` reads. Keeps tests free of the real Game
    object's heavy initialisation."""
    return types.SimpleNamespace(
        _module_quest_defs=quest_defs,
        module_quest_states=quest_states,
        pending_killed_monsters=list(killed_names),
        pending_killed_quest_tags=list(killed_quest_tags or []),
        pending_combat_location=combat_location,
        sfx=_Sfx(),
        pending_quest_callouts=[],
    )


@pytest.fixture
def patch_dragon_encounter(monkeypatch):
    """Make ``find_encounter_template("Lone Dragon")`` resolve to a
    template whose roster contains a Dragon."""

    def fake_find(name):
        if name == "Lone Dragon":
            return {"name": "Lone Dragon", "monsters": ["Dragon"]}
        if name == "Goblin Pack":
            return {"name": "Goblin Pack",
                    "monsters": ["Goblin", "Goblin"]}
        return None

    monkeypatch.setattr(
        "src.monster.find_encounter_template", fake_find)


# ── Localized (dungeon) kill step ──────────────────────────────────


class TestDungeonKillCredit:
    """A kill step pinned to a dungeon must only count quest-tagged
    kills. Random encounters that happen to share the roster's name
    no longer credit the quest."""

    def _quest(self):
        return [{
            "name": "Slay the Ancient Dragon",
            "steps": [{
                "step_type": "kill",
                "encounter": "Lone Dragon",
                "spawn_location": "dungeon:Dragon's Lair",
                "target_count": 1,
                "description": "Defeat the Ancient Dragon",
            }],
        }]

    def _state(self):
        return {"Slay the Ancient Dragon": {
            "status": "active",
            "step_progress": [False],
        }}

    def test_random_dragon_does_not_credit(
            self, patch_dragon_encounter):
        """The bug: killing a random Dragon (no quest tag) on floor 1
        of a multi-floor dungeon used to mark the kill quest complete.
        After the fix, an untagged Dragon kill is ignored — the quest
        only finishes when the actual tagged spawn dies."""
        game = _make_game(
            self._quest(), self._state(),
            killed_names=["Dragon"],
            killed_quest_tags=[],  # untagged random encounter
            combat_location="dungeon:Dragon's Lair - Floor 1",
        )
        result = quest_manager.check_quest_kills(game)
        assert result is None, (
            "Untagged Dragon kill should not produce a credit "
            "message in a localized dungeon step.")
        progress = game.module_quest_states[
            "Slay the Ancient Dragon"]["step_progress"]
        assert progress == [False], (
            "Random encounter Dragon must NOT advance the quest.")

    def test_tagged_dragon_credits_and_completes(
            self, patch_dragon_encounter):
        """The intended path: the player descends to floor 10, fights
        the glowing quest-tagged Dragon, and the kill credits."""
        game = _make_game(
            self._quest(), self._state(),
            killed_names=["Dragon"],
            killed_quest_tags=[{
                "quest_name": "Slay the Ancient Dragon",
                "step_idx": 0,
                "monster_name": "Dragon",
            }],
            combat_location="dungeon:Dragon's Lair - Floor 10",
        )
        result = quest_manager.check_quest_kills(game)
        assert result is not None, (
            "Tagged Dragon kill should produce a credit message.")
        progress = game.module_quest_states[
            "Slay the Ancient Dragon"]["step_progress"]
        assert progress == [True]
        assert game.module_quest_states[
            "Slay the Ancient Dragon"]["status"] == "completed"

    def test_tag_for_different_quest_does_not_credit(
            self, patch_dragon_encounter):
        """A monster tagged for a *different* quest's step shouldn't
        cross-credit our quest, even if the names line up."""
        game = _make_game(
            self._quest(), self._state(),
            killed_names=["Dragon"],
            killed_quest_tags=[{
                "quest_name": "Some Other Quest",
                "step_idx": 0,
                "monster_name": "Dragon",
            }],
            combat_location="dungeon:Dragon's Lair - Floor 10",
        )
        result = quest_manager.check_quest_kills(game)
        assert result is None
        progress = game.module_quest_states[
            "Slay the Ancient Dragon"]["step_progress"]
        assert progress == [False]


# ── Overworld kill step (back-compat) ──────────────────────────────


class TestOverworldKillCreditUntagged:
    """Overview/overworld kill steps keep the legacy roster-name
    behaviour: a random goblin counts toward "kill 5 goblins" without
    needing a quest tag. Otherwise older modules would silently break
    on update."""

    def test_random_goblin_credits_overworld_step(
            self, patch_dragon_encounter):
        quest_defs = [{
            "name": "Goblin Hunt",
            "steps": [{
                "step_type": "kill",
                "encounter": "Goblin Pack",
                "spawn_location": "overview",
                "target_count": 1,
                "description": "Hunt a goblin pack",
            }],
        }]
        quest_states = {"Goblin Hunt": {
            "status": "active",
            "step_progress": [False],
        }}
        game = _make_game(
            quest_defs, quest_states,
            killed_names=["Goblin"],
            killed_quest_tags=[],  # random encounter
            combat_location="overview",
        )
        result = quest_manager.check_quest_kills(game)
        assert result is not None, (
            "Random goblin kill should still credit an overworld "
            "kill step (legacy behaviour preserved).")
        assert game.module_quest_states[
            "Goblin Hunt"]["step_progress"] == [True]
