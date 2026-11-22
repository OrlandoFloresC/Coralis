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
    def sure(d: dict) -> bool:   # the vote's own measure of agreement: notes without ties, or settled
        if d.get("settled") or max(d["weight"], d.get("notes_weight", 0)) >= TRUSTED * d["total"]:
            return True
        # every reading that has this measure saw the same (others skipped it: «Tú en cuya presencia»)
        return d.get("versions") == 1 and d["weight"] >= 0.4 * d["total"]

    return bool(m.votes) and all(v in m.votes and sure(m.votes[v]) for v in voices)


def _notes(m: Measure, v: str):
    return [(e.offset, e.duration, e.pitch) for e in m.voices.get(v, []) if not e.is_rest]


def _written_unison(score: ChoralScore, upper: str, lower: str, run: int = 4) -> set[int]:
    """Measures inside a printed unison passage: the two voices of the staff equal for `run` or more
    measures in a row, and the readings confirm it in at least one of them («Buscar a los perdidos»:
    32 measures of «murmullo unísono»). A voice lost by an engine does not make such a passage."""
    out: set[int] = set()
    stretch: list[Measure] = []

    def close() -> None:
        # 8 measures or more in a row: written so («Recuerdos de infancia», a «doble dúo»: two voices
        # per staff in unison for 40 measures); a voice is not lost identically for that long
        if len(stretch) >= max(8, run) or (len(stretch) >= run and any(_agreed(x, upper, lower) for x in stretch)):
            out.update(x.index for x in stretch)
        stretch.clear()

    for m in score.measures:
        a = _notes(m, upper)
        if a and a == _notes(m, lower):
            stretch.append(m)
        else:
            close()
    close()
    return out


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    issues = []
    last = len(score.measures) - 1
    written = {upper: _written_unison(score, upper, lower) for upper, lower, _ in PAIRS}
    for m in score.measures:
        # A voice silent for the whole measure while the others sing: in a hymn its
        # notes were almost surely lost or pushed into a neighbouring measure.
        singing = [v for v in VOICES if _notes(m, v)]
        if len(singing) >= 2:
            for v in VOICES:
                if m.solo and GROUP_OF[v] != m.solo:
                    continue  # a solo: the staff of this voice is not printed in this system
                if not any(w in singing for w in VOICES if GROUP_OF[w] == GROUP_OF[v]):
                    continue  # its whole staff rests (the other staff sings a solo): written so, not a lost voice
                if v not in singing and len(m.staves) >= 4 and m.voices.get(v) \
                        and all(e.is_rest and not e.filled for e in m.voices[v]):
                    continue  # open score, a rest printed on this voice's own staff (voices entering one by one)
                if v not in singing:
                    issues.append(Issue("unisono", "error",
                                        f"La voz de {VOICE_ES[v]} no tiene notas en este compás mientras "
                                        f"las demás cantan; el motor perdió sus notas o las movió de compás.",
                                        m.index, v))
        if m.index in (0, last):
            continue
        for upper, lower, text in PAIRS:
            a, b = _notes(m, upper), _notes(m, lower)
            if not a or a != b or m.solo == GROUP_OF[upper] or _agreed(m, upper, lower) or m.index in written[upper]:
                continue
            others = [v for v in VOICES if GROUP_OF[v] != GROUP_OF[upper]]
            if not any(_notes(m, v) for v in others):
                continue  # the other staff rests: a solo of this staff, sung by both its voices («Cristo, Cristo, Cristo»)
            attacks = sum(1 for e in m.voices[upper] if e.is_attack)
            whole_bar = len(a) == 1 and a[0][1] >= m.bar_length
            if attacks >= 2 or whole_bar:
                issues.append(Issue("unisono", "aviso",
                                    f"{text} en todo el compás; puede faltar una voz que el motor no leyó.",
                                    m.index, lower))
    return issues
