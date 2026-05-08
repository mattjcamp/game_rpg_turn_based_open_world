cd /Users/matthewcampbell/Projects/game_rpg_turn_based_open_world/web
npm run dev

python3 main.py

## Polish

- Port boat feature
- Port Examine tile feature (including making sure rangers and alchemists can find herbs)
- Port lockpick and knock spell feature (thiefs, rangers, spellcasters)
- Make sure the characters in combat are correct (damage, weapons, etc)
- Port Party formation workflow and add Constitution ability score as the way for all to get hit point mods
- Make sure 2x monsters are bigger on screen and their boundries are respected
- Make sure that monsters with effects and spellcasting use their abilities
- Port Dungeon feature (they only should be generated one time, we only need procedural)
- Port Quest Feature
- Add worflow (Return to Game, New Game)

## Bugs
- Again, I found in a second random monster encounter that the party did not have it's normal options appear on the right (range, cast, throw). No error appeared in the console.

## Features



- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to addd a way to communicate content