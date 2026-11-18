"""Endings that cover several times through ("1.-6." ... "7.")."""

from fractions import Fraction as Fr
from pathlib import Path

from omr_coral.model.repeats import performance_order
from omr_coral.model.score import VOICES, ChoralScore, Event, Measure, _ending_number
from omr_coral.voting.vote import _fix_endings


def _m(i, **marks):
    m = Measure(index=i, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(4))
    m.voices = {v: [Event(Fr(0), Fr(4), "C4")] for v in VOICES}
    for k, v in marks.items():
        setattr(m.marks, k, v)
    return m


def test_audiveris_ending_text_is_read_as_a_range():
    assert _ending_number("1,,6") == "1-6"   # "1.-6." as Audiveris writes it
    assert _ending_number("1, 2") == "1-2"
    assert _ending_number("2") == "2"
    assert _ending_number("1, 2, 4") == "1, 2, 4"


def test_ending_one_to_six_is_sung_six_times_and_the_next_is_the_seventh():
    ms = [_m(0), _m(1, repeat_start=True), _m(2, volta=1, volta_to=6, repeat_end=True), _m(3, volta=2), _m(4)]
    cs = ChoralScore(Path("x"), ms, [])
    _fix_endings(cs)
    assert (ms[3].marks.volta, ms[3].marks.volta_to) == (7, None)
    steps, warnings = performance_order(cs)
    assert [s.index for s in steps] == [0] + [1, 2] * 6 + [1, 3, 4]
    assert not warnings


def test_a_stray_mark_is_not_a_second_stanza():
    from omr_coral.model.repeats import lyric_line, performance_order

    ms = [_m(i) for i in range(10)]
    for m in ms:
        for v in VOICES:
            m.voices[v][0].lyrics = {1: ("la", "single")}
    ms[5].voices["soprano"][0].lyrics[2] = ("A ^", "single")
    cs = ChoralScore(Path("x"), ms, [])
    assert lyric_line(cs, performance_order(cs)[0])["stanzas"] == 1


def test_a_chorus_printed_once_is_sung_with_every_stanza():
    from omr_coral.model.verses import expand_verses

    ms = [_m(i) for i in range(8)]
    for i, m in enumerate(ms):
        for v in VOICES:
            m.voices[v][0].lyrics = ({1: (f"a{i}", "single"), 2: (f"b{i}", "single")} if i < 3
                                     else {1: (f"coro{i}", "single")})
    out = expand_verses(ChoralScore(Path("x"), ms, []))
    words = [m.voices["soprano"][0].lyrics.get(1, ("-",))[0] for m in out.measures]
    chorus = [f"coro{i}" for i in range(3, 8)]
    assert words == ["a0", "a1", "a2"] + chorus + ["-"] + ["b0", "b1", "b2"] + chorus


def test_an_ending_of_many_times_over_a_long_passage():
    body = [_m(i) for i in range(1, 31)]
    body[0].marks.repeat_start = True
    last = _m(31, volta=1, volta_to=12, repeat_end=True)
    cs = ChoralScore(Path("x"), [_m(0)] + body + [last, _m(32, volta=13)], [])
    steps, _ = performance_order(cs)
    assert [s.index for s in steps].count(31) == 12
    assert [s.index for s in steps][-1] == 32
