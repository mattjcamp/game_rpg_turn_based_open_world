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

    def enter(self):
        self._apply_pending_combat_rewards()
        # Skip the first tile-event check so we don't immediately re-enter
        # the town/dungeon we just left.
        self._exit_grace = True
        if self.pending_combat_message:
            self.show_message(self.pending_combat_message, 2500)
            self.pending_combat_message = None
        elif not self.overworld_monsters:
            self.message = "Welcome, adventurers! Use arrow keys to explore."
            self.message_timer = 3000
            # Spawn initial orcs
            self._spawn_orcs()
            # ── TEST: place a spell-casting Dark Mage near the start ──
            self._spawn_test_spellcaster()

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

    def _spawn_test_spellcaster(self):
        """Place a spell-casting Dark Mage 4 tiles east of the party start.

        This is for testing the monster spell system — walk into it to
        trigger a Dark Coven encounter with sleep/curse spells.
        """
        party = self.game.party
        tile_map = self.game.tile_map
        # Try a few offsets near the player
        for dc, dr in [(4, 0), (3, 0), (5, 0), (4, 1), (3, -1), (0, 4)]:
            c, r = party.col + dc, party.row + dr
            if 0 <= c < tile_map.width and 0 <= r < tile_map.height:
                if tile_map.is_walkable(c, r):
                    mage = create_monster("Dark Mage")
                    mage.encounter_template = {
                        "name": "Dark Coven",
                        "monster_names": ["Dark Mage", "Orc Shaman", "Goblin"],
                        "monster_party_tile": "Dark Mage",
                    }
                    mage.col = c
                    mage.row = r
                    self.overworld_monsters.append(mage)
                    return

    # ── Equipment management ─────────────────────────────────────

    # ── Orc spawning ──────────────────────────────────────────────

    def _spawn_orcs(self):
        """Top-up roaming orcs to _MAX_OVERWORLD_ORCS.

        Each candidate position is classified as ``"land"`` or ``"sea"``
        based on the tile type, and the encounter template is chosen to
        match.  Sea encounters can only appear on water tiles, and land
        encounters can only appear on walkable land tiles.

        Also prunes any monster that has somehow ended up on a water tile
        (safety net for movement edge-cases or legacy state).
        """
        tile_map = self.game.tile_map
        party = self.game.party

        # Keep only alive monsters that are NOT standing on invalid terrain.
        # Land monsters on water tiles are removed as a safety net.
        valid = []
        for m in self.overworld_monsters:
            if not m.is_alive():
                continue
            tile_id = tile_map.get_tile(m.col, m.row)
            if getattr(m, "terrain", "land") != "sea" and tile_id == TILE_WATER:
                continue  # land monster on water — remove it
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

                # Determine terrain at this position
                tile_id = tile_map.get_tile(c, r)
                if tile_id == TILE_WATER:
                    terrain = "sea"
                else:
                    # Land monsters require a walkable tile
                    if not tile_map.is_walkable(c, r):
                        continue
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
                    self.game.music.play("title")
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

        # If showing party, character detail, or party inventory, block all other input
        if self.showing_party or self.showing_char_detail is not None or self.showing_party_inv:
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
                and not (pygame.key.get_mods() & (pygame.KMOD_CTRL | pygame.KMOD_META))):
            drow = 1

        if dcol != 0 or drow != 0:
            party = self.game.party
            target_col = party.col + dcol
            target_row = party.row + drow

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
                    self._check_monster_contact()
                    # Occasionally respawn orcs that were killed
                    if random.random() < 0.08:
                        self._spawn_orcs()
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

    # ── Monster helpers ───────────────────────────────────────────

    def _get_monster_at(self, col, row):
        """Return the alive orc at (col, row), or None."""
        for mon in self.overworld_monsters:
            if mon.col == col and mon.row == row and mon.is_alive():
                return mon
        return None

    def _move_monsters(self):
        """Each alive orc wanders randomly, but pursues if within 6 tiles.

        While a repel effect is active, monsters inside its radius flee
        *away* from the party instead of pursuing.
        """
        party = self.game.party
        alive = [m for m in self.overworld_monsters if m.is_alive()]
        occupied = {(m.col, m.row) for m in alive}

        repel = self.repel_effect  # may be None

        for mon in alive:
            occupied.discard((mon.col, mon.row))
            cheb = max(abs(mon.col - party.col), abs(mon.row - party.row))

            # If repel effect is active and monster is within radius, flee
            if repel and cheb <= repel["radius"]:
                # Move away: target is opposite direction from party
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
            occupied.add((mon.col, mon.row))

        # Tick down the lingering repel effect (one step per party move)
        if repel:
            repel["steps_remaining"] -= 1
            if repel["steps_remaining"] <= 0:
                self.repel_effect = None

    def _check_monster_contact(self):
        """If an orc is adjacent to the party, start combat."""
        party = self.game.party
        for mon in self.overworld_monsters:
            if not mon.is_alive():
                continue
            if abs(mon.col - party.col) + abs(mon.row - party.row) == 1:
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
                                  terrain_tile=terrain_tile)
        self.game.change_state("combat")

    # ── Tile events ───────────────────────────────────────────────

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        # After returning from a town/dungeon, skip the first check so
        # the player isn't immediately prompted to re-enter.
        if self._exit_grace:
            self._exit_grace = False
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
                    interior_name, party.col, party.row)
                return
            return  # no other tile events inside interiors

        # ── Overworld tile_link check (highest priority) ──
        # An explicit tile_link overrides any tile-type behaviour so the
        # designer can place an interior/town entrance on any tile graphic.
        pcol, prow = party.col, party.row
        tmap = self.game.tile_map
        link = tmap.tile_links.get(f"{pcol},{prow}")
        if link and link.get("interior"):
            link_name = link["interior"]
            # Check if the link target is a town rather than a
            # dungeon-style overworld interior.  Towns live in
            # town_data_map and use the dedicated town state.
            town_match = self._find_town_by_name(link_name)
            if town_match is not None:
                # Ensure the town is registered at this tile position
                # so get_town_at() finds it during _show_town_action.
                if (pcol, prow) not in self.game.town_data_map:
                    self.game.town_data_map[(pcol, prow)] = town_match
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

        elif tile_id == TILE_DUNGEON:
            self._show_dungeon_action(pcol, prow)
            return

        elif tile_id == TILE_DUNGEON_CLEARED:
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

    def _enter_overworld_interior(self, interior_name, door_col, door_row):
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

        # Push current state onto the interior stack
        self._overworld_interior_stack.append({
            "col": door_col,
            "row": door_row,
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

        # Collect exit positions and interior-to-interior links
        self._overworld_interior_exit_positions = set()
        self._overworld_interior_links = {}
        exit_positions = []
        first_walkable = None
        entry_placed = False

        for pos_key, td in interior.get("tiles", {}).items():
            parts = pos_key.split(",")
            c, r = int(parts[0]), int(parts[1])
            if td.get("to_overworld"):
                self._overworld_interior_exit_positions.add((c, r))
                exit_positions.append((c, r))
            if td.get("interior"):
                self._overworld_interior_links[(c, r)] = td["interior"]
            # Track any walkable tile as fallback spawn
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
        self._exit_grace = True  # don't re-trigger the tile link immediately
        self.show_message(f"Leaving {leaving_name}...", 1000)

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

    def _show_town_action(self):
        """Show the town entry action screen."""
        pcol, prow = self.game.party.col, self.game.party.row
        town_data = self.game.get_town_at(pcol, prow)
        name = town_data.name if town_data else "Town"
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
        town_state = self.game.states["town"]
        town_state.enter_town(town_data, pcol, prow)
        self.game.change_state("town")

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
        elif event.key == pygame.K_ESCAPE:
            self.dungeon_action_active = False

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
        dungeon_state = self.game.states["dungeon"]
        cache = self.game.dungeon_cache

        # Mark as visited
        self.game.mark_dungeon_visited(pcol, prow)

        if entry_type == "key_dungeon":
            kd = self.game.get_key_dungeon(pcol, prow)
            if kd:
                # If quest hasn't been accepted yet, mask floor names
                # so they don't reveal quest details.
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
            # Random / cleared dungeon — use cached version if available
            cached = cache.get((pcol, prow))
            if cached:
                dungeon_data = cached[0]
            else:
                dungeon_data = generate_dungeon("The Depths")
                cache[(pcol, prow)] = [dungeon_data]
            dungeon_state.enter_dungeon(dungeon_data, pcol, prow)

        self.dungeon_action_active = False
        self.game.change_state("dungeon")

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
        )
        if self.town_action_active:
            renderer.draw_town_action_screen(
                self.town_action_info, self.town_action_cursor)
        if self.dungeon_action_active:
            renderer.draw_dungeon_action_screen(
                self.dungeon_action_info, self.dungeon_action_cursor)
        if self.level_up_queue:
            renderer.draw_level_up_animation(self.level_up_queue[0])
        if self.showing_help:
            renderer.draw_overworld_help_overlay()
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
