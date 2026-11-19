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


def _words(m, offset_line_text):
    """Put syllables on the soprano: [(offset, line, text)]; the soprano gets one note per offset."""
    offs = sorted({o for o, _, _ in offset_line_text})
    m.voices = {v: [Event(Fr(o), Fr(1), "C4") for o in offs] + ([Event(Fr(offs[-1] + 1), Fr(4) - Fr(offs[-1] + 1))]
                if offs[-1] + 1 < 4 else []) for v in VOICES}
    for o, n, t in offset_line_text:
        for v in VOICES:
            next(e for e in m.voices[v] if e.offset == o).lyrics[n] = (t, "single")


def test_final_first_and_second_endings_without_repeat_sign_go_back_to_the_start():
    # «¿Cómo podré estar triste?»: stanzas stacked, "1." and "2." at the end, no :| printed
    ms = [_m(0), _m(1), _m(2, volta=1), _m(3, volta=2)]
    cs = ChoralScore(Path("x"), ms, [])
    _fix_endings(cs)
    assert [m.marks.volta for m in ms] == [None, None, 1, 2]
    assert [s.index for s in performance_order(cs)[0]] == [0, 1, 2, 0, 1, 3]
    # endings in the middle with no :| are still a misreading
    ms = [_m(0, volta=1), _m(1, volta=2), _m(2), _m(3)]
    cs = ChoralScore(Path("x"), ms, [])
    _fix_endings(cs)
    assert [m.marks.volta for m in ms] == [None] * 4


def test_a_line_repeating_line_1_is_not_a_stanza():
    from omr_coral.model.repeats import drop_echo_lines

    ms = [_m(i) for i in range(6)]
    for i in range(4):
        _words(ms[i], [(0, 1, f"a{i}"), (0, 2, f"b{i}"), (1, 1, f"c{i}"), (1, 2, f"d{i}")])
    for i in (4, 5):  # the men's words in the chorus: the same as line 1, on line 3
        _words(ms[i], [(0, 1, "Fe"), (0, 3, "Fe"), (1, 1, "liz"), (1, 3, "liz")])
    cs = ChoralScore(Path("x"), ms, [])
    assert drop_echo_lines(cs) == [3]
    assert cs.verses == 2


def test_one_chorus_text_printed_on_two_lines_is_sung_by_every_stanza():
    from omr_coral.model.verses import expand_verses

    ms = [_m(i) for i in range(7)]
    for i in range(2):
        _words(ms[i], [(0, 1, f"uno{i}"), (0, 2, f"dos{i}")])
    # chorus: «Feliz cantando alegre,» on line 1, «yo vivo» lower (line 2), line 1 again
    _words(ms[2], [(0, 1, "Fe"), (1, 1, "liz")])
    _words(ms[3], [(0, 1, "a"), (1, 1, "le"), (2, 2, "yo")])
    _words(ms[4], [(0, 2, "vi"), (1, 2, "vo")])
    _words(ms[5], [(0, 1, "si"), (1, 1, "él")])
    _words(ms[6], [(0, 1, "cui"), (1, 1, "da")])
    out = expand_verses(ChoralScore(Path("x"), ms, []))
    sung = [[e.lyrics[1][0] for e in m.voices["soprano"] if e.lyrics] for m in out.measures]
    assert sung[3] == ["a", "le", "yo"] and sung[4] == ["vi", "vo"]          # stanza 1
    assert sung[8 + 3] == ["a", "le", "yo"] and sung[8 + 4] == ["vi", "vo"]  # stanza 2, same chorus
    assert sung[8] == ["dos0"]


def test_men_answering_with_their_own_words_is_not_a_second_stanza():
    # «Cuando la pena»: one stanza; from bar 9 on the basses answer with other words (line 2,
    # on other notes). Stanzas printed after a chorus lie under the same notes: they stay.
    from omr_coral.model.repeats import split_part_lines

    def piece(answer_offsets):
        ms = [_m(i) for i in range(12)]
        for i in range(8):
            _words(ms[i], [(0, 1, f"a{i}"), (1, 1, f"b{i}")])
        for i in range(8, 12):
            _words(ms[i], [(0, 1, f"c{i}")] + [(o, 2, f"d{i}{o}") for o in answer_offsets])
        return ChoralScore(Path("x"), ms, [])

    cs = piece([2, 3])
    assert split_part_lines(cs) == [2]
    assert cs.verses == 1
    m = cs.measures[9]
    assert [e.lyrics[1][0] for e in m.voices["soprano"] if e.lyrics] == ["c9"]
    assert [e.lyrics[1][0] for e in m.voices["bass"] if e.lyrics] == ["d92", "d93"]
    stacked = piece([0])
    assert split_part_lines(stacked) == [] and stacked.verses == 2


def test_chorus_upbeat_on_line_2_and_alto_echo_are_sung_by_every_stanza():
    # «El camino es escabroso»: the chorus upbeat «Muy can-» is printed on line 2 only, and in
    # the chorus the soprano holds a note while the alto echoes «(muy can-sa-dos)»
    from omr_coral.model.verses import expand_verses

    ms = [_m(i) for i in range(6)]
    for i in range(1):
        _words(ms[i], [(0, 1, "uno"), (0, 2, "dos")])
    _words(ms[1], [(0, 1, "án?"), (0, 2, "án!"), (3, 2, "Muy")])
    for i in range(2, 6):
        _words(ms[i], [(0, 1, f"sa{i}")])
        for v in ("alto", "tenor", "bass"):  # the echo: notes at 1 and 2 while the soprano holds
            ms[i].voices[v] = [Event(Fr(0), Fr(1), "C4", lyrics={1: (f"sa{i}", "single")}),
                               Event(Fr(1), Fr(1), "C4", lyrics={1: ("muy", "single")}),
                               Event(Fr(2), Fr(2), "C4", lyrics={1: ("can", "single")})]
        ms[i].voices["soprano"] = [Event(Fr(0), Fr(4), "E4", lyrics={1: (f"sa{i}", "single")})]
    out = expand_verses(ChoralScore(Path("x"), ms, []))
    sung = lambda m, v: [e.lyrics[1][0] for e in m.voices[v] if e.lyrics]
    for start in (0, 7):  # stanza 1, and stanza 2 after its silent measure
        assert sung(out.measures[start + 1], "soprano")[-1] == "Muy"
        assert sung(out.measures[start + 2], "alto") == ["sa2", "muy", "can"]
