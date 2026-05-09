/**
 * Background music manager — area-keyed looping tracks with crossfade.
 *
 * Stripped-down port of `src/music.py::MusicManager`. The Python version
 * scans `data/soundtrack/<area>/` directories and shuffles the playlist
 * for each area; the web port deliberately ships at most a handful of
 * tracks (one per area, two for the overworld) and loops a single
 * picked track per area until the player crosses into a new state. No
 * shuffle queue, no end-of-track event handling — `<audio>.loop = true`
 * does the looping for us.
 *
 * Design notes:
 *
 *   - **Lazy loading.** We don't preload any audio at module-load. The
 *     first `playArea(name)` call for a given area constructs the
 *     `<audio>` element pointing at the asset URL; the browser streams
 *     it on demand. A player who never enters a dungeon never pays the
 *     dungeon track's bytes.
 *
 *   - **Crossfade.** Switching areas fades the previous track out
 *     while the new one fades in over 1.5s. Implemented with a CSS-
 *     style requestAnimationFrame ramp on the HTMLAudioElement's
 *     `volume` property — the Web Audio API would give finer control
 *     but doesn't add much value for two-track crossfades and means
 *     fighting a separate AudioContext.
 *
 *   - **Autoplay gate.** Browsers refuse `audio.play()` until the page
 *     has seen a user gesture. We try anyway — if `play()` rejects,
 *     we install a one-shot capture-phase listener that will retry on
 *     the next pointer/key/touch event. This matches the title
 *     screen's "Press any key to start" flow naturally: the first key
 *     press both starts the game AND unlocks audio.
 *
 *   - **Mute.** Toggle persists to localStorage so refreshes remember
 *     it. Mirrors the Sfx module's mute behaviour exactly.
 *
 *   - **Volume.** Master volume scales every track. Defaults to 0.5
 *     (the Python game's default) so music sits below SFX.
 *
 * Public API:
 *   Music.playArea("overworld" | "town" | "dungeon" | "combat")
 *   Music.stop(fadeMs?)
 *   Music.setMuted(bool)         — persists to localStorage
 *   Music.muted                  — current state
 *   Music.setVolume(0..1)        — persists to localStorage
 *   Music.volume                 — current state
 */

import { withBase } from "../world/Module";

const MUTED_KEY  = "rpg.music.muted";
const VOLUME_KEY = "rpg.music.volume";

/**
 * Catalog of available tracks, keyed by area. Each entry is a list
 * of `/audio/...` paths the manager picks from on first entry. The
 * pick is RANDOM so a player who walks back into the overworld has
 * a chance of hearing the second track this session — no shuffle
 * queue or playlist memory beyond that. One-track areas trivially
 * always pick the same track.
 *
 * If you add or replace tracks: drop new MP3s into
 * `web/public/audio/<area>/`, list them here, and they're live —
 * no build step.
 */
export const MUSIC_TRACKS: Record<string, string[]> = {
  overworld: [
    "/audio/overworld/scepter_of_the_celestial_guardian.mp3",
    "/audio/overworld/aurelian_overture.mp3",
  ],
  town: [
    "/audio/town/bards_ballad.mp3",
  ],
  dungeon: [
    "/audio/dungeon/lost_in_the_labyrinth.mp3",
  ],
  combat: [
    "/audio/combat/winds_of_destiny.mp3",
  ],
};

export type MusicArea = keyof typeof MUSIC_TRACKS;

const DEFAULT_VOLUME = 0.5;
const CROSSFADE_MS   = 1500;
const FADE_OUT_MS    = 1000;

/** Read the persisted mute / volume state, with localStorage-safe defaults. */
function readMuted(): boolean {
  if (typeof localStorage === "undefined") return false;
  return localStorage.getItem(MUTED_KEY) === "1";
}
function readVolume(): number {
  if (typeof localStorage === "undefined") return DEFAULT_VOLUME;
  const raw = localStorage.getItem(VOLUME_KEY);
  if (raw == null) return DEFAULT_VOLUME;
  const v = Number.parseFloat(raw);
  if (!Number.isFinite(v)) return DEFAULT_VOLUME;
  return Math.max(0, Math.min(1, v));
}

let _muted = readMuted();
let _volume = readVolume();

/** Currently playing area, or null when nothing's been started. */
let _currentArea: MusicArea | null = null;
/** Audio element for the currently playing track. */
let _currentEl: HTMLAudioElement | null = null;
/**
 * Pending unlock listener — installed when an autoplay attempt was
 * blocked, fires once on the next user gesture and then removes
 * itself. Non-null while audio is locked.
 */
let _unlockListener: (() => void) | null = null;

/** Pick a random URL for an area. Returns null when the area has no tracks. */
function pickTrack(area: MusicArea): string | null {
  const tracks = MUSIC_TRACKS[area];
  if (!tracks || tracks.length === 0) return null;
  const idx = Math.floor(Math.random() * tracks.length);
  return tracks[idx] ?? tracks[0] ?? null;
}

/**
 * Construct an HTMLAudioElement for `url`, looped, paused, with
 * volume 0 so the caller can fade it in cleanly. Returns null when
 * we're running outside a browser (server render / unit tests).
 */
function buildAudio(url: string): HTMLAudioElement | null {
  if (typeof window === "undefined" || typeof Audio === "undefined") return null;
  const el = new Audio(withBase(url));
  el.loop = true;
  el.volume = 0;
  // `preload="auto"` lets the browser start fetching as soon as the
  // element is created, rather than waiting for `play()`. Combined
  // with our crossfade, this means the first audible note arrives
  // pretty close to the moment the area changes.
  el.preload = "auto";
  return el;
}

/**
 * RAF-driven volume ramp from `el.volume` → `target` over `durationMs`.
 * Resolves once the ramp completes (or the element is replaced).
 */
function fadeVolume(el: HTMLAudioElement, target: number, durationMs: number): Promise<void> {
  return new Promise((resolve) => {
    const from = el.volume;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const v = from + (target - from) * t;
      // Element may have been swapped out from under us by a faster
      // area transition; bail without further ramping.
      el.volume = Math.max(0, Math.min(1, v));
      if (t < 1) {
        requestAnimationFrame(step);
      } else {
        resolve();
      }
    };
    requestAnimationFrame(step);
  });
}

/**
 * Try to start `el`, falling back to a "wait for the next user
 * gesture" listener when the browser's autoplay policy rejects the
 * call. Resolves once the element actually starts (or the listener
 * fires).
 */
function startWhenAllowed(el: HTMLAudioElement): void {
  const attempt = () => el.play();
  const result = attempt();
  if (typeof result?.then !== "function") return;
  result.catch(() => {
    // Autoplay blocked — install a one-shot listener on the document
    // that will retry on the next user gesture. capture: true so we
    // catch events even when an inner element calls
    // stopPropagation. once: true cleans up automatically.
    if (typeof document === "undefined") return;
    if (_unlockListener) return;
    const unlock = () => {
      _unlockListener = null;
      // The current track may have changed by the time the user
      // clicks (e.g. they immediately enter a town). Always start
      // whatever's CURRENTLY assigned, not the el captured at the
      // time the listener was installed.
      const live = _currentEl;
      if (live) {
        live.play().catch(() => {
          /* still blocked — give up; user can press play in browser UI */
        });
      }
    };
    _unlockListener = unlock;
    const opts = { once: true, capture: true } as AddEventListenerOptions;
    document.addEventListener("pointerdown", unlock, opts);
    document.addEventListener("keydown",     unlock, opts);
    document.addEventListener("touchstart",  unlock, opts);
  });
}

/** Effective playback volume — multiplies the master by mute state. */
function effectiveVolume(): number {
  return _muted ? 0 : _volume;
}

/**
 * Start the playlist for `area`. No-op when we're already playing
 * the same area's track (so re-entering the overworld doesn't
 * restart the song mid-bar).
 *
 * Crossfades when switching: the previous element fades to 0 over
 * `CROSSFADE_MS` and is then paused/torn down; the new element fades
 * from 0 → effective volume over the same window. Both ramps run
 * concurrently so there's no audio gap.
 */
export function playArea(area: MusicArea): void {
  if (_currentArea === area && _currentEl) return;
  const url = pickTrack(area);
  if (!url) return;
  const next = buildAudio(url);
  if (!next) return;

  const prev = _currentEl;
  _currentArea = area;
  _currentEl = next;

  // Kick the new element off (autoplay-aware) and ramp it in.
  startWhenAllowed(next);
  void fadeVolume(next, effectiveVolume(), CROSSFADE_MS);

  if (prev) {
    void fadeVolume(prev, 0, CROSSFADE_MS).then(() => {
      try { prev.pause(); } catch { /* ignore */ }
      // Drop the src so the browser GCs the buffered audio.
      try { prev.removeAttribute("src"); prev.load(); } catch { /* ignore */ }
    });
  }
}

/** Fade the current track out and stop. Safe to call when nothing's playing. */
export function stop(fadeMs = FADE_OUT_MS): void {
  const prev = _currentEl;
  _currentArea = null;
  _currentEl = null;
  if (!prev) return;
  void fadeVolume(prev, 0, fadeMs).then(() => {
    try { prev.pause(); } catch { /* ignore */ }
  });
}

/**
 * Set or clear the global mute. Persisted to localStorage so a
 * refresh remembers the player's preference. While muted, the
 * currently playing element's volume is set to 0 directly (no fade)
 * so the toggle feels instant.
 */
export function setMuted(value: boolean): void {
  _muted = !!value;
  if (typeof localStorage !== "undefined") {
    try { localStorage.setItem(MUTED_KEY, _muted ? "1" : "0"); } catch { /* ignore */ }
  }
  if (_currentEl) _currentEl.volume = effectiveVolume();
}

/**
 * Set the master music volume in [0, 1]. Persisted. Updates the
 * currently playing element immediately (clamped via effective
 * volume so flipping mute later still works).
 */
export function setVolume(value: number): void {
  if (!Number.isFinite(value)) return;
  _volume = Math.max(0, Math.min(1, value));
  if (typeof localStorage !== "undefined") {
    try { localStorage.setItem(VOLUME_KEY, String(_volume)); } catch { /* ignore */ }
  }
  if (_currentEl) _currentEl.volume = effectiveVolume();
}

/** Public read-only view of the manager state. */
export const Music = {
  playArea,
  stop,
  setMuted,
  setVolume,
  get muted(): boolean { return _muted; },
  get volume(): number { return _volume; },
  get currentArea(): MusicArea | null { return _currentArea; },
};

/**
 * Test-only reset: tear down any current element + clear listeners
 * so each unit test starts from a clean slate. Doesn't touch
 * localStorage — `_muted`/`_volume` are re-read from the same
 * variables each call, but tests can override via `setMuted` /
 * `setVolume`.
 */
export function _resetMusic(): void {
  if (_currentEl) {
    try { _currentEl.pause(); } catch { /* ignore */ }
  }
  _currentEl = null;
  _currentArea = null;
  _unlockListener = null;
}
