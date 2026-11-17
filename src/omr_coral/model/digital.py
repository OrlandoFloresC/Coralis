"""ChoralScore -> "copia digital": the score as printed, on 2 staves.

    upper staff: soprano + alto      lower staff: barítono (tenor) + bajo

Each staff of each measure is written the way a hymnal engraves it:
  - both voices sing the same thing (unison, a solo line) -> one line of notes,
  - same rhythm                                          -> chords,
  - different rhythms                                    -> two voices (stems up / down).
All verses stay stacked under the notes, and the voted notation marks are kept:
repeats, 1st/2nd endings, segno, coda, D.S./D.C., Fine, double/final barlines,
dynamics and hairpins.
"""

from __future__ import annotations

from fractions import Fraction

from music21 import (bar, chord, clef, dynamics, key, layout, metadata, meter, note, repeat, spanner,
                     stream, tie)

from .score import ChoralScore, Event, Measure

GROUPS = {"upper": ("soprano", "alto"), "lower": ("tenor", "bass")}
_JUMP_CLASSES = {"D.S. al Coda": repeat.DalSegnoAlCoda, "D.S. al Fine": repeat.DalSegnoAlFine,
                 "D.C. al Coda": repeat.DaCapoAlCoda, "D.C. al Fine": repeat.DaCapoAlFine,
                 "D.S.": repeat.DalSegno, "D.C.": repeat.DaCapo}


def _written(events: list[Event]) -> list[Event]:
    return [e for e in events if e.duration > 0]


def _content(events: list[Event]) -> list[tuple]:
    return [(e.offset, e.duration, e.pitch) for e in events]


def _rhythm(events: list[Event]) -> list[tuple]:
    return [(e.offset, e.duration, e.is_rest) for e in events]


def _lyrics_to(el, e: Event) -> None:
    for verse, (text, syllabic) in sorted(e.lyrics.items()):
        ly = note.Lyric(text=text, number=verse)
        ly.syllabic = syllabic
        el.lyrics.append(ly)


def _single(e: Event, stem: str | None = None):
    if e.is_rest:
        return note.Rest(quarterLength=e.duration)
    n = note.Note(e.pitch, quarterLength=e.duration)
    if e.tie:
        n.tie = tie.Tie(e.tie)
    if stem:
        n.stemDirection = stem
    return n


def _chord(a: Event, b: Event):
    """Two simultaneous events with the same rhythm: rest, single note (unison) or a chord."""
    if a.is_rest:
        return note.Rest(quarterLength=a.duration)
    if a.pitch == b.pitch:
        return _single(a if a.tie else b)
    c = chord.Chord([a.pitch, b.pitch], quarterLength=a.duration)
    for n, e in zip(c.notes, sorted([a, b], key=lambda x: x.midi or 0)):
        if e.tie:
            n.tie = tie.Tie(e.tie)
    return c


def _staff_measure(m: Measure, group: str, lyric_events: dict[Fraction, Event]) -> tuple[list, dict]:
    """Elements for one staff of one measure, plus {offset: element} of the top line (for marks)."""
    v1, v2 = (_written(m.voices.get(v, [])) for v in GROUPS[group])
    out, tops = [], {}
    if not v2 or _content(v1) == _content(v2):
        for e in v1:
            el = _single(e)
            out.append((e.offset, el))
            tops[e.offset] = el
    elif _rhythm(v1) == _rhythm(v2):
        for a, b in zip(v1, v2):
            el = _chord(a, b)
            out.append((a.offset, el))
            tops[a.offset] = el
    else:
        voices = []
        for vid, (evs, stem) in enumerate(((v1, "up"), (v2, "down")), start=1):
            voice = stream.Voice(id=str(vid))
            for e in evs:
                el = _single(e, stem)
                voice.insert(float(e.offset), el)
                if vid == 1:
                    tops[e.offset] = el
            voices.append(voice)
        out = [(Fraction(0), v) for v in voices]
    for off, e in lyric_events.items():
        el = tops.get(off)
        if el is not None and not el.isRest:
            _lyrics_to(el, e)
    return out, tops


def _lyric_events(m: Measure) -> dict[str, dict[Fraction, Event]]:
    """Which staff carries the verses in this measure: the upper one, or the lower one when
    only the men sing (their notes then carry the syllables)."""
    out = {"upper": {}, "lower": {}}
    for group, voices in GROUPS.items():
        for v in voices:
            for e in m.voices.get(v, []):
                if e.lyrics and e.is_attack:
                    out[group].setdefault(e.offset, e)
    if out["upper"]:
        out["lower"] = {}
    return out


def to_two_staves(cs: ChoralScore, cfg: dict) -> stream.Score:
    names = cfg["output"]["parts"]
    score = stream.Score()
    score.metadata = metadata.Metadata(title=cs.title or "")
    score.metadata.composer = ""
    parts = {}
    for group, clef_cls in (("upper", clef.TrebleClef), ("lower", clef.BassClef)):
        part = stream.Part(id=group)
        a, b = GROUPS[group]
        part.partName = f"{names[a]['name']} / {names[b]['name']}"
        part.partAbbreviation = f"{names[a]['name'][:1]}{names[b]['name'][:1]}"
        parts[group] = (part, clef_cls)

    tops_by_group: dict[str, list[dict]] = {"upper": [], "lower": []}
    measures_by_group: dict[str, list[stream.Measure]] = {"upper": [], "lower": []}
    prev_time = prev_key = None
    measures = _expand_multirests(cs.measures)
    for k, m in enumerate(measures):
        lyric_events = _lyric_events(m)
        for group, (part, clef_cls) in parts.items():
            meas = stream.Measure(number=m.number)
            if k == 0:
                meas.insert(0, clef_cls())
            if m.key_fifths != prev_key:
                meas.insert(0, key.KeySignature(m.key_fifths))
            if m.time != prev_time:
                meas.insert(0, meter.TimeSignature(f"{m.time[0]}/{m.time[1]}"))
            elements, tops = _staff_measure(m, group, lyric_events[group])
            for off, el in elements:
                meas.insert(float(off), el)
            if m.pickup and k == 0:
                meas.paddingLeft = float(m.bar_length - m.duration)
            _barlines(meas, m)
            for g, off, value in m.marks.dynamics:
                if g == group:
                    meas.insert(float(off), dynamics.Dynamic(value))
            if group == "upper":
                _signs(meas, m)
            part.append(meas)
            tops_by_group[group].append(tops)
            measures_by_group[group].append(meas)
        prev_time, prev_key = m.time, m.key_fifths

    for group, (part, _) in parts.items():
        _endings(part, measures_by_group[group], measures)
        _hairpins(part, measures, group, tops_by_group[group])
        score.insert(0, part)
    score.insert(0, layout.StaffGroup([parts["upper"][0], parts["lower"][0]], symbol="bracket", barTogether=True))
    return score


def _expand_multirests(measures: list[Measure]) -> list[Measure]:
    """A measure marked as a silence of N measures becomes N silent measures (MuseScore can
    show them as one multi-measure rest); the numbers after it move on accordingly."""
    import copy

    out, shift = [], 0
    for m in measures:
        n = m.marks.multirest or 1
        for r in range(n):
            c = copy.copy(m) if n > 1 else m
            if n > 1:
                c.marks = copy.deepcopy(m.marks)
                c.marks.multirest = None
                if r > 0:  # signs at the start stay on the first, signs at the end on the last
                    c.marks.repeat_start = c.marks.segno = c.marks.coda = False
                    c.marks.dynamics = []
                if r < n - 1:
                    c.marks.repeat_end = c.marks.to_coda = c.marks.fine = False
                    c.marks.jump = c.marks.barline = None
            c_number = m.number + shift + r
            if n > 1:
                c.number = c_number
            elif shift:
                c = copy.copy(m)
                c.number = c_number
            out.append(c)
        shift += n - 1
    return out


def _barlines(meas: stream.Measure, m: Measure) -> None:
    if m.marks.repeat_start:
        meas.leftBarline = bar.Repeat(direction="start")
    if m.marks.repeat_end:
        meas.rightBarline = bar.Repeat(direction="end")
    elif m.marks.barline == "double":
        meas.rightBarline = bar.Barline("double")
    elif m.marks.barline == "final":
        meas.rightBarline = bar.Barline("final")


def _signs(meas: stream.Measure, m: Measure) -> None:
    mk = m.marks
    if mk.segno:
        meas.insert(0, repeat.Segno())
    if mk.coda:
        meas.insert(0, repeat.Coda())
    if mk.to_coda:
        meas.storeAtEnd(repeat.Coda("To Coda"))
    if mk.fine:
        meas.storeAtEnd(repeat.Fine())
    if mk.jump in _JUMP_CLASSES:
        meas.storeAtEnd(_JUMP_CLASSES[mk.jump]())


def _endings(part: stream.Part, written: list[stream.Measure], measures: list[Measure]) -> None:
    """Consecutive measures with the same ending number form one 1st/2nd-time bracket."""
    run, number = [], None
    for meas, m in zip(written + [None], measures + [None]):
        n = m.marks.volta if m is not None else None
        if run and n != number:
            part.insert(0, spanner.RepeatBracket(run, number=number))
            run = []
        if n is not None:
            run.append(meas)
        number = n


def _hairpins(part: stream.Part, measures: list[Measure], group: str, tops: list[dict]) -> None:
    """Crescendo/diminuendo from the note where it starts to the note where it stops."""
    def element_at(k: int, off: Fraction, after: bool):
        cands = sorted(tops[k].items())
        if not cands:
            return None
        if after:
            return next((el for o, el in cands if o >= off), cands[-1][1])
        return next((el for o, el in reversed(cands) if o <= off), cands[0][1])

    open_wedge = None  # (kind, element)
    for k, m in enumerate(measures):
        for g, off, kind in m.marks.wedges:
            if g != group:
                continue
            if kind == "stop":
                if open_wedge:
                    end = element_at(k, off, after=False)
                    if end is not None and end is not open_wedge[1]:
                        cls = dynamics.Crescendo if open_wedge[0] == "crescendo" else dynamics.Diminuendo
                        part.insert(0, cls(open_wedge[1], end))
                    open_wedge = None
            else:
                start = element_at(k, off, after=True)
                if start is not None:
                    open_wedge = (kind, start)
