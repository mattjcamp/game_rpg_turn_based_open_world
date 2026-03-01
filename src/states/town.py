"""
Town state - exploring a town interior.

The party walks around inside a town, talks to NPCs by bumping into them,
and can leave through the exit gate to return to the overworld.
"""

import math
import random

import pygame

from src.states.base_state import BaseState
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_EXIT, TILE_DUNGEON,
    TILE_GRASS, TILE_FOREST, TILE_PATH, TILE_WATER, TILE_MOUNTAIN,
    TILE_TOWN,
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


class TownState(BaseState):
    """Handles exploration inside a town."""

    def __init__(self, game):
        super().__init__(game)
        self.town_data = None
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        self.npc_dialogue_active = False
        self.npc_speaking = None
        self.showing_party = False
        self.showing_char_detail = None
        self.char_sheet_cursor = 0
        self.char_sheet_origin = None
        self.char_action_menu = False
        self.char_action_cursor = 0
        self.examining_item = None
        self.showing_party_inv = False
        self.party_inv_cursor = 0
        self.party_inv_choosing = False
        self.party_inv_member = 0
        self.party_inv_action_menu = False
        self.party_inv_action_cursor = 0
        self.choosing_effect = False
        self.effect_list = []
        self.effect_cursor = 0

        # Use-item animation overlay
        self.use_item_anim = None  # dict with effect, timer, duration, text

        # Game log overlay
        self.showing_log = False
        self.log_scroll = 0

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
        else:
            self.move_cooldown = MOVE_REPEAT_DELAY

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        tile_id = self.town_data.tile_map.get_tile(
            self.game.party.col, self.game.party.row
        )
        if tile_id == TILE_EXIT:
            self._exit_town()

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

    def _handle_party_inv_input(self, event):
        """Handle input for the shared party inventory screen.

        The unified cursor covers effect slots, a torch slot,
        and then shared inventory items.
        """
        party = self.game.party
        inv = party.shared_inventory
        members = party.members
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        TORCH_ROW = NUM_EFFECTS
        STASH_START = TORCH_ROW + 1
        total_items = STASH_START + len(inv)

        # Examining an item — close on ESC/Enter/Space
        if self.examining_item is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.examining_item = None
            return

        # Effect chooser is open
        if self.choosing_effect:
            if event.key == pygame.K_ESCAPE:
                self.choosing_effect = False
            elif event.key == pygame.K_UP and self.effect_list:
                self.effect_cursor = (self.effect_cursor - 1) % len(self.effect_list)
            elif event.key == pygame.K_DOWN and self.effect_list:
                self.effect_cursor = (self.effect_cursor + 1) % len(self.effect_list)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.effect_list:
                chosen_eff = self.effect_list[self.effect_cursor]
                eff_idx = self.party_inv_cursor
                slot_key = party.EFFECT_SLOTS[eff_idx]
                party.set_effect(slot_key, chosen_eff["name"])
                self.choosing_effect = False
            return

        # Action menu is open
        if self.party_inv_action_menu:
            options = self._get_party_inv_action_options()
            if not options:
                self.party_inv_action_menu = False
                return
            if event.key == pygame.K_UP:
                self.party_inv_action_cursor = (self.party_inv_action_cursor - 1) % len(options)
            elif event.key == pygame.K_DOWN:
                self.party_inv_action_cursor = (self.party_inv_action_cursor + 1) % len(options)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                chosen = options[self.party_inv_action_cursor]
                self._handle_party_inv_action(chosen)
            elif event.key == pygame.K_ESCAPE:
                self.party_inv_action_menu = False
            return

        # Browsing unified list (equip slots + effect slots + inventory)
        if True:
            if event.key == pygame.K_UP and total_items > 0:
                self.party_inv_cursor = (self.party_inv_cursor - 1) % total_items
            elif event.key == pygame.K_DOWN and total_items > 0:
                self.party_inv_cursor = (self.party_inv_cursor + 1) % total_items
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and total_items > 0:
                options = self._get_party_inv_action_options()
                if options:
                    self.party_inv_action_menu = True
                    self.party_inv_action_cursor = 0
            elif event.key == pygame.K_ESCAPE:
                self.showing_party_inv = False
            elif event.key == pygame.K_p:
                self.showing_party_inv = False
                self.showing_party = False
            else:
                # Number keys 1-4: open character detail sheet
                num = {pygame.K_1: 0, pygame.K_2: 1,
                       pygame.K_3: 2, pygame.K_4: 3}.get(event.key)
                if num is not None and num < len(self.game.party.members):
                    self.showing_party_inv = False
                    self.showing_char_detail = num
                    self.char_sheet_cursor = 0
                    self.char_sheet_origin = "inventory"

    def _handle_party_inv_action(self, chosen):
        """Execute the chosen action on the selected party inventory entry."""
        party = self.game.party
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        TORCH_ROW = NUM_EFFECTS
        STASH_START = TORCH_ROW + 1
        idx = self.party_inv_cursor

        if idx < NUM_EFFECTS:
            # Acting on an effect slot
            slot_key = party.EFFECT_SLOTS[idx]
            if chosen == "ASSIGN EFFECT":
                self.effect_list = party.get_available_effects()
                self.effect_cursor = 0
                self.choosing_effect = True
                self.party_inv_action_menu = False
            elif chosen == "REMOVE":
                party.set_effect(slot_key, None)
                self.party_inv_action_menu = False
        elif idx == TORCH_ROW:
            # Acting on the torch slot
            if chosen == "UNEQUIP":
                party.party_unequip("light")
                self.party_inv_action_menu = False
            elif chosen == "EXAMINE":
                item = party.get_equipped_name("light")
                if item:
                    self.examining_item = item
        else:
            inv_idx = idx - STASH_START
            inv = party.shared_inventory
            if inv_idx < len(inv):
                item_name = party.item_name(inv[inv_idx])
                if chosen == "USE":
                    self._use_party_item(item_name, inv_idx)
                    self.party_inv_action_menu = False
                    new_total = STASH_START + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)
                elif chosen == "EXAMINE":
                    self.examining_item = item_name
                elif chosen.startswith("GIVE TO "):
                    give_name = chosen[8:].strip()
                    for mi, member in enumerate(party.members):
                        if member.name.upper() == give_name:
                            party.give_item_to_member(inv_idx, mi)
                            break
                    self.party_inv_action_menu = False
                    new_total = STASH_START + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)
                elif chosen == "EQUIP → TORCH":
                    party.party_equip(item_name, "light")
                    self.party_inv_action_menu = False
                    new_total = STASH_START + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)

    def _get_party_inv_action_options(self):
        """Build action options for the selected party inventory entry."""
        party = self.game.party
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        TORCH_ROW = NUM_EFFECTS
        STASH_START = TORCH_ROW + 1
        idx = self.party_inv_cursor

        if idx < NUM_EFFECTS:
            slot_key = party.EFFECT_SLOTS[idx]
            current = party.get_effect(slot_key)
            options = []
            if party.get_available_effects():
                options.append("ASSIGN EFFECT")
            if current is not None:
                options.append("REMOVE")
            return options
        elif idx == TORCH_ROW:
            item = party.get_equipped_name("light")
            if item is None:
                return []
            return ["UNEQUIP", "EXAMINE"]
        else:
            inv_idx = idx - STASH_START
            inv = party.shared_inventory
            if inv_idx >= len(inv):
                return []
            options = []
            item_name = party.item_name(inv[inv_idx])
            from src.party import ITEM_INFO
            info = ITEM_INFO.get(item_name, {})
            if info.get("usable", False):
                options.append("USE")
            # Offer torch slot if empty and item is a Torch
            if party.get_equipped_name("light") is None and item_name == "Torch":
                options.append("EQUIP → TORCH")
            for mi, member in enumerate(self.game.party.members):
                options.append(f"GIVE TO {member.name.upper()}")
            options.append("EXAMINE")
            return options

    def _use_party_item(self, item_name, inv_idx):
        """Use a consumable item from the party stash."""
        from src.party import ITEM_INFO
        party = self.game.party
        info = ITEM_INFO.get(item_name, {})
        effect = info.get("effect", "")
        power = info.get("power", 0)

        if effect == "rest":
            # Camping Supplies: restore HP and MP for the whole party
            total_hp = 0
            total_mp = 0
            for m in party.members:
                if m.hp <= 0:
                    continue  # skip dead members
                hp_restore = max(1, int(m.max_hp * 0.35)) + random.randint(1, 8)
                mp_restore = max(1, int(m.max_mp * 0.30)) + random.randint(1, 4)
                old_hp, old_mp = m.hp, getattr(m, "current_mp", 0)
                m.hp = min(m.max_hp, m.hp + hp_restore)
                m.current_mp = min(m.max_mp, getattr(m, "current_mp", 0) + mp_restore)
                total_hp += m.hp - old_hp
                total_mp += m.current_mp - old_mp
            self.game.game_log.append(f"The party rests using {item_name}...")
            self.game.game_log.append(
                f"  Restored {total_hp} HP and {total_mp} MP across the party!")
            self.message = f"Rested! +{total_hp} HP, +{total_mp} MP"
            self.message_timer = 3500
        elif effect == "heal_hp":
            # Single-target heal — heals the most injured member
            best = None
            best_missing = 0
            for m in party.members:
                if m.hp <= 0:
                    continue
                missing = m.max_hp - m.hp
                if missing > best_missing:
                    best_missing = missing
                    best = m
            if best and best_missing > 0:
                heal = power + random.randint(1, 6)
                best.hp = min(best.max_hp, best.hp + heal)
                self.game.game_log.append(
                    f"{best.name} uses {item_name}. (+{heal} HP)")
                self.message = f"{best.name}: +{heal} HP"
                self.message_timer = 3000
            else:
                self.game.game_log.append("Everyone is already at full health!")
                self.message = "Everyone is at full health!"
                self.message_timer = 2500
                return  # don't consume
        elif effect == "heal_mp":
            best = None
            best_missing = 0
            for m in party.members:
                if m.hp <= 0:
                    continue
                missing = m.max_mp - getattr(m, "current_mp", 0)
                if missing > best_missing:
                    best_missing = missing
                    best = m
            if best and best_missing > 0:
                restore = power + random.randint(1, 4)
                best.current_mp = min(best.max_mp,
                                      getattr(best, "current_mp", 0) + restore)
                self.game.game_log.append(
                    f"{best.name} uses {item_name}. (+{restore} MP)")
                self.message = f"{best.name}: +{restore} MP"
                self.message_timer = 3000
            else:
                self.game.game_log.append("Everyone is already at full mana!")
                self.message = "Everyone is at full mana!"
                self.message_timer = 2500
                return  # don't consume
        elif effect == "cure_poison":
            cured = False
            for m in party.members:
                if getattr(m, "poisoned", False):
                    m.poisoned = False
                    self.game.game_log.append(f"{m.name}'s poison was cured!")
                    cured = True
                    break
            if not cured:
                self.game.game_log.append("Nobody is poisoned!")
                self.message = "Nobody is poisoned!"
                self.message_timer = 2500
                return  # don't consume
        else:
            self.game.game_log.append(f"Used {item_name}.")
            self.message = f"Used {item_name}"
            self.message_timer = 2000

        # Start use-item animation
        anim_text = self.message or f"Used {item_name}"
        self.use_item_anim = {
            "effect": effect,
            "timer": 1800,
            "duration": 1800,
            "text": anim_text,
        }

        # Consume: use inv_consume_charge for items with charges, else remove
        entry = party.shared_inventory[inv_idx] if inv_idx < len(party.shared_inventory) else None
        if entry is not None and isinstance(entry, dict) and entry.get("charges", 0) > 0:
            party.inv_consume_charge(item_name)
        else:
            party.inv_remove(item_name)

    def _handle_equip_action(self, member):
        """Open the action menu for the selected item/slot."""
        options = self._get_action_options(member)
        if not options:
            self.message = "Empty slot — equip items from inventory"
            self.message_timer = 2000
            return
        self.char_action_menu = True
        self.char_action_cursor = 0

    def _get_item_at_cursor(self, member):
        """Return the item name at the current char_sheet_cursor position."""
        idx = self.char_sheet_cursor
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            return member.equipped.get(slot_keys[idx])
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                return member.inventory[inv_idx]
        return None

    def _get_action_options(self, member):
        """Build the list of action option keys for the current cursor position."""
        from src.party import PartyMember
        idx = self.char_sheet_cursor
        options = []
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            slot = slot_keys[idx]
            current = member.equipped.get(slot)
            if current:
                options.append("UNEQUIP")
                options.append("RETURN TO PARTY STASH")
                options.append("EXAMINE")
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                item_name = member.inventory[inv_idx]
                from src.party import ITEM_INFO
                info = ITEM_INFO.get(item_name, {})
                if info.get("usable", False):
                    options.append("USE")
                if member.can_use_item(item_name):
                    valid_slots = member.get_valid_slots(item_name)
                    for s in valid_slots:
                        label = PartyMember._SLOT_LABELS[s]
                        options.append(f"EQUIP \u2192 {label}")
                options.append("RETURN TO PARTY STASH")
                options.append("EXAMINE")
        return options

    def _handle_char_action_input(self, event):
        """Handle input while the action menu popup is open."""
        if self.examining_item is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.examining_item = None
            return

        member = self.game.party.members[self.showing_char_detail]
        options = self._get_action_options(member)

        if not options:
            self.char_action_menu = False
            return

        if event.key == pygame.K_UP:
            self.char_action_cursor = (self.char_action_cursor - 1) % len(options)
        elif event.key == pygame.K_DOWN:
            self.char_action_cursor = (self.char_action_cursor + 1) % len(options)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            chosen = options[self.char_action_cursor]
            idx = self.char_sheet_cursor
            if chosen == "EXAMINE":
                self.examining_item = self._get_item_at_cursor(member)
                return
            elif chosen == "USE":
                inv_idx = idx - 4
                if inv_idx < len(member.inventory):
                    item_name = member.inventory[inv_idx]
                    self._use_char_item(member, item_name, inv_idx)
            elif chosen == "UNEQUIP":
                if idx < 4:
                    slot_keys = ["right_hand", "left_hand", "body", "head"]
                    if not member.unequip_slot(slot_keys[idx]):
                        self.message = f"Cannot remove basic {member.equipped.get(slot_keys[idx], 'gear')}!"
                        self.message_timer = 2000
            elif chosen.startswith("EQUIP"):
                inv_idx = idx - 4
                if inv_idx < len(member.inventory):
                    from src.party import PartyMember
                    _label_to_key = {v: k for k, v in PartyMember._SLOT_LABELS.items()}
                    slot_label = chosen.split("\u2192 ", 1)[1].strip()
                    slot_key = _label_to_key.get(slot_label)
                    member.equip_item(member.inventory[inv_idx], slot_key)
            elif chosen == "RETURN TO PARTY STASH":
                if idx < 4:
                    slot_keys = ["right_hand", "left_hand", "body", "head"]
                    member.return_equipped_to_party(slot_keys[idx], self.game.party)
                else:
                    inv_idx = idx - 4
                    if inv_idx < len(member.inventory):
                        member.return_item_to_party(
                            member.inventory[inv_idx], self.game.party)
            self.char_action_menu = False
            total = 4 + len(member.inventory)
            if self.char_sheet_cursor >= total:
                self.char_sheet_cursor = max(0, total - 1)
        elif event.key == pygame.K_ESCAPE:
            self.char_action_menu = False

    def _use_char_item(self, member, item_name, inv_idx):
        """Use a consumable item from a character's personal inventory."""
        from src.party import ITEM_INFO
        info = ITEM_INFO.get(item_name, {})
        effect = info.get("effect", "")
        power = info.get("power", 0)

        if effect == "rest":
            # Rest effect on the individual character
            if member.hp <= 0:
                self.message = f"{member.name} is unconscious!"
                self.message_timer = 2500
                return
            hp_restore = max(1, int(member.max_hp * 0.35)) + random.randint(1, 8)
            mp_restore = max(1, int(member.max_mp * 0.30)) + random.randint(1, 4)
            old_hp, old_mp = member.hp, getattr(member, "current_mp", 0)
            member.hp = min(member.max_hp, member.hp + hp_restore)
            member.current_mp = min(member.max_mp, getattr(member, "current_mp", 0) + mp_restore)
            actual_hp = member.hp - old_hp
            actual_mp = member.current_mp - old_mp
            self.game.game_log.append(
                f"{member.name} rests using {item_name}. (+{actual_hp} HP, +{actual_mp} MP)")
            self.message = f"{member.name}: +{actual_hp} HP, +{actual_mp} MP"
            self.message_timer = 3000
        elif effect == "heal_hp":
            if member.hp <= 0:
                self.message = f"{member.name} is unconscious!"
                self.message_timer = 2500
                return
            missing = member.max_hp - member.hp
            if missing <= 0:
                self.message = f"{member.name} is already at full health!"
                self.message_timer = 2500
                return
            heal = power + random.randint(1, 6)
            member.hp = min(member.max_hp, member.hp + heal)
            self.game.game_log.append(
                f"{member.name} uses {item_name}. (+{heal} HP)")
            self.message = f"{member.name}: +{heal} HP"
            self.message_timer = 3000
        elif effect == "heal_mp":
            if member.hp <= 0:
                self.message = f"{member.name} is unconscious!"
                self.message_timer = 2500
                return
            missing = member.max_mp - getattr(member, "current_mp", 0)
            if missing <= 0:
                self.message = f"{member.name} is already at full mana!"
                self.message_timer = 2500
                return
            restore = power + random.randint(1, 4)
            member.current_mp = min(member.max_mp,
                                    getattr(member, "current_mp", 0) + restore)
            self.game.game_log.append(
                f"{member.name} uses {item_name}. (+{restore} MP)")
            self.message = f"{member.name}: +{restore} MP"
            self.message_timer = 3000
        elif effect == "cure_poison":
            if getattr(member, "poisoned", False):
                member.poisoned = False
                self.game.game_log.append(f"{member.name}'s poison was cured!")
                self.message = f"{member.name}: Poison cured!"
                self.message_timer = 3000
            else:
                self.message = f"{member.name} is not poisoned!"
                self.message_timer = 2500
                return
        else:
            self.game.game_log.append(f"{member.name} used {item_name}.")
            self.message = f"Used {item_name}"
            self.message_timer = 2000

        # Start use-item animation
        anim_text = self.message or f"Used {item_name}"
        self.use_item_anim = {
            "effect": effect,
            "timer": 1800,
            "duration": 1800,
            "text": anim_text,
        }

        # Remove the item from the character's inventory
        if inv_idx < len(member.inventory):
            member.inventory.pop(inv_idx)

    def _exit_town(self):
        """Leave the town and return to the overworld."""
        # Restore party position on the overworld
        self.game.party.col = self.overworld_col
        self.game.party.row = self.overworld_row

        # Restore camera for overworld map
        self.game.camera.map_width = self.game.tile_map.width
        self.game.camera.map_height = self.game.tile_map.height
        self.game.camera.update(self.game.party.col, self.game.party.row)

        self.game.change_state("overworld")

    def show_message(self, text, duration_ms=2000):
        """Display a temporary message."""
        self.message = text
        self.message_timer = duration_ms
        if text:
            self.game.game_log.append(text)

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
                effect_cursor=self.effect_cursor)
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
        )
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
