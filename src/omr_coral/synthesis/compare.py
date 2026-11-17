"""Analysis by synthesis: where should the noteheads be, and are they there?

For a measure, the chosen version is "drawn" as the set of noteheads it implies:
one head per (onset, staff, staff step). The original image gives the heads that
are actually printed. Both are grouped into columns (same onset = same x), the
columns are aligned in order, and the similarity is the F1 score of matched heads:

    100%  every expected head is printed, and every printed head is explained
     low  a wrong pitch (head one step off), a missing or an extra note...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from ..model.score import VOICES
from .heads import Head, detect_heads

_DIATONIC = "CDEFGAB"
# diatonic index of the top staff line for each clef (C0 = 0)
_TOP_LINE = {"G": 3 + 7 * 5, "F": 5 + 7 * 3, "G8vb": 3 + 7 * 4, "C": 4 + 7 * 4}


def staff_step(pitch_name: str, clef: str) -> int:
    """Staff position of a pitch ("E-4", "F#3"): 0 = top line, +1 per line/space downwards."""
    m = re.fullmatch(r"([A-G])[#\-~`]*(\d+)", pitch_name)
    if not m:
        raise ValueError(f"Nombre de nota no reconocido: {pitch_name}")
    d = _DIATONIC.index(m.group(1)) + 7 * int(m.group(2))
    return _TOP_LINE.get(clef, _TOP_LINE["G"]) - d


@dataclass
class Geometry:
    """Where a measure is on a page image: enough to detect its heads."""
    image: Path
    x0: float
    x1: float
    staves: list[tuple[float, float]]  # (top line y, interline) per staff, top to bottom
    clefs: list[str]                   # clef of each staff in the original


@dataclass
class SynthResult:
    similarity: float
    expected: int
    detected: int
    matched: int
    missing: list[tuple[int, int, float, object]] = field(default_factory=list)  # (staff, step, x, onset)
    # Note: heads are compared by staff position only, so accidentals (si♭ vs si♮) are invisible here.
    extra: list[Head] = field(default_factory=list)
    found: list[Head] = field(default_factory=list)


@lru_cache(maxsize=16)
def _load(path: str) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"No se pudo leer {path}")
    return img


_heads_cache: dict[tuple, list[Head]] = {}


def detected_heads(geom: Geometry) -> list[Head]:
    key = (str(geom.image), round(geom.x0), round(geom.x1), tuple(geom.staves))
    if key not in _heads_cache:
        gray = _load(str(geom.image))
        heads: list[Head] = []
        for i, (top, il) in enumerate(geom.staves):
            heads += detect_heads(gray, top, il, int(geom.x0), int(geom.x1), staff_index=i)
        _heads_cache[key] = heads
    return _heads_cache[key]


def voice_staff_map(n_staves: int, clefs: list[str]) -> dict[str, int]:
    if n_staves >= 4:
        return {v: i for i, v in enumerate(VOICES)}
    if n_staves == 3:
        if clefs[1] == "G":
            return {"soprano": 0, "alto": 1, "tenor": 2, "bass": 2}
        return {"soprano": 0, "alto": 0, "tenor": 1, "bass": 2}
    if n_staves == 2:
        return {"soprano": 0, "alto": 0, "tenor": 1, "bass": 1}
    return {v: 0 for v in VOICES}


def expected_columns(voices: dict, geom: Geometry) -> list[tuple[float, set[tuple[int, int]]]]:
    vmap = voice_staff_map(len(geom.staves), geom.clefs)
    cols: dict = {}
    for v in VOICES:
        st = vmap[v]
        for e in voices.get(v, []):
            if e.is_rest or not e.pitch:
                continue
            cols.setdefault(e.offset, set()).add((st, staff_step(e.pitch, geom.clefs[st])))
    return sorted(cols.items())


def _columns(heads: list[Head], gap: float) -> list[list[Head]]:
    cols: list[list[Head]] = []
    for h in sorted(heads, key=lambda h: h.x):
        if cols and h.x - np.mean([c.x for c in cols[-1]]) < gap:
            cols[-1].append(h)
        else:
            cols.append([h])
    return cols


def compare(voices: dict, geom: Geometry) -> SynthResult:
    exp = expected_columns(voices, geom)
    heads = detected_heads(geom)
    il = float(np.mean([s[1] for s in geom.staves])) if geom.staves else 20.0
    det = _columns(heads, gap=1.6 * il)  # heads of a second sit side by side
    det_sets = [{(h.staff, h.step) for h in col} for col in det]

    n, m = len(exp), len(det)
    dp = np.zeros((n + 1, m + 1))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            tp = len(exp[i - 1][1] & det_sets[j - 1])
            dp[i, j] = max(dp[i - 1, j], dp[i, j - 1], dp[i - 1, j - 1] + tp)

    # backtrack to know which heads matched (for the report overlay)
    pairs = {}
    i, j = n, m
    while i > 0 and j > 0:
        tp = len(exp[i - 1][1] & det_sets[j - 1])
        if tp and dp[i, j] == dp[i - 1, j - 1] + tp:
            pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif dp[i, j] == dp[i - 1, j]:
            i -= 1
        else:
            j -= 1

    n_exp = sum(len(s) for _, s in exp)
    n_det = sum(len(s) for s in det_sets)
    matched = int(dp[n, m])
    res = SynthResult(0.0, n_exp, n_det, matched)
    used = set()
    width = max(1.0, geom.x1 - geom.x0)
    total = max([o for o, _ in exp] + [0]) or 1
    for ei, (off, steps) in enumerate(exp):
        dj = pairs.get(ei)
        for st_step in steps:
            hit = None
            if dj is not None:
                hit = next((h for h in det[dj] if (h.staff, h.step) == st_step), None)
            if hit:
                res.found.append(hit)
                used.add(id(hit))
            else:
                x = (np.mean([h.x for h in det[dj]]) if dj is not None
                     else geom.x0 + width * (0.1 + 0.8 * float(off) / float(total)))
                res.missing.append((st_step[0], st_step[1], float(x), off))
    res.extra = [h for col in det for h in col if id(h) not in used]
    if n_exp + n_det:
        res.similarity = 2 * matched / (n_exp + n_det)
    return res
