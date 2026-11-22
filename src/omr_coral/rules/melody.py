"""Voice-leading checks: improbable leaps and broken ties.

Hymn voices move mostly by step or small leaps. A leap of a seventh or more than
an octave is very rare and usually means a misread note or clef. Octave leaps
are common (especially in the bass) and are allowed.
"""

from __future__ import annotations

from ..model.issues import Issue
from ..model.score import VOICES, ChoralScore
from .duration import VOICE_ES
from .ranges import _es


def _sounding(score: ChoralScore, v: str):
    """(measure_index, event, after_rest) for every note of the voice, in order."""
    rested = False
    for m in score.measures:
        for e in m.voices.get(v, []):
            if e.is_rest:
                rested = True
                continue
            yield m.index, e, rested
            rested = False


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    max_leap = cfg.get("rules", {}).get("max_leap_semitones", 9)
    issues = []
    for v in VOICES:
        prev = None
        for mi, e, after_rest in _sounding(score, v):
            if prev is not None:
                pmi, p = prev
                leap = abs(e.midi - p.midi)
                # after a rest a new phrase may start anywhere: in the 9 hand-made hymns all 12 such
                # leaps were right (between joined notes 1 of 14 was a misread)
                # a bass line leaps sevenths (sol2 → fa♯3) as a matter of course: in the 9 hand-made
                # hymns its 6 such leaps were all right; only past the octave it is suspicious
                limit = 12 if v == "bass" else max_leap
                if leap > limit and leap != 12 and not after_rest:
                    issues.append(Issue("melodia", "aviso",
                                        f"{VOICE_ES[v].capitalize()}: salto de {leap} semitonos "
                                        f"({_es(p.pitch)} → {_es(e.pitch)}), muy raro en un himno.", mi, v))
                # A tie must join two notes of the same pitch.
                if p.tie in ("start", "continue") and e.midi != p.midi:
                    issues.append(Issue("melodia", "aviso",
                                        f"{VOICE_ES[v].capitalize()}: ligadura entre notas distintas "
                                        f"({_es(p.pitch)} → {_es(e.pitch)}).", pmi, v))
                if e.tie in ("stop", "continue") and (p.midi != e.midi or p.tie not in ("start", "continue")):
                    issues.append(Issue("melodia", "aviso",
                                        f"{VOICE_ES[v].capitalize()}: ligadura que no viene de la nota anterior "
                                        f"({_es(e.pitch)}).", mi, v))
            prev = (mi, e)
        if prev and prev[1].tie in ("start", "continue"):
            issues.append(Issue("melodia", "aviso",
                                f"{VOICE_ES[v].capitalize()}: ligadura sin terminar al final.", prev[0], v))
    return issues
