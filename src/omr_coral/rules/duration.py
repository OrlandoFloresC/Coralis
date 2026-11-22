"""Each voice must fill its measure exactly.

Allowed exceptions: the pickup, the final measure, and a measure split in two by a
repeat or double barline (two consecutive short measures, the same length in every
voice, adding up to one full bar).
"""

from __future__ import annotations

from fractions import Fraction

from ..model.issues import Issue
from ..model.score import VOICES, ChoralScore, Measure, fmt_beats

VOICE_ES = {"soprano": "soprano", "alto": "contralto", "tenor": "tenor/barítono", "bass": "bajo"}


def _ends(m: Measure) -> dict[str, Fraction | None]:
    out = {}
    for v in VOICES:
        sounding = [e for e in m.voices.get(v, []) if not e.filled]
        out[v] = max((e.end for e in sounding), default=None)
    return out


def _uniform_short(m: Measure) -> Fraction | None:
    """Common length if every voice is equally short, else None."""
    ends = set(_ends(m).values())
    if len(ends) == 1:
        (e,) = ends
        if e is not None and e < m.duration:
            return e
    return None


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    issues = []
    ms = score.measures
    split_ok: set[int] = set()
    # the piece's usual bar: the two halves of a cut bar may have been given another time each
    usual = max({m.bar_length for m in ms}, key=lambda L: sum(1 for m in ms if m.bar_length == L)) if ms else 0
    for i in range(len(ms) - 1):
        a, b = _uniform_short(ms[i]), _uniform_short(ms[i + 1])
        if a and b and a + b in (ms[i].bar_length, usual) and not ms[i].pickup:
            split_ok |= {i, i + 1}

    # the last measure that sounds: a silent measure an engine added after the end does not make
    # the real final measure (completing the pickup) look short
    last = max((m.index for m in ms if any(not e.is_rest for evs in m.voices.values() for e in evs)),
               default=len(ms) - 1)
    for m in ms:
        ends = _ends(m)
        for v in VOICES:
            evs = m.voices.get(v, [])
            end = ends[v]
            if end is None:
                issues.append(Issue("duracion", "error", f"La voz de {VOICE_ES[v]} está vacía.", m.index, v))
                continue
            gaps = sum((e.duration for e in evs if e.filled and e.end <= end), start=0)
            if gaps:
                issues.append(Issue("duracion", "error",
                                    f"{VOICE_ES[v].capitalize()}: faltan {fmt_beats(gaps)} tiempo(s) dentro del compás.",
                                    m.index, v))
            if end > m.duration:
                issues.append(Issue("duracion", "error",
                                    f"{VOICE_ES[v].capitalize()}: suma {fmt_beats(end)} tiempos y el compás "
                                    f"{m.time[0]}/{m.time[1]} tiene {fmt_beats(m.duration)}.", m.index, v))
            elif end < m.duration and m.index != last and m.index not in split_ok:
                issues.append(Issue("duracion", "error",
                                    f"{VOICE_ES[v].capitalize()}: suma {fmt_beats(end)} tiempos y el compás "
                                    f"pide {fmt_beats(m.duration)}.", m.index, v))
    return issues
