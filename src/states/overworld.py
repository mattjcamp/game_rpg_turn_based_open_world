"""
Overworld state - the main exploration mode.

This is where the party walks around the overworld map, encounters
towns, dungeons, and random encounters. It's the "hub" state of
the game.
"""

import random

import pygame

from src.states.base_state import BaseState
from src.states.inventory_mixin import InventoryMixin
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_TOWN, TILE_DUNGEON, TILE_CHEST, TILE_GRASS,
    TILE_WATER, TILE_MACHINE, TILE_DUNGEON_CLEARED,
    GUARDIAN_LEASH, GUARDIAN_INTERCEPT_RANGE_OVERWORLD, GUARDIAN_INTERCEPT_RANGE_INTERIOR,
    NPC_WANDER_RANGE, ORC_RESPAWN_CHANCE,
)
from src.dungeon_generator import generate_dungeon, generate_house_dungeon
from src.monster import create_encounter, create_monster


# How many monsters roam the overworld at a time
_MAX_OVERWORLD_ORCS = 2
# Minimum Chebyshev distance from party when spawning
_SPAWN_MIN_DIST = 8
_SPAWN_MAX_DIST = 14


class OverworldState(InventoryMixin, BaseState):
    """Handles overworld exploration."""

    def __init__(self, game):
        super().__init__(game)
        self.message = ""
        self.message_timer = 0  # ms remaining to show message
        self.move_cooldown = 0  # ms until next move allowed
        self._init_inventory_state()

        # Help overlay
        self.showing_help = False

        # Unique tile discovery display
        self.unique_tile_text = ""
        self.unique_tile_timer = 0       # ms remaining to show text
        self.unique_tile_flash = 0.0     # animation phase (radians)
        self.unique_tile_pos = None      # (col, row) for map flash effect

        # Roaming overworld orcs
        self.overworld_monsters = []

        # Track original tiles under placed chests: {(col, row): tile_id}
        self.chest_under_tiles = {}

        # Message queued by combat state on return
        self.pending_combat_message = None

        # Push spell expanding-wave animation
        # dict with keys: timer, duration, max_radius
        self.push_spell_anim = None

        # Lingering repel effect: monsters flee for N movement steps
        # dict with keys: steps_remaining, radius
        self.repel_effect = None

        # Dungeon entry action screen
        self.dungeon_action_active = False
        self.dungeon_action_cursor = 0        # 0=Enter, 1=Leave
        self.dungeon_action_info = {}         # {name, description, visited, quest_name}
        self.dungeon_action_entry_args = None # pre-computed entry params

        # Town/location entry action screen
        self.town_action_active = False
        self.town_action_cursor = 0           # 0=Enter, 1=Leave
        self.town_action_info = {}            # {name, description}

        # Building entry action screen
        self.building_action_active = False
        self.building_action_cursor = 0       # 0=Enter, 1=Leave
        self.building_action_info = {}        # {name, description}
        self.building_action_entry_args = None

        # Grace flag: skip one tile-event check after returning from a
        # town/dungeon so the player isn't immediately prompted to re-enter
        # the location they just left.
        self._exit_grace = False

        # ── Overworld interior state ──
        self._in_overworld_interior = False
        self._overworld_interior_stack = []
        self._overworld_interior_exit_positions = set()
        self._overworld_interior_links = {}  # {(col,row): interior_name}
        self._overworld_interior_name = ""
        self._overworld_interior_entry_grace = False
        # Stashed overworld state restored on exit
        self._stashed_overworld_tile_map = None
        self._stashed_overworld_monsters = None
        # NPCs spawned inside building interiors (quest items + guardians)
        self._building_interior_npcs = []
        self._building_combat_npc = None
        self._building_returning_from_combat = False
        self._building_name = ""  # the building name (not space name)

        # ── Overworld NPC dialogue (module quest givers) ──
        self.ow_npc_dialogue_active = False
        self.ow_npc_speaking = None
        self.ow_quest_dialogue_lines = []
        self.ow_quest_dialogue_index = 0
        self.ow_quest_choice_active = False
        self.ow_quest_choice_cursor = 0
        self.ow_quest_choices = []

        # ── Quest visual effects ──
        # List of active effects: {type, timer, duration, ...}
        self.quest_effects = []

    def enter(self):
        self._apply_pending_combat_rewards()
        # Check quest kill progress (sets message if a step completed)
        quest_msg = self._check_quest_monster_kills()
        # Clean up building interior quest monster after combat
        if self._building_returning_from_combat and self._building_combat_npc:
            combat_state = self.game.states.get("combat")
            player_won = getattr(combat_state, "player_won", True)
            if player_won:
                npc = self._building_combat_npc
                if npc in self._building_interior_npcs:
                    self._building_interior_npcs.remove(npc)
            self._building_combat_npc = None
            self._building_returning_from_combat = False
        # Skip the first tile-event check so we don't immediately re-enter
        # the town/dungeon we just left.
        self._exit_grace = True
        if quest_msg:
            self.show_message(quest_msg, 4000)
        elif self.pending_combat_message:
            self.show_message(self.pending_combat_message, 2500)
            self.pending_combat_message = None
        elif not self.overworld_monsters and not self._in_overworld_interior:
            self.message = "Welcome, adventurers! Use arrow keys to explore."
            self.message_timer = 3000
            # Spawn initial orcs
            self._spawn_orcs()

    def _interact_machine(self):
        """Handle stepping on the gnome machine tile (Keys of Shadow)."""
        kd = self.game.get_key_dungeons()
        if not kd:
            self.show_message("A strange machine hums ominously.", 2000)
            return

        # Count keys the party currently holds
        party = self.game.party
        key_names = [d["key_name"] for d in kd.values()]
        held_keys = [k for k in key_names if party.inv_count(k) > 0]

        total = self.game.get_total_keys()
        inserted = self.game.get_keys_inserted()

        if held_keys:
            # Insert all held keys
            for key in held_keys:
                party.inv_remove(key)
                inserted = self.game.insert_key()
            n = len(held_keys)
            names = ", ".join(held_keys)
            self.show_message(
                f"Inserted {names}! ({inserted}/{total} keys placed)", 3500)

            # Check victory
            if inserted >= total:
                self._trigger_victory()
        elif inserted >= total:
            self.show_message(
                "The machine is deactivated. Sunlight bathes the land!", 3000)
        elif inserted > 0:
            remaining = total - inserted
            self.show_message(
                f"The machine hums... {inserted}/{total} keys inserted. "
                f"{remaining} more needed.", 3000)
        else:
            self.show_message(
                "A massive gnomish machine blocks the sun! "
                "It has 8 empty keyhole slots.", 3500)

    def _trigger_victory(self):
        """Called when all keys are inserted — quest complete!"""
        self.game.set_darkness(False)
        # Award XP and gold to all alive party members
        for m in self.game.party.alive_members():
            if m.is_alive():
                m.exp += 500
                msgs = m.check_level_up()
                for msg in msgs:
                    self.game.game_log.append(msg)
        self.game.party.gold += 1000
        town_name = getattr(self.game, "town_data", None)
        town_name = town_name.name if town_name else "the realm"
        self.game.game_log.append("*** Quest complete! ***")
        self.game.game_log.append("Peace returns to the land!")
        self.game.game_log.append(f"The people of {town_name} are saved!")
        self.game.game_log.append("Victory! +500 XP, +1000 Gold")
        self.show_message(
            "Quest complete! Peace returns! Victory!", 6000)

    # ── Equipment management ─────────────────────────────────────

    # ── Orc spawning ──────────────────────────────────────────────

    def _spawn_orcs(self):
        """Top-up roaming orcs to _MAX_OVERWORLD_ORCS.

        Monsters are only spawned on walkable land tiles.  Water,
        mountains, and any other non-walkable tiles are excluded.

        Also prunes any existing monster that has somehow ended up on a
        non-walkable tile (safety net for movement edge-cases, map edits,
        or legacy state).
        """
        tile_map = self.game.tile_map
        party = self.game.party

        # Keep only alive monsters standing on walkable tiles.
        # Removes any monster that ended up on water, mountains, or
        # any other non-walkable tile (e.g. after map edits or bugs).
        valid = []
        for m in self.overworld_monsters:
            if not m.is_alive():
                continue
            if not tile_map.is_walkable(m.col, m.row):
                continue  # monster on non-walkable tile — remove it
            valid.append(m)
        self.overworld_monsters = valid

        needed = _MAX_OVERWORLD_ORCS - len(valid)

        for _ in range(needed):
            placed = False
            for _attempt in range(60):
                c = party.col + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
                r = party.row + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
                dist = max(abs(c - party.col), abs(r - party.row))
                if dist < _SPAWN_MIN_DIST:
                    continue
                if not (0 <= c < tile_map.width and 0 <= r < tile_map.height):
                    continue

                # Only spawn on walkable land tiles — skip water,
                # mountains, and any other non-walkable tile.
                if not tile_map.is_walkable(c, r):
                    continue
                tile_id = tile_map.get_tile(c, r)
                if tile_id == TILE_WATER:
                    continue  # water is non-walkable but guard anyway
                terrain = "land"

                # Pick an encounter matching this terrain
                enc = create_encounter("overworld", terrain=terrain)
                if enc is None:
                    # No encounters defined for this terrain — skip
                    continue

                orc = create_monster(enc["monster_party_tile"])
                orc.encounter_template = {
                    "name": enc["name"],
                    "monster_names": [m.name for m in enc["monsters"]],
                    "monster_party_tile": enc["monster_party_tile"],
                }
                orc.col = c
                orc.row = r
                placed = True
                break
            if placed:
                self.overworld_monsters.append(orc)

    # ── Input ─────────────────────────────────────────────────────

    def handle_input(self, events, keys_pressed):
        """Handle arrow key movement with repeat delay."""
        for event in events:
            if event.type == pygame.KEYDOWN:
                # ── Help overlay input ──
                if self.showing_help:
                    if event.key in (pygame.K_h, pygame.K_ESCAPE):
                        self.showing_help = False
                    return

                # ── Log overlay input ──
                if self.showing_log:
                    if event.key == pygame.K_l or event.key == pygame.K_ESCAPE:
                        self.showing_log = False
                    elif event.key == pygame.K_UP:
                        self.log_scroll += 3
                    elif event.key == pygame.K_DOWN:
                        self.log_scroll = max(0, self.log_scroll - 3)
                    return

                # ── Town action screen input ──
                if self.town_action_active:
                    self._handle_town_action_input(event)
                    return

                # ── Dungeon action screen input ──
                if self.dungeon_action_active:
                    self._handle_dungeon_action_input(event)
                    return

                # ── Building action screen input ──
                if self.building_action_active:
                    self._handle_building_action_input(event)
                    return

                # ── Overworld NPC dialogue input ──
                if self.ow_npc_dialogue_active:
                    self._handle_ow_npc_dialogue_input(event)
                    return

                # ── Party inventory screen input ──
                if self.showing_party_inv:
                    self._handle_party_inv_input(event)
                    return

                # ── Action menu input ──
                if self.char_action_menu and self.showing_char_detail is not None:
                    self._handle_char_action_input(event)
                    return

                if event.key == pygame.K_ESCAPE:
                    if self.showing_char_detail is not None:
                        origin = self.char_sheet_origin
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = None
                        if origin == "inventory":
                            self.showing_party_inv = True
                        elif origin == "party":
                            self.showing_party = True
                        return
                    if self.showing_party:
                        self.showing_party = False
                        return
                    # Return to title screen (where the player can save)
                    self.game.showing_title = True
                    self.game.title_cursor = 0
                    return
                if event.key == pygame.K_p:
                    if self.showing_char_detail is not None:
                        origin = self.char_sheet_origin
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = None
                        if origin == "inventory":
                            self.showing_party_inv = True
                        elif origin == "party":
                            self.showing_party = True
                        return
                    if self.showing_party_inv:
                        self.showing_party_inv = False
                        return
                    if self.showing_party:
                        self.showing_party = False
                        return
                    self.showing_party_inv = True
                    self.party_inv_cursor = 0
                    self.party_inv_choosing = False
                    self.party_inv_member = 0
                    return
                if event.key == pygame.K_l:
                    self.showing_log = True
                    self.log_scroll = 0
                    return
                if event.key == pygame.K_h:
                    self.showing_help = True
                    return
                if event.key == pygame.K_e:
                    self.game.change_state("examine")
                    return
                # Character sheet cursor navigation
                if self.showing_char_detail is not None:
                    member = self.game.party.members[self.showing_char_detail]
                    total_rows = 4 + len(member.inventory)
                    if event.key == pygame.K_UP:
                        self.char_sheet_cursor = (self.char_sheet_cursor - 1) % total_rows
                        return
                    elif event.key == pygame.K_DOWN:
                        self.char_sheet_cursor = (self.char_sheet_cursor + 1) % total_rows
                        return
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._handle_equip_action(member)
                        return
                # 1-4 keys for char detail, 5 for party inventory
                if self.showing_party and self.showing_char_detail is None:
                    num = None
                    if event.key == pygame.K_1:
                        num = 0
                    elif event.key == pygame.K_2:
                        num = 1
                    elif event.key == pygame.K_3:
                        num = 2
                    elif event.key == pygame.K_4:
                        num = 3
                    if num is not None and num < len(self.game.party.members):
                        self.showing_char_detail = num
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = "party"
                        return
                    if event.key == pygame.K_5:
                        self.showing_party_inv = True
                        self.party_inv_cursor = 0
                        self.party_inv_choosing = False
                        self.party_inv_member = 0
                        return

        # If showing party, character detail, party inventory, NPC dialogue,
        # or an action screen, block all other input (including movement).
        if (self.showing_party or self.showing_char_detail is not None
                or self.showing_party_inv or self.ow_npc_dialogue_active
                or self.town_action_active or self.dungeon_action_active
                or self.building_action_active):
            return

        # Movement only if cooldown has elapsed
        if self.move_cooldown > 0:
            return

        dcol, drow = 0, 0
        if keys_pressed[pygame.K_LEFT] or keys_pressed[pygame.K_a]:
            dcol = -1
        elif keys_pressed[pygame.K_RIGHT] or keys_pressed[pygame.K_d]:
            dcol = 1
        elif keys_pressed[pygame.K_UP] or keys_pressed[pygame.K_w]:
            drow = -1
        elif keys_pressed[pygame.K_DOWN] or (
                keys_pressed[pygame.K_s]
                and not ((pygame.key.get_mods()
                          & ~(pygame.KMOD_CAPS | pygame.KMOD_NUM))
                         & (pygame.KMOD_CTRL | pygame.KMOD_META
                            | getattr(pygame, "KMOD_GUI", 0)))):
            drow = 1

        if dcol != 0 or drow != 0:
            party = self.game.party
            target_col = party.col + dcol
            target_row = party.row + drow

            # Bump-to-interact: building interior NPCs
            if self._in_overworld_interior and self._building_interior_npcs:
                for bnpc in self._building_interior_npcs:
                    if bnpc.col == target_col and bnpc.row == target_row:
                        if bnpc.npc_type == "quest_monster":
                            self._start_building_quest_combat(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return
                        elif bnpc.npc_type == "quest_item":
                            self._collect_building_quest_item(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return
                        elif bnpc.npc_type == "module_quest_giver":
                            self._start_ow_npc_dialogue(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return
                        else:
                            # Regular NPC types (villager, shopkeep, etc.)
                            self._start_building_npc_dialogue(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return

            # Bump-to-talk: check if a quest NPC is on the target tile
            ow_npc = self._get_ow_npc_at(target_col, target_row)
            if ow_npc:
                if getattr(ow_npc, "npc_type", "") == "quest_item":
                    self._collect_overworld_quest_item(ow_npc)
                else:
                    self._start_ow_npc_dialogue(ow_npc)
                self.move_cooldown = MOVE_REPEAT_DELAY
                return

            # Bump-to-fight: check if an orc is on the target tile
            orc = self._get_monster_at(target_col, target_row)
            if orc:
                self._start_orc_combat(orc)
                self.move_cooldown = MOVE_REPEAT_DELAY
                return

            moved = party.try_move(dcol, drow, self.game.tile_map)

            if moved:
                self.move_cooldown = MOVE_REPEAT_DELAY
                party.clock.advance(5)
                self.game.tile_map.tick_cooldowns()
                self._check_tile_events()
                # Move orcs after party moves (not inside interiors)
                if not self._in_overworld_interior:
                    self._move_monsters()
                    self._move_overworld_npcs()
                    self._check_monster_contact()
                    # Occasionally respawn orcs that were killed
                    if random.random() < ORC_RESPAWN_CHANCE:
                        self._spawn_orcs()
                else:
                    # Move building interior guardian NPCs
                    if self._building_interior_npcs:
                        self._move_building_interior_npcs()
                        self._check_building_interior_npc()
                # Tick Galadriel's Light step counter
                self._tick_galadriels_light()
            else:
                self.move_cooldown = MOVE_REPEAT_DELAY
                self.show_message("Blocked!", 800)

    # ── Galadriel's Light step tracking ─────────────────────────

    def _tick_galadriels_light(self):
        """Decrement Galadriel's Light step counter and auto-remove when expired."""
        party = self.game.party
        if not party.has_effect("Galadriel's Light"):
            return
        if party.galadriels_light_steps <= 0:
            return
        party.galadriels_light_steps -= 1
        if party.galadriels_light_steps <= 0:
            for slot_key in party.EFFECT_SLOTS:
                if party.get_effect(slot_key) == "Galadriel's Light":
                    party.set_effect(slot_key, None)
                    break
            self.show_message("Galadriel's Light fades away...", 3000)

    # ── Overworld NPC helpers (module quest givers) ──────────────

    def _get_ow_npc_at(self, col, row):
        """Return the overworld quest NPC at (col, row), or None."""
        for npc in getattr(self.game, "overworld_quest_npcs", []):
            if npc.col == col and npc.row == row:
                return npc
        return None

    def _collect_overworld_quest_item(self, npc):
        """Pick up a quest collectible item on the overworld."""
        from src.quest_manager import collect_quest_item
        ow_npcs = getattr(self.game, "overworld_quest_npcs", [])
        if npc in ow_npcs:
            ow_npcs.remove(npc)
        msg = collect_quest_item(
            self.game,
            getattr(npc, "_quest_name", ""),
            getattr(npc, "_quest_step_idx", -1),
            npc.name)
        self.show_message(msg, 3000 if "complete" in msg.lower() else 2500)

    def _start_ow_npc_dialogue(self, npc):
        """Begin talking to an overworld quest NPC."""
        mqname = getattr(npc, "_module_quest_name", "")
        mq_states = getattr(self.game, "module_quest_states", {})
        mq_state = mq_states.get(mqname, {})
        status = mq_state.get("status", "available")

        self.ow_npc_dialogue_active = True
        self.ow_npc_speaking = npc

        if status == "available":
            # Offer the quest
            self.ow_quest_dialogue_lines = list(
                npc.quest_dialogue or [])
            self.ow_quest_dialogue_index = 0
            if self.ow_quest_dialogue_lines:
                remaining = len(self.ow_quest_dialogue_lines) - 1
                hint = "  [ENTER] >" if remaining > 0 else "  [ENTER]"
                self.show_message(
                    f"{npc.name}: "
                    f"{self.ow_quest_dialogue_lines[0]}{hint}",
                    999999)
            else:
                self.show_message(
                    f"{npc.name}: I have a quest for you!  [ENTER]",
                    999999)
        elif status == "active":
            progress = mq_state.get("step_progress", [])
            done = sum(1 for p in progress if p)
            total = len(progress)
            self.show_message(
                f"{npc.name}: How's the quest going? "
                f"({done}/{total} steps done)  [ENTER]", 999999)
            self.ow_quest_dialogue_lines = []
        elif status == "completed":
            # Turn in quest — award rewards and play celebration
            quest_defs = getattr(self.game, "_module_quest_defs", [])
            qdef = None
            for q in quest_defs:
                if q.get("name") == mqname:
                    qdef = q
                    break
            reward_xp = qdef.get("reward_xp", 0) if qdef else 0
            reward_gold = qdef.get("reward_gold", 0) if qdef else 0

            # Grant rewards
            if reward_xp:
                for m in self.game.party.members:
                    if m.is_alive():
                        m.exp += reward_xp
                        m.check_level_up()
            if reward_gold:
                self.game.party.gold += reward_gold

            # Build reward text for dialogue
            parts = []
            if reward_xp:
                parts.append(f"+{reward_xp} XP")
            if reward_gold:
                parts.append(f"+{reward_gold} Gold")
            reward_str = ", ".join(parts)
            if reward_str:
                self.show_message(
                    f"{npc.name}: Thank you, hero! "
                    f"Here is your reward: {reward_str}  [ENTER]",
                    999999)
            else:
                self.show_message(
                    f"{npc.name}: Thank you for completing the quest!"
                    f"  [ENTER]", 999999)

            # Quest complete visual effect
            self.quest_effects.append({
                "type": "quest_complete",
                "timer": 3000,
                "duration": 3000,
                "quest_name": mqname,
                "reward_xp": reward_xp,
                "reward_gold": reward_gold,
            })
            self.game.sfx.play("quest_complete")

            # Mark as turned in so rewards aren't given again
            mq_state["status"] = "turned_in"
            self.ow_quest_dialogue_lines = []

        elif status == "turned_in":
            self.show_message(
                f"{npc.name}: Thank you again, hero! "
                f"Your deeds will be remembered.  [ENTER]", 999999)
            self.ow_quest_dialogue_lines = []

    def _handle_ow_npc_dialogue_input(self, event):
        """Handle input while overworld NPC dialogue is active."""
        import pygame

        # Quest choice screen (accept / decline)
        if self.ow_quest_choice_active:
            if event.key in (pygame.K_UP, pygame.K_LEFT):
                self.ow_quest_choice_cursor = 0
            elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                self.ow_quest_choice_cursor = 1
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._handle_ow_quest_choice()
            elif event.key == pygame.K_ESCAPE:
                # Decline on escape
                self.ow_quest_choice_cursor = 1
                self._handle_ow_quest_choice()
            return

        # Advancing dialogue lines — accept ANY key press
        if self.ow_quest_dialogue_lines:
            self.ow_quest_dialogue_index += 1
            if (self.ow_quest_dialogue_index
                    < len(self.ow_quest_dialogue_lines)):
                npc = self.ow_npc_speaking
                line = self.ow_quest_dialogue_lines[
                    self.ow_quest_dialogue_index]
                remaining = (len(self.ow_quest_dialogue_lines)
                             - self.ow_quest_dialogue_index - 1)
                hint = "  [ENTER] >" if remaining > 0 else "  [ENTER]"
                self.show_message(
                    f"{npc.name}: {line}{hint}", 999999)
                return
            else:
                # All dialogue shown — present choices if available
                npc = self.ow_npc_speaking
                if npc and npc.quest_choices:
                    self.ow_quest_choice_active = True
                    self.ow_quest_choices = list(npc.quest_choices)
                    self.ow_quest_choice_cursor = 0
                    return
        # No more lines / no choices — dismiss
        self._dismiss_ow_npc_dialogue()

    def _handle_ow_quest_choice(self):
        """Handle accept/decline on overworld quest offer."""
        npc = self.ow_npc_speaking
        if self.ow_quest_choice_cursor == 0:
            # Accept
            mqname = getattr(npc, "_module_quest_name", "")
            mq_states = getattr(self.game, "module_quest_states", {})
            if mqname in mq_states:
                mq_states[mqname]["status"] = "active"
            # Spawn quest monsters for any 'kill' steps
            if hasattr(self.game, "_spawn_quest_monsters"):
                self.game._spawn_quest_monsters(mqname)
            # Quest accepted visual effect
            self.quest_effects.append({
                "type": "quest_accepted",
                "timer": 2500,
                "duration": 2500,
                "col": npc.col,
                "row": npc.row,
                "quest_name": mqname,
            })
            self.game.sfx.play("quest_complete")
            self.show_message(
                f"{npc.name}: Wonderful! I'm counting on you. "
                f"Good luck!", 3000)
        else:
            # Decline
            self.show_message(
                f"{npc.name}: No worries. Come back if you change "
                f"your mind.", 3000)
        self.ow_quest_choice_active = False
        self.ow_quest_choices = []
        self.ow_quest_dialogue_lines = []
        self.ow_quest_dialogue_index = 0
        self.ow_npc_dialogue_active = False
        self.ow_npc_speaking = None

    def _dismiss_ow_npc_dialogue(self):
        """Close the overworld NPC dialogue."""
        self.ow_npc_dialogue_active = False
        self.ow_npc_speaking = None
        self.ow_quest_dialogue_lines = []
        self.ow_quest_dialogue_index = 0
        self.ow_quest_choice_active = False
        self.ow_quest_choices = []
        self.message = ""
        self.message_timer = 0

    def _check_quest_monster_kills(self):
        """After returning from combat, check if any killed monsters
        were quest targets and update step progress accordingly.

        Returns a message string if a step or quest was completed,
        otherwise None.
        """
        from src.quest_manager import check_quest_kills
        result_msg = check_quest_kills(self.game)
        if result_msg:
            self.quest_effects.append({
                "type": "step_complete",
                "timer": 2000,
                "duration": 2000,
                "text": result_msg,
            })
        return result_msg

    def _move_overworld_npcs(self):
        """Randomly wander overworld quest NPCs one step."""
        from src.settings import TILE_GRASS, TILE_PATH
        tmap = self.game.tile_map
        party = self.game.party
        npcs = getattr(self.game, "overworld_quest_npcs", [])
        if not npcs:
            return
        # Only move ~30% of the time so they don't zip around
        if random.random() > 0.3:
            return
        occupied = {(party.col, party.row)}
        for n in npcs:
            occupied.add((n.col, n.row))
        for mon in self.overworld_monsters:
            if mon.is_alive():
                occupied.add((mon.col, mon.row))
        for npc in npcs:
            # Quest collectible items never move
            if getattr(npc, "npc_type", "") == "quest_item":
                continue
            dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            random.shuffle(dirs)
            for dc, dr in dirs:
                nc, nr = npc.col + dc, npc.row + dr
                if ((nc, nr) not in occupied
                        and 0 <= nc < tmap.width
                        and 0 <= nr < tmap.height
                        and tmap.get_tile(nc, nr) in (
                            TILE_GRASS, TILE_PATH)):
                    occupied.discard((npc.col, npc.row))
                    npc.col = nc
                    npc.row = nr
                    occupied.add((nc, nr))
                    break

    # ── Monster helpers ───────────────────────────────────────────

    def _get_monster_at(self, col, row):
        """Return the alive orc at (col, row), or None."""
        for mon in self.overworld_monsters:
            if mon.col == col and mon.row == row and mon.is_alive():
                return mon
        return None

    def _move_monsters(self):
        """Each alive orc wanders randomly, but pursues if within 6 tiles.

        Guardian monsters (tagged with ``_guardian_anchor``) stay leashed
        near their artifact and only intercept the party when it gets
        close to the anchor point.

        While a repel effect is active, monsters inside its radius flee
        *away* from the party instead of pursuing.
        """
        party = self.game.party
        alive = [m for m in self.overworld_monsters if m.is_alive()]
        occupied = {(m.col, m.row) for m in alive}
        occupied.add((party.col, party.row))

        repel = self.repel_effect  # may be None

        for mon in alive:
            occupied.discard((mon.col, mon.row))
            prev_col, prev_row = mon.col, mon.row
            cheb = max(abs(mon.col - party.col), abs(mon.row - party.row))

            anchor = getattr(mon, "_guardian_anchor", None)
            if anchor:
                # ── Guardian behaviour: stay near artifact, intercept ──
                leash = getattr(mon, "_guardian_leash", GUARDIAN_LEASH)
                ax, ay = anchor
                dist_party_to_anchor = (abs(party.col - ax)
                                        + abs(party.row - ay))
                # Intercept: pursue if party is within 8 tiles of artifact
                if dist_party_to_anchor <= GUARDIAN_INTERCEPT_RANGE_OVERWORLD and cheb <= 10:
                    # Move toward party but don't stray too far from anchor
                    self._guardian_move_toward(
                        mon, party.col, party.row,
                        ax, ay, leash, occupied)
                else:
                    # Drift back toward anchor if too far, else idle
                    dist_to_anchor = (abs(mon.col - ax)
                                      + abs(mon.row - ay))
                    if dist_to_anchor > leash:
                        mon.try_move_toward(
                            ax, ay, self.game.tile_map, occupied)
                    # Otherwise stay put — guardians don't wander
            elif repel and cheb <= repel["radius"]:
                # If repel effect is active and monster is within radius, flee
                flee_col = mon.col + (mon.col - party.col)
                flee_row = mon.row + (mon.row - party.row)
                mon.try_move_toward(
                    flee_col, flee_row,
                    self.game.tile_map,
                    occupied,
                )
            elif abs(mon.col - party.col) + abs(mon.row - party.row) <= 6:
                mon.try_move_toward(
                    party.col, party.row,
                    self.game.tile_map,
                    occupied,
                )
            else:
                mon.try_move_random(
                    self.game.tile_map,
                    occupied,
                    party_col=party.col,
                    party_row=party.row,
                )
            # Safety: if a monster somehow landed on a non-walkable tile,
            # snap it back to its previous position.
            if not self.game.tile_map.is_walkable(mon.col, mon.row):
                mon.col, mon.row = prev_col, prev_row
            occupied.add((mon.col, mon.row))

        # Tick down the lingering repel effect (one step per party move)
        if repel:
            repel["steps_remaining"] -= 1
            if repel["steps_remaining"] <= 0:
                self.repel_effect = None

    def _guardian_move_toward(self, mon, target_col, target_row,
                              anchor_col, anchor_row, leash, occupied):
        """Move a guardian monster toward *target* without exceeding *leash*
        distance from the anchor (the artifact it protects).
        """
        from src.settings import TILE_GRASS, TILE_PATH
        tmap = self.game.tile_map

        # Try all four cardinal directions, prefer the one closest to target
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        best = None
        best_dist = abs(mon.col - target_col) + abs(mon.row - target_row)
        for dc, dr in dirs:
            nc, nr = mon.col + dc, mon.row + dr
            # Must stay within leash of anchor
            if (abs(nc - anchor_col) + abs(nr - anchor_row)) > leash:
                continue
            if (nc, nr) in occupied:
                continue
            if not (0 <= nc < tmap.width and 0 <= nr < tmap.height):
                continue
            if tmap.get_tile(nc, nr) not in (TILE_GRASS, TILE_PATH):
                continue
            d = abs(nc - target_col) + abs(nr - target_row)
            if d < best_dist:
                best_dist = d
                best = (nc, nr)
        if best:
            mon.col, mon.row = best

    def _check_monster_contact(self):
        """If an orc is adjacent to (or on top of) the party, start combat."""
        party = self.game.party
        for mon in self.overworld_monsters:
            if not mon.is_alive():
                continue
            if abs(mon.col - party.col) + abs(mon.row - party.row) <= 1:
                self._start_orc_combat(mon)
                return

    # ── Push spell (repel monsters) ───────────────────────────

    def _on_spell_repel_monsters(self, radius, push_distance, duration=0):
        """Push all overworld monsters within *radius* tiles away from the
        party, moving them *push_distance* steps in the opposite direction.
        Also triggers an expanding-wave animation on the map.

        If *duration* > 0 the repel effect lingers: for that many movement
        steps, all monsters within the radius will flee instead of pursuing.
        """
        self._push_monsters_away(radius, push_distance)

        # Set up lingering repel effect that lasts *duration* movement steps.
        # The visual animation is tied to this effect's lifetime.
        if duration > 0:
            self.repel_effect = {
                "steps_remaining": duration,
                "total_steps": duration,
                "radius": radius,
            }

        # Start the initial expanding-wave burst animation
        burst_ms = 1200
        self.push_spell_anim = {
            "burst_timer": burst_ms,
            "burst_duration": burst_ms,
            "max_radius": radius,
            "elapsed_ms": 0.0,       # total ms since cast (for pulsing)
        }

        self.game.sfx.play("magic_burst")

    def _push_monsters_away(self, radius, push_distance):
        """Immediately push all monsters within *radius* tiles away from
        the party by up to *push_distance* steps."""
        party = self.game.party
        tile_map = self.game.tile_map

        occupied = {(m.col, m.row) for m in self.overworld_monsters
                    if m.is_alive()}

        for mon in self.overworld_monsters:
            if not mon.is_alive():
                continue
            dx = mon.col - party.col
            dy = mon.row - party.row
            dist = max(abs(dx), abs(dy))  # Chebyshev distance
            if dist > radius or dist == 0:
                continue

            # Normalise direction away from party
            dir_x = (1 if dx > 0 else (-1 if dx < 0 else 0))
            dir_y = (1 if dy > 0 else (-1 if dy < 0 else 0))

            # Push step by step (terrain-aware so sea creatures stay in
            # water and land creatures stay on land)
            occupied.discard((mon.col, mon.row))
            for _step in range(push_distance):
                nc = mon.col + dir_x
                nr = mon.row + dir_y
                if (mon._can_enter(nc, nr, tile_map)
                        and (nc, nr) not in occupied
                        and (nc, nr) != (party.col, party.row)):
                    mon.col = nc
                    mon.row = nr
                else:
                    break
            occupied.add((mon.col, mon.row))

    def _start_orc_combat(self, orc):
        """Start combat against the contacted orc and any nearby orcs."""
        combat_state = self.game.states.get("combat")
        if not combat_state:
            return

        fighter = None
        for member in self.game.party.members:
            if member.is_alive():
                fighter = member
                break
        if not fighter:
            return

        # Use the pre-assigned encounter template stored on the map monster.
        # Fall back to a random encounter if not present.
        tmpl = getattr(orc, "encounter_template", None)
        if tmpl is None:
            enc = create_encounter("overworld")
            monsters = enc["monsters"]
            enc_name = enc["name"]
        else:
            monsters = [create_monster(n) for n in tmpl["monster_names"]]
            enc_name = tmpl["name"]
        for m in monsters:
            m.col = orc.col
            m.row = orc.row

        self.game.sfx.play("encounter")
        # Pass the terrain tile the party is standing on so the combat
        # arena can spawn appropriate obstacles (trees, rocks, etc.)
        terrain_tile = self.game.tile_map.get_tile(
            self.game.party.col, self.game.party.row)
        combat_state.start_combat(fighter, monsters,
                                  source_state="overworld",
                                  encounter_name=enc_name,
                                  map_monster_refs=[orc],
                                  terrain_tile=terrain_tile,
                                  combat_location="overview")
        self.game.change_state("combat")

    # ── Tile events ───────────────────────────────────────────────

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        # After returning from a town/dungeon, skip the first check so
        # the player isn't immediately prompted to re-enter.
        if self._exit_grace:
            self._exit_grace = False
            return

        # Don't re-trigger if an action screen is already active
        if (self.building_action_active or self.dungeon_action_active
                or self.town_action_active):
            return

        party = self.game.party

        # ── If inside an overworld interior, check exits and links ──
        if self._in_overworld_interior:
            # Skip exit check on the first move after entering so the
            # player isn't immediately ejected when spawning on an exit.
            if self._overworld_interior_entry_grace:
                self._overworld_interior_entry_grace = False
            else:
                if (party.col, party.row) in self._overworld_interior_exit_positions:
                    self._exit_overworld_interior()
                    return
            # Interior-to-interior links
            interior_name = self._overworld_interior_links.get(
                (party.col, party.row))
            if interior_name:
                self._enter_overworld_interior(
                    interior_name, party.col, party.row,
                    building_name=self._building_name)
                return
            return  # no other tile events inside interiors

        # ── Overworld link check (highest priority) ──
        # An explicit link overrides any tile-type behaviour so the
        # designer can place an interior/town entrance on any tile graphic.
        pcol, prow = party.col, party.row
        tmap = self.game.tile_map
        link = tmap.get_link(pcol, prow)
        if link and link.get("target_map"):
            link_name = link["target_map"]
            link_type = link.get("target_type", "")

            # ── Building link — show action screen ──
            if link_type == "building":
                building_def = self._find_module_building_by_name(link_name)
                if building_def is not None:
                    spaces = building_def.get("spaces", [])
                    if spaces:
                        sub = link.get("sub_interior", "")
                        display_name = (
                            f"{building_def.get('name', link_name)}"
                            f" / {sub}" if sub else
                            building_def.get("name", link_name))
                        self.building_action_info = {
                            "name": display_name,
                            "description": building_def.get("description",
                                "A structure stands before you."),
                        }
                        self.building_action_entry_args = {
                            "building_def": building_def,
                            "col": pcol,
                            "row": prow,
                            "sub_interior": sub,
                        }
                        self.building_action_cursor = 0
                        self.building_action_active = True
                        return

            # ── Dungeon link ──
            if link_type == "dungeon":
                dungeon_def = self._find_module_dungeon_by_name(link_name)
                if dungeon_def is not None:
                    # Show dungeon action screen with module dungeon info
                    visited = self.game.is_dungeon_visited(pcol, prow)
                    self.dungeon_action_info = {
                        "name": dungeon_def.get("name", link_name),
                        "description": dungeon_def.get("description",
                            "A dark entrance leads underground."),
                        "visited": visited,
                        "cleared": False,
                        "quest_name": None,
                    }
                    self.dungeon_action_entry_args = {
                        "type": "module_dungeon",
                        "col": pcol,
                        "row": prow,
                        "dungeon_def": dungeon_def,
                    }
                    self.dungeon_action_cursor = 0
                    self.dungeon_action_active = True
                    return

            # ── Town link (optionally targeting a sub-interior) ──
            town_match = self._find_town_by_name(link_name)
            if town_match is not None:
                # Ensure the town is registered at this tile position
                # so get_town_at() finds it during _show_town_action.
                if (pcol, prow) not in self.game.town_data_map:
                    self.game.town_data_map[(pcol, prow)] = town_match
                # If the link targets a specific sub-interior, stash
                # it so _enter_town_confirmed can auto-enter it.
                sub = link.get("sub_interior", "")
                if sub:
                    self._pending_sub_interior = sub
                else:
                    self._pending_sub_interior = ""
                self._show_town_action()
                return
            self._enter_overworld_interior(
                link_name, pcol, prow)
            return

        tile_id = tmap.get_tile(pcol, prow)

        if tile_id == TILE_TOWN:
            # Only trigger town entry if the module actually defines a
            # town at this position.  Placing a town *graphic* on the
            # overworld map is purely cosmetic until the designer
            # registers the town in the module editor.
            if (pcol, prow) in self.game.town_data_map:
                self._show_town_action()
                return

        elif tile_id in (TILE_DUNGEON, TILE_DUNGEON_CLEARED):
            # Check if a unified link points to a module dungeon
            # (handles dungeon tiles that have an explicit link)
            link = tmap.get_link(pcol, prow)
            if link and link.get("target_map"):
                ddef = self._find_module_dungeon_by_name(
                    link["target_map"])
                if ddef is not None:
                    visited = self.game.is_dungeon_visited(pcol, prow)
                    self.dungeon_action_info = {
                        "name": ddef.get("name", link["target_map"]),
                        "description": ddef.get("description",
                            "A dark entrance leads underground."),
                        "visited": visited,
                        "cleared": (tile_id == TILE_DUNGEON_CLEARED),
                        "quest_name": None,
                    }
                    self.dungeon_action_entry_args = {
                        "type": "module_dungeon",
                        "col": pcol,
                        "row": prow,
                        "dungeon_def": ddef,
                    }
                    self.dungeon_action_cursor = 0
                    self.dungeon_action_active = True
                    return
            # In custom modules, only linked dungeons should trigger entry.
            # Unlinked dungeon tiles are treated as scenery.
            if not self.game.module_manifest:
                self._show_dungeon_action(pcol, prow)
            return

        elif tile_id == TILE_MACHINE:
            self._interact_machine()
            return

        elif tile_id == TILE_CHEST:
            self._open_chest()
            # Restore the original tile that was under the chest
            pos = (pcol, prow)
            original = self.chest_under_tiles.pop(pos, TILE_GRASS)
            tmap.set_tile(pos[0], pos[1], original)
            return

        # ── Unique tile check ──
        self._check_unique_tile()

    # ── Overworld interior entry / exit ──────────────────────

    def _enter_overworld_interior(self, interior_name, door_col, door_row,
                                     building_name=""):
        """Transition into an overworld interior (dungeon-style map)."""
        tmap = self.game.tile_map

        # If the target interior is already in the stack, unwind back to it
        # instead of nesting deeper (same pattern as town.py).
        stack = self._overworld_interior_stack
        for i in range(len(stack) - 1, -1, -1):
            if stack[i].get("name") == interior_name:
                while len(stack) > i + 1:
                    stack.pop()
                prev = stack.pop()
                self.game.tile_map = prev["tile_map"]
                self._overworld_interior_links = prev["interior_links"]
                self._overworld_interior_exit_positions = prev["exit_positions"]
                self.game.party.col = prev["col"]
                self.game.party.row = prev["row"]
                self._overworld_interior_name = prev.get("name", "")
                if not stack:
                    self._in_overworld_interior = False
                    # Restore overworld state
                    if self._stashed_overworld_tile_map is not None:
                        self.game.tile_map = self._stashed_overworld_tile_map
                        self._stashed_overworld_tile_map = None
                    if self._stashed_overworld_monsters is not None:
                        self.overworld_monsters = self._stashed_overworld_monsters
                        self._stashed_overworld_monsters = None
                self.game.camera.map_width = self.game.tile_map.width
                self.game.camera.map_height = self.game.tile_map.height
                self.game.camera.update(
                    self.game.party.col, self.game.party.row)
                self.show_message(
                    f"Returning to {interior_name}...", 1000)
                return

        # Find the interior definition from the overworld tile map's
        # interiors list (loaded from static_overworld.json).
        src_tmap = self._stashed_overworld_tile_map or tmap
        interiors = getattr(src_tmap, "overworld_interiors", [])
        interior = None
        for entry in interiors:
            if entry.get("name") == interior_name:
                interior = entry
                break
        if not interior or not interior.get("tiles"):
            self.show_message("Nothing here.", 1500)
            return

        # Push current state onto the interior stack.
        # ``source_map`` records where we came from so the destination
        # interior can find the correct back-link tile without searching.
        source_map_name = self._overworld_interior_name or "overworld"
        self._overworld_interior_stack.append({
            "col": door_col,
            "row": door_row,
            "source_map": source_map_name,
            "tile_map": self.game.tile_map,
            "interior_links": dict(self._overworld_interior_links),
            "exit_positions": set(self._overworld_interior_exit_positions),
            "name": self._overworld_interior_name,
        })

        # First time entering from the overworld — stash the overworld map
        if not self._in_overworld_interior:
            self._stashed_overworld_tile_map = tmap
            self._stashed_overworld_monsters = list(self.overworld_monsters)
            self.overworld_monsters = []  # no roaming orcs in interiors

        self._overworld_interior_name = interior_name
        self._in_overworld_interior = True
        self._overworld_interior_entry_grace = True

        # Build a tile map from the interior grid (dungeon tiles)
        from src.tile_map import TileMap
        from src.settings import TILE_VOID
        iw = interior.get("width", 14)
        ih = interior.get("height", 15)
        imap = TileMap(iw, ih, default_tile=TILE_VOID, oob_tile=TILE_VOID)

        for pos_key, td in interior.get("tiles", {}).items():
            parts = pos_key.split(",")
            c, r = int(parts[0]), int(parts[1])
            tid = td.get("tile_id")
            if tid is not None and 0 <= c < iw and 0 <= r < ih:
                imap.set_tile(c, r, tid)
                path = td.get("path")
                if path:
                    imap.sprite_overrides[(c, r)] = path

        self.game.tile_map = imap

        # Build unified links from interior tile flags and derive
        # exit/interior-link sets from them.
        from src.tile_map import TileMap as _TM
        imap.links = _TM.build_links_from_sparse_tiles(
            interior.get("tiles", {}), source_map=interior_name)
        self._overworld_interior_exit_positions = imap.get_exit_positions()
        self._overworld_interior_links = imap.get_interior_links()
        exit_positions = list(self._overworld_interior_exit_positions)
        first_walkable = None
        entry_placed = False

        # ── Priority 1: explicit target_pos from link registry ──
        # If the link that triggered this transition has a target_pos,
        # use it directly — no guessing.
        _src_link = tmap.get_link(door_col, door_row) if tmap else None
        if _src_link:
            _tp = _src_link.get("target_pos")
            if _tp and _tp != (0, 0) and _tp is not None:
                self.game.party.col = _tp[0]
                self.game.party.row = _tp[1]
                entry_placed = True

        # ── Priority 2+: BFS / fallback ──
        if not entry_placed:
            for pos_key, td in interior.get("tiles", {}).items():
                parts = pos_key.split(",")
                c, r = int(parts[0]), int(parts[1])
                tid = td.get("tile_id")
                if first_walkable is None and tid is not None:
                    from src.settings import TILE_DEFS
                    tdef = TILE_DEFS.get(tid, {})
                    if tdef.get("walkable", False):
                        first_walkable = (c, r)

        # BFS from exit tile to find nearest walkable non-exit tile for spawn
        if exit_positions and not entry_placed:
            from src.settings import TILE_DEFS as _TD
            ec, er = exit_positions[0]
            visited = set()
            queue = [(ec, er)]
            visited.add((ec, er))
            while queue and not entry_placed:
                cx, cy = queue.pop(0)
                for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    nc, nr = cx + dc, cy + dr
                    if (nc, nr) in visited:
                        continue
                    visited.add((nc, nr))
                    if not (0 <= nc < iw and 0 <= nr < ih):
                        continue
                    ntid = imap.get_tile(nc, nr)
                    if _TD.get(ntid, {}).get("walkable", False):
                        if (nc, nr) not in self._overworld_interior_exit_positions:
                            self.game.party.col = nc
                            self.game.party.row = nr
                            entry_placed = True
                            break
                    queue.append((nc, nr))
            # Last resort: place on the exit tile itself
            if not entry_placed:
                self.game.party.col = ec
                self.game.party.row = er
                entry_placed = True

        if not entry_placed and first_walkable:
            self.game.party.col = first_walkable[0]
            self.game.party.row = first_walkable[1]
            entry_placed = True

        if not entry_placed:
            self.game.party.col = iw // 2
            self.game.party.row = ih // 2

        # Update camera
        self.game.camera.map_width = iw
        self.game.camera.map_height = ih
        self.game.camera.update(self.game.party.col, self.game.party.row)

        # Spawn data-defined NPCs from the interior definition first.
        self._building_interior_npcs = []
        self._build_building_interior_npcs(interior, imap)

        # Spawn quest items and guardians for this building interior.
        # Quest data can be keyed by building name ("building:X") or
        # by a specific space ("space:X/Y").
        self._building_name = building_name or interior_name
        quest_key_name = self._building_name
        self._spawn_building_quest_collect_items(
            quest_key_name, imap, space_name=interior_name)
        self._spawn_building_quest_monsters(
            quest_key_name, imap, space_name=interior_name)
        self._spawn_building_quest_givers(
            quest_key_name, interior_name, imap)

        self.show_message(f"Entering {interior_name}...", 1500)

    def _exit_overworld_interior(self):
        """Return from an overworld interior to the previous level."""
        stack = self._overworld_interior_stack
        if not stack:
            self._in_overworld_interior = False
            return
        prev = stack.pop()
        self.game.tile_map = prev["tile_map"]
        self.game.party.col = prev["col"]
        self.game.party.row = prev["row"]
        self._overworld_interior_exit_positions = prev.get(
            "exit_positions", set())
        self._overworld_interior_links = prev.get("interior_links", {})
        leaving_name = self._overworld_interior_name
        self._overworld_interior_name = prev.get("name", "")

        # If the stack is now empty, we're back on the overworld
        if not stack:
            self._in_overworld_interior = False
            # Restore the stashed overworld tile map (which has tile_links etc)
            if self._stashed_overworld_tile_map is not None:
                self.game.tile_map = self._stashed_overworld_tile_map
                self._stashed_overworld_tile_map = None
            if self._stashed_overworld_monsters is not None:
                self.overworld_monsters = self._stashed_overworld_monsters
                self._stashed_overworld_monsters = None

        self.game.camera.map_width = self.game.tile_map.width
        self.game.camera.map_height = self.game.tile_map.height
        self.game.camera.update(self.game.party.col, self.game.party.row)
        self._building_interior_npcs = []
        self._building_name = ""
        self._exit_grace = True  # don't re-trigger the tile link immediately
        self.show_message(f"Leaving {leaving_name}...", 1000)

    # ── Building interior quest spawning & interaction ─────────

    def _build_building_interior_npcs(self, interior_def, imap):
        """Create NPC objects from a building interior's ``npcs`` list.

        Reads an optional ``"npcs"`` array from the interior/space
        definition and appends :class:`NPC` objects to
        ``_building_interior_npcs``.
        """
        import random as _rng
        from src.town_generator import NPC

        npc_defs = interior_def.get("npcs")
        if not npc_defs:
            return

        iw, ih = imap.width, imap.height
        walkable = set()
        for wy in range(ih):
            for wx in range(iw):
                if imap.is_walkable(wx, wy):
                    walkable.add((wx, wy))
        # Remove exit tiles from candidates
        for pos in self._overworld_interior_exit_positions:
            walkable.discard(pos)
        walkable.discard((self.game.party.col, self.game.party.row))

        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        rng = _rng.Random(
            hash(interior_def.get("name", "")) & 0xFFFFFFFF)

        for nd in npc_defs:
            npc_name = nd.get("name", "Villager")
            dialogue = nd.get("dialogue", ["..."])
            if not dialogue:
                dialogue = ["..."]
            npc = NPC(
                col=nd.get("col", 0),
                row=nd.get("row", 0),
                name=npc_name,
                dialogue=dialogue,
                npc_type=nd.get("npc_type", "villager"),
                god_name=nd.get("god_name"),
                shop_type=nd.get("shop_type", "general"),
                sprite=nd.get("sprite") or None,
                quest_dialogue=nd.get("quest_dialogue"),
                quest_choices=nd.get("quest_choices"),
                quest_name=nd.get("quest_name"),
                artifact_name=nd.get("artifact_name"),
                hint_active=nd.get("hint_active"),
                text_complete=nd.get("text_complete"),
                innkeeper_quests=nd.get("innkeeper_quests", False),
            )
            npc.wander_range = nd.get("wander_range", 4)

            # If specified position is free, keep it; else pick random
            pos = (npc.col, npc.row)
            if pos in walkable and pos not in occupied:
                occupied.add(pos)
            else:
                free = list(walkable - occupied)
                if free:
                    nc, nr = rng.choice(free)
                    npc.col = nc
                    npc.row = nr
                    occupied.add((nc, nr))

            self._building_interior_npcs.append(npc)

    def _spawn_building_quest_collect_items(self, interior_name, imap,
                                               space_name=""):
        """Place collectible quest items inside a building interior."""
        import random as _rng
        from src.town_generator import NPC

        items_dict = getattr(self.game, "quest_collect_items", {})
        # Check both the generic building key and the specific space key.
        # e.g. "building:Abandoned Building" and
        #      "space:Abandoned Building/Basement"
        entries = list(items_dict.get(f"building:{interior_name}", []))
        if space_name:
            entries.extend(items_dict.get(
                f"space:{interior_name}/{space_name}", []))
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})

        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = set()
        # Exclude exit positions
        occupied.update(self._overworld_interior_exit_positions)
        rng = _rng.Random(hash(interior_name) & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            item_name = entry["item_name"]
            item_sprite = entry.get("item_sprite", "")

            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue

            free = [p for p in walkable if p not in occupied]
            if not free:
                break
            col, row = rng.choice(free)
            occupied.add((col, row))

            npc = NPC(
                col=col, row=row,
                name=item_name,
                dialogue=[f"You found {item_name}!"],
                npc_type="quest_item",
            )
            npc._quest_name = qname
            npc._quest_step_idx = step_idx
            npc._item_sprite = item_sprite
            npc.quest_highlight = True
            self._building_interior_npcs.append(npc)

    def _spawn_building_quest_monsters(self, interior_name, imap,
                                          space_name=""):
        """Place quest monster NPCs inside a building interior."""
        import random as _rng
        from src.town_generator import NPC
        from src.monster import MONSTERS

        monsters_dict = getattr(self.game, "quest_interior_monsters", {})
        # Check both the generic building key and the specific space key.
        entries = list(monsters_dict.get(f"building:{interior_name}", []))
        if space_name:
            entries.extend(monsters_dict.get(
                f"space:{interior_name}/{space_name}", []))
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})

        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        occupied.update(self._overworld_interior_exit_positions)
        rng = _rng.Random(hash(interior_name + "_mon") & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            monster_key = entry["monster_key"]
            count = entry.get("count", 1)
            is_guardian = entry.get("is_guardian", False)

            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue

            monster_info = MONSTERS.get(monster_key, {})
            display_name = monster_info.get(
                "name", monster_key.replace("_", " ").title())

            # Find the quest_item this guardian protects
            anchor_pos = None
            if is_guardian:
                for existing_npc in self._building_interior_npcs:
                    if (getattr(existing_npc, "npc_type", "") == "quest_item"
                            and getattr(existing_npc, "_quest_name", "") == qname
                            and getattr(existing_npc, "_quest_step_idx", -1) == step_idx):
                        anchor_pos = (existing_npc.col, existing_npc.row)
                        break

            for i in range(count):
                if anchor_pos:
                    ax, ay = anchor_pos
                    nearby = [(ax + dc, ay + dr)
                              for dc in range(-2, 3)
                              for dr in range(-2, 3)
                              if (dc, dr) != (0, 0)
                              and (ax + dc, ay + dr) in walkable
                              and (ax + dc, ay + dr) not in occupied]
                    if nearby:
                        col, row = rng.choice(nearby)
                    else:
                        free = [p for p in walkable if p not in occupied]
                        if not free:
                            break
                        col, row = rng.choice(free)
                else:
                    free = [p for p in walkable if p not in occupied]
                    if not free:
                        break
                    col, row = rng.choice(free)
                occupied.add((col, row))

                npc = NPC(
                    col=col, row=row,
                    name=display_name,
                    dialogue=["*growls menacingly*"],
                    npc_type="quest_monster",
                )
                npc._quest_name = qname
                npc._quest_step_idx = step_idx
                npc._monster_key = monster_key
                npc.wander_range = NPC_WANDER_RANGE
                if is_guardian and anchor_pos:
                    npc._guardian_anchor = anchor_pos
                    npc._guardian_leash = GUARDIAN_LEASH
                self._building_interior_npcs.append(npc)

    def _spawn_building_quest_givers(self, building_name, space_name, imap):
        """Place quest giver NPCs inside a building interior.

        Matches quests whose giver_location is
        ``space:<building_name>/<space_name>``.
        """
        import random as _rng
        from src.town_generator import NPC

        quest_defs = getattr(self.game, "_module_quest_defs", [])
        if not quest_defs:
            return

        mq_states = getattr(self.game, "module_quest_states", {})

        # Match locations like "space:Mystery Shrine/Main Hall"
        loc_key = f"space:{building_name}/{space_name}"
        # Also match just the building name for simpler configs
        loc_key_bldg = f"space:{building_name}"

        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        occupied.update(self._overworld_interior_exit_positions)
        rng = _rng.Random(hash(building_name + space_name) & 0xFFFFFFFF)

        for qdef in quest_defs:
            qname = qdef.get("name", "")
            if not qname:
                continue
            loc = qdef.get("giver_location", "")
            if loc != loc_key and loc != loc_key_bldg:
                continue

            # Don't spawn if quest is fully turned in
            qstate = mq_states.get(qname, {})
            if qstate.get("status") == "turned_in":
                continue

            # Don't spawn if already present
            already = any(
                getattr(n, "_module_quest_name", "") == qname
                for n in self._building_interior_npcs
            )
            if already:
                continue

            npc_label = qdef.get("giver_npc", "") or qname
            sprite = qdef.get("giver_sprite", "") or None
            dialogue_text = qdef.get("giver_dialogue", "")
            if dialogue_text:
                lines = [s.strip() for s in dialogue_text.split("\n")
                         if s.strip()]
                if not lines:
                    lines = [dialogue_text]
            else:
                lines = [f"I have a quest for you: {qname}"]

            free = [p for p in walkable if p not in occupied]
            if not free:
                break
            col, row = rng.choice(free)
            occupied.add((col, row))

            npc = NPC(
                col=col, row=row,
                name=npc_label,
                dialogue=[
                    "Thank you for your help!",
                    "The quest awaits...",
                ],
                npc_type="module_quest_giver",
                quest_dialogue=lines,
                quest_choices=["Accept quest", "Not right now"],
                sprite=sprite,
            )
            npc._module_quest_name = qname
            npc.wander_range = NPC_WANDER_RANGE
            self._building_interior_npcs.append(npc)

    def _check_building_interior_npc(self):
        """Check if the party bumped into a building interior NPC."""
        party = self.game.party
        for npc in self._building_interior_npcs:
            if npc.col == party.col and npc.row == party.row:
                if npc.npc_type == "quest_monster":
                    self._start_building_quest_combat(npc)
                    return True
                elif npc.npc_type == "quest_item":
                    self._collect_building_quest_item(npc)
                    return True
        return False

    def _collect_building_quest_item(self, npc):
        """Pick up a quest collectible item inside a building interior."""
        from src.quest_manager import collect_quest_item
        if npc in self._building_interior_npcs:
            self._building_interior_npcs.remove(npc)
        msg = collect_quest_item(
            self.game,
            getattr(npc, "_quest_name", ""),
            getattr(npc, "_quest_step_idx", -1),
            npc.name)
        self.show_message(msg, 3000 if "complete" in msg.lower() else 2500)

    def _start_building_quest_combat(self, npc):
        """Initiate combat with a quest monster NPC inside a building."""
        from src.monster import create_monster

        monster_key = getattr(npc, "_monster_key", "skeleton")
        combat_state = self.game.states.get("combat")
        if not combat_state:
            return

        fighter = None
        for member in self.game.party.members:
            if member.is_alive():
                fighter = member
                break
        if not fighter:
            return

        monsters = [create_monster(monster_key)]
        enc_name = f"Quest: {npc.name}"

        self.game.sfx.play("encounter")
        terrain_tile = self.game.tile_map.get_tile(
            self.game.party.col, self.game.party.row)
        npc._is_quest_monster_npc = True
        self._building_combat_npc = npc
        self._building_returning_from_combat = True
        # Determine the combat location for quest kill tracking
        int_name = self._overworld_interior_name
        bld_name = self._building_name
        bld_loc = f"space:{bld_name}/{int_name}" \
            if bld_name and int_name and bld_name != int_name \
            else f"building:{bld_name or int_name}"
        combat_state.start_combat(
            fighter, monsters,
            source_state="overworld",
            encounter_name=enc_name,
            terrain_tile=terrain_tile,
            combat_location=bld_loc)
        self.game.change_state("combat")

    def _move_building_interior_npcs(self):
        """Move NPCs inside a building interior (guardians + wanderers)."""
        import random as _rng
        import time as _t

        party = self.game.party
        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        occupied.add((party.col, party.row))

        from src.town_generator import NPC as _NPCClass
        for npc in self._building_interior_npcs:
            # Random wandering for quest givers and non-guardian NPCs.
            # Quest items, quest monsters (guardians), and stationary
            # types (shopkeep, innkeeper, priest, gnome) stay in place.
            wr = getattr(npc, "wander_range", 0)
            stationary = getattr(_NPCClass, "STATIONARY_TYPES", set())
            if wr and npc.npc_type not in stationary and npc.npc_type != "quest_monster":
                if _rng.random() < 0.3:  # 30% chance each move
                    dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
                    _rng.shuffle(dirs)
                    for dc, dr in dirs:
                        nc, nr = npc.col + dc, npc.row + dr
                        if (nc, nr) in occupied:
                            continue
                        if not self.game.tile_map.is_walkable(nc, nr):
                            continue
                        occupied.discard((npc.col, npc.row))
                        npc.col, npc.row = nc, nr
                        occupied.add((nc, nr))
                        break
                continue

            if npc.npc_type != "quest_monster":
                continue

            anchor = getattr(npc, "_guardian_anchor", None)
            if not anchor:
                continue

            leash = getattr(npc, "_guardian_leash", GUARDIAN_LEASH)
            ax, ay = anchor
            pcol, prow = party.col, party.row
            dist_party_to_anchor = abs(pcol - ax) + abs(prow - ay)

            # Guardian intercepts when party approaches artifact
            if dist_party_to_anchor <= GUARDIAN_INTERCEPT_RANGE_INTERIOR:
                # Move toward party but stay within leash of anchor
                best = None
                best_dist = abs(npc.col - pcol) + abs(npc.row - prow)
                for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    nc, nr = npc.col + dc, npc.row + dr
                    if (nc, nr) in occupied and (nc, nr) != (npc.col, npc.row):
                        continue
                    if not self.game.tile_map.is_walkable(nc, nr):
                        continue
                    if abs(nc - ax) + abs(nr - ay) > leash:
                        continue
                    d = abs(nc - pcol) + abs(nr - prow)
                    if d < best_dist:
                        best_dist = d
                        best = (nc, nr)
                if best:
                    occupied.discard((npc.col, npc.row))
                    npc.col, npc.row = best
                    occupied.add(best)
            else:
                # Drift back to anchor if too far
                dist_to_anchor = abs(npc.col - ax) + abs(npc.row - ay)
                if dist_to_anchor > leash:
                    best = None
                    best_d = dist_to_anchor
                    for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                        nc, nr = npc.col + dc, npc.row + dr
                        if (nc, nr) in occupied:
                            continue
                        if not self.game.tile_map.is_walkable(nc, nr):
                            continue
                        d = abs(nc - ax) + abs(nr - ay)
                        if d < best_d:
                            best_d = d
                            best = (nc, nr)
                    if best:
                        occupied.discard((npc.col, npc.row))
                        npc.col, npc.row = best
                        occupied.add(best)

    def _start_building_npc_dialogue(self, npc):
        """Show dialogue for a regular NPC inside a building interior.

        Shows all dialogue lines sequentially; press Enter to advance.
        """
        lines = list(npc.dialogue) if npc.dialogue else ["..."]
        self.ow_npc_dialogue_active = True
        self.ow_npc_speaking = npc
        if len(lines) > 1:
            self.ow_quest_dialogue_lines = lines
            self.ow_quest_dialogue_index = 0
            remaining = len(lines) - 1
            hint = "  [ENTER] >" if remaining > 0 else "  [ENTER]"
            self.show_message(
                f"{npc.name}: {lines[0]}{hint}", 999999)
        else:
            self.ow_quest_dialogue_lines = []
            self.show_message(
                f"{npc.name}: {lines[0]}  [ENTER]", 999999)

    # ── Unique tile interaction ────────────────────────────────

    def _check_unique_tile(self):
        """Check if the party is standing on a unique tile and trigger it."""
        tmap = self.game.tile_map
        col, row = self.game.party.col, self.game.party.row
        utile = tmap.get_unique(col, row)
        if not utile:
            return

        # One-time tiles that have already been triggered
        one_time = utile.get("interact_data", {}).get("one_time", False)
        if one_time and tmap.is_unique_triggered(col, row):
            return

        # Cooldown check
        if tmap.is_unique_on_cooldown(col, row):
            return

        # ── Show the description and interact text ──
        name = utile.get("name", "Something")
        description = utile.get("description", "")
        interact_text = utile.get("interact_text", "")

        # Log the discovery
        self.game.game_log.append(f"-- {name} --")
        if description:
            self.game.game_log.append(description)
        if interact_text:
            self.game.game_log.append(interact_text)

        # Show a brief floating message on screen
        self.show_message(name, 3500)

        # Show description in bottom bar with animation
        self.unique_tile_text = description or interact_text or name
        self.unique_tile_timer = 5000  # 5 seconds
        self.unique_tile_flash = 0.0
        self.unique_tile_pos = (col, row)

        # Mark one-time tiles
        if one_time:
            tmap.mark_unique_triggered(col, row)

        # Apply cooldown if specified
        cooldown = utile.get("interact_data", {}).get("cooldown_steps", 0)
        if cooldown > 0:
            tmap.set_unique_cooldown(col, row, cooldown)

        # ── Special quest handling ──
        quest_id = utile.get("interact_data", {}).get("quest_id")
        if quest_id == "house_quest":
            self._activate_house_quest()

    # ── House quest ───────────────────────────────────────────

    def _is_house_quest_dungeon(self, col, row):
        """Check if the tile at (col, row) is the active house quest dungeon."""
        hq = getattr(self.game, "house_quest", None)
        if not hq or hq["status"] not in ("active", "artifact_found"):
            return False
        return col == hq["dungeon_col"] and row == hq["dungeon_row"]

    # ── Dungeon action screen ─────────────────────────────────

    # ── Town/location action screen ──────────────────────────────

    _TOWN_DESCRIPTIONS = {
        "Thornwall": "A sturdy frontier town nestled against the hills. Merchants, healers, and townsfolk go about their daily lives within its wooden walls.",
        "Duskhollow": "A shadowed settlement cloaked in perpetual twilight. Strange lights flicker in the windows and whispered rumors fill the streets.",
    }

    def _find_town_by_name(self, name):
        """Return the TownData whose name matches *name*, or None."""
        for td in self.game.town_data_map.values():
            if getattr(td, "name", None) == name:
                return td
        # Also check the default town_data (hub town)
        if (hasattr(self.game, "town_data")
                and self.game.town_data
                and getattr(self.game.town_data, "name", None) == name):
            return self.game.town_data
        return None

    def _find_module_dungeon_by_name(self, name):
        """Return the dungeon dict from dungeons.json whose name matches, or None."""
        import json, os
        mod_path = getattr(self.game, "active_module_path", "")
        if not mod_path:
            return None
        p = os.path.join(mod_path, "dungeons.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r") as f:
                dungeons = json.load(f)
            if not isinstance(dungeons, list):
                return None
            for d in dungeons:
                if d.get("name") == name:
                    return d
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _find_module_building_by_name(self, name):
        """Return the building dict from buildings.json whose name matches, or None."""
        import json, os
        mod_path = getattr(self.game, "active_module_path", "")
        if not mod_path:
            return None
        p = os.path.join(mod_path, "buildings.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r") as f:
                buildings = json.load(f)
            if not isinstance(buildings, list):
                return None
            # Exact match first
            for b in buildings:
                if b.get("name") == name:
                    return b
            # Case-insensitive fallback
            name_lower = name.lower()
            for b in buildings:
                if b.get("name", "").lower() == name_lower:
                    return b
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[building lookup] Error reading {p}: {exc}")
        return None

    def _enter_module_dungeon(self, dungeon_def, pcol, prow):
        """Enter a module-defined dungeon (procedural or custom).

        For procedural mode: generates levels using generate_dungeon().
        For custom mode: converts the module's level data to DungeonData.
        """
        from src.dungeon_generator import generate_dungeon, DungeonData
        from src.tile_map import TileMap

        name = dungeon_def.get("name", "Dungeon")
        mode = dungeon_def.get("mode", "procedural")
        style = dungeon_def.get("dungeon_style", "cave")
        levels_data = dungeon_def.get("levels", [])

        dungeon_state = self.game.states["dungeon"]
        cache = self.game.dungeon_cache

        # Check cache first
        cached = cache.get((pcol, prow))
        if cached:
            if isinstance(cached, list) and len(cached) > 1:
                dungeon_state.enter_quest_dungeon(cached, pcol, prow)
            elif isinstance(cached, list) and len(cached) == 1:
                dungeon_state.enter_dungeon(cached[0], pcol, prow)
            else:
                dungeon_state.enter_dungeon(cached, pcol, prow)
            self.game.mark_dungeon_visited(pcol, prow)
            self.game.change_state("dungeon")
            return

        if mode == "procedural":
            # Map dungeon settings to generate_dungeon parameters
            size_map = {"small": (30, 20), "medium": (40, 30),
                        "large": (60, 40)}
            diff_rooms = {"easy": (4, 6), "normal": (6, 10),
                          "hard": (8, 14), "deadly": (10, 18)}
            torch_map = {"none": "none", "sparse": "sparse",
                         "moderate": "medium", "abundant": "dense"}
            sz = size_map.get(
                dungeon_def.get("level_size", "medium"), (40, 30))
            rm = diff_rooms.get(
                dungeon_def.get("difficulty", "normal"), (6, 10))
            td = torch_map.get(
                dungeon_def.get("torch_density", "moderate"), "medium")
            num_levels = max(1, int(dungeon_def.get("num_levels", 1)))
            doors = dungeon_def.get("locked_doors", "off") == "on"

            gen_levels = []
            seed_base = hash((name, pcol, prow)) & 0xFFFFFFFF
            for li in range(num_levels):
                lname = f"{name} - Floor {li + 1}" if num_levels > 1 else name
                dd = generate_dungeon(
                    name=lname, width=sz[0], height=sz[1],
                    min_rooms=rm[0], max_rooms=rm[1],
                    seed=seed_base + li,
                    place_stairs_down=(li < num_levels - 1),
                    place_doors=doors,
                    torch_density=td)
                gen_levels.append(dd)

            cache[(pcol, prow)] = gen_levels
            if len(gen_levels) > 1:
                dungeon_state.enter_quest_dungeon(gen_levels, pcol, prow)
            else:
                dungeon_state.enter_dungeon(gen_levels[0], pcol, prow)
        else:
            # Custom mode: convert module level data to DungeonData
            if not levels_data:
                # No levels defined yet — generate a placeholder
                dd = generate_dungeon(name=name)
                cache[(pcol, prow)] = [dd]
                dungeon_state.enter_dungeon(dd, pcol, prow)
            else:
                gen_levels = []
                from src.settings import TILE_DEFS as _TD
                from src.settings import TILE_STAIRS, TILE_STAIRS_DOWN
                from src.settings import TILE_DWALL
                for lv in levels_data:
                    lname = lv.get("name", name)
                    lw = lv.get("width", 20)
                    lh = lv.get("height", 20)
                    ecol = lv.get("entry_col", 0)
                    erow = lv.get("entry_row", 0)
                    # Build a TileMap from sparse tile data.
                    # Default to dungeon wall so unset cells render
                    # as solid walls rather than overworld grass.
                    # oob_tile also walls so camera edge is clean.
                    tmap = TileMap(lw, lh, default_tile=TILE_DWALL,
                                  oob_tile=TILE_DWALL)
                    # Parse tiles and collect designer-placed links
                    for pos_key, td in lv.get("tiles", {}).items():
                        parts = pos_key.split(",")
                        if len(parts) == 2:
                            c, r = int(parts[0]), int(parts[1])
                            tile_id = (td.get("tile_id", 0)
                                       if isinstance(td, dict) else td)
                            if 0 <= c < lw and 0 <= r < lh:
                                tmap.set_tile(c, r, tile_id)

                    # Build unified links from tile flags
                    from src.tile_map import TileMap as _TM2
                    tmap.links = _TM2.build_links_from_sparse_tiles(
                        lv.get("tiles", {}), source_map=lname)
                    overworld_exits = tmap.get_exit_positions()
                    interior_links = tmap.get_interior_links()

                    # ── Resolve entry point ──
                    # For the first level entering from the
                    # overworld, spawn at a to_overworld tile.
                    # For other levels, the dungeon state resolves
                    # spawn from the interior back-link at runtime.
                    if overworld_exits:
                        ecol, erow = next(iter(overworld_exits))
                    elif not _TD.get(tmap.get_tile(ecol, erow),
                                     {}).get("walkable", False):
                        for r in range(lh):
                            for c in range(lw):
                                if _TD.get(tmap.get_tile(c, r),
                                           {}).get("walkable", False):
                                    ecol, erow = c, r
                                    break
                            else:
                                continue
                            break

                    # ── Store legacy link attributes for backward
                    # compatibility with dungeon.py code ──
                    tmap._custom_mode = True
                    if overworld_exits:
                        tmap._custom_exit_doors = overworld_exits
                    if interior_links:
                        tmap._interior_links = interior_links

                    dd = DungeonData(
                        tile_map=tmap, rooms=[],
                        entry_col=ecol, entry_row=erow,
                        name=lname)

                    # ── Inject designer-placed encounters ──
                    import random as _rng
                    for enc_spec in lv.get("encounters", []):
                        mon_names = enc_spec.get("monsters", [])
                        if not mon_names:
                            # Legacy format
                            mid = enc_spec.get("monster_id", "")
                            cnt = max(1, int(enc_spec.get("count", 1)))
                            if mid:
                                mon_names = [mid] * cnt
                        if not mon_names:
                            continue
                        lead = mon_names[0]
                        monster = create_monster(lead)
                        placement = enc_spec.get("placement", "procedural")
                        if placement == "manual":
                            monster.col = int(enc_spec.get("col", ecol))
                            monster.row = int(enc_spec.get("row", erow))
                        else:
                            # Procedural: pick a random walkable tile
                            walkable = []
                            for _wr in range(lh):
                                for _wc in range(lw):
                                    if (_TD.get(tmap.get_tile(_wc, _wr),
                                                {}).get("walkable", False)
                                            and (_wc, _wr)
                                                not in overworld_exits):
                                        walkable.append((_wc, _wr))
                            if walkable:
                                mc, mr = _rng.choice(walkable)
                                monster.col, monster.row = mc, mr
                            else:
                                monster.col, monster.row = ecol, erow
                        ename = enc_spec.get("name", f"Encounter")
                        monster.encounter_template = {
                            "name": ename,
                            "monster_names": mon_names,
                            "monster_party_tile": lead,
                        }
                        dd.monsters.append(monster)

                    gen_levels.append(dd)
                cache[(pcol, prow)] = gen_levels
                if len(gen_levels) > 1:
                    dungeon_state.enter_quest_dungeon(
                        gen_levels, pcol, prow)
                else:
                    dungeon_state.enter_dungeon(
                        gen_levels[0], pcol, prow)

        self.game.mark_dungeon_visited(pcol, prow)
        self.game.change_state("dungeon")

    def _show_town_action(self):
        """Show the town entry action screen."""
        pcol, prow = self.game.party.col, self.game.party.row
        town_data = self.game.get_town_at(pcol, prow)
        name = town_data.name if town_data else "Town"
        # Use the user-defined description from TownData if available,
        # then fall back to hardcoded descriptions, then generic text.
        custom_desc = getattr(town_data, "description", "") if town_data else ""
        if custom_desc:
            desc = custom_desc
        else:
            desc = self._TOWN_DESCRIPTIONS.get(name,
                f"The town of {name} rises from the landscape. "
                "Smoke drifts from chimneys and voices carry on the wind.")

        # After a gnome machine quest is complete, darkness lifts
        has_gnome_machine = any(
            kd.get("quest_type") == "gnome_machine"
            for kd in getattr(self.game, "key_dungeons", {}).values())
        mod_id = ""
        if self.game.module_manifest:
            mod_id = self.game.module_manifest.get(
                "metadata", {}).get("id", "")
        if mod_id == "keys_of_shadow":
            has_gnome_machine = True
        if (has_gnome_machine
                and not getattr(self.game, "darkness_active", False)
                and getattr(self.game, "keys_inserted", 0) > 0):
            desc = (f"Once shrouded in eternal darkness, {name} now basks "
                    f"in warm sunlight. The townsfolk celebrate their freedom "
                    f"as life returns to normal.")

        self.town_action_info = {
            "name": name,
            "description": desc,
        }
        self.town_action_cursor = 0
        self.town_action_active = True

    def _handle_town_action_input(self, event):
        """Handle input for the town entry action screen."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.town_action_cursor = (self.town_action_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.town_action_cursor = (self.town_action_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.town_action_cursor == 0:
                self._enter_town_confirmed()
            else:
                self.town_action_active = False
        elif event.key == pygame.K_ESCAPE:
            self.town_action_active = False

    def _enter_town_confirmed(self):
        """Execute the actual town entry after the player confirms."""
        self.town_action_active = False
        pcol, prow = self.game.party.col, self.game.party.row
        town_data = self.game.get_town_at(pcol, prow)
        # Update game.town_data to the town being entered (for
        # downstream code that reads it, like victory messages)
        self.game.town_data = town_data

        # If a sub-interior was requested (e.g. overworld tile linked
        # directly to a tunnel inside this town), tell the town state
        # to auto-enter it once the town loads.
        sub = getattr(self, "_pending_sub_interior", "")
        if sub:
            self._pending_sub_interior = ""
        # Look up the link to get target_pos for exact placement
        _link = self.game.tile_map.get_link(pcol, prow)
        _target_pos = (_link.get("target_pos")
                       if _link else None)
        if _target_pos == (0, 0):
            _target_pos = None  # unresolved, use default

        # If entering via a registry link (has link_id), preserve the
        # town's existing overworld exit position so that normal exits
        # still return the party to their original entry point — not
        # to the registry link's source tile.  This prevents
        # bidirectional links from "coupling" the exit behaviour.
        _preserve = False
        if _link and _link.get("link_id"):
            town_state = self.game.states["town"]
            # Only preserve if the party was already in this town
            # (town_data is set from a prior visit to the same town).
            if (getattr(town_state, "town_data", None) is not None
                    and getattr(town_state, "town_data", None) is town_data):
                _preserve = True

        town_name = getattr(town_data, "name", None) or "Town"

        def _do_enter():
            town_state = self.game.states["town"]
            town_state.enter_town(town_data, pcol, prow,
                                  auto_interior=sub or None,
                                  target_pos=_target_pos,
                                  preserve_exit=_preserve)
            self.game.change_state("town")

        self.game.start_loading_screen(f"Entering {town_name}", _do_enter)

    # ── Dungeon action screen ─────────────────────────────────

    def _show_dungeon_action(self, pcol, prow):
        """Show the dungeon entry action screen instead of entering immediately."""
        visited = self.game.is_dungeon_visited(pcol, prow)
        cleared = False

        # Determine dungeon type and build info
        kd = self.game.get_key_dungeon(pcol, prow)
        quest = self.game.get_quest()
        hq = self.game.get_house_quest()

        if kd:
            if kd["status"] == "undiscovered":
                # Player hasn't accepted this quest yet — show a
                # generic name and description so quest details
                # aren't revealed prematurely.
                name = "Unknown Cave"
                desc = (
                    "A dark cave entrance leads deep underground. "
                    "The air smells of ancient stone and danger."
                )
                quest_name = None
                entry_type = "key_dungeon"
            elif kd["status"] == "completed":
                name = kd.get("name", "Key Dungeon")
                desc = kd.get("description") or (
                    "A dark cave entrance leads deep underground. "
                    "The air smells of ancient stone and danger."
                )
                cleared = True
                quest_name = f"{kd.get('key_name', 'Key')} (completed)"
                entry_type = "key_dungeon"
            else:
                name = kd.get("name", "Key Dungeon")
                # Use the dungeon's unique description if available
                desc = kd.get("description") or (
                    "A dark cave entrance leads deep underground. "
                    "The air smells of ancient stone and danger."
                )
                # Use the dungeon's unique quest objective if available
                quest_name = kd.get("quest_objective") or (
                    f"Retrieve the {kd.get('key_name', 'Key')}"
                )
                entry_type = "key_dungeon"
        elif (quest
                and pcol == quest.get("dungeon_col")
                and prow == quest.get("dungeon_row")):
            artifact = quest.get("artifact_name", "Shadow Crystal")
            name = quest.get("name", "The Shadow Crystal")
            desc = f"A foreboding passage descends into darkness. Somewhere below lies the {artifact}."
            if quest["status"] == "completed":
                cleared = True
                quest_name = f"{name} (completed)"
            else:
                quest_name = name
            entry_type = "quest"
        elif (hq
                and pcol == hq.get("dungeon_col")
                and prow == hq.get("dungeon_row")):
            name = "Elara's House"
            desc = "The old house sits quietly. The family heirloom is said to be hidden inside."
            if hq.get("status") == "completed":
                cleared = True
                quest_name = "Family Heirloom (completed)"
            else:
                quest_name = "Retrieve the Family Heirloom"
            entry_type = "house_quest"
        else:
            name = "The Depths"
            desc = "A yawning cave entrance beckons. Who knows what lurks in the darkness below."
            quest_name = None
            entry_type = "random"
            # A cleared random dungeon (TILE_DUNGEON_CLEARED with no quest)
            tile_id = self.game.tile_map.get_tile(pcol, prow)
            if tile_id == TILE_DUNGEON_CLEARED:
                cleared = True

        self.dungeon_action_info = {
            "name": name,
            "description": desc,
            "visited": visited,
            "cleared": cleared,
            "quest_name": quest_name,
        }
        self.dungeon_action_entry_args = {
            "type": entry_type,
            "col": pcol,
            "row": prow,
        }
        self.dungeon_action_cursor = 0
        self.dungeon_action_active = True

    def _handle_dungeon_action_input(self, event):
        """Handle input for the dungeon entry action screen."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.dungeon_action_cursor = (self.dungeon_action_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.dungeon_action_cursor = (self.dungeon_action_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.dungeon_action_cursor == 0:
                self._enter_dungeon_confirmed()
            else:
                self.dungeon_action_active = False
                self._exit_grace = True
        elif event.key == pygame.K_ESCAPE:
            self.dungeon_action_active = False
            self._exit_grace = True

    def _enter_dungeon_confirmed(self):
        """Execute the actual dungeon entry after the player confirms.

        Dungeons are persistent — once generated, their state (explored
        tiles, opened chests, triggered traps, killed monsters) is kept
        in ``game.dungeon_cache`` and reused on re-entry.
        """
        args = self.dungeon_action_entry_args
        if not args:
            self.dungeon_action_active = False
            return

        pcol, prow = args["col"], args["row"]
        entry_type = args["type"]
        dungeon_name = self.dungeon_action_info.get("name", "Dungeon")

        # For module dungeons, handle specially (they have their own
        # state-change logic inside _enter_module_dungeon).
        if entry_type == "module_dungeon":
            dungeon_def = args.get("dungeon_def")
            if dungeon_def:
                self.dungeon_action_active = False

                def _do_enter_module():
                    self._enter_module_dungeon(dungeon_def, pcol, prow)

                self.game.start_loading_screen(
                    f"Entering {dungeon_name}", _do_enter_module)
            else:
                self.dungeon_action_active = False
            return

        def _do_enter():
            dungeon_state = self.game.states["dungeon"]
            cache = self.game.dungeon_cache

            # Mark as visited
            self.game.mark_dungeon_visited(pcol, prow)

            if entry_type == "key_dungeon":
                kd = self.game.get_key_dungeon(pcol, prow)
                if kd:
                    if kd["status"] == "undiscovered":
                        for i, level in enumerate(kd["levels"]):
                            level.name = f"Unknown Cave - Floor {i + 1}"
                    dungeon_state.enter_quest_dungeon(kd["levels"], pcol, prow)
            elif entry_type == "quest":
                quest = self.game.get_quest()
                if quest:
                    dungeon_state.enter_quest_dungeon(quest["levels"], pcol, prow)
            elif entry_type == "house_quest":
                hq = self.game.get_house_quest()
                if hq:
                    dungeon_state.enter_quest_dungeon(hq["levels"], pcol, prow)
            else:
                cached = cache.get((pcol, prow))
                if cached:
                    dungeon_data = cached[0]
                else:
                    dungeon_data = generate_dungeon("The Depths")
                    cache[(pcol, prow)] = [dungeon_data]
                dungeon_state.enter_dungeon(dungeon_data, pcol, prow)

            self.game.change_state("dungeon")

        self.dungeon_action_active = False
        self.game.start_loading_screen(f"Entering {dungeon_name}", _do_enter)

    # ── Building action screen ─────────────────────────────────

    def _handle_building_action_input(self, event):
        """Handle input for the building entry action screen."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.building_action_cursor = (self.building_action_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.building_action_cursor = (self.building_action_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.building_action_cursor == 0:
                self._enter_building_confirmed()
            else:
                self.building_action_active = False
                self._exit_grace = True
        elif event.key == pygame.K_ESCAPE:
            self.building_action_active = False
            self._exit_grace = True

    def _enter_building_confirmed(self):
        """Execute the actual building entry after the player confirms."""
        self.building_action_active = False
        args = self.building_action_entry_args
        self.building_action_entry_args = {}
        if not args:
            return

        building_def = args["building_def"]
        pcol, prow = args["col"], args["row"]

        # Re-read building from disk to pick up any editor changes
        bname = building_def.get("name", "")
        fresh = self._find_module_building_by_name(bname)
        if fresh is not None:
            building_def = fresh

        spaces = building_def.get("spaces", [])
        if not spaces:
            return

        tmap = self.game.tile_map
        src_tmap = self._stashed_overworld_tile_map or tmap
        interiors = getattr(src_tmap, "overworld_interiors", [])

        # Always update building spaces with the latest data from
        # buildings.json so edits (e.g. adding a door) take effect
        # without needing a full restart.
        for sp in spaces:
            sp_name = sp.get("name", "")
            if not sp_name:
                continue
            new_entry = {
                "name": sp_name,
                "width": sp.get("width", 20),
                "height": sp.get("height", 20),
                "entry_col": sp.get("entry_col", 0),
                "entry_row": sp.get("entry_row", 0),
                "tiles": sp.get("tiles", {}),
                "npcs": sp.get("npcs", []),
            }
            # Replace existing entry or append new one
            replaced = False
            for i, existing in enumerate(interiors):
                if existing.get("name") == sp_name:
                    interiors[i] = new_entry
                    replaced = True
                    break
            if not replaced:
                interiors.append(new_entry)
        src_tmap.overworld_interiors = interiors
        # Use the sub_interior if specified, otherwise default to
        # the first space in the building.
        sub = args.get("sub_interior", "")
        if sub:
            # Find the matching space by name
            entrance_name = sub
        else:
            entrance_name = spaces[0].get("name",
                                          building_def.get("name", ""))
        bldg_name = building_def.get("name", "")
        self._enter_overworld_interior(entrance_name, pcol, prow,
                                       building_name=bldg_name)

    def _activate_house_quest(self):
        """Activate the house quest when the party speaks to Elara."""
        hq = self.game.get_house_quest()
        if hq and hq["status"] != "not_started":
            # Quest already active or completed
            if hq["status"] == "completed":
                self.show_message("Elara: Thank you again for returning my heirloom!", 3000)
            elif hq["status"] == "artifact_found":
                self.show_message("Elara: You found it! Thank you so much!", 3000)
                self._complete_house_quest()
            else:
                self.show_message("Elara: Please, my heirloom is still in the basement!", 3000)
            return

        # Generate the house dungeon
        levels = generate_house_dungeon()
        house_col, house_row = 7, 10  # fixed house dungeon location

        # Store house quest state
        self.game.set_house_quest({
            "name": "Family Heirloom",
            "status": "active",
            "dungeon_col": house_col,
            "dungeon_row": house_row,
            "levels": levels,
            "current_level": 0,
            "artifact_name": "Family Heirloom",
        })

        self.show_message("Elara: Thank you! The house is just north of here. Be careful!", 4000)
        self.game.game_log.append("Quest accepted: Retrieve the Family Heirloom from Elara's house.")

    def _complete_house_quest(self):
        """Complete the house quest: remove heirloom, give reward."""
        party = self.game.party

        # Remove the heirloom
        party.inv_remove("Family Heirloom")

        # Give gold reward
        reward_gold = 100
        party.gold += reward_gold

        # Give XP to all alive members
        for member in party.alive_members():
            member.exp += 30

        self.game.get_house_quest()["status"] = "completed"
        self.game.game_log.append(
            f"Quest complete! Elara rewards the party with {reward_gold} gold."
        )

    # ── Chest loot ─────────────────────────────────────────────

    def _open_chest(self):
        """Roll random loot from a chest: gold, an item, or both."""
        from src import data_registry as DR
        self.game.sfx.play("treasure")
        gold = random.randint(5, 30)
        self.game.party.gold += gold

        loot_table = DR.chest_loot()
        total_weight = sum(w for _, w in loot_table)
        roll = random.randint(1, total_weight)
        cumulative = 0
        chosen_item = None
        for item, weight in loot_table:
            cumulative += weight
            if roll <= cumulative:
                chosen_item = item
                break

        if chosen_item:
            self.game.party.inv_add(chosen_item)
            self.show_message(
                f"The party opened a treasure chest and found {gold} gold and {chosen_item}.", 2500)
        else:
            self.show_message(
                f"The party opened a treasure chest and found {gold} gold.", 2000)

    def update(self, dt):
        """Update timers."""
        dt_ms = dt * 1000  # convert seconds to ms
        if self.message_timer > 0:
            self.message_timer -= dt_ms
            if self.message_timer <= 0:
                self.message = ""
                self.message_timer = 0

        if self.move_cooldown > 0:
            self.move_cooldown -= dt_ms
            if self.move_cooldown < 0:
                self.move_cooldown = 0

        # Tick use-item animation
        if self.use_item_anim and self.use_item_anim["timer"] > 0:
            self.use_item_anim["timer"] -= dt_ms
            if self.use_item_anim["timer"] <= 0:
                self.use_item_anim = None

        # Tick level-up animations
        self._update_level_up_queue(dt_ms)

        # Push spell animation — lives as long as the repel effect is active
        if self.push_spell_anim:
            anim = self.push_spell_anim
            anim["elapsed_ms"] += dt_ms
            if anim["burst_timer"] > 0:
                anim["burst_timer"] -= dt_ms
                if anim["burst_timer"] < 0:
                    anim["burst_timer"] = 0
            # Clear the animation only when the repel effect is also gone
            if not self.repel_effect and anim["burst_timer"] <= 0:
                self.push_spell_anim = None

        # Unique tile discovery animation
        if self.unique_tile_timer > 0:
            self.unique_tile_timer -= dt_ms
            self.unique_tile_flash += dt * 6.0  # ~6 radians/sec for pulsing
            if self.unique_tile_timer <= 0:
                self.unique_tile_timer = 0
                self.unique_tile_text = ""
                self.unique_tile_pos = None

        # Tick quest visual effects
        if self.quest_effects:
            for fx in self.quest_effects:
                fx["timer"] -= dt_ms
            self.quest_effects = [
                fx for fx in self.quest_effects if fx["timer"] > 0]

    def draw(self, renderer):
        """Draw the overworld in Ultima III style."""
        if self.showing_party_inv:
            action_opts = self._get_party_inv_action_options() if self.party_inv_action_menu else None
            renderer.draw_party_inventory_u3(
                self.game.party, self.party_inv_cursor,
                self.party_inv_choosing, self.party_inv_member,
                self.party_inv_action_menu, self.party_inv_action_cursor,
                action_options=action_opts,
                choosing_effect=self.choosing_effect,
                effect_list=self.effect_list,
                effect_cursor=self.effect_cursor,
                showing_spell_list=self.showing_spell_list,
                spell_list_items=self.spell_list_items,
                spell_list_cursor=self.spell_list_cursor,
                choosing_heal_target=self.choosing_heal_target,
                heal_target_cursor=self.heal_target_cursor,
                showing_brew_list=self.showing_brew_list,
                brew_list_items=self.brew_list_items,
                brew_list_cursor=self.brew_list_cursor,
                brew_result_msg=self.brew_result_msg,
                tinker_available=self._can_tinker(),
                applying_poison_step=self.applying_poison_step,
                applying_poison_cursor=self.applying_poison_cursor,
                applying_poison_item=self.applying_poison_item,
                applying_poison_member=getattr(self, '_applying_poison_member', None))
            if self.use_item_anim:
                renderer.draw_use_item_animation(self.game.party, self.use_item_anim)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item, getattr(self, 'examining_durability', None))
            return
        if self.showing_char_detail is not None:
            idx = self.showing_char_detail
            member = self.game.party.members[idx]
            action_opts = self._get_action_options(member) if self.char_action_menu else None
            renderer.draw_character_sheet_u3(
                member, idx, self.char_sheet_cursor,
                self.char_action_menu, self.char_action_cursor,
                action_options=action_opts)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item, getattr(self, 'examining_durability', None))
            return
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        # Sync quest status onto NPC objects for renderer
        if self._in_overworld_interior:
            # Inside a building: only show building interior NPCs,
            # not overworld quest NPCs (whose coordinates are for the
            # overworld map and would appear at wrong positions).
            ow_npcs = list(self._building_interior_npcs)
        else:
            ow_npcs = getattr(self.game, "overworld_quest_npcs", [])
        mq_states = getattr(self.game, "module_quest_states", {})
        for npc in ow_npcs:
            mqn = getattr(npc, "_module_quest_name", "")
            npc._quest_status = mq_states.get(mqn, {}).get(
                "status", "available")

        renderer.draw_overworld_u3(
            self.game.party,
            self.game.tile_map,
            message=self.message,
            overworld_monsters=self.overworld_monsters,
            unique_text=self.unique_tile_text,
            unique_flash=self.unique_tile_flash,
            unique_pos=self.unique_tile_pos,
            push_anim=self.push_spell_anim,
            repel_effect=self.repel_effect,
            darkness_active=getattr(self.game, "darkness_active", False),
            overworld_npcs=ow_npcs,
            quest_effects=self.quest_effects,
            interior_darkness=getattr(self, "_in_overworld_interior", False),
        )
        # ── Overworld NPC quest choice overlay ──
        if self.ow_quest_choice_active:
            renderer.draw_ow_quest_choice(
                self.ow_quest_choices, self.ow_quest_choice_cursor)
        if self.town_action_active:
            renderer.draw_town_action_screen(
                self.town_action_info, self.town_action_cursor)
        if self.dungeon_action_active:
            renderer.draw_dungeon_action_screen(
                self.dungeon_action_info, self.dungeon_action_cursor)
        if self.building_action_active:
            renderer.draw_building_action_screen(
                self.building_action_info, self.building_action_cursor)
        if self.level_up_queue:
            renderer.draw_level_up_animation(self.level_up_queue[0])
        if self.showing_help:
            renderer.draw_overworld_help_overlay()
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
