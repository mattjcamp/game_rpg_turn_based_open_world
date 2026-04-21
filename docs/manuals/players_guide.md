# REALM OF SHADOW

---

## PLAYER'S HANDBOOK

*A Player's Guide to the Lands of Shadow*

*An Ultima III-Inspired Tactical Fantasy RPG*

---

## INSTALLATION & GETTING STARTED

---

There are two ways to play Realm of Shadow: download a pre-built release, or run directly from the Python source code. Both methods are described below.

### Option 1: Downloading & Playing (macOS)

A pre-built macOS version is available on the Releases page. To get started:

**1.** Download the `.zip` file from the latest release:
[https://github.com/mattjcamp/game_rpg_turn_based_open_world/releases](https://github.com/mattjcamp/game_rpg_turn_based_open_world/releases)

**2.** Unzip it — you'll get a folder called **RealmOfShadow**.

**3.** Before opening the game, you must clear the macOS quarantine flag. Open Terminal and run:

```
xattr -cr ~/Downloads/RealmOfShadow/
```

If you unzipped it somewhere other than Downloads, adjust the path — or drag the folder onto the Terminal window to fill it in automatically. You need to do this each time you download a new release.

**4.** Open the **RealmOfShadow** folder and double-click the file called **RealmOfShadow** (the one with no file extension) to launch the game.

**First launch:** The game may take 10–20 seconds to appear the first time you run it while your system unpacks and caches the bundled libraries. Subsequent launches will be faster.

**"Damaged and can't be opened" error:** If you skipped step 3 and macOS says the app is damaged, don't worry — the file isn't actually damaged. macOS shows this message for any downloaded app that isn't notarized with Apple. Run the `xattr -cr` command from step 3 and try again.

### Option 2: Run from Python Source

If thou dost prefer to run from source (or wish to modify the game), follow these steps. Requires **Python 3.10+**.

**1.** Clone or download the repository:
[https://github.com/mattjcamp/game_rpg_turn_based_open_world](https://github.com/mattjcamp/game_rpg_turn_based_open_world)

**2.** Install the dependencies:

```
pip3 install -r requirements.txt
```

This installs **pygame** (≥2.5) and **numpy** (≥1.24).

**3.** Run the game:

```
python3 main.py
```

---

For the latest updates, bug reports, and source code, visit the GitHub repository: [github.com/mattjcamp/game_rpg_turn_based_open_world](https://github.com/mattjcamp/game_rpg_turn_based_open_world)

---

Welcome, brave adventurer! Long have the lands of Shadow awaited a champion bold enough to face the darkness that gathers at the edge of the world. The people whisper of ancient evils stirring in forgotten dungeons, of cursed treasures guarded by creatures born of nightmare, and of a shadow that grows longer with each passing day.

Realm of Shadow is a turn-based tactical RPG in the tradition of the classic Ultima games. Thou dost lead a party of up to four adventurers through a dangerous open world — exploring the overworld, delving into dungeons, trading in towns, and engaging in grid-based tactical combat against a host of enemies.

### First Steps

After creating thy party, thou wilt appear on the overworld map — a vast wilderness of forests, mountains, and open plains. Use the **WASD** keys to move thy party across the land. If thou art ever unsure of what to do, press the **H** key at any time to open the help screen, which lists all available commands and options.

A town will be nearby when thou first set out — seek it and enter, for within its walls thou wilt find merchants to outfit thy party with weapons and armor, healers to tend thy wounds, and quest givers who will set thee on thy path. Walk into the town entrance to step inside.

Beware: **monsters roam the overworld**, and they will attack if thou dost draw near. In the early going, stay close to town until thy party is properly equipped. When monsters approach, combat will begin automatically — there is no fleeing from a fight once it has started, so choose thy battles wisely.

### The Overworld

The overworld is a vast landscape of forests, mountains, rivers, and coastline. Roam freely across the map, discovering towns, dungeon entrances, and points of interest. Time passes as thou dost travel — day turns to night, and the seasons change. Beware: wandering monsters grow stronger the further thou dost venture from civilization.

### Towns & Commerce

Towns offer respite from the dangers of the wilderness. Walk into an NPC to speak with them — merchants sell weapons, armor, and supplies; healers restore thy wounds; and quest-givers send thee on adventures for gold and glory. Speak to everyone, for some hold valuable clues to hidden treasures and secret passages.

### Thy Party

Thy party shares a pool of gold and a communal inventory, but each character maintains their own equipped gear, hit points, magic points, and experience. The party inventory screen lets thee manage thy shared stash, cast spells outside of combat, brew potions, and review each companion's status at a glance.

Choose thy party wisely — a balanced group with frontline fighters, healers, and spellcasters will fare better than one that leans too heavily upon a single role. **The wilderness is unforgiving, and a lone adventurer rarely survives long.**

### Combat

When combat is joined, the action moves to a tactical grid arena. Each character and monster takes individual turns based on initiative. Move with the WASD keys, attack by walking into foes, and fire ranged weapons with the arrow keys. Positioning matters — protect thy spellcasters behind a wall of fighters, and watch for flanking enemies.

### Dungeons

Dungeons are multi-floor underground labyrinths filled with monsters, traps, treasure, and quest objectives. Lighting varies — some floors are well-lit by wall torches, while others are shrouded in darkness. Bring torches, a Light spell, or a Dwarf with Infravision to see thy way through the deepest halls.

---

Now that thou hast seen the shape of the world, let us prepare thee for the journey. In the pages that follow, thou shalt learn of the races and classes available to thy companions, the ways of combat, and the secrets of the realm.

---

## THE RACES OF THE REALM

---

Five races walk the lands of Shadow, each possessing unique strengths and innate abilities. Thy choice of race will shape thy character's attributes and grant a special power that no training can replicate. Consider well which race best complements the profession thou hast in mind.

### Human

*Versatile and adaptable, excels in no single area but has no weaknesses.*

| STR | DEX | INT | WIS |
|:---:|:---:|:---:|:---:|
| +0  | +0  | +0  | +0  |

**Innate Ability — Fast Learner:** Humans require only 750 XP per level instead of the standard 1000, allowing them to level up 25% faster than other races. This compensates for their lack of stat bonuses and makes them an excellent choice for any class.

---

### Dwarf

*Stout and hardy, natural miners and warriors with keen underground senses.*

| STR | DEX | INT | WIS |
|:---:|:---:|:---:|:---:|
| +2  | -1  | +0  | +1  |

**Innate Ability — Infravision:** Dwarves can see in total darkness. Dungeon corridors that would be pitch-black to other races are dimly visible to a Dwarf, eliminating the need for a torch or Light spell.

---

### Halfling

*Small and nimble, surprisingly resilient and hard to hit.*

| STR | DEX | INT | WIS |
|:---:|:---:|:---:|:---:|
| -2  | +2  | +0  | +1  |

**Innate Ability — Pickpocket:** Halflings can attempt to steal items from town NPCs. This ability has a daily cooldown and a chance of failure — use it wisely.

---

### Elf

*Graceful and keen-minded, with a natural affinity for magic and sharp senses.*

| STR | DEX | INT | WIS |
|:---:|:---:|:---:|:---:|
| -1  | +1  | +2  | +0  |

**Innate Ability — Galadriel's Light:** Elves can conjure a soft magical illumination, lighting up dark areas without consuming a torch. This ability has a daily cooldown.

---

### Gnome

*Clever and curious, combining tinkering skill with innate magical talent.*

| STR | DEX | INT | WIS |
|:---:|:---:|:---:|:---:|
| -1  | +0  | +2  | +1  |

**Innate Ability — Tinker:** Gnomes can repair broken equipment and craft simple items from reagents. This ability has a daily cooldown.

---

## THE PROFESSIONS

---

Eight professions are available to the aspiring adventurer. Each determines thy character's combat prowess, magical abilities, allowed equipment, and special skills. The choice of profession is perhaps the most important decision thou wilt make, for it shapes the entire course of thy adventure.

### Table 1: Characteristics of Each Profession

| Class     | HP/Lvl | MP/Lvl | Range | Spell Type | Best Armor |
|-----------|:------:|:------:|:-----:|:----------:|:----------:|
| Fighter   |   15   |   0    |   4   |    None    |   Plate    |
| Wizard    |    4   |   15   |   2   |  Sorcerer  |   Cloth    |
| Cleric    |    6   |   10   |   2   |   Priest   |   Chain    |
| Thief     |    5   |    0   |   6   |    None    |  Leather   |
| Paladin   |   10   |    5   |   4   |   Priest   |   Plate    |
| Ranger    |   10   |    3   |   6   |   Priest   |   Chain    |
| Druid     |    5   |    8   |   2   |    Both    |   Cloth    |
| Alchemist |    4   |    8   |   4   |  Sorcerer  |   Cloth    |

---

### Fighter

*The quintessential warrior — tough, versatile, and deadly in melee.*

| HP/Lvl | MP/Lvl | Range | Spells |
|:------:|:------:|:-----:|:------:|
|   15   |   0    |   4   |  None  |

**Weapons:** All weapons
**Armor:** All armor (Cloth, Leather, Chain, Plate)

Fighters are the backbone of any party. With the highest HP per level, a generous 4-tile combat range, and access to every weapon and armor type, they belong on the front line where the fighting is thickest. They wield no magic but more than compensate with raw staying power and devastating damage output.

---

### Wizard

*Master of arcane forces — fragile but devastatingly powerful at range.*

| HP/Lvl | MP/Lvl | Range | Spells   |
|:------:|:------:|:-----:|:--------:|
|   4    |   15   |   2   | Sorcerer |

**Weapons:** Fists, Dagger
**Armor:** Cloth only

Wizards command the most diverse and powerful spell list in the game. From Fireball to Lightning Bolt, Charm Person to Animate Dead, they reshape the battlefield. Their weakness is severe — the lowest HP per level, no armor, and only daggers for weapons. Keep them behind thy front line and let them rain destruction from safety.

**Arcane Focus** — Spell damage is increased by the Intelligence modifier.

---

### Cleric

*Holy warrior and healer — the party's lifeline in long fights.*

| HP/Lvl | MP/Lvl | Range | Spells |
|:------:|:------:|:-----:|:------:|
|   6    |   10   |   2   | Priest |

**Weapons:** Fists, Club, Mace, Sling
**Armor:** Cloth, Leather, Chain

Clerics are the primary healers of the party. Minor Heal, Major Heal, Mass Heal, and the ultimate Restore spell keep everyone standing, while Cure Poison removes dangerous status effects. They can also fight respectably in melee with maces and clubs, wear chain armor, and devastate undead with Turn Undead from level 2 — a signature ability no other class matches at that tier. Every party should have one.

**Turn Undead** (Cleric Level 2+; Paladin Level 5+) — Channels holy energy at every undead on the battlefield. Each undead makes a Wisdom save against the caster's DC. On a failed save, the undead is destroyed completely; on a success it still takes 50% of its max HP as holy damage.

---

### Thief

*Quick, cunning, and deadly from the shadows — unmatched utility.*

| HP/Lvl | MP/Lvl | Range | Spells |
|:------:|:------:|:-----:|:------:|
|   5    |   0    |   6   |  None  |

**Weapons:** Fists, Dagger, Club, Sling, Short Bow
**Armor:** Cloth, Leather

The Thief has the longest combat range of any class (6 tiles), making them effective skirmishers who can outmaneuver most opponents. With a Short Bow they can pelt enemies from a safe distance. At Level 3, Backstab turns the humble Dagger into a devastating weapon. At Level 7, Shadow Step transforms them into true hit-and-run fighters. Their real value outside combat is Pick Locks and Detect Traps, which open up areas and loot that other classes cannot reach.

**Pick Locks** — Open locked doors and chests. **Backstab** (Level 3+) — Critical hits with daggers on a DEX save. **Shadow Step** (Level 7+) — Move after attacking.

---

### Paladin

*Holy knight — a tough fighter with limited healing and anti-undead power.*

| HP/Lvl | MP/Lvl | Range | Spells |
|:------:|:------:|:-----:|:------:|
|   10   |   5    |   4   | Priest |

**Weapons:** All weapons
**Armor:** Cloth, Leather, Chain, Plate

Paladins combine Fighter durability with limited Priest magic. They can wear the heaviest armor, use any weapon, and still cast healing spells (though with a smaller MP pool than a Cleric). Holy Smite makes them devastating against undead — every attack hits twice as hard — and from level 5 they can also channel Turn Undead, making them a formidable second line of defense against the undead when no Cleric is at hand.

**Holy Smite** — Double damage against undead. **Turn Undead (Level 5+)** — From level 5, a Paladin can channel holy energy at every undead on the battlefield, just as a Cleric does. Each undead saves vs Wisdom: failure = destroyed, success = 50% max-HP damage.

---

### Ranger

*Versatile woodsman — bow master, herbalist, and able scout.*

| HP/Lvl | MP/Lvl | Range | Spells |
|:------:|:------:|:-----:|:------:|
|   10   |   3    |   6   | Priest |

**Weapons:** Fists, Dagger, Club, Sling, Short Bow, Long Bow, Crossbow, Sword
**Armor:** Cloth, Leather, Chain

Rangers are durable frontliners with bow mastery, wilderness lore, and limited healing magic. Their 6-tile combat range matches a Thief's reach, and they are proficient with every bow in the game — Short Bow, Long Bow, and Crossbow — making them the party's premier ranged attacker. Their small MP pool lets them cast the occasional Minor Heal to keep the party going between fights. A strong choice for a self-sufficient frontliner who can also scout dangerous terrain.

**Herbalism** — When the party presses E to examine a tile in the wilderness, each Ranger rolls a d20 + INT saving throw against DC 10. On a success, the Ranger identifies a potion reagent in the area and adds it to the shared inventory. **Pick Locks (Level 3+)** — From level 3, a Ranger can pick locked doors and chests exactly as a Thief can (d20 + DEX vs DC 12, one lockpick consumed per attempt). **Detect Traps (Level 3+)** — From level 3, the Ranger's woodcraft reveals hidden traps before the party steps on them, rolling d20 + DEX vs DC 10 to spot each trap within sight.

---

### Druid

*Nature's emissary — the only dual-caster, drawing from both Priest and Sorcerer spell lists.*

| HP/Lvl | MP/Lvl | Range | Spells |
|:------:|:------:|:-----:|:------:|
|   5    |    8   |   2   |  Both  |

**Weapons:** Fists, Dagger, Club, Mace, Sling
**Armor:** Cloth only

The Druid is the game's only hybrid caster, able to cast both Priest spells (Minor Heal, Cure Poison, Light) and Sorcerer spells (Magic Dart, Shield, Knock). To balance that remarkable spell breadth, a Druid's Magic Point pool is modest — about half the size of a Wizard's or Cleric's at equivalent stats. Their MP pool is drawn from the average of Intelligence and Wisdom and they regenerate MP twice as fast as other classes. The trade-off is low HP and cloth-only armor — like Wizards, they need protection.

**Dual Casting** — Access to both Priest and Sorcerer spell lists. **2× MP Regen** — MP regenerates twice as fast as other classes. **Half-caster Pool** — Base MP is ≈ half a Wizard's, balancing breadth against raw spell count.

---

### Alchemist

*Master of potions and elixirs — support specialist and crafter.*

| HP/Lvl | MP/Lvl | Range | Spells   |
|:------:|:------:|:-----:|:--------:|
|   4    |   8    |   4   | Sorcerer |

**Weapons:** Fists, Dagger, Sling
**Armor:** Cloth only

Alchemists have modest combat ability but provide unique value through potion crafting. Their 4-tile range matches the Fighter's mobility, a Sling gives them a light ranged option, and access to Sorcerer spells means they can still contribute offensive magic. Brew Potions lets them turn reagents into healing potions, antidotes, and other useful consumables. Because that crafting utility is so powerful, the Alchemist is balanced as a partial caster — their base Magic Point pool is half their Intelligence score (roughly half a Wizard's raw casting output), so lean on potions and thrown oils as much as on spells.

**Brew Potions** — Craft potions from reagents found in shops and dungeons. **Half-caster Pool** — Base MP is ½ Intelligence, balancing brewing utility against raw spellcasting.

---

## COMBAT

---

Combat takes place on an 18 × 21 tile grid arena. All four party members and all enemy monsters are placed on the grid and take individual turns. Each character may independently control their actions — moving, fighting, or casting spells.

At the start of combat, every combatant rolls initiative: d20 + DEX modifier. Higher rolls act first. Thy party members take turns in order, then all monsters act, then the cycle repeats. When a character attacks, the game rolls d20 + Attack Bonus against the target's Armor Class. A natural 1 always misses. A natural 20 always hits and doubles the damage dice. Be careful of thy positioning — monsters can attack on diagonals while characters can only strike in cardinal directions.

### Movement & Melee

During their turn, a character may move using the WASD keys. Each class has a base movement range. Walk into an adjacent enemy to trigger a melee attack. Use the arrow keys to fire ranged weapons in cardinal directions. Press spacebar to skip thy turn and defend, gaining +2 AC until thy next turn.

### The Action Pane

The right-hand pane displays the active character's available actions. From here thou canst cast spells by selecting from thy known spell list, fire ranged weapons such as bows or slings at distant targets, use items from the party inventory, or simply pass thy turn. When all enemies have been slain and the battle is won, a **Leave** option will appear in the pane — select it to exit the encounter and return to the map. Any experience and gold earned will be awarded at this time.

### Status Effects

| Effect    | Duration  | Description                                  |
|-----------|:---------:|----------------------------------------------|
| Sleep     | 3-5 turns | Target skips all turns; broken by damage     |
| Poison    | 4 turns   | Takes damage at start of each turn           |
| Curse     | 3-5 turns | -2 AC and -2 attack penalty                  |
| Charm     | 3 turns   | Humanoid monster fights for the party         |
| Invisible | 3 turns   | Monsters cannot target the character          |
| Blessed   | 4 turns   | +2 attack bonus for all allies               |
| Shielded  | 3 turns   | +1 AC bonus                                  |

---

## QUESTS & ADVENTURES

---

### Finding Quests

Quest givers can be found throughout the towns of the realm. Look for NPCs with **highlighted text above their heads** — this marks them as having a quest to offer. Walk into them and press Enter to speak. If they have a task for thee, they will describe the quest and it will be added to thy journal. Not every NPC is a quest giver, but those with the glowing text always have something important to say.

Open the **Quest Screen** from the party menu to review thy active quests, their objectives, and progress. When on a quest, keep a sharp eye in dungeons — **quest-related monsters and items will glow** to distinguish them from ordinary encounters and treasure. Defeat the marked monsters or collect the glowing items to fulfill thy objectives, then return to the quest giver to claim thy reward.

### Dungeon Exploration

The dungeons have, of late, become particularly treacherous and deadly. Explore carefully and slowly. Secret doors abound throughout the different dungeons. Magical winds howl down the corridors, blowing out all light. If thou walks slowly, glimpses of faint mystic writings may be noticed periodically.

There also exist many traps and pitfalls for the unwary. A Thief is an excellent choice to have in a party. If the party puts the Thief at the front, thou wilt have an excellent chance of spotting traps before they are sprung. Many strange and wonderful places are hidden within different dungeons, such as fountains. Some fountains are beneficial, while others are poisonous. Always drink carefully at a fountain.

---

The towns of the realm offer respite from the dangers of the wilderness. Walk into an NPC to speak with them — merchants, healers, and quest-givers all have wisdom to share and goods to trade. Speak to all of them, for some hold valuable clues to the locations of hidden items and secret passages.

Bare is the back who hast not kin to protect it! Decide quickly — equip thy party with the finest weapons and armor thy purse can afford. The party's ability to survive depends as much on the quality of its equipment as on the quality of its leader. Forget not to obtain enough Food, for towns are widely scattered and starvation is always so unpleasant to watch.

---

## CONTROLS & COMMANDS

---

The following commands are available whilst exploring the overworld. Commit them to memory, for swift action is often the difference between life and death.

| Key                | Action                                |
|--------------------|---------------------------------------|
| **W / A / S / D**  | Move on the overworld map             |
| **Arrow Keys**     | Move on the overworld map (alternate) |
| **P**              | Open party inventory screen           |
| **L**              | Open game log                         |
| **H**              | Toggle help screen                    |
| **M**              | Open settings                         |
| **E**              | Open / close examine view             |
| **ESC**            | Quit game                             |

### Interactions

Walk into a town entrance or dungeon entrance to enter. Walk into an NPC to speak with them. Walk into an enemy on the overworld to initiate combat. In the examine view, use **[W/A/S/D]** to look around, **[L]** to drop items, and walk over ground items to pick them up.

### Party Screen

Press **[P]** to open the party inventory. Use **[Up/Down]** to select a party member, **[Enter]** to view character details, and **[ESC]** to close the screen.

### Combat Controls

During combat, use **[W/A/S/D]** to move thy character on the tactical grid. Walk into an adjacent enemy to strike with a melee weapon. Press the **[Arrow Keys]** to fire a ranged weapon in that direction. Press **[Spacebar]** to defend, gaining +2 AC until thy next turn. Press **[1–4]** during the loot phase to switch which party member collects treasure.

---

## BESTIARY

---

The lands of Shadow teem with dangerous creatures, from vermin in the cellars to terrible beasts lurking in the deepest dungeon halls. Herein is a field guide to the monsters thou shalt encounter on thy journey. Study it well, for knowledge of thine enemy is the first step toward victory.

### Giant Rat

*A common pest found in basements and dungeon tunnels. Weak alone, but they attack in swarms.*

**HP: 8 • AC: 12 • Attack: +2 • Damage: 1d4**

Found in dungeons and house basements. Swarms of rats are a frequent first encounter for new adventurers. They pose little individual threat but can overwhelm the careless.

---

### Goblin

*Small, sneaky creatures that attack in groups. They carry thrown rocks for ranged harassment.*

**HP: 6 • AC: 11 • Attack: +2 • Damage: 1d4**

Ranged: Thrown rock (range 4, 1d3). Goblins are cowardly but cunning — they prefer to pelt the party from a distance and flee when cornered.

---

### Wolf

*Fierce grey wolves that hunt in packs. Fast and cunning.*

**HP: 12 • AC: 13 • Attack: +4 • Damage: 1d6+1**

Found roaming the overworld and in dungeon corridors. Wolves are swift and dangerous in numbers. Keep thy formation tight.

---

### Skeleton

*Undead warriors animated by dark magic. Vulnerable to Turn Undead and holy weapons.*

**HP: 16 • AC: 13 • Attack: +3 • Damage: 1d6+1**

Undead — takes massive damage from Turn Undead. A Cleric is invaluable against these foes. Found in dungeons throughout the realm.

---

### Zombie

*Shambling corpses — slow but surprisingly durable. They just keep coming.*

**HP: 20 • AC: 10 • Attack: +2 • Damage: 1d6+1**

Undead — vulnerable to Turn Undead. Zombies are slow but absorb punishment that would fell lesser creatures. Cleave through them quickly.

---

### Orc

*Brutal and well-armed warriors. A serious threat, especially in groups.*

**HP: 22 • AC: 13 • Attack: +5 • Damage: 1d8+2**

Ranged: Javelin (range 3, 1d6+1). Humanoid — can be charmed. Orcs are among the most dangerous common enemies in the realm.

---

### Orc Shaman

*An orc witch doctor who bolsters allies with healing magic and poisons foes.*

**HP: 16 • AC: 11 • Attack: +3 • Damage: 1d4**

Casts Mend Wounds to heal allies and Poison Spit to weaken the party. Eliminate shamans first to prevent them from healing their warriors.

---

### Dark Mage

*A robed figure crackling with dark energy. Attacks from range and casts debilitating spells.*

**HP: 14 • AC: 12 • Attack: +4 • Damage: 2d4+1**

Ranged: Dark bolt (range 7, 2d4+1). Casts Dark Slumber and Hex. Close distance quickly — their ranged attacks are devastating.

---

### Troll

*A massive brute with thick hide. Hits incredibly hard and regenerates health each turn.*

**HP: 30 • AC: 14 • Attack: +6 • Damage: 2d6+2**

Regenerates 1d6+2 HP per turn. Focus fire to overwhelm its regeneration. A Curse spell can reduce its devastating damage output.

---

### Dragon

*An ancient wyrm of terrible power. The most fearsome creature in the realm.*

**HP: 60 • AC: 18 • Attack: +10 • Damage: 3d8+4**

Ranged: Fire breath (range 5, 4d6 damage in a cone). The Dragon is the deadliest foe thou shalt face. It strikes with devastating claws and breathes searing flame that scorches all in its path. Only the most powerful and well-prepared parties should dare challenge a Dragon. Bring thy strongest weapons, healing magic, and courage.

---

## THE ARCANE & DIVINE ARTS

---

Spells consume Magic Points (MP) and are divided into two schools: Sorcerer and Priest. Each class may only cast spells from its allowed school. The Druid alone draws from both traditions. Thy MP pool is determined by thy class and the relevant attribute — Intelligence for Sorcerers, Wisdom for Priests.

### Magic Point Sources

| Class     | Attribute      | Rate         | School   |
|-----------|:--------------:|:------------:|:--------:|
| Wizard    | Intelligence   | 100%         | Sorcerer |
| Cleric    | Wisdom         | 100%         | Priest   |
| Paladin   | Wisdom         | 50%          | Priest   |
| Ranger    | Wisdom         | 50%          | Priest   |
| Alchemist | Intelligence   | 50%          | Sorcerer |
| Druid     | avg(INT, WIS)  | 50% (2× regen) | Both  |

### Sorcerer Spells

These spells are available to Wizards, Alchemists, and Druids. New spells unlock at every level — higher-level spells are more powerful but require more MP to cast.

| Spell           | Lvl | MP | Effect                                           |
|-----------------|:---:|:--:|--------------------------------------------------|
| **Magic Dart**  |  1  |  3 | 1d6 + INT mod damage (single target projectile)  |
| **Shield**      |  1  |  4 | +1 AC to target for 3 turns                      |
| **Sleep**       |  1  |  5 | Puts target to sleep (2 turns, save DC 8 + INT)  |
| **Long Shanks** |  2  |  6 | +4 movement range to target for 3 turns          |
| **Knock**       |  2  |  6 | Unlocks a locked door (d20 + INT vs DC 12)       |
| **Magic Arrow** |  3  |  8 | 3d8 + INT mod damage (piercing bolt)             |
| **Misty Step**  |  4  |  8 | Teleport to a chosen location on the battlefield |
| **Invisibility**|  4  | 16 | Caster becomes invisible for 3 turns             |
| **Charm Person**|  5  | 14 | Humanoid fights for you (3 turns, save DC 12 + INT) |
| **Lightning Bolt** | 5 | 15 | 6d6 + INT mod damage in a straight line        |
| **Animate Dead**|  6  | 20 | Summon a skeleton ally for 5 turns               |
| **Fireball**    |  7  | 25 | 5d8 + INT mod in 3-tile radius (hits allies!)    |

**Warning:** Fireball is the game's most devastating spell, but it hits everything in its radius — including thine own party members! Position carefully before casting.

### Priest Spells

These spells are available to Clerics, Paladins, Rangers, and Druids. Priest magic focuses on healing, protection, and turning the undead.

| Spell           | Lvl | MP | Effect                                              |
|-----------------|:---:|:--:|-----------------------------------------------------|
| **Minor Heal**  |  1  |  3 | Heals 1d6 + WIS mod HP (usable outside combat)      |
| **Light**       |  1  |  3 | Illuminates dungeon corridors for 100 turns          |
| **Cure Poison** |  2  |  5 | Removes poison from target                           |
| **Turn Undead** |  2  |  8 | Cleric (Lvl 2+) or Paladin (Lvl 5+). Each undead saves vs WIS — fail = destroyed, pass = 50% HP damage |
| **Bless**       |  3  | 10 | +2 attack bonus to all allies for 4 turns            |
| **Curse**       |  3  | 10 | −2 AC and −2 attack on target for 4 turns            |
| **Major Heal**  |  4  | 15 | Heals 4d8 + WIS mod HP                              |
| **Push**        |  5  | 14 | Repels monsters in a 5-tile radius                   |
| **Mass Heal**   |  6  | 25 | Heals 3d10 + WIS mod HP to all nearby allies         |
| **Restore**     |  7  | 35 | Fully restores HP and MP for all allies, cures all poisons |

**Tip:** Minor Heal and Light are usable outside of combat. Keep thy healers' MP stocked for between-fight patching up. At Level 1, thy MP pool is small — save it for when it counts.

**Warning:** Restore is the Cleric's ultimate spell — it fully heals the entire party's HP and MP and cures all poisons, but at 35 MP it costs half the Cleric's total pool at Level 7, and the caster's own MP is not restored.

---

## DUNGEON MASTER MODE

---

*This mode is not for the faint of heart.*

Realm of Shadow includes a built-in **Dungeon Master Mode** — a powerful editing and creation toolset that allows players to craft their own custom adventures from scratch. To access it, select **Dungeon Master Mode** from the main menu.

Within Dungeon Master Mode, nearly every aspect of the game is customizable. Thou canst design new **overworld maps** with custom terrain layouts, build entirely new **towns** filled with shops and NPCs, create intricate **dungeon levels** with traps and treasure, write **quests** with custom objectives and rewards, and even replace the game's **graphics** with thine own artwork. The tool gives thee the same building blocks used to create the original campaign.

A word of caution: Dungeon Master Mode is a complex tool. Building a complete adventure requires working with map grids, tile placement, NPC scripting, encounter balancing, and module configuration files. It is a rewarding but demanding process, and thou may find it helpful — even necessary — to enlist the aid of an **LLM assistant** (such as Claude or ChatGPT) to help debug issues, generate content, and work through the more intricate details of module creation. Do not be discouraged if it takes time to master; the results are well worth the effort.

---

Thou art now as prepared as possible to face the trials of thy quest. Drink deep of the fellowship of thy companions, for the morrow may bring thy parting. Journey onward, and may the Gods of the People grant thou victory!
