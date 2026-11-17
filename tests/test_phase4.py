"""Phase 4: notehead detection and comparison with the image."""

from fractions import Fraction as Fr
from pathlib import Path

import cv2
import numpy as np

from omr_coral.model.score import Event
from omr_coral.synthesis.compare import Geometry, compare, staff_step
from omr_coral.synthesis.heads import detect_heads

IL = 20       # interline in px
TOP = 100     # y of the top staff line


def _page(heads: list[tuple[int, int, bool]]) -> np.ndarray:
    """A 5-line staff with heads at (x, step, filled)."""
    img = np.full((300, 600), 255, np.uint8)
    for k in range(5):
        cv2.line(img, (10, TOP + k * IL), (590, TOP + k * IL), 0, 2)
    for x, step, filled in heads:
        y = TOP + step * IL // 2
        cv2.ellipse(img, (x, y), (int(0.65 * IL), int(0.45 * IL)), -20, 0, 360, 0,
                    thickness=-1 if filled else 3)
        cv2.line(img, (x + int(0.6 * IL), y), (x + int(0.6 * IL), y - 3 * IL), 0, 2)  # stem
    return img


def test_staff_step():
    assert staff_step("F5", "G") == 0      # top line, treble
    assert staff_step("E-4", "G") == 8     # bottom line, treble (flat does not move it)
    assert staff_step("C4", "G") == 10     # first ledger line below
    assert staff_step("A3", "F") == 0      # top line, bass
    assert staff_step("G2", "F") == 8      # bottom line, bass


def test_detects_filled_and_hollow_heads_on_lines_and_spaces():
    wanted = [(100, 3, True), (200, 4, False), (300, 8, True), (400, 10, False), (500, 1, True)]
    heads = detect_heads(_page(wanted), TOP, IL, 30, 590)
    assert sorted((round(h.x / 100) * 100, h.step) for h in heads) == [(x, s) for x, s, _ in wanted]


def test_detects_stacked_chord():
    img = _page([(200, 4, True), (200, 6, True)])  # a third: heads touch
    heads = detect_heads(img, TOP, IL, 30, 590)
    assert sorted(h.step for h in heads) == [4, 6]


def _ev(off, pitch):
    return Event(Fr(off), Fr(1), pitch, 60)


def test_compare_prefers_the_version_that_matches(tmp_path: Path):
    # treble staff: heads at steps 3 (C5), 6 (G4), 5 (A4)
    img = _page([(150, 3, True), (300, 6, True), (450, 5, True)])
    path = tmp_path / "p.png"
    cv2.imwrite(str(path), img)
    geom = Geometry(path, 60, 590, [(TOP, IL)], ["G"])
    right = {"soprano": [_ev(0, "C5"), _ev(1, "G4"), _ev(2, "A4")], "alto": []}
    wrong = {"soprano": [_ev(0, "C5"), _ev(1, "F4"), _ev(2, "A4")], "alto": []}  # one step off
    r_ok, r_bad = compare(right, geom), compare(wrong, geom)
    assert r_ok.similarity == 1.0
    assert r_bad.similarity < r_ok.similarity
    assert [(s, st) for s, st, _, _ in r_bad.missing] == [(0, 7)]
