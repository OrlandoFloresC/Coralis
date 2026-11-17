"""Phase 5: verses written out, lyrics from a text file, evaluation."""

from fractions import Fraction as Fr
from pathlib import Path

from omr_coral.evaluate import score_against
from omr_coral.model.lyrics_text import apply_lyrics_text, place_verse, read_lyrics_file, syllabify, verse_syllables
from omr_coral.model.score import VOICES, ChoralScore, Event, Measure
from omr_coral.model.verses import expand_verses, merge_split_measures


def _m(index, voices, pickup=False, duration=Fr(3)):
    m = Measure(index=index, system=1, page=None, staves=[], time=(3, 4), bar_length=Fr(3),
                duration=duration, pickup=pickup)
    m.voices = voices
    return m


def _note(off, dur, pitch, **lyr):
    e = Event(Fr(off), Fr(dur), pitch, 60)
    e.lyrics = {int(k[1:]): (t, "single") for k, t in lyr.items()}
    return e


def _hymn() -> ChoralScore:
    pick = {v: [_note(0, 1, "C4", v1="Su", v2="Mi") if v == "soprano" else _note(0, 1, "C3")] for v in VOICES}
    mid = {v: [_note(0, 2, "F4", v1="bli", v2="co"), _note(2, 1, "A4", v1="me", v2="ra")]
           if v == "soprano" else [_note(0, 2, "F3"), _note(2, 1, "F3")] for v in VOICES}
    end = {v: [_note(0, 2, "F4", v1="ver", v2="él")] if v == "soprano" else [_note(0, 2, "F3")] for v in VOICES}
    return ChoralScore(Path("x"), [_m(0, pick, pickup=True, duration=Fr(1)), _m(1, mid), _m(2, end, duration=Fr(2))],
                       [])


def test_verses_written_out_like_the_user_does():
    out = expand_verses(_hymn())
    # verse 1 (3 bars) + silent bar + verse 2 (3 bars)
    assert len(out.measures) == 7
    first = out.measures[0].voices["soprano"]
    assert [(e.pitch, e.duration) for e in first] == [(None, 1), (None, 1), ("C4", 1)]  # R R C4
    assert first[2].lyrics == {1: ("Su", "single")}
    assert out.measures[0].voices["bass"][2].lyrics == {1: ("Su", "single")}  # every voice sings it
    assert [(e.pitch, e.duration) for e in out.measures[2].voices["alto"]] == [("F3", 2), (None, 1)]
    assert all(e.is_rest for v in VOICES for e in out.measures[3].voices[v])  # the silent bar
    assert out.measures[4].voices["soprano"][2].lyrics == {1: ("Mi", "single")}


def test_spanish_syllables():
    cases = {"Sublime": "Su-bli-me", "corazón": "co-ra-zón", "enterneció": "en-ter-ne-ció",
             "guía": "guí-a", "perdido": "per-di-do", "instante": "ins-tan-te", "guerra": "gue-rra",
             "Su-bli-me": "Su-bli-me", "doquier": "do-quier", "busquen": "bus-quen",
             "alguien": "al-guien", "seguir": "se-guir", "agua": "a-gua"}
    for word, expected in cases.items():
        assert "-".join(syllabify(word)) == expected


def test_lyrics_file(tmp_path):
    f = tmp_path / "letra.txt"
    f.write_text("1. ¡Sublime gracia!\n\n2) Mi corazón\n", encoding="utf-8")
    verses = read_lyrics_file(f)
    assert [s.text for s in verses[0]] == ["¡Su", "bli", "me", "gra", "cia!"]
    assert [s.text for s in verses[1]] == ["Mi", "co", "ra", "zón"]


def test_placement_merges_sinalefa_and_skips_melisma():
    slots = [_note(i, 1, "C4") for i in range(4)]
    syls = verse_syllables("ho-ra en que")  # 4 syllables, 3 sung notes + 1 melisma
    sung = [True, True, False, True]
    placed = place_verse(slots, [None] * 4, syls, sung)
    assert [(j, t) for j, t, _ in placed] == [(0, "ho"), (1, "ra‿en"), (3, "que")]


def test_score_against():
    gt = expand_verses(_hymn())
    rec = expand_verses(_hymn())
    rec.measures[1].voices["soprano"][1].pitch = "G4"  # one wrong note
    res = score_against(rec, gt)
    assert res["measures_perfect"] == res["measures"] - 1
    assert 90 < res["notes_pct"] < 100


def test_measure_cut_by_system_break_is_joined():
    # 3/4: "...ver" (2 beats, end of system 1) | new system: "Mi" (1 beat) | next bar
    end = {v: [_note(0, 2, "F4", v1="ver"), Event(Fr(2), Fr(1), filled=True)] for v in VOICES}
    upbeat = {v: [_note(0, 1, "C4", v1="Mi"), Event(Fr(1), Fr(2), filled=True)] for v in VOICES}
    full = {v: [_note(0, 3, "F4", v1="co")] for v in VOICES}
    ms = [_m(0, end), _m(1, upbeat), _m(2, full)]
    ms[1].system = ms[2].system = 2
    out = merge_split_measures(ChoralScore(Path("x"), ms, []))
    assert len(out.measures) == 2
    sop = out.measures[0].voices["soprano"]
    assert [(e.pitch, e.offset, e.duration) for e in sop] == [("F4", 0, 2), ("C4", 2, 1)]
    assert sop[1].lyrics == {1: ("Mi", "single")}
    assert [m.number for m in out.measures] == [1, 2]
    # a full bar at the start of a system is left alone
    ms2 = [_m(0, full), _m(1, full)]
    ms2[1].system = 2
    assert len(merge_split_measures(ChoralScore(Path("x"), ms2, [])).measures) == 2


def test_lyrics_file_goes_to_the_men_where_the_women_are_silent():
    women = {"soprano": [_note(0, 3, "C5")], "alto": [_note(0, 3, "A4")],
             "tenor": [_note(0, 3, "F3")], "bass": [_note(0, 3, "F2")]}
    men = {"soprano": [Event(Fr(0), Fr(3))], "alto": [Event(Fr(0), Fr(3))],
           "tenor": [_note(0, 1, "C4"), _note(1, 1, "D4"), _note(2, 1, "E4")],
           "bass": [_note(0, 1, "C3"), _note(1, 1, "D3"), _note(2, 1, "E3")]}
    cs = ChoralScore(Path("x"), [_m(0, women), _m(1, men)], [])
    apply_lyrics_text(cs, [verse_syllables("Dios es san-to")])
    assert cs.measures[0].voices["soprano"][0].lyrics[1][0] == "Dios"
    assert [e.lyrics[1][0] for e in cs.measures[1].voices["tenor"]] == ["es", "san", "to"]
    assert [e.lyrics[1][0] for e in cs.measures[1].voices["bass"]] == ["es", "san", "to"]
