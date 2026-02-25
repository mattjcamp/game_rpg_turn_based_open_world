"""
Combat state - tactical top-down combat on a small arena grid.

All 4 party members are placed on the arena and take turns individually.
Each can move with WASD and must be adjacent to the monster to melee attack
(bump-to-attack or menu).  The monster chases the closest party member
and attacks when adjacent.
"""

import random
import pygame

from src.states.base_state import BaseState
from src.combat_engine import (
    roll_initiative, roll_attack, roll_damage, roll_d20,
    format_modifier,
)


# ── Arena constants ──────────────────────────────────────────────
ARENA_COLS = 15
ARENA_ROWS = 10

# ── Combat phases ────────────────────────────────────────────────
PHASE_INIT        = "init"
PHASE_PLAYER      = "player"
PHASE_PLAYER_ACT  = "player_act"
PHASE_MONSTER     = "monster"
PHASE_MONSTER_ACT = "monster_act"
PHASE_VICTORY     = "victory"
PHASE_DEFEAT      = "defeat"

# ── Action indices ───────────────────────────────────────────────
ACTION_ATTACK = 0
ACTION_DEFEND = 1
ACTION_FLEE   = 2
ACTION_NAMES  = ["Attack", "Defend", "Flee"]


class CombatState(BaseState):
    """Handles a single combat encounter on a tactical arena."""

    def __init__(self, game):
        super().__init__(game)
        self.monster = None
        self.phase = PHASE_INIT
        self.selected_action = 0
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

        # Callback info for returning to source state
        self.source_state = "dungeon"
        self.monster_ref = None

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
        """Start combat. fighter param kept for compatibility but we use full party."""
        self.monster = monster
        self.source_state = source_state
        self.monster_ref = monster
        self.combat_log = []
        self.phase = PHASE_INIT
        self.selected_action = 0
        self.phase_timer = 0
        self.combat_message = ""
        self.combat_msg_timer = 0

        # Gather alive party members
        self.fighters = [m for m in self.game.party.members if m.is_alive()]
        self.active_idx = 0
        self.defending = {m: False for m in self.fighters}

        # Place party members on left side of arena, spaced out
        self.fighter_positions = {}
        start_rows = [2, 4, 6, 8]
        for i, member in enumerate(self.fighters):
            row = start_rows[i] if i < len(start_rows) else 2 + i
            self.fighter_positions[member] = (2, row)

        # Monster on the right
        self.monster_col = ARENA_COLS - 4
        self.monster_row = ARENA_ROWS // 2

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
            self.combat_log.append(f"-- {f.name}'s turn --")

    # ── Input ────────────────────────────────────────────────────

    def handle_input(self, events, keys_pressed):
        if self.phase != PHASE_PLAYER:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        if self.phase_timer > 300:
                            self.phase_timer = 300
            return

        for event in events:
            if event.type == pygame.KEYDOWN:
                # ── Menu navigation (arrow keys) ──
                if event.key == pygame.K_UP:
                    self.selected_action = (self.selected_action - 1) % len(ACTION_NAMES)
                elif event.key == pygame.K_DOWN:
                    self.selected_action = (self.selected_action + 1) % len(ACTION_NAMES)
                elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self._execute_player_action()

                # ── Arena movement (WASD) ──
                elif event.key == pygame.K_w:
                    self._try_arena_move(0, -1)
                elif event.key == pygame.K_s:
                    self._try_arena_move(0, 1)
                elif event.key == pygame.K_a:
                    self._try_arena_move(-1, 0)
                elif event.key == pygame.K_d:
                    self._try_arena_move(1, 0)

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
            if self._is_adjacent():
                self._player_attack()
            else:
                self.combat_message = "Too far! Move next to the enemy."
                self.combat_msg_timer = 1200
        elif action == ACTION_DEFEND:
            self._player_defend()
        elif action == ACTION_FLEE:
            self._player_flee()

    def _player_attack(self):
        f = self.active_fighter
        if not f:
            return

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

        if not self.monster.is_alive():
            self.phase = PHASE_VICTORY
            self.phase_timer = 2500
            xp = self.monster.xp_reward
            gold = self.monster.gold_reward
            # Distribute XP to all alive fighters
            for m in self.fighters:
                if m.is_alive():
                    m.exp += xp
            self.game.party.gold += gold
            self.combat_log.append(
                f"{self.monster.name} is defeated! +{xp} XP each, +{gold} gold!"
            )
        else:
            self._end_fighter_turn()

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
            # Next fighter's turn
            self.selected_action = 0
            self._announce_turn()

    # ── Monster actions ──────────────────────────────────────────

    def _monster_turn(self):
        """Monster AI: attack if adjacent to any fighter, otherwise move toward closest."""
        # Find the closest alive fighter
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
            # No alive targets
            self.phase = PHASE_VICTORY
            self.phase_timer = 1500
            return

        # Check adjacency to any alive fighter — attack them
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
            # Don't walk onto players
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

        if not target.is_alive():
            self.combat_log.append(f"{target.name} has fallen!")

        # Check if all party members are dead
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
            # Reset defending for all fighters, start new round
            for m in self.fighters:
                self.defending[m] = False
            self.active_idx = 0
            # Skip dead fighters at start
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
            dungeon_state = self.game.states.get("dungeon")
            if dungeon_state and dungeon_state.dungeon_data:
                monsters = dungeon_state.dungeon_data.monsters
                if self.monster_ref in monsters:
                    monsters.remove(self.monster_ref)

        if not won:
            # Revive all dead members with 1 HP
            for m in self.game.party.members:
                if not m.is_alive():
                    m.hp = 1

        self.game.change_state(self.source_state)

    # ── Drawing ──────────────────────────────────────────────────

    def draw(self, renderer):
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
            # New: pass all fighter data for multi-character rendering
            fighters=self.fighters,
            fighter_positions=self.fighter_positions,
            active_fighter=self.active_fighter,
            defending_map=self.defending,
        )
