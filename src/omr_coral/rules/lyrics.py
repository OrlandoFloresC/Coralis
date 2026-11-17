"""Syllables vs. notes.

In a hymn every verse is sung to the same notes, so in each measure all verses
should have the same number of syllables, and no verse can have more syllables
than the melody has note attacks.
"""

from __future__ import annotations

from ..model.issues import Issue
from ..model.score import ChoralScore, lyric_voice


def check(score: ChoralScore, cfg: dict) -> list[Issue]:
    verses = score.verses
    if verses == 0:
        return []
    # The voice that carries the lyrics: the one with most syllables (usually soprano).
    ms = score.measures
    per_measure = [
        {n: sum(1 for e in m.voices.get(lyric_voice(m), []) if n in e.lyrics) for n in range(1, verses + 1)}
        for m in ms
    ]
    window = cfg.get("rules", {}).get("lyrics_window", 2)
    issues = []
    for i, m in enumerate(ms):
        evs = m.voices.get(lyric_voice(m), [])
        attacks = sum(1 for e in evs if e.is_attack)
        slots = sum(1 for e in evs if e.takes_syllable)
        # Only compare verses sung around here (some passages have fewer verses):
        # a verse counts if it has syllables in this measure, or both before and after it.
        before = per_measure[max(0, i - window): i]
        after = per_measure[i + 1: i + window + 1]
        active = [n for n in range(1, verses + 1)
                  if per_measure[i][n] or (any(c[n] for c in before) and any(c[n] for c in after))]
        counts = {n: per_measure[i][n] for n in active}
        if not any(counts.values()):
            continue
        if len(set(counts.values())) > 1:
            issues.append(Issue("letra", "aviso", _mismatch_message(counts, attacks, slots), m.index))
        over = [n for n, c in counts.items() if c > attacks]
        if over:
            issues.append(Issue("letra", "error",
                                f"La estrofa {_join(over)} tiene más sílabas que notas en este compás "
                                f"({attacks} nota(s) donde puede caer una sílaba).", m.index))

    # A verse present in the score but absent from a whole system: the OCR lost that line.
    # Only in multi-verse passages: a single lyric line (refrain, after a repeat) is normal.
    systems: dict[int, list[int]] = {}
    for i, m in enumerate(ms):
        systems.setdefault(m.system, []).append(i)
    if len(systems) > 1:
        for s, idxs in systems.items():
            found = {n for i in idxs for n in range(1, verses + 1) if per_measure[i][n]}
            missing = [n for n in range(1, verses + 1) if len(found) >= 2 and n not in found]
            if missing:
                issues.append(Issue("letra", "error",
                                    f"En el sistema {s} solo se detectaron {len(found)} de {verses} líneas de letra; "
                                    f"falta una línea y las estrofas pueden estar corridas (la 2 marcada como 1, etc.).",
                                    idxs[0]))

    # Syllables that cannot be real lyrics (OCR garbage).
    for m in ms:
        bad = []
        for e in m.voices.get(lyric_voice(m), []):
            for n, (text, _) in sorted(e.lyrics.items()):
                if _suspicious_syllable(text):
                    bad.append(f"«{text}» (estrofa {n})")
        if bad:
            issues.append(Issue("letra", "aviso", "Texto que no parece letra: " + ", ".join(bad) + ".", m.index))
    return issues


def _join(ns) -> str:
    ns = [str(n) for n in ns]
    return ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " y " + ns[-1]


def _mismatch_message(counts: dict[int, int], attacks: int, slots: int) -> str:
    """'La estrofa 2 tiene 3 sílabas y las estrofas 1 y 3 tienen 2...' (the odd ones out first)."""
    from collections import Counter

    modal = Counter(counts.values()).most_common(1)[0][0]
    odd = {n: c for n, c in counts.items() if c != modal}
    usual = [n for n, c in counts.items() if c == modal]
    sil = lambda c: f"{c} sílaba" + ("" if c == 1 else "s")  # noqa: E731
    parts = [f"la estrofa {n} tiene {sil(c)}" for n, c in odd.items()]
    rest = (f"la estrofa {_join(usual)} tiene" if len(usual) == 1 else f"las estrofas {_join(usual)} tienen")
    text = "; ".join(parts) + f", y {rest} {sil(modal)}"
    where = f"hay {slots} nota" + (" que lleva sílaba" if slots == 1 else "s que llevan sílaba")
    if slots != attacks:
        where += f" ({attacks} notas, {attacks - slots} unida(s) a la anterior por ligadura)"
    hint = ""
    if any(c > modal for c in odd.values()):
        hint = " Puede ser una sinalefa que el OCR separó, o una sílaba de más."
    elif any(c < modal for c in odd.values()):
        hint = " Probablemente el OCR no leyó una sílaba."
    return f"{text[0].upper()}{text[1:]}. En este compás {where}.{hint}"


_LEADING = "¡¿"
_TRAILING = ".,;:!?"
_ELISION = " ‿_~"  # spaces and elision ties (‿) join two syllables on one note
_VOWELS = set("aeiouyáéíóúüàèìòùâêîôûäëïö")


def _suspicious_syllable(text: str) -> bool:
    core = text.strip().lstrip(_LEADING).rstrip(_TRAILING)
    if not core or core != core.rstrip():
        return True  # empty, or punctuation detached by a space ("das' .")
    for k, ch in enumerate(core):
        if ch in "'’" and k > 0 and core[k - 1].isalpha():
            continue  # elision apostrophe: "sag'", "d'amor"
        if not (ch.isalpha() or ch in _ELISION or ch == "-"):
            return True  # quotes, stray apostrophes, digits, … are OCR noise in hymn lyrics
    words = [w for w in "".join(c if c not in _ELISION else " " for c in core).split() if w]
    for w in words:
        if not any(c.lower() in _VOWELS for c in w):
            return True  # a sung syllable always has a vowel
        if any(c.isupper() for c in w[1:]):
            return True  # "LSu": capitals inside a syllable
    return False
