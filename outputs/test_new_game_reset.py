"""Verify leftover interior/darkness state gets wiped on new game."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()

root = sys.argv[1]
sys.path.insert(0, root)
os.chdir(root)

# Construct the state classes directly without a full Game, so we can
# poke their fields and then invoke reset_for_new_game() in isolation.
from src.states.overworld import OverworldState
from src.states.town import TownState
from src.states.dungeon import DungeonState

class _GameStub:
    """Minimal stub so BaseState subclasses can __init__ without Game."""
    def __init__(self):
        self.party = None
        self.states = {}
        self.game_log = []
        self.sfx = type("_Sfx", (), {"play": staticmethod(lambda *_: None)})()


stub = _GameStub()

# ── Overworld: set up "dirty" interior state (the real bug) ──
ow = OverworldState(stub)
ow._in_overworld_interior = True
ow._overworld_interior_stack = [{"snapshot": 1}]
ow._overworld_interior_exit_positions = {(3, 4)}
ow._overworld_interior_links = {(5, 6): "Inner Room"}
ow._overworld_interior_name = "Shop"
ow._overworld_interior_entry_grace = True
ow._stashed_overworld_tile_map = "<fake tile map>"
ow._stashed_overworld_monsters = ["orc"]
ow._stashed_overworld_party_col = 10
ow._stashed_overworld_party_row = 10
ow._building_interior_npcs = ["npc1"]
ow._building_combat_npc = "orc"
ow._building_returning_from_combat = True
ow._building_name = "Abandoned House"
ow._exit_grace = True
ow.ow_npc_dialogue_active = True
ow.message = "stale message"
ow.message_timer = 5000

print("Before reset:")
print(f"  _in_overworld_interior = {ow._in_overworld_interior}")
print(f"  interior stack size = {len(ow._overworld_interior_stack)}")
print(f"  building NPCs = {ow._building_interior_npcs}")
print(f"  dialogue active = {ow.ow_npc_dialogue_active}")

ow.reset_for_new_game()

print("\nAfter reset:")
print(f"  _in_overworld_interior = {ow._in_overworld_interior}")
print(f"  interior stack size = {len(ow._overworld_interior_stack)}")
print(f"  building NPCs = {ow._building_interior_npcs}")
print(f"  dialogue active = {ow.ow_npc_dialogue_active}")

assert ow._in_overworld_interior is False, (
    "Interior flag (root cause of dark overworld) NOT reset")
assert ow._overworld_interior_stack == []
assert ow._overworld_interior_exit_positions == set()
assert ow._overworld_interior_links == {}
assert ow._overworld_interior_name == ""
assert ow._overworld_interior_entry_grace is False
assert ow._stashed_overworld_tile_map is None
assert ow._stashed_overworld_monsters is None
assert not hasattr(ow, "_stashed_overworld_party_col")
assert not hasattr(ow, "_stashed_overworld_party_row")
assert ow._building_interior_npcs == []
assert ow._building_combat_npc is None
assert ow._building_returning_from_combat is False
assert ow._building_name == ""
assert ow._exit_grace is False
assert ow.ow_npc_dialogue_active is False
assert ow.message == ""
assert ow.message_timer == 0
print("Overworld state fully clean — dark-interior flag cleared")

# ── Town: overlay state (shops, temple, healing counter) ──
tn = TownState(stub)
tn.showing_shop = True
tn.shop_cursor = 3
tn.shop_message = "leftover"
tn.showing_temple_service = True
tn.temple_npc = "priest"
tn.showing_healing_counter = True
tn.healing_counter_data = {"name": "Healer"}
tn.pickpocket_targeting = True
tn._in_interior = True
tn._interior_stack = [{"snap": 1}]
tn.npc_dialogue_active = True
tn.message = "stale"

tn.reset_for_new_game()

assert tn.showing_shop is False
assert tn.shop_cursor == 0
assert tn.shop_message == ""
assert tn.showing_temple_service is False
assert tn.temple_npc is None
assert tn.showing_healing_counter is False
assert tn.healing_counter_data is None
assert tn.pickpocket_targeting is False
assert tn._in_interior is False
assert tn._interior_stack == []
assert tn.npc_dialogue_active is False
assert tn.message == ""
print("Town state fully clean — shop/temple/healing/pickpocket overlays cleared")

# ── Dungeon: torch timer + door overlays + encounter action ──
dg = DungeonState(stub)
dg.torch_active = True
dg.torch_steps = 50
dg.overworld_col = 10
dg.overworld_row = 12
dg.door_interact_active = True
dg.door_interact_options = [("Unlock", "unlock")]
dg.encounter_action_active = True
dg.encounter_action_monster = "Dragon"
dg.pending_combat_message = "Previous victory!"
dg._entered = True
dg.artifact_pickup_anim = {"col": 5, "row": 5, "timer": 2, "name": "Crystal"}

dg.reset_for_new_game()

assert dg.torch_active is False
assert dg.torch_steps == 0
assert dg.overworld_col == 0 and dg.overworld_row == 0
assert dg.door_interact_active is False
assert dg.door_interact_options == []
assert dg.encounter_action_active is False
assert dg.encounter_action_monster is None
assert dg.pending_combat_message is None
assert dg._entered is False
assert dg.artifact_pickup_anim is None
print("Dungeon state fully clean — torch timer + door/encounter overlays cleared")

print("\nAll new-game state-reset checks passed.")
