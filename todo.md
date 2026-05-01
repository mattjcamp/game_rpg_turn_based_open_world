## Polish
- The Sun Sword Aura option should only appear if the character has the sun sword equiped
- the language in forest dungeons should not say "you ascend to the next level, but you go to another area"
- One quest should be designated the "last quest" and will prompt a special end of game screen. Players will still have the option to play return to the game.

## Bugs
- Map state doesn't appear to be persistant. Changes from quests get lost, ship postions are not recorded, and destroyed spawns reappear when the game is reloaded. Audit how the maps are saved. Keep in mind that once a new game has begun, that map should be consistant until the end of the game. This probably requires a map saved for each game independently of the defined module map.

## Features

- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to addd a way to communicate content