cd /Users/matthewcampbell/Projects/game_rpg_turn_based_open_world/web
npm run dev

python3 main.py

## Polish

- Do a full QA on party creation attributes, combat, etc. Do a few playthroughs.
- Add soundtrack (only two mpg3 to keep it small)
- Lighting should not pass through walls and essentially only light based on Light of Sight and the lighting effect range
- In the character creation screen, add descriptions of races and classes with detailed lists of special abilities

## Bugs
- The party graphics are missing in the published version
- Again, I found in a second random monster encounter that the party did not have it's normal options appear on the right (range, cast, throw). No error appeared in the console.

## Features



- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to addd a way to communicate content