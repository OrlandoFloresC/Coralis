"""Measure-by-measure alignment between two readings of the same score.

Readings can differ in measure count (a missed barline, a measure split in two),
so measures are aligned with a Needleman-Wunsch dynamic program over a musical
similarity, like aligning two sentences word by word.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from ..model.score import VOICES, Measure

GAP = -0.25        # cost of leaving a measure unmatched
MATCH_BIAS = -0.25  # a match must be better than ~0 similarity to beat a gap


def _seq(m: Measure, v: str):
    return [(e.pitch, e.duration) for e in m.voices.get(v, []) if not e.is_rest]


def measure_similarity(a: Measure, b: Measure) -> float:
    total = 0.0
    for v in VOICES:
        x, y = _seq(a, v), _seq(b, v)
        if not x and not y:
            total += 1.0
        else:
            total += SequenceMatcher(None, x, y, autojunk=False).ratio()
    return total / len(VOICES)


def align(ref: list[Measure], other: list[Measure]) -> dict[int, int]:
    """Map ref measure index -> other measure index for matched pairs."""
    n, m = len(ref), len(other)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[0] * (m + 1) for _ in range(n + 1)]  # 0 diag, 1 up (skip ref), 2 left (skip other)
    for i in range(1, n + 1):
        score[i][0], move[i][0] = i * GAP, 1
    for j in range(1, m + 1):
        score[0][j], move[0][j] = j * GAP, 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = score[i - 1][j - 1] + measure_similarity(ref[i - 1], other[j - 1]) + MATCH_BIAS
            up = score[i - 1][j] + GAP
            left = score[i][j - 1] + GAP
            best = max(diag, up, left)
            score[i][j] = best
            move[i][j] = 0 if best == diag else (1 if best == up else 2)
    pairs: dict[int, int] = {}
    i, j = n, m
    while i > 0 or j > 0:
        mv = move[i][j]
        if i > 0 and j > 0 and mv == 0:
            pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif i > 0 and (j == 0 or mv == 1):
            i -= 1
        else:
            j -= 1
    return pairs
