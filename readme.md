# NOTE Development on Realm of Shadow has Stopped

I made the decision to start this project over in order to make it a browser first game, including the game editor tool itself. Since this project grew too complicated, I decided to start over uisng all the lessons learned and ported the web based version of the game written in TypeScript and Phaser into a new project:

[https://github.com/mattjcamp/wilderstep_infinite_abyss](https://github.com/mattjcamp/wilderstep_infinite_abyss)

The data models have been refactored and the map/link system has been simplified to make things less error prone. And the game editor uses a React UI which is far better that the Python frontend which was primarily meant for games and not rich applications. The game and editor now work, but in order to provide a "dungeon master" experience for players I will need to set up a server infrastructure that can manage an API. We have a plan in place, but it's big feature so .... well, you know how that goes.

You can try the game (I have one short module ready named "The Dragon's Lair"). You can play with the editor, but there is no way to publish modules from your browser yet.

**[Try Wilderstep:Infinite Abyss](https://mattjcamp.github.io/wilderstep_infinite_abyss/)**

------


# Realm of Shadow

An Ultima III  and D&D inspired top-down, turn-based RPG built with TypeScript and Phaser. Lead a party of four adventurers through a procedurally generated world of overworld exploration, town visits, dungeon delving, and tactical grid combat.

[You can try Realm of Shadow by clicking here to play online.](https://mattjcamp.github.io/game_rpg_turn_based_open_world/) 

## Features

- Dungeons & Dragons inspired turn-based combat system
- Quest system
- Procedurally generated dungeons and intentionally crafted adventures
- Race and class system
- [1980s-style Player's Manual](docs/manuals/players_guide.pdf), [Adventure Map](docs/manuals/overview_map.png), and [Cloth Map](docs/manuals/cloth_map.png)
- Game is saved to your browser's local storage

---

<table>
<tr>
<td align="center"><img src="docs/blog/web_version/Screenshot 2026-05-12 at 3.57.13 PM.png" width="400" alt="Town exploration"></td>
<td align="center"><img src="docs/blog/web_version/Screenshot 2026-05-12 at 3.44.13 PM.png" width="400" alt="Overworld map"></td>
</tr>
<tr>
<td align="center"><img src="docs/blog/web_version/Screenshot 2026-05-12 at 3.45.26 PM.png" width="400" alt="Turn-based combat"></td>
<td align="center"><img src="docs/blog/web_version/Screenshot 2026-05-12 at 3.46.34 PM.png" width="400" alt="Dungeon delving"></td>
</tr>
<tr>
<td align="center"><img src="docs/blog/web_version/Screenshot 2026-05-12 at 3.47.34 PM.png" width="400" alt="Turn-based combat"></td>
<td align="center"><img src="docs/blog/web_version/Screenshot 2026-05-12 at 3.44.37 PM.png" width="400" alt="Dungeon delving"></td>
</tr>
</table>

