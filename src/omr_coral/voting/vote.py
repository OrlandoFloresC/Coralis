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
    for e in mm.voices.get(lyric_voice(mm), []):
        for n, (text, syl) in e.lyrics.items():
            if any(ch.lower() in _VOWELS for ch in text):  # "F", "-", "'" can never be a sung syllable
                out[n].append((e.offset, text, syl))
    return out


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
                                            "sources": []})
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
            m.votes[v] = {"weight": best["weight"], "total": total, "versions": len(groups),
                          "sources": best["sources"]}
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
        sop = [e for e in m.voices.get(lyric_voice(m), []) if e.is_attack]
        for n, opts in sorted(options.items()):
            best = min(opts.values(), key=lambda g: (any(_suspicious_syllable(t) for _, t, _ in g["line"]),
                                                     len(g["line"]) > len(sop), -g["weight"]))
            _attach_lyrics(m, n, best["line"], sop)

        # ---- time and key signature: by majority (an engine may miss a signature on page 2)
        sig_tallies.append(_signature_tally(aligned, marks_engines))

        # ---- notation marks (repeats, endings, dynamics...): only engines that read them vote
        m.marks = _vote_marks([(c, j) for c, j in aligned if c.engine in marks_engines])

        # ---- crop image: from the most natural-looking reading that knows where this measure is
        for variant in CROP_PREFERENCE:
            src = next(((c, j) for c, j in aligned
                        if c.variant == variant and c.score.measures[j].bbox), None)
            if src:
                c, j = src
                m.bbox, m.page, m.image_dir = c.score.measures[j].bbox, c.score.measures[j].page, c.image_dir
                break

        # ---- geometry for analysis by synthesis: the sharpest image that knows where this measure is
        for variant in GEOMETRY_PREFERENCE:
            src = next(((c, j) for c, j in aligned
                        if c.variant == variant and c.score.measures[j].geometry), None)
            if src:
                c, j = src
                m.geometry, m.geometry_dir = c.score.measures[j].geometry, c.image_dir
                break

        # ---- agreement
        weak = {v: d for v, d in m.votes.items() if d["weight"] / total < min_agree}
        if weak:
            detail = ", ".join(f"{_VOICE_ES[v]} {d['weight']:g}/{total:g}" for v, d in weak.items())
            issues.append(Issue("votacion", "aviso",
                                f"Las lecturas no se ponen de acuerdo ({detail} votos para la versión elegida).",
                                m.index))
        details["measures"].append(m_detail)

    _resolve_signatures(voted, sig_tallies)
    _fix_endings(voted)
    _layout_fallback(voted, cands)
    _drop_phantoms(voted, cands, maps, marks_engines, issues, details)
    return voted, issues, details


def _fix_endings(voted: ChoralScore) -> None:
    """Inside one run of 1st/2nd-time endings the numbers only go up: a "1" after a "2"
    is a misread of the 2nd ending (its bracket is often drawn open, without an end).
    After an ending "1.-6." the next one is the 7th, whatever number the engine gave it."""
    prev = None  # (first, last) time through of the ending of the previous measure
    for m in voted.measures:
        mk = m.marks
        if mk.volta is None or mk.repeat_start:
            prev = (mk.volta, mk.volta_to or mk.volta) if mk.volta is not None else None
            continue
        if prev is not None:
            first, last = prev
            if mk.volta == first or mk.volta < first:      # the same ending goes on
                mk.volta, mk.volta_to = first, (last if last > first else None)
            elif mk.volta <= last:                          # the ending after a "1.-6."
                width = (mk.volta_to or mk.volta) - mk.volta
                mk.volta = last + 1
                mk.volta_to = mk.volta + width if width else None
        prev = (mk.volta, mk.volta_to or mk.volta)


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
                continue  # a different bar length would not fit the voted notes
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
