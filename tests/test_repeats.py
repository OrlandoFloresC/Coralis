"""Repeticiones desplegadas en el orden en que se cantan."""

from fractions import Fraction as Fr
from pathlib import Path

from omr_coral.model.repeats import performance_order
from omr_coral.model.score import VOICES, ChoralScore, Event, Marks, Measure
from omr_coral.model.verses import expand_verses


def _m(i, pitch="C4", lyrics=None, **marks):
    e = Event(Fr(0), Fr(3), pitch, 60)
    e.lyrics = lyrics or {}
    m = Measure(index=i, system=1, page=None, staves=[], time=(3, 4), bar_length=Fr(3), duration=Fr(3))
    m.voices = {v: [Event(Fr(0), Fr(3), pitch, 60, lyrics=dict(e.lyrics))] for v in VOICES}
    m.number, m.marks = i + 1, Marks(**marks)
    return m


def _order(*measures):
    steps, warnings = performance_order(ChoralScore(Path("x"), list(measures), []))
    return [s.index for s in steps], warnings


def test_plain_repeat():
    assert _order(_m(0), _m(1, repeat_start=True), _m(2, repeat_end=True), _m(3))[0] == [0, 1, 2, 1, 2, 3]


def test_repeat_with_endings():
    order, _ = _order(_m(0, repeat_start=True), _m(1, volta=1, repeat_end=True), _m(2, volta=2), _m(3))
    assert order == [0, 1, 0, 2, 3]


def test_repeat_without_start_sign_goes_back_to_the_beginning():
    assert _order(_m(0), _m(1, repeat_end=True), _m(2))[0] == [0, 1, 0, 1, 2]


def test_two_repeats_in_a_row():
    order, _ = _order(_m(0), _m(1, repeat_end=True), _m(2), _m(3, repeat_end=True))
    assert order == [0, 1, 0, 1, 2, 3, 2, 3]


def test_dal_segno_al_coda():
    order, warnings = _order(_m(0), _m(1, segno=True), _m(2, to_coda=True), _m(3, jump="D.S. al Coda"),
                             _m(4, coda=True), _m(5))
    assert order == [0, 1, 2, 3, 1, 2, 4, 5] and not warnings


def test_da_capo_al_fine_skips_repeats_and_takes_last_ending():
    order, _ = _order(_m(0, repeat_start=True), _m(1, volta=1, repeat_end=True), _m(2, volta=2, fine=True),
                      _m(3, jump="D.C. al Fine"))
    assert order == [0, 1, 0, 2, 3, 0, 2]


def test_missing_segno_is_not_invented():
    order, warnings = _order(_m(0), _m(1, jump="D.S. al Coda"), _m(2, coda=True))
    assert order == [0, 1, 2]
    assert warnings and "segno" in warnings[0][1]


def test_second_pass_sings_the_second_line():
    one = {1: ("Can", "single")}
    both = {1: ("pri", "single"), 2: ("se", "single")}
    cs = ChoralScore(Path("x"), [_m(0, lyrics=one), _m(1, lyrics=both, repeat_start=True),
                                 _m(2, lyrics=both, repeat_end=True)], [])
    out = expand_verses(cs)
    words = [m.voices["soprano"][0].lyrics.get(1, ("", ""))[0] for m in out.measures]
    assert words == ["Can", "pri", "pri", "se", "se"]  # one stanza, the repeat with its 2nd line


def test_two_dal_segno_each_with_its_own_segno_and_coda_and_repeats_inside_the_coda():
    order, warnings = _order(
        _m(0), _m(1, segno=True), _m(2, to_coda=True), _m(3, jump="D.S. al Coda"),
        _m(4, coda=True, repeat_start=True), _m(5, repeat_end=True),
        _m(6, segno=True), _m(7, to_coda=True), _m(8, jump="D.S. al Coda"), _m(9, coda=True))
    assert not warnings
    assert order == [0, 1, 2, 3, 1, 2, 4, 5, 4, 5, 6, 7, 8, 6, 7, 9]


def test_coda_sign_inside_the_passage_marks_where_to_leave():
    order, _ = _order(_m(0, segno=True), _m(1), _m(2, coda=True), _m(3, jump="D.S. al Coda"), _m(4, coda=True))
    assert order == [0, 1, 2, 3, 0, 1, 4]


def test_multirest_counts_as_several_measures():
    order, _ = _order(_m(0, multirest=3), _m(1))
    assert order == [0, 0, 0, 1]


def test_repeat_after_the_coda_goes_back_to_its_own_start_sign():
    # |: 0 1(segno) 2(to coda) 3 D.S. | 4 coda 5[1. :|] 6[2.]
    order, _ = _order(_m(0, repeat_start=True, segno=True), _m(1, to_coda=True), _m(2, jump="D.S. al Coda"),
                      _m(3, coda=True), _m(4, volta=1, repeat_end=True), _m(5, volta=2))
    assert order == [0, 1, 2, 0, 1, 3, 4, 0, 1, 2, 3, 5]


def test_missing_start_sign_after_an_ending_does_not_loop():
    # |: 0 [1. 1 :|] [2. 2] | 3 4 [1. 5 :|] [2. 6]   (the |: before 3 was not read)
    order, _ = _order(_m(0, repeat_start=True), _m(1, volta=1, repeat_end=True), _m(2, volta=2),
                      _m(3), _m(4), _m(5, volta=1, repeat_end=True), _m(6, volta=2))
    assert order == [0, 1, 0, 2, 3, 4, 5, 3, 4, 6]
