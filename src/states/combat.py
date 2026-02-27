"""
Combat state - tactical top-down combat on a small arena grid.

All 4 party members are placed on the arena and take turns individually.
Each can move with WASD and must be adjacent to the monster to melee attack
(bump-to-attack or menu).  Arrow keys fire ranged attacks when the active
character has a ranged weapon equipped.  The monster chases the closest
party member and attacks when adjacent.
"""

import random
import math
import pygame

from src.states.base_state import BaseState
from src.combat_engine import (
    roll_initiative, roll_attack, roll_damage, roll_d20,
    format_modifier,
)


# ── Arena constants ──────────────────────────────────────────────
ARENA_COLS = 15
ARENA_ROWS = 17

# ── Combat phases ────────────────────────────────────────────────
PHASE_INIT        = "init"
PHASE_PLAYER      = "player"         # menu selection (up/down + enter)
PHASE_PLAYER_DIR  = "player_dir"     # choosing direction for action
PHASE_PLAYER_ACT  = "player_act"
PHASE_PROJECTILE  = "projectile"     # projectile in flight
PHASE_MELEE_ANIM  = "melee_anim"     # melee slash animation
PHASE_FIREBALL    = "fireball"       # fireball in flight
PHASE_HEAL        = "heal"           # heal animation playing
PHASE_MONSTER     = "monster"
PHASE_MONSTER_ACT = "monster_act"
PHASE_EQUIP       = "equip"          # character sheet / equip screen
PHASE_VICTORY     = "victory"
PHASE_DEFEAT      = "defeat"

# ── Fireball constants ──────────────────────────────────────────
FIREBALL_MP_COST  = 5
FIREBALL_SPEED    = 320   # pixels per second (slower than arrow for drama)

# ── Heal constants ─────────────────────────────────────────────
HEAL_MP_COST      = 4

# ── Action indices ───────────────────────────────────────────────
ACTION_MOVE   = 0      # kept for internal use (WASD movement)
ACTION_ATTACK = 1      # kept for internal use (bump-to-attack)
ACTION_CAST   = 2
ACTION_HEAL   = 3
ACTION_SKIP   = 4      # spacebar skip
ACTION_RANGED = 5      # menu ranged attack
ACTION_EQUIP  = 6      # open equip screen (costs turn)

# Menu is built dynamically per character — see _build_menu_actions()

# ── Projectile speed (pixels per second) ─────────────────────────
PROJECTILE_SPEED = 480


class Projectile:
    """A projectile traveling across the arena."""

    def __init__(self, start_col, start_row, end_col, end_row,
                 color=(255, 255, 255), symbol="*"):
        self.start_col = start_col
        self.start_row = start_row
        self.end_col = end_col
        self.end_row = end_row
        self.color = color
        self.symbol = symbol
        self.progress = 0.0  # 0 = start, 1 = arrived
        self.alive = True

    def update(self, dt):
        """Advance the projectile. dt in seconds."""
        # Calculate total travel distance in tiles
        dx = self.end_col - self.start_col
        dy = self.end_row - self.start_row
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.01:
            self.progress = 1.0
            self.alive = False
            return

        # Speed in tiles per second (PROJECTILE_SPEED px / 32 px per tile)
        tiles_per_sec = PROJECTILE_SPEED / 32.0
        self.progress += (tiles_per_sec / dist) * dt

        if self.progress >= 1.0:
            self.progress = 1.0
            self.alive = False

    @property
    def current_col(self):
        return self.start_col + (self.end_col - self.start_col) * self.progress

    @property
    def current_row(self):
        return self.start_row + (self.end_row - self.start_row) * self.progress


class MeleeEffect:
    """A short-lived slash animation at a target tile."""

    DURATION = 0.35  # seconds

    def __init__(self, col, row, direction, color=(255, 255, 255)):
        self.col = col
        self.row = row
        self.direction = direction  # (dcol, drow)
        self.color = color
        self.timer = self.DURATION
        self.alive = True

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = 0
            self.alive = False

    @property
    def progress(self):
        """0 = start, 1 = done."""
        return 1.0 - (self.timer / self.DURATION)


class HitEffect:
    """A flash/shake on a target when they take damage."""

    DURATION = 0.3  # seconds

    def __init__(self, col, row, damage=0):
        self.col = col
        self.row = row
        self.damage = damage
        self.timer = self.DURATION
        self.alive = True

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = 0
            self.alive = False

    @property
    def progress(self):
        return 1.0 - (self.timer / self.DURATION)


class FireballEffect:
    """An animated fireball traveling across the arena."""

    def __init__(self, start_col, start_row, end_col, end_row):
        self.start_col = start_col
        self.start_row = start_row
        self.end_col = end_col
        self.end_row = end_row
        self.progress = 0.0  # 0 = start, 1 = arrived
        self.alive = True
        self.radius = 6  # base visual radius in pixels

    def update(self, dt):
        """Advance the fireball. dt in seconds."""
        dx = self.end_col - self.start_col
        dy = self.end_row - self.start_row
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.01:
            self.progress = 1.0
            self.alive = False
            return

        tiles_per_sec = FIREBALL_SPEED / 32.0
        self.progress += (tiles_per_sec / dist) * dt

        if self.progress >= 1.0:
            self.progress = 1.0
            self.alive = False

    @property
    def current_col(self):
        return self.start_col + (self.end_col - self.start_col) * self.progress

    @property
    def current_row(self):
        return self.start_row + (self.end_row - self.start_row) * self.progress


class FireballExplosion:
    """A brief explosion effect when the fireball hits."""

    DURATION = 0.5

    def __init__(self, col, row):
        self.col = col
        self.row = row
        self.timer = self.DURATION
        self.alive = True

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = 0
            self.alive = False

    @property
    def progress(self):
        return 1.0 - (self.timer / self.DURATION)


class HealEffect:
    """A glowing heal animation over a party member."""

    DURATION = 0.8  # seconds

    def __init__(self, col, row, amount=0):
        self.col = col
        self.row = row
        self.amount = amount
        self.timer = self.DURATION
        self.alive = True

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = 0
            self.alive = False

    @property
    def progress(self):
        return 1.0 - (self.timer / self.DURATION)


class CombatState(BaseState):
    """Handles a single combat encounter on a tactical arena."""

    def __init__(self, game):
        super().__init__(game)
        self.monster = None
        self.phase = PHASE_INIT
        self.selected_action = 0
        self.menu_actions = []  # dynamic menu: [(action_id, label), ...]
        self.directing_action = None  # which action is being directed

        # Equip screen state
        self.equip_cursor = 0           # cursor in equip/item list
        self.equip_action_menu = False  # True when action popup is open
        self.equip_action_cursor = 0    # selected option in action popup
        self.equip_examining = None     # item name being examined
        self.combat_log = []
        self.phase_timer = 0

        # Active fighter index (which party member's turn it is)
        self.active_idx = 0
        self.fighters = []        # list of alive PartyMembers in combat
        self.fighter_positions = {}  # member -> (col, row)
        self.defending = {}       # member -> bool

        # Monster arena position
        self.monster_col = ARENA_COLS - 4
        self.monster_row = ARENA_ROWS // 2

        # Temporary combat message
        self.combat_message = ""
        self.combat_msg_timer = 0

        # Projectile animation
        self.projectiles = []     # active Projectile objects
        self._pending_ranged = None  # deferred attack resolution after anim

        # Melee / hit effects
        self.melee_effects = []   # active MeleeEffect objects
        self.hit_effects = []     # active HitEffect objects
        self._pending_melee = None  # deferred melee resolution after anim

        # Fireball effects
        self.fireballs = []           # active FireballEffect objects
        self.fireball_explosions = [] # active FireballExplosion objects
        self._pending_fireball = None # deferred fireball resolution

        # Heal effects
        self.heal_effects = []        # active HealEffect objects

        # Callback info for returning to source state
        self.source_state = "dungeon"
        self.monster_ref = None
        self.monster_map_col = 0    # monster's position on dungeon map
        self.monster_map_row = 0

    # ── Arena helpers ────────────────────────────────────────────

    @staticmethod
    def _is_arena_wall(col, row):
        """True if the tile is part of the arena perimeter wall."""
        return col <= 0 or col >= ARENA_COLS - 1 or row <= 0 or row >= ARENA_ROWS - 1

    def _is_adjacent_to_monster(self, col, row):
        """True if (col, row) is adjacent to the monster (Chebyshev dist 1)."""
        dx = abs(col - self.monster_col)
        dy = abs(row - self.monster_row)
        return max(dx, dy) == 1

    def _is_occupied_by_ally(self, col, row, exclude=None):
        """True if another party member is standing on (col, row)."""
        for member, (mc, mr) in self.fighter_positions.items():
            if member is exclude:
                continue
            if mc == col and mr == row and member.is_alive():
                return True
        return False

    @property
    def active_fighter(self):
        """The party member whose turn it is."""
        if 0 <= self.active_idx < len(self.fighters):
            return self.fighters[self.active_idx]
        return None

    @property
    def active_col(self):
        f = self.active_fighter
        if f and f in self.fighter_positions:
            return self.fighter_positions[f][0]
        return 3

    @property
    def active_row(self):
        f = self.active_fighter
        if f and f in self.fighter_positions:
            return self.fighter_positions[f][1]
        return ARENA_ROWS // 2

    def _is_adjacent(self):
        """True if the active fighter is adjacent to the monster."""
        return self._is_adjacent_to_monster(self.active_col, self.active_row)

    # ── Setup ────────────────────────────────────────────────────

    def start_combat(self, fighter, monster, source_state="dungeon"):
        """Start combat. fighter param kept for compatibility but we use full party.
        For overworld encounters, the monster is an Orc Warband (two orcs combined)
        and two orc sprites are displayed."""
        self.monster = monster
        self.source_state = source_state
        self.monster_ref = monster
        # Remember where the monster was on the dungeon/overworld map
        self.monster_map_col = monster.col
        self.monster_map_row = monster.row
        self.combat_log = []
        self.phase = PHASE_INIT
        self.selected_action = 0
        self.phase_timer = 0
        self.combat_message = ""
        self.combat_msg_timer = 0
        self.projectiles = []
        self._pending_ranged = None
        self.melee_effects = []
        self.hit_effects = []
        self._pending_melee = None
        self.fireballs = []
        self.fireball_explosions = []
        self._pending_fireball = None
        self.heal_effects = []

        # Gather alive party members
        self.fighters = [m for m in self.game.party.members if m.is_alive()]
        self.active_idx = 0
        self.defending = {m: False for m in self.fighters}

        # Place party members near the bottom, randomly spread out
        self.fighter_positions = {}
        bottom_zone_start = ARENA_ROWS - 5  # rows 12-15 in a 17-row arena
        used = set()
        for member in self.fighters:
            for _attempt in range(30):
                col = random.randint(2, ARENA_COLS - 3)
                row = random.randint(bottom_zone_start, ARENA_ROWS - 2)
                if (col, row) not in used:
                    self.fighter_positions[member] = (col, row)
                    used.add((col, row))
                    break

        # Monster near the top, randomly placed
        for _attempt in range(30):
            mc = random.randint(3, ARENA_COLS - 4)
            mr = random.randint(2, 5)
            if (mc, mr) not in used:
                break
        self.monster_col = mc
        self.monster_row = mr

        # Keep a reference to the first fighter for backward compat
        self.fighter = fighter

    def enter(self):
        self.combat_log.append(
            f"--- Party vs {self.monster.name}! ---"
        )
        self.combat_log.append(
            f"{len(self.fighters)} party members engage!"
        )
        self.phase = PHASE_PLAYER
        self.active_idx = 0
        self._announce_turn()

    def exit(self):
        pass

    def _announce_turn(self):
        """Add a log entry for whose turn it is."""
        f = self.active_fighter
        if f:
            ranged_hint = " [RANGED]" if f.is_ranged(self.game.party) else ""
            self.combat_log.append(f"-- {f.name}'s turn --{ranged_hint}")
        self._rebuild_menu()

    def _rebuild_menu(self):
        """Build the dynamic action menu for the current fighter."""
        f = self.active_fighter
        self.menu_actions = []  # list of (action_id, label)
        if not f:
            return
        if f.is_ranged(self.game.party):
            label = "Range Attack"
            if f.is_throwable_weapon():
                ammo = self._count_throwable(f)
                label += f" (x{ammo})"
            elif f.uses_ammo():
                ammo = self.game.party.inv_get_charges(f.get_ammo_type())
                label += f" (x{ammo})"
            self.menu_actions.append((ACTION_RANGED, label))
        if f.can_cast_sorcerer() and f.current_mp >= FIREBALL_MP_COST:
            self.menu_actions.append((ACTION_CAST, f"Cast ({f.current_mp}MP)"))
        if f.can_cast_priest() and f.current_mp >= HEAL_MP_COST:
            self.menu_actions.append((ACTION_HEAL, f"Heal ({f.current_mp}MP)"))
        # Equip is always available
        self.menu_actions.append((ACTION_EQUIP, "Equip"))
        self.selected_action = 0

    # ── Input ────────────────────────────────────────────────────

    def handle_input(self, events, keys_pressed):
        # During animation phases, no input
        if self.phase in (PHASE_PROJECTILE, PHASE_MELEE_ANIM, PHASE_FIREBALL, PHASE_HEAL):
            return

        # Equip screen handles its own input
        if self.phase == PHASE_EQUIP:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self._handle_equip_input(event)
            return

        # Speed up non-player phases with Space/Enter
        if self.phase not in (PHASE_PLAYER, PHASE_PLAYER_DIR):
            for event in events:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        if self.phase_timer > 300:
                            self.phase_timer = 300
            return

        for event in events:
            if event.type != pygame.KEYDOWN:
                continue

            # ── PHASE_PLAYER: menu navigation + WASD move + spacebar skip ──
            if self.phase == PHASE_PLAYER:
                if event.key == pygame.K_UP:
                    if self.menu_actions:
                        self.selected_action = (self.selected_action - 1) % len(self.menu_actions)
                elif event.key == pygame.K_DOWN:
                    if self.menu_actions:
                        self.selected_action = (self.selected_action + 1) % len(self.menu_actions)
                elif event.key == pygame.K_RETURN:
                    if self.menu_actions:
                        self._confirm_action()
                elif event.key == pygame.K_SPACE:
                    # Spacebar skips turn
                    f = self.active_fighter
                    if f:
                        self.combat_log.append(f"{f.name} skips their turn.")
                    self._end_fighter_turn()
                # WASD direct movement + bump-to-attack
                elif event.key == pygame.K_w:
                    self._try_arena_move(0, -1)
                elif event.key == pygame.K_s:
                    self._try_arena_move(0, 1)
                elif event.key == pygame.K_a:
                    self._try_arena_move(-1, 0)
                elif event.key == pygame.K_d:
                    self._try_arena_move(1, 0)

            # ── PHASE_PLAYER_DIR: directional input ──
            elif self.phase == PHASE_PLAYER_DIR:
                dcol, drow = 0, 0
                if event.key == pygame.K_UP:
                    drow = -1
                elif event.key == pygame.K_DOWN:
                    drow = 1
                elif event.key == pygame.K_LEFT:
                    dcol = -1
                elif event.key == pygame.K_RIGHT:
                    dcol = 1
                elif event.key == pygame.K_ESCAPE:
                    # Cancel back to menu
                    self.phase = PHASE_PLAYER
                    self.directing_action = None
                    continue

                if dcol != 0 or drow != 0:
                    self._execute_directed_action(dcol, drow)

    def _confirm_action(self):
        """Player confirmed a menu selection — enter direction mode or act."""
        if not self.menu_actions:
            return
        action_id, _label = self.menu_actions[self.selected_action]

        if action_id == ACTION_EQUIP:
            # Open the equip screen for the active fighter
            self.equip_cursor = 0
            self.equip_action_menu = False
            self.equip_action_cursor = 0
            self.equip_examining = None
            self.phase = PHASE_EQUIP
            return

        # Directional actions (ranged, cast, heal)
        self.directing_action = action_id
        self.phase = PHASE_PLAYER_DIR

    # ── Equip screen helpers ──────────────────────────────────────

    def _equip_get_item_at_cursor(self, member):
        """Return the item name at the current equip cursor position."""
        idx = self.equip_cursor
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            return member.equipped.get(slot_keys[idx])
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                return member.inventory[inv_idx]
        return None

    def _equip_get_action_options(self, member):
        """Build the action options for the current equip cursor position."""
        from src.party import WEAPONS, ARMORS
        idx = self.equip_cursor
        options = []
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            slot = slot_keys[idx]
            current = member.equipped.get(slot)
            if current:
                options.append("UNEQUIP")
                options.append("EXAMINE")
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                item_name = member.inventory[inv_idx]
                if item_name in ARMORS or item_name in WEAPONS:
                    options.append("EQUIP")
                options.append("EXAMINE")
        return options

    def _handle_equip_input(self, event):
        """Handle input while the equip screen is open during combat."""
        f = self.active_fighter
        if not f:
            return

        # Examining an item — close on any key
        if self.equip_examining is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.equip_examining = None
            return

        # Action popup is open
        if self.equip_action_menu:
            options = self._equip_get_action_options(f)
            if not options:
                self.equip_action_menu = False
                return
            if event.key == pygame.K_UP:
                self.equip_action_cursor = (self.equip_action_cursor - 1) % len(options)
            elif event.key == pygame.K_DOWN:
                self.equip_action_cursor = (self.equip_action_cursor + 1) % len(options)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                chosen = options[self.equip_action_cursor]
                idx = self.equip_cursor
                if chosen == "EXAMINE":
                    self.equip_examining = self._equip_get_item_at_cursor(f)
                    return
                elif chosen == "EQUIP":
                    inv_idx = idx - 4
                    if inv_idx < len(f.inventory):
                        f.equip_item(f.inventory[inv_idx])
                elif chosen == "UNEQUIP":
                    if idx < 4:
                        slot_keys = ["right_hand", "left_hand", "body", "head"]
                        if not f.unequip_slot(slot_keys[idx]):
                            self.combat_log.append(f"Cannot remove basic {f.equipped.get(slot_keys[idx], 'gear')}!")
                self.equip_action_menu = False
                # Clamp cursor
                total = 4 + len(f.inventory)
                if self.equip_cursor >= total:
                    self.equip_cursor = max(0, total - 1)
            elif event.key == pygame.K_ESCAPE:
                self.equip_action_menu = False
            return

        # Main equip screen navigation
        total_rows = 4 + len(f.inventory)

        if event.key == pygame.K_ESCAPE:
            # Close equip screen — costs the turn
            self.combat_log.append(f"{f.name} changes equipment.")
            self._rebuild_menu()
            self._end_fighter_turn()
        elif event.key == pygame.K_UP:
            if total_rows > 0:
                self.equip_cursor = (self.equip_cursor - 1) % total_rows
        elif event.key == pygame.K_DOWN:
            if total_rows > 0:
                self.equip_cursor = (self.equip_cursor + 1) % total_rows
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Open action popup for selected item/slot
            self.equip_action_menu = True
            self.equip_action_cursor = 0

    def _execute_directed_action(self, dcol, drow):
        """Execute the chosen action in the given direction."""
        action = self.directing_action

        if action == ACTION_MOVE:
            self._try_arena_move(dcol, drow)

        elif action == ACTION_ATTACK:
            f = self.active_fighter
            if f:
                # Check if monster is adjacent in that direction — melee
                col, row = self.fighter_positions[f]
                tc, tr = col + dcol, row + drow
                if tc == self.monster_col and tr == self.monster_row:
                    self._player_attack_animated(dcol, drow)
                elif f.is_ranged(self.game.party):
                    self._fire_ranged(dcol, drow)
                else:
                    self._try_melee_directional(dcol, drow)

        elif action == ACTION_RANGED:
            self._fire_ranged(dcol, drow)

        elif action == ACTION_CAST:
            self._fire_fireball(dcol, drow)

        elif action == ACTION_HEAL:
            self._cast_heal(dcol, drow)

    # ── Player actions ───────────────────────────────────────────

    def _try_arena_move(self, dcol, drow):
        """Move the active fighter in the arena. Bump-attacks the monster."""
        f = self.active_fighter
        if not f:
            return

        col, row = self.fighter_positions[f]
        new_col = col + dcol
        new_row = row + drow

        # Bump attack: moving into the monster's tile
        if new_col == self.monster_col and new_row == self.monster_row:
            self._player_attack()
            return

        # Can't walk onto another ally
        if self._is_occupied_by_ally(new_col, new_row, exclude=f):
            return

        # Normal movement
        if not self._is_arena_wall(new_col, new_row):
            self.fighter_positions[f] = (new_col, new_row)
            # Moving ends this fighter's turn
            self._end_fighter_turn()

    def _execute_player_action(self):
        action = self.selected_action
        if action == ACTION_ATTACK:
            f = self.active_fighter
            if f and self._is_adjacent():
                # Always prefer melee when adjacent
                self._player_attack()
            elif f and f.is_ranged(self.game.party):
                # For ranged fighters, menu Attack fires toward monster
                self._fire_ranged_at_monster()
            else:
                self.combat_message = "Too far! Move next to the enemy."
                self.combat_msg_timer = 1200
        elif action == ACTION_DEFEND:
            self._player_defend()
        elif action == ACTION_FLEE:
            self._player_flee()

    # ── Ranged attack ────────────────────────────────────────────

    def _count_throwable(self, fighter):
        """Count how many of the fighter's weapon are available to throw."""
        wname = fighter.weapon
        # Count in personal inventory + shared stash (equipped one is kept)
        count = fighter.inventory.count(wname)
        count += self.game.party.inv_count(wname)
        return count

    def _consume_throwable(self, fighter):
        """Remove one of the fighter's weapon from inventory for throwing."""
        wname = fighter.weapon
        # Take from personal inventory first, then shared stash
        if wname in fighter.inventory:
            fighter.inventory.remove(wname)
            return True
        removed = self.game.party.inv_remove(wname)
        return removed is not None

    def _fire_ranged(self, dcol, drow):
        """Fire a ranged attack in the given direction."""
        f = self.active_fighter
        if not f or not f.is_ranged(self.game.party):
            if f and f.is_throwable_weapon():
                self.combat_log.append(f"{f.name} is out of {f.weapon}s to throw!")
            return

        # Consume ammo for throwable weapons (daggers, etc.)
        if f.is_throwable_weapon():
            if not self._consume_throwable(f):
                self.combat_log.append(f"{f.name} has no {f.weapon}s left to throw!")
                return
            ammo_left = self._count_throwable(f)
            ammo_note = f" ({ammo_left} left)"
        elif f.uses_ammo():
            ammo_type = f.get_ammo_type()
            if not self.game.party.inv_consume_charge(ammo_type):
                self.combat_log.append(f"{f.name} is out of {ammo_type.lower()}!")
                return
            ammo_left = self.game.party.inv_get_charges(ammo_type)
            ammo_note = f" ({ammo_left} {ammo_type.lower()} left)"
        else:
            ammo_note = ""

        col, row = self.fighter_positions[f]

        # Trace a ray from the fighter in direction (dcol, drow)
        # to find the monster or hit a wall
        tc, tr = col + dcol, row + drow
        hit_monster = False
        end_col, end_row = col, row

        while not self._is_arena_wall(tc, tr):
            if tc == self.monster_col and tr == self.monster_row:
                hit_monster = True
                end_col, end_row = tc, tr
                break
            tc += dcol
            tr += drow

        if not hit_monster:
            # Arrow flies to wall edge
            # Step back to last non-wall tile
            end_col = tc - dcol
            end_row = tr - drow
            if end_col == col and end_row == row:
                end_col = tc
                end_row = tr

        # Determine projectile color based on weapon
        proj_color = (255, 200, 80)  # default gold arrow
        if "bow" in f.weapon.lower():
            proj_color = (255, 255, 200)  # pale arrow
        elif "sling" in f.weapon.lower():
            proj_color = (180, 180, 180)  # gray stone
        elif "dagger" in f.weapon.lower():
            proj_color = (200, 220, 240)  # silver

        proj = Projectile(col, row, end_col, end_row,
                          color=proj_color, symbol=">" if dcol > 0 else
                          "<" if dcol < 0 else "v" if drow > 0 else "^")
        self.projectiles.append(proj)

        # Defer attack resolution until projectile arrives
        self._pending_ranged = {
            "fighter": f,
            "hit_monster": hit_monster,
        }

        self.phase = PHASE_PROJECTILE
        if "dagger" in f.weapon.lower():
            self.combat_log.append(f"{f.name} throws {f.weapon}!{ammo_note}")
        else:
            self.combat_log.append(f"{f.name} fires {f.weapon}!{ammo_note}")

    def _fire_ranged_at_monster(self):
        """Fire toward the monster directly (from menu Attack)."""
        f = self.active_fighter
        if not f:
            return

        col, row = self.fighter_positions[f]
        mc, mr = self.monster_col, self.monster_row

        # Determine dominant direction to monster
        dx = mc - col
        dy = mr - row

        if abs(dx) >= abs(dy):
            dcol = 1 if dx > 0 else -1
            drow = 0
        else:
            dcol = 0
            drow = 1 if dy > 0 else -1

        self._fire_ranged(dcol, drow)

    def _resolve_ranged(self):
        """Called when the projectile arrives. Resolve hit/miss."""
        info = self._pending_ranged
        self._pending_ranged = None

        if not info:
            self._end_fighter_turn()
            return

        f = info["fighter"]
        hit_monster = info["hit_monster"]

        if not hit_monster:
            self.combat_log.append(f"{f.name}'s shot misses the target!")
            self._end_fighter_turn()
            return

        # Roll attack
        self.defending[f] = False
        atk_bonus = f.get_attack_bonus()
        hit, roll, total, crit = roll_attack(atk_bonus, self.monster.ac)

        if crit:
            self.combat_log.append(
                f"{f.name} rolls {roll} — CRITICAL HIT!"
            )
        elif hit:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {self.monster.ac} — Hit!"
            )
        else:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {self.monster.ac} — Miss!"
            )

        if hit:
            dice_count, dice_sides, dmg_bonus = f.get_damage_dice()
            damage = roll_damage(dice_count, dice_sides, dmg_bonus, critical=crit)
            self.monster.hp = max(0, self.monster.hp - damage)
            self.combat_log.append(
                f"{f.name} deals {damage} damage with {f.weapon}!"
            )
            # Spawn a hit flash on the monster
            self.hit_effects.append(
                HitEffect(self.monster_col, self.monster_row, damage))

        if not self.monster.is_alive():
            self.phase = PHASE_VICTORY
            self.phase_timer = 2500
            xp = self.monster.xp_reward
            gold = self.monster.gold_reward
            for m in self.fighters:
                if m.is_alive():
                    m.exp += xp
            self.game.party.gold += gold
            self.combat_log.append(
                f"{self.monster.name} is defeated! +{xp} XP each, +{gold} gold!"
            )
        else:
            self._end_fighter_turn()

    # ── Melee attack ─────────────────────────────────────────────

    def _try_melee_directional(self, dcol, drow):
        """Arrow key melee: attack the monster if it's in the given direction."""
        f = self.active_fighter
        if not f:
            return

        col, row = self.fighter_positions[f]
        target_col = col + dcol
        target_row = row + drow

        # Check if monster is in that direction (adjacent)
        if target_col == self.monster_col and target_row == self.monster_row:
            self._player_attack_animated(dcol, drow)
        else:
            # Nothing in that direction — show a quick slash anyway?
            # No, only attack when there's a target
            pass

    def _player_attack_animated(self, dcol=0, drow=0):
        """Start a melee attack with slash animation, then resolve."""
        f = self.active_fighter
        if not f:
            return

        # Determine slash direction from fighter to monster if not provided
        if dcol == 0 and drow == 0:
            col, row = self.fighter_positions[f]
            dcol = 1 if self.monster_col > col else -1 if self.monster_col < col else 0
            drow = 1 if self.monster_row > row else -1 if self.monster_row < row else 0

        # Class color for the slash
        from src.renderer import Renderer
        slash_color = Renderer._CLASS_COLORS.get(
            f.char_class.lower(), (255, 255, 255))

        # Create a melee slash effect at the monster's position
        effect = MeleeEffect(self.monster_col, self.monster_row,
                             (dcol, drow), color=slash_color)
        self.melee_effects.append(effect)

        # Defer the attack resolution
        self._pending_melee = {"fighter": f}
        self.phase = PHASE_MELEE_ANIM
        self.combat_log.append(f"{f.name} attacks with {f.weapon}!")

    def _player_attack(self):
        """Melee attack — now always animated."""
        self._player_attack_animated()

    def _resolve_melee(self):
        """Called when the melee slash animation finishes. Resolve hit/miss."""
        info = self._pending_melee
        self._pending_melee = None

        if not info:
            self._end_fighter_turn()
            return

        f = info["fighter"]
        self.defending[f] = False
        atk_bonus = f.get_attack_bonus()
        hit, roll, total, crit = roll_attack(atk_bonus, self.monster.ac)

        if crit:
            self.combat_log.append(
                f"{f.name} rolls {roll} — CRITICAL HIT!"
            )
        elif hit:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {self.monster.ac} — Hit!"
            )
        else:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {self.monster.ac} — Miss!"
            )

        if hit:
            dice_count, dice_sides, dmg_bonus = f.get_damage_dice()
            damage = roll_damage(dice_count, dice_sides, dmg_bonus, critical=crit)
            self.monster.hp = max(0, self.monster.hp - damage)
            self.combat_log.append(
                f"{f.name} deals {damage} damage with {f.weapon}!"
            )
            # Spawn a hit flash on the monster
            self.hit_effects.append(
                HitEffect(self.monster_col, self.monster_row, damage))

        if not self.monster.is_alive():
            self.phase = PHASE_VICTORY
            self.phase_timer = 2500
            xp = self.monster.xp_reward
            gold = self.monster.gold_reward
            for m in self.fighters:
                if m.is_alive():
                    m.exp += xp
            self.game.party.gold += gold
            self.combat_log.append(
                f"{self.monster.name} is defeated! +{xp} XP each, +{gold} gold!"
            )
        else:
            self._end_fighter_turn()

    # ── Fireball casting ─────────────────────────────────────────

    def _fire_fireball(self, dcol, drow):
        """Cast a fireball in the given direction. Costs MP, deals INT-based damage."""
        f = self.active_fighter
        if not f:
            return

        # Check if character can cast sorcerer spells
        if not f.can_cast_sorcerer():
            self.combat_log.append(f"{f.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Check MP
        if f.current_mp < FIREBALL_MP_COST:
            self.combat_log.append(f"{f.name} doesn't have enough MP! (need {FIREBALL_MP_COST})")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Deduct MP
        f.current_mp -= FIREBALL_MP_COST

        col, row = self.fighter_positions[f]

        # Trace ray to find monster or wall
        tc, tr = col + dcol, row + drow
        hit_monster = False
        end_col, end_row = col, row

        while not self._is_arena_wall(tc, tr):
            if tc == self.monster_col and tr == self.monster_row:
                hit_monster = True
                end_col, end_row = tc, tr
                break
            tc += dcol
            tr += drow

        if not hit_monster:
            end_col = tc - dcol
            end_row = tr - drow
            if end_col == col and end_row == row:
                end_col = tc
                end_row = tr

        fb = FireballEffect(col, row, end_col, end_row)
        self.fireballs.append(fb)

        self._pending_fireball = {
            "fighter": f,
            "hit_monster": hit_monster,
            "end_col": end_col,
            "end_row": end_row,
        }

        self.phase = PHASE_FIREBALL
        self.combat_log.append(
            f"{f.name} casts FIREBALL! (-{FIREBALL_MP_COST} MP)"
        )

    def _resolve_fireball(self):
        """Called when the fireball arrives. Resolve damage."""
        info = self._pending_fireball
        self._pending_fireball = None

        if not info:
            self._end_fighter_turn()
            return

        f = info["fighter"]
        hit_monster = info["hit_monster"]
        end_col = info["end_col"]
        end_row = info["end_row"]

        # Spawn explosion effect at impact point
        self.fireball_explosions.append(FireballExplosion(end_col, end_row))

        if not hit_monster:
            self.combat_log.append(f"{f.name}'s fireball fizzles against the wall!")
            self._end_fighter_turn()
            return

        # Fireball always hits — no attack roll needed, uses INT for damage
        # Damage: 2d8 + INT modifier (serious damage!)
        int_mod = f.int_mod
        damage = 0
        for _ in range(2):
            damage += random.randint(1, 8)
        damage += int_mod
        damage = max(1, damage)

        self.monster.hp = max(0, self.monster.hp - damage)
        self.combat_log.append(
            f"FIREBALL hits {self.monster.name} for {damage} damage!"
        )
        self.hit_effects.append(
            HitEffect(self.monster_col, self.monster_row, damage))

        if not self.monster.is_alive():
            self.phase = PHASE_VICTORY
            self.phase_timer = 2500
            xp = self.monster.xp_reward
            gold = self.monster.gold_reward
            for m in self.fighters:
                if m.is_alive():
                    m.exp += xp
            self.game.party.gold += gold
            self.combat_log.append(
                f"{self.monster.name} is defeated! +{xp} XP each, +{gold} gold!"
            )
        else:
            self._end_fighter_turn()

    # ── Heal casting ──────────────────────────────────────────────

    def _cast_heal(self, dcol, drow):
        """Cast a heal in the given direction. Targets the first ally in that line."""
        f = self.active_fighter
        if not f:
            return

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast healing spells!")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Check MP
        if f.current_mp < HEAL_MP_COST:
            self.combat_log.append(f"{f.name} doesn't have enough MP! (need {HEAL_MP_COST})")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        col, row = self.fighter_positions[f]

        # Ray-trace in the chosen direction to find the first alive ally
        target = None
        tc, tr = col + dcol, row + drow
        while not self._is_arena_wall(tc, tr):
            for member in self.fighters:
                if member is f or not member.is_alive():
                    continue
                mc, mr = self.fighter_positions.get(member, (-1, -1))
                if mc == tc and mr == tr:
                    target = member
                    break
            if target:
                break
            tc += dcol
            tr += drow

        if target is None:
            self.combat_log.append(f"No ally in that direction!")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Deduct MP
        f.current_mp -= HEAL_MP_COST

        # Calculate heal amount: 1d8 + WIS modifier
        wis_mod = f.wis_mod
        heal_amount = random.randint(1, 8) + wis_mod
        heal_amount = max(1, heal_amount)

        # Apply healing (cap at max HP)
        old_hp = target.hp
        target.hp = min(target.max_hp, target.hp + heal_amount)
        actual_heal = target.hp - old_hp

        # Spawn heal effect over the target
        tcol, trow = self.fighter_positions.get(target, (3, 5))
        self.heal_effects.append(HealEffect(tcol, trow, actual_heal))

        self.phase = PHASE_HEAL
        self.combat_log.append(
            f"{f.name} casts HEAL on {target.name}! (+{actual_heal} HP, -{HEAL_MP_COST} MP)"
        )

    def _player_defend(self):
        f = self.active_fighter
        if not f:
            return
        self.defending[f] = True
        self.combat_log.append(
            f"{f.name} takes a defensive stance! (+2 AC)"
        )
        self._end_fighter_turn()

    def _player_flee(self):
        f = self.active_fighter
        if not f:
            return
        self.defending[f] = False
        roll = roll_d20()
        total = roll + f.dex_mod
        dc = 10

        if total >= dc:
            self.combat_log.append(
                f"{f.name} rolls {roll} "
                f"({format_modifier(f.dex_mod)}) = {total} — Escaped!"
            )
            self.phase = PHASE_VICTORY
            self.phase_timer = 1500
            self.combat_log.append("Your party flees the battle!")
        else:
            self.combat_log.append(
                f"{f.name} rolls {roll} "
                f"({format_modifier(f.dex_mod)}) = {total} vs DC {dc} — Failed!"
            )
            self._end_fighter_turn()

    def _end_fighter_turn(self):
        """Advance to next alive fighter, or to monster turn if all have acted."""
        self.directing_action = None
        self.active_idx += 1

        # Skip dead fighters
        while (self.active_idx < len(self.fighters)
               and not self.fighters[self.active_idx].is_alive()):
            self.active_idx += 1

        if self.active_idx >= len(self.fighters):
            # All fighters have acted — monster's turn
            self.phase = PHASE_PLAYER_ACT
            self.phase_timer = 400
        else:
            # Next fighter's turn — always reset to PHASE_PLAYER
            self.phase = PHASE_PLAYER
            self.selected_action = 0
            self.directing_action = None
            self._announce_turn()

    # ── Monster actions ──────────────────────────────────────────

    def _monster_turn(self):
        """Monster AI: attack if adjacent to any fighter, otherwise move toward closest."""
        best_dist = 999
        best_target = None
        for member in self.fighters:
            if not member.is_alive():
                continue
            col, row = self.fighter_positions[member]
            dist = max(abs(col - self.monster_col), abs(row - self.monster_row))
            if dist < best_dist:
                best_dist = dist
                best_target = member

        if not best_target:
            self.phase = PHASE_VICTORY
            self.phase_timer = 1500
            return

        # Check adjacency to any alive fighter
        adjacent_targets = []
        for member in self.fighters:
            if not member.is_alive():
                continue
            col, row = self.fighter_positions[member]
            if self._is_adjacent_to_monster(col, row):
                adjacent_targets.append(member)

        if adjacent_targets:
            target = random.choice(adjacent_targets)
            self._monster_attack_player(target)
        else:
            self._monster_move_toward(best_target)
            self.combat_log.append(f"{self.monster.name} moves closer...")
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 500

    def _monster_move_toward(self, target):
        """Step 1 tile toward the target (Chebyshev)."""
        mc, mr = self.monster_col, self.monster_row
        tc, tr = self.fighter_positions[target]

        best_dist = max(abs(mc - tc), abs(mr - tr))
        candidates = []

        for dcol, drow in [
            (0, -1), (0, 1), (-1, 0), (1, 0),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ]:
            nc, nr = mc + dcol, mr + drow
            occupied = False
            for m in self.fighters:
                if m.is_alive() and self.fighter_positions.get(m) == (nc, nr):
                    occupied = True
                    break
            if occupied:
                continue
            if self._is_arena_wall(nc, nr):
                continue
            dist = max(abs(nc - tc), abs(nr - tr))
            if dist < best_dist:
                candidates = [(nc, nr)]
                best_dist = dist
            elif dist == best_dist:
                candidates.append((nc, nr))

        if candidates:
            nc, nr = random.choice(candidates)
            self.monster_col = nc
            self.monster_row = nr

    def _monster_attack_player(self, target):
        """The monster attacks a specific party member."""
        player_ac = target.get_ac()
        if self.defending.get(target, False):
            player_ac += 2

        hit, roll, total, crit = roll_attack(
            self.monster.attack_bonus, player_ac
        )

        ac_display = f"AC {player_ac}"
        if self.defending.get(target, False):
            ac_display += " (def)"

        if crit:
            self.combat_log.append(
                f"{self.monster.name} → {target.name}: rolls {roll} — CRITICAL HIT!"
            )
        elif hit:
            self.combat_log.append(
                f"{self.monster.name} → {target.name}: rolls {roll} "
                f"({format_modifier(self.monster.attack_bonus)}) "
                f"= {total} vs {ac_display} — Hit!"
            )
        else:
            self.combat_log.append(
                f"{self.monster.name} → {target.name}: rolls {roll} "
                f"({format_modifier(self.monster.attack_bonus)}) "
                f"= {total} vs {ac_display} — Miss!"
            )

        if hit:
            damage = roll_damage(
                self.monster.damage_dice,
                self.monster.damage_sides,
                self.monster.damage_bonus,
                critical=crit,
            )
            target.hp = max(0, target.hp - damage)
            self.combat_log.append(
                f"{self.monster.name} deals {damage} damage to {target.name}!"
            )
            # Spawn hit flash on the target party member
            tcol, trow = self.fighter_positions.get(target, (3, 5))
            self.hit_effects.append(HitEffect(tcol, trow, damage))

        if not target.is_alive():
            self.combat_log.append(f"{target.name} has fallen!")

        if not any(m.is_alive() for m in self.fighters):
            self.phase = PHASE_DEFEAT
            self.phase_timer = 2500
            self.combat_log.append("The party has been defeated!")
        else:
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 800

    # ── Phase machine ────────────────────────────────────────────

    def update(self, dt):
        dt_ms = dt * 1000

        # Tick the temporary combat message
        if self.combat_msg_timer > 0:
            self.combat_msg_timer -= dt_ms
            if self.combat_msg_timer <= 0:
                self.combat_message = ""
                self.combat_msg_timer = 0

        # Update all visual effects (always, regardless of phase)
        for fx in self.hit_effects:
            if fx.alive:
                fx.update(dt)
        self.hit_effects = [fx for fx in self.hit_effects if fx.alive]

        # Update fireball explosions (always, visual only)
        for fx in self.fireball_explosions:
            if fx.alive:
                fx.update(dt)
        self.fireball_explosions = [fx for fx in self.fireball_explosions if fx.alive]

        # Update heal effects
        for fx in self.heal_effects:
            if fx.alive:
                fx.update(dt)
        # Check if heal phase is done
        if self.phase == PHASE_HEAL:
            if all(not fx.alive for fx in self.heal_effects):
                self.heal_effects = []
                self._end_fighter_turn()
            return
        self.heal_effects = [fx for fx in self.heal_effects if fx.alive]

        # Update fireballs
        if self.phase == PHASE_FIREBALL:
            for fb in self.fireballs:
                if fb.alive:
                    fb.update(dt)

            if all(not fb.alive for fb in self.fireballs):
                self.fireballs = []
                self._resolve_fireball()
            return

        # Update projectiles
        if self.phase == PHASE_PROJECTILE:
            for proj in self.projectiles:
                if proj.alive:
                    proj.update(dt)

            # Check if all projectiles have arrived
            if all(not p.alive for p in self.projectiles):
                self.projectiles = []
                self._resolve_ranged()
            return

        # Update melee effects
        if self.phase == PHASE_MELEE_ANIM:
            for fx in self.melee_effects:
                if fx.alive:
                    fx.update(dt)

            # Check if all melee effects are done
            if all(not fx.alive for fx in self.melee_effects):
                self.melee_effects = []
                self._resolve_melee()
            return

        if self.phase_timer > 0:
            self.phase_timer -= dt_ms
            if self.phase_timer <= 0:
                self.phase_timer = 0
                self._advance_phase()

    def _advance_phase(self):
        if self.phase == PHASE_PLAYER_ACT:
            self.phase = PHASE_MONSTER
            self.phase_timer = 600
        elif self.phase == PHASE_MONSTER:
            self._monster_turn()
        elif self.phase == PHASE_MONSTER_ACT:
            for m in self.fighters:
                self.defending[m] = False
            self.active_idx = 0
            while (self.active_idx < len(self.fighters)
                   and not self.fighters[self.active_idx].is_alive()):
                self.active_idx += 1
            if self.active_idx >= len(self.fighters):
                self.phase = PHASE_DEFEAT
                self.phase_timer = 2500
            else:
                self.phase = PHASE_PLAYER
                self.selected_action = 0
                self._announce_turn()
        elif self.phase == PHASE_VICTORY:
            self._end_combat(won=True)
        elif self.phase == PHASE_DEFEAT:
            self._end_combat(won=False)

    def _end_combat(self, won):
        if won and self.monster_ref:
            from src.settings import TILE_CHEST
            mc = self.monster_map_col
            mr = self.monster_map_row

            if self.source_state == "dungeon":
                dungeon_state = self.game.states.get("dungeon")
                if dungeon_state and dungeon_state.dungeon_data:
                    ddata = dungeon_state.dungeon_data
                    if self.monster_ref in ddata.monsters:
                        ddata.monsters.remove(self.monster_ref)

                    # Place a treasure chest where the monster stood
                    ddata.tile_map.set_tile(mc, mr, TILE_CHEST)
                    dungeon_state.pending_combat_message = (
                        "Victory! A treasure chest appears!"
                    )

            elif self.source_state == "overworld":
                overworld_state = self.game.states.get("overworld")
                if overworld_state:
                    if self.monster_ref in overworld_state.overworld_monsters:
                        overworld_state.overworld_monsters.remove(self.monster_ref)

                    # Remember the original tile before placing the chest
                    original_tile = self.game.tile_map.get_tile(mc, mr)
                    overworld_state.chest_under_tiles[(mc, mr)] = original_tile

                    # Place a treasure chest where the orc stood
                    self.game.tile_map.set_tile(mc, mr, TILE_CHEST)
                    overworld_state.pending_combat_message = (
                        "Victory! A treasure chest appears!"
                    )

        if not won:
            for m in self.game.party.members:
                if not m.is_alive():
                    m.hp = 1

        self.game.change_state(self.source_state)

    # ── Drawing ──────────────────────────────────────────────────

    def draw(self, renderer):
        if self.phase == PHASE_EQUIP and self.active_fighter:
            f = self.active_fighter
            member_idx = self.fighters.index(f) if f in self.fighters else 0
            # Find the real party index for this member
            real_idx = 0
            for i, m in enumerate(self.game.party.members):
                if m is f:
                    real_idx = i
                    break
            action_opts = self._equip_get_action_options(f) if self.equip_action_menu else None
            renderer.draw_character_sheet_u3(
                f, real_idx, self.equip_cursor,
                self.equip_action_menu, self.equip_action_cursor,
                action_options=action_opts)
            if self.equip_examining:
                renderer.draw_item_examine(self.equip_examining)
            return

        renderer.draw_combat_arena(
            fighter=self.active_fighter or self.fighters[0],
            monster=self.monster,
            combat_log=self.combat_log,
            phase=self.phase,
            selected_action=self.selected_action,
            defending=self.defending.get(self.active_fighter, False) if self.active_fighter else False,
            player_col=self.active_col,
            player_row=self.active_row,
            monster_col=self.monster_col,
            monster_row=self.monster_row,
            is_adjacent=self._is_adjacent(),
            combat_message=self.combat_message,
            fighters=self.fighters,
            fighter_positions=self.fighter_positions,
            active_fighter=self.active_fighter,
            defending_map=self.defending,
            projectiles=self.projectiles,
            melee_effects=self.melee_effects,
            hit_effects=self.hit_effects,
            fireballs=self.fireballs,
            fireball_explosions=self.fireball_explosions,
            heal_effects=self.heal_effects,
            is_warband=False,
            source_state=self.source_state,
            directing_action=self.directing_action,
            menu_actions=self.menu_actions,
        )
