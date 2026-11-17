"""Phase 3: image variants, measure alignment and voting."""

import copy
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from omr_coral.config import load_config
from omr_coral.model.score import build_choral_score
from omr_coral.preprocess.variants import estimate_interline, estimate_skew, flatten_background, rotate
from omr_coral.voting.align import align
from omr_coral.voting.vote import Candidate, vote
from test_phase2 import SA, TB, _hymn, _write

CFG = load_config()


def _staff_image(interline=20, skew=0.0) -> np.ndarray:
    img = np.full((600, 1200), 255, np.uint8)
    for top in (100, 350):
        for k in range(5):
            y = top + k * interline
            cv2.line(img, (50, y), (1150, y), 0, 2)
    return rotate(img, skew) if skew else img


def test_deskew_finds_rotation():
    assert abs(estimate_skew(_staff_image(skew=1.5)) + 1.5) <= 0.2


def test_interline_estimate():
    assert estimate_interline(_staff_image(interline=20)) == 20


def test_flatten_background_removes_faint_marks():
    img = _staff_image()
    img[450:520, 300:500] = 200  # light-gray blotch, like bleed-through
    clean = flatten_background(img)
    assert clean[480, 400] == 255          # blotch gone
    assert clean[100, 600] < 100           # staff line kept


def _score(tmp_path, sa, name, tb=TB):
    d = tmp_path / name
    d.mkdir()
    return build_choral_score(_write(_hymn(sa, tb), d))


def test_alignment_skips_an_extra_measure(tmp_path):
    ref = _score(tmp_path, SA, "ref")
    extra = SA[:2] + [[(["C4", "F4"], 3)]] + SA[2:]
    other = _score(tmp_path, extra, "other", tb=TB[:2] + [[(["F2", "A3"], 3)]] + TB[2:])
    assert align(ref.measures, other.measures) == {0: 0, 1: 1, 2: 3, 3: 4}


def test_vote_majority_and_rules(tmp_path):
    good = _score(tmp_path, SA, "good")
    # wrong pitch in alto, measure 1 (still a valid measure: only the majority can fix it)
    wrong_pitch = [list(m) for m in SA]
    wrong_pitch[1] = [(["G4", "A4"], 2), (["C4", "F4"], 1)]
    # wrong rhythm in soprano, measure 2 (breaks the duration rule)
    wrong_rhythm = [list(m) for m in SA]
    wrong_rhythm[2] = [(["D4", "B-4"], 2), (["E4", "G4"], 1.5)]
    cands = [
        Candidate("a", "v1", good, Path(".")),
        Candidate("a", "v2", _score(tmp_path, wrong_pitch, "wp"), Path(".")),
        Candidate("b", "v1", _score(tmp_path, wrong_pitch, "wp2"), Path(".")),
        Candidate("b", "v2", _score(tmp_path, wrong_rhythm, "wr"), Path(".")),
        Candidate("b", "v3", _score(tmp_path, wrong_rhythm, "wr2"), Path(".")),
    ]
    voted, issues, _ = vote(cands, CFG)
    pitches = lambda k, v: [e.pitch for e in voted.measures[k].voices[v] if not e.is_rest]  # noqa: E731
    # measure 1: two readings say G4, three say F4 -> F4 wins
    assert pitches(1, "alto") == ["F4", "C4"]
    # measure 2: two readings break the rules, so the rule-abiding version wins
    assert [e.duration for e in voted.measures[2].voices["soprano"] if not e.is_rest] == [Fraction(2), Fraction(1)]
    assert voted.measures[1].votes["alto"]["weight"] == 3


def test_vote_flags_disagreement(tmp_path):
    a = [list(m) for m in SA]
    b = copy.deepcopy(a)
    b[0] = [(["F4", "B-4"], 2), (["E4", "G4"], 1)]
    c = copy.deepcopy(a)
    c[0] = [(["F4", "C5"], 2), (["E4", "G4"], 1)]
    cands = [Candidate("x", n, _score(tmp_path, s, n), Path(".")) for n, s in (("a", a), ("b", b), ("c", c))]
    _, issues, _ = vote(cands, CFG)
    assert any(i.rule == "votacion" and i.measure == 0 for i in issues)
