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
import json
import os
import pygame

from src.states.base_state import BaseState
from src.party import SPELLS_DATA
from src.monster import Monster


class _DualLog(list):
    """A list that also appends each entry to a second target list."""

    def __init__(self, mirror_target):
        super().__init__()
        self._mirror = mirror_target

    def append(self, item):
        super().append(item)
        self._mirror.append(item)
from src.combat_engine import (
    roll_initiative, roll_attack, roll_damage, roll_d20,
    format_modifier,
)

# SPELLS_DATA is imported from src.party (shared across combat and exploration)


# ── Arena constants ──────────────────────────────────────────────
ARENA_COLS = 18
ARENA_ROWS = 21

# ── Combat phases ────────────────────────────────────────────────
PHASE_INIT        = "init"
PHASE_PLAYER      = "player"         # menu selection (up/down + enter)
PHASE_PLAYER_DIR  = "player_dir"     # choosing direction for action
PHASE_PLAYER_ACT  = "player_act"
PHASE_PROJECTILE  = "projectile"     # projectile in flight
PHASE_MELEE_ANIM  = "melee_anim"     # melee slash animation
PHASE_FIREBALL    = "fireball"       # fireball in flight
PHASE_HEAL        = "heal"           # heal animation playing
PHASE_SHIELD      = "shield"         # shield animation playing
PHASE_SHIELD_TARGET = "shield_target"  # selecting a target for shield spell
PHASE_TURN_UNDEAD   = "turn_undead"    # turn undead holy blast animation
PHASE_MONSTER     = "monster"
PHASE_MONSTER_ACT = "monster_act"
PHASE_SPELL_SELECT = "spell_select"  # choosing a spell from the list
PHASE_THROW_SELECT = "throw_select"  # choosing an item to throw
PHASE_USE_ITEM     = "use_item"      # choosing an item to use
PHASE_EQUIP       = "equip"          # character sheet / equip screen
PHASE_CHARM       = "charm"          # charm person animation playing
PHASE_SLEEP       = "sleep"          # sleep spell animation playing
PHASE_TELEPORT    = "teleport"       # misty step teleport animation
PHASE_INVISIBILITY = "invisibility"  # invisibility spell animation
PHASE_ANIMATE_DEAD = "animate_dead"  # animate dead summoning animation
PHASE_AOE_FIREBALL = "aoe_fireball"  # AoE fireball projectile in flight
PHASE_AOE_EXPLOSION = "aoe_explosion"  # AoE fireball explosion expanding
PHASE_LIGHTNING_BOLT = "lightning_bolt"  # lightning bolt crackling along its path
PHASE_CURE_POISON = "cure_poison"        # cure poison cleansing animation
PHASE_BLESS = "bless"                    # bless party-wide buff animation
PHASE_CURSE = "curse"                    # curse debuff animation on enemy
PHASE_VICTORY     = "victory"
PHASE_DEFEAT      = "defeat"

# ── Spell constants (loaded from data/spells.json) ────────────────
FIREBALL_MP_COST  = SPELLS_DATA["fireball"]["mp_cost"]
FIREBALL_SPEED    = 320   # pixels per second (slower than arrow for drama)
HEAL_MP_COST      = SPELLS_DATA["heal"]["mp_cost"]

# ── Action indices ───────────────────────────────────────────────
ACTION_MOVE   = 0      # kept for internal use (WASD movement)
ACTION_ATTACK = 1      # kept for internal use (bump-to-attack)
ACTION_CAST   = 2
ACTION_HEAL   = 3
ACTION_SKIP   = 4      # spacebar skip
ACTION_RANGED = 5      # menu ranged attack
ACTION_EQUIP  = 6      # open equip screen (costs turn)
ACTION_THROW  = 7      # throw a throwable item from inventory
ACTION_USE_ITEM = 8    # use a consumable item (herb, potion, etc.)

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


class ShieldEffect:
    """A blue shield glow animation over a party member."""

    DURATION = 0.8  # seconds

    def __init__(self, col, row, ac_bonus=0):
        self.col = col
        self.row = row
        self.ac_bonus = ac_bonus
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


class TurnUndeadEffect:
    """A holy blast radiating out from the caster toward the monster."""

    DURATION = 1.2  # seconds — longer for dramatic effect

    def __init__(self, caster_col, caster_row, monster_col, monster_row, damage=0):
        self.caster_col = caster_col
        self.caster_row = caster_row
        self.monster_col = monster_col
        self.monster_row = monster_row
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


class CharmEffect:
    """A swirling pink/purple enchantment spiral around the target monster."""

    DURATION = 1.4  # seconds

    def __init__(self, col, row, success=True):
        self.col = col
        self.row = row
        self.success = success  # True = charmed, False = resisted
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


class SleepEffect:
    """A soft blue/purple mist descending over the target monster."""

    DURATION = 1.2  # seconds

    def __init__(self, col, row, success=True):
        self.col = col
        self.row = row
        self.success = success  # True = asleep, False = resisted
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


class TeleportEffect:
    """A silvery mist effect for Misty Step — plays at both origin and destination."""

    DURATION = 1.0  # seconds

    def __init__(self, from_col, from_row, to_col, to_row):
        self.from_col = from_col
        self.from_row = from_row
        self.to_col = to_col
        self.to_row = to_row
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


class InvisibilityEffect:
    """A shimmer/fade animation when a character turns invisible."""

    DURATION = 1.0  # seconds

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


class AnimateDeadEffect:
    """A dark green/black rising-from-the-ground animation for summoning a skeleton."""

    DURATION = 1.4  # seconds

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


class AoeFireballEffect:
    """An AoE fireball projectile traveling to a target tile."""

    def __init__(self, start_col, start_row, end_col, end_row):
        self.start_col = start_col
        self.start_row = start_row
        self.end_col = end_col
        self.end_row = end_row
        self.progress = 0.0  # 0 = start, 1 = arrived
        self.alive = True
        self.radius = 8  # base visual radius in pixels (bigger than normal fireball)

    def update(self, dt):
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


class AoeExplosionEffect:
    """A massive expanding explosion covering a multi-tile radius."""

    DURATION = 1.2  # seconds — longer than normal explosion for drama

    def __init__(self, col, row, radius=3):
        self.col = col
        self.row = row
        self.radius = radius
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


class BlessEffect:
    """A golden radiance expanding from the caster to all allies."""

    DURATION = 1.0  # seconds

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


class CurseEffect:
    """A dark purple miasma settling on a cursed enemy."""

    DURATION = 1.0  # seconds

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


class CurePoisonEffect:
    """A green-to-white cleansing glow over a cured ally."""

    DURATION = 1.0  # seconds

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


class LightningBoltEffect:
    """A crackling bolt of lightning along a straight line of tiles.

    Unlike projectiles, the bolt appears all at once along its path and
    crackles for its duration before dissipating.
    """

    DURATION = 1.0  # seconds

    def __init__(self, tiles):
        """*tiles* is a list of (col, row) tuples the bolt passes through."""
        self.tiles = tiles  # ordered list of (col, row)
        self.timer = self.DURATION
        self.alive = True

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = 0
            self.alive = False

    @property
    def progress(self):
        """0 = just appeared, 1 = done."""
        return 1.0 - (self.timer / self.DURATION)


class CombatState(BaseState):
    """Handles combat encounters on a tactical arena (supports multiple monsters)."""

    def __init__(self, game):
        super().__init__(game)
        # Multi-monster support
        self.monsters = []              # list of Monster objects in this encounter
        self.monster_positions = {}     # Monster -> (col, row)
        self.monster_refs = []          # original refs for removal after combat
        self.monster_map_positions = {} # Monster -> (map_col, map_row)
        self.active_monster_idx = 0     # which monster is currently acting

        # Legacy alias (first monster) for backward compat in enter() etc.
        self.monster = None

        self.phase = PHASE_INIT
        self.selected_action = 0
        self.menu_actions = []  # dynamic menu: [(action_id, label), ...]
        self.directing_action = None  # which action is being directed

        # Spell selection state
        self.spell_list = []        # available spells: [(spell_id, label, mp_cost), ...]
        self.spell_cursor = 0       # cursor in spell list
        self.selected_spell = None  # chosen spell id (e.g. "fireball", "heal")

        # Throw selection state
        self.throw_list = []        # throwable items: [(item_name, count), ...]
        self.throw_cursor = 0       # cursor in throw list
        self.selected_throw = None  # chosen item name to throw

        # Use item selection state
        self.use_item_list = []       # usable items: [(item_name, count, effect, power), ...]
        self.use_item_cursor = 0      # cursor in use item list
        self.selected_use_item = None # chosen item name to use

        # Equip screen state
        self.equip_cursor = 0           # cursor in equip/item list
        self.equip_action_menu = False  # True when action popup is open
        self.equip_action_cursor = 0    # selected option in action popup
        self.equip_examining = None     # item name being examined
        self.combat_log = _DualLog(self.game.game_log)
        self.phase_timer = 0

        # Game log overlay
        self.showing_log = False
        self.log_scroll = 0

        # Help overlay
        self.showing_help = False

        # Active fighter index (which party member's turn it is)
        self.active_idx = 0
        self.fighters = []        # list of alive PartyMembers in combat
        self.fighter_positions = {}  # member -> (col, row)
        self.defending = {}       # member -> bool
        self.moves_remaining = 0  # movement steps left this turn (from class range)

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

        # Shield effects
        self.shield_effects = []      # active ShieldEffect objects
        self.shield_buffs = {}        # member -> {"ac_bonus": int, "turns_left": int}
        self.range_buffs = {}         # member -> {"range_bonus": int, "turns_left": int}

        # Shield target selection cursor
        self.shield_target_col = 0
        self.shield_target_row = 0

        # Turn Undead effects
        self.turn_undead_effects = []  # active TurnUndeadEffect objects

        # Charm Person effects
        self.charm_effects = []       # active CharmEffect objects
        self.charm_target = None      # Monster being charmed (removed when anim ends)
        self.charm_buffs = {}         # Monster -> turns_left

        # Sleep effects
        self.sleep_effects = []       # active SleepEffect objects
        self.sleep_buffs = {}         # Monster -> turns_left

        # Teleport effects
        self.teleport_effects = []    # active TeleportEffect objects

        # Invisibility effects
        self.invisibility_effects = []    # active InvisibilityEffect objects
        self.invisibility_buffs = {}      # member -> turns_left

        # Animate Dead effects
        self.animate_dead_effects = []    # active AnimateDeadEffect objects
        self.summon_buffs = {}            # Monster -> turns_left (summoned allies)

        # AoE Fireball effects
        self.aoe_fireball_effects = []    # active AoeFireballEffect projectiles
        self.aoe_explosions = []          # active AoeExplosionEffect objects
        self._pending_aoe_fireball = None # info dict while projectile is in flight

        # Lightning Bolt effects
        self.lightning_bolt_effects = []  # active LightningBoltEffect objects

        # Cure Poison effects
        self.cure_poison_effects = []    # active CurePoisonEffect objects

        # Bless / Curse
        self.bless_effects = []          # active BlessEffect objects
        self.bless_buffs = {}            # member -> {"attack_bonus": int, "turns_left": int}
        self.curse_effects = []          # active CurseEffect objects
        self.curse_buffs = {}            # Monster -> {"ac_penalty": int, "attack_penalty": int, "turns_left": int}

        # Callback info for returning to source state
        self.source_state = "dungeon"

    # ── Arena helpers ────────────────────────────────────────────

    @staticmethod
    def _is_arena_wall(col, row):
        """True if the tile is part of the arena perimeter wall."""
        return col <= 0 or col >= ARENA_COLS - 1 or row <= 0 or row >= ARENA_ROWS - 1

    def _is_adjacent_to_any_monster(self, col, row):
        """True if (col, row) is adjacent to any alive monster (Chebyshev dist 1)."""
        for m in self.monsters:
            if not m.is_alive():
                continue
            mc, mr = self.monster_positions.get(m, (-99, -99))
            if max(abs(col - mc), abs(row - mr)) == 1:
                return True
        return False

    def _get_monster_at(self, col, row):
        """Return the alive monster occupying (col, row), or None."""
        for m in self.monsters:
            if not m.is_alive():
                continue
            mc, mr = self.monster_positions.get(m, (-99, -99))
            if mc == col and mr == row:
                return m
        return None

    def _is_monster_tile(self, col, row):
        """True if any alive monster occupies (col, row)."""
        return self._get_monster_at(col, row) is not None

    def _get_adjacent_monster(self, col, row, dcol, drow):
        """Return the alive monster adjacent in direction (dcol, drow), or None."""
        return self._get_monster_at(col + dcol, row + drow)

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
        """True if the active fighter is adjacent to any alive monster."""
        return self._is_adjacent_to_any_monster(self.active_col, self.active_row)

    # ── Setup ────────────────────────────────────────────────────

    def start_combat(self, fighter, monsters, source_state="dungeon",
                     encounter_name=None, map_monster_refs=None):
        """Start combat with one or more monsters.

        Parameters
        ----------
        fighter : PartyMember
            Kept for compatibility; full party is used.
        monsters : Monster or list[Monster]
            A single monster or list of monsters to fight.
        source_state : str
            "dungeon" or "overworld".
        encounter_name : str or None
            Display name for this encounter (e.g. "Goblin Ambush").
        map_monster_refs : list[Monster] or None
            Original monster refs from the dungeon/overworld map that
            should be removed after combat. If None, defaults to the
            combat monster list.
        """
        # Normalise to list
        if not isinstance(monsters, (list, tuple)):
            monsters = [monsters]

        self.monsters = list(monsters)
        self.monster = self.monsters[0]  # legacy alias
        self.encounter_name = encounter_name or self.monsters[0].name
        self.source_state = source_state

        # Store map refs for removal after combat (may differ from combat monsters)
        self.monster_refs = list(map_monster_refs) if map_monster_refs else list(monsters)
        self.monster_map_positions = {}
        for m in self.monster_refs:
            self.monster_map_positions[m] = (m.col, m.row)

        self.active_monster_idx = 0
        self.combat_log = _DualLog(self.game.game_log)
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
        self.shield_effects = []
        self.shield_buffs = {}
        self.range_buffs = {}
        self.turn_undead_effects = []
        self.charm_effects = []
        self.charm_target = None
        self.charm_buffs = {}
        self.sleep_effects = []
        self.sleep_buffs = {}
        self.teleport_effects = []
        self.invisibility_effects = []
        self.invisibility_buffs = {}
        self.animate_dead_effects = []
        self.summon_buffs = {}
        self.aoe_fireball_effects = []
        self.aoe_explosions = []
        self._pending_aoe_fireball = None
        self.lightning_bolt_effects = []
        self.cure_poison_effects = []
        self.bless_effects = []
        self.bless_buffs = {}
        self.curse_effects = []
        self.curse_buffs = {}
        self.showing_log = False
        self.log_scroll = 0
        self.showing_help = False

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

        # Place each monster near the top, randomly spread out
        self.monster_positions = {}
        for mon in self.monsters:
            for _attempt in range(30):
                mc = random.randint(3, ARENA_COLS - 4)
                mr = random.randint(2, 5)
                if (mc, mr) not in used:
                    self.monster_positions[mon] = (mc, mr)
                    used.add((mc, mr))
                    break

        # Keep a reference to the first fighter for backward compat
        self.fighter = fighter

    def enter(self):
        if len(self.monsters) == 1:
            self.combat_log.append(
                f"--- Party vs {self.monsters[0].name}! ---"
            )
        else:
            names = ", ".join(m.name for m in self.monsters)
            self.combat_log.append(
                f"--- Party vs {len(self.monsters)} enemies! ---"
            )
            self.combat_log.append(f"  ({names})")
        self.combat_log.append(
            f"{len(self.fighters)} party members engage!"
        )
        self.phase = PHASE_PLAYER
        self.active_idx = 0
        self._announce_turn()

    def exit(self):
        pass

    def _announce_turn(self):
        """Add a log entry for whose turn it is and reset move budget."""
        f = self.active_fighter
        if f:
            base_range = f.range
            bonus = 0
            rb = self.range_buffs.get(f)
            if rb:
                bonus = rb["range_bonus"]
            self.moves_remaining = base_range + bonus
            ranged_hint = " [RANGED]" if f.is_ranged(self.game.party) else ""
            speed_hint = f" [+{bonus} MOVE]" if bonus else ""
            self.combat_log.append(
                f"-- {f.name}'s turn --{ranged_hint}{speed_hint}")
        self._rebuild_menu()

    def _rebuild_menu(self):
        """Build the dynamic action menu for the current fighter."""
        f = self.active_fighter
        self.menu_actions = []  # list of (action_id, label)
        if not f:
            return
        rw = f.get_ranged_weapon()
        if rw and f.is_ranged(self.game.party):
            label = f"{rw}"
            if f.is_throwable_weapon():
                ammo = self._count_throwable(f)
                label += f" (x{ammo})"
            elif f.uses_ammo():
                ammo_type = f.get_ammo_type()
                ammo = (f._count_personal_ammo(ammo_type)
                        + self.game.party.inv_get_charges(ammo_type))
                label += f" ({ammo} {ammo_type})"
            self.menu_actions.append((ACTION_RANGED, label))
        # Show "Throw" if the character has any throwable items available
        throwables = self._build_throw_list(f)
        if throwables:
            self.menu_actions.append((ACTION_THROW, "Throw"))
        # Show "Cast" if the character has any castable spells
        spells = self._build_spell_list(f)
        if spells:
            self.menu_actions.append((ACTION_CAST, f"Cast ({f.current_mp}MP)"))
        # Show "Use Item" if the character has any usable items
        usable = self._build_usable_item_list(f)
        if usable:
            self.menu_actions.append((ACTION_USE_ITEM, "Use Item"))
        # Equip is always available
        self.menu_actions.append((ACTION_EQUIP, "Equip"))
        self.selected_action = 0

    def _build_spell_list(self, fighter):
        """Build the list of spells available to this fighter.

        Returns a list of (spell_id, label, mp_cost) tuples.
        Only includes spells the fighter has enough MP to cast and
        whose class/level requirements are met (driven by data/spells.json).
        """
        spells = []
        fighter_class = fighter.char_class.strip()
        fighter_level = getattr(fighter, "level", 1)
        for spell_id, spell in SPELLS_DATA.items():
            # Check usable_in — only show spells that work in battle
            if "battle" not in spell.get("usable_in", []):
                continue
            # Check class requirement
            allowed = [c.lower() for c in spell.get("allowable_classes", [])]
            if fighter_class.lower() not in allowed:
                continue
            # Check level requirement
            if fighter_level < spell.get("min_level", 1):
                continue
            # Check MP
            cost = spell["mp_cost"]
            if fighter.current_mp < cost:
                continue
            label = f"{spell['name']} ({cost}MP)"
            spells.append((spell_id, label, cost))
        return spells

    def _build_throw_list(self, fighter):
        """Build the list of throwable items the fighter can throw.

        Scans personal inventory and party shared stash for items with
        the 'throwable' attribute. Returns [(item_name, count), ...].
        """
        from src.party import WEAPONS
        seen = {}
        # Check personal inventory
        for item in fighter.inventory:
            wp = WEAPONS.get(item)
            if wp and wp.get("throwable", False):
                seen[item] = seen.get(item, 0) + 1
        # Check party shared stash
        party = self.game.party
        for entry in party.shared_inventory:
            name = party.item_name(entry)
            wp = WEAPONS.get(name)
            if wp and wp.get("throwable", False):
                seen[name] = seen.get(name, 0) + 1
        return [(name, count) for name, count in seen.items()]

    def _build_usable_item_list(self, fighter):
        """Build the list of usable items available to this fighter.

        Scans personal inventory and party shared stash for items with
        the 'usable' attribute. Returns [(item_name, count, effect, power), ...].
        """
        from src.party import ITEM_INFO
        seen = {}  # name -> (count, effect, power)
        # Check personal inventory
        for item in fighter.inventory:
            info = ITEM_INFO.get(item, {})
            if info.get("usable", False):
                if item not in seen:
                    seen[item] = [0, info.get("effect", ""), info.get("power", 0)]
                seen[item][0] += 1
        # Check party shared stash
        party = self.game.party
        for entry in party.shared_inventory:
            name = party.item_name(entry)
            info = ITEM_INFO.get(name, {})
            if info.get("usable", False):
                if name not in seen:
                    seen[name] = [0, info.get("effect", ""), info.get("power", 0)]
                seen[name][0] += 1
        return [(name, cnt, eff, pwr) for name, (cnt, eff, pwr) in seen.items()]

    # ── Input ────────────────────────────────────────────────────

    def handle_input(self, events, keys_pressed):
        # ── Help overlay input ──
        if self.showing_help:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_h, pygame.K_ESCAPE):
                        self.showing_help = False
            return

        # ── Log overlay input ──
        if self.showing_log:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_l or event.key == pygame.K_ESCAPE:
                        self.showing_log = False
                    elif event.key == pygame.K_UP:
                        self.log_scroll += 3
                    elif event.key == pygame.K_DOWN:
                        self.log_scroll = max(0, self.log_scroll - 3)
            return

        # During animation phases, no input
        if self.phase in (PHASE_PROJECTILE, PHASE_MELEE_ANIM, PHASE_FIREBALL, PHASE_HEAL, PHASE_SHIELD, PHASE_TURN_UNDEAD, PHASE_CHARM, PHASE_SLEEP, PHASE_TELEPORT, PHASE_INVISIBILITY, PHASE_ANIMATE_DEAD, PHASE_AOE_FIREBALL, PHASE_AOE_EXPLOSION, PHASE_LIGHTNING_BOLT, PHASE_CURE_POISON, PHASE_BLESS, PHASE_CURSE):
            return

        # Equip screen handles its own input
        if self.phase == PHASE_EQUIP:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self._handle_equip_input(event)
            return

        # Spell selection screen handles its own input
        if self.phase == PHASE_SPELL_SELECT:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self._handle_spell_select_input(event)
            return

        # Shield target selection handles its own input
        if self.phase == PHASE_SHIELD_TARGET:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self._handle_shield_target_input(event)
            return

        # Throw selection screen handles its own input
        if self.phase == PHASE_THROW_SELECT:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self._handle_throw_select_input(event)
            return

        # Use item selection screen handles its own input
        if self.phase == PHASE_USE_ITEM:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self._handle_use_item_select_input(event)
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

            if event.key == pygame.K_l:
                self.showing_log = True
                self.log_scroll = 0
                return

            if event.key == pygame.K_h:
                self.showing_help = True
                return

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

        if action_id == ACTION_CAST:
            # Open the spell selection sub-menu
            f = self.active_fighter
            self.spell_list = self._build_spell_list(f) if f else []
            self.spell_cursor = 0
            self.selected_spell = None
            self.phase = PHASE_SPELL_SELECT
            return

        if action_id == ACTION_THROW:
            # Open the throw item selection sub-menu
            f = self.active_fighter
            self.throw_list = self._build_throw_list(f) if f else []
            self.throw_cursor = 0
            self.selected_throw = None
            self.phase = PHASE_THROW_SELECT
            return

        if action_id == ACTION_USE_ITEM:
            # Open the use-item selection sub-menu
            f = self.active_fighter
            self.use_item_list = self._build_usable_item_list(f) if f else []
            self.use_item_cursor = 0
            self.selected_use_item = None
            self.phase = PHASE_USE_ITEM
            return

        # Directional actions (ranged)
        self.directing_action = action_id
        self.phase = PHASE_PLAYER_DIR

    # ── Spell selection ─────────────────────────────────────────

    def _handle_spell_select_input(self, event):
        """Handle input while the spell selection sub-menu is open."""
        if not self.spell_list:
            self.phase = PHASE_PLAYER
            return

        if event.key == pygame.K_UP:
            self.spell_cursor = (self.spell_cursor - 1) % len(self.spell_list)
        elif event.key == pygame.K_DOWN:
            self.spell_cursor = (self.spell_cursor + 1) % len(self.spell_list)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            spell_id, _label, _cost = self.spell_list[self.spell_cursor]
            self.selected_spell = spell_id
            # Check targeting mode for the selected spell
            spell_data = SPELLS_DATA.get(spell_id, {})
            targeting = spell_data.get("targeting", "directional_projectile")
            if targeting in ("select_ally", "select_enemy", "select_tile"):
                # Enter free-cursor target selection mode
                f = self.active_fighter
                if f:
                    if targeting == "select_enemy" and self.monsters:
                        # Start cursor on the first alive monster
                        for m in self.monsters:
                            if m.is_alive():
                                pos = self.monster_positions.get(m)
                                if pos:
                                    self.shield_target_col, self.shield_target_row = pos
                                    break
                    else:
                        col, row = self.fighter_positions.get(f, (3, 5))
                        self.shield_target_col = col
                        self.shield_target_row = row
                self.phase = PHASE_SHIELD_TARGET
            elif targeting == "self":
                # Self-targeting spell — cast immediately on the caster
                self._cast_self_spell(spell_id)
            elif targeting == "auto_monster":
                # Auto-targeting spell — cast immediately on the monster
                self._cast_auto_monster_spell(spell_id)
            else:
                # Standard directional targeting
                self.directing_action = ACTION_CAST
                self.phase = PHASE_PLAYER_DIR
        elif event.key == pygame.K_ESCAPE:
            # Cancel back to action menu
            self.phase = PHASE_PLAYER
            self.selected_spell = None

    def _handle_shield_target_input(self, event):
        """Handle input during free-cursor target selection.

        Works for both ally-targeting spells (Shield) and enemy-targeting
        spells (Magic Arrow).  Arrow keys move the selection box around
        the arena.  Enter confirms the target.  Escape cancels.
        """
        if event.key == pygame.K_UP:
            self.shield_target_row = max(1, self.shield_target_row - 1)
        elif event.key == pygame.K_DOWN:
            self.shield_target_row = min(ARENA_ROWS - 2, self.shield_target_row + 1)
        elif event.key == pygame.K_LEFT:
            self.shield_target_col = max(1, self.shield_target_col - 1)
        elif event.key == pygame.K_RIGHT:
            self.shield_target_col = min(ARENA_COLS - 2, self.shield_target_col + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            f = self.active_fighter
            spell = SPELLS_DATA.get(self.selected_spell, {})
            targeting = spell.get("targeting", "select_ally")

            if targeting == "select_tile":
                # Tile targeting (Misty Step teleport, AoE Fireball, etc.)
                tc = self.shield_target_col
                tr = self.shield_target_row
                if spell.get("effect_type") == "aoe_fireball":
                    # AoE fireball can target any non-wall tile
                    if self._is_arena_wall(tc, tr):
                        self.combat_log.append("Can't target a wall!")
                    else:
                        self._cast_aoe_fireball(f, tc, tr)
                elif self._is_arena_wall(tc, tr):
                    self.combat_log.append("Can't teleport into a wall!")
                elif self._is_monster_tile(tc, tr):
                    self.combat_log.append("A monster is in the way!")
                elif self._is_occupied_by_ally(tc, tr, exclude=f):
                    self.combat_log.append("An ally is standing there!")
                else:
                    if spell.get("effect_type") == "teleport":
                        self._cast_misty_step(f, tc, tr)
                    elif spell.get("effect_type") == "summon_skeleton":
                        self._cast_animate_dead(f, tc, tr)
                    else:
                        self.combat_log.append("Unknown tile spell!")
            elif targeting == "select_enemy":
                # Look for an alive monster at the cursor position
                target = self._get_monster_at(
                    self.shield_target_col, self.shield_target_row)
                if target and target.is_alive():
                    # Enemy-targeting spells break invisibility
                    self._break_invisibility(f)
                    spell_range = spell.get("range", 99)
                    caster_col, caster_row = self.fighter_positions.get(f, (0, 0))
                    dist = max(abs(self.shield_target_col - caster_col),
                               abs(self.shield_target_row - caster_row))
                    if dist > spell_range:
                        self.combat_log.append("Target is out of range!")
                    elif spell.get("effect_type") == "charm":
                        self._cast_charm_person(f, target)
                    elif spell.get("effect_type") == "sleep":
                        self._cast_sleep_spell(f, target)
                    elif spell.get("effect_type") == "curse":
                        self._cast_curse(f, target)
                    else:
                        self._cast_targeted_damage_spell(f, target)
                else:
                    self.combat_log.append("No enemy at that position!")
            else:
                # Ally targeting (Shield, etc.)
                target = None
                for member in self.fighters:
                    if member is f or not member.is_alive():
                        continue
                    mc, mr = self.fighter_positions.get(member, (-1, -1))
                    if mc == self.shield_target_col and mr == self.shield_target_row:
                        target = member
                        break
                if target:
                    spell_range = spell.get("range", 99)
                    caster_col, caster_row = self.fighter_positions.get(f, (0, 0))
                    dist = max(abs(self.shield_target_col - caster_col),
                               abs(self.shield_target_row - caster_row))
                    if dist > spell_range:
                        self.combat_log.append("Target is out of range!")
                    elif spell.get("effect_type") == "range_buff":
                        self._cast_range_buff_on_target(target)
                    elif spell.get("effect_type") == "cure_poison":
                        self._cast_cure_poison(target)
                    elif spell.get("effect_type") in ("heal", "major_heal"):
                        self._cast_heal_on_target(target)
                    else:
                        self._cast_shield_on_target(target)
                else:
                    self.combat_log.append("No ally at that position!")
        elif event.key == pygame.K_ESCAPE:
            # Cancel back to spell selection
            self.phase = PHASE_SPELL_SELECT
            self.selected_spell = None

    def _handle_throw_select_input(self, event):
        """Handle input while the throw item selection sub-menu is open."""
        if not self.throw_list:
            self.phase = PHASE_PLAYER
            return

        if event.key == pygame.K_UP:
            self.throw_cursor = (self.throw_cursor - 1) % len(self.throw_list)
        elif event.key == pygame.K_DOWN:
            self.throw_cursor = (self.throw_cursor + 1) % len(self.throw_list)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            item_name, _count = self.throw_list[self.throw_cursor]
            self.selected_throw = item_name
            # Enter direction mode for the throw
            self.directing_action = ACTION_THROW
            self.phase = PHASE_PLAYER_DIR
        elif event.key == pygame.K_ESCAPE:
            self.phase = PHASE_PLAYER
            self.selected_throw = None

    def _handle_use_item_select_input(self, event):
        """Handle input while the use-item selection sub-menu is open."""
        if not self.use_item_list:
            self.phase = PHASE_PLAYER
            return

        if event.key == pygame.K_UP:
            self.use_item_cursor = (self.use_item_cursor - 1) % len(self.use_item_list)
        elif event.key == pygame.K_DOWN:
            self.use_item_cursor = (self.use_item_cursor + 1) % len(self.use_item_list)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            item_name, _count, effect, power = self.use_item_list[self.use_item_cursor]
            self.selected_use_item = item_name
            # Use items are self-targeted — apply immediately
            self._apply_use_item(item_name, effect, power)
        elif event.key == pygame.K_ESCAPE:
            self.phase = PHASE_PLAYER
            self.selected_use_item = None

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
        from src.party import PartyMember
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
                # Only show equip options if the class can use the weapon
                if member.can_use_item(item_name):
                    valid_slots = member.get_valid_slots(item_name)
                    for s in valid_slots:
                        label = PartyMember._SLOT_LABELS[s]
                        options.append(f"EQUIP \u2192 {label}")
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
                elif chosen.startswith("EQUIP"):
                    inv_idx = idx - 4
                    if inv_idx < len(f.inventory):
                        from src.party import PartyMember
                        _label_to_key = {v: k for k, v in PartyMember._SLOT_LABELS.items()}
                        slot_label = chosen.split("\u2192 ", 1)[1].strip()
                        slot_key = _label_to_key.get(slot_label)
                        f.equip_item(f.inventory[inv_idx], slot_key)
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

        # Offensive actions break invisibility
        f = self.active_fighter
        if f and action in (ACTION_ATTACK, ACTION_RANGED, ACTION_THROW):
            self._break_invisibility(f)
        elif f and action == ACTION_CAST:
            # Offensive directional spells (fireball) break invisibility;
            # heal does not
            if self.selected_spell != "heal":
                self._break_invisibility(f)

        if action == ACTION_MOVE:
            self._try_arena_move(dcol, drow)

        elif action == ACTION_ATTACK:
            f = self.active_fighter
            if f:
                # Check if a monster is adjacent in that direction — melee
                col, row = self.fighter_positions[f]
                target_mon = self._get_adjacent_monster(col, row, dcol, drow)
                if target_mon:
                    self._player_attack_animated(dcol, drow, target_monster=target_mon)
                elif f.is_ranged(self.game.party):
                    self._fire_ranged(dcol, drow)
                else:
                    self._try_melee_directional(dcol, drow)

        elif action == ACTION_RANGED:
            self._fire_ranged(dcol, drow)

        elif action == ACTION_CAST:
            # Dispatch based on selected spell
            if self.selected_spell == "fireball":
                self._fire_fireball(dcol, drow)
            elif self.selected_spell == "lightning_bolt":
                self._fire_lightning_bolt(dcol, drow)
            else:
                # Unknown spell — cancel safely
                self.phase = PHASE_PLAYER
                self.directing_action = None

        elif action == ACTION_THROW:
            self._throw_item(dcol, drow)

    # ── Player actions ───────────────────────────────────────────

    def _try_arena_move(self, dcol, drow):
        """Move the active fighter in the arena. Bump-attacks a monster."""
        f = self.active_fighter
        if not f:
            return

        col, row = self.fighter_positions[f]
        new_col = col + dcol
        new_row = row + drow

        # Bump attack: moving into a monster's tile (uses all remaining moves)
        bump_monster = self._get_monster_at(new_col, new_row)
        if bump_monster:
            self._player_attack_animated(dcol, drow, target_monster=bump_monster)
            return

        # Can't walk onto another ally
        if self._is_occupied_by_ally(new_col, new_row, exclude=f):
            return

        # Normal movement — spend one move step
        if not self._is_arena_wall(new_col, new_row):
            self.fighter_positions[f] = (new_col, new_row)
            self.moves_remaining -= 1
            if self.moves_remaining <= 0:
                self._end_fighter_turn()

    def _execute_player_action(self):
        action = self.selected_action
        if action == ACTION_ATTACK:
            f = self.active_fighter
            if f and self._is_adjacent():
                # Always prefer melee when adjacent
                self._player_attack()
            elif f and f.is_ranged(self.game.party):
                # For ranged fighters, menu Attack fires toward nearest monster
                self._fire_ranged_at_nearest_monster()
            else:
                self.combat_message = "Too far! Move next to the enemy."
                self.combat_msg_timer = 1200
        elif action == ACTION_DEFEND:
            self._player_defend()
        elif action == ACTION_FLEE:
            self._player_flee()

    # ── Ranged attack ────────────────────────────────────────────

    def _count_throwable(self, fighter):
        """Count how many of the fighter's ranged weapon are available to throw."""
        wname = fighter.get_ranged_weapon() or fighter.weapon
        # Count in personal inventory + shared stash (equipped one is kept)
        count = fighter.inventory.count(wname)
        count += self.game.party.inv_count(wname)
        return count

    def _consume_throwable(self, fighter):
        """Remove one of the fighter's ranged weapon from inventory for throwing."""
        wname = fighter.get_ranged_weapon() or fighter.weapon
        # Take from personal inventory first, then shared stash
        if wname in fighter.inventory:
            fighter.inventory.remove(wname)
            return True
        removed = self.game.party.inv_remove(wname)
        return removed is not None

    def _consume_personal_ammo(self, fighter, ammo_type):
        """Consume one charge of ammo from the fighter's personal inventory.

        Returns True if successful.
        """
        for i, entry in enumerate(fighter.inventory):
            if isinstance(entry, dict) and entry.get("name") == ammo_type:
                ch = entry.get("charges", 1)
                if ch > 1:
                    entry["charges"] = ch - 1
                else:
                    fighter.inventory.pop(i)
                return True
            elif entry == ammo_type:
                fighter.inventory.pop(i)
                return True
        return False

    def _fire_ranged(self, dcol, drow):
        """Fire a ranged attack in the given direction."""
        f = self.active_fighter
        if not f or not f.is_ranged(self.game.party):
            rw = f.get_ranged_weapon() if f else None
            if f and f.is_throwable_weapon():
                self.combat_log.append(f"{f.name} is out of {rw}s to throw!")
            return

        rw = f.get_ranged_weapon()

        # Consume ammo for throwable weapons (daggers, etc.)
        if f.is_throwable_weapon():
            if not self._consume_throwable(f):
                self.combat_log.append(f"{f.name} has no {rw}s left to throw!")
                return
            ammo_left = self._count_throwable(f)
            ammo_note = f" ({ammo_left} left)"
        elif f.uses_ammo():
            ammo_type = f.get_ammo_type()
            # Try personal inventory first, then party shared stash
            consumed = self._consume_personal_ammo(f, ammo_type)
            if not consumed:
                consumed = self.game.party.inv_consume_charge(ammo_type)
            if not consumed:
                self.combat_log.append(f"{f.name} is out of {ammo_type.lower()}!")
                return
            ammo_left = (f._count_personal_ammo(ammo_type)
                         + self.game.party.inv_get_charges(ammo_type))
            ammo_note = f" ({ammo_left} {ammo_type.lower()} left)"
        else:
            ammo_note = ""

        col, row = self.fighter_positions[f]

        # Trace a ray from the fighter in direction (dcol, drow)
        # to find the first alive monster or hit a wall
        tc, tr = col + dcol, row + drow
        hit_monster = None  # the Monster object hit, or None
        end_col, end_row = col, row

        while not self._is_arena_wall(tc, tr):
            m = self._get_monster_at(tc, tr)
            if m:
                hit_monster = m
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
        rw_lower = rw.lower() if rw else ""
        proj_color = (255, 200, 80)  # default gold arrow
        if "bow" in rw_lower:
            proj_color = (255, 255, 200)  # pale arrow
        elif "sling" in rw_lower:
            proj_color = (180, 180, 180)  # gray stone
        elif "dagger" in rw_lower:
            proj_color = (200, 220, 240)  # silver
        elif "rock" in rw_lower:
            proj_color = (160, 140, 120)  # brown stone

        proj = Projectile(col, row, end_col, end_row,
                          color=proj_color, symbol=">" if dcol > 0 else
                          "<" if dcol < 0 else "v" if drow > 0 else "^")
        self.projectiles.append(proj)
        self.game.sfx.play("arrow")

        # Defer attack resolution until projectile arrives
        self._pending_ranged = {
            "fighter": f,
            "hit_monster": hit_monster,  # Monster object or None
            "ranged_weapon": rw,
        }

        self.phase = PHASE_PROJECTILE
        if f.is_throwable_weapon():
            self.combat_log.append(f"{f.name} throws {rw}!{ammo_note}")
        else:
            self.combat_log.append(f"{f.name} fires {rw}!{ammo_note}")

    def _throw_item(self, dcol, drow):
        """Throw a selected item from inventory in the given direction."""
        from src.party import WEAPONS
        f = self.active_fighter
        item_name = self.selected_throw
        if not f or not item_name:
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Consume one from personal inventory first, then party stash
        if item_name in f.inventory:
            f.inventory.remove(item_name)
        else:
            removed = self.game.party.inv_remove(item_name)
            if removed is None:
                self.combat_log.append(f"{f.name} has no {item_name} to throw!")
                self.phase = PHASE_PLAYER
                self.directing_action = None
                return

        col, row = self.fighter_positions[f]

        # Trace ray to find first alive monster or wall
        tc, tr = col + dcol, row + drow
        hit_monster = None  # Monster object or None
        end_col, end_row = col, row

        while not self._is_arena_wall(tc, tr):
            m = self._get_monster_at(tc, tr)
            if m:
                hit_monster = m
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

        proj_color = (200, 220, 240)  # silver for thrown items
        proj = Projectile(col, row, end_col, end_row,
                          color=proj_color,
                          symbol=">" if dcol > 0 else
                          "<" if dcol < 0 else "v" if drow > 0 else "^")
        self.projectiles.append(proj)
        self.game.sfx.play("arrow")

        # Store the weapon stats for damage resolution — use the thrown
        # item's power, not the equipped weapon's
        wp = WEAPONS.get(item_name, {"power": 0})
        self._pending_ranged = {
            "fighter": f,
            "hit_monster": hit_monster,  # Monster object or None
            "thrown_item": item_name,
            "thrown_power": wp.get("power", 0),
        }

        self.phase = PHASE_PROJECTILE
        # Count remaining
        remaining = f.inventory.count(item_name) + self.game.party.inv_count(item_name)
        self.combat_log.append(
            f"{f.name} throws {item_name}! ({remaining} left)"
        )

    def _fire_ranged_at_nearest_monster(self):
        """Fire toward the nearest alive monster directly (from menu Attack)."""
        f = self.active_fighter
        if not f:
            return

        col, row = self.fighter_positions[f]

        # Find nearest alive monster
        best_dist = 999
        best_mc, best_mr = col, row - 1
        for m in self.monsters:
            if not m.is_alive():
                continue
            mc, mr = self.monster_positions.get(m, (col, row))
            dist = max(abs(mc - col), abs(mr - row))
            if dist < best_dist:
                best_dist = dist
                best_mc, best_mr = mc, mr

        # Determine dominant direction to nearest monster
        dx = best_mc - col
        dy = best_mr - row

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
        target = info["hit_monster"]  # Monster object or None
        thrown_item = info.get("thrown_item")

        if not target:
            label = thrown_item or info.get("ranged_weapon") or f.weapon
            self.combat_log.append(f"{f.name}'s {label} misses the target!")
            self.game.sfx.play("miss")
            self._end_fighter_turn()
            return

        # Roll attack
        self.defending[f] = False
        atk_bonus = f.get_attack_bonus()
        bless = self.bless_buffs.get(f)
        if bless:
            atk_bonus += bless["attack_bonus"]
        target_ac = target.ac
        curse = self.curse_buffs.get(target)
        if curse:
            target_ac -= curse["ac_penalty"]
        hit, roll, total, crit = roll_attack(atk_bonus, target_ac)

        if crit:
            self.combat_log.append(
                f"{f.name} rolls {roll} — CRITICAL HIT!"
            )
            self.game.sfx.play("critical")
        elif hit:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {target_ac} — Hit!"
            )
            self.game.sfx.play("sword_hit")
        else:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {target_ac} — Miss!"
            )
            self.game.sfx.play("miss")

        if hit:
            if thrown_item:
                thrown_power = info.get("thrown_power", 0)
                damage = roll_damage(1, 6, thrown_power, critical=crit)
                dmg_label = thrown_item
            else:
                rw_name = info.get("ranged_weapon") or f.weapon
                dice_count, dice_sides, dmg_bonus = f.get_damage_dice(rw_name)
                damage = roll_damage(dice_count, dice_sides, dmg_bonus, critical=crit)
                dmg_label = rw_name
            target.hp = max(0, target.hp - damage)
            self.combat_log.append(
                f"{f.name} deals {damage} damage to {target.name} with {dmg_label}!"
            )
            # Spawn a hit flash on the monster
            mc, mr = self.monster_positions.get(target, (0, 0))
            self.hit_effects.append(HitEffect(mc, mr, damage))

        self._check_monster_death(target)

    # ── Melee attack ─────────────────────────────────────────────

    def _try_melee_directional(self, dcol, drow):
        """Arrow key melee: attack a monster if it's in the given direction."""
        f = self.active_fighter
        if not f:
            return

        col, row = self.fighter_positions[f]
        target_mon = self._get_adjacent_monster(col, row, dcol, drow)

        if target_mon:
            self._player_attack_animated(dcol, drow, target_monster=target_mon)
        # Nothing in that direction — no action

    def _player_attack_animated(self, dcol=0, drow=0, target_monster=None):
        """Start a melee attack with slash animation, then resolve."""
        f = self.active_fighter
        if not f:
            return

        # If no explicit target, find the nearest adjacent monster
        if target_monster is None:
            col, row = self.fighter_positions[f]
            best_dist = 999
            for m in self.monsters:
                if not m.is_alive():
                    continue
                mc, mr = self.monster_positions.get(m, (-99, -99))
                d = max(abs(mc - col), abs(mr - row))
                if d <= 1 and d < best_dist:
                    best_dist = d
                    target_monster = m
        if target_monster is None:
            return

        mc, mr = self.monster_positions.get(target_monster, (0, 0))

        # Determine slash direction from fighter to monster if not provided
        if dcol == 0 and drow == 0:
            col, row = self.fighter_positions[f]
            dcol = 1 if mc > col else -1 if mc < col else 0
            drow = 1 if mr > row else -1 if mr < row else 0

        # Class color for the slash
        from src.renderer import Renderer
        slash_color = Renderer._CLASS_COLORS.get(
            f.char_class.lower(), (255, 255, 255))

        # Create a melee slash effect at the monster's position
        effect = MeleeEffect(mc, mr, (dcol, drow), color=slash_color)
        self.melee_effects.append(effect)

        # Defer the attack resolution
        self._pending_melee = {"fighter": f, "target": target_monster}
        self.phase = PHASE_MELEE_ANIM
        self.combat_log.append(f"{f.name} attacks {target_monster.name} with {f.weapon}!")

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
        target = info.get("target", self.monsters[0] if self.monsters else None)
        if not target:
            self._end_fighter_turn()
            return

        self.defending[f] = False
        atk_bonus = f.get_attack_bonus()
        bless = self.bless_buffs.get(f)
        if bless:
            atk_bonus += bless["attack_bonus"]
        target_ac = target.ac
        curse = self.curse_buffs.get(target)
        if curse:
            target_ac -= curse["ac_penalty"]
        hit, roll, total, crit = roll_attack(atk_bonus, target_ac)

        if crit:
            self.combat_log.append(
                f"{f.name} rolls {roll} — CRITICAL HIT!"
            )
            self.game.sfx.play("critical")
        elif hit:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {target_ac} — Hit!"
            )
            self.game.sfx.play("sword_hit")
        else:
            self.combat_log.append(
                f"{f.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {target_ac} — Miss!"
            )
            self.game.sfx.play("miss")

        if hit:
            dice_count, dice_sides, dmg_bonus = f.get_damage_dice()
            damage = roll_damage(dice_count, dice_sides, dmg_bonus, critical=crit)
            target.hp = max(0, target.hp - damage)
            self.combat_log.append(
                f"{f.name} deals {damage} damage to {target.name} with {f.weapon}!"
            )
            # Spawn a hit flash on the monster
            mc, mr = self.monster_positions.get(target, (0, 0))
            self.hit_effects.append(HitEffect(mc, mr, damage))

        self._check_monster_death(target)

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

        # Trace ray to find first alive monster or wall (capped by spell range)
        spell_range = SPELLS_DATA["fireball"].get("range", 99)
        tc, tr = col + dcol, row + drow
        hit_monster = None  # Monster object or None
        end_col, end_row = col, row
        steps = 0

        while not self._is_arena_wall(tc, tr) and steps < spell_range:
            m = self._get_monster_at(tc, tr)
            if m:
                hit_monster = m
                end_col, end_row = tc, tr
                break
            tc += dcol
            tr += drow
            steps += 1

        if not hit_monster:
            end_col = tc - dcol
            end_row = tr - drow
            if end_col == col and end_row == row:
                end_col = tc
                end_row = tr

        fb = FireballEffect(col, row, end_col, end_row)
        self.fireballs.append(fb)
        self.game.sfx.play("fireball")

        self._pending_fireball = {
            "fighter": f,
            "hit_monster": hit_monster,  # Monster object or None
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
        target = info["hit_monster"]  # Monster object or None
        end_col = info["end_col"]
        end_row = info["end_row"]

        # Spawn explosion effect at impact point
        self.fireball_explosions.append(FireballExplosion(end_col, end_row))
        self.game.sfx.play("explosion")

        if not target:
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

        target.hp = max(0, target.hp - damage)
        self.combat_log.append(
            f"FIREBALL hits {target.name} for {damage} damage!"
        )
        mc, mr = self.monster_positions.get(target, (end_col, end_row))
        self.hit_effects.append(HitEffect(mc, mr, damage))

        self._check_monster_death(target)

    # ── AoE Fireball casting ─────────────────────────────────────

    def _cast_aoe_fireball(self, caster, target_col, target_row):
        """Cast AoE Fireball — fire a projectile to the selected tile.

        When the projectile arrives, ``_resolve_aoe_fireball`` will deal
        damage to ALL entities (monsters AND party members) within the
        blast radius.
        """
        spell_id = self.selected_spell
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Fireball")
        mp_cost = spell.get("mp_cost", 8)

        # Check MP
        if caster.current_mp < mp_cost:
            self.combat_log.append(
                f"Not enough MP! ({caster.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Deduct MP
        caster.current_mp -= mp_cost

        # Break invisibility (offensive spell)
        self._break_invisibility(caster)

        # Fire projectile from caster to target tile
        col, row = self.fighter_positions[caster]
        fb = AoeFireballEffect(col, row, target_col, target_row)
        self.aoe_fireball_effects.append(fb)
        self.game.sfx.play("fireball")

        ev = spell.get("effect_value", {})
        self._pending_aoe_fireball = {
            "fighter": caster,
            "target_col": target_col,
            "target_row": target_row,
            "dice_count": ev.get("dice_count", 3),
            "dice_sides": ev.get("dice_sides", 8),
            "stat_bonus": ev.get("stat_bonus", "intelligence"),
            "min_damage": ev.get("min_damage", 1),
            "radius": ev.get("radius", 3),
        }

        self.combat_log.append(
            f"{caster.name} casts {spell_name}! (-{mp_cost} MP)")
        self.selected_spell = None
        self.phase = PHASE_AOE_FIREBALL

    def _resolve_aoe_fireball(self):
        """Called when the AoE fireball projectile arrives at the target tile.

        Spawns the massive explosion effect and deals damage to ALL monsters
        and party members within ``radius`` tiles (Chebyshev distance) of the
        impact point.  Friendly fire is very much intentional.
        """
        info = self._pending_aoe_fireball
        self._pending_aoe_fireball = None

        if not info:
            self._end_fighter_turn()
            return

        caster = info["fighter"]
        tc = info["target_col"]
        tr = info["target_row"]
        dice_count = info["dice_count"]
        dice_sides = info["dice_sides"]
        stat_bonus = info["stat_bonus"]
        min_damage = info["min_damage"]
        radius = info["radius"]

        # Spawn the big explosion
        self.aoe_explosions.append(AoeExplosionEffect(tc, tr, radius))
        self.game.sfx.play("explosion")
        self.phase = PHASE_AOE_EXPLOSION

        # Calculate stat bonus
        if stat_bonus == "intelligence":
            bonus = caster.int_mod
        elif stat_bonus == "wisdom":
            bonus = caster.wis_mod
        else:
            bonus = 0

        # Roll damage once — everyone in the blast takes the same damage
        damage = 0
        for _ in range(dice_count):
            damage += random.randint(1, dice_sides)
        damage += bonus
        damage = max(min_damage, damage)

        self.combat_log.append(
            f"The fireball detonates for {damage} damage!")

        # Track all killed so we can check victory/defeat after
        monsters_hit = []
        fighters_hit = []

        # Damage ALL monsters in blast radius (Chebyshev distance)
        for monster in list(self.monsters):
            if not monster.is_alive():
                continue
            mc, mr = self.monster_positions.get(monster, (-99, -99))
            dist = max(abs(mc - tc), abs(mr - tr))
            if dist <= radius:
                monster.hp = max(0, monster.hp - damage)
                label = monster.name
                if monster.charmed:
                    label += " (ally)"
                self.combat_log.append(
                    f"  {label} takes {damage} fire damage!")
                self.hit_effects.append(HitEffect(mc, mr, damage))
                monsters_hit.append(monster)

        # Damage ALL party members in blast radius
        for member in list(self.fighters):
            if not member.is_alive():
                continue
            fc, fr = self.fighter_positions.get(member, (-99, -99))
            dist = max(abs(fc - tc), abs(fr - tr))
            if dist <= radius:
                member.hp = max(0, member.hp - damage)
                self.combat_log.append(
                    f"  {member.name} takes {damage} fire damage!")
                self.hit_effects.append(HitEffect(fc, fr, damage))
                fighters_hit.append(member)

        # Process monster deaths
        for monster in monsters_hit:
            if not monster.is_alive():
                self._on_monster_killed(monster)
            else:
                self._wake_monster(monster)

        # Process fighter deaths
        for member in fighters_hit:
            if not member.is_alive():
                self.combat_log.append(f"{member.name} has been slain!")

        # NOTE: Victory/defeat is checked when the explosion animation ends
        #       (in the update loop), not here.

    # ── Lightning Bolt casting ───────────────────────────────────

    def _fire_lightning_bolt(self, dcol, drow):
        """Cast Lightning Bolt in the given direction.

        Unlike a fireball, the bolt does NOT stop at the first target.
        It traces a line from the caster to the arena wall and damages
        EVERY entity (monster or party member) along its entire path.
        """
        f = self.active_fighter
        if not f:
            return

        # Check if character can cast sorcerer spells
        if not f.can_cast_sorcerer():
            self.combat_log.append(f"{f.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        spell = SPELLS_DATA.get("lightning_bolt", {})
        mp_cost = spell.get("mp_cost", 7)

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(
                f"{f.name} doesn't have enough MP! (need {mp_cost})")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Deduct MP
        f.current_mp -= mp_cost

        # Break invisibility (offensive spell)
        self._break_invisibility(f)

        col, row = self.fighter_positions[f]

        # Trace the full line from caster to arena wall
        bolt_tiles = []
        tc, tr = col + dcol, row + drow
        while not self._is_arena_wall(tc, tr):
            bolt_tiles.append((tc, tr))
            tc += dcol
            tr += drow

        if not bolt_tiles:
            # Facing directly into a wall
            self.combat_log.append("The lightning crackles against the wall!")
            self._end_fighter_turn()
            return

        # Create the bolt effect (appears all at once)
        self.lightning_bolt_effects.append(LightningBoltEffect(bolt_tiles))
        self.game.sfx.play("fireball")

        self.combat_log.append(
            f"{f.name} casts LIGHTNING BOLT! (-{mp_cost} MP)")

        # Resolve damage immediately — the animation plays while damage is shown
        ev = spell.get("effect_value", {})
        dice_count = ev.get("dice_count", 4)
        dice_sides = ev.get("dice_sides", 6)
        stat_bonus = ev.get("stat_bonus", "intelligence")
        min_damage = ev.get("min_damage", 1)

        if stat_bonus == "intelligence":
            bonus = f.int_mod
        elif stat_bonus == "wisdom":
            bonus = f.wis_mod
        else:
            bonus = 0

        # Roll damage once — every target on the line takes the same damage
        damage = 0
        for _ in range(dice_count):
            damage += random.randint(1, dice_sides)
        damage += bonus
        damage = max(min_damage, damage)

        bolt_set = set(bolt_tiles)

        # Damage all monsters on the bolt path
        monsters_hit = []
        for monster in list(self.monsters):
            if not monster.is_alive():
                continue
            mc, mr = self.monster_positions.get(monster, (-99, -99))
            if (mc, mr) in bolt_set:
                monster.hp = max(0, monster.hp - damage)
                label = monster.name
                if monster.charmed:
                    label += " (ally)"
                self.combat_log.append(
                    f"  Lightning strikes {label} for {damage} damage!")
                self.hit_effects.append(HitEffect(mc, mr, damage))
                monsters_hit.append(monster)

        # Damage all party members on the bolt path (friendly fire!)
        fighters_hit = []
        for member in list(self.fighters):
            if member is f:
                continue  # caster is not on the bolt path
            if not member.is_alive():
                continue
            fc, fr = self.fighter_positions.get(member, (-99, -99))
            if (fc, fr) in bolt_set:
                member.hp = max(0, member.hp - damage)
                self.combat_log.append(
                    f"  Lightning strikes {member.name} for {damage} damage!")
                self.hit_effects.append(HitEffect(fc, fr, damage))
                fighters_hit.append(member)

        # Process deaths
        for monster in monsters_hit:
            if not monster.is_alive():
                self._on_monster_killed(monster)
            else:
                self._wake_monster(monster)

        for member in fighters_hit:
            if not member.is_alive():
                self.combat_log.append(f"{member.name} has been slain!")

        # Phase controls the animation — victory/defeat checked when it ends
        self.phase = PHASE_LIGHTNING_BOLT

    # ── Heal casting ──────────────────────────────────────────────

    def _cast_heal(self, dcol, drow):
        """Cast a heal in the given direction. Targets the first ally in that line.

        Works for both Minor Heal (heal) and Major Heal (major_heal) by
        looking up the selected spell's data for MP cost and dice.
        """
        f = self.active_fighter
        if not f:
            return

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast healing spells!")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Look up the selected spell (works for heal and major_heal)
        spell_id = self.selected_spell or "heal"
        spell = SPELLS_DATA.get(spell_id, SPELLS_DATA.get("heal", {}))
        spell_name = spell.get("name", "Heal")
        mp_cost = spell.get("mp_cost", HEAL_MP_COST)

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(f"{f.name} doesn't have enough MP! (need {mp_cost})")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        col, row = self.fighter_positions[f]

        # Ray-trace in the chosen direction to find the first alive ally (capped by range)
        spell_range = spell.get("range", 99)
        target = None
        tc, tr = col + dcol, row + drow
        steps = 0
        while not self._is_arena_wall(tc, tr) and steps < spell_range:
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
            steps += 1

        if target is None:
            self.combat_log.append(f"No ally in that direction!")
            self.phase = PHASE_PLAYER
            self.directing_action = None
            return

        # Deduct MP
        f.current_mp -= mp_cost

        # Calculate heal amount from spell data
        ev = spell.get("effect_value", {})
        dice_count = ev.get("dice_count", 1)
        dice_sides = ev.get("dice_sides", 8)
        stat_bonus = ev.get("stat_bonus", "wisdom")
        min_heal = ev.get("min_heal", 1)

        if stat_bonus == "wisdom":
            bonus = f.wis_mod
        elif stat_bonus == "intelligence":
            bonus = f.int_mod
        else:
            bonus = 0

        heal_amount = 0
        for _ in range(dice_count):
            heal_amount += random.randint(1, dice_sides)
        heal_amount += bonus
        heal_amount = max(min_heal, heal_amount)

        # Apply healing (cap at max HP)
        old_hp = target.hp
        target.hp = min(target.max_hp, target.hp + heal_amount)
        actual_heal = target.hp - old_hp

        # Spawn heal effect over the target
        tcol, trow = self.fighter_positions.get(target, (3, 5))
        self.heal_effects.append(HealEffect(tcol, trow, actual_heal))

        self.phase = PHASE_HEAL
        self.game.sfx.play("heal")
        self.combat_log.append(
            f"{f.name} casts {spell_name} on {target.name}! (+{actual_heal} HP, -{mp_cost} MP)"
        )

    def _cast_heal_on_target(self, target):
        """Cast a heal spell on a specific ally chosen via the selection cursor.

        Works for both Minor Heal and Major Heal by reading the selected
        spell's data for MP cost, dice, and stat bonus.
        """
        f = self.active_fighter
        if not f:
            return

        spell_id = self.selected_spell or "heal"
        spell = SPELLS_DATA.get(spell_id, SPELLS_DATA.get("heal", {}))
        spell_name = spell.get("name", "Heal")
        mp_cost = spell.get("mp_cost", 5)

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast healing spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(
                f"Not enough MP! ({f.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Deduct MP
        f.current_mp -= mp_cost

        # Calculate heal amount from spell data
        ev = spell.get("effect_value", {})
        dice_count = ev.get("dice_count", 1)
        dice_sides = ev.get("dice_sides", 8)
        stat_bonus = ev.get("stat_bonus", "wisdom")
        min_heal = ev.get("min_heal", 1)

        if stat_bonus == "wisdom":
            bonus = f.wis_mod
        elif stat_bonus == "intelligence":
            bonus = f.int_mod
        else:
            bonus = 0

        heal_amount = 0
        for _ in range(dice_count):
            heal_amount += random.randint(1, dice_sides)
        heal_amount += bonus
        heal_amount = max(min_heal, heal_amount)

        # Apply healing (cap at max HP)
        old_hp = target.hp
        target.hp = min(target.max_hp, target.hp + heal_amount)
        actual_heal = target.hp - old_hp

        # Spawn heal effect over the target
        tcol, trow = self.fighter_positions.get(target, (3, 5))
        self.heal_effects.append(HealEffect(tcol, trow, actual_heal))

        self.phase = PHASE_HEAL
        self.game.sfx.play("heal")
        self.combat_log.append(
            f"{f.name} casts {spell_name} on {target.name}! (+{actual_heal} HP, -{mp_cost} MP)"
        )
        self.selected_spell = None

    def _cast_mass_heal(self):
        """Cast Mass Heal — heals ALL alive party members at once.

        Self-targeting spell that radiates healing energy from the caster.
        Spawns a HealEffect on every healed ally (and the caster) simultaneously.
        """
        f = self.active_fighter
        if not f:
            return

        spell_id = self.selected_spell or "mass_heal"
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Mass Heal")
        mp_cost = spell.get("mp_cost", 14)

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast healing spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(
                f"Not enough MP! ({f.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Deduct MP
        f.current_mp -= mp_cost

        # Calculate heal from spell data
        ev = spell.get("effect_value", {})
        dice_count = ev.get("dice_count", 2)
        dice_sides = ev.get("dice_sides", 8)
        stat_bonus = ev.get("stat_bonus", "wisdom")
        min_heal = ev.get("min_heal", 1)

        if stat_bonus == "wisdom":
            bonus = f.wis_mod
        elif stat_bonus == "intelligence":
            bonus = f.int_mod
        else:
            bonus = 0

        # Roll once — everyone gets the same heal
        heal_amount = 0
        for _ in range(dice_count):
            heal_amount += random.randint(1, dice_sides)
        heal_amount += bonus
        heal_amount = max(min_heal, heal_amount)

        self.combat_log.append(
            f"{f.name} casts {spell_name}! (-{mp_cost} MP)")

        # Heal every alive party member (including the caster)
        for member in self.fighters:
            if not member.is_alive():
                continue
            old_hp = member.hp
            member.hp = min(member.max_hp, member.hp + heal_amount)
            actual = member.hp - old_hp
            if actual > 0:
                mc, mr = self.fighter_positions.get(member, (3, 5))
                self.heal_effects.append(HealEffect(mc, mr, actual))
                self.combat_log.append(
                    f"  {member.name} is healed for {actual} HP!")

        self.phase = PHASE_HEAL
        self.game.sfx.play("heal")
        self.selected_spell = None

    def _cast_cure_poison(self, target):
        """Cast Cure Poison on a selected ally, removing the poisoned condition."""
        f = self.active_fighter
        if not f:
            return

        spell_id = self.selected_spell or "cure_poison"
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Cure Poison")
        mp_cost = spell.get("mp_cost", 6)

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast cleansing spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(
                f"Not enough MP! ({f.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Check if target is actually poisoned
        if not getattr(target, "poisoned", False):
            self.combat_log.append(f"{target.name} is not poisoned!")
            self.selected_spell = None
            self.phase = PHASE_SPELL_SELECT
            return

        # Deduct MP
        f.current_mp -= mp_cost

        # Cure the poison
        target.poisoned = False

        # Spawn cleansing effect
        tc, tr = self.fighter_positions.get(target, (3, 5))
        self.cure_poison_effects.append(CurePoisonEffect(tc, tr))

        self.phase = PHASE_CURE_POISON
        self.game.sfx.play("heal")
        self.combat_log.append(
            f"{f.name} casts {spell_name} on {target.name}! (-{mp_cost} MP)")
        self.combat_log.append(
            f"{target.name}'s poison has been cleansed!")
        self.selected_spell = None

    # ── Bless casting ──────────────────────────────────────────────

    def _cast_bless(self):
        """Cast Bless — party-wide attack buff for several turns."""
        f = self.active_fighter
        if not f:
            return

        spell_id = self.selected_spell or "bless"
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Bless")
        mp_cost = spell.get("mp_cost", 8)

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast divine spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(
                f"Not enough MP! ({f.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Deduct MP
        f.current_mp -= mp_cost

        duration = spell.get("duration", 5)
        if isinstance(duration, str):
            duration = 5
        ev = spell.get("effect_value", {})
        attack_bonus = ev.get("attack_bonus", 2)

        # Apply bless buff to all alive fighters
        for member in self.fighters:
            if member.is_alive():
                self.bless_buffs[member] = {
                    "attack_bonus": attack_bonus,
                    "turns_left": duration,
                }
                mc, mr = self.fighter_positions.get(member, (0, 0))
                self.bless_effects.append(BlessEffect(mc, mr))

        self.phase = PHASE_BLESS
        self.game.sfx.play("shield")
        self.combat_log.append(
            f"{f.name} casts {spell_name}! (-{mp_cost} MP)")
        self.combat_log.append(
            f"All allies gain +{attack_bonus} attack for {duration} turns!")
        self.selected_spell = None

    def _tick_bless_buffs(self):
        """Decrement bless buff durations at end of each round."""
        expired = []
        for member, buff in self.bless_buffs.items():
            buff["turns_left"] -= 1
            if buff["turns_left"] <= 0:
                expired.append(member)
        for member in expired:
            del self.bless_buffs[member]
            if member.is_alive():
                self.combat_log.append(
                    f"{member.name}'s blessing fades.")

    # ── Curse casting ──────────────────────────────────────────────

    def _cast_curse(self, caster, target):
        """Cast Curse — debuff a single enemy's AC and attack for several turns."""
        f = caster
        if not f:
            return

        spell_id = self.selected_spell or "curse"
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Curse")
        mp_cost = spell.get("mp_cost", 7)

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast divine spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(
                f"Not enough MP! ({f.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Deduct MP
        f.current_mp -= mp_cost

        duration = spell.get("duration", 5)
        if isinstance(duration, str):
            duration = 5
        ev = spell.get("effect_value", {})
        ac_penalty = ev.get("ac_penalty", 2)
        attack_penalty = ev.get("attack_penalty", 2)

        # Apply curse debuff to target monster
        self.curse_buffs[target] = {
            "ac_penalty": ac_penalty,
            "attack_penalty": attack_penalty,
            "turns_left": duration,
        }

        tc, tr = self.monster_positions.get(target, (0, 0))
        self.curse_effects.append(CurseEffect(tc, tr))

        self.phase = PHASE_CURSE
        self.game.sfx.play("shield")
        self.combat_log.append(
            f"{f.name} casts {spell_name} on {target.name}! (-{mp_cost} MP)")
        self.combat_log.append(
            f"{target.name} is cursed! (-{ac_penalty} AC, -{attack_penalty} ATK "
            f"for {duration} turns)")
        self.selected_spell = None

    def _tick_curse_buffs(self):
        """Decrement curse debuff durations at end of each round."""
        expired = []
        for monster, buff in self.curse_buffs.items():
            buff["turns_left"] -= 1
            if buff["turns_left"] <= 0:
                expired.append(monster)
        for monster in expired:
            del self.curse_buffs[monster]
            if monster.is_alive():
                self.combat_log.append(
                    f"{monster.name}'s curse lifts.")

    # ── Shield casting ─────────────────────────────────────────────

    def _cast_shield_on_target(self, target):
        """Cast the shield spell on a specific ally chosen via the selection box."""
        f = self.active_fighter
        if not f:
            return

        spell = SPELLS_DATA[self.selected_spell]
        mp_cost = spell["mp_cost"]

        # Check if character can cast sorcerer spells
        if not f.can_cast_sorcerer():
            self.combat_log.append(f"{f.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(f"{f.name} doesn't have enough MP! (need {mp_cost})")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Deduct MP
        f.current_mp -= mp_cost

        # Apply shield buff
        ac_bonus = spell["effect_value"].get("ac_bonus", 2)
        duration = spell.get("duration", 3)
        self.shield_buffs[target] = {"ac_bonus": ac_bonus, "turns_left": duration}

        # Spawn shield effect over the target
        tcol, trow = self.fighter_positions.get(target, (3, 5))
        self.shield_effects.append(ShieldEffect(tcol, trow, ac_bonus))

        self.phase = PHASE_SHIELD
        self.game.sfx.play("shield")
        self.combat_log.append(
            f"{f.name} casts SHIELD on {target.name}! (+{ac_bonus} AC for {duration} turns, -{mp_cost} MP)"
        )

    def _cast_range_buff_on_target(self, target):
        """Cast Long Shanks (range buff) on a specific ally."""
        f = self.active_fighter
        if not f:
            return

        spell = SPELLS_DATA[self.selected_spell]
        mp_cost = spell["mp_cost"]
        spell_name = spell.get("name", "Long Shanks").upper()

        # Check casting ability
        if not f.can_cast_sorcerer():
            self.combat_log.append(f"{f.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(
                f"{f.name} doesn't have enough MP! (need {mp_cost})")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Deduct MP
        f.current_mp -= mp_cost

        # Apply range buff
        range_bonus = spell["effect_value"].get("range_bonus", 6)
        duration = spell.get("duration", 5)
        if isinstance(duration, str):
            duration = 5
        self.range_buffs[target] = {
            "range_bonus": range_bonus, "turns_left": duration}

        # Reuse shield visual effect (green-tinted via the renderer later)
        tcol, trow = self.fighter_positions.get(target, (3, 5))
        self.shield_effects.append(ShieldEffect(tcol, trow, 0))

        self.phase = PHASE_SHIELD
        self.game.sfx.play("shield")
        self.combat_log.append(
            f"{f.name} casts {spell_name} on {target.name}! "
            f"(+{range_bonus} move for {duration} turns, -{mp_cost} MP)")

    def _cast_targeted_damage_spell(self, caster, target):
        """Cast a targeted damage spell on a specific monster.

        Reads dice, stat bonus, and MP cost from the selected spell's
        JSON data so this works generically for any ``select_enemy``
        damage spell (Magic Arrow, etc.).
        """
        spell = SPELLS_DATA.get(self.selected_spell, {})
        mp_cost = spell.get("mp_cost", 5)
        spell_name = spell.get("name", "Spell").upper()

        # Check casting ability
        casting_type = spell.get("casting_type", "sorcerer")
        if casting_type == "sorcerer" and not caster.can_cast_sorcerer():
            self.combat_log.append(f"{caster.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return
        if casting_type == "priest" and not caster.can_cast_priest():
            self.combat_log.append(f"{caster.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if caster.current_mp < mp_cost:
            self.combat_log.append(
                f"{caster.name} doesn't have enough MP! (need {mp_cost})")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Deduct MP
        caster.current_mp -= mp_cost

        # Parse dice from effect_value (e.g. "4d8")
        ev = spell.get("effect_value", {})
        dice_str = ev.get("dice", "1d4")
        parts = dice_str.lower().split("d")
        num_dice = int(parts[0]) if len(parts) == 2 else 1
        die_sides = int(parts[1]) if len(parts) == 2 else 4

        # Roll damage
        damage = sum(random.randint(1, die_sides) for _ in range(num_dice))

        # Add stat bonus
        stat_bonus = ev.get("stat_bonus")
        if stat_bonus == "intelligence":
            damage += caster.int_mod
        elif stat_bonus == "wisdom":
            damage += caster.wis_mod
        elif stat_bonus == "strength":
            damage += caster.str_mod

        min_damage = ev.get("min_damage", 1)
        damage = max(min_damage, damage)

        # Apply damage
        target.hp = max(0, target.hp - damage)

        # Visual and audio feedback — reuse fireball explosion effect
        mc, mr = self.monster_positions.get(target, (0, 0))
        self.fireball_explosions.append(FireballExplosion(mc, mr))
        self.hit_effects.append(HitEffect(mc, mr, damage))

        sfx = spell.get("sfx", "fireball")
        hit_sfx = spell.get("hit_sfx", "explosion")
        if sfx:
            self.game.sfx.play(sfx)
        if hit_sfx:
            self.game.sfx.play(hit_sfx)

        self.combat_log.append(
            f"{caster.name} casts {spell_name} on {target.name} "
            f"for {damage} damage! (-{mp_cost} MP)"
        )

        self.selected_spell = None

        # _check_monster_death sets PHASE_VICTORY if all monsters are dead,
        # or calls _end_fighter_turn() otherwise.  Do NOT overwrite the phase
        # afterwards — damage is already resolved inline (unlike the regular
        # fireball which needs PHASE_FIREBALL to wait for the projectile).
        self._check_monster_death(target)

    def _tick_shield_buffs(self):
        """Decrement shield buff durations at the end of each full round.
        Called when all fighters have taken their turns."""
        expired = []
        for member, buff in self.shield_buffs.items():
            buff["turns_left"] -= 1
            if buff["turns_left"] <= 0:
                expired.append(member)
                self.combat_log.append(
                    f"{member.name}'s shield fades away."
                )
        for member in expired:
            del self.shield_buffs[member]

    def _tick_range_buffs(self):
        """Decrement range buff durations at the end of each full round."""
        expired = []
        for member, buff in self.range_buffs.items():
            buff["turns_left"] -= 1
            if buff["turns_left"] <= 0:
                expired.append(member)
                self.combat_log.append(
                    f"{member.name}'s Long Shanks wears off."
                )
        for member in expired:
            del self.range_buffs[member]

    def _tick_charm_buffs(self):
        """Decrement charm durations at the end of each full round.

        When a charm expires the monster reverts to hostile.
        """
        expired = []
        for monster, turns_left in self.charm_buffs.items():
            turns_left -= 1
            self.charm_buffs[monster] = turns_left
            if turns_left <= 0:
                expired.append(monster)
        for monster in expired:
            del self.charm_buffs[monster]
            if monster.is_alive():
                monster.charmed = False
                self.combat_log.append(
                    f"The charm on {monster.name} wears off!")

    def _tick_sleep_buffs(self):
        """Decrement sleep durations at the end of each full round.

        When sleep expires the monster wakes up and acts normally.
        """
        expired = []
        for monster, turns_left in self.sleep_buffs.items():
            turns_left -= 1
            self.sleep_buffs[monster] = turns_left
            if turns_left <= 0:
                expired.append(monster)
        for monster in expired:
            del self.sleep_buffs[monster]
            if monster.is_alive():
                self.combat_log.append(
                    f"{monster.name} wakes up!")

    def _tick_invisibility_buffs(self):
        """Decrement invisibility durations at the end of each full round."""
        expired = []
        for member, turns_left in self.invisibility_buffs.items():
            turns_left -= 1
            self.invisibility_buffs[member] = turns_left
            if turns_left <= 0:
                expired.append(member)
        for member in expired:
            del self.invisibility_buffs[member]
            if member.is_alive():
                self.combat_log.append(
                    f"{member.name}'s invisibility fades away.")

    def _break_invisibility(self, member):
        """Break invisibility when the member attacks or casts offensively."""
        if member in self.invisibility_buffs:
            del self.invisibility_buffs[member]
            self.combat_log.append(
                f"{member.name} breaks invisibility!")

    # ── Self-targeting spell dispatch ────────────────────────────

    def _cast_self_spell(self, spell_id):
        """Dispatch self-targeting spells that affect the caster."""
        spell = SPELLS_DATA.get(spell_id, {})
        effect_type = spell.get("effect_type", "")

        if effect_type == "invisibility":
            self._cast_invisibility()
        elif effect_type == "mass_heal":
            self._cast_mass_heal()
        elif effect_type == "bless":
            self._cast_bless()
        else:
            # Unknown self-spell — cancel safely
            self.phase = PHASE_PLAYER
            self.selected_spell = None

    def _cast_invisibility(self):
        """Cast Invisibility — the caster becomes invisible for several turns.

        Invisible characters are ignored by monster AI.  Attacking or casting
        an offensive spell breaks the effect immediately.
        """
        f = self.active_fighter
        if not f:
            return

        spell_id = self.selected_spell
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Invisibility")
        mp_cost = spell.get("mp_cost", 5)

        # Check if already invisible
        if f in self.invisibility_buffs:
            self.combat_log.append(f"{f.name} is already invisible!")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(f"Not enough MP! ({f.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Deduct MP
        f.current_mp -= mp_cost

        duration = spell.get("duration", 5)
        if isinstance(duration, str):
            duration = 5

        self.invisibility_buffs[f] = duration

        self.combat_log.append(
            f"{f.name} casts {spell_name}! (-{mp_cost} MP)")
        self.combat_log.append(
            f"{f.name} fades from sight! ({duration} turns)")

        # Create the visual effect
        col, row = self.fighter_positions.get(f, (0, 0))
        self.invisibility_effects.append(InvisibilityEffect(col, row))
        self.selected_spell = None
        self.phase = PHASE_INVISIBILITY
        sfx = spell.get("sfx")
        if sfx:
            self.game.sfx.play(sfx)

    def _cast_animate_dead(self, caster, dest_col, dest_row):
        """Cast Animate Dead — summon a skeleton ally at the chosen tile.

        Creates a new Skeleton monster flagged as ``charmed`` so it uses
        the existing charmed-monster AI to fight enemy monsters.  Tracked
        separately in ``summon_buffs`` so it crumbles when the duration
        expires (rather than reverting to hostile like a charmed monster
        would).
        """
        spell_id = self.selected_spell
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Animate Dead")
        mp_cost = spell.get("mp_cost", 5)

        # Check MP
        if caster.current_mp < mp_cost:
            self.combat_log.append(
                f"Not enough MP! ({caster.current_mp}/{mp_cost})")
            self.selected_spell = None
            self.phase = PHASE_PLAYER
            return

        # Deduct MP
        caster.current_mp -= mp_cost

        # Build the skeleton from spell data
        ev = spell.get("effect_value", {})
        skeleton = Monster(
            name="Skeleton Ally",
            hp=ev.get("skeleton_hp", 12),
            ac=ev.get("skeleton_ac", 11),
            attack_bonus=ev.get("skeleton_attack", 3),
            damage_dice=ev.get("skeleton_dmg_dice", 1),
            damage_sides=ev.get("skeleton_dmg_sides", 6),
            damage_bonus=ev.get("skeleton_dmg_bonus", 0),
            xp_reward=0,
            gold_reward=0,
            color=(200, 200, 180),
            tile="skeleton_f1.png",
            undead=True,
            humanoid=False,
        )
        skeleton.charmed = True  # fights for the party

        # Add to the combat roster
        self.monsters.append(skeleton)
        self.monster_positions[skeleton] = (dest_col, dest_row)

        # Track duration
        duration = spell.get("duration", 5)
        if isinstance(duration, str):
            duration = 5
        self.summon_buffs[skeleton] = duration

        self.combat_log.append(
            f"{caster.name} casts {spell_name}! (-{mp_cost} MP)")
        self.combat_log.append(
            f"A skeleton claws its way out of the ground! ({duration} turns)")

        # Create the animation
        self.animate_dead_effects.append(
            AnimateDeadEffect(dest_col, dest_row))
        self.selected_spell = None
        self.phase = PHASE_ANIMATE_DEAD
        sfx = spell.get("sfx")
        if sfx:
            self.game.sfx.play(sfx)

    def _tick_summon_buffs(self):
        """Decrement summon durations at the end of each full round.

        When a summon expires the skeleton crumbles to dust (killed).
        """
        expired = []
        for monster, turns_left in self.summon_buffs.items():
            turns_left -= 1
            self.summon_buffs[monster] = turns_left
            if turns_left <= 0:
                expired.append(monster)
        for monster in expired:
            del self.summon_buffs[monster]
            if monster.is_alive():
                monster.hp = 0
                monster.charmed = False
                self.combat_log.append(
                    f"{monster.name} crumbles to dust!")

    # ── Auto-monster spell dispatch ──────────────────────────────

    def _cast_auto_monster_spell(self, spell_id):
        """Dispatch auto-targeting spells that hit the monster directly."""
        if spell_id == "turn_undead":
            self._cast_turn_undead()
        else:
            # Unknown auto-monster spell — cancel safely
            self.phase = PHASE_PLAYER
            self.selected_spell = None

    # ── Turn Undead casting ────────────────────────────────────────

    def _cast_turn_undead(self):
        """Cast Turn Undead — deals 75% HP damage to ALL undead monsters."""
        f = self.active_fighter
        if not f:
            return

        spell = SPELLS_DATA["turn_undead"]
        mp_cost = spell["mp_cost"]

        # Check if character can cast priest spells
        if not f.can_cast_priest():
            self.combat_log.append(f"{f.name} cannot cast priest spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if f.current_mp < mp_cost:
            self.combat_log.append(f"{f.name} doesn't have enough MP! (need {mp_cost})")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Find all alive undead monsters
        undead_targets = [m for m in self.monsters
                         if m.is_alive() and getattr(m, "undead", False)]

        if not undead_targets:
            # Check if there are any alive monsters at all for the message
            alive = [m for m in self.monsters if m.is_alive()]
            if alive:
                self.combat_log.append(
                    f"No undead enemies! The holy energy has no effect."
                )
            # Still costs the turn but not MP
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Deduct MP
        f.current_mp -= mp_cost

        hp_pct = spell["effect_value"].get("hp_percent", 0.75)
        caster_col, caster_row = self.fighter_positions.get(f, (3, 5))
        total_damage = 0

        for target in undead_targets:
            damage = max(1, int(target.hp * hp_pct))
            target.hp = max(0, target.hp - damage)
            total_damage += damage

            mc, mr = self.monster_positions.get(target, (0, 0))
            self.turn_undead_effects.append(
                TurnUndeadEffect(caster_col, caster_row, mc, mr, damage))
            self.hit_effects.append(HitEffect(mc, mr, damage))

            self.combat_log.append(
                f"Holy light sears {target.name} for {damage} damage!"
            )

        self.phase = PHASE_TURN_UNDEAD
        self.game.sfx.play("turn_undead")
        self.combat_log.append(
            f"{f.name} channels TURN UNDEAD! (-{mp_cost} MP)"
        )

        # Check all undead targets for death
        for target in undead_targets:
            if not target.is_alive():
                self._on_monster_killed(target)

    # ── Charm Person casting ─────────────────────────────────────────

    def _cast_charm_person(self, caster, target):
        """Cast Charm Person — charms a humanoid monster to fight for the party.

        The target must be humanoid.  The monster gets a Wisdom save
        against a DC based on the caster's Intelligence.  On a failed
        save the monster is charmed and will attack other monsters on
        its turns.  On a successful save the spell has no effect but
        still costs MP.
        """
        spell = SPELLS_DATA.get(self.selected_spell, {})
        mp_cost = spell.get("mp_cost", 5)
        spell_name = spell.get("name", "Charm Person").upper()

        # Check casting ability
        casting_type = spell.get("casting_type", "sorcerer")
        if casting_type == "sorcerer" and not caster.can_cast_sorcerer():
            self.combat_log.append(f"{caster.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return
        if casting_type == "priest" and not caster.can_cast_priest():
            self.combat_log.append(f"{caster.name} cannot cast spells!")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Check MP
        if caster.current_mp < mp_cost:
            self.combat_log.append(
                f"{caster.name} doesn't have enough MP! (need {mp_cost})")
            self.phase = PHASE_PLAYER
            self.selected_spell = None
            return

        # Must be humanoid
        if not getattr(target, "humanoid", False):
            self.combat_log.append(
                f"{target.name} is not humanoid — {spell_name} has no effect!")
            # Still costs the turn but not MP
            self.selected_spell = None
            self._end_fighter_turn()
            return

        # Already charmed?
        if getattr(target, "charmed", False):
            self.combat_log.append(
                f"{target.name} is already charmed!")
            self.selected_spell = None
            self._end_fighter_turn()
            return

        # Deduct MP
        caster.current_mp -= mp_cost

        # Calculate save DC: base + caster's Intelligence modifier
        ev = spell.get("effect_value", {})
        dc_base = ev.get("save_dc_base", 10)
        dc_stat = ev.get("save_dc_stat", "intelligence")
        if dc_stat == "intelligence":
            save_dc = dc_base + caster.int_mod
        elif dc_stat == "wisdom":
            save_dc = dc_base + caster.wis_mod
        else:
            save_dc = dc_base

        # Monster Wisdom save (use attack_bonus as a rough save bonus)
        save_roll = roll_d20()
        save_bonus = max(0, target.attack_bonus - 2)  # rough Wis save
        save_total = save_roll + save_bonus

        mc, mr = self.monster_positions.get(target, (0, 0))

        if save_total >= save_dc:
            # Monster resisted!
            self.combat_log.append(
                f"{caster.name} casts {spell_name} on {target.name}! (-{mp_cost} MP)")
            self.combat_log.append(
                f"{target.name} resists! (save {save_roll}+{save_bonus}="
                f"{save_total} vs DC {save_dc})")
            self.charm_effects.append(CharmEffect(mc, mr, success=False))
            self.charm_target = None
            self.selected_spell = None
            self.phase = PHASE_CHARM
            sfx = spell.get("sfx")
            if sfx:
                self.game.sfx.play(sfx)
        else:
            # Charmed! Monster switches sides and attacks other monsters
            self.combat_log.append(
                f"{caster.name} casts {spell_name} on {target.name}! (-{mp_cost} MP)")
            self.combat_log.append(
                f"{target.name} is CHARMED! (save {save_roll}+{save_bonus}="
                f"{save_total} vs DC {save_dc})")
            # Track duration from spell data (default 5 turns)
            duration = spell.get("duration", 5)
            if isinstance(duration, str):
                duration = 5  # fallback if "instant"
            self.combat_log.append(
                f"{target.name} turns against its allies! ({duration} turns)")
            target.charmed = True
            self.charm_buffs[target] = duration
            # Zero out rewards — charmed monsters don't give XP/gold
            target.xp_reward = 0
            target.gold_reward = 0
            self.charm_effects.append(CharmEffect(mc, mr, success=True))
            self.charm_target = target
            self.selected_spell = None
            self.phase = PHASE_CHARM
            sfx = spell.get("sfx")
            if sfx:
                self.game.sfx.play(sfx)

    def _cast_sleep_spell(self, caster, target):
        """Cast Sleep — puts a low-level monster to sleep for several turns.

        Only works on monsters whose max HP is at or below the spell's
        ``max_target_hp`` threshold.  The monster gets a Wisdom save to resist.
        Sleeping monsters skip their turns until the effect wears off or they
        are damaged (damage breaks sleep).
        """
        spell_id = self.selected_spell
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Sleep")
        mp_cost = spell.get("mp_cost", 5)

        # Check if monster is already asleep
        if target in self.sleep_buffs:
            self.combat_log.append(f"{target.name} is already asleep!")
            return

        # Check max HP threshold — only works on low-level monsters
        ev = spell.get("effect_value", {})
        max_hp_threshold = ev.get("max_target_hp", 20)
        if target.max_hp > max_hp_threshold:
            self.combat_log.append(
                f"{caster.name} casts {spell_name}... but {target.name} "
                f"is too powerful! (HP {target.max_hp} > {max_hp_threshold})")
            caster.current_mp -= mp_cost
            mc, mr = self.monster_positions.get(target, (0, 0))
            self.sleep_effects.append(SleepEffect(mc, mr, success=False))
            self.selected_spell = None
            self.phase = PHASE_SLEEP
            sfx = spell.get("sfx")
            if sfx:
                self.game.sfx.play(sfx)
            return

        # Deduct MP
        caster.current_mp -= mp_cost

        # Calculate save DC: base + caster's Intelligence modifier
        dc_base = ev.get("save_dc_base", 10)
        dc_stat = ev.get("save_dc_stat", "intelligence")
        if dc_stat == "intelligence":
            save_dc = dc_base + caster.int_mod
        elif dc_stat == "wisdom":
            save_dc = dc_base + caster.wis_mod
        else:
            save_dc = dc_base

        # Monster Wisdom save
        save_roll = roll_d20()
        save_bonus = max(0, target.attack_bonus - 2)
        save_total = save_roll + save_bonus

        mc, mr = self.monster_positions.get(target, (0, 0))

        if save_total >= save_dc:
            # Monster resisted!
            self.combat_log.append(
                f"{caster.name} casts {spell_name} on {target.name}! (-{mp_cost} MP)")
            self.combat_log.append(
                f"{target.name} resists! (save {save_roll}+{save_bonus}="
                f"{save_total} vs DC {save_dc})")
            self.sleep_effects.append(SleepEffect(mc, mr, success=False))
            self.selected_spell = None
            self.phase = PHASE_SLEEP
            sfx = spell.get("sfx")
            if sfx:
                self.game.sfx.play(sfx)
        else:
            # Asleep!
            duration = spell.get("duration", 5)
            if isinstance(duration, str):
                duration = 5
            self.combat_log.append(
                f"{caster.name} casts {spell_name} on {target.name}! (-{mp_cost} MP)")
            self.combat_log.append(
                f"{target.name} falls ASLEEP! (save {save_roll}+{save_bonus}="
                f"{save_total} vs DC {save_dc})")
            self.combat_log.append(
                f"{target.name} will sleep for {duration} turns.")
            self.sleep_buffs[target] = duration
            self.sleep_effects.append(SleepEffect(mc, mr, success=True))
            self.selected_spell = None
            self.phase = PHASE_SLEEP
            sfx = spell.get("sfx")
            if sfx:
                self.game.sfx.play(sfx)

    def _cast_misty_step(self, caster, dest_col, dest_row):
        """Cast Misty Step — teleport the caster to a chosen empty tile.

        The caster vanishes from their current position and reappears at
        the destination in a swirl of silvery mist.
        """
        spell_id = self.selected_spell
        spell = SPELLS_DATA.get(spell_id, {})
        spell_name = spell.get("name", "Misty Step")
        mp_cost = spell.get("mp_cost", 5)

        # Deduct MP
        caster.current_mp -= mp_cost

        # Record origin for the animation
        from_col, from_row = self.fighter_positions.get(caster, (0, 0))

        # Move the caster
        self.fighter_positions[caster] = (dest_col, dest_row)

        self.combat_log.append(
            f"{caster.name} casts {spell_name}! (-{mp_cost} MP)")
        self.combat_log.append(
            f"{caster.name} vanishes and reappears across the battlefield!")

        # Create the teleport animation
        self.teleport_effects.append(
            TeleportEffect(from_col, from_row, dest_col, dest_row))
        self.selected_spell = None
        self.phase = PHASE_TELEPORT
        sfx = spell.get("sfx")
        if sfx:
            self.game.sfx.play(sfx)

    def _apply_use_item(self, item_name, effect, power):
        """Apply a consumable item's effect and consume it."""
        f = self.active_fighter
        if not f:
            return

        # Consume the item — personal inventory first, then shared stash
        consumed = False
        if item_name in f.inventory:
            f.inventory.remove(item_name)
            consumed = True
        else:
            removed = self.game.party.inv_remove(item_name)
            consumed = removed is not None

        if not consumed:
            self.combat_log.append(f"No {item_name} available!")
            self.phase = PHASE_PLAYER
            return

        if effect == "heal_hp":
            # Restore HP: power is the base heal amount
            heal = power + random.randint(1, 6)
            old_hp = f.hp
            f.hp = min(f.max_hp, f.hp + heal)
            actual = f.hp - old_hp
            # Spawn heal effect over the fighter
            fcol, frow = self.fighter_positions.get(f, (3, 5))
            self.heal_effects.append(HealEffect(fcol, frow, actual))
            self.combat_log.append(
                f"{f.name} uses {item_name}! (+{actual} HP)"
            )
            self.game.sfx.play("heal")
            self.phase = PHASE_HEAL

        elif effect == "heal_mp":
            # Restore MP
            restore = power + random.randint(1, 4)
            old_mp = f.current_mp
            f.current_mp = min(f.max_mp, f.current_mp + restore)
            actual = f.current_mp - old_mp
            self.combat_log.append(
                f"{f.name} uses {item_name}! (+{actual} MP)"
            )
            self._end_fighter_turn()

        elif effect == "cure_poison":
            self.combat_log.append(
                f"{f.name} uses {item_name}!"
            )
            self._end_fighter_turn()

        elif effect == "buff_strength":
            buffs = getattr(f, "potion_buffs", {})
            buffs["strength"] = buffs.get("strength", 0) + power
            f.potion_buffs = buffs
            self.combat_log.append(
                f"{f.name} drinks {item_name}! (+{power} STR)"
            )
            self._end_fighter_turn()

        elif effect == "buff_ac":
            buffs = getattr(f, "potion_buffs", {})
            buffs["ac"] = buffs.get("ac", 0) + power
            f.potion_buffs = buffs
            self.combat_log.append(
                f"{f.name} drinks {item_name}! (+{power} AC)"
            )
            self._end_fighter_turn()

        elif effect == "combat_only":
            # Throwable items like Fire Oil — deal fire damage to all monsters
            total_dmg = 0
            for monster in list(self.monsters):
                if monster.hp > 0:
                    dmg = power + random.randint(1, 6)
                    monster.hp -= dmg
                    total_dmg += dmg
                    if not monster.is_alive():
                        self._on_monster_killed(monster)
            self.combat_log.append(
                f"{f.name} hurls {item_name}! Fire engulfs the battlefield! ({total_dmg} dmg)"
            )
            if self._all_monsters_dead():
                self._trigger_victory()
            else:
                self._end_fighter_turn()

        else:
            # Unknown effect — just consume and end turn
            self.combat_log.append(
                f"{f.name} uses {item_name}!"
            )
            self._end_fighter_turn()

    def _player_defend(self):
        f = self.active_fighter
        if not f:
            return
        self.defending[f] = True
        self.game.sfx.play("defend")
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
            self.game.sfx.play("flee")
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
        self.selected_spell = None
        self.selected_throw = None
        self.selected_use_item = None
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
        """Monsters act sequentially. Advance to the next alive monster."""
        # Find next alive monster starting from active_monster_idx
        while self.active_monster_idx < len(self.monsters):
            mon = self.monsters[self.active_monster_idx]
            if mon.is_alive():
                break
            self.active_monster_idx += 1

        if self.active_monster_idx >= len(self.monsters):
            # All monsters have acted — back to player phase
            self.active_monster_idx = 0
            for m in self.fighters:
                self.defending[m] = False
            self._tick_shield_buffs()
            self._tick_range_buffs()
            self._tick_charm_buffs()
            self._tick_sleep_buffs()
            self._tick_invisibility_buffs()
            self._tick_summon_buffs()
            self._tick_bless_buffs()
            self._tick_curse_buffs()
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
            return

        mon = self.monsters[self.active_monster_idx]
        mc, mr = self.monster_positions.get(mon, (0, 0))

        # ── Charmed monster: attacks other (non-charmed) monsters ──
        if getattr(mon, "charmed", False):
            self._charmed_monster_turn(mon)
            return

        # ── Sleeping monster: skip turn entirely ──
        if mon in self.sleep_buffs:
            self.combat_log.append(f"{mon.name} is fast asleep... Zzz")
            self.active_monster_idx += 1
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 600
            return

        # Find closest alive, visible fighter
        best_dist = 999
        best_target = None
        for member in self.fighters:
            if not member.is_alive():
                continue
            # Invisible fighters are ignored by monsters
            if member in self.invisibility_buffs:
                continue
            col, row = self.fighter_positions[member]
            dist = max(abs(col - mc), abs(row - mr))
            if dist < best_dist:
                best_dist = dist
                best_target = member

        if not best_target:
            # No visible fighters — monster is confused, skip turn
            self.combat_log.append(
                f"{mon.name} looks around confused...")
            self.active_monster_idx += 1
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 500
            return

        # Check adjacency to any alive, visible fighter
        adjacent_targets = []
        for member in self.fighters:
            if not member.is_alive():
                continue
            if member in self.invisibility_buffs:
                continue
            col, row = self.fighter_positions[member]
            if max(abs(col - mc), abs(row - mr)) == 1:
                adjacent_targets.append(member)

        if adjacent_targets:
            target = random.choice(adjacent_targets)
            self._monster_attack_player(mon, target)
        else:
            self._monster_move_toward(mon, best_target)
            self.combat_log.append(f"{mon.name} moves closer...")
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 500

    def _monster_move_toward(self, monster, target):
        """Step monster 1 tile toward the target (Chebyshev)."""
        mc, mr = self.monster_positions.get(monster, (0, 0))
        tc, tr = self.fighter_positions[target]

        best_dist = max(abs(mc - tc), abs(mr - tr))
        candidates = []

        for dcol, drow in [
            (0, -1), (0, 1), (-1, 0), (1, 0),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ]:
            nc, nr = mc + dcol, mr + drow
            # Check occupied by fighter
            occupied = False
            for m in self.fighters:
                if m.is_alive() and self.fighter_positions.get(m) == (nc, nr):
                    occupied = True
                    break
            if occupied:
                continue
            # Check occupied by another alive monster
            for other in self.monsters:
                if other is monster or not other.is_alive():
                    continue
                if self.monster_positions.get(other) == (nc, nr):
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
            self.monster_positions[monster] = (nc, nr)

    def _monster_attack_player(self, monster, target):
        """A specific monster attacks a specific party member."""
        player_ac = target.get_ac()
        if self.defending.get(target, False):
            player_ac += 2
        shield = self.shield_buffs.get(target)
        if shield:
            player_ac += shield["ac_bonus"]

        monster_atk = monster.attack_bonus
        curse = self.curse_buffs.get(monster)
        if curse:
            monster_atk -= curse["attack_penalty"]

        hit, roll, total, crit = roll_attack(
            monster_atk, player_ac
        )

        ac_display = f"AC {player_ac}"
        if self.defending.get(target, False):
            ac_display += " (def)"
        if shield:
            ac_display += " (shld)"

        if crit:
            self.combat_log.append(
                f"{monster.name} → {target.name}: rolls {roll} — CRITICAL HIT!"
            )
            self.game.sfx.play("critical")
        elif hit:
            self.combat_log.append(
                f"{monster.name} → {target.name}: rolls {roll} "
                f"({format_modifier(monster.attack_bonus)}) "
                f"= {total} vs {ac_display} — Hit!"
            )
            self.game.sfx.play("player_hurt")
        else:
            self.combat_log.append(
                f"{monster.name} → {target.name}: rolls {roll} "
                f"({format_modifier(monster.attack_bonus)}) "
                f"= {total} vs {ac_display} — Miss!"
            )
            self.game.sfx.play("miss")

        if hit:
            damage = roll_damage(
                monster.damage_dice,
                monster.damage_sides,
                monster.damage_bonus,
                critical=crit,
            )
            target.hp = max(0, target.hp - damage)
            self.combat_log.append(
                f"{monster.name} deals {damage} damage to {target.name}!"
            )
            # Spawn hit flash on the target party member
            tcol, trow = self.fighter_positions.get(target, (3, 5))
            self.hit_effects.append(HitEffect(tcol, trow, damage))

        if not target.is_alive():
            self.combat_log.append(f"{target.name} has fallen!")

        if not any(m.is_alive() for m in self.fighters):
            self.phase = PHASE_DEFEAT
            self.phase_timer = 2500
            self.game.sfx.play("defeat")
            self.combat_log.append("The party has been defeated!")
        else:
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 800

    # ── Charmed monster AI ─────────────────────────────────────────

    def _charmed_monster_turn(self, mon):
        """A charmed monster targets the closest non-charmed enemy monster."""
        mc, mr = self.monster_positions.get(mon, (0, 0))

        # Find alive, non-charmed monsters as targets
        enemies = [m for m in self.monsters
                   if m is not mon and m.is_alive() and not getattr(m, "charmed", False)]

        if not enemies:
            # No enemies left — charmed monster just idles
            self.combat_log.append(
                f"{mon.name} (charmed) looks around peacefully.")
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 500
            return

        # Find closest enemy monster
        best_dist = 999
        best_target = None
        for enemy in enemies:
            ec, er = self.monster_positions.get(enemy, (0, 0))
            dist = max(abs(ec - mc), abs(er - mr))
            if dist < best_dist:
                best_dist = dist
                best_target = enemy

        # Check adjacency to any enemy monster
        adjacent = []
        for enemy in enemies:
            ec, er = self.monster_positions.get(enemy, (0, 0))
            if max(abs(ec - mc), abs(er - mr)) == 1:
                adjacent.append(enemy)

        if adjacent:
            target = random.choice(adjacent)
            self._charmed_monster_attack(mon, target)
        else:
            # Move toward closest enemy monster
            self._charmed_monster_move_toward(mon, best_target)
            self.combat_log.append(
                f"{mon.name} (charmed) moves toward {best_target.name}...")
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 500

    def _charmed_monster_move_toward(self, monster, target_monster):
        """Move a charmed monster one step toward a target monster."""
        mc, mr = self.monster_positions.get(monster, (0, 0))
        tc, tr = self.monster_positions.get(target_monster, (0, 0))

        best_dist = max(abs(mc - tc), abs(mr - tr))
        candidates = []

        for dcol, drow in [
            (0, -1), (0, 1), (-1, 0), (1, 0),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ]:
            nc, nr = mc + dcol, mr + drow
            # Check occupied by fighter
            occupied = False
            for m in self.fighters:
                if m.is_alive() and self.fighter_positions.get(m) == (nc, nr):
                    occupied = True
                    break
            if occupied:
                continue
            # Check occupied by another alive monster (can't stack)
            for other in self.monsters:
                if other is monster or not other.is_alive():
                    continue
                if self.monster_positions.get(other) == (nc, nr):
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
            self.monster_positions[monster] = (nc, nr)

    def _charmed_monster_attack(self, attacker, target):
        """A charmed monster attacks another (non-charmed) monster."""
        hit, roll, total, crit = roll_attack(
            attacker.attack_bonus, target.ac
        )

        if crit:
            self.combat_log.append(
                f"{attacker.name} (charmed) → {target.name}: "
                f"rolls {roll} — CRITICAL HIT!")
            self.game.sfx.play("critical")
        elif hit:
            self.combat_log.append(
                f"{attacker.name} (charmed) → {target.name}: "
                f"rolls {roll} ({format_modifier(attacker.attack_bonus)}) "
                f"= {total} vs AC {target.ac} — Hit!")
            self.game.sfx.play("explosion")
        else:
            self.combat_log.append(
                f"{attacker.name} (charmed) → {target.name}: "
                f"rolls {roll} ({format_modifier(attacker.attack_bonus)}) "
                f"= {total} vs AC {target.ac} — Miss!")
            self.game.sfx.play("miss")

        if hit:
            damage = roll_damage(
                attacker.damage_dice,
                attacker.damage_sides,
                attacker.damage_bonus,
                critical=crit,
            )
            target.hp = max(0, target.hp - damage)
            self.combat_log.append(
                f"{attacker.name} deals {damage} damage to {target.name}!")

            # Spawn hit effect on the target monster
            tc, tr = self.monster_positions.get(target, (0, 0))
            self.hit_effects.append(HitEffect(tc, tr, damage))

        if not target.is_alive():
            self._on_monster_killed(target)

        # Check if all non-charmed monsters are dead
        if self._all_monsters_dead():
            self._trigger_victory()
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

        # Update cure poison effects
        for fx in self.cure_poison_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_CURE_POISON:
            if all(not fx.alive for fx in self.cure_poison_effects):
                self.cure_poison_effects = []
                self._end_fighter_turn()
            return
        self.cure_poison_effects = [fx for fx in self.cure_poison_effects if fx.alive]

        # Update bless effects
        for fx in self.bless_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_BLESS:
            if all(not fx.alive for fx in self.bless_effects):
                self.bless_effects = []
                self._end_fighter_turn()
            return
        self.bless_effects = [fx for fx in self.bless_effects if fx.alive]

        # Update curse effects
        for fx in self.curse_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_CURSE:
            if all(not fx.alive for fx in self.curse_effects):
                self.curse_effects = []
                self._end_fighter_turn()
            return
        self.curse_effects = [fx for fx in self.curse_effects if fx.alive]

        # Update shield effects
        for fx in self.shield_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_SHIELD:
            if all(not fx.alive for fx in self.shield_effects):
                self.shield_effects = []
                self._end_fighter_turn()
            return
        self.shield_effects = [fx for fx in self.shield_effects if fx.alive]

        # Update turn undead effects
        for fx in self.turn_undead_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_TURN_UNDEAD:
            if all(not fx.alive for fx in self.turn_undead_effects):
                self.turn_undead_effects = []
                # Check if all monsters died from the holy blast
                if self._all_monsters_dead():
                    self._trigger_victory()
                else:
                    self._end_fighter_turn()
            return
        self.turn_undead_effects = [fx for fx in self.turn_undead_effects if fx.alive]

        # Update charm effects
        for fx in self.charm_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_CHARM:
            if all(not fx.alive for fx in self.charm_effects):
                self.charm_effects = []
                self.charm_target = None
                # Check if all non-charmed monsters are dead
                if self._all_monsters_dead():
                    self._trigger_victory()
                else:
                    self._end_fighter_turn()
            return
        self.charm_effects = [fx for fx in self.charm_effects if fx.alive]

        # Update sleep effects
        for fx in self.sleep_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_SLEEP:
            if all(not fx.alive for fx in self.sleep_effects):
                self.sleep_effects = []
                # Check if all non-charmed monsters are dead
                if self._all_monsters_dead():
                    self._trigger_victory()
                else:
                    self._end_fighter_turn()
            return
        self.sleep_effects = [fx for fx in self.sleep_effects if fx.alive]

        # Update teleport effects
        for fx in self.teleport_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_TELEPORT:
            if all(not fx.alive for fx in self.teleport_effects):
                self.teleport_effects = []
                self._end_fighter_turn()
            return
        self.teleport_effects = [fx for fx in self.teleport_effects if fx.alive]

        # Update invisibility effects
        for fx in self.invisibility_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_INVISIBILITY:
            if all(not fx.alive for fx in self.invisibility_effects):
                self.invisibility_effects = []
                self._end_fighter_turn()
            return
        self.invisibility_effects = [fx for fx in self.invisibility_effects if fx.alive]

        # Update animate dead effects
        for fx in self.animate_dead_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_ANIMATE_DEAD:
            if all(not fx.alive for fx in self.animate_dead_effects):
                self.animate_dead_effects = []
                self._end_fighter_turn()
            return
        self.animate_dead_effects = [fx for fx in self.animate_dead_effects if fx.alive]

        # Update AoE fireball projectile
        for fx in self.aoe_fireball_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_AOE_FIREBALL:
            if all(not fx.alive for fx in self.aoe_fireball_effects):
                self.aoe_fireball_effects = []
                self._resolve_aoe_fireball()
            return
        self.aoe_fireball_effects = [fx for fx in self.aoe_fireball_effects if fx.alive]

        # Update AoE explosions
        for fx in self.aoe_explosions:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_AOE_EXPLOSION:
            if all(not fx.alive for fx in self.aoe_explosions):
                self.aoe_explosions = []
                # Check victory/defeat after the explosion animation
                if self._all_monsters_dead():
                    self._trigger_victory()
                elif not any(m.is_alive() for m in self.fighters):
                    self.phase = PHASE_DEFEAT
                    self.phase_timer = 2500
                else:
                    self._end_fighter_turn()
            return
        self.aoe_explosions = [fx for fx in self.aoe_explosions if fx.alive]

        # Update lightning bolt effects
        for fx in self.lightning_bolt_effects:
            if fx.alive:
                fx.update(dt)
        if self.phase == PHASE_LIGHTNING_BOLT:
            if all(not fx.alive for fx in self.lightning_bolt_effects):
                self.lightning_bolt_effects = []
                # Check victory/defeat after the bolt animation
                if self._all_monsters_dead():
                    self._trigger_victory()
                elif not any(m.is_alive() for m in self.fighters):
                    self.phase = PHASE_DEFEAT
                    self.phase_timer = 2500
                else:
                    self._end_fighter_turn()
            return
        self.lightning_bolt_effects = [fx for fx in self.lightning_bolt_effects if fx.alive]

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
            self.active_monster_idx = 0
            self.phase = PHASE_MONSTER
            self.phase_timer = 600
        elif self.phase == PHASE_MONSTER:
            self._monster_turn()
        elif self.phase == PHASE_MONSTER_ACT:
            # Advance to next monster
            self.active_monster_idx += 1
            self._monster_turn()
        elif self.phase == PHASE_VICTORY:
            self._end_combat(won=True)
        elif self.phase == PHASE_DEFEAT:
            self._end_combat(won=False)

    # ── Monster death & victory helpers ─────────────────────────

    def _all_monsters_dead(self):
        """True if every non-charmed monster in the encounter is dead.

        Charmed monsters fight for the party, so they don't count as
        enemies for the purpose of the victory check.
        """
        for m in self.monsters:
            if m.is_alive() and not getattr(m, "charmed", False):
                return False
        return True

    def _on_monster_killed(self, monster):
        """Log a monster's death. Does NOT trigger victory — caller checks."""
        self.combat_log.append(f"{monster.name} is defeated!")

    def _wake_monster(self, monster):
        """Wake a sleeping monster (e.g. when it takes damage)."""
        if monster in self.sleep_buffs:
            del self.sleep_buffs[monster]
            self.combat_log.append(
                f"{monster.name} is jolted awake by the attack!")

    def _check_monster_death(self, target):
        """After damaging a monster, check if it died and if combat is over."""
        if target and target.is_alive():
            # Damage wakes sleeping monsters
            self._wake_monster(target)
        if target and not target.is_alive():
            self._on_monster_killed(target)
        if self._all_monsters_dead():
            self._trigger_victory()
        else:
            self._end_fighter_turn()

    def _trigger_victory(self):
        """Handle the common victory sequence: XP, gold, level-ups."""
        self.phase = PHASE_VICTORY
        self.phase_timer = 2500

        # Sum rewards from all monsters
        total_xp = sum(m.xp_reward for m in self.monsters)
        total_gold = sum(m.gold_reward for m in self.monsters)

        for m in self.fighters:
            if m.is_alive():
                m.exp += total_xp
        self.game.party.gold += total_gold
        self.game.sfx.play("victory")
        self.combat_log.append(
            f"All enemies defeated! +{total_xp} XP each, +{total_gold} gold!"
        )
        # Check for level-ups
        for m in self.fighters:
            if m.is_alive():
                level_msgs = m.check_level_up()
                for msg in level_msgs:
                    self.combat_log.append(msg)
                    self.game.sfx.play("level_up")
                    self.phase_timer += 1500  # extra time per level-up

    def _end_combat(self, won):
        if won and self.monster_refs:
            from src.settings import TILE_CHEST
            # Place chest at first monster's map position
            first = self.monster_refs[0]
            mc, mr = self.monster_map_positions.get(first, (0, 0))

            if self.source_state == "dungeon":
                dungeon_state = self.game.states.get("dungeon")
                if dungeon_state and dungeon_state.dungeon_data:
                    ddata = dungeon_state.dungeon_data
                    for mref in self.monster_refs:
                        if mref in ddata.monsters:
                            ddata.monsters.remove(mref)

                    # Place a treasure chest where the first monster stood
                    ddata.tile_map.set_tile(mc, mr, TILE_CHEST)
                    dungeon_state.pending_combat_message = (
                        "Victory! A treasure chest appears!"
                    )

            elif self.source_state == "overworld":
                overworld_state = self.game.states.get("overworld")
                if overworld_state:
                    for mref in self.monster_refs:
                        if mref in overworld_state.overworld_monsters:
                            overworld_state.overworld_monsters.remove(mref)

                    # Remember the original tile before placing the chest
                    original_tile = self.game.tile_map.get_tile(mc, mr)
                    overworld_state.chest_under_tiles[(mc, mr)] = original_tile

                    # Place a treasure chest where the orc stood
                    self.game.tile_map.set_tile(mc, mr, TILE_CHEST)
                    overworld_state.pending_combat_message = (
                        "Victory! A treasure chest appears!"
                    )

        if not won:
            # Check if this is a total party wipe
            if not any(m.is_alive() for m in self.game.party.members):
                self.game.trigger_game_over()
                return
            # Partial wipe — revive dead members with 1 HP
            for m in self.game.party.members:
                if not m.is_alive():
                    m.hp = 1

        # Clear potion buffs after combat (they last for one combat only)
        for m in self.game.party.members:
            if hasattr(m, "potion_buffs"):
                m.potion_buffs = {}

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
            monster_col=0,
            monster_row=0,
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
            shield_effects=self.shield_effects,
            shield_buffs=self.shield_buffs,
            range_buffs=self.range_buffs,
            shield_target_col=self.shield_target_col,
            shield_target_row=self.shield_target_row,
            turn_undead_effects=self.turn_undead_effects,
            charm_effects=self.charm_effects,
            sleep_effects=self.sleep_effects,
            sleep_buffs=self.sleep_buffs,
            teleport_effects=self.teleport_effects,
            invisibility_effects=self.invisibility_effects,
            invisibility_buffs=self.invisibility_buffs,
            animate_dead_effects=self.animate_dead_effects,
            summon_buffs=self.summon_buffs,
            aoe_fireball_effects=self.aoe_fireball_effects,
            aoe_explosions=self.aoe_explosions,
            lightning_bolt_effects=self.lightning_bolt_effects,
            cure_poison_effects=self.cure_poison_effects,
            bless_effects=self.bless_effects,
            bless_buffs=self.bless_buffs,
            curse_effects=self.curse_effects,
            curse_buffs=self.curse_buffs,
            is_warband=False,
            source_state=self.source_state,
            directing_action=self.directing_action,
            menu_actions=self.menu_actions,
            spell_list=self.spell_list,
            spell_cursor=self.spell_cursor,
            selected_spell=self.selected_spell,
            throw_list=self.throw_list,
            throw_cursor=self.throw_cursor,
            selected_throw=self.selected_throw,
            use_item_list=self.use_item_list,
            use_item_cursor=self.use_item_cursor,
            selected_use_item=self.selected_use_item,
            monsters=self.monsters,
            monster_positions=self.monster_positions,
            encounter_name=self.encounter_name,
        )
        if self.showing_help:
            renderer.draw_combat_help_overlay()
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
