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


class TestTagPropagationFromMapMonster:
    """The dungeon and overworld bridges build *fresh* in-combat
    monsters from the encounter template — they don't carry over the
    ``_quest_name`` tag set by the quest spawner on the map monster.
    Without harvesting the tag from ``self.monster_refs`` (the map
    monsters that triggered the encounter), a localized dungeon kill
    quest like "Slay the Dragon" would never credit on victory:
    combat code never sees the tag because it lives on the map
    monster, not on the in-combat instance.

    This was the bug the player hit on the dragon quest after the
    earlier false-credit fix — the tag was being checked, but never
    reaching the credit path.
    """

    def test_tag_on_map_monster_credits_after_combat(self, combat):
        # combat fixture wires a single Giant Rat into combat. We
        # rebuild it minimally to mimic the dungeon-quest case: the
        # in-combat monster has NO tag, but the map_monster_ref does.
        ds = combat
        # Rename the in-combat creature so the test reads as the
        # dragon quest scenario without any data-file coupling.
        for m in ds.monsters:
            m.name = "Dragon"
            m.hp = 0
            # Explicitly leave _quest_name / _quest_step_idx unset.
            assert not hasattr(m, "_quest_name")
        # Give the map-side monster ref the quest tag — same shape
        # as ``_inject_quest_dungeon_monsters`` writes.
        for ref in ds.monster_refs:
            ref._quest_name = "Slay the Ancient Dragon"
            ref._quest_step_idx = 0
        ds.combat_location = "dungeon:Dragon's Lair - Floor 10"

        ds._trigger_victory()

        tags = ds.game.pending_killed_quest_tags
        keys = {(t["quest_name"], t["step_idx"]) for t in tags}
        assert ("Slay the Ancient Dragon", 0) in keys, (
            "Map-monster quest tag must be harvested into "
            "pending_killed_quest_tags so the localized-step credit "
            "path sees the kill.")

    def test_tag_only_on_combat_monster_still_works(self, combat):
        # Belt-and-suspenders: original tagging path (tag set directly
        # on the in-combat monster) must still work.
        ds = combat
        for m in ds.monsters:
            m.name = "Goblin"
            m.hp = 0
            m._quest_name = "Goblin Hunt"
            m._quest_step_idx = 0
        ds.combat_location = "dungeon:Goblin Camp"

        ds._trigger_victory()

        tags = ds.game.pending_killed_quest_tags
        keys = {(t["quest_name"], t["step_idx"]) for t in tags}
        assert ("Goblin Hunt", 0) in keys

    def test_duplicate_tags_deduplicated(self, combat):
        # Same tag on combat monster AND map monster ref shouldn't
        # produce two entries — the credit logic uses a set lookup
        # so a duplicate is harmless, but the harvested list staying
        # tidy makes the in-game log cleaner.
        ds = combat
        for m in ds.monsters:
            m.name = "Dragon"
            m.hp = 0
            m._quest_name = "Slay the Dragon"
            m._quest_step_idx = 0
        for ref in ds.monster_refs:
            ref._quest_name = "Slay the Dragon"
            ref._quest_step_idx = 0
        ds.combat_location = "dungeon:Dragon's Lair"

        ds._trigger_victory()

        tags = ds.game.pending_killed_quest_tags
        matching = [t for t in tags
                    if (t["quest_name"], t["step_idx"])
                    == ("Slay the Dragon", 0)]
        assert len(matching) == 1, (
            "Tag harvested from both lanes must be deduplicated.")


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
