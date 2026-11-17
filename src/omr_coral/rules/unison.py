"""Two voices sharing a staff that are identical for a whole measure.

When the engine misses the notes of one voice on a shared staff (SA or TB), the
splitter can only copy the other voice, producing a whole-measure unison. Real
hymns rarely do this, except for a single short note (often the pickup) or the
final chord.
"""

from __future__ import annotations

from ..model.issues import Issue
from ..model.score import VOICES, ChoralScore, Measure
from .duration import VOICE_ES

PAIRS = (("soprano", "alto", "Contralto igual a soprano"), ("tenor", "bass", "Bajo igual a tenor/barítono"))
GROUP_OF = {"soprano": "upper", "alto": "upper", "tenor": "lower", "bass": "lower"}
TRUSTED = 0.75  # this share of the readings agreeing on both voices: the unison is printed


def _agreed(m: Measure, *voices: str) -> bool:
    """Most readings saw exactly this (after voting): a written unison, not a lost voice."""
    return bool(m.votes) and all(
        v in m.votes and m.votes[v]["weight"] >= TRUSTED * m.votes[v]["total"] for v in voices)


def _notes(m: Measure, v: str):
    return [(e.offset, e.duration, e.pitch) for e in m.voices.get(v, []) if not e.is_rest]


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    issues = []
    last = len(score.measures) - 1
    for m in score.measures:
        # A voice silent for the whole measure while the others sing: in a hymn its
        # notes were almost surely lost or pushed into a neighbouring measure.
        singing = [v for v in VOICES if _notes(m, v)]
        if len(singing) >= 2:
            for v in VOICES:
                if m.solo and GROUP_OF[v] != m.solo:
                    continue  # a solo: the staff of this voice is not printed in this system
                if v not in singing:
                    issues.append(Issue("unisono", "error",
                                        f"La voz de {VOICE_ES[v]} no tiene notas en este compás mientras "
                                        f"las demás cantan; el motor perdió sus notas o las movió de compás.",
                                        m.index, v))
        if m.index in (0, last):
            continue
        for upper, lower, text in PAIRS:
            a, b = _notes(m, upper), _notes(m, lower)
            if not a or a != b or m.solo == GROUP_OF[upper] or _agreed(m, upper, lower):
                continue
            attacks = sum(1 for e in m.voices[upper] if e.is_attack)
            whole_bar = len(a) == 1 and a[0][1] >= m.bar_length
            if attacks >= 2 or whole_bar:
                issues.append(Issue("unisono", "aviso",
                                    f"{text} en todo el compás; puede faltar una voz que el motor no leyó.",
                                    m.index, lower))
    return issues
