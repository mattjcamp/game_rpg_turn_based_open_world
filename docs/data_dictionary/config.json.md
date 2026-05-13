# config.json

## Purpose

Was intended as the runtime flags file — debug toggles, music settings, starting conditions, active module path. **In the canonical TypeScript build it is entirely dead**: every flag is reimplemented as a hardcoded constant in TS source. The file is kept around as a hold-over from the legacy Python game.

## Location

`data/config.json` (the byte-identical copy served by the web build is `web/public/data/config.json`)

## Scope of this document

The "Used?" column reflects the TypeScript + Phaser implementation under `web/` only. Every field is currently `No`. The file is documented here for completeness and because the keys describe authoring intent that may be revived.

## File shape

Flat singleton object — no records, no nesting. Every top-level key is an independent scalar.

## Fields

| Field | Type | Description | Used in web/? |
|---|---|---|---|
| `smite_enabled` | bool | Intended to gate the Shift+K "smite all enemies" debug cheat | **No** — TS uses a hardcoded `SMITE_ALL_CHEAT = true` constant at `CombatScene.ts:182` |
| `start_with_equipment` | bool | Whether new parties spawn already kitted out | **No** |
| `dm_mode` | bool | Dungeon-master / debug overlays toggle | **No** |
| `active_module_path` | string | Filesystem path to the active module (legacy Python pathing) | **No** — TS hardcodes `ACTIVE_MODULE = "the_dragon_of_dagorn"` at `Module.ts:19` |
| `music_enabled` | bool | Master music toggle | **No** |
| `soundtrack_style` | string | Music style preset (e.g. `"Classic"`) | **No** |
| `start_level` | int | Starting character level for a new party | **No** |
| `music_muted` | bool | Mute flag | **No** |
| `quest_monsters_only` | bool | Restrict overworld spawns to quest targets | **No** |
| `music_volume` | number (0–1) | Music volume | **No** |

## Cross-references to other JSON files

`active_module_path` once pointed at a path under `modules/`, but the TS port hardcodes the active module instead. No live linkage.

## Example record

The entire file:

```json
{
  "smite_enabled": false,
  "start_with_equipment": true,
  "dm_mode": false,
  "active_module_path": "/Users/.../modules/the_dragon_of_dagorn",
  "music_enabled": true,
  "soundtrack_style": "Classic",
  "start_level": 1,
  "music_muted": false,
  "quest_monsters_only": false,
  "music_volume": 0.5
}
```

## Notes and open questions

This file is the clearest candidate for either deletion or full revival. The flags express real authoring intent (debug toggles, music preferences, starting conditions) that would be reasonable to expose as user settings — but currently none of them work. Options:

- Delete the file and the corresponding `web/public/data/config.json` copy.
- Wire each flag to its hardcoded counterpart in TS (the most useful targets are `smite_enabled` → `SMITE_ALL_CHEAT`, `music_enabled` / `music_muted` / `music_volume` → the music system, `dm_mode` → debug overlays).
- Repurpose the file as a settings file driven by a UI panel.

Until one of those happens, treat this file as documentation of intent, not as runtime configuration.
