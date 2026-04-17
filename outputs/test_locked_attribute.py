"""Smoke-test the universal 'locked' tile attribute end-to-end.

Exercises the LockInteractionMixin directly (no full Game needed) to
confirm:
  1. The Attributes panel exposes a Locked toggle.
  2. A tile marked tile_properties['locked']=True triggers the dialog.
  3. A successful pick-lock fires the unlock animation.
  4. After the animation completes, the 'locked' flag is removed and
     the tile reverts to its base walkability.
  5. The legacy TILE_LOCKED_DOOR still converts to TILE_DDOOR.
"""
import os
import random
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()

root = sys.argv[1]
sys.path.insert(0, root)
os.chdir(root)

# Deterministic d20 — force success on every pick by making every
# random.randint call return 20.
import src.states.lock_mixin as _lm
_lm.random = SimpleNamespace(randint=lambda a, b: 20)

# ── 1. Attributes panel shows Locked toggle ─────────────────────────
from src.map_editor import (
    MapEditorConfig, MapEditorState,
    STORAGE_SPARSE, GRID_FIXED,
)

cfg = MapEditorConfig(
    title="T", storage=STORAGE_SPARSE, grid_type=GRID_FIXED,
    width=10, height=10, tile_context="town", brushes=[],
)
state = MapEditorState(cfg, tiles={"5,5": {"tile_id": 29,
                                           "name": "Locked Door"}})
state.cursor_col = 5
state.cursor_row = 5
info = state.get_cursor_tile_info()
locked_field = next((f for f in info["fields"] if f[1] == "locked"), None)
assert locked_field is not None, (
    f"Locked row missing from Attributes; fields={info['fields']!r}")
print(f"Attributes panel exposes Locked row: {locked_field!r}")

# ── 2. Simulate toggling the Locked flag via tile_properties ────────
state.set_tile_prop(7, 7, "locked", True)
assert state.tile_properties.get("7,7", {}).get("locked") is True
print("set_tile_prop successfully set 'locked' on an arbitrary tile")

# ── 3. Exercise LockInteractionMixin on a fake state ────────────────
from src.states.lock_mixin import LockInteractionMixin
from src.tile_map import TileMap
from src.settings import TILE_LOCKED_DOOR, TILE_DDOOR, TILE_DFLOOR


class FakeState(LockInteractionMixin):
    """Bare-bones host state that just provides self.game and show_message."""
    def __init__(self, game):
        self.game = game
        self._init_lock_interaction()
        self.last_message = None

    def show_message(self, text, duration_ms=0):
        self.last_message = text


from src.party import Party, PartyMember
# Thief with DEX high enough to succeed on d20+mod >= 12
thief = PartyMember("Sly", "Thief", "Human")
thief.base_dexterity = 18  # +4 mod — guaranteed success on d20>=8
thief.hp = thief.max_hp
party = Party.__new__(Party)
party.members = [thief]
party.shared_inventory = ["Lockpick"]
party.shared_inventory_durability = {"Lockpick": 5}
party.gold = 0
party.col = 3
party.row = 3

game = SimpleNamespace(
    party=party,
    game_log=[],
    sfx=SimpleNamespace(play=lambda *_: None),
)

st = FakeState(game)
tmap = TileMap(10, 10)
# Paint a normally-walkable floor tile and mark it locked via
# tile_properties — simulating what the Attributes panel does.
tmap.set_tile(4, 4, TILE_DFLOOR)
tmap.tile_properties = {"4,4": {"locked": True}}

# ── 3a. Bumping the tile opens the dialog ────────────────────────────
opened = st._try_open_locked(tmap, 4, 4)
assert opened is True
assert st.door_interact_active is True
opts = [opt[1] for opt in st.door_interact_options]
print(f"Dialog options when bumping locked floor: {opts}")
assert "pick" in opts, f"Pick Lock should be available; got {opts}"

# ── 3b. Confirm Pick Lock → animation queued + locked flag still set
# (the flag is only cleared AFTER the animation completes).
pick_idx = next(i for i, (_, a) in enumerate(st.door_interact_options)
                 if a == "pick")
st.door_interact_cursor = pick_idx
# Fake Enter key
ev = SimpleNamespace(key=pygame.K_RETURN)
st._handle_lock_interact_input(ev)
assert st.door_interact_active is False
assert st.door_unlock_anim is not None, "unlock animation not queued"
assert tmap.tile_properties["4,4"].get("locked") is True
print(f"Pick Lock queued unlock animation: timer={st.door_unlock_anim['timer']}ms")

# ── 3c. Tick the animation to completion — flag should be removed ──
st._tick_lock_animation(2000)  # more than enough to expire the 1200ms timer
assert st.door_unlock_anim is None
assert tmap.tile_properties.get("4,4", {}).get("locked") is None, (
    "locked flag should be gone after unlock animation finishes")
# Base tile stays walkable — party can now step on (4,4).
assert tmap.is_walkable(4, 4) is True
print("Animation complete: 'locked' removed, tile now walkable")

# ── 4. Legacy TILE_LOCKED_DOOR: pick converts to TILE_DDOOR ──────────
# Refill lockpicks — the previous pick consumed the only one.
party.shared_inventory = ["Lockpick"]
tmap2 = TileMap(10, 10)
tmap2.set_tile(6, 6, TILE_LOCKED_DOOR)
st2 = FakeState(game)
assert st2._try_open_locked(tmap2, 6, 6) is True
st2.door_interact_cursor = next(
    i for i, (_, a) in enumerate(st2.door_interact_options) if a == "pick")
st2._handle_lock_interact_input(SimpleNamespace(key=pygame.K_RETURN))
st2._tick_lock_animation(2000)
assert tmap2.get_tile(6, 6) == TILE_DDOOR, (
    f"legacy locked door should become open door; got {tmap2.get_tile(6, 6)}")
print("Legacy TILE_LOCKED_DOOR correctly converts to TILE_DDOOR on pick")

# ── 5. Non-locked tile short-circuits ───────────────────────────────
st3 = FakeState(game)
tmap3 = TileMap(10, 10)
tmap3.set_tile(0, 0, TILE_DFLOOR)  # no locked flag
assert st3._try_open_locked(tmap3, 0, 0) is False
assert st3.door_interact_active is False
print("Non-locked tile correctly does not open the dialog")

print("\nAll locked-attribute checks passed.")
