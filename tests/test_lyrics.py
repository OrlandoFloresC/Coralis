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
