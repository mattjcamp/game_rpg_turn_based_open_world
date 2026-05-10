"use client";

/**
 * Character creator — port of the title-screen "Create Character"
 * flow at `src/game.py:_cc_init`/`_handle_char_create_input`.
 *
 * Six steps in a multi-page form:
 *   1. Name
 *   2. Race + gender
 *   3. Class (filtered by what the chosen race can be)
 *   4. Avatar — pick the 32×32 sprite that represents this character
 *   5. Stats — every attribute starts at the floor (8) and the player
 *      distributes BONUS_POINTS (15) on top, up to STAT_MAX (18).
 *      Racial modifiers add on top at runtime. The 15-point budget
 *      is deliberately tight: maxing one stat costs 10, leaving 5 to
 *      scatter, so the player must accept real weaknesses rather
 *      than max-ing both their primary AND Constitution. Forces a
 *      meaningful build choice instead of converging to one optimal
 *      stat line.
 *   6. Confirm → append to roster, save to localStorage, return to
 *      /party
 *
 * The roster is loaded once on mount so the player can keep adding
 * characters without flipping back to the formation page; "Save"
 * appends and bumps you back to /party.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  loadParty,
  saveStoredRoster,
  _clearPartyCache,
  spriteForMember,
  type Party,
  type PartyMember,
} from "@/game/world/Party";
import { dataPath, assetUrl } from "@/game/world/Module";

// ── Static catalogs (mirror data/races.json + data/classes/*.json) ──

const RACES = ["Human", "Dwarf", "Halfling", "Elf", "Gnome"] as const;
type RaceName = (typeof RACES)[number];

const RACE_MODS: Record<RaceName, Record<StatKey, number>> = {
  Human:    { strength:  0, dexterity:  0, constitution:  0, intelligence:  0, wisdom: 0 },
  Dwarf:    { strength:  2, dexterity: -1, constitution:  2, intelligence:  0, wisdom: 1 },
  Halfling: { strength: -2, dexterity:  2, constitution:  0, intelligence:  0, wisdom: 1 },
  Elf:      { strength: -1, dexterity:  1, constitution: -1, intelligence:  2, wisdom: 0 },
  Gnome:    { strength: -1, dexterity:  0, constitution:  0, intelligence:  2, wisdom: 1 },
};

const GENDERS = ["Male", "Female"] as const;

const CLASSES = [
  "Fighter", "Thief", "Wizard", "Cleric",
  "Ranger", "Paladin", "Druid", "Alchemist",
] as const;
type ClassName = (typeof CLASSES)[number];

/** Wizards are restricted to magically-attuned races; everyone else
 *  is open to all five. Mirrors `data/classes/*.json` `allowed_races`. */
const CLASS_RACES: Record<ClassName, ReadonlySet<RaceName>> = {
  Fighter:   new Set(["Human", "Dwarf", "Halfling", "Elf", "Gnome"]),
  Thief:     new Set(["Human", "Dwarf", "Halfling", "Elf", "Gnome"]),
  Cleric:    new Set(["Human", "Dwarf", "Halfling", "Elf", "Gnome"]),
  Ranger:    new Set(["Human", "Dwarf", "Halfling", "Elf", "Gnome"]),
  Paladin:   new Set(["Human", "Dwarf", "Halfling", "Elf", "Gnome"]),
  Druid:     new Set(["Human", "Dwarf", "Halfling", "Elf", "Gnome"]),
  Alchemist: new Set(["Human", "Dwarf", "Halfling", "Elf", "Gnome"]),
  Wizard:    new Set(["Human", "Elf", "Gnome"]),
};

/** Approximate hp_per_level from data/classes/*.json. Used to seed
 *  starting HP so Fighters get more than Wizards even at level 1. */
const CLASS_BASE_HP: Record<ClassName, number> = {
  Fighter: 15, Paladin: 12, Ranger: 10, Thief: 8,
  Cleric: 8,  Druid: 8,    Alchemist: 6, Wizard: 6,
};

/**
 * Per-class `mp_per_level` from data/classes/*.json. Seed starting
 * MP at level 1 from this same value plus the casting-stat modifier
 * (mirrors the formula `awardXp` applies on every subsequent
 * level-up, so leveling N→N+1 always adds the same shape of MP gain
 * the character started with). Non-caster classes are 0 — they get
 * no `mp` field at all on the new member.
 */
const CLASS_MP_PER_LEVEL: Record<ClassName, number> = {
  Fighter: 0, Paladin: 5, Ranger: 3, Thief: 0,
  Cleric: 10, Druid: 8, Alchemist: 8, Wizard: 15,
};

/**
 * Casting stat for each class — drives the MP modifier at creation
 * and at level-up. Mirrors `mp_source.ability` in the JSON for
 * single-stat classes; Druid's dual-stat formula (average INT/WIS)
 * is special-cased in `startingMpFor` below since it's the only
 * class that uses the multi-ability shape today.
 */
const CLASS_MP_STAT: Record<ClassName, StatKey | null> = {
  Fighter: null, Paladin: "wisdom", Ranger: "wisdom", Thief: null,
  Cleric: "wisdom", Druid: null, Alchemist: "intelligence", Wizard: "intelligence",
};

/**
 * Compute starting MP for a freshly created character. Matches the
 * MP formula `awardXp` uses on level-up (`mp_per_level + casting_mod`)
 * so seed wizards in party.json (Gandolf: INT 18 → 15+4=19 MP) and
 * newly-created wizards land on the same numbers. Returns 0 for
 * non-casters; the caller leaves their `mp`/`maxMp` fields unset.
 *
 * Druid is the only class whose casting stat is derived from two
 * abilities — averaging INT and WIS, mirroring the JSON's
 * `mp_source.abilities + mode: "average"` shape.
 */
function startingMpFor(klass: ClassName, eff: Record<StatKey, number>): number {
  const perLevel = CLASS_MP_PER_LEVEL[klass];
  if (perLevel <= 0) return 0;
  let mod = 0;
  if (klass === "Druid") {
    const avg = Math.floor((eff.intelligence + eff.wisdom) / 2);
    mod = statMod(avg);
  } else {
    const stat = CLASS_MP_STAT[klass];
    if (stat) mod = statMod(eff[stat]);
  }
  return Math.max(0, perLevel + mod);
}

type StatKey = "strength" | "dexterity" | "constitution" | "intelligence" | "wisdom";
const STAT_KEYS: StatKey[] = ["strength", "dexterity", "constitution", "intelligence", "wisdom"];
const STAT_LABELS: Record<StatKey, string> = {
  strength: "STR", dexterity: "DEX", constitution: "CON",
  intelligence: "INT", wisdom: "WIS",
};

/** Floor for every attribute — also the starting value, so the player
 *  begins with every stat at 8 and chooses where the bonus goes. The
 *  + button can never push a stat past STAT_MAX, the - button can
 *  never drop it below STAT_MIN. */
const STAT_MIN = 8;
const STAT_MAX = 18;

/** Bonus points the player has to allocate above the floor.
 *
 *  Tuning history: the per-stat budget was originally 63 (12.5/stat
 *  average, rescaled from the Python game's 50 across 4 stats), which
 *  meant 23 bonus points above an 8-floor — enough to max the primary
 *  AND Constitution with 3 to spare. That made every build converge
 *  to "18/8/8/13/18" or similar, with no real trade-offs.
 *
 *  We pulled the budget down to 15 so the math forces a choice:
 *  maxing one stat costs 10 of those 15, leaving 5 to scatter (so
 *  one strong primary + a moderate secondary, OR a flat spread of
 *  ~+3 across all five). The "max two stats" pattern is no longer
 *  reachable, which is the whole point. */
const BONUS_POINTS = 15;
/** Total points across all five stats when the build is complete.
 *  Floor (8 per stat) + the bonus pool. */
const POINTS_TOTAL = STAT_MIN * STAT_KEYS.length + BONUS_POINTS;

/** Starting stats — every attribute begins at the floor so the
 *  player allocates the full BONUS_POINTS pool from a clean slate.
 *  Mirrors the "you have N points to spend" framing in classic RPG
 *  character creators rather than the "tweak these defaults" model. */
const STAT_DEFAULTS: Record<StatKey, number> = {
  strength: STAT_MIN, dexterity: STAT_MIN, constitution: STAT_MIN,
  intelligence: STAT_MIN, wisdom: STAT_MIN,
};

/** Available avatar sprites — every humanoid PNG the game ships,
 *  grouped by source folder so the picker stays browsable. Sprites in
 *  `monsters/` that aren't humanoid (Dragon, Wolf, Giant Rat) are
 *  excluded; everything else is fair game for a player-character
 *  portrait. Each entry is `{ key, src }` where `src` is the path the
 *  member's `sprite` field is set to (no `BASE_PATH` prefix — that's
 *  applied at render time by `assetUrl`). */
type AvatarKey = string;

interface AvatarGroup {
  label: string;
  avatars: ReadonlyArray<{ key: AvatarKey; src: string }>;
}

function listFromFolder(folder: string, names: ReadonlyArray<string>): AvatarGroup["avatars"] {
  return names.map((n) => ({ key: n, src: `/assets/${folder}/${n}.png` }));
}

const AVATAR_GROUPS: ReadonlyArray<AvatarGroup> = [
  {
    label: "Adventurers",
    avatars: listFromFolder("characters", [
      "fighter", "barbarian", "paladin", "ranger",
      "thief", "cleric", "druid", "wizard", "alchemist", "illusionist",
    ]),
  },
  {
    label: "Townsfolk",
    avatars: listFromFolder("npcs", [
      "elder", "innkeeper", "shopkeep", "townsfolk", "brigand",
      "villager_bard", "villager_beggar", "villager_child",
      "villager_citizen", "villager_guard", "villager_shepherd",
    ]),
  },
  {
    label: "Classic NPCs",
    // Ultima IV-style sprites — the smaller-palette, blockier
    // portraits that read as "older RPG" energy. Keeping them in
    // their own group lets a player who wants a specifically
    // retro-styled character browse them together rather than
    // hunting through a 30-row grid.
    avatars: listFromFolder("npcs", [
      "u4_avatar", "u4_villager_male", "u4_villager_female",
      "u4_citizen", "u4_beggar", "u4_child",
      "u4_guard", "u4_guard_npc", "u4_knight",
      "u4_healer", "u4_monk", "u4_shepherd",
      "u4_tinker", "u4_jester",
    ]),
  },
  {
    label: "VGA Adventurers",
    // VGA-era sprites — more detail, brighter palette, generally
    // class-coded (mage, fighter, paladin, etc.). Useful for a
    // player who wants their character to read clearly as a
    // particular archetype.
    avatars: listFromFolder("npcs", [
      "vga_avatar", "vga_fighter", "vga_paladin", "vga_ranger",
      "vga_rogue", "vga_mage", "vga_druid", "vga_jester",
      "vga_evil_mage",
    ]),
  },
  {
    label: "Other Folk",
    avatars: listFromFolder("monsters", [
      "barbarian_f2", "paladin_f1", "illusionist_f1",
      "dark_mage", "npcs_u4_healer", "npcs_vga_evil_mage",
      "orc", "goblin", "troll", "daemon_f1",
      "man_thing_f1", "man_thing_f2",
      "skeleton", "zombie", "super_zombie", "lich",
    ]),
  },
];

const ALL_AVATARS: ReadonlyArray<{ key: AvatarKey; src: string }> =
  AVATAR_GROUPS.flatMap((g) => g.avatars);

function spritePathFor(key: AvatarKey): string {
  const found = ALL_AVATARS.find((a) => a.key === key);
  return found ? found.src : `/assets/characters/${key}.png`;
}

/** Friendly display label for an avatar key — `villager_bard` →
 *  `Villager Bard`, `man_thing_f1` → `Man Thing F1`, etc. */
function avatarLabel(key: AvatarKey): string {
  return key.split("_").map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(" ");
}

/** Default avatar to highlight for a freshly-picked class. Not a
 *  hard requirement — players can pick any sprite. */
function defaultAvatarFor(klass: ClassName): AvatarKey {
  switch (klass) {
    case "Fighter":   return "fighter";
    case "Paladin":   return "paladin";
    case "Ranger":    return "ranger";
    case "Thief":     return "thief";
    case "Cleric":    return "cleric";
    // Druid now has its own dedicated sprite (copied over from the
    // Python game's character folder) instead of falling back to
    // the ranger placeholder.
    case "Druid":     return "druid";
    case "Wizard":    return "wizard";
    case "Alchemist": return "alchemist";
  }
}

function statMod(value: number): number {
  return Math.floor((value - 10) / 2);
}

function fmtMod(n: number): string {
  return n >= 0 ? `+${n}` : String(n);
}

// ── Race & class lore (mirrors docs/manuals/players_guide.md) ─────
//
// The character creator displays a description block when the player
// selects a race or class so they know what they're picking. This
// data is sourced from the Player's Guide (the design source of
// truth) and the per-class JSONs (the implementation source of
// truth). Where both agree we use the manual's flavor text; where
// the manual mentions abilities not yet in the JSON (Backstab,
// Shadow Step, Holy Smite) we still show them so the player knows
// what to expect — they're tagged with the level they unlock at.
//
// The lore tables stay in this file (rather than being fetched from
// JSON) because the rest of the creator already mirrors data with
// hardcoded constants — staying consistent with that pattern.

interface AbilityLore {
  name: string;
  /** Level the ability unlocks; omitted means "from level 1". */
  minLevel?: number;
  description: string;
}

interface RaceLore {
  /** Italic flavor tagline from the Player's Guide. */
  tagline: string;
  /** Innate racial ability. Every shipped race has exactly one. */
  ability: AbilityLore;
}

interface ClassLore {
  /** Italic flavor tagline from the Player's Guide. */
  tagline: string;
  /** Multi-paragraph description condensed to one or two sentences. */
  description: string;
  /** Class abilities, in unlock order. */
  abilities: AbilityLore[];
}

const RACE_LORE: Record<RaceName, RaceLore> = {
  Human: {
    tagline: "Versatile and adaptable; excels in no single area but has no weaknesses.",
    ability: {
      name: "Fast Learner",
      description:
        "Humans require only 750 XP per level instead of the standard 1000, leveling up 25% faster than other races.",
    },
  },
  Dwarf: {
    tagline: "Stout and hardy, natural miners and warriors with keen underground senses.",
    ability: {
      name: "Infravision",
      description:
        "Dwarves can see in total darkness — dungeon corridors that would be pitch-black to other races stay dimly visible.",
    },
  },
  Halfling: {
    tagline: "Small and nimble, surprisingly resilient and hard to hit.",
    ability: {
      name: "Pickpocket",
      description:
        "Halflings can attempt to steal items from town NPCs. Once per NPC, with a chance of failure.",
    },
  },
  Elf: {
    tagline: "Graceful and keen-minded, with a natural affinity for magic and sharp senses.",
    ability: {
      name: "Galadriel's Light",
      description:
        "Elves can conjure a soft magical illumination, lighting up dark areas without consuming a torch.",
    },
  },
  Gnome: {
    tagline: "Clever and curious, combining tinkering skill with innate magical talent.",
    ability: {
      name: "Tinker",
      description:
        "Once per in-game day, fashion any single item normally found in a general store.",
    },
  },
};

const CLASS_LORE: Record<ClassName, ClassLore> = {
  Fighter: {
    tagline: "The quintessential warrior — tough, versatile, and deadly in melee.",
    description:
      "The backbone of any party. Highest HP per level, a generous 4-tile combat range, every weapon and every armor type. Casts no spells but more than makes up for it with raw staying power.",
    abilities: [],
  },
  Wizard: {
    tagline: "Master of arcane forces — fragile but devastatingly powerful at range.",
    description:
      "The most diverse and powerful spell list in the game, from Fireball to Animate Dead. Lowest HP per level, no armor, daggers only — keep them behind the front line.",
    abilities: [],
  },
  Cleric: {
    tagline: "Holy warrior and healer — the party's lifeline in long fights.",
    description:
      "The primary healers. Minor Heal, Major Heal, Mass Heal, and Restore keep the party standing; Cure Poison clears nasty status effects. Can also fight respectably with maces and clubs.",
    abilities: [
      {
        name: "Turn Undead",
        minLevel: 2,
        description:
          "Channel holy energy at every undead on the field — failed Wisdom save = destroyed, success = 50% max-HP damage.",
      },
    ],
  },
  Thief: {
    tagline: "Quick, cunning, and deadly from the shadows — unmatched utility.",
    description:
      "Longest combat range of any class (6 tiles). Real value outside combat is Pick Locks and Detect Traps, opening areas and loot other classes can't reach.",
    abilities: [
      {
        name: "Pick Locks",
        description:
          "Open locked doors and chests — d20 + DEX vs DC 12, one lockpick consumed per attempt.",
      },
      {
        name: "Detect Traps",
        description:
          "Reveal hidden traps before the party steps on them.",
      },
      {
        name: "Backstab",
        minLevel: 3,
        description:
          "Critical hits with daggers on a successful DEX save.",
      },
      {
        name: "Shadow Step",
        minLevel: 7,
        description: "Move after attacking — true hit-and-run play.",
      },
    ],
  },
  Paladin: {
    tagline: "Holy knight — a tough fighter with limited healing and anti-undead power.",
    description:
      "Combines Fighter durability with limited Priest magic. Heaviest armor, any weapon, Minor Heal between fights. The premier anti-undead warrior outside the Cleric.",
    abilities: [
      {
        name: "Holy Smite",
        description: "Double damage against undead enemies.",
      },
      {
        name: "Turn Undead",
        minLevel: 5,
        description:
          "Channel holy energy at every undead on the field, just as a Cleric does.",
      },
    ],
  },
  Ranger: {
    tagline: "Versatile woodsman — bow master and able scout.",
    description:
      "Durable frontliner with bow mastery and limited healing. 6-tile combat range matches a Thief; proficient with every bow in the game. A self-sufficient pick.",
    abilities: [
      {
        name: "Pick Locks",
        minLevel: 3,
        description:
          "From level 3, pick locked doors and chests exactly as a Thief can.",
      },
      {
        name: "Detect Traps",
        minLevel: 3,
        description:
          "From level 3, woodcraft reveals hidden traps before the party steps on them.",
      },
    ],
  },
  Druid: {
    tagline: "Nature's emissary — dual-caster and herbalist of the wilds.",
    description:
      "Game's only hybrid caster, with both Priest and Sorcerer spells. MP pool is roughly half a Wizard's at equivalent stats. Cloth-only — keep them protected.",
    abilities: [
      {
        name: "Dual Casting",
        description: "Access to both Priest and Sorcerer spell lists.",
      },
      {
        name: "Herbalism",
        description:
          "Druids' nature lore spots reagents in the wild — examining a tile rolls d20 + INT vs DC 13, and each overworld step rolls again at DC 20 for a passive find.",
      },
    ],
  },
  Alchemist: {
    tagline: "Master of potions and elixirs — support specialist and crafter.",
    description:
      "Modest combat ability but unique value through potion crafting. 4-tile range, Sling for ranged, access to Sorcerer spells. Half-caster MP pool — lean on potions and thrown oils as much as on spells.",
    abilities: [
      {
        name: "Brew Potions",
        description:
          "Craft potions from reagents found in shops and dungeons.",
      },
      {
        name: "Herbalism",
        description:
          "Doubles the chance of finding reagents when examining the wilderness.",
      },
    ],
  },
};

// ── Page ──────────────────────────────────────────────────────────

type Step = 1 | 2 | 3 | 4 | 5 | 6;

export default function NewCharacterPage() {
  const router = useRouter();
  const [party, setParty] = useState<Party | null>(null);
  const [step, setStep] = useState<Step>(1);
  const [name, setName] = useState("");
  const [race, setRace] = useState<RaceName>("Human");
  const [gender, setGender] = useState<typeof GENDERS[number]>("Male");
  const [klass, setKlass] = useState<ClassName>("Fighter");
  const [avatar, setAvatar] = useState<AvatarKey>(defaultAvatarFor("Fighter"));
  const [avatarTouched, setAvatarTouched] = useState(false);
  const [stats, setStats] = useState<Record<StatKey, number>>({ ...STAT_DEFAULTS });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    _clearPartyCache();
    loadParty(dataPath("party.json")).then((p) => {
      if (alive) setParty(p);
    });
    return () => { alive = false; };
  }, []);

  // When race changes and the chosen class isn't valid for the new
  // race, snap to the first allowed class so the form stays coherent.
  useEffect(() => {
    if (!CLASS_RACES[klass].has(race)) {
      const firstValid = CLASSES.find((c) => CLASS_RACES[c].has(race));
      if (firstValid) setKlass(firstValid);
    }
  }, [race, klass]);

  // When the class changes, suggest a matching avatar — unless the
  // player has explicitly picked one, in which case respect the
  // override.
  useEffect(() => {
    if (!avatarTouched) setAvatar(defaultAvatarFor(klass));
  }, [klass, avatarTouched]);

  const pointsSpent = useMemo(
    () => STAT_KEYS.reduce((sum, k) => sum + stats[k], 0),
    [stats]
  );
  const pointsLeft = POINTS_TOTAL - pointsSpent;

  function adjust(stat: StatKey, delta: number): void {
    const next = stats[stat] + delta;
    if (next < STAT_MIN || next > STAT_MAX) return;
    if (delta > 0 && pointsLeft < delta) return;
    setStats({ ...stats, [stat]: next });
    setError(null);
  }

  function next(): void {
    if (step === 1 && name.trim().length === 0) {
      setError("Enter a name.");
      return;
    }
    if (step === 5 && pointsLeft !== 0) {
      const spent = BONUS_POINTS - pointsLeft;
      setError(`Distribute all ${BONUS_POINTS} bonus points (${spent} of ${BONUS_POINTS} so far).`);
      return;
    }
    setError(null);
    setStep((s) => (s < 6 ? ((s + 1) as Step) : s));
  }

  function back(): void {
    setError(null);
    setStep((s) => (s > 1 ? ((s - 1) as Step) : s));
  }

  function finalize(): void {
    if (!party) return;
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Enter a name.");
      setStep(1);
      return;
    }
    if (pointsLeft !== 0) {
      setError(`Distribute all ${BONUS_POINTS} bonus points first.`);
      setStep(5);
      return;
    }
    const mods = RACE_MODS[race];
    // Effective stats include the racial modifier so HP / AC math
    // already reflects the bonus when combat starts.
    const eff = {
      strength: stats.strength + mods.strength,
      dexterity: stats.dexterity + mods.dexterity,
      constitution: stats.constitution + mods.constitution,
      intelligence: stats.intelligence + mods.intelligence,
      wisdom: stats.wisdom + mods.wisdom,
    };
    const hp = Math.max(1, CLASS_BASE_HP[klass] + statMod(eff.constitution));
    const mp = startingMpFor(klass, eff);
    const newMember: PartyMember = {
      name: trimmedName,
      class: klass,
      race,
      gender,
      hp,
      maxHp: hp,
      // Casters carry mp/maxMp fields; non-casters omit them
      // entirely so `member.maxMp == null` reads as "this class
      // doesn't cast" downstream (the spell pickers and HUD bars
      // already check that exact null path).
      ...(mp > 0 ? { mp, maxMp: mp } : {}),
      strength: eff.strength,
      dexterity: eff.dexterity,
      constitution: eff.constitution,
      intelligence: eff.intelligence,
      wisdom: eff.wisdom,
      level: 1,
      exp: 0,
      equipped: { rightHand: null, leftHand: null, body: null, head: null },
      equippedDurability: { right_hand: null, left_hand: null, body: null, head: null },
      inventory: [],
      sprite: spriteForMember(spritePathFor(avatar), klass),
    };
    party.roster.push(newMember);
    saveStoredRoster(party);
    router.push("/party");
  }

  if (!party) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6">
        <p className="text-parchment/60">Loading roster&hellip;</p>
      </main>
    );
  }

  const allowedClasses = CLASSES.filter((c) => CLASS_RACES[c].has(race));
  const mods = RACE_MODS[race];

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-6 py-8">
      <div className="mb-4 flex items-center justify-between">
        <Link href="/party" className="text-sm text-parchment/60 hover:text-parchment">
          &larr; Cancel
        </Link>
        <h1 className="font-display text-2xl text-parchment">
          New Character — Step {step} of 6
        </h1>
        <span className="w-16" />
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-parchment">
          {error}
        </div>
      )}

      {/* ── Step 1: Name ─────────────────────────────── */}
      {step === 1 && (
        <section className="rounded border border-parchment/20 bg-parchment/5 p-6">
          <label className="block">
            <span className="block text-sm text-parchment/70">Name</span>
            <input
              type="text"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={20}
              className="mt-2 w-full rounded border border-parchment/30 bg-bg-canvas px-3 py-2 text-parchment focus:border-ember focus:outline-none"
              placeholder="Aldric"
            />
          </label>
        </section>
      )}

      {/* ── Step 2: Race + Gender ────────────────────── */}
      {step === 2 && (
        <section className="space-y-6">
          <div>
            <h2 className="text-sm uppercase tracking-wider text-parchment/60">Race</h2>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-5">
              {RACES.map((r) => (
                <Pick key={r} active={r === race} onClick={() => setRace(r)}>
                  {r}
                </Pick>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-5 gap-1 text-center text-[11px] text-parchment/60">
              {STAT_KEYS.map((k) => {
                const m = mods[k];
                return (
                  <div key={k} className="rounded bg-parchment/5 py-1">
                    <div className="font-semibold text-parchment">
                      {m === 0 ? "—" : fmtMod(m)}
                    </div>
                    <div className="text-[9px] uppercase tracking-wider text-parchment/40">
                      {STAT_LABELS[k]}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* Race lore — flavor + innate ability. Updates as the
                player flips between race options so the description
                always matches the highlighted choice. */}
            <RaceLoreCard race={race} />
          </div>
          <div>
            <h2 className="text-sm uppercase tracking-wider text-parchment/60">Gender</h2>
            <div className="mt-2 flex gap-2">
              {GENDERS.map((g) => (
                <Pick key={g} active={g === gender} onClick={() => setGender(g)}>
                  {g}
                </Pick>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── Step 3: Class ────────────────────────────── */}
      {step === 3 && (
        <section>
          <h2 className="text-sm uppercase tracking-wider text-parchment/60">
            Class — available to {race}s
          </h2>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {allowedClasses.map((c) => (
              <Pick key={c} active={c === klass} onClick={() => setKlass(c)}>
                {c}
              </Pick>
            ))}
          </div>
          <p className="mt-3 text-xs text-parchment/50">
            Wizards require an arcane heritage (Human, Elf, or Gnome).
          </p>
          {/* Class lore — flavor + abilities list with level gates.
              Updates as the player flips between class options. */}
          <ClassLoreCard klass={klass} />
        </section>
      )}

      {/* ── Step 4: Avatar ───────────────────────────── */}
      {step === 4 && (
        <section>
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm uppercase tracking-wider text-parchment/60">
              Avatar
            </h2>
            <div className="text-xs text-parchment/50">
              Picked: <span className="text-parchment">{avatarLabel(avatar)}</span>
            </div>
          </div>
          <div className="mt-3 space-y-4">
            {AVATAR_GROUPS.map((group) => (
              <div key={group.label}>
                <div className="text-[11px] uppercase tracking-wider text-parchment/50">
                  {group.label}
                </div>
                <div className="mt-2 grid grid-cols-3 gap-3 sm:grid-cols-6">
                  {group.avatars.map(({ key, src }) => {
                    const selected = key === avatar;
                    return (
                      <button
                        key={key}
                        onClick={() => { setAvatar(key); setAvatarTouched(true); }}
                        title={avatarLabel(key)}
                        className={`flex flex-col items-center rounded border bg-parchment/5 p-2 transition ${
                          selected
                            ? "border-ember bg-ember/10"
                            : "border-parchment/20 hover:border-parchment/40"
                        }`}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element --
                            32×32 pixel art — `next/image` would either
                            blur it or add LCP overhead for no gain. */}
                        <img
                          src={assetUrl(src)}
                          alt={avatarLabel(key)}
                          width={48}
                          height={48}
                          className="pixelated"
                          style={{ imageRendering: "pixelated" }}
                        />
                        <div className="mt-1 line-clamp-1 text-[10px] uppercase tracking-wider text-parchment/70">
                          {avatarLabel(key)}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-parchment/50">
            Cosmetic only — your class drives your stats and abilities,
            not your sprite. Pick whatever fits the character you&apos;re
            making, even from the &ldquo;Other Folk&rdquo; row.
          </p>
        </section>
      )}

      {/* ── Step 5: Stats ────────────────────────────── */}
      {step === 5 && (
        <section>
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm uppercase tracking-wider text-parchment/60">
              Stats — distribute {BONUS_POINTS} bonus points
            </h2>
            <div className="text-sm text-parchment/70">
              Remaining: <span className={pointsLeft === 0 ? "text-ember" : "text-parchment"}>
                {pointsLeft}
              </span>
            </div>
          </div>
          <p className="mt-1 text-xs text-parchment/50">
            Each attribute starts at {STAT_MIN}. {BONUS_POINTS} points to
            spend, max {STAT_MAX} per stat — enough to max one and lift
            another, or spread roughly +3 across all five. Pick what
            matters most; you can&apos;t have everything.
          </p>
          <div className="mt-3 space-y-2">
            {STAT_KEYS.map((k) => {
              const base = stats[k];
              const racial = mods[k];
              const eff = base + racial;
              return (
                <div key={k} className="flex items-center gap-3 rounded border border-parchment/20 bg-parchment/5 px-3 py-2">
                  <div className="w-10 font-semibold text-parchment">
                    {STAT_LABELS[k]}
                  </div>
                  <button
                    onClick={() => adjust(k, -1)}
                    disabled={base <= STAT_MIN}
                    className="rounded border border-parchment/30 px-2 py-0.5 text-parchment hover:bg-parchment/10 disabled:opacity-30"
                  >
                    −
                  </button>
                  <div className="w-8 text-center font-mono text-parchment">{base}</div>
                  <button
                    onClick={() => adjust(k, +1)}
                    disabled={base >= STAT_MAX || pointsLeft <= 0}
                    className="rounded border border-parchment/30 px-2 py-0.5 text-parchment hover:bg-parchment/10 disabled:opacity-30"
                  >
                    +
                  </button>
                  <div className="ml-2 text-xs text-parchment/60">
                    {racial !== 0 && (
                      <>
                        {fmtMod(racial)} {race} → <strong className="text-parchment">{eff}</strong>
                      </>
                    )}
                    {racial === 0 && <>effective {eff}</>}
                    <span className="ml-2 text-parchment/40">
                      mod {fmtMod(statMod(eff))}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Step 6: Confirm ──────────────────────────── */}
      {step === 6 && (
        <section className="rounded border border-parchment/20 bg-parchment/5 p-6">
          <div className="flex items-center gap-4">
            {/* eslint-disable-next-line @next/next/no-img-element -- pixel art, see step 4. */}
            <img
              src={assetUrl(spritePathFor(avatar))}
              alt={avatar}
              width={64}
              height={64}
              style={{ imageRendering: "pixelated" }}
              className="rounded border border-parchment/20"
            />
            <div>
              <div className="text-2xl font-display text-parchment">{name || "Unnamed"}</div>
              <div className="mt-1 text-sm text-parchment/70">
                Level 1 {race} {klass} · {gender}
              </div>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-5 gap-2 text-center text-xs text-parchment/70">
            {STAT_KEYS.map((k) => {
              const eff = stats[k] + mods[k];
              return (
                <div key={k} className="rounded bg-parchment/5 py-2">
                  <div className="text-lg font-semibold text-parchment">{eff}</div>
                  <div className="text-[10px] uppercase tracking-wider text-parchment/40">
                    {STAT_LABELS[k]}
                  </div>
                  <div className="text-[10px] text-parchment/50">
                    mod {fmtMod(statMod(eff))}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 text-sm text-parchment/70">
            Starting HP:{" "}
            <strong className="text-parchment">
              {Math.max(1, CLASS_BASE_HP[klass] + statMod(stats.constitution + mods.constitution))}
            </strong>
            {" "}({CLASS_BASE_HP[klass]} base + CON mod)
          </div>
          {CLASS_MP_PER_LEVEL[klass] > 0 && (
            <div className="mt-1 text-sm text-parchment/70">
              Starting MP:{" "}
              <strong className="text-parchment">
                {startingMpFor(klass, {
                  strength: stats.strength + mods.strength,
                  dexterity: stats.dexterity + mods.dexterity,
                  constitution: stats.constitution + mods.constitution,
                  intelligence: stats.intelligence + mods.intelligence,
                  wisdom: stats.wisdom + mods.wisdom,
                })}
              </strong>
              {" "}({CLASS_MP_PER_LEVEL[klass]} base + casting mod)
            </div>
          )}
        </section>
      )}

      {/* ── Nav ─────────────────────────────────────── */}
      <div className="mt-6 flex justify-between gap-2">
        <button
          onClick={back}
          disabled={step === 1}
          className="rounded border border-parchment/30 px-4 py-2 text-sm text-parchment/80 hover:bg-parchment/10 disabled:opacity-30"
        >
          &larr; Back
        </button>
        {step < 6 ? (
          <button
            onClick={next}
            className="rounded border border-ember bg-ember/40 px-4 py-2 text-sm text-parchment hover:bg-ember/60"
          >
            Next &rarr;
          </button>
        ) : (
          <button
            onClick={finalize}
            className="rounded border border-ember bg-ember/40 px-4 py-2 text-sm text-parchment hover:bg-ember/60"
          >
            Create Character
          </button>
        )}
      </div>
    </main>
  );
}

function Pick({
  active, onClick, children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded border px-3 py-2 text-sm transition ${
        active
          ? "border-ember bg-ember/20 text-parchment"
          : "border-parchment/30 text-parchment/80 hover:bg-parchment/10"
      }`}
    >
      {children}
    </button>
  );
}

/** Description card shown below the race grid in step 2. Pulls from
 *  RACE_LORE so the flavor + innate ability stay in sync with the
 *  Player's Guide. Updates whenever the selected race changes. */
function RaceLoreCard({ race }: { race: RaceName }) {
  const lore = RACE_LORE[race];
  return (
    <div className="mt-4 rounded border border-parchment/20 bg-parchment/5 p-4">
      <div className="text-base font-display text-parchment">{race}</div>
      <p className="mt-1 text-sm italic text-parchment/70">{lore.tagline}</p>
      <div className="mt-3">
        <div className="text-[11px] uppercase tracking-wider text-parchment/50">
          Innate Ability
        </div>
        <div className="mt-1 text-sm text-parchment">
          <strong className="text-ember">{lore.ability.name}</strong>
          <span className="text-parchment/80"> — {lore.ability.description}</span>
        </div>
      </div>
    </div>
  );
}

/** Description card shown below the class grid in step 3. Lists
 *  flavor text + every class ability with its unlock level. Mirrors
 *  the Player's Guide so players see what they're committing to,
 *  including high-level abilities like Backstab + Shadow Step that
 *  unlock long after character creation. */
function ClassLoreCard({ klass }: { klass: ClassName }) {
  const lore = CLASS_LORE[klass];
  return (
    <div className="mt-4 rounded border border-parchment/20 bg-parchment/5 p-4">
      <div className="text-base font-display text-parchment">{klass}</div>
      <p className="mt-1 text-sm italic text-parchment/70">{lore.tagline}</p>
      <p className="mt-2 text-sm text-parchment/80">{lore.description}</p>
      {lore.abilities.length > 0 && (
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wider text-parchment/50">
            Class Abilities
          </div>
          <ul className="mt-1 space-y-1.5 text-sm">
            {lore.abilities.map((a) => (
              <li key={a.name} className="text-parchment/80">
                <strong className="text-ember">{a.name}</strong>
                {a.minLevel != null && a.minLevel > 1 && (
                  <span className="ml-1 text-parchment/50">
                    (Lvl {a.minLevel}+)
                  </span>
                )}
                <span> — {a.description}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
