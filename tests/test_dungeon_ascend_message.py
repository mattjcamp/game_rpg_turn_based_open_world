"""Tests for the player-facing copy when ascending one area in a
multi-level dungeon.

Forest "dungeons" are open-air woodland trails — there is no staircase,
no floors, and the verb "ascend" reads as stone-corridor language.
The descend handler already branches on ``dungeon_data.style ==
"forest"`` to swap in trail-themed copy ("The trail winds deeper into
the woods..."). The ascend handler now mirrors that branch so the
return trip stays in the same voice.
"""

from src.dungeon_generator import DungeonData
from src.tile_map import TileMap
from src.settings import (
    TILE_DFLOOR, TILE_GRASS,
    TILE_FOREST_ARCHWAY_DOWN, TILE_STAIRS_DOWN,
)


def _build_level(style, archway_tile, archway_pos=(1, 1),
                 default_tile=None, name="Test Level"):
    """Construct a tiny DungeonData with a single descent tile so
    ``_ascend_level`` has a placement target on the level above."""
    if default_tile is None:
        default_tile = TILE_GRASS if style == "forest" else TILE_DFLOOR
    tm = TileMap(5, 5, default_tile=default_tile)
    tm.set_tile(archway_pos[0], archway_pos[1], archway_tile)
    return DungeonData(
        tile_map=tm, rooms=[],
        entry_col=2, entry_row=2,
        name=name, style=style,
    )


def _setup_two_level_dungeon(game, *, top_style, bottom_style):
    """Wire a two-level quest dungeon into the existing dungeon state.

    The ascend handler walks back from the bottom level to the top, so
    only the *top* level's style controls the message we want to test.
    The bottom level can be whatever — we just need it to exist as the
    starting position.
    """
    top = _build_level(
        top_style,
        TILE_FOREST_ARCHWAY_DOWN if top_style == "forest"
        else TILE_STAIRS_DOWN,
        name="Top")
    bottom = _build_level(
        bottom_style,
        TILE_FOREST_ARCHWAY_DOWN if bottom_style == "forest"
        else TILE_STAIRS_DOWN,
        name="Bottom")
    ds = game.states["dungeon"]
    ds.quest_levels = [top, bottom]
    ds.current_level = 1
    ds.dungeon_data = bottom
    ds.torch_active = False
    ds.message = ""
    # _get_active_quest looks these up for the "current_level" write
    # in ``_ascend_level`` — leaving overworld_col/row at default 0/0
    # is fine because the test game has no quests at (0, 0).
    ds.overworld_col = 0
    ds.overworld_row = 0
    return ds


# ── The regression ─────────────────────────────────────────────────


def test_forest_ascend_message_is_trail_themed(game):
    """The bug report: a forest dungeon was telling the player they
    "ascend to the next level" — staircase language for an outdoor
    woodland trail. The new copy mirrors the descend handler's
    forest-themed wording."""
    ds = _setup_two_level_dungeon(
        game, top_style="forest", bottom_style="forest")
    ds._ascend_level()
    msg = ds.message
    assert "ascend" not in msg.lower(), (
        f"Forest ascend message must not say 'ascend': {msg!r}")
    assert "floor" not in msg.lower(), (
        f"Forest ascend message must not say 'floor': {msg!r}")
    # Sanity: the new copy mentions the trail and the area count.
    assert "trail" in msg.lower()
    assert "1/2" in msg, (
        f"Forest ascend message should still surface the area "
        f"counter: {msg!r}")


def test_stone_ascend_message_unchanged(game):
    """Stone-style dungeons keep the original 'You ascend to floor N'
    wording — only forest output is being re-themed."""
    ds = _setup_two_level_dungeon(
        game, top_style=None, bottom_style=None)
    ds._ascend_level()
    msg = ds.message
    assert "ascend" in msg.lower()
    assert "floor 1" in msg.lower(), (
        f"Stone ascend message should mention 'floor 1': {msg!r}")
