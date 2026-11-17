"""Every note must be inside the configured range of its voice."""

from __future__ import annotations

from music21 import pitch

from ..model.issues import Issue
from ..model.score import VOICES, ChoralScore
from .duration import VOICE_ES


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    ranges = cfg["voices"]["ranges"]
    far = cfg.get("rules", {}).get("range_error_semitones", 5)
    issues = []
    for v in VOICES:
        lo, hi = (pitch.Pitch(x).midi for x in ranges[v])
        for m in score.measures:
            for e in m.voices.get(v, []):
                if e.midi is None or lo <= e.midi <= hi:
                    continue
                out = lo - e.midi if e.midi < lo else e.midi - hi
                where = "debajo" if e.midi < lo else "encima"
                issues.append(Issue(
                    "rango", "error" if out >= far else "aviso",
                    f"{VOICE_ES[v].capitalize()}: {_es(e.pitch)} está {out} semitono(s) por {where} "
                    f"de su rango ({ranges[v][0]}–{ranges[v][1]}).",
                    m.index, v))
    return issues


def _es(name: str) -> str:
    """'E-4' -> 'mi♭4' (Spanish note names)."""
    p = pitch.Pitch(name)
    names = {"C": "do", "D": "re", "E": "mi", "F": "fa", "G": "sol", "A": "la", "B": "si"}
    acc = {-2: "𝄫", -1: "♭", 0: "", 1: "♯", 2: "𝄪"}.get(int(p.alter), "")
    return f"{names[p.step]}{acc}{p.octave}"
