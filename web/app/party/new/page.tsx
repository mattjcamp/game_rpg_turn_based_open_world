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
 *   5. Stats — 63 points across STR/DEX/CON/INT/WIS, min 5 max 18 base
 *      (racial modifiers add on top at runtime). The Python game used
 *      50 across 4 stats (avg 12.5 per stat); rescaled to keep the
 *      same per-stat budget after adding Constitution.
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

type StatKey = "strength" | "dexterity" | "constitution" | "intelligence" | "wisdom";
const STAT_KEYS: StatKey[] = ["strength", "dexterity", "constitution", "intelligence", "wisdom"];
const STAT_LABELS: Record<StatKey, string> = {
  strength: "STR", dexterity: "DEX", constitution: "CON",
  intelligence: "INT", wisdom: "WIS",
};

/** Per-stat budget. The Python game shipped 50 points across 4 stats
 *  (STR/DEX/INT/WIS) — average 12.5 per stat. Adding Constitution
 *  rescales to 63 points across 5 stats so the per-stat average is
 *  preserved (5 × 12.5 ≈ 63). */
const POINTS_TOTAL = 63;
const STAT_MIN = 5;
const STAT_MAX = 18;

/** Default starting stats — sums to POINTS_TOTAL. Spread is mildly
 *  caster-friendly (CON/INT/WIS slightly higher than STR/DEX) so a
 *  freshly-created Wizard isn't crippled and a Fighter can shift
 *  points into STR without scrabbling. */
const STAT_DEFAULTS: Record<StatKey, number> = {
  strength: 12, dexterity: 12, constitution: 13, intelligence: 13, wisdom: 13,
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
      "thief", "cleric", "wizard", "alchemist", "illusionist",
    ]),
  },
  {
    label: "Townsfolk",
    avatars: listFromFolder("npcs", [
      "elder", "innkeeper", "shopkeep",
      "villager_bard", "villager_beggar", "villager_child",
      "villager_citizen", "villager_guard", "villager_shepherd",
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
    case "Druid":     return "ranger";
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
      setError(`Spend exactly ${POINTS_TOTAL} points (${pointsSpent} so far).`);
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
      setError(`Spend exactly ${POINTS_TOTAL} points first.`);
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
    const newMember: PartyMember = {
      name: trimmedName,
      class: klass,
      race,
      gender,
      hp,
      maxHp: hp,
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
              Stats — distribute {POINTS_TOTAL} points
            </h2>
            <div className="text-sm text-parchment/70">
              Remaining: <span className={pointsLeft === 0 ? "text-ember" : "text-parchment"}>
                {pointsLeft}
              </span>
            </div>
          </div>
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
