"""Measures added or removed by hand, and time or key signatures changed by hand.

In <run>/correcciones.json:

    {"structure": [{"op": "insert", "at": 12}, {"op": "delete", "at": 30}],
     "signatures": {"12": {"time": [3, 4], "scope": "run"}, "40": {"key": -2, "scope": "one"}}}

"structure" is applied in order, right after the vote: «insert at 12» puts a measure of rests at
position 12 (what was 12 becomes 13), «delete at 30» takes position 30 away; then every measure is
renumbered. Every other correction (marks, voices, edits, rhythm, lyrics...) refers to the measures
as they are after that: when the user adds or removes a measure, `rekey` moves the keys of the
saved corrections so that each one stays on its measure.

"signatures": from that measure, the time or key signature the user gave. "run" = that measure and
the ones after it that the engines read with the same signature as it ("the 2/4 that should be
4/4, from here until the reading changes"); "one" = that measure only. A new key spells again the
notes that followed the old key (B♭ in F major becomes B♮ in C); printed accidentals stay.
"""

from __future__ import annotations

import copy
from fractions import Fraction

from .score import VOICES, ChoralScore, Event, Marks, Measure

KEYED = ("marks", "voices", "edits", "rhythm", "lyrics", "voice_lyrics", "signatures")


# --------------------------------------------------------------------------- the user's corrections follow their measures
def rekey(data: dict, op: dict) -> dict:
    """The saved corrections after adding or removing a measure (in place; returns data)."""
    at = int(op["at"])
    for name in KEYED:
        old = data.get(name)
        if not isinstance(old, dict):
            continue
        new = {}
        for key, val in old.items():
            try:
                i = int(key)
            except (TypeError, ValueError):
                new[key] = val
                continue
            if op["op"] == "insert":
                new[str(i + 1 if i >= at else i)] = val
            elif i != at:   # delete: that measure's corrections go with it
                new[str(i - 1 if i > at else i)] = val
        data[name] = new
    return data


# --------------------------------------------------------------------------- adding and removing measures
def apply_structure(cs: ChoralScore, data: dict) -> dict[int, int | None]:
    """Insert and delete measures as the user asked. Returns where each measure of the vote went
    (old index → new index, None = deleted), for what was computed before (issues, details)."""
    ops = [op for op in (data.get("structure") or []) if isinstance(op, dict) and op.get("op") in ("insert", "delete")]
    if not ops:
        return {m.index: m.index for m in cs.measures}
    origin = [m.index for m in cs.measures]   # vote index of the measure at each place (None = added)
    for op in ops:
        try:
            at = int(op["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if op["op"] == "insert" and 0 <= at <= len(cs.measures):
            cs.measures.insert(at, blank_like(cs.measures, at))
            origin.insert(at, None)
        elif op["op"] == "delete" and 0 <= at < len(cs.measures) and len(cs.measures) > 1:
            del cs.measures[at]
            del origin[at]
    renumber(cs)
    where: dict[int, int | None] = {}
    for new, old in enumerate(origin):
        if old is not None:
            where[old] = new
    return where


def renumber(cs: ChoralScore) -> None:
    first_pickup = bool(cs.measures) and cs.measures[0].pickup
    for k, m in enumerate(cs.measures):
        m.index = k
        if k > 0 and m.pickup:   # only the first measure can be an upbeat
            m.pickup, m.duration = False, m.bar_length
        m.number = k if first_pickup else k + 1


def blank_like(measures: list[Measure], at: int) -> Measure:
    """A measure of rests in every voice, with the signatures of the measure before (or after)."""
    near = measures[at - 1] if at > 0 else measures[0]
    if near.pickup:   # an upbeat is short: the signatures of a full measure
        near = next((x for x in measures if not x.pickup), near)
    m = Measure(index=at, system=near.system, page=near.page, staves=[], time=near.time,
                key_fifths=near.key_fifths, bar_length=near.bar_length, duration=near.bar_length)
    for st in near.staves:   # same staves (clefs), with nothing on them
        s = copy.copy(st)
        s.layers, s.lyrics, s.texts, s.marks = [], {}, [], Marks()
        m.staves.append(s)
    m.voices = {v: [Event(Fraction(0), m.bar_length)] for v in VOICES}
    m.solo = near.solo
    return m


# --------------------------------------------------------------------------- time and key signatures
def apply_signatures(cs: ChoralScore, data: dict) -> set[int]:
    """Put the signatures the user gave. Returns the measures changed."""
    wanted = data.get("signatures") or {}
    if not wanted:
        return set()
    ms = cs.measures
    read_time = [m.time for m in ms]       # as the engines read them, before any change
    read_key = [m.key_fifths for m in ms]
    changed: set[int] = set()
    for key in sorted(wanted, key=lambda x: int(x) if str(x).lstrip("-").isdigit() else 10**9):
        try:
            k = int(key)
        except (TypeError, ValueError):
            continue
        if not 0 <= k < len(ms):
            continue
        sig = wanted[key] or {}
        one = sig.get("scope") == "one"
        if "time" in sig:
            try:
                n, d = int(sig["time"][0]), int(sig["time"][1])
            except (TypeError, ValueError, IndexError):
                n = d = 0
            if 1 <= n <= 32 and d in (1, 2, 4, 8, 16, 32):
                for j in _span(read_time, k, one):
                    set_time(ms[j], (n, d))
                    changed.add(j)
        if "key" in sig:
            try:
                f = int(sig["key"])
            except (TypeError, ValueError):
                f = 99
            if -7 <= f <= 7:
                for j in _span(read_key, k, one):
                    set_key(ms[j], f)
                    changed.add(j)
    return changed


def _span(read: list, k: int, one: bool) -> range:
    if one:
        return range(k, k + 1)
    end = k + 1
    while end < len(read) and read[end] == read[k]:
        end += 1
    return range(k, end)


def set_time(m: Measure, time: tuple[int, int]) -> None:
    length = Fraction(4 * time[0], time[1])
    m.time, m.bar_length = time, length
    m.duration = min(m.duration, length) if m.pickup else length
    for st in m.staves:
        st.time = time
    for v, evs in list(m.voices.items()):
        # the rests the program added to fill the old measure go; a voice too short is filled again
        kept = [e for e in evs if not (e.filled and e.offset >= m.duration)]
        if kept and kept[-1].filled and kept[-1].end > m.duration:
            kept[-1] = copy.copy(kept[-1])
            kept[-1].duration = m.duration - kept[-1].offset
        end = max((e.end for e in kept), default=Fraction(0))
        if end < m.duration:
            kept.append(Event(end, m.duration - end, filled=True))
        m.voices[v] = kept


def set_key(m: Measure, fifths: int) -> None:
    from music21 import key, pitch

    from .corrections import _set_pitch

    old, new = key.KeySignature(m.key_fifths), key.KeySignature(fifths)

    def alter(ks, step: str) -> float:
        acc = ks.accidentalByStep(step)
        return float(acc.alter) if acc is not None else 0.0

    for evs in m.voices.values():
        for e in evs:
            if e.pitch is None:
                continue
            p = pitch.Pitch(e.pitch)
            if (float(p.accidental.alter) if p.accidental else 0.0) == alter(old, p.step):
                a = alter(new, p.step)
                p.accidental = pitch.Accidental(a) if a else None
                _set_pitch(e, p)
    m.key_fifths = fifths
    for st in m.staves:
        st.key_fifths = fifths
