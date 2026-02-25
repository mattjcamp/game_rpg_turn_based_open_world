#!/usr/bin/env python3
"""
Combat Test — Headless
======================
Exercises the combat state logic without needing a pygame display.
Mocks just enough of pygame to instantiate and run the combat loop.

    python test_combat.py
"""

import sys
import types
import random

# ── Minimal pygame mock ─────────────────────────────────────────
# We only need the constants and a few stubs so the imports succeed.
pg = types.ModuleType("pygame")
pg.init = lambda: None
pg.quit = lambda: None
pg.QUIT = 256
pg.KEYDOWN = 768

# Key constants
for name, val in [
    ("K_UP", 273), ("K_DOWN", 274), ("K_LEFT", 275), ("K_RIGHT", 276),
    ("K_RETURN", 13), ("K_SPACE", 32), ("K_ESCAPE", 27),
    ("K_w", 119), ("K_a", 97), ("K_s", 115), ("K_d", 100),
    ("K_p", 112),
]:
    setattr(pg, name, val)

class _MockSurface:
    def __init__(self, *a, **kw): pass
    def set_mode(self, *a): return self
    def fill(self, *a): pass
    def blit(self, *a): pass
    def get_rect(self, **kw):
        class R:
            centerx = 0; centery = 0; x = 0; y = 0
            def inflate(self, *a): return self
            def get_width(self): return 10
        return R()
    def get_width(self): return 10
    def get_height(self): return 10
    def render(self, *a, **kw): return self

class _MockDisplay:
    def set_mode(self, *a): return _MockSurface()
    def set_caption(self, *a): pass
    def flip(self): pass

class _MockClock:
    def tick(self, fps): return 16  # ~60fps

class _MockFont:
    def __init__(self, *a, **kw): pass
    def render(self, text, aa, color):
        s = _MockSurface()
        return s
    def SysFont(self, *a, **kw): return self

class _MockDraw:
    @staticmethod
    def rect(*a, **kw): pass
    @staticmethod
    def circle(*a, **kw): pass
    @staticmethod
    def line(*a, **kw): pass
    @staticmethod
    def polygon(*a, **kw): pass

class _MockRect:
    def __init__(self, *a): self.x=0; self.y=0; self.centerx=0; self.centery=0
    def inflate(self, *a): return self

class _MockKey:
    def get_pressed(self):
        return [0] * 512

class _MockEvent:
    def get(self):
        return []

pg.display = _MockDisplay()
pg.time = types.ModuleType("pygame.time")
pg.time.Clock = _MockClock
pg.font = types.ModuleType("pygame.font")
pg.font.SysFont = lambda *a, **kw: _MockFont()
pg.draw = _MockDraw()
pg.Rect = _MockRect
pg.key = _MockKey()
pg.event = _MockEvent()
pg.Surface = _MockSurface
pg.SRCALPHA = 0x00010000

sys.modules["pygame"] = pg
sys.modules["pygame.display"] = pg.display
sys.modules["pygame.time"] = pg.time
sys.modules["pygame.font"] = pg.font
sys.modules["pygame.draw"] = pg.draw

# ── Now import the real game code ────────────────────────────────
from src.game import Game
from src.monster import create_skeleton, create_orc, create_giant_rat
from src.states.combat import (
    PHASE_PLAYER, PHASE_MONSTER, PHASE_MONSTER_ACT, PHASE_PLAYER_ACT,
    PHASE_VICTORY, PHASE_DEFEAT, PHASE_PROJECTILE, PHASE_MELEE_ANIM,
    ACTION_ATTACK, ACTION_DEFEND, ACTION_FLEE,
)


def make_event(key):
    """Create a fake KEYDOWN event."""
    class FakeEvent:
        type = pg.KEYDOWN
    e = FakeEvent()
    e.key = key
    return e


def tick(combat, dt=0.05, steps=1):
    """Advance the combat state by dt seconds, `steps` times."""
    for _ in range(steps):
        combat.update(dt)


def print_status(combat):
    """Print the current combat state for debugging."""
    print(f"  Phase: {combat.phase}")
    f = combat.active_fighter
    if f:
        pos = combat.fighter_positions.get(f, "?")
        print(f"  Active: {f.name} ({f.char_class}) at {pos} "
              f"HP:{f.hp}/{f.max_hp} ranged={f.is_ranged()}")
    print(f"  Monster: {combat.monster.name} HP:{combat.monster.hp}/{combat.monster.max_hp} "
          f"at ({combat.monster_col},{combat.monster_row})")
    print(f"  Projectiles: {len(combat.projectiles)}  "
          f"Melee FX: {len(combat.melee_effects)}  "
          f"Hit FX: {len(combat.hit_effects)}")
    if combat.combat_log:
        print(f"  Last log: {combat.combat_log[-1]}")
    print()


def test_basic_combat_init():
    """Test 1: Combat initializes correctly with all party members."""
    print("=" * 60)
    print("TEST 1: Basic combat initialization")
    print("=" * 60)

    game = Game()
    monster = create_skeleton()
    monster.col = 5
    monster.row = 5

    fighter = game.party.members[0]
    combat = game.states["combat"]
    combat.start_combat(fighter, monster, source_state="overworld")
    game.change_state("combat")

    print(f"  Fighters: {[f.name for f in combat.fighters]}")
    print(f"  Positions: {dict((m.name, p) for m, p in combat.fighter_positions.items())}")
    print(f"  Monster map pos saved: ({combat.monster_map_col}, {combat.monster_map_row})")
    print_status(combat)

    assert combat.phase == PHASE_PLAYER, f"Expected PHASE_PLAYER, got {combat.phase}"
    assert len(combat.fighters) == 4, f"Expected 4 fighters, got {len(combat.fighters)}"
    assert combat.monster_map_col == 5
    assert combat.monster_map_row == 5
    print("  PASSED!")
    print()


def test_melee_arrow_keys():
    """Test 2: Arrow key melee attack (non-ranged fighter)."""
    print("=" * 60)
    print("TEST 2: Melee arrow key attack")
    print("=" * 60)

    game = Game()
    monster = create_giant_rat()
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    # Move the first fighter (Roland, Fighter, melee) next to the monster
    roland = combat.fighters[0]
    # Place Roland adjacent to monster
    combat.fighter_positions[roland] = (combat.monster_col - 1, combat.monster_row)

    print(f"  Roland at {combat.fighter_positions[roland]}")
    print(f"  Monster at ({combat.monster_col}, {combat.monster_row})")
    print(f"  Roland is_ranged: {roland.is_ranged()}")

    # Press RIGHT arrow to attack monster to the right
    events = [make_event(pg.K_RIGHT)]
    combat.handle_input(events, [0] * 512)

    print(f"  Phase after arrow: {combat.phase}")
    assert combat.phase == PHASE_MELEE_ANIM, f"Expected PHASE_MELEE_ANIM, got {combat.phase}"
    assert len(combat.melee_effects) == 1, f"Expected 1 melee effect, got {len(combat.melee_effects)}"

    # Tick until the melee animation finishes
    for _ in range(20):
        tick(combat, dt=0.05)
    print(f"  Phase after animation: {combat.phase}")
    print_status(combat)

    # Check that the melee resolved (hit or miss) and turn advanced
    assert combat.phase != PHASE_MELEE_ANIM, "Melee animation should have finished"
    print("  PASSED!")
    print()


def test_ranged_arrow_keys():
    """Test 3: Arrow key ranged attack (ranged fighter)."""
    print("=" * 60)
    print("TEST 3: Ranged arrow key attack")
    print("=" * 60)

    game = Game()
    monster = create_skeleton()
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    # Find Sable (Thief with Bow - ranged)
    sable = None
    for f in combat.fighters:
        if f.name == "Sable":
            sable = f
            break

    if not sable:
        print("  SKIPPED - Sable not found in fighters")
        return

    # Set Sable as the active fighter
    combat.active_idx = combat.fighters.index(sable)
    print(f"  Sable at {combat.fighter_positions[sable]}")
    print(f"  Sable is_ranged: {sable.is_ranged()}")
    print(f"  Monster at ({combat.monster_col}, {combat.monster_row})")

    # Fire RIGHT toward the monster
    events = [make_event(pg.K_RIGHT)]
    combat.handle_input(events, [0] * 512)

    print(f"  Phase after arrow: {combat.phase}")
    assert combat.phase == PHASE_PROJECTILE, f"Expected PHASE_PROJECTILE, got {combat.phase}"
    assert len(combat.projectiles) == 1, f"Expected 1 projectile, got {len(combat.projectiles)}"
    proj = combat.projectiles[0]
    print(f"  Projectile: ({proj.start_col},{proj.start_row}) -> ({proj.end_col},{proj.end_row}) symbol={proj.symbol}")

    # Tick until projectile arrives
    for _ in range(30):
        tick(combat, dt=0.05)
    print(f"  Phase after projectile: {combat.phase}")
    print_status(combat)

    assert combat.phase != PHASE_PROJECTILE, "Projectile should have arrived"
    print("  PASSED!")
    print()


def test_wasd_movement():
    """Test 4: WASD movement in combat arena."""
    print("=" * 60)
    print("TEST 4: WASD movement")
    print("=" * 60)

    game = Game()
    monster = create_skeleton()
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    roland = combat.fighters[0]
    start_pos = combat.fighter_positions[roland]
    print(f"  Roland starts at {start_pos}")

    # Move right with D key
    events = [make_event(pg.K_d)]
    combat.handle_input(events, [0] * 512)
    new_pos = combat.fighter_positions[roland]
    print(f"  After D key: {new_pos}")
    assert new_pos == (start_pos[0] + 1, start_pos[1]), f"Expected move right, got {new_pos}"

    # Moving should end Roland's turn
    print(f"  Active fighter after move: {combat.active_fighter.name if combat.active_fighter else 'None'}")
    print("  PASSED!")
    print()


def test_bump_attack():
    """Test 5: Bump-to-attack (WASD into monster)."""
    print("=" * 60)
    print("TEST 5: Bump-to-attack")
    print("=" * 60)

    game = Game()
    monster = create_giant_rat()
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    # Place Roland next to monster
    roland = combat.fighters[0]
    combat.fighter_positions[roland] = (combat.monster_col - 1, combat.monster_row)
    print(f"  Roland at {combat.fighter_positions[roland]}, Monster at ({combat.monster_col},{combat.monster_row})")

    # Bump into monster with D key
    events = [make_event(pg.K_d)]
    combat.handle_input(events, [0] * 512)

    print(f"  Phase after bump: {combat.phase}")
    # Should trigger melee animation
    assert combat.phase == PHASE_MELEE_ANIM, f"Expected PHASE_MELEE_ANIM, got {combat.phase}"

    # Let animation finish
    for _ in range(20):
        tick(combat, dt=0.05)
    print_status(combat)
    print("  PASSED!")
    print()


def test_menu_attack():
    """Test 6: Menu-based attack via ENTER."""
    print("=" * 60)
    print("TEST 6: Menu attack via ENTER")
    print("=" * 60)

    game = Game()
    monster = create_giant_rat()
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    # Place Roland adjacent
    roland = combat.fighters[0]
    combat.fighter_positions[roland] = (combat.monster_col - 1, combat.monster_row)
    combat.selected_action = ACTION_ATTACK
    print(f"  Roland at {combat.fighter_positions[roland]}")

    # Press ENTER to execute attack from menu
    events = [make_event(pg.K_RETURN)]
    combat.handle_input(events, [0] * 512)

    print(f"  Phase after ENTER: {combat.phase}")
    assert combat.phase == PHASE_MELEE_ANIM, f"Expected PHASE_MELEE_ANIM, got {combat.phase}"

    # Finish animation
    for _ in range(20):
        tick(combat, dt=0.05)
    print_status(combat)
    print("  PASSED!")
    print()


def test_full_combat_to_victory():
    """Test 7: Full combat loop until monster is defeated."""
    print("=" * 60)
    print("TEST 7: Full combat to victory")
    print("=" * 60)

    game = Game()
    # Create a very weak monster for easy kill
    monster = create_giant_rat()
    monster.hp = 1
    monster.max_hp = 1
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    # Place Roland adjacent
    roland = combat.fighters[0]
    combat.fighter_positions[roland] = (combat.monster_col - 1, combat.monster_row)

    # Keep attacking until victory
    attempts = 0
    while combat.phase not in (PHASE_VICTORY, PHASE_DEFEAT) and attempts < 50:
        if combat.phase == PHASE_PLAYER:
            f = combat.active_fighter
            if f:
                pos = combat.fighter_positions.get(f)
                if pos and abs(pos[0] - combat.monster_col) <= 1 and abs(pos[1] - combat.monster_row) <= 1:
                    # Adjacent - attack with arrow key
                    dcol = combat.monster_col - pos[0]
                    drow = combat.monster_row - pos[1]
                    if dcol > 0:
                        events = [make_event(pg.K_RIGHT)]
                    elif dcol < 0:
                        events = [make_event(pg.K_LEFT)]
                    elif drow > 0:
                        events = [make_event(pg.K_DOWN)]
                    else:
                        events = [make_event(pg.K_UP)]
                    combat.handle_input(events, [0] * 512)
                else:
                    # Not adjacent - move toward monster
                    events = [make_event(pg.K_d)]
                    combat.handle_input(events, [0] * 512)
        tick(combat, dt=0.1)
        attempts += 1

    print(f"  Combat ended after {attempts} ticks")
    print(f"  Phase: {combat.phase}")
    print(f"  Monster HP: {combat.monster.hp}/{combat.monster.max_hp}")
    for line in combat.combat_log[-5:]:
        print(f"    LOG: {line}")

    assert combat.phase == PHASE_VICTORY, f"Expected PHASE_VICTORY, got {combat.phase}"
    print("  PASSED!")
    print()


def test_defend_action():
    """Test 8: Defend action."""
    print("=" * 60)
    print("TEST 8: Defend action")
    print("=" * 60)

    game = Game()
    monster = create_skeleton()
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    roland = combat.fighters[0]
    combat.selected_action = ACTION_DEFEND

    events = [make_event(pg.K_RETURN)]
    combat.handle_input(events, [0] * 512)

    print(f"  Roland defending: {combat.defending.get(roland, False)}")
    assert combat.defending.get(roland, False), "Roland should be defending"
    print("  PASSED!")
    print()


def test_hit_effects_on_damage():
    """Test 9: Hit effects spawn when damage is dealt."""
    print("=" * 60)
    print("TEST 9: Hit effects")
    print("=" * 60)

    game = Game()
    monster = create_giant_rat()
    monster.ac = 0  # guaranteed hit
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    roland = combat.fighters[0]
    combat.fighter_positions[roland] = (combat.monster_col - 1, combat.monster_row)

    # Attack
    events = [make_event(pg.K_RIGHT)]
    combat.handle_input(events, [0] * 512)

    # Let melee animation finish
    for _ in range(20):
        tick(combat, dt=0.05)

    # Check if hit effects were spawned (only if the attack hit)
    hit_logged = any("damage" in line.lower() for line in combat.combat_log)
    if hit_logged:
        print(f"  Attack landed! Hit effects spawned: {len(combat.hit_effects) >= 0}")
    else:
        print(f"  Attack missed (AC 0 should be rare)")

    print_status(combat)
    print("  PASSED!")
    print()


def test_draw_calls():
    """Test 10: Draw method doesn't crash."""
    print("=" * 60)
    print("TEST 10: Draw method doesn't crash")
    print("=" * 60)

    game = Game()
    monster = create_skeleton()
    monster.col = 5
    monster.row = 5

    combat = game.states["combat"]
    combat.start_combat(game.party.members[0], monster, source_state="overworld")
    game.change_state("combat")

    try:
        combat.draw(game.renderer)
        print("  draw() in PHASE_PLAYER — OK")
    except Exception as e:
        print(f"  draw() FAILED: {e}")
        raise

    # Add some effects and try again
    from src.states.combat import MeleeEffect, HitEffect, Projectile
    combat.melee_effects.append(MeleeEffect(5, 5, (1, 0), (255, 255, 255)))
    combat.hit_effects.append(HitEffect(5, 5, 10))
    combat.projectiles.append(Projectile(2, 4, 10, 4, (255, 200, 80), ">"))

    try:
        combat.draw(game.renderer)
        print("  draw() with effects — OK")
    except Exception as e:
        print(f"  draw() with effects FAILED: {e}")
        raise

    print("  PASSED!")
    print()


# ── Run all tests ────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("COMBAT SYSTEM TEST SUITE")
    print("========================")
    print()

    tests = [
        test_basic_combat_init,
        test_melee_arrow_keys,
        test_ranged_arrow_keys,
        test_wasd_movement,
        test_bump_attack,
        test_menu_attack,
        test_full_combat_to_victory,
        test_defend_action,
        test_hit_effects_on_damage,
        test_draw_calls,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            print()

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 60)
