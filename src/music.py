"""
Ultima III-style chiptune music system.

Generates retro square-wave / pulse-wave music procedurally using numpy
and pygame.mixer. Each game state gets its own looping track composed
of period-appropriate melodic phrases, arpeggios, and bass lines.
"""

import numpy as np
import pygame

# ── Audio constants ─────────────────────────────────────────────
SAMPLE_RATE = 22050
MASTER_VOLUME = 0.25        # keep chiptune from being ear-piercing


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
                   volume=0.35, attack=0.005, release=0.03):
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


def _render_bass(notes, note_dur, volume=0.30):
    """Render a bass line using triangle waves."""
    return _render_melody(notes, note_dur, wave_fn=_triangle_wave,
                          volume=volume, attack=0.005, release=0.04)


def _render_drums(pattern, note_dur, volume=0.12):
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
#  TRACK COMPOSITIONS
# ═══════════════════════════════════════════════════════════════

def _compose_overworld():
    """Heroic overworld march — bright, adventurous feel."""
    bpm = 140
    note_dur = 60.0 / bpm

    # Melody: heroic fanfare-like phrase (2 repeats of a 16-note phrase)
    phrase_a = [
        'C4', 'C4', 'G4', 'G4', 'A4', 'A4', 'G4', 'R',
        'F4', 'F4', 'E4', 'E4', 'D4', 'D4', 'C4', 'R',
    ]
    phrase_b = [
        'C4', 'D4', 'E4', 'F4', 'G4', 'A4', 'G4', 'E4',
        'F4', 'E4', 'D4', 'C4', 'D4', 'E4', 'C4', 'R',
    ]
    melody_notes = phrase_a + phrase_b + phrase_a + phrase_b

    # Bass: root notes following the harmony
    bass_phrase_a = [
        'C2', 'C2', 'C2', 'C2', 'F2', 'F2', 'C2', 'C2',
        'F2', 'F2', 'C2', 'C2', 'G2', 'G2', 'C2', 'C2',
    ]
    bass_phrase_b = [
        'C2', 'C2', 'E2', 'E2', 'G2', 'G2', 'E2', 'E2',
        'F2', 'F2', 'G2', 'G2', 'G2', 'G2', 'C2', 'C2',
    ]
    bass_notes = bass_phrase_a + bass_phrase_b + bass_phrase_a + bass_phrase_b

    # Counter-melody: arpeggiated harmony line
    counter_a = [
        'E5', 'R', 'E5', 'R', 'F5', 'R', 'E5', 'R',
        'A4', 'R', 'G4', 'R', 'F4', 'R', 'E4', 'R',
    ]
    counter_b = [
        'G5', 'R', 'G5', 'R', 'E5', 'R', 'C5', 'R',
        'A4', 'R', 'B4', 'R', 'C5', 'R', 'E5', 'R',
    ]
    counter_notes = counter_a + counter_b + counter_a + counter_b

    # Drums
    drum_bar = ['K', 'H', 'S', 'H'] * 4
    drum_pattern = drum_bar * 4

    melody = _render_melody(melody_notes, note_dur, duty=0.5, volume=0.30)
    counter = _render_melody(counter_notes, note_dur, duty=0.25, volume=0.15)
    bass = _render_bass(bass_notes, note_dur, volume=0.25)
    drums = _render_drums(drum_pattern, note_dur, volume=0.10)

    return _mix_tracks(melody, counter, bass, drums)


def _compose_town():
    """Peaceful town theme — gentle, lilting waltz feel."""
    bpm = 110
    note_dur = 60.0 / bpm

    # Melody: gentle folk tune
    phrase_a = [
        'E4', 'G4', 'A4', 'G4', 'E4', 'D4', 'C4', 'R',
        'D4', 'F4', 'G4', 'F4', 'D4', 'C4', 'D4', 'R',
    ]
    phrase_b = [
        'E4', 'G4', 'C5', 'B4', 'A4', 'G4', 'A4', 'R',
        'G4', 'F4', 'E4', 'D4', 'E4', 'G4', 'E4', 'R',
    ]
    melody_notes = phrase_a + phrase_b + phrase_a + phrase_b

    # Bass: simple root movement
    bass_phrase = [
        'C3', 'R', 'G2', 'R', 'C3', 'R', 'C3', 'R',
        'D3', 'R', 'G2', 'R', 'D3', 'R', 'G2', 'R',
    ]
    bass_notes = bass_phrase * 4

    # Light arpeggio harmony
    arp_a = [
        'C5', 'E5', 'G5', 'E5', 'C5', 'R', 'R', 'R',
        'D5', 'F5', 'A5', 'F5', 'D5', 'R', 'R', 'R',
    ]
    arp_b = [
        'E5', 'G5', 'C6', 'G5', 'E5', 'R', 'R', 'R',
        'G5', 'R', 'E5', 'R', 'C5', 'R', 'R', 'R',
    ]
    arp_notes = arp_a + arp_b + arp_a + arp_b

    melody = _render_melody(melody_notes, note_dur, duty=0.25, volume=0.28)
    arp = _render_melody(arp_notes, note_dur, duty=0.125, volume=0.12)
    bass = _render_bass(bass_notes, note_dur, volume=0.20)

    return _mix_tracks(melody, arp, bass)


def _compose_dungeon():
    """Dark dungeon theme — ominous minor key, slow and tense."""
    bpm = 85
    note_dur = 60.0 / bpm

    # Melody: creepy minor-key phrases
    phrase_a = [
        'A3', 'R', 'C4', 'R', 'B3', 'R', 'A3', 'R',
        'E3', 'R', 'F3', 'R', 'E3', 'R', 'R', 'R',
    ]
    phrase_b = [
        'A3', 'R', 'E4', 'R', 'D4', 'R', 'C4', 'B3',
        'A3', 'R', 'G#3', 'R', 'A3', 'R', 'R', 'R',
    ]
    melody_notes = phrase_a + phrase_b + phrase_a + phrase_b

    # Droning bass
    bass_notes = [
        'A1', 'A1', 'A1', 'A1', 'A1', 'A1', 'A1', 'A1',
        'E1', 'E1', 'E1', 'E1', 'E1', 'E1', 'E1', 'E1',
    ] * 4

    # Eerie high arpeggios
    eerie_a = [
        'R', 'E5', 'R', 'R', 'R', 'C5', 'R', 'R',
        'R', 'R', 'B4', 'R', 'R', 'R', 'A4', 'R',
    ]
    eerie_b = [
        'R', 'R', 'E5', 'R', 'R', 'R', 'R', 'D5',
        'R', 'R', 'R', 'C5', 'R', 'R', 'R', 'R',
    ]
    eerie_notes = eerie_a + eerie_b + eerie_a + eerie_b

    # Sparse percussion
    drum_bar = ['R', 'R', 'R', 'H', 'R', 'R', 'K', 'R'] * 2
    drum_pattern = drum_bar * 4

    melody = _render_melody(melody_notes, note_dur, duty=0.5, volume=0.25,
                            attack=0.02, release=0.08)
    eerie = _render_melody(eerie_notes, note_dur, duty=0.125, volume=0.10,
                           attack=0.03, release=0.15)
    bass = _render_bass(bass_notes, note_dur, volume=0.22)
    drums = _render_drums(drum_pattern, note_dur, volume=0.06)

    return _mix_tracks(melody, eerie, bass, drums)


def _compose_combat():
    """Intense combat music — fast, driving, urgent."""
    bpm = 170
    note_dur = 60.0 / bpm

    # Melody: aggressive, punchy
    phrase_a = [
        'A4', 'A4', 'C5', 'A4', 'E4', 'E4', 'A4', 'R',
        'G4', 'G4', 'A4', 'G4', 'E4', 'D4', 'E4', 'R',
    ]
    phrase_b = [
        'A4', 'C5', 'D5', 'E5', 'D5', 'C5', 'A4', 'R',
        'G4', 'A4', 'G4', 'E4', 'D4', 'E4', 'A4', 'R',
    ]
    melody_notes = (phrase_a + phrase_b) * 2

    # Driving bass
    bass_a = [
        'A2', 'R', 'A2', 'R', 'A2', 'R', 'A2', 'R',
        'G2', 'R', 'G2', 'R', 'E2', 'R', 'E2', 'R',
    ]
    bass_b = [
        'A2', 'R', 'C3', 'R', 'D3', 'R', 'E3', 'R',
        'D3', 'R', 'C3', 'R', 'A2', 'R', 'A2', 'R',
    ]
    bass_notes = (bass_a + bass_b) * 2

    # Fast drums
    drum_bar = ['K', 'H', 'K', 'H', 'S', 'H', 'K', 'H'] * 2
    drum_pattern = drum_bar * 4

    melody = _render_melody(melody_notes, note_dur, duty=0.5, volume=0.30)
    bass = _render_bass(bass_notes, note_dur, volume=0.28)
    drums = _render_drums(drum_pattern, note_dur, volume=0.12)

    return _mix_tracks(melody, bass, drums)


# ═══════════════════════════════════════════════════════════════
#  PUBLIC API — MusicManager
# ═══════════════════════════════════════════════════════════════

class MusicManager:
    """Manages procedurally-generated chiptune music for each game state."""

    # Map state names to composer functions
    _COMPOSERS = {
        "overworld": _compose_overworld,
        "town":      _compose_town,
        "dungeon":   _compose_dungeon,
        "combat":    _compose_combat,
    }

    def __init__(self):
        """Initialize the mixer and pre-generate all tracks."""
        # Ensure mixer is initialized with our sample rate (mono, 16-bit)
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1,
                              buffer=1024)

        self._sounds = {}      # track_name -> pygame.mixer.Sound
        self._channel = None   # dedicated channel for music
        self._current = None   # name of currently playing track
        self._muted = False

        # Pre-generate all music tracks
        for name, composer in self._COMPOSERS.items():
            wave = composer()
            self._sounds[name] = _to_sound(wave)

        # Reserve a channel for music playback
        # Use last channel so game SFX can use the others
        num_channels = pygame.mixer.get_num_channels()
        if num_channels < 2:
            pygame.mixer.set_num_channels(4)
        self._channel = pygame.mixer.Channel(
            pygame.mixer.get_num_channels() - 1)

    def play(self, track_name, fade_ms=500):
        """Start playing a track, looping forever. Fades the old track out."""
        if self._muted:
            self._current = track_name
            return
        if track_name == self._current and self._channel.get_busy():
            return  # already playing this track

        sound = self._sounds.get(track_name)
        if not sound:
            return

        if self._channel.get_busy():
            self._channel.fadeout(fade_ms)
            # Small delay not needed — fadeout is non-blocking, new play
            # will queue after fade automatically via pygame

        self._channel.play(sound, loops=-1, fade_ms=fade_ms)
        self._current = track_name

    def stop(self, fade_ms=500):
        """Stop any currently playing music."""
        if self._channel and self._channel.get_busy():
            self._channel.fadeout(fade_ms)
        self._current = None

    def toggle_mute(self):
        """Toggle music on/off. Returns new muted state."""
        self._muted = not self._muted
        if self._muted:
            if self._channel:
                self._channel.fadeout(300)
        else:
            # Resume the current track
            if self._current:
                sound = self._sounds.get(self._current)
                if sound:
                    self._channel.play(sound, loops=-1, fade_ms=300)
        return self._muted

    @property
    def is_muted(self):
        return self._muted
