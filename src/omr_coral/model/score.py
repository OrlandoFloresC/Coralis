"""Normalized SATB model built from any engine's MusicXML.

Engines disagree on how they encode a choral score (4 staves, 2 staves with chords
or two voices, staves split into separate systems by mistake, lyrics attached to
either voice...). This module turns all of that into one shape:

    ChoralScore.measures[i].voices["soprano"|"alto"|"tenor"|"bass"] -> list[Event]

and records what it had to repair as `info` issues.
"""

from __future__ import annotations

import contextlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from music21 import converter, layout as m21layout, stream

from .issues import Issue
from .layout import LayoutSystem

VOICES = ("soprano", "alto", "tenor", "bass")
CLEF_RANK = {"G": 0, "G8vb": 1, "C": 1, "F": 2}


PARTNER = {"soprano": "alto", "tenor": "bass", "alto": "soprano", "bass": "tenor"}


def lyric_voice(m: "Measure") -> str:
    """The voice whose notes carry the words in this measure: the soprano, or the men when the
    women are silent (a men's solo, "Varones")."""
    for v in ("soprano", "tenor", "alto", "bass"):
        if any(e.is_attack for e in m.voices.get(v, [])):
            return v
    return "soprano"


def F(x) -> Fraction:
    return Fraction(x).limit_denominator(1024)


def fmt_beats(x: Fraction) -> str:
    """Quarter-note beats, readable: 3, 2.5, 0.75."""
    return f"{float(x):g}"


# --------------------------------------------------------------------------- data


@dataclass
class Event:
    offset: Fraction
    duration: Fraction
    pitch: str | None = None       # music21 name with octave, e.g. "E-4"; None = rest
    midi: int | None = None
    step: str | None = None
    alter: float = 0.0
    tie: str | None = None         # start | stop | continue
    lyrics: dict[int, tuple[str, str]] = field(default_factory=dict)  # verse -> (text, syllabic)
    filled: bool = False           # rest inserted by the pipeline to cover a gap
    slur_cont: bool = False        # sung on the previous syllable (inside a slur, after its first note)

    @property
    def takes_syllable(self) -> bool:
        return self.is_attack and not self.slur_cont

    @property
    def end(self) -> Fraction:
        return self.offset + self.duration

    @property
    def is_rest(self) -> bool:
        return self.pitch is None

    @property
    def is_attack(self) -> bool:
        return not self.is_rest and self.tie not in ("stop", "continue")


@dataclass
class RawEvent:
    offset: Fraction
    duration: Fraction
    pitches: list  # music21 Pitch objects sorted low -> high, empty for rests
    ties: list     # tie type per pitch
    hidden: bool = False
    layer: str = ""          # voice id inside the measure ("" = no explicit voices)
    source_id: int = 0       # id() of the music21 element it came from
    slur_cont: bool = False  # under a slur, after its first note (melisma: no new syllable)
    stem: str = ""           # printed stem direction ("up"/"down") when the reading gives it


@dataclass
class Marks:
    """Notation around the notes of one measure: what a printed copy needs besides pitches.

    Staff-bound marks carry a group: "upper" (soprano/alto staff) or "lower" (tenor/bass staff).
    """
    repeat_start: bool = False   # |:  at the left
    repeat_end: bool = False     # :|  at the right
    barline: str | None = None   # right barline when not a repeat: "double" | "final"
    volta: int | None = None     # the measure is inside the 1st/2nd... ending
    volta_to: int | None = None  # last time through of an ending printed "1.-6.": 6 (else None)
    segno: bool = False          # segno sign at the start of the measure
    coda: bool = False           # coda sign: the coda section starts here
    to_coda: bool = False        # "To Coda": jump from the end of this measure (2nd time)
    fine: bool = False           # "Fine" at the end of this measure
    jump: str | None = None      # at the end: "D.S. al Coda" | "D.S. al Fine" | "D.S." | "D.C. al Coda" | ...
    multirest: int | None = None  # this one printed measure is a silence of N measures
    dynamics: list = field(default_factory=list)  # [(group, offset, "mf")]
    wedges: list = field(default_factory=list)    # [(group, offset, "crescendo"|"diminuendo"|"stop")]

    def is_empty(self) -> bool:
        return self == Marks()


@dataclass
class Staff:
    part_index: int
    source_index: int        # position of the measure inside that MusicXML part
    clef: str                # G | G8vb | C | F
    time: tuple[int, int]
    key_fifths: int
    tempo: float | None
    layers: list[list[RawEvent]]
    lyrics: dict[Fraction, dict[int, tuple[str, str]]]  # onset -> verse -> syllable
    marks: Marks = field(default_factory=Marks)  # staff-bound marks use group "" until assigned
    texts: list = field(default_factory=list)  # [(offset, text)]: words printed as plain text

    @property
    def has_notes(self) -> bool:
        return any(e.pitches for layer in self.layers for e in layer)


@dataclass
class Measure:
    index: int
    system: int
    page: int | None
    staves: list[Staff]
    time: tuple[int, int] = (4, 4)
    key_fifths: int = 0
    bar_length: Fraction = Fraction(4)
    duration: Fraction = Fraction(4)    # expected length (shorter for a pickup)
    pickup: bool = False
    bbox: tuple[int, int, int, int] | None = None
    voices: dict[str, list[Event]] = field(default_factory=dict)
    number: int = 0                      # number shown to the user
    image_dir: Path | None = None        # folder with the page images bbox refers to
    # page geometry for analysis by synthesis: {"page", "x0", "x1", "staves": [(top, interline)], "clefs"}
    geometry: dict | None = None
    geometry_dir: Path | None = None     # folder with the page images geometry refers to
    votes: dict = field(default_factory=dict)  # voice -> vote summary (filled by voting)
    alternatives: dict = field(default_factory=dict)  # voice -> versions offered by the readings
    synth: object | None = None  # SynthResult: comparison with the noteheads of the image
    marks: Marks = field(default_factory=Marks)
    solo: str | None = None  # "upper"/"lower": only that staff is printed in this system (a solo)
    own_words: bool = False  # each voice carries its own words here (men answering with other text)

    @property
    def label(self) -> str:
        return "anacrusa" if self.pickup else str(self.number)


@dataclass
class ChoralScore:
    source: Path
    measures: list[Measure]
    issues: list[Issue]
    title: str | None = None
    # page geometry the engine found (Audiveris), kept even when its MusicXML has a different
    # number of measures: the vote can still use it if it matches the final measures
    layout: list[LayoutSystem] | None = None

    @property
    def verses(self) -> int:
        return max(
            (v for m in self.measures for evs in m.voices.values() for e in evs for v in e.lyrics),
            default=0,
        )


# --------------------------------------------------------------------------- reading MusicXML


def _clef_name(c) -> str:
    sign = getattr(c, "sign", "G")
    if sign == "G" and getattr(c, "octaveChange", 0) == -1:
        return "G8vb"
    return sign if sign in ("G", "F", "C") else "G"


def _read_staff_measure(m: stream.Measure, part_index: int, pos: int, state: dict) -> Staff:
    for c in m.recurse().getElementsByClass("Clef"):
        if c.offset == 0 or c.activeSite is m:
            state["clef"] = _clef_name(c)
            break
    if m.timeSignature is not None:
        state["time"] = (m.timeSignature.numerator, m.timeSignature.denominator)
    if m.keySignature is not None:
        state["key"] = m.keySignature.sharps
    tempo = None
    for mm in m.recurse().getElementsByClass("MetronomeMark"):
        if mm.number:
            tempo = float(mm.number)
            break

    layers: list[list[RawEvent]] = []
    lyrics: dict[Fraction, dict[int, tuple[str, str]]] = {}
    for container in (list(m.voices) or [m]):
        layer_id = str(container.id) if container is not m else ""
        layer = []
        for el in container.notesAndRests:
            if el.duration.isGrace:
                continue
            off, dur = F(el.offset), F(el.quarterLength)
            if el.isRest:
                layer.append(RawEvent(off, dur, [], [], hidden=bool(el.style.hideObjectOnPrint),
                                      layer=layer_id, source_id=id(el)))
                continue
            notes = list(el.notes) if el.isChord else [el]
            notes.sort(key=lambda n: n.pitch.ps)
            # In a chord each note carries its own tie (soprano tied, alto not).
            ties = [(n.tie.type if n.tie else None) for n in notes]
            # MusicXML gives a chord's stem on each of its notes.
            stem = next((d for d in [el.stemDirection] + [n.stemDirection for n in notes]
                         if d in ("up", "down")), "")
            layer.append(RawEvent(off, dur, [n.pitch for n in notes], ties, layer=layer_id, source_id=id(el),
                                  stem=stem))
            for ly in el.lyrics:
                if ly.text and ly.text.strip():
                    lyrics.setdefault(off, {})[ly.number or 1] = (ly.text.strip(), ly.syllabic or "single")
        layers.append(layer)
    marks = _read_marks(m)
    texts = [(F(t.getOffsetInHierarchy(m)), str(t.content)) for t in m.recurse().getElementsByClass("TextExpression")
             if t.content and not _is_sign_text(str(t.content))]
    return Staff(part_index, pos, state["clef"], state["time"], state["key"], tempo, layers, lyrics,
                 marks, texts)


def _is_sign_text(text: str) -> bool:
    probe = Marks()
    _text_mark(text, probe)
    return probe != Marks() or bool(re.fullmatch(r"[\d\s|_.]*", text))  # a jump, Fine, a measure number


_JUMPS = [  # (regex on the lower-cased text, canonical jump); longest first
    (r"d\.?\s*s\.?\s*al\s*coda|dal\s*segno\s*al\s*coda|^\s*[ds]\.?\s*al\s*coda", "D.S. al Coda"),
    (r"d\.?\s*s\.?\s*al\s*fine|dal\s*segno\s*al\s*fine", "D.S. al Fine"),
    (r"d\.?\s*c\.?\s*al\s*coda|da\s*capo\s*al\s*coda", "D.C. al Coda"),
    (r"d\.?\s*c\.?\s*al\s*fine|da\s*capo\s*al\s*fine", "D.C. al Fine"),
    (r"^\s*d\.?\s*s\.?\s*$|^\s*dal\s*segno\s*$", "D.S."),
    (r"^\s*d\.?\s*c\.?\s*$|^\s*da\s*capo\s*$", "D.C."),
]
_REPEAT_EXPRESSIONS = {"DalSegnoAlCoda": "D.S. al Coda", "DalSegnoAlFine": "D.S. al Fine",
                       "DaCapoAlCoda": "D.C. al Coda", "DaCapoAlFine": "D.C. al Fine",
                       "DalSegno": "D.S.", "DaCapo": "D.C."}


def _text_mark(text: str, marks: Marks) -> None:
    import re

    low = text.strip().lower()
    for rx, jump in _JUMPS:
        if re.search(rx, low):
            marks.jump = jump
            return
    if re.fullmatch(r"fine\.?", low):
        marks.fine = True
    elif re.fullmatch(r"(to|al)\s*coda\.?", low):
        marks.to_coda = True


def _read_marks(m: stream.Measure) -> Marks:
    from music21 import bar

    mk = Marks()
    if isinstance(m.leftBarline, bar.Repeat):
        mk.repeat_start = True
    rb = m.rightBarline
    if isinstance(rb, bar.Repeat):
        mk.repeat_end = True
    elif rb is not None and rb.type in ("double", "light-light"):
        mk.barline = "double"
    elif rb is not None and rb.type in ("final", "light-heavy"):
        mk.barline = "final"
    for el in m.recurse():
        name = type(el).__name__
        if name == "Dynamic" and el.value:
            mk.dynamics.append(("", F(el.getOffsetInHierarchy(m)), str(el.value)))
        elif name == "Segno":
            mk.segno = True
        elif name == "Coda":
            mk.coda = True
        elif name in _REPEAT_EXPRESSIONS:
            mk.jump = _REPEAT_EXPRESSIONS[name]
        elif name == "Fine":
            mk.fine = True
        elif name == "TextExpression" and el.content:
            _text_mark(str(el.content), mk)
    return mk


def _read_spanner_marks(score: stream.Score, parts: list, per_part: list[list[Staff]]) -> None:
    """Endings (1st/2nd time) and hairpins live in spanners across measures: attach them."""
    where_measure: dict[int, tuple[int, int]] = {}
    where_note: dict[int, tuple[int, int, Fraction]] = {}
    for pi, part in enumerate(parts):
        for j, m in enumerate(part.getElementsByClass(stream.Measure)):
            where_measure[id(m)] = (pi, j)
            for el in m.recurse().notesAndRests:
                off = F(el.getOffsetInHierarchy(m))
                where_note[id(el)] = (pi, j, off)
                for n in getattr(el, "notes", ()):
                    where_note[id(n)] = (pi, j, off)
    for sp in score.recurse().getElementsByClass("RepeatBracket"):
        numbers = [x for x in getattr(sp, "numberRange", []) if x]
        if not numbers:
            continue
        number, last = min(numbers), max(numbers)
        # the bracket lists only the measures where it starts and stops: fill the ones between
        spots = [where_measure[id(m)] for m in sp.getSpannedElements() if id(m) in where_measure]
        for pi in {p for p, _ in spots}:
            js = [j for p, j in spots if p == pi]
            for j in range(min(js), max(js) + 1):
                if j < len(per_part[pi]):
                    per_part[pi][j].marks.volta = number
                    per_part[pi][j].marks.volta_to = last if last > number else None
    for sp in score.recurse().getElementsByClass("DynamicWedge"):
        kind = "crescendo" if type(sp).__name__ == "Crescendo" else "diminuendo"
        a, b = sp.getFirst(), sp.getLast()
        if a is None or id(a) not in where_note:
            continue
        pi, j, off = where_note[id(a)]
        if j < len(per_part[pi]):
            per_part[pi][j].marks.wedges.append(("", off, kind))
        if b is not None and id(b) in where_note:
            pi2, j2, off2 = where_note[id(b)]
            if j2 < len(per_part[pi2]):
                per_part[pi2][j2].marks.wedges.append(("", off2, "stop"))


def _system_starts(part: stream.Part) -> list[int]:
    starts = [0]
    for i, m in enumerate(part.getElementsByClass(stream.Measure)):
        # a new page also starts a new system (Audiveris writes only <print new-page> there)
        if i and any(sl.isNew for sl in m.getElementsByClass((m21layout.SystemLayout, m21layout.PageLayout))):
            starts.append(i)
    return starts


# --------------------------------------------------------------------------- voice splitting


def _overlaps(a0, a1, spans) -> bool:
    return any(a0 < b1 and b0 < a1 for b0, b1 in spans)


def _mean_pitch(layer: list[RawEvent]) -> float:
    ps = [p.ps for e in layer for p in e.pitches]
    return sum(ps) / len(ps) if ps else 0.0


def _pick(raw: RawEvent, which: str) -> Event:
    i = -1 if which == "top" else 0
    p = raw.pitches[i]
    return Event(raw.offset, raw.duration, p.nameWithOctave, int(p.midi), p.step,
                 float(p.accidental.alter) if p.accidental else 0.0, raw.ties[i], slur_cont=raw.slur_cont)


def _mark_slurs(score: stream.Score, per_part: list[list["Staff"]]) -> None:
    """Flag the notes inside each slur (after its first note) as melisma continuations."""
    where: dict[int, tuple[int, int, RawEvent]] = {}
    for pi, staves in enumerate(per_part):
        for j, st in enumerate(staves):
            for layer in st.layers:
                for raw in layer:
                    where[raw.source_id] = (pi, j, raw)
    for slur in score.recurse().getElementsByClass("Slur"):
        els = slur.getSpannedElements()
        if len(els) < 2:
            continue
        a, b = where.get(id(els[0])), where.get(id(els[-1]))
        if not a or not b or a[0] != b[0]:
            continue
        pi, (j0, r0), (j1, r1) = a[0], (a[1], a[2]), (b[1], b[2])
        start, end = (j0, r0.offset), (j1, r1.offset)
        if end <= start:
            continue
        for j in range(j0, j1 + 1):
            for layer in per_part[pi][j].layers:
                for raw in layer:
                    if raw.pitches and raw.layer == r0.layer and start < (j, raw.offset) <= end:
                        raw.slur_cont = True


def _voice_from(primary, fallbacks, which: str, length: Fraction) -> list[Event]:
    """Notes of `primary`, gaps filled with notes of `fallbacks`, remaining gaps as rests.

    Order of precedence: this voice's notes, the other voice's notes (a shared note head),
    this voice's printed rests (a voice entering late), the other voice's rests (one rest
    printed for both voices of the staff, «Bálsamo existe»). Giving this voice's rests
    precedence over the other voice's notes was tried: homr often gives a rest to the wrong
    voice, and «Jamás podrá alguien separarnos» lost bass notes."""
    events: list[Event] = []
    spans: list[tuple[Fraction, Fraction]] = []

    def take(layer, notes: bool) -> None:
        for raw in layer:
            if notes and raw.pitches:
                ev = _pick(raw, which)
            elif not notes and not raw.pitches and not raw.hidden:
                ev = Event(raw.offset, raw.duration)
            else:
                continue
            if not _overlaps(raw.offset, raw.offset + raw.duration, spans):
                events.append(ev)
                spans.append((raw.offset, raw.offset + raw.duration))

    take(primary, True)
    for layer in fallbacks:
        take(layer, True)
    take(primary, False)
    for layer in fallbacks:
        take(layer, False)
    events.sort(key=lambda e: e.offset)
    out, t = [], Fraction(0)
    end = max([length] + [e.end for e in events])
    for e in events:
        if e.offset > t:
            out.append(Event(t, e.offset - t, filled=True))
        out.append(e)
        t = max(t, e.end)
    if t < end:
        out.append(Event(t, end - t, filled=True))
    return out


def _stem_of(layer: list[RawEvent]) -> str:
    """The layer's stem direction when every note gives the same one, else ""."""
    stems = [e.stem for e in layer if e.pitches]
    return stems[0] if stems and stems[0] and all(x == stems[0] for x in stems) else ""


def _crossing(upper: list[RawEvent], lower: list[RawEvent]) -> float:
    """How far (semitones) `lower` rises above `upper` where both sound at once."""
    worst = 0.0
    for a in upper:
        for b in lower:
            if a.pitches and b.pitches and a.offset < b.offset + b.duration and b.offset < a.offset + a.duration:
                worst = max(worst, b.pitches[-1].ps - a.pitches[-1].ps)
    return worst


def _order_layers(layers: list[list[RawEvent]]) -> list[list[RawEvent]]:
    """Upper voice first. Two printed voices are told apart by their stems (up = upper voice),
    not by pitch: the alto may sit above the soprano for a few notes («Castillo fuerte»: alto
    holds c♭ while the soprano runs c♭ b♭ a♭ g♭). With no stems at all, the engine's voice
    numbers (1 = upper). With partial stems (a muddled reading) or none of that, mean pitch.
    Voices in a hymn cross by a little, never by more than a fifth: a wider crossing is a
    misread note («Todas las promesas»: homr put the bass a♭2 an octave up), so mean pitch."""
    by_pitch = sorted(layers, key=_mean_pitch, reverse=True)
    if len(layers) != 2:
        return by_pitch
    order = None
    if sorted(_stem_of(l) for l in layers) == ["down", "up"]:
        order = sorted(layers, key=lambda l: _stem_of(l) != "up")
    else:
        ids = [l[0].layer for l in layers]
        no_stems = not any(e.stem for l in layers for e in l)
        if no_stems and all(i.isdigit() for i in ids) and ids[0] != ids[1]:
            order = sorted(layers, key=lambda l: int(l[0].layer))
    if order is None or _crossing(order[0], order[1]) > 7:
        return by_pitch
    return order


def _split_staff(staff: Staff, n: int, length: Fraction) -> list[list[Event]]:
    """Split one staff into n (1 or 2) voices: upper takes top notes, lower bottom notes."""
    note_layers = _order_layers([l for l in staff.layers if any(e.pitches for e in l)])
    if not note_layers:
        # Only rests (e.g. a silent bar between verses): keep the visible ones.
        rests = max(staff.layers, key=lambda l: sum(e.duration for e in l if not e.hidden), default=[])
        return [_voice_from(rests, [], "top", length) for _ in range(n)]
    upper = _voice_from(note_layers[0], note_layers[1:], "top", length)
    if n == 1:
        voices = [upper]
    else:
        voices = [upper, _voice_from(note_layers[-1], note_layers[-2::-1], "bottom", length)]
    for v in voices:
        for e in v:
            if not e.is_rest and e.offset in staff.lyrics:
                e.lyrics = dict(staff.lyrics[e.offset])
    return voices


def _assign(staves: list[Staff], upper_clefs: set | None = None) -> list[tuple[Staff, int, int]] | None:
    """(staff, voices_in_staff, first_voice_index) for each staff, or None if not SATB-like.

    upper_clefs: clefs of the upper staff in this piece's two-staff systems. A lone staff with
    one of them is the upper staff (a men's quartet prints its upper staff in the octave treble
    clef, which otherwise would mean tenors)."""
    n = len(staves)
    if n == 1:  # solo passage: the other staff is silent (or not printed at all)
        upper = CLEF_RANK[staves[0].clef] == 0 or staves[0].clef in (upper_clefs or set())
        return [(staves[0], 2, 0 if upper else 2)]
    if n == 4:
        return [(s, 1, i) for i, s in enumerate(staves)]
    if n == 2:
        return [(staves[0], 2, 0), (staves[1], 2, 2)]
    if n == 3:
        if CLEF_RANK[staves[1].clef] == 0:  # G G F -> S, A, TB
            return [(staves[0], 1, 0), (staves[1], 1, 1), (staves[2], 2, 2)]
        return [(staves[0], 2, 0), (staves[1], 1, 2), (staves[2], 1, 3)]
    return None


# --------------------------------------------------------------------------- building


def _fit_layout(layout: list[LayoutSystem], counts: list[int]) -> list[LayoutSystem] | None:
    """Match the page geometry to the MusicXML system by system. A system may show one
    measure-wide slot more than it has measures (a courtesy key or time signature at the end
    of a line): the narrowest slot is dropped."""
    import copy

    if len(layout) != len(counts):
        return None
    out = []
    for s, n in zip(layout, counts):
        if len(s.stacks) == n:
            out.append(s)
        elif len(s.stacks) == n + 1:
            drop = min(range(len(s.stacks)), key=lambda k: s.stacks[k][1] - s.stacks[k][0])
            fixed = copy.copy(s)
            fixed.stacks = [st for k, st in enumerate(s.stacks) if k != drop]
            out.append(fixed)
        else:
            return None
    return out


def _stacks_aligned(a: LayoutSystem, b: LayoutSystem, page_width: float) -> bool:
    if len(a.stacks) != len(b.stacks):
        return False
    tol = 0.03 * page_width
    return all(abs(x[1] - y[1]) <= tol for x, y in zip(a.stacks[:-1], b.stacks[:-1]))


_ENDING_NUMBER = re.compile(r'(<ending\b[^>]*?\bnumber=")([^"]*)(")')


def _ending_number(text: str) -> str:
    """Audiveris writes what it read in an ending bracket: "1.-6." comes out as "1,,6", which
    music21 cannot read (the whole reading was lost). Two numbers are a range ("1, 2" and
    "1-6" alike); more are a list."""
    numbers = sorted({int(x) for x in re.findall(r"\d+", text)})
    if not numbers:
        return text
    if len(numbers) == 2:
        return f"{numbers[0]}-{numbers[1]}"
    return ", ".join(str(x) for x in numbers)


def _parse(path: Path):
    """converter.parse, after tidying the ending numbers the engines write."""
    raw = None
    try:
        if path.suffix.lower() == ".mxl":
            import zipfile

            with zipfile.ZipFile(path) as z:
                inner = next((n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF")), None)
                raw = z.read(inner).decode("utf-8", "replace") if inner else None
        elif path.suffix.lower() in (".xml", ".musicxml"):
            raw = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError, KeyError):
        raw = None
    if raw is not None:
        fixed = _ENDING_NUMBER.sub(lambda m: m.group(1) + _ending_number(m.group(2)) + m.group(3), raw)
        if fixed != raw:
            return converter.parseData(fixed, format="musicxml")
    return converter.parse(str(path))


def build_choral_score(xml_path: Path, layout: list[LayoutSystem] | None = None) -> ChoralScore:
    # music21 prints import warnings ("ties left open") to stderr; the rules report those properly.
    with contextlib.redirect_stderr(io.StringIO()):
        score = _parse(Path(xml_path))
    if isinstance(score, stream.Opus):
        score = score.scores[0]
    parts = list(score.parts)
    issues: list[Issue] = []

    # 1. read every staff-measure of every part
    per_part: list[list[Staff]] = []
    for pi, part in enumerate(parts):
        state = {"clef": "G", "time": (4, 4), "key": 0}
        per_part.append([
            _read_staff_measure(m, pi, i, state)
            for i, m in enumerate(part.getElementsByClass(stream.Measure))
        ])
    n_measures = min(len(p) for p in per_part)

    _mark_slurs(score, per_part)
    _read_spanner_marks(score, parts, per_part)

    raw_layout = layout
    # 2. system boundaries (layout if it matches the MusicXML, else <print new-system>)
    if layout and sum(len(s.stacks) for s in layout) == n_measures:
        bounds, i = [], 0
        for s in layout:
            bounds.append((i, i + len(s.stacks)))
            i += len(s.stacks)
    else:
        # parts may differ in length (merged movements): only use the measures all parts have
        starts = [s for s in _system_starts(parts[0]) if s < n_measures] + [n_measures]
        bounds = [(a, b) for a, b in zip(starts, starts[1:]) if a < b]
        if layout:
            fitted = _fit_layout(layout, [b - a for a, b in bounds])
            if fitted is None:
                issues.append(Issue("estructura", "info",
                                    "La geometría de Audiveris no coincide con el MusicXML; el reporte irá sin recortes."))
            layout = fitted

    # 3. the staves with content in each system (top to bottom)
    systems = []
    for si, (a, b) in enumerate(bounds):
        staff_rows = [
            [per_part[pi][j] for j in range(a, b)]
            for pi in range(len(parts))
            if any(per_part[pi][j].has_notes for j in range(a, b))
        ]
        systems.append({"rows": staff_rows, "layout": [layout[si]] if layout else [], "count": b - a})

    # 4. repair systems whose staves were detected as separate systems
    target = max((len(s["rows"]) for s in systems), default=0)
    page_w = max((st.right for s in (layout or []) for st in s.staves), default=1)
    merged = []
    for s in systems:
        prev = merged[-1] if merged else None
        if (prev and len(prev["rows"]) + len(s["rows"]) <= max(target, 2)
                and prev["count"] == s["count"] and s["rows"] and prev["rows"]
                # the upper staff of a choir system has a higher clef than the lower one: two
                # one-staff systems in the same clef are two solo systems one after the other
                # («Primer mandamiento» c.45-52: the men in unison, bass clef, two systems)
                and CLEF_RANK[prev["rows"][-1][0].clef] < CLEF_RANK[s["rows"][0][0].clef]
                and (not (prev["layout"] and s["layout"])
                     or _stacks_aligned(prev["layout"][-1], s["layout"][0], page_w))):
            prev["rows"] += s["rows"]
            prev["layout"] += s["layout"]
            prev["repaired"] = True
            continue
        merged.append(s)

    # 5. text attached as lyrics to a staff that has lyrics in only a few systems
    #    (a copyright line at the page bottom, a footnote...) is not lyrics: drop it.
    _drop_stray_lyrics(merged, issues)
    _words_for_solos(merged, issues)
    for si, s in enumerate(merged, start=1):
        _renumber_verses(s, si, issues)
    _align_verse_numbers(merged, issues)

    # 6. canonical measures
    measures: list[Measure] = []
    lower_clefs = {s["rows"][1][0].clef for s in merged if len(s["rows"]) == 2 and s["rows"][1]}
    upper_clefs = {s["rows"][0][0].clef for s in merged if len(s["rows"]) == 2 and s["rows"][0]} - lower_clefs
    for si, s in enumerate(merged, start=1):
        if s.get("repaired"):
            issues.append(Issue("estructura", "info",
                                f"Sistema {si}: el motor separó sus pentagramas en sistemas distintos; se volvieron a unir.",
                                measure=len(measures)))
        assignment = None
        for j in range(s["count"]):
            staves = [row[j] for row in s["rows"]]
            m = Measure(index=len(measures), system=si, page=s["layout"][0].page if s["layout"] else None,
                        staves=staves)
            ref = staves[0] if staves else None
            if ref:
                m.time, m.key_fifths = ref.time, ref.key_fifths
            m.bar_length = m.duration = F(Fraction(4 * m.time[0], m.time[1]))
            if s["layout"]:
                m.bbox = _bbox(s["layout"], j)
                m.geometry = _geometry(s["layout"], j, staves)
            assignment = _assign(staves, upper_clefs)
            if assignment is None:
                if j == 0:
                    issues.append(Issue("estructura", "error",
                                        f"Sistema {si}: {len(staves)} pentagrama(s) con notas; se esperaban 2, 3 o 4.",
                                        measure=m.index))
                m.voices = {v: [Event(Fraction(0), m.bar_length, filled=True)] for v in VOICES}
            else:
                for staff, k, first in assignment:
                    for off, evs in enumerate(_split_staff(staff, k, m.bar_length)):
                        m.voices[VOICES[first + off]] = evs
                for v in VOICES:  # voices not printed in this system rest
                    m.voices.setdefault(v, [Event(Fraction(0), m.bar_length)])
                if len(staves) == 1:
                    m.solo = "upper" if assignment[0][2] == 0 else "lower"
            m.marks = _measure_marks(staves, assignment)
            measures.append(m)

    _time_from_content(measures, issues)
    _detect_pickup_and_number(measures)
    md = score.metadata
    title = _biggest_credit(score) or ((md.title or md.movementName) if md else None)
    return ChoralScore(Path(xml_path), measures, issues, title, raw_layout)


def _measure_marks(staves: list[Staff], assignment) -> Marks:
    """One measure's marks: the union of its staves; staff-bound ones get their group."""
    groups = {}
    for staff, _k, first in (assignment or []):
        groups[id(staff)] = "upper" if first < 2 else "lower"
    out = Marks()
    for st in staves:
        mk, g = st.marks, groups.get(id(st), "upper")
        out.repeat_start |= mk.repeat_start
        out.repeat_end |= mk.repeat_end
        out.segno |= mk.segno
        out.coda |= mk.coda
        out.to_coda |= mk.to_coda
        out.fine |= mk.fine
        out.barline = out.barline or mk.barline
        out.volta = out.volta or mk.volta
        out.volta_to = out.volta_to or mk.volta_to
        out.jump = out.jump or mk.jump
        out.dynamics += [(g, off, v) for _, off, v in mk.dynamics]
        out.wedges += [(g, off, w) for _, off, w in mk.wedges]
    out.dynamics = sorted(set(out.dynamics))
    out.wedges = sorted(set(out.wedges))
    if out.repeat_end:
        out.barline = None
    return out


def _solo_syllables(text: str) -> list[tuple[str, str]]:
    """Plain text read under a solo -> syllables: '40 Gran-de es Dios, El es san - to' ->
    [('Gran','begin'), ('de','end'), ('es','single'), ...]."""
    from .lyrics_text import verse_syllables

    text = unicodedata.normalize("NFKC", text)                  # the "ﬁ" ligature -> "fi"
    text = re.sub(r"^\s*\d+\s*", "", text)                     # a measure number read with the words
    text = re.sub(r"\s*[-—–]+\s*", "-", text)                   # "a - mos" -> "a-mos"
    text = re.sub(r"[^\w\s,.;:!?¡¿'’-]", "", text)
    return [(s.text, s.syllabic) for s in verse_syllables(text)]


def _words_for_solos(systems: list[dict], issues: list[Issue]) -> None:
    """In a solo system (one printed staff) the engine may read the words as plain text instead
    of lyrics. Turn that text into syllables on the notes of the solo, in order."""
    for si, s in enumerate(systems, start=1):
        if len(s["rows"]) != 1:
            continue
        row = s["rows"][0]
        if any(st.lyrics for st in row):
            continue
        text = " ".join(t for st in row for _, t in sorted(st.texts))
        syllables = _solo_syllables(text)
        if not syllables:
            continue
        slots = []
        for st in row:
            layer = max(st.layers, key=lambda l: sum(1 for e in l if e.pitches), default=[])
            slots += [(st, e.offset) for e in layer if e.pitches and not e.slur_cont
                      and not any(t in ("stop", "continue") for t in e.ties)]
        for (st, off), (txt, syl) in zip(slots, syllables):
            st.lyrics.setdefault(off, {})[1] = (txt, syl)
        for st in row:
            st.texts = []
        issues.append(Issue("estructura", "info",
                            f"Sistema {si}: la letra del solo venía como texto suelto; se repartió en sus notas "
                            f"({min(len(slots), len(syllables))} sílabas)."))


def _drop_stray_lyrics(systems: list[dict], issues: list[Issue]) -> None:
    # A solo system (one staff) at the bottom of a page may get the page footer ("Coro Voces
    # Reunidas") as its lyrics. Sung words are split into syllables somewhere ("Gran-de");
    # a few whole words and nothing split is not a sung line.
    for si, s in enumerate(systems, start=1):
        if len(s["rows"]) != 1:
            continue
        row = s["rows"][0]
        sylls = [(t, syl) for st in row for d in st.lyrics.values() for t, syl in d.values()]
        if sylls and len(sylls) <= 4 and all(syl == "single" for _, syl in sylls):
            for st in row:
                st.lyrics = {}
            issues.append(Issue("estructura", "info",
                                f"Sistema {si}: se descartó texto que no parece letra: "
                                f"«{' '.join(t for t, _ in sylls)[:80]}»."))
    if len(systems) < 2:
        return
    n_rows = max(len(s["rows"]) for s in systems)
    has = [[r < len(s["rows"]) and any(st.lyrics for st in s["rows"][r]) for r in range(n_rows)] for s in systems]
    share = [sum(h[r] for h in has) / len(systems) for r in range(n_rows)]
    if max(share) < 0.5:
        return
    for si, s in enumerate(systems, start=1):
        for r, row in enumerate(s["rows"]):
            if share[r] < 0.5 and has[si - 1][r]:
                sylls = [syl for st in row for d in st.lyrics.values() for _, syl in d.values()]
                if len(sylls) >= 6 and sum(syl != "single" for syl in sylls) >= 3:
                    continue  # sung words split into syllables: a stanza for this staff's voices
                words = [t for st in row for d in st.lyrics.values() for t, _ in d.values()]
                for st in row:
                    st.lyrics = {}
                issues.append(Issue("estructura", "info",
                                    f"Sistema {si}: se descartó texto que no parece letra: «{' '.join(words)[:80]}»."))


def _time_from_content(measures: list[Measure], issues: list[Issue]) -> None:
    """A time signature the engine missed: «Campeón de amor» goes 4/4 → 2/4 → 4/4 several times;
    Audiveris saw the 2/4 but not the way back and kept 2/4 for 30 measures, homr read 3/4.
    When every voice that sings in a measure fills exactly the same length, longer than the
    bar read, and that length is a bar of a time signature printed elsewhere in the piece,
    the measure is in that time. One voice overflowing (a misread note) changes nothing."""
    printed = {}
    for m in measures:
        printed.setdefault(m.bar_length, m.time)
    for m in measures:
        ends = [max(e.end for e in evs if not e.filled)
                for evs in m.voices.values() if any(not e.is_rest for e in evs)]
        if len(ends) < 2 or len(set(ends)) != 1:
            continue
        length = ends[0]
        if length <= m.bar_length or length not in printed:
            continue
        issues.append(Issue("estructura", "info",
                            f"Compás de {length} tiempos leído como {m.time[0]}/{m.time[1]}: "
                            f"se toma {printed[length][0]}/{printed[length][1]}.", m.index))
        m.time = printed[length]
        m.bar_length = m.duration = length
        for st in m.staves:
            st.time = m.time
        for v, evs in m.voices.items():  # a trailing filled gap past the new bar goes
            m.voices[v] = [e for e in evs if e.offset < length]


def _biggest_credit(score) -> str | None:
    """The title is the biggest text on the first page. Engines sometimes call a publisher
    line the title ("Maranatha Music — The Praise Series" over "Oh, Dios y Padre")."""
    from music21 import text as m21text

    boxes = [t for t in score.getElementsByClass(m21text.TextBox)
             if (t.page or 1) == 1 and t.content and t.content.strip() and t.style.fontSize
             and any(c.isalpha() for c in t.content)]
    if not boxes:
        return None
    best = max(boxes, key=lambda t: float(t.style.fontSize))
    return best.content.strip()


def _renumber_verses(system: dict, si: int, issues: list[Issue]) -> None:
    """Fix lyric line numbers inside one system.

    Engines number lyric lines top to bottom. A stray mark read as an extra line
    (a lone "F", a dash) shifts every real verse by one. Lines with very few
    syllables compared with the fullest line are dropped, and the remaining lines
    are renumbered 1, 2, 3... in their original order.
    """
    staves = [st for row in system["rows"] for st in row]
    counts: dict[int, int] = {}
    for st in staves:
        for d in st.lyrics.values():
            for n in d:
                counts[n] = counts.get(n, 0) + 1
    if len(counts) < 2:
        return
    fullest = max(counts.values())
    keep = sorted(n for n, c in counts.items() if c >= max(2, 0.25 * fullest))
    dropped = sorted(set(counts) - set(keep))
    mapping = {old: new for new, old in enumerate(keep, start=1)}
    if not dropped and all(k == v for k, v in mapping.items()):
        return
    removed = []
    for st in staves:
        for off, d in list(st.lyrics.items()):
            removed += [d[n][0] for n in d if n in dropped]
            st.lyrics[off] = {mapping[n]: v for n, v in d.items() if n in mapping}
    if dropped:
        issues.append(Issue("estructura", "info",
                            f"Sistema {si}: se descartó una línea de letra casi vacía («{' '.join(removed)}») "
                            f"y se renumeraron las estrofas."))


def _system_lines(system: dict) -> set[int]:
    return {n for row in system["rows"] for st in row for d in st.lyrics.values() for n in d}


def _align_verse_numbers(systems: list[dict], issues: list[Issue]) -> None:
    """A system whose lyric lines are numbered oddly ({2} where every other system has {1}).

    Engines sometimes start counting at 2 in one system (a stray mark above taken as a
    line, then dropped). If the system has as many lines as most systems, its lines are
    the usual verses: renumber them 1..k. A system with fewer lines keeps its numbers
    (it may have lost verse 1, and verse 2 must stay verse 2).
    """
    sets = [_system_lines(s) for s in systems]
    sizes = [len(x) for x in sets if x]
    if not sizes:
        return
    modal = max(set(sizes), key=lambda k: (sizes.count(k), k))
    for si, (s, lines) in enumerate(zip(systems, sets), start=1):
        if len(lines) != modal or lines == set(range(1, modal + 1)):
            continue
        mapping = {old: new for new, old in enumerate(sorted(lines), start=1)}
        for row in s["rows"]:
            for st in row:
                for off, d in list(st.lyrics.items()):
                    st.lyrics[off] = {mapping[n]: v for n, v in d.items()}
        issues.append(Issue("estructura", "info",
                            f"Sistema {si}: las líneas de letra venían numeradas {sorted(lines)}; "
                            f"se renumeraron como en el resto de la partitura."))


def _geometry(systems: list[LayoutSystem], j: int, staves: list[Staff]) -> dict | None:
    boxes = [st for s in systems for st in s.staves]
    if len(boxes) != len(staves):
        return None  # layout staves and content staves do not correspond one to one
    x0 = min(s.stacks[j][0] for s in systems)
    if j == 0:  # skip the clef/key/time header at the start of the system
        x0 = max([x0] + [b.header_stop for b in boxes])
    x1 = max(s.stacks[j][1] for s in systems)
    xm = (x0 + x1) / 2  # staff lines can bend or tilt: measure them where this measure is
    return {
        "page": systems[0].page,
        "x0": x0,
        "x1": x1,
        "staves": [(b.top_at(xm), (b.bottom_at(xm) - b.top_at(xm)) / 4) for b in boxes],
        "clefs": [st.clef for st in staves],
    }


def _bbox(systems: list[LayoutSystem], j: int) -> tuple[int, int, int, int]:
    il = systems[0].interline
    x0 = min(s.stacks[j][0] for s in systems)
    x1 = max(s.stacks[j][1] for s in systems)
    y0 = min(st.top for s in systems for st in s.staves) - 6 * il  # room for segno, coda, 1st/2nd endings
    y1 = max(st.bottom for s in systems for st in s.staves) + 3 * il
    return int(x0 - il), int(max(0, y0)), int(x1 + il), int(y1)


def _content_end(events: list[Event]) -> Fraction:
    return max((e.end for e in events if not e.filled), default=Fraction(0))


def _detect_pickup_and_number(measures: list[Measure]) -> None:
    if not measures:
        return
    first = measures[0]
    longest = max((_content_end(v) for v in first.voices.values()), default=Fraction(0))
    if 0 < longest < first.bar_length:
        first.pickup = True
        first.duration = longest
        for name, evs in first.voices.items():  # trim the padding added by the splitter
            first.voices[name] = [e for e in evs if e.offset < longest]
            if first.voices[name] and first.voices[name][-1].end > longest and first.voices[name][-1].filled:
                first.voices[name][-1].duration = longest - first.voices[name][-1].offset
    for m in measures:
        m.number = m.index if first.pickup else m.index + 1
