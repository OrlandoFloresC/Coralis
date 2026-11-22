"""Vote between several readings (engines x image variants) of the same score.

For every measure and every voice:
  1. collect the version each reading gives (after aligning measures),
  2. keep the versions that pass the rules (no error, then no warning),
  3. among those, take the one with most (weighted) votes.

Lyrics are voted separately, per measure and verse, among readings that have them,
then attached to the chosen soprano/alto notes.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from fractions import Fraction
from dataclasses import dataclass, field
from pathlib import Path

from ..model.issues import Issue
from ..model.score import PARTNER, VOICES, ChoralScore, Event, Marks, _bbox, _geometry, lyric_voice
from ..rules import run_rules
from ..rules.lyrics import _suspicious_syllable
from .align import align

# Preferred image for the crops shown in the report: the most natural-looking one.
CROP_PREFERENCE = ("original", "enderezada", "contraste", "limpia", "binaria", "escala")
# Image used to find noteheads: the largest and cleanest one.
GEOMETRY_PREFERENCE = ("escala", "limpia", "enderezada", "original", "contraste", "binaria")


@dataclass
class Candidate:
    engine: str
    variant: str
    score: ChoralScore
    image_dir: Path
    weight: float = 1.0
    issues: list[Issue] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.engine}/{self.variant}"


def _badness(c: Candidate) -> tuple[int, int]:
    errors = {i.measure for i in c.issues if i.severity == "error" and i.rule != "letra"}
    avisos = {i.measure for i in c.issues if i.severity == "aviso" and i.rule != "letra"}
    return len(errors), len(avisos)


def _sounding(c: Candidate) -> int:
    """Measures with at least one note. Silent measures do not count: an engine may invent
    empty ones (a page start, a repeat sign) or lose a solo system, and both change the
    plain measure count without changing the music."""
    return sum(1 for m in c.score.measures if any(not e.is_rest for evs in m.voices.values() for e in evs))


def choose_reference(cands: list[Candidate]) -> Candidate:
    counts = defaultdict(float)
    for c in cands:
        counts[_sounding(c)] += c.weight
    modal = max(counts, key=lambda n: (counts[n], n))
    return min(cands, key=lambda c: (_sounding(c) != modal, *_badness(c),
                                     not any(m.bbox for m in c.score.measures)))


def _content(events: list[Event]) -> tuple:
    return tuple((e.offset, e.pitch, e.duration, e.tie) for e in events if not e.filled)


def _engine_settles(best: dict, groups: dict, engines_of: dict) -> bool:
    """(Nearly) every reading of one engine (at least 3 readings, ¾ of them) chose this version,
    it breaks no rule, and the
    other engine's readings do not agree among themselves (none of its versions has more than
    half of them): one engine sure, the other guessing."""
    if best["errors"] or best["avisos"]:
        return False
    eng = {s.split("/")[0] for s in best["sources"]}
    if len(eng) != 1:
        return False
    (e,) = eng
    if engines_of.get(e, 0) < 3 or sum(1 for s in best["sources"] if s.startswith(e + "/")) < 0.75 * engines_of[e]:
        return False
    for other, n in engines_of.items():
        if other == e or not n:
            continue
        top = max((sum(1 for s in g["sources"] if s.startswith(other + "/")) for g in groups.values()), default=0)
        if top > n / 2:
            return False
    return True


def _untied(key: tuple) -> tuple:
    return tuple((o, p, d) for o, p, d, _ in key)


def key_of(group: dict, groups: dict) -> tuple:
    return next(k for k, g in groups.items() if g is group)


def _voice_issues(c: Candidate, mi: int, v: str) -> tuple[int, int]:
    errs = avs = 0
    for i in c.issues:
        if i.measure != mi or i.rule == "letra" or (i.voice not in (None, v)):
            continue
        if i.severity == "error":
            errs += 1
        elif i.severity == "aviso":
            avs += 1
    return errs, avs


def _lyric_lines(c: Candidate, mi: int) -> dict[int, list[tuple]]:
    """verse -> [(offset, text, syllabic)] on the lyrics-carrying voice (soprano)."""
    out: dict[int, list[tuple]] = defaultdict(list)
    mm = c.score.measures[mi]
    lead = lyric_voice(mm)
    for e in mm.voices.get(lead, []):
        for n, (text, syl) in e.lyrics.items():
            if any(ch.lower() in _VOWELS for ch in text):  # "F", "-", "'" can never be a sung syllable
                out[n].append((e.offset, text, syl))
    # the staff partner's syllables while the lead voice holds a note («El camino es escabroso»:
    # the soprano holds while the alto echoes «(muy can-sa-dos)»)
    shared = len(mm.staves) < 4   # one staff per voice («Yo pensaba que el hombre»): each sings its own words
    for e in (mm.voices.get(PARTNER[lead], []) if shared else []):
        if not e.is_attack or not holding(mm.voices.get(lead, []), e.offset):
            continue
        for n, (text, syl) in e.lyrics.items():
            if any(ch.lower() in _VOWELS for ch in text) and all(o != e.offset for o, _, _ in out[n]):
                out[n].append((e.offset, text, syl))
    for n in out:
        out[n].sort(key=lambda x: x[0])
    return out


def holding(events: list[Event], offset) -> bool:
    """The voice is sustaining a note (attacked earlier) at this offset."""
    return any(e.pitch and e.offset < offset < e.end for e in events)


_VOWELS = set("aeiouyáéíóúüàèìòùâêîôûäëïö")


def _title(cands: list[Candidate]) -> str | None:
    """Real title of the piece: engines that read it (Audiveris) beat file names (homr)."""
    titles = [t for t in ((c.score.title or "").strip() for c in cands)
              if t and not t.lower().endswith((".musicxml", ".xml", ".mxl", ".png", ".jpg", ".pdf"))]
    if not titles:
        return None
    from collections import Counter

    from ..model.lyrics_fix import fix_ocr_letters

    return fix_ocr_letters(Counter(titles).most_common(1)[0][0])  # the title most readings agree on


def vote(cands: list[Candidate], cfg: dict) -> tuple[ChoralScore, list[Issue], dict]:
    for c in cands:
        c.issues = run_rules(c.score, cfg)
    ref = choose_reference(cands)
    maps = {id(c): (align(ref.score.measures, c.score.measures) if c is not ref
                    else {i: i for i in range(len(ref.score.measures))}) for c in cands}
    total = sum(c.weight for c in cands)
    min_agree = cfg.get("voting", {}).get("min_agreement", 0.5)
    marks_engines = set(cfg.get("voting", {}).get("marks_engines", ["audiveris"]))

    lines_per_system: dict[int, dict[int, set[int]]] = {}
    for c in cands:
        per: dict[int, set[int]] = defaultdict(set)
        for mm in c.score.measures:
            for e in mm.voices.get(lyric_voice(mm), []):
                per[mm.system].update(e.lyrics)
        lines_per_system[id(c)] = per
    n_verses = max((c.score.verses for c in cands), default=0)

    voted = copy.deepcopy(ref.score)
    voted.title = _title(cands)
    issues: list[Issue] = [i for i in ref.score.issues if i.severity == "info"]
    details = {"reference": ref.label, "readings": [c.label for c in cands], "measures": []}

    engines_of: dict[str, int] = defaultdict(int)   # how many readings each engine gave
    for c in cands:
        engines_of[c.engine] += 1
    sig_tallies: list[dict] = []
    for k, m in enumerate(voted.measures):
        aligned = [(c, maps[id(c)][k]) for c in cands if k in maps[id(c)]]
        m_detail = {"measure": m.label, "voices": {}}

        # ---- notes, voice by voice
        for v in VOICES:
            groups: dict[tuple, dict] = {}
            for c, j in aligned:
                evs = c.score.measures[j].voices.get(v, [])
                key = _content(evs)
                errs, avs = _voice_issues(c, j, v)
                g = groups.setdefault(key, {"events": evs, "weight": 0.0, "errors": errs, "avisos": avs,
                                            "sources": [], "key": c.score.measures[j].key_fifths})
                g["weight"] += c.weight
                g["errors"] = min(g["errors"], errs)
                g["avisos"] = min(g["avisos"], avs)
                g["sources"].append(c.label)
            if not groups:
                continue
            # A rule error rules a version out; a warning (aviso) is only a suspicion, so it
            # halves the votes instead: 9 readings with a warning still beat 1 without
            # («Oh, Dios y Padre», contralto c.57). Exact ties: the reference reading decides.
            best = min(groups.values(), key=lambda g: (g["errors"] > 0,
                                                       -g["weight"] * (0.5 if g["avisos"] else 1.0),
                                                       ref.label not in g["sources"]))
            m.alternatives[v] = [{**g, "content": key, "chosen": g is best} for key, g in groups.items()]
            new_events = copy.deepcopy(best["events"])
            for e in new_events:
                e.lyrics = {}
            m.voices[v] = new_events
            # agreement on the notes: versions that differ only in a tie («Puertas abiertas» c.28:
            # 4 homr readings tie the last note, 3 Audiveris readings do not) agree on what is sung
            untied = _untied(key_of(best, groups))
            notes_weight = sum(g["weight"] for key, g in groups.items() if _untied(key) == untied)
            # one engine unanimous, the other split («Puertas abiertas» c.24, 29, 32: all of homr's
            # readings see a small eighth rest that each Audiveris reading misses in its own way)
            settled = _engine_settles(best, groups, engines_of)
            m.votes[v] = {"weight": best["weight"], "total": total, "versions": len(groups),
                          "sources": best["sources"], "notes_weight": notes_weight, "settled": settled}
            m_detail["voices"][v] = {"agreement": round(best["weight"] / total, 3), "versions": len(groups),
                                     "sources": best["sources"]}

        # ---- lyrics, verse by verse
        # A reading that lost a lyric line in this system has its verses shifted
        # (verse 2 labelled 1...): only trust readings that found every line here.
        complete = [(c, j) for c, j in aligned
                    if len(lines_per_system[id(c)].get(c.score.measures[j].system, ())) >= n_verses]
        options: dict[int, dict[tuple, dict]] = defaultdict(dict)
        for c, j in (complete or aligned):
            for n, line in _lyric_lines(c, j).items():
                key = tuple(t for _, t, _ in line)
                g = options[n].setdefault(key, {"line": line, "weight": 0.0})
                g["weight"] += c.weight
        lead = lyric_voice(m)
        sop = [e for e in m.voices.get(lead, []) if e.is_attack]
        sop = sorted(sop + [e for e in m.voices.get(PARTNER[lead], [])
                            if e.is_attack and holding(m.voices.get(lead, []), e.offset)],
                     key=lambda e: e.offset)
        for n, opts in sorted(options.items()):
            best = min(opts.values(), key=lambda g: (any(_suspicious_syllable(t) for _, t, _ in g["line"]),
                                                     len(g["line"]) > len(sop), -len(g["line"]), -g["weight"]))
            _attach_lyrics(m, n, best["line"], sop)

        # ---- the men's own words: printed under the lower staff while the upper staff hums
        # or rests («Cuando suene la trompeta»: «Tra-ba-je-mos, pues, por Cris-to» under «Uh»)
        upper_text = [t for e in m.voices.get(lyric_voice(m), []) for t, _ in e.lyrics.values()]
        chosen: dict[str, dict[int, list]] = {}
        for v in ("tenor", "bass"):
            if v == lyric_voice(m):
                continue
            lines: dict[int, dict[int, list]] = defaultdict(dict)
            for c, j in aligned:
                for e in c.score.measures[j].voices.get(v, []):
                    for n, (text, syl) in e.lyrics.items():
                        if any(ch.lower() in _VOWELS for ch in text):
                            lines[n].setdefault(id(c), []).append((e.offset, text, syl))
            for n, per_reading in lines.items():
                opts: dict[tuple, dict] = {}
                for cid, line in per_reading.items():
                    c = next(c for c, _ in aligned if id(c) == cid)
                    g = opts.setdefault(tuple(t for _, t, _ in line), {"line": line, "weight": 0.0})
                    g["weight"] += c.weight
                best = max(opts.values(), key=lambda g: g["weight"])["line"]
                if [t for _, t, _ in best] != upper_text:
                    chosen.setdefault(v, {})[n] = best
        for n in {n for lines in chosen.values() for n in lines}:
            # the staff's whole line: the voice that moves with the words gets them; one that
            # holds long notes with the upper staff (catching a syllable or two) does not
            full = max(len(lines.get(n, [])) for lines in chosen.values())
            for v, lines in chosen.items():
                attacks = {e.offset: e for e in m.voices.get(v, []) if e.is_attack}
                hit = [(off, text, syl) for off, text, syl in lines.get(n, []) if off in attacks]
                if len(hit) < 0.5 * full:
                    continue
                for off, text, syl in hit:
                    attacks[off].lyrics[n] = (text, syl)
                m.own_words = True

        # ---- time and key signature: by majority (an engine may miss a signature on page 2)
        sig_tallies.append(_signature_tally(aligned, marks_engines))

        # ---- notation marks (repeats, endings, dynamics...): only engines that read them vote
        m.marks = _vote_marks([(c, j) for c, j in aligned if c.engine in marks_engines])

        # ---- crop image: from the most natural-looking reading that knows where this measure is
        # and saw all its staves (a reading that missed the upper staff crops only the lower one,
        # «A Cristo coronad»)
        def placed(attr, preference):
            found = [(c, j) for c, j in aligned if getattr(c.score.measures[j], attr)]
            rank = {v: i for i, v in enumerate(preference)}
            found = [cj for cj in found if cj[0].variant in rank]
            return min(found, key=lambda cj: (-len(cj[0].score.measures[cj[1]].staves), rank[cj[0].variant]),
                       default=None)

        src = placed("bbox", CROP_PREFERENCE)
        if src:
            c, j = src
            m.bbox, m.page, m.image_dir = c.score.measures[j].bbox, c.score.measures[j].page, c.image_dir

        # ---- geometry for analysis by synthesis: the sharpest image that knows where this measure is
        src = placed("geometry", GEOMETRY_PREFERENCE)
        if src:
            c, j = src
            m.geometry, m.geometry_dir = c.score.measures[j].geometry, c.image_dir

        # ---- agreement
        weak = {v: d for v, d in m.votes.items()
                if d.get("notes_weight", d["weight"]) / total < min_agree and not d.get("settled")}
        if weak:
            detail = ", ".join(f"{_VOICE_ES[v]} {d['weight']:g}/{total:g}" for v, d in weak.items())
            issues.append(Issue("votacion", "aviso",
                                f"Las lecturas no se ponen de acuerdo ({detail} votos para la versión elegida).",
                                m.index))
        details["measures"].append(m_detail)

    _resolve_signatures(voted, sig_tallies)
    _respell_to_voted_key(voted, sig_tallies)
    _fit_bars(voted, issues)
    _fix_endings(voted)
    _layout_fallback(voted, cands)
    _drop_phantoms(voted, cands, maps, marks_engines, issues, details)
    return voted, issues, details


def _sung_end(events: list[Event]) -> Fraction:
    return max((e.end for e in events if not e.filled), default=Fraction(0))


def _fit_bars(voted: ChoralScore, issues: list[Issue]) -> None:
    """Make each measure as long as its bar.

    - Padding the pipeline added (filled rests) past the bar goes: a reading that took the
      bar for longer («Exaltado sea tu nombre»: Audiveris read «3/8 … 6/8» as 9/8 and kept it
      for 50 measures) leaves its padding on the notes it won.
    - A short bar the engines all missed (a 3/8 measure inside a 6/8 piece): every voice that
      sings ends at the same point before the bar's end, the rest is only padding, and the
      measure is not one half of a measure cut by a system break → it is a bar of that length.
    """
    ms = voted.measures
    for m in ms:
        for v, evs in m.voices.items():
            kept = [e for e in evs if not (e.filled and e.offset >= m.bar_length)]
            for e in kept:
                if e.filled and e.end > m.bar_length:
                    e.duration = m.bar_length - e.offset
            m.voices[v] = kept
    # quarter-note times too (2/4 bars inside a 4/4: «A Dios sea la gloria» c.40), but only to a
    # time printed elsewhere in the piece: all voices missing a rest at a phrase end is no new time
    printed_quarter = {mm.time for mm in ms if mm.time[1] == 4}
    for k, m in enumerate(ms):
        if k in (0, len(ms) - 1) or m.pickup or m.time[1] not in (4, 8):
            continue
        singing = {v: evs for v, evs in m.voices.items() if any(not e.is_rest for e in evs)}
        if len(singing) < 2:
            continue
        unit = Fraction(1, 2) if m.time[1] == 8 else Fraction(1)   # an eighth / a quarter
        if m.time[1] == 4:
            fits0 = {_sung_end(evs) for evs in singing.values()}
            if len(fits0) != 1 or (int(min(fits0)), 4) not in printed_quarter:
                continue
        fits = sorted({_sung_end(evs) for evs in singing.values()})
        length = fits[0]
        if not (0 < length < m.bar_length) or length % unit:
            continue
        if len(fits) > 1:
            # some voices won a version with something extra (the cautionary «6/8» at the end
            # of the 3/8 bar read as a note or a rest): another reading of them may fit
            swap = {}
            for v, evs in singing.items():
                if _sung_end(evs) == length:
                    continue
                alt = next((g for g in m.alternatives.get(v, [])
                            if any(not e.is_rest for e in g["events"]) and _sung_end(g["events"]) == length), None)
                if alt is None:
                    break
                swap[v] = alt
            else:
                for v, g in swap.items():
                    # the voted words go on the new notes in order (not the other reading's OCR)
                    words = [e.lyrics for e in m.voices[v] if e.lyrics]
                    m.voices[v] = copy.deepcopy(g["events"])
                    attacks = [e for e in m.voices[v] if e.is_attack]
                    for e in m.voices[v]:
                        e.lyrics = {}
                    for e, ly in zip(attacks, words):
                        e.lyrics = dict(ly)
                    for alt in m.alternatives[v]:
                        alt["chosen"] = alt is g
            if any(_sung_end(evs) != length for v, evs in m.voices.items() if v in singing):
                continue
        if any(not e.filled for evs in m.voices.values() for e in evs if e.offset >= length):
            continue  # printed rests after the notes: the bar is full
        neighbours = [_sung_end_all(ms[j]) for j in (k - 1, k + 1)]
        if any(n < ms[j].bar_length and n + length == m.bar_length for n, j in zip(neighbours, (k - 1, k + 1))):
            continue  # one half of a measure cut by a system break
        new = (int(length / unit), m.time[1])
        issues.append(Issue("estructura", "info",
                            f"Compás de {new[0]}/{new[1]} (las voces llenan {new[0]} "
                            f"{'corcheas' if new[1] == 8 else 'negras'}) leído como {m.time[0]}/{m.time[1]}.", m.index))
        m.time, m.bar_length, m.duration = new, length, length
        for st in m.staves:
            st.time = new
        for v, evs in m.voices.items():
            m.voices[v] = [e for e in evs if e.offset < length]


def _sung_end_all(m) -> Fraction:
    return max((_sung_end(evs) for evs in m.voices.values()), default=Fraction(0))


def _fix_endings(voted: ChoralScore) -> None:
    """Make the 1st/2nd-time endings consistent.

    - An ending belongs to a repeat: a run of endings with no :| in it (nor right before it)
      is a misreading, unless it is a 1st and 2nd ending closing the piece (back to the start) (Audiveris put endings on measures 1-4 of «A Cristo coronad») and goes,
      unless a :| comes a few measures later (a short bracket: the ending reaches the :|).
    - Inside one run the numbers only go up: a "1" after a "2" is a misread of the 2nd ending
      (its bracket is often drawn open, without an end).
    - The ending right after a :| is the next one; after an ending "1.-6." it is the 7th,
      whatever number the engine gave it.
    """
    ms = voted.measures
    k = 0
    while k < len(ms):
        if ms[k].marks.volta is None:
            k += 1
            continue
        end = k
        while end + 1 < len(ms) and ms[end + 1].marks.volta is not None:
            end += 1
        # A 1st ending then a 2nd ending that closes the piece, with no :| at all: going back
        # to the beginning is implied (hymns with the stanzas stacked, «¿Cómo podré estar
        # triste?»). Audiveris does not invent a pair like that at the very end.
        numbers = [ms[j].marks.volta for j in range(k, end + 1)]
        implied = end == len(ms) - 1 and numbers[0] == 1 and 2 in numbers and numbers == sorted(numbers)
        if not implied and not any(ms[j].marks.repeat_end for j in range(max(0, k - 3), end + 1)):
            # the bracket may be drawn short: the ending goes on to a :| a few measures later
            close = next((j for j in range(end + 1, min(len(ms), end + 5))
                          if ms[j].marks.repeat_end or ms[j].marks.volta is not None), None)
            if close is not None and ms[close].marks.repeat_end and ms[close].marks.volta is None:
                for j in range(end + 1, close + 1):
                    ms[j].marks.volta, ms[j].marks.volta_to = ms[end].marks.volta, ms[end].marks.volta_to
                end = close
            else:
                for j in range(k, end + 1):
                    ms[j].marks.volta = ms[j].marks.volta_to = None
        k = end + 1

    prev = None  # (first, last) time through of the ending of the previous measure
    prev_closed = False  # the previous measure ends with :|
    closed_last = None   # last time through of the latest ending that ended with :|
    closed_at = -99      # ...and the measure of that :|
    for k, m in enumerate(ms):
        mk = m.marks
        if mk.repeat_start:
            closed_last = None
        if mk.volta is None or mk.repeat_start:
            prev = (mk.volta, mk.volta_to or mk.volta) if mk.volta is not None else None
            prev_closed = mk.repeat_end
            continue
        width = (mk.volta_to or mk.volta) - mk.volta
        if prev is None:
            if closed_last is not None and k - closed_at <= 3 and mk.volta <= closed_last:  # the next ending
                mk.volta = closed_last + 1
                mk.volta_to = mk.volta + width if width else None
        else:
            first, last = prev
            if prev_closed and mk.volta <= last:            # the ending after the :| is the next one
                mk.volta = last + 1
                mk.volta_to = mk.volta + width if width else None
            elif mk.volta == first or mk.volta < first:      # the same ending goes on
                mk.volta, mk.volta_to = first, (last if last > first else None)
            elif mk.volta <= last:                          # the ending after a "1.-6."
                mk.volta = last + 1
                mk.volta_to = mk.volta + width if width else None
        prev = (mk.volta, mk.volta_to or mk.volta)
        prev_closed = mk.repeat_end
        if mk.repeat_end:
            closed_last, closed_at = mk.volta_to or mk.volta, k


def _signature_tally(aligned: list[tuple], whole_book_engines: set) -> dict:
    """Votes for the time and key signature of one measure. The time signature is voted only
    by engines that read the whole book (Audiveris) when any is aligned here: homr reads each
    page alone and guesses a time signature on pages that do not print one."""
    out = {"time": defaultdict(float), "key_fifths": defaultdict(float)}
    book = [(c, j) for c, j in aligned if c.engine in whole_book_engines]
    for c, j in (book or aligned):
        out["time"][c.score.measures[j].time] += c.weight
    # only homr saw this measure (Audiveris skipped it): its time signature is a guess
    out["time_guess"] = not book and any(c.engine not in whole_book_engines for c, _ in aligned)
    for c, j in aligned:
        out["key_fifths"][c.score.measures[j].key_fifths] += c.weight
    return out


def _respell_to_voted_key(voted: ChoralScore, tallies: list[dict]) -> None:
    """A voice chosen from a reading that did not see a key change has its notes in the old key
    («Si alguien te pregunta» c.40: 3 sharps → 6 flats; the voted soprano sang sol♯ for sol♭).
    The notes that followed the reading's key signature take the voted one; a note with its own
    accidental keeps it."""
    from music21 import key as m21key, pitch as m21pitch

    from ..model.corrections import _set_pitch

    def alter(ks, step):
        acc = ks.accidentalByStep(step)
        return float(acc.alter) if acc is not None else 0.0

    for m in voted.measures:
        for v, alts in m.alternatives.items():
            chosen = next((g for g in alts if g.get("chosen")), None)
            src = chosen.get("key") if chosen else None
            if src is None or src == m.key_fifths:
                continue
            # only when the voted key is clear: twice the weight of the reading's key and most of
            # all («Es exaltado» c.31: the vote got the key wrong; respelling broke right notes)
            def clear(k, value, other):
                t = tallies[k]["key_fifths"] if 0 <= k < len(tallies) else {}
                total = sum(t.values())
                return bool(total) and t.get(value, 0) >= 2 * t.get(other, 0) and t.get(value, 0) >= 0.6 * total

            k = m.index
            t = tallies[k]["key_fifths"] if k < len(tallies) else {}
            nxt = voted.measures[k + 1] if k + 1 < len(voted.measures) else None
            # or a tie on the first measure of a change that the next measure confirms (one engine
            # saw the new key a measure late: «Si alguien te pregunta» c.40)
            late = (t.get(m.key_fifths, 0) >= t.get(src, 0) and nxt is not None
                    and nxt.key_fifths == m.key_fifths and clear(k + 1, m.key_fifths, src))
            if not (clear(k, m.key_fifths, src) or late):
                continue
            old, new = m21key.KeySignature(src), m21key.KeySignature(m.key_fifths)
            for e in m.voices.get(v, []):
                if e.pitch is None:
                    continue
                p = m21pitch.Pitch(e.pitch)
                if (float(p.accidental.alter) if p.accidental else 0.0) == alter(old, p.step):
                    a = alter(new, p.step)
                    p.accidental = m21pitch.Accidental(a) if a else None
                    _set_pitch(e, p)


def _resolve_signatures(voted: ChoralScore, tallies: list[dict]) -> None:
    """Time and key signature by majority, measure by measure.

    A tie (Audiveris and homr each sure of a different value for a stretch) is settled by the
    music around it: for the key, the value all readings agree on right after the tied stretch
    (the change was real and one engine saw it late); for the time, the value before it.
    """
    for attr in ("time", "key_fifths"):
        winners: list[list] = []
        for tally in tallies:
            t = tally[attr]
            best = max(t.values(), default=0)
            winners.append([v for v, w in t.items() if w == best])
        for k, m in enumerate(voted.measures):
            options = winners[k]
            if not options:
                continue
            prev = getattr(voted.measures[k - 1], attr) if k else None
            if attr == "time" and tallies[k].get("time_guess") and prev is not None:
                value = prev  # a measure only homr saw keeps the time signature around it
            elif len(options) == 1:
                value = options[0]
            else:
                after = next((w[0] for w in winners[k + 1:] if len(w) == 1), None)
                before = getattr(voted.measures[k - 1], attr) if k else None
                # key: a change seen late by one engine is real (look after the tie); time: an engine
                # guesses a time signature on a page that prints none (keep the one before)
                order = (after, before) if attr == "key_fifths" else (before, after)
                value = next((x for x in order if x in options), getattr(m, attr))
            if attr == "time" and Fraction(4 * value[0], value[1]) != m.bar_length:
                # a different bar length must fit the voted notes: it does when every voice that
                # sings ends right there and only gap-filling rests come after (a 2/4 bar read by
                # Audiveris in a reference that kept 4/4: «A Dios sea la gloria» c.40)
                new_len = Fraction(4 * value[0], value[1])
                singing = [evs for evs in m.voices.values() if any(not e.is_rest for e in evs)]
                if m.pickup or not singing or any(_sung_end(evs) != new_len for evs in singing) or any(
                        not e.filled and e.end > new_len for evs in m.voices.values() for e in evs):
                    continue
                m.bar_length = m.duration = new_len
                for v, evs in m.voices.items():
                    kept = [e for e in evs if e.offset < new_len]
                    for e in kept:
                        if e.end > new_len:
                            e.duration = new_len - e.offset
                    m.voices[v] = kept or [Event(Fraction(0), new_len, filled=True)]
                for st in m.staves:
                    st.time = value
            setattr(m, attr, value)
            if attr == "key_fifths":
                for st in m.staves:  # the staves of the reference may disagree among themselves
                    st.key_fifths = value


def _drop_phantoms(voted: ChoralScore, cands: list[Candidate], maps: dict, marks_engines: set,
                   issues: list[Issue], details: dict) -> None:
    """An empty measure that only the note-only engines see is not in the image.

    homr sometimes adds a silent measure at a page start, a repeat sign or a key change.
    Audiveris (which reads the whole page layout) does not, so when no Audiveris reading
    has that measure and it holds only rests, it is dropped.
    """
    full = [c for c in cands if c.engine in marks_engines]
    if not full:
        return
    keep_m, keep_d = [], []
    dropped = []
    for k, (m, md) in enumerate(zip(voted.measures, details["measures"])):
        seen_by_full = any(k in maps[id(c)] for c in full)
        silent = all(e.is_rest for evs in m.voices.values() for e in evs)
        if not seen_by_full and silent and not m.pickup:
            dropped.append(m.label)
            continue
        keep_m.append(m)
        keep_d.append(md)
    if not dropped:
        return
    old_index = {id(m): m.index for m in voted.measures}
    for i, m in enumerate(keep_m):
        m.index = i
    if keep_m and not keep_m[0].pickup and keep_m[0] is not voted.measures[0]:
        # the measure now first was a pickup that the reference reading (homr, with a silent
        # measure of its own before it) took for a full measure («Grato es contar la historia»)
        from ..model.score import _detect_pickup_and_number

        _detect_pickup_and_number(keep_m)
    first_pickup = bool(keep_m) and keep_m[0].pickup
    for m in keep_m:
        m.number = m.index if first_pickup else m.index + 1
    remap = {old_index[id(m)]: m.index for m in keep_m}
    issues[:] = [i for i in issues if i.measure is None or i.measure in remap]
    for i in issues:
        if i.measure is not None:
            i.measure = remap.get(i.measure)
    for md, m in zip(keep_d, keep_m):
        md["measure"] = m.label
    voted.measures = keep_m
    details["measures"] = keep_d
    issues.append(Issue("estructura", "info",
                        f"Se quitaron {len(dropped)} compás(es) vacíos que solo veía homr "
                        f"(no están en la imagen): {', '.join(dropped)}."))


_FLAGS = ("repeat_start", "repeat_end", "segno", "coda", "to_coda", "fine")


def _vote_marks(readings: list[tuple]) -> Marks:
    """A mark is kept when at least half of the (weighted) readings that read marks see it."""
    out = Marks()
    total = sum(c.weight for c, _ in readings)
    if not total:
        return out

    def keep(weight: float) -> bool:
        return weight >= total / 2

    for flag in _FLAGS:
        if keep(sum(c.weight for c, j in readings if getattr(c.score.measures[j].marks, flag))):
            setattr(out, flag, True)
    for attr in ("barline", "volta", "jump"):
        tally: dict = defaultdict(float)
        for c, j in readings:
            value = getattr(c.score.measures[j].marks, attr)
            if value is not None:
                tally[value] += c.weight
        if tally:
            value, weight = max(tally.items(), key=lambda kv: kv[1])
            if keep(weight):
                setattr(out, attr, value)
    if out.volta is not None:
        # "1.-6.": Audiveris numbers endings 1, 2... when it cannot read their text, so one
        # reading that did read a range at this ending is believed
        ranges: dict = defaultdict(float)
        for c, j in readings:
            mk = c.score.measures[j].marks
            if mk.volta == out.volta and mk.volta_to:
                ranges[mk.volta_to] += c.weight
        if ranges:
            out.volta_to = max(ranges.items(), key=lambda kv: kv[1])[0]
    for attr in ("dynamics", "wedges"):
        tally = defaultdict(float)
        for c, j in readings:
            for item in set(getattr(c.score.measures[j].marks, attr)):
                tally[item] += c.weight
        setattr(out, attr, sorted(item for item, w in tally.items() if keep(w)))
    if out.repeat_end:
        out.barline = None
    return out


def _layout_fallback(voted: ChoralScore, cands: list[Candidate]) -> None:
    """Crops and geometry for measures no aligned reading could place on the page.

    Audiveris may find every measure in the image (its layout) yet merge some of them in
    its MusicXML; that reading then has no boxes. Its layout is still right when it has
    exactly as many measures, system by system, as the voted score.
    """
    if all(m.bbox and m.geometry for m in voted.measures):
        return
    per_system: dict[int, int] = defaultdict(int)
    for m in voted.measures:
        per_system[m.system] += 1
    counts = [per_system[s] for s in sorted(per_system)]

    def usable(c: Candidate) -> list[tuple] | None:
        layout = c.score.layout
        if not layout or sum(len(s.stacks) for s in layout) != len(voted.measures):
            return None
        if len(counts) > 1 and [len(s.stacks) for s in layout] != counts:
            return None
        return [(s, j) for s in layout for j in range(len(s.stacks))]

    def pick(order: tuple[str, ...]):
        for variant in order:
            for c in cands:
                if c.variant == variant and (places := usable(c)):
                    return c, places
        return None, None

    c, places = pick(CROP_PREFERENCE)
    if c:
        for m, (s, j) in zip(voted.measures, places):
            if not m.bbox:
                m.bbox, m.page, m.image_dir = _bbox([s], j), s.page, c.image_dir
    c, places = pick(GEOMETRY_PREFERENCE)
    if c:
        for m, (s, j) in zip(voted.measures, places):
            if not m.geometry:
                g = _geometry([s], j, m.staves)
                if g:
                    m.geometry, m.geometry_dir = g, c.image_dir


_VOICE_ES = {"soprano": "soprano", "alto": "contralto", "tenor": "tenor/barítono", "bass": "bajo"}


def _attach_lyrics(m, verse: int, line: list[tuple], sop_attacks: list[Event]) -> None:
    """Put a verse's syllables on the chosen soprano notes (same onset if possible, else in order)."""
    onsets = {e.offset: e for e in sop_attacks}
    if all(off in onsets for off, _, _ in line):
        targets = [onsets[off] for off, _, _ in line]
    else:
        targets = sop_attacks[: len(line)]
    partner = PARTNER[lyric_voice(m)]
    for e, (_, text, syl) in zip(targets, line):
        e.lyrics[verse] = (text, syl)
        for other in m.voices.get(partner, []):  # same syllable on the note sung with it
            if other.offset == e.offset and other.is_attack:
                other.lyrics[verse] = (text, syl)
