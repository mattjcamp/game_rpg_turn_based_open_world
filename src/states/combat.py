"""
Combat state - tactical top-down combat on a small arena grid.

The player moves around the arena with WASD and must be adjacent to the
monster to attack (bump-to-attack or menu).  The monster chases the player
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
        self.fighter = None
        self.monster = None
        self.phase = PHASE_INIT
        self.selected_action = 0
        self.combat_log = []
        self.phase_timer = 0
        self.defending = False
        self.player_goes_first = True

        # Arena positions
        self.player_col = 3
        self.player_row = ARENA_ROWS // 2
        self.monster_col = ARENA_COLS - 4
        self.monster_row = ARENA_ROWS // 2

        # Temporary combat message (e.g. "Too far!")
        self.combat_message = ""
        self.combat_msg_timer = 0

        # Callback info for returning to dungeon
        self.source_state = "dungeon"
        self.monster_ref = None

    # ── Arena helpers ────────────────────────────────────────────

    @staticmethod
    def _is_arena_wall(col, row):
        """True if the tile is part of the arena perimeter wall."""
        return col <= 0 or col >= ARENA_COLS - 1 or row <= 0 or row >= ARENA_ROWS - 1

    def _is_adjacent(self):
        """True if the player is adjacent to the monster (Chebyshev dist 1)."""
        dx = abs(self.player_col - self.monster_col)
        dy = abs(self.player_row - self.monster_row)
        return max(dx, dy) == 1

    # ── Setup ────────────────────────────────────────────────────

    def start_combat(self, fighter, monster, source_state="dungeon"):
        self.fighter = fighter
        self.monster = monster
        self.source_state = source_state
        self.monster_ref = monster
        self.combat_log = []
        self.phase = PHASE_INIT
        self.selected_action = 0
        self.defending = False
        self.phase_timer = 0

        # Place combatants on the arena
        self.player_col = 3
        self.player_row = ARENA_ROWS // 2
        self.monster_col = ARENA_COLS - 4
        self.monster_row = ARENA_ROWS // 2

        self.combat_message = ""
        self.combat_msg_timer = 0

    def enter(self):
        player_init, player_roll = roll_initiative(self.fighter.dex_mod)
        monster_init, monster_roll = roll_initiative(
            self.monster.attack_bonus // 2
        )

        self.combat_log.append(
            f"--- {self.fighter.name} vs {self.monster.name}! ---"
        )
        self.combat_log.append(
            f"Initiative: {self.fighter.name} rolls {player_roll} "
            f"({format_modifier(self.fighter.dex_mod)}) = {player_init}"
        )
        self.combat_log.append(
            f"Initiative: {self.monster.name} rolls {monster_roll} = {monster_init}"
        )

        self.player_goes_first = player_init >= monster_init
        if self.player_goes_first:
            self.combat_log.append(f"{self.fighter.name} acts first!")
        else:
            self.combat_log.append(f"{self.monster.name} acts first!")

        if self.player_goes_first:
            self.phase = PHASE_PLAYER
        else:
            self.phase = PHASE_MONSTER
            self.phase_timer = 1200

    def exit(self):
        pass

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
        """Move the player in the arena. Bump-attacks the monster."""
        new_col = self.player_col + dcol
        new_row = self.player_row + drow

        # Bump attack: moving into the monster's tile
        if new_col == self.monster_col and new_row == self.monster_row:
            self._player_attack()
            return

        # Normal movement
        if not self._is_arena_wall(new_col, new_row):
            self.player_col = new_col
            self.player_row = new_row
            self.phase = PHASE_PLAYER_ACT
            self.phase_timer = 250

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
        self.defending = False
        atk_bonus = self.fighter.get_attack_bonus()
        hit, roll, total, crit = roll_attack(atk_bonus, self.monster.ac)

        if crit:
            self.combat_log.append(
                f"{self.fighter.name} rolls {roll} — CRITICAL HIT!"
            )
        elif hit:
            self.combat_log.append(
                f"{self.fighter.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {self.monster.ac} — Hit!"
            )
        else:
            self.combat_log.append(
                f"{self.fighter.name} rolls {roll} ({format_modifier(atk_bonus)}) "
                f"= {total} vs AC {self.monster.ac} — Miss!"
            )

        if hit:
            dice_count, dice_sides, dmg_bonus = self.fighter.get_damage_dice()
            damage = roll_damage(dice_count, dice_sides, dmg_bonus, critical=crit)
            self.monster.hp = max(0, self.monster.hp - damage)
            weapon = self.fighter.weapon
            self.combat_log.append(
                f"{self.fighter.name} deals {damage} damage with {weapon}!"
            )

        if not self.monster.is_alive():
            self.phase = PHASE_VICTORY
            self.phase_timer = 2500
            xp = self.monster.xp_reward
            gold = self.monster.gold_reward
            self.fighter.exp += xp
            self.game.party.gold += gold
            self.combat_log.append(
                f"{self.monster.name} is defeated! +{xp} XP, +{gold} gold!"
            )
        else:
            self.phase = PHASE_PLAYER_ACT
            self.phase_timer = 800

    def _player_defend(self):
        self.defending = True
        self.combat_log.append(
            f"{self.fighter.name} takes a defensive stance! (+2 AC)"
        )
        self.phase = PHASE_PLAYER_ACT
        self.phase_timer = 600

    def _player_flee(self):
        self.defending = False
        roll = roll_d20()
        total = roll + self.fighter.dex_mod
        dc = 10

        if total >= dc:
            self.combat_log.append(
                f"{self.fighter.name} rolls {roll} "
                f"({format_modifier(self.fighter.dex_mod)}) = {total} — Escaped!"
            )
            self.phase = PHASE_VICTORY
            self.phase_timer = 1500
            self.combat_log.append("You flee the battle!")
        else:
            self.combat_log.append(
                f"{self.fighter.name} rolls {roll} "
                f"({format_modifier(self.fighter.dex_mod)}) = {total} vs DC {dc} — Failed!"
            )
            self.phase = PHASE_PLAYER_ACT
            self.phase_timer = 600

    # ── Monster actions ──────────────────────────────────────────

    def _monster_turn(self):
        """Monster AI: attack if adjacent, otherwise move toward player."""
        if self._is_adjacent():
            self._monster_attack_player()
        else:
            self._monster_move_toward_player()
            self.combat_log.append(f"{self.monster.name} moves closer...")
            self.phase = PHASE_MONSTER_ACT
            self.phase_timer = 500

    def _monster_move_toward_player(self):
        """Step 1 tile toward the player (Chebyshev)."""
        mc, mr = self.monster_col, self.monster_row
        pc, pr = self.player_col, self.player_row

        best_dist = max(abs(mc - pc), abs(mr - pr))
        candidates = []

        for dcol, drow in [
            (0, -1), (0, 1), (-1, 0), (1, 0),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ]:
            nc, nr = mc + dcol, mr + drow
            if nc == pc and nr == pr:
                continue  # don't walk onto the player
            if self._is_arena_wall(nc, nr):
                continue
            dist = max(abs(nc - pc), abs(nr - pr))
            if dist < best_dist:
                candidates = [(nc, nr)]
                best_dist = dist
            elif dist == best_dist:
                candidates.append((nc, nr))

        if candidates:
            nc, nr = random.choice(candidates)
            self.monster_col = nc
            self.monster_row = nr

    def _monster_attack_player(self):
        """The monster attacks the player."""
        player_ac = self.fighter.get_ac()
        if self.defending:
            player_ac += 2

        hit, roll, total, crit = roll_attack(
            self.monster.attack_bonus, player_ac
        )

        ac_display = f"AC {player_ac}"
        if self.defending:
            ac_display += " (defending)"

        if crit:
            self.combat_log.append(
                f"{self.monster.name} rolls {roll} — CRITICAL HIT!"
            )
        elif hit:
            self.combat_log.append(
                f"{self.monster.name} rolls {roll} "
                f"({format_modifier(self.monster.attack_bonus)}) "
                f"= {total} vs {ac_display} — Hit!"
            )
        else:
            self.combat_log.append(
                f"{self.monster.name} rolls {roll} "
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
            self.fighter.hp = max(0, self.fighter.hp - damage)
            self.combat_log.append(
                f"{self.monster.name} deals {damage} damage!"
            )

        if not self.fighter.is_alive():
            self.phase = PHASE_DEFEAT
            self.phase_timer = 2500
            self.combat_log.append(f"{self.fighter.name} has fallen!")
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
            self.defending = False
            self.phase = PHASE_PLAYER
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
            self.fighter.hp = 1

        self.game.change_state(self.source_state)

    # ── Drawing ──────────────────────────────────────────────────

    def draw(self, renderer):
        renderer.draw_combat_arena(
            fighter=self.fighter,
            monster=self.monster,
            combat_log=self.combat_log,
            phase=self.phase,
            selected_action=self.selected_action,
            defending=self.defending,
            player_col=self.player_col,
            player_row=self.player_row,
            monster_col=self.monster_col,
            monster_row=self.monster_row,
            is_adjacent=self._is_adjacent(),
            combat_message=self.combat_message,
        )
