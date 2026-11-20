"""The user's answers in the review: signs the engines missed or misread.

Saved in <run>/correcciones.json, separate from the readings, and applied after the vote,
so re-validating never loses them:

    {"marks": {"22": {"jump": "D.S. al Coda"}, "1": {"segno": true}, "0": {"multirest": 10}}}

Keys are measure indices of the voted score (0-based); each entry overrides only the
fields it names (false / null removes a sign the engines saw by mistake).
"""

from __future__ import annotations

import json
from dataclasses import fields
from fractions import Fraction
from pathlib import Path

from .issues import Issue
from .score import VOICES, ChoralScore, Event, Marks

FILE = "correcciones.json"
EDITABLE = ("segno", "coda", "to_coda", "fine", "jump", "repeat_start", "repeat_end", "volta", "volta_to",
            "multirest", "barline")
JUMPS = ("D.S. al Coda", "D.S. al Fine", "D.S.", "D.C. al Coda", "D.C. al Fine", "D.C.")


def load(run_dir: Path) -> dict:
    p = run_dir / FILE
    if not p.exists():
        return {"marks": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"marks": {}}
    data.setdefault("marks", {})
    return data


def save(run_dir: Path, data: dict) -> None:
    (run_dir / FILE).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _clean(field: str, value):
    if field in ("volta", "volta_to", "multirest"):
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n if n >= (2 if field == "multirest" else 1) else None
    if field == "jump":
        return value if value in JUMPS else None
    if field == "barline":
        return value if value in ("double", "final") else None
    return bool(value)


def apply(cs: ChoralScore, data: dict) -> list[Issue]:
    """Apply the saved answers to the voted score. Returns info issues describing them."""
    issues = []
    by_index = {m.index: m for m in cs.measures}
    changed_pickup = False
    for key, fields_ in (data.get("marks") or {}).items():
        try:
            m = by_index[int(key)]
        except (KeyError, ValueError):
            continue
        for field, value in fields_.items():
            if field in EDITABLE:
                setattr(m.marks, field, _clean(field, value))
        if m.marks.volta is None or (m.marks.volta_to or 0) <= m.marks.volta:
            m.marks.volta_to = None  # "1.ª a 1.ª vez" is just the 1st
        if m.marks.repeat_end:
            m.marks.barline = None
        if m.marks.multirest:
            # a silence of several measures: every voice rests, the whole bar
            m.voices = {v: [Event(Fraction(0), m.bar_length)] for v in VOICES}
            if m.pickup:
                m.pickup, changed_pickup = False, True
            m.duration = m.bar_length
        issues.append(Issue("estructura", "info", f"Compás {m.label}: signos corregidos a mano.", m.index))
    if changed_pickup:
        for m in cs.measures:
            m.number = m.index + 1
    return issues


def marks_json(marks: Marks) -> dict:
    out = {}
    for f in fields(Marks):
        v = getattr(marks, f.name)
        if f.name in ("dynamics", "wedges"):
            v = [[g, float(off), x] for g, off, x in v]
        out[f.name] = v
    return out


# --------------------------------------------------------------------------- note versions
#
#   {"voices": {"12": {"alto": "<version key>"}}}
#
# A version is identified by its notes (offset, pitch, duration, tie), so the answer stays
# valid when the result is rebuilt from the same readings.


def version_key(events) -> str:
    return json.dumps([[str(e.offset), e.pitch, str(e.duration), e.tie] for e in events if not e.filled])


def apply_voices(cs: ChoralScore, data: dict) -> set[int]:
    """Put the chosen versions in place. Returns the measures the user decided."""
    from ..synthesis.refine import _move_lyrics

    decided = set()
    by_index = {m.index: m for m in cs.measures}
    for key, choice in (data.get("voices") or {}).items():
        try:
            m = by_index[int(key)]
        except (KeyError, ValueError):
            continue
        for v, wanted in choice.items():
            alts = m.alternatives.get(v, [])
            alt = next((a for a in alts if version_key(a["events"]) == wanted), None)
            if alt is None:
                continue  # the readings changed: that version no longer exists
            m.voices[v] = _move_lyrics(m.voices.get(v, []), alt["events"])
            for a in alts:
                a["chosen"] = a is alt
            decided.add(m.index)
    return decided


# --------------------------------------------------------------------------- notes fixed by hand
#
#   {"edits": {"12": {"alto": {"3/2": "B-4", "2": {"pitch": "C5", "tie": true}}}}}
#
# The pitch the user gave to the note that starts at that offset (in quarter notes) of that
# voice, and optionally whether it is tied to the next note (a tie the engines missed, or one
# they invented). The rhythm is the one of the version in place; a note tied into the next
# measure takes its continuation along.

_PITCH = __import__("re").compile(r"^[A-G](#{1,2}|-{1,2})?\d$")


def apply_edits(cs: ChoralScore, data: dict) -> set[int]:
    """Put the pitches fixed by hand in place. Returns the measures edited."""
    from music21 import pitch as m21pitch

    edited = set()
    ms = cs.measures
    by_index = {m.index: k for k, m in enumerate(ms)}
    for key, per_voice in (data.get("edits") or {}).items():
        try:
            k = by_index[int(key)]
        except (KeyError, ValueError):
            continue
        m = ms[k]
        for v, notes in (per_voice or {}).items():
            for off, value in (notes or {}).items():
                name, tie = (value.get("pitch"), value.get("tie")) if isinstance(value, dict) else (value, None)
                if not isinstance(name, str) or not _PITCH.match(name):
                    continue
                try:
                    offset = Fraction(off)
                except (ValueError, ZeroDivisionError):
                    continue
                e = next((e for e in m.voices.get(v, []) if e.offset == offset and not e.is_rest), None)
                if e is None:
                    continue  # the rhythm changed since: that note is gone
                old = e.pitch
                _set_pitch(e, m21pitch.Pitch(name))
                edited.add(m.index)
                # a note tied across the barline: its continuation sounds the same
                j, cur = k, e
                while cur.tie in ("start", "continue") and j + 1 < len(ms):
                    j += 1
                    nxt = next((x for x in ms[j].voices.get(v, []) if not x.is_rest), None)
                    if nxt is None or nxt.offset != 0 or nxt.pitch != old or nxt.tie not in ("stop", "continue"):
                        break
                    _set_pitch(nxt, m21pitch.Pitch(name))
                    cur = nxt
                if isinstance(tie, bool):
                    _set_tie(ms, k, v, e, tie)
    return edited


def _next_note(ms, k: int, v: str, e: Event):
    """The note right after e in this voice: later in the measure, or opening the next one."""
    later = [x for x in ms[k].voices.get(v, []) if x.offset > e.offset]
    if later:
        return later[0] if not later[0].is_rest else None
    if k + 1 < len(ms):
        first = next(iter(ms[k + 1].voices.get(v, [])), None)
        if first is not None and first.offset == 0 and not first.is_rest:
            return first
    return None


def _set_tie(ms, k: int, v: str, e: Event, tied: bool) -> None:
    """Tie e to the next note (only to the same pitch: a tie joins one sound) or untie it."""
    has = e.tie in ("start", "continue")
    if tied == has:
        return
    nxt = _next_note(ms, k, v, e)
    if tied:
        if nxt is None or nxt.pitch != e.pitch:
            return
        e.tie = "continue" if e.tie == "stop" else "start"
        nxt.tie = "continue" if nxt.tie == "start" else "stop"
        nxt.lyrics = {}  # a tied note is not sung again: no syllable of its own
    else:
        e.tie = "stop" if e.tie == "continue" else None
        if nxt is not None and nxt.tie in ("stop", "continue"):
            nxt.tie = "start" if nxt.tie == "continue" else None


def _set_pitch(e: Event, p) -> None:
    e.pitch = p.nameWithOctave
    e.midi = int(p.midi)
    e.step = p.step
    e.alter = float(p.accidental.alter) if p.accidental else 0.0
