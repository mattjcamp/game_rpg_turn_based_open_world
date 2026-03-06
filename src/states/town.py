"""
Town state - exploring a town interior.

The party walks around inside a town, talks to NPCs by bumping into them,
and can leave through the exit gate to return to the overworld.
"""

import math
import random

import pygame

from src.states.base_state import BaseState
from src.states.inventory_mixin import InventoryMixin
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_EXIT, TILE_DUNGEON,
    TILE_GRASS, TILE_FOREST, TILE_PATH, TILE_WATER, TILE_MOUNTAIN,
    TILE_TOWN, TILE_MACHINE,
)
from src.dungeon_generator import generate_quest_dungeon


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

        # Pickpocket targeting mode
        self.pickpocket_targeting = False
        self.pickpocket_targets = []   # list of adjacent NPCs
        self.pickpocket_cursor = 0     # index into pickpocket_targets

        # We'll save the overworld position so we can restore it on exit
        self.overworld_col = 0
        self.overworld_row = 0

    def enter_town(self, town_data, overworld_col, overworld_row):
        """
        Set up the town state with town-specific data.
        Called before change_state so the town knows what to load.
        """
        self.town_data = town_data
        self.overworld_col = overworld_col
        self.overworld_row = overworld_row

    def enter(self):
        """Called when this state becomes active."""
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

    def exit(self):
        """Called when leaving this state."""
        self.npc_dialogue_active = False
        self.npc_speaking = None
        self.pickpocket_targeting = False
        self.pickpocket_targets = []

    def handle_input(self, events, keys_pressed):
        """Handle movement and NPC interaction."""
        # Block all input during quest celebration
        if self.quest_complete_effect:
            return

        for event in events:
            if event.type == pygame.KEYDOWN:
                # ── Log overlay input ──
                if self.showing_log:
                    if event.key == pygame.K_l or event.key == pygame.K_ESCAPE:
                        self.showing_log = False
                    elif event.key == pygame.K_UP:
                        self.log_scroll += 3
                    elif event.key == pygame.K_DOWN:
                        self.log_scroll = max(0, self.log_scroll - 3)
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
        if self.showing_shop:
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
        elif keys_pressed[pygame.K_DOWN] or keys_pressed[pygame.K_s]:
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
        tile_id = self.town_data.tile_map.get_tile(
            self.game.party.col, self.game.party.row
        )
        if tile_id == TILE_EXIT:
            self._exit_town()
        elif tile_id == TILE_MACHINE:
            self._interact_machine()

    # ── Machine interaction (Keys of Shadow) ──────────────────

    def _interact_machine(self):
        """Handle stepping on the gnome machine tile."""
        kd = getattr(self.game, "key_dungeons", {})
        if not kd:
            self.show_message("A strange machine hums ominously.", 2000)
            return

        party = self.game.party
        key_names = [d["key_name"] for d in kd.values()]
        held_keys = [k for k in key_names if party.inv_count(k) > 0]

        total = len(kd)
        inserted = self.game.keys_inserted

        if held_keys:
            for key in held_keys:
                party.inv_remove(key)
                self.game.keys_inserted += 1
            inserted = self.game.keys_inserted
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
                "A massive gnomish machine blocks the sun! "
                "It has 8 empty keyhole slots.", 3500)

    def _trigger_victory(self):
        """Called when all 8 keys are inserted — the sun returns!"""
        self.game.darkness_active = False
        for m in self.game.party.active_members():
            if m.is_alive():
                m.exp += 500
                msgs = m.check_level_up()
                for msg in msgs:
                    self.game.log(msg)
        self.game.party.gold += 1000
        self.game.log("*** THE MACHINE POWERS DOWN! ***")
        self.game.log("Sunlight floods the land once more!")
        self.game.log("The people of Duskhollow are saved!")
        self.game.log("VICTORY! +500 XP, +1000 Gold")
        self.show_message(
            "THE MACHINE POWERS DOWN! Sunlight returns! VICTORY!", 6000)

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

    def _start_dialogue(self, npc):
        """Begin talking to an NPC, or open the shop for shopkeepers."""
        if npc.npc_type == "shopkeep":
            self.showing_shop = True
            self.shop_mode = "buy"
            self.shop_cursor = 0
            self.shop_sell_cursor = 0
            self.shop_message = ""
            self.shop_message_timer = 0
            return

        # Innkeeper quest logic
        if npc.npc_type == "innkeeper":
            quest = self.game.quest
            # No quest yet — offer one
            if quest is None and npc.quest_dialogue:
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self.quest_dialogue_lines = list(npc.quest_dialogue)
                self.quest_dialogue_index = 0
                self.message = f"{npc.name}: {self.quest_dialogue_lines[0]}"
                self.message_timer = 0
                return
            # Player has the artifact — complete the quest
            if quest and quest["status"] == "artifact_found":
                self._complete_quest(npc)
                return
            # Quest already active — hint
            if quest and quest["status"] == "active":
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self.message = f"{npc.name}: Have you found the Shadow Crystal yet? It's out there somewhere..."
                self.message_timer = 0
                return
            # Quest completed — display item dialogue
            if quest and quest["status"] == "completed":
                self.npc_dialogue_active = True
                self.npc_speaking = npc
                self.message = f"{npc.name}: The Shadow Crystal sits safely behind my counter. You've earned a hero's welcome here!"
                self.message_timer = 0
                return

        self.npc_dialogue_active = True
        self.npc_speaking = npc
        line = npc.get_dialogue()
        self.message = f"{npc.name}: {line}"
        self.message_timer = 0  # dialogue stays until dismissed

    def _advance_dialogue(self):
        """Advance or dismiss the current dialogue."""
        # If in quest dialogue flow, advance through lines then show choices
        if self.quest_dialogue_lines:
            self.quest_dialogue_index += 1
            if self.quest_dialogue_index < len(self.quest_dialogue_lines):
                # Show next quest dialogue line
                npc = self.npc_speaking
                self.message = f"{npc.name}: {self.quest_dialogue_lines[self.quest_dialogue_index]}"
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

    # ── Quest ─────────────────────────────────────────────────────

    def _handle_quest_choice(self):
        """Handle the player's Y/N choice on the quest offer."""
        if self.quest_choice_cursor == 0:
            # Accepted
            self._accept_quest()
        else:
            # Declined
            npc = self.npc_speaking
            self.message = f"{npc.name}: No worries. Come back if you change your mind."
            self.quest_choice_active = False
            self.quest_choices = []
            self.quest_dialogue_lines = []
            self.quest_dialogue_index = 0
            # Keep dialogue active to show the decline message

    def _accept_quest(self):
        """Accept the innkeeper's quest: place a dungeon on the overworld."""
        npc = self.npc_speaking

        # Generate the two-level quest dungeon
        levels = generate_quest_dungeon("Shadow Dungeon")

        # Find a random accessible tile on the overworld for the dungeon
        dc, dr = self._find_quest_dungeon_location()

        # Place dungeon tile on the overworld map
        self.game.tile_map.set_tile(dc, dr, TILE_DUNGEON)

        # Store quest state
        self.game.quest = {
            "name": "The Shadow Crystal",
            "status": "active",
            "dungeon_col": dc,
            "dungeon_row": dr,
            "levels": levels,
            "current_level": 0,
            "artifact_name": "Shadow Crystal",
        }

        # Show confirmation
        self.message = f"{npc.name}: Thank you! I've marked a suspicious location on your map. Be careful down there!"
        self.quest_choice_active = False
        self.quest_choices = []
        self.quest_dialogue_lines = []
        self.quest_dialogue_index = 0

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

        # Remove the Shadow Crystal from inventory
        party.inv_remove("Shadow Crystal")

        # Give gold reward
        reward = 200
        party.gold += reward

        # Give XP reward to all alive members
        for member in party.alive_members():
            member.exp += 50

        # Mark quest completed
        self.game.quest["status"] = "completed"

        # Launch celebration animation and play fanfare
        self.quest_complete_effect = QuestCompleteEffect(reward)
        self.game.sfx.play("quest_complete")

        # Dialogue will show after the animation finishes
        self.npc_dialogue_active = True
        self.npc_speaking = npc
        self.message = f"{npc.name}: You found the Shadow Crystal! Here's {reward} gold for your bravery!"
        self.message_timer = 0

    # ── Shop ──────────────────────────────────────────────────────

    def _handle_shop_input(self, event):
        """Handle input while the shop screen is open."""
        from src.party import SHOP_INVENTORY, get_sell_price

        buy_items = list(SHOP_INVENTORY.keys())
        sell_items = self.game.party.shared_inventory

        if event.key == pygame.K_ESCAPE:
            self.showing_shop = False
            return

        if event.key == pygame.K_TAB:
            # Toggle buy / sell
            if self.shop_mode == "buy":
                self.shop_mode = "sell"
                self.shop_sell_cursor = min(
                    self.shop_sell_cursor, max(0, len(sell_items) - 1))
            else:
                self.shop_mode = "buy"
            return

        if self.shop_mode == "buy":
            if not buy_items:
                return
            if event.key == pygame.K_UP:
                self.shop_cursor = (self.shop_cursor - 1) % len(buy_items)
            elif event.key == pygame.K_DOWN:
                self.shop_cursor = (self.shop_cursor + 1) % len(buy_items)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                item_name = buy_items[self.shop_cursor]
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
                self.shop_sell_cursor = (self.shop_sell_cursor - 1) % len(sell_items)
            elif event.key == pygame.K_DOWN:
                self.shop_sell_cursor = (self.shop_sell_cursor + 1) % len(sell_items)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                entry = sell_items[self.shop_sell_cursor]
                item_name = self.game.party.item_name(entry)
                price = get_sell_price(item_name)
                self.game.party.gold += price
                self.game.party.shared_inventory.pop(self.shop_sell_cursor)
                self.shop_message = f"Sold {item_name} for {price}g!"
                self.shop_message_timer = 1500
                # Clamp cursor
                if self.shop_sell_cursor >= len(self.game.party.shared_inventory):
                    self.shop_sell_cursor = max(
                        0, len(self.game.party.shared_inventory) - 1)

    def _handle_equip_action(self, member):
        """Open the action menu for the selected item/slot."""
        options = self._get_action_options(member)
        if not options:
            self.message = "Empty slot — equip items from inventory"
            self.message_timer = 2000
            return
        self.char_action_menu = True
        self.char_action_cursor = 0
    def _exit_town(self):
        """Leave the town and return to the overworld."""
        # Restore party position on the overworld
        self.game.party.col = self.overworld_col
        self.game.party.row = self.overworld_row
        self.game.change_state("overworld")

    def update(self, dt):
        """Update timers."""
        dt_ms = dt * 1000

        # Quest completion animation blocks everything else
        if self.quest_complete_effect:
            self.quest_complete_effect.update(dt)
            if not self.quest_complete_effect.alive:
                self.quest_complete_effect = None
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

        if self.move_cooldown > 0:
            self.move_cooldown -= dt_ms
            if self.move_cooldown < 0:
                self.move_cooldown = 0

        # Tick use-item animation
        if self.use_item_anim and self.use_item_anim["timer"] > 0:
            self.use_item_anim["timer"] -= dt_ms
            if self.use_item_anim["timer"] <= 0:
                self.use_item_anim = None

    def draw(self, renderer):
        """Draw the town in Ultima III style."""
        if self.showing_shop:
            cursor = (self.shop_cursor if self.shop_mode == "buy"
                      else self.shop_sell_cursor)
            quest = self.game.quest
            quest_complete = (quest is not None
                              and quest.get("status") == "completed")
            renderer.draw_shop_u3(
                self.game.party, self.shop_mode, cursor,
                self.shop_message,
                quest_complete=quest_complete)
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
                tinker_available=self._can_tinker())
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
        msg = self.message if not self.npc_dialogue_active else ""
        quest = self.game.quest
        quest_complete = (quest is not None
                          and quest.get("status") == "completed")
        renderer.draw_town_u3(
            self.game.party,
            self.town_data,
            message=msg,
            quest_complete=quest_complete,
            darkness_active=getattr(self.game, "darkness_active", False),
        )
        # Pickpocket targeting overlay
        if self.pickpocket_targeting and self.pickpocket_targets:
            renderer.draw_pickpocket_targeting(
                self.game.party, self.town_data,
                self.pickpocket_targets, self.pickpocket_cursor)

        # Quest completion celebration overlay
        if self.quest_complete_effect:
            renderer.draw_quest_complete_effect(self.quest_complete_effect)
            return  # blocks dialogue rendering during animation

        # Dialogue box renders on top if active
        if self.message and self.npc_dialogue_active:
            renderer.draw_dialogue_box(self.message)
        # Quest choice overlay (Y/N prompt)
        if self.quest_choice_active:
            renderer.draw_quest_choice_box(
                self.quest_choices, self.quest_choice_cursor)
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
