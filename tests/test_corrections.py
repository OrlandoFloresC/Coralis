"""Respuestas del usuario en la revisión de signos."""

from fractions import Fraction as Fr
from pathlib import Path

from omr_coral.model import corrections
from omr_coral.model.repeats import performance_order
from omr_coral.model.score import VOICES, ChoralScore, Event, Measure


def _m(i, pickup=False):
    m = Measure(index=i, system=1, page=None, staves=[], time=(3, 4), bar_length=Fr(3),
                duration=Fr(1) if pickup else Fr(3), pickup=pickup)
    m.voices = {v: [Event(Fr(0), m.duration, "C4", 60)] for v in VOICES}
    m.number = i if pickup else i + 1
    return m


def test_answers_are_saved_and_applied(tmp_path: Path):
    cs = ChoralScore(Path("x"), [_m(0, pickup=True), _m(1), _m(2), _m(3)], [])
    corrections.save(tmp_path, {"marks": {"0": {"multirest": 4}, "1": {"segno": True},
                                          "2": {"to_coda": True, "jump": "D.S. al Coda"}, "3": {"coda": True},
                                          "9": {"segno": True}}})          # a measure that no longer exists
    corrections.apply(cs, corrections.load(tmp_path))
    first = cs.measures[0]
    assert first.marks.multirest == 4 and not first.pickup                # was read as a pickup
    assert all(e.is_rest for evs in first.voices.values() for e in evs)
    order, warnings = performance_order(cs)
    assert not warnings
    assert [s.index for s in order] == [0, 0, 0, 0, 1, 2, 1, 2, 3]


def test_unknown_values_are_ignored(tmp_path: Path):
    cs = ChoralScore(Path("x"), [_m(0), _m(1)], [])
    corrections.apply(cs, {"marks": {"0": {"jump": "Salta por ahí", "volta": "x", "segno": 1}}})
    assert cs.measures[0].marks.jump is None and cs.measures[0].marks.volta is None
    assert cs.measures[0].marks.segno is True


def test_chosen_note_version_replaces_the_voted_one_and_keeps_the_syllable():
    m = _m(0)
    voted_ev = [Event(Fr(0), Fr(3), "A4", 69, lyrics={1: ("Dios", "single")})]
    other = [Event(Fr(0), Fr(3), "B-4", 70)]
    m.voices["soprano"] = voted_ev
    m.alternatives["soprano"] = [{"events": voted_ev, "weight": 5, "sources": ["a"], "chosen": True},
                                 {"events": other, "weight": 3, "sources": ["b"], "chosen": False}]
    cs = ChoralScore(Path("x"), [m], [])
    decided = corrections.apply_voices(cs, {"voices": {"0": {"soprano": corrections.version_key(other)}}})
    assert decided == {0}
    sop = cs.measures[0].voices["soprano"]
    assert sop[0].pitch == "B-4" and sop[0].lyrics == {1: ("Dios", "single")}
    assert [a["chosen"] for a in m.alternatives["soprano"]] == [False, True]


def test_version_that_no_longer_exists_is_ignored():
    cs = ChoralScore(Path("x"), [_m(0)], [])
    assert corrections.apply_voices(cs, {"voices": {"0": {"soprano": "[]"}}}) == set()
