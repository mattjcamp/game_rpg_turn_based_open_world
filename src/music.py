"""
Chiptune sound effects system.

Generates retro square-wave / pulse-wave sound effects procedurally
using numpy and pygame.mixer.
"""

import numpy as np
import pygame

# ── Audio constants ─────────────────────────────────────────────
SAMPLE_RATE = 22050
MASTER_VOLUME = 0.16        # ambient background level


# ── Note frequency helpers ──────────────────────────────────────

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F",
               "F#", "G", "G#", "A", "A#", "B"]

def _note_freq(name, octave):
    """Return frequency in Hz for a note like ('C', 4) = middle C."""
    idx = _NOTE_NAMES.index(name)
    # A4 = 440 Hz is index 9 in octave 4
    semitones_from_a4 = (octave - 4) * 12 + (idx - 9)
    return 440.0 * (2.0 ** (semitones_from_a4 / 12.0))


def _n(note_str):
    """Shorthand: 'C4' -> freq.  'R' -> 0 (rest)."""
    if note_str == "R":
        return 0.0
    # Handle sharps like 'C#4'
    if len(note_str) == 3 and note_str[1] == '#':
        return _note_freq(note_str[:2], int(note_str[2]))
    return _note_freq(note_str[0], int(note_str[1]))


# ── Waveform generators ────────────────────────────────────────

def _square_wave(freq, duration, sample_rate=SAMPLE_RATE, duty=0.5):
    """Generate a square / pulse wave at the given frequency."""
    if freq <= 0:
        return np.zeros(int(sample_rate * duration), dtype=np.float32)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = np.where((t * freq) % 1.0 < duty, 1.0, -1.0).astype(np.float32)
    return wave


def _triangle_wave(freq, duration, sample_rate=SAMPLE_RATE):
    """Generate a triangle wave (softer bass sound)."""
    if freq <= 0:
        return np.zeros(int(sample_rate * duration), dtype=np.float32)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = 2.0 * np.abs(2.0 * ((t * freq) % 1.0) - 1.0) - 1.0
    return wave.astype(np.float32)


def _noise(duration, sample_rate=SAMPLE_RATE):
    """Generate white noise (for percussion)."""
    n_samples = int(sample_rate * duration)
    return (np.random.rand(n_samples).astype(np.float32) * 2.0 - 1.0)


def _envelope(wave, attack=0.01, release=0.05):
    """Apply a simple attack-release amplitude envelope."""
    n = len(wave)
    env = np.ones(n, dtype=np.float32)
    att_samples = min(int(attack * SAMPLE_RATE), n)
    rel_samples = min(int(release * SAMPLE_RATE), n)
    if att_samples > 0:
        env[:att_samples] = np.linspace(0, 1, att_samples)
    if rel_samples > 0:
        env[-rel_samples:] = np.linspace(1, 0, rel_samples)
    return wave * env


# ── Phrase / track builders ─────────────────────────────────────

def _render_melody(notes, note_dur, wave_fn=_square_wave, duty=0.5,
                   volume=0.25, attack=0.005, release=0.03):
    """Render a list of note strings into a single numpy array.

    notes: list of note strings like ['C4', 'E4', 'G4', 'R']
    note_dur: duration per note in seconds
    """
    parts = []
    for note_str in notes:
        freq = _n(note_str)
        if wave_fn == _square_wave:
            raw = wave_fn(freq, note_dur, duty=duty)
        else:
            raw = wave_fn(freq, note_dur)
        raw = _envelope(raw, attack=attack, release=release)
        parts.append(raw * volume)
    return np.concatenate(parts)


def _render_bass(notes, note_dur, volume=0.20):
    """Render a bass line using triangle waves."""
    return _render_melody(notes, note_dur, wave_fn=_triangle_wave,
                          volume=volume, attack=0.005, release=0.04)


def _render_drums(pattern, note_dur, volume=0.05):
    """Render a simple drum pattern.

    pattern: list of 'K' (kick), 'H' (hihat), 'S' (snare), 'R' (rest)
    """
    parts = []
    for hit in pattern:
        if hit == 'K':
            # Kick: short low-freq burst
            raw = _square_wave(55, note_dur * 0.3, duty=0.5)
            raw = _envelope(raw, attack=0.002, release=0.08)
            pad = np.zeros(int(SAMPLE_RATE * note_dur) - len(raw), dtype=np.float32)
            parts.append(np.concatenate([raw, pad]) * volume * 1.5)
        elif hit == 'H':
            raw = _noise(note_dur * 0.1)
            raw = _envelope(raw, attack=0.001, release=0.03)
            pad = np.zeros(int(SAMPLE_RATE * note_dur) - len(raw), dtype=np.float32)
            parts.append(np.concatenate([raw, pad]) * volume * 0.5)
        elif hit == 'S':
            raw = _noise(note_dur * 0.2)
            raw = _envelope(raw, attack=0.002, release=0.06)
            pad = np.zeros(int(SAMPLE_RATE * note_dur) - len(raw), dtype=np.float32)
            parts.append(np.concatenate([raw, pad]) * volume)
        else:
            parts.append(np.zeros(int(SAMPLE_RATE * note_dur), dtype=np.float32))
    return np.concatenate(parts)


def _mix_tracks(*tracks):
    """Mix multiple tracks together, padding shorter ones."""
    max_len = max(len(t) for t in tracks)
    result = np.zeros(max_len, dtype=np.float32)
    for t in tracks:
        result[:len(t)] += t
    # Clip to prevent distortion
    result = np.clip(result, -1.0, 1.0)
    return result


def _to_sound(wave):
    """Convert a float32 numpy array to a pygame.mixer.Sound."""
    # Scale to 16-bit integer range
    scaled = (wave * MASTER_VOLUME * 32767).astype(np.int16)
    return pygame.mixer.Sound(buffer=scaled.tobytes())



# ═══════════════════════════════════════════════════════════════
#  SOUND EFFECTS — chiptune-style combat SFX
# ═══════════════════════════════════════════════════════════════

def _sfx_sweep(start_freq, end_freq, duration, wave_fn=_square_wave,
               volume=0.30, duty=0.5):
    """Generate a frequency-sweep sound effect."""
    n_samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    freqs = np.linspace(start_freq, end_freq, n_samples)
    phase = np.cumsum(freqs / SAMPLE_RATE)
    if wave_fn == _square_wave:
        wave = np.where(phase % 1.0 < duty, 1.0, -1.0).astype(np.float32)
    else:
        wave = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    wave = _envelope(wave, attack=0.005, release=duration * 0.3)
    return wave * volume


def _gen_sfx_sword_hit():
    """Melee hit: short noise burst + descending tone."""
    burst = _noise(0.04) * 0.35
    burst = _envelope(burst, attack=0.002, release=0.02)
    tone = _sfx_sweep(600, 200, 0.10, volume=0.30)
    pad = np.zeros(int(SAMPLE_RATE * 0.02), dtype=np.float32)
    return np.concatenate([burst, pad, tone])


def _gen_sfx_miss():
    """Attack miss: quick rising whoosh."""
    whoosh = _noise(0.12) * 0.15
    whoosh = _envelope(whoosh, attack=0.005, release=0.08)
    tone = _sfx_sweep(200, 500, 0.08, volume=0.12)
    return _mix_tracks(whoosh, tone)


def _gen_sfx_critical():
    """Critical hit: sharp impact + rising fanfare."""
    impact = _noise(0.06) * 0.40
    impact = _envelope(impact, attack=0.001, release=0.03)
    tone1 = _sfx_sweep(400, 800, 0.08, volume=0.30)
    tone2 = _sfx_sweep(600, 1200, 0.08, volume=0.25)
    pad = np.zeros(int(SAMPLE_RATE * 0.03), dtype=np.float32)
    combined = np.concatenate([impact, pad, tone1])
    # Layer the second tone offset slightly
    result = np.zeros(len(combined) + len(tone2), dtype=np.float32)
    result[:len(combined)] += combined
    offset = len(impact) + len(pad) + int(SAMPLE_RATE * 0.03)
    result[offset:offset + len(tone2)] += tone2
    return np.clip(result, -1.0, 1.0)


def _gen_sfx_arrow():
    """Arrow/projectile fire: quick ascending whistle."""
    tone = _sfx_sweep(300, 900, 0.12, duty=0.25, volume=0.25)
    return tone


def _gen_sfx_fireball():
    """Fireball cast: rising roar with noise."""
    roar = _noise(0.25) * 0.20
    roar = _envelope(roar, attack=0.01, release=0.15)
    tone = _sfx_sweep(150, 600, 0.25, volume=0.25)
    return _mix_tracks(roar, tone)


def _gen_sfx_explosion():
    """Fireball explosion: loud noise burst + descending boom."""
    burst = _noise(0.15) * 0.40
    burst = _envelope(burst, attack=0.002, release=0.10)
    boom = _sfx_sweep(300, 50, 0.20, wave_fn=_triangle_wave, volume=0.35)
    return _mix_tracks(burst, boom)


def _gen_sfx_heal():
    """Heal spell: ascending arpeggio (gentle chime)."""
    notes = ['C5', 'E5', 'G5', 'C6']
    parts = []
    for n_str in notes:
        freq = _n(n_str)
        raw = _square_wave(freq, 0.08, duty=0.25)
        raw = _envelope(raw, attack=0.005, release=0.04)
        parts.append(raw * 0.20)
    return np.concatenate(parts)


def _gen_sfx_monster_hit():
    """Monster takes damage: thud + crunch."""
    thud = _triangle_wave(80, 0.06)
    thud = _envelope(thud, attack=0.002, release=0.04) * 0.35
    crunch = _noise(0.06) * 0.25
    crunch = _envelope(crunch, attack=0.002, release=0.04)
    return _mix_tracks(thud, crunch)


def _gen_sfx_player_hurt():
    """Player takes damage: descending tone + noise."""
    tone = _sfx_sweep(500, 150, 0.15, volume=0.25)
    hit = _noise(0.05) * 0.30
    hit = _envelope(hit, attack=0.002, release=0.03)
    result = np.zeros(len(tone), dtype=np.float32)
    result[:len(hit)] += hit
    result += tone
    return np.clip(result, -1.0, 1.0)


def _gen_sfx_victory():
    """Victory: triumphant ascending fanfare."""
    notes = ['C4', 'E4', 'G4', 'C5', 'E5', 'G5', 'C6']
    parts = []
    for n_str in notes:
        freq = _n(n_str)
        raw = _square_wave(freq, 0.10, duty=0.5)
        raw = _envelope(raw, attack=0.005, release=0.05)
        parts.append(raw * 0.25)
    return np.concatenate(parts)


def _gen_sfx_defeat():
    """Defeat: sad descending tones."""
    notes = ['C4', 'B3', 'A3', 'G3', 'F3', 'E3', 'D3', 'C3']
    parts = []
    for n_str in notes:
        freq = _n(n_str)
        raw = _triangle_wave(freq, 0.15)
        raw = _envelope(raw, attack=0.01, release=0.10)
        parts.append(raw * 0.25)
    return np.concatenate(parts)


def _gen_sfx_level_up():
    """Level up: bright ascending arpeggio with harmonics."""
    notes = ['C4', 'E4', 'G4', 'C5', 'E5', 'G5', 'C6']
    parts = []
    for i, n_str in enumerate(notes):
        freq = _n(n_str)
        raw = _square_wave(freq, 0.08, duty=0.25)
        raw = _envelope(raw, attack=0.003, release=0.04)
        parts.append(raw * 0.22)
    fanfare = np.concatenate(parts)
    # Add a bright final chord
    chord_dur = 0.25
    c = _square_wave(_n('C5'), chord_dur, duty=0.25) * 0.15
    e = _square_wave(_n('E5'), chord_dur, duty=0.25) * 0.12
    g = _square_wave(_n('G5'), chord_dur, duty=0.25) * 0.12
    chord = _envelope(_mix_tracks(c, e, g), attack=0.005, release=0.15)
    return np.concatenate([fanfare, chord])


def _gen_sfx_defend():
    """Defend stance: shield-like clang."""
    tone = _square_wave(800, 0.05, duty=0.5)
    tone = _envelope(tone, attack=0.001, release=0.03) * 0.25
    ring = _square_wave(1200, 0.10, duty=0.125)
    ring = _envelope(ring, attack=0.005, release=0.08) * 0.12
    return np.concatenate([tone, ring])


def _gen_sfx_flee():
    """Flee: quick descending run."""
    notes = ['G4', 'F4', 'E4', 'D4', 'C4']
    parts = []
    for n_str in notes:
        freq = _n(n_str)
        raw = _square_wave(freq, 0.06, duty=0.5)
        raw = _envelope(raw, attack=0.003, release=0.03)
        parts.append(raw * 0.20)
    return np.concatenate(parts)


def _gen_sfx_treasure():
    """Treasure chest opened: bright coin jingle + chime."""
    # Coin jingle — rapid high notes
    jingle_notes = ['E6', 'G6', 'E6', 'C6', 'E6', 'G6']
    parts = []
    for n_str in jingle_notes:
        freq = _n(n_str)
        raw = _square_wave(freq, 0.04, duty=0.25)
        raw = _envelope(raw, attack=0.002, release=0.02)
        parts.append(raw * 0.18)
    jingle = np.concatenate(parts)
    # Reward chime — bright chord
    chord_dur = 0.20
    c = _square_wave(_n('C5'), chord_dur, duty=0.25) * 0.15
    e = _square_wave(_n('E5'), chord_dur, duty=0.25) * 0.12
    g = _square_wave(_n('G5'), chord_dur, duty=0.25) * 0.12
    chord = _envelope(_mix_tracks(c, e, g), attack=0.005, release=0.12)
    return np.concatenate([jingle, chord])


def _gen_sfx_encounter():
    """Monster encounter: alarming descending stinger."""
    # Sharp alert tone
    alert = _square_wave(900, 0.06, duty=0.5)
    alert = _envelope(alert, attack=0.001, release=0.03) * 0.30
    # Descending menacing sweep
    sweep = _sfx_sweep(700, 200, 0.18, volume=0.25)
    # Noise burst for tension
    burst = _noise(0.08) * 0.20
    burst = _envelope(burst, attack=0.002, release=0.05)
    pad = np.zeros(int(SAMPLE_RATE * 0.02), dtype=np.float32)
    combined = np.concatenate([alert, pad, sweep])
    result = np.zeros(len(combined), dtype=np.float32)
    result[:len(combined)] += combined
    result[:len(burst)] += burst
    return np.clip(result, -1.0, 1.0)


def _gen_sfx_trap():
    """Trap sprung: sharp snap + descending dissonant screech."""
    # Sharp snap
    snap = _noise(0.04) * 0.45
    snap = _envelope(snap, attack=0.001, release=0.02)
    # Dissonant descending screech
    screech1 = _sfx_sweep(1100, 300, 0.20, duty=0.5, volume=0.25)
    screech2 = _sfx_sweep(900, 200, 0.20, duty=0.25, volume=0.20)
    screech = _mix_tracks(screech1, screech2)
    # Low rumble
    rumble = _triangle_wave(60, 0.15)
    rumble = _envelope(rumble, attack=0.01, release=0.10) * 0.25
    pad = np.zeros(int(SAMPLE_RATE * 0.02), dtype=np.float32)
    combined = np.concatenate([snap, pad, screech])
    result = np.zeros(len(combined), dtype=np.float32)
    result[:len(combined)] += combined
    result[:len(rumble)] += rumble
    return np.clip(result, -1.0, 1.0)


def _gen_sfx_lock_pick_success():
    """Lock picked successfully: metallic clicks ascending to a satisfying clunk."""
    clicks = []
    for freq in [800, 1000, 1200, 1500]:
        click = _square_wave(freq, 0.03, duty=0.125)
        click = _envelope(click, attack=0.001, release=0.02) * 0.20
        clicks.append(click)
        clicks.append(np.zeros(int(SAMPLE_RATE * 0.04), dtype=np.float32))
    # Final satisfying clunk
    clunk = _triangle_wave(200, 0.08)
    clunk = _envelope(clunk, attack=0.002, release=0.05) * 0.30
    return np.concatenate(clicks + [clunk])


def _gen_sfx_lock_pick_fail():
    """Lock pick failed: metallic scrape + dull thud."""
    scrape = _noise(0.08) * 0.20
    scrape = _envelope(scrape, attack=0.005, release=0.05)
    tone = _sfx_sweep(600, 300, 0.08, duty=0.125, volume=0.15)
    thud = _triangle_wave(100, 0.06)
    thud = _envelope(thud, attack=0.002, release=0.04) * 0.25
    pad = np.zeros(int(SAMPLE_RATE * 0.03), dtype=np.float32)
    return np.concatenate([_mix_tracks(scrape, tone), pad, thud])


def _gen_sfx_shield():
    """Shield spell: crystalline ascending shimmer + bright chime."""
    # Ascending shimmer — three rising tones
    notes = ['C5', 'E5', 'G5']
    parts = []
    for n_str in notes:
        freq = _n(n_str)
        raw = _triangle_wave(freq, 0.08)
        raw = _envelope(raw, attack=0.005, release=0.05)
        parts.append(raw * 0.18)
    shimmer = np.concatenate(parts)
    # Bright chime at the end
    chime = _triangle_wave(_n('C6'), 0.15)
    chime = _envelope(chime, attack=0.005, release=0.12) * 0.15
    # Harmonic overlay
    overlay = _triangle_wave(_n('E6'), 0.12)
    overlay = _envelope(overlay, attack=0.01, release=0.10) * 0.10
    return np.concatenate([shimmer, _mix_tracks(chime, overlay)])


def _gen_sfx_turn_undead():
    """Turn Undead: majestic holy chord building to a bright blast."""
    # Low holy drone — organ-like chord (C4 + E4 + G4)
    dur = 0.18
    c4 = _triangle_wave(_n('C4'), dur) * 0.12
    e4 = _triangle_wave(_n('E4'), dur) * 0.10
    g4 = _triangle_wave(_n('G4'), dur) * 0.10
    chord = _mix_tracks(_mix_tracks(c4, e4), g4)
    chord = _envelope(chord, attack=0.01, release=0.12)
    # Rising holy sweep — ascending from C5 to C6
    sweep = _sfx_sweep(_n('C5'), _n('C6'), 0.15, duty=0.25, volume=0.15)
    sweep = _envelope(sweep, attack=0.01, release=0.10)
    # Bright burst — high octave chord (C6 + E6 + G6)
    burst_dur = 0.20
    c6 = _triangle_wave(_n('C6'), burst_dur) * 0.14
    e6 = _triangle_wave(_n('E6'), burst_dur) * 0.12
    g6 = _triangle_wave(_n('G6'), burst_dur) * 0.10
    burst = _mix_tracks(_mix_tracks(c6, e6), g6)
    burst = _envelope(burst, attack=0.005, release=0.15)
    # Noise crackle for the blast impact
    crackle = _noise(0.08) * 0.08
    crackle = _envelope(crackle, attack=0.002, release=0.06)
    return np.concatenate([chord, sweep, _mix_tracks(burst, crackle)])


def _gen_sfx_quest_complete():
    """Triumphant fanfare — ascending arpeggio with sustain chord."""
    # Rising arpeggio: C4 → E4 → G4 → C5 → E5
    notes = ['C4', 'E4', 'G4', 'C5', 'E5']
    arp = _render_melody(notes, 0.12, _square_wave, duty=0.25,
                         volume=0.25, attack=0.005, release=0.08)
    # Sustain chord: C5 + E5 + G5 (triumphant major chord)
    chord_dur = 0.5
    c5 = _square_wave(_n('C5'), chord_dur, duty=0.25) * 0.20
    e5 = _square_wave(_n('E5'), chord_dur, duty=0.25) * 0.18
    g5 = _square_wave(_n('G5'), chord_dur, duty=0.25) * 0.16
    chord = _mix_tracks(_mix_tracks(c5, e5), g5)
    chord = _envelope(chord, attack=0.02, release=0.25)
    # Shimmering high octave
    shimmer = _triangle_wave(_n('C6'), 0.3) * 0.10
    shimmer = _envelope(shimmer, attack=0.01, release=0.20)
    return np.concatenate([arp, _mix_tracks(chord, shimmer)])


def _gen_sfx_chirp():
    """Item pickup chirp: quick ascending two-note bleep."""
    n1 = _square_wave(_n('E5'), 0.05, duty=0.25) * 0.18
    n1 = _envelope(n1, attack=0.002, release=0.03)
    n2 = _square_wave(_n('A5'), 0.07, duty=0.25) * 0.18
    n2 = _envelope(n2, attack=0.002, release=0.04)
    return np.concatenate([n1, n2])


class SoundEffects:
    """Manages chiptune combat sound effects."""

    _SFX_GENERATORS = {
        "sword_hit":    _gen_sfx_sword_hit,
        "miss":         _gen_sfx_miss,
        "critical":     _gen_sfx_critical,
        "arrow":        _gen_sfx_arrow,
        "fireball":     _gen_sfx_fireball,
        "explosion":    _gen_sfx_explosion,
        "heal":         _gen_sfx_heal,
        "monster_hit":  _gen_sfx_monster_hit,
        "player_hurt":  _gen_sfx_player_hurt,
        "victory":      _gen_sfx_victory,
        "defeat":       _gen_sfx_defeat,
        "level_up":     _gen_sfx_level_up,
        "defend":       _gen_sfx_defend,
        "flee":         _gen_sfx_flee,
        "treasure":     _gen_sfx_treasure,
        "encounter":    _gen_sfx_encounter,
        "trap":         _gen_sfx_trap,
        "lock_pick_success": _gen_sfx_lock_pick_success,
        "lock_pick_fail":    _gen_sfx_lock_pick_fail,
        "shield":            _gen_sfx_shield,
        "turn_undead":       _gen_sfx_turn_undead,
        "quest_complete":    _gen_sfx_quest_complete,
        "chirp":             _gen_sfx_chirp,
    }

    def __init__(self):
        """Pre-generate all sound effects."""
        self._sounds = {}
        self._muted = False
        for name, gen_fn in self._SFX_GENERATORS.items():
            wave = gen_fn()
            self._sounds[name] = _to_sound(wave)

    def play(self, sfx_name):
        """Play a sound effect by name. Silently ignores unknown names."""
        if self._muted:
            return
        sound = self._sounds.get(sfx_name)
        if sound:
            sound.play()

    @property
    def muted(self):
        return self._muted

    @muted.setter
    def muted(self, value):
        self._muted = value
