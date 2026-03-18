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
#  TRACK COMPOSITIONS
# ═══════════════════════════════════════════════════════════════

def _compose_title():
    """Mysterious, majestic title screen theme — sets the tone for adventure."""
    bpm = 65
    note_dur = 60.0 / bpm

    # Slow, haunting melody — minor key with rising hope
    melody_a = [
        'R', 'R', 'R', 'R',
        'E4', 'R', 'E4', 'F4', 'G4', 'R', 'G4', 'A4',
        'B4', 'R', 'B4', 'A4', 'G4', 'R', 'R', 'R',
        'A4', 'R', 'A4', 'G4', 'F4', 'R', 'E4', 'R',
    ]
    melody_b = [
        'R', 'R', 'R', 'R',
        'C5', 'R', 'B4', 'A4', 'G4', 'R', 'A4', 'B4',
        'C5', 'R', 'D5', 'C5', 'B4', 'R', 'A4', 'R',
        'G4', 'R', 'A4', 'G4', 'E4', 'R', 'R', 'R',
    ]
    melody_notes = melody_a + melody_b

    # Deep bass — pedal tones, slow and ominous
    bass_a = [
        'E2', 'E2', 'E2', 'E2',
        'E2', 'E2', 'E2', 'E2', 'C2', 'C2', 'C2', 'C2',
        'G2', 'G2', 'G2', 'G2', 'E2', 'E2', 'E2', 'E2',
        'A2', 'A2', 'A2', 'A2', 'B2', 'B2', 'E2', 'E2',
    ]
    bass_b = [
        'C2', 'C2', 'C2', 'C2',
        'C2', 'C2', 'C2', 'C2', 'G2', 'G2', 'G2', 'G2',
        'A2', 'A2', 'A2', 'A2', 'F2', 'F2', 'F2', 'F2',
        'E2', 'E2', 'E2', 'E2', 'E2', 'E2', 'E2', 'E2',
    ]
    bass_notes = bass_a + bass_b

    # High arpeggiated shimmer — ethereal atmosphere
    arp_a = [
        'E5', 'B4', 'E5', 'B4',
        'E5', 'G5', 'E5', 'R', 'C5', 'E5', 'C5', 'R',
        'G5', 'B4', 'G5', 'R', 'E5', 'G4', 'E5', 'R',
        'A5', 'E5', 'A5', 'R', 'B4', 'E5', 'B4', 'R',
    ]
    arp_b = [
        'C5', 'G5', 'C5', 'G5',
        'C5', 'E5', 'G5', 'R', 'G5', 'C5', 'E5', 'R',
        'A5', 'C5', 'A5', 'R', 'F5', 'A4', 'F5', 'R',
        'E5', 'G4', 'B4', 'R', 'E5', 'B4', 'E4', 'R',
    ]
    arp_notes = arp_a + arp_b

    melody = _render_melody(melody_notes, note_dur, _triangle_wave,
                            volume=0.22, attack=0.04, release=0.20)
    bass = _render_bass(bass_notes, note_dur, volume=0.18)
    arp = _render_melody(arp_notes, note_dur, _triangle_wave,
                         volume=0.10, attack=0.02, release=0.25)

    return _mix_tracks(melody, bass, arp)


# ── Overworld variations ──────────────────────────────────────

def _compose_overworld_1():
    """Overworld A — gentle wandering theme."""
    bpm = 78
    nd = 60.0 / bpm
    melody = _render_melody(
        ['C4', 'C4', 'G4', 'G4', 'A4', 'A4', 'G4', 'R',
         'F4', 'F4', 'E4', 'E4', 'D4', 'D4', 'C4', 'R',
         'C4', 'D4', 'E4', 'F4', 'G4', 'A4', 'G4', 'E4',
         'F4', 'E4', 'D4', 'C4', 'D4', 'E4', 'C4', 'R'] * 2,
        nd, _triangle_wave, volume=0.22, attack=0.02, release=0.12)
    counter = _render_melody(
        ['E5', 'R', 'E5', 'R', 'F5', 'R', 'E5', 'R',
         'A4', 'R', 'G4', 'R', 'F4', 'R', 'E4', 'R',
         'G5', 'R', 'G5', 'R', 'E5', 'R', 'C5', 'R',
         'A4', 'R', 'B4', 'R', 'C5', 'R', 'E5', 'R'] * 2,
        nd, _triangle_wave, volume=0.09, attack=0.02, release=0.18)
    bass = _render_bass(
        ['C2', 'C2', 'C2', 'C2', 'F2', 'F2', 'C2', 'C2',
         'F2', 'F2', 'C2', 'C2', 'G2', 'G2', 'C2', 'C2',
         'C2', 'C2', 'E2', 'E2', 'G2', 'G2', 'E2', 'E2',
         'F2', 'F2', 'G2', 'G2', 'G2', 'G2', 'C2', 'C2'] * 2,
        nd, volume=0.18)
    drums = _render_drums((['K', 'R', 'H', 'R'] * 4) * 4, nd, volume=0.04)
    return _mix_tracks(melody, counter, bass, drums)


def _compose_overworld_2():
    """Overworld B — pastoral wandering, gentle and airy."""
    bpm = 72
    nd = 60.0 / bpm
    melody = _render_melody(
        ['E4', 'R', 'G4', 'A4', 'G4', 'R', 'E4', 'R',
         'D4', 'R', 'F4', 'G4', 'F4', 'R', 'D4', 'R',
         'C4', 'E4', 'G4', 'R', 'A4', 'G4', 'E4', 'R',
         'F4', 'E4', 'D4', 'R', 'C4', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.20, attack=0.03, release=0.15)
    arp = _render_melody(
        ['C5', 'E5', 'G5', 'R', 'R', 'R', 'R', 'R',
         'D5', 'F5', 'A5', 'R', 'R', 'R', 'R', 'R',
         'E5', 'G5', 'C6', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.08, attack=0.02, release=0.20)
    bass = _render_bass(
        ['C2', 'C2', 'R', 'R', 'F2', 'F2', 'R', 'R',
         'G2', 'G2', 'R', 'R', 'C2', 'C2', 'R', 'R'] * 4,
        nd, volume=0.16)
    return _mix_tracks(melody, arp, bass)


def _compose_overworld_3():
    """Overworld C — spacious adventure, gentle rhythm."""
    bpm = 80
    nd = 60.0 / bpm
    melody = _render_melody(
        ['G4', 'R', 'G4', 'A4', 'B4', 'R', 'A4', 'G4',
         'E4', 'R', 'E4', 'F4', 'G4', 'R', 'F4', 'E4',
         'D4', 'R', 'D4', 'E4', 'F4', 'G4', 'A4', 'R',
         'G4', 'F4', 'E4', 'D4', 'C4', 'R', 'R', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.20, attack=0.02, release=0.12)
    counter = _render_melody(
        ['R', 'B4', 'R', 'R', 'R', 'D5', 'R', 'R',
         'R', 'G4', 'R', 'R', 'R', 'B4', 'R', 'R',
         'R', 'R', 'A4', 'R', 'R', 'R', 'C5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.08, attack=0.03, release=0.18)
    bass = _render_bass(
        ['G2', 'R', 'G2', 'R', 'C2', 'R', 'C2', 'R',
         'E2', 'R', 'E2', 'R', 'G2', 'R', 'G2', 'R',
         'D2', 'R', 'D2', 'R', 'F2', 'R', 'G2', 'R',
         'C2', 'R', 'C2', 'R', 'C2', 'R', 'C2', 'R'] * 2,
        nd, volume=0.17)
    drums = _render_drums(
        (['K', 'R', 'R', 'R', 'H', 'R', 'R', 'R'] * 4) * 2,
        nd, volume=0.04)
    return _mix_tracks(melody, counter, bass, drums)


# ── Town variations ───────────────────────────────────────────

def _compose_town_1():
    """Town A — gentle folk waltz, soft and warm."""
    bpm = 82
    nd = 60.0 / bpm
    melody = _render_melody(
        ['E4', 'G4', 'A4', 'G4', 'E4', 'D4', 'C4', 'R',
         'D4', 'F4', 'G4', 'F4', 'D4', 'C4', 'D4', 'R',
         'E4', 'G4', 'C5', 'B4', 'A4', 'G4', 'A4', 'R',
         'G4', 'F4', 'E4', 'D4', 'E4', 'G4', 'E4', 'R'] * 2,
        nd, _triangle_wave, volume=0.20, attack=0.03, release=0.14)
    arp = _render_melody(
        ['C5', 'E5', 'G5', 'E5', 'C5', 'R', 'R', 'R',
         'D5', 'F5', 'A5', 'F5', 'D5', 'R', 'R', 'R',
         'E5', 'G5', 'C6', 'G5', 'E5', 'R', 'R', 'R',
         'G5', 'R', 'E5', 'R', 'C5', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.07, attack=0.02, release=0.20)
    bass = _render_bass(
        ['C3', 'R', 'G2', 'R', 'C3', 'R', 'C3', 'R',
         'D3', 'R', 'G2', 'R', 'D3', 'R', 'G2', 'R'] * 4,
        nd, volume=0.14)
    return _mix_tracks(melody, arp, bass)


def _compose_town_2():
    """Town B — cosy tavern melody, warm and dreamy."""
    bpm = 76
    nd = 60.0 / bpm
    melody = _render_melody(
        ['C4', 'E4', 'G4', 'E4', 'C4', 'R', 'R', 'R',
         'D4', 'F4', 'A4', 'F4', 'D4', 'R', 'R', 'R',
         'E4', 'G4', 'B4', 'G4', 'E4', 'D4', 'C4', 'R',
         'D4', 'E4', 'F4', 'E4', 'D4', 'C4', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.19, attack=0.03, release=0.16)
    counter = _render_melody(
        ['R', 'R', 'R', 'R', 'E5', 'R', 'C5', 'R',
         'R', 'R', 'R', 'R', 'F5', 'R', 'D5', 'R',
         'R', 'R', 'R', 'R', 'G5', 'R', 'E5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.07, attack=0.02, release=0.20)
    bass = _render_bass(
        ['C2', 'R', 'C2', 'R', 'G2', 'R', 'G2', 'R',
         'D2', 'R', 'D2', 'R', 'A2', 'R', 'A2', 'R',
         'E2', 'R', 'E2', 'R', 'G2', 'R', 'C2', 'R',
         'D2', 'R', 'G2', 'R', 'C2', 'R', 'R', 'R'] * 2,
        nd, volume=0.14)
    return _mix_tracks(melody, counter, bass)


def _compose_town_3():
    """Town C — airy market square, delicate and floating."""
    bpm = 85
    nd = 60.0 / bpm
    melody = _render_melody(
        ['G4', 'A4', 'B4', 'C5', 'B4', 'A4', 'G4', 'R',
         'A4', 'B4', 'C5', 'D5', 'C5', 'B4', 'A4', 'R',
         'B4', 'C5', 'D5', 'E5', 'D5', 'C5', 'B4', 'A4',
         'G4', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _square_wave, duty=0.125, volume=0.18, attack=0.03, release=0.14)
    arp = _render_melody(
        ['G5', 'R', 'D5', 'R', 'B4', 'R', 'R', 'R',
         'A5', 'R', 'E5', 'R', 'C5', 'R', 'R', 'R',
         'B5', 'R', 'G5', 'R', 'D5', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.06, attack=0.02, release=0.22)
    bass = _render_bass(
        ['G2', 'R', 'G2', 'R', 'D2', 'R', 'D2', 'R',
         'A2', 'R', 'A2', 'R', 'E2', 'R', 'E2', 'R',
         'B2', 'R', 'B2', 'R', 'G2', 'R', 'G2', 'R',
         'C2', 'R', 'D2', 'R', 'G2', 'R', 'R', 'R'] * 2,
        nd, volume=0.13)
    return _mix_tracks(melody, arp, bass)


# ── Dungeon variations ────────────────────────────────────────

def _compose_dungeon_1():
    """Dungeon A — ominous creep, dark ambient drone."""
    bpm = 60
    nd = 60.0 / bpm
    melody = _render_melody(
        ['A3', 'R', 'C4', 'R', 'B3', 'R', 'A3', 'R',
         'E3', 'R', 'F3', 'R', 'E3', 'R', 'R', 'R',
         'A3', 'R', 'E4', 'R', 'D4', 'R', 'C4', 'B3',
         'A3', 'R', 'G#3', 'R', 'A3', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.18, attack=0.05, release=0.20)
    eerie = _render_melody(
        ['R', 'E5', 'R', 'R', 'R', 'C5', 'R', 'R',
         'R', 'R', 'B4', 'R', 'R', 'R', 'A4', 'R',
         'R', 'R', 'E5', 'R', 'R', 'R', 'R', 'D5',
         'R', 'R', 'R', 'C5', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.06, attack=0.05, release=0.25)
    bass = _render_bass(
        ['A1', 'A1', 'A1', 'A1', 'A1', 'A1', 'A1', 'A1',
         'E1', 'E1', 'E1', 'E1', 'E1', 'E1', 'E1', 'E1'] * 4,
        nd, volume=0.16)
    drums = _render_drums(
        (['R', 'R', 'R', 'R', 'R', 'R', 'K', 'R'] * 2) * 4,
        nd, volume=0.03)
    return _mix_tracks(melody, eerie, bass, drums)


def _compose_dungeon_2():
    """Dungeon B — dripping cavern, sparse and eerie."""
    bpm = 55
    nd = 60.0 / bpm
    # Sparse melody — mostly silence with occasional notes
    melody = _render_melody(
        ['R', 'R', 'R', 'R', 'E3', 'R', 'R', 'R',
         'R', 'R', 'R', 'F3', 'R', 'R', 'R', 'R',
         'R', 'R', 'G#3', 'R', 'R', 'R', 'R', 'R',
         'A3', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.15, attack=0.06, release=0.25)
    # Drip-like high notes
    drips = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'E6',
         'R', 'R', 'R', 'R', 'R', 'C6', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'A5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.05, attack=0.003, release=0.08)
    # Deep rumbling bass
    bass = _render_bass(
        ['A1', 'A1', 'A1', 'A1', 'R', 'R', 'R', 'R',
         'E1', 'E1', 'R', 'R', 'R', 'R', 'R', 'R',
         'D1', 'D1', 'D1', 'D1', 'R', 'R', 'R', 'R',
         'A1', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.14)
    return _mix_tracks(melody, drips, bass)


def _compose_dungeon_3():
    """Dungeon C — restless shadows, slow tension."""
    bpm = 68
    nd = 60.0 / bpm
    melody = _render_melody(
        ['E4', 'R', 'E4', 'D4', 'C4', 'R', 'B3', 'R',
         'A3', 'R', 'B3', 'C4', 'D4', 'R', 'C4', 'B3',
         'A3', 'R', 'R', 'R', 'E3', 'R', 'R', 'R',
         'F3', 'R', 'G#3', 'R', 'A3', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.17, attack=0.04, release=0.18)
    counter = _render_melody(
        ['R', 'R', 'A4', 'R', 'R', 'R', 'E4', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'C5', 'R', 'R', 'R', 'B4', 'R',
         'A4', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.06, attack=0.04, release=0.20)
    bass = _render_bass(
        ['A1', 'R', 'A1', 'R', 'R', 'R', 'E1', 'R',
         'A1', 'R', 'R', 'R', 'D1', 'R', 'D1', 'R',
         'A1', 'R', 'A1', 'R', 'R', 'R', 'E1', 'R',
         'F1', 'R', 'G#1', 'R', 'A1', 'R', 'R', 'R'] * 2,
        nd, volume=0.16)
    drums = _render_drums(
        (['R', 'R', 'R', 'R', 'R', 'R', 'H', 'R'] * 4) * 2,
        nd, volume=0.03)
    return _mix_tracks(melody, counter, bass, drums)


# ── Combat variations ─────────────────────────────────────────

def _compose_combat_1():
    """Combat A — tense undertone, restrained energy."""
    bpm = 120
    nd = 60.0 / bpm
    melody = _render_melody(
        (['A4', 'A4', 'C5', 'A4', 'E4', 'E4', 'A4', 'R',
          'G4', 'G4', 'A4', 'G4', 'E4', 'D4', 'E4', 'R',
          'A4', 'C5', 'D5', 'E5', 'D5', 'C5', 'A4', 'R',
          'G4', 'A4', 'G4', 'E4', 'D4', 'E4', 'A4', 'R']) * 2,
        nd, _square_wave, duty=0.25, volume=0.22, attack=0.01, release=0.08)
    bass = _render_bass(
        (['A2', 'R', 'A2', 'R', 'A2', 'R', 'A2', 'R',
          'G2', 'R', 'G2', 'R', 'E2', 'R', 'E2', 'R',
          'A2', 'R', 'C3', 'R', 'D3', 'R', 'E3', 'R',
          'D3', 'R', 'C3', 'R', 'A2', 'R', 'A2', 'R']) * 2,
        nd, volume=0.20)
    drums = _render_drums(
        (['K', 'R', 'H', 'R', 'S', 'R', 'H', 'R'] * 2) * 4,
        nd, volume=0.06)
    return _mix_tracks(melody, bass, drums)


def _compose_combat_2():
    """Combat B — urgent tension, controlled pace."""
    bpm = 130
    nd = 60.0 / bpm
    melody = _render_melody(
        ['E5', 'D5', 'C5', 'B4', 'A4', 'R', 'A4', 'B4',
         'C5', 'D5', 'E5', 'R', 'E5', 'D5', 'C5', 'R',
         'A4', 'B4', 'C5', 'R', 'E4', 'R', 'A4', 'R',
         'G4', 'A4', 'B4', 'C5', 'B4', 'A4', 'G4', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.20, attack=0.01, release=0.08)
    counter = _render_melody(
        ['R', 'R', 'E4', 'R', 'R', 'R', 'C4', 'R',
         'R', 'R', 'A3', 'R', 'R', 'R', 'E4', 'R',
         'R', 'R', 'C4', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'E4', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.08, attack=0.02, release=0.14)
    bass = _render_bass(
        ['A2', 'A2', 'R', 'A2', 'A2', 'R', 'E2', 'R',
         'A2', 'R', 'C3', 'R', 'A2', 'R', 'E2', 'R',
         'A2', 'R', 'A2', 'R', 'D3', 'R', 'C3', 'R',
         'A2', 'R', 'E2', 'R', 'A2', 'R', 'A2', 'R'] * 2,
        nd, volume=0.18)
    drums = _render_drums(
        (['K', 'R', 'H', 'R', 'S', 'R', 'H', 'R'] * 2) * 4,
        nd, volume=0.06)
    return _mix_tracks(melody, counter, bass, drums)


def _compose_combat_3():
    """Combat C — brooding and heavy, deliberate pace."""
    bpm = 110
    nd = 60.0 / bpm
    melody = _render_melody(
        ['A4', 'R', 'A4', 'R', 'C5', 'R', 'D5', 'R',
         'E5', 'R', 'D5', 'R', 'C5', 'R', 'A4', 'R',
         'G4', 'R', 'A4', 'R', 'G4', 'R', 'E4', 'R',
         'D4', 'R', 'E4', 'R', 'A4', 'R', 'R', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.22, attack=0.02, release=0.10)
    bass = _render_bass(
        ['A2', 'A2', 'A2', 'R', 'A2', 'A2', 'A2', 'R',
         'E2', 'E2', 'E2', 'R', 'E2', 'E2', 'E2', 'R',
         'G2', 'G2', 'G2', 'R', 'A2', 'A2', 'A2', 'R',
         'D2', 'D2', 'E2', 'E2', 'A2', 'R', 'A2', 'R'] * 2,
        nd, volume=0.20)
    drums = _render_drums(
        (['K', 'R', 'R', 'R', 'S', 'R', 'R', 'R'] * 2) * 4,
        nd, volume=0.06)
    return _mix_tracks(melody, bass, drums)


# ═══════════════════════════════════════════════════════════════
#  DARK & MOODY SOUNDTRACK
# ═══════════════════════════════════════════════════════════════

def _compose_dark_title():
    """Dark title — foreboding, low, rumbling atmosphere."""
    bpm = 50
    nd = 60.0 / bpm
    melody = _render_melody(
        ['R', 'R', 'R', 'R',
         'A3', 'R', 'R', 'C4', 'R', 'R', 'B3', 'R',
         'A3', 'R', 'R', 'R', 'G#3', 'R', 'R', 'R',
         'F3', 'R', 'R', 'E3', 'R', 'R', 'R', 'R'],
        nd, _triangle_wave, volume=0.18, attack=0.06, release=0.30)
    drone = _render_bass(
        ['A1'] * 28, nd, volume=0.20)
    eerie = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'E5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'C5',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R'],
        nd, _triangle_wave, volume=0.05, attack=0.08, release=0.30)
    return _mix_tracks(melody, drone, eerie)


def _compose_dark_overworld():
    """Dark overworld — bleak, desolate wandering."""
    bpm = 58
    nd = 60.0 / bpm
    melody = _render_melody(
        ['A3', 'R', 'C4', 'R', 'E4', 'R', 'D4', 'R',
         'C4', 'R', 'B3', 'R', 'A3', 'R', 'R', 'R',
         'F3', 'R', 'G#3', 'R', 'A3', 'R', 'R', 'R',
         'E3', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.17, attack=0.05, release=0.22)
    bass = _render_bass(
        ['A1', 'A1', 'R', 'R', 'A1', 'R', 'R', 'R',
         'F1', 'F1', 'R', 'R', 'E1', 'R', 'R', 'R',
         'D1', 'D1', 'R', 'R', 'E1', 'R', 'R', 'R',
         'A1', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.18)
    drums = _render_drums(
        (['R', 'R', 'R', 'R', 'R', 'R', 'K', 'R'] * 4) * 2,
        nd, volume=0.03)
    return _mix_tracks(melody, bass, drums)


def _compose_dark_town():
    """Dark town — uneasy, shadowy settlement."""
    bpm = 62
    nd = 60.0 / bpm
    melody = _render_melody(
        ['E3', 'R', 'A3', 'R', 'C4', 'R', 'B3', 'R',
         'A3', 'R', 'G#3', 'R', 'A3', 'R', 'R', 'R',
         'D4', 'R', 'C4', 'R', 'A3', 'R', 'R', 'R',
         'G#3', 'R', 'A3', 'R', 'E3', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.16, attack=0.04, release=0.20)
    counter = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'E5', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'C5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.05, attack=0.06, release=0.28)
    bass = _render_bass(
        ['A1', 'R', 'A1', 'R', 'E1', 'R', 'E1', 'R',
         'F1', 'R', 'F1', 'R', 'E1', 'R', 'R', 'R'] * 4,
        nd, volume=0.16)
    return _mix_tracks(melody, counter, bass)


def _compose_dark_dungeon():
    """Dark dungeon — crushing dread, almost silent with low rumbles."""
    bpm = 45
    nd = 60.0 / bpm
    melody = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'A2', 'R', 'R', 'R', 'C3', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'B2', 'R', 'R', 'R', 'A2', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.14, attack=0.08, release=0.30)
    drone = _render_bass(
        ['A1', 'A1', 'A1', 'A1', 'R', 'R', 'R', 'R',
         'E1', 'E1', 'R', 'R', 'R', 'R', 'R', 'R',
         'D1', 'D1', 'D1', 'D1', 'R', 'R', 'R', 'R',
         'A1', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.20)
    noise = _render_drums(
        (['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
          'R', 'R', 'R', 'R', 'H', 'R', 'R', 'R'] * 2) * 2,
        nd, volume=0.02)
    return _mix_tracks(melody, drone, noise)


def _compose_dark_combat():
    """Dark combat — aggressive, dissonant, heavy."""
    bpm = 105
    nd = 60.0 / bpm
    melody = _render_melody(
        ['A4', 'A4', 'R', 'A4', 'C5', 'R', 'B4', 'R',
         'A4', 'R', 'G#4', 'R', 'A4', 'R', 'R', 'R',
         'E4', 'R', 'F4', 'R', 'G#4', 'R', 'A4', 'R',
         'F4', 'R', 'E4', 'R', 'D4', 'R', 'R', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.22, attack=0.01, release=0.08)
    bass = _render_bass(
        ['A2', 'A2', 'A2', 'R', 'A2', 'A2', 'R', 'R',
         'E2', 'E2', 'R', 'E2', 'E2', 'R', 'R', 'R',
         'F2', 'F2', 'F2', 'R', 'G#2', 'R', 'A2', 'R',
         'D2', 'D2', 'E2', 'R', 'A2', 'R', 'R', 'R'] * 2,
        nd, volume=0.22)
    drums = _render_drums(
        (['K', 'R', 'H', 'R', 'S', 'R', 'K', 'H'] * 2) * 4,
        nd, volume=0.07)
    return _mix_tracks(melody, bass, drums)


# ═══════════════════════════════════════════════════════════════
#  QUIET SOUNDTRACK
# ═══════════════════════════════════════════════════════════════

def _compose_quiet_title():
    """Quiet title — gentle breath, barely there."""
    bpm = 50
    nd = 60.0 / bpm
    melody = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'E4', 'R', 'R', 'R', 'R', 'R', 'G4', 'R',
         'R', 'R', 'R', 'R', 'A4', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, _triangle_wave, volume=0.12, attack=0.08, release=0.30)
    bass = _render_bass(
        ['C2', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'G2', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, volume=0.10)
    return _mix_tracks(melody, bass)


def _compose_quiet_overworld():
    """Quiet overworld — sparse, meditative wandering."""
    bpm = 55
    nd = 60.0 / bpm
    melody = _render_melody(
        ['R', 'R', 'C4', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'E4', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'G4', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.12, attack=0.06, release=0.25)
    arp = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'G5',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.06, attack=0.04, release=0.30)
    return _mix_tracks(melody, arp)


def _compose_quiet_town():
    """Quiet town — hushed lullaby, barely audible."""
    bpm = 58
    nd = 60.0 / bpm
    melody = _render_melody(
        ['E4', 'R', 'R', 'R', 'G4', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'A4', 'R', 'R', 'R', 'G4', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.11, attack=0.06, release=0.25)
    bass = _render_bass(
        ['C2', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 4,
        nd, volume=0.08)
    return _mix_tracks(melody, bass)


def _compose_quiet_dungeon():
    """Quiet dungeon — near silence, occasional drip."""
    bpm = 40
    nd = 60.0 / bpm
    drips = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'E6', 'R'] * 2,
        nd, _triangle_wave, volume=0.04, attack=0.003, release=0.06)
    bass = _render_bass(
        ['A1', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.10)
    return _mix_tracks(drips, bass)


def _compose_quiet_combat():
    """Quiet combat — restrained tension, heartbeat drums."""
    bpm = 90
    nd = 60.0 / bpm
    melody = _render_melody(
        ['A4', 'R', 'R', 'R', 'C5', 'R', 'R', 'R',
         'B4', 'R', 'R', 'R', 'A4', 'R', 'R', 'R',
         'R', 'R', 'E4', 'R', 'R', 'R', 'A4', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.15, attack=0.03, release=0.15)
    bass = _render_bass(
        ['A2', 'R', 'R', 'R', 'R', 'R', 'A2', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 4,
        nd, volume=0.15)
    drums = _render_drums(
        (['K', 'R', 'R', 'R', 'K', 'R', 'R', 'R'] * 2) * 4,
        nd, volume=0.05)
    return _mix_tracks(melody, bass, drums)


# ═══════════════════════════════════════════════════════════════
#  TWIN PEAKS SOUNDTRACK
# ═══════════════════════════════════════════════════════════════

def _compose_peaks_title():
    """Twin Peaks title — jazzy, dreamy, slightly sinister."""
    bpm = 62
    nd = 60.0 / bpm
    melody = _render_melody(
        ['R', 'R', 'R', 'R',
         'D4', 'R', 'F#4', 'R', 'A4', 'R', 'C5', 'R',
         'B4', 'R', 'R', 'R', 'G4', 'R', 'R', 'R',
         'F#4', 'R', 'E4', 'R', 'D4', 'R', 'R', 'R'],
        nd, _triangle_wave, volume=0.18, attack=0.05, release=0.25)
    bass = _render_bass(
        ['D2', 'R', 'D2', 'R', 'R', 'R', 'R', 'R',
         'A2', 'R', 'R', 'R', 'G2', 'R', 'R', 'R',
         'F#2', 'R', 'R', 'R', 'E2', 'R', 'R', 'R',
         'D2', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, volume=0.15)
    shimmer = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'F#5', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'D5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, _triangle_wave, volume=0.06, attack=0.06, release=0.30)
    return _mix_tracks(melody, bass, shimmer)


def _compose_peaks_overworld():
    """Twin Peaks overworld — chromatic wandering, bossa-tinged."""
    bpm = 68
    nd = 60.0 / bpm
    melody = _render_melody(
        ['D4', 'R', 'F#4', 'G4', 'A4', 'R', 'C5', 'R',
         'B4', 'R', 'A4', 'R', 'G4', 'R', 'F#4', 'R',
         'E4', 'R', 'G4', 'R', 'F#4', 'R', 'D4', 'R',
         'C#4', 'R', 'D4', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.18, attack=0.04, release=0.18)
    counter = _render_melody(
        ['R', 'A4', 'R', 'R', 'R', 'R', 'R', 'F#5',
         'R', 'R', 'R', 'R', 'R', 'D5', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.07, attack=0.04, release=0.22)
    bass = _render_bass(
        ['D2', 'R', 'R', 'R', 'A2', 'R', 'R', 'R',
         'G2', 'R', 'R', 'R', 'F#2', 'R', 'R', 'R',
         'E2', 'R', 'R', 'R', 'D2', 'R', 'R', 'R',
         'C#2', 'R', 'D2', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.14)
    return _mix_tracks(melody, counter, bass)


def _compose_peaks_town():
    """Twin Peaks town — smoky jazz lounge, soft and warm."""
    bpm = 72
    nd = 60.0 / bpm
    melody = _render_melody(
        ['F#4', 'R', 'A4', 'R', 'D5', 'R', 'C#5', 'R',
         'A4', 'R', 'R', 'R', 'F#4', 'R', 'R', 'R',
         'G4', 'R', 'B4', 'R', 'D5', 'R', 'C5', 'R',
         'B4', 'R', 'A4', 'R', 'F#4', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.17, attack=0.04, release=0.20)
    arp = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'F#5',
         'R', 'R', 'R', 'R', 'R', 'R', 'A5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.05, attack=0.04, release=0.25)
    bass = _render_bass(
        ['D2', 'R', 'D2', 'R', 'A2', 'R', 'R', 'R',
         'D2', 'R', 'R', 'R', 'F#2', 'R', 'R', 'R',
         'G2', 'R', 'G2', 'R', 'D2', 'R', 'R', 'R',
         'D2', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.13)
    return _mix_tracks(melody, arp, bass)


def _compose_peaks_dungeon():
    """Twin Peaks dungeon — surreal, disorienting, Lynch-esque."""
    bpm = 48
    nd = 60.0 / bpm
    melody = _render_melody(
        ['R', 'R', 'R', 'R', 'D4', 'R', 'R', 'R',
         'R', 'R', 'R', 'C#4', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'F#4', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.14, attack=0.08, release=0.30)
    eerie = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'A#5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'D#5'] * 2,
        nd, _triangle_wave, volume=0.05, attack=0.06, release=0.30)
    bass = _render_bass(
        ['D1', 'D1', 'R', 'R', 'R', 'R', 'R', 'R',
         'C#1', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'D1', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.16)
    return _mix_tracks(melody, eerie, bass)


def _compose_peaks_combat():
    """Twin Peaks combat — syncopated, jazzy tension."""
    bpm = 115
    nd = 60.0 / bpm
    melody = _render_melody(
        ['D5', 'R', 'F#5', 'R', 'A4', 'R', 'C5', 'D5',
         'R', 'R', 'C#5', 'R', 'D5', 'R', 'R', 'R',
         'A4', 'R', 'G4', 'R', 'F#4', 'R', 'A4', 'R',
         'D4', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.20, attack=0.01, release=0.08)
    bass = _render_bass(
        ['D2', 'R', 'D2', 'R', 'A2', 'R', 'R', 'D2',
         'R', 'R', 'C#2', 'R', 'D2', 'R', 'R', 'R',
         'G2', 'R', 'R', 'R', 'F#2', 'R', 'R', 'R',
         'D2', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.18)
    drums = _render_drums(
        (['K', 'R', 'R', 'H', 'R', 'S', 'R', 'H'] * 2) * 4,
        nd, volume=0.05)
    return _mix_tracks(melody, bass, drums)


# ═══════════════════════════════════════════════════════════════
#  EPIC FANTASY SOUNDTRACK
# ═══════════════════════════════════════════════════════════════

def _compose_epic_title():
    """Epic title — sweeping, majestic, heroic horn call."""
    bpm = 72
    nd = 60.0 / bpm
    melody = _render_melody(
        ['R', 'R', 'R', 'R',
         'C4', 'R', 'E4', 'G4', 'C5', 'R', 'R', 'R',
         'B4', 'R', 'A4', 'G4', 'A4', 'R', 'R', 'R',
         'G4', 'R', 'F4', 'E4', 'D4', 'R', 'C4', 'R'],
        nd, _square_wave, duty=0.25, volume=0.22, attack=0.03, release=0.18)
    counter = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'E5', 'R', 'D5', 'C5',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'G4', 'R', 'E4', 'R'],
        nd, _triangle_wave, volume=0.10, attack=0.03, release=0.22)
    bass = _render_bass(
        ['C2', 'C2', 'C2', 'C2', 'C2', 'C2', 'C2', 'C2',
         'G2', 'G2', 'G2', 'G2', 'A2', 'A2', 'A2', 'A2',
         'F2', 'F2', 'F2', 'F2', 'F2', 'F2', 'F2', 'F2',
         'G2', 'G2', 'G2', 'G2', 'C2', 'C2', 'C2', 'C2'],
        nd, volume=0.20)
    return _mix_tracks(melody, counter, bass)


def _compose_epic_overworld():
    """Epic overworld — sweeping adventure theme, heroic stride."""
    bpm = 88
    nd = 60.0 / bpm
    melody = _render_melody(
        ['C4', 'E4', 'G4', 'C5', 'B4', 'G4', 'A4', 'R',
         'G4', 'F4', 'E4', 'D4', 'E4', 'G4', 'C4', 'R',
         'A4', 'C5', 'E5', 'D5', 'C5', 'A4', 'G4', 'R',
         'F4', 'G4', 'A4', 'G4', 'E4', 'D4', 'C4', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.20, attack=0.02, release=0.12)
    counter = _render_melody(
        ['R', 'R', 'R', 'R', 'G5', 'R', 'E5', 'R',
         'R', 'R', 'R', 'R', 'C5', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'E5', 'R', 'C5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.08, attack=0.02, release=0.18)
    bass = _render_bass(
        ['C2', 'C2', 'G2', 'G2', 'A2', 'A2', 'E2', 'E2',
         'F2', 'F2', 'C2', 'C2', 'G2', 'G2', 'C2', 'C2',
         'A2', 'A2', 'E2', 'E2', 'F2', 'F2', 'G2', 'G2',
         'F2', 'F2', 'G2', 'G2', 'C2', 'C2', 'C2', 'C2'] * 2,
        nd, volume=0.18)
    drums = _render_drums(
        (['K', 'R', 'H', 'R', 'S', 'R', 'H', 'R'] * 4) * 2,
        nd, volume=0.05)
    return _mix_tracks(melody, counter, bass, drums)


def _compose_epic_town():
    """Epic town — warm, pastoral, Shire-like gentleness."""
    bpm = 78
    nd = 60.0 / bpm
    melody = _render_melody(
        ['E4', 'G4', 'A4', 'G4', 'E4', 'D4', 'C4', 'R',
         'D4', 'E4', 'F4', 'E4', 'D4', 'C4', 'D4', 'R',
         'C4', 'E4', 'G4', 'A4', 'G4', 'E4', 'D4', 'R',
         'C4', 'D4', 'E4', 'C4', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.19, attack=0.03, release=0.16)
    arp = _render_melody(
        ['C5', 'E5', 'G5', 'R', 'R', 'R', 'R', 'R',
         'D5', 'F5', 'A5', 'R', 'R', 'R', 'R', 'R',
         'E5', 'G5', 'C6', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.06, attack=0.03, release=0.22)
    bass = _render_bass(
        ['C2', 'R', 'G2', 'R', 'C2', 'R', 'G2', 'R',
         'F2', 'R', 'C2', 'R', 'G2', 'R', 'C2', 'R'] * 4,
        nd, volume=0.14)
    return _mix_tracks(melody, arp, bass)


def _compose_epic_dungeon():
    """Epic dungeon — ominous but grand, echoing stone halls."""
    bpm = 65
    nd = 60.0 / bpm
    melody = _render_melody(
        ['A3', 'R', 'C4', 'R', 'E4', 'R', 'D4', 'C4',
         'B3', 'R', 'A3', 'R', 'R', 'R', 'R', 'R',
         'F4', 'R', 'E4', 'R', 'D4', 'R', 'C4', 'R',
         'B3', 'R', 'A3', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.18, attack=0.04, release=0.18)
    drone = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'E5', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'C5', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.06, attack=0.05, release=0.25)
    bass = _render_bass(
        ['A1', 'A1', 'A1', 'A1', 'E1', 'E1', 'E1', 'E1',
         'F1', 'F1', 'F1', 'F1', 'A1', 'A1', 'A1', 'A1',
         'D1', 'D1', 'D1', 'D1', 'E1', 'E1', 'E1', 'E1',
         'F1', 'F1', 'F1', 'F1', 'A1', 'A1', 'A1', 'A1'] * 2,
        nd, volume=0.18)
    drums = _render_drums(
        (['R', 'R', 'R', 'R', 'R', 'R', 'K', 'R'] * 4) * 2,
        nd, volume=0.03)
    return _mix_tracks(melody, drone, bass, drums)


def _compose_epic_combat():
    """Epic combat — heroic battle theme, triumphant energy."""
    bpm = 135
    nd = 60.0 / bpm
    melody = _render_melody(
        ['C5', 'C5', 'G4', 'A4', 'C5', 'D5', 'E5', 'R',
         'D5', 'C5', 'A4', 'G4', 'A4', 'C5', 'D5', 'R',
         'E5', 'D5', 'C5', 'A4', 'G4', 'A4', 'C5', 'R',
         'G4', 'A4', 'C5', 'D5', 'C5', 'A4', 'G4', 'R'] * 2,
        nd, _square_wave, duty=0.25, volume=0.22, attack=0.01, release=0.08)
    counter = _render_melody(
        ['R', 'R', 'E5', 'R', 'R', 'R', 'G5', 'R',
         'R', 'R', 'E5', 'R', 'R', 'R', 'C5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'E5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, _triangle_wave, volume=0.08, attack=0.02, release=0.12)
    bass = _render_bass(
        ['C2', 'C2', 'G2', 'R', 'A2', 'R', 'C3', 'R',
         'G2', 'R', 'A2', 'R', 'C3', 'R', 'G2', 'R',
         'A2', 'R', 'C3', 'R', 'G2', 'R', 'A2', 'R',
         'G2', 'R', 'A2', 'R', 'C2', 'R', 'C2', 'R'] * 2,
        nd, volume=0.20)
    drums = _render_drums(
        (['K', 'R', 'H', 'R', 'S', 'R', 'H', 'K'] * 2) * 4,
        nd, volume=0.06)
    return _mix_tracks(melody, counter, bass, drums)


# ═══════════════════════════════════════════════════════════════
#  CINEMATIC SOUNDTRACK
# ═══════════════════════════════════════════════════════════════
#
# Uses the same proven waveform generators as every other style
# but with slower tempos, longer attack/release envelopes,
# layered triangle-wave voices, and plenty of rests to create
# a spacious, atmospheric, film-score feel.


def _sine_wave(freq, duration, sample_rate=SAMPLE_RATE):
    """Pure sine wave — warmer than square/triangle for pads."""
    if freq <= 0:
        return np.zeros(int(sample_rate * duration), dtype=np.float32)
    t = np.linspace(0, duration, int(sample_rate * duration),
                    endpoint=False)
    return np.sin(2.0 * np.pi * freq * t).astype(np.float32)


def _render_pad(notes, note_dur, volume=0.10):
    """Render a warm pad by layering two slightly-detuned triangle
    waves with a slow sine underneath.  Uses only existing primitives
    so it's fully safe."""
    parts = []
    for note_str in notes:
        freq = _n(note_str)
        n_samp = int(SAMPLE_RATE * note_dur)
        if freq <= 0:
            parts.append(np.zeros(n_samp, dtype=np.float32))
            continue
        # Two triangle voices, ~4 cents apart for warmth
        v1 = _triangle_wave(freq, note_dur)
        v2 = _triangle_wave(freq * 1.003, note_dur)
        # Sine an octave below for depth
        v3 = _sine_wave(freq * 0.5, note_dur)
        raw = (v1 * 0.40 + v2 * 0.35 + v3 * 0.25)
        raw = _envelope(raw, attack=0.12, release=0.25)
        parts.append(raw * volume)
    return np.concatenate(parts)


def _render_strings(notes, note_dur, volume=0.14):
    """Render a string-like voice — three slightly detuned triangle
    waves with longer envelopes for a legato feel."""
    parts = []
    for note_str in notes:
        freq = _n(note_str)
        n_samp = int(SAMPLE_RATE * note_dur)
        if freq <= 0:
            parts.append(np.zeros(n_samp, dtype=np.float32))
            continue
        v1 = _triangle_wave(freq, note_dur)
        v2 = _triangle_wave(freq * 1.002, note_dur)
        v3 = _triangle_wave(freq * 0.998, note_dur)
        raw = (v1 + v2 + v3) / 3.0
        raw = _envelope(raw, attack=0.06, release=0.20)
        parts.append(raw * volume)
    return np.concatenate(parts)


def _render_choir(notes, note_dur, volume=0.06):
    """Very soft choir-like voice — two sine waves a fifth apart with
    slow attack for an ethereal quality."""
    parts = []
    for note_str in notes:
        freq = _n(note_str)
        n_samp = int(SAMPLE_RATE * note_dur)
        if freq <= 0:
            parts.append(np.zeros(n_samp, dtype=np.float32))
            continue
        v1 = _sine_wave(freq, note_dur)
        v2 = _sine_wave(freq * 1.5, note_dur)  # perfect fifth
        raw = v1 * 0.6 + v2 * 0.4
        raw = _envelope(raw, attack=0.15, release=0.30)
        parts.append(raw * volume)
    return np.concatenate(parts)


def _render_deep_bass(notes, note_dur, volume=0.16):
    """Sub-bass using a sine wave for a clean, deep low end."""
    parts = []
    for note_str in notes:
        freq = _n(note_str)
        n_samp = int(SAMPLE_RATE * note_dur)
        if freq <= 0:
            parts.append(np.zeros(n_samp, dtype=np.float32))
            continue
        raw = _sine_wave(freq, note_dur)
        raw = _envelope(raw, attack=0.02, release=0.10)
        parts.append(raw * volume)
    return np.concatenate(parts)


# ── Cinematic compositions ─────────────────────────────────────

def _compose_cine_title():
    """Cinematic title — majestic, slow-building, with layered
    strings, brass-like melody, choir swells, and deep bass."""
    bpm = 54
    nd = 60.0 / bpm

    # Warm pad chords (slow harmonic progression)
    pad = _render_pad(
        ['C3', 'C3', 'E3', 'E3', 'G3', 'G3', 'E3', 'E3',
         'A2', 'A2', 'C3', 'C3', 'E3', 'E3', 'C3', 'C3',
         'F3', 'F3', 'A3', 'A3', 'C4', 'C4', 'A3', 'A3',
         'G2', 'G2', 'B2', 'B2', 'D3', 'D3', 'B2', 'B2'],
        nd, volume=0.10)

    # Brass-like melody — enters after 8 rests
    melody = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'C4', 'R', 'E4', 'G4', 'C5', 'R', 'R', 'R',
         'B4', 'R', 'A4', 'G4', 'E4', 'R', 'R', 'R',
         'A4', 'R', 'G4', 'E4', 'D4', 'R', 'C4', 'R'],
        nd, _square_wave, duty=0.25, volume=0.16,
        attack=0.05, release=0.30)

    # Ethereal choir hum (sparse)
    choir = _render_choir(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'C4', 'R', 'R', 'R', 'E4', 'R', 'R', 'R',
         'D4', 'R', 'R', 'R', 'C4', 'R', 'R', 'R'],
        nd, volume=0.06)

    # Deep sub bass
    bass = _render_deep_bass(
        ['C2', 'R', 'C2', 'R', 'R', 'R', 'R', 'R',
         'A1', 'R', 'A1', 'R', 'R', 'R', 'R', 'R',
         'F2', 'R', 'F2', 'R', 'R', 'R', 'R', 'R',
         'G1', 'R', 'G1', 'R', 'C2', 'R', 'R', 'R'],
        nd, volume=0.14)

    return _mix_tracks(pad, melody, choir, bass)


def _compose_cine_overworld():
    """Cinematic overworld — hopeful, wide-open strings with a soaring
    lead and warm bass.  Evokes journeying across a vast landscape."""
    bpm = 62
    nd = 60.0 / bpm

    # Soaring string melody
    melody = _render_strings(
        ['E4', 'R', 'G4', 'A4', 'B4', 'R', 'A4', 'G4',
         'E4', 'R', 'D4', 'E4', 'G4', 'R', 'R', 'R',
         'A4', 'R', 'B4', 'C5', 'B4', 'R', 'A4', 'G4',
         'E4', 'R', 'D4', 'R', 'E4', 'R', 'R', 'R',
         'C5', 'R', 'B4', 'A4', 'G4', 'R', 'E4', 'D4',
         'E4', 'R', 'G4', 'A4', 'B4', 'R', 'R', 'R',
         'A4', 'R', 'G4', 'E4', 'D4', 'R', 'E4', 'R',
         'E4', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, volume=0.14)

    # Warm sustained pad
    pad = _render_pad(
        ['E3', 'E3', 'E3', 'E3', 'E3', 'E3', 'E3', 'E3',
         'A2', 'A2', 'A2', 'A2', 'A2', 'A2', 'A2', 'A2',
         'D3', 'D3', 'D3', 'D3', 'D3', 'D3', 'D3', 'D3',
         'G2', 'G2', 'G2', 'G2', 'G2', 'G2', 'G2', 'G2',
         'C3', 'C3', 'C3', 'C3', 'C3', 'C3', 'C3', 'C3',
         'A2', 'A2', 'A2', 'A2', 'A2', 'A2', 'A2', 'A2',
         'D3', 'D3', 'D3', 'D3', 'G2', 'G2', 'G2', 'G2',
         'E3', 'E3', 'E3', 'E3', 'E3', 'E3', 'E3', 'E3'],
        nd, volume=0.08)

    # Gentle counter (sparse, high)
    counter = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'B4', 'R', 'A4', 'G4',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'G4', 'R', 'E4', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, _triangle_wave, volume=0.07, attack=0.06, release=0.30)

    bass = _render_deep_bass(
        ['E2', 'R', 'E2', 'R', 'A1', 'R', 'A1', 'R',
         'D2', 'R', 'D2', 'R', 'G1', 'R', 'G1', 'R',
         'C2', 'R', 'C2', 'R', 'A1', 'R', 'A1', 'R',
         'D2', 'R', 'G1', 'R', 'E2', 'R', 'E2', 'R'] * 2,
        nd, volume=0.12)

    return _mix_tracks(melody, pad, counter, bass)


def _compose_cine_town():
    """Cinematic town — peaceful, intimate, music-box quality with
    warm strings and a gentle hum.  Safe and welcoming."""
    bpm = 68
    nd = 60.0 / bpm

    # Delicate melody — like a lullaby
    melody = _render_strings(
        ['G4', 'A4', 'B4', 'R', 'D5', 'C5', 'B4', 'A4',
         'G4', 'R', 'E4', 'R', 'D4', 'E4', 'G4', 'R',
         'A4', 'B4', 'C5', 'R', 'B4', 'A4', 'G4', 'R',
         'E4', 'D4', 'E4', 'G4', 'A4', 'R', 'R', 'R',
         'B4', 'C5', 'D5', 'R', 'C5', 'B4', 'A4', 'G4',
         'E4', 'R', 'D4', 'R', 'E4', 'R', 'G4', 'R',
         'A4', 'R', 'G4', 'E4', 'D4', 'R', 'E4', 'R',
         'G4', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, volume=0.12)

    # Soft pad harmony
    pad = _render_pad(
        ['G3', 'G3', 'G3', 'G3', 'G3', 'G3', 'G3', 'G3',
         'C3', 'C3', 'C3', 'C3', 'C3', 'C3', 'C3', 'C3',
         'D3', 'D3', 'D3', 'D3', 'D3', 'D3', 'D3', 'D3',
         'G3', 'G3', 'G3', 'G3', 'G3', 'G3', 'G3', 'G3',
         'E3', 'E3', 'E3', 'E3', 'E3', 'E3', 'E3', 'E3',
         'C3', 'C3', 'C3', 'C3', 'C3', 'C3', 'C3', 'C3',
         'D3', 'D3', 'D3', 'D3', 'D3', 'D3', 'D3', 'D3',
         'G3', 'G3', 'G3', 'G3', 'G3', 'G3', 'G3', 'G3'],
        nd, volume=0.07)

    # Very faint choir hum on roots
    choir = _render_choir(
        ['G3', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'C3', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'D3', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'G3', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.04)

    bass = _render_deep_bass(
        ['G1', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'C2', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'D2', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'G1', 'R', 'R', 'R', 'R', 'R', 'R', 'R'] * 2,
        nd, volume=0.10)

    return _mix_tracks(melody, pad, choir, bass)


def _compose_cine_dungeon():
    """Cinematic dungeon — dark, sparse, and tense.  Lots of silence
    punctuated by eerie tones and a rumbling sub-bass drone."""
    bpm = 44
    nd = 60.0 / bpm

    # Eerie sparse melody — mostly silence
    melody = _render_melody(
        ['R', 'R', 'R', 'R', 'R', 'R', 'E4', 'R',
         'R', 'R', 'R', 'F4', 'R', 'R', 'E4', 'R',
         'R', 'R', 'C4', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'D4', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'G3', 'R', 'R',
         'R', 'R', 'A3', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'B3', 'R', 'R', 'C4', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd / 2, _triangle_wave, volume=0.12,
        attack=0.10, release=0.35)

    # Dark low pad — sustained dissonance
    pad = _render_pad(
        ['C2', 'C2', 'C2', 'C2', 'C2', 'C2', 'C2', 'C2',
         'C2', 'C2', 'C2', 'C2', 'C2', 'C2', 'C2', 'C2',
         'E2', 'E2', 'E2', 'E2', 'E2', 'E2', 'E2', 'E2',
         'E2', 'E2', 'E2', 'E2', 'E2', 'E2', 'E2', 'E2'],
        nd, volume=0.08)

    # Very faint high dissonant tone (tritone shimmer)
    eerie = _render_choir(
        ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'F#5', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'B4'],
        nd, volume=0.04)

    # Deep rumbling bass drone
    bass = _render_deep_bass(
        ['C1', 'C1', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'C1', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, volume=0.14)

    # Sparse percussion — just occasional deep thuds
    drums = _render_drums(
        ['K', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'K',
         'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R'],
        nd, volume=0.04)

    return _mix_tracks(melody, pad, eerie, bass, drums)


def _compose_cine_combat():
    """Cinematic combat — driving and heroic.  Pulsing bass,
    bold melody, urgent strings, and pounding drums."""
    bpm = 96
    nd = 60.0 / bpm

    # Bold lead melody
    melody = _render_melody(
        ['C4', 'C4', 'E4', 'G4', 'C5', 'R', 'G4', 'R',
         'A4', 'A4', 'G4', 'E4', 'C4', 'R', 'D4', 'R',
         'E4', 'E4', 'G4', 'C5', 'D5', 'R', 'C5', 'R',
         'G4', 'E4', 'C4', 'D4', 'E4', 'R', 'R', 'R',
         'F4', 'F4', 'A4', 'C5', 'D5', 'R', 'C5', 'A4',
         'G4', 'G4', 'E4', 'G4', 'A4', 'R', 'G4', 'R',
         'C5', 'B4', 'A4', 'G4', 'E4', 'R', 'D4', 'E4',
         'C4', 'R', 'R', 'R', 'C4', 'R', 'R', 'R'],
        nd, _square_wave, duty=0.25, volume=0.18,
        attack=0.02, release=0.10)

    # Urgent pulsing strings
    strings = _render_strings(
        ['C3', 'G3', 'C3', 'G3', 'C3', 'G3', 'C3', 'G3',
         'A2', 'E3', 'A2', 'E3', 'A2', 'E3', 'A2', 'E3',
         'F3', 'C4', 'F3', 'C4', 'F3', 'C4', 'F3', 'C4',
         'G2', 'D3', 'G2', 'D3', 'G2', 'D3', 'G2', 'D3',
         'F3', 'A3', 'F3', 'A3', 'F3', 'A3', 'F3', 'A3',
         'G2', 'D3', 'G2', 'D3', 'G2', 'D3', 'G2', 'D3',
         'A2', 'E3', 'A2', 'E3', 'A2', 'E3', 'A2', 'E3',
         'C3', 'G3', 'C3', 'G3', 'C3', 'G3', 'C3', 'G3'],
        nd, volume=0.09)

    # Driving bass
    bass = _render_deep_bass(
        ['C2', 'R', 'C2', 'R', 'A1', 'R', 'A1', 'R',
         'F2', 'R', 'F2', 'R', 'G1', 'R', 'G1', 'R',
         'F2', 'R', 'F2', 'R', 'G1', 'R', 'G1', 'R',
         'A1', 'R', 'A1', 'R', 'C2', 'R', 'C2', 'R'] * 2,
        nd, volume=0.14)

    # Driving drums
    drums = _render_drums(
        (['K', 'R', 'H', 'R', 'S', 'R', 'H', 'K',
          'R', 'H', 'R', 'K', 'S', 'R', 'H', 'R'] * 2) * 2,
        nd, volume=0.06)

    return _mix_tracks(melody, strings, bass, drums)


# ═══════════════════════════════════════════════════════════════
#  SOUNDTRACK STYLE REGISTRY
# ═══════════════════════════════════════════════════════════════

# Available styles (display label → internal key)
SOUNDTRACK_STYLES = [
    "Classic",
    "Dark & Moody",
    "Quiet",
    "Twin Peaks",
    "Epic Fantasy",
    "Cinematic",
]

# Composer functions keyed by style → area → list of variations
_STYLE_COMPOSERS = {
    "Classic": {
        "title":     [_compose_title],
        "overworld": [_compose_overworld_1, _compose_overworld_2,
                      _compose_overworld_3],
        "town":      [_compose_town_1, _compose_town_2, _compose_town_3],
        "dungeon":   [_compose_dungeon_1, _compose_dungeon_2,
                      _compose_dungeon_3],
        "combat":    [_compose_combat_1, _compose_combat_2,
                      _compose_combat_3],
    },
    "Dark & Moody": {
        "title":     [_compose_dark_title],
        "overworld": [_compose_dark_overworld],
        "town":      [_compose_dark_town],
        "dungeon":   [_compose_dark_dungeon],
        "combat":    [_compose_dark_combat],
    },
    "Quiet": {
        "title":     [_compose_quiet_title],
        "overworld": [_compose_quiet_overworld],
        "town":      [_compose_quiet_town],
        "dungeon":   [_compose_quiet_dungeon],
        "combat":    [_compose_quiet_combat],
    },
    "Twin Peaks": {
        "title":     [_compose_peaks_title],
        "overworld": [_compose_peaks_overworld],
        "town":      [_compose_peaks_town],
        "dungeon":   [_compose_peaks_dungeon],
        "combat":    [_compose_peaks_combat],
    },
    "Epic Fantasy": {
        "title":     [_compose_epic_title],
        "overworld": [_compose_epic_overworld],
        "town":      [_compose_epic_town],
        "dungeon":   [_compose_epic_dungeon],
        "combat":    [_compose_epic_combat],
    },
    "Cinematic": {
        "title":     [_compose_cine_title],
        "overworld": [_compose_cine_overworld],
        "town":      [_compose_cine_town],
        "dungeon":   [_compose_cine_dungeon],
        "combat":    [_compose_cine_combat],
    },
}


# ═══════════════════════════════════════════════════════════════
#  PUBLIC API — MusicManager
# ═══════════════════════════════════════════════════════════════

class MusicManager:
    """Manages procedurally-generated chiptune music for each game state.

    Each area has multiple track variations. When a track restarts (after
    a silence gap or on entering an area) a random variation is chosen so
    the music doesn't feel repetitive. Intermittent tracks fade in/out
    and pause between plays; continuous tracks (combat, title) loop one
    variation.

    Supports multiple soundtrack styles that can be switched at runtime.
    """

    # How long (seconds) to wait in silence before replaying a track.
    # Tracks not listed here loop continuously (e.g. combat, title).
    _PAUSE_BETWEEN = {
        "overworld": (14, 25),
        "town":      (12, 20),
        "dungeon":   (18, 30),
    }

    # Fade durations (ms) for tracks that fade in and out.
    _FADE_IN_MS = 2500
    _FADE_OUT_MS = 3000

    def __init__(self, style="Classic"):
        """Initialize the mixer and pre-generate all track variations."""
        import random as _rng
        self._rng = _rng

        self._style = style

        # Ensure mixer is initialized with our sample rate (mono, 16-bit)
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1,
                              buffer=1024)

        # track_name -> list of pygame.mixer.Sound (one per variation)
        self._variations = {}
        self._channel = None
        self._current = None       # area name ("overworld", etc.)
        self._current_idx = 0      # which variation is playing
        self._muted = False

        # Intermittent playback state
        self._paused = False
        self._pause_timer = 0.0
        self._playing_once = False

        # Pre-generate all variations for the active style
        self._generate_variations()

        # Reserve a channel for music playback
        num_channels = pygame.mixer.get_num_channels()
        if num_channels < 2:
            pygame.mixer.set_num_channels(4)
        self._channel = pygame.mixer.Channel(
            pygame.mixer.get_num_channels() - 1)

    def _generate_variations(self):
        """Pre-generate all track variations for the current style."""
        composers = _STYLE_COMPOSERS.get(self._style,
                                          _STYLE_COMPOSERS["Classic"])
        self._variations = {}
        for name, comp_fns in composers.items():
            sounds = []
            for comp_fn in comp_fns:
                wave = comp_fn()
                sounds.append(_to_sound(wave))
            self._variations[name] = sounds

    def set_style(self, style):
        """Switch to a different soundtrack style.

        Regenerates all track variations and restarts the current track
        (if any) with the new style.
        """
        if style == self._style:
            return
        if style not in _STYLE_COMPOSERS:
            return
        self._style = style
        # Stop current playback
        was_playing = self._current
        if self._channel and self._channel.get_busy():
            self._channel.stop()
        self._paused = False
        self._playing_once = False
        # Regenerate all sounds
        self._generate_variations()
        # Resume the same area with new style
        if was_playing:
            self._current = None  # force restart
            self.play(was_playing, fade_ms=self._FADE_IN_MS)

    @property
    def style(self):
        """Return the current soundtrack style name."""
        return self._style

    # ── Helpers ─────────────────────────────────────────────────

    def _is_intermittent(self, track_name):
        """Return True if this track should play with silence gaps."""
        return track_name in self._PAUSE_BETWEEN

    def _pick_variation(self, track_name):
        """Choose a random variation, avoiding the one that just played."""
        sounds = self._variations.get(track_name, [])
        if not sounds:
            return None, 0
        if len(sounds) == 1:
            return sounds[0], 0
        # Pick a different index than last time
        choices = [i for i in range(len(sounds)) if i != self._current_idx]
        idx = self._rng.choice(choices)
        return sounds[idx], idx

    def _start_pause(self):
        """Enter a silence gap before replaying a different variation."""
        bounds = self._PAUSE_BETWEEN.get(self._current)
        if bounds:
            lo, hi = bounds
            self._pause_timer = self._rng.uniform(lo, hi)
            self._paused = True
            self._playing_once = False

    # ── Public API ──────────────────────────────────────────────

    def play(self, track_name, fade_ms=None):
        """Start playing a random variation for the given area.

        Intermittent tracks play once then pause; continuous tracks loop.
        Always fades in.
        """
        if fade_ms is None:
            fade_ms = self._FADE_IN_MS

        # Reset intermittent state on track change
        self._paused = False
        self._pause_timer = 0.0
        self._playing_once = False

        if self._muted:
            self._current = track_name
            return
        if track_name == self._current and self._channel.get_busy():
            return

        sound, idx = self._pick_variation(track_name)
        if not sound:
            return

        if self._channel.get_busy():
            self._channel.fadeout(self._FADE_OUT_MS)

        self._current = track_name
        self._current_idx = idx

        if self._is_intermittent(track_name):
            self._channel.play(sound, loops=0, fade_ms=fade_ms)
            self._playing_once = True
        else:
            self._channel.play(sound, loops=-1, fade_ms=fade_ms)
            self._playing_once = False

    def update(self, dt):
        """Call every frame to manage intermittent playback.

        After a one-shot track finishes: fade out → silence gap →
        fade in a new random variation.
        """
        if self._muted or not self._current:
            return

        # Count down the silence gap
        if self._paused:
            self._pause_timer -= dt
            if self._pause_timer <= 0:
                self._paused = False
                # Pick a *different* variation for variety
                sound, idx = self._pick_variation(self._current)
                if sound:
                    self._current_idx = idx
                    self._channel.play(sound, loops=0,
                                       fade_ms=self._FADE_IN_MS)
                    self._playing_once = True
            return

        # Detect end of a one-shot playback → start silence gap
        if self._playing_once and not self._channel.get_busy():
            self._start_pause()

    def stop(self, fade_ms=None):
        """Stop any currently playing music with a fade out."""
        if fade_ms is None:
            fade_ms = self._FADE_OUT_MS
        if self._channel and self._channel.get_busy():
            self._channel.fadeout(fade_ms)
        self._current = None
        self._paused = False
        self._playing_once = False

    def toggle_mute(self):
        """Toggle music on/off. Returns new muted state."""
        self._muted = not self._muted
        if self._muted:
            if self._channel:
                self._channel.fadeout(self._FADE_OUT_MS)
            self._paused = False
            self._playing_once = False
        else:
            if self._current:
                sound, idx = self._pick_variation(self._current)
                if sound:
                    self._current_idx = idx
                    if self._is_intermittent(self._current):
                        self._channel.play(sound, loops=0,
                                           fade_ms=self._FADE_IN_MS)
                        self._playing_once = True
                    else:
                        self._channel.play(sound, loops=-1,
                                           fade_ms=self._FADE_IN_MS)
        return self._muted

    @property
    def is_muted(self):
        return self._muted


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
