/**
 * XP awards & level-up logic.
 *
 * Mirrors the Python game's `Fighter.check_level_up`:
 *
 *   - Required XP for the *next* level = current_level × exp_per_level.
 *     `exp_per_level` comes from the class template (default 1000), with
 *     a possible race override (Humans = 750).
 *   - Each level-up adds `hp_per_level + STR mod` HP (minimum +1).
 *   - Casters also gain `mp_per_level + casting_stat mod` MP, where the
 *     casting stat is named by `mp_source.ability` (single-stat) or
 *     derived from `mp_source.abilities + mode` (dual-stat). Non-casters
 *     (mp_per_level === 0) get no MP gain.
 *   - Multiple level-ups in one award are processed sequentially —
 *     enough XP can carry a member through several thresholds at once.
 */

import type { PartyMember } from "./Party";
import type { ClassTemplate, RaceInfo } from "./Classes";

export interface LevelUpEvent {
  name: string;
  newLevel: number;
  hpGain: number;
  mpGain: number;
  message: string;
}

/** D&D-style modifier (10 = 0, 18 = +4, 8 = -1, …). */
function abilityMod(stat: number): number {
  return Math.floor((stat - 10) / 2);
}

function castingMod(member: PartyMember, tpl: ClassTemplate): number {
  const src = tpl.mpSource;
  if (!src) return 0;
  if (src.ability) {
    return abilityMod(member[src.ability]);
  }
  if (Array.isArray(src.abilities) && src.abilities.length > 0) {
    const vals = src.abilities.map((a) => member[a]);
    if (src.mode === "higher") return abilityMod(Math.max(...vals));
    if (src.mode === "average") {
      const avg = Math.floor(vals.reduce((a, b) => a + b, 0) / vals.length);
      return abilityMod(avg);
    }
    return abilityMod(Math.min(...vals)); // Python default
  }
  return 0;
}

/** XP threshold to reach `member.level + 1`. */
export function xpForNextLevel(
  member: PartyMember,
  tpl: ClassTemplate,
  race: RaceInfo | null,
): number {
  const xpPer = race?.expPerLevel ?? tpl.expPerLevel;
  return member.level * xpPer;
}

/**
 * Add XP and apply any level-ups in place. Returns one event per
 * level gained so the caller can show messages / play sfx / animate.
 *
 * Mutates `member.exp`, `member.level`, `member.maxHp`, `member.hp`,
 * and (for casters) `member.maxMp`, `member.mp`. HP / MP are bumped
 * by the gain on each level so a wounded member partially heals on
 * level-up — same behaviour as the Python game.
 */
export function awardXp(
  member: PartyMember,
  xp: number,
  tpl: ClassTemplate,
  race: RaceInfo | null,
): LevelUpEvent[] {
  if (xp <= 0) return [];
  member.exp += xp;
  const events: LevelUpEvent[] = [];
  const xpPer = race?.expPerLevel ?? tpl.expPerLevel;
  while (member.exp >= member.level * xpPer) {
    member.level += 1;

    const hpGain = Math.max(1, tpl.hpPerLevel + abilityMod(member.strength));
    member.maxHp += hpGain;
    member.hp = Math.min(member.hp + hpGain, member.maxHp);

    let mpGain = 0;
    if (tpl.mpPerLevel > 0) {
      mpGain = Math.max(0, tpl.mpPerLevel + castingMod(member, tpl));
      if (mpGain > 0) {
        if (member.maxMp == null) member.maxMp = 0;
        if (member.mp == null) member.mp = 0;
        member.maxMp += mpGain;
        member.mp = Math.min(member.mp + mpGain, member.maxMp);
      }
    }

    let msg = `${member.name} reached Level ${member.level}! HP+${hpGain}`;
    if (mpGain > 0) msg += ` MP+${mpGain}`;
    events.push({
      name: member.name,
      newLevel: member.level,
      hpGain,
      mpGain,
      message: msg,
    });
  }
  return events;
}
