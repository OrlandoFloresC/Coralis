"""All staves of a measure must agree on time signature, key signature and tempo."""

from __future__ import annotations

from ..model.issues import Issue
from ..model.score import ChoralScore


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    issues = []
    prev_time = prev_key = None
    for m in score.measures:
        if len(m.staves) < 2:
            continue
        times = {s.time for s in m.staves}
        keys = {s.key_fifths for s in m.staves}
        tempos = {s.tempo for s in m.staves if s.tempo}
        if len(times) > 1:
            issues.append(Issue("coherencia", "error",
                                "Los pentagramas tienen compases distintos: "
                                + ", ".join(f"{a}/{b}" for a, b in sorted(times)) + ".", m.index))
        if len(keys) > 1:
            issues.append(Issue("coherencia", "error",
                                "Los pentagramas tienen armaduras distintas: "
                                + ", ".join(_key_es(k) for k in sorted(keys)) + ".", m.index))
        if len(tempos) > 1:
            issues.append(Issue("coherencia", "aviso",
                                "Indicaciones de tempo distintas: " + ", ".join(f"♩={t:g}" for t in sorted(tempos)) + ".",
                                m.index))
        # A change of time or key mid-piece is legal but a classic OMR misread: flag for a look.
        # A bar every voice fills exactly, with nothing added by the pipeline, confirms it.
        filled_exactly = all(
            sum(e.duration for e in evs) == m.bar_length and not any(e.filled for e in evs)
            for evs in m.voices.values() if any(not e.is_rest for e in evs))
        if prev_time and m.time != prev_time and not filled_exactly:
            issues.append(Issue("coherencia", "aviso",
                                f"Cambio de compás {prev_time[0]}/{prev_time[1]} → {m.time[0]}/{m.time[1]}.", m.index))
        if prev_key is not None and m.key_fifths != prev_key:
            issues.append(Issue("coherencia", "aviso",
                                f"Cambio de armadura {_key_es(prev_key)} → {_key_es(m.key_fifths)}.", m.index))
        prev_time, prev_key = m.time, m.key_fifths
    return issues


def _key_es(fifths: int) -> str:
    if fifths == 0:
        return "sin alteraciones"
    return f"{abs(fifths)} {'sostenido' if fifths > 0 else 'bemol'}{'s' if abs(fifths) > 1 else ''}"
