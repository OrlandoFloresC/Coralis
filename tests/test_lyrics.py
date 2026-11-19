"""Lyrics: sinalefa merging and slur-aware syllable slots."""

from fractions import Fraction as Fr
from pathlib import Path

from music21 import chord, clef, key, meter, spanner, stream

from omr_coral.model.lyrics_fix import merge_elisions
from omr_coral.model.score import ChoralScore, Event, Measure, build_choral_score


def _ev(off, dur, pitch, **lyrics):
    e = Event(Fr(off), Fr(dur), pitch, 60)
    e.lyrics = {int(k[1:]): v for k, v in lyrics.items()}
    return e


def _measure(sop):
    m = Measure(index=0, system=1, page=None, staves=[])
    m.voices = {"soprano": sop, "alto": [], "tenor": [], "bass": []}
    m.number = 11
    return m


def test_sinalefa_is_merged_on_the_shared_note():
    # verse 1: res(0) ca(2) ; verse 2: ho(0) ra(1.5) en(2)  -> "ra‿en" on beat 2
    sop = [
        _ev(0, 1.5, "D4", v1=("res", "begin"), v2=("ho", "begin")),
        _ev(1.5, 0.5, "F4", v2=("ra", "end")),
        _ev(2, 0.5, "F4", v1=("ca", "middle"), v2=("en", "single")),
        _ev(2.5, 0.5, "D4"),
    ]
    cs = ChoralScore(Path("x"), [_measure(sop)], [])
    issues = merge_elisions(cs)
    assert len(issues) == 1
    assert 2 not in sop[1].lyrics
    assert sop[2].lyrics[2] == ("ra‿en", "end")


def test_no_merge_without_vowels_meeting():
    sop = [
        _ev(0, 1, "C4", v1=("sol", "single"), v2=("con", "single")),
        _ev(1, 1, "D4", v2=("tar", "single")),
        _ev(2, 1, "E4", v1=("mi", "single"), v2=("des", "single")),
    ]
    cs = ChoralScore(Path("x"), [_measure(sop)], [])
    assert merge_elisions(cs) == []


def test_slur_marks_melisma(tmp_path):
    s = stream.Score()
    p1, p2 = stream.Part(), stream.Part()
    m1 = stream.Measure(number=1)
    m1.insert(0, clef.TrebleClef())
    m1.insert(0, key.KeySignature(-1))
    m1.insert(0, meter.TimeSignature("3/4"))
    d = chord.Chord(["B-3", "D4"], quarterLength=1.5)
    f1 = chord.Chord(["G3", "F4"], quarterLength=0.5)
    f2 = chord.Chord(["G3", "F4"], quarterLength=1)
    for n in (d, f1, f2):
        m1.append(n)
    p1.append(m1)
    m2 = stream.Measure(number=1)
    m2.insert(0, clef.BassClef())
    m2.append(chord.Chord(["B-2", "F3"], quarterLength=3))
    p2.append(m2)
    p1.insert(0, spanner.Slur(d, f1))
    s.insert(0, p1)
    s.insert(0, p2)
    path = tmp_path / "slur.musicxml"
    s.write("musicxml", fp=str(path), makeNotation=False)
    cs = build_choral_score(path)
    sop = cs.measures[0].voices["soprano"]
    assert [e.takes_syllable for e in sop if not e.is_rest] == [True, False, True]


def test_glued_ocr_syllables_are_spread_over_the_empty_notes():
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.model.lyrics_fix import split_glued_syllables
    from omr_coral.model.score import VOICES, ChoralScore, Event, Measure

    m = Measure(index=0, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(4))
    m.voices = {v: [Event(Fr(i), Fr(1), "C4") for i in range(4)] for v in VOICES}
    s = m.voices["soprano"]
    s[0].lyrics = {1: ("to", "begin")}
    s[1].lyrics = {1: ("daslaspro", "end")}
    a = m.voices["alto"]
    a[0].lyrics = {1: ("doen", "single")}   # a sinalefa without its mark: kept on one note
    split_glued_syllables(ChoralScore(Path("x"), [m], []))
    assert [e.lyrics.get(1, ("",))[0] for e in s] == ["to", "das", "las", "pro"]
    assert [e.lyrics.get(1, ("",))[0] for e in a] == ["doen", "", "", ""]


def test_ocr_apostrophe_and_il_for_ll():
    from omr_coral.model.lyrics_fix import fix_ocr_letters

    assert fix_ocr_letters("p’e") == "pe"            # «Cuando suene la trompeta»
    assert fix_ocr_letters("Ilan") == "llan"         # «Cuando la pena»: «llan-to»
    assert fix_ocr_letters("(Ilamen") == "(llamen"
    assert fix_ocr_letters("Iglesia") == "Iglesia"
    assert fix_ocr_letters("Ilu") == "Ilu"           # «I-lu-mi-na»: a real "Il"
