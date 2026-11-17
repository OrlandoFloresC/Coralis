"""Automatic lyric repairs that do not need a dictionary.

Sinalefa (elision): in Spanish (and Latin, Italian...) a word ending in a vowel
and the next word starting with a vowel are sung on one note: "ho-ra‿en".
OCR reads the two words as two syllables, so that verse ends up with one
syllable more than the others in the measure. When that happens and two
neighbouring syllables of the verse can form a sinalefa, they are joined on
the note where the other verses have their syllable.
"""

from __future__ import annotations

from collections import Counter

from .issues import Issue
from .score import PARTNER, ChoralScore, lyric_voice

ELISION = "‿"
_VOWELS = set("aeiouáéíóúüAEIOUÁÉÍÓÚÜ")
_PUNCT = ".,;:!?¡¿\"'“”«»"


def _ends_in_vowel(text: str) -> bool:
    core = text.rstrip(_PUNCT)
    return bool(core) and (core[-1] in _VOWELS or core[-1] in "yY")


def _starts_with_vowel(text: str) -> bool:
    core = text.lstrip(_PUNCT)
    if not core:
        return False
    if core[0] in "hH" and len(core) > 1:  # "h" is silent in Spanish: "me‿hi-zo"
        core = core[1:]
    return core[0] in _VOWELS or core in ("y", "Y")


def _join_syllabic(first: str, second: str) -> str:
    begins = first in ("single", "begin")
    ends = second in ("single", "end")
    return {(True, True): "single", (True, False): "begin", (False, True): "end"}.get((begins, ends), "middle")


def merge_elisions(score: ChoralScore) -> list[Issue]:
    issues: list[Issue] = []
    verses = score.verses
    if verses < 2:
        return issues
    for m in score.measures:
        voice = lyric_voice(m)
        evs = [e for e in m.voices.get(voice, []) if e.lyrics]
        counts = {n: sum(1 for e in evs if n in e.lyrics) for n in range(1, verses + 1)}
        present = [c for c in counts.values() if c]
        if len(present) < 2:
            continue
        modal = Counter(present).most_common(1)[0][0]
        for n, c in counts.items():
            if c != modal + 1:
                continue
            others_onsets = {e.offset for e in evs for k in e.lyrics if k != n}
            sylls = [e for e in evs if n in e.lyrics]
            for a, b in zip(sylls, sylls[1:]):
                ta, sa = a.lyrics[n]
                tb, sb = b.lyrics[n]
                if sa not in ("single", "end") or sb not in ("single", "begin"):
                    continue  # must be the end of one word and the start of the next
                if not (_ends_in_vowel(ta) and _starts_with_vowel(tb)):
                    continue
                # keep the note the other verses sing on; drop the extra one
                target, drop = (b, a) if (b.offset in others_onsets and a.offset not in others_onsets) else (a, b)
                if target.offset not in others_onsets:
                    continue
                merged = f"{ta.rstrip(_PUNCT)}{ELISION}{tb}"
                del drop.lyrics[n]
                target.lyrics[n] = (merged, _join_syllabic(sa, sb))
                for alto in m.voices.get(PARTNER[voice], []):  # keep the copy in sync
                    if n in alto.lyrics and alto.offset in (a.offset, b.offset):
                        del alto.lyrics[n]
                        if alto.offset == target.offset:
                            alto.lyrics[n] = target.lyrics[n]
                issues.append(Issue("letra", "info",
                                    f"Compás {m.label}, estrofa {n}: «{ta}» + «{tb}» se unieron en una sola nota "
                                    f"como sinalefa («{merged}»).", m.index))
                break
    return issues
