"""Raise or lower a whole hymn by some semitones (to sing it in another key).

The interval is spelled so that the new key is the simplest one for that sound (at most 6 sharps
or flats): one semitone up from G major gives A♭ major, not G♯ major."""

from __future__ import annotations

from music21 import interval, key, pitch

from .corrections import _set_pitch
from .score import ChoralScore


def _major_tonic(fifths: int) -> str:
    return key.KeySignature(fifths).asKey("major").tonic.name


def key_after(fifths: int, semitones: int) -> int:
    """The key signature (in fifths, −6…+6) of a key moved by those semitones."""
    x = (fifths + 7 * semitones) % 12   # every semitone up is 7 fifths
    return x - 12 if x >= 6 else x   # F♯/G♭: G♭ (flats are more common in hymnals)


def interval_for(fifths: int, semitones: int) -> interval.Interval:
    """The interval from the key with those fifths to the simplest key that many semitones away."""
    p1 = pitch.Pitch(_major_tonic(fifths) + "4")
    p2 = pitch.Pitch(_major_tonic(key_after(fifths, semitones)) + "4")
    while p2.ps - p1.ps > semitones:
        p2.octave -= 1
    while p2.ps - p1.ps < semitones:
        p2.octave += 1
    return interval.Interval(p1, p2)


def transpose_score(cs: ChoralScore, semitones: int) -> ChoralScore:
    """Move every note and every key signature (in place). 0 leaves the score as it is."""
    if not semitones or not cs.measures:
        return cs
    intv = interval_for(cs.measures[0].key_fifths, semitones)
    for m in cs.measures:
        m.key_fifths = _moved_key(m.key_fifths, intv)
        for st in m.staves:
            st.key_fifths = _moved_key(st.key_fifths, intv)
        for evs in m.voices.values():
            for e in evs:
                if e.pitch is None:
                    continue
                p = pitch.Pitch(e.pitch).transpose(intv)
                if p.accidental is not None and abs(p.accidental.alter) > 1:
                    p = p.simplifyEnharmonic()   # no double sharps or flats from a printed accidental
                _set_pitch(e, p)
    return cs


def _moved_key(fifths: int, intv: interval.Interval) -> int:
    k = key.KeySignature(fifths).transpose(intv)
    return k.sharps


def shift_label(semitones: int) -> str:
    """For file names: « (2 semitonos más alto)»."""
    if not semitones:
        return ""
    n = abs(semitones)
    return f" ({n} semitono{'s' if n > 1 else ''} más {'alto' if semitones > 0 else 'bajo'})"
