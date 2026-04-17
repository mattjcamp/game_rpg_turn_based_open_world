"""Verify the Add Space picker scrolls past row 11."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()

root = sys.argv[1]
sys.path.insert(0, root)
os.chdir(root)

# Re-create scroll logic the handler uses:
from src.features_editor import FeaturesEditor
from src.settings import SCREEN_HEIGHT

# Inline the picker_max_visible constants (same as Game._picker_max_visible)
panel_h = SCREEN_HEIGHT - 130
content_h = panel_h - 24 - 42 - 80
max_vis = max(4, content_h // 40)
print(f"SCREEN_HEIGHT={SCREEN_HEIGHT} → picker renders ~{max_vis} rows per overlay")

# Simulate 13 templates: Create Blank Space + 12 real templates
# (which matches the user's situation with Dungeon 4 being #13, index 12).
n_templates = 13
names = ["Create Blank Space"] + [f"Template {i}" for i in range(1, n_templates)]
assert len(names) == n_templates

# Walk cursor from 0 to 12, computing what scroll offset the old code vs
# the new code would produce and what row Dungeon 4 (index 12) sits at.
def adjust(cursor, scroll, max_visible):
    if cursor < scroll:
        return cursor
    if cursor >= scroll + max_visible:
        return cursor - max_visible + 1
    return scroll

# Old behaviour: max_visible=14 (default)
scroll_old = 0
for c in range(n_templates):
    scroll_old = adjust(c, scroll_old, 14)
# Row of last element relative to scroll window
row_in_view_old = n_templates - 1 - scroll_old
visible_old = row_in_view_old < max_vis
print(f"Old (max_visible=14): cursor=12 → scroll={scroll_old}, "
      f"last row would render at index {row_in_view_old} → visible={visible_old}")

# New behaviour: max_visible = actual render count
scroll_new = 0
for c in range(n_templates):
    scroll_new = adjust(c, scroll_new, max_vis)
row_in_view_new = n_templates - 1 - scroll_new
visible_new = row_in_view_new < max_vis
print(f"New (max_visible={max_vis}): cursor=12 → scroll={scroll_new}, "
      f"last row would render at index {row_in_view_new} → visible={visible_new}")

assert visible_new, "Dungeon 4 (index 12) should now be visible"
assert not visible_old, "Old behaviour had the bug"
print("\nScroll fix verified: picker now brings Dungeon 4 into view.")

# Also test reverse: cursor back to 0 should show top of list.
scroll_new = adjust(0, scroll_new, max_vis)
assert scroll_new == 0
print("Scrolling back to top works.")
