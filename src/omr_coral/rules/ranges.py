"""Every note must be inside the configured range of its voice."""

from __future__ import annotations

from music21 import pitch

from ..model.issues import Issue
from ..model.score import VOICES, ChoralScore
from .duration import VOICE_ES


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    ranges = cfg["voices"]["ranges"]
    far = cfg.get("rules", {}).get("range_error_semitones", 5)
    # a semitone or two past the usual range is written music (a quartet bass down to E♭2),
    # not a misreading: those are an octave or a clef off
    margin = cfg.get("rules", {}).get("range_margin_semitones", 2)
    issues = []
    tenor = tuple(pitch.Pitch(x).midi for x in ranges["tenor"])
    for v in VOICES:
        lo0, hi0 = (pitch.Pitch(x).midi for x in ranges[v])
        for m in score.measures:
            lo, hi = lo0, hi0
            # a men's quartet prints its upper voices in the octave treble clef: 1st tenor = the
            # soprano an octave lower; 2nd tenor = a tenor (an alto an octave lower is too low)
            if v in ("soprano", "alto") and _upper_octave_clef(m, v):
                lo, hi = (lo0 - 12, hi0 - 12) if v == "soprano" else tenor
            for e in m.voices.get(v, []):
                if e.midi is None or lo <= e.midi <= hi:
                    continue
                out = lo - e.midi if e.midi < lo else e.midi - hi
                if out <= margin:
                    continue
                where = "debajo" if e.midi < lo else "encima"
                issues.append(Issue(
                    "rango", "error" if out >= far else "aviso",
                    f"{VOICE_ES[v].capitalize()}: {_es(e.pitch)} está {out} semitono(s) por {where} "
                    f"de su rango ({_es(pitch.Pitch(lo).nameWithOctave)}–{_es(pitch.Pitch(hi).nameWithOctave)}).",
                    m.index, v))
    return issues


def _upper_octave_clef(m, voice: str = "soprano") -> bool:
    """The staff of this upper voice is in the treble clef with an 8 below: the staff of both
    (two staves, or an upper solo), or its own staff in an open score of four staves."""
    if len(m.staves) == 4:
        return m.staves[0 if voice == "soprano" else 1].clef == "G8vb"
    if not m.staves or m.staves[0].clef != "G8vb":
        return False
    return len(m.staves) == 2 or (len(m.staves) == 1 and m.solo == "upper")


def _es(name: str) -> str:
    """'E-4' -> 'mi♭4' (Spanish note names)."""
    p = pitch.Pitch(name)
    names = {"C": "do", "D": "re", "E": "mi", "F": "fa", "G": "sol", "A": "la", "B": "si"}
    acc = {-2: "𝄫", -1: "♭", 0: "", 1: "♯", 2: "𝄪"}.get(int(p.alter), "")
    return f"{names[p.step]}{acc}{p.octave}"
