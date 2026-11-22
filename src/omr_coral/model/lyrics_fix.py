"""Automatic lyric repairs that do not need a dictionary.

Sinalefa (elision): in Spanish (and Latin, Italian...) a word ending in a vowel
and the next word starting with a vowel are sung on one note: "ho-ra‿en".
OCR reads the two words as two syllables, so that verse ends up with one
syllable more than the others in the measure. When that happens and two
neighbouring syllables of the verse can form a sinalefa, they are joined on
the note where the other verses have their syllable.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .issues import Issue
from .score import VOICES, PARTNER, ChoralScore, lyric_voice

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


# --------------------------------------------------------------------------- OCR elision marks

_V = "aeiouáéíóúü"
_STRONG_PAIR = re.compile(r"([aeoáéíóú])([aeoáéíóú])", re.IGNORECASE)
# The OCR reads the elision tie "‿" as a letter "v": "doven" = "do‿en", "devho" = "de‿ho".
# A "v" between vowels inside ONE syllable cannot be Spanish ("a-ve", "nue-va": v starts a
# syllable). "...ve" at the end is left alone: English "love", "give".
_Y_V = re.compile(rf"^([yY])v(?=h?[{_V}])")
_V_MARK = re.compile(rf"([{_V}])v(h?[{_V}])", re.IGNORECASE)


def _v_to_mark(m: re.Match, spanish: bool = False) -> str:
    if not spanish and m.group(2).lower() == "e" and m.end() == len(m.string):
        return m.group(0)  # final "-ve": English "love", "give" (in Spanish one syllable is never "lave")
    s, i = m.string, m.start()
    if i > 0 and s[i - 1].lower() in _V and m.end() == len(s) and not s[:i].lower().endswith(("qu", "gu")):
        return m.group(0)  # after a diphthong, ending the word: "nueva", "nuevo" (not "dio‿or", "que‿el")
    return f"{m.group(1)}{ELISION}{m.group(2)}"


_I_FOR_L = re.compile(r"(?<![^\W\d_])I(?=[aeoáéó])")  # "Ia historia": no Spanish word starts "Ia/Ie/Io"
_I_INSIDE = re.compile(r"(?<=[a-záéíóúñü])I")  # "gIoria", "aIto": a capital I never follows a small letter
_ONE_FOR_L = re.compile(r"(?<=[a-záéíóúñ])1|1(?=[a-záéíóúñ])", re.IGNORECASE)  # "ta1" = "tal"
_BRACKET_FOR_J = re.compile(r"(?<![^\W\d_])\](?=[a-záéíóúñ])")  # "]eho-vá", "]e-sús"


# Spanish words have no apostrophe; a word does not start with "Il" + a, e, o (it is "ll").
_APOSTROPHE = re.compile(r"(?<=[^\W\d_])['’`´](?=[^\W\d_])")
_L_FOR_I = re.compile(r"(?<![^\W\d_])([mnsdrMNSDR])l(?=[a-záéíóúv])")
_I_FOR_LL = re.compile(r"(^|[\s¿¡(\"“])Il(?=[aeoáéó])")
_RN_FOR_M = re.compile(r"rn(?=[.,;:!?)»”]*$)")


_DIGIT_LETTER = str.maketrans({"1": "i", "0": "o", "5": "s"})
_SPANISH_MARKS = {"\u0301", "\u0303", "\u0308"}   # acute, tilde (ñ), diaeresis (ü)


def _ten_for_io(text: str) -> str:
    """Small «io» read as «10» («na-c10» = «na-ció»); a «1» after a consonant with no vowel after it
    is an «i» («di-v1-no»: no Spanish syllable ends in consonant + l like «vl»)."""
    text = re.sub(r"(?<=[^\W\d_])10|10(?=[^\W\d_])", "io", text)
    return re.sub(r"(?<=[b-df-hj-np-tv-zñB-DF-HJ-NP-TV-ZÑ])1(?![aeiouáéíóúAEIOUÁÉÍÓÚ])", "i", text)


def _digits_in_word(text: str) -> str:
    """Digits inside a word that has letters are misread letters (lyrics have no digits)."""
    return re.sub(r"[^\W_]*\d[^\W_]*",
                  lambda m: m.group(0).translate(_DIGIT_LETTER)
                  if any(c.isalpha() for c in m.group(0)) else m.group(0), text)


def _odd_marks(text: str) -> str:
    out = unicodedata.normalize("NFD", text)
    out = "".join(c for c in out if not (unicodedata.combining(c) and c not in _SPANISH_MARKS))
    return unicodedata.normalize("NFC", out)


def fix_ocr_letters(text: str, spanish: bool = True) -> str:
    """Letters the OCR confuses: "I" for "l", "]" for "J", "1" for "l" inside a word."""
    text = unicodedata.normalize("NFKC", text)  # typeset ligatures: "ﬁ" -> "fi"
    text = _BRACKET_FOR_J.sub("J", text)
    text = _ten_for_io(text)                # «na-c10» = «na-ció», «di-v1-no»: before "1" = "l" («ta1»)
    text = _ONE_FOR_L.sub("l", text)
    text = _I_INSIDE.sub("l", text)
    if not spanish:
        return text
    text = _APOSTROPHE.sub("", text)        # «p’e»: a speck read as an apostrophe
    text = _digits_in_word(text)            # what digits are left inside a word: 0 = o, 1 = i
    text = _odd_marks(text)                 # «tẹ»: a mark Spanish does not use (a speck under the letter)
    text = _RN_FOR_M.sub("m", text)         # «corn-pa-ñí-a»: "m" read as "rn"; no Spanish syllable ends in "rn"
    text = _I_FOR_LL.sub(r"\1ll", text)     # «Ila», «Ilan»: "ll" read as "Il"
    text = _L_FOR_I.sub(r"\1i", text)       # «mlva» = «mi‿a»: no word starts with "ml", "nl", "sl"...
    return _I_FOR_L.sub("l", text)


def fix_ocr_syllable(text: str, spanish: bool = True) -> str:
    """Repair elision marks the OCR misread or lost inside one syllable."""
    text = fix_ocr_letters(text, spanish)
    if ELISION in text or " " in text.strip():
        return text
    fixed = _V_MARK.sub(lambda m: _v_to_mark(m, spanish), text)
    if spanish:  # «yva» = «y‿a»: no Spanish word starts with "yv"
        fixed = _Y_V.sub(rf"\1{ELISION}", fixed)
    if spanish and fixed == text:
        # Two strong vowels never share a syllable in Spanish ("mo-a", "da-a"): a lost mark.
        fixed = _STRONG_PAIR.sub(lambda m: f"{m.group(1)}{ELISION}{m.group(2)}", text, count=1)
    return fixed


def fix_ocr_lyrics(score: ChoralScore, spanish: bool = True) -> int:
    """Apply fix_ocr_syllable to every syllable of a reading. Returns how many changed."""
    changed = 0
    for m in score.measures:
        for evs in m.voices.values():
            for e in evs:
                for n, (text, syl) in list(e.lyrics.items()):
                    new = fix_ocr_syllable(text, spanish)
                    if new != text:
                        e.lyrics[n] = (new, syl)
                        changed += 1
    return changed


_VOWELS = set("aeiouáéíóúü")


def split_glued_syllables(score: ChoralScore) -> int:
    """The OCR sometimes glues the syllables of several notes into one ("daslaspro" under
    «das las pro») and leaves the next notes empty. When a syllable is several Spanish
    syllables and as many following notes of that voice have no word on that line, spread
    them. A split between two vowels is not made: that is a sinalefa sung on one note.
    Returns how many glued syllables were spread."""
    from .lyrics_text import syllabify

    spread = 0
    for v in VOICES:
        evs = [e for m in score.measures for e in m.voices.get(v, []) if e.is_attack]
        lines = {n for e in evs for n in e.lyrics}
        for n in lines:
            for k, e in enumerate(evs):
                if n not in e.lyrics:
                    continue
                text, syl = e.lyrics[n]
                core = text.strip()
                glued = re.fullmatch(r"([^\W\d_]+[,;:.!?])([^\W\d_]+)", core)
                if glued and (k + 1 < len(evs)) and n not in evs[k + 1].lyrics:
                    # «ñor,mar» under «Se-ñor, mar-chan-do»: a word's end and the next word's start
                    head, tail = glued.groups()
                    e.lyrics[n] = (head, "end" if syl in ("middle", "end") else "single")
                    evs[k + 1].lyrics[n] = (tail, "begin" if syl in ("begin", "middle") else "single")
                    spread += 1
                    continue
                if not core.isalpha() or ELISION in core:
                    continue
                parts = syllabify(core)
                if len(parts) < 2 or any(a[-1].lower() in _VOWELS and b[0].lower() in _VOWELS
                                         for a, b in zip(parts, parts[1:])):
                    continue
                nxt = evs[k + 1:k + len(parts)]
                if len(nxt) < len(parts) - 1 or any(n in x.lyrics for x in nxt):
                    continue
                first = "begin" if syl in ("single", "begin") else "middle"
                last = "end" if syl in ("single", "end") else "middle"
                e.lyrics[n] = (parts[0], first)
                for j, (x, part) in enumerate(zip(nxt, parts[1:]), start=1):
                    x.lyrics[n] = (part, last if j == len(parts) - 1 else "middle")
                spread += 1
    return spread


def lower_ocr_capitals(score: ChoralScore) -> int:
    """«Vi-llas», «Voy», «Vi-vas»: the OCR reads a small «v» as «V» (same shape, other size). In the
    middle of a sentence a syllable starting with «V» and lowercase after it goes lowercase. Only
    «V»: other capitals in hymns are often meant («Señor», «Su», «Cristo»). Returns how many changed."""
    changed = 0
    for line in sorted({n for m in score.measures for evs in m.voices.values() for e in evs for n in e.lyrics}):
        prev = None
        for m in score.measures:
            seen = set()
            for v in ("soprano", "alto", "tenor", "bass"):
                for e in m.voices.get(v, []):
                    if line not in e.lyrics or (e.offset in seen and v != "soprano"):
                        continue
                    seen.add(e.offset)
                    text, syl = e.lyrics[line]
                    if (len(text) > 1 and text[0] == "V" and text[1:2].islower() and prev is not None
                            and not prev.rstrip().endswith((".", "!", "?", ";", ":"))):
                        e.lyrics[line] = ("v" + text[1:], syl)
                        changed += 1
                    if v == "soprano" or e.offset not in seen:
                        prev = e.lyrics[line][0]
    return changed
