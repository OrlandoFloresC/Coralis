"""Lyrics from a text file, placed on the notes.

File format (UTF-8), one verse per paragraph, blank line between verses:

    1. Sublime gracia del Señor,
    que a mí, pecador, salvó...

    2. Mi corazón enterneció...

Verse numbers ("1.", "2)") are optional. Words are split into syllables
automatically (Spanish rules); to force a split, write hyphens: "Su-bli-me".

Placement: the syllables of each verse are aligned with the notes that take a
syllable (soprano attacks not inside a slur), guided by what the OCR read in
each place. Two syllables meeting vowel to vowel across words may share a note
(sinalefa, written "me‿el"); notes may stay without syllable (melisma).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .issues import Issue
from .lyrics_fix import ELISION
from .score import PARTNER, VOICES, ChoralScore, Event, lyric_voice

# --------------------------------------------------------------------------- Spanish syllables

_STRONG = set("aeoáéíóú")      # accented i/u are strong (they break a diphthong: "guí-a")
_WEAK = set("iuü")
_VOWELS = _STRONG | _WEAK
_INSEPARABLE = {"pr", "br", "tr", "dr", "cr", "kr", "gr", "fr", "pl", "bl", "cl", "kl", "gl", "fl", "tl",
                "ch", "ll", "rr", "qu", "gu"}  # qu/gu: the silent u belongs to the consonant


def _is_vowel(word: str, i: int) -> bool:
    c = word[i].lower()
    if c in _VOWELS:
        # "u" in que/qui/gue/gui is silent: part of the consonant
        if c == "u" and i > 0 and word[i - 1].lower() in "qg" and i + 1 < len(word) and word[i + 1].lower() in "eéií":
            return False
        return True
    if c == "y":  # vowel at the end of a word or alone: "rey", "y"
        return i == len(word) - 1 and (i == 0 or not _is_vowel(word, i - 1) or True)
    return False


def syllabify(word: str) -> list[str]:
    """Split one Spanish word into syllables: 'corazón' -> ['co', 'ra', 'zón']."""
    if "-" in word:
        return [p for p in word.split("-") if p]
    letters = [c for c in word]
    n = len(letters)
    if n == 0:
        return []
    # nuclei: maximal vowel runs, split where two vowels form a hiatus
    nuclei: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if not _is_vowel(word, i):
            i += 1
            continue
        start = i
        while i + 1 < n and _is_vowel(word, i + 1):
            a, b = word[i].lower(), word[i + 1].lower()
            if a in _STRONG and b in _STRONG:  # hiatus: "le-er", "guí-a"
                break
            i += 1
        nuclei.append((start, i + 1))
        i += 1
    if len(nuclei) <= 1:
        return [word]
    cuts = []
    for (_, end), (nxt, _) in zip(nuclei, nuclei[1:]):
        cons = word[end:nxt]
        k = len(cons)
        if k == 0:
            cut = end                                  # hiatus
        elif k == 1:
            cut = end                                  # co-ra
        elif k == 2:
            cut = end if cons.lower() in _INSEPARABLE else end + 1   # su-bli / per-di
        elif k == 3:
            cut = end + 1 if cons[1:].lower() in _INSEPARABLE else end + 2  # en-tre / ins-tan
        else:
            cut = end + 2                              # ins-tru
        cuts.append(cut)
    parts, prev = [], 0
    for c in cuts:
        parts.append(word[prev:c])
        prev = c
    parts.append(word[prev:])
    return [p for p in parts if p]


@dataclass
class Syl:
    text: str
    syllabic: str  # single | begin | middle | end
    word_start: bool
    word_end: bool


_WORD = re.compile(r"[\wáéíóúüñÁÉÍÓÚÜÑ'’-]+[.,;:!?»”\"]*|[¡¿«“\"]+", re.UNICODE)


def verse_syllables(text: str) -> list[Syl]:
    text = re.sub(r"^\s*\d+\s*[.)-]\s*", "", text)  # leading verse number "1." / "2)"
    out: list[Syl] = []
    pending_prefix = ""
    for tok in _WORD.findall(text):
        if not any(ch.isalnum() for ch in tok):
            pending_prefix += tok  # opening ¡ ¿ « stick to the next word
            continue
        m = re.match(r"^(.*?)([.,;:!?»”\"]*)$", tok)
        core, punct = m.group(1), m.group(2)
        sy = syllabify(core)
        for k, s in enumerate(sy):
            first, last = k == 0, k == len(sy) - 1
            txt = (pending_prefix if first else "") + s + (punct if last else "")
            syl = "single" if first and last else "begin" if first else "end" if last else "middle"
            out.append(Syl(txt, syl, first, last))
        pending_prefix = ""
    return out


def read_lyrics_file(path: Path) -> list[list[Syl]]:
    text = path.read_text(encoding="utf-8-sig")
    verses = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = re.sub(r"^\s*\d+\s*[.)-]\s*", "", block.strip())  # "1. " / "2) "
        if block:
            verses.append(verse_syllables(block.replace("\n", " ")))
    return verses


# --------------------------------------------------------------------------- placement


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if c.isalpha())


def _sim(a: str | None, b: str) -> float:
    """1 = same syllable; ~0 = unrelated. Unknown OCR (None) is neutral."""
    if a is None:
        return 0.3
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return 0.3
    # Levenshtein distance
    prev = list(range(len(y) + 1))
    for i, cx in enumerate(x, 1):
        cur = [i]
        for j, cy in enumerate(y, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
        prev = cur
    return 1 - prev[-1] / max(len(x), len(y))


def _can_merge(a: Syl, b: Syl) -> bool:
    if not (a.word_end and b.word_start):
        return False
    x, y = _norm(a.text), _norm(b.text)
    if y.startswith("h"):
        y = y[1:]
    return bool(x) and bool(y) and x[-1] in "aeiouy" and y[0] in "aeiouy"


def place_verse(slots: list[Event], ocr: list[str | None], syls: list[Syl],
                sung: list[bool] | None = None) -> list[tuple[int, str, str]]:
    """Dynamic programming: assign syllables to slots. Returns [(slot, text, syllabic)].

    ocr[j]:  what the OCR read for this verse on slot j (None = nothing).
    sung[j]: whether the OCR found a syllable on slot j in ANY verse. A note where no
             verse has a syllable is almost surely a melisma (e.g. the second of two
             beamed eighths), so putting a syllable there is expensive.
    """
    sung = sung or [True] * len(slots)
    n, m = len(syls), len(slots)
    NEG = float("-inf")
    best = [[NEG] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            cur = best[i][j]
            if cur == NEG or j == m:
                continue
            # leave slot j without a syllable (melisma); costly if the OCR saw one there
            # (on a melisma note an OCR syllable is weak evidence: OCR lines are often shifted)
            pen = (0.6 if ocr[j] else 0.3) if sung[j] else 0.05
            if cur - pen > best[i][j + 1]:
                best[i][j + 1], back[i][j + 1] = cur - pen, (i, j, "skip")
            place_bonus = 0.0 if sung[j] else -1.5  # a syllable on a melisma note: rare in hymns
            if i < n:  # one syllable on slot j
                sc = cur + _sim(ocr[j], syls[i].text) + place_bonus
                if sc > best[i + 1][j + 1]:
                    best[i + 1][j + 1], back[i + 1][j + 1] = sc, (i, j, "one")
            if i + 1 < n and _can_merge(syls[i], syls[i + 1]):  # sinalefa: two on slot j
                merged = syls[i].text + ELISION + syls[i + 1].text
                # the OCR often reads only one half of a sinalefa ("ra" for "ra‿en")
                sim = max(_sim(ocr[j], merged), _sim(ocr[j], syls[i].text), _sim(ocr[j], syls[i + 1].text))
                sc = cur + sim - 0.25 + place_bonus
                if sc > best[i + 2][j + 1]:
                    best[i + 2][j + 1], back[i + 2][j + 1] = sc, (i, j, "two")
    if best[n][m] == NEG:
        return []  # more syllables than notes even with every sinalefa
    out = []
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj, kind = back[i][j]
        if kind == "one":
            s = syls[pi]
            out.append((pj, s.text, s.syllabic))
        elif kind == "two":
            a, b = syls[pi], syls[pi + 1]
            first = a.syllabic in ("single", "begin")
            last = b.syllabic in ("single", "end")
            syl = "single" if first and last else "begin" if first else "end" if last else "middle"
            out.append((pj, a.text + ELISION + b.text, syl))
        i, j = pi, pj
    return list(reversed(out))


def apply_lyrics_text(cs: ChoralScore, verses: list[list[Syl]]) -> list[Issue]:
    # the words go on the soprano, or on the men where the women are silent
    slots: list[Event] = [e for m in cs.measures for e in m.voices.get(lyric_voice(m), []) if e.takes_syllable]
    owner = {id(e): m for m in cs.measures for e in m.voices.get(lyric_voice(m), [])}
    issues: list[Issue] = []
    # In a homophonic hymn the syllables fall where the voices move together: a soprano
    # note that no other voice attacks with is a melisma (the 2nd of two beamed eighths
    # over a held chord). Without other voices, every note may take a syllable.
    others = [v for v in ("alto", "tenor", "bass")
              if any(not e.is_rest for m in cs.measures for e in m.voices.get(v, []))]

    def together(e: Event) -> bool:
        m = owner[id(e)]
        mine = lyric_voice(m)
        return not others or any(x.offset == e.offset and x.is_attack
                                 for v in others if v != mine for x in m.voices.get(v, []))

    sung = [together(e) for e in slots]
    ocr_all = [{k: t for k, (t, _) in e.lyrics.items()} for e in slots]
    for n, syls in enumerate(verses, start=1):
        ocr = [d.get(n) for d in ocr_all]
        placed = place_verse(slots, ocr, syls, sung)
        if not placed:
            issues.append(Issue("letra", "error",
                                f"La estrofa {n} del archivo de letra tiene {len(syls)} sílabas y solo hay "
                                f"{len(slots)} notas para ponerlas; se dejó la letra leída por el OCR."))
            continue
        # replace this verse everywhere (soprano and the alto copies)
        for m in cs.measures:
            for v in VOICES:
                for e in m.voices.get(v, []):
                    e.lyrics.pop(n, None)
        for j, text, syl in placed:
            e = slots[j]
            e.lyrics[n] = (text, syl)
            m = owner[id(e)]
            for a in m.voices.get(PARTNER[lyric_voice(m)], []):
                if a.offset == e.offset and a.is_attack:
                    a.lyrics[n] = (text, syl)
        issues.append(Issue("letra", "info",
                            f"Estrofa {n}: letra tomada del archivo de texto ({len(syls)} sílabas)."))
    return issues
