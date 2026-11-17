"""Accidentals outside the key that nothing around them supports.

A chromatic note is considered supported (not suspicious) when:
  - the same altered note also appears in another voice of the same measure, or
  - it appears again in the same voice in this or a neighbouring measure, or
  - the voice moves on by step (≤ 2 semitones), as chromatic passing notes and
    leading tones do, or
  - it inflects the previous note of the same name (mi -> mi♭).
Real chromaticism usually leaves such traces; a misread accidental usually does not.
"""

from __future__ import annotations

from music21 import key

from ..model.issues import Issue
from ..model.score import VOICES, ChoralScore
from .duration import VOICE_ES
from .ranges import _es


def _key_alters(fifths: int) -> dict[str, float]:
    return {p.step: float(p.alter) for p in key.KeySignature(fifths).alteredPitches}


_STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_STEP_ES = {"C": "do", "D": "re", "E": "mi", "F": "fa", "G": "sol", "A": "la", "B": "si"}


def _diatonic_enharmonic(midi: int, in_key: dict[str, float]) -> str | None:
    """Name of the in-key note with the same sound as `midi`, if any (e.g. fa♭ -> 'mi')."""
    for step, base in _STEP_SEMITONES.items():
        if (base + in_key.get(step, 0.0)) % 12 == midi % 12:
            acc = {-1: "♭", 1: "♯"}.get(int(in_key.get(step, 0.0)), "")
            return f"{_STEP_ES[step]}{acc}"
    return None


def _next_note(ms, i, v, e):
    """Next sounding note (different attack) in the same voice, in this or the next measure."""
    later = [x for x in ms[i].voices.get(v, []) if x.offset > e.offset and x.is_attack]
    if not later and i + 1 < len(ms):
        later = [x for x in ms[i + 1].voices.get(v, []) if x.is_attack]
    return later[0] if later else None


def _prev_note(ms, i, v, e):
    """Previous sounding note in the same voice, in this or the previous measure."""
    earlier = [x for x in ms[i].voices.get(v, []) if x.offset < e.offset and not x.is_rest]
    if not earlier and i > 0:
        earlier = [x for x in ms[i - 1].voices.get(v, []) if not x.is_rest]
    return earlier[-1] if earlier else None


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    issues = []
    ms = score.measures
    for i, m in enumerate(ms):
        in_key = _key_alters(m.key_fifths)
        chroma = {}  # voice -> set of (step, alter) chromatic notes in this measure
        for v in VOICES:
            chroma[v] = {(e.step, e.alter) for e in m.voices.get(v, [])
                         if e.step and e.alter != in_key.get(e.step, 0.0)}
        for v in VOICES:
            for e in m.voices.get(v, []):
                if not e.step or e.alter == in_key.get(e.step, 0.0) or not e.is_attack:
                    continue
                # Spelled as a chromatic note but equal to a note of the key (fa♭ = mi in F major):
                # a composer would write the diatonic note, so this is almost surely a misread.
                diatonic_twin = _diatonic_enharmonic(e.midi, in_key)
                if diatonic_twin:
                    issues.append(Issue(
                        "alteraciones", "error",
                        f"{VOICE_ES[v].capitalize()}: {_es(e.pitch)} suena igual que {diatonic_twin}, "
                        f"que sí está en la tonalidad; casi seguro es una alteración mal leída.",
                        m.index, v))
                    continue
                pc = (e.step, e.alter)
                other_voices = any(pc in chroma[o] for o in VOICES if o != v)
                same_voice = sum(1 for x in m.voices[v] if (x.step, x.alter) == pc) > 1
                neighbours = any(
                    (x.step, x.alter) == pc
                    for j in (i - 1, i + 1) if 0 <= j < len(ms)
                    for x in ms[j].voices.get(v, [])
                )
                nxt = _next_note(ms, i, v, e)
                resolves = nxt is not None and abs(nxt.midi - e.midi) <= 2
                prv = _prev_note(ms, i, v, e)
                inflection = prv is not None and prv.step == e.step and prv.alter != e.alter  # e.g. mi -> mi♭
                if not (other_voices or same_voice or neighbours or resolves or inflection):
                    issues.append(Issue(
                        "alteraciones", "aviso",
                        f"{VOICE_ES[v].capitalize()}: {_es(e.pitch)} no pertenece a la tonalidad y aparece aislado.",
                        m.index, v))
    return issues
