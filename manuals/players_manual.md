# Realm of Shadow — Player's Manual

*A tactical fantasy RPG inspired by the classics*

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Races](#races)
3. [Character Classes](#character-classes)
4. [Attributes & Modifiers](#attributes--modifiers)
5. [Armor Class & Defense](#armor-class--defense)
6. [Combat](#combat)
7. [Spells & Magic](#spells--magic)
8. [Weapons](#weapons)
9. [Armor](#armor)
10. [Items & Consumables](#items--consumables)
11. [Experience & Leveling](#experience--leveling)
12. [Monsters & Bestiary](#monsters--bestiary)
13. [Controls & Interface](#controls--interface)

---

## Getting Started

Realm of Shadow is a turn-based tactical RPG where you lead a party of up to four adventurers through a dangerous world. Explore the overworld, delve into dungeons, trade in towns, and engage in grid-based tactical combat against a host of enemies.

Your party shares a pool of gold and a communal inventory, but each character has their own equipped gear, hit points, magic points, and experience. Choose your party wisely — a balanced group with frontline fighters, healers, and spellcasters will fare better than one that leans too heavily on a single role.

---

## Races

Each race provides permanent stat bonuses and a unique innate ability. Choose a race that complements the class you have in mind.

### ![Human](images/race_human.png) Human

*Versatile and adaptable, excels in no single area but has no weaknesses.*

| STR | DEX | INT | WIS |
|-----|-----|-----|-----|
| +0  | +0  | +0  | +0  |

**Innate Ability — Fast Learner:** Humans require only **350 XP per level** instead of the standard 500, allowing them to level up roughly 30% faster than other races. This compensates for their lack of stat bonuses and makes them an excellent choice for any class.

---

### ![Dwarf](images/race_dwarf.png) Dwarf

*Stout and hardy, natural miners and warriors with keen underground senses.*

| STR | DEX | INT | WIS |
|-----|-----|-----|-----|
| +2  | -1  | +0  | +1  |

**Innate Ability — Infravision:** Dwarves can see in total darkness. Dungeon corridors that would be pitch-black to other races are dimly visible to a Dwarf, eliminating the need for a torch or Light spell.

---

### ![Halfling](images/race_halfling.png) Halfling

*Small and nimble, surprisingly resilient and hard to hit.*

| STR | DEX | INT | WIS |
|-----|-----|-----|-----|
| -2  | +2  | +0  | +1  |

**Innate Ability — Pickpocket:** Halflings can attempt to steal items from town NPCs. This ability has a daily cooldown and a chance of failure — use it wisely.

---

### ![Elf](images/race_elf.png) Elf

*Graceful and keen-minded, with a natural affinity for magic and sharp senses.*

| STR | DEX | INT | WIS |
|-----|-----|-----|-----|
| -1  | +1  | +2  | +0  |

**Innate Ability — Galadriel's Light:** Elves can conjure a soft magical illumination, lighting up dark areas without consuming a torch. This ability has a daily cooldown.

---

### ![Gnome](images/race_gnome.png) Gnome

*Clever and curious, combining tinkering skill with innate magical talent.*

| STR | DEX | INT | WIS |
|-----|-----|-----|-----|
| -1  | +0  | +2  | +1  |

**Innate Ability — Tinker:** Gnomes can repair broken equipment and craft simple items from reagents. This ability has a daily cooldown.

---

## Character Classes

Each class determines your character's hit points per level, magic points per level, allowed weapons and armor, combat range, and special abilities.

### ![Fighter](images/class_fighter.png) Fighter

*The quintessential warrior — tough, versatile, and deadly in melee.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 15       | 0        | 2     | None       |

**Allowed Weapons:** All weapons
**Allowed Armor:** All armor (Cloth, Leather, Chain, Plate)
**Allowed Races:** All

**Class Abilities:**

- **Shield Wall** — Reduces incoming physical damage when wielding a shield.
- **Cleave** — Melee attacks can strike adjacent enemies in a sweeping arc.

Fighters are the backbone of any party. With the highest HP per level and access to every weapon and armor type, they belong on the front line where the fighting is thickest. They have no magic but more than compensate with raw staying power and damage output.

---

### ![Wizard](images/class_wizard.png) Wizard

*Master of arcane forces — fragile but devastatingly powerful at range.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 4        | 15       | 2     | Sorcerer   |

**Allowed Weapons:** Fists, Dagger
**Allowed Armor:** Cloth only
**Allowed Races:** Human, Elf, Gnome

**MP Source:** 100% of Intelligence

**Class Abilities:**

- **Arcane Focus** — Spell damage is increased by the Intelligence bonus.
- **Identify** — Can identify unknown magical items.

Wizards command the most diverse and powerful spell list in the game. From Fireball to Lightning Bolt, Charm Person to Animate Dead, they reshape the battlefield. Their weakness is severe — the lowest HP per level, no armor, and only daggers for weapons. Keep them behind your front line and let them rain destruction from safety.

---

### ![Cleric](images/class_cleric.png) Cleric

*Holy warrior and healer — the party's lifeline in long fights.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 6        | 10       | 2     | Priest     |

**Allowed Weapons:** Fists, Club, Mace, Sling
**Allowed Armor:** Cloth, Leather, Chain
**Allowed Races:** All

**MP Source:** 100% of Wisdom

**Class Abilities:**

- **Turn Undead** — Channels holy energy that strips 75% of HP from all undead enemies on the battlefield. Devastating against skeletons and zombies.

Clerics are the primary healers of the party. Minor Heal, Major Heal, and Mass Heal keep everyone standing, while Cure Poison removes dangerous status effects. They can also fight respectably in melee with maces and clubs, wear chain armor, and devastate undead with Turn Undead. Every party should have one.

---

### ![Thief](images/class_thief.png) Thief

*Quick, cunning, and deadly from the shadows — unmatched utility.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 5        | 0        | 5     | None       |

**Allowed Weapons:** Fists, Dagger, Club, Sling, Short Bow
**Allowed Armor:** Cloth, Leather
**Allowed Races:** All

**Class Abilities:**

- **Pick Locks** — Can open locked doors and chests without a key.
- **Detect Traps** — Can detect and disarm hidden traps in dungeons.
- **Backstab** — Deals double damage when attacking from behind an enemy.

The Thief has the longest combat range of any class (5 tiles), making them excellent skirmishers. With a Short Bow they can pelt enemies from across the arena. Their real value outside combat is Pick Locks and Detect Traps, which open up areas and loot that other classes can't reach. Pair with Halfling for the Pickpocket bonus.

---

### ![Paladin](images/class_paladin.png) Paladin

*Holy knight — a tough fighter with limited healing and anti-undead power.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 10       | 5        | 2     | Priest     |

**Allowed Weapons:** All weapons
**Allowed Armor:** Cloth, Leather, Chain, Plate
**Allowed Races:** All

**MP Source:** 50% of Wisdom

**Class Abilities:**

- **Lay on Hands** — Can heal allies with a touch outside of combat.
- **Holy Aura** — Nearby undead take damage each turn.
- **Shield Wall** — Reduces incoming physical damage when wielding a shield.

Paladins combine Fighter durability with limited Priest magic. They can wear the heaviest armor, use any weapon, and still cast healing spells (though with a smaller MP pool than a Cleric). Their Holy Aura makes them particularly effective in undead-heavy dungeons.

---

### ![Ranger](images/class_ranger.png) Ranger

*Versatile woodsman — skilled with bows, swords, and light healing.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 15       | 0        | 2     | Priest     |

**Allowed Weapons:** Fists, Dagger, Club, Sling, Short Bow, Long Bow, Sword
**Allowed Armor:** Cloth, Leather, Chain
**Allowed Races:** All

**MP Source:** 50% of Wisdom

**Class Abilities:**

- **Track** — Can detect nearby enemies on the overworld.
- **Forage** — Can find herbs and reagents while exploring.
- **Dual Wield** — Can equip a weapon in each hand for extra attacks.

Rangers match Fighters for HP per level and add bow proficiency plus limited healing magic. With Long Bow access they can deal serious ranged damage, and Forage keeps the party supplied with herbs and reagents. A strong choice for parties that want a self-sufficient frontliner.

---

### ![Druid](images/class_druid.png) Druid

*Nature's emissary — the only dual-caster, drawing from both Priest and Sorcerer spell lists.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 5        | 12       | 2     | Both       |

**Allowed Weapons:** Fists, Dagger, Club, Mace
**Allowed Armor:** Cloth only
**Allowed Races:** All

**MP Source:** 50% of whichever is higher (INT or WIS)
**MP Regeneration:** 2× normal rate

**Class Abilities:**

- **Nature's Blessing** — Slowly regenerates HP while outdoors.
- **Herbalism** — Can identify and use wild herbs for healing.

The Druid is the game's only hybrid caster, able to cast both Priest spells (healing, Cure Poison, Bless) and Sorcerer spells (Fireball, Shield, Lightning Bolt). Their MP regenerates twice as fast as other classes. The trade-off is low HP and cloth-only armor — like Wizards, they need protection.

---

### ![Alchemist](images/class_alchemist.png) Alchemist

*Master of potions and elixirs — support specialist and crafter.*

| HP/Level | MP/Level | Range | Spell Type |
|----------|----------|-------|------------|
| 4        | 8        | 3     | Sorcerer   |

**Allowed Weapons:** Fists, Dagger
**Allowed Armor:** Cloth only
**Allowed Races:** All

**MP Source:** 50% of Intelligence

**Class Abilities:**

- **Brew Potions** — Can craft potions from gathered reagents, turning Moonpetal, Glowcap Mushrooms, and other ingredients into useful elixirs.

Alchemists have modest combat ability but provide unique value through potion crafting. Their 3-tile range gives them slightly better positioning than Wizards, and access to Sorcerer spells means they can still contribute offensive magic.

---

## Attributes & Modifiers

Every character has four core attributes, typically ranging from 8 to 20. These are modified by racial bonuses during character creation.

### The Four Attributes

| Attribute | Abbreviation | Affects |
|-----------|-------------|---------|
| **Strength** | STR | Melee damage bonus, carrying capacity |
| **Dexterity** | DEX | Armor Class, initiative order, ranged accuracy |
| **Intelligence** | INT | Sorcerer spell power, MP pool for Wizards/Alchemists |
| **Wisdom** | WIS | Priest spell power, MP pool for Clerics/Paladins/Rangers |

### Calculating Modifiers

Every attribute generates a **modifier** used in combat rolls:

**Modifier = (Attribute − 10) ÷ 2** (rounded down)

| Attribute Score | Modifier |
|----------------|----------|
| 8–9            | −1       |
| 10–11          | +0       |
| 12–13          | +1       |
| 14–15          | +2       |
| 16–17          | +3       |
| 18–19          | +4       |
| 20             | +5       |

**Examples:**

- A Fighter with STR 16 gets a +3 modifier on melee damage rolls.
- A Wizard with INT 18 gets a +4 modifier on spell damage and save DCs.
- A character with DEX 14 gets +2 added to their Armor Class.

---

## Armor Class & Defense

Armor Class (AC) represents how hard a character is to hit. Higher AC means better defense.

### AC Formula

**AC = 10 + DEX modifier + Armor bonus**

The armor bonus comes from the **evasion rating** of your equipped armor:

**Armor bonus = (Evasion − 50) ÷ 5**

| Armor | Evasion | Armor Bonus |
|-------|---------|-------------|
| Cloth | 50 | +0 |
| Leather | 56 | +1.2 |
| Chain | 58 | +1.6 |
| Plate | 60 | +2 |
| +2 Chain | 62 | +2.4 |
| +2 Plate | 64 | +2.8 |
| Exotic | 67 | +3.4 |

### AC Modifiers

Your AC can be further modified by:

- **Defending** (skipping your turn to brace): +2 AC until your next turn
- **Shield spell**: +2 AC for 3 turns
- **Elixir of Warding**: +2 AC for the duration of combat
- **Curse debuff**: −2 AC (applied by enemy spellcasters)

### Example

A Ranger wearing Chain armor (evasion 58) with DEX 14 (+2 modifier):

AC = 10 + 2 + (58 − 50) ÷ 5 = 10 + 2 + 1.6 = **13.6 ≈ 14**

If they are also under a Shield spell: AC = 14 + 2 = **16**

---

## Combat

Combat takes place on an **18 × 21 tile grid arena**. All four party members and all enemy monsters are placed on the grid and take individual turns.

### Turn Order

At the start of combat, every combatant rolls **initiative**:

**Initiative = d20 + DEX modifier**

Higher rolls act first. Your party members take turns in order, then all monsters act, then the cycle repeats.

### Attack Rolls

When a character attacks (melee or ranged), the game rolls:

**d20 + Attack Bonus vs. Target's AC**

- **Natural 1** (the die shows 1): Always misses, no matter the bonuses.
- **Natural 20** (the die shows 20): Always hits and is a **Critical Hit** — damage dice are doubled.
- **Otherwise:** The attack hits if the total meets or exceeds the target's AC.

The **Attack Bonus** for melee attacks is typically the character's **STR modifier**. For ranged attacks, the weapon's stats determine the bonus.

### Damage

When an attack hits, damage is rolled based on the weapon's power rating:

| Weapon Power | Damage Dice |
|-------------|-------------|
| 0–2         | 1d4         |
| 3–5         | 1d6         |
| 6–8         | 1d8         |
| 9+          | 1d10        |

**Damage = Weapon dice + STR modifier**

On a **Critical Hit**, the dice are rolled twice (but the STR modifier is only added once).

### Movement

During their turn, a character can **move** using WASD keys. Each class has a base movement range (typically 2 tiles). The **Long Shanks** spell adds +6 movement for 5 turns.

Characters can also:

- **Bump-to-attack**: Walk into an adjacent enemy to trigger a melee attack.
- **Fire ranged weapons**: Use arrow keys to fire in a cardinal direction (up, down, left, right).
- **Cast spells**: Choose from available spells.
- **Use items**: Consume potions, throw items, or use herbs.
- **Equip gear**: Open the equipment screen (costs your turn).
- **Skip turn**: Press spacebar to defend (+2 AC until next turn).

### Combat HP Bar

During combat, each character and monster displays a colored **HP bar** beneath their sprite:

- **Green** — HP above 66% (healthy)
- **Yellow** — HP between 33% and 66% (wounded)
- **Red** — HP below 33% (critical)

### Monster AI

Monsters follow a decision tree each turn:

1. If adjacent to a party member → **melee attack**
2. If the monster has spells and the cast-chance roll succeeds → **cast a spell**
3. If the monster has a ranged weapon and a target is in range → **fire ranged attack**
4. Otherwise → **move one tile closer** to the nearest visible party member

Sleeping monsters skip their turn. Invisible party members are ignored by monster targeting.

### Status Effects

| Effect | How Applied | Duration | Effect |
|--------|------------|----------|--------|
| **Sleep** | Sleep spell, Dark Slumber | 3–5 turns | Target skips all turns; broken by taking damage |
| **Poison** | Poison Spit, traps | 4 turns | Takes damage at the start of each turn |
| **Curse** | Curse spell, Hex | 3–5 turns | −2 AC and −2 attack penalty |
| **Charm** | Charm Person | 5 turns | Humanoid monster fights for the party |
| **Invisible** | Invisibility spell | 5 turns | Monsters cannot target you |
| **Blessed** | Bless spell | 5 turns | +2 attack bonus for all allies |
| **Shielded** | Shield spell | 3 turns | +2 AC bonus |

### Death & Revival

When a character's HP reaches 0, they are **incapacitated** and can no longer act. If the entire party falls, combat is lost — but surviving members are revived with 1 HP afterward. A total party wipe triggers a game over.

---

## Spells & Magic

Spells consume **Magic Points (MP)** and are divided into two schools: **Priest** and **Sorcerer**. Each class can only cast spells from its allowed school(s).

### MP Sources

| Class | MP Source | Rate |
|-------|----------|------|
| Wizard | Intelligence | 100% |
| Cleric | Wisdom | 100% |
| Paladin | Wisdom | 50% |
| Ranger | Wisdom | 50% |
| Alchemist | Intelligence | 50% |
| Druid | Higher of INT or WIS | 50% (2× regen) |

### Sorcerer Spells

These spells are available to Wizards, Alchemists, and Druids.

| Spell | MP | Effect | Range |
|-------|-----|--------|-------|
| **Magic Dart** | 5 | 2d8 + INT mod damage (single target projectile) | 99 |
| **Magic Arrow** | 5 | 4d8 + INT mod damage (piercing bolt) | 99 |
| **Fireball** | 8 | 3d8 + INT mod damage in a 3-tile radius (hits allies too!) | 99 |
| **Lightning Bolt** | 7 | 4d6 + INT mod damage to all creatures in a straight line | 99 |
| **Shield** | 5 | +2 AC to target for 3 turns | 5 |
| **Long Shanks** | 5 | +6 movement range to target for 5 turns | 99 |
| **Charm Person** | 5 | Humanoid target fights for you (5 turns, save DC 10 + INT mod) | 99 |
| **Sleep** | 5 | Puts target to sleep (5 turns, targets up to 20 HP, save DC 10 + INT mod) | 99 |
| **Invisibility** | 5 | Caster becomes invisible to enemies for 5 turns | Self |
| **Misty Step** | 5 | Teleport to a chosen location on the battlefield | 99 |
| **Animate Dead** | 5 | Summon a skeleton ally (12 HP, AC 11, +3 attack, 1d6 dmg) for 5 turns | 99 |

### Priest Spells

These spells are available to Clerics, Paladins, Rangers, and Druids.

| Spell | MP | Effect | Range | Usable |
|-------|-----|--------|-------|--------|
| **Minor Heal** | 5 | Heals 1d8 + WIS mod HP | 6 | Battle, Overworld, Town, Dungeon |
| **Major Heal** | 10 | Heals 3d8 + WIS mod HP | 4 | Battle only |
| **Mass Heal** | 14 | Heals 2d8 + WIS mod HP to all nearby allies | Self | Battle only |
| **Cure Poison** | 6 | Removes poison from target | 99 | Battle only |
| **Turn Undead** | 5 | Strips 75% HP from all undead on the battlefield | 99 | Battle only |
| **Bless** | 8 | +2 attack bonus to all allies for 5 turns | Self | Battle only |
| **Curse** | 7 | −2 AC and −2 attack penalty on target for 5 turns | 99 | Battle only |
| **Light** | 4 | Illuminates dungeon corridors for 100 turns | Self | Dungeon only |
| **Push** | 5 | Repels monsters in a 5-tile radius | Self | Overworld, Dungeon, Town |

> **Tip:** Minor Heal is one of the only spells usable outside of combat. Keep your healers' MP stocked for between-fight patching up.

> **Warning:** Fireball hits *everything* in its radius, including your own party members. Position carefully before casting!

---

## Weapons

Weapons determine your attack damage in combat. Each has a **power rating** that sets the damage dice, and some have special properties.

### Melee Weapons

| Weapon | Power | Damage | Buy | Classes |
|--------|-------|--------|-----|---------|
| Fists | 0 | 1d4 | — | All |
| Dagger | 1 | 1d4 | 20g | All except some |
| Club | 1 | 1d4 | 20g | Fighter, Cleric, Thief, Ranger, Druid |
| Mace | 2 | 1d4 | 40g | Fighter, Cleric, Paladin, Druid |
| Axe | 4 | 1d6 | 80g | Fighter, Paladin |
| Sword | 5 | 1d6 | 120g | Fighter, Paladin, Ranger |
| Spear | 6 | 1d8 | — | Fighter, Paladin |
| Broad Axe | 7 | 1d8 | — | Fighter |
| Iron Sword | 8 | 1d8 | — | Fighter, Paladin |
| Gloves | 8 | 1d8 | — | Fighter |
| Halberd | 9 | 1d10 | — | Fighter |
| Sun Sword | 10 | 1d10 | — | Fighter, Paladin |
| Mystic Sword | 10 | 1d10 | — | Fighter, Paladin |

> Weapons without a buy price can only be found as treasure in dungeon chests.

### Ranged Weapons

| Weapon | Power | Damage | Ammo | Buy | Classes |
|--------|-------|--------|------|-----|---------|
| Sling | 3 | 1d6 | Stones | 60g | Cleric, Thief, Ranger |
| Short Bow | 4 | 1d6 | Arrows | 60g | Thief, Ranger |
| Long Bow | 7 | 1d8 | Arrows | 150g | Ranger |
| Crossbow | 9 | 1d10 | Bolts | 250g | Fighter, Paladin |
| Silver Bow | 9 | 1d10 | Arrows | — | Ranger |

### Ammunition

Ranged weapons consume ammo from your inventory. When you run out, you can't fire.

| Ammo | Used By | Buy |
|------|---------|-----|
| Arrows | Short Bow, Long Bow, Silver Bow | 5g |
| Bolts | Crossbow | 8g |
| Stones | Sling | 3g |

### Throwable Items

Some items can be thrown as a ranged attack and are consumed on use:

- **Dagger** — Can be thrown (power 1) or used in melee
- **Rock** — Free throwable projectile (power 1)
- **Fire Oil** — Thrown in combat for 20 burst damage (buy: 35g)

---

## Armor

Armor is equipped in the **body** slot and determines your armor bonus to AC. Heavier armor provides better protection but is restricted by class.

| Armor | Evasion | AC Bonus | Buy | Available To |
|-------|---------|----------|-----|-------------|
| Cloth | 50 | +0 | 20g | All classes |
| Leather | 56 | +1 | 50g | Fighter, Cleric, Thief, Paladin, Ranger |
| Chain | 58 | +2 | 120g | Fighter, Cleric, Paladin, Ranger |
| Plate | 60 | +2 | — | Fighter, Paladin |
| +2 Chain | 62 | +2 | — | Fighter, Cleric, Paladin, Ranger |
| +2 Plate | 64 | +3 | — | Fighter, Paladin |
| Exotic | 67 | +3 | — | Fighter |

> Enchanted armor (+2 Chain, +2 Plate) and Exotic armor can only be found as treasure.

---

## Items & Consumables

Items are shared across the party inventory. Some are consumed on use, others have limited charges.

### Healing

| Item | Effect | Buy |
|------|--------|-----|
| Healing Herb | Restores 15 HP | 15g |
| Healing Potion | Restores 30 HP | 40g |
| Antidote | Cures poison | 10g |
| Mana Potion | Restores 10 MP | — |

### Combat Items

| Item | Effect | Buy |
|------|--------|-----|
| Fire Oil | Throw for 20 fire damage | 35g |
| Smoke Bomb | Creates a blinding cloud | — |

### Elixirs (Combat Buffs)

Elixirs provide a bonus that lasts for the next combat encounter.

| Elixir | Effect | Buy |
|--------|--------|-----|
| Elixir of Strength | +2 STR bonus | 60g |
| Elixir of Warding | +2 AC bonus | 60g |

### Tools

| Item | Effect | Buy |
|------|--------|-----|
| Torch | Illuminates dark areas (150 charges) | 5g |
| Lockpick | Opens locked doors and chests (5 uses) | 8g |
| Camping Supplies | Rest safely to restore HP/MP (3 uses) | 25g |

### Reagents (Crafting Materials)

Alchemists use these to brew potions. Rangers can find them with Forage.

| Reagent | Buy |
|---------|-----|
| Moonpetal | 12g |
| Glowcap Mushroom | 10g |
| Serpent Root | 8g |
| Brimite Ore | 15g |
| Spring Water | 3g |

---

## Experience & Leveling

Characters earn **Experience Points (XP)** by defeating monsters. Every surviving party member receives the full XP reward from each battle — XP is not split.

### Leveling Thresholds

The XP required for each level follows a simple formula:

**Level N requires N × XP-per-level cumulative XP**

The standard XP-per-level is **500** for most races. **Humans** level faster, requiring only **350 XP per level**.

| Level | Standard (500/lvl) | Human (350/lvl) |
|-------|-------------------|-----------------|
| 1 | 0 | 0 |
| 2 | 500 | 350 |
| 3 | 1,000 | 700 |
| 4 | 1,500 | 1,050 |
| 5 | 2,000 | 1,400 |
| 6 | 2,500 | 1,750 |
| 7 | 3,000 | 2,100 |
| 8 | 3,500 | 2,450 |

### What You Gain Per Level

Each level-up grants HP and MP increases that scale with your attributes:

- **HP increase** — Your class's base HP per level plus your Strength modifier. A Fighter with 18 STR (+4 modifier) gains 15 + 4 = 19 HP per level. The minimum HP gain is always 1, even with a negative modifier.
- **MP increase** — Your class's base MP per level plus a modifier from your casting stat. Which stat is used depends on the class: Wizards use Intelligence, Clerics use Wisdom, and hybrid casters like Paladins and Rangers use the higher of Intelligence or Wisdom. The minimum MP gain is 0 (you never lose MP on level-up). Non-casting classes with 0 base MP per level gain no MP regardless of stats.

Level-ups are applied immediately — your HP and MP pools grow as soon as you qualify.

### XP Rewards by Monster

| Monster | XP | Gold |
|---------|-----|------|
| Giant Rat | 15 | 2–8 |
| Goblin | 10 | 1–6 |
| Wolf | 20 | 0–5 |
| Zombie | 25 | 3–12 |
| Skeleton | 30 | 5–20 |
| Skeleton Archer | 35 | 5–18 |
| Dark Mage | 45 | 10–35 |
| Orc | 50 | 10–30 |
| Orc Shaman | 55 | 12–35 |
| Troll | 75 | 15–40 |

---

## Monsters & Bestiary

The world of Realm of Shadow is populated with dangerous creatures. Here is a field guide to the monsters you will encounter.

### ![Giant Rat](images/monster_giant_rat.png) Giant Rat

*A common pest found in basements and dungeon tunnels. Weak alone, but they attack in swarms.*

HP: 8 | AC: 12 | Attack: +2 | Damage: 1d4
Found in: Dungeons, house basements

---

### ![Goblin](images/monster_goblin.png) Goblin

*Small, sneaky creatures that attack in groups. They carry thrown rocks for ranged harassment.*

HP: 6 | AC: 11 | Attack: +2 | Damage: 1d4
**Ranged:** Thrown rock (range 4, 1d3 damage)
Found in: Dungeons, overworld

---

### ![Wolf](images/monster_wolf.png) Wolf

*Fierce grey wolves that hunt in packs. Fast and cunning.*

HP: 12 | AC: 13 | Attack: +4 | Damage: 1d6+1
Found in: Overworld, dungeons

---

### ![Skeleton](images/monster_skeleton.png) Skeleton

*Undead warriors animated by dark magic. Vulnerable to Turn Undead and holy weapons.*

HP: 16 | AC: 13 | Attack: +3 | Damage: 1d6+1
**Undead** — Takes massive damage from Turn Undead
Found in: Dungeons

---

### Skeleton Archer

*A skeletal bowman that fires bone arrows from distance. Even more dangerous than regular skeletons.*

HP: 12 | AC: 12 | Attack: +3 | Damage: 1d4 (melee)
**Ranged:** Bone arrow (range 6, +4 attack, 1d6 damage)
**Undead** — Vulnerable to Turn Undead
Found in: Dungeons

---

### ![Zombie](images/monster_zombie.png) Zombie

*Shambling corpses — slow but surprisingly durable. They just keep coming.*

HP: 20 | AC: 10 | Attack: +2 | Damage: 1d6+1
**Undead** — Vulnerable to Turn Undead
Found in: Dungeons

---

### ![Orc](images/monster_orc.png) Orc

*Brutal and well-armed warriors. Orcs are a serious threat, especially in groups. They carry javelins for ranged attacks.*

HP: 22 | AC: 13 | Attack: +5 | Damage: 1d8+2
**Ranged:** Javelin (range 3, +3 attack, 1d6+1 damage)
**Humanoid** — Can be affected by Charm Person
Found in: Dungeons, overworld

---

### ![Orc Shaman](images/monster_orc_shaman.png) Orc Shaman

*An orc witch doctor who bolsters allies with healing magic and poisons foes.*

HP: 16 | AC: 11 | Attack: +3 | Damage: 1d4
**Humanoid** — Can be affected by Charm Person
**Spells:**

- **Mend Wounds** (40% chance) — Heals a wounded ally for 1d8+2 HP
- **Poison Spit** (30% chance) — Poisons a party member (STR save DC 11, 2 damage/turn for 4 turns)

Found in: Dungeons

---

### ![Dark Mage](images/monster_dark_mage.png) Dark Mage

*A robed figure crackling with dark energy. Attacks from range and casts debilitating spells.*

HP: 14 | AC: 12 | Attack: +4 | Damage: 2d4+1
**Ranged:** Dark bolt (range 7, +5 attack, 2d4+1 damage)
**Humanoid** — Can be affected by Charm Person
**Spells:**

- **Dark Slumber** (30% chance) — Puts a party member to sleep (WIS save DC 12, 3 turns)
- **Hex** (25% chance) — Curses a party member (−2 AC, −2 attack for 3 turns)

Found in: Dungeons

---

### ![Troll](images/monster_troll.png) Troll

*A massive brute with thick hide. Hits incredibly hard and regenerates health each turn.*

HP: 30 | AC: 14 | Attack: +6 | Damage: 2d6+2
**Humanoid** — Can be affected by Charm Person
**Spells:**

- **Regenerate** (40% chance) — Heals itself for 1d6+2 HP per turn

Found in: Dungeons (rare), overworld (rare)

> **Tip:** Focus fire on Trolls to overwhelm their regeneration. A Curse spell (-2 attack) can reduce their devastating damage output.

---

## Controls & Interface

### Overworld Controls

| Key | Action |
|-----|--------|
| Arrow keys | Move the party |
| L | Open the game log |
| H | Help overlay |
| 1–4 | View character details |
| ESC | Back / close |

### Combat Controls

| Key | Action |
|-----|--------|
| W/A/S/D | Move the active character |
| Arrow keys | Fire ranged weapon (up/down/left/right) |
| Enter | Confirm menu selection |
| Up/Down | Navigate menu options |
| Spacebar | Skip turn (defend, +2 AC) |
| L | Open combat log |
| H | Help overlay |
| ESC | Back / cancel |

### Combat Menu Options

When it's your turn, you'll see a menu on the right side of the screen. Available options depend on your class and equipment:

- **[Weapon Name]** — Fire your ranged weapon (if equipped)
- **Throw** — Throw a consumable item (rocks, daggers, fire oil)
- **Cast (XMP)** — Open the spell selection list
- **Use Item** — Use a potion, herb, or consumable
- **Equip** — Open the equipment screen (costs your turn)

Movement (WASD) and melee attacks (bump into enemies) are always available without using the menu.

### Log Screen

Press **L** at any time to open the full game log. This scrollable overlay shows every combat action, spell cast, damage dealt, and event that has occurred. Use **Up/Down** arrows to scroll through the history, and **L** or **ESC** to close.

Log entries are color-coded:

- **White** — Hits and damage
- **Gold** — Critical hits and victories
- **Orange** — Turn announcements
- **Gray** — Misses and resisted effects
- **Green** — Healing
- **Yellow** — Gold and treasure
- **Purple** — Sleep effects
- **Red** — Curses and fallen characters
- **Sickly green** — Poison effects

---

*May your blades stay sharp and your spells true. The realm needs heroes — will you answer the call?*
