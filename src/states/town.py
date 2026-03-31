"""
Town state - exploring a town interior.

The party walks around inside a town, talks to NPCs by bumping into them,
and can leave through the exit gate to return to the overworld.
"""

import random

import pygame

from src.states.base_state import BaseState
from src.states.inventory_mixin import InventoryMixin
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_EXIT, TILE_DUNGEON,
    TILE_GRASS, TILE_FOREST, TILE_PATH, TILE_WATER, TILE_MOUNTAIN,
    TILE_TOWN, TILE_MACHINE,
    GUARDIAN_LEASH, GUARDIAN_INTERCEPT_RANGE_INTERIOR, NPC_WANDER_RANGE,
)
from src.dungeon_generator import generate_innkeeper_quest_dungeon


class QuestCompleteEffect:
    """Multi-phase celebration animation when a quest is completed.

    Phase 1 (0.0 - 1.5s): The Shadow Crystal rises and glows at center screen.
    Phase 2 (1.5 - 3.0s): Crystal shatters into sparks, gold coins rain down.
    Phase 3 (3.0 - 5.0s): "QUEST COMPLETE" banner fades in with fanfare sparkles.
    """
    DURATION = 5.0

    def __init__(self, reward_gold, item_name="Shadow Crystal"):
        self.timer = 0.0
        self.alive = True
        self.reward_gold = reward_gold
        self.item_name = item_name

        # Pre-generate particle data for the shattering crystal
        self.shards = []
        for _ in range(24):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(60, 200)
            self.shards.append({
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 80,  # upward bias
                "color": random.choice([
                    (100, 60, 200), (140, 80, 255), (80, 40, 180),
                    (200, 160, 255), (60, 20, 140),
                ]),
                "size": random.randint(2, 5),
            })

        # Pre-generate gold coin rain positions
        self.coins = []
        for _ in range(16):
            self.coins.append({
                "x": random.randint(100, 700),
                "delay": random.uniform(0.0, 1.0),
                "speed": random.uniform(80, 160),
            })

        # Pre-generate sparkles for the banner phase
        self.sparkles = []
        for _ in range(20):
            self.sparkles.append({
                "x": random.randint(50, 750),
                "y": random.randint(50, 650),
                "phase": random.uniform(0, 2 * math.pi),
                "speed": random.uniform(2, 5),
            })

    def update(self, dt):
        self.timer += dt
        if self.timer >= self.DURATION:
            self.alive = False

    @property
    def progress(self):
        return min(1.0, self.timer / self.DURATION)


class TempleHealEffect:
    """Celestial animation when a temple service is performed.

    Golden/white particles rise and radiate outward from the screen centre
    while a holy glow expands and fades over ~2.5 seconds.
    """
    DURATION = 2.5

    def __init__(self):
        self.timer = 0.0
        self.alive = True
        # Pre-generate ascending particle data
        self.particles = []
        for _ in range(30):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(40, 120)
            self.particles.append({
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 50,  # upward bias
                "color": random.choice([
                    (255, 255, 255),    # white
                    (255, 220, 100),    # gold
                    (200, 255, 200),    # pale green
                    (100, 200, 255),    # pale blue
                ]),
                "lifetime": random.uniform(1.0, 2.4),
            })

    def update(self, dt):
        self.timer += dt
        if self.timer >= self.DURATION:
            self.alive = False


class MachineShutdownEffect:
    """Multi-phase animation when the gnome machine is shut down.

    Phase 1 (0.0 – 1.5s): Machine overload — screen shakes, red/orange pulsing,
                            energy arcs radiate from center.
    Phase 2 (1.5 – 3.0s): Machine dies — shockwave ring expands, colour cools
                            from red to blue, arcs fade.
    Phase 3 (3.0 – 4.5s): Light returns — golden light expands from center,
                            darkness alpha fades to zero.
    Phase 4 (4.5 – 6.0s): Victory banner — "QUEST COMPLETE" with reward text
                            and sparkles.
    """
    DURATION = 6.0

    def __init__(self):
        self.timer = 0.0
        self.alive = True

        # Pre-generate energy arc data (Phase 1-2)
        self.arcs = []
        for _ in range(12):
            angle = random.uniform(0, 2 * math.pi)
            length = random.uniform(80, 220)
            self.arcs.append({
                "angle": angle,
                "length": length,
                "width": random.randint(1, 3),
                "phase_offset": random.uniform(0, 2 * math.pi),
                "speed": random.uniform(3, 8),
            })

        # Pre-generate shockwave sparks (Phase 2)
        self.sparks = []
        for _ in range(30):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(100, 300)
            self.sparks.append({
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "color": random.choice([
                    (100, 160, 255), (140, 200, 255), (200, 220, 255),
                    (80, 120, 220), (255, 255, 255),
                ]),
                "size": random.randint(2, 4),
                "lifetime": random.uniform(0.8, 1.4),
            })

        # Pre-generate light rays (Phase 3)
        self.rays = []
        for _ in range(16):
            angle = random.uniform(0, 2 * math.pi)
            self.rays.append({
                "angle": angle,
                "width": random.uniform(0.04, 0.12),
                "alpha_mult": random.uniform(0.6, 1.0),
            })

        # Pre-generate banner sparkles (Phase 4)
        self.sparkles = []
        for _ in range(20):
            self.sparkles.append({
                "x": random.randint(50, 750),
                "y": random.randint(50, 650),
                "phase": random.uniform(0, 2 * math.pi),
                "speed": random.uniform(2, 5),
            })

        # Pre-generate screen shake offsets (Phase 1)
        self.shake_offsets = []
        for _ in range(60):
            self.shake_offsets.append((
                random.randint(-6, 6),
                random.randint(-6, 6),
            ))

    def update(self, dt):
        self.timer += dt
        if self.timer >= self.DURATION:
            self.alive = False

    @property
    def progress(self):
        return min(1.0, self.timer / self.DURATION)

    @property
    def shake_offset(self):
        """Return current screen shake (x, y) offset — only active in Phase 1."""
        if self.timer > 1.5:
            return (0, 0)
        intensity = 1.0 - self.timer / 1.5  # fade out shake
        idx = int(self.timer * 40) % len(self.shake_offsets)
        sx, sy = self.shake_offsets[idx]
        return (int(sx * intensity), int(sy * intensity))


class TownState(InventoryMixin, BaseState):
    """Handles exploration inside a town."""

    def __init__(self, game):
        super().__init__(game)
        self.town_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        self.npc_dialogue_active = False
        self.npc_speaking = None
        self._init_inventory_state()

        # Quest dialogue
        self.quest_choice_active = False
        self.quest_choice_cursor = 0
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0

        # Shop screen
        self.showing_shop = False
        self.shop_mode = "buy"      # "buy" or "sell"
        self.shop_cursor = 0        # cursor in buy list
        self.shop_sell_cursor = 0   # cursor in sell list
        self.shop_message = ""
        self.shop_message_timer = 0

        # Quest completion celebration effect
        self.quest_complete_effect = None
        # Module quest visual effects
        self.quest_effects = []
        # Machine shutdown animation (Keys of Shadow victory)
        self.machine_shutdown_effect = None
        self._pending_victory = False  # deferred until dialogue dismissed

        # Temple service menu
        self.showing_temple_service = False
        self.temple_service_cursor = 0   # 0=HEALING, 1=RESURRECTION
        self.temple_npc = None
        self.temple_heal_effect = None
        self.temple_message = ""
        self.temple_message_timer = 0

        # Pickpocket targeting mode
        self.pickpocket_targeting = False
        self.pickpocket_targets = []   # list of adjacent NPCs
        self.pickpocket_cursor = 0     # index into pickpocket_targets

        # ── Help overlay ──
        self.showing_help = False

        # We'll save the overworld position so we can restore it on exit
        self.overworld_col = 0
        self.overworld_row = 0
        self._auto_interior = None  # set by enter_town for direct links

    def enter_town(self, town_data, overworld_col, overworld_row,
                   auto_interior=None):
        """
        Set up the town state with town-specific data.
        Called before change_state so the town knows what to load.

        If *auto_interior* is a string, the town will immediately
        transition into that named interior after loading (used when
        the overworld links directly to a sub-interior like a tunnel).
        """
        self.town_data = town_data
        self.overworld_col = overworld_col
        self.overworld_row = overworld_row
        self._auto_interior = auto_interior

    def enter(self):
        """Called when this state becomes active."""
        self._apply_pending_combat_rewards()

        # If returning from interior combat, stay in place and check kills
        if getattr(self, "_returning_from_combat", False):
            self._returning_from_combat = False
            # Remove the killed monster NPC
            dead_npc = getattr(self, "_combat_monster_npc", None)
            if dead_npc and dead_npc in self.town_data.npcs:
                self.town_data.npcs.remove(dead_npc)
            self._combat_monster_npc = None
            # Check quest kill progress
            quest_msg = self._check_quest_monster_kills()
            if quest_msg:
                self.show_message(quest_msg, 4000)
            # Update camera (still in the interior)
            self.game.camera.map_width = self.town_data.tile_map.width
            self.game.camera.map_height = self.town_data.tile_map.height
            self.game.camera.update(
                self.game.party.col, self.game.party.row)
            return

        if self.town_data:
            town_name = self.town_data.name
            self.show_message(f"Welcome to {town_name}!", 2500)
            # Move party to town entry point
            self.game.party.col = self.town_data.entry_col
            self.game.party.row = self.town_data.entry_row
            # Update camera for the town map
            self.game.camera.map_width = self.town_data.tile_map.width
            self.game.camera.map_height = self.town_data.tile_map.height
            self.game.camera.update(self.game.party.col, self.game.party.row)
            self._refresh_quest_highlights()
            # Spawn quest monsters registered for this town
            self._spawn_town_quest_monsters()

            # If the overworld linked directly to a sub-interior
            # (e.g. a specific tunnel), auto-enter it now.
            auto = getattr(self, "_auto_interior", None)
            if auto:
                self._auto_interior = None
                self._enter_interior(auto,
                                     self.game.party.col,
                                     self.game.party.row)

    def _check_quest_monster_kills(self):
        """After returning from combat in an interior, check if the killed
        monster was a quest target and update step progress.

        Returns a message string if a step or quest was completed, else None.
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

    def _refresh_quest_highlights(self):
        """Update quest_highlight on all NPCs based on current quest state."""
        if not self.town_data:
            return
        quest = self.game.get_quest()
        kd_map = getattr(self.game, "key_dungeons", {})
        inserted = getattr(self.game, "keys_inserted", 0)
        total = len(kd_map) if kd_map else 0
        gnome_accepted = getattr(self.game, "_gnome_quest_accepted", False)

        for npc in self.town_data.npcs:
            npc.quest_highlight = False

            if npc.npc_type == "innkeeper":
                # Highlight when offering a quest or waiting for resolution
                inn_quests = getattr(npc, "innkeeper_quests", False)
                if quest is None and npc.quest_dialogue:
                    npc.quest_highlight = True
                elif quest and quest.get("status") in (
                        "active", "artifact_found"):
                    npc.quest_highlight = True
                elif quest and quest.get("status") == "completed" and inn_quests:
                    # Repeatable innkeeper — highlight to signal new quest ready
                    npc.quest_highlight = True

            elif npc.npc_type == "gnome":
                # Highlight when quest not accepted, or keys still needed
                gnome_total = sum(
                    1 for kd in kd_map.values()
                    if kd.get("quest_type") == "gnome_machine")
                # Keys of Shadow: all quests count
                if total > 0 and gnome_total == 0:
                    gnome_total = total  # KoS compat
                if npc.quest_dialogue and not gnome_accepted:
                    npc.quest_highlight = True
                elif kd_map and inserted < gnome_total:
                    npc.quest_highlight = True

            elif npc.npc_type == "quest_giver":
                # Highlight when this NPC's quest is undiscovered or
                # the quest is active/artifact_found
                dk_str = getattr(npc, "dungeon_key_str", "")
                if dk_str:
                    parts = dk_str.split(",")
                    if len(parts) == 2:
                        kd = kd_map.get((int(parts[0]), int(parts[1])))
                        if kd and kd.get("status") in (
                                "undiscovered", "active", "artifact_found"):
                            npc.quest_highlight = True

            elif npc.npc_type == "module_quest_giver":
                # Highlight when quest is available, active, or completed
                # (waiting for turn-in). Stop highlighting after turned in.
                mqname = getattr(npc, "_module_quest_name", "")
                mq_states = getattr(self.game, "module_quest_states", {})
                mq_status = mq_states.get(mqname, {}).get(
                    "status", "available")
                if mq_status in ("available", "active", "completed"):
                    npc.quest_highlight = True

            elif npc.npc_type == "elder":
                # Highlight only when the elder has something actionable:
                # quest turn-ins or active quests to give hints about.
                # Undiscovered quests are the quest_giver NPCs' job.
                elder_kds = [kd for kd in kd_map.values()
                             if kd.get("quest_type") != "gnome_machine"]
                has_turnin = any(
                    kd.get("status") == "artifact_found"
                    for kd in elder_kds)
                has_active = any(
                    kd.get("status") == "active"
                    for kd in elder_kds)
                if has_turnin or has_active:
                    npc.quest_highlight = True

    def exit(self):
        """Called when leaving this state — reset all transient UI state."""
        self.npc_dialogue_active = False
        self.npc_speaking = None
        self.message = ""
        self.message_timer = 0
        self.pickpocket_targeting = False
        self.pickpocket_targets = []
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0
        self.showing_shop = False
        self.showing_temple_service = False
        self.showing_log = False
        self.showing_party = False
        self.showing_party_inv = False
        self.showing_char_detail = None

    def handle_input(self, events, keys_pressed):
        """Handle movement and NPC interaction."""
        # Block all input during quest celebration or machine shutdown
        if self.quest_complete_effect or self.machine_shutdown_effect:
            return

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

                # ── Temple service menu input ──
                if self.showing_temple_service:
                    self._handle_temple_service_input(event)
                    return

                # ── Shop screen input ──
                if self.showing_shop:
                    self._handle_shop_input(event)
                    return

                # ── Pickpocket targeting input ──
                if self.pickpocket_targeting:
                    self._handle_pickpocket_targeting_input(event)
                    return

                # ── Party inventory screen input ──
                if self.showing_party_inv:
                    self._handle_party_inv_input(event)
                    return

                # ── Action menu input ──
                if self.char_action_menu and self.showing_char_detail is not None:
                    self._handle_char_action_input(event)
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
                    if not self.npc_dialogue_active:
                        self.showing_party_inv = True
                        self.party_inv_cursor = 0
                        self.party_inv_choosing = False
                        self.party_inv_member = 0
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
                if event.key == pygame.K_l:
                    if not self.npc_dialogue_active:
                        self.showing_log = True
                        self.log_scroll = 0
                    return
                if event.key == pygame.K_h:
                    if not self.npc_dialogue_active:
                        self.showing_help = True
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
                    if self.npc_dialogue_active:
                        # Dismiss dialogue (and any quest choice state)
                        self.npc_dialogue_active = False
                        self.npc_speaking = None
                        self.message = ""
                        self.message_timer = 0
                        self.quest_choice_active = False
                        self.quest_choices = []
                        self.quest_dialogue_lines = []
                        self.quest_dialogue_index = 0
                    else:
                        # Leave town
                        self._exit_town()
                        return

                # Quest choice navigation
                if self.quest_choice_active and self.quest_choices:
                    if event.key == pygame.K_UP:
                        self.quest_choice_cursor = (self.quest_choice_cursor - 1) % len(self.quest_choices)
                        return
                    elif event.key == pygame.K_DOWN:
                        self.quest_choice_cursor = (self.quest_choice_cursor + 1) % len(self.quest_choices)
                        return
                    elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self._handle_quest_choice()
                        return
                    # Block other keys while choices are shown
                    return

                # Space/Enter to advance NPC dialogue or interact
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    if self.npc_dialogue_active:
                        # Advance dialogue
                        self._advance_dialogue()
                        return

        # If showing party screen, character detail, inventory, dialogue, or shop, block movement
        if self.showing_party or self.showing_char_detail is not None or self.showing_party_inv:
            return
        if self.showing_shop or self.showing_temple_service:
            return
        if self.npc_dialogue_active:
            return

        # Movement
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
            self._try_move_or_interact(dcol, drow)

    def _try_move_or_interact(self, dcol, drow):
        """Move the party, or interact with an NPC if one is in the way."""
        party = self.game.party
        target_col = party.col + dcol
        target_row = party.row + drow

        # Check for NPC at target
        npc = self.town_data.get_npc_at(target_col, target_row)
        if npc:
            if npc.npc_type == "quest_monster":
                self._start_quest_monster_combat(npc)
                self.move_cooldown = MOVE_REPEAT_DELAY
                return
            if npc.npc_type == "quest_item":
                self._collect_quest_item(npc)
                self.move_cooldown = MOVE_REPEAT_DELAY
                return
            self._start_dialogue(npc)
            self.move_cooldown = MOVE_REPEAT_DELAY
            return

        # Check walkability on the town map
        if self.town_data.tile_map.is_walkable(target_col, target_row):
            party.col = target_col
            party.row = target_row
            self.move_cooldown = MOVE_REPEAT_DELAY
            self._check_tile_events()
            # Tick Galadriel's Light step counter
            self._tick_galadriels_light()
        else:
            # Non-walkable tile — check for tile interaction
            self._try_tile_interaction(target_col, target_row)
            self.move_cooldown = MOVE_REPEAT_DELAY

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

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        party = self.game.party

        # If inside an interior, check for "to_town" / "to_overworld" exits
        if getattr(self, "_in_interior", False):
            # Skip exit check on the first move after entering so the player
            # isn't immediately ejected when spawning on an exit tile.
            if getattr(self, "_interior_entry_grace", False):
                self._interior_entry_grace = False
            else:
                # "to_overworld" exits leave the town entirely
                ow_exits = getattr(self, "_interior_overworld_exits", set())
                if (party.col, party.row) in ow_exits:
                    # Restore town-level state before exiting so the
                    # TownData object isn't left pointing at an interior map.
                    stack = getattr(self, "_interior_stack", [])
                    if stack:
                        bottom = stack[0]
                        stack.clear()
                        self.town_data.tile_map = bottom["tile_map"]
                        self.town_data.npcs = bottom["npcs"]
                        self.town_data.interior_links = bottom["interior_links"]
                        self.town_data.overworld_exits = bottom.get(
                            "overworld_exits", set())
                    self._in_interior = False
                    self._exit_town()
                    return
                # "to_town" exits return all the way to the town level
                exit_positions = getattr(self, "_interior_exit_positions", set())
                if (party.col, party.row) in exit_positions:
                    self._exit_to_town()
                    return
            # Check for interior-to-interior links while inside
            links = getattr(self.town_data, "interior_links", {})
            interior_name = links.get((party.col, party.row))
            if interior_name:
                self._enter_interior(interior_name, party.col, party.row)
                return

        # Check for interior links first (editor-defined door → interior).
        # This must happen before tile-type checks because the linked tile
        # could be any tile type (Machine, Door, etc.).
        links = getattr(self.town_data, "interior_links", {})
        interior_name = links.get((party.col, party.row))
        if interior_name:
            self._enter_interior(interior_name, party.col, party.row)
            return

        tile_id = self.town_data.tile_map.get_tile(
            party.col, party.row
        )
        if tile_id == TILE_EXIT:
            self._exit_town()
            return
        elif tile_id == TILE_MACHINE:
            self._interact_machine()
            return

        # Check for overworld exit (custom layout "Return to Overworld")
        ow_exits = getattr(self.town_data, "overworld_exits", set())
        if (party.col, party.row) in ow_exits:
            self._exit_town()
            return

        # Check for walkable tile interactions (e.g. signs the player
        # steps onto rather than bumps into).
        self._try_tile_interaction(party.col, party.row,
                                   walkable_only=True)

    def _try_tile_interaction(self, col, row, walkable_only=False):
        """Check if a tile has an interaction defined in TILE_DEFS.

        Called when the player bumps into a non-walkable tile, or when
        they step onto a walkable tile that carries an interaction
        (e.g. a sign).

        When *walkable_only* is True only interactions on walkable
        tiles fire (used by _check_tile_events to avoid duplicate
        triggers for non-walkable tiles).
        """
        from src.settings import TILE_DEFS
        tile_id = self.town_data.tile_map.get_tile(col, row)
        tdef = TILE_DEFS.get(tile_id)
        if not tdef:
            return

        # When called from _check_tile_events (walkable_only=True)
        # skip non-walkable tiles — those are handled by the bump path.
        if walkable_only and not tdef.get("walkable", False):
            return

        itype = tdef.get("interaction_type", "")
        if not itype or itype == "none":
            return
        idata = tdef.get("interaction_data", "")

        if itype == "shop":
            self.showing_shop = True
            self.shop_mode = "buy"
            self.shop_cursor = 0
            self.shop_sell_cursor = 0
            self.shop_message = ""
            self.shop_message_timer = 0
            self.shop_type = idata or "general"
        elif itype == "sign":
            if idata:
                self.show_message(idata, 4000)

    def _enter_interior(self, interior_name, door_col, door_row):
        """Transition into a building interior."""
        # If the target interior is already in the stack, unwind back to it
        # instead of creating a new nested instance (e.g. Interior 3 linking
        # back to Interior 2 should return, not nest deeper).
        stack = getattr(self, "_interior_stack", [])
        for i in range(len(stack) - 1, -1, -1):
            if stack[i].get("name") == interior_name:
                # Unwind: pop everything above that level, then pop the
                # target itself to restore its state.
                while len(stack) > i + 1:
                    stack.pop()
                prev = stack.pop()
                self.town_data.tile_map = prev["tile_map"]
                self.town_data.npcs = prev["npcs"]
                self.town_data.interior_links = prev["interior_links"]
                self.town_data.overworld_exits = prev.get(
                    "overworld_exits", set())
                self.game.party.col = prev["col"]
                self.game.party.row = prev["row"]
                self._interior_exit_positions = prev.get(
                    "exit_positions", set())
                self._interior_overworld_exits = prev.get(
                    "overworld_exit_positions", set())
                self._interior_name = prev.get("name", "")
                if not stack:
                    self._in_interior = False
                self.game.camera.map_width = self.town_data.tile_map.width
                self.game.camera.map_height = self.town_data.tile_map.height
                self.game.camera.update(
                    self.game.party.col, self.game.party.row)
                self.show_message(
                    f"Returning to {interior_name}...", 1000)
                return

        # First check custom interiors stored on the TownData (from the
        # module's towns.json enclosures).  Fall back to the global
        # town_templates.json for procedurally generated towns.
        interior = None
        custom_interiors = getattr(self.town_data, "interiors", [])
        for entry in custom_interiors:
            if entry.get("name") == interior_name:
                interior = entry
                break
        if interior is None:
            import json, os
            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data", "town_templates.json")
            try:
                with open(path, "r") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                self.show_message("The door is locked.", 1500)
                return
            for entry in data.get("interiors", []):
                if entry.get("name") == interior_name:
                    interior = entry
                    break
        if not interior or not interior.get("tiles"):
            self.show_message("The door is locked.", 1500)
            return

        # Remember the name of the interior we're leaving so we can find
        # the back-link tile in the destination and spawn near it.
        source_interior_name = getattr(self, "_interior_name", "")

        # Push current state onto the interior stack so we can return
        if not hasattr(self, "_interior_stack"):
            self._interior_stack = []
        self._interior_stack.append({
            "col": door_col,
            "row": door_row,
            "tile_map": self.town_data.tile_map,
            "npcs": self.town_data.npcs,
            "interior_links": getattr(self.town_data, "interior_links", {}),
            "overworld_exits": getattr(self.town_data, "overworld_exits", set()),
            "exit_positions": getattr(self, "_interior_exit_positions", set()),
            "overworld_exit_positions": getattr(self, "_interior_overworld_exits", set()),
            "name": getattr(self, "_interior_name", ""),
        })
        self._interior_name = interior_name
        self._in_interior = True
        self._interior_entry_grace = True  # skip first exit check

        # Build a tile map from the interior grid
        from src.tile_map import TileMap
        from src.settings import TILE_VOID
        iw = interior.get("width", 14)
        ih = interior.get("height", 15)
        imap = TileMap(iw, ih, default_tile=TILE_VOID, oob_tile=TILE_VOID)
        # Apply the painted tiles (unpainted stays as black void)
        for pos_key, td in interior.get("tiles", {}).items():
            parts = pos_key.split(",")
            c, r = int(parts[0]), int(parts[1])
            tid = td.get("tile_id")
            if tid is not None and 0 <= c < iw and 0 <= r < ih:
                imap.set_tile(c, r, tid)
                # Store sprite path so runtime rendering matches the editor
                path = td.get("path")
                if path:
                    imap.sprite_overrides[(c, r)] = path

        self.town_data.tile_map = imap

        # ── Build NPCs defined in the interior data ──
        self.town_data.npcs = self._build_interior_npcs(interior, imap)

        # ── Spawn quest collect items first so guardians can anchor to them ──
        self._spawn_interior_quest_collect_items(interior_name, imap)
        self._spawn_interior_quest_monsters(interior_name, imap)

        # Collect exit positions and interior-to-interior links from tiles.
        # Also track which tile links back to the source interior so we can
        # spawn the party near the correct door.
        self._interior_exit_positions = set()
        self._interior_overworld_exits = set()
        interior_links = {}
        entry_placed = False
        first_walkable = None
        exit_positions = []
        back_link_pos = None  # tile that links back to source interior
        source_name = source_interior_name
        for pos_key, td in interior.get("tiles", {}).items():
            parts = pos_key.split(",")
            c, r = int(parts[0]), int(parts[1])
            if td.get("to_town"):
                self._interior_exit_positions.add((c, r))
                exit_positions.append((c, r))
            if td.get("to_overworld"):
                self._interior_overworld_exits.add((c, r))
                exit_positions.append((c, r))
            if td.get("interior"):
                interior_links[(c, r)] = td["interior"]
                # If this tile links back to the source interior we came
                # from, prefer spawning near it.
                if source_name and td["interior"] == source_name:
                    back_link_pos = (c, r)
            # Track any walkable tile as fallback spawn point
            tid = td.get("tile_id")
            if first_walkable is None and tid is not None:
                from src.settings import TILE_DEFS
                tdef = TILE_DEFS.get(tid, {})
                if tdef.get("walkable", False):
                    first_walkable = (c, r)

        # Place the party directly on the entry door tile.
        # Priority:
        #   1. The tile linking back to the source interior we came from
        #   2. The first to_town exit (coming from town level)
        #   3. Any exit position
        #   4. First walkable tile
        #   5. Center of grid
        # The entry grace flag prevents immediate ejection.
        spawn = (back_link_pos
                 or (exit_positions[0] if exit_positions else None)
                 or first_walkable
                 or (iw // 2, ih // 2))
        self.game.party.col = spawn[0]
        self.game.party.row = spawn[1]

        self.town_data.interior_links = interior_links
        self.town_data.overworld_exits = set()

        # Update camera
        self.game.camera.map_width = iw
        self.game.camera.map_height = ih
        self.game.camera.update(self.game.party.col, self.game.party.row)
        self.show_message(f"Entering {interior_name}...", 1500)

    def _build_interior_npcs(self, interior_def, imap):
        """Create NPC objects from an interior's ``npcs`` list.

        Works the same way as the town-level NPC builder in
        ``game._build_town_from_towns_json`` — reads an optional
        ``"npcs"`` array from the interior definition and returns
        a list of :class:`NPC` objects placed on walkable tiles.
        """
        import random as _rng
        from src.town_generator import NPC

        npc_defs = interior_def.get("npcs")
        if not npc_defs:
            return []

        npcs = []
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
            npcs.append(npc)

        # Distribute NPCs so none share a tile
        iw, ih = imap.width, imap.height
        walkable = set()
        for wy in range(ih):
            for wx in range(iw):
                if imap.is_walkable(wx, wy):
                    walkable.add((wx, wy))
        # Remove exit / link tiles from candidate positions
        for pos in getattr(self, "_interior_exit_positions", set()):
            walkable.discard(pos)
        walkable.discard((self.game.party.col, self.game.party.row))

        occupied = set()
        rng = _rng.Random(
            hash(interior_def.get("name", "")) & 0xFFFFFFFF)
        for npc in npcs:
            pos = (npc.col, npc.row)
            if pos in walkable and pos not in occupied:
                occupied.add(pos)
                continue
            free = list(walkable - occupied)
            if free:
                nc, nr = rng.choice(free)
                npc.col = nc
                npc.row = nr
                npc.home_col = nc
                npc.home_row = nr
                occupied.add((nc, nr))

        return npcs

    def _spawn_town_quest_monsters(self):
        """Place quest monster NPCs in the town when the player enters.

        Reads ``game.quest_interior_monsters`` for entries registered
        under the ``"town:<town_name>"`` key and creates NPC objects
        with ``npc_type='quest_monster'`` on walkable tiles.
        """
        import random as _rng
        from src.town_generator import NPC
        from src.monster import MONSTERS

        town_name = self.town_data.name
        monsters_dict = getattr(self.game, "quest_interior_monsters", {})
        key = f"town:{town_name}"
        entries = monsters_dict.get(key, [])
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})
        tmap = self.town_data.tile_map

        # Collect walkable tiles
        walkable = []
        for wy in range(tmap.height):
            for wx in range(tmap.width):
                if tmap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = {(n.col, n.row) for n in self.town_data.npcs}
        rng = _rng.Random(hash(town_name) & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            monster_key = entry["monster_key"]
            count = entry.get("count", 1)

            # Skip if quest is no longer active
            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            # Skip if this step is already complete
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue

            monster_info = MONSTERS.get(monster_key, {})
            display_name = monster_info.get(
                "name", monster_key.replace("_", " ").title())

            for i in range(count):
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
                self.town_data.npcs.append(npc)

    def _spawn_interior_quest_monsters(self, interior_name, imap):
        """Place quest monster NPCs inside an interior when entered.

        Reads ``game.quest_interior_monsters`` for pending monsters
        registered to this interior and creates NPC objects with
        ``npc_type='quest_monster'`` on walkable tiles.
        """
        import random as _rng
        from src.town_generator import NPC
        from src.monster import MONSTERS

        monsters_dict = getattr(self.game, "quest_interior_monsters", {})
        key = f"interior:{interior_name}"
        entries = monsters_dict.get(key, [])
        if not entries:
            return

        # Check which quests are still active (don't spawn for completed)
        mq_states = getattr(self.game, "module_quest_states", {})

        # Collect walkable tiles for placement
        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = set()
        rng = _rng.Random(hash(interior_name) & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            monster_key = entry["monster_key"]
            count = entry.get("count", 1)
            is_guardian = entry.get("is_guardian", False)

            # Skip if quest is no longer active
            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            # Skip if this step is already complete
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue

            monster_info = MONSTERS.get(monster_key, {})
            display_name = monster_info.get(
                "name", monster_key.replace("_", " ").title())

            # If this is a guardian, find the quest_item NPC it protects
            # so we can place it nearby.
            anchor_pos = None
            if is_guardian:
                for existing_npc in self.town_data.npcs:
                    if (getattr(existing_npc, "npc_type", "") == "quest_item"
                            and getattr(existing_npc, "_quest_name", "") == qname
                            and getattr(existing_npc, "_quest_step_idx", -1) == step_idx):
                        anchor_pos = (existing_npc.col, existing_npc.row)
                        break

            for i in range(count):
                if anchor_pos:
                    # Place guardian near the item it protects
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
                self.town_data.npcs.append(npc)

    def _spawn_interior_quest_collect_items(self, interior_name, imap):
        """Place collectible quest items inside an interior when entered.

        Reads ``game.quest_collect_items`` for pending items registered
        to this interior and creates NPC objects with
        ``npc_type='quest_item'`` on walkable tiles.  The player can
        walk into them to pick them up.
        """
        import random as _rng
        from src.town_generator import NPC

        items_dict = getattr(self.game, "quest_collect_items", {})
        key = f"interior:{interior_name}"
        entries = items_dict.get(key, [])
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})

        # Collect walkable tiles
        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        # Exclude tiles already occupied by NPCs
        occupied = {(n.col, n.row) for n in self.town_data.npcs}
        rng = _rng.Random(hash(interior_name) & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            item_name = entry["item_name"]
            item_sprite = entry.get("item_sprite", "")

            # Skip if quest is no longer active
            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            # Skip if this step is already complete
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
            self.town_data.npcs.append(npc)

    # ── Machine interaction (Keys of Shadow) ──────────────────

    def _interact_machine(self):
        """Handle stepping on the gnome machine tile."""
        kd = getattr(self.game, "key_dungeons", {})
        if not kd:
            self.show_message("A strange machine hums ominously.", 2000)
            return

        # Filter to only gnome_machine quest keys (or all for KoS)
        mod_id = ""
        if self.game.module_manifest:
            mod_id = self.game.module_manifest.get(
                "metadata", {}).get("id", "")
        if mod_id == "keys_of_shadow":
            gnome_kds = kd
        else:
            gnome_kds = {k: v for k, v in kd.items()
                         if v.get("quest_type") == "gnome_machine"}
        if not gnome_kds:
            self.show_message("A strange machine hums ominously.", 2000)
            return

        party = self.game.party
        key_names = [d["key_name"] for d in gnome_kds.values()]
        held_keys = [k for k in key_names if party.inv_count(k) > 0]

        total = len(gnome_kds)
        inserted = self.game.get_keys_inserted()

        if held_keys:
            for key in held_keys:
                party.inv_remove(key)
                inserted = self.game.insert_key()
                # Mark the matching key dungeon as completed
                for gkd in gnome_kds.values():
                    if (gkd.get("key_name") == key
                            and gkd.get("status") != "completed"):
                        gkd["status"] = "completed"
                        break
            names = ", ".join(held_keys)
            self.show_message(
                f"Inserted {names}! ({inserted}/{total} keys placed)", 3500)
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
                f"A massive gnomish machine hums with power! "
                f"It has {total} empty keyhole slots.", 3500)

    def _trigger_victory(self):
        """Called when all keys are inserted — quest complete!"""
        # Award rewards immediately (behind the animation)
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

        # Launch the machine shutdown animation — darkness_active is
        # cleared when the animation finishes (in update()).
        self.machine_shutdown_effect = MachineShutdownEffect()
        self.game.sfx.play("quest_complete")

    # ── Pickpocket targeting ──────────────────────────────────

    def _start_pickpocket_targeting(self):
        """Close the stash and enter pickpocket target selection on the map."""
        targets = self._get_adjacent_npcs()
        if not targets:
            self.show_message("No one nearby to pickpocket!", 2000)
            return
        self.showing_party_inv = False
        self.showing_party = False
        self.pickpocket_targeting = True
        self.pickpocket_targets = targets
        self.pickpocket_cursor = 0

    def _handle_pickpocket_targeting_input(self, event):
        """Handle arrow-key target selection for pickpocketing."""
        targets = self.pickpocket_targets
        if not targets:
            self.pickpocket_targeting = False
            return

        if event.key in (pygame.K_LEFT, pygame.K_UP):
            self.pickpocket_cursor = (self.pickpocket_cursor - 1) % len(targets)
        elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
            self.pickpocket_cursor = (self.pickpocket_cursor + 1) % len(targets)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            npc = targets[self.pickpocket_cursor]
            self.pickpocket_targeting = False
            self.pickpocket_targets = []
            self._attempt_pickpocket(npc)
        elif event.key == pygame.K_ESCAPE:
            self.pickpocket_targeting = False
            self.pickpocket_targets = []

    def _set_dialogue(self, text):
        """Set the NPC dialogue message and log it to the game log."""
        self.message = text
        self.message_timer = 0
        if text:
            self.game.game_log.append(text)

    def _start_quest_monster_combat(self, npc):
        """Initiate combat with a quest monster NPC inside a town or interior."""
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
        terrain_tile = self.town_data.tile_map.get_tile(
            self.game.party.col, self.game.party.row)
        # Tag the NPC so _end_combat can remove it
        npc._is_quest_monster_npc = True
        # Store the monster NPC reference so combat can clean it up
        self._combat_monster_npc = npc
        self._returning_from_combat = True
        town_name = getattr(self.town_data, "name", "")

        # Build the correct combat_location so quest kill tracking
        # can match the step's spawn_location.  Inside a town interior
        # the format must be "interior:TownName/InteriorName"; at the
        # town level it is "town:TownName".
        in_interior = getattr(self, "_in_interior", False)
        interior_name = getattr(self, "_interior_name", "")
        if in_interior and interior_name:
            location = f"interior:{town_name}/{interior_name}"
        else:
            location = f"town:{town_name}"

        combat_state.start_combat(
            fighter, monsters,
            source_state="town",
            encounter_name=enc_name,
            map_monster_refs=[npc],
            terrain_tile=terrain_tile,
            combat_location=location)
        self.game.change_state("combat")

    def _collect_quest_item(self, npc):
        """Pick up a quest collectible item NPC."""
        from src.quest_manager import collect_quest_item
        if npc in self.town_data.npcs:
            self.town_data.npcs.remove(npc)
        msg = collect_quest_item(
            self.game,
            getattr(npc, "_quest_name", ""),
            getattr(npc, "_quest_step_idx", -1),
            npc.name)
        self.show_message(msg, 3000 if "complete" in msg.lower() else 2500)

    def _start_dialogue(self, npc):
        """Begin talking to an NPC, or open the shop for shopkeepers."""
        if npc.npc_type == "shopkeep":
            self.showing_shop = True
            self.shop_mode = "buy"
            self.shop_cursor = 0
            self.shop_sell_cursor = 0
            self.shop_message = ""
            self.shop_message_timer = 0
            self.shop_type = getattr(npc, "shop_type", "general")
            return

        # Priest — open the temple service menu
        if npc.npc_type == "priest":
            self.showing_temple_service = True
            self.temple_npc = npc
            self.temple_service_cursor = 0
            self.temple_message = ""
            self.temple_message_timer = 0
            return

        # Innkeeper quest logic
        if npc.npc_type == "innkeeper":
            quest = self.game.get_quest()
            inn_quests = getattr(npc, "innkeeper_quests", False)
            # Quest completed + innkeeper_quests — clear and offer new
            if quest and quest["status"] == "completed" and inn_quests:
                self.game.set_quest(None)
                quest = None  # fall through to "no quest" below
            # No quest yet — offer one
            if quest is None and npc.quest_dialogue:
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                if inn_quests:
                    # Generate fresh random quest dialogue
                    q = self._generate_random_innkeeper_quest(npc)
                    qt = q.get("quest_type", "retrieve")
                    if qt == "kill":
                        lines = [
                            f"I've been hearing reports of {q['kill_target']}s "
                            f"lurking in a dungeon nearby.",
                            f"Could you clear out {q['kill_count']} of them "
                            f"before they become a bigger threat?",
                        ]
                    else:
                        lines = [
                            f"I've heard about a {q['artifact_name']} hidden "
                            f"somewhere in a dangerous dungeon.",
                            "Could you seek it out and bring it back safely?",
                        ]
                    # Store pending quest data on the NPC for _accept_quest
                    npc._pending_innkeeper_quest = q
                    npc.quest_name = q["name"]
                    npc.artifact_name = q.get("artifact_name", "artifact")
                    self.quest_dialogue_lines = lines
                else:
                    self.quest_dialogue_lines = list(npc.quest_dialogue)
                self.quest_dialogue_index = 0
                self._set_dialogue(
                    f"{npc.name}: {self.quest_dialogue_lines[0]}")
                return
            # Player has the artifact / kill count — complete the quest
            if quest and quest["status"] == "artifact_found":
                q_type = quest.get("quest_type", "retrieve")
                if q_type == "kill":
                    self._complete_quest(npc)
                else:
                    # Retrieve: check that the artifact is in inventory
                    artifact = quest.get("artifact_name", "Shadow Crystal")
                    if self.game.party.inv_count(artifact) > 0:
                        self._complete_quest(npc)
                    else:
                        self.npc_dialogue_active = True
                        self.npc_speaking = npc
                        self._set_dialogue(
                            f"{npc.name}: You seem to have lost the "
                            f"{artifact}... Please find it!")
                return
            # Quest already active — hint
            if quest and quest["status"] == "active":
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                q_type = quest.get("quest_type", "retrieve")
                hint = getattr(npc, "hint_active", None)
                if not hint:
                    if q_type == "kill":
                        target = quest.get("kill_target", "monsters")
                        progress = quest.get("kill_progress", 0)
                        needed = quest.get("kill_count", 1)
                        hint = (f"Keep hunting those {target}s! "
                                f"({progress}/{needed} so far)")
                    else:
                        artifact = quest.get("artifact_name", "the artifact")
                        hint = (f"Have you found the {artifact} yet? "
                                f"It's out there somewhere...")
                self._set_dialogue(f"{npc.name}: {hint}")
                return
            # Quest completed (non-repeatable) — display item dialogue
            if quest and quest["status"] == "completed":
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                done_text = getattr(npc, "text_complete", None)
                if not done_text:
                    artifact = quest.get("artifact_name", "artifact")
                    done_text = (f"The {artifact} is safe. You've earned "
                                 f"a hero's welcome here!")
                self._set_dialogue(f"{npc.name}: {done_text}")
                return

        # Gnome (Fizzwick) — Keys of Shadow quest-giver
        if npc.npc_type == "gnome":
            kd = getattr(self.game, "key_dungeons", {})
            inserted = getattr(self.game, "keys_inserted", 0)
            # Count gnome_machine quests (or all for KoS)
            mod_id = ""
            if self.game.module_manifest:
                mod_id = self.game.module_manifest.get(
                    "metadata", {}).get("id", "")
            if mod_id == "keys_of_shadow":
                gnome_kds = kd
            else:
                gnome_kds = {k: v for k, v in kd.items()
                             if v.get("quest_type") == "gnome_machine"}
            total = len(gnome_kds) if gnome_kds else 8

            if gnome_kds:
                # Check for held keys and auto-insert them
                party = self.game.party
                key_names = [d["key_name"] for d in gnome_kds.values()]
                held_keys = [k for k in key_names if party.inv_count(k) > 0]

                if held_keys:
                    for key in held_keys:
                        party.inv_remove(key)
                        inserted = self.game.insert_key()
                        # Mark the matching key dungeon as completed
                        for gkd in gnome_kds.values():
                            if (gkd.get("key_name") == key
                                    and gkd.get("status") != "completed"):
                                gkd["status"] = "completed"
                                break
                    n = len(held_keys)
                    names = ", ".join(held_keys)
                    self._refresh_quest_highlights()
                    self.npc_dialogue_active = True
                    self.npc_speaking = npc
                    if inserted >= total:
                        self._set_dialogue(
                            f"{npc.name}: The {names}! That's the last one! "
                            f"Stand back — I'm shutting it down!")
                        # Defer the machine animation until the player
                        # dismisses this dialogue (see _advance_dialogue).
                        self._pending_victory = True
                    else:
                        self._set_dialogue(
                            f"{npc.name}: Wonderful! You found the {names}! "
                            f"That's {inserted}/{total} keys. Keep going!")
                    return

                # No keys held — give progress dialogue
                if inserted >= total:
                    self.npc_dialogue_active = True
                    self.npc_speaking = npc
                    town_nm = getattr(self.game, "town_data", None)
                    town_nm = town_nm.name if town_nm else "the realm"
                    self._set_dialogue(
                        f"{npc.name}: The quest is complete! "
                        f"I can never thank you enough. {town_nm} is saved!")
                    return
                elif inserted > 0:
                    self.npc_dialogue_active = True
                    self.npc_speaking = npc
                    remaining = total - inserted
                    self._set_dialogue(
                        f"{npc.name}: {inserted} keys inserted so far... "
                        f"{remaining} more to go! Try the next dungeon!")
                    return

            # No keys inserted yet — offer the quest or cycle dialogue
            if npc.quest_dialogue and not getattr(self.game, "_gnome_quest_accepted", False):
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self.quest_dialogue_lines = list(npc.quest_dialogue)
                self.quest_dialogue_index = 0
                self._set_dialogue(f"{npc.name}: {self.quest_dialogue_lines[0]}")
                return

            # Fall through to normal cycling dialogue
            pass

        # Module quest giver — user-created quests from the module editor
        if npc.npc_type == "module_quest_giver":
            mqname = getattr(npc, "_module_quest_name", "")
            mq_states = getattr(self.game, "module_quest_states", {})
            mq_state = mq_states.get(mqname, {})
            status = mq_state.get("status", "available")

            if status == "available":
                # Offer the quest
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self.quest_dialogue_lines = list(npc.quest_dialogue or [])
                self.quest_dialogue_index = 0
                if self.quest_dialogue_lines:
                    self._set_dialogue(
                        f"{npc.name}: {self.quest_dialogue_lines[0]}")
                else:
                    self._set_dialogue(
                        f"{npc.name}: I have a quest for you!")
                return

            elif status == "active":
                # Quest in progress — show hint
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                progress = mq_state.get("step_progress", [])
                done_count = sum(1 for p in progress if p)
                total = len(progress)
                self._set_dialogue(
                    f"{npc.name}: How's the quest going? "
                    f"({done_count}/{total} steps completed)")
                return

            elif status == "completed":
                # Turn in quest — award rewards and play celebration
                self.npc_dialogue_active = True
                self.npc_speaking = npc
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

                # Build reward text
                parts = []
                if reward_xp:
                    parts.append(f"+{reward_xp} XP")
                if reward_gold:
                    parts.append(f"+{reward_gold} Gold")
                reward_str = ", ".join(parts)
                if reward_str:
                    self._set_dialogue(
                        f"{npc.name}: Thank you, hero! "
                        f"Here is your reward: {reward_str}")
                else:
                    self._set_dialogue(
                        f"{npc.name}: Thank you for completing "
                        f"the quest! You truly are a hero.")

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
                self._refresh_quest_highlights()
                return

            elif status == "turned_in":
                # Already turned in — friendly message
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self._set_dialogue(
                    f"{npc.name}: Thank you again, hero! "
                    f"Your deeds will be remembered.")
                return

        # Quest giver — offers a single specific quest
        if npc.npc_type == "quest_giver":
            dk_str = getattr(npc, "dungeon_key_str", "")
            dname = getattr(npc, "dungeon_name", "a dungeon")
            kd_map = getattr(self.game, "key_dungeons", {})
            # Find the specific key dungeon this NPC is linked to
            kd = None
            if dk_str:
                parts = dk_str.split(",")
                if len(parts) == 2:
                    kd = kd_map.get((int(parts[0]), int(parts[1])))
            if kd and kd.get("status") == "undiscovered":
                # Offer the quest
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self.quest_dialogue_lines = list(npc.quest_dialogue or [])
                self.quest_dialogue_index = 0
                self._set_dialogue(
                    f"{npc.name}: {self.quest_dialogue_lines[0]}")
                return
            elif kd and kd.get("status") == "artifact_found":
                # Turn in this specific quest
                party = self.game.party
                qtype = kd.get("quest_type", "retrieve")
                completed = False
                if qtype == "kill":
                    kd["status"] = "completed"
                    completed = True
                    label = kd.get("name", "Dungeon")
                else:
                    art = kd.get("artifact_name", kd.get("key_name", ""))
                    if art and party.inv_count(art) > 0:
                        party.inv_remove(art)
                        kd["status"] = "completed"
                        completed = True
                        label = art
                if completed:
                    reward_gold = 37
                    reward_xp = 75
                    party.gold += reward_gold
                    for member in party.alive_members():
                        member.exp += reward_xp
                    self.npc_dialogue_active = True
                    self.npc_speaking = npc
                    self.quest_complete_effect = QuestCompleteEffect(
                        reward_gold, item_name=label)
                    self.game.sfx.play("quest_complete")
                    if qtype == "kill":
                        self._set_dialogue(
                            f"{npc.name}: You cleared the {label}! "
                            f"Here is {reward_gold} gold for your bravery!")
                    else:
                        self._set_dialogue(
                            f"{npc.name}: You recovered the {label}! "
                            f"Here is {reward_gold} gold for your bravery!")
                    self._refresh_quest_highlights()
                    return
            elif kd and kd.get("status") == "active":
                # Quest in progress hint
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self._set_dialogue(
                    f"{npc.name}: The {dname} still needs to be cleared. "
                    f"We're counting on you!")
                return
            # Quest completed — fall through to normal dialogue

        # Elder — gives progress hints about remaining quests
        # (individual quest_giver NPCs handle quest discovery now;
        #  gnome_machine quests are handled by the gnome)
        if npc.npc_type == "elder":
            kd_map = getattr(self.game, "key_dungeons", {})
            # Check for quests ready to turn in (artifact_found status)
            # Elder can still accept completed quests as a fallback
            found = [kd for kd in kd_map.values()
                     if kd.get("status") == "artifact_found"
                     and kd.get("quest_type") != "gnome_machine"]
            if found:
                party = self.game.party
                turned_in = []
                kill_turned_in = []
                for kd in found:
                    qtype = kd.get("quest_type", "retrieve")
                    if qtype == "kill":
                        kd["status"] = "completed"
                        kill_turned_in.append(kd.get("name", "Dungeon"))
                    else:
                        art = kd.get("artifact_name", kd.get("key_name", ""))
                        if art and party.inv_count(art) > 0:
                            party.inv_remove(art)
                            kd["status"] = "completed"
                            turned_in.append(art)
                all_completed = turned_in + kill_turned_in
                if all_completed:
                    reward_gold = 37 * len(all_completed)
                    reward_xp = 75 * len(all_completed)
                    party.gold += reward_gold
                    for member in party.alive_members():
                        member.exp += reward_xp
                    self.npc_dialogue_active = True
                    self.npc_speaking = npc
                    first_name = turned_in[0] if turned_in else kill_turned_in[0]
                    self.quest_complete_effect = QuestCompleteEffect(
                        reward_gold, item_name=first_name)
                    self.game.sfx.play("quest_complete")
                    if turned_in and not kill_turned_in:
                        names = ", ".join(turned_in)
                        self._set_dialogue(
                            f"{npc.name}: You recovered the {names}! "
                            f"Here is {reward_gold} gold for your bravery!")
                    elif kill_turned_in and not turned_in:
                        names = ", ".join(kill_turned_in)
                        self._set_dialogue(
                            f"{npc.name}: You cleared the {names}! "
                            f"Here is {reward_gold} gold for your bravery!")
                    else:
                        self._set_dialogue(
                            f"{npc.name}: Excellent work! "
                            f"Here is {reward_gold} gold for your bravery!")
                    self._refresh_quest_highlights()
                    return

            # Active quests still in progress — give progress hint
            non_gnome = [kd for kd in kd_map.values()
                         if kd.get("quest_type") != "gnome_machine"]
            active = [kd for kd in non_gnome
                      if kd.get("status") == "active"]
            undiscovered = [kd for kd in non_gnome
                           if kd.get("status") == "undiscovered"]
            if active:
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                n = len(active)
                self._set_dialogue(
                    f"{npc.name}: There are still {n} dungeon"
                    f"{'s' if n > 1 else ''} to clear. "
                    f"We're counting on you!")
                return
            if undiscovered:
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self._set_dialogue(
                    f"{npc.name}: Seek out the travelers in our towns. "
                    f"They know of dangers that threaten the land.")
                return

        self.npc_dialogue_active = True
        self.npc_speaking = npc
        # Show all dialogue lines sequentially — press Enter to advance
        lines = list(npc.dialogue) if npc.dialogue else ["..."]
        if len(lines) > 1:
            self.quest_dialogue_lines = lines
            self.quest_dialogue_index = 0
            self._set_dialogue(f"{npc.name}: {lines[0]}")
        else:
            self._set_dialogue(f"{npc.name}: {lines[0]}")

    def _advance_dialogue(self):
        """Advance or dismiss the current dialogue."""
        # If in quest dialogue flow, advance through lines then show choices
        if self.quest_dialogue_lines:
            self.quest_dialogue_index += 1
            if self.quest_dialogue_index < len(self.quest_dialogue_lines):
                # Show next quest dialogue line
                npc = self.npc_speaking
                self._set_dialogue(f"{npc.name}: {self.quest_dialogue_lines[self.quest_dialogue_index]}")
                return
            else:
                # All dialogue lines shown — present the Y/N choices
                npc = self.npc_speaking
                if npc and npc.quest_choices:
                    self.quest_choice_active = True
                    self.quest_choices = list(npc.quest_choices)
                    self.quest_choice_cursor = 0
                    return
                # No choices defined — just dismiss
                self.quest_dialogue_lines = []
                self.quest_dialogue_index = 0

        self.npc_dialogue_active = False
        self.npc_speaking = None
        self.message = ""
        self.message_timer = 0
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0

        # If the gnome's final dialogue was just dismissed, fire the
        # machine shutdown animation now.
        if self._pending_victory:
            self._pending_victory = False
            self._trigger_victory()

    # ── Quest ─────────────────────────────────────────────────────

    def _handle_quest_choice(self):
        """Handle the player's Y/N choice on the quest offer."""
        npc = self.npc_speaking
        if self.quest_choice_cursor == 0:
            # Accepted
            if npc and npc.npc_type == "gnome":
                self._accept_gnome_quest()
            elif npc and npc.npc_type == "module_quest_giver":
                self._accept_module_quest()
            elif npc and npc.npc_type == "quest_giver":
                self._accept_quest_giver_quest()
            elif npc and npc.npc_type == "elder":
                self._accept_elder_quest()
            else:
                self._accept_quest()
        else:
            # Declined
            self._set_dialogue(f"{npc.name}: No worries. Come back if you change your mind.")
            self.quest_choice_active = False
            self.quest_choices = []
            self.quest_dialogue_lines = []
            self.quest_dialogue_index = 0
            # Keep dialogue active to show the decline message

    def _accept_quest_giver_quest(self):
        """Accept a quest_giver NPC's quest: reveal one key dungeon."""
        npc = self.npc_speaking
        dk_str = getattr(npc, "dungeon_key_str", "")
        dname = getattr(npc, "dungeon_name", "the dungeon")
        self.game.discover_single_key_dungeon(dk_str)
        self._set_dialogue(
            f"{npc.name}: Thank you, brave souls! "
            f"I've marked the {dname} on your map. "
            f"Be careful out there!")
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0
        self._refresh_quest_highlights()

    def _accept_module_quest(self):
        """Accept a module quest giver's quest."""
        npc = self.npc_speaking
        mqname = getattr(npc, "_module_quest_name", "")
        mq_states = getattr(self.game, "module_quest_states", {})
        if mqname in mq_states:
            mq_states[mqname]["status"] = "active"

        # Spawn quest monsters for any 'kill' steps
        if hasattr(self.game, "_spawn_quest_monsters"):
            self.game._spawn_quest_monsters(mqname)

        # Find quest definition for reward info
        quest_defs = getattr(self.game, "_module_quest_defs", [])
        qdef = None
        for q in quest_defs:
            if q.get("name") == mqname:
                qdef = q
                break

        reward_xp = 0
        reward_gold = 0
        if qdef:
            reward_xp = qdef.get("reward_xp", 0)
            reward_gold = qdef.get("reward_gold", 0)

        # Quest accepted visual effect
        self.quest_effects.append({
            "type": "quest_accepted",
            "timer": 2500,
            "duration": 2500,
        })
        self.game.sfx.play("quest_complete")

        self._set_dialogue(
            f"{npc.name}: Wonderful! I'm counting on you. "
            f"Good luck out there!")
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0

    def _accept_gnome_quest(self):
        """Accept the gnome's machine quest (Keys of Shadow or custom)."""
        npc = self.npc_speaking
        self.game.set_gnome_quest_accepted()
        # Reveal only gnome_machine key dungeons (KoS reveals all)
        mod_id = ""
        if self.game.module_manifest:
            mod_id = self.game.module_manifest.get(
                "metadata", {}).get("id", "")
        if mod_id == "keys_of_shadow":
            self.game.discover_key_dungeons()
        else:
            self.game.discover_key_dungeons(
                only_types={"gnome_machine"})
        total = self.game.get_total_keys()
        self._set_dialogue(
            f"{npc.name}: Thank you! The {total} dungeons are scattered "
            f"across the land. Start with the closest one — it's the "
            f"easiest. Bring the keys back to me!")
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0
        self._refresh_quest_highlights()

    def _accept_elder_quest(self):
        """Legacy fallback — elder no longer gives quests directly.

        Individual quest_giver NPCs handle quest discovery now.
        This method exists only as a safety net.
        """
        npc = self.npc_speaking
        self._set_dialogue(
            f"{npc.name}: Seek out the travelers in the towns. "
            f"They know of the dangers that threaten our land.")
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0
        npc.quest_choices = None
        self._refresh_quest_highlights()

    def _accept_quest(self):
        """Accept the innkeeper's quest: place a dungeon on the overworld."""
        npc = self.npc_speaking

        # Use the quest metadata from the innkeeper NPC
        quest_name = getattr(npc, "quest_name", "The Shadow Crystal")
        artifact_name = getattr(npc, "artifact_name", "Shadow Crystal")

        # If innkeeper_quests mode: use the pending quest data
        # that was generated during the dialogue offer
        inn_quests = getattr(npc, "innkeeper_quests", False)
        pending = getattr(npc, "_pending_innkeeper_quest", None)
        if inn_quests and pending:
            quest_data = pending
            npc._pending_innkeeper_quest = None
        else:
            quest_data = {
                "name": quest_name,
                "quest_type": "retrieve",
                "artifact_name": artifact_name,
            }

        q_type = quest_data.get("quest_type", "retrieve")
        q_name = quest_data["name"]

        # Generate a multi-level quest dungeon (1-4 floors)
        num_floors = random.randint(1, 4) if inn_quests else 2
        place_artifact = (q_type != "kill")
        kill_target = quest_data.get("kill_target") if q_type == "kill" else None
        kill_count = quest_data.get("kill_count", 0) if q_type == "kill" else 0
        levels = generate_innkeeper_quest_dungeon(
            q_name, num_floors=num_floors,
            place_artifact=place_artifact,
            kill_target=kill_target,
            kill_count=kill_count)

        # Find a random accessible tile on the overworld for the dungeon
        dc, dr = self._find_quest_dungeon_location()

        # Place dungeon tile on the overworld map
        self.game.tile_map.set_tile(dc, dr, TILE_DUNGEON)

        # Store quest state
        quest = {
            "name": q_name,
            "status": "active",
            "dungeon_col": dc,
            "dungeon_row": dr,
            "levels": levels,
            "current_level": 0,
            "artifact_name": quest_data.get("artifact_name", artifact_name),
            "quest_type": q_type,
            "exit_portal": True,
        }
        if q_type == "kill":
            quest["kill_target"] = quest_data.get("kill_target", "Skeleton")
            quest["kill_count"] = quest_data.get("kill_count", 3)
            quest["kill_progress"] = 0
        self.game.set_quest(quest)

        # Show confirmation
        self._set_dialogue(
            f"{npc.name}: Thank you! I've marked a suspicious "
            f"location on your map. Be careful down there!")
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0
        self._refresh_quest_highlights()

    # ── Random innkeeper quest pools ─────────────────────────────

    _RANDOM_RETRIEVE_QUESTS = [
        {"name": "The Lost Chalice", "artifact": "Golden Chalice"},
        {"name": "The Stolen Tome", "artifact": "Ancient Tome"},
        {"name": "The Missing Pendant", "artifact": "Silver Pendant"},
        {"name": "The Dark Orb", "artifact": "Shadow Orb"},
        {"name": "The Cursed Idol", "artifact": "Cursed Idol"},
        {"name": "The Hidden Crown", "artifact": "Forgotten Crown"},
        {"name": "The Ember Stone", "artifact": "Ember Stone"},
        {"name": "The Frost Shard", "artifact": "Frost Shard"},
    ]

    _RANDOM_KILL_TARGETS = [
        "Giant Rat", "Skeleton", "Orc", "Goblin", "Zombie",
        "Wolf", "Dark Mage", "Troll",
    ]

    def _generate_random_innkeeper_quest(self, npc):
        """Generate a random quest — retrieve or kill — for the innkeeper."""
        q_type = random.choice(["retrieve", "kill"])
        if q_type == "retrieve":
            template = random.choice(self._RANDOM_RETRIEVE_QUESTS)
            return {
                "name": template["name"],
                "quest_type": "retrieve",
                "artifact_name": template["artifact"],
            }
        else:
            target = random.choice(self._RANDOM_KILL_TARGETS)
            count = random.randint(2, 6)
            return {
                "name": f"Hunt the {target}s",
                "quest_type": "kill",
                "kill_target": target,
                "kill_count": count,
                "artifact_name": target,  # not really used for kill
            }

    def _find_quest_dungeon_location(self):
        """Find a random walkable overworld tile for the quest dungeon.

        Avoids water, mountains, town, and existing dungeon tiles.
        Stays within the playable map area (inside ocean border).
        """
        tmap = self.game.tile_map
        candidates = []
        ok_tiles = {TILE_GRASS, TILE_FOREST, TILE_PATH}

        for r in range(4, tmap.height - 4):
            for c in range(4, tmap.width - 4):
                if tmap.get_tile(c, r) in ok_tiles:
                    candidates.append((c, r))

        # Shuffle and pick first candidate with some spacing from town
        random.shuffle(candidates)
        town_col, town_row = 10, 14  # known town location
        for c, r in candidates:
            dist = abs(c - town_col) + abs(r - town_row)
            if dist >= 6:
                return (c, r)
        # Fallback — just pick any candidate
        return candidates[0] if candidates else (20, 10)

    def _complete_quest(self, npc):
        """Complete the quest: remove artifact, give reward, play celebration."""
        party = self.game.party
        quest = self.game.get_quest()
        q_type = quest.get("quest_type", "retrieve") if quest else "retrieve"
        artifact = quest.get("artifact_name", "Shadow Crystal") if quest else "Shadow Crystal"

        # Remove the artifact from inventory (retrieve quests only)
        if q_type != "kill" and party.inv_count(artifact) > 0:
            party.inv_remove(artifact)

        # Give gold reward
        reward = 50
        party.gold += reward

        # Give XP reward to all alive members
        for member in party.alive_members():
            member.exp += 50

        # Mark quest completed
        quest["status"] = "completed"

        # Launch celebration animation and play fanfare
        display_name = artifact if q_type != "kill" else quest.get("name", "Quest")
        self.quest_complete_effect = QuestCompleteEffect(
            reward, item_name=display_name)
        self.game.sfx.play("quest_complete")

        # Dialogue — use per-NPC text if available, else generic
        inn_quests = getattr(npc, "innkeeper_quests", False)
        complete_text = getattr(npc, "text_complete", None)
        if complete_text and not inn_quests:
            dialogue = f"{npc.name}: {complete_text}"
        elif q_type == "kill":
            target = quest.get("kill_target", "monsters")
            dialogue = (f"{npc.name}: The {target}s have been dealt with! "
                        f"Here's {reward} gold for your bravery!")
        else:
            dialogue = (f"{npc.name}: You found the {artifact}! "
                        f"Here's {reward} gold for your bravery!")
        if inn_quests:
            dialogue += " Talk to me again when you're ready for more work."

        self.npc_dialogue_active = True
        self.npc_speaking = npc
        self._set_dialogue(dialogue)
        self._refresh_quest_highlights()

    # ── Shop ──────────────────────────────────────────────────────

    def _handle_shop_input(self, event):
        """Handle input while the shop screen is open."""
        from src.party import (SHOP_INVENTORY, get_sell_price,
                                group_items_by_category,
                                group_inventory_by_category,
                                get_shop_items)

        buy_items = get_shop_items(getattr(self, "shop_type", "general"))
        sell_items = self.game.party.shared_inventory
        num_buy = len(buy_items)
        num_sell = len(sell_items)

        if event.key == pygame.K_ESCAPE:
            self.showing_shop = False
            return

        if event.key == pygame.K_TAB:
            if self.shop_mode == "buy":
                self.shop_mode = "sell"
                self.shop_sell_cursor = min(
                    self.shop_sell_cursor, max(0, num_sell - 1))
            else:
                self.shop_mode = "buy"
            return

        if self.shop_mode == "buy":
            if not buy_items:
                return
            if event.key == pygame.K_UP:
                self.shop_cursor = (self.shop_cursor - 1) % num_buy
            elif event.key == pygame.K_DOWN:
                self.shop_cursor = (self.shop_cursor + 1) % num_buy
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Resolve item name from grouped list
                grouped = group_items_by_category(buy_items)
                item_name = None
                ic = -1
                for iname, cat in grouped:
                    if iname is not None:
                        ic += 1
                        if ic == self.shop_cursor:
                            item_name = iname
                            break
                if item_name is None:
                    return
                cost = SHOP_INVENTORY[item_name]["buy"]
                if self.game.party.gold >= cost:
                    self.game.party.gold -= cost
                    self.game.party.inv_add(item_name)
                    self.shop_message = f"Bought {item_name}!"
                    self.shop_message_timer = 1500
                else:
                    self.shop_message = "Not enough gold!"
                    self.shop_message_timer = 1500

        else:  # sell mode
            if not sell_items:
                return
            if event.key == pygame.K_UP:
                self.shop_sell_cursor = (self.shop_sell_cursor - 1) % num_sell
            elif event.key == pygame.K_DOWN:
                self.shop_sell_cursor = (self.shop_sell_cursor + 1) % num_sell
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Resolve entry from grouped list
                grouped = group_inventory_by_category(
                    sell_items, self.game.party.item_name)
                real_entry = None
                real_idx = None
                ic = -1
                for entry in grouped:
                    is_hdr = (isinstance(entry, str)
                              and entry.startswith("__header__:"))
                    if not is_hdr:
                        ic += 1
                        if ic == self.shop_sell_cursor:
                            real_entry = entry
                            # Find index in original list
                            real_idx = sell_items.index(entry)
                            break
                if real_entry is None:
                    return
                item_name = self.game.party.item_name(real_entry)
                price = get_sell_price(item_name)
                self.game.party.gold += price
                self.game.party.shared_inventory.pop(real_idx)
                self.shop_message = f"Sold {item_name} for {price}g!"
                self.shop_message_timer = 1500
                if self.shop_sell_cursor >= len(self.game.party.shared_inventory):
                    self.shop_sell_cursor = max(
                        0, len(self.game.party.shared_inventory) - 1)

    # ── Temple service menu ─────────────────────────────────

    def _handle_temple_service_input(self, event):
        """Handle input while the temple service menu is open."""
        if event.key == pygame.K_ESCAPE:
            self.showing_temple_service = False
            self.temple_npc = None
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.temple_service_cursor = (self.temple_service_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.temple_service_cursor = (self.temple_service_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._process_temple_service()

    def _process_temple_service(self):
        """Perform the selected temple service (healing or resurrection)."""
        party = self.game.party
        npc = self.temple_npc

        if self.temple_service_cursor == 0:
            # ── HEALING — 100 gold ──
            if party.gold < 100:
                self.temple_message = "Not enough gold for healing."
                self.temple_message_timer = 2500
                return
            # Check if anyone actually needs healing
            needs_heal = any(
                (m.hp < m.max_hp or m.current_mp < m.max_mp)
                for m in party.members if m.is_alive()
            )
            if not needs_heal:
                self.temple_message = "Your party is already in perfect health."
                self.temple_message_timer = 2500
                return
            # Apply full heal to all alive members
            party.gold -= 100
            for m in party.members:
                if m.is_alive():
                    m.hp = m.max_hp
                    m.current_mp = m.max_mp
            self.temple_message = (
                f"The blessing of {npc.god_name} restores your party!"
            )
            self.temple_message_timer = 3000
            self.temple_heal_effect = TempleHealEffect()
            self.game.game_log.append(
                f"Temple of {npc.god_name}: All HP and MP restored for 100 gold."
            )
            try:
                self.game.sfx.play("heal")
            except Exception:
                pass

        elif self.temple_service_cursor == 1:
            # ── RESURRECTION — 1000 gold ──
            if party.gold < 1000:
                self.temple_message = "Not enough gold for resurrection."
                self.temple_message_timer = 2500
                return
            # Find first dead (non-ash) party member
            target = None
            for m in party.members:
                if m.hp <= 0 and not getattr(m, "is_ash", False):
                    target = m
                    break
            if target is None:
                self.temple_message = "No fallen allies to resurrect."
                self.temple_message_timer = 2500
                return
            # Resurrect to full
            party.gold -= 1000
            target.hp = target.max_hp
            target.current_mp = target.max_mp
            self.temple_message = (
                f"{target.name} is returned to life by {npc.god_name}!"
            )
            self.temple_message_timer = 3000
            self.temple_heal_effect = TempleHealEffect()
            self.game.game_log.append(
                f"Temple of {npc.god_name}: {target.name} resurrected for 1000 gold."
            )
            try:
                self.game.sfx.play("heal")
            except Exception:
                pass

    def _exit_town(self):
        """Leave the town (or exit an interior back to the town)."""
        # If inside a building interior, return to the town map
        if getattr(self, "_in_interior", False):
            self._exit_interior()
            return
        # Otherwise leave the town entirely
        self.game.party.col = self.overworld_col
        self.game.party.row = self.overworld_row
        self.game.change_state("overworld")

    def _exit_to_town(self):
        """Unwind the entire interior stack, returning to the town level."""
        stack = getattr(self, "_interior_stack", [])
        if not stack:
            self._in_interior = False
            return
        # The bottom of the stack is the town level — restore it.
        bottom = stack[0]
        stack.clear()
        self.town_data.tile_map = bottom["tile_map"]
        self.town_data.npcs = bottom["npcs"]
        self.town_data.interior_links = bottom["interior_links"]
        self.town_data.overworld_exits = bottom.get("overworld_exits", set())
        self.game.party.col = bottom["col"]
        self.game.party.row = bottom["row"]
        self._interior_exit_positions = bottom.get("exit_positions", set())
        self._interior_overworld_exits = bottom.get(
            "overworld_exit_positions", set())
        self._interior_name = ""
        self._in_interior = False
        self.game.camera.map_width = self.town_data.tile_map.width
        self.game.camera.map_height = self.town_data.tile_map.height
        self.game.camera.update(self.game.party.col, self.game.party.row)
        self.show_message("Returning to town...", 1000)

    def _exit_interior(self):
        """Return from a building interior to the previous level (town or parent interior)."""
        stack = getattr(self, "_interior_stack", [])
        if not stack:
            # Safety fallback — shouldn't happen
            self._in_interior = False
            return
        prev = stack.pop()
        self.town_data.tile_map = prev["tile_map"]
        self.town_data.npcs = prev["npcs"]
        self.town_data.interior_links = prev["interior_links"]
        self.town_data.overworld_exits = prev.get("overworld_exits", set())
        # Place party back at the door tile
        self.game.party.col = prev["col"]
        self.game.party.row = prev["row"]
        # Restore exit positions and interior name from the level we're returning to
        self._interior_exit_positions = prev.get("exit_positions", set())
        self._interior_overworld_exits = prev.get("overworld_exit_positions", set())
        leaving_name = getattr(self, "_interior_name", "building")
        self._interior_name = prev.get("name", "")
        # If the stack is now empty, we're back at the town level
        if not stack:
            self._in_interior = False
        # Restore camera
        self.game.camera.map_width = self.town_data.tile_map.width
        self.game.camera.map_height = self.town_data.tile_map.height
        self.game.camera.update(self.game.party.col, self.game.party.row)
        self.show_message(f"Leaving {leaving_name}...", 1000)

    def update(self, dt):
        """Update timers."""
        dt_ms = dt * 1000

        # Quest completion animation blocks everything else
        if self.quest_complete_effect:
            self.quest_complete_effect.update(dt)
            if not self.quest_complete_effect.alive:
                self.quest_complete_effect = None
            return

        # Machine shutdown animation — when it finishes, lift the darkness
        if self.machine_shutdown_effect:
            self.machine_shutdown_effect.update(dt)
            if not self.machine_shutdown_effect.alive:
                self.game.set_darkness(False)
                self.machine_shutdown_effect = None
            return

        if self.message_timer > 0:
            self.message_timer -= dt_ms
            if self.message_timer <= 0:
                if not self.npc_dialogue_active:
                    self.message = ""
                self.message_timer = 0

        if self.shop_message_timer > 0:
            self.shop_message_timer -= dt_ms
            if self.shop_message_timer <= 0:
                self.shop_message = ""
                self.shop_message_timer = 0

        # Temple timers
        if self.temple_heal_effect:
            self.temple_heal_effect.update(dt)
            if not self.temple_heal_effect.alive:
                self.temple_heal_effect = None
        if self.temple_message_timer > 0:
            self.temple_message_timer -= dt_ms
            if self.temple_message_timer <= 0:
                self.temple_message = ""
                self.temple_message_timer = 0

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

        # Tick module quest effects
        if self.quest_effects:
            for fx in self.quest_effects:
                fx["timer"] -= dt_ms
            self.quest_effects = [
                fx for fx in self.quest_effects if fx["timer"] > 0]

        # NPC wandering
        self._update_npc_wandering(dt)

    def _update_npc_wandering(self, dt):
        """Move wandering NPCs around the town at random intervals.

        Stationary NPC types (shopkeepers, innkeepers, priests, gnomes)
        stay in place.  Everyone else drifts randomly within a few tiles
        of their starting position, avoiding walls, other NPCs, and the
        player.
        """
        if not self.town_data:
            return
        # Don't move NPCs while the player is in dialogue or a menu
        if (self.npc_dialogue_active or self.quest_choice_active
                or self.showing_shop or self.showing_temple_service
                or self.pickpocket_targeting):
            return

        from src.town_generator import NPC as NPCClass
        tmap = self.town_data.tile_map
        party = self.game.party

        # Build a set of occupied positions (other NPCs + player)
        occupied = set()
        for npc in self.town_data.npcs:
            occupied.add((npc.col, npc.row))
        occupied.add((party.col, party.row))

        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]

        for npc in self.town_data.npcs:
            # Skip stationary NPC types
            if npc.npc_type in NPCClass.STATIONARY_TYPES:
                continue

            npc.wander_timer -= dt
            if npc.wander_timer > 0:
                continue

            # Reset timer for next move (randomised pace)
            anchor = getattr(npc, "_guardian_anchor", None)
            if anchor:
                # Guardians move faster to intercept
                npc.wander_timer = random.uniform(0.4, 1.0)
            else:
                npc.wander_timer = random.uniform(1.5, 4.0)

            # ── Guardian interception behaviour ──
            if anchor:
                ax, ay = anchor
                leash = getattr(npc, "_guardian_leash", GUARDIAN_LEASH)
                dist_party = (abs(party.col - ax) + abs(party.row - ay))
                # Intercept when party is within 6 tiles of the artifact
                if dist_party <= GUARDIAN_INTERCEPT_RANGE_INTERIOR:
                    best = None
                    best_dist = (abs(npc.col - party.col)
                                 + abs(npc.row - party.row))
                    for dc, dr in directions:
                        nc, nr = npc.col + dc, npc.row + dr
                        # Must stay within leash of anchor
                        if (abs(nc - ax) + abs(nr - ay)) > leash:
                            continue
                        if not tmap.is_walkable(nc, nr):
                            continue
                        if (nc, nr) in occupied:
                            continue
                        d = abs(nc - party.col) + abs(nr - party.row)
                        if d < best_dist:
                            best_dist = d
                            best = (nc, nr)
                    if best:
                        occupied.discard((npc.col, npc.row))
                        npc.col, npc.row = best
                        occupied.add(best)
                else:
                    # Drift back toward anchor if too far away
                    dist_to_anchor = (abs(npc.col - ax)
                                      + abs(npc.row - ay))
                    if dist_to_anchor > leash:
                        best = None
                        best_dist = dist_to_anchor
                        for dc, dr in directions:
                            nc, nr = npc.col + dc, npc.row + dr
                            if not tmap.is_walkable(nc, nr):
                                continue
                            if (nc, nr) in occupied:
                                continue
                            d = abs(nc - ax) + abs(nr - ay)
                            if d < best_dist:
                                best_dist = d
                                best = (nc, nr)
                        if best:
                            occupied.discard((npc.col, npc.row))
                            npc.col, npc.row = best
                            occupied.add(best)
                    # Otherwise stay put — guardians don't wander randomly
                continue

            # Pick a random direction
            random.shuffle(directions)
            moved = False
            for dc, dr in directions:
                nc, nr = npc.col + dc, npc.row + dr

                # Stay within wander range of home position
                if (abs(nc - npc.home_col) > npc.wander_range
                        or abs(nr - npc.home_row) > npc.wander_range):
                    continue

                # Must be a walkable tile
                if not tmap.is_walkable(nc, nr):
                    continue

                # Can't step on another NPC or the player
                if (nc, nr) in occupied:
                    continue

                # Move the NPC
                occupied.discard((npc.col, npc.row))
                npc.col = nc
                npc.row = nr
                occupied.add((nc, nr))
                moved = True
                break

            # If stuck, just wait for next timer tick (no movement)

    def draw(self, renderer):
        """Draw the town in Ultima III style."""
        if self.showing_temple_service:
            npc = self.temple_npc
            renderer.draw_temple_service_menu(
                self.game.party,
                self.temple_service_cursor,
                npc.name if npc else "",
                npc.god_name if npc else "The Divine",
                self.temple_message,
            )
            if self.temple_heal_effect:
                renderer.draw_temple_heal_effect(self.temple_heal_effect)
            return
        if self.showing_shop:
            cursor = (self.shop_cursor if self.shop_mode == "buy"
                      else self.shop_sell_cursor)
            quest = self.game.get_quest()
            quest_complete = (quest.get("artifact_name", "Shadow Crystal")
                              if quest and quest.get("status") == "completed"
                              else False)
            renderer.draw_shop_u3(
                self.game.party, self.shop_mode, cursor,
                self.shop_message,
                quest_complete=quest_complete,
                shop_type=getattr(self, "shop_type", "general"))
            return
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
                pickpocket_available=self._can_pickpocket(),
                tinker_available=self._can_tinker(),
                applying_poison_step=self.applying_poison_step,
                applying_poison_cursor=self.applying_poison_cursor,
                applying_poison_item=self.applying_poison_item,
                applying_poison_member=getattr(self, '_applying_poison_member', None))
            if self.use_item_anim:
                renderer.draw_use_item_animation(self.game.party, self.use_item_anim)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item)
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
                renderer.draw_item_examine(self.examining_item)
            return
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        # Use the new sprite-tile-based town renderer
        msg = self.message
        quest = self.game.get_quest()
        quest_complete = (quest.get("artifact_name", "Shadow Crystal")
                          if quest and quest.get("status") == "completed"
                          else False)
        # Screen shake offset during machine shutdown Phase 1
        shake_x, shake_y = (0, 0)
        if self.machine_shutdown_effect:
            shake_x, shake_y = self.machine_shutdown_effect.shake_offset

        # Town is dark if global darkness is on (KoS) OR if THIS town
        # is the gnome machine town and the quest is still incomplete.
        # Keep darkness active while the shutdown animation is playing
        # so the town doesn't light up before the cinematic transition.
        town_dark = getattr(self.game, "darkness_active", False)
        if self.machine_shutdown_effect:
            town_dark = True
        elif not town_dark:
            kd_map = getattr(self.game, "key_dungeons", {})
            inserted = getattr(self.game, "keys_inserted", 0)
            current_name = self.town_data.name if self.town_data else ""
            gnome_total = sum(
                1 for kd in kd_map.values()
                if kd.get("quest_type") == "gnome_machine")
            # Only darken the specific town chosen for the gnome quest
            gnome_town_name = ""
            for kd in kd_map.values():
                if kd.get("quest_type") == "gnome_machine":
                    gnome_town_name = kd.get("gnome_town", "")
                    if gnome_town_name:
                        break
            if gnome_total > 0 and inserted < gnome_total:
                if gnome_town_name:
                    town_dark = (current_name == gnome_town_name)
                else:
                    # No town specified — fall back to darkening
                    # the first/hub town (which has the machine)
                    town_dark = self.town_data == getattr(
                        self.game, "town_data", None)

        _int_dark = getattr(self, "_in_interior", False)
        print(f"[TOWN DEBUG] draw call: _in_interior={_int_dark}, "
              f"town={self.town_data.name}, "
              f"party=({self.game.party.col},{self.game.party.row}), "
              f"map_size=({self.town_data.tile_map.width}x{self.town_data.tile_map.height})")
        renderer.draw_town_u3(
            self.game.party,
            self.town_data,
            message=msg,
            quest_complete=quest_complete,
            darkness_active=town_dark,
            keys_inserted=getattr(self.game, "keys_inserted", 0),
            total_keys=self.game.get_total_keys(),
            shake_offset=(shake_x, shake_y),
            interior_darkness=_int_dark,
        )
        # Pickpocket targeting overlay
        if self.pickpocket_targeting and self.pickpocket_targets:
            renderer.draw_pickpocket_targeting(
                self.game.party, self.town_data,
                self.pickpocket_targets, self.pickpocket_cursor)

        # Machine shutdown animation overlay
        if self.machine_shutdown_effect:
            _td = getattr(self.game, "town_data", None)
            _tn = _td.name if _td else "the realm"
            renderer.draw_machine_shutdown_effect(
                self.machine_shutdown_effect, town_name=_tn)
            return  # blocks dialogue rendering during animation

        # Quest completion celebration overlay
        if self.quest_complete_effect:
            renderer.draw_quest_complete_effect(self.quest_complete_effect)
            return  # blocks dialogue rendering during animation

        # Module quest visual effects (accepted, step complete, etc.)
        if self.quest_effects:
            renderer._draw_quest_effects(self.quest_effects)

        # Temple celestial animation overlay (when walking in town after service)
        if self.temple_heal_effect:
            renderer.draw_temple_heal_effect(self.temple_heal_effect)

        # Dialogue box renders on top if active
        if self.message and self.npc_dialogue_active:
            renderer.draw_dialogue_box(self.message)
        # Quest choice overlay (Y/N prompt)
        if self.quest_choice_active:
            renderer.draw_quest_choice_box(
                self.quest_choices, self.quest_choice_cursor)
        if self.level_up_queue:
            renderer.draw_level_up_animation(self.level_up_queue[0])
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
        if self.showing_help:
            renderer.draw_town_help_overlay()
