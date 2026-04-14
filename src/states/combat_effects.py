"""
Visual effect classes for the combat system.

These are short-lived animation objects that track progress via a timer
and an ``alive`` flag.  The renderer reads their state each frame to
draw the corresponding visual; the combat update loop checks ``alive``
to know when an animation phase has finished.
"""

import math

# ── Projectile speed (pixels per second) ─────────────────────────
PROJECTILE_SPEED = 480
FIREBALL_SPEED   = 320   # slower than arrow for drama


# ── Base timer effect ────────────────────────────────────────────

class _TimerEffect:
    """Base class for effects that count down from a fixed duration.

    Subclasses only need to set ``DURATION`` and override ``__init__``
    to store any extra fields they need.
    """

    DURATION = 1.0  # seconds — override in subclasses

    def __init__(self):
        self.timer = self.DURATION
        self.alive = True

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = 0
            self.alive = False

    @property
    def progress(self):
        """0 = just started, 1 = done."""
        return 1.0 - (self.timer / self.DURATION)


# ── Travelling-projectile base ───────────────────────────────────

class _TravelEffect:
    """Base for effects that travel from one tile to another."""

    SPEED = PROJECTILE_SPEED  # px/s — override per subclass

    def __init__(self, start_col, start_row, end_col, end_row, **extra):
        self.start_col = start_col
        self.start_row = start_row
        self.end_col = end_col
        self.end_row = end_row
        self.progress = 0.0  # 0 = start, 1 = arrived
        self.alive = True
        # Store any extra keyword attrs
        for k, v in extra.items():
            setattr(self, k, v)

    def update(self, dt):
        dx = self.end_col - self.start_col
        dy = self.end_row - self.start_row
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.01:
            self.progress = 1.0
            self.alive = False
            return
        tiles_per_sec = self.SPEED / 32.0
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


# ── Concrete effect classes ──────────────────────────────────────

class Projectile(_TravelEffect):
    """A projectile traveling across the arena."""
    SPEED = PROJECTILE_SPEED

    def __init__(self, start_col, start_row, end_col, end_row,
                 color=(255, 255, 255), symbol="*"):
        super().__init__(start_col, start_row, end_col, end_row)
        self.color = color
        self.symbol = symbol


class MeleeEffect(_TimerEffect):
    """A short-lived slash animation at a target tile."""
    DURATION = 0.35

    def __init__(self, col, row, direction, color=(255, 255, 255)):
        super().__init__()
        self.col = col
        self.row = row
        self.direction = direction  # (dcol, drow)
        self.color = color


class HitEffect(_TimerEffect):
    """A flash/shake on a target when they take damage."""
    DURATION = 0.3

    def __init__(self, col, row, damage=0):
        super().__init__()
        self.col = col
        self.row = row
        self.damage = damage


class _BackstabEffect(_TimerEffect):
    """A brief purple-white flash for the Thief's backstab.

    Rendered as expanding rings with sparkles — visually distinct from
    the normal HitEffect so the player can tell a backstab crit happened.
    """
    DURATION = 0.5

    def __init__(self, col, row):
        super().__init__()
        self.col = col
        self.row = row
        self.damage = 0  # not used for rendering damage numbers


class FireballEffect(_TravelEffect):
    """An animated fireball traveling across the arena."""
    SPEED = FIREBALL_SPEED

    def __init__(self, start_col, start_row, end_col, end_row):
        super().__init__(start_col, start_row, end_col, end_row)
        self.radius = 6  # base visual radius in pixels


class FireballExplosion(_TimerEffect):
    """A brief explosion effect when the fireball hits."""
    DURATION = 0.5

    def __init__(self, col, row):
        super().__init__()
        self.col = col
        self.row = row


class HealEffect(_TimerEffect):
    """A glowing heal animation over a party member."""
    DURATION = 0.8

    def __init__(self, col, row, amount=0):
        super().__init__()
        self.col = col
        self.row = row
        self.amount = amount


class ShieldEffect(_TimerEffect):
    """A blue shield glow animation over a party member."""
    DURATION = 0.8

    def __init__(self, col, row, ac_bonus=0):
        super().__init__()
        self.col = col
        self.row = row
        self.ac_bonus = ac_bonus


class TurnUndeadEffect(_TimerEffect):
    """A holy blast radiating out from the caster toward the monster."""
    DURATION = 1.2

    def __init__(self, caster_col, caster_row, monster_col, monster_row, damage=0):
        super().__init__()
        self.caster_col = caster_col
        self.caster_row = caster_row
        self.monster_col = monster_col
        self.monster_row = monster_row
        self.damage = damage


class CharmEffect(_TimerEffect):
    """A swirling pink/purple enchantment spiral around the target monster."""
    DURATION = 1.4

    def __init__(self, col, row, success=True):
        super().__init__()
        self.col = col
        self.row = row
        self.success = success


class SleepEffect(_TimerEffect):
    """A soft blue/purple mist descending over the target monster."""
    DURATION = 1.2

    def __init__(self, col, row, success=True):
        super().__init__()
        self.col = col
        self.row = row
        self.success = success


class TeleportEffect(_TimerEffect):
    """A silvery mist effect for Misty Step — plays at both origin and destination."""
    DURATION = 1.0

    def __init__(self, from_col, from_row, to_col, to_row):
        super().__init__()
        self.from_col = from_col
        self.from_row = from_row
        self.to_col = to_col
        self.to_row = to_row


class InvisibilityEffect(_TimerEffect):
    """A shimmer/fade animation when a character turns invisible."""
    DURATION = 1.0

    def __init__(self, col, row):
        super().__init__()
        self.col = col
        self.row = row


class AnimateDeadEffect(_TimerEffect):
    """A dark green/black rising-from-the-ground animation for summoning a skeleton."""
    DURATION = 1.4

    def __init__(self, col, row):
        super().__init__()
        self.col = col
        self.row = row


class AoeFireballEffect(_TravelEffect):
    """An AoE fireball projectile traveling to a target tile."""
    SPEED = FIREBALL_SPEED

    def __init__(self, start_col, start_row, end_col, end_row):
        super().__init__(start_col, start_row, end_col, end_row)
        self.radius = 8  # base visual radius in pixels (bigger than normal fireball)


class AoeExplosionEffect(_TimerEffect):
    """A massive expanding explosion covering a multi-tile radius."""
    DURATION = 1.2

    def __init__(self, col, row, radius=3):
        super().__init__()
        self.col = col
        self.row = row
        self.radius = radius


class BlessEffect(_TimerEffect):
    """A golden radiance expanding from the caster to all allies."""
    DURATION = 1.0

    def __init__(self, col, row):
        super().__init__()
        self.col = col
        self.row = row


class CurseEffect(_TimerEffect):
    """A dark purple miasma settling on a cursed enemy."""
    DURATION = 1.0

    def __init__(self, col, row):
        super().__init__()
        self.col = col
        self.row = row


class CurePoisonEffect(_TimerEffect):
    """A green-to-white cleansing glow over a cured ally."""
    DURATION = 1.0

    def __init__(self, col, row):
        super().__init__()
        self.col = col
        self.row = row


class LightningBoltEffect(_TimerEffect):
    """A crackling bolt of lightning along a straight line of tiles.

    Unlike projectiles, the bolt appears all at once along its path and
    crackles for its duration before dissipating.
    """
    DURATION = 1.0

    def __init__(self, tiles):
        """*tiles* is a list of (col, row) tuples the bolt passes through."""
        super().__init__()
        self.tiles = tiles  # ordered list of (col, row)


class MonsterSpellEffect(_TimerEffect):
    """A brief visual effect when a monster casts a spell-like ability.

    Colour coded by spell type:
        sleep  -> purple/blue
        curse  -> dark red
        heal   -> green
        poison -> sickly green
    """
    DURATION = 1.0

    # Default colour per spell type
    COLORS = {
        "sleep":        (120,  80, 200),
        "curse":        (200,  60,  60),
        "heal_self":    ( 60, 200,  80),
        "heal_ally":    ( 60, 200,  80),
        "poison":       (100, 180,  40),
        "breath_fire":  (255, 120,  30),
    }

    def __init__(self, col, row, spell_type="sleep", label="", success=True):
        super().__init__()
        self.col = col
        self.row = row
        self.spell_type = spell_type
        self.color = self.COLORS.get(spell_type, (200, 200, 200))
        self.label = label
        self.success = success


class ShatterEffect(_TimerEffect):
    """A dramatic weapon/armor shatter burst.

    Rendered as expanding red-orange shards radiating outward from the
    target tile, with a brief screen-shake cue.
    """
    DURATION = 0.7

    def __init__(self, col, row, item_name=""):
        super().__init__()
        self.col = col
        self.row = row
        self.item_name = item_name
        self.damage = 0  # not used for damage numbers
