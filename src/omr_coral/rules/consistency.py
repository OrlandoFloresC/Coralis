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
        if prev_key is not None and m.key_fifths != prev_key and not _key_confirmed(score, m.index, prev_key):
            issues.append(Issue("coherencia", "aviso",
                                f"Cambio de armadura {_key_es(prev_key)} → {_key_es(m.key_fifths)}.", m.index))
        prev_time, prev_key = m.time, m.key_fifths
    return issues


_SHARPS = "FCGDAEB"   # order in which a key signature alters the letters (flats: reversed)


def _altered(fifths: int) -> dict[str, int]:
    """{letter: alteration} a key signature puts on the notes."""
    if fifths > 0:
        return {c: 1 for c in _SHARPS[:fifths]}
    return {c: -1 for c in _SHARPS[::-1][:-fifths]}


def _key_confirmed(score: ChoralScore, k: int, old: int) -> bool:
    """A printed key change («La cruz excelsa»: 1 ♭ → 2 ♭ → 3 ♭, double barlines): the new key lasts
    at least 4 measures and the notes sung there take its alterations (E♭ after 1 → 2 flats), not
    the old key's. A misread key flickers, or leaves the notes contradicting it."""
    ms = score.measures
    new = ms[k].key_fifths
    span = []
    for m in ms[k:k + 16]:
        if m.key_fifths != new:
            break
        span.append(m)
    if len(span) < 4:
        return False
    a, b = _altered(old), _altered(new)
    letters = {c for c in set(a) | set(b) if a.get(c, 0) != b.get(c, 0)}
    with_new = with_old = 0
    for m in span:
        for evs in m.voices.values():
            for e in evs:
                if e.is_rest or not e.pitch or not e.is_attack:
                    continue
                letter, alter = e.pitch[0], (e.pitch.count("#") - e.pitch.count("-"))
                if letter in letters:
                    with_new += alter == b.get(letter, 0)
                    with_old += alter == a.get(letter, 0)
    return with_new >= 2 and with_new >= 2 * with_old   # real naturals happen (V of V)


def _key_es(fifths: int) -> str:
    if fifths == 0:
        return "sin alteraciones"
    return f"{abs(fifths)} {'sostenido' if fifths > 0 else 'bemol'}{'s' if abs(fifths) > 1 else ''}"
