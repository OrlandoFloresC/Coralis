"""Write the music out once per verse, the way the user's solfège app expects it.

    verse 1 | silent bar | verse 2 | silent bar | verse 3

Within each verse:
  - the pickup becomes a full measure, padded with beat rests in front (R R C4 in 3/4),
  - the final short measure is completed with rests,
  - only that verse's lyrics are kept (as lyric line 1), on every voice: each voice
    gets the syllable on its note that starts together with the soprano's syllable.
"""

from __future__ import annotations

import copy
from fractions import Fraction

from .repeats import lyric_line, performance_order
from .score import VOICES, ChoralScore, Event, Measure


def _beat_rests(start: Fraction, length: Fraction, beat: Fraction) -> list[Event]:
    """Rests covering [start, start+length), one per beat (as engravers write them)."""
    out, t, end = [], start, start + length
    while t < end:
        d = min(beat - (t % beat) if t % beat else beat, end - t)
        out.append(Event(t, d))
        t += d
    return out


def _pad_pickup(m: Measure) -> None:
    pad = m.bar_length - m.duration
    beat = Fraction(4, m.time[1])
    for v in VOICES:
        evs = [e for e in m.voices.get(v, []) if not (e.filled and e.is_rest)]
        for e in evs:
            e.offset += pad
        m.voices[v] = _beat_rests(Fraction(0), pad, beat) + evs
    m.pickup, m.duration = False, m.bar_length


def _complete_last(m: Measure) -> None:
    beat = Fraction(4, m.time[1])
    for v in VOICES:
        evs = [e for e in m.voices.get(v, []) if not (e.filled and e.is_rest)]
        end = max((e.end for e in evs), default=Fraction(0))
        if end < m.bar_length:
            evs += _beat_rests(end, m.bar_length - end, beat)
        m.voices[v] = evs


def _silent(template: Measure) -> Measure:
    m = copy.deepcopy(template)
    m.voices = {v: [Event(Fraction(0), m.bar_length)] for v in VOICES}
    m.pickup, m.duration = False, m.bar_length
    m.votes, m.alternatives, m.synth = {}, {}, None
    return m


def _refrain(cs: ChoralScore) -> dict[int, Fraction]:
    """Where the words are the same for every stanza (a chorus printed with one line under
    stanzas printed with several): {measure index: offset from which line 1 is sung by all}.

    A chorus is a run of at least 4 measures whose words are on line 1 only (measures with no
    words do not break it). The measure just before it gives line 1 from its last syllable
    of a stanza line on (the upbeat «Los» after «...quí?»).
    """
    def lines(m: Measure) -> set[int]:
        return {n for evs in m.voices.values() for e in evs for n in e.lyrics}

    out: dict[int, Fraction] = {}
    if max((max(lines(m), default=0) for m in cs.measures), default=0) < 2:
        return out
    run: list[int] = []
    for i, m in enumerate(cs.measures + [None]):
        ls = lines(m) if m is not None else {2}
        if ls <= {1}:
            run.append(i)
            continue
        worded = [k for k in run if lines(cs.measures[k])]
        if len(worded) >= 4:
            for k in run:
                out[k] = Fraction(0)
            first = run[0]
            if first > 0:
                prev = cs.measures[first - 1]
                multi = [e.end for evs in prev.voices.values() for e in evs if any(n >= 2 for n in e.lyrics)]
                if multi:
                    out[first - 1] = max(multi)
        run = []
    return out


def _keep_verse(m: Measure, verse: int, refrain_from: Fraction | None = None) -> None:
    """Only `verse` survives, as line 1, copied to every voice at the onsets of the voice
    that carries the words (the soprano; the men in a men-only passage). In a chorus
    (from `refrain_from` on) every stanza sings line 1."""
    syllables: dict = {}
    for v in VOICES:
        syllables = {e.offset: e.lyrics[verse] for e in m.voices.get(v, []) if verse in e.lyrics}
        if refrain_from is not None:
            syllables.update({e.offset: e.lyrics[1] for e in m.voices.get(v, [])
                              if 1 in e.lyrics and e.offset >= refrain_from})
        if syllables:
            break
    for v in VOICES:
        for e in m.voices.get(v, []):
            e.lyrics = {}
            if e.is_attack and e.offset in syllables:
                e.lyrics = {1: syllables[e.offset]}


def _content_length(m: Measure) -> Fraction:
    return max((e.end for evs in m.voices.values() for e in evs if not e.filled), default=Fraction(0))


def _sung_length(m: Measure) -> Fraction:
    return max((e.end for evs in m.voices.values() for e in evs if not e.filled and not e.is_rest),
               default=Fraction(0))


def _cut(evs: list[Event], length: Fraction, shift: Fraction = Fraction(0)) -> list[Event]:
    """Events inside [0, length), moved by `shift`; a gap at the end becomes a filled rest."""
    out = []
    for e in evs:
        if e.offset >= length:
            continue
        e = copy.deepcopy(e)
        e.duration = min(e.duration, length - e.offset)
        out.append(e)
    end = max((e.end for e in out), default=Fraction(0))
    if end < length:
        out.append(Event(end, length - end, filled=True))
    for e in out:
        e.offset += shift
    return out


def _join_marks(a: Measure, b: Measure, shift: Fraction) -> None:
    """Marks of `b` (the second half) move into `a`: right-side ones replace a's, the rest add up."""
    ma, mb = a.marks, b.marks
    ma.repeat_end, ma.barline, ma.jump = mb.repeat_end, mb.barline, mb.jump
    ma.fine |= mb.fine
    ma.to_coda |= mb.to_coda
    ma.volta = ma.volta or mb.volta
    ma.volta_to = ma.volta_to or mb.volta_to
    ma.dynamics = ma.dynamics + [(g, off + shift, v) for g, off, v in mb.dynamics]
    ma.wedges = ma.wedges + [(g, off + shift, w) for g, off, w in mb.wedges]


def merge_split_measures(cs: ChoralScore) -> ChoralScore:
    """Join measures that a system break cut in two.

    Hymnals end a phrase with a short measure and print the missing upbeat at the start
    of the next system ("na!" 5/8 | new system | "En" 1/8, in 6/8). The engines read two
    measures; music-wise it is one. Merge them when they add up to exactly one bar.
    """
    out = copy.deepcopy(cs)
    merged: list[Measure] = []
    ms = out.measures
    i = 0
    while i < len(ms):
        a = ms[i]
        b = ms[i + 1] if i + 1 < len(ms) else None
        # a repeat sign between them means two real measures (e.g. a 1st ending and the bar after)
        if (b is not None and not a.pickup and b.system != a.system and a.time == b.time
                and not a.marks.repeat_end and not b.marks.repeat_start and a.marks.volta == b.marks.volta):
            la, lb = _content_length(a), _content_length(b)
            if la + lb != a.bar_length:
                # the engines may write the missing part as rests: count up to the last note
                la, lb = _sung_length(a), _sung_length(b)
            if 0 < la < a.bar_length and 0 < lb < a.bar_length and la + lb == a.bar_length:
                for v in VOICES:
                    a.voices[v] = _cut(a.voices.get(v, []), la) + _cut(b.voices.get(v, []), lb, la)
                _join_marks(a, b, la)
                merged.append(a)
                i += 2
                continue
        merged.append(a)
        i += 1
    first_pickup = bool(merged) and merged[0].pickup
    for k, m in enumerate(merged):
        m.index, m.number = k, (k if first_pickup else k + 1)
    out.measures = merged
    return out


def expand_verses(cs: ChoralScore, n_verses: int | None = None) -> ChoralScore:
    """Each stanza written out in performance order (repeats unfolded), then the next one."""
    steps, _ = performance_order(cs)
    lines = lyric_line(cs, steps)
    n = n_verses or max(1, lines["stanzas"])
    refrain = _refrain(cs)
    out = copy.deepcopy(cs)
    measures: list[Measure] = []
    for verse in range(1, n + 1):
        block = [copy.deepcopy(cs.measures[s.index]) for s in steps]
        if not block:
            break
        if block[0].pickup:
            _pad_pickup(block[0])
        for m in block[1:]:
            if m.pickup:  # a repeat back to the very start passes the pickup again
                _pad_pickup(m)
        _complete_last(block[-1])
        for m, s in zip(block, steps):
            _keep_verse(m, verse + (s.pass_no - 1) * lines["shift"], refrain.get(s.index))
        if measures:
            measures.append(_silent(block[0]))
        measures += block
    for i, m in enumerate(measures):
        m.index, m.number = i, i + 1
    out.measures = measures
    return out
