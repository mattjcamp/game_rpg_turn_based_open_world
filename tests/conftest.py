"""
Shared fixtures and pygame mock for headless testing.

This conftest installs a lightweight pygame stub *before* any game module
is imported, so every test in the suite can safely import src.* without
needing a real display server.
"""

import sys
import types
import math

import pytest

# ── Minimal pygame mock ─────────────────────────────────────────────
# We build a mock module tree that satisfies all the imports in src/*.

pg = types.ModuleType("pygame")
pg.init = lambda: None
pg.quit = lambda: None
pg.QUIT = 256
pg.KEYDOWN = 768
pg.KEYUP = 769
pg.SRCALPHA = 0x00010000

# Key constants used in the game
_KEYS = {
    "K_UP": 273, "K_DOWN": 274, "K_LEFT": 275, "K_RIGHT": 276,
    "K_RETURN": 13, "K_SPACE": 32, "K_ESCAPE": 27,
    "K_w": 119, "K_a": 97, "K_s": 115, "K_d": 100,
    "K_h": 104, "K_l": 108, "K_p": 112, "K_e": 101,
    "K_r": 114, "K_t": 116, "K_q": 113, "K_i": 105,
    "K_m": 109, "K_n": 110, "K_y": 121, "K_1": 49,
    "K_2": 50, "K_3": 51, "K_4": 52,
}
for _name, _val in _KEYS.items():
    setattr(pg, _name, _val)


class _MockSurface:
    """Stub Surface that silently absorbs all draw/blit calls."""
    def __init__(self, *a, **kw):
        self._w = a[0][0] if a and isinstance(a[0], (tuple, list)) else 800
        self._h = a[0][1] if a and isinstance(a[0], (tuple, list)) and len(a[0]) > 1 else 600

    def fill(self, *a, **kw): pass
    def blit(self, *a, **kw): pass
    def set_clip(self, *a): pass
    def get_clip(self): return _MockRect(0, 0, 800, 600)
    def get_width(self): return self._w
    def get_height(self): return self._h
    def get_size(self): return (self._w, self._h)
    def get_rect(self, **kw): return _MockRect(0, 0, self._w, self._h)
    def set_alpha(self, *a): pass
    def convert_alpha(self): return self
    def render(self, *a, **kw): return _MockSurface((100, 20))
    def subsurface(self, *a): return self
    def copy(self): return self
    def set_at(self, *a): pass
    def get_at(self, *a): return (0, 0, 0, 255)


class _MockRect:
    def __init__(self, x=0, y=0, w=10, h=10):
        self.x = x; self.y = y; self.w = w; self.h = h
        self.width = w; self.height = h
        self.centerx = x + w // 2; self.centery = y + h // 2
        self.center = (self.centerx, self.centery)
        self.top = y; self.bottom = y + h; self.left = x; self.right = x + w
        self.topleft = (x, y); self.topright = (x + w, y)
        self.bottomleft = (x, y + h); self.bottomright = (x + w, y + h)
    def inflate(self, dx, dy): return _MockRect(self.x - dx//2, self.y - dy//2, self.w + dx, self.h + dy)
    def move(self, dx, dy): return _MockRect(self.x + dx, self.y + dy, self.w, self.h)
    def colliderect(self, other): return False
    def collidepoint(self, *a): return False


class _MockFont:
    def __init__(self, *a, **kw): pass
    def render(self, text, aa, color, *extra):
        # Return a surface with approximate width based on text length
        return _MockSurface((len(str(text)) * 8, 18))
    def size(self, text):
        return (len(str(text)) * 8, 18)
    def get_height(self): return 18


class _MockDraw:
    @staticmethod
    def rect(*a, **kw): return _MockRect()
    @staticmethod
    def circle(*a, **kw): pass
    @staticmethod
    def line(*a, **kw): pass
    @staticmethod
    def lines(*a, **kw): pass
    @staticmethod
    def polygon(*a, **kw): pass
    @staticmethod
    def ellipse(*a, **kw): pass
    @staticmethod
    def arc(*a, **kw): pass
    @staticmethod
    def aaline(*a, **kw): pass
    @staticmethod
    def aalines(*a, **kw): pass


class _MockDisplay:
    def set_mode(self, *a, **kw): return _MockSurface((800, 600))
    def set_caption(self, *a): pass
    def flip(self): pass
    def update(self, *a): pass
    def get_surface(self): return _MockSurface((800, 600))


class _MockClock:
    def tick(self, fps): return 16
    def get_fps(self): return 60.0


class _MockTime:
    Clock = _MockClock
    @staticmethod
    def get_ticks(): return 1000
    @staticmethod
    def delay(ms): pass
    @staticmethod
    def wait(ms): return ms


class _MockKey:
    def get_pressed(self):
        return [0] * 512


class _MockEvent:
    def get(self):
        return []
    def pump(self):
        pass


class _MockChannel:
    def __init__(self, *a): pass
    def play(self, *a, **kw): pass
    def stop(self): pass
    def fadeout(self, ms): pass
    def get_busy(self): return False
    def set_volume(self, v): pass
    def queue(self, *a): pass


class _MockMixer:
    def init(self, *a, **kw): pass
    def quit(self): pass
    def get_init(self): return (44100, -16, 2)
    def get_num_channels(self): return 8
    def set_num_channels(self, n): pass
    Channel = _MockChannel
    class Sound:
        def __init__(self, *a, **kw): pass
        def play(self, *a): return _MockChannel()
        def stop(self): pass
        def set_volume(self, v): pass
        def get_length(self): return 1.0
    class music:
        @staticmethod
        def load(*a): pass
        @staticmethod
        def play(*a): pass
        @staticmethod
        def stop(): pass
        @staticmethod
        def set_volume(v): pass


class _MockImage:
    @staticmethod
    def load(*a, **kw): return _MockSurface((32, 32))


class _MockTransform:
    @staticmethod
    def scale(surf, size): return _MockSurface(size)
    @staticmethod
    def rotate(surf, angle): return surf
    @staticmethod
    def flip(surf, xbool, ybool): return surf


# Wire everything up
pg.display = _MockDisplay()
pg.time = _MockTime()
pg.font = types.ModuleType("pygame.font")
pg.font.init = lambda: None
pg.font.SysFont = lambda *a, **kw: _MockFont()
pg.font.Font = lambda *a, **kw: _MockFont()
pg.draw = _MockDraw()
pg.Rect = _MockRect
pg.key = _MockKey()
pg.event = _MockEvent()
pg.Surface = _MockSurface
pg.mixer = _MockMixer()
pg.image = _MockImage()
pg.transform = _MockTransform()
pg.math = types.ModuleType("pygame.math")

# Register all mock modules before any game import
sys.modules["pygame"] = pg
sys.modules["pygame.display"] = pg.display
sys.modules["pygame.time"] = pg.time
sys.modules["pygame.font"] = pg.font
sys.modules["pygame.draw"] = pg.draw
sys.modules["pygame.mixer"] = pg.mixer
sys.modules["pygame.image"] = pg.image
sys.modules["pygame.transform"] = pg.transform
sys.modules["pygame.math"] = pg.math


# ── Shared fixtures ─────────────────────────────────────────────────

@pytest.fixture
def game():
    """Create a fresh Game instance for each test."""
    from src.game import Game
    return Game()


@pytest.fixture
def combat(game):
    """Set up a combat encounter with a single weak monster."""
    from src.monster import create_giant_rat
    monster = create_giant_rat()
    monster.hp = 1
    monster.max_hp = 1
    monster.col = 5
    monster.row = 5
    combat_state = game.states["combat"]
    combat_state.start_combat(game.party.members[0], monster,
                              source_state="overworld")
    game.change_state("combat")
    return combat_state


@pytest.fixture
def combat_multi(game):
    """Set up a combat encounter with three weak monsters."""
    from src.monster import create_giant_rat
    monsters = []
    for i in range(3):
        m = create_giant_rat()
        m.hp = 1
        m.max_hp = 1
        m.col = 5 + i
        m.row = 3
        monsters.append(m)
    combat_state = game.states["combat"]
    combat_state.start_combat(game.party.members[0], monsters,
                              source_state="overworld",
                              encounter_name="Rat Pack")
    game.change_state("combat")
    return combat_state


def make_event(key):
    """Create a fake KEYDOWN event."""
    class FakeEvent:
        type = pg.KEYDOWN
    e = FakeEvent()
    e.key = key
    return e


def tick(state, dt=0.05, steps=1):
    """Advance a state by dt seconds, `steps` times."""
    for _ in range(steps):
        state.update(dt)


def send_key(state, key):
    """Send a single keypress to a state's handle_input."""
    events = [make_event(key)]
    state.handle_input(events, [0] * 512)
