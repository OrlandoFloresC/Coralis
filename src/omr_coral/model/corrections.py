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
EDITABLE = ("segno", "coda", "to_coda", "fine", "jump", "repeat_start", "repeat_end", "volta", "multirest", "barline")
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
    if field in ("volta", "multirest"):
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n if n >= (1 if field == "volta" else 2) else None
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
